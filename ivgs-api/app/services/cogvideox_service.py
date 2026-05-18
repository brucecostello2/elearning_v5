"""CogVideoX integration service for Phase 3 AI video generation."""
import os
import time
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import torch
from app.services.timeout_manager import TimeoutManager
from app.services.corruption_detector import CorruptionDetector

logger = logging.getLogger(__name__)

# VRAM requirements per model variant
COGVIDEOX_VRAM = {
    "cogvideox_5b": 24576,   # 24 GB
    "cogvideox_2b": 14336,   # 14 GB
}

SUPPORTED_RESOLUTIONS = {
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "480p":  (854, 480),
}


class CogVideoXService:
    """Wraps CogVideoX model inference with timeout, VRAM checks, and
    output validation. Falls back gracefully by returning None on failure."""

    def __init__(
        self,
        model_path: str,
        timeout_manager: TimeoutManager,
        corruption_detector: CorruptionDetector,
        device: str = "cuda",
        model_variant: str = "cogvideox_5b",
    ):
        self.model_path = model_path
        self.timeout_manager = timeout_manager
        self.corruption_detector = corruption_detector
        self.device = device
        self.model_variant = model_variant
        self._pipeline = None          # Lazy-loaded on first generate()
        self._model_loaded_at: Optional[float] = None

    # ------------------------------------------------------------------
    # VRAM preflight
    # ------------------------------------------------------------------
    def get_available_vram_mb(self) -> int:
        if not torch.cuda.is_available():
            return 0
        device_idx = int(self.device.split(":")[-1]) \
            if ":" in self.device else 0
        free, _ = torch.cuda.mem_get_info(device_idx)
        return free // (1024 * 1024)

    def has_sufficient_vram(self) -> bool:
        required = COGVIDEOX_VRAM.get(self.model_variant, 24576)
        available = self.get_available_vram_mb()
        if available < required:
            logger.warning(
                "Insufficient VRAM: need %d MB, have %d MB",
                required, available)
            return False
        return True

    def is_available(self) -> bool:
        """True if model path exists and VRAM is sufficient."""
        if not Path(self.model_path).exists():
            logger.info("CogVideoX model path not found: %s", self.model_path)
            return False
        return self.has_sufficient_vram()

    # ------------------------------------------------------------------
    # Model loading (lazy, thread-safe via GIL)
    # ------------------------------------------------------------------
    def _load_pipeline(self):
        """Lazy-load the CogVideoX diffusion pipeline."""
        if self._pipeline is not None:
            return
        logger.info("Loading CogVideoX pipeline from %s ...", self.model_path)
        t0 = time.monotonic()
        try:
            from diffusers import CogVideoXPipeline
            self._pipeline = CogVideoXPipeline.from_pretrained(
                self.model_path,
                torch_dtype=torch.bfloat16,
            ).to(self.device)
            self._pipeline.enable_model_cpu_offload()
            self._pipeline.vae.enable_slicing()
            self._pipeline.vae.enable_tiling()
            elapsed = time.monotonic() - t0
            self._model_loaded_at = time.monotonic()
            logger.info("CogVideoX loaded in %.1f s", elapsed)
        except Exception as exc:
            logger.error("Failed to load CogVideoX: %s", exc)
            self._pipeline = None
            raise

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def estimate_vram(self, resolution: str, duration_s: int) -> int:
        """Rough VRAM estimate (MB). Scales with resolution × duration."""
        base = COGVIDEOX_VRAM.get(self.model_variant, 24576)
        res_factor = 1.0 if resolution == "720p" else \
                     1.4 if resolution == "1080p" else 0.6
        dur_factor = min(1.0 + (duration_s - 5) * 0.02, 2.0)
        return int(base * res_factor * dur_factor)

    def get_generation_params(
        self,
        scene_type: str,
        duration_s: int = 5,
        resolution: str = "720p",
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return optimised generation params per scene type."""
        fps = 8  # CogVideoX native frame rate
        num_frames = max(1, duration_s * fps)
        w, h = SUPPORTED_RESOLUTIONS.get(resolution, (1280, 720))
        params: Dict[str, Any] = {
            "num_frames": num_frames,
            "width": w,
            "height": h,
            "num_inference_steps": 50,
            "guidance_scale": 6.0,
        }
        if seed is not None:
            params["generator"] = torch.Generator(
                device=self.device).manual_seed(seed)
        # Scene-type tuning
        if scene_type in ("action", "transition"):
            params["guidance_scale"] = 7.5
        elif scene_type in ("talking_head", "interview"):
            params["guidance_scale"] = 5.5
            params["num_inference_steps"] = 40
        return params

    def generate_video(
        self,
        prompt: str,
        output_path: str,
        duration_s: int = 5,
        resolution: str = "720p",
        scene_type: str = "broll",
        seed: Optional[int] = None,
    ) -> Optional[str]:
        """Generate video using CogVideoX. Returns output_path or None."""
        if not self.is_available():
            return None
        try:
            self._load_pipeline()
        except Exception:
            return None

        params = self.get_generation_params(scene_type, duration_s,
                                            resolution, seed)
        timeout_s = 1800 if self.model_variant == "cogvideox_5b" else 900

        logger.info("CogVideoX generating: %s... (%.0fs timeout)",
                    prompt[:60], timeout_s)
        t0 = time.monotonic()

        def _do_generate():
            result = self._pipeline(prompt=prompt, **params)
            return result.frames[0]

        try:
            frames = self.timeout_manager.wrap_with_timeout(
                _do_generate, timeout_s)
        except TimeoutError:
            logger.error("CogVideoX timed out after %ds", timeout_s)
            return None
        except torch.cuda.OutOfMemoryError:
            logger.error("CogVideoX OOM — clearing CUDA cache")
            torch.cuda.empty_cache()
            return None
        except Exception as exc:
            logger.error("CogVideoX generation error: %s", exc)
            return None

        elapsed = time.monotonic() - t0
        logger.info("CogVideoX generation complete in %.1fs", elapsed)

        # Export frames to MP4 via diffusers helper
        try:
            from diffusers.utils import export_to_video
            export_to_video(frames, output_path, fps=8)
        except Exception as exc:
            logger.error("CogVideoX frame export failed: %s", exc)
            return None

        # Validate output integrity
        issues = self.corruption_detector.detect_corruption(output_path)
        if issues:
            logger.error("CogVideoX output corrupted: %s", issues)
            return None

        return output_path

    def validate_output(self, video_path: str) -> bool:
        """Validate generated video with FFprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams",
                 "-of", "json", video_path],
                capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception:
            return False
