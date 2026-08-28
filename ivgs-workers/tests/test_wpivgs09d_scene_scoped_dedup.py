"""WP-IVGS-09d — two scenes may want the same picture, and each needs its own row.

THE MEASURED DEFECT, on project 9c29b1d1. Three consecutive `prototype_draft`
runs failed with *"Scene 355de248... has no background layer"*. Scene index 4 is
`motion_graphics`, its render reported SUCCESS, and it had no video asset at all.

Scenes 3, 4 and 5 all carried `{"top": 23, "bottom": 14, "step": 1}` — which is
legitimate; a lesson working 23 x 14 can show one step more than once. WP-IVGS-09
hashed the PARAMETERS ALONE and probed project-scoped, so scene 3 rendered, and
scenes 4 and 5 took scene 3's asset id into their result object, reported
`was_deduplicated=True` / `success`, and **never got an asset row**.
`manifests.py` builds layers by grouping assets on `scene_id`, so both scenes had
no background and stage 7 refused the whole draft.

Measured in the worker log: two `motion_scene_rendered`, three
`motion_scene_deduplicated`, all three pointing at asset `0eadd523`, which
belongs to scene 3.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _params_hash():
    """Load the hash helper without importing Celery's whole app."""
    path = _ROOT / "ivgs-workers" / "tasks" / "motion_graphics_task.py"
    src = path.read_text()
    start = src.index("def _params_hash(")
    end = src.index("\nasync def ", start)
    ns: dict = {}
    exec(  # noqa: S102 - a pure function, lifted verbatim from the module
        "import hashlib, json\nfrom typing import Any, Dict, List\n" + src[start:end],
        ns,
    )
    return ns["_params_hash"]


SPEC = [{"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1}]


class TestTheIdempotencyKeyIsPerScene:
    def test_the_same_scene_re_run_gets_the_same_key(self):
        """What the dedup is FOR: a re-run of one scene re-links rather than
        re-rendering. That behaviour is unchanged."""
        h = _params_hash()
        assert h(SPEC, "scene-A") == h(SPEC, "scene-A")

    def test_two_scenes_wanting_the_same_picture_get_DIFFERENT_keys(self):
        """⛔ THE DEFECT. Identical parameters, different scenes — and before
        this fix these were the same key, so the second scene silently inherited
        the first's asset and never got a row of its own."""
        h = _params_hash()
        assert h(SPEC, "scene-A") != h(SPEC, "scene-B")

    def test_the_three_real_scenes_no_longer_collide(self):
        """The exact ids from project 9c29b1d1, with the exact params all three
        carried."""
        h = _params_hash()
        keys = {
            h(SPEC, "b4094625-41ef-470d-96fa-c83dda57a590"),  # index 3, rendered
            h(SPEC, "355de248-121a-421d-8f77-56866aee92e6"),  # index 4, had none
            h(SPEC, "a0281954-3c3e-4ffb-bbe0-b9f66e7c9c0c"),  # index 5, had none
        }
        assert len(keys) == 3

    def test_different_params_on_one_scene_still_differ(self):
        h = _params_hash()
        other = [{"template": "place_value_split", "number": 23}]
        assert h(SPEC, "scene-A") != h(other, "scene-A")

    def test_key_order_does_not_change_the_key(self):
        h = _params_hash()
        a = [{"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1}]
        b = [{"step": 1, "bottom": 14, "top": 23, "template": "column_multiplication_step"}]
        assert h(a, "scene-A") == h(b, "scene-A")


class TestTheDeadLetterPayloadExists:
    """`utils/error_handler.py:295` has always called `to_dlq_payload()` and the
    method has never existed: every routing attempt died on AttributeError,
    caught and logged `dlq_routing_failed` CRITICAL. Four times on this
    project's stage-7 failures alone."""

    def _detail(self):
        """Imported normally, not by file location.

        `task_result` uses `from __future__ import annotations`, so loading it
        under a synthetic module name leaves pydantic unable to resolve
        `FailureCategory` (`PydanticUserError: not fully defined`). `ivgs-workers`
        is on `pythonpath`; this is how every other worker test reaches it."""
        from models.task_result import ErrorDetail, FailureCategory

        return ErrorDetail, FailureCategory

    def test_the_method_exists_and_returns_a_dict(self):
        ErrorDetail, _ = self._detail()
        assert hasattr(ErrorDetail, "to_dlq_payload")
        assert isinstance(ErrorDetail().to_dlq_payload(), dict)

    def test_it_carries_every_column_the_table_has(self):
        """Keyed on `dead_letter_messages`'s real columns so the payload cannot
        drift from the row it is meant to become."""
        ErrorDetail, _ = self._detail()
        payload = ErrorDetail(
            task_name="tasks.prototype_draft_task.assemble_prototype_draft",
            exception_type="Stage7RenderError", exception_message="no background",
            traceback="...", retry_count=3,
        ).to_dlq_payload()
        for column in (
            "task_name", "task_kwargs", "exception_type", "exception_message",
            "traceback", "failure_category", "retry_count_exhausted",
        ):
            assert column in payload, column
        assert payload["retry_count_exhausted"] == 3

    def test_failure_category_is_serialised_not_an_enum(self):
        """It goes out as JSON."""
        import json

        ErrorDetail, _ = self._detail()
        payload = ErrorDetail().to_dlq_payload()
        assert isinstance(payload["failure_category"], str)
        json.dumps(payload)

    def test_it_names_the_job_so_an_operator_can_find_the_run(self):
        ErrorDetail, _ = self._detail()
        payload = ErrorDetail(job_id="J", project_id="P", stage="prototype_draft").to_dlq_payload()
        assert payload["job_id"] == "J" and payload["project_id"] == "P"
        assert payload["stage"] == "prototype_draft"
