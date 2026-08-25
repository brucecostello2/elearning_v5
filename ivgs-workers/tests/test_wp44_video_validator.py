"""
WP-44-QUALITY Task 3 — video assets get a validator, and it runs.

Before this package the whole of video validation was::

    # 4. Validate
    _validator = VideoValidator()  # noqa: F841

built and discarded, with a lint suppression on top. The first e2e run's video
assets carry ``quality_decision: ""`` and ``quality_score: 0.0`` — not a bad
score, no score at all.

These tests build real MP4s with ffmpeg and validate them, because the whole
point of the check is what it does to real frames. Where ffmpeg is absent the
distinctness tests SKIP with the reason stated — they do not silently pass,
which would be the same defect this package exists to end. (ffmpeg is present
in the workers image; it is absent from node-01's host, so a host-side run
skips and a container-side run does not. Both are recorded in the report.)
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from utils.video_validator import (
    CHECK_WEIGHTS,
    VideoQualityDecision,
    VideoValidator,
)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

needs_ffmpeg = pytest.mark.skipif(
    not (FFMPEG and FFPROBE),
    reason=(
        "ffmpeg/ffprobe not on PATH. These tests decode real frames; they are "
        "SKIPPED rather than passed, because a check that cannot run must "
        "never report itself as having passed — which is WP-44's whole subject."
    ),
)


# ---------------------------------------------------------------------------
# Real MP4s, made here
# ---------------------------------------------------------------------------

def _make_mp4(path: Path, *, kind: str, seconds: float = 2.0, fps: int = 30,
              w: int = 1920, h: int = 1080) -> Path:
    """Render a real H.264 MP4.

    kind='moving' — a testsrc pattern that changes every frame.
    kind='still'  — one solid colour, every frame byte-identical.
    """
    if kind == "moving":
        src = f"testsrc=size={w}x{h}:rate={fps}:duration={seconds}"
    else:
        src = f"color=c=0x3355aa:size={w}x{h}:rate={fps}:duration={seconds}"

    subprocess.run(
        [
            FFMPEG, "-v", "error", "-y",
            "-f", "lavfi", "-i", src,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return path


@pytest.fixture(scope="module")
def tmp_media(tmp_path_factory):
    return tmp_path_factory.mktemp("wp44media")


@pytest.fixture(scope="module")
def moving_mp4(tmp_media):
    if not FFMPEG:
        pytest.skip("ffmpeg absent")
    return _make_mp4(tmp_media / "moving.mp4", kind="moving")


@pytest.fixture(scope="module")
def still_mp4(tmp_media):
    if not FFMPEG:
        pytest.skip("ffmpeg absent")
    return _make_mp4(tmp_media / "still.mp4", kind="still")


# ---------------------------------------------------------------------------
# The validator actually runs
# ---------------------------------------------------------------------------

class TestTheValidatorIsWiredIn:
    """The construction sites, pinned. A discarded validator is the defect."""

    def test_video_task_constructs_and_uses_the_validator(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "tasks" / "video_generation_task.py"
        ).read_text(encoding="utf-8")
        assert "_validator = VideoValidator()  # noqa: F841" not in src, (
            "the build-and-discard line is back"
        )
        assert "validator.validate_bytes(" in src
        assert "result.quality_decision = validation.decision.value" in src
        assert "submit_quality_score(" in src

    def test_animation_task_constructs_and_uses_the_validator(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "tasks" / "animation_generation_task.py"
        ).read_text(encoding="utf-8")
        assert "validator.validate_bytes(" in src
        assert "result.quality_decision = validation.decision.value" in src
        assert "submit_quality_score(" in src


# ---------------------------------------------------------------------------
# Frame distinctness — the WP-46 addendum measurement, made standing
# ---------------------------------------------------------------------------

@needs_ffmpeg
class TestFrameDistinctness:

    def test_a_moving_clip_measures_as_moving(self, moving_mp4):
        m, reason = VideoValidator().measure_frame_distinctness(str(moving_mp4))
        assert m is not None, reason
        assert m["frames_decoded"] >= 2
        assert m["identical_consecutive_pairs"] == 0
        assert m["distinct_frame_ratio"] == pytest.approx(1.0)
        assert m["consecutive_abs_diff_mean"] > 0.0
        # The addendum's shape: distinct of decoded, and the pair count.
        assert m["distinct_frames"] == m["frames_decoded"]
        assert m["consecutive_pairs"] == m["frames_decoded"] - 1

    def test_a_still_in_an_mp4_is_measured_as_a_still(self, still_mp4):
        m, reason = VideoValidator().measure_frame_distinctness(str(still_mp4))
        assert m is not None, reason
        assert m["distinct_frames"] == 1
        assert m["identical_consecutive_pairs"] == m["consecutive_pairs"]
        assert m["consecutive_abs_diff_max"] == pytest.approx(0.0)
        assert m["first_vs_last_abs_diff"] == pytest.approx(0.0)

    def test_a_still_is_REJECTED_not_flagged(self, still_mp4):
        """`media_type=animation` producing a still is the WP-46 defect.

        A clip whose every frame equals its neighbour is a still in a
        container. The gate refuses it rather than scoring it.
        """
        r = VideoValidator().validate_file(
            str(still_mp4), expected_duration=2.0, expect_audio=False
        )
        assert r.decision is VideoQualityDecision.REJECTED
        assert r.is_valid is False
        assert any("does not move" in e for e in r.errors)

    def test_a_moving_clip_passes_distinctness(self, moving_mp4):
        r = VideoValidator().validate_file(
            str(moving_mp4), expected_duration=2.0, expect_audio=False
        )
        assert r.distinctness_ok is True
        assert "distinctness_ok" not in r.checks_missing
        assert r.distinctness["distinct_frame_ratio"] == pytest.approx(1.0)

    def test_the_measurement_is_recorded_in_the_submitted_details(self, moving_mp4):
        r = VideoValidator().validate_file(
            str(moving_mp4), expected_duration=2.0, expect_audio=False
        )
        details = r.scoring_details()
        assert details["distinctness"]["frames_decoded"] >= 2
        assert details["distinctness"]["method"] == "greyscale_pairwise_abs_diff"


# ---------------------------------------------------------------------------
# A check that cannot run reports itself missing
# ---------------------------------------------------------------------------

class TestAChecKThatCannotRunSaysSo:

    def test_distinctness_unavailable_is_missing_not_passed(self):
        """No ffmpeg binary → the check is MISSING, and never a silent pass."""
        v = VideoValidator(ffmpeg_path="/nonexistent/ffmpeg")
        m, reason = v.measure_frame_distinctness("/anything.mp4")
        assert m is None
        assert "not found" in reason

    @needs_ffmpeg
    def test_missing_distinctness_caps_the_decision_and_shrinks_coverage(
        self, moving_mp4
    ):
        v = VideoValidator(ffmpeg_path="/nonexistent/ffmpeg")
        r = v.validate_file(
            str(moving_mp4), expected_duration=2.0, expect_audio=False
        )
        assert "distinctness_ok" in r.checks_missing
        assert r.distinctness_ok is False
        assert r.quality_score_complete is False
        assert r.decision is not VideoQualityDecision.APPROVED
        assert any("CHECK MISSING" in w for w in r.warnings)
        assert r.check_coverage < 1.0

    def test_unreadable_file_names_every_check_it_could_not_run(self):
        r = VideoValidator().validate_file("/definitely/not/here.mp4")
        assert r.decision is VideoQualityDecision.REJECTED
        assert r.quality_score_complete is False
        # It did not merely mark everything False; it said they were missing.
        assert "codec_ok" in r.checks_missing
        assert "distinctness_ok" in r.checks_missing

    @needs_ffmpeg
    def test_no_expected_duration_reports_the_comparison_as_missing(
        self, moving_mp4
    ):
        """Duration vs expected cannot run without an expected value."""
        r = VideoValidator().validate_file(str(moving_mp4), expect_audio=False)
        assert "duration_vs_expected" in r.checks_missing
        assert any("CHECK MISSING" in w and "duration" in w for w in r.warnings)

    @needs_ffmpeg
    def test_silent_clip_records_audio_as_not_applicable_not_failed(
        self, moving_mp4
    ):
        """CogVideoX/Wan emit video-only MP4s; that is not a defect."""
        r = VideoValidator().validate_file(
            str(moving_mp4), expected_duration=2.0, expect_audio=False
        )
        assert "audio_ok" in r.checks_missing
        assert not any("No audio stream" in w for w in r.warnings)
        assert r.metadata["audio_expected"] is False


# ---------------------------------------------------------------------------
# Duration vs expected
# ---------------------------------------------------------------------------

@needs_ffmpeg
class TestDurationAgainstExpected:

    def test_matching_duration_passes(self, moving_mp4):
        r = VideoValidator().validate_file(
            str(moving_mp4), expected_duration=2.0, expect_audio=False
        )
        assert r.duration_ok is True
        assert r.actual_duration_seconds == pytest.approx(2.0, abs=0.15)
        assert r.metadata["duration_expected_s"] == 2.0

    def test_wrong_duration_is_flagged_and_the_deviation_is_recorded(
        self, moving_mp4
    ):
        r = VideoValidator().validate_file(
            str(moving_mp4), expected_duration=10.0, expect_audio=False
        )
        assert r.duration_ok is False
        assert r.decision is VideoQualityDecision.FLAGGED
        assert r.metadata["duration_deviation_pct"] > 10.0
        assert any("Duration deviation" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Scoring arithmetic
# ---------------------------------------------------------------------------

class TestScoringNeverAbsorbsAnUnrunCheck:

    def test_missing_check_leaves_both_numerator_and_denominator(self):
        all_pass = {k: True for k in CHECK_WEIGHTS}
        score, coverage = VideoValidator._compute_quality_score(all_pass, [])
        assert score == pytest.approx(1.0)
        assert coverage == pytest.approx(1.0)

        without = {k: v for k, v in all_pass.items() if k != "distinctness_ok"}
        score, coverage = VideoValidator._compute_quality_score(
            without, ["distinctness_ok"]
        )
        # Still 1.0 of what RAN — but coverage says how little that was, and
        # quality_score_complete (set by validate_file) is False.
        assert score == pytest.approx(1.0)
        expected = (
            sum(w for k, w in CHECK_WEIGHTS.items() if k != "distinctness_ok")
            / sum(CHECK_WEIGHTS.values())
        )
        assert coverage == pytest.approx(expected, abs=1e-4)

    def test_nothing_ran_is_zero_not_one(self):
        score, coverage = VideoValidator._compute_quality_score(
            {}, list(CHECK_WEIGHTS)
        )
        assert score == 0.0
        assert coverage == 0.0
