"""AdmissionController — pre-acceptance validation and circuit breaker.

Validates that a task can be accepted before creating a GPU reservation:
  1. Sufficient VRAM exists on at least one node
  2. Model compatibility (Phase 3 models rejected in Phase 1)
  3. Concurrency limit not exceeded (max 1 video gen job per GPU)
  4. Circuit breaker: rejects if recent error rate > 20%

Usage:
    adm = AdmissionController(db_session)
    result = adm.check_admission(task_type="sdxl_image", vram_mb=8192)
    if result.admitted:
        sched.schedule_job(...)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db_models import GpuNode, GpuReservation

logger = logging.getLogger(__name__)

# VRAM requirements per task type (MB)
VRAM_REQUIREMENTS: Dict[str, int] = {
    "sdxl_image":    8_192,   # SDXL needs ~8GB
    "flux_image":    16_384,  # FLUX.1 needs ~16GB
    "openai_tts":    0,       # API-based, no GPU
    "elevenlabs_tts":0,
    "did_talking_head": 0,    # API-based
    "ffmpeg_compose":  512,   # Minimal GPU requirement
    "cogvideox":     24_576,  # Phase 3 only — 24GB VRAM
}

# Task types that require a GPU (not API-based)
REQUIRES_LOCAL_GPU = {"sdxl_image", "flux_image", "cogvideox"}


@dataclass
class AdmissionResult:
    """Result of an admission control check."""

    admitted: bool
    reason: Optional[str] = None


class AdmissionController:
    """Validates scheduling requests before creating GPU reservations.

    Prevents wasteful reservation attempts when no eligible GPU exists,
    and enforces safety limits like concurrency caps.
    """

    # Circuit breaker: reject if error rate exceeds this in the window
    ERROR_RATE_THRESHOLD = 0.20
    CIRCUIT_WINDOW_MINUTES = 10

    # Max concurrent video generation jobs per GPU
    MAX_VIDEO_JOBS_PER_GPU = 1

    def __init__(self, db: Session) -> None:
        self.db = db

    def check_admission(
        self,
        task_type: str,
        vram_requirement_mb: int,
    ) -> AdmissionResult:
        """Run all admission checks for a task scheduling request.

        Checks in order:
        1. Phase gate (reject Phase 3-only models in Phase 1)
        2. VRAM availability
        3. Concurrency limit
        4. Circuit breaker

        Args:
            task_type:          Task type identifier (e.g., "sdxl_image").
            vram_requirement_mb: Minimum VRAM needed.

        Returns:
            AdmissionResult with admitted=True if all checks pass.
        """
        # 1. Phase gate
        if task_type == "cogvideox":
            return AdmissionResult(
                admitted=False,
                reason="CogVideoX is deferred to Phase 3. Use fallback levels 2-4.",
            )

        # 2. VRAM availability (only for local GPU tasks)
        if task_type in REQUIRES_LOCAL_GPU and vram_requirement_mb > 0:
            has_capacity = self._check_vram_availability(vram_requirement_mb)
            if not has_capacity:
                return AdmissionResult(
                    admitted=False,
                    reason=f"No GPU with {vram_requirement_mb}MB available VRAM.",
                )

        # 3. Concurrency limit for video generation tasks
        if task_type in {"cogvideox", "wan21_video"}:
            if self._concurrency_limit_reached(task_type):
                return AdmissionResult(
                    admitted=False,
                    reason="Video generation concurrency limit reached.",
                )

        # 4. Circuit breaker
        if self._circuit_breaker_open(task_type):
            return AdmissionResult(
                admitted=False,
                reason=(f"Circuit breaker open for {task_type}: "
                        f"error rate > {self.ERROR_RATE_THRESHOLD:.0%} "
                        f"in last {self.CIRCUIT_WINDOW_MINUTES}m."),
            )

        return AdmissionResult(admitted=True)

    def reserve_resources(
        self,
        job_id: int,
        gpu_node_id: int,
        vram_mb: int,
        model_name: str,
        ttl_seconds: int = 300,
    ) -> GpuReservation:
        """Create a resource reservation for a scheduled job."""
        reservation = GpuReservation.create_for_job(
            gpu_node_id=gpu_node_id,
            job_id=job_id,
            vram_mb=vram_mb,
            model_name=model_name,
            ttl_seconds=ttl_seconds,
        )
        self.db.add(reservation)
        self.db.flush()
        return reservation

    # ------------------------------------------------------------------
    # Private check implementations
    # ------------------------------------------------------------------

    def _check_vram_availability(self, min_vram_mb: int) -> bool:
        """Return True if any online GPU has sufficient available VRAM."""
        nodes = (
            self.db.query(GpuNode)
            .filter(GpuNode.status == "online")
            .all()
        )
        return any(n.available_vram_mb >= min_vram_mb and n.is_alive
                   for n in nodes)

    def _concurrency_limit_reached(self, task_type: str) -> bool:
        """Check if video generation concurrency limit is exceeded."""
        # Count active video gen reservations across all GPUs
        active_count = (
            self.db.query(GpuReservation)
            .filter(
                GpuReservation.model_name.in_(["cogvideox", "wan2.1"]),
                GpuReservation.status.in_(["reserved", "active"]),
            )
            .count()
        )

        total_gpus = (
            self.db.query(GpuNode)
            .filter(GpuNode.status == "online")
            .count()
        )

        max_allowed = total_gpus * self.MAX_VIDEO_JOBS_PER_GPU
        return active_count >= max_allowed

    def _circuit_breaker_open(self, task_type: str) -> bool:
        """Check if the circuit breaker for this task type is open.

        Calculates error rate over the last CIRCUIT_WINDOW_MINUTES by
        querying the task_retries table.
        """
        window_start = (
            datetime.now(timezone.utc)
            - timedelta(minutes=self.CIRCUIT_WINDOW_MINUTES)
        )

        # Map task_type to stage_name in task_retries
        stage_map = {
            "sdxl_image": "image_gen",
            "flux_image": "image_gen",
            "openai_tts": "tts",
            "did_talking_head": "talking_head",
        }
        stage = stage_map.get(task_type, task_type)

        result = self.db.execute(
            sa_text("""
                SELECT
                    COUNT(*) FILTER (WHERE failure_type != 'config') AS failures,
                    COUNT(*) AS total
                FROM task_retries
                WHERE stage_name = :stage AND created_at >= :since
            """),
            {"stage": stage, "since": window_start},
        ).first()

        if result is None or result[1] == 0:
            return False

        error_rate = result[0] / result[1]
        if error_rate > self.ERROR_RATE_THRESHOLD:
            logger.warning("Circuit breaker open: %s error_rate=%.2f",
                           task_type, error_rate)
            return True

        return False
