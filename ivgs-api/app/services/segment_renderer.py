"""Segment-based partial render engine.

Divides the composition manifest into 30-second segments.
Each segment is an independently renderable and cacheable unit.
Failed segments can be retried individually.
Assembly uses FFmpeg concat demuxer for final stitch.
"""

import logging
import os
import subprocess
import tempfile
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models.segment import RenderSegment
from app.models.manifest import CompositionManifest
from app.services.manifest_service import ManifestService
from app.services.corruption_detector import CorruptionDetector

logger = logging.getLogger(__name__)

WORKDIR = os.environ.get('WORKDIR', '/mnt/workdir')
DEFAULT_SEGMENT_DURATION_MS = 30_000   # 30 seconds per segment
MAX_RENDER_RETRIES = 3


class SegmentRenderer:
    """Segment-based render engine for partial recovery."""

    def __init__(self, db: Session):
        self.db = db
        self.manifest_svc = ManifestService(db)
        self.corruption_detector = CorruptionDetector()

    def plan_segments(
        self, job_id: str,
        segment_duration_ms: int = DEFAULT_SEGMENT_DURATION_MS
    ) -> List[RenderSegment]:
        """Create segment plan from locked manifest.

        Returns list of RenderSegment objects (persisted to DB).
        Existing segments are not recreated (idempotent).
        """
        manifest = (self.db.query(CompositionManifest)
                    .filter(CompositionManifest.job_id == job_id)
                    .first())
        if not manifest:
            raise ValueError(f"No manifest for job {job_id}")
        if manifest.status != 'locked':
            raise ValueError(
                f"Manifest must be locked to plan segments "
                f"(current: {manifest.status})"
            )

        total_ms = manifest.total_duration_ms
        segments = []
        seg_idx = 0
        start_ms = 0

        while start_ms < total_ms:
            end_ms = min(start_ms + segment_duration_ms, total_ms)

            # Skip if segment already exists
            existing = (
                self.db.query(RenderSegment)
                .filter(RenderSegment.job_id == job_id,
                        RenderSegment.segment_index == seg_idx)
                .first()
            )
            if not existing:
                # Gather input assets for this segment from manifest
                input_assets = self._gather_segment_inputs(
                    manifest, start_ms, end_ms
                )
                seg = RenderSegment(
                    job_id=job_id,
                    segment_index=seg_idx,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    input_assets=input_assets,
                )
                self.db.add(seg)
                segments.append(seg)
            else:
                segments.append(existing)

            start_ms = end_ms
            seg_idx += 1

        self.db.commit()
        logger.info(
            "Planned %d segments for job %s (total: %dms)",
            seg_idx, job_id, total_ms
        )
        return segments

    def render_segment(
        self, job_id: str, segment_index: int,
        worker_id: str = "unknown"
    ) -> RenderSegment:
        """Render a single segment. Returns updated RenderSegment.

        Uses ManifestService to generate the FFmpeg command for this
        segment's time range, then executes it.
        """
        segment = (
            self.db.query(RenderSegment)
            .filter(RenderSegment.job_id == job_id,
                    RenderSegment.segment_index == segment_index)
            .first()
        )
        if not segment:
            raise ValueError(
                f"Segment {segment_index} not found for job {job_id}"
            )

        if segment.status == 'complete':
            logger.info("Segment %d already complete — skipping", segment_index)
            return segment

        if segment.attempts >= MAX_RENDER_RETRIES:
            segment.mark_failed(
                f"Max retries ({MAX_RENDER_RETRIES}) exhausted"
            )
            self.db.commit()
            return segment

        segment.mark_rendering(worker_id)
        self.db.commit()

        try:
            cmd_str, output_path = self.manifest_svc.get_ffmpeg_commands(
                job_id=job_id,
                segment_index=segment_index,
                segment_start_ms=segment.start_ms,
                segment_end_ms=segment.end_ms,
            )

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

            logger.info(
                "Rendering segment %d for job %s (%dms–%dms)",
                segment_index, job_id, segment.start_ms, segment.end_ms
            )

            result = subprocess.run(
                cmd_str, shell=True,
                capture_output=True, text=True,
                timeout=300  # 5 minute max per 30-second segment
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg failed (rc={result.returncode}): "
                    f"{result.stderr[-500:]}"
                )

            # Validate output
            issues = self.corruption_detector.validate_media(
                output_path, 'video'
            )
            if issues:
                raise RuntimeError(
                    f"Segment output corrupted: {'; '.join(issues)}"
                )

            segment.mark_complete(output_path)
            self.db.commit()
            logger.info(
                "Segment %d complete: %s (%.1fs render time)",
                segment_index, output_path,
                segment.render_duration_seconds or 0
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Segment %d failed for job %s: %s",
                segment_index, job_id, error_msg
            )
            segment.mark_failed(error_msg)
            self.db.commit()

        return segment

    def get_incomplete_segments(self, job_id: str) -> List[RenderSegment]:
        """Return segments that still need rendering."""
        return (
            self.db.query(RenderSegment)
            .filter(RenderSegment.job_id == job_id,
                    RenderSegment.status.in_(['pending', 'failed']))
            .order_by(RenderSegment.segment_index)
            .all()
        )

    def assemble_segments(self, job_id: str) -> str:
        """Concatenate all completed segments into final video.

        Uses FFmpeg concat demuxer — fast, lossless concat.
        Returns path to assembled video.
        """
        segments = (
            self.db.query(RenderSegment)
            .filter(RenderSegment.job_id == job_id,
                    RenderSegment.status == 'complete')
            .order_by(RenderSegment.segment_index)
            .all()
        )

        if not segments:
            raise ValueError(f"No complete segments for job {job_id}")

        # Check for gaps
        expected_indices = list(range(len(segments)))
        actual_indices = [s.segment_index for s in segments]
        if actual_indices != expected_indices:
            missing = set(expected_indices) - set(actual_indices)
            raise ValueError(
                f"Missing segments before assembly: {sorted(missing)}"
            )

        output_dir = os.path.join(WORKDIR, job_id)
        os.makedirs(output_dir, exist_ok=True)
        final_path = os.path.join(output_dir, 'final_assembled.mp4')

        # Write concat list file
        list_path = os.path.join(output_dir, 'concat_list.txt')
        with open(list_path, 'w') as f:
            for seg in segments:
                f.write(f"file '{seg.output_path}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', list_path,
            '-c', 'copy',
            '-movflags', '+faststart',
            final_path
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Assembly failed: {result.stderr[-500:]}"
            )

        logger.info(
            "Assembly complete for job %s: %s (%d segments)",
            job_id, final_path, len(segments)
        )
        return final_path

    def validate_segment(self, segment_id: int) -> bool:
        """Validate segment output file integrity."""
        seg = (self.db.query(RenderSegment)
               .filter(RenderSegment.id == segment_id)
               .first())
        if not seg:
            return False
        return seg.validate_output()

    # ──────────────────────────────────────────────

    def _gather_segment_inputs(
        self, manifest: CompositionManifest,
        start_ms: int, end_ms: int
    ) -> List[Dict[str, Any]]:
        """Collect asset references for a segment's time range."""
        assets = []
        for scene in manifest.timeline.get('scenes', []):
            s_start = scene['start_ms']
            s_end = s_start + scene['duration_ms']
            if s_end <= start_ms or s_start >= end_ms:
                continue
            for layer in scene.get('layers', []):
                assets.append({
                    "scene_id": scene['scene_id'],
                    "layer_type": layer['type'],
                    "path": layer.get('path', ''),
                    "scene_start_ms": s_start,
                    "scene_duration_ms": scene['duration_ms'],
                })
        return assets
