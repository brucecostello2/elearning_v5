"""
WP-41 — the compiled pipeline graph (AD-05 §5.1, Draft 2 §5).

The 1,502-line orchestrator these tests replace has none of its own. That is
not incidental: ``STAGE_TRANSITIONS`` / ``STAGE_TASK_MAP`` are lookup tables
resolved at dispatch time, so there is nothing to assert about them until
something dispatches. A compiled graph can be asserted about standing still.
"""

from __future__ import annotations

import pytest

from temporal_pipeline.dag import (
    CHECKPOINT_STAGE_INDEX,
    MEDIA_BRANCHES,
    SIGNAL_DRAFT_APPROVED,
    SIGNAL_STORYBOARD_APPROVED,
    DagNode,
    NodeKind,
    SceneRef,
    build_pipeline_dag,
    gate_positions,
    stage_sequence,
    topological_waves,
)
from temporal_pipeline.idempotency import STAGE_TOKENS
from temporal_pipeline.reference_storyboard import reference_storyboard


def scenes(*media_types: str) -> list[SceneRef]:
    return [
        SceneRef(scene_id=f"scene-{i}", scene_index=i, media_type=mt)
        for i, mt in enumerate(media_types)
    ]


# The storyboard of job bd99fe37, 2026-08-23: 4 image, 12 animation, 2 video.
REFERENCE_MIX = reference_storyboard()


class TestWaveStructure:
    def test_reference_storyboard_compiles_to_ten_waves(self):
        waves = topological_waves(build_pipeline_dag(REFERENCE_MIX))
        assert len(waves) == 10
        assert [n.id for n in waves[0]] == ["s1_transcript"]
        assert [n.id for n in waves[1]] == ["s2_storyboard"]
        assert [n.id for n in waves[2]] == ["gate_storyboard"]
        # The three media branches are ONE wave: no dependency path between
        # them, so they are discovered to be parallel rather than declared so.
        assert [n.id for n in waves[3]] == ["s3_image", "s3_video", "s3_animation"]
        assert [n.id for n in waves[-1]] == ["s8_final"]

    def test_stage_order_matches_ad05_section_5_1(self):
        assert stage_sequence(build_pipeline_dag(REFERENCE_MIX)) == [
            "transcript_refinement",
            "storyboard_generation",
            "image_generation",
            "video_generation",
            "animation_generation",
            "composition_manifest",
            "tts_audio",
            "talking_head_render",
            "prototype_draft",
            "final_render",
        ]

    def test_draft_depends_on_both_manifest_and_head(self):
        """The first place the graph is genuinely a graph and not a line."""
        nodes = {n.id: n for n in build_pipeline_dag(REFERENCE_MIX)}
        assert set(nodes["s7_draft"].depends_on) == {"s6_talking_head", "s4_manifest"}


class TestThreeMediaLabels:
    """
    WP-39, as a property.

    On 2026-08-23 image and animation shared one Celery task AND one stage
    label, so the 12-scene animation completion hit the image run's
    already-set ``media_join_seen`` key and was dropped as a duplicate.
    """

    def test_all_three_media_types_get_distinct_nodes_and_labels(self):
        media = [
            n for n in build_pipeline_dag(REFERENCE_MIX) if n.kind is NodeKind.FANOUT
        ]
        assert [n.id for n in media] == ["s3_image", "s3_video", "s3_animation"]
        assert len({n.label for n in media}) == 3
        assert [n.label for n in media] == [
            "image_generation",
            "video_generation",
            "animation_generation",
        ]

    def test_image_and_animation_share_a_queue_but_not_a_label(self):
        """They share the queue and the engine. They must not share identity."""
        media = {
            n.id: n for n in build_pipeline_dag(REFERENCE_MIX)
            if n.kind is NodeKind.FANOUT
        }
        assert media["s3_image"].queue == media["s3_animation"].queue == "gpu_image"
        assert media["s3_image"].label != media["s3_animation"].label
        assert (
            media["s3_image"].idempotency_stage
            != media["s3_animation"].idempotency_stage
        )

    def test_scene_indexes_are_partitioned_across_branches(self):
        media = [
            n for n in build_pipeline_dag(REFERENCE_MIX) if n.kind is NodeKind.FANOUT
        ]
        assert [len(n.scene_indexes) for n in media] == [4, 2, 12]
        allocated = [i for n in media for i in n.scene_indexes]
        assert sorted(allocated) == list(range(18))
        assert len(allocated) == len(set(allocated)), "a scene reached two branches"

    def test_manifest_joins_every_branch_that_exists(self):
        nodes = {n.id: n for n in build_pipeline_dag(REFERENCE_MIX)}
        assert set(nodes["s4_manifest"].depends_on) == {
            "s3_image",
            "s3_video",
            "s3_animation",
        }

    @pytest.mark.parametrize(
        "mix, expected",
        [
            (("image",), ["s3_image"]),
            (("animation",), ["s3_animation"]),
            (("image", "video_clip"), ["s3_image", "s3_video"]),
            (("video_clip", "animation"), ["s3_video", "s3_animation"]),
        ],
    )
    def test_absent_media_types_produce_no_branch(self, mix, expected):
        """Mirrors dispatch_media_generation, which dispatches only what exists."""
        nodes = build_pipeline_dag(scenes(*mix))
        assert [n.id for n in nodes if n.kind is NodeKind.FANOUT] == expected
        manifest = next(n for n in nodes if n.id == "s4_manifest")
        assert set(manifest.depends_on) == set(expected)

    def test_empty_storyboard_still_connects_the_graph(self):
        nodes = build_pipeline_dag([])
        assert not [n for n in nodes if n.kind is NodeKind.FANOUT]
        manifest = next(n for n in nodes if n.id == "s4_manifest")
        assert manifest.depends_on == ("gate_storyboard",)
        # s1, s2, gate1, s4, s5, s6, s7, gate2, s8 -- the media wave is simply absent
        assert len(topological_waves(nodes)) == 9

    def test_unknown_media_type_is_rejected_at_compile_time(self):
        with pytest.raises(ValueError, match="media_type"):
            build_pipeline_dag(scenes("hologram"))


class TestGates:
    def test_both_gates_are_signals_and_execute_nothing(self):
        gates = [n for n in build_pipeline_dag(REFERENCE_MIX) if n.is_gate]
        assert [g.signal_name for g in gates] == [
            SIGNAL_STORYBOARD_APPROVED,
            SIGNAL_DRAFT_APPROVED,
        ]
        assert all(g.label == "" and g.queue == "-" for g in gates)

    def test_gate_1_sits_between_storyboard_and_all_media(self):
        nodes = build_pipeline_dag(REFERENCE_MIX)
        sequence = stage_sequence(nodes)
        at = gate_positions(nodes)[SIGNAL_STORYBOARD_APPROVED]
        assert sequence[at - 1] == "storyboard_generation"
        assert set(sequence[at:at + 3]) == {
            "image_generation",
            "video_generation",
            "animation_generation",
        }

    def test_gate_2_sits_between_draft_and_final(self):
        nodes = build_pipeline_dag(REFERENCE_MIX)
        sequence = stage_sequence(nodes)
        at = gate_positions(nodes)[SIGNAL_DRAFT_APPROVED]
        assert sequence[at - 1] == "prototype_draft"
        assert sequence[at] == "final_render"

    def test_stopping_at_the_draft_drops_gate_2_and_the_final(self):
        nodes = build_pipeline_dag(REFERENCE_MIX, include_final_render=False)
        assert stage_sequence(nodes)[-1] == "prototype_draft"
        assert SIGNAL_DRAFT_APPROVED not in gate_positions(nodes)


class TestCompileTimeErrors:
    """
    A cycle must be a ValueError naming the nodes, at compile time -- not a
    workflow parked forever on an await nobody will satisfy.
    """

    def test_cycle_raises_rather_than_deadlocking(self):
        a = DagNode("a", NodeKind.ACTIVITY, "x", "default", depends_on=("b",))
        b = DagNode("b", NodeKind.ACTIVITY, "y", "default", depends_on=("a",))
        with pytest.raises(ValueError, match="cycle"):
            topological_waves([a, b])

    def test_dangling_dependency_raises(self):
        a = DagNode("a", NodeKind.ACTIVITY, "x", "default", depends_on=("ghost",))
        with pytest.raises(ValueError, match="unknown node 'ghost'"):
            topological_waves([a])

    def test_duplicate_node_id_raises(self):
        a = DagNode("a", NodeKind.ACTIVITY, "x", "default")
        with pytest.raises(ValueError, match="duplicate node id"):
            topological_waves([a, a])


class TestStageNumbering:
    def test_checkpoint_index_matches_what_the_live_pipeline_writes(self):
        """
        Read off the save_checkpoint call sites at HEAD, not off the spec.
        tts_audio is stage_index 4, not 5 (stage5_voiceover.py:619,668).
        """
        assert CHECKPOINT_STAGE_INDEX["transcript_refinement"] == 1
        assert CHECKPOINT_STAGE_INDEX["storyboard_generation"] == 2
        assert CHECKPOINT_STAGE_INDEX["image_generation"] == 3
        assert CHECKPOINT_STAGE_INDEX["video_generation"] == 3
        assert CHECKPOINT_STAGE_INDEX["animation_generation"] == 3
        assert CHECKPOINT_STAGE_INDEX["tts_audio"] == 4
        assert CHECKPOINT_STAGE_INDEX["talking_head_render"] == 5
        assert CHECKPOINT_STAGE_INDEX["prototype_draft"] == 6
        assert CHECKPOINT_STAGE_INDEX["final_render"] == 7

    def test_composition_manifest_has_no_live_checkpoint_index(self):
        """
        The dispatched Stage 4 task writes no checkpoint. The only
        composition_manifest write is in an undispatched orchestrator task
        (pipeline_orchestrator_v2.py:620) and uses stage_index=4, which
        tts_audio already occupies. Mapping it to None keeps that fact
        visible instead of inventing a number.
        """
        assert CHECKPOINT_STAGE_INDEX["composition_manifest"] is None

    def test_spec_stage_numbers_run_one_to_eight(self):
        stages = sorted(
            {n.spec_stage for n in build_pipeline_dag(REFERENCE_MIX) if n.spec_stage}
        )
        assert stages == [1, 2, 3, 4, 5, 6, 7, 8]


def test_every_node_token_is_the_one_the_key_scheme_knows():
    """dag.py and idempotency.py must not drift apart on stage tokens."""
    for node in build_pipeline_dag(REFERENCE_MIX):
        if node.is_gate:
            continue
        assert node.idempotency_stage == STAGE_TOKENS[node.label], node.id


def test_media_branch_table_covers_every_media_type():
    from models.task_result import MediaType

    assert {b.media_type for b in MEDIA_BRANCHES} == {m.value for m in MediaType}
