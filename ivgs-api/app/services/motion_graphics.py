"""MotionGraphicsService — Ken Burns and zoom/pan animation via FFmpeg.

Creates animated video segments from still images. Used by the
FallbackManager at L2 (Ken Burns) and L3 (zoom/pan) when AI video
generation is unavailable.

All methods are synchronous and call FFmpeg via subprocess. The caller
should wrap calls in TimeoutManager if needed.

Usage:
    svc = MotionGraphicsService(workdir="/mnt/workdir")
    video_path = svc.create_ken_burns(
        image_path="/workdir/42/scene_1.png",
        output_path="/workdir/42/scene_1_anim.mp4",
        duration_seconds=14.5,
    )
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class EffectType(str, Enum):
    KEN_BURNS = "ken_burns"
    ZOOM_IN   = "zoom_in"
    ZOOM_OUT  = "zoom_out"
    PAN_LEFT  = "pan_left"
    PAN_RIGHT = "pan_right"
    STATIC    = "static"


@dataclass
class KenBurnsParams:
    """Parameters for Ken Burns effect."""

    zoom_start: float = 1.0    # Starting zoom multiplier
    zoom_end: float   = 1.3    # Ending zoom multiplier (30% zoom in)
    pan_x: float      = 0.0    # X pan pixels/frame (positive = right)
    pan_y: float      = 0.0    # Y pan pixels/frame (positive = down)
    fps: int          = 25
    output_width: int  = 1920
    output_height: int = 1080


class MotionGraphicsService:
    """Renders animated stills using FFmpeg filter chains."""

    FFMPEG_BIN = "ffmpeg"
    DEFAULT_CRF = 23
    DEFAULT_PRESET = "medium"

    def __init__(
        self,
        workdir: str = "/mnt/workdir",
        ffmpeg_bin: str = FFMPEG_BIN,
    ) -> None:
        self.workdir = workdir
        self.ffmpeg_bin = ffmpeg_bin

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_ken_burns(
        self,
        image_path: str,
        output_path: str,
        duration_seconds: float,
        params: Optional[KenBurnsParams] = None,
    ) -> str:
        """Create a Ken Burns (slow zoom) animation from a still image.

        Args:
            image_path:       Path to source PNG/JPEG image.
            output_path:      Destination .mp4 file path.
            duration_seconds: Target video duration.
            params:           Animation parameters. Uses defaults if None.

        Returns:
            output_path on success.

        Raises:
            subprocess.CalledProcessError: If FFmpeg fails.
            FileNotFoundError:             If image_path does not exist.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Source image not found: {image_path}")

        p = params or KenBurnsParams()
        total_frames = int(duration_seconds * p.fps)

        # FFmpeg zoompan filter for Ken Burns effect
        # z=: zoom expression (linear interpolation from zoom_start to zoom_end)
        # x/y=: pan to center of frame
        zoom_expr = (
            f"'min(zoom+{(p.zoom_end - p.zoom_start) / total_frames:.6f}, "
            f"{p.zoom_end})'"
        )
        vf = (
            f"scale={p.output_width * 2}:{p.output_height * 2},"
            f"zoompan=z={zoom_expr}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:fps={p.fps}:"
            f"s={p.output_width}x{p.output_height},"
            f"setsar=1"
        )

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        cmd = [
            self.ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration_seconds),
            "-c:v", "libx264",
            "-crf", str(self.DEFAULT_CRF),
            "-preset", self.DEFAULT_PRESET,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        logger.debug("Ken Burns FFmpeg: %s", " ".join(cmd))
        self._run_ffmpeg(cmd)
        logger.info("Ken Burns created: %s (%.1fs)", output_path, duration_seconds)
        return output_path

    def create_zoom_pan(
        self,
        image_path: str,
        output_path: str,
        duration_seconds: float,
        effect: EffectType = EffectType.ZOOM_IN,
        target_width: int = 1920,
        target_height: int = 1080,
        fps: int = 25,
    ) -> str:
        """Create a simple zoom-in, zoom-out, or pan animation.

        Args:
            image_path:       Source image path.
            output_path:      Output .mp4 path.
            duration_seconds: Duration in seconds.
            effect:           Which zoom/pan direction to apply.
            target_width:     Output video width in pixels.
            target_height:    Output video height in pixels.
            fps:              Output frames per second.

        Returns:
            output_path on success.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Source image not found: {image_path}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        total_frames = int(duration_seconds * fps)

        vf = self._build_zoom_pan_filter(
            effect, total_frames, fps, target_width, target_height
        )

        cmd = [
            self.ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration_seconds),
            "-c:v", "libx264",
            "-crf", str(self.DEFAULT_CRF),
            "-preset", self.DEFAULT_PRESET,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd)
        logger.info("Zoom/pan created: %s effect=%s", output_path, effect.value)
        return output_path

    def create_static_video(
        self,
        image_path: str,
        output_path: str,
        duration_seconds: float,
        target_width: int = 1920,
        target_height: int = 1080,
    ) -> str:
        """Convert a still image to a static (no motion) video segment.

        Args:
            image_path:       Source image.
            output_path:      Output .mp4 path.
            duration_seconds: Duration in seconds.
            target_width:     Output width.
            target_height:    Output height.

        Returns:
            output_path on success.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Source image not found: {image_path}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        vf = (f"scale={target_width}:{target_height}:"
              f"force_original_aspect_ratio=decrease,"
              f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
              f"setsar=1")

        cmd = [
            self.ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration_seconds),
            "-c:v", "libx264",
            "-crf", str(self.DEFAULT_CRF),
            "-preset", self.DEFAULT_PRESET,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd)
        logger.info("Static video created: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_zoom_pan_filter(
        self,
        effect: EffectType,
        total_frames: int,
        fps: int,
        w: int,
        h: int,
    ) -> str:
        """Build FFmpeg -vf string for zoom/pan effect."""
        scale_w, scale_h = w * 2, h * 2

        if effect == EffectType.ZOOM_IN:
            z_expr = f"'min(zoom+{0.3 / total_frames:.6f}, 1.3)'"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif effect == EffectType.ZOOM_OUT:
            z_expr = f"'max(zoom-{0.3 / total_frames:.6f}, 1.0)'"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif effect == EffectType.PAN_LEFT:
            z_expr = "'1.1'"
            x_expr = f"'iw/2-(iw/zoom/2)+on*{w * 0.3 / total_frames:.4f}'"
            y_expr = "ih/2-(ih/zoom/2)"
        elif effect == EffectType.PAN_RIGHT:
            z_expr = "'1.1'"
            x_expr = f"'iw/2-(iw/zoom/2)-on*{w * 0.3 / total_frames:.4f}'"
            y_expr = "ih/2-(ih/zoom/2)"
        else:  # STATIC or unknown
            return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")

        return (
            f"scale={scale_w}:{scale_h},"
            f"zoompan=z={z_expr}:x={x_expr}:y={y_expr}:"
            f"d={total_frames}:fps={fps}:s={w}x{h},"
            f"setsar=1"
        )

    def _run_ffmpeg(self, cmd: list) -> None:
        """Execute an FFmpeg command, raising on non-zero exit."""
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout,
                stderr=stderr.encode(),
            )
