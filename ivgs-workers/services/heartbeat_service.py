"""Worker heartbeat reporter — writes liveness signals every 10 seconds.

Each Celery worker process starts a HeartbeatReporter background thread
on startup. The thread writes to Redis (fast) and periodically syncs to
the PostgreSQL worker_heartbeats table (persistent).

Usage (in Celery worker init):
    reporter = HeartbeatReporter(
        worker_id="celery@node-02-pid1234",
        node_hostname="node-02",
        gpu_index=0,
    )
    reporter.start()
    # In task:
    reporter.report_job_start(job_id=42, stage="image_gen")
    # On task completion:
    reporter.report_job_end(job_id=42)
    # On worker shutdown:
    reporter.stop()
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional

import redis

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 10
DB_SYNC_INTERVAL_SECONDS = 30  # Sync to PostgreSQL every 30s
REDIS_KEY_PREFIX = "ivgs:worker_heartbeat:"
REDIS_TTL_SECONDS = 90  # Redis key expires if heartbeat stops


class HeartbeatReporter:
    """Sends worker heartbeat signals to Redis and PostgreSQL."""

    def __init__(
        self,
        worker_id: str,
        node_hostname: str,
        gpu_index: Optional[int] = None,
        redis_url: str = None,
    ) -> None:
        self.worker_id = worker_id
        self.node_hostname = node_hostname
        self.gpu_index = gpu_index
        self._redis_url = redis_url or os.getenv("REDIS_URL",
                                                  "redis://node-01:6379/0")
        self._redis: Optional[redis.Redis] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._current_job_id: Optional[int] = None
        self._current_stage: Optional[str] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background heartbeat thread."""
        self._redis = redis.from_url(self._redis_url, decode_responses=True)
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"heartbeat-{self.worker_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Heartbeat started: worker=%s gpu=%s",
                    self.worker_id, self.gpu_index)

    def stop(self) -> None:
        """Stop the heartbeat thread gracefully."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._redis:
            # Clear our Redis key to signal clean shutdown
            try:
                self._redis.delete(f"{REDIS_KEY_PREFIX}{self.worker_id}")
            except Exception:
                pass

    def report_job_start(self, job_id: int, stage: str) -> None:
        """Record that this worker has started processing a job stage."""
        with self._lock:
            self._current_job_id = job_id
            self._current_stage = stage

    def report_job_end(self, job_id: int) -> None:
        """Clear the current job after completion."""
        with self._lock:
            if self._current_job_id == job_id:
                self._current_job_id = None
                self._current_stage = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main heartbeat loop — runs every HEARTBEAT_INTERVAL_SECONDS."""
        last_db_sync = 0.0

        while not self._stop_event.is_set():
            try:
                metrics = self._collect_gpu_metrics()
                payload = self._build_payload(metrics)

                # Fast path: write to Redis
                self._write_to_redis(payload)

                # Slow path: sync to PostgreSQL every 30s
                now = time.time()
                if now - last_db_sync >= DB_SYNC_INTERVAL_SECONDS:
                    self._sync_to_postgres(payload)
                    last_db_sync = now

            except Exception as exc:
                logger.warning("Heartbeat error: %s", exc)

            self._stop_event.wait(timeout=HEARTBEAT_INTERVAL_SECONDS)

    def _build_payload(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            return {
                "worker_id": self.worker_id,
                "node_hostname": self.node_hostname,
                "gpu_index": self.gpu_index,
                "current_job_id": self._current_job_id,
                "current_stage": self._current_stage,
                "timestamp": time.time(),
                **metrics,
            }

    def _write_to_redis(self, payload: Dict[str, Any]) -> None:
        key = f"{REDIS_KEY_PREFIX}{self.worker_id}"
        self._redis.setex(key, REDIS_TTL_SECONDS, json.dumps(payload))

    def _sync_to_postgres(self, payload: Dict[str, Any]) -> None:
        """Upsert heartbeat row in worker_heartbeats table."""
        from sqlalchemy import create_engine, text
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return

        engine = create_engine(db_url, pool_size=1, max_overflow=0)
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO worker_heartbeats
                    (worker_id, node_hostname, gpu_index, current_job_id,
                     current_stage, heartbeat_data, last_heartbeat_at, status)
                VALUES
                    (:wid, :host, :gpu, :job_id, :stage,
                     :data::jsonb, now(), 'alive')
                ON CONFLICT (worker_id) DO UPDATE SET
                    current_job_id    = EXCLUDED.current_job_id,
                    current_stage     = EXCLUDED.current_stage,
                    heartbeat_data    = EXCLUDED.heartbeat_data,
                    last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                    status            = 'alive'
            """), {
                "wid": payload["worker_id"],
                "host": payload["node_hostname"],
                "gpu": payload["gpu_index"],
                "job_id": payload["current_job_id"],
                "stage": payload["current_stage"],
                "data": json.dumps({k: v for k, v in payload.items()
                                    if k not in ("worker_id", "node_hostname",
                                                 "gpu_index", "current_job_id",
                                                 "current_stage")}),
            })
            conn.commit()
        engine.dispose()

    def _collect_gpu_metrics(self) -> Dict[str, Any]:
        """Collect GPU utilization metrics via nvidia-smi."""
        if self.gpu_index is None:
            return {}
        try:
            result = subprocess.run(
                ["nvidia-smi",
                 f"--id={self.gpu_index}",
                 "--query-gpu=utilization.gpu,memory.used,memory.total,"
                 "temperature.gpu,power.draw",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 5:
                    return {
                        "gpu_util_pct": float(parts[0]),
                        "mem_used_mb": float(parts[1]),
                        "mem_total_mb": float(parts[2]),
                        "temperature_c": float(parts[3]),
                        "power_draw_w": float(parts[4].split()[0]),
                    }
        except Exception:
            pass
        return {}
