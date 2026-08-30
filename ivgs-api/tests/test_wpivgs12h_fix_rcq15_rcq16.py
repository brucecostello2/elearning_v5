"""WP-IVGS-12h-fix — RC-Q15 and RC-Q16, both found by the operator's Phase-1 watch.

⛔ RC-Q15 — THE UPLOADED SCRIPT WAS PARAPHRASED INTO THE DESIGN'S INPUT.

MEASURED, project `3beaf804` / job `5b228dd5`, 2026-08-30:

    source_kind   'uploaded'
    source_text   3,138 bytes   "# How to Multiply Double-Digit Numbers…"
    refined_text  1,647 bytes   "Here's how to multiply two-digit numbers.
                                 Let's break it down into small steps."

`stage2_storyboard.py:122` builds the design call's `combined_transcript` from
`refined_text`, so **the entire Design Core — six packages of grammar, belts and
acceptance — was reasoning about a summary of the operator's lesson.**

⛳ AND THE MECHANISM IS NOT THE ONE IT LOOKED LIKE. It was not a model ignoring a
verbatim-copy instruction: the instruction never arrived. `GET /prompts` took
`get_current_user`, which answers a service token with **401**, so
`_fetch_active_prompt` returned `""` for every lineage and every stage silently
loaded the `.j2` baked into its image. Stage 1 ran the OLD refine-for-readability
prompt and paraphrased exactly as told. The operator's own watch logged it:
`system_prompt_not_published … "the stage will load its .j2 from the image"`,
for a row that was active in the database.

⛔ RC-Q16 — JOB-STATUS PATCHES SILENTLY BOUNCING 422. `JobStatusUpdate.status`
was required on a PATCH whose docstring says *"only fields the worker sends are
written"*, and WP-45 added a caller sending `{"celery_task_id": …}` alone. Two
422s on the watch run; the call never read its response.
"""
from __future__ import annotations

import uuid as _uuid

import pytest


# ---------------------------------------------------------------------------
# RC-Q15 — the substitution, the belt, and the paths that must NOT change
# ---------------------------------------------------------------------------

OPERATOR_SCRIPT = (
    "# How to Multiply Double-Digit Numbers\n\n"
    "Hi there! Today we are going to multiply two 2-digit numbers.\n"
    "Our problem is: 23 times 14.\n"
)
MODEL_PARAPHRASE = (
    "Here's how to multiply two-digit numbers. Let's break it down."
)


async def _transcript(db_session, *, source_kind, source_text, refined="orig"):
    from app.models.project import Project
    from app.models.transcript import Transcript

    project = Project(id=_uuid.uuid4(), name="rcq15", state="DRAFT")
    db_session.add(project)
    await db_session.flush()
    transcript = Transcript(
        id=_uuid.uuid4(), project_id=project.id, sequence_order=0,
        source_kind=source_kind, source_text=source_text, refined_text=refined,
    )
    db_session.add(transcript)
    await db_session.flush()
    return project, transcript


class TestTheUploadedScriptSurvives:

    async def test_the_workers_paraphrase_is_discarded_for_an_uploaded_script(
        self, db_session,
    ):
        """⛔ THE DEFECT, PINNED. The worker writes its echo; the row keeps the
        operator's bytes."""
        from app.services.transcript_service import TranscriptService

        project, transcript = await _transcript(
            db_session, source_kind="uploaded", source_text=OPERATOR_SCRIPT)
        updated = await TranscriptService(db_session).update_transcript(
            project_id=project.id, transcript_id=transcript.id,
            refined_text=MODEL_PARAPHRASE, by_service=True)

        assert updated.refined_text == OPERATOR_SCRIPT
        assert updated.refined_text == updated.source_text
        # ⛳ AND THE ORIGINAL PHRASING IS FINDABLE, which is what a coverage gap
        # quote at the gate shows a reviewer.
        assert "Hi there!" in updated.refined_text
        assert "Hi there!" not in MODEL_PARAPHRASE

    async def test_a_human_edit_of_the_same_field_is_honoured(self, db_session):
        """⚠ THE SCOPING DECISION THE ORDER DID NOT COVER, PINNED SO IT IS NOT
        LOST. This endpoint is also how a person edits `refined_text` inline from
        the gate. Substituting unconditionally would hand an operator's own
        correction straight back to them unchanged — a worse defect than the one
        being fixed. The test is the authenticated principal, not a body flag."""
        from app.services.transcript_service import TranscriptService

        project, transcript = await _transcript(
            db_session, source_kind="uploaded", source_text=OPERATOR_SCRIPT)
        updated = await TranscriptService(db_session).update_transcript(
            project_id=project.id, transcript_id=transcript.id,
            refined_text="a deliberate human correction", by_service=False)

        assert updated.refined_text == "a deliberate human correction"

    async def test_the_generated_path_is_untouched_byte_for_byte(self, db_session):
        """A generated transcript IS raw material and refining it is right. The
        model's work is stored exactly as before, on both principals."""
        from app.services.transcript_service import TranscriptService

        for by_service in (True, False):
            project, transcript = await _transcript(
                db_session, source_kind="generated", source_text=OPERATOR_SCRIPT)
            updated = await TranscriptService(db_session).update_transcript(
                project_id=project.id, transcript_id=transcript.id,
                refined_text=MODEL_PARAPHRASE, by_service=by_service)
            assert updated.refined_text == MODEL_PARAPHRASE

    async def test_the_belt_refuses_an_uploaded_row_with_no_source_text(
        self, db_session,
    ):
        """⛔ The extraction prompt now has the model emit the fixed word
        `EXTRACTED`. With nothing to substitute, storing that placeholder AS the
        script would make every stage design from one word."""
        from app.services.transcript_service import TranscriptService

        project, transcript = await _transcript(
            db_session, source_kind="uploaded", source_text=None)
        with pytest.raises(RuntimeError, match="RC-Q15"):
            await TranscriptService(db_session).update_transcript(
                project_id=project.id, transcript_id=transcript.id,
                refined_text="EXTRACTED", by_service=True)

    async def test_the_belt_is_a_post_write_read_back_not_a_local_variable(self):
        """The claim is about what is IN the database. An ORM default, a trigger
        or a future column could make the local value and the stored row
        disagree, and that is exactly the silent case this ledger exists for."""
        import inspect

        from app.services.transcript_service import TranscriptService

        source = inspect.getsource(TranscriptService.update_transcript)
        belt = source[source.index("RC-Q15's BELT"):]
        assert "await self.db.refresh" in source
        assert source.index("await self.db.refresh") < source.index("RC-Q15's BELT")
        assert "transcript.refined_text != transcript.source_text" in belt


class TestTheServicePrincipalIsTheTest:

    def test_it_reads_the_authenticated_username_not_a_body_flag(self):
        """A worker must not be able to present itself as a person to keep its
        paraphrase, and a person must not be able to claim to be the worker."""
        from app.core.auth import SERVICE_ACCOUNT_USERNAME, is_service_principal

        class U:
            username = SERVICE_ACCOUNT_USERNAME

        class P:
            username = "bruce"

        assert is_service_principal(U()) is True
        assert is_service_principal(P()) is False
        assert is_service_principal(None) is False

    def test_the_username_is_one_constant_and_not_two_copies(self):
        """⛳ It became load-bearing beyond authentication when RC-Q15 made it
        decide whether a write is a model's echo or a person's edit."""
        from pathlib import Path

        from app.core import auth

        source = Path(auth.__file__).read_text()
        assert source.count('"svc-pipeline"') == 1


class TestThePromptsEndpointAnswersTheWorker:
    """⛔ THE MECHANISM OF RC-Q15, AND THE SAME DEFECT 12b FIXED IN ANOTHER ROUTE.

    12b wrote: *"`/design-outcomes`, NOT `/projects/{id}`. The latter takes
    `get_current_user` and answers a service token with 401, so this returned []
    every time, the enum never armed."* Identical shape here — and the swallow is
    worse, because `_fetch_active_prompt` returns `""` and the stage falls back to
    a `.j2` in the image, so a published prompt appears to be live and is not.
    """

    def test_the_list_route_the_worker_calls_accepts_a_service_token(self):
        import inspect

        from app.api.v1 import prompts

        source = inspect.getsource(prompts.list_global_prompts)
        assert "get_service_or_user" in source
        assert "get_current_user" not in source.split('"""')[0]

    def test_the_worker_reads_this_exact_route(self):
        """A test that pins the fix to the wrong route proves nothing."""
        from pathlib import Path

        REPO = Path(__file__).resolve().parents[2]
        worker = (REPO / "ivgs-workers" / "tasks"
                  / "pipeline_orchestrator_v2.py").read_text()
        assert 'full_base_url}/prompts"' in worker
        assert '"prompt_type": prompt_type, "is_active": "true"' in worker


class TestTheExtractionPromptStoppedAskingForTheCopy:

    def _prompt(self):
        from pathlib import Path

        REPO = Path(__file__).resolve().parents[2]
        return (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "transcript_extraction_system.j2").read_text(encoding="utf-8")

    def test_the_verbatim_copy_instruction_is_gone(self):
        assert "COPIED CHARACTER FOR CHARACTER" not in self._prompt()

    def test_it_asks_for_a_placeholder_and_says_why_not_empty(self):
        """⚠ A FIXED WORD AND NOT AN EMPTY STRING, because
        `stage1_transcript.py:368` refuses an empty `refined_text` as "Empty
        response from vLLM" and fails the stage — before the substitution can
        run. That guard is in a FROZEN body and cannot be changed."""
        text = self._prompt()
        assert "EMIT THE SINGLE WORD `EXTRACTED`" in text
        assert '"refined_text": "EXTRACTED"' in text
        assert "stage1_transcript.py:368" in text

    def test_the_generated_branch_is_untouched(self):
        text = self._prompt()
        assert "Flesch-Kincaid" in text
        assert "Time Alignment" in text

    def test_the_publisher_gates_the_new_instruction_and_not_the_old(self):
        from app.scripts.wpivgs12_publish_design_prompts import EXTRACTION_PHRASES

        assert "COPIED CHARACTER FOR CHARACTER, UNCHANGED" not in EXTRACTION_PHRASES
        assert "`refined_text` IS NOT YOURS TO WRITE" in EXTRACTION_PHRASES
        assert [p for p in EXTRACTION_PHRASES if p not in self._prompt()] == []


# ---------------------------------------------------------------------------
# RC-Q16 — the 422, and the swallow that hid it
# ---------------------------------------------------------------------------

class TestThePartialJobPatch:

    def test_status_is_optional_because_this_is_a_patch(self):
        """⛔ The endpoint's own docstring said *"only fields the worker sends
        are written"* while the schema required one. Requiring it would also
        force a caller to restate a status it does not know is current, so a
        `celery_task_id` write could overwrite a concurrent transition."""
        from app.api.v1.jobs import JobStatusUpdate

        body = JobStatusUpdate(celery_task_id="abc")   # WP-45's exact payload
        assert body.status is None
        assert body.celery_task_id == "abc"

    def test_a_status_only_update_still_validates(self):
        from app.api.v1.jobs import JobStatusUpdate

        assert JobStatusUpdate(status="running").status == "running"

    def test_transition_logic_is_guarded_against_a_statusless_patch(self):
        """Stamping and the DRAFT reset are TRANSITION logic. A task-id write is
        not a transition, and stamping it with `None` would either crash or
        record a change that did not happen."""
        import inspect

        from app.api.v1 import jobs

        source = inspect.getsource(jobs.update_job_status)
        stamp = source.index("stamp_status_timestamps")
        guard = source.rindex("payload.status is not None", 0, stamp)
        assert stamp - guard < 400, "stamping is not guarded by the None check"
        assert "payload.status is not None\n            and payload.status in FAILED_STATUSES" in source


class TestTheTaskIdWriteIsLoud:

    def test_it_returns_a_bool_and_names_a_rejection(self):
        """⛔ WP-00's swallow class. `client.patch(…)` with no assignment inside a
        `try` that catches only transport errors: a 422 is a successful request
        carrying a refusal, so the `except` never fired."""
        import inspect

        from pathlib import Path

        REPO = Path(__file__).resolve().parents[2]
        source = (REPO / "ivgs-workers" / "tasks"
                  / "pipeline_orchestrator_v2.py").read_text()
        body = source[source.index("def _update_job_celery_task_id"):]
        body = body[:body.index("\n# ---")]
        assert "resp = client.patch(" in body, "the response is still unread"
        assert "job_celery_task_id_update_rejected" in body
        assert "logger.error(" in body
        assert "-> bool" in body

    def test_it_does_not_fail_the_pipeline_over_bookkeeping(self):
        """A job whose task id was not recorded is still a job that should run.
        Loud is the requirement; fatal is not."""
        from pathlib import Path

        REPO = Path(__file__).resolve().parents[2]
        source = (REPO / "ivgs-workers" / "tasks"
                  / "pipeline_orchestrator_v2.py").read_text()
        body = source[source.index("def _update_job_celery_task_id"):]
        body = body[:body.index("\n# ---")]
        # ⚠ CODE ONLY — the docstring says the word "raised" while explaining why
        # it does not. A test that greps a docstring tests the prose.
        code = body[body.index('"""', body.index('"""') + 3) + 3:]
        assert "raise" not in code
