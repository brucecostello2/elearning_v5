"""WP-68 — maths-teaching motion templates.

WHAT TASK 1 MEASURED, AND HOW IT RESHAPED THIS PACKAGE.

The brief hoped for a cheap path: *"If the compositor can already animate
overlays, the cheapest real teaching animation is an animated overlay over a
still or slow video, needing no new engine at all."* **That path does not
exist**, and it was checked rather than assumed:

  * ``drawtext`` appears NOWHERE in the repository. The compositor overlays
    PRE-RENDERED layers at a fixed x:y (``ffmpeg_client.py:480-517``) and burns
    bottom-aligned SRT captions (``:524-531``, ``Alignment=2, MarginV=40``). It
    cannot place a digit at a position and cannot move one between columns.
  * ``services/motion_graphics.py`` is a Ken Burns / zoom-pan service; its only
    caller is ``FallbackChain``, which is never constructed outside tests.
  * ``RemotionClient`` IS wired -- ``stage7_prototype_draft.py:219``,
    ``stage8_final_render.py:412`` -- but only for LOWER THIRDS, and every
    failure is swallowed (``:230-236``). With no Remotion container, lower
    thirds silently do not render.

A COROLLARY WORTH STATING: the storyboard prompt has told the model since v3
that *"every equation, number, label and caption is rendered by the COMPOSITION
OVERLAY in a later stage, with a real font"* and to keep the upper-right third
clear for it. **No stage draws those numbers.** RULE 1's bargain has one half
missing, and these templates are the first thing in the repo that could keep it.

SO THE TEMPLATES ARE A SPEC, not a renderer: parameters -> a deterministic
timeline of drawing ops, renderable by Remotion, by ffmpeg, or by the local
rasteriser. Every property below is checkable without an engine, and frames are
banked from the rasteriser as real evidence.
"""
from __future__ import annotations

import re

import pytest

from shared.motion.raster import render_digest
from shared.motion.templates import (
    FPS,
    Op,
    render,
    template_names,
    template_spec,
)

ALL = template_names()


def _answer_row(r) -> str:
    """The digits on the answer row of the last frame, left to right."""
    last = r.frames[-1]
    digits = [o for o in last.ops if o.role == "digit" and o.y > 380]
    return "".join(o.text for o in sorted(digits, key=lambda o: o.x))


class TestTheFourTemplatesTheBriefNamed:
    def test_all_four_exist(self):
        assert set(ALL) == {
            "column_multiplication_step",
            "place_value_split",
            "column_addition_carry",
            "highlight_and_hold",
        }

    @pytest.mark.parametrize("name", ALL)
    def test_each_declares_what_its_parameters_mean(self, name):
        spec = template_spec(name)
        assert spec["params"]
        assert spec["describes"]

    @pytest.mark.parametrize("name", ALL)
    def test_each_renders_frames(self, name):
        r = render(name)
        assert len(r.frames) > 0
        assert r.fps == FPS
        assert 1.0 < r.duration_seconds < 12.0

    @pytest.mark.parametrize("name", ALL)
    def test_frame_indices_are_contiguous_from_zero(self, name):
        r = render(name)
        assert [f.index for f in r.frames] == list(range(len(r.frames)))


class TestDeterminism:
    """The property the conformance baseline needs, and Temporal after it."""

    @pytest.mark.parametrize("name", ALL)
    def test_the_same_parameters_give_the_same_pixels(self, name):
        assert render_digest(render(name), every=11) == render_digest(
            render(name), every=11
        )

    def test_different_parameters_give_different_pixels(self):
        assert render_digest(render("place_value_split", number=23), every=11) != (
            render_digest(render("place_value_split", number=47), every=11)
        )

    def test_the_font_is_pinned_not_discovered(self, monkeypatch):
        """A 'deterministic' renderer whose output depends on which fonts are
        installed is not one. It REFUSES rather than substituting, because a
        silent fallback changes every pixel and nothing would say so."""
        from shared.motion import raster

        assert raster.FONT_PATH.endswith(".ttf")
        monkeypatch.setattr(raster, "FONT_PATH", "/nonexistent-a.ttf")
        monkeypatch.setattr(raster, "FONT_FALLBACK", "/nonexistent-b.ttf")
        with pytest.raises(FileNotFoundError) as exc:
            raster._font(48)
        assert "not deterministic" in str(exc.value)


class TestTheArithmeticIsRight:
    """The one thing no quality gate in this pipeline can catch.

    CLAUDE.md's trap table records it: the reference run's scene-5 narration
    teaches 10x3=30, 10x2=20 => "320" written as 230, and no stage caught it,
    "because every quality gate measures output-against-input". A template
    renders the arithmetic itself, so it can be checked here -- once, for all
    parameters.
    """

    @pytest.mark.parametrize("top,bottom,want", [
        (27, 15, "42"), (23, 14, "37"), (5, 5, "10"),
        (99, 1, "100"), (12, 34, "46"), (8, 7, "15"),
    ])
    def test_column_addition_reaches_the_right_answer(self, top, bottom, want):
        assert _answer_row(render("column_addition_carry",
                                  top=top, bottom=bottom)) == want

    def test_addition_writes_no_leading_zero(self):
        """The loop runs one column past the operands so a final carry has
        somewhere to go. Writing that column unconditionally made 27 + 15 read
        '042' -- caught by LOOKING at a banked frame, which no digest over
        those frames could have told me."""
        assert not _answer_row(
            render("column_addition_carry", top=27, bottom=15)
        ).startswith("0")

    @pytest.mark.parametrize("top,bottom,step,want", [
        (23, 14, 0, "92"), (23, 14, 1, "230"),
        (47, 26, 0, "282"), (47, 26, 1, "940"), (9, 9, 0, "81"),
    ])
    def test_a_multiplication_step_reaches_the_right_partial_product(
        self, top, bottom, step, want
    ):
        assert _answer_row(render("column_multiplication_step",
                                  top=top, bottom=bottom, step=step)) == want

    def test_the_tens_step_writes_its_placeholder_zero(self):
        """23 x 1 at step 1 is 230, not 23 -- the placeholder zero IS the
        lesson, and it is the step the operator's own project teaches."""
        assert _answer_row(
            render("column_multiplication_step", top=23, bottom=14, step=1)
        ) == "230"

    @pytest.mark.parametrize("n,tens,units", [
        (23, "20", "3"), (47, "40", "7"), (90, "90", "0"), (10, "10", "0"),
    ])
    def test_place_value_splits_correctly(self, n, tens, units):
        r = render("place_value_split", number=n)
        texts = {o.text for f in r.frames for o in f.ops if o.role == "digit"}
        assert texts == {str(n), tens, units}


class TestTheCarryIsTheThingAStillCannotShow:
    def test_the_carry_travels(self):
        """Its x moves between frames. That is the entire justification for
        this scene being a motion graphic rather than an image."""
        r = render("column_addition_carry", top=27, bottom=15)
        xs = [
            o.x for f in r.frames for o in f.ops if o.role == "carry"
        ]
        assert len(set(round(x) for x in xs)) > 5

    def test_the_carry_persists_after_it_lands(self):
        """A first draft drew the carry ONLY while travelling, so by the time
        the next column was highlighted the carried 1 had vanished -- visible
        in the banked frame, and a worse lesson than a still would have been.
        A child adding that column must SEE the 1 sitting there."""
        r = render("column_addition_carry", top=27, bottom=15)
        # find a frame where the tens column is highlighted, after the units
        # carry has landed
        for i, f in enumerate(r.frames):
            if i < 45:
                continue
            if any(o.op is Op.HIGHLIGHT for o in f.ops):
                assert any(o.role == "carry" for o in f.ops), (
                    f"frame {i} highlights a column with no carry above it"
                )
                return
        pytest.fail("no highlighted frame found after the first carry")

    def test_a_sum_with_no_carry_shows_none(self):
        r = render("column_addition_carry", top=12, bottom=34)
        assert not any(o.role == "carry" for f in r.frames for o in f.ops)

    def test_multiplication_carries_persist_too(self):
        r = render("column_multiplication_step", top=47, bottom=26, step=0)
        assert any(o.role == "carry" for o in r.frames[-1].ops)


class TestTheDigitsAreDrawnNotGenerated:
    """The path that makes RULE 1 unnecessary rather than merely enforced.

    RULE 1 exists because this pipeline measured an image model asked for
    '23 x 14' producing a board reading '2? x 23.14'. A renderer that puts
    '23' on screen in a real font cannot misspell it.
    """

    @pytest.mark.parametrize("name", ALL)
    def test_every_digit_op_carries_exact_text(self, name):
        r = render(name)
        for f in r.frames:
            for o in f.ops:
                if o.op is Op.TEXT and o.role in ("digit", "carry"):
                    assert re.fullmatch(r"\d+", o.text), o.text

    def test_no_template_emits_a_prose_instruction_anywhere(self):
        """These are drawing ops, not a prompt. Nothing here is handed to a
        model to interpret."""
        for name in ALL:
            for f in render(name).frames:
                for o in f.ops:
                    assert len(o.text) < 12, (name, o.text)


class TestTheRasteriserProducesARealPicture:
    @pytest.mark.parametrize("name", ALL)
    def test_a_mid_frame_is_not_blank(self, name):
        """WP-63 paid for this check on generated images; it applies to a
        rendered one too. A template that renders an empty canvas would pass
        every other assertion in this file."""
        from shared.motion.raster import render_frame

        r = render(name)
        img = render_frame(r, len(r.frames) // 2)
        colours = img.getcolors(maxcolors=100_000)
        assert colours is not None and len(colours) > 20

    def test_frames_differ_across_the_animation(self):
        """A 'motion' graphic whose frames are identical is a still with extra
        steps."""
        from shared.motion.raster import frame_bytes

        r = render("column_addition_carry", top=27, bottom=15)
        first = frame_bytes(r, 0)
        middle = frame_bytes(r, len(r.frames) // 2)
        last = frame_bytes(r, len(r.frames) - 1)
        assert len({first, middle, last}) == 3
