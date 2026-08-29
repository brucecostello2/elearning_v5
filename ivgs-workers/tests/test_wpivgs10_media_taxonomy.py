"""WP-IVGS-10 — Stage 2 can finally RECEIVE the media type it is told to choose.

⛔ HOW THIS WAS FOUND, AND WHY NOTHING FOUND IT SOONER.

WP-68 added `motion_graphics` on 2026-08-26 to the PostgreSQL enum (migration
0041), to the capability registry, to the selection panel and to the storyboard
prompt's RULE 2 and RULE 8. It did not add it to `MediaType` here — the
taxonomy Stage 2 validates its own output against.

Nothing met the gap because nothing had tried. Every motion scene on this fleet
since 2026-08-26 arrived by a GUI flip or by WP-IVGS-09c's Regen path, and both
write the row through the API, past this enum entirely. **WP-IVGS-10's
acceptance run was the first time a storyboard model ever chose the value**, and
it met the gap immediately, on project 5d58f2f5 at 2026-08-29 00:56:20Z:

    Scene 3: media_type 'motion_graphics' is not in the pipeline taxonomy.
    Known values: ['animated','animation','image','still','video','video_clip'].
    Stage 3 dispatches on this field and has no branch for it.

⚠ AND ONE SCENE FAILED THE WHOLE STORYBOARD. WP-53's check RAISES rather than
skipping the offending scene — deliberately and correctly, because silently
dropping a scene loses content the operator asked for. So a single
motion_graphics scene took the stage down and it retried to exhaustion.
"""
from __future__ import annotations

import pytest

from models.task_result import MEDIA_TYPE_SYNONYMS, MediaType, StoryboardScene


def test_the_taxonomy_has_all_four_media_types():
    assert {m.value for m in MediaType} == {
        "image", "video_clip", "animation", "motion_graphics",
    }


def test_the_synonym_table_maps_the_fourth_type():
    """The enum decides what is LEGAL; this table decides what prose maps onto
    it. A value in one and not the other still fails the storyboard, which is
    exactly the shape of the defect this file records."""
    assert MEDIA_TYPE_SYNONYMS["motion_graphics"] == "motion_graphics"
    assert MEDIA_TYPE_SYNONYMS["motion graphics"] == "motion_graphics"


def test_every_synonym_resolves_to_a_real_enum_member():
    """⛔ THE INVARIANT THAT WOULD HAVE CAUGHT THIS ON THE DAY IT WAS
    INTRODUCED, had it existed — and the one that catches the next one."""
    values = {m.value for m in MediaType}
    unmapped = {k: v for k, v in MEDIA_TYPE_SYNONYMS.items() if v not in values}
    assert unmapped == {}


def test_every_enum_member_is_reachable_from_the_synonym_table():
    """The converse, and the half that actually failed: `motion_graphics` was
    reachable everywhere in the system EXCEPT from the prose a model writes."""
    reachable = set(MEDIA_TYPE_SYNONYMS.values())
    missing = {m.value for m in MediaType} - reachable
    assert missing == set(), (
        f"{missing} is a legal media type that Stage 2 cannot receive: the "
        f"storyboard prompt can ask for it and the model's answer will be "
        f"rejected"
    )


@pytest.mark.parametrize(
    "written", ["motion_graphics", "motion graphics", "MOTION_GRAPHICS", " Motion Graphics "]
)
def test_a_scene_the_model_writes_as_motion_graphics_validates(written):
    """The end-to-end shape: what the LLM emits, through the validator, to the
    stored value Stage 3 dispatches on."""
    scene = StoryboardScene(
        scene_index=3,
        narration_text="Multiply 4 times 3, which equals 12, and carry the 1.",
        visual_description="the carry travelling to the tens column",
        media_type=written,
        duration_seconds=8.0,
    )
    assert scene.media_type == "motion_graphics"


def test_an_unknown_media_type_is_still_rejected_loudly():
    """⛔ THE CLOSED-TABLE RULE IS NOT WEAKENED BY ADDING A ROW TO IT.

    WP-53's whole point is that this is a CLOSED table, not a normaliser: a
    receiver rejects, it does not infer. Adding the fourth legal value must not
    turn the check into a fuzzy match.
    """
    with pytest.raises(Exception):
        StoryboardScene(
            scene_index=0, narration_text="n", visual_description="v",
            media_type="motion_graphic",      # singular: a near miss
            duration_seconds=8.0,
        )


def test_the_extra_keys_the_storyboard_model_emits_survive_validation():
    """The property `storyboard_reconcile` depends on, pinned on this side too.

    v7 asks for `generation_params`, `media_rationale` and `text_carried_by`.
    `_save_storyboard_scenes` posts none of them, so the only reason they are
    recoverable at all is that this model keeps unexpected keys and the
    checkpoint records them.
    """
    scene = StoryboardScene(
        scene_index=3,
        narration_text="Multiply 4 times 3 and carry the 1.",
        visual_description="the carry travelling",
        media_type="motion_graphics",
        duration_seconds=8.0,
        generation_params={
            "template": "column_multiplication_step",
            "top": 23, "bottom": 14, "step": 0, "phase": "start",
        },
        media_rationale="motion_graphics: a digit is written and a carry travels.",
    )
    dumped = scene.model_dump(mode="json")
    assert dumped["generation_params"]["phase"] == "start"
    assert dumped["media_rationale"].startswith("motion_graphics:")
