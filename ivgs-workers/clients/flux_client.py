from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import httpx

from shared.providers import ImageProvider, ImageParams, ImageResult

logger = logging.getLogger("ivgs.workers.flux")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FluxError(Exception):
    """Base exception for FLUX/ComfyUI errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, prompt_id: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.prompt_id = prompt_id


class FluxConnectionError(FluxError):
    """ComfyUI server unreachable."""
    pass


class FluxTimeoutError(FluxError):
    """ComfyUI generation timed out."""
    pass


class FluxQueueFullError(FluxError):
    """ComfyUI queue is at capacity."""
    pass


class FluxWorkflowError(FluxError):
    """ComfyUI workflow execution failed."""
    pass


class FluxImageDownloadError(FluxError):
    """Failed to download generated image from ComfyUI."""
    pass


# ---------------------------------------------------------------------------
# Enums and data models
# ---------------------------------------------------------------------------

class FluxModel(str, Enum):
    """Available image generation models."""
    FLUX_DEV = "flux1-dev-fp8.safetensors"
    FLUX_SCHNELL = "flux1-schnell-fp8.safetensors"
    SDXL = "sd_xl_base_1.0.safetensors"
    SD35_MEDIUM = "sd3.5_medium.safetensors"


class FluxSampler(str, Enum):
    """Available samplers for diffusion."""
    EULER = "euler"
    EULER_ANCESTRAL = "euler_ancestral"
    DPM_2M = "dpmpp_2m"
    DPM_2M_SDE = "dpmpp_2m_sde"
    DPM_SDE = "dpmpp_sde"
    UNI_PC = "uni_pc"


class FluxScheduler(str, Enum):
    """Available noise schedulers."""
    NORMAL = "normal"
    KARRAS = "karras"
    SIMPLE = "simple"
    BETA = "beta"
    SGM_UNIFORM = "sgm_uniform"


@dataclass(frozen=True)
class FluxGenerationParams:
    """Parameters for a single image generation request."""
    prompt: str
    negative_prompt: str = ""
    model: FluxModel = FluxModel.FLUX_SCHNELL
    width: int = 1024
    height: int = 1024
    steps: int = 4
    cfg_scale: float = 1.0
    sampler: FluxSampler = FluxSampler.EULER
    scheduler: FluxScheduler = FluxScheduler.SIMPLE
    seed: int = -1
    batch_size: int = 1
    denoise_strength: float = 1.0
    clip_skip: int = -1

    def compute_hash(self) -> str:
        """SHA-256 hash for idempotency."""
        data = {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "model": self.model.value,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "sampler": self.sampler.value,
            "scheduler": self.scheduler.value,
            "seed": self.seed,
        }
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class FluxGenerationResult:
    """Result from a ComfyUI image generation."""
    prompt_id: str
    image_data: bytes
    image_filename: str
    width: int
    height: int
    model_used: str
    generation_time_seconds: float
    seed_used: int
    params_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Flux / ComfyUI Client
# ---------------------------------------------------------------------------

class FluxClient(ImageProvider):
    """
    ComfyUI + FLUX.1 implementation of the ImageProvider interface (spec 19.1).

    Two call paths over one shared ComfyUI workflow flow:
      - generate(prompt, ImageParams) -> ImageResult            (provider interface)
      - generate_image(FluxGenerationParams) -> FluxGenerationResult
        (task-facing interface used by tasks.stage3_images)

    Optional fallback_url enables primary->secondary failover (node-04 ->
    node-05). NOTE: live execution, the failover branch, the ComfyUI queue-
    capacity guard, FLUX->SDXL model-downgrade-on-fallback, and batch
    generation are validated/implemented in Stage 2/3.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "flux1-dev-fp8.safetensors",
        steps: int = 50,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
        fallback_url: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or os.environ["COMFYUI_PRIMARY_URL"]).rstrip("/")
        self.fallback_url = fallback_url.rstrip("/") if fallback_url else None
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
        sampler: str = "euler",
        scheduler: str = "normal",
        denoise: float = 1.0,
        clip_skip: int = -1,
    ) -> dict:
        """Build ComfyUI workflow JSON for FLUX.1/SDXL generation."""
        actual_seed = seed if (seed is not None and seed >= 0) else random.randint(0, 2**32 - 1)
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": actual_seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": denoise,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            # WP-IVGS-07 Task 3 (D-11). `clip_skip` was declared on
            # `FluxGenerationParams:105` and referenced NOWHERE -- one mention
            # tree-wide, its own declaration. Both encoders now read CLIP
            # through `CLIPSetLastLayer` instead of straight off the
            # checkpoint, which is the only way ComfyUI expresses this.
            #
            # BEHAVIOURALLY NEUTRAL UNTIL SOMEONE SETS IT: -1 is the declared
            # default here AND ComfyUI's own default for `stop_at_clip_layer`
            # (verified against node-04's /object_info), so an unset request
            # renders exactly as it did before this node existed.
            "10": {
                "class_type": "CLIPSetLastLayer",
                "inputs": {"clip": ["4", 1], "stop_at_clip_layer": clip_skip},
            },
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["10", 0]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["10", 0]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ivgs_flux", "images": ["8", 0]}},
        }

    async def _run_workflow(self, base_url: str, workflow: dict, client_id: Optional[str] = None):
        """
        Submit a workflow to one ComfyUI server, poll history, download the image.
        Returns (prompt_id, image_bytes, image_filename, history_node, elapsed_seconds).
        Raises typed FluxError subclasses on failure.
        """
        client = await self._get_client()
        cid = client_id or str(uuid.uuid4())
        try:
            response = await client.post(f"{base_url}/prompt", json={"prompt": workflow, "client_id": cid})
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise FluxConnectionError(f"cannot reach ComfyUI at {base_url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise FluxError(str(e), status_code=e.response.status_code) from e

        prompt_id = response.json()["prompt_id"]
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise FluxTimeoutError(f"ComfyUI generation timed out after {self.timeout}s", prompt_id=prompt_id)
            history_resp = await client.get(f"{base_url}/history/{prompt_id}")
            history_resp.raise_for_status()
            history = history_resp.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for _node_id, node_output in outputs.items():
                    if "images" in node_output:
                        image_info = node_output["images"][0]
                        image_url = (
                            f"{base_url}/view?filename={image_info['filename']}"
                            f"&subfolder={image_info.get('subfolder', '')}"
                            f"&type={image_info.get('type', 'output')}"
                        )
                        try:
                            img_resp = await client.get(image_url)
                            img_resp.raise_for_status()
                        except httpx.HTTPError as e:
                            raise FluxImageDownloadError(f"failed to download image for {prompt_id}: {e}", prompt_id=prompt_id) from e
                        return prompt_id, img_resp.content, image_info["filename"], history[prompt_id], elapsed
                raise FluxWorkflowError(f"ComfyUI completed but no image output for {prompt_id}", prompt_id=prompt_id)
            await asyncio.sleep(self.poll_interval)

    async def _run_with_failover(self, workflow: dict, client_id: Optional[str] = None):
        """Run a workflow against the primary, failing over to fallback_url on connection error."""
        try:
            return await self._run_workflow(self.base_url, workflow, client_id)
        except FluxConnectionError:
            if self.fallback_url:
                logger.warning("ComfyUI primary %s unreachable; failing over to %s", self.base_url, self.fallback_url)
                return await self._run_workflow(self.fallback_url, workflow, client_id)
            raise

    async def generate(self, prompt: str, params: ImageParams) -> ImageResult:
        """Generate an image via the provider interface."""
        workflow = self._build_workflow(
            prompt=prompt,
            negative_prompt=params.negative_prompt,
            width=params.width or 1024,
            height=params.height or 1024,
            steps=params.steps or self.steps,
            cfg_scale=params.cfg_scale or 7.5,
            seed=params.seed,
            model=params.model or self.model,
        )
        _pid, image_bytes, _fn, _hist, _elapsed = await self._run_with_failover(workflow)
        return ImageResult(
            image_data=image_bytes,
            width=params.width or 1024,
            height=params.height or 1024,
            seed=params.seed if params.seed is not None else 0,
            model=params.model or self.model,
        )

    async def generate_image(
        self,
        params: FluxGenerationParams,
        client_id: Optional[str] = None,
    ) -> FluxGenerationResult:
        """Generate an image via the richer task-facing interface."""
        workflow = self._build_workflow(
            prompt=params.prompt,
            negative_prompt=params.negative_prompt,
            width=params.width,
            height=params.height,
            steps=params.steps,
            cfg_scale=params.cfg_scale,
            seed=params.seed,
            model=params.model.value,
            sampler=params.sampler.value,
            scheduler=params.scheduler.value,
            denoise=params.denoise_strength,
            clip_skip=params.clip_skip,
        )
        prompt_id, image_bytes, image_filename, _hist, elapsed = await self._run_with_failover(workflow, client_id)
        return FluxGenerationResult(
            prompt_id=prompt_id,
            image_data=image_bytes,
            image_filename=image_filename,
            width=params.width,
            height=params.height,
            model_used=params.model.value,
            generation_time_seconds=elapsed,
            seed_used=params.seed,
            params_hash=params.compute_hash(),
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
