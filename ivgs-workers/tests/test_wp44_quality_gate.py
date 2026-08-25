"""
WP-44-QUALITY — the quality gate is not allowed to rubber-stamp.

Swallow register **instance 24**: the first e2e run shipped sixteen deformed
images with ``quality_score: 1.0`` and ``clip_score: None``, flagged. Three
mechanisms produced that number:

  1. numpy was absent from the workers image, so ``ImageValidator``'s
     blank/noise block hit ``ImportError`` and set both checks to **True**.
  2. The CLIP endpoint stage 3 constructs did not exist — every call 404'd.
  3. ``_compute_quality_score`` awarded the FULL CLIP weight (+0.15) precisely
     when CLIP had not run.

These tests pin the behaviour that replaces it. They are deliberately written
against the real validators with real bytes, not against mocks of them: the
old code passed every test it had, because none of them ever asked what a
score means when a checker is missing.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
from typing import Any, Dict

import pytest

from utils.image_validator import (
    CHECK_WEIGHTS,
    ClipStatus,
    ImageQualityDecision,
    ImageValidator,
)


# ---------------------------------------------------------------------------
# Fixtures — real images, made here so the tests carry their own inputs
# ---------------------------------------------------------------------------

def _png(width: int = 1920, height: int = 1080, mode: str = "noise") -> bytes:
    """A real PNG. ``mode``: 'noise' (rich), 'blank' (solid), 'flat' (near-solid)."""
    from PIL import Image
    import numpy as np

    if mode == "blank":
        arr = np.full((height, width, 3), 200, dtype=np.uint8)
    elif mode == "flat":
        arr = np.full((height, width, 3), 128, dtype=np.uint8)
        # A hair of variance: unique colours, but std well under the threshold.
        arr[:, :, 0] = (np.arange(width, dtype=np.uint16) % 3).astype(np.uint8) + 127
    else:
        rng = np.random.default_rng(20260826)
        arr = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def good_png() -> bytes:
    return _png(mode="noise")


@pytest.fixture(scope="module")
def blank_png() -> bytes:
    return _png(mode="blank")


# ---------------------------------------------------------------------------
# TASK 1 — numpy is present, so the blank/noise checks actually run
# ---------------------------------------------------------------------------

class TestNumpyIsAvailableSoTheChecksRun:
    """The dependency half of the fix.

    ``import numpy`` inside ImageValidator is what the blank/solid-colour and
    pixel-variance checks stand on. It was never declared in
    ivgs-workers/requirements.txt, so in the shipped image it raised.
    """

    def test_numpy_imports_in_the_worker_environment(self):
        import numpy  # noqa: F401

    def test_numpy_is_declared_in_worker_requirements(self):
        from pathlib import Path

        req = (
            Path(__file__).resolve().parents[1] / "requirements.txt"
        ).read_text(encoding="utf-8")
        assert "numpy==" in req, (
            "numpy must be a PINNED worker dependency. Without it "
            "ImageValidator's blank/noise checks do not run, and before WP-44 "
            "they reported themselves PASSED when that happened."
        )

    def test_blank_image_is_actually_detected(self, blank_png):
        """The check that could not run before now rejects a solid image."""
        result = ImageValidator().validate(blank_png)
        assert result.blank_check_ok is False
        assert result.decision is ImageQualityDecision.REJECTED
        assert any("blank" in e.lower() for e in result.errors)
        assert "blank_check_ok" not in result.checks_missing

    def test_rich_image_passes_the_blank_and_noise_checks(self, good_png):
        result = ImageValidator().validate(good_png)
        assert result.blank_check_ok is True
        assert result.noise_check_ok is True
        assert "blank_check_ok" in result.checks_run
        assert "noise_check_ok" in result.checks_run

    def test_missing_numpy_reports_missing_not_passed(self, monkeypatch, good_png):
        """If numpy ever vanishes again, the checks say so instead of passing.

        This is the exact condition of the first e2e run, simulated. The old
        code answered it with ``blank_check_ok = noise_check_ok = True``.
        """
        import builtins

        real_import = builtins.__import__

        def no_numpy(name, *args, **kwargs):
            if name == "numpy":
                raise ImportError("simulated: numpy not in the image")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_numpy)
        result = ImageValidator().validate(good_png)

        assert "blank_check_ok" in result.checks_missing
        assert "noise_check_ok" in result.checks_missing
        assert result.blank_check_ok is False, "missing must not read as passed"
        assert result.noise_check_ok is False, "missing must not read as passed"
        assert result.quality_score_complete is False
        assert result.decision is not ImageQualityDecision.APPROVED
        assert any("CHECK MISSING" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# TASK 1 — an unavailable CLIP scorer contributes NOTHING
# ---------------------------------------------------------------------------

class TestUnavailableClipContributesNothing:

    def test_no_free_pass_weight_when_clip_is_unavailable(self, good_png):
        """The literal defect: ``score += 0.15  # Default pass if CLIP unavailable``.

        With CLIP unavailable and every other check passing, the score is the
        share of the checks that RAN — and CLIP's weight is in neither the
        numerator nor the denominator.
        """
        v = ImageValidator(clip_api_url="http://127.0.0.1:1/does-not-exist")
        result = v.validate(good_png, prompt="a photograph of a cat")

        assert result.clip_status == ClipStatus.UNAVAILABLE.value
        assert "clip_ok" in result.checks_missing
        assert result.quality_score_complete is False

        expected_coverage = (
            sum(w for k, w in CHECK_WEIGHTS.items() if k != "clip_ok")
            / sum(CHECK_WEIGHTS.values())
        )
        assert result.check_coverage == pytest.approx(expected_coverage, abs=1e-4)
        assert result.check_coverage < 1.0

    def test_records_the_string_unavailable_never_a_bare_none(self, good_png):
        """`clip_score: None` meant three different things. It does not now."""
        v = ImageValidator(clip_api_url="http://127.0.0.1:1/does-not-exist")
        result = v.validate(good_png, prompt="a photograph of a cat")

        details = result.scoring_details()
        assert details["clip_score"] == "unavailable"
        assert details["clip_status"] == "unavailable"
        assert result.metadata["clip_score"] == "unavailable"
        # And it survives the JSON round trip that reaches the API.
        assert json.loads(json.dumps(details))["clip_score"] == "unavailable"

    def test_not_requested_is_distinct_from_unavailable(self, good_png):
        """No prompt is a different fact from a scorer that would not answer."""
        result = ImageValidator().validate(good_png)
        assert result.clip_status == ClipStatus.NOT_REQUESTED.value
        assert result.scoring_details()["clip_score"] == "not_requested"

    def test_a_real_score_is_recorded_as_a_number(self, good_png, monkeypatch):
        """When a scorer really answers, the float is carried through."""
        v = ImageValidator(clip_api_url="http://clip.invalid/api/v1/clip")
        monkeypatch.setattr(
            ImageValidator,
            "_compute_clip_score",
            lambda self, data, prompt: (0.2871, ClipStatus.SCORED),
        )
        result = v.validate(good_png, prompt="a photograph of a cat")

        assert result.clip_status == "scored"
        assert result.clip_score == pytest.approx(0.2871)
        assert result.scoring_details()["clip_score"] == pytest.approx(0.2871)
        assert "clip_ok" not in result.checks_missing
        assert result.check_coverage == pytest.approx(1.0)
        assert result.quality_score_complete is True

    def test_the_scoring_call_carries_the_service_token(self, monkeypatch, good_png):
        """`/api/v1/clip/score` is service-token authenticated.

        Measured live on 2026-08-26: without the header the route answers 403,
        the validator records `unavailable`, and the score is honest and
        useless. The old code would have hidden that behind a free +0.15.
        """
        import httpx

        captured = {}

        class _Resp:
            status_code = 200
            text = ""

            def json(self):
                return {"score": 0.31}

        class _Client:
            def __init__(self, *a, **k):
                captured["headers"] = dict(k.get("headers") or {})

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(httpx, "Client", _Client)
        v = ImageValidator(
            clip_api_url="http://fastapi-backend:8001/api/v1/clip",
            clip_auth_token="SENTINEL-SERVICE-TOKEN",
        )
        score, status = v._compute_clip_score(good_png, "anything")
        assert status is ClipStatus.SCORED
        assert score == pytest.approx(0.31)
        assert captured["headers"].get("Authorization") == (
            "Bearer SENTINEL-SERVICE-TOKEN"
        )

    def test_stage3_passes_the_service_token_to_the_validator(self):
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "tasks" / "stage3_images.py"
        ).read_text(encoding="utf-8")
        assert "clip_auth_token=config.pipeline_api.service_token" in src

    def test_non_200_is_unavailable_not_zero(self, monkeypatch, good_png):
        """A 404 — the first run's actual condition — must not read as 0.0."""
        import httpx

        class _Resp:
            status_code = 404
            text = "Not Found"

            def json(self):  # pragma: no cover - never reached on 404
                return {}

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(httpx, "Client", _Client)
        score, status = ImageValidator(
            clip_api_url="http://node-01:8001/api/v1/clip"
        )._compute_clip_score(good_png, "anything")
        assert score is None
        assert status is ClipStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# TASK 1 — a score computed with checks missing SAYS which
# ---------------------------------------------------------------------------

class TestAScoreWithMissingChecksSaysSo:

    def test_the_original_16_image_condition_no_longer_scores_1_0_as_complete(
        self, monkeypatch, good_png
    ):
        """Reconstruct the first run exactly: no numpy, no CLIP endpoint.

        Old behaviour: ``quality_score 1.0``, ``clip_score None``, flagged, and
        nothing anywhere saying three of seven checks had not run.
        """
        import builtins

        real_import = builtins.__import__

        def no_numpy(name, *args, **kwargs):
            if name == "numpy":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_numpy)
        v = ImageValidator(clip_api_url="http://127.0.0.1:1/api/v1/clip")
        result = v.validate(good_png, prompt="a whiteboard with 23 x 14 on it")

        assert set(result.checks_missing) == {
            "blank_check_ok",
            "noise_check_ok",
            "clip_ok",
        }
        assert result.quality_score_complete is False
        assert result.check_coverage < 1.0
        assert result.decision is ImageQualityDecision.FLAGGED

        details = result.scoring_details()
        for key in (
            "checks_missing",
            "check_coverage",
            "quality_score_complete",
            "clip_status",
        ):
            assert key in details, f"the submitted record must carry {key}"
        assert sorted(details["checks_missing"]) == [
            "blank_check_ok",
            "clip_ok",
            "noise_check_ok",
        ]

    def test_missing_checks_cap_the_decision_at_flagged(self, monkeypatch, good_png):
        """A gate may not APPROVE what it did not measure."""
        v = ImageValidator(clip_api_url="http://127.0.0.1:1/api/v1/clip")
        # Force a perfect 1920x1080 so no resolution warning is in play, and
        # confirm that the ONLY reason it is not approved is the missing check.
        result = v.validate(
            good_png, prompt="anything", expected_width=1920, expected_height=1080
        )
        assert result.errors == []
        assert result.checks_missing == ["clip_ok"]
        assert result.decision is ImageQualityDecision.FLAGGED
        assert result.is_valid is True

    def test_all_checks_present_and_passing_can_approve(self, good_png, monkeypatch):
        """The gate is not merely stuck at flagged — a complete pass approves."""
        monkeypatch.setattr(
            ImageValidator,
            "_compute_clip_score",
            lambda self, data, prompt: (0.33, ClipStatus.SCORED),
        )
        result = ImageValidator(clip_api_url="http://clip.invalid").validate(
            good_png, prompt="x", expected_width=1920, expected_height=1080
        )
        assert result.checks_missing == []
        assert result.quality_score_complete is True
        assert result.check_coverage == pytest.approx(1.0)
        assert result.quality_score == pytest.approx(1.0)
        assert result.decision is ImageQualityDecision.APPROVED

    def test_renormalisation_is_the_old_sum_when_nothing_is_missing(self):
        """With full coverage the new score equals the old weighted sum."""
        checks = {k: True for k in CHECK_WEIGHTS}
        score, coverage = ImageValidator._compute_quality_score(checks, [])
        assert score == pytest.approx(1.0)
        assert coverage == pytest.approx(1.0)

        checks["format_ok"] = False
        score, coverage = ImageValidator._compute_quality_score(checks, [])
        expected = (
            sum(w for k, w in CHECK_WEIGHTS.items() if k != "format_ok")
            / sum(CHECK_WEIGHTS.values())
        )
        assert score == pytest.approx(expected, abs=1e-4)

    def test_nothing_measurable_scores_zero_not_one(self):
        """No checks ran at all — there is no score to report, and it is not 1.0."""
        score, coverage = ImageValidator._compute_quality_score(
            {}, list(CHECK_WEIGHTS)
        )
        assert score == 0.0
        assert coverage == 0.0


# ---------------------------------------------------------------------------
# Stage 3 carries the honest record all the way to the review queue
# ---------------------------------------------------------------------------

class TestStage3CarriesTheRecord:
    """The plumbing between the validator and the API, pinned.

    Written because ``ivgs-workers/tests/test_stage3.py`` could not cover it:
    five of its tests were RED on ``main`` since well before WP-44 — they
    patched ``tasks.stage3_images._update_scene_asset`` and
    ``tasks.stage3_images.CogVideoXClient``, neither of which exists, and they
    called ``_process_single_scene`` with ``flux_client=`` /
    ``cogvideox_client=`` parameters the provider-factory rewrite removed.
    Verified red at 5a9fd23 with this working tree stashed.

    WP-52 repaired that module (ledger P2.45 CLOSED); it is green again and
    exercises the same task through ``_process_single_scene``. These assertions
    are KEPT and are not redundant: they read ``stage3_images.py`` as SOURCE and
    pin the SHAPE of the WP-44 seam — that one helper builds the quality fields
    at all three construction sites, and that submission is not re-gated on
    ``enable_clip_scoring``. A behavioural test passes whether those three sites
    share a helper or copy seven fields by hand three times; that is precisely
    the regression WP-44 exists to prevent, so it is asserted where it lives.
    """

    from pathlib import Path as _Path

    SRC = (
        _Path(__file__).resolve().parents[1] / "tasks" / "stage3_images.py"
    ).read_text(encoding="utf-8")

    def test_one_helper_builds_the_quality_fields_for_every_call_site(self):
        """Three constructors used to copy three fields by hand and drop the rest."""
        assert self.SRC.count("**_quality_fields(validation)") == 3

    def test_the_helper_carries_the_honesty_fields(self):
        from tasks.stage3_images import _quality_fields

        result = ImageValidator().validate(_png(mode="noise"))
        fields = _quality_fields(result)
        for key in (
            "quality_score",
            "quality_decision",
            "clip_score",
            "clip_status",
            "checks_missing",
            "check_coverage",
            "quality_score_complete",
        ):
            assert key in fields, f"_quality_fields drops {key}"
        assert fields["clip_status"] == "not_requested"
        assert fields["quality_score_complete"] is False

    def test_the_scene_result_model_exposes_them(self):
        from tasks.stage3_images import SceneImageResult

        r = SceneImageResult(scene_id="s", scene_index=0)
        assert r.clip_status == "not_requested"
        assert r.checks_missing == []
        assert r.check_coverage == 0.0
        assert r.quality_score_complete is False

    def test_the_submitted_details_are_the_validators_own_record(self):
        assert "details = validation.scoring_details()" in self.SRC
        assert 'details["prompt_used"]' in self.SRC

    def test_submission_is_no_longer_gated_on_clip_scoring(self):
        """Turning CLIP off used to discard the entire quality verdict."""
        block = self.SRC[self.SRC.index("# 8. Submit quality score"):]
        block = block[: block.index("elapsed = round(")]
        assert "if task_input.enable_clip_scoring:" not in block

    def test_a_failed_submission_is_logged_with_its_status(self):
        """A 404 raises nothing; the old code looked only for exceptions."""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1]
            / "utils" / "quality_reporting.py"
        ).read_text(encoding="utf-8")
        assert "resp.status_code not in (200, 201)" in src
        assert 'reason="http_status"' in src
        assert 'reason="transport"' in src
