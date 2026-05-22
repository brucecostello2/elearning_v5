"""
IVGS v5 — Media Converter Utilities
======================================

Provides conversion and normalization for media assets:
- Image: resize to 1920×1080, format conversion (PNG/JPEG/WEBP)
- Audio: resample to 48kHz 24-bit mono WAV, trim silence
- Video: container conversion, resolution scaling, codec transcoding

Used by pipeline stages to normalize generated media before SeaweedFS upload.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger("ivgs.media_converter")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MediaConversionError(Exception):
    """Media conversion failed."""


class FFmpegNotFoundError(MediaConversionError):
    """FFmpeg binary not found."""


class ImageConversionError(MediaConversionError):
    """Image conversion/resize failed."""


class AudioConversionError(MediaConversionError):
    """Audio conversion/normalization failed."""


class VideoConversionError(MediaConversionError):
    """Video conversion/transcoding failed."""


# ---------------------------------------------------------------------------
# Conversion results
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    """Generic conversion result."""
    output_data: bytes
    input_sha256: str
    output_sha256: str
    input_size_bytes: int
    output_size_bytes: int
    conversion_details: Dict[str, Any]


# ---------------------------------------------------------------------------
# Image Converter
# ---------------------------------------------------------------------------

class ImageConverter:
    """Image resizing and format conversion using PIL."""

    @staticmethod
    def resize_to_target(
        image_data: bytes,
        target_width: int = 1920,
        target_height: int = 1080,
        maintain_aspect: bool = True,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        output_format: str = "PNG",
        quality: int = 95,
    ) -> ConversionResult:
        """
        Resize image to target dimensions.

        If maintain_aspect=True, the image is fit within the target
        dimensions and padded with background_color.
        If maintain_aspect=False, the image is stretched to fill exactly.
        """
        from PIL import Image

        input_sha256 = hashlib.sha256(image_data).hexdigest()

        try:
            img = Image.open(io.BytesIO(image_data))

            if img.mode == "RGBA" and output_format.upper() == "JPEG":
                background = Image.new("RGB", img.size, background_color)
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if maintain_aspect:
                # Fit within target, pad remaining space
                img_ratio = img.width / img.height
                target_ratio = target_width / target_height

                if img_ratio > target_ratio:
                    # Width-constrained
                    new_width = target_width
                    new_height = int(target_width / img_ratio)
                else:
                    # Height-constrained
                    new_height = target_height
                    new_width = int(target_height * img_ratio)

                resized = img.resize(
                    (new_width, new_height), Image.LANCZOS
                )

                # Create padded canvas
                canvas = Image.new(
                    "RGB", (target_width, target_height), background_color
                )
                offset_x = (target_width - new_width) // 2
                offset_y = (target_height - new_height) // 2
                canvas.paste(resized, (offset_x, offset_y))
                output_img = canvas
            else:
                output_img = img.resize(
                    (target_width, target_height), Image.LANCZOS
                )

            # Save to bytes
            output_buffer = io.BytesIO()
            save_kwargs: Dict[str, Any] = {"format": output_format}
            if output_format.upper() == "JPEG":
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True
            elif output_format.upper() == "PNG":
                save_kwargs["optimize"] = True
            elif output_format.upper() == "WEBP":
                save_kwargs["quality"] = quality

            output_img.save(output_buffer, **save_kwargs)
            output_data = output_buffer.getvalue()
            output_sha256 = hashlib.sha256(output_data).hexdigest()

            img.close()
            output_img.close()

            return ConversionResult(
                output_data=output_data,
                input_sha256=input_sha256,
                output_sha256=output_sha256,
                input_size_bytes=len(image_data),
                output_size_bytes=len(output_data),
                conversion_details={
                    "original_size": f"{img.width}×{img.height}" if hasattr(img, 'width') else "unknown",
                    "output_size": f"{target_width}×{target_height}",
                    "format": output_format,
                    "maintain_aspect": maintain_aspect,
                },
            )

        except Exception as e:
            raise ImageConversionError(f"Image resize failed: {e}") from e

    @staticmethod
    def convert_format(
        image_data: bytes,
        output_format: str = "PNG",
        quality: int = 95,
    ) -> ConversionResult:
        """Convert image between formats without resizing."""
        from PIL import Image

        input_sha256 = hashlib.sha256(image_data).hexdigest()

        try:
            img = Image.open(io.BytesIO(image_data))

            if output_format.upper() == "JPEG" and img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            output_buffer = io.BytesIO()
            save_kwargs: Dict[str, Any] = {"format": output_format}
            if output_format.upper() == "JPEG":
                save_kwargs["quality"] = quality
            output_img = img
            output_img.save(output_buffer, **save_kwargs)
            output_data = output_buffer.getvalue()

            return ConversionResult(
                output_data=output_data,
                input_sha256=input_sha256,
                output_sha256=hashlib.sha256(output_data).hexdigest(),
                input_size_bytes=len(image_data),
                output_size_bytes=len(output_data),
                conversion_details={"format": output_format},
            )

        except Exception as e:
            raise ImageConversionError(f"Format conversion failed: {e}") from e


# ---------------------------------------------------------------------------
# Audio Converter
# ---------------------------------------------------------------------------

class AudioConverter:
    """Audio resampling and normalization using FFmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self._ffmpeg_path = ffmpeg_path
        self._verify_ffmpeg()

    def _verify_ffmpeg(self) -> None:
        try:
            subprocess.run(
                [self._ffmpeg_path, "-version"],
                capture_output=True,
                timeout=5,
            )
        except FileNotFoundError:
            raise FFmpegNotFoundError(
                f"FFmpeg not found at '{self._ffmpeg_path}'"
            )

    def normalize_wav(
        self,
        audio_data: bytes,
        target_sample_rate: int = 48000,
        target_bit_depth: int = 24,
        target_channels: int = 1,
    ) -> ConversionResult:
        """
        Normalize audio to target WAV specifications.

        Converts to 48kHz 24-bit mono WAV per §7.1.5.
        """
        input_sha256 = hashlib.sha256(audio_data).hexdigest()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as inp:
            inp.write(audio_data)
            input_path = inp.name

        output_path = input_path + ".normalized.wav"

        try:
            codec = f"pcm_s{target_bit_depth}le"
            cmd = [
                self._ffmpeg_path,
                "-y",
                "-i", input_path,
                "-ar", str(target_sample_rate),
                "-ac", str(target_channels),
                "-acodec", codec,
                "-f", "wav",
                output_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise AudioConversionError(
                    f"FFmpeg audio normalization failed: {result.stderr[:500]}"
                )

            with open(output_path, "rb") as f:
                output_data = f.read()

            return ConversionResult(
                output_data=output_data,
                input_sha256=input_sha256,
                output_sha256=hashlib.sha256(output_data).hexdigest(),
                input_size_bytes=len(audio_data),
                output_size_bytes=len(output_data),
                conversion_details={
                    "sample_rate": target_sample_rate,
                    "bit_depth": target_bit_depth,
                    "channels": target_channels,
                },
            )

        except subprocess.TimeoutExpired:
            raise AudioConversionError("Audio normalization timed out")
        finally:
            for path in (input_path, output_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def trim_silence(
        self,
        audio_data: bytes,
        silence_threshold_db: float = -40.0,
        min_silence_duration: float = 0.5,
    ) -> ConversionResult:
        """Trim leading and trailing silence from audio."""
        input_sha256 = hashlib.sha256(audio_data).hexdigest()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as inp:
            inp.write(audio_data)
            input_path = inp.name

        output_path = input_path + ".trimmed.wav"

        try:
            cmd = [
                self._ffmpeg_path,
                "-y",
                "-i", input_path,
                "-af", (
                    f"silenceremove=start_periods=1"
                    f":start_duration={min_silence_duration}"
                    f":start_threshold={silence_threshold_db}dB"
                    f",areverse"
                    f",silenceremove=start_periods=1"
                    f":start_duration={min_silence_duration}"
                    f":start_threshold={silence_threshold_db}dB"
                    f",areverse"
                ),
                output_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )

            if result.returncode != 0:
                raise AudioConversionError(
                    f"Silence trimming failed: {result.stderr[:500]}"
                )

            with open(output_path, "rb") as f:
                output_data = f.read()

            return ConversionResult(
                output_data=output_data,
                input_sha256=input_sha256,
                output_sha256=hashlib.sha256(output_data).hexdigest(),
                input_size_bytes=len(audio_data),
                output_size_bytes=len(output_data),
                conversion_details={"operation": "silence_trim"},
            )

        finally:
            for path in (input_path, output_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Video Converter
# ---------------------------------------------------------------------------

class VideoConverter:
    """Video transcoding and resolution scaling using FFmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self._ffmpeg_path = ffmpeg_path

    def scale_resolution(
        self,
        video_data: bytes,
        target_width: int = 1920,
        target_height: int = 1080,
        video_codec: str = "libx264",
        crf: int = 23,
        audio_codec: str = "aac",
        preset: str = "medium",
    ) -> ConversionResult:
        """Scale video to target resolution with transcoding."""
        input_sha256 = hashlib.sha256(video_data).hexdigest()

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as inp:
            inp.write(video_data)
            input_path = inp.name

        output_path = input_path + ".scaled.mp4"

        try:
            cmd = [
                self._ffmpeg_path,
                "-y",
                "-i", input_path,
                "-vf", f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                       f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", video_codec,
                "-crf", str(crf),
                "-preset", preset,
                "-c:a", audio_codec,
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )

            if result.returncode != 0:
                raise VideoConversionError(
                    f"Video scaling failed: {result.stderr[:500]}"
                )

            with open(output_path, "rb") as f:
                output_data = f.read()

            return ConversionResult(
                output_data=output_data,
                input_sha256=input_sha256,
                output_sha256=hashlib.sha256(output_data).hexdigest(),
                input_size_bytes=len(video_data),
                output_size_bytes=len(output_data),
                conversion_details={
                    "resolution": f"{target_width}×{target_height}",
                    "codec": video_codec,
                    "crf": crf,
                },
            )

        finally:
            for path in (input_path, output_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def extract_frame(
        self,
        video_data: bytes,
        timestamp_seconds: float = 0.0,
        output_format: str = "png",
    ) -> bytes:
        """Extract a single frame from video as an image."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as inp:
            inp.write(video_data)
            input_path = inp.name

        output_path = input_path + f".frame.{output_format}"

        try:
            cmd = [
                self._ffmpeg_path,
                "-y",
                "-ss", str(timestamp_seconds),
                "-i", input_path,
                "-frames:v", "1",
                "-f", "image2",
                output_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                raise VideoConversionError(
                    f"Frame extraction failed: {result.stderr[:500]}"
                )

            with open(output_path, "rb") as f:
                return f.read()

        finally:
            for path in (input_path, output_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Asset deduplication helper
# ---------------------------------------------------------------------------

def compute_asset_sha256(data: bytes) -> str:
    """Compute SHA-256 hash for asset deduplication before SeaweedFS upload."""
    return hashlib.sha256(data).hexdigest()


def check_duplicate_asset(
    sha256_hash: str,
    api_base_url: str,
    service_token: str,
) -> Optional[Dict[str, Any]]:
    """
    Check if an asset with the same SHA-256 already exists in SeaweedFS.

    Calls GET /api/v1/assets?sha256={hash} to find duplicates.
    Returns asset metadata if found, None otherwise.
    """
    try:
        import httpx
        with httpx.Client(
            timeout=10.0,
            headers={
                "Authorization": f"Bearer {service_token}",
            },
        ) as client:
            resp = client.get(
                f"{api_base_url}/assets",
                params={"sha256": sha256_hash},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("items", [])
                if items:
                    return items[0]
            return None
    except Exception as e:
        logger.warning("duplicate_check_failed", error=str(e))
        return None
