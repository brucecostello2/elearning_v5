"""AD-04 seam 1 — certification-export receiver (POST /ad01/v1/certified-models)."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from shared.config import settings
from shared.models.model_store import (
    Model,
    ModelApproval,
    ModelEngine,
    ModelStage,
    ModelState,
)

pytestmark = pytest.mark.asyncio

URL = "/ad01/v1/certified-models"


def _svc() -> dict[str, str]:
    return {"X-Service-Token": settings.IVGS_MBCP_INGEST_TOKEN}


def _bundle(**o) -> dict:
    b = {
        "certification_id": str(uuid.uuid4()),
        "model_id": str(uuid.uuid4()),
        "model_name": f"mbcp-model-{uuid.uuid4().hex[:8]}",
        "ivgs_stage": "storyboard",
        "weight_tier": "certified",
        "bundle_digest": "a" * 64,
        "bundle_manifest_url": "https://mbcp/weights/xyz/manifest?tier=certified",
        "engine_version": "vllm-0.6.3",
        "provenance": {"engine_image_digest": "sha256:abc", "cuda_version": "12.4"},
        "quality_summary": {"gate_passed": True, "score": 0.91},
        "certified_at": "2026-07-06T00:00:00Z",
        "certified_by": "mbcp",
    }
    b.update(o)
    return b


class TestAuth:
    async def test_missing_token_401(self, client: AsyncClient):
        r = await client.post(URL, json=_bundle())
        assert r.status_code == 401

    async def test_bad_token_401(self, client: AsyncClient):
        r = await client.post(URL, json=_bundle(), headers={"X-Service-Token": "no"})
        assert r.status_code == 401


class TestIngest:
    async def test_creates_candidate_engine_derived(self, client: AsyncClient, db_session):
        r = await client.post(URL, json=_bundle(), headers=_svc())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["created"] is True
        assert body["state"] == "candidate"
        assert body["ad01_id"]  # MBCP reads this

        model = await db_session.get(Model, body["ad01_id"])
        assert model.state == ModelState.CANDIDATE
        assert model.stage == ModelStage.STORYBOARD_GENERATION
        assert model.engine == ModelEngine.VLLM  # derived from stage
        assert model.weights_ref.endswith("/manifest?tier=certified")
        assert model.weights_checksum == "a" * 64
        assert model.vram_gb is None  # not supplied by the lean bundle
        assert model.default_params["engine_version"] == "vllm-0.6.3"
        assert model.default_params["provenance"]["cuda_version"] == "12.4"

        appr = (
            await db_session.execute(
                select(ModelApproval).where(ModelApproval.model_id == model.id)
            )
        ).scalars().all()
        assert len(appr) == 1
        assert appr[0].checklist["gate_passed"] is True

    async def test_supplied_full_contract_fields_win(self, client: AsyncClient, db_session):
        # SSOT full-contract fields present -> preferred over stage derivation.
        r = await client.post(
            URL,
            json=_bundle(engine="comfyui", measured_vram_gb=42.5,
                         license="llama-community", quantization="fp8"),
            headers=_svc(),
        )
        assert r.status_code == 201, r.text
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert model.engine == ModelEngine.COMFYUI  # supplied wins over vllm default
        assert float(model.vram_gb) == pytest.approx(42.5)
        assert model.license == "llama-community"
        assert model.default_params["quantization"] == "fp8"

    async def test_composition_stage_maps(self, client: AsyncClient):
        # Frozen taxonomy includes composition; requires a supplied engine.
        r = await client.post(
            URL, json=_bundle(ivgs_stage="composition", engine="comfyui"), headers=_svc()
        )
        assert r.status_code == 201, r.text

    async def test_unknown_stage_422(self, client: AsyncClient):
        r = await client.post(URL, json=_bundle(ivgs_stage="bogus"), headers=_svc())
        assert r.status_code == 422

    async def test_replay_same_certification_is_deduped(self, client: AsyncClient, db_session):
        b = _bundle()
        r1 = await client.post(URL, json=b, headers=_svc())
        assert r1.json()["created"] is True
        r2 = await client.post(URL, json=b, headers=_svc())  # identical replay
        assert r2.status_code == 201
        assert r2.json()["created"] is False
        assert r2.json()["ad01_id"] == r1.json()["ad01_id"]
        n = (
            await db_session.execute(
                select(func.count()).select_from(ModelApproval).where(
                    ModelApproval.vetting_reference == b["certification_id"]
                )
            )
        ).scalar_one()
        assert n == 1  # no duplicate attestation

    async def test_recertification_upserts(self, client: AsyncClient, db_session):
        name = f"recert-{uuid.uuid4().hex[:8]}"
        r1 = await client.post(URL, json=_bundle(model_name=name), headers=_svc())
        mid = r1.json()["ad01_id"]
        r2 = await client.post(
            URL, json=_bundle(model_name=name, bundle_digest="b" * 64), headers=_svc()
        )
        assert r2.json()["created"] is False
        assert r2.json()["ad01_id"] == mid  # same model row
        count = (
            await db_session.execute(
                select(func.count()).select_from(Model).where(
                    Model.name == name
                )
            )
        ).scalar_one()
        assert count == 1
        model = await db_session.get(Model, mid)
        await db_session.refresh(model)
        assert model.weights_checksum == "b" * 64
        appr = (
            await db_session.execute(
                select(func.count()).select_from(ModelApproval).where(
                    ModelApproval.model_id == mid
                )
            )
        ).scalar_one()
        assert appr == 2  # trail preserved
