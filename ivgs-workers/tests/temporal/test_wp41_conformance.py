"""
WP-41 Task 4 — conformance against the banked 2026-08-23 reference run.

AD-05 §12 verifies the migration against a known-good reference output. This is
the part of that gate that can run before any real render: does the workflow's
stage graph, compiled from the reference run's OWN storyboard, produce the stage
sequence the real pipeline executed, with the gates where the run's own timing
says they were?

It is the baseline for the eventual cutover comparison, and it is deliberately
two-sided. The reference record does not contain everything that ran:

  * ``animation_generation`` is absent because the animation run reported under
    ``image_generation`` and, since ``pipeline_checkpoints`` upserts on
    ``(job_id, stage_name)``, overwrote it -- WP-39;
  * ``composition_manifest`` is absent because the live Stage 4 task writes no
    checkpoint at all, so no run can produce one.

A test that demanded an exact sequence match would fail a correct workflow. A
test that compared loosely would bless a record that lost a stage. So both
absences are asserted BY NAME, with their reasons, and anything else is a
failure.

Skips if the banked dump is not mounted. A skip is not a pass -- if this file
is silent, /mnt/ivgs-shared was not there.
"""

from __future__ import annotations

import pytest

from temporal_pipeline.conformance import (
    MEDIA_LABELS,
    REFERENCE_JOB_ID,
    REFERENCE_PROJECT_ID,
    REFERENCE_SQL,
    UNCHECKPOINTED_STAGES,
    compare,
    load_reference_run,
    parse_dump,
)
from temporal_pipeline.dag import (
    SIGNAL_DRAFT_APPROVED,
    SIGNAL_STORYBOARD_APPROVED,
    build_pipeline_dag,
)
from temporal_pipeline.reference_storyboard import REFERENCE_MEDIA_TYPES

pytestmark = pytest.mark.skipif(
    not REFERENCE_SQL.exists(),
    reason=f"banked reference run not mounted at {REFERENCE_SQL}",
)


@pytest.fixture(scope="module")
def run():
    return load_reference_run()


@pytest.fixture(scope="module")
def report(run):
    return compare(run)


class TestTheBankedRunLoads:
    def test_it_is_the_run_we_think_it_is(self, run):
        assert run.job_id == REFERENCE_JOB_ID
        assert run.project_id == REFERENCE_PROJECT_ID
        assert run.job_status == "success"

    def test_the_storyboard_is_eighteen_scenes_in_three_media_types(self, run):
        assert len(run.scenes) == 18
        assert run.media_types() == {"image": 4, "animation": 12, "video_clip": 2}

    def test_the_hardcoded_reference_storyboard_matches_the_bank(self, run):
        """
        ``reference_storyboard.py`` reproduces this storyboard so demos and unit
        tests can use it without the NFS mount. If the two ever disagree, the
        constant is lying about the run it claims to reproduce.
        """
        assert tuple(s.media_type for s in run.scenes) == REFERENCE_MEDIA_TYPES

    def test_it_stopped_at_the_draft(self, run):
        assert run.resume_from_stage == "prototype_draft"
        assert run.reached_final_render() is False


class TestStageSequence:
    def test_the_spine_matches_exactly(self, report):
        assert report.spine_matches, (
            f"reference {report.reference_spine} != workflow {report.workflow_spine}"
        )
        assert report.reference_spine == [
            "transcript_refinement",
            "storyboard_generation",
            "<media>",
            "tts_audio",
            "talking_head_render",
            "prototype_draft",
        ]

    def test_the_reference_executed_these_stages_in_this_order(self, run):
        assert run.stage_sequence() == [
            "transcript_refinement",
            "storyboard_generation",
            "image_generation",
            "video_generation",
            "tts_audio",
            "talking_head_render",
            "prototype_draft",
        ]

    def test_the_workflow_covers_every_stage_the_record_holds(self, report):
        assert report.media_missing_from_workflow == []
        for label in report.reference_sequence:
            assert label in report.workflow_sequence, label

    def test_it_conforms(self, report):
        assert report.conforms, report.notes


class TestTheTwoKnownAbsences:
    def test_animation_generation_is_missing_from_the_record(self, report):
        """
        Three media stages executed. The record holds two. WP-39: the animation
        run reported under image_generation, and the upsert on
        (job_id, stage_name) overwrote 4 scenes of image work with 12 scenes of
        animation work.
        """
        assert report.media_missing_from_reference == ["animation_generation"]
        assert set(report.reference_media) == {"image_generation", "video_generation"}
        assert set(report.workflow_media) == set(MEDIA_LABELS)

    def test_the_surviving_image_row_carries_the_animation_count(self, run):
        """
        The defect, still legible in the banked data: the storyboard has 4
        image scenes, and the image_generation checkpoint says 12 succeeded --
        which is the animation count.
        """
        tables = parse_dump(REFERENCE_SQL.read_text(encoding="utf-8"))
        row = next(
            r
            for r in tables["pipeline_checkpoints"]
            if r["job_id"] == run.job_id and r["stage_name"] == "image_generation"
        )
        assert '"successful_count": 12' in (row["checkpoint_data"] or "")
        assert run.media_types()["image"] == 4
        assert run.media_types()["animation"] == 12

    def test_the_video_row_never_completed(self, run):
        """The join never closed -- the same defect from the other side."""
        video = next(c for c in run.checkpoints if c.stage_name == "video_generation")
        assert video.status == "pending"
        assert video.completed_at is None

    def test_composition_manifest_can_never_appear_in_a_checkpoint_record(
        self, run, report
    ):
        """
        The dispatched Stage 4 task writes no checkpoint. Excluding it from the
        comparison is not a convenience -- including it would fail every real
        run forever.
        """
        assert "composition_manifest" not in run.stage_sequence()
        assert report.stages_excluded_from_comparison == list(UNCHECKPOINTED_STAGES)
        assert "composition_manifest" in report.workflow_sequence


class TestGatePlacement:
    def test_gate_1_sits_where_the_run_waited(self, run, report):
        """
        pipeline_checkpoints has no row for a gate, so the record's only
        evidence a human was asked something is the hole in the timeline:
        storyboard_generation completed 16:03:25, image_generation started
        16:45:05. 41 minutes 40 seconds of nothing.
        """
        assert report.gate1_after == "storyboard_generation"
        assert report.gate1_before in MEDIA_LABELS
        gap = run.gap_seconds("storyboard_generation", "image_generation")
        assert gap is not None and gap > 2000
        assert report.gate1_reference_gap_seconds == gap

    def test_no_media_stage_started_before_the_storyboard_finished(self, run):
        done = next(
            c.completed_at
            for c in run.checkpoints
            if c.stage_name == "storyboard_generation"
        )
        for cp in run.checkpoints:
            if cp.stage_name in MEDIA_LABELS:
                assert cp.started_at > done, cp.stage_name

    def test_gate_2_sits_after_the_draft_and_the_run_stopped_there(self, run, report):
        """
        The run reached prototype_draft and went no further:
        resume_from_stage='prototype_draft', no final_render checkpoint. That
        IS gate 2 holding -- the graph puts the gate in the same place.
        """
        assert report.gate2_after == "prototype_draft"
        assert run.reached_final_render() is False
        assert report.reference_sequence[-1] == "prototype_draft"

    def test_gate_positions_come_from_the_full_graph(self, report):
        assert SIGNAL_STORYBOARD_APPROVED in report.gate_positions
        assert SIGNAL_DRAFT_APPROVED in report.gate_positions


class TestTheComparisonIsNotVacuous:
    """
    Each of these takes the reference run and perturbs the graph. If the
    comparison passed anyway, it would be proving nothing.
    """

    def test_a_graph_missing_the_animation_branch_fails(self, run):
        """
        The case the reference record CANNOT catch on its own. The record never
        named animation_generation, so a graph with no animation branch matches
        it perfectly -- spine, media set and all. What refuses it is the
        storyboard: 12 of its 18 scenes are animation.
        """
        without_animation = [s for s in run.scenes if s.media_type != "animation"]
        report = compare(
            run, build_pipeline_dag(without_animation, include_final_render=False)
        )
        assert "animation_generation" not in report.workflow_media
        # matches the record exactly, which is precisely the trap
        assert report.media_missing_from_reference == []
        assert report.spine_matches
        # and is still refused, because the storyboard says otherwise
        assert report.media_types_uncovered == ["animation_generation"]
        assert not report.conforms

    def test_a_graph_with_a_reordered_spine_fails(self, run):
        from temporal_pipeline.dag import DagNode

        broken = [
            n
            for n in build_pipeline_dag(run.scenes, include_final_render=False)
            if n.id != "s6_talking_head"
        ]
        # Re-point the draft at the manifest only, so the head vanishes from
        # the sequence entirely.
        broken = [
            DagNode(**{**n.__dict__, "depends_on": ("s4_manifest",)})
            if n.id == "s7_draft"
            else n
            for n in broken
        ]
        report = compare(run, broken)
        assert not report.spine_matches
        assert not report.conforms

    def test_a_graph_with_no_gates_fails(self, run):
        nodes = [
            n
            for n in build_pipeline_dag(run.scenes, include_final_render=False)
            if not n.is_gate
        ]
        # gate_storyboard is a dependency of the media nodes, so removing it
        # must be caught at compile time rather than silently ignored.
        with pytest.raises(ValueError, match="unknown node"):
            compare(run, nodes)
