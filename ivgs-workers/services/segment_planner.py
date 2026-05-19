"""
IVGS v5 — Segment Planner
=============================

Splits a composition manifest into 10–30 second segments for parallel
rendering in Stage 8 (Final Render) per §6.1.

Segment planning rules:
- Segments are 10–30 seconds long (configurable)
- Scene boundaries are preferred split points (no mid-scene cuts when possible)
- Short scenes are grouped into a single segment
- Long scenes are split at natural pause points if caption timestamps available
- Each segment tracks: start_time, end_time, scene_refs, status, checksum
- Segments are stored in the render_segments table
- Failed segments retry independently without discarding completed segments
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger("ivgs.services.segment_planner")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SceneRef:
    """Reference to a scene within a segment."""
    scene_id: str
    scene_index: int
    offset: float  # Offset within the segment
    duration: float  # Duration of this scene portion in the segment


@dataclass
class RenderSegment:
    """A segment of the composition for independent rendering."""
    segment_id: str
    project_id: str
    segment_index: int
    start_time: float
    end_time: float
    duration: float
    scene_refs: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    sha256_hash: str = ""
    retry_count: int = 0
    max_retries: int = 2

    @property
    def is_retriable(self) -> bool:
        return self.retry_count < self.max_retries


# ---------------------------------------------------------------------------
# SegmentPlanner
# ---------------------------------------------------------------------------

class SegmentPlanner:
    """
    Plans render segments from a composition manifest.

    Strategy:
    1. Prefer scene boundaries as segment split points
    2. Group short scenes together (sum duration < max_segment_duration)
    3. Split long scenes if they exceed max_segment_duration
    4. Ensure no segment is shorter than min_segment_duration
    """

    def __init__(
        self,
        max_segment_duration: float = 30.0,
        min_segment_duration: float = 10.0,
        max_retries: int = 2,
    ):
        self._max_duration = max_segment_duration
        self._min_duration = min_segment_duration
        self._max_retries = max_retries

    def plan_segments(
        self,
        project_id: str,
        scenes: List[Dict[str, Any]],
    ) -> List[RenderSegment]:
        """
        Plan render segments from scene list.

        Each scene dict should have: scene_id, scene_index, duration_seconds.
        Returns ordered list of RenderSegments.
        """
        if not scenes:
            return []

        sorted_scenes = sorted(scenes, key=lambda s: s.get("scene_index", 0))

        segments: List[RenderSegment] = []
        current_scenes: List[Dict[str, Any]] = []
        current_duration = 0.0
        segment_index = 0
        timeline_offset = 0.0

        for scene in sorted_scenes:
            scene_duration = scene.get("duration_seconds", 10.0)

            # Case 1: Single scene exceeds max duration → split it
            if scene_duration > self._max_duration:
                # Flush current buffer first
                if current_scenes:
                    seg = self._create_segment(
                        project_id=project_id,
                        segment_index=segment_index,
                        scenes=current_scenes,
                        start_time=timeline_offset - current_duration,
                    )
                    segments.append(seg)
                    segment_index += 1
                    current_scenes = []
                    current_duration = 0.0

                # Split long scene
                split_segments = self._split_long_scene(
                    project_id=project_id,
                    scene=scene,
                    start_index=segment_index,
                    timeline_offset=timeline_offset,
                )
                segments.extend(split_segments)
                segment_index += len(split_segments)
                timeline_offset += scene_duration
                continue

            # Case 2: Adding this scene would exceed max → flush buffer
            if current_duration + scene_duration > self._max_duration and current_scenes:
                seg = self._create_segment(
                    project_id=project_id,
                    segment_index=segment_index,
                    scenes=current_scenes,
                    start_time=timeline_offset - current_duration,
                )
                segments.append(seg)
                segment_index += 1
                current_scenes = []
                current_duration = 0.0

            # Add scene to current buffer
            current_scenes.append(scene)
            current_duration += scene_duration
            timeline_offset += scene_duration

        # Flush remaining scenes
        if current_scenes:
            # If remaining is too short and we have previous segments, merge with last
            if (
                current_duration < self._min_duration
                and segments
                and segments[-1].duration + current_duration <= self._max_duration * 1.2
            ):
                # Merge with last segment
                last_seg = segments[-1]
                for scene in current_scenes:
                    offset_in_seg = last_seg.duration
                    last_seg.scene_refs.append({
                        "scene_id": scene["scene_id"],
                        "scene_index": scene.get("scene_index", 0),
                        "offset": offset_in_seg,
                        "duration": scene.get("duration_seconds", 10.0),
                    })
                    last_seg.duration += scene.get("duration_seconds", 10.0)
                last_seg.end_time = last_seg.start_time + last_seg.duration
            else:
                seg = self._create_segment(
                    project_id=project_id,
                    segment_index=segment_index,
                    scenes=current_scenes,
                    start_time=timeline_offset - current_duration,
                )
                segments.append(seg)

        logger.info(
            "segments_planned",
            project_id=project_id,
            total_segments=len(segments),
            total_duration=sum(s.duration for s in segments),
            avg_duration=round(
                sum(s.duration for s in segments) / max(len(segments), 1), 2,
            ),
        )

        return segments

    def _create_segment(
        self,
        project_id: str,
        segment_index: int,
        scenes: List[Dict[str, Any]],
        start_time: float,
    ) -> RenderSegment:
        """Create a RenderSegment from a list of scenes."""
        scene_refs: List[Dict[str, Any]] = []
        offset = 0.0

        for scene in scenes:
            duration = scene.get("duration_seconds", 10.0)
            scene_refs.append({
                "scene_id": scene["scene_id"],
                "scene_index": scene.get("scene_index", 0),
                "offset": offset,
                "duration": duration,
            })
            offset += duration

        return RenderSegment(
            segment_id=str(uuid4()),
            project_id=project_id,
            segment_index=segment_index,
            start_time=start_time,
            end_time=start_time + offset,
            duration=offset,
            scene_refs=scene_refs,
            max_retries=self._max_retries,
        )

    def _split_long_scene(
        self,
        project_id: str,
        scene: Dict[str, Any],
        start_index: int,
        timeline_offset: float,
    ) -> List[RenderSegment]:
        """Split a single long scene into multiple segments."""
        scene_duration = scene.get("duration_seconds", 10.0)
        num_segments = math.ceil(scene_duration / self._max_duration)
        segment_duration = scene_duration / num_segments

        segments: List[RenderSegment] = []
        for i in range(num_segments):
            seg_start = timeline_offset + (i * segment_duration)
            seg_duration = min(segment_duration, scene_duration - (i * segment_duration))

            segments.append(RenderSegment(
                segment_id=str(uuid4()),
                project_id=project_id,
                segment_index=start_index + i,
                start_time=seg_start,
                end_time=seg_start + seg_duration,
                duration=seg_duration,
                scene_refs=[{
                    "scene_id": scene["scene_id"],
                    "scene_index": scene.get("scene_index", 0),
                    "offset": i * segment_duration,
                    "duration": seg_duration,
                }],
                max_retries=self._max_retries,
            ))

        return segments
