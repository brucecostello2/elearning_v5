"""WP-63 Task 1 — the blank/solid-colour check, pinned on five files.

THE INCIDENT. A full-defaults 9-scene run on 2026-08-26 held at the storyboard
gate, was approved, and died at `image_generation`: 6 of 9 succeeded, 3 were
rejected with "Image appears blank or solid color" (scene indexes 0, 2, 7).
The three files were recovered from ComfyUI and verified by eye by the
operator — people at whiteboards, a hand with a pencil over paper. They are
banked at `tests/fixtures/wp63/` with the measurement in that directory's
README.

WHY EVERY TEST HERE RUNS THE STAGE-3 RESIZE FIRST. The banked frames are
1024x1024 as FLUX produced them, and at that size the OLD check passed them
(ratio 0.0876 / 0.0766 / 0.0809, floor 0.05). Stage 3 fits each frame inside
1920x1080 and pads it with black before validating (`stage3_images.py` step 3
-> `ImageConverter.resize_to_target`), which added 907,200 identical pixels to
the old metric's denominator and dropped the ratios to 0.0485 / 0.0427 /
0.0447. **A test that fed the banked bytes straight to `validate()` would pass
against the broken code.** So `_as_stage3_sees_it` calls the real converter,
and these tests are red without the fix.

WHAT IS BEING PINNED, in Task 1(c)'s terms: not a loosened threshold, a
different measurement. The three legitimate frames score 0.57-0.72 on
`structured_tile_fraction`; the two constructed blanks score exactly 0.0. No
value of the floor makes those groups overlap, and `test_the_floor_is_a_gap`
asserts that separation directly rather than asserting the frames pass.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from utils.image_validator import (
    ImageQualityThresholds,
    ImageValidator,
    measure_blankness,
)
from utils.media_converter import ImageConverter

FIXTURES = Path(__file__).parent / "fixtures" / "wp63"

#: The three operator-verified frames the run rejected, with the scene index
#: each was generated for.
BANKED = [
    ("ivgs_flux_00087_.png", 0, "people at a whiteboard"),
    ("ivgs_flux_00089_.png", 2, "people at a whiteboard"),
    ("ivgs_flux_00094_.png", 7, "a hand with a pencil over paper"),
]


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A solid-colour PNG. The two negative cases, in one line each."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), rgb).save(buf, format="PNG")
    return buf.getvalue()


def _as_stage3_sees_it(image_data: bytes) -> bytes:
    """Exactly what Stage 3 hands the validator: the resized, padded frame."""
    return ImageConverter.resize_to_target(
        image_data=image_data,
        target_width=1920,
        target_height=1080,
        maintain_aspect=True,
        output_format="PNG",
    ).output_data


def _banked(name: str) -> bytes:
    path = FIXTURES / name
    assert path.exists(), (
        f"{path} is missing. These three files ARE the evidence for this "
        "package; the check cannot be pinned without them."
    )
    return path.read_bytes()


# ---------------------------------------------------------------------------
# (a) All three banked frames PASS
# ---------------------------------------------------------------------------

class TestTheThreeRejectedFramesPass:
    @pytest.mark.parametrize("name,scene_index,subject", BANKED)
    def test_the_frame_is_not_called_blank(self, name, scene_index, subject):
        result = ImageValidator().validate(
            image_data=_as_stage3_sees_it(_banked(name)),
            expected_width=1920,
            expected_height=1080,
        )
        assert result.blank_check_ok is True, (
            f"{name} (scene_index {scene_index}, {subject}) was rejected as "
            f"blank. structured_tile_fraction="
            f"{result.metadata.get('structured_tile_fraction')}"
        )
        assert not any("blank" in e.lower() for e in result.errors)

    @pytest.mark.parametrize("name,scene_index,subject", BANKED)
    def test_the_check_ran_rather_than_being_skipped(self, name, scene_index, subject):
        """A pass is only worth something if the check was performed.

        WP-44's finding was two checks that reported themselves passed after
        an ImportError. `blank_check_ok is True` alone cannot tell those apart.
        """
        result = ImageValidator().validate(
            image_data=_as_stage3_sees_it(_banked(name)),
            expected_width=1920,
            expected_height=1080,
        )
        assert "blank_check_ok" in result.checks_run
        assert "blank_check_ok" not in result.checks_missing


# ---------------------------------------------------------------------------
# (b) A constructed blank and a constructed solid colour FAIL
# ---------------------------------------------------------------------------

class TestConstructedBlanksAreStillCaught:
    def test_a_truly_blank_frame_fails(self):
        result = ImageValidator().validate(
            image_data=_png(1920, 1080, (255, 255, 255)),
            expected_width=1920,
            expected_height=1080,
        )
        assert result.blank_check_ok is False
        assert any("blank" in e.lower() for e in result.errors)

    def test_a_solid_colour_frame_fails(self):
        result = ImageValidator().validate(
            image_data=_png(1920, 1080, (37, 99, 235)),
            expected_width=1920,
            expected_height=1080,
        )
        assert result.blank_check_ok is False
        assert any("blank" in e.lower() for e in result.errors)

    def test_a_blank_frame_inside_letterbox_bars_still_fails(self):
        """The bars must not become the structure that rescues a blank frame.

        This is the case the fix could plausibly have got wrong: stripping the
        uniform border is what stops the padding punishing a real frame, and a
        naive edge-counting check would have read the bar/content seam as
        content and passed a white square. It is two solid colours and no
        picture, and the verdict must still be 'blank'.
        """
        result = ImageValidator().validate(
            image_data=_as_stage3_sees_it(_png(1024, 1024, (255, 255, 255))),
            expected_width=1920,
            expected_height=1080,
        )
        assert result.blank_check_ok is False

    def test_a_flat_frame_with_imperceptible_noise_still_fails(self):
        """Distinct colours are not structure.

        Every pixel differs from its neighbour by at most one level. The OLD
        metric would count over a million distinct colours here; there is
        still no picture.
        """
        import numpy as np
        from PIL import Image

        rng = np.random.default_rng(20260826)
        arr = np.clip(
            250 + rng.normal(0, 0.6, (1080, 1920, 3)), 0, 255
        ).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")

        result = ImageValidator().validate(
            image_data=buf.getvalue(),
            expected_width=1920,
            expected_height=1080,
        )
        assert result.blank_check_ok is False


# ---------------------------------------------------------------------------
# (c) It is a discrimination improvement, not a loosened threshold
# ---------------------------------------------------------------------------

class TestItIsDiscriminationNotLooseness:
    def test_the_floor_is_a_gap_not_a_setting(self):
        """The two populations do not overlap, by a factor of at least 20.

        This is the assertion that makes the change defensible. A threshold
        tuned until a complaint stopped would sit just under the lowest
        legitimate value; this one sits in an empty band, because the blanks
        score exactly zero.
        """
        thresholds = ImageQualityThresholds()
        legitimate = [
            _fraction(_as_stage3_sees_it(_banked(name)))
            for name, _idx, _subj in BANKED
        ]
        blanks = [
            _fraction(_png(1920, 1080, (255, 255, 255))),
            _fraction(_png(1920, 1080, (37, 99, 235))),
        ]
        assert max(blanks) == 0.0, blanks
        assert min(legitimate) > 20 * thresholds.blank_structured_tile_fraction, (
            f"the legitimate frames score {legitimate}; the floor is "
            f"{thresholds.blank_structured_tile_fraction}"
        )

    def test_the_old_metric_would_still_reject_these_frames(self):
        """The record of WHY, kept executable.

        `unique_color_ratio` is still measured and still recorded — it is just
        no longer the verdict. If a future change made these frames pass the
        old metric too, the story in this module would be wrong and this test
        says so.
        """
        for name, _idx, _subj in BANKED:
            m = measure_blankness(
                _rgb(_as_stage3_sees_it(_banked(name))), ImageQualityThresholds()
            )
            assert m.unique_color_ratio < 0.05, (
                f"{name} now scores {m.unique_color_ratio} on the OLD metric; "
                "the letterbox measurement in this module needs re-checking."
            )
            assert m.is_blank is False

    def test_the_measurement_is_scale_invariant(self):
        """The defect was a metric whose value depended on the pixel count.

        The same picture at two sizes must get the same verdict. The old one
        did not: 0.0876 at 1024x1024 and 0.0485 at 1920x1080, either side of
        its own floor.
        """
        raw = _banked(BANKED[0][0])
        thresholds = ImageQualityThresholds()
        small = measure_blankness(_rgb(raw), thresholds)
        large = measure_blankness(_rgb(_as_stage3_sees_it(raw)), thresholds)
        assert small.is_blank is False and large.is_blank is False
        assert abs(
            small.structured_tile_fraction - large.structured_tile_fraction
        ) < 0.15, (
            f"{small.structured_tile_fraction} vs "
            f"{large.structured_tile_fraction}"
        )

    def test_every_statistic_is_recorded_on_the_result(self):
        """A rejection must be arguable from the record, not only re-runnable."""
        result = ImageValidator().validate(
            image_data=_as_stage3_sees_it(_banked(BANKED[0][0])),
            expected_width=1920,
            expected_height=1080,
        )
        for key in (
            "structured_tile_fraction",
            "dominant_color_share",
            "unique_color_ratio",
            "content_box",
        ):
            assert key in result.metadata, key

    def test_the_letterbox_bars_are_identified_as_padding(self):
        """The content box names the bars, so the record shows what was stripped."""
        m = measure_blankness(
            _rgb(_as_stage3_sees_it(_banked(BANKED[0][0]))),
            ImageQualityThresholds(),
        )
        assert m.content_box == (0, 1080, 420, 1500), m.content_box
        # And the dominant colour is the padding itself — 43.75% of the frame.
        # Any check keyed on "how much of one colour is there" would still be
        # measuring IVGS's own bars.
        assert m.dominant_color_share == pytest.approx(0.4375, abs=0.001)


def _rgb(image_data: bytes):
    import numpy as np
    from PIL import Image

    return np.array(Image.open(io.BytesIO(image_data)).convert("RGB"))


def _fraction(image_data: bytes) -> float:
    return measure_blankness(
        _rgb(image_data), ImageQualityThresholds()
    ).structured_tile_fraction
