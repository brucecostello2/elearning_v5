"""
WP-04-FRAME-ALIGN - frame-aligned segment splitting (AD-03 s4.4)

Closes AD-03 s10 criterion 3's arithmetic half: piece boundaries land on whole
frames at the target fps, so the engine's per-piece frame-count round-up cannot
accumulate across the concat.

The drift these tests model was measured on a real artifact on 2026-08-23:
head 6465 frames at 30/1 CFR = 215.500000 s against 214.881334 s of narration,
0.618666 s = 18.56 frames. See the WP-04 report and
scripts/measure_head_av_drift.sh.
"""

from __future__ import annotations

import math

import pytest

from tasks.talking_head_task import (
    MAX_SEGMENT_SECONDS,
    TARGET_FPS_DEFAULT,
    plan_frame_aligned_pieces,
)

# The six real Stage 5 scene durations for project 3814f845-4668-496b-a88a-53fea95897c2,
# probed from the stored WAVs (pcm_s24le, 48 kHz mono) on 2026-08-23.
REAL_SCENE_DURATIONS = [
    7.094667,
    5.558667,
    31.397333,
    75.349333,
    57.108667,
    38.372667,
]


def _old_pieces(scene_dur: float, max_seg: float = MAX_SEGMENT_SECONDS):
    """The pre-WP-04 arithmetic, verbatim, for the regression comparison.

    Was talking_head_task.py:495-497 at HEAD 9af5a48:
        n_parts   = ceil(scene_dur / MAX_SEGMENT_SECONDS)
        piece_dur = scene_dur / n_parts
    with the last piece running to EOF.
    """
    if scene_dur <= max_seg or scene_dur <= 0.0:
        return [scene_dur]
    n_parts = math.ceil(scene_dur / max_seg)
    piece_dur = scene_dur / n_parts
    out = []
    for p in range(n_parts):
        if p < n_parts - 1:
            out.append(piece_dur)
        else:
            out.append(scene_dur - p * piece_dur)
    return out


def _new_piece_durations(scene_dur: float, fps: int = TARGET_FPS_DEFAULT):
    """Actual audio length of each piece the new planner produces."""
    plans = plan_frame_aligned_pieces(scene_dur, MAX_SEGMENT_SECONDS, fps)
    out = []
    for i, plan in enumerate(plans):
        if plan["duration_s"] is not None:
            out.append(plan["duration_s"])
        else:
            # Runs to EOF from its start offset.
            out.append(scene_dur - plan["start_s"])
    assert len(out) == len(plans)
    return out


def _engine_video_seconds(piece_durations, fps: int = TARGET_FPS_DEFAULT) -> float:
    """What the engine emits: whole frames, so ceil(d * fps) frames per piece.

    This is the model of the engine, NOT the engine. The real per-piece
    quantisation on node-04 is unverified - WP-04 Finding 4 records a ~0.5 s
    residual this model does not explain. These tests bound what the ARITHMETIC
    contributes; they do not claim the artifact will hit < 1 frame.
    """
    frames = sum(math.ceil(round(d * fps, 9)) for d in piece_durations)
    return frames / fps


class TestPieceTiling:
    """Whatever else changes, the pieces must still tile the source exactly."""

    @pytest.mark.parametrize("scene_dur", REAL_SCENE_DURATIONS)
    def test_pieces_tile_without_gap_or_overlap(self, scene_dur):
        plans = plan_frame_aligned_pieces(scene_dur, MAX_SEGMENT_SECONDS)
        # Each piece starts where the previous one ended.
        for prev, cur in zip(plans, plans[1:]):
            assert prev["duration_s"] is not None, "only the last piece runs to EOF"
            expected_start = prev["start_s"] + prev["duration_s"]
            assert cur["start_s"] == pytest.approx(expected_start, abs=1e-9)
        assert plans[-1]["duration_s"] is None, "the last piece must run to EOF"
        assert plans[0]["start_s"] == 0.0

    @pytest.mark.parametrize("scene_dur", REAL_SCENE_DURATIONS)
    def test_piece_audio_sums_to_source(self, scene_dur):
        assert sum(_new_piece_durations(scene_dur)) == pytest.approx(scene_dur, abs=1e-9)

    @pytest.mark.parametrize("scene_dur", REAL_SCENE_DURATIONS)
    def test_piece_count_is_unchanged(self, scene_dur):
        """Piece COUNT was never the defect - the OOM bound must not move."""
        assert len(plan_frame_aligned_pieces(scene_dur, MAX_SEGMENT_SECONDS)) == len(
            _old_pieces(scene_dur)
        )

    @pytest.mark.parametrize("scene_dur", REAL_SCENE_DURATIONS)
    def test_no_piece_exceeds_the_oom_bound(self, scene_dur):
        for d in _new_piece_durations(scene_dur):
            assert d <= MAX_SEGMENT_SECONDS + 1e-6


class TestFrameAlignment:
    """The fix itself: every piece but the last is a whole number of frames."""

    @pytest.mark.parametrize("scene_dur", REAL_SCENE_DURATIONS)
    def test_non_final_pieces_are_whole_frames(self, scene_dur):
        plans = plan_frame_aligned_pieces(scene_dur, MAX_SEGMENT_SECONDS)
        for plan in plans[:-1]:
            frames = plan["duration_s"] * TARGET_FPS_DEFAULT
            assert frames == pytest.approx(round(frames), abs=1e-9)
            assert plan["frames"] == round(frames)

    @pytest.mark.parametrize("scene_dur", REAL_SCENE_DURATIONS)
    def test_non_final_pieces_start_on_whole_frames(self, scene_dur):
        plans = plan_frame_aligned_pieces(scene_dur, MAX_SEGMENT_SECONDS)
        for plan in plans:
            frames = plan["start_s"] * TARGET_FPS_DEFAULT
            assert frames == pytest.approx(round(frames), abs=1e-9)

    @pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
    def test_alignment_holds_at_any_fps(self, fps):
        """The planner takes fps as a parameter; Q5 is a value, not a hardcode."""
        plans = plan_frame_aligned_pieces(75.349333, MAX_SEGMENT_SECONDS, fps)
        for plan in plans[:-1]:
            frames = plan["duration_s"] * fps
            assert frames == pytest.approx(round(frames), abs=1e-9)


class TestDriftRegression:
    """Fails against the pre-fix arithmetic, passes against the fix."""

    @pytest.mark.parametrize("scene_dur", [d for d in REAL_SCENE_DURATIONS if d > MAX_SEGMENT_SECONDS])
    def test_intra_scene_rounding_is_eliminated(self, scene_dur):
        """A split scene must round exactly once - on its final piece - not per piece."""
        new_video = _engine_video_seconds(_new_piece_durations(scene_dur))
        new_drift = new_video - scene_dur
        # One piece can round up by at most one frame; zero pieces round up by more.
        assert 0.0 <= new_drift < 1.0 / TARGET_FPS_DEFAULT + 1e-9

    def test_new_arithmetic_beats_old_on_the_real_material(self):
        """The measured case: six real scenes, 11 pieces."""
        old_total = sum(
            _engine_video_seconds(_old_pieces(d)) for d in REAL_SCENE_DURATIONS
        )
        new_total = sum(
            _engine_video_seconds(_new_piece_durations(d)) for d in REAL_SCENE_DURATIONS
        )
        narration = sum(REAL_SCENE_DURATIONS)

        old_drift = old_total - narration
        new_drift = new_total - narration

        # The pre-fix arithmetic drifts by more than a frame. This assertion is the
        # "fails against the pre-fix code" demonstration required by the queue rules.
        assert old_drift > 1.0 / TARGET_FPS_DEFAULT

        # The fix strictly reduces it, and bounds it at one frame per SCENE rather
        # than one per PIECE. Six scenes, so at most six frames from the arithmetic -
        # down from eleven pieces' worth.
        assert new_drift < old_drift
        assert new_drift <= len(REAL_SCENE_DURATIONS) / TARGET_FPS_DEFAULT + 1e-9

    def test_a_whole_frame_scene_now_drifts_by_nothing_at_all(self):
        """When the source is itself frame-aligned, the arithmetic adds zero."""
        scene_dur = 2400 / TARGET_FPS_DEFAULT  # 80.0 s, exactly 2400 frames
        pieces = _new_piece_durations(scene_dur)
        assert _engine_video_seconds(pieces) == pytest.approx(scene_dur, abs=1e-9)

        old = _engine_video_seconds(_old_pieces(scene_dur))
        assert old == pytest.approx(scene_dur, abs=1e-9)  # 3 x 800 frames, also clean


class TestDegenerateInputs:
    def test_zero_duration_yields_one_eof_piece(self):
        plans = plan_frame_aligned_pieces(0.0, MAX_SEGMENT_SECONDS)
        assert plans == [{"start_s": 0.0, "duration_s": None, "frames": None}]

    def test_short_scene_is_not_split(self):
        plans = plan_frame_aligned_pieces(7.094667, MAX_SEGMENT_SECONDS)
        assert len(plans) == 1
        assert plans[0]["duration_s"] is None

    def test_zero_fps_does_not_divide_by_zero(self):
        plans = plan_frame_aligned_pieces(75.349333, MAX_SEGMENT_SECONDS, 0)
        assert len(plans) == 1

    def test_fewer_frames_than_parts_falls_back_to_one_piece(self):
        plans = plan_frame_aligned_pieces(0.05, 0.001, TARGET_FPS_DEFAULT)
        assert len(plans) == 1
        assert plans[0]["duration_s"] is None
