from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from ivgs.shared.providers import VideoProvider, VideoParams, VideoResult

logger = logging.getLogger("ivgs.workers.wan21")


class Wan21Client(VideoProvider):
    """
    Wan2.1 implementation of VideoProvider interface (§19.1).

    Generates 720p video clips up to 5 seconds on node-02/node-03.
    VRAM: 16 GB. Timeout: 30s per segment.
    """

    def __init__(
        self,
        base_url: str = "http://10.10.0.2:8190",
        timeout: float = 30.0,
        poll_interval: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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

    async def generate(self, prompt: str, params: VideoParams) -> VideoResult:
        """Generate a video clip via Wan2.1."""
        client = await self._get_client()

        payload = {
            "prompt": prompt,
            "width": params.width or 1280,
            "height": params.height or 720,
            "num_frames": min(params.num_frames or 120, 150),
            "fps": params.fps or 24,
            "guidance_scale": params.guidance_scale or 5.0,
            "seed": params.seed,
        }

        response = await client.post(
            f"{self.base_url}/generate",
            json=payload,
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]

        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(f"Wan2.1 generation timed out after {self.timeout}s")

            status_resp = await client.get(f"{self.base_url}/status/{job_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data["status"] == "completed":
                video_resp = await client.get(f"{self.base_url}/download/{job_id}")
                video_resp.raise_for_status()
                return VideoResult(
                    video_bytes=video_resp.content,
                    width=params.width or 1280,
                    height=params.height or 720,
                    fps=params.fps or 24,
                    duration_seconds=status_data.get("duration", 5.0),
                    format="mp4",
                    model="wan2.1",
                )
            elif status_data["status"] == "failed":
                raise RuntimeError(
                    f"Wan2.1 failed: {status_data.get('error', 'unknown')}"
                )

            await asyncio.sleep(self.poll_interval)

    def max_clip_duration_seconds(self) -> float:
        """Wan2.1 max clip duration: 5 seconds."""
        return 5.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
