from __future__ import annotations

import asyncio
import logging
import uuid
import os
from typing import Optional

import httpx

from shared.providers import ImageProvider, ImageParams, ImageResult

logger = logging.getLogger("ivgs.workers.flux")


class FluxClient(ImageProvider):
    """
    ComfyUI + FLUX.1 implementation of ImageProvider interface (§19.1).

    Lifecycle:
    1. Submit workflow via POST /prompt
    2. Poll GET /history/{prompt_id} until complete
    3. Download output image via GET /view
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "flux1-dev-fp8.safetensors",
        steps: int = 50,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
    ) -> None:
        self.base_url = (base_url or os.environ["COMFYUI_PRIMARY_URL"]).rstrip("/")
        self.model = model
        self.steps = steps
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def generate(self, prompt: str, params: ImageParams) -> ImageResult:
        """Generate an image via ComfyUI FLUX.1 Dev workflow."""
        client = await self._get_client()
        client_id = str(uuid.uuid4())

        workflow = self._build_workflow(
            prompt=prompt,
            negative_prompt=params.negative_prompt or "",
            width=params.width or 1024,
            height=params.height or 1024,
            steps=params.steps or self.steps,
            cfg_scale=params.cfg_scale or 7.5,
            seed=params.seed,
            model=params.model or self.model,
        )

        # Submit workflow
        response = await client.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        # Poll for completion
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(
                    f"ComfyUI generation timed out after {self.timeout}s"
                )

            history_resp = await client.get(
                f"{self.base_url}/history/{prompt_id}"
            )
            history_resp.raise_for_status()
            history = history_resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    if "images" in node_output:
                        image_info = node_output["images"][0]
                        image_url = (
                            f"{self.base_url}/view?"
                            f"filename={image_info['filename']}"
                            f"&subfolder={image_info.get('subfolder', '')}"
                            f"&type={image_info.get('type', 'output')}"
                        )
                        # Download image bytes
                        img_resp = await client.get(image_url)
                        img_resp.raise_for_status()

                        return ImageResult(
                            image_bytes=img_resp.content,
                            width=params.width or 1024,
                            height=params.height or 1024,
                            format="png",
                            model=params.model or self.model,
                            seed=params.seed,
                        )
                raise RuntimeError(
                    f"ComfyUI completed but no image output found for {prompt_id}"
                )

            await asyncio.sleep(self.poll_interval)

    def _build_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: Optional[int],
        model: str,
    ) -> dict:
        """Build ComfyUI workflow JSON for FLUX.1 generation."""
        import random

        actual_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": actual_seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": model},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1],
                },
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["4", 1],
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2],
                },
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "ivgs_flux",
                    "images": ["8", 0],
                },
            },
        }

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
