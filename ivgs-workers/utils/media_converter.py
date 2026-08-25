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


class DuplicateCheckError(RuntimeError):
    """The deduplication probe could not be answered.

    WP-45 Task 1, and WP-00 swallowed-failures register. The old helper caught
    every exception and returned ``None``, which the four call sites read as
    "no duplicate exists" — so a probe against a route that **did not exist**
    (``GET /api/v1/assets?sha256=`` was never implemented; ``asset_router`` had
    only ``/{asset_id}`` and its children) answered 404, was swallowed, and
    reported itself as a clean miss. Content-hash dedup was dead fleet-wide for
    image, video, animation and audio alike and nothing on any surface said so
    (WP-46 addendum A5.2 / ledger L-8).

    "I could not check" and "I checked and there is nothing" are different
    facts. This exception is the first one; ``None`` is now only ever the
    second.
    """


def check_duplicate_asset(
    sha256_hash: str,
    api_base_url: str,
    service_token: str,
    hash_kind: str = "content",
    project_id: Optional[str] = None,
    timeout_seconds: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Find an existing asset with this hash, or ``None`` if there is none.

    ``hash_kind`` names which question is being asked, because the two are not
    interchangeable:

    * ``"content"`` — the SHA-256 of bytes that already exist. Stage 3 and
      Stage 5 dedup on this *after* generating, so it saves the upload and the
      duplicate row, not the GPU time.
    * ``"params"`` — the caller's idempotency key over prompt, parameters and
      input digests. Video and animation dedup on this *before* generating,
      which is the case where a repeat run costs seconds instead of minutes.

    Raises ``DuplicateCheckError`` when the probe cannot be answered. Callers
    decide whether to fail open; they no longer have that decision made for
    them by an ``except Exception: return None``.
    """
    import httpx

    param = {
        "content": "content_hash",
        "params": "generation_params_hash",
        "any": "sha256",
    }.get(hash_kind)
    if param is None:
        raise ValueError(
            f"hash_kind must be one of content|params|any; got {hash_kind!r}"
        )

    params: Dict[str, Any] = {param: sha256_hash}
    if project_id:
        params["project_id"] = project_id

    try:
        with httpx.Client(
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {service_token}"},
        ) as client:
            resp = client.get(f"{api_base_url}/assets", params=params)
    except Exception as exc:
        raise DuplicateCheckError(
            f"deduplication probe could not reach {api_base_url}/assets: {exc}"
        ) from exc

    if resp.status_code != 200:
        raise DuplicateCheckError(
            f"deduplication probe to {api_base_url}/assets returned HTTP "
            f"{resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    items = data if isinstance(data, list) else data.get("data", data.get("items", []))
    if not items:
        return None
    return items[0]


def find_duplicate_or_none(
    sha256_hash: str,
    api_base_url: str,
    service_token: str,
    hash_kind: str = "content",
    project_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """``check_duplicate_asset`` with a deliberate, logged fail-open.

    Deduplication is an optimisation: if the probe cannot be answered, the
    right behaviour is to generate the asset anyway. That was also the OLD
    behaviour — the difference is that the decision is now made here, in the
    open, under one greppable event, instead of being the accidental
    consequence of a bare ``except``. The WP-08 ``gpu_reservation_unavailable
    ... fail_open=True`` line is the precedent.
    """
    try:
        return check_duplicate_asset(
            sha256_hash=sha256_hash,
            api_base_url=api_base_url,
            service_token=service_token,
            hash_kind=hash_kind,
            project_id=project_id,
        )
    except DuplicateCheckError as exc:
        logger.error(
            "dedup_check_unavailable",
            hash_kind=hash_kind,
            error=str(exc),
            fail_open=True,
            consequence="asset will be generated and uploaded without a dedup check",
        )
        return None


def asset_storage_path(asset: Optional[Dict[str, Any]]) -> str:
    """The SeaweedFS path off an asset payload.

    ``AssetResponse`` sends ``seaweedfs_path``. Three call sites read
    ``storage_path``, a key the API has never sent, so a dedup hit set the
    result's path to ``""`` and the scene lost its file reference. Reads the
    real field and keeps the old name as a fallback rather than asserting
    either one exists.
    """
    if not asset:
        return ""
    return asset.get("seaweedfs_path") or asset.get("storage_path") or ""
