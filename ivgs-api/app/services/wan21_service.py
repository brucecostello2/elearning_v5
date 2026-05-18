"""Wan2.1 text-to-video model integration. Identical interface to
CogVideoXService for drop-in interchangeability."""
import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import torch
from app.services.timeout_manager import TimeoutManager
from app.services.corruption_detector import CorruptionDetector

logger = logging.getLogger(__name__)

WAN21_VRAM_MB = 16384   # 16 GB required for Wan2.1 T2V
WAN21_MAX_DURATION_S = 30


class Wan21Service:
    """Wan2.1 T2V (text-to-video) integration.
    Lower VRAM than CogVideoX — suitable for shorter clips on more nodes."""

    def __init__(
        self,
        model_path: str,
        timeout_manager: TimeoutManager,
        corruption_detector: CorruptionDetector,
        device: str = "cuda",
    ):
        self.model_path = model_path
        self.timeout_manager = timeout_manager
        self.corruption_detector = corruption_detector
        self.device = device
        self._pipeline = None

    def get_available_vram_mb(self) -> int:
        if not torch.cuda.is_available():
            return 0
        idx = int(self.device.split(":")[-1]) if ":" in self.device else 0
        free, _ = torch.cuda.mem_get_info(idx)
        return free // (1024 * 1024)

    def is_available(self) -> bool:
        if not Path(self.model_path).exists():
            return False
        return self.get_available_vram_mb() >= WAN21_VRAM_MB

    def _load_pipeline(self):
        if self._pipeline is not None:
            return
        logger.info("Loading Wan2.1 pipeline from %s ...", self.model_path)
        try:
            from wan import WanT2VPipeline  # Wan2.1 library
            self._pipeline = WanT2VPipeline.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
            ).to(self.device)
            logger.info("Wan2.1 loaded successfully")
        except ImportError:
            logger.error("wan package not installed — skipping Wan2.1")
            raise
        except Exception as exc:
            logger.error("Failed to load Wan2.1: %s", exc)
            self._pipeline = None
            raise

    def get_generation_params(
        self,
        scene_type: str,
        duration_s: int = 4,
        resolution: str = "720p",
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        fps = 16  # Wan2.1 default frame rate
        num_frames = max(1, min(duration_s * fps, WAN21_MAX_DURATION_S * fps))
        w, h = (1280, 720) if resolution == "720p" else (854, 480)
        params: Dict[str, Any] = {
            "num_frames": num_frames,
            "width": w,
            "height": h,
            "num_inference_steps": 40,
            "guidance_scale": 5.0,
        }
        if seed is not None:
            params["generator"] = torch.Generator(
                device=self.device).manual_seed(seed)
        return params

    def generate_video(
        self,
        prompt: str,
        output_path: str,
        duration_s: int = 4,
        resolution: str = "720p",
        scene_type: str = "broll",
        seed: Optional[int] = None,
    ) -> Optional[str]:
        """Generate clip with Wan2.1. Returns output_path or None."""
        if duration_s > WAN21_MAX_DURATION_S:
            logger.warning("Wan2.1 max duration is %ds; requested %ds",
                           WAN21_MAX_DURATION_S, duration_s)
            return None
        if not self.is_available():
            return None
        try:
            self._load_pipeline()
        except Exception:
            return None

        params = self.get_generation_params(scene_type, duration_s,
                                            resolution, seed)
        logger.info("Wan2.1 generating: %s...", prompt[:60])
        t0 = time.monotonic()

        def _generate():
            result = self._pipeline(prompt=prompt, **params)
            return result.frames[0]

        try:
            frames = self.timeout_manager.wrap_with_timeout(_generate, 900)
        except TimeoutError:
            logger.error("Wan2.1 timed out")
            return None
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            logger.error("Wan2.1 OOM")
            return None
        except Exception as exc:
            logger.error("Wan2.1 error: %s", exc)
            return None

        elapsed = time.monotonic() - t0
        logger.info("Wan2.1 complete in %.1fs", elapsed)

        try:
            import imageio
            imageio.mimwrite(output_path, frames, fps=16, quality=8)
        except Exception as exc:
            logger.error("Wan2.1 frame export failed: %s", exc)
            return None

        if self.corruption_detector.detect_corruption(output_path):
            return None
        return output_path
