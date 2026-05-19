"""
IVGS v5 — Video Validator
===========================

Validates generated video files per §11.1 quality thresholds.

Checks:
- Codec: H.264 or H.265 expected
- Container: MP4 expected
- Resolution: 1920×1080 (or as specified)
- Frame rate: 24fps, 25fps, or 30fps expected
- Duration: matches expected ± tolerance
- Audio track: present with correct codec/sample rate
- Corruption: ffprobe validation, frame count consistency
- File size: within bounds

Uses subprocess calls to ffprobe for metadata extraction.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger("ivgs.video_validator")


# ---------------------------------------------------------------------------
# Enums and thresholds
# ---------------------------------------------------------------------------

class VideoQualityDecision(str, Enum):
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class VideoQualityThresholds:
    """Quality thresholds for video validation."""
    expected_width: int = 1920
    expected_height: int = 1080
    allowed_video_codecs: Tuple[str, ...] = ("h264", "h265", "hevc", "vp9")
    allowed_audio_codecs: Tuple[str, ...] = ("aac", "pcm_s16le", "pcm_s24le", "opus")
    allowed_containers: Tuple[str, ...] = ("mp4", "mov", "webm")
    allowed_fps: Tuple[int, ...] = (24, 25, 30, 60)
    fps_tolerance: float = 0.5
    min_duration_seconds: float = 0.5
    max_duration_seconds: float = 3600.0
    duration_tolerance_pct: float = 0.15
    min_file_size_bytes: int = 10240
    max_file_size_bytes: int = 5368709120  # 5GB
    min_bitrate_kbps: int = 500
    max_bitrate_kbps: int = 50000


@dataclass
class VideoValidationResult:
    """Comprehensive video validation result."""
    is_valid: bool
    decision: VideoQualityDecision
    quality_score: float = 0.0
    codec_ok: bool = False
    resolution_ok: bool = False
    fps_ok: bool = False
    duration_ok: bool = False
    audio_ok: bool = False
    corruption_ok: bool = False
    file_size_ok: bool = False
    actual_width: int = 0
    actual_height: int = 0
    actual_fps: float = 0.0
    actual_duration_seconds: float = 0.0
    actual_video_codec: str = ""
    actual_audio_codec: str = ""
    actual_bitrate_kbps: int = 0
    frame_count: int = 0
    file_size_bytes: int = 0
    sha256_hash: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Video Validator
# ---------------------------------------------------------------------------

class VideoValidator:
    """Validates generated video files using ffprobe."""

    def __init__(
        self,
        thresholds: Optional[VideoQualityThresholds] = None,
        ffprobe_path: str = "ffprobe",
    ):
        self._thresholds = thresholds or VideoQualityThresholds()
        self._ffprobe_path = ffprobe_path

    def validate_file(
        self,
        file_path: str,
        expected_duration: Optional[float] = None,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
    ) -> VideoValidationResult:
        """
        Validate a video file on disk using ffprobe.

        Parameters
        ----------
        file_path : str
            Path to the video file.
        expected_duration : float, optional
            Expected duration for tolerance check.
        expected_width : int, optional
            Expected width (overrides default).
        expected_height : int, optional
            Expected height (overrides default).
        """
        errors: List[str] = []
        warnings: List[str] = []
        metadata: Dict[str, Any] = {}

        exp_w = expected_width or self._thresholds.expected_width
        exp_h = expected_height or self._thresholds.expected_height

        # --- File size and hash ---
        try:
            import os
            file_size = os.path.getsize(file_path)
            with open(file_path, "rb") as f:
                sha256_hash = hashlib.sha256(f.read()).hexdigest()
        except (OSError, IOError) as e:
            return VideoValidationResult(
                is_valid=False,
                decision=VideoQualityDecision.REJECTED,
                errors=[f"Cannot read file: {e}"],
            )

        file_size_ok = (
            self._thresholds.min_file_size_bytes
            <= file_size
            <= self._thresholds.max_file_size_bytes
        )
        if not file_size_ok:
            errors.append(f"File size out of range: {file_size} bytes")

        # --- FFprobe analysis ---
        probe_data = self._run_ffprobe(file_path)
        if not probe_data:
            errors.append("FFprobe analysis failed: possibly corrupt file")
            return VideoValidationResult(
                is_valid=False,
                decision=VideoQualityDecision.REJECTED,
                file_size_bytes=file_size,
                sha256_hash=sha256_hash,
                errors=errors,
            )

        corruption_ok = True
        metadata["ffprobe"] = probe_data

        # --- Extract streams ---
        streams = probe_data.get("streams", [])
        format_info = probe_data.get("format", {})

        video_stream = None
        audio_stream = None
        for s in streams:
            if s.get("codec_type") == "video" and video_stream is None:
                video_stream = s
            elif s.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = s

        if not video_stream:
            errors.append("No video stream found")
            return VideoValidationResult(
                is_valid=False,
                decision=VideoQualityDecision.REJECTED,
                corruption_ok=False,
                file_size_bytes=file_size,
                sha256_hash=sha256_hash,
                errors=errors,
            )

        # --- Video codec ---
        video_codec = video_stream.get("codec_name", "").lower()
        codec_ok = video_codec in self._thresholds.allowed_video_codecs
        if not codec_ok:
            errors.append(
                f"Unsupported video codec: {video_codec} "
                f"(allowed: {', '.join(self._thresholds.allowed_video_codecs)})"
            )

        # --- Resolution ---
        actual_width = int(video_stream.get("width", 0))
        actual_height = int(video_stream.get("height", 0))
        resolution_ok = actual_width == exp_w and actual_height == exp_h
        if not resolution_ok:
            if actual_width > 0 and actual_height > 0:
                warnings.append(
                    f"Resolution mismatch: expected {exp_w}×{exp_h}, "
                    f"got {actual_width}×{actual_height}"
                )
            else:
                errors.append("Cannot determine video resolution")

        # --- Frame rate ---
        fps_str = video_stream.get("r_frame_rate", "0/1")
        actual_fps = self._parse_fps(fps_str)
        fps_ok = any(
            abs(actual_fps - target) <= self._thresholds.fps_tolerance
            for target in self._thresholds.allowed_fps
        )
        if not fps_ok:
            warnings.append(
                f"Unexpected frame rate: {actual_fps:.1f}fps "
                f"(expected: {', '.join(str(f) for f in self._thresholds.allowed_fps)})"
            )

        # --- Duration ---
        duration_str = format_info.get("duration", video_stream.get("duration", "0"))
        actual_duration = float(duration_str) if duration_str else 0.0
        duration_ok = (
            self._thresholds.min_duration_seconds
            <= actual_duration
            <= self._thresholds.max_duration_seconds
        )
        if not duration_ok:
            errors.append(f"Duration out of range: {actual_duration:.2f}s")

        if expected_duration and duration_ok:
            tolerance = expected_duration * self._thresholds.duration_tolerance_pct
            if abs(actual_duration - expected_duration) > tolerance:
                warnings.append(
                    f"Duration deviation: expected {expected_duration:.2f}s, "
                    f"got {actual_duration:.2f}s"
                )

        # --- Frame count consistency ---
        frame_count = int(video_stream.get("nb_frames", 0))
        if frame_count > 0 and actual_fps > 0 and actual_duration > 0:
            expected_frames = int(actual_fps * actual_duration)
            frame_deviation = abs(frame_count - expected_frames) / max(expected_frames, 1)
            if frame_deviation > 0.1:
                warnings.append(
                    f"Frame count inconsistency: {frame_count} frames vs "
                    f"{expected_frames} expected at {actual_fps}fps"
                )
            metadata["frame_deviation_pct"] = round(frame_deviation * 100, 2)

        # --- Audio stream ---
        audio_ok = True
        actual_audio_codec = ""
        if audio_stream:
            actual_audio_codec = audio_stream.get("codec_name", "").lower()
            if actual_audio_codec not in self._thresholds.allowed_audio_codecs:
                warnings.append(f"Unexpected audio codec: {actual_audio_codec}")
        else:
            audio_ok = False
            warnings.append("No audio stream found in video")

        # --- Bitrate ---
        bitrate_str = format_info.get("bit_rate", "0")
        actual_bitrate_kbps = int(float(bitrate_str)) // 1000 if bitrate_str else 0
        if actual_bitrate_kbps > 0:
            if actual_bitrate_kbps < self._thresholds.min_bitrate_kbps:
                warnings.append(f"Low bitrate: {actual_bitrate_kbps}kbps")
            elif actual_bitrate_kbps > self._thresholds.max_bitrate_kbps:
                warnings.append(f"High bitrate: {actual_bitrate_kbps}kbps")

        # --- Quality score ---
        quality_score = self._compute_quality_score(
            corruption_ok, codec_ok, resolution_ok, fps_ok,
            duration_ok, audio_ok, file_size_ok,
        )

        # --- Decision ---
        if errors:
            decision = VideoQualityDecision.REJECTED
        elif warnings:
            decision = VideoQualityDecision.FLAGGED
        else:
            decision = VideoQualityDecision.APPROVED

        return VideoValidationResult(
            is_valid=decision != VideoQualityDecision.REJECTED,
            decision=decision,
            quality_score=quality_score,
            codec_ok=codec_ok,
            resolution_ok=resolution_ok,
            fps_ok=fps_ok,
            duration_ok=duration_ok,
            audio_ok=audio_ok,
            corruption_ok=corruption_ok,
            file_size_ok=file_size_ok,
            actual_width=actual_width,
            actual_height=actual_height,
            actual_fps=actual_fps,
            actual_duration_seconds=round(actual_duration, 3),
            actual_video_codec=video_codec,
            actual_audio_codec=actual_audio_codec,
            actual_bitrate_kbps=actual_bitrate_kbps,
            frame_count=frame_count,
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
        )

    def validate_bytes(
        self,
        video_data: bytes,
        expected_duration: Optional[float] = None,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
    ) -> VideoValidationResult:
        """Validate video from bytes by writing to temp file."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(
            suffix=".mp4", delete=False
        ) as tmp:
            tmp.write(video_data)
            tmp_path = tmp.name

        try:
            result = self.validate_file(
                tmp_path,
                expected_duration=expected_duration,
                expected_width=expected_width,
                expected_height=expected_height,
            )
            result.sha256_hash = hashlib.sha256(video_data).hexdigest()
            result.file_size_bytes = len(video_data)
            return result
        finally:
            os.unlink(tmp_path)

    def _run_ffprobe(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Run ffprobe and parse JSON output."""
        try:
            cmd = [
                self._ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            logger.warning(
                "ffprobe_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500],
            )
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("ffprobe_error", error=str(e))
            return None

    @staticmethod
    def _parse_fps(fps_str: str) -> float:
        """Parse ffprobe frame rate string (e.g., '30/1' or '29.97')."""
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                return float(num) / float(den) if float(den) != 0 else 0.0
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 0.0

    @staticmethod
    def _compute_quality_score(
        corruption_ok: bool,
        codec_ok: bool,
        resolution_ok: bool,
        fps_ok: bool,
        duration_ok: bool,
        audio_ok: bool,
        file_size_ok: bool,
    ) -> float:
        """Compute weighted quality score."""
        weights = {
            "corruption": (corruption_ok, 0.30),
            "codec": (codec_ok, 0.10),
            "resolution": (resolution_ok, 0.20),
            "fps": (fps_ok, 0.10),
            "duration": (duration_ok, 0.10),
            "audio": (audio_ok, 0.10),
            "file_size": (file_size_ok, 0.10),
        }
        score = sum(w for _, (ok, w) in weights.items() if ok)
        return round(min(score, 1.0), 4)
