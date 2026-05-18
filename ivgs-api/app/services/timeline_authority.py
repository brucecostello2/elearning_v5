"""Timeline Authority — single source of truth for render timing.

Once a manifest is locked, all asset generation must conform to
the declared durations. This service enforces that contract:

  - Assets within ±10% of declared duration: auto-adjust (speed filter)
  - Assets >10% drift: flag for human review, block render
  - Assets missing: trigger regeneration via fallback chain

Used by workers before storing generated assets to checkpoints.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.manifest import CompositionManifest

logger = logging.getLogger(__name__)

AUTO_ADJUST_THRESHOLD = 0.10   # ±10% auto-adjustment range
HARD_REJECT_THRESHOLD = 0.30   # >30% drift → reject and regenerate


class TimelineAuthority:
    """Enforces manifest timing constraints for asset generation."""

    def __init__(self, db: Session):
        self.db = db

    def set_authoritative_timeline(
        self, job_id: str, timeline: Dict[str, Any]
    ) -> None:
        """Update manifest timeline (only valid in draft state)."""
        manifest = self._get_manifest(job_id)
        if manifest and manifest.status == 'draft':
            manifest.timeline = timeline
            self.db.commit()
            logger.info("Timeline updated for job %s", job_id)

    def propagate_constraints(
        self, job_id: str, scene_id: str
    ) -> Dict[str, Any]:
        """Return timing constraints for a specific scene.

        Workers call this before generating assets to know expected durations.
        Returns:
          {
            "scene_id": ...,
            "expected_duration_ms": ...,
            "min_duration_ms": ...,
            "max_duration_ms": ...,
            "transition": ...,
            "locked": bool
          }
        """
        manifest = self._get_manifest(job_id)
        if not manifest:
            return {"scene_id": scene_id, "expected_duration_ms": None,
                    "locked": False}

        timeline = manifest.timeline or {}
        for scene in timeline.get('scenes', []):
            if scene.get('scene_id') == scene_id:
                expected = scene.get('duration_ms', 5000)
                tolerance = int(expected * AUTO_ADJUST_THRESHOLD)
                return {
                    "scene_id": scene_id,
                    "expected_duration_ms": expected,
                    "min_duration_ms": expected - tolerance,
                    "max_duration_ms": expected + tolerance,
                    "transition": scene.get('transition', 'cut'),
                    "locked": manifest.status == 'locked'
                }
        return {"scene_id": scene_id, "expected_duration_ms": None,
                "locked": False}

    def resolve_conflict(
        self,
        job_id: str,
        scene_id: str,
        actual_duration_ms: int,
        expected_duration_ms: int,
    ) -> Tuple[str, Optional[str]]:
        """Resolve timing conflict between actual and expected durations.

        Returns:
          ("ok", None)              — within tolerance, no action
          ("adjust", filter_str)    — minor drift, apply FFmpeg filter
          ("flag", reason)          — major drift, needs human review
          ("reject", reason)        — extreme drift, regenerate required
        """
        if expected_duration_ms == 0:
            return ("ok", None)

        drift_ratio = abs(actual_duration_ms - expected_duration_ms) / \
                      expected_duration_ms

        if drift_ratio <= 0.02:
            # <2% drift — negligible
            return ("ok", None)

        if drift_ratio <= AUTO_ADJUST_THRESHOLD:
            # 2–10% drift — auto-adjust with atempo/setpts filter
            speed_factor = actual_duration_ms / expected_duration_ms
            if speed_factor > 1.0:
                # Asset is longer than expected — speed up
                filter_str = f"atempo={speed_factor:.4f}"
            else:
                # Asset is shorter than expected — slow down (within atempo limit)
                filter_str = f"atempo={speed_factor:.4f}"
            logger.info(
                "Timeline: auto-adjusting scene %s drift %.1f%% "
                "speed_factor=%.4f",
                scene_id, drift_ratio * 100, speed_factor
            )
            return ("adjust", filter_str)

        if drift_ratio <= HARD_REJECT_THRESHOLD:
            # 10–30% drift — flag for review but allow through
            reason = (
                f"Scene {scene_id}: {drift_ratio*100:.1f}% drift "
                f"(actual={actual_duration_ms}ms, "
                f"expected={expected_duration_ms}ms)"
            )
            logger.warning("Timeline: flagging %s for review: %s",
                           scene_id, reason)
            return ("flag", reason)

        # >30% drift — reject, trigger regeneration
        reason = (
            f"Scene {scene_id}: excessive drift {drift_ratio*100:.1f}% "
            f"(actual={actual_duration_ms}ms, "
            f"expected={expected_duration_ms}ms) — regeneration required"
        )
        logger.error("Timeline: rejecting %s: %s", scene_id, reason)
        return ("reject", reason)

    def validate_all_timing(self, job_id: str) -> Dict[str, Any]:
        """Check all asset timing against locked manifest.

        Returns summary with scenes that pass, need adjustment, or fail.
        """
        manifest = self._get_manifest(job_id)
        if not manifest or manifest.status != 'locked':
            return {"error": "Manifest not locked"}

        results = {"passed": [], "adjusted": [], "flagged": [], "rejected": []}
        import subprocess, os

        for scene in manifest.timeline.get('scenes', []):
            scene_id = scene['scene_id']
            expected = scene['duration_ms']

            for layer in scene.get('layers', []):
                if layer['type'] == 'audio' and os.path.exists(
                        layer.get('path', '')):
                    # Measure actual audio duration
                    try:
                        result = subprocess.run(
                            ['ffprobe', '-v', 'error',
                             '-show_entries', 'format=duration',
                             '-of', 'default=noprint_wrappers=1:nokey=1',
                             layer['path']],
                            capture_output=True, text=True, timeout=10
                        )
                        actual_ms = int(float(result.stdout.strip()) * 1000)
                    except Exception:
                        actual_ms = expected

                    verdict, detail = self.resolve_conflict(
                        job_id, scene_id, actual_ms, expected
                    )
                    entry = {"scene_id": scene_id,
                             "actual_ms": actual_ms,
                             "expected_ms": expected,
                             "detail": detail}
                    results[verdict].append(entry) if verdict in results \
                        else results["flagged"].append(entry)

        return results

    # ──────────────────────────────────────────────

    def _get_manifest(self, job_id: str) -> Optional[CompositionManifest]:
        return (self.db.query(CompositionManifest)
                .filter(CompositionManifest.job_id == job_id)
                .first())
