"""GpuValidator — pre-task VRAM validation and scheduler integration.

Workers call validate_for_task() before accepting GPU-intensive tasks.
If insufficient VRAM is available, the task is rejected back to the
queue with a backoff delay.

Usage:
    validator = GpuValidator(gpu_index=0)
    if not validator.validate_for_task("sdxl_image"):
        # Reject task — Celery will requeue it
        raise Exception("Insufficient VRAM — task rejected")
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Minimum VRAM (MB) required per task type
VRAM_REQUIREMENTS: Dict[str, int] = {
    "sdxl_image":      8_192,
    "flux_image":      16_384,
    "cogvideox":       24_576,   # Phase 3 only
    "talking_head":    0,         # API-based
    "tts":             0,         # API-based
    "composition":     1_024,
    "motion_graphics": 512,
}

# VRAM headroom: keep 10% free before accepting a task
VRAM_HEADROOM_PCT = 0.10


class GpuValidator:
    """Validates GPU VRAM availability before accepting a task."""

    def __init__(
        self,
        gpu_index: int = 0,
        scheduler_url: Optional[str] = None,
    ) -> None:
        self.gpu_index = gpu_index
        self._scheduler_url = scheduler_url or os.getenv(
            "GPU_SCHEDULER_URL", "http://node-01:8001"
        )

    def check_available_vram(self) -> int:
        """Query current available VRAM on this GPU via nvidia-smi.

        Returns:
            Available VRAM in MB, or 0 on error.
        """
        try:
            result = subprocess.run(
                ["nvidia-smi",
                 f"--id={self.gpu_index}",
                 "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception as exc:
            logger.warning("nvidia-smi failed: %s", exc)
        return 0

    def get_total_vram(self) -> int:
        """Query total VRAM on this GPU."""
        try:
            result = subprocess.run(
                ["nvidia-smi",
                 f"--id={self.gpu_index}",
                 "--query-gpu=memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception:
            pass
        return 0

    def validate_for_task(self, task_type: str) -> bool:
        """Check if this GPU has enough VRAM to accept the given task type.

        Includes headroom buffer to avoid thrashing near capacity.

        Args:
            task_type: Task identifier matching VRAM_REQUIREMENTS keys.

        Returns:
            True if task can be safely accepted, False otherwise.
        """
        required = VRAM_REQUIREMENTS.get(task_type, 0)
        if required == 0:
            return True  # API-based task, no GPU requirement

        available = self.check_available_vram()
        # Apply headroom: effective available = available - 10% of total
        total = self.get_total_vram()
        headroom = int(total * VRAM_HEADROOM_PCT)
        effective = max(0, available - headroom)

        ok = effective >= required
        if not ok:
            logger.warning(
                "VRAM check failed: task=%s required=%dMB "
                "available=%dMB (effective=%dMB after headroom)",
                task_type, required, available, effective,
            )
        else:
            logger.debug(
                "VRAM check OK: task=%s required=%dMB available=%dMB",
                task_type, required, available,
            )
        return ok

    def get_vram_requirement(self, task_type: str) -> int:
        """Return the VRAM requirement for a task type in MB."""
        return VRAM_REQUIREMENTS.get(task_type, 0)

    def request_scheduler_reservation(
        self,
        job_id: int,
        model_name: str,
        task_type: str,
    ) -> Optional[int]:
        """Request a VRAM reservation from the GPU Scheduler.

        Calls the scheduler's /schedule endpoint. Returns reservation_id
        or None if scheduling failed.

        Args:
            job_id:     Job requesting the reservation.
            model_name: Model to be loaded (for residency tracking).
            task_type:  Task type for VRAM requirement lookup.

        Returns:
            reservation_id if successful, None otherwise.
        """
        import httpx
        vram_needed = self.get_vram_requirement(task_type)

        try:
            resp = httpx.post(
                f"{self._scheduler_url}/schedule",
                json={
                    "job_id": job_id,
                    "model_name": model_name,
                    "task_type": task_type,
                    "vram_requirement_mb": vram_needed,
                    "estimated_duration_seconds": 300,
                },
                timeout=5.0,
            )
            if resp.status_code == 200:
                return resp.json().get("reservation_id")
            logger.warning("Scheduler rejected task: %s", resp.json())
            return None
        except Exception as exc:
            logger.warning("Scheduler unreachable: %s — proceeding without reservation",
                           exc)
            # Fall back to local VRAM check if scheduler is unavailable
            return -1 if self.validate_for_task(task_type) else None
