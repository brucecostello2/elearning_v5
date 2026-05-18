"""Composition Manifest builder and validator.

The manifest is the single source of truth for a job's render timeline.
Once locked, every render task reads from the manifest — no inference,
no re-querying storyboard state. This makes renders deterministic and
reproducible across re-runs.

Timeline JSON schema:
  {
    "version": 1,
    "job_id": "...",
    "total_duration_ms": 120000,
    "resolution": {"width": 1920, "height": 1080},
    "framerate": 25.0,
    "scenes": [
      {
        "scene_id": "s01",
        "start_ms": 0,
        "duration_ms": 8000,
        "layers": [
          {"type": "video", "path": "/mnt/workdir/.../s01_video.mp4",
           "start_ms": 0, "duration_ms": 8000, "z_index": 0},
          {"type": "audio", "path": "/mnt/workdir/.../s01_tts.wav",
           "start_ms": 0, "duration_ms": 7800, "z_index": 10},
          {"type": "caption", "path": "/mnt/workdir/.../s01.srt",
           "start_ms": 0, "duration_ms": 8000, "z_index": 20}
        ]
      }
    ]
  }
"""

import hashlib
import json
import logging
import subprocess
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.manifest import CompositionManifest
from app.models.checkpoint import PipelineCheckpoint

logger = logging.getLogger(__name__)

WORKDIR = os.environ.get('WORKDIR', '/mnt/workdir')
TIMING_TOLERANCE_MS = 100  # ±100ms is acceptable drift


class ManifestService:
    """Composition manifest builder and validator."""

    def __init__(self, db: Session):
        self.db = db

    def generate_manifest(self, job_id: str) -> CompositionManifest:
        """Build a draft manifest from job checkpoints and measured durations.

        Reads TTS checkpoints for authoritative audio durations.
        Pads or trims video assets to match audio timing within tolerance.
        """
        logger.info("Generating manifest for job %s", job_id)

        # Load all checkpoints
        checkpoints = (
            self.db.query(PipelineCheckpoint)
            .filter(PipelineCheckpoint.job_id == job_id,
                    PipelineCheckpoint.status == 'complete')
            .all()
        )
        cp_map = {cp.stage_name: cp.checkpoint_data for cp in checkpoints}

        storyboard = cp_map.get('storyboard', {})
        scenes_data = storyboard.get('scenes', [])

        timeline_scenes = []
        total_ms = 0

        for i, scene in enumerate(scenes_data):
            scene_id = scene.get('scene_id', f's{i+1:02d}')
            # TTS duration is authoritative — measured from actual output file
            tts_key = f'tts_{scene_id}'
            tts_cp = cp_map.get(tts_key, {})
            tts_path = tts_cp.get('output_path', '')
            tts_duration_ms = self._measure_duration_ms(tts_path)

            # If TTS not available, use storyboard estimate
            if not tts_duration_ms:
                tts_duration_ms = scene.get('duration_ms', 5000)

            # Image/video asset
            img_key = f'image_{scene_id}'
            img_cp = cp_map.get(img_key, {})
            video_path = img_cp.get('video_path', '')
            image_path = img_cp.get('output_path', '')

            scene_start_ms = total_ms
            layers = []

            if video_path and os.path.exists(video_path):
                layers.append({
                    "type": "video",
                    "path": video_path,
                    "start_ms": 0,
                    "duration_ms": tts_duration_ms,
                    "z_index": 0
                })
            elif image_path and os.path.exists(image_path):
                layers.append({
                    "type": "image",
                    "path": image_path,
                    "start_ms": 0,
                    "duration_ms": tts_duration_ms,
                    "z_index": 0
                })

            if tts_path and os.path.exists(tts_path):
                layers.append({
                    "type": "audio",
                    "path": tts_path,
                    "start_ms": 0,
                    "duration_ms": tts_duration_ms,
                    "z_index": 10
                })

            # Caption layer if SRT exists
            caption_path = os.path.join(
                WORKDIR, job_id, f'{scene_id}_captions.srt'
            )
            if os.path.exists(caption_path):
                layers.append({
                    "type": "caption",
                    "path": caption_path,
                    "start_ms": 0,
                    "duration_ms": tts_duration_ms,
                    "z_index": 20
                })

            timeline_scenes.append({
                "scene_id": scene_id,
                "scene_index": i,
                "start_ms": scene_start_ms,
                "duration_ms": tts_duration_ms,
                "transition": scene.get('transition', 'cut'),
                "layers": layers
            })
            total_ms += tts_duration_ms

        manifest_json = {
            "version": 1,
            "job_id": job_id,
            "total_duration_ms": total_ms,
            "resolution": {"width": 1920, "height": 1080},
            "framerate": 25.0,
            "scenes": timeline_scenes
        }

        # Upsert manifest
        existing = (self.db.query(CompositionManifest)
                    .filter(CompositionManifest.job_id == job_id)
                    .first())
        if existing:
            existing.timeline = manifest_json
            existing.total_duration_ms = total_ms
            existing.status = 'draft'
            existing.manifest_version += 1
            manifest = existing
        else:
            manifest = CompositionManifest(
                job_id=job_id,
                timeline=manifest_json,
                total_duration_ms=total_ms,
            )
            self.db.add(manifest)

        self.db.commit()
        self.db.refresh(manifest)
        logger.info(
            "Manifest generated for %s: %d scenes, %dms total",
            job_id, len(timeline_scenes), total_ms
        )
        return manifest

    def lock_manifest(self, job_id: str) -> CompositionManifest:
        """Validate and lock the manifest. Raises if assets are missing."""
        manifest = self._get_or_raise(job_id)
        errors = manifest.validate_assets()
        if errors:
            raise ValueError(
                f"Cannot lock manifest — missing assets:\n" +
                "\n".join(errors)
            )
        manifest.lock()
        self.db.commit()
        logger.info("Manifest locked for job %s checksum=%s",
                    job_id, manifest.checksum)
        return manifest

    def validate_manifest(self, job_id: str) -> Dict[str, Any]:
        """Check asset existence and timing consistency.

        Returns dict with valid bool, errors list, warnings list.
        """
        manifest = self._get_or_raise(job_id)
        errors = manifest.validate_assets()
        warnings = []
        total_computed = 0

        for scene in manifest.get_timeline().get('scenes', []):
            total_computed += scene.get('duration_ms', 0)
            for layer in scene.get('layers', []):
                if layer['type'] == 'audio':
                    measured = self._measure_duration_ms(layer['path'])
                    declared = layer['duration_ms']
                    if abs(measured - declared) > TIMING_TOLERANCE_MS:
                        warnings.append(
                            f"Timing drift in scene {scene['scene_id']}: "
                            f"declared {declared}ms vs measured {measured}ms"
                        )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "total_duration_ms": manifest.total_duration_ms,
            "scene_count": len(manifest.get_timeline().get('scenes', [])),
        }

    def get_ffmpeg_commands(self, job_id: str, segment_index: int,
                            segment_start_ms: int,
                            segment_end_ms: int) -> str:
        """Generate FFmpeg command for a specific render segment.

        Returns a shell command string ready for subprocess execution.
        """
        manifest = self._get_or_raise(job_id)
        if manifest.status != 'locked':
            raise ValueError(
                f"Manifest must be locked before rendering (status: "
                f"{manifest.status})"
            )

        output_path = os.path.join(
            WORKDIR, job_id,
            f'segment_{segment_index:04d}.mp4'
        )
        timeline = manifest.get_timeline()
        scenes = timeline.get('scenes', [])

        # Build filter_complex for scenes overlapping this segment
        inputs = []
        video_filters = []
        audio_filters = []

        for scene in scenes:
            s_start = scene['start_ms']
            s_end = s_start + scene['duration_ms']
            # Overlap check
            if s_end <= segment_start_ms or s_start >= segment_end_ms:
                continue

            clip_start = max(0, segment_start_ms - s_start)
            clip_end = min(scene['duration_ms'],
                           segment_end_ms - s_start)
            clip_dur = clip_end - clip_start

            for layer in scene.get('layers', []):
                if not os.path.exists(layer.get('path', '')):
                    continue
                idx = len(inputs)
                inputs.extend(['-i', layer['path']])
                if layer['type'] in ('video', 'image'):
                    video_filters.append(
                        f"[{idx}:v]trim=start_pts={clip_start}MS:"
                        f"end_pts={clip_end}MS,"
                        f"setpts=PTS-STARTPTS[v{idx}]"
                    )
                elif layer['type'] == 'audio':
                    audio_filters.append(
                        f"[{idx}:a]atrim=start={clip_start/1000:.3f}:"
                        f"end={clip_end/1000:.3f},"
                        f"asetpts=PTS-STARTPTS[a{idx}]"
                    )

        if not video_filters:
            # No video — generate black frame
            inputs = ['-f', 'lavfi', '-i',
                      f'color=black:s=1920x1080:d='
                      f'{(segment_end_ms-segment_start_ms)/1000:.3f}']
            filter_complex = '[0:v]copy[vout];anullsrc[aout]'
        else:
            all_filters = video_filters + audio_filters
            v_labels = ''.join(
                f'[v{i}]' for i in range(len(video_filters))
            )
            a_labels = ''.join(
                f'[a{i}]' for i in range(len(audio_filters))
            )
            concat_v = f"{v_labels}concat=n={len(video_filters)}"
            concat_a = (
                f"{a_labels}concat=n={len(audio_filters)}:v=0:a=1[aout]"
                if audio_filters else ""
            )
            filter_complex = (
                ';'.join(all_filters) + ';' +
                concat_v + '[vout]' +
                (';' + concat_a if concat_a else '')
            )

        cmd_parts = (
            ['ffmpeg', '-y'] +
            inputs +
            ['-filter_complex', filter_complex,
             '-map', '[vout]'] +
            (['-map', '[aout]'] if audio_filters else []) +
            ['-c:v', 'libx264', '-preset', 'fast',
             '-crf', '18', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-ar', '44100',
             '-movflags', '+faststart',
             output_path]
        )
        return ' '.join(cmd_parts), output_path

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _get_or_raise(self, job_id: str) -> CompositionManifest:
        manifest = (self.db.query(CompositionManifest)
                    .filter(CompositionManifest.job_id == job_id)
                    .first())
        if not manifest:
            raise ValueError(f"No manifest found for job {job_id}")
        return manifest

    def _measure_duration_ms(self, path: str) -> int:
        """Use FFprobe to measure actual media duration in milliseconds."""
        if not path or not os.path.exists(path):
            return 0
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries',
                 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                 path],
                capture_output=True, text=True, timeout=10
            )
            duration_s = float(result.stdout.strip())
            return int(duration_s * 1000)
        except Exception as e:
            logger.warning("FFprobe failed for %s: %s", path, e)
            return 0
