"""
IVGS v5 — GPU Utilities
=========================

Provides GPU reservation lifecycle management for worker tasks:
- acquire_gpu_reservation()  → call GPU scheduler to reserve VRAM
- send_heartbeat()           → keep reservation alive (5-min TTL, §12.2)
- release_gpu_reservation()  → release VRAM on task completion
- check_gpu_available()      → pre-flight check before task execution
- start_heartbeat_loop()     → background heartbeat every 10s (§6.2)

All calls go through the GPU Scheduler API at node-01:8001 (§12.3).
Heartbeats include GPU temperature, memory usage, and utilization.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

import httpx
import structlog

from config import GpuSchedulerConfig, WorkerConfig

logger = structlog.get_logger("ivgs.gpu_utils")

# Module-level config and client
_config: Optional[GpuSchedulerConfig] = None
_http_client: Optional[httpx.Client] = None
_heartbeat_thread: Optional[threading.Thread] = None
_heartbeat_stop_event = threading.Event()


def _get_config() -> GpuSchedulerConfig:
    global _config
    if _config is None:
        _config = WorkerConfig().gpu_scheduler
    return _config


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        config = _get_config()
        _http_client = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            headers={
                "Content-Type": "application/json",
                "X-Service-Token": os.getenv(
                    "IVGS_SERVICE_TOKEN", "dev-service-token"
                ),
            },
        )
    return _http_client


# ---------------------------------------------------------------------------
# GPU availability check
# ---------------------------------------------------------------------------

def check_gpu_available(
    model_name: str,
    vram_requirement_mb: int,
    node_hostname: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pre-flight check: is there a GPU with enough VRAM for this model?

    Calls GET /fleet on the GPU scheduler and checks available capacity.

    Returns
    -------
    dict with keys:
        available: bool
        node_id: Optional[str]
        gpu_index: Optional[int]
        available_vram_mb: Optional[int]
    """
    client = _get_client()
    try:
        resp = client.get("/fleet")
        if resp.status_code != 200:
            logger.warning(
                "gpu_fleet_check_failed",
                status_code=resp.status_code,
            )
            return {"available": False, "reason": f"Fleet API returned {resp.status_code}"}

        fleet_data = resp.json()
        nodes = fleet_data.get("nodes", [])

        for node in nodes:
            if node.get("status") != "online":
                continue
            if node_hostname and node.get("node_hostname") != node_hostname:
                continue

            available_vram = node.get("available_vram_mb", 0)
            if available_vram >= vram_requirement_mb:
                return {
                    "available": True,
                    "node_id": node.get("id"),
                    "node_hostname": node.get("node_hostname"),
                    "gpu_index": node.get("gpu_index"),
                    "available_vram_mb": available_vram,
                }

        return {
            "available": False,
            "reason": f"No GPU with {vram_requirement_mb}MB available VRAM",
        }

    except Exception as e:
        logger.error("gpu_availability_check_error", error=str(e))
        return {"available": False, "reason": str(e)}


# ---------------------------------------------------------------------------
# GPU reservation
# ---------------------------------------------------------------------------

def acquire_gpu_reservation(
    job_id: str,
    model_name: str,
    vram_requirement_mb: int,
    estimated_duration_s: int = 120,
    priority: str = "normal",
) -> Dict[str, Any]:
    """
    Acquire a GPU reservation via the GPU Scheduler API (§12.3).

    POST /schedule with job details. Returns reservation info including
    node_id, gpu_index, and reservation_id.

    The reservation has a 5-minute TTL (§12.2). Workers must call
    send_heartbeat() within 5 minutes to keep it active.

    Returns
    -------
    dict with keys:
        reservation_id: str
        node_id: str
        gpu_index: int
        node_hostname: str

    Raises
    ------
    GpuReservationError
        If no capacity available or scheduler rejects the request.
    """
    client = _get_client()
    payload = {
        "job_id": job_id,
        "model_name": model_name,
        "vram_requirement_mb": vram_requirement_mb,
        "estimated_duration_s": estimated_duration_s,
        "priority": priority,
    }

    try:
        resp = client.post("/schedule", json=payload)

        if resp.status_code == 200:
            data = resp.json()
            logger.info(
                "gpu_reservation_acquired",
                job_id=job_id,
                reservation_id=data.get("reservation_id"),
                node_id=data.get("node_id"),
                gpu_index=data.get("gpu_index"),
            )
            return data

        elif resp.status_code == 503:
            error_data = resp.json() if resp.text else {}
            raise GpuNoCapacityError(
                f"No GPU capacity available: {error_data.get('detail', 'unknown')}",
                job_id=job_id,
            )

        elif resp.status_code == 409:
            raise GpuAdmissionError(
                f"Admission control rejected: {resp.text}",
                job_id=job_id,
            )

        elif resp.status_code == 429:
            raise GpuCircuitBreakerError(
                f"Circuit breaker open: {resp.text}",
                job_id=job_id,
            )

        else:
            raise GpuReservationError(
                f"GPU scheduler returned {resp.status_code}: {resp.text}",
                job_id=job_id,
            )

    except (GpuReservationError,):
        raise
    except Exception as e:
        raise GpuReservationError(
            f"GPU reservation failed: {e}", job_id=job_id
        ) from e


def release_gpu_reservation(reservation_id: str) -> bool:
    """
    Release a GPU reservation on task completion (§12.3).
    DELETE /reservations/{reservation_id}
    """
    client = _get_client()
    try:
        resp = client.delete(f"/reservations/{reservation_id}")
        if resp.status_code in (200, 204, 404):
            logger.info(
                "gpu_reservation_released",
                reservation_id=reservation_id,
            )
            return True
        logger.warning(
            "gpu_reservation_release_unexpected",
            reservation_id=reservation_id,
            status_code=resp.status_code,
        )
        return False
    except Exception as e:
        logger.error(
            "gpu_reservation_release_error",
            reservation_id=reservation_id,
            error=str(e),
        )
        return False


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def send_heartbeat(
    worker_id: str,
    node_hostname: str,
    gpu_index: int = 0,
    current_job_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send worker heartbeat to GPU scheduler (§6.2, §12.3).

    PUT /heartbeat with worker status. Workers must send heartbeats
    every 10 seconds; missed heartbeats > 60s trigger suspected_dead,
    > 120s trigger confirmed_dead and job rescheduling.
    """
    client = _get_client()
    payload: Dict[str, Any] = {
        "worker_id": worker_id,
        "node_hostname": node_hostname,
        "gpu_index": gpu_index,
        "current_job_id": current_job_id,
        "heartbeat_data": _collect_gpu_metrics(gpu_index),
    }
    if extra_data:
        payload["heartbeat_data"].update(extra_data)

    try:
        resp = client.put("/heartbeat", json=payload)
        return resp.status_code == 200
    except Exception as e:
        logger.warning("heartbeat_send_failed", error=str(e))
        return False


def _collect_gpu_metrics(gpu_index: int = 0) -> Dict[str, Any]:
    """
    Collect GPU metrics for heartbeat payload.
    Uses nvidia-smi for NVIDIA GPUs (node-02 through node-05).
    """
    metrics: Dict[str, Any] = {
        "timestamp": time.time(),
        "gpu_index": gpu_index,
    }

    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-gpu=temperature.gpu,memory.used,memory.total,"
                "utilization.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                metrics["gpu_temperature_celsius"] = float(parts[0])
                metrics["gpu_memory_used_mb"] = float(parts[1])
                metrics["gpu_memory_total_mb"] = float(parts[2])
                metrics["gpu_utilization_pct"] = float(parts[3])
                metrics["gpu_power_draw_watts"] = float(parts[4])
    except FileNotFoundError:
        metrics["gpu_driver"] = "not_available"
    except Exception as e:
        metrics["gpu_metrics_error"] = str(e)

    return metrics


def _detect_gpu_identity(gpu_index: int) -> Optional[Dict[str, Any]]:
    """Resolve this node's GPU identity: env override -> nvidia-smi -> None.

    Returns ``{gpu_model, total_vram_mb, compute_capability}`` or ``None`` when
    neither source is available (CI / a non-GPU worker) — the caller then skips
    registration rather than registering a phantom node.
    """
    model = os.environ.get("IVGS_GPU_MODEL")
    vram = os.environ.get("IVGS_GPU_VRAM_MB")
    cc = os.environ.get("IVGS_GPU_COMPUTE_CAP")
    if model and vram and cc:
        return {
            "gpu_model": model,
            "total_vram_mb": int(vram),
            "compute_capability": cc,
        }
    try:
        import subprocess

        out = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-gpu=name,memory.total,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            name, mem, ccap = [p.strip() for p in out.stdout.strip().split(",")]
            return {
                "gpu_model": model or name,
                "total_vram_mb": int(vram) if vram else int(float(mem)),
                "compute_capability": cc or ccap,
            }
    except Exception as exc:  # nvidia-smi absent / unparsable
        logger.info("gpu_identity_probe_failed", error=str(exc))
    if model and vram:  # partial env; compute_cap unavailable
        return {
            "gpu_model": model,
            "total_vram_mb": int(vram),
            "compute_capability": cc or "0.0",
        }
    return None


def register_node(gpu_index: Optional[int] = None) -> Optional[str]:
    """Register this node with the GPU scheduler (POST /register).

    Server-side registration is idempotent. Returns the ``node_id``, or
    ``None`` when the node has no resolvable GPU identity (skip) or the
    scheduler is unreachable — the worker still runs; placement simply won't
    see this node until a later registration/heartbeat succeeds.
    """
    cfg = WorkerConfig()
    if not cfg.enable_node_registration:
        logger.info("node_registration_disabled")
        return None
    idx = gpu_index if gpu_index is not None else int(
        os.environ.get("IVGS_GPU_INDEX", "0")
    )
    ident = _detect_gpu_identity(idx)
    if ident is None:
        logger.info(
            "node_registration_skipped",
            reason="no GPU identity (env or nvidia-smi)",
        )
        return None
    payload = {"node_hostname": cfg.node_hostname, "gpu_index": idx, **ident}
    try:
        resp = _get_client().post("/register", json=payload)
        if resp.status_code == 201:
            node_id = resp.json().get("node_id")
            logger.info(
                "node_registered",
                node_id=node_id,
                node_hostname=cfg.node_hostname,
                gpu_index=idx,
            )
            return node_id
        logger.warning(
            "node_registration_failed",
            status_code=resp.status_code,
            body=resp.text[:200],
        )
    except Exception as exc:
        logger.warning("node_registration_error", error=str(exc))
    return None


def start_heartbeat_loop(
    worker_id: str,
    node_hostname: str,
    gpu_index: int = 0,
    interval_seconds: int = 10,
) -> threading.Thread:
    """
    Start a background thread sending heartbeats at the configured interval.

    Returns the thread handle for cleanup.
    """
    global _heartbeat_thread  # noqa: F824 — _heartbeat_stop_event is module-level
    _heartbeat_stop_event.clear()

    def _loop() -> None:
        while not _heartbeat_stop_event.is_set():
            send_heartbeat(
                worker_id=worker_id,
                node_hostname=node_hostname,
                gpu_index=gpu_index,
            )
            _heartbeat_stop_event.wait(interval_seconds)

    _heartbeat_thread = threading.Thread(
        target=_loop, daemon=True, name="ivgs-heartbeat"
    )
    _heartbeat_thread.start()
    logger.info(
        "heartbeat_loop_started",
        worker_id=worker_id,
        interval=interval_seconds,
    )
    return _heartbeat_thread


def stop_heartbeat_loop() -> None:
    """Stop the background heartbeat thread."""
    global _heartbeat_thread
    _heartbeat_stop_event.set()
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        _heartbeat_thread.join(timeout=5)
        logger.info("heartbeat_loop_stopped")
    _heartbeat_thread = None


# ---------------------------------------------------------------------------
# VRAM requirement lookup
# ---------------------------------------------------------------------------

VRAM_REQUIREMENTS: Dict[str, int] = {
    "meta-llama/Llama-3.3-70B-Instruct": 96_000,
    "Qwen/Qwen2.5-72B-Instruct": 96_000,
    "mistralai/Mistral-Small-24B-Instruct-2501": 48_000,
    "FLUX.1-dev": 24_000,
    "FLUX.1-schnell": 16_000,
    "SDXL": 10_000,
    "SD3.5-medium": 10_000,
    "CogVideoX-5B": 24_000,
    "CogVideoX-2B": 14_000,
    "Wan2.1": 16_000,
    "coqui-xtts-v2": 16_000,
    "kokoro-tts": 8_000,
    "whisperx-large-v3": 8_000,
    "latentsync": 12_000,
    "sadtalker": 8_000,
    "animatediff": 16_000,
}


def get_vram_requirement(model_name: str) -> int:
    """Get VRAM requirement in MB for a model."""
    for key, vram in VRAM_REQUIREMENTS.items():
        if key.lower() in model_name.lower():
            return vram
    return 16_000  # Default conservative estimate


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GpuReservationError(Exception):
    """Base GPU reservation error."""
    def __init__(self, message: str, job_id: Optional[str] = None):
        super().__init__(message)
        self.job_id = job_id


class GpuNoCapacityError(GpuReservationError):
    """No GPU capacity available."""


class GpuAdmissionError(GpuReservationError):
    """Admission control rejected the request."""


class GpuCircuitBreakerError(GpuReservationError):
    """Circuit breaker is open for target GPU."""
