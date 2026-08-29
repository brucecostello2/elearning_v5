"""
WP-64 — the medium reaches the engine, and the outcomes reach Stage 2.

TWO THINGS ARE GATED HERE, and both are fallbacks whose whole risk is that they
fail silently.

TASK 4. `_generate_image_prompt` writes prompts for ALL media types through one
hardcoded "Generate an image prompt..." user prompt (`stage3_images.py:210-216`)
and renders `stage3_system.j2` with PROJECT fields only (`:203-208`) -- no
`media_type`, so the template cannot branch on the medium and this package does
not pretend it can. What it CAN do is stop the writer flattening motion out of a
description that carries it, and the interim carrier of that motion is the
description itself. These tests measure that the description arrives INTACT.

TASK 6(c). The storyboard stage's `project_description` is composed from the
project's description plus a delimited learning-outcomes block, in the
ORCHESTRATOR, because `stage2_storyboard._render_user_prompt` fixes the
template's variable list inside a frozen stage body. The delimiter is the whole
mechanism; if it drifts, nothing errors and the outcomes are ignored.
"""
from __future__ import annotations

import asyncio
import pathlib
import types
from uuid import uuid4

import pytest

from config import WorkerConfig
from shared.providers.binding import ModelBinding
from tasks.pipeline_orchestrator_v2 import (
    OUTCOMES_CLOSE,
    OUTCOMES_OPEN,
    _description_with_outcomes,
)
from tasks.stage3_images import SceneImageInput, _generate_image_prompt

REPO = pathlib.Path(__file__).resolve().parents[2]
STAGE3_TEMPLATE = REPO / "ivgs-workers" / "prompts" / "stage3_system.j2"

MOVING_DESCRIPTION = (
    "The same desk and lamp, camera holding steady over the sheet; the pencil "
    "begins at the ones column of the top row and traces downward, a small "
    "carry mark forming above the tens column, then the first partial-product "
    "row fills in beneath the ruled line, muted blue-grey illustration style"
)

OUTCOMES = (
    "By the end, the viewer can follow the carrying step as it happens."
)


class Recorder:
    """Stands in for the vLLM client and keeps what it was asked to send."""

    def __init__(self):
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(content="a prompt\nNEGATIVE: none")


def _binding() -> ModelBinding:
    return ModelBinding(
        model_id=uuid4(), name="llama-3.3-70b-storyboard",
        display_name="test", stage="image_generation", engine="vllm",
        tier="prototype", endpoint="http://vllm.test",
        default_params={"engine_model": "llama-3.3-70b"},
    )


def _write(media_type: str, description: str = MOVING_DESCRIPTION) -> dict:
    recorder = Recorder()
    scene = SceneImageInput(
        scene_id=str(uuid4()), scene_index=1, media_type=media_type,
        scene_title="Multiplying by the ones digit",
        narration_text="Multiply four times three, and carry the one.",
        visual_description=description, duration_seconds=8.0,
    )
    asyncio.run(_generate_image_prompt(
        scene=scene,
        project_context={
            "project_name": "double digit multiplication",
            "project_description": "A short lesson on long multiplication.",
            "target_audience": "general",
            "visual_style": "muted blue-grey illustration",
        },
        vllm_client=recorder,
        prompt_binding=_binding(),
        config=WorkerConfig(),
    ))
    return recorder.calls[0]


# ---------------------------------------------------------------------------
# Task 4(a) — the description IS the carrier, measured end to end
# ---------------------------------------------------------------------------


class TestTheDescriptionReachesTheWriterIntact:
    def test_every_word_of_it_arrives(self):
        """The interim contract of this package, in one assertion.

        Tasks 2 and 3 put motion, camera and order INTO the description. If
        this line ever fails, that intent stops arriving anywhere and both of
        them become decorative.
        """
        assert MOVING_DESCRIPTION in _write("video_clip")["user_prompt"]

    def test_the_narration_arrives_with_it(self):
        assert "carry the one" in _write("video_clip")["user_prompt"]

    @pytest.mark.parametrize("media_type", ["image", "video_clip", "animation"])
    def test_all_three_media_types_take_the_same_path(self, media_type):
        """MEASURED, and it is the finding this package opened with: one
        writer, one hardcoded opener, three media types."""
        sent = _write(media_type)["user_prompt"]
        assert sent.startswith(
            "Generate an image prompt for this educational video scene:"
        )
        assert MOVING_DESCRIPTION in sent

    def test_the_system_prompt_is_byte_identical_for_all_three_media(self):
        """`stage3_images.py:203-208` renders the template with four PROJECT
        values and no media type, so it CANNOT branch on the medium.

        Asserted as identity rather than as an absent substring: the template's
        own prose discusses media types, and a substring check would pass or
        fail on the wording rather than on the property. Three different
        scenes, three different media types, one identical system prompt — that
        is the fact P2.65 records, and it cannot quietly stop being true.
        """
        rendered = {
            m: _write(m)["system_prompt"]
            for m in ("image", "video_clip", "animation")
        }
        assert rendered["image"] == rendered["video_clip"] == rendered["animation"]

    def test_the_writer_runs_on_the_binding_not_an_env_profile(self):
        call = _write("video_clip")
        assert call["model"] == "llama-3.3-70b"
        assert call["base_url"] == "http://vllm.test"


# ---------------------------------------------------------------------------
# Task 4(b) — the template says preserve, and does not pretend to branch
# ---------------------------------------------------------------------------


class TestTheStage3TemplateAsksToPreserveMotion:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return STAGE3_TEMPLATE.read_text(encoding="utf-8")

    def test_it_asks_for_motion_camera_and_order_to_survive(self, text):
        assert "PRESERVE MOTION, CAMERA AND TEMPORAL LANGUAGE" in text
        assert "DO NOT FLATTEN IT" in text

    def test_it_names_what_flattening_looks_like(self, text):
        """A rule stated abstractly did not stop the last one (WP-62's lesson
        about the translation prompt, and WP-63's about the storyboard one)."""
        assert "must\n   not become" in text or "must not become" in text
        assert "a pencil resting on a sheet of paper" in text

    def test_it_states_that_it_cannot_branch_on_the_medium(self, text):
        """Honesty about the limit is the point of Task 4(b). A template that
        implied it knew the media type would be a claim the code cannot keep."""
        assert "is never told which" in text
        assert "P2.65" in text

    def test_it_reaches_the_writer(self):
        """The amended text is the text the writer renders — not a file that
        happens to sit beside the one that is loaded."""
        system = _write("video_clip")["system_prompt"]
        assert "PRESERVE MOTION, CAMERA AND TEMPORAL LANGUAGE" in system


# ---------------------------------------------------------------------------
# Task 6(c) — the outcomes carrier
# ---------------------------------------------------------------------------


class TestTheOutcomesCarrier:
    def test_it_appends_a_delimited_block(self):
        out = _description_with_outcomes("A short lesson.", OUTCOMES)
        assert out.startswith("A short lesson.")
        assert OUTCOMES_OPEN in out
        assert OUTCOMES_CLOSE in out
        assert OUTCOMES in out

    def test_the_block_is_the_last_thing_in_the_string(self):
        """So a model reading top-to-bottom meets the brief, then the outcomes,
        and the delimiter is not buried mid-paragraph."""
        out = _description_with_outcomes("A short lesson.", OUTCOMES)
        assert out.rstrip().endswith(OUTCOMES_CLOSE)

    def test_no_outcomes_leaves_the_description_byte_identical(self):
        """Task 6(d): the degradation is invisible. No heading, no delimiter,
        no placeholder — a prompt that reads "LEARNING OUTCOMES: (none)" invites
        the model to reason about the absence."""
        for empty in ("", "   ", None):
            assert _description_with_outcomes("A short lesson.", empty) == (
                "A short lesson."
            )

    def test_outcomes_without_a_description_are_still_delivered(self):
        """A project may have outcomes and no dashboard blurb."""
        out = _description_with_outcomes("", OUTCOMES)
        assert out.startswith(OUTCOMES_OPEN)
        assert OUTCOMES in out

    def test_neither_present_is_an_empty_string_not_a_stray_delimiter(self):
        assert _description_with_outcomes("", "") == ""
        assert _description_with_outcomes(None, None) == ""

    def test_the_carrier_moved_to_the_system_prompt_and_the_block_is_gone(self):
        """THE ONE WAY THIS FAILS SILENTLY — RE-AIMED BY WP-IVGS-12, 2026-08-29.

        It used to be delimiter drift: the orchestrator wrote the block, RULE 0
        told the model to look for it, and divergence produced no error and no
        log line — just outcomes that were never read.

        P2.66 IS CLOSED. The outcomes are a first-class Jinja variable in a
        VERSIONED system prompt (migration 0047), handed to the stage in
        `task_input.system_prompt` — which the frozen body honours ahead of its
        own `.j2`, so no frozen edit was needed. The failure mode moved with the
        carrier: what must not drift now is the interpolation, so that is what
        is asserted, and the template must NOT still be hunting for a block
        nobody writes.
        """
        template = (
            REPO / "ivgs-api" / "seed" / "default_prompts"
            / "storyboard_generation.j2"
        ).read_text(encoding="utf-8")
        assert OUTCOMES_OPEN not in template
        assert OUTCOMES_CLOSE not in template

        from jinja2 import BaseLoader, Environment

        system = (
            REPO / "ivgs-api" / "seed" / "default_prompts"
            / "storyboard_design_system.j2"
        ).read_text(encoding="utf-8")
        env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
        # ⛔ RE-AIMED BY WP-IVGS-12b (RC-Q9): the model is no longer given the
        # raw text to transcribe — it is given ID and TEXT and may only cite the
        # id, which the schema closes by a per-request enum. Both must arrive.
        from shared.design.outcomes import parse_outcomes

        raw = "LO-1: SENTINEL-OUTCOME."
        rendered = env.from_string(system).render(
            learning_outcomes=raw, outcomes=parse_outcomes(raw))
        assert "SENTINEL-OUTCOME" in rendered
        assert "LO-1" in rendered

    def test_the_orchestrator_no_longer_folds_them_into_the_description(self):
        """Retired, not deleted: the function is the record of what the
        fallback was. But nothing may call it, or the outcomes would arrive
        twice by two routes."""
        source = (
            REPO / "ivgs-workers" / "tasks" / "pipeline_orchestrator_v2.py"
        ).read_text(encoding="utf-8")
        assert source.count("_description_with_outcomes(") == 1
