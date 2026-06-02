"""
IVGS v5 - Async job lifecycle for media-server wrappers (Build Plan section 6).

Used by the async + multipart wrappers (LatentSync, SadTalker; retrofittable to
CogVideoX/Wan2.1). Provides the in-memory job store, a background runner, and the
/status //download //metrics routes the deployed clients poll. The submit endpoint
itself is service-specific (it parses JSON or multipart), so each service defines its
own POST handler plus a SYNC `runner(job, ...)` worker, then calls store.submit(runner, ...).

Contract (Build Plan section 2):
  POST /              -> {"job_id"}    (service-defined; multipart for talking-head)
  GET  /status/{id}   -> {"status","progress","duration","error"}
  GET  /metrics/{id}  -> {"alignment_score","duration_seconds", ...}  (quality gate 11.1)
  GET  /download/{id} -> raw media bytes
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("common.jobs")


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.pending
    created_at: float = field(default_factory=time.time)
    progress: float = 0.0
    duration: float = 0.0
    output_path: Optional[Path] = None
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)


# A runner mutates the job and does the blocking work; it runs in a worker thread.
JobRunner = Callable[..., None]


class JobStore:
    """In-memory job registry with TTL GC and a thread-pool background runner.

    Single-process only (each wrapper is one container, one GPU) - jobs live in this
    dict, outputs live on local disk, and both are reaped after ttl_seconds.
    """

    def __init__(self, *, ttl_seconds: int = 3600) -> None:
        self._jobs: dict = {}
        self._ttl = ttl_seconds

    def create(self) -> Job:
        job = Job(job_id=str(uuid.uuid4()))
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def submit(self, runner: JobRunner, *args: Any) -> Job:
        """Create a job and run `runner(job, *args)` in the default executor.

        `runner` is SYNC (blocking GPU work) so it must not run on the event loop.
        It should populate job.output_path / job.duration / job.metrics on success and
        may raise to signal failure; status transitions are handled here (processing ->
        completed, or failed + error on exception). A runner may also set
        job.status/progress itself for finer-grained reporting.
        """
        self.gc()
        job = self.create()

        def _wrapped() -> None:
            t0 = time.time()
            try:
                job.status = JobStatus.processing
                runner(job, *args)
                if job.status is JobStatus.processing:
                    job.status = JobStatus.completed
                logger.info(
                    "job %s -> %s in %.1fs", job.job_id, job.status.value, time.time() - t0
                )
            except Exception as exc:
                job.status = JobStatus.failed
                job.error = str(exc)
                logger.exception("job %s failed", job.job_id)

        asyncio.get_running_loop().run_in_executor(None, _wrapped)
        return job

    def gc(self) -> None:
        cutoff = time.time() - self._ttl
        for jid in [j for j, job in self._jobs.items() if job.created_at < cutoff]:
            job = self._jobs.pop(jid)
            if job.output_path and Path(job.output_path).exists():
                try:
                    Path(job.output_path).unlink()
                except OSError:
                    pass


def register_job_routes(
    app: FastAPI,
    store: JobStore,
    *,
    download_media_type: str,
    with_metrics: bool = False,
) -> None:
    """Add GET /status/{id}, /download/{id}, and (optionally) /metrics/{id} to `app`."""

    @app.get("/status/{job_id}")
    async def status(job_id: str) -> dict:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job_id")
        return {
            "status": job.status.value,
            "progress": job.progress,
            "duration": job.duration,
            "error": job.error,
        }

    @app.get("/download/{job_id}")
    async def download(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job_id")
        if job.status is not JobStatus.completed or not job.output_path:
            raise HTTPException(status_code=409, detail=f"job not ready: {job.status.value}")
        if not Path(job.output_path).exists():
            raise HTTPException(status_code=410, detail="output expired")
        return FileResponse(str(job.output_path), media_type=download_media_type)

    if with_metrics:

        @app.get("/metrics/{job_id}")
        async def metrics(job_id: str) -> dict:
            job = store.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="unknown job_id")
            if job.status is not JobStatus.completed:
                raise HTTPException(status_code=409, detail=f"job not ready: {job.status.value}")
            return job.metrics
