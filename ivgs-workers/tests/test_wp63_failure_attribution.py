"""WP-63 Task 3 — one failure, three stories, and which one was right.

MEASURED on the live fleet, project 14f71729, job d4b41765, 2026-08-26:

    render_jobs row     "Stage talking_head_render failed",
                        failure_category = transient
    checkpoint ledger   image_generation FAILED (failed_count 3,
                        successful_count 6); tts_audio complete
    stepper             Media

The checkpoints were right. Stage 3 rejected 3 of 9 scenes, the media join
drained and PARTIAL-ADVANCED by design, stages 4 and 5 ran, and the run died at
stage 6 with three scenes carrying no image. `handle_stage_completion` writes
`f"Stage {completed_stage} failed"` for whichever stage reported the terminal
failure, so under partial-advance the job row can only ever name the symptom.

These tests drive the real `update_job_status` with the ledger stubbed to what
the live rows actually contain, and assert on the PATCH body the API would
receive — the same standard WP-58's tests use.
"""
from unittest.mock import MagicMock

import pytest

from utils.error_handler import _attribute_failure, update_job_status


#: The ledger for job d4b41765, verbatim from `pipeline_checkpoints`.
INCIDENT_LEDGER = [
    {"stage_name": "transcript_refinement", "stage_index": 1, "status": "complete",
     "created_at": "2026-08-26T13:21:06.002993+00:00"},
    {"stage_name": "storyboard_generation", "stage_index": 2, "status": "complete",
     "created_at": "2026-08-26T13:21:33.092687+00:00"},
    {"stage_name": "image_generation", "stage_index": 3, "status": "failed",
     "created_at": "2026-08-26T13:41:39.029441+00:00"},
    {"stage_name": "tts_audio", "stage_index": 4, "status": "complete",
     "created_at": "2026-08-26T13:42:56.734128+00:00"},
]

INCIDENT_CHECKPOINT_DATA = {
    "failed_count": 3,
    "successful_count": 6,
    "deduplicated_count": 0,
    "total_generation_time": 82.928,
}


def _http(monkeypatch, ledger, checkpoint_data, *, list_status=200, detail_status=200):
    """Stub the module's one httpx.Client: two GETs (ledger) and one PATCH."""
    client = MagicMock()
    ctx = client.return_value.__enter__.return_value

    def _get(url, *_a, **_kw):
        resp = MagicMock()
        if url.rstrip("/").endswith("/checkpoints"):
            resp.status_code = list_status
            resp.json.return_value = {"checkpoints": ledger}
        else:
            resp.status_code = detail_status
            resp.json.return_value = {"checkpoint_data": checkpoint_data}
        return resp

    ctx.get.side_effect = _get
    patch_resp = MagicMock()
    patch_resp.status_code = 200
    ctx.patch.return_value = patch_resp
    monkeypatch.setattr("utils.error_handler.httpx.Client", client)
    return client


def _payload(client) -> dict:
    return client.return_value.__enter__.return_value.patch.call_args.kwargs["json"]


class TestTheJobRowNamesTheStageTheCheckpointRecorded:
    def test_the_incident_is_reattributed_to_image_generation(self, monkeypatch):
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        assert update_job_status(
            "d4b41765", "failed", error_message="Stage talking_head_render failed",
        ) is True
        body = _payload(client)
        assert "Stage image_generation failed" in body["error_message"]
        assert "3 of 9 scenes" in body["error_message"]

    def test_the_reported_stage_is_kept_rather_than_erased(self, monkeypatch):
        """Attribution is a correction, not a deletion.

        `talking_head_render` genuinely did fail; it failed BECAUSE three
        scenes had no image. An operator reading the row must be able to see
        both, or the next person to look at the stage-6 logs will not know why
        they are being sent to stage 3.
        """
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        update_job_status(
            "d4b41765", "failed", error_message="Stage talking_head_render failed",
        )
        assert "talking_head_render" in _payload(client)["error_message"]

    def test_resume_from_stage_becomes_the_stage_that_failed(self, monkeypatch):
        """`stage` lands on `render_jobs.resume_from_stage`.

        The live row says `talking_head_render` — three stages past the fault.
        A resume from there would have skipped the only work that needed
        redoing and produced the same broken draft.
        """
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        update_job_status(
            "d4b41765", "failed", error_message="Stage talking_head_render failed",
        )
        assert _payload(client)["stage"] == "image_generation"

    def test_an_explicit_stage_from_the_caller_still_wins(self, monkeypatch):
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        update_job_status(
            "d4b41765", "failed",
            error_message="Stage talking_head_render failed",
            stage="final_render",
        )
        assert _payload(client)["stage"] == "final_render"

    def test_the_earliest_failure_wins_not_the_latest(self, monkeypatch):
        """Two failed checkpoints means a cause and a consequence."""
        ledger = INCIDENT_LEDGER + [
            {"stage_name": "talking_head_render", "stage_index": 6,
             "status": "failed", "created_at": "2026-08-26T13:44:00+00:00"},
        ]
        client = _http(monkeypatch, ledger, INCIDENT_CHECKPOINT_DATA)
        update_job_status(
            "d4b41765", "failed", error_message="Stage talking_head_render failed",
        )
        assert _payload(client)["stage"] == "image_generation"

    def test_a_clean_ledger_leaves_the_message_alone(self, monkeypatch):
        """No failed checkpoint, no attribution. Silence is not a licence to invent."""
        clean = [r for r in INCIDENT_LEDGER if r["status"] != "failed"]
        client = _http(monkeypatch, clean, {})
        update_job_status(
            "job-x", "failed", error_message="Stage talking_head_render failed",
        )
        assert _payload(client)["error_message"] == "Stage talking_head_render failed"

    def test_an_unreachable_ledger_does_not_cost_the_status_write(self, monkeypatch):
        """The job status is the thing that matters.

        A failed attribution is a worse report; losing the terminal status
        would be a worse OUTCOME — the job would sit `running` forever and the
        in-flight guard would refuse every retrigger.
        """
        client = _http(monkeypatch, [], {}, list_status=403)
        assert update_job_status(
            "job-x", "failed", error_message="Stage talking_head_render failed",
        ) is True
        assert _payload(client)["error_message"] == "Stage talking_head_render failed"

    def test_a_success_is_never_attributed(self, monkeypatch):
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        update_job_status("d4b41765", "success")
        body = _payload(client)
        assert body == {"status": "success"}


class TestAValidatorRejectionIsNotTransient:
    def test_the_incident_stops_being_classified_transient(self, monkeypatch):
        """The live row reads `transient`. That invites a retry of a refusal."""
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        update_job_status(
            "d4b41765", "failed", error_message="Stage talking_head_render failed",
        )
        assert _payload(client)["failure_category"] == "external"

    def test_the_validator_message_itself_is_pinned(self):
        """"Image appears blank or solid color" — the message this package is about.

        It produced 6 of the 20 rejections in the 2026-08-26 reference-run
        rescore. Nothing in the classifier matched it, so it fell to the
        `transient` default, which means "retry it". A frame that was produced,
        measured and refused is a model-OUTPUT failure: §6.2 `external`.
        """
        from services.error_classifier import ErrorClassifier

        assert ErrorClassifier().classify_from_strings(
            "", "Image appears blank or solid color",
        ).value == "external"

    def test_the_british_spelling_is_covered_too(self):
        from services.error_classifier import ErrorClassifier

        assert ErrorClassifier().classify_from_strings(
            "", "Image appears blank or solid colour",
        ).value == "external"

    def test_a_total_media_failure_offers_no_class(self, monkeypatch):
        """THE LIMIT OF THE INFERENCE, pinned rather than glossed over.

        The class comes from the SPLIT: some scenes rendered and some did not,
        in one pass, on one node, against one model, so the difference is the
        content. When everything failed, that shape is equally consistent with
        the generator being unreachable — which is transient — and this module
        offers no opinion. WP-57's rule: a confident wrong class is worse than
        the honest default.
        """
        client = _http(
            monkeypatch, INCIDENT_LEDGER,
            {"failed_count": 9, "successful_count": 0},
        )
        update_job_status(
            "d4b41765", "failed", error_message="Stage talking_head_render failed",
        )
        body = _payload(client)
        assert "Stage image_generation failed" in body["error_message"]
        assert body["failure_category"] == "transient", (
            "the honest default; nothing here knows why all nine failed"
        )

    def test_an_explicit_category_from_the_caller_still_wins(self, monkeypatch):
        client = _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        update_job_status(
            "d4b41765", "failed",
            error_message="Stage talking_head_render failed",
            failure_category="resource",
        )
        assert _payload(client)["failure_category"] == "resource"


class TestTheComposedMessageIsReadable:
    def test_it_says_what_happened_in_one_sentence_each(self, monkeypatch):
        _http(monkeypatch, INCIDENT_LEDGER, INCIDENT_CHECKPOINT_DATA)
        from config import WorkerConfig

        message, stage, category = _attribute_failure(
            "d4b41765", "Stage talking_head_render failed", WorkerConfig(),
        )
        assert stage == "image_generation"
        assert category == "external"
        # The three facts an operator needs, in order: what failed, how much of
        # it, and why the row used to say something else.
        assert message.index("Stage image_generation failed") < message.index(
            "3 of 9 scenes"
        ) < message.index("talking_head_render")
