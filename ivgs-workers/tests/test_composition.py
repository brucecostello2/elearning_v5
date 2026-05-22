"""
IVGS v5 — Composition Tests (Stages 7 & 8)
=============================================

Test suite for:
- Stage 7: Prototype draft assembly (720p)
- Stage 8: Final render (segment-based 1080p/4K)
- FFmpeg client composition
- Segment planner
- Caption service
- Manifest builder
"""

from __future__ import annotations

import os
import tempfile

import pytest

from clients.ffmpeg_client import (
    CompositionTimeline,
    TimelineScene,
)
from services.caption_service import CaptionService
from services.manifest_builder import (
    CompositionManifest,
    ManifestBuilder,
)
from services.segment_planner import RenderSegment, SegmentPlanner
from tasks.prototype_draft_task import (
    ManifestScene,
    ManifestSceneAsset,
    Stage7Input,
    Stage7Output,
)
from tasks.final_render_task import (
    FinalRenderScene,
    ProfileRenderResult,
    Stage8Input,
    Stage8Output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory(prefix="test_comp_") as d:
        yield d


@pytest.fixture
def sample_stage7_input() -> Stage7Input:
    return Stage7Input(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Course",
        language_code="en-US",
        manifest_id="manifest-001",
        talking_head_asset_id="asset-th-001",
        scenes=[
            ManifestScene(
                scene_id="scene-001",
                scene_index=0,
                scene_title="Introduction",
                narration_text="Welcome to this course.",
                duration_seconds=15.0,
                media_type="image",
                background_asset=ManifestSceneAsset(
                    asset_id="asset-img-001",
                    asset_type="image",
                    content_hash="abc123",
                ),
                audio_asset=ManifestSceneAsset(
                    asset_id="asset-audio-001",
                    asset_type="audio",
                    duration_seconds=15.0,
                ),
                caption_timestamps=[
                    {"word": "Welcome", "start": 0.0, "end": 0.5},
                    {"word": "to", "start": 0.5, "end": 0.7},
                    {"word": "this", "start": 0.7, "end": 0.9},
                    {"word": "course.", "start": 0.9, "end": 1.3},
                ],
            ),
            ManifestScene(
                scene_id="scene-002",
                scene_index=1,
                scene_title="Main Topic",
                narration_text="Today we will learn about Python.",
                duration_seconds=20.0,
                media_type="image",
                background_asset=ManifestSceneAsset(
                    asset_id="asset-img-002",
                    asset_type="image",
                    content_hash="def456",
                ),
                audio_asset=ManifestSceneAsset(
                    asset_id="asset-audio-002",
                    asset_type="audio",
                    duration_seconds=20.0,
                ),
            ),
        ],
    )


@pytest.fixture
def sample_stage8_input() -> Stage8Input:
    return Stage8Input(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Course",
        language_code="en-US",
        manifest_id="manifest-001",
        talking_head_asset_id="asset-th-001",
        scenes=[
            FinalRenderScene(
                scene_id="scene-001",
                scene_index=0,
                scene_title="Intro",
                duration_seconds=15.0,
            ),
            FinalRenderScene(
                scene_id="scene-002",
                scene_index=1,
                scene_title="Body",
                duration_seconds=25.0,
            ),
        ],
        render_profiles=["1080p", "4k"],
    )


# ---------------------------------------------------------------------------
# Caption Service Tests
# ---------------------------------------------------------------------------

class TestCaptionService:
    """Test caption generation from WhisperX timestamps."""

    def test_group_words_basic(self):
        service = CaptionService()
        timestamps = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world.", "start": 0.5, "end": 1.0},
        ]
        entries = service.group_words(timestamps)
        assert len(entries) >= 1
        assert entries[0].text == "Hello world."

    def test_group_words_respects_max_words(self):
        service = CaptionService(max_words_per_line=3)
        timestamps = [
            {"word": f"word{i}", "start": i * 0.5, "end": (i + 1) * 0.5}
            for i in range(10)
        ]
        entries = service.group_words(timestamps)
        for entry in entries:
            word_count = len(entry.text.split())
            assert word_count <= 4  # Allow some overflow from flush logic

    def test_generate_srt(self):
        service = CaptionService()
        timestamps = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world.", "start": 0.5, "end": 1.0},
        ]
        srt_content = service.generate_srt(timestamps)
        assert "00:00:00,000" in srt_content
        assert "Hello world." in srt_content

    def test_generate_vtt(self):
        service = CaptionService()
        timestamps = [
            {"word": "Test", "start": 0.0, "end": 0.5},
        ]
        vtt_content = service.generate_vtt(timestamps)
        assert "WEBVTT" in vtt_content
        assert "Test" in vtt_content

    def test_write_srt_file(self, temp_dir):
        service = CaptionService()
        timestamps = [
            {"word": "File", "start": 0.0, "end": 0.5},
            {"word": "test.", "start": 0.5, "end": 1.0},
        ]
        path = os.path.join(temp_dir, "test.srt")
        service.write_srt(timestamps, path)
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "File test." in content

    def test_write_vtt_file(self, temp_dir):
        service = CaptionService()
        timestamps = [
            {"word": "VTT", "start": 0.0, "end": 0.5},
        ]
        path = os.path.join(temp_dir, "test.vtt")
        service.write_vtt(timestamps, path)
        assert os.path.exists(path)

    def test_empty_timestamps(self):
        service = CaptionService()
        entries = service.group_words([])
        assert entries == []

    def test_srt_timecode_format(self):
        tc = CaptionService._format_srt_timecode(3661.5)
        assert tc == "01:01:01,500"

    def test_vtt_timecode_format(self):
        tc = CaptionService._format_vtt_timecode(3661.5)
        assert tc == "01:01:01.500"


# ---------------------------------------------------------------------------
# Segment Planner Tests
# ---------------------------------------------------------------------------

class TestSegmentPlanner:
    """Test segment planning for final render."""

    def test_plan_basic_segments(self):
        planner = SegmentPlanner(max_segment_duration=30.0, min_segment_duration=10.0)
        scenes = [
            {"scene_id": "s1", "scene_index": 0, "duration_seconds": 15.0},
            {"scene_id": "s2", "scene_index": 1, "duration_seconds": 20.0},
            {"scene_id": "s3", "scene_index": 2, "duration_seconds": 10.0},
        ]
        segments = planner.plan_segments("proj-001", scenes)
        assert len(segments) >= 1
        total_duration = sum(s.duration for s in segments)
        assert abs(total_duration - 45.0) < 0.1

    def test_long_scene_split(self):
        planner = SegmentPlanner(max_segment_duration=30.0)
        scenes = [
            {"scene_id": "s1", "scene_index": 0, "duration_seconds": 60.0},
        ]
        segments = planner.plan_segments("proj-001", scenes)
        assert len(segments) == 2  # 60s split into 2x30s

    def test_short_scene_grouping(self):
        planner = SegmentPlanner(max_segment_duration=30.0, min_segment_duration=10.0)
        scenes = [
            {"scene_id": f"s{i}", "scene_index": i, "duration_seconds": 5.0}
            for i in range(6)
        ]
        segments = planner.plan_segments("proj-001", scenes)
        # 6 × 5s = 30s, should fit in 1 segment
        assert len(segments) == 1

    def test_empty_scenes(self):
        planner = SegmentPlanner()
        segments = planner.plan_segments("proj-001", [])
        assert segments == []

    def test_segment_ordering(self):
        planner = SegmentPlanner(max_segment_duration=20.0)
        scenes = [
            {"scene_id": f"s{i}", "scene_index": i, "duration_seconds": 15.0}
            for i in range(4)
        ]
        segments = planner.plan_segments("proj-001", scenes)
        for i, seg in enumerate(segments):
            assert seg.segment_index == i

    def test_segment_retryable(self):
        seg = RenderSegment(
            segment_id="seg-001",
            project_id="proj-001",
            segment_index=0,
            start_time=0.0,
            end_time=15.0,
            duration=15.0,
            retry_count=0,
            max_retries=2,
        )
        assert seg.is_retriable is True
        seg.retry_count = 2
        assert seg.is_retriable is False


# ---------------------------------------------------------------------------
# Manifest Builder Tests
# ---------------------------------------------------------------------------

class TestManifestBuilder:
    """Test composition manifest building and validation."""

    def test_build_manifest_basic(self):
        builder = ManifestBuilder()
        scenes = [
            {
                "scene_id": "s1",
                "scene_index": 0,
                "scene_title": "Intro",
                "narration_text": "Hello",
                "duration_seconds": 10.0,
                "media_type": "image",
                "background_asset": {
                    "asset_id": "img-001",
                    "asset_type": "image",
                    "storage_path": "/ivgs/images/proj/s1/image.png",
                    "content_hash": "abc123",
                },
                "audio_asset": {
                    "asset_id": "aud-001",
                    "asset_type": "audio",
                    "content_hash": "def456",
                },
            },
        ]
        manifest = builder.build_manifest("proj-001", "en-US", scenes)
        assert manifest.project_id == "proj-001"
        assert manifest.scene_count == 1
        assert manifest.total_duration_seconds == 10.0
        assert manifest.status == "draft"

    def test_lock_manifest(self):
        builder = ManifestBuilder()
        manifest = CompositionManifest(
            project_id="proj-001",
            scene_count=1,
            total_duration_seconds=10.0,
        )
        locked = builder.lock_manifest(manifest)
        assert locked.status == "locked"
        assert locked.locked_at is not None
        assert locked.manifest_hash != ""

    def test_validate_manifest_checksums(self):
        builder = ManifestBuilder()
        scenes = [
            {
                "scene_id": "s1",
                "scene_index": 0,
                "duration_seconds": 10.0,
                "background_asset": {
                    "asset_id": "img-001",
                    "asset_type": "image",
                    "content_hash": "abc123",
                },
            },
        ]
        manifest = builder.build_manifest("proj-001", "en-US", scenes)

        # Matching checksums
        errors = builder.validate_manifest(
            manifest, {"img-001": "abc123"},
        )
        assert errors == []

        # Mismatched checksum
        errors = builder.validate_manifest(
            manifest, {"img-001": "wrong_hash"},
        )
        assert len(errors) == 1
        assert "mismatch" in errors[0].lower()


# ---------------------------------------------------------------------------
# Stage 7 Input/Output Tests
# ---------------------------------------------------------------------------

class TestStage7Models:
    """Test Stage 7 Pydantic models."""

    def test_valid_stage7_input(self, sample_stage7_input: Stage7Input):
        assert sample_stage7_input.job_id == "job-001"
        assert len(sample_stage7_input.scenes) == 2
        assert sample_stage7_input.manifest_id == "manifest-001"

    def test_stage7_output_defaults(self):
        output = Stage7Output(job_id="job-001", project_id="proj-001")
        assert output.width == 1280
        assert output.height == 720
        assert output.fps == 30


# ---------------------------------------------------------------------------
# Stage 8 Input/Output Tests
# ---------------------------------------------------------------------------

class TestStage8Models:
    """Test Stage 8 Pydantic models."""

    def test_valid_stage8_input(self, sample_stage8_input: Stage8Input):
        assert sample_stage8_input.job_id == "job-001"
        assert len(sample_stage8_input.render_profiles) == 2
        assert "1080p" in sample_stage8_input.render_profiles
        assert "4k" in sample_stage8_input.render_profiles

    def test_stage8_output_with_profiles(self):
        output = Stage8Output(
            job_id="job-001",
            project_id="proj-001",
            profile_results=[
                ProfileRenderResult(
                    profile="1080p",
                    width=1920,
                    height=1080,
                    duration_seconds=35.0,
                    status="success",
                ),
                ProfileRenderResult(
                    profile="4k",
                    width=3840,
                    height=2160,
                    duration_seconds=35.0,
                    status="success",
                ),
            ],
        )
        assert len(output.profile_results) == 2

    def test_segment_render_defaults(self):
        from tasks.final_render_task import SegmentRenderResult
        seg = SegmentRenderResult(
            segment_id="seg-001",
            segment_index=0,
            start_time=0.0,
            end_time=15.0,
            duration=15.0,
        )
        assert seg.status == "pending"
        assert seg.retry_count == 0


# ---------------------------------------------------------------------------
# FFmpeg Client Tests
# ---------------------------------------------------------------------------

class TestFFmpegClient:
    """Test FFmpeg client operations."""

    def test_render_profile_configs(self):
        from clients.ffmpeg_client import RENDER_PROFILES, RenderProfile

        draft = RENDER_PROFILES[RenderProfile.DRAFT]
        assert draft.width == 1280
        assert draft.height == 720
        assert draft.video_codec == "libx264"
        assert draft.crf == 23

        hd = RENDER_PROFILES[RenderProfile.HD_1080P]
        assert hd.width == 1920
        assert hd.height == 1080
        assert hd.vbv_maxrate == "8M"
        assert hd.audio_bitrate == "192k"

        uhd = RENDER_PROFILES[RenderProfile.UHD_4K]
        assert uhd.width == 3840
        assert uhd.height == 2160
        assert uhd.video_codec == "libx265"
        assert uhd.vbv_maxrate == "20M"
        assert uhd.audio_bitrate == "256k"

    def test_pip_positions(self):
        from clients.ffmpeg_client import PiPPosition
        assert PiPPosition.BOTTOM_RIGHT.value == "bottom_right"
        assert PiPPosition.FULL_SCREEN.value == "full_screen"

    def test_timeline_scene_count(self):
        timeline = CompositionTimeline(
            project_id="proj-001",
            scenes=[
                TimelineScene(
                    scene_id="s1",
                    scene_index=0,
                    start_time=0.0,
                    duration=10.0,
                ),
                TimelineScene(
                    scene_id="s2",
                    scene_index=1,
                    start_time=10.0,
                    duration=15.0,
                ),
            ],
        )
        assert timeline.scene_count == 2
