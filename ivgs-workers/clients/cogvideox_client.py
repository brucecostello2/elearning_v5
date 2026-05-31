from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from shared.providers import VideoProvider, VideoParams, VideoResult

logger = logging.getLogger("ivgs.workers.cogvideox")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CogVideoXError(Exception):
    """Base exception for CogVideoX errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, job_id: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.job_id = job_id


class CogVideoXConnectionError(CogVideoXError):
    """CogVideoX server unreachable."""
    pass


class CogVideoXTimeoutError(CogVideoXError):
    """CogVideoX generation timed out."""
    pass


class CogVideoXGenerationError(CogVideoXError):
    """CogVideoX video generation failed."""
    pass


class CogVideoXDownloadError(CogVideoXError):
    """Failed to download generated video."""
    pass


# ---------------------------------------------------------------------------
# Config and data models
# ---------------------------------------------------------------------------

class CogVideoXModel(str, Enum):
    """Available CogVideoX models."""
    COGVIDEOX_5B = "CogVideoX-5b"
    COGVIDEOX_2B = "CogVideoX-2b"


@dataclass(frozen=True)
class CogVideoXGenerationParams:
    """Parameters for video generation."""
    prompt: str
    negative_prompt: str = "low quality, blurry, distorted"
    model: CogVideoXModel = CogVideoXModel.COGVIDEOX_5B
    num_frames: int = 49
    guidance_scale: float = 6.0
    num_inference_steps: int = 50
    fps: int = 8
    width: int = 854
    height: int = 480
    seed: int = -1

    def compute_hash(self) -> str:
        """SHA-256 hash for idempotency."""
        data = {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "model": self.model.value,
            "num_frames": self.num_frames,
            "guidance_scale": self.guidance_scale,
            "num_inference_steps": self.num_inference_steps,
            "seed": self.seed,
        }
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class CogVideoXGenerationResult:
    """Result from CogVideoX video generation."""
    job_id: str
    video_data: bytes
    duration_seconds: float
    width: int
    height: int
    fps: int
    num_frames: int
    model_used: str
    generation_time_seconds: float
    params_hash: str
    keyframes: List[bytes] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CogVideoX Client
# ---------------------------------------------------------------------------

class CogVideoXClient(VideoProvider):
    """
    CogVideoX 5B implementation of the VideoProvider interface (spec 19.1).

    Two call paths over one shared HTTP flow:
      - generate(prompt, VideoParams) -> VideoResult            (provider interface)
      - generate_video(CogVideoXGenerationParams) -> CogVideoXGenerationResult
        (richer task-facing interface used by tasks.video_generation_task)

    Optional fallback_url enables primary->secondary failover (e.g. node-02
    -> node-03). NOTE: live end-to-end execution and the failover path are
    validated in Stage 2 (requires a running GPU server).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "cogvideox-5b",
        timeout: float = 1800.0,
        poll_interval: float = 5.0,
        fallback_url: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or os.environ["COGVIDEOX_URL"]).rstrip("/")
        self.fallback_url = fallback_url.rstrip("/") if fallback_url else None
        self.model = model
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    async def _run_job(self, base_url: str, payload: Dict[str, Any]):
        """
        Submit a job to one server, poll to completion, download the result.
        Returns (job_id, video_bytes, status_data, elapsed_seconds).
        Raises typed CogVideoXError subclasses on failure.
        """
        client = await self._get_client()
        try:
            response = await client.post(f"{base_url}/generate", json=payload)
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise CogVideoXConnectionError(f"cannot reach CogVideoX server at {base_url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CogVideoXError(str(e), status_code=e.response.status_code) from e

        job_id = response.json()["job_id"]
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise CogVideoXTimeoutError(
                    f"CogVideoX generation timed out after {self.timeout}s", job_id=job_id
                )
            status_resp = await client.get(f"{base_url}/status/{job_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data.get("status")
            if status == "completed":
                try:
                    video_resp = await client.get(f"{base_url}/download/{job_id}")
                    video_resp.raise_for_status()
                except httpx.HTTPError as e:
                    raise CogVideoXDownloadError(f"failed to download job {job_id}: {e}", job_id=job_id) from e
                return job_id, video_resp.content, status_data, elapsed
            if status == "failed":
                raise CogVideoXGenerationError(
                    f"CogVideoX generation failed: {status_data.get('error', 'unknown')}", job_id=job_id
                )
            await asyncio.sleep(self.poll_interval)

    async def _run_with_failover(self, payload: Dict[str, Any]):
        """Run a job against the primary, failing over to fallback_url on connection error."""
        try:
            return await self._run_job(self.base_url, payload)
        except CogVideoXConnectionError:
            if self.fallback_url:
                logger.warning(
                    "CogVideoX primary %s unreachable; failing over to %s",
                    self.base_url, self.fallback_url,
                )
                return await self._run_job(self.fallback_url, payload)
            raise

    async def generate(self, prompt: str, params: VideoParams) -> VideoResult:
        """Generate a video clip via the provider interface."""
        payload = {
            "prompt": prompt,
            "model": params.model or self.model,
            "num_frames": min(params.num_frames or 49, 49),
            "width": params.width or 720,
            "height": params.height or 480,
            "fps": params.fps or 24,
            "guidance_scale": params.guidance_scale or 6.0,
            "num_inference_steps": params.num_inference_steps or 50,
            "seed": params.seed,
        }
        _job_id, video_bytes, status_data, _elapsed = await self._run_with_failover(payload)
        return VideoResult(
            video_data=video_bytes,
            width=params.width or 720,
            height=params.height or 480,
            fps=params.fps or 24,
            duration_seconds=status_data.get("duration", 6.0),
            model=params.model or self.model,
        )

    async def generate_video(self, params: CogVideoXGenerationParams) -> CogVideoXGenerationResult:
        """Generate a video clip via the richer task-facing interface."""
        payload = {
            "prompt": params.prompt,
            "negative_prompt": params.negative_prompt,
            "model": params.model.value,
            "num_frames": min(params.num_frames, 49),
            "width": params.width,
            "height": params.height,
            "fps": params.fps,
            "guidance_scale": params.guidance_scale,
            "num_inference_steps": params.num_inference_steps,
            "seed": params.seed,
        }
        job_id, video_bytes, status_data, elapsed = await self._run_with_failover(payload)
        return CogVideoXGenerationResult(
            job_id=job_id,
            video_data=video_bytes,
            duration_seconds=status_data.get("duration", params.num_frames / params.fps),
            width=params.width,
            height=params.height,
            fps=params.fps,
            num_frames=params.num_frames,
            model_used=params.model.value,
            generation_time_seconds=elapsed,
            params_hash=params.compute_hash(),
            metadata=status_data,
        )

    async def generate_keyframe(
        self,
        params: CogVideoXGenerationParams,
        keyframe_index: int = 0,
    ) -> Optional[bytes]:
        """
        Generate a video and extract a single keyframe as a scene image.
        Returns None if no keyframe is available (keyframe population is
        server-side, validated in Stage 2). stage3_images falls back to
        flux when this returns None.
        """
        try:
            result = await self.generate_video(params)
            if result.keyframes and keyframe_index < len(result.keyframes):
                return result.keyframes[keyframe_index]
            return None
        except CogVideoXError:
            return None

    def max_clip_duration_seconds(self) -> float:
        """CogVideoX 5B max clip duration: 6 seconds."""
        return 6.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
