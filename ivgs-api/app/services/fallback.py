"""FallbackManager — generation fallback chain for video scenes.

Implements the 4-level fallback chain for video scene generation:
  L1: AI video (CogVideoX/Wan2.1) — deferred to Phase 3
  L2: Animated still image (Ken Burns effect)
  L3: Static image with zoom/pan
  L4: Static image only

In Phase 1, all scene types start at L2. Level 1 is registered but
marked as unavailable until Phase 3 enables it.

Usage:
    mgr = FallbackManager(db_session)
    result = mgr.execute_with_fallback(
        job_id=42, scene_id=1, scene_type="action",
        image_path="/workdir/42/scene_1_image.png",
        duration_ms=14500,
    )
    # result = {"video_path": "...", "level_used": 2, "strategy": "ken_burns"}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


@dataclass
class FallbackLevel:
    """Defines one level in the fallback chain."""

    level: int
    strategy: str
    enabled: bool
    handler: Optional[Callable[..., Dict[str, Any]]] = None


class FallbackManager:
    """Executes generation with automatic fallback on failure.

    Tries each level in sequence. Records all attempts in the
    job_scenes table for analytics. Returns on the first success.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._levels: Dict[str, List[FallbackLevel]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default fallback levels for Phase 1."""
        # L1 handler is None until Phase 3 enables it
        default_chain = [
            FallbackLevel(level=1, strategy="ai_video", enabled=False, handler=None),
            FallbackLevel(level=2, strategy="ken_burns", enabled=True, handler=None),
            FallbackLevel(level=3, strategy="zoom_pan",  enabled=True, handler=None),
            FallbackLevel(level=4, strategy="static",    enabled=True, handler=None),
        ]
        for scene_type in ["action", "talking_head", "broll", "default"]:
            self._levels[scene_type] = [FallbackLevel(**vars(fl))
                                         for fl in default_chain]
        # title_card starts at L4 — no animation needed
        self._levels["title_card"] = [
            FallbackLevel(level=1, strategy="ai_video",  enabled=False, handler=None),
            FallbackLevel(level=2, strategy="ken_burns", enabled=False, handler=None),
            FallbackLevel(level=3, strategy="zoom_pan",  enabled=False, handler=None),
            FallbackLevel(level=4, strategy="static",    enabled=True,  handler=None),
        ]

    def register_handler(
        self,
        scene_type: str,
        level: int,
        handler: Callable[..., Dict[str, Any]],
        enabled: bool = True,
    ) -> None:
        """Register a handler function for a specific level and scene type.

        Args:
            scene_type: Scene type this handler applies to, or "default".
            level:      Fallback level (1–4).
            handler:    Callable(job_id, scene_id, image_path, duration_ms,
                                 **kwargs) -> {"video_path": ...}
            enabled:    Whether this level is active (False = skip to next).
        """
        chain = self._levels.get(scene_type, self._levels["default"])
        for fl in chain:
            if fl.level == level:
                fl.handler = handler
                fl.enabled = enabled
                return
        logger.warning("Level %d not found for scene_type=%s", level, scene_type)

    def execute_with_fallback(
        self,
        job_id: int,
        scene_id: int,
        scene_type: str,
        image_path: str,
        duration_ms: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute generation with automatic fallback.

        Tries enabled levels in order from the determined start level.
        Records each attempt (success or failure) in the database.

        Args:
            job_id:      Job ID for checkpoint/DB tracking.
            scene_id:    Scene ID within the job.
            scene_type:  Determines which fallback chain to use.
            image_path:  Path to the source still image.
            duration_ms: Target video duration in milliseconds.
            **kwargs:    Additional arguments forwarded to handlers.

        Returns:
            Dict with at minimum:
                {"video_path": str, "level_used": int, "strategy": str}

        Raises:
            RuntimeError: If all fallback levels fail.
        """
        chain = self._levels.get(scene_type, self._levels["default"])
        start_level = self._get_start_level(scene_type)

        attempts = []
        last_error = None

        for fl in chain:
            if fl.level < start_level or not fl.enabled:
                continue

            if fl.handler is None:
                logger.debug("Skipping level %d (no handler)", fl.level)
                continue

            logger.info("Trying fallback level %d (%s): job=%s scene=%s",
                        fl.level, fl.strategy, job_id, scene_id)
            try:
                result = fl.handler(
                    job_id=job_id,
                    scene_id=scene_id,
                    image_path=image_path,
                    duration_ms=duration_ms,
                    **kwargs,
                )
                result["level_used"] = fl.level
                result["strategy"] = fl.strategy

                # Record successful attempt
                attempts.append({"level": fl.level, "strategy": fl.strategy,
                                  "status": "success"})
                self._record_outcome(job_id, scene_id, fl.level,
                                     fl.strategy, None, attempts)
                logger.info("Fallback level %d succeeded: job=%s scene=%s",
                            fl.level, job_id, scene_id)
                return result

            except Exception as exc:
                last_error = str(exc)
                logger.warning("Fallback level %d failed: %s", fl.level, exc)
                attempts.append({"level": fl.level, "strategy": fl.strategy,
                                  "status": "failed", "error": last_error})

        self._record_outcome(job_id, scene_id, -1, "none", last_error, attempts)
        raise RuntimeError(
            f"All fallback levels failed for job={job_id} scene={scene_id}. "
            f"Last error: {last_error}"
        )

    def get_fallback_history(self, job_id: int,
                              scene_id: int) -> Optional[List[Dict]]:
        """Retrieve the fallback attempt history for a scene."""
        row = self.db.execute(
            sa_text(
                "SELECT fallback_attempts FROM job_scenes "
                "WHERE job_id = :jid AND id = :sid"
            ),
            {"jid": job_id, "sid": scene_id},
        ).first()
        return row[0] if row else None

    def _get_start_level(self, scene_type: str) -> int:
        """Determine which fallback level to start at for this scene type."""
        row = self.db.execute(
            sa_text(
                "SELECT phase1_start_level FROM fallback_policies "
                "WHERE scene_type = :st"
            ),
            {"st": scene_type},
        ).first()
        if not row:
            row = self.db.execute(
                sa_text(
                    "SELECT phase1_start_level FROM fallback_policies "
                    "WHERE scene_type = 'default'"
                )
            ).first()
        return row[0] if row else 2

    def _record_outcome(
        self,
        job_id: int,
        scene_id: int,
        level_used: int,
        strategy: str,
        error: Optional[str],
        attempts: List[Dict],
    ) -> None:
        """Persist fallback outcome to job_scenes table."""
        import json
        try:
            self.db.execute(
                sa_text(
                    "UPDATE job_scenes "
                    "SET generation_level = :lvl, "
                    "    fallback_reason   = :reason, "
                    "    fallback_attempts = :attempts::jsonb "
                    "WHERE job_id = :jid AND id = :sid"
                ),
                {
                    "lvl": level_used,
                    "reason": error,
                    "attempts": json.dumps(attempts),
                    "jid": job_id,
                    "sid": scene_id,
                },
            )
            self.db.flush()
        except Exception as exc:
            logger.warning("Could not record fallback outcome: %s", exc)
