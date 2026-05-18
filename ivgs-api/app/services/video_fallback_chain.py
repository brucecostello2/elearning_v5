"""Full L1→L4 video fallback chain for Phase 3.
Extends Phase 1 FallbackManager with AI video as L1."""
import logging
from typing import Optional, Dict, Any
from app.services.fallback import FallbackManager, FallbackLevel
from app.services.cogvideox_service import CogVideoXService
from app.services.wan21_service import Wan21Service
from app.models.ai_video import AiVideoGeneration
from app.core.database import get_db_context

logger = logging.getLogger(__name__)


class VideoFallbackChain(FallbackManager):
    """Phase 3 upgrade: activates L1 AI video tier.

    L1 — AI video (CogVideoX / Wan2.1)
    L2 — Ken Burns animated still (Phase 1 MotionGraphicsService)
    L3 — Static image with zoom/pan
    L4 — Static image only
    """

    def __init__(
        self,
        cogvideox: CogVideoXService,
        wan21: Wan21Service,
        *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.cogvideox = cogvideox
        self.wan21 = wan21

    def select_model(self, scene_type: str, duration_s: int) -> str:
        """Choose between CogVideoX and Wan2.1 based on duration + VRAM."""
        if duration_s > 30:
            # Only CogVideoX handles long clips
            if self.cogvideox.is_available():
                return "cogvideox"
            return "none"
        # Prefer CogVideoX if VRAM allows, fall back to Wan2.1
        if self.cogvideox.is_available():
            return "cogvideox"
        if self.wan21.is_available():
            return "wan21"
        return "none"

    def execute(
        self,
        job_id: str,
        scene_id: str,
        prompt: str,
        output_path: str,
        scene_type: str = "broll",
        duration_s: int = 5,
        resolution: str = "720p",
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute fallback chain starting from L1.
        Returns: {output_path, level_used, model_used, fallback_reason}"""
        model = self.select_model(scene_type, duration_s)
        result_path: Optional[str] = None
        level_used = 1
        model_used = model
        fallback_reason: Optional[str] = None

        # -------- L1: AI video ----------------------------------------
        if model == "cogvideox":
            result_path = self.cogvideox.generate_video(
                prompt=prompt, output_path=output_path,
                duration_s=duration_s, resolution=resolution,
                scene_type=scene_type, seed=seed)
            if result_path is None:
                fallback_reason = "cogvideox_failed"
        elif model == "wan21":
            result_path = self.wan21.generate_video(
                prompt=prompt, output_path=output_path,
                duration_s=duration_s, resolution=resolution,
                scene_type=scene_type, seed=seed)
            if result_path is None:
                fallback_reason = "wan21_failed"
        else:
            fallback_reason = "no_ai_model_available"

        # Record L1 attempt in DB
        self._record_generation(job_id, scene_id, model, prompt,
                                duration_s, resolution, result_path,
                                fallback_reason)

        if result_path:
            return {
                "output_path": result_path,
                "level_used": 1,
                "model_used": model_used,
                "fallback_reason": None,
            }

        # -------- L2–L4: delegate to Phase 1 FallbackManager ----------
        logger.info("L1 failed (%s) — falling to L2+", fallback_reason)
        level_used, result_path = self._execute_l2_l4(
            job_id, scene_id, prompt, output_path, scene_type, duration_s)

        return {
            "output_path": result_path,
            "level_used": level_used,
            "model_used": "motion_graphics",
            "fallback_reason": fallback_reason,
        }

    def _execute_l2_l4(
        self,
        job_id: str,
        scene_id: str,
        prompt: str,
        output_path: str,
        scene_type: str,
        duration_s: int,
    ):
        """Delegate to Phase 1 fallback chain (L2 animated still → L4 static)."""
        return super().execute_with_fallback(
            job_id=job_id, scene_id=scene_id,
            scene_type=scene_type,
            output_path=output_path,
        )

    def _record_generation(
        self,
        job_id: str,
        scene_id: str,
        model: str,
        prompt: str,
        duration_s: int,
        resolution: str,
        output_path: Optional[str],
        error: Optional[str],
    ):
        """Persist generation attempt to ai_video_generations table."""
        try:
            with get_db_context() as db:
                record = AiVideoGeneration(
                    job_id=job_id,
                    scene_id=scene_id,
                    model_name=model if model != "none" else "cogvideox_2b",
                    prompt=prompt,
                    generation_params={"duration_s": duration_s,
                                       "resolution": resolution},
                    output_path=output_path,
                    status="complete" if output_path else "failed",
                    error_message=error,
                )
                db.add(record)
                db.commit()
        except Exception as exc:
            logger.warning("Failed to record AI video generation: %s", exc)

    def get_fallback_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """Return fallback rate stats for the last N hours."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with get_db_context() as db:
            all_gen = db.query(AiVideoGeneration).filter(
                AiVideoGeneration.created_at >= cutoff).all()
        total = len(all_gen)
        if total == 0:
            return {"total": 0, "l1_success_rate": 0.0}
        l1_success = sum(1 for g in all_gen
                         if g.status == "complete" and g.fallback_level_used == 1)
        return {
            "total": total,
            "l1_success_rate": l1_success / total,
            "l1_failures": total - l1_success,
            "model_breakdown": {
                model: sum(1 for g in all_gen if g.model_name == model)
                for model in ["cogvideox_5b", "cogvideox_2b",
                              "wan21_t2v", "wan21_i2v"]
            },
        }
