"""
IVGS v5 — LatentSync Talking Head Client
==========================================

HTTP client for LatentSync lip-sync rendering per §7.1.7.

Specifications:
- Node: node-04
- VRAM: 12GB (running), 16GB configured
- Output: 30fps lip-synced video, 1920×1080
- Quality threshold: alignment score > 0.85 (§11.1)
- Timeout: 600s
- Fallback: SadTalker (8GB VRAM)

Input requirements:
- Scene image: 1920×1080 PNG (from Stage 3)
- Voiceover audio: WAV 48kHz mono (from Stage 4)
- Talking head reference clip: MP4/MOV (user-uploaded)

Output:
- MP4 video with lip-synced talking head
- Stored at /ivgs/talking-heads/{project_id}/{scene_id}.mp4
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

logger = structlog.get_logger("ivgs.latentsync_client")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LatentSyncError(Exception):
    """Base exception for LatentSync errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        job_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.job_id = job_id


class LatentSyncConnectionError(LatentSyncError):
    """LatentSync server unreachable."""


class LatentSyncTimeoutError(LatentSyncError):
    """LatentSync rendering timed out."""


class LatentSyncRenderError(LatentSyncError):
    """LatentSync rendering failed."""


class LatentSyncAlignmentError(LatentSyncError):
    """Lip-sync alignment score below threshold."""


class LatentSyncDownloadError(LatentSyncError):
    """Failed to download rendered video."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class LatentSyncMode(str, Enum):
    """Rendering modes."""
    FULL_FRAME = "full_frame"
    PICTURE_IN_PICTURE = "pip"
    CHROMA_KEY = "chroma_key"


@dataclass(frozen=True)
class LatentSyncParams:
    """Parameters for talking head rendering."""
    audio_data: bytes
    reference_video_data: bytes
    scene_image_data: Optional[bytes] = None
    mode: LatentSyncMode = LatentSyncMode.FULL_FRAME
    output_width: int = 1920
    output_height: int = 1080
    output_fps: int = 30
    face_detection_threshold: float = 0.5
    lip_sync_strength: float = 1.0
    face_enhance: bool = True
    pip_scale: float = 0.3
    pip_position: str = "bottom_right"
    pip_margin: int = 20

    def compute_hash(self) -> str:
        """SHA-256 hash for idempotency (excludes binary data)."""
        audio_hash = hashlib.sha256(self.audio_data).hexdigest()[:16]
        ref_hash = hashlib.sha256(self.reference_video_data).hexdigest()[:16]
        scene_hash = ""
        if self.scene_image_data:
            scene_hash = hashlib.sha256(self.scene_image_data).hexdigest()[:16]
        data = {
            "audio_hash": audio_hash,
            "reference_hash": ref_hash,
            "scene_hash": scene_hash,
            "mode": self.mode.value,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "output_fps": self.output_fps,
            "lip_sync_strength": self.lip_sync_strength,
        }
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class LatentSyncResult:
    """Result from LatentSync rendering."""
    job_id: str
    video_data: bytes
    duration_seconds: float
    width: int
    height: int
    fps: int
    alignment_score: float
    model_used: str
    generation_time_seconds: float
    params_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def meets_quality_threshold(self) -> bool:
        """Check if alignment score meets §11.1 threshold (>0.85)."""
        return self.alignment_score >= 0.85


# ---------------------------------------------------------------------------
# LatentSync Client
# ---------------------------------------------------------------------------

class LatentSyncClient:
    """
    Async HTTP client for LatentSync lip-sync rendering.

    API Flow:
    1. POST /render — submit rendering job with audio + reference video
    2. GET /status/{job_id} — poll until complete
    3. GET /download/{job_id} — download rendered video
    4. GET /metrics/{job_id} — get alignment score and quality metrics

    Supports automatic fallback to SadTalker on failure.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        fallback_url: Optional[str] = None,
        timeout: float = 600.0,
        poll_interval: float = 5.0,
        alignment_threshold: float = 0.85,
    ):
        self._base_url = base_url or os.environ["LATENTSYNC_URL"]
        self._fallback_url = fallback_url or os.environ.get("SADTALKER_URL")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._alignment_threshold = alignment_threshold
        self._clients: Dict[str, httpx.AsyncClient] = {}

    async def _get_client(self, base_url: str) -> httpx.AsyncClient:
        if base_url not in self._clients:
            self._clients[base_url] = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(
                    connect=15.0,
                    read=self._timeout,
                    write=120.0,
                    pool=15.0,
                ),
                limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),
            )
        return self._clients[base_url]

    async def close(self) -> None:
        for url, client in self._clients.items():
            await client.aclose()
        self._clients.clear()

    # ----- Health -----

    async def check_health(self, base_url: Optional[str] = None) -> bool:
        url = base_url or self._base_url
        try:
            client = await self._get_client(url)
            resp = await client.get("/health", timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False

    # ----- Core rendering -----

    async def render(
        self,
        params: LatentSyncParams,
    ) -> LatentSyncResult:
        """
        Render a talking head video using LatentSync.

        Combines reference video (user-uploaded presenter clip)
        with voiceover audio to produce lip-synced output.
        Optionally composites over a scene image.

        Falls back to SadTalker on failure.
        """
        start_time = time.monotonic()
        params_hash = params.compute_hash()

        log = logger.bind(
            mode=params.mode.value,
            output=f"{params.output_width}x{params.output_height}",
            params_hash=params_hash[:12],
        )

        try:
            result = await self._render_on_server(
                params=params,
                base_url=self._base_url,
                model_name="latentsync",
                start_time=start_time,
                params_hash=params_hash,
            )

            if not result.meets_quality_threshold:
                log.warning(
                    "latentsync_low_alignment",
                    score=result.alignment_score,
                    threshold=self._alignment_threshold,
                )

            log.info(
                "latentsync_render_success",
                alignment_score=round(result.alignment_score, 3),
                elapsed=round(result.generation_time_seconds, 2),
            )
            return result

        except LatentSyncError as primary_err:
            if not self._fallback_url or self._fallback_url == self._base_url:
                raise

            log.warning(
                "latentsync_primary_failed_trying_sadtalker",
                error=str(primary_err),
            )

            result = await self._render_on_server(
                params=params,
                base_url=self._fallback_url,
                model_name="sadtalker",
                start_time=start_time,
                params_hash=params_hash,
            )
            log.info(
                "sadtalker_fallback_success",
                alignment_score=round(result.alignment_score, 3),
            )
            return result

    async def _render_on_server(
        self,
        params: LatentSyncParams,
        base_url: str,
        model_name: str,
        start_time: float,
        params_hash: str,
    ) -> LatentSyncResult:
        """Execute rendering on a specific server."""
        client = await self._get_client(base_url)

        # Build multipart form
        files: Dict[str, Any] = {
            "audio": ("audio.wav", params.audio_data, "audio/wav"),
            "reference_video": (
                "reference.mp4",
                params.reference_video_data,
                "video/mp4",
            ),
        }
        if params.scene_image_data:
            files["scene_image"] = (
                "scene.png",
                params.scene_image_data,
                "image/png",
            )

        form_data = {
            "mode": params.mode.value,
            "output_width": str(params.output_width),
            "output_height": str(params.output_height),
            "output_fps": str(params.output_fps),
            "face_detection_threshold": str(params.face_detection_threshold),
            "lip_sync_strength": str(params.lip_sync_strength),
            "face_enhance": str(params.face_enhance).lower(),
            "pip_scale": str(params.pip_scale),
            "pip_position": params.pip_position,
            "pip_margin": str(params.pip_margin),
        }

        # 1. Submit rendering job
        try:
            resp = await client.post(
                "/render",
                files=files,
                data=form_data,
                timeout=120.0,
            )
        except httpx.ConnectError as e:
            raise LatentSyncConnectionError(
                f"Cannot connect to {model_name} at {base_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise LatentSyncTimeoutError(
                f"Timeout submitting to {model_name}: {e}"
            ) from e

        if resp.status_code not in (200, 201, 202):
            raise LatentSyncRenderError(
                f"{model_name} rejected request: HTTP {resp.status_code} — {resp.text[:500]}",
                status_code=resp.status_code,
            )

        job_data = resp.json()
        job_id = job_data.get("job_id") or job_data.get("id")
        if not job_id:
            raise LatentSyncRenderError(f"{model_name} did not return a job_id")

        logger.info(
            "latentsync_job_submitted",
            job_id=job_id,
            model=model_name,
            base_url=base_url,
        )

        # 2. Poll for completion
        await self._poll_completion(
            client=client,
            job_id=job_id,
            timeout=self._timeout,
            start_time=start_time,
            model_name=model_name,
        )

        # 3. Get quality metrics
        metrics = await self._get_metrics(client, job_id)
        alignment_score = metrics.get("alignment_score", 0.0)

        # 4. Download rendered video
        video_data = await self._download_video(client, job_id)

        elapsed = time.monotonic() - start_time

        return LatentSyncResult(
            job_id=job_id,
            video_data=video_data,
            duration_seconds=metrics.get("duration_seconds", 0.0),
            width=params.output_width,
            height=params.output_height,
            fps=params.output_fps,
            alignment_score=alignment_score,
            model_used=model_name,
            generation_time_seconds=round(elapsed, 3),
            params_hash=params_hash,
            metadata={
                "mode": params.mode.value,
                "face_enhance": params.face_enhance,
                "lip_sync_strength": params.lip_sync_strength,
                "base_url": base_url,
                "quality_metrics": metrics,
            },
        )

    async def _poll_completion(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        timeout: float,
        start_time: float,
        model_name: str,
    ) -> None:
        """Poll until rendering completes."""
        deadline = start_time + timeout

        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"/status/{job_id}", timeout=15.0)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "unknown")

                    if status in ("completed", "done", "success"):
                        return
                    elif status in ("failed", "error"):
                        error_msg = data.get("error", "Unknown error")
                        raise LatentSyncRenderError(
                            f"{model_name} rendering failed: {error_msg}",
                            job_id=job_id,
                        )

                    progress = data.get("progress", 0)
                    if progress > 0:
                        logger.debug(
                            "latentsync_progress",
                            job_id=job_id,
                            progress=progress,
                            model=model_name,
                        )

            except LatentSyncRenderError:
                raise
            except httpx.HTTPError as e:
                logger.warning(
                    "latentsync_poll_error",
                    job_id=job_id,
                    error=str(e),
                )

            await asyncio.sleep(self._poll_interval)

        raise LatentSyncTimeoutError(
            f"{model_name} rendering timed out after {timeout}s",
            job_id=job_id,
        )

    async def _get_metrics(
        self, client: httpx.AsyncClient, job_id: str
    ) -> Dict[str, Any]:
        """Get quality metrics including alignment score."""
        try:
            resp = await client.get(f"/metrics/{job_id}", timeout=30.0)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "latentsync_metrics_failed",
                job_id=job_id,
                status_code=resp.status_code,
            )
            return {"alignment_score": 0.0}
        except Exception as e:
            logger.warning(
                "latentsync_metrics_error", job_id=job_id, error=str(e)
            )
            return {"alignment_score": 0.0}

    async def _download_video(
        self, client: httpx.AsyncClient, job_id: str
    ) -> bytes:
        """Download rendered video."""
        try:
            resp = await client.get(f"/download/{job_id}", timeout=120.0)
            if resp.status_code != 200:
                raise LatentSyncDownloadError(
                    f"Video download failed: HTTP {resp.status_code}",
                    job_id=job_id,
                )
            return resp.content
        except httpx.HTTPError as e:
            raise LatentSyncDownloadError(
                f"Video download error: {e}", job_id=job_id
            ) from e

    # ----- Batch rendering -----

    async def render_batch(
        self,
        params_list: List[LatentSyncParams],
        max_concurrent: int = 1,
    ) -> List[Tuple[Optional[LatentSyncResult], Optional[LatentSyncError]]]:
        """Render multiple talking head videos with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _render(p: LatentSyncParams) -> Tuple[Optional[LatentSyncResult], Optional[LatentSyncError]]:
            async with semaphore:
                try:
                    result = await self.render(p)
                    return (result, None)
                except LatentSyncError as e:
                    return (None, e)

        tasks = [_render(p) for p in params_list]
        results = await asyncio.gather(*tasks)
        return list(results)
