from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import httpx

from shared.providers import VideoProvider, VideoParams, VideoResult

logger = logging.getLogger("ivgs.workers.wan21")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class Wan21Error(Exception):
    """Base exception for Wan2.1 client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, request_id: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class Wan21ConnectionError(Wan21Error):
    """Wan2.1 server unreachable."""
    pass


class Wan21TimeoutError(Wan21Error):
    """Wan2.1 generation timed out."""
    pass


class Wan21GenerationError(Wan21Error):
    """Wan2.1 generation failed."""
    pass


class Wan21DownloadError(Wan21Error):
    """Failed to download generated video from Wan2.1."""
    pass


# ---------------------------------------------------------------------------
# Configuration and data models
# ---------------------------------------------------------------------------

class Wan21Quality(str, Enum):
    """Available quality presets."""
    STANDARD = "standard"
    HIGH = "high"


@dataclass(frozen=True)
class Wan21GenerationParams:
    """Parameters for a single Wan2.1 video generation request."""
    prompt: str
    negative_prompt: str = "blurry, low quality, distorted, watermark, text, static"
    width: int = 1280
    height: int = 720
    num_frames: int = 150
    fps: int = 30
    guidance_scale: float = 7.5
    num_inference_steps: int = 50
    seed: int = -1
    quality: Wan21Quality = Wan21Quality.STANDARD

    def compute_hash(self) -> str:
        """SHA-256 hash for idempotency."""
        data = {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "width": self.width,
            "height": self.height,
            "num_frames": self.num_frames,
            "fps": self.fps,
            "guidance_scale": self.guidance_scale,
            "num_inference_steps": self.num_inference_steps,
            "seed": self.seed,
            # ⛔ WP-IVGS-07 Task 3 (D-11) — THE DEDUP TRAP, AND WHY THE HASH AND
            # THE REQUEST HAD TO CHANGE IN THE SAME COMMIT.
            #
            # `quality` reached NEITHER the request NOR this hash. That was
            # self-consistent while it did nothing: two requests differing only
            # in `quality` produced identical video, so sharing a cache entry
            # was correct.
            #
            # The moment `quality` starts influencing the render -- as it now
            # does, below -- a hash that ignores it makes STANDARD and HIGH
            # collide: the second request is served the first one's artifact
            # from the dedup cache and nothing anywhere reports a mismatch.
            # Wiring the parameter without this line would have been strictly
            # worse than leaving it dead.
            "quality": self.quality.value,
        }
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


#: What each preset actually changes. WP-IVGS-07 Task 3.
#: Declared as a table rather than computed so the two presets are readable
#: side by side and a third cannot be added by accident.
_QUALITY_PROFILES: dict[str, dict[str, int]] = {
    "standard": {},                                  # the shipped defaults
    "high": {"num_inference_steps": 75},
}


@dataclass
class Wan21GenerationResult:
    """Result from a Wan2.1 video generation."""
    request_id: str
    video_data: bytes
    width: int
    height: int
    fps: int
    duration_seconds: float
    num_frames: int
    file_size_bytes: int
    generation_time_seconds: float
    seed_used: int
    params_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Wan2.1 Client
# ---------------------------------------------------------------------------

class Wan21Client(VideoProvider):
    """
    Wan2.1 implementation of the VideoProvider interface (spec 19.1).

    Generates 720p clips up to 5s on node-02/node-03. VRAM: 16 GB.

    Two call paths over one shared HTTP flow:
      - generate(prompt, VideoParams) -> VideoResult            (provider interface)
      - generate_video(Wan21GenerationParams) -> Wan21GenerationResult
        (task-facing interface used by tasks.video_generation_task)

    Optional fallback_url enables primary->secondary failover. NOTE: live
    execution and the failover branch are validated in Stage 2.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        poll_interval: float = 2.0,
        fallback_url: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or os.environ["WAN21_URL"]).rstrip("/")
        self.fallback_url = fallback_url.rstrip("/") if fallback_url else None
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
        Returns (request_id, video_bytes, status_data, elapsed_seconds).
        Raises typed Wan21Error subclasses on failure.
        """
        client = await self._get_client()
        try:
            response = await client.post(f"{base_url}/generate", json=payload)
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise Wan21ConnectionError(f"cannot reach Wan2.1 server at {base_url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise Wan21Error(str(e), status_code=e.response.status_code) from e

        request_id = response.json()["job_id"]
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise Wan21TimeoutError(
                    f"Wan2.1 generation timed out after {self.timeout}s", request_id=request_id
                )
            status_resp = await client.get(f"{base_url}/status/{request_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data.get("status")
            if status == "completed":
                try:
                    video_resp = await client.get(f"{base_url}/download/{request_id}")
                    video_resp.raise_for_status()
                except httpx.HTTPError as e:
                    raise Wan21DownloadError(f"failed to download job {request_id}: {e}", request_id=request_id) from e
                return request_id, video_resp.content, status_data, elapsed
            if status == "failed":
                raise Wan21GenerationError(
                    f"Wan2.1 generation failed: {status_data.get('error', 'unknown')}", request_id=request_id
                )
            await asyncio.sleep(self.poll_interval)

    async def _run_with_failover(self, payload: Dict[str, Any]):
        """Run a job against the primary, failing over to fallback_url on connection error."""
        try:
            return await self._run_job(self.base_url, payload)
        except Wan21ConnectionError:
            if self.fallback_url:
                logger.warning(
                    "Wan2.1 primary %s unreachable; failing over to %s",
                    self.base_url, self.fallback_url,
                )
                return await self._run_job(self.fallback_url, payload)
            raise

    async def generate(self, prompt: str, params: VideoParams) -> VideoResult:
        """Generate a video clip via the provider interface."""
        payload = {
            "prompt": prompt,
            "width": params.width or 1280,
            "height": params.height or 720,
            "num_frames": min(params.num_frames or 120, 150),
            "fps": params.fps or 24,
            "guidance_scale": params.guidance_scale or 5.0,
            "seed": params.seed,
        }
        _rid, video_bytes, status_data, _elapsed = await self._run_with_failover(payload)
        return VideoResult(
            video_data=video_bytes,
            width=params.width or 1280,
            height=params.height or 720,
            fps=params.fps or 24,
            duration_seconds=status_data.get("duration", 5.0),
            model="wan2.1",
        )

    async def generate_video(self, params: Wan21GenerationParams) -> Wan21GenerationResult:
        """Generate a video clip via the richer task-facing interface."""
        # WP-IVGS-07 Task 3 (D-11). `quality` reached nothing at all -- and
        # neither did `num_inference_steps`, which this payload simply omitted,
        # so the engine used its own default for every render regardless of
        # what the caller asked for. Both are sent now.
        #
        # The preset is applied as an OVERRIDE on top of the explicit fields,
        # so `quality` cannot silently contradict a value the caller set
        # deliberately without that being visible in this one table.
        steps = params.num_inference_steps
        profile = _QUALITY_PROFILES.get(params.quality.value, {})
        steps = profile.get("num_inference_steps", steps)
        payload = {
            "prompt": params.prompt,
            "negative_prompt": params.negative_prompt,
            "width": params.width,
            "height": params.height,
            "num_frames": min(params.num_frames, 150),
            "fps": params.fps,
            "guidance_scale": params.guidance_scale,
            "num_inference_steps": steps,
            "seed": params.seed,
        }
        request_id, video_bytes, status_data, elapsed = await self._run_with_failover(payload)
        return Wan21GenerationResult(
            request_id=request_id,
            video_data=video_bytes,
            width=params.width,
            height=params.height,
            fps=params.fps,
            duration_seconds=status_data.get("duration", params.num_frames / params.fps),
            num_frames=params.num_frames,
            file_size_bytes=len(video_bytes),
            generation_time_seconds=elapsed,
            seed_used=params.seed,
            params_hash=params.compute_hash(),
            metadata=status_data,
        )

    def max_clip_duration_seconds(self) -> float:
        """Wan2.1 max clip duration: 5 seconds."""
        return 5.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
