"""
IVGS v5 — Corruption Detector
=================================

Post-generation FFprobe validation on all video and audio assets per §11.2.

Checks:
    1. Codec identification — must match expected format
    2. Resolution verification — must match expected dimensions
    3. Duration validation — within 10% of expected (configurable)
    4. Frame count validation — frame count matches fps × duration
    5. File truncation detection — last byte sequence check
    6. Stream integrity — at least one valid video/audio stream

SHA-256 checksums are computed and stored; checksums are re-verified
immediately before composition to detect storage corruption (§11.2).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("ivgs.validators.corruption")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class CorruptionSeverity(str, Enum):
    """Severity of detected corruption."""
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class CorruptionCheck:
    """Result of a single corruption check."""
    check_name: str
    passed: bool
    severity: CorruptionSeverity = CorruptionSeverity.NONE
    expected: str = ""
    actual: str = ""
    message: str = ""


@dataclass
class CorruptionValidationResult:
    """Full corruption detection result."""
    is_valid: bool
    file_path: str
    sha256_hash: str = ""
    file_size_bytes: int = 0
    checks: List[CorruptionCheck] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def critical_failures(self) -> List[CorruptionCheck]:
        return [c for c in self.checks if not c.passed and c.severity == CorruptionSeverity.CRITICAL]

    @property
    def warnings(self) -> List[CorruptionCheck]:
        return [c for c in self.checks if not c.passed and c.severity == CorruptionSeverity.WARNING]


# ---------------------------------------------------------------------------
# CorruptionDetector
# ---------------------------------------------------------------------------

class CorruptionDetector:
    """
    FFprobe-based corruption detection for video and audio assets.

    All checks are non-destructive and read-only.
    """

    def __init__(
        self,
        ffprobe_path: str = "ffprobe",
        duration_tolerance: float = 0.10,
        frame_count_tolerance: float = 0.05,
        min_video_bitrate_bps: int = 20_000,
    ):
        self._ffprobe = ffprobe_path
        self._duration_tolerance = duration_tolerance
        self._frame_count_tolerance = frame_count_tolerance
        # Collapse floor, not a quality bar - see the video_bitrate_floor check.
        # 20 kb/s is ~7x below the lowest known-good measurement (153 kb/s draft).
        self._min_video_bitrate_bps = min_video_bitrate_bps

    def _probe_video_bitrate(self, file_path: str) -> Optional[int]:
        """Video-stream bitrate in bps, or None if it cannot be determined.

        Falls back to (file size * 8 / duration) when the stream carries no
        bit_rate tag, which some muxers omit. Returns None rather than 0 on
        failure so the caller skips the check instead of reporting a false
        collapse - a probe failure is not evidence of a bad video.
        """
        try:
            proc = subprocess.run(
                [
                    self._ffprobe, "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=bit_rate",
                    "-show_entries", "format=duration,size",
                    "-of", "default=noprint_wrappers=1:nokey=0",
                    file_path,
                ],
                capture_output=True, text=True, timeout=60, check=False,
            )
            if proc.returncode != 0:
                return None
            fields: Dict[str, str] = {}
            for line in proc.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    fields[k.strip()] = v.strip()

            raw = fields.get("bit_rate", "")
            if raw.isdigit() and int(raw) > 0:
                return int(raw)

            size = float(fields.get("size", 0) or 0)
            duration = float(fields.get("duration", 0) or 0)
            if size > 0 and duration > 0:
                return int(size * 8 / duration)
            return None
        except Exception as e:  # probe failure is not a corruption verdict
            logger.warning("video_bitrate_probe_failed", error=str(e))
            return None

    # ----- Video validation -----

    def validate_video(
        self,
        file_path: str,
        expected_codec: Optional[str] = None,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
        expected_duration: Optional[float] = None,
        expected_fps: Optional[float] = None,
        duration_tolerance: Optional[float] = None,
    ) -> CorruptionValidationResult:
        """
        Validate a video file for corruption.

        Runs all applicable checks based on provided expected values.
        """
        tolerance = duration_tolerance or self._duration_tolerance
        result = CorruptionValidationResult(
            is_valid=True,
            file_path=file_path,
        )

        log = logger.bind(file_path=os.path.basename(file_path))

        # File existence
        if not os.path.exists(file_path):
            result.is_valid = False
            result.errors.append(f"File not found: {file_path}")
            return result

        # File size
        file_size = os.path.getsize(file_path)
        result.file_size_bytes = file_size

        result.checks.append(CorruptionCheck(
            check_name="file_size",
            passed=file_size > 0,
            severity=CorruptionSeverity.CRITICAL if file_size == 0 else CorruptionSeverity.NONE,
            expected="> 0 bytes",
            actual=f"{file_size} bytes",
            message="File is empty" if file_size == 0 else "File size OK",
        ))

        if file_size == 0:
            result.is_valid = False
            return result

        # SHA-256
        result.sha256_hash = self._compute_sha256(file_path)

        # FFprobe analysis
        probe_data = self._probe(file_path)
        if probe_data is None:
            result.is_valid = False
            result.checks.append(CorruptionCheck(
                check_name="ffprobe_parse",
                passed=False,
                severity=CorruptionSeverity.CRITICAL,
                message="FFprobe failed to parse file",
            ))
            return result

        result.metadata = probe_data

        # Extract streams
        video_streams = [
            s for s in probe_data.get("streams", [])
            if s.get("codec_type") == "video"
        ]
        _audio_streams = [  # noqa: F841
            s for s in probe_data.get("streams", [])
            if s.get("codec_type") == "audio"
        ]

        # Check: at least one video stream
        result.checks.append(CorruptionCheck(
            check_name="video_stream_exists",
            passed=len(video_streams) > 0,
            severity=CorruptionSeverity.CRITICAL,
            expected=">= 1 video stream",
            actual=f"{len(video_streams)} video stream(s)",
        ))

        if not video_streams:
            result.is_valid = False
            return result

        vs = video_streams[0]

        # Check: codec
        if expected_codec:
            actual_codec = vs.get("codec_name", "").lower()
            # Normalize codec names
            codec_aliases = {
                "h264": ["h264", "avc"],
                "h265": ["h265", "hevc"],
                "x264": ["h264", "avc"],
                "x265": ["h265", "hevc"],
                "vp9": ["vp9"],
            }
            expected_normalized = expected_codec.lower().replace("lib", "")
            valid_names = codec_aliases.get(expected_normalized, [expected_normalized])
            codec_ok = actual_codec in valid_names

            result.checks.append(CorruptionCheck(
                check_name="video_codec",
                passed=codec_ok,
                severity=CorruptionSeverity.CRITICAL,
                expected=expected_codec,
                actual=actual_codec,
            ))

            if not codec_ok:
                result.is_valid = False

        # Check: resolution
        if expected_width and expected_height:
            actual_w = int(vs.get("width", 0))
            actual_h = int(vs.get("height", 0))
            res_ok = actual_w == expected_width and actual_h == expected_height

            result.checks.append(CorruptionCheck(
                check_name="resolution",
                passed=res_ok,
                severity=CorruptionSeverity.CRITICAL,
                expected=f"{expected_width}×{expected_height}",
                actual=f"{actual_w}×{actual_h}",
            ))

            if not res_ok:
                result.is_valid = False

        # Check: duration
        if expected_duration and expected_duration > 0:
            fmt_duration = float(probe_data.get("format", {}).get("duration", 0))
            duration_diff = abs(fmt_duration - expected_duration) / expected_duration
            duration_ok = duration_diff <= tolerance

            result.checks.append(CorruptionCheck(
                check_name="duration",
                passed=duration_ok,
                severity=CorruptionSeverity.CRITICAL if duration_diff > 0.5 else CorruptionSeverity.WARNING,
                expected=f"{expected_duration:.2f}s (±{tolerance*100:.0f}%)",
                actual=f"{fmt_duration:.2f}s (diff: {duration_diff*100:.1f}%)",
            ))

            if not duration_ok:
                if duration_diff > 0.5:
                    result.is_valid = False

        # Check: frame count
        if expected_fps and expected_duration:
            expected_frames = int(expected_fps * expected_duration)
            actual_frames_str = vs.get("nb_frames", "0")
            actual_frames = int(actual_frames_str) if actual_frames_str.isdigit() else 0

            if actual_frames > 0:
                frame_diff = abs(actual_frames - expected_frames) / max(expected_frames, 1)
                frames_ok = frame_diff <= self._frame_count_tolerance

                result.checks.append(CorruptionCheck(
                    check_name="frame_count",
                    passed=frames_ok,
                    severity=CorruptionSeverity.WARNING,
                    expected=f"{expected_frames} frames",
                    actual=f"{actual_frames} frames (diff: {frame_diff*100:.1f}%)",
                ))

        # Check: truncation (MP4 moov atom)
        truncation_ok = self._check_truncation(file_path)
        result.checks.append(CorruptionCheck(
            check_name="truncation",
            passed=truncation_ok,
            severity=CorruptionSeverity.CRITICAL,
            message="File appears truncated" if not truncation_ok else "No truncation detected",
        ))

        if not truncation_ok:
            result.is_valid = False

        # Check: video bitrate floor (WP-03 / AD-03 S14, ledger P1.4c).
        #
        # This catches COLLAPSE - a black, frozen or near-empty video stream -
        # not low bitrate as such. AD-03 S14 is explicit that the measured
        # 506 kb/s at 1080p is NOT established as a defect: CRF targets quality
        # and lets bitrate fall where content complexity allows, and this
        # material is near-static stills with a 0.25-scale PiP head. The VBV
        # maxrate is a ceiling, not a floor.
        #
        # The floor is therefore set far below every known-good reference
        # measured on 2026-08-15, so it cannot fail them:
        #     720p draft  153 kb/s     1080p final  506 kb/s
        #     4K final    939 kb/s
        # A real collapse lands one to two orders of magnitude below these.
        # Severity WARNING, not CRITICAL: it must not fail a render on its own
        # until it has a track record. Raise the floor once it has one.
        video_bitrate = self._probe_video_bitrate(file_path)
        if video_bitrate is not None:
            bitrate_ok = video_bitrate >= self._min_video_bitrate_bps
            result.checks.append(CorruptionCheck(
                check_name="video_bitrate_floor",
                passed=bitrate_ok,
                severity=CorruptionSeverity.WARNING,
                expected=f"at least {self._min_video_bitrate_bps} bps",
                actual=f"{video_bitrate} bps",
                message=(
                    "Video bitrate collapsed - check for a black or frozen stream"
                    if not bitrate_ok else "Video bitrate above the collapse floor"
                ),
            ))

        log.info(
            "corruption_validation_complete",
            is_valid=result.is_valid,
            checks_passed=sum(1 for c in result.checks if c.passed),
            checks_total=len(result.checks),
        )

        return result

    # ----- Audio validation -----

    def validate_audio(
        self,
        file_path: str,
        expected_codec: Optional[str] = None,
        expected_sample_rate: Optional[int] = None,
        expected_channels: Optional[int] = None,
        expected_duration: Optional[float] = None,
    ) -> CorruptionValidationResult:
        """Validate an audio file for corruption."""
        result = CorruptionValidationResult(
            is_valid=True,
            file_path=file_path,
        )

        if not os.path.exists(file_path):
            result.is_valid = False
            result.errors.append(f"File not found: {file_path}")
            return result

        file_size = os.path.getsize(file_path)
        result.file_size_bytes = file_size
        result.sha256_hash = self._compute_sha256(file_path)

        if file_size == 0:
            result.is_valid = False
            result.checks.append(CorruptionCheck(
                check_name="file_size",
                passed=False,
                severity=CorruptionSeverity.CRITICAL,
                message="Audio file is empty",
            ))
            return result

        probe_data = self._probe(file_path)
        if probe_data is None:
            result.is_valid = False
            result.checks.append(CorruptionCheck(
                check_name="ffprobe_parse",
                passed=False,
                severity=CorruptionSeverity.CRITICAL,
                message="FFprobe failed to parse audio file",
            ))
            return result

        result.metadata = probe_data

        audio_streams = [
            s for s in probe_data.get("streams", [])
            if s.get("codec_type") == "audio"
        ]

        result.checks.append(CorruptionCheck(
            check_name="audio_stream_exists",
            passed=len(audio_streams) > 0,
            severity=CorruptionSeverity.CRITICAL,
            expected=">= 1 audio stream",
            actual=f"{len(audio_streams)} audio stream(s)",
        ))

        if not audio_streams:
            result.is_valid = False
            return result

        astream = audio_streams[0]

        if expected_codec:
            actual_codec = astream.get("codec_name", "").lower()
            codec_ok = actual_codec == expected_codec.lower()
            result.checks.append(CorruptionCheck(
                check_name="audio_codec",
                passed=codec_ok,
                severity=CorruptionSeverity.WARNING,
                expected=expected_codec,
                actual=actual_codec,
            ))

        if expected_sample_rate:
            actual_sr = int(astream.get("sample_rate", 0))
            sr_ok = actual_sr == expected_sample_rate
            result.checks.append(CorruptionCheck(
                check_name="sample_rate",
                passed=sr_ok,
                severity=CorruptionSeverity.WARNING,
                expected=f"{expected_sample_rate} Hz",
                actual=f"{actual_sr} Hz",
            ))

        if expected_channels:
            actual_ch = int(astream.get("channels", 0))
            ch_ok = actual_ch == expected_channels
            result.checks.append(CorruptionCheck(
                check_name="channels",
                passed=ch_ok,
                severity=CorruptionSeverity.WARNING,
                expected=f"{expected_channels}",
                actual=f"{actual_ch}",
            ))

        if expected_duration and expected_duration > 0:
            fmt_duration = float(probe_data.get("format", {}).get("duration", 0))
            diff = abs(fmt_duration - expected_duration) / expected_duration
            dur_ok = diff <= self._duration_tolerance
            result.checks.append(CorruptionCheck(
                check_name="duration",
                passed=dur_ok,
                severity=CorruptionSeverity.WARNING,
                expected=f"{expected_duration:.2f}s",
                actual=f"{fmt_duration:.2f}s",
            ))

        return result

    # ----- Checksum verification -----

    def verify_checksum(
        self,
        file_path: str,
        expected_sha256: str,
    ) -> CorruptionCheck:
        """Verify SHA-256 checksum of a file."""
        actual = self._compute_sha256(file_path)
        passed = actual == expected_sha256

        return CorruptionCheck(
            check_name="sha256_checksum",
            passed=passed,
            severity=CorruptionSeverity.CRITICAL if not passed else CorruptionSeverity.NONE,
            expected=expected_sha256[:16] + "...",
            actual=actual[:16] + "...",
            message="Checksum mismatch — possible storage corruption" if not passed else "Checksum OK",
        )

    # ----- Internal helpers -----

    def _probe(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Run ffprobe and return parsed JSON."""
        cmd = [
            self._ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning("ffprobe_failed", file=file_path, error=str(e))
        return None

    def _compute_sha256(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _check_truncation(self, file_path: str) -> bool:
        """
        Check for file truncation by verifying MP4 container integrity.

        For MP4 files: checks for presence of moov atom.
        For other formats: checks last bytes are not all zeros.
        """
        try:
            file_size = os.path.getsize(file_path)
            if file_size < 8:
                return False

            with open(file_path, "rb") as f:
                # Check for MP4 ftyp header
                header = f.read(8)
                is_mp4 = b"ftyp" in header

                if is_mp4:
                    # Scan for moov atom
                    f.seek(0)
                    content = f.read()
                    if b"moov" not in content:
                        return False  # Missing moov = truncated

                # Check last 64 bytes aren't all zeros
                f.seek(max(0, file_size - 64))
                tail = f.read(64)
                if tail == b"\x00" * len(tail):
                    return False  # All zeros at end = likely truncated

            return True

        except Exception as e:
            logger.warning("truncation_check_failed", error=str(e))
            return False
