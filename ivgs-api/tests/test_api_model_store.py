"""AD-01 Model Store + planner API tests (ARCH-1 Tarball 1).

Covers: registration (CANDIDATE, dup-name 409, RBAC), attestation-gated
approval (AD-01.7.2), deprecate/retire chain, is_default swap + APPROVED
gate, availability upsert, plan endpoint (selection + rationale, tier=both
rejection, PlanningError -> 422), manual override (AD-01.8.4) + validations.
"""
import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


REGISTER_BODY = {
    "name": "latentsync-1.5",
    "display_name": "LatentSync 1.5",
    "stage": "talking_head",
    "engine": "latentsync",
    "tier": "both",
    "vram_gb": 16.0,
    "capability_tags": [
        {"dimension": "visual_style", "value": "photorealistic", "weight": 1.0},
        {"dimension": "motion_profile", "value": "subtle", "weight": 0.5},
    ],
}

ATTESTATION = {
    "attested_by": "bruce",
    "vetting_reference": "MBCP cert 2026-07-06 / AD-04 export bundle",
    "checklist": {"license_ok": True, "weights_checksum_verified": True},
}


async def _register(client: AsyncClient, admin_token: str, body=None) -> dict:
    r = await client.post(
        "/api/v1/models", json=body or REGISTER_BODY, headers=_auth(admin_token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _register_approved(
    client: AsyncClient, admin_token: str, body=None
) -> dict:
    model = await _register(client, admin_token, body)
    r = await client.post(
        f"/api/v1/models/{model['id']}/approve",
        json=ATTESTATION,
        headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _set_availability(
    client: AsyncClient, admin_token: str, model_id: str,
    node_id: str = "node-04", status: str = "available", served: bool = False,
) -> None:
    r = await client.put(
        f"/api/v1/models/{model_id}/availability/{node_id}",
        json={"status": status, "served": served},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text


class TestRegistry:
    async def test_register_lands_in_candidate(self, client, admin_token):
        model = await _register(client, admin_token)
        assert model["state"] == "candidate"
        assert model["is_default"] is False
        assert len(model["capability_tags"]) == 2

    async def test_register_duplicate_name_409(self, client, admin_token):
        await _register(client, admin_token)
        r = await client.post(
            "/api/v1/models", json=REGISTER_BODY, headers=_auth(admin_token),
        )
        assert r.status_code == 409

    async def test_register_requires_admin(self, client, operator_token):
        r = await client.post(
            "/api/v1/models", json=REGISTER_BODY, headers=_auth(operator_token),
        )
        assert r.status_code == 403

    async def test_list_and_get(self, client, admin_token, operator_token):
        model = await _register(client, admin_token)
        r = await client.get("/api/v1/models", headers=_auth(operator_token))
        assert r.status_code == 200
        assert [m["id"] for m in r.json()] == [model["id"]]
        r = await client.get(
            f"/api/v1/models/{model['id']}", headers=_auth(operator_token),
        )
        assert r.status_code == 200


class TestLifecycle:
    async def test_approve_requires_attestation_checklist(
        self, client, admin_token
    ):
        model = await _register(client, admin_token)
        r = await client.post(
            f"/api/v1/models/{model['id']}/approve",
            json={**ATTESTATION, "checklist": {}},
            headers=_auth(admin_token),
        )
        assert r.status_code == 422

    async def test_approve_records_attestation(self, client, admin_token):
        model = await _register_approved(client, admin_token)
        assert model["state"] == "approved"
        assert model["approvals"][0]["attested_by"] == "bruce"

    async def test_approve_only_from_candidate(self, client, admin_token):
        model = await _register_approved(client, admin_token)
        r = await client.post(
            f"/api/v1/models/{model['id']}/approve",
            json=ATTESTATION,
            headers=_auth(admin_token),
        )
        assert r.status_code == 422

    async def test_deprecate_then_retire_chain(self, client, admin_token):
        model = await _register_approved(client, admin_token)
        r = await client.post(
            f"/api/v1/models/{model['id']}/retire", headers=_auth(admin_token),
        )
        assert r.status_code == 422  # approved -> retire is not a legal jump
        r = await client.post(
            f"/api/v1/models/{model['id']}/deprecate", headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["state"] == "deprecated"
        r = await client.post(
            f"/api/v1/models/{model['id']}/retire", headers=_auth(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "retired"
        assert body["enabled"] is False

    async def test_default_requires_approved_and_swaps(self, client, admin_token):
        candidate = await _register(client, admin_token)
        r = await client.patch(
            f"/api/v1/models/{candidate['id']}",
            json={"is_default": True},
            headers=_auth(admin_token),
        )
        assert r.status_code == 422  # candidate cannot be default

        first = await _register_approved(
            client, admin_token,
            {**REGISTER_BODY, "name": "th-first"},
        )
        second = await _register_approved(
            client, admin_token,
            {**REGISTER_BODY, "name": "th-second"},
        )
        for mid in (first["id"], second["id"]):
            r = await client.patch(
                f"/api/v1/models/{mid}",
                json={"is_default": True},
                headers=_auth(admin_token),
            )
            assert r.status_code == 200
        r = await client.get(
            f"/api/v1/models/{first['id']}", headers=_auth(admin_token),
        )
        assert r.json()["is_default"] is False  # swapped to second


class TestPlanner:
    async def test_plan_selects_and_persists(
        self, client, admin_token, operator_token, project_id
    ):
        photorealistic = await _register_approved(client, admin_token)
        stylized = await _register_approved(
            client, admin_token,
            {
                **REGISTER_BODY,
                "name": "sadtalker-v2",
                "engine": "sadtalker",
                "vram_gb": 8.0,
                "capability_tags": [
                    {"dimension": "visual_style", "value": "stylized",
                     "weight": 1.0},
                ],
            },
        )
        for m in (photorealistic, stylized):
            await _set_availability(client, admin_token, m["id"])

        r = await client.post(
            f"/api/v1/projects/{project_id}/model-selections/plan",
            json={
                "stages": ["talking_head"],
                "tier": "prototype",
                "capability_profile": {"visual_style": "stylized"},
            },
            headers=_auth(operator_token),
        )
        assert r.status_code == 200, r.text
        sel = r.json()["selections"][0]
        assert sel["model_id"] == stylized["id"]
        assert sel["selected_by"] == "auto"
        assert "visual_style=stylized" in sel["rationale"]

        r = await client.get(
            f"/api/v1/projects/{project_id}/model-selections",
            headers=_auth(operator_token),
        )
        assert [s["id"] for s in r.json()] == [sel["id"]]

    async def test_plan_rejects_tier_both(
        self, client, operator_token, project_id
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/model-selections/plan",
            json={"stages": ["talking_head"], "tier": "both"},
            headers=_auth(operator_token),
        )
        assert r.status_code == 422

    async def test_plan_nothing_eligible_422(
        self, client, operator_token, project_id
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/model-selections/plan",
            json={"stages": ["talking_head"], "tier": "prototype"},
            headers=_auth(operator_token),
        )
        assert r.status_code == 422
        assert "no eligible model" in r.json()["detail"]

    async def test_manual_override_and_validation(
        self, client, admin_token, operator_token, project_id
    ):
        model = await _register_approved(client, admin_token)
        r = await client.put(
            f"/api/v1/projects/{project_id}/model-selections",
            json={
                "stage": "talking_head",
                "tier": "prototype",
                "model_id": model["id"],
                "rationale": "operator prefers this checkpoint",
            },
            headers=_auth(operator_token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["selected_by"] == "manual"
        assert "manual override by" in body["rationale"]

        r = await client.put(
            f"/api/v1/projects/{project_id}/model-selections",
            json={
                "stage": "talking_head",
                "tier": "prototype",
                "model_id": str(uuid.uuid4()),
                "rationale": "x",
            },
            headers=_auth(operator_token),
        )
        assert r.status_code == 422
