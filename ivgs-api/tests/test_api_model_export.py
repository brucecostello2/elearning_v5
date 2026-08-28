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


async def test_composition_bundle_with_ffmpeg_engine_accepted(
    client, db_session, monkeypatch
):
    """0027: composition + supplied engine=ffmpeg passes validation -> 201."""
    from shared.config import settings
    from datetime import datetime, UTC
    from uuid import uuid4
    payload = {
        "certification_id": str(uuid4()),
        "model_id": str(uuid4()),
        "model_name": "ffmpeg-concat",
        "ivgs_stage": "composition",
        "weight_tier": "certified",
        "bundle_digest": "sha256:" + "a" * 64,
        "bundle_manifest_url": "http://mbcp/engines/sha256:aa/manifest",
        "engine": "ffmpeg",
        "certified_at": datetime.now(UTC).isoformat(),
        "certified_by": "test",
    }
    r = await client.post(
        "/ad01/v1/certified-models",
        json=payload,
        headers={"X-Service-Token": settings.IVGS_MBCP_INGEST_TOKEN},
    )
    assert r.status_code == 201, r.text
    assert r.json().get("ad01_id")


# ---------------------------------------------------------------------------
# WP-53 — the seam carries what the sender sends, and says so when it cannot
# ---------------------------------------------------------------------------

class TestRequestConstraintsRoundTrip:
    """MBCP has sent `request_constraints` since 2026-08-21 (WP-E32-R).

    IVGS's `ExportBundleIn` had no such field and carried `extra="ignore"`, so
    every bundle since then was accepted with a 201 and the field discarded
    without a trace. These tests are the acceptance criteria for WP-53 Task 5.

    Why it matters, in MBCP's own words: a consumer that reads
    `quality_summary.performance.resolution` — a MEASURED 1920x1080 for
    Wan2.2-T2V — and builds a request from it reproduces a 135/134 sampler
    failure while holding MBCP's certificate. Measured-under-test geometry is
    not permitted-request geometry, and until this field landed there was
    nowhere in IVGS for the difference to live.
    """

    CONSTRAINTS = {
        "resolution": {"max_width": 1280, "max_height": 720},
        "sampler": {"allowed": ["ddim", "dpmpp_2m"], "steps": {"min": 20, "max": 50}},
        "frames": {"max": 121},
    }

    async def test_constraints_reach_the_store_row(self, client: AsyncClient, db_session):
        r = await client.post(
            URL,
            json=_bundle(request_constraints=self.CONSTRAINTS),
            headers=_svc(),
        )
        assert r.status_code == 201, r.text

        model = await db_session.get(Model, r.json()["ad01_id"])
        assert model is not None
        # Carried verbatim. WP-53 stores and surfaces; it does not interpret,
        # so anything short of an exact round-trip is a bug in the carrying.
        assert model.request_constraints == self.CONSTRAINTS

    async def test_constraints_are_not_folded_into_default_params(
        self, client: AsyncClient, db_session
    ):
        """Constraints are not defaults, and must not be stored as though they were.

        `default_params` already carries four MBCP-sourced facts, so this field
        could have gone there with no migration. A caller may override a
        default; a caller must satisfy a constraint. One careless read of the
        wrong bag is the sampler failure above.
        """
        r = await client.post(
            URL,
            json=_bundle(request_constraints=self.CONSTRAINTS),
            headers=_svc(),
        )
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert "request_constraints" not in (model.default_params or {})

    async def test_a_bundle_without_constraints_stores_null_not_empty(
        self, client: AsyncClient, db_session
    ):
        """NULL means "the sender declared nothing".

        MBCP is explicit that these are not the same fact: "An empty block would
        be the claim 'we checked'; a missing one is the truth 'we have declared
        nothing'." IVGS must not substitute one for the other in either
        direction.
        """
        r = await client.post(URL, json=_bundle(), headers=_svc())
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert model.request_constraints is None

    async def test_an_explicit_null_is_accepted_not_rejected(
        self, client: AsyncClient, db_session
    ):
        """MBCP sends `null` for MOST models, and this nearly went out wrong.

        `mbcp_core.request_constraints()` returns None for any model with no
        declared rule -- MBCP's own tests pin that for FLUX.1-dev and for
        unregistered names -- and `export.py:82` declares the field
        `dict | None`. WP-53's first cut typed it `dict` with a
        `default_factory`, which would have 422'd every one of those bundles:
        a silently-dropped field traded for a rejected export.

        Caught by reading MBCP's committed code rather than the work order's
        description of it (origin/main at 156ddb4; the local clone was 16 days
        stale and had to be fetched first).
        """
        r = await client.post(
            URL, json=_bundle(request_constraints=None), headers=_svc()
        )
        assert r.status_code == 201, r.text
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert model.request_constraints is None

    async def test_the_declared_block_shape_round_trips_verbatim(
        self, client: AsyncClient, db_session
    ):
        """The real block, as `mbcp_core.request_constraints` builds it.

        It leads with an honesty label -- `kind: "declared"` -- because
        everything in it is MBCP's assertion read off engine source, while
        `quality_summary.performance` is the measured half. Note the NESTED
        `default_params`: one more reason this field cannot live inside
        `models.default_params`, where the two would collide.
        """
        declared = {
            "kind": "declared",
            "declared_by": "MBCP",
            "declared_on": "2026-08-21",
            "geometry": {"width": 832, "height": 480},
            "frame_count_rule": {"formula": "4n+1", "min": 5, "max": 121},
            "value_rules": {"guidance_scale": {"min": 1.0, "max": 10.0}},
            "default_params": {"output_width": 832, "output_height": 480},
        }
        r = await client.post(
            URL, json=_bundle(request_constraints=declared), headers=_svc()
        )
        assert r.status_code == 201, r.text
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert model.request_constraints == declared
        assert model.request_constraints["kind"] == "declared"
        # The nested key stayed nested and did not leak into the sibling column.
        assert "output_width" not in (model.default_params or {})

    async def test_a_lean_recert_does_not_erase_existing_constraints(
        self, client: AsyncClient, db_session
    ):
        """Re-certification follows the same supplied-wins rule as engine/VRAM.

        Dropping constraints because a later bundle omitted them would be this
        package's own defect, one step later in the lifecycle.
        """
        name = f"mbcp-model-{uuid.uuid4().hex[:8]}"
        r1 = await client.post(
            URL,
            json=_bundle(model_name=name, request_constraints=self.CONSTRAINTS),
            headers=_svc(),
        )
        assert r1.status_code == 201, r1.text

        r2 = await client.post(URL, json=_bundle(model_name=name), headers=_svc())
        assert r2.status_code == 201, r2.text
        assert r2.json()["created"] is False

        await db_session.commit()
        model = await db_session.get(Model, r2.json()["ad01_id"])
        await db_session.refresh(model)
        assert model.request_constraints == self.CONSTRAINTS


class TestUnknownFieldsProduceARecord:
    """`extra="ignore"` on a seam schema is the swallow pattern in schema form.

    WP-53 replaced it with `extra="allow"` plus a recording path, rather than
    `extra="forbid"`: AD-04 seam 1 is an MBCP-initiated PUSH and MBCP amends the
    bundle unilaterally, so `forbid` would 422 every export until IVGS shipped a
    schema change — a silent drop traded for a total ingest outage the sender
    could not clear. The bundle must land AND the drift must be recorded.
    """

    async def test_an_unknown_field_is_named_in_the_log(
        self, client: AsyncClient, caplog
    ):
        import logging

        with caplog.at_level(logging.WARNING, logger="app.api.ad01_ingest"):
            r = await client.post(
                URL,
                json=_bundle(some_future_mbcp_field={"a": 1}, another_one=2),
                headers=_svc(),
            )
        assert r.status_code == 201, r.text

        messages = " ".join(rec.getMessage() for rec in caplog.records)
        assert "ad01_export_unknown_fields" in messages
        # The NAMES, not just a count -- "we dropped 2 fields" does not tell
        # anyone which contract moved.
        assert "some_future_mbcp_field" in messages
        assert "another_one" in messages

    async def test_the_record_is_durable_not_just_a_log_line(
        self, client: AsyncClient, db_session
    ):
        """Logs rotate; "when did the seam drift?" gets asked months later."""
        r = await client.post(
            URL,
            json=_bundle(some_future_mbcp_field={"a": 1}),
            headers=_svc(),
        )
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert model.default_params["_unknown_export_fields"] == [
            "some_future_mbcp_field"
        ]

    async def test_a_conforming_bundle_records_nothing(
        self, client: AsyncClient, db_session
    ):
        """No false positives: the marker must mean drift, or it means nothing."""
        r = await client.post(URL, json=_bundle(), headers=_svc())
        model = await db_session.get(Model, r.json()["ad01_id"])
        assert "_unknown_export_fields" not in (model.default_params or {})

    async def test_an_unknown_field_does_not_reject_the_bundle(
        self, client: AsyncClient
    ):
        """The `forbid` alternative, pinned as a decision rather than a comment.

        If someone later switches this schema to `extra="forbid"`, this test
        fails and they have to argue with the reasoning above instead of
        discovering the outage at the seam.
        """
        r = await client.post(
            URL, json=_bundle(a_field_from_the_future=True), headers=_svc()
        )
        assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# WP-IVGS-03 — the four MBCP runtimes ModelEngine could not name
# ---------------------------------------------------------------------------

class TestMbcpRuntimeEngines:
    """0042: `engine=tts` and the three remote talking-head runtimes validate.

    MBCP's export drain was 422'd on `engine` with `input: "tts"`, blocking four
    live certificates (Kokoro + three XTTS-v2). `magihuman`, `humo` and
    `wan22_s2v` would have failed identically on certification.

    ⛔ These prove validation ONLY, against a test client. They do NOT prove the
    live endpoint accepts the value: the enum lands in the API image and nothing
    takes effect until node-01 is deployed and 0042 runs. See the WP-IVGS-03
    report §5 — the live half is NOT YET PROVEN.
    """

    # (engine value, the ivgs_stage MBCP certifies it under)
    BLOCKED = [
        ("tts", "tts"),                    # XTTS-v2 + Kokoro, one TtsServerAdapter
        ("magihuman", "talking_head"),
        ("humo", "talking_head"),
        ("wan22_s2v", "talking_head"),
    ]

    @pytest.mark.parametrize("engine,stage", BLOCKED)
    async def test_previously_blocked_engine_now_accepted(
        self, client: AsyncClient, engine: str, stage: str
    ):
        r = await client.post(
            URL,
            json=_bundle(engine=engine, ivgs_stage=stage),
            headers=_svc(),
        )
        assert r.status_code == 201, r.text
        assert r.json().get("ad01_id")

    async def test_the_exact_refused_payload_shape_validates(
        self, client: AsyncClient, db_session
    ):
        """The verbatim failure: engine='tts' on a voiceover_tts certificate.

        Asserts the value REACHES THE ROW, not merely that the request 201s —
        `engine` is supplied-wins (`ad01_ingest.py:195`), and a value that
        validated but was silently replaced by the stage default (`coqui`) would
        still be a defect.
        """
        name = f"Kokoro-{uuid.uuid4().hex[:8]}"
        r = await client.post(
            URL,
            json=_bundle(model_name=name, ivgs_stage="tts", engine="tts"),
            headers=_svc(),
        )
        assert r.status_code == 201, r.text

        row = (
            await db_session.execute(select(Model).where(Model.name == name))
        ).scalar_one()
        assert row.engine == ModelEngine.TTS
        assert row.stage == ModelStage.VOICEOVER_TTS

    async def test_no_existing_value_was_removed(self):
        """§7.1 is RULED: ledger the inconsistency, do not clean it up.

        `coqui`, `kokoro`, `animatediff`, `latentsync` and `sadtalker` name model
        families rather than runtimes by WP-46's own reasoning. They are in use
        on live rows — including the Kokoro-82M row rendering today — so 0042
        removes nothing. This test fails if a later package removes one without
        the separate ruling that requires.
        """
        assert {e.value for e in ModelEngine} == {
            # the twelve that existed before 0042
            "vllm", "ollama", "comfyui", "coqui", "kokoro", "cogvideox",
            "wan21", "animatediff", "latentsync", "sadtalker", "remotion",
            "ffmpeg",
            # the four 0042 adds
            "tts", "magihuman", "humo", "wan22_s2v",
        }

    async def test_domain_is_still_closed(self, client: AsyncClient):
        """Extending the enum must not turn `engine` into free text.

        MBCP's side IS free text (`mbcp_core/models/model.py:33`, String(64), no
        CHECK). IVGS's staying closed is what makes the next unnamed runtime a
        loud 422 rather than a silently mis-registered row.
        """
        r = await client.post(
            URL,
            json=_bundle(engine="tts_coqui"),  # MBCP's adapter_key, NOT its engine
            headers=_svc(),
        )
        assert r.status_code == 422
        assert r.json()["detail"][0]["loc"] == ["body", "engine"]


class TestWpIvgs04WhatTheReSentTtsCertificateDoesToTheStore:
    """WP-IVGS-04 Task 2 — UPDATE or INSERT, proven rather than reasoned.

    The work order's premise was that MBCP's Kokoro certificate lands on the
    row rendering today and flips its engine under it. **It does not**, and the
    reason is that the receiver matches on ``Model.name``
    (``ad01_ingest.py:150``, a UNIQUE column) while MBCP's certificate carries
    ``model_name="Kokoro"`` (``scripts/seed_stage.py:576`` on origin/main) and
    the rendering row is named ``kokoro-82m``. Two different strings, so the
    certificate reaches a DIFFERENT row.

    These tests pin the mechanism, not the live data: same name -> UPDATE in
    place, different name -> INSERT a second row. Both branches are exercised
    so a later change to the match key cannot flip one silently.
    """

    async def test_a_matching_name_UPDATES_the_existing_row_in_place(
        self, client: AsyncClient, db_session
    ):
        """``ad01_ingest.py:190-196`` — the else branch. Supplied-wins engine."""
        first = await client.post(
            URL,
            json=_bundle(model_name="Kokoro", ivgs_stage="tts", engine="kokoro"),
            headers=_svc(),
        )
        assert first.status_code == 201, first.text
        assert first.json()["created"] is True
        model_id = first.json()["ad01_id"]

        second = await client.post(
            URL,
            json=_bundle(model_name="Kokoro", ivgs_stage="tts", engine="tts"),
            headers=_svc(),
        )
        assert second.status_code == 201, second.text
        # SAME id back, and created=False: one row, updated.
        assert second.json()["created"] is False
        assert second.json()["ad01_id"] == model_id

        rows = (
            await db_session.execute(select(Model).where(Model.name == "Kokoro"))
        ).scalars().all()
        assert len(rows) == 1, "the re-send must not duplicate the row"
        assert rows[0].engine == ModelEngine.TTS, (
            "engine is supplied-wins (ad01_ingest.py:195) — the row's engine "
            "changes under it"
        )

    async def test_a_DIFFERENT_name_INSERTS_and_leaves_the_first_row_alone(
        self, client: AsyncClient, db_session
    ):
        """THE CASE THAT ACTUALLY APPLIES to the live store.

        ``kokoro-82m`` is the row rendering today. MBCP's certificate says
        ``Kokoro``. The match at ``ad01_ingest.py:150`` is exact string
        equality on a UNIQUE column, so the certificate cannot reach it: the
        rendering row keeps its engine and keeps resolving through the
        registration WP-IVGS-04 left untouched.
        """
        rendering = Model(
            name="kokoro-82m",
            display_name="kokoro-82m",
            stage=ModelStage.VOICEOVER_TTS,
            engine=ModelEngine.KOKORO,
            state=ModelState.APPROVED,
            enabled=True,
        )
        db_session.add(rendering)
        await db_session.commit()

        r = await client.post(
            URL,
            json=_bundle(model_name="Kokoro", ivgs_stage="tts", engine="tts"),
            headers=_svc(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["created"] is True, "a new row, not an update"
        assert r.json()["ad01_id"] != str(rendering.id)

        await db_session.refresh(rendering)
        assert rendering.engine == ModelEngine.KOKORO, (
            "the live rendering row is NOT touched by the certificate"
        )
        assert (
            await db_session.execute(
                select(func.count()).select_from(Model).where(
                    Model.stage == ModelStage.VOICEOVER_TTS
                )
            )
        ).scalar_one() == 2, "two rows now co-exist — AD-10 §5.2 territory"

    async def test_the_xtts_row_DOES_change_engine_because_its_name_matches(
        self, client: AsyncClient, db_session
    ):
        """The blast radius that is real. ``XTTS-v2`` is MBCP's model name AND
        the IVGS row name, so this certificate lands on the live row and flips
        ``coqui`` -> ``tts``. That row is approved and enabled."""
        existing = Model(
            name="XTTS-v2",
            display_name="XTTS-v2",
            stage=ModelStage.VOICEOVER_TTS,
            engine=ModelEngine.COQUI,
            state=ModelState.APPROVED,
            enabled=True,
        )
        db_session.add(existing)
        await db_session.commit()

        r = await client.post(
            URL,
            json=_bundle(model_name="XTTS-v2", ivgs_stage="tts", engine="tts"),
            headers=_svc(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["created"] is False
        await db_session.refresh(existing)
        assert existing.engine == ModelEngine.TTS
        assert existing.state == ModelState.APPROVED, "lifecycle state is kept"
        assert existing.enabled is True, "and it stays enabled — still selectable"


class TestWpIvgs08DynamicallyLoadableIsSetNotDefaulted:
    """WP-IVGS-08 Task 4. The column defaulted to an unconditional TRUE, so
    every ingested model claimed it could be hot-swapped -- vLLM included,
    which AD-01 §211 says outright cannot be."""

    @pytest.mark.parametrize("engine,expected", [
        # FIXED at process start -> not loadable.
        ("vllm", False),      # AD-01 §211, named
        ("coqui", False),     # measured: servers/coqui/server.py:52-56
        ("kokoro", False),    # measured: servers/kokoro/server.py:50
        ("tts", False),       # the runtime name for both TTS engines
        # LOADABLE.
        ("comfyui", True),    # AD-01 §91, named
        ("ollama", True),     # ⛔ AD-01 §91 AND §211 both put Ollama HERE.
        ("cogvideox", True),
        ("latentsync", True),
    ])
    def test_the_class_boundary(self, engine, expected):
        from app.api.ad01_ingest import is_dynamically_loadable
        assert is_dynamically_loadable(ModelEngine(engine)) is expected

    async def test_ingest_writes_it_explicitly_for_a_fixed_engine(
        self, client: AsyncClient, db_session
    ):
        r = await client.post(URL, json=_bundle(
            ivgs_stage="tts", engine="tts",
            model_name=f"wpivgs08-fixed-{uuid.uuid4().hex[:6]}"), headers=_svc())
        assert r.status_code == 201, r.text
        row = await db_session.get(Model, uuid.UUID(r.json()["ad01_id"]))
        assert row.dynamically_loadable is False

    async def test_ingest_writes_it_explicitly_for_a_loadable_engine(
        self, client: AsyncClient, db_session
    ):
        r = await client.post(URL, json=_bundle(
            ivgs_stage="image_generation", engine="comfyui",
            model_name=f"wpivgs08-load-{uuid.uuid4().hex[:6]}"), headers=_svc())
        assert r.status_code == 201, r.text
        row = await db_session.get(Model, uuid.UUID(r.json()["ad01_id"]))
        assert row.dynamically_loadable is True

    async def test_a_re_cert_that_changes_engine_moves_the_flag_with_it(
        self, client: AsyncClient, db_session
    ):
        """The flag is a property of the ENGINE. A model re-certified onto a
        fixed engine must stop claiming it is hot-swappable."""
        name = f"wpivgs08-move-{uuid.uuid4().hex[:6]}"
        first = await client.post(URL, json=_bundle(
            ivgs_stage="image_generation", engine="comfyui", model_name=name),
            headers=_svc())
        mid = await db_session.get(Model, uuid.UUID(first.json()["ad01_id"]))
        assert mid.dynamically_loadable is True

        await client.post(URL, json=_bundle(
            ivgs_stage="tts", engine="tts", model_name=name), headers=_svc())
        await db_session.refresh(mid)
        assert mid.dynamically_loadable is False
