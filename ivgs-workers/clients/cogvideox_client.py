from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from ivgs.shared.providers import VideoProvider, VideoParams, VideoResult

logger = logging.getLogger("ivgs.workers.cogvideox")


class CogVideoXClient(VideoProvider):
    """
    CogVideoX 5B implementation of VideoProvider interface (§19.1).

    Generates 480p video clips up to 6 seconds on node-02/node-03.
    VRAM: 24 GB. Timeout: 1800s.
    """

    def __init__(
        self,
        base_url: str = "http://10.10.0.2:8188",
        model: str = "cogvideox-5b",
        timeout: float = 1800.0,
        poll_interval: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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

    async def generate(self, prompt: str, params: VideoParams) -> VideoResult:
        """Generate a video clip via CogVideoX 5B."""
        client = await self._get_client()

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

        # Submit generation job
        response = await client.post(
            f"{self.base_url}/generate",
            json=payload,
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]

        # Poll for completion
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(
                    f"CogVideoX generation timed out after {self.timeout}s"
                )

            status_resp = await client.get(f"{self.base_url}/status/{job_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data["status"] == "completed":
                video_resp = await client.get(
                    f"{self.base_url}/download/{job_id}"
                )
                video_resp.raise_for_status()

                return VideoResult(
                    video_bytes=video_resp.content,
                    width=params.width or 720,
                    height=params.height or 480,
                    fps=params.fps or 24,
                    duration_seconds=status_data.get("duration", 6.0),
                    format="mp4",
                    model=params.model or self.model,
                )
            elif status_data["status"] == "failed":
                raise RuntimeError(
                    f"CogVideoX generation failed: {status_data.get('error', 'unknown')}"
                )

            await asyncio.sleep(self.poll_interval)

    def max_clip_duration_seconds(self) -> float:
        """CogVideoX 5B max clip duration: 6 seconds."""
        return 6.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
