"""
IVGS v5 — SadTalker Talking Head Client
=========================================

HTTP client for SadTalker lip-sync rendering per §6.2 Table 6-4.

SadTalker is the FALLBACK talking head provider, used when LatentSync
is unavailable or VRAM is insufficient.

Specifications (§7.1.8):
- Node: node-04
- VRAM: 8GB (vs LatentSync's 12GB)
- Output: 25fps lip-synced video, 1920×1080
- Quality threshold: alignment score > 0.80 (lower than LatentSync's 0.85)
- Timeout: 900s (longer due to multi-step pipeline)
- Port: 7861

Input requirements:
- Scene image: 1920×1080 PNG (from Stage 3)
- Voiceover audio: WAV 48kHz mono (from Stage 4)
- Talking head reference clip: MP4/MOV (user-uploaded)

Output:
- MP4 video with lip-synced talking head
- Stored at /ivgs/talking-heads/{project_id}/{scene_id}.mp4

Implements TalkingHeadProvider ABC from shared.providers.
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

from shared.providers import TalkingHeadProvider, TalkingHeadParams, TalkingHeadResult

logger = structlog.get_logger("ivgs.sadtalker_client")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SadTalkerError(Exception):
    """Base exception for SadTalker errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        job_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.job_id = job_id


class SadTalkerConnectionError(SadTalkerError):
    """SadTalker server unreachable."""


class SadTalkerTimeoutError(SadTalkerError):
    """SadTalker rendering timed out."""


class SadTalkerRenderError(SadTalkerError):
    """SadTalker rendering failed."""


class SadTalkerAlignmentError(SadTalkerError):
    """Lip-sync alignment score below threshold."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class SadTalkerMode(str, Enum):
    """SadTalker rendering modes."""
    FULL = "full"           # Full face reenactment (highest quality, slowest)
    POSE_ONLY = "pose_only"  # Head pose transfer only (faster, lower quality)
    LIP_ONLY = "lip_only"   # Lip sync only (fastest)


@dataclass
class SadTalkerConfig:
    """SadTalker-specific configuration beyond TalkingHeadParams."""
    mode: SadTalkerMode = SadTalkerMode.FULL
    still_mode: bool = False        # Use still image mode (less movement)
    preprocess: str = "crop"        # crop | resize | full
    expression_scale: float = 1.0   # Expression intensity multiplier
    use_enhancer: bool = True       # GFPGAN face enhancement post-process
    batch_size: int = 2             # Internal batch size for inference


@dataclass
class SadTalkerJobStatus:
    """Status of a SadTalker rendering job."""
    job_id: str
    status: str  # queued | processing | complete | failed
    progress: float = 0.0
    output_url: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SadTalker Client — implements TalkingHeadProvider ABC
# ---------------------------------------------------------------------------

class SadTalkerClient(TalkingHeadProvider):
    """
    HTTP client for the SadTalker lip-sync service on node-04:7861.

    Implements TalkingHeadProvider ABC so it can be used interchangeably
    with LatentSyncClient in the pipeline.

    SadTalker pipeline:
    1. 3DMM face reconstruction from reference image
    2. Audio-driven coefficient generation
    3. Face rendering with lip-sync
    4. Optional GFPGAN enhancement

    Lower VRAM requirement (8GB vs 12GB) makes it suitable as fallback
    when LatentSync cannot be scheduled.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 900.0,
        max_retries: int = 2,
        config: Optional[SadTalkerConfig] = None,
    ):
        self.base_url = (base_url or os.environ["SADTALKER_URL"]).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.config = config or SadTalkerConfig()
        self._clients: Dict[str, httpx.AsyncClient] = {}

    async def _get_client(self, base_url: str) -> httpx.AsyncClient:
        """Get or create an httpx async client for the given base URL."""
        if base_url not in self._clients:
            self._clients[base_url] = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=4),
            )
        return self._clients[base_url]

    async def close(self) -> None:
        """Close all HTTP client connections."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    # --- TalkingHeadProvider ABC implementation ---

    async def check_health(self) -> bool:
        """Check if SadTalker service is reachable and healthy."""
        try:
            client = await self._get_client(self.base_url)
            resp = await client.get("/health", timeout=5.0)
            return resp.status_code == 200
        except (httpx.HTTPError, httpx.ConnectError):
            return False

    def vram_requirement_mb(self) -> int:
        """SadTalker requires 8GB VRAM per §7.1.8."""
        return 8192

    def provider_name(self) -> str:
        """Return provider name for logging."""
        return "SadTalker"

    async def render(
        self, params: TalkingHeadParams
    ) -> TalkingHeadResult:
        """
        Render a talking head video using SadTalker.

        Submits a rendering job, polls for completion, validates alignment
        score, and returns the result.
        """
        log = logger.bind(
            scene_image=params.scene_image_path,
            audio=params.voiceover_audio_path,
            provider="sadtalker",
        )
        log.info("sadtalker_render_start")

        client = await self._get_client(self.base_url)
        start_time = time.monotonic()

        # Submit rendering job
        job_id = await self._submit_job(client, params, log)

        # Poll for completion
        result = await self._poll_completion(
            client, job_id, params.timeout_seconds, log
        )

        elapsed = time.monotonic() - start_time
        log.info(
            "sadtalker_render_complete",
            job_id=job_id,
            alignment_score=result.alignment_score,
            duration_s=round(elapsed, 2),
        )

        # Validate alignment threshold
        if result.alignment_score < params.alignment_threshold:
            raise SadTalkerAlignmentError(
                f"Alignment score {result.alignment_score:.3f} below "
                f"threshold {params.alignment_threshold:.3f}",
                job_id=job_id,
            )

        return result

    async def _submit_job(
        self,
        client: httpx.AsyncClient,
        params: TalkingHeadParams,
        log: Any,
    ) -> str:
        """Submit a rendering job to SadTalker."""
        payload = {
            "source_image": params.scene_image_path,
            "driven_audio": params.voiceover_audio_path,
            "ref_clip": params.reference_clip_path,
            "result_width": params.output_width,
            "result_height": params.output_height,
            "fps": params.output_fps,
            "mode": self.config.mode.value,
            "still_mode": self.config.still_mode,
            "preprocess": self.config.preprocess,
            "expression_scale": self.config.expression_scale,
            "use_enhancer": self.config.use_enhancer,
            "batch_size": self.config.batch_size,
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post("/api/render", json=payload)
                resp.raise_for_status()
                data = resp.json()
                job_id = data["job_id"]
                log.info("sadtalker_job_submitted", job_id=job_id)
                return job_id
            except httpx.ConnectError as e:
                if attempt == self.max_retries:
                    raise SadTalkerConnectionError(
                        f"Cannot connect to SadTalker: {e}"
                    ) from e
                await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as e:
                raise SadTalkerRenderError(
                    f"SadTalker submit failed: {e.response.text}",
                    status_code=e.response.status_code,
                ) from e

        raise SadTalkerConnectionError("Exhausted retries connecting to SadTalker")

    async def _poll_completion(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        timeout: float,
        log: Any,
    ) -> TalkingHeadResult:
        """Poll SadTalker job until completion or timeout."""
        deadline = time.monotonic() + timeout
        poll_interval = 3.0

        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"/api/status/{job_id}")
                resp.raise_for_status()
                status = SadTalkerJobStatus(**resp.json())

                if status.status == "complete":
                    # Download the result
                    video_data = await self._download_video(
                        client, status.output_url or "", log
                    )
                    return TalkingHeadResult(
                        video_data=video_data,
                        width=1920,
                        height=1080,
                        fps=25,
                        duration_seconds=status.metrics.get("duration_seconds", 0.0),
                        alignment_score=status.metrics.get("alignment_score", 0.0),
                        model="SadTalker",
                        output_path=status.output_url or "",
                    )

                if status.status == "failed":
                    raise SadTalkerRenderError(
                        f"SadTalker rendering failed: {status.error}",
                        job_id=job_id,
                    )

                log.debug(
                    "sadtalker_poll",
                    job_id=job_id,
                    status=status.status,
                    progress=status.progress,
                )
            except httpx.HTTPError as e:
                log.warning("sadtalker_poll_error", error=str(e))

            await asyncio.sleep(poll_interval)

        raise SadTalkerTimeoutError(
            f"SadTalker job {job_id} timed out after {timeout}s",
            job_id=job_id,
        )

    async def _download_video(
        self,
        client: httpx.AsyncClient,
        output_url: str,
        log: Any,
    ) -> bytes:
        """Download rendered video from SadTalker output URL."""
        try:
            resp = await client.get(output_url)
            resp.raise_for_status()
            log.info("sadtalker_video_downloaded", size_bytes=len(resp.content))
            return resp.content
        except httpx.HTTPError as e:
            raise SadTalkerError(
                f"Failed to download SadTalker output: {e}"
            ) from e

    async def render_batch(
        self,
        params_list: List[TalkingHeadParams],
        concurrency: int = 2,
    ) -> List[Tuple[Optional[TalkingHeadResult], Optional[SadTalkerError]]]:
        """
        Render multiple talking head videos concurrently.

        Returns list of (result, error) tuples — one per input params.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _render(
            p: TalkingHeadParams,
        ) -> Tuple[Optional[TalkingHeadResult], Optional[SadTalkerError]]:
            async with semaphore:
                try:
                    result = await self.render(p)
                    return (result, None)
                except SadTalkerError as e:
                    return (None, e)

        return await asyncio.gather(*[_render(p) for p in params_list])
