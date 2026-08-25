"""
WP-44-QUALITY Task 5 — the animation input guard.

Wan2.2-Animate is pose reenactment: reference image + driving video, motion
transferred onto **the subject of the reference**. Given a reference with no
subject it does not refuse — it invents a body. WP-46 refuses a *missing*
reference by name; this package makes the same refusal fire for a reference
that is present and has nobody in it, before any GPU is reserved.

The tests come in two halves:

* the DETECTOR, run against the two real frames from the reference project's
  first e2e run (see ``fixtures/wp44/README.md``) — a teacher and an equation
  card, the exact pair the defect was found on;
* the GUARD's contract, which has THREE outcomes and not two. ``absent`` fails
  the scene; ``unavailable`` does not, because "we did not look" is not "there
  is nobody there". A guard that failed scenes when its own detector was
  missing would be the rubber-stamp defect pointed the other way.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clients.wan_animate_client import WanAnimateInputError
from utils.person_detector import (
    DEFAULT_MODEL_PATH,
    PersonDetectionResult,
    PersonDetector,
    PersonPresence,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wp44"
WITH_PERSON = FIXTURES / "reference_with_person.jpg"
WITHOUT_PERSON = FIXTURES / "reference_without_person.jpg"

needs_weights = pytest.mark.skipif(
    not os.path.isfile(DEFAULT_MODEL_PATH),
    reason=(
        f"YOLOv10m detection weights not present at {DEFAULT_MODEL_PATH}. "
        f"These tests run a real detector on real frames; they SKIP rather "
        f"than pass, because a check that cannot run must not report itself "
        f"as having passed."
    ),
)


@pytest.fixture(scope="module")
def detector() -> PersonDetector:
    return PersonDetector()


# ---------------------------------------------------------------------------
# The detector, on the two real frames
# ---------------------------------------------------------------------------

@needs_weights
class TestTheDetectorOnRealReferenceFrames:

    def test_a_character_image_detects_a_person(self, detector):
        """Scene 0's teacher — the kind of still `animation` is for."""
        result = detector.detect(WITH_PERSON.read_bytes())
        assert result.presence is PersonPresence.PRESENT
        assert result.person_count >= 1
        assert result.best_confidence > 0.5
        assert result.ran is True
        assert result.detections and "box_xyxy" in result.detections[0]

    def test_a_person_free_image_detects_no_person(self, detector):
        """Scene 2's equation card — typed `animation` by the storyboard."""
        result = detector.detect(WITHOUT_PERSON.read_bytes())
        assert result.presence is PersonPresence.ABSENT
        assert result.person_count == 0
        assert result.best_confidence < 0.05
        assert result.ran is True

    def test_the_two_populations_are_not_close(self, detector):
        """The 0.25 floor is not a delicate threshold; it is a chasm."""
        person = detector.detect(WITH_PERSON.read_bytes()).best_confidence
        no_person = detector.detect(WITHOUT_PERSON.read_bytes()).best_confidence
        assert person > 100 * max(no_person, 1e-6)

    def test_the_detector_uses_the_engines_own_verified_weights(self):
        """MBCP provenance: the same ONNX the certified Wan graph loads."""
        assert DEFAULT_MODEL_PATH.endswith("yolov10m.onnx")
        assert "wan-weights-staging/detection" in DEFAULT_MODEL_PATH


# ---------------------------------------------------------------------------
# The three-outcome contract
# ---------------------------------------------------------------------------

class TestUnavailableIsNotAbsent:

    def test_missing_weights_file_is_unavailable_with_a_reason(self):
        d = PersonDetector(model_path="/nonexistent/yolov10m.onnx")
        result = d.detect(b"not-an-image")
        assert result.presence is PersonPresence.UNAVAILABLE
        assert result.ran is False
        assert "not found" in result.reason

    @needs_weights
    def test_undecodable_bytes_are_unavailable_not_absent(self, detector):
        """A broken download must not be read as 'there is no person here'."""
        result = detector.detect(b"\x00\x01\x02 definitely not an image")
        assert result.presence is PersonPresence.UNAVAILABLE
        assert "inference failed" in result.reason

    def test_the_result_serialises_its_own_status(self):
        d = PersonDetector(model_path="/nonexistent/yolov10m.onnx")
        payload = d.detect(b"x").to_dict()
        assert payload["presence"] == "unavailable"
        assert payload["reason"]
        assert "person_count" in payload and "best_confidence" in payload


# ---------------------------------------------------------------------------
# The guard, as wired into the animation task
# ---------------------------------------------------------------------------

class TestTheGuardIsWiredIntoTheAnimationTask:

    SRC = (
        Path(__file__).resolve().parents[1]
        / "tasks" / "animation_generation_task.py"
    ).read_text(encoding="utf-8")

    def test_the_task_runs_the_detector(self):
        assert "PersonDetector().detect(reference_image)" in self.SRC

    def test_it_raises_the_named_error_with_the_named_message(self):
        """The work order names both the exception and the sentence."""
        assert "WanAnimateInputError(" in self.SRC
        assert "reference image contains no person to animate" in self.SRC

    def test_the_guard_precedes_the_gpu_work(self):
        """~1.3 s of CPU instead of a reservation and a 256 s render."""
        guard = self.SRC.index("PersonDetector().detect(reference_image)")
        render = self.SRC.index("await client.generate_animation(")
        dedup = self.SRC.index("if enable_dedup:")
        params = self.SRC.index("params = _params_from_binding(binding, scene)")
        assert guard < params < dedup < render, (
            "the guard must fire before parameter resolution, the dedup "
            "lookup and the render"
        )

    def test_unavailable_does_not_fail_the_scene(self):
        """Only ABSENT raises. UNAVAILABLE warns and proceeds."""
        raise_block = self.SRC[
            self.SRC.index("if detection.presence is PersonPresence.ABSENT:"):
            self.SRC.index("params = _params_from_binding(binding, scene)")
        ]
        assert "raise WanAnimateInputError" in raise_block
        after_unavailable = raise_block[
            raise_block.index("if detection.presence is PersonPresence.UNAVAILABLE:"):
        ]
        assert "raise" not in after_unavailable, (
            "an unavailable detector must not fail the scene — 'we did not "
            "look' is not 'there is nobody there'"
        )
        assert "log.warning(" in after_unavailable

    def test_the_verdict_travels_with_the_result(self):
        assert "reference_person_check" in self.SRC
        assert 'details["reference_person_check"] = detection.to_dict()' in self.SRC

    def test_the_result_model_carries_the_field(self):
        from tasks.animation_generation_task import SceneAnimationResult

        r = SceneAnimationResult(scene_id="s", scene_index=0)
        assert r.reference_person_check == "not_run"
        assert r.quality_score_complete is False
        assert r.checks_missing == []


# ---------------------------------------------------------------------------
# The refusal reads as a refusal
# ---------------------------------------------------------------------------

class TestTheRefusalNamesTheGap:

    def test_wan_animate_input_error_is_the_existing_named_type(self):
        """WP-46 already refuses a MISSING reference by this name.

        Task 5 extends the same exception to a reference that is present and
        unusable, so a caller distinguishing input problems from engine
        problems keeps working unchanged.
        """
        assert issubclass(WanAnimateInputError, Exception)
        err = WanAnimateInputError(
            "reference image contains no person to animate: scene 2"
        )
        assert "no person to animate" in str(err)
