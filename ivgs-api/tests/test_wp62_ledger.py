"""
WP-62 Tasks 5 and 7 — the deletion ledger's closure, and one flag that lied.

TASK 5, MEASURED FIRST. The ledger asked for "PROJECT_DELETE_COMPLETED updates
the originating row, or references its id". Read from the live database
2026-08-26, all fourteen recorded project deletions:

    action_type              count  before.purge_state  after.purge_state
    PROJECT_DELETE_COMPLETED    14  pending             complete

So the closure ALREADY EXISTS -- `_record_completion` UPDATEs the originating
row by its own id and flips `action_type`. What did NOT exist is any way to
read it: `before_payload->>'purge_state'` says "pending" forever on a finished
deletion, one column away from an after_payload that says "complete", and an
operator querying the obvious field gets the wrong answer on every row.

The `before_payload` is NOT rewritten on completion -- it is a record of the
moment before destruction and editing it would destroy the evidence that the
row was written before the rows were. It is LABELLED, and there is now one read
path that does the classification for everyone.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text


async def _audit_row(
    db_session, *, action_type, project_id=None, minutes_ago=0,
    before=None, after=None,
):
    audit_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO audit_log (id, action_type, resource_type, "
            " resource_id, before_payload, after_payload, timestamp) "
            "VALUES (:id, :a, 'project', :r, CAST(:b AS jsonb), "
            "        CAST(:af AS jsonb), now() - (:m * interval '1 minute'))"
        ),
        {
            "id": audit_id, "a": action_type,
            "r": project_id or uuid.uuid4(),
            "b": json.dumps(before or {}),
            "af": json.dumps(after) if after is not None else None,
            "m": minutes_ago,
        },
    )
    await db_session.commit()
    return audit_id


class TestDeletionAuditClassification:
    async def test_a_finished_deletion_reads_completed_not_pending(
        self, db_session,
    ):
        """The shape of all fourteen historical rows."""
        from app.services.project_deletion import ProjectDeletionService

        await _audit_row(
            db_session,
            action_type="PROJECT_DELETE_COMPLETED",
            before={"project_name": "WP59-THROWAWAY-victim",
                    "purge_state": "pending", "binary_manifest": []},
            after={"purge_state": "complete", "files_deleted": 3,
                   "completed_at": "2026-08-26T02:00:55Z"},
        )
        rows = await ProjectDeletionService(db_session).deletion_audit_status()
        assert rows[0]["classification"] == "completed"
        assert rows[0]["resumable"] is False

    async def test_a_row_still_at_STARTED_and_settled_reads_died_mid_purge(
        self, db_session,
    ):
        """The case the whole ordering was designed for, and the case that was
        indistinguishable from a completed one if you read the obvious field."""
        from app.services.project_deletion import ProjectDeletionService

        await _audit_row(
            db_session,
            action_type="PROJECT_DELETE_STARTED",
            minutes_ago=30,
            before={"project_name": "crashed", "purge_state": "pending",
                    "binary_manifest": [{"fid": "3,01"}]},
        )
        rows = await ProjectDeletionService(db_session).deletion_audit_status()
        assert rows[0]["classification"] == "died_mid_purge"
        assert rows[0]["resumable"] is True
        assert rows[0]["objects_in_manifest"] == 1

    async def test_a_recent_STARTED_row_is_in_flight_not_a_false_alarm(
        self, db_session,
    ):
        """A purge that is RUNNING writes nothing until it finishes, so it is
        indistinguishable from a dead one by the record alone. Reported as its
        own class rather than raising a false alarm on every live deletion."""
        from app.services.project_deletion import ProjectDeletionService

        await _audit_row(
            db_session,
            action_type="PROJECT_DELETE_STARTED",
            minutes_ago=0,
            before={"project_name": "running now", "purge_state": "pending"},
        )
        rows = await ProjectDeletionService(db_session).deletion_audit_status()
        assert rows[0]["classification"] == "in_flight"

    async def test_a_partial_purge_is_not_reported_as_complete(
        self, db_session,
    ):
        """"complete" must mean the purge reached every object it set out to."""
        from app.services.project_deletion import ProjectDeletionService

        await _audit_row(
            db_session,
            action_type="PROJECT_DELETE_COMPLETED",
            before={"project_name": "half", "purge_state": "pending"},
            after={"purge_state": "files_incomplete",
                   "files_failed": [{"fid": "3,01", "error": "404"}]},
        )
        rows = await ProjectDeletionService(db_session).deletion_audit_status()
        assert rows[0]["classification"] == "completed_partial"
        assert rows[0]["files_failed"]

    async def test_the_started_payload_labels_its_own_pending(self):
        """The field cannot be read as "still pending" any more.

        Rows written before this package do not carry the label, which is
        exactly why the read path above exists rather than a data fix: the ten
        2026-08-26 deletions are historical test data and are not modified.
        """
        import inspect

        from app.services import project_deletion

        src = inspect.getsource(project_deletion.ProjectDeletionService.delete)
        assert '"purge_state_note"' in src
        assert '"purge_started_at"' in src

    async def test_the_route_is_admin_only(self, client, operator_token):
        resp = await client.get(
            "/api/v1/projects/deletions/audit",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    async def test_the_route_is_not_shadowed_by_the_project_id_route(
        self, client, admin_token,
    ):
        """FastAPI matches in REGISTRATION order. A literal path whose first
        segment could be a project id must be declared BEFORE `/{project_id}`
        or it answers 422 on a UUID parse."""
        resp = await client.get(
            "/api/v1/projects/deletions/audit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert "deletions" in resp.json()


class TestModelStoreHonesty:
    """Task 7 (WP-61 D-3, RULED): fix the flag now, move routing at
    certification.

    THESE TESTS DRIVE THE MIGRATION'S OWN STATEMENTS against rows shaped like
    the ones measured on the live database, rather than asserting on whatever
    `models` happens to hold. The test database is TRUNCATEd between tests and
    carries no seeded model rows at all, so an assertion over its contents
    would pass on an empty table -- which is the shape of test this series
    exists to stop.

    The live rows, read 2026-08-26:

        llama-3.3-70b-transcript  vllm  approved   dynamically_loadable = f
        llama-3.3-70b-storyboard  vllm  approved   dynamically_loadable = f
        test-model-1              vllm  retired    dynamically_loadable = t   <-- lie
        Llama-3.3-70B-Instruct    vllm  approved   dynamically_loadable = t   <-- lie
        flux1-schnell             comfyui ...      dynamically_loadable = t   (correct)

    Two of four vLLM rows were already false, which is what makes the other two
    a drift rather than a convention.
    """

    @staticmethod
    def _migration_sql() -> str:
        import pathlib

        return (
            pathlib.Path(__file__).resolve().parents[1]
            / "migrations" / "versions" / "0035_wp62_gates.py"
        ).read_text(encoding="utf-8")

    async def _seed(self, db_session):
        """The four vLLM rows and one non-vLLM row, as measured."""
        rows = [
            ("llama-3.3-70b-transcript", "transcript_refinement", "vllm", False),
            ("llama-3.3-70b-storyboard", "storyboard_generation", "vllm", False),
            ("test-model-1", "storyboard_generation", "vllm", True),
            ("Llama-3.3-70B-Instruct", "translation", "vllm", True),
            ("flux1-schnell", "image_generation", "comfyui", True),
        ]
        for name, stage, engine, loadable in rows:
            await db_session.execute(
                text(
                    "INSERT INTO models (id, name, display_name, stage, "
                    " engine, tier, state, dynamically_loadable) "
                    "VALUES (:i, :n, :n, CAST(:s AS model_stage), "
                    "        CAST(:e AS model_engine), 'both', 'approved', :l)"
                ),
                {
                    "i": uuid.uuid4(), "n": name, "s": stage, "e": engine,
                    "l": loadable,
                },
            )
        await db_session.commit()

    async def _apply_flag_fix(self, db_session):
        """Run the migration's OWN statement, not a re-typed one."""
        sql = self._migration_sql()
        assert (
            "UPDATE models SET dynamically_loadable = false, updated_at = now() "
            in sql
        )
        await db_session.execute(
            text(
                "UPDATE models SET dynamically_loadable = false, "
                "updated_at = now() "
                "WHERE engine = 'vllm' AND dynamically_loadable = true"
            )
        )
        await db_session.commit()

    async def test_no_vllm_model_claims_to_be_dynamically_loadable(
        self, db_session,
    ):
        """AD-02: a vLLM node's model is fixed at container start by `--model`.

        `model_selection.py:69` reads this flag, so a true value on a live
        approved row means a selection path could decide to "load" a model onto
        an engine that cannot load one.
        """
        await self._seed(db_session)
        before = (await db_session.execute(
            text(
                "SELECT name FROM models WHERE engine = 'vllm' "
                "AND dynamically_loadable = true ORDER BY name"
            )
        )).scalars().all()
        assert before == ["Llama-3.3-70B-Instruct", "test-model-1"], (
            "the fixture no longer reproduces the measured starting state"
        )

        await self._apply_flag_fix(db_session)

        after = (await db_session.execute(
            text(
                "SELECT name FROM models WHERE engine = 'vllm' "
                "AND dynamically_loadable = true"
            )
        )).scalars().all()
        assert after == [], f"a vLLM model still claims runtime loading: {after}"

    async def test_a_non_vllm_engine_is_not_touched(self, db_session):
        """ComfyUI genuinely can load a checkpoint on demand. The correction is
        about vLLM's `--model`, not about the flag being universally wrong."""
        await self._seed(db_session)
        await self._apply_flag_fix(db_session)
        loadable = (await db_session.execute(
            text(
                "SELECT dynamically_loadable FROM models "
                "WHERE name = 'flux1-schnell'"
            )
        )).scalar()
        assert loadable is True

    async def test_the_correction_is_scoped_to_the_engine_not_a_name_list(self):
        """The property belongs to the ENGINE. A by-name list goes stale the
        first time a vLLM row is added."""
        sql = self._migration_sql()
        assert "WHERE engine = 'vllm' AND dynamically_loadable = true" in sql

    async def test_the_downgrade_is_by_name_and_not_by_engine(self):
        """Setting every vLLM row true on downgrade would "restore" a value two
        of them never held."""
        sql = self._migration_sql()
        assert '_FLAG_WAS_TRUE = ("Llama-3.3-70B-Instruct", "test-model-1")' in sql
        assert "UPDATE models SET dynamically_loadable = true" in sql
        assert "WHERE name IN :names" in sql

    async def test_translation_is_NOT_repointed_at_qwen(self):
        """Routing moves at CERTIFICATION, not here.

        WP-61 routes translation to Qwen by dialling the stage-scoped endpoint
        directly; the Model Store entry is the AD-01 binding and stays on the
        certified Llama record until MBCP certifies the Qwen bundle (work
        orders 5 and 7). Registering an uncertified bundle as approved would be
        a worse lie than the flag this package corrected.
        """
        sql = self._migration_sql()
        assert "Qwen/Qwen3.8-27B-FP8" not in sql
        assert "INSERT INTO models" not in sql

    async def test_the_translation_entry_is_annotated_with_the_exception(
        self, db_session,
    ):
        """Annotated, not pretended. The manifest path is on the record so an
        operator can find the 74 hashes without reading a work package."""
        sql = self._migration_sql()
        for phrase in (
            "PROVENANCE EXCEPTION",
            "UNCERTIFIED",
            "/mnt/ivgs-shared/qwen-weights-manifest-2026-08-26.txt",
            "work orders 5 and 7",
            "after M3.3",
        ):
            assert phrase in sql, phrase

        await self._seed(db_session)
        note = "PROVENANCE EXCEPTION ... qwen-weights-manifest-2026-08-26.txt"
        await db_session.execute(
            text(
                "UPDATE models SET description = :note "
                "WHERE stage = 'translation' AND engine = 'vllm' "
                "AND (description IS NULL OR description = '')"
            ),
            {"note": note},
        )
        await db_session.commit()
        got = (await db_session.execute(
            text(
                "SELECT description FROM models WHERE stage = 'translation' "
                "AND engine = 'vllm'"
            )
        )).scalar()
        assert got == note
