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
- Audio track: present with correct codec/sample rate (when one is expected)
- Corruption: ffprobe validation, frame count consistency
- Frame distinctness: the clip actually moves
- File size: within bounds

Uses subprocess calls to ffprobe/ffmpeg for metadata extraction and decoding.

WP-44 — video assets get a validator that runs
-----------------------------------------------

This class existed before WP-44 and was never called. The one construction of
it in the whole repository was::

    # 4. Validate
    _validator = VideoValidator()  # noqa: F841

— built, lint-silenced, discarded. The first e2e run's two video assets
therefore carry ``quality_decision: ""`` and ``quality_score: 0.0``: not a bad
score, no score. WP-44 wires it into ``video_generation_task`` and
``animation_generation_task``, and brings it up to the honesty contract the
image validator now holds:

* **A check that cannot run reports itself MISSING**, never passed.
  ``checks_missing`` names them; ``check_coverage`` says how much of the
  scoring weight was exercised; ``quality_score_complete`` is the flag.
* **A missing check removes its weight from the numerator *and* the
  denominator**, so no un-run check can be absorbed as a pass. This is the
  ``+0.15 default pass if CLIP unavailable`` defect (swallow register instance
  24), refused in advance on the video side.
* **Missing checks cap the decision at ``flagged``.** A gate may not certify
  what it did not measure.

* **Frame distinctness is a real measurement.** It is the WP-46 addendum's
  method promoted from a one-off proof into a standing check: decode frames to
  greyscale, compare them pairwise, and report how many are distinct and how
  many consecutive pairs are identical. That addendum measured the first real
  Wan2.2-Animate render at *77 distinct frames of 77, zero identical
  consecutive pairs* — which is what told us it was an animation rather than a
  still. A generated clip whose frames are all identical IS a still, and this
  check is what refuses it.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    #: Below this fraction of distinct frames the clip is barely moving and is
    #: flagged for review. At 0.0 distinct movement (every frame identical to
    #: its neighbour) it is rejected outright — that is a still in an MP4.
    distinct_frame_ratio_flagged: float = 0.50
    #: Frames decoded for the distinctness measurement. Capped so a 30-minute
    #: final render does not decode 54,000 frames inside a Celery task.
    distinctness_max_frames: int = 120
    #: Frames are decoded to greyscale at this working resolution before being
    #: compared. Fixed, so the diff numbers are comparable between assets.
    distinctness_working_size: int = 128


#: Scoring weights. A check that does not run is removed from BOTH numerator
#: and denominator — see ``_compute_quality_score``.
CHECK_WEIGHTS: Dict[str, float] = {
    "corruption_ok": 0.25,
    "codec_ok": 0.10,
    "resolution_ok": 0.15,
    "fps_ok": 0.10,
    "duration_ok": 0.10,
    "audio_ok": 0.10,
    "file_size_ok": 0.05,
    "distinctness_ok": 0.15,
}


@dataclass
class VideoValidationResult:
    """Comprehensive video validation result.

    ``quality_score`` is normalised over the checks that ACTUALLY RAN. Read it
    with ``checks_missing`` / ``check_coverage``: a 1.0 over three checks is
    not the claim a 1.0 over eight checks is, and ``quality_score_complete``
    is what separates them.
    """
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
    distinctness_ok: bool = False
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
    #: The distinctness measurement itself, or None when it could not run.
    distinctness: Optional[Dict[str, Any]] = None
    checks_run: List[str] = field(default_factory=list)
    checks_missing: List[str] = field(default_factory=list)
    check_coverage: float = 0.0
    quality_score_complete: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def scoring_details(self) -> Dict[str, Any]:
        """The record that goes to the Quality Scores API."""
        return {
            "codec_ok": self.codec_ok,
            "resolution_ok": self.resolution_ok,
            "fps_ok": self.fps_ok,
            "duration_ok": self.duration_ok,
            "audio_ok": self.audio_ok,
            "corruption_ok": self.corruption_ok,
            "file_size_ok": self.file_size_ok,
            "distinctness_ok": self.distinctness_ok,
            "distinctness": self.distinctness,
            "checks_run": list(self.checks_run),
            "checks_missing": list(self.checks_missing),
            "check_coverage": self.check_coverage,
            "quality_score_complete": self.quality_score_complete,
            "actual_width": self.actual_width,
            "actual_height": self.actual_height,
            "actual_fps": self.actual_fps,
            "actual_duration_seconds": self.actual_duration_seconds,
            "actual_video_codec": self.actual_video_codec,
            "actual_audio_codec": self.actual_audio_codec,
            "frame_count": self.frame_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Video Validator
# ---------------------------------------------------------------------------

class VideoValidator:
    """Validates generated video files using ffprobe and ffmpeg."""

    def __init__(
        self,
        thresholds: Optional[VideoQualityThresholds] = None,
        ffprobe_path: str = "ffprobe",
        ffmpeg_path: str = "ffmpeg",
    ):
        self._thresholds = thresholds or VideoQualityThresholds()
        self._ffprobe_path = ffprobe_path
        self._ffmpeg_path = ffmpeg_path

    # -- public API ---------------------------------------------------------

    def validate_file(
        self,
        file_path: str,
        expected_duration: Optional[float] = None,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
        expect_audio: bool = True,
        check_distinctness: bool = True,
    ) -> VideoValidationResult:
        """
        Validate a video file on disk using ffprobe/ffmpeg.

        Parameters
        ----------
        file_path : str
            Path to the video file.
        expected_duration : float, optional
            Scene duration the storyboard asked for. Absent, the duration
            *range* is still checked but the vs-expected comparison reports
            itself missing rather than passing by default.
        expected_width, expected_height : int, optional
            Expected geometry (overrides the threshold defaults).
        expect_audio : bool
            False for silent generated clips — CogVideoX and Wan2.2-Animate
            both emit video-only MP4s, and "no audio stream" is their normal
            output, not a defect. When False, the audio check is not run and
            is recorded as such rather than warned about on every asset.
        check_distinctness : bool
            Run the frame-distinctness measurement. Decoding costs real time on
            long assets; the caller decides.
        """
        errors: List[str] = []
        warnings: List[str] = []
        checks: Dict[str, bool] = {}
        missing: List[str] = []
        metadata: Dict[str, Any] = {}

        exp_w = expected_width or self._thresholds.expected_width
        exp_h = expected_height or self._thresholds.expected_height

        # --- File size and hash ---
        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, "rb") as f:
                sha256_hash = hashlib.sha256(f.read()).hexdigest()
        except (OSError, IOError) as e:
            # Nothing at all could be measured. Every check is MISSING except
            # the one that just failed.
            return self._terminal(
                errors=[f"Cannot read file: {e}"],
                missing=[k for k in CHECK_WEIGHTS if k != "corruption_ok"],
                checks={"corruption_ok": False},
            )

        file_size_ok = (
            self._thresholds.min_file_size_bytes
            <= file_size
            <= self._thresholds.max_file_size_bytes
        )
        checks["file_size_ok"] = file_size_ok
        if not file_size_ok:
            errors.append(f"File size out of range: {file_size} bytes")

        # --- FFprobe analysis ---
        probe_data = self._run_ffprobe(file_path)
        if not probe_data:
            errors.append("FFprobe analysis failed: possibly corrupt file")
            return self._terminal(
                errors=errors,
                missing=[
                    k for k in CHECK_WEIGHTS
                    if k not in ("corruption_ok", "file_size_ok")
                ],
                checks={"corruption_ok": False, "file_size_ok": file_size_ok},
                file_size=file_size,
                sha256_hash=sha256_hash,
            )

        checks["corruption_ok"] = True
        metadata["ffprobe_format"] = probe_data.get("format", {}).get("format_name", "")

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
            return self._terminal(
                errors=errors,
                missing=[
                    k for k in CHECK_WEIGHTS
                    if k not in ("corruption_ok", "file_size_ok")
                ],
                checks={"corruption_ok": False, "file_size_ok": file_size_ok},
                file_size=file_size,
                sha256_hash=sha256_hash,
            )

        # --- Video codec ---
        video_codec = video_stream.get("codec_name", "").lower()
        codec_ok = video_codec in self._thresholds.allowed_video_codecs
        checks["codec_ok"] = codec_ok
        if not codec_ok:
            errors.append(
                f"Unsupported video codec: {video_codec} "
                f"(allowed: {', '.join(self._thresholds.allowed_video_codecs)})"
            )

        # --- Resolution ---
        actual_width = int(video_stream.get("width", 0))
        actual_height = int(video_stream.get("height", 0))
        if actual_width > 0 and actual_height > 0:
            resolution_ok = actual_width == exp_w and actual_height == exp_h
            checks["resolution_ok"] = resolution_ok
            if not resolution_ok:
                warnings.append(
                    f"Resolution mismatch: expected {exp_w}×{exp_h}, "
                    f"got {actual_width}×{actual_height}"
                )
        else:
            missing.append("resolution_ok")
            errors.append("Cannot determine video resolution")

        # --- Frame rate ---
        fps_str = video_stream.get("r_frame_rate", "0/1")
        actual_fps = self._parse_fps(fps_str)
        if actual_fps > 0:
            fps_ok = any(
                abs(actual_fps - target) <= self._thresholds.fps_tolerance
                for target in self._thresholds.allowed_fps
            )
            checks["fps_ok"] = fps_ok
            if not fps_ok:
                warnings.append(
                    f"Unexpected frame rate: {actual_fps:.1f}fps "
                    f"(expected: {', '.join(str(f) for f in self._thresholds.allowed_fps)})"
                )
        else:
            missing.append("fps_ok")
            warnings.append(
                "CHECK MISSING — frame rate could not be determined from the "
                f"container (r_frame_rate={fps_str!r})."
            )

        # --- Duration ---
        duration_str = format_info.get("duration", video_stream.get("duration", "0"))
        try:
            actual_duration = float(duration_str) if duration_str else 0.0
        except (TypeError, ValueError):
            actual_duration = 0.0

        if actual_duration > 0:
            in_range = (
                self._thresholds.min_duration_seconds
                <= actual_duration
                <= self._thresholds.max_duration_seconds
            )
            if not in_range:
                errors.append(f"Duration out of range: {actual_duration:.2f}s")

            # Duration vs what the storyboard asked for. Without an expected
            # value there is nothing to compare against, and saying so beats
            # scoring the asset as if it matched.
            if expected_duration:
                tolerance = expected_duration * self._thresholds.duration_tolerance_pct
                deviation = abs(actual_duration - expected_duration)
                within = deviation <= tolerance
                checks["duration_ok"] = in_range and within
                metadata["duration_expected_s"] = round(expected_duration, 3)
                metadata["duration_deviation_s"] = round(deviation, 3)
                metadata["duration_deviation_pct"] = round(
                    100.0 * deviation / expected_duration, 2
                )
                if not within:
                    warnings.append(
                        f"Duration deviation: expected {expected_duration:.2f}s, "
                        f"got {actual_duration:.2f}s "
                        f"(tolerance ±{tolerance:.2f}s)"
                    )
            else:
                checks["duration_ok"] = in_range
                missing.append("duration_vs_expected")
                warnings.append(
                    "CHECK MISSING — duration was not compared against an "
                    "expected value: none was supplied for this asset. Only "
                    "the absolute range was checked."
                )
        else:
            missing.append("duration_ok")
            errors.append("Duration could not be determined")

        # --- Frame count consistency (informational) ---
        try:
            frame_count = int(video_stream.get("nb_frames", 0) or 0)
        except (TypeError, ValueError):
            frame_count = 0
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
        actual_audio_codec = ""
        if not expect_audio:
            # Silent by design. Not run, not passed, and not warned about.
            missing.append("audio_ok")
            metadata["audio_expected"] = False
        elif audio_stream:
            actual_audio_codec = audio_stream.get("codec_name", "").lower()
            audio_ok = actual_audio_codec in self._thresholds.allowed_audio_codecs
            checks["audio_ok"] = audio_ok
            if not audio_ok:
                warnings.append(f"Unexpected audio codec: {actual_audio_codec}")
        else:
            checks["audio_ok"] = False
            warnings.append("No audio stream found in video")

        # --- Bitrate (informational) ---
        bitrate_str = format_info.get("bit_rate", "0")
        try:
            actual_bitrate_kbps = int(float(bitrate_str)) // 1000 if bitrate_str else 0
        except (TypeError, ValueError):
            actual_bitrate_kbps = 0
        if actual_bitrate_kbps > 0:
            if actual_bitrate_kbps < self._thresholds.min_bitrate_kbps:
                warnings.append(f"Low bitrate: {actual_bitrate_kbps}kbps")
            elif actual_bitrate_kbps > self._thresholds.max_bitrate_kbps:
                warnings.append(f"High bitrate: {actual_bitrate_kbps}kbps")

        # --- Frame distinctness (the WP-46 addendum measurement) ---
        distinctness: Optional[Dict[str, Any]] = None
        if check_distinctness:
            distinctness, reason = self.measure_frame_distinctness(file_path)
            if distinctness is None:
                missing.append("distinctness_ok")
                warnings.append(
                    f"CHECK MISSING — frame distinctness did not run: {reason}. "
                    f"Whether this clip moves has NOT been established."
                )
            else:
                metadata["distinctness"] = distinctness
                n = distinctness["frames_decoded"]
                ratio = distinctness["distinct_frame_ratio"]
                if distinctness["identical_consecutive_pairs"] == max(n - 1, 0) and n >= 2:
                    checks["distinctness_ok"] = False
                    errors.append(
                        f"Video does not move: all {n} decoded frames are "
                        f"identical to their neighbour. This is a still in an "
                        f"MP4 container, not a clip."
                    )
                elif ratio < self._thresholds.distinct_frame_ratio_flagged:
                    checks["distinctness_ok"] = False
                    warnings.append(
                        f"Low frame distinctness: {distinctness['distinct_frames']} "
                        f"of {n} decoded frames are distinct "
                        f"({ratio:.2f} < {self._thresholds.distinct_frame_ratio_flagged})"
                    )
                else:
                    checks["distinctness_ok"] = True
        else:
            missing.append("distinctness_ok")
            metadata["distinctness_requested"] = False

        # --- Quality score over the checks that ran ---
        quality_score, coverage = self._compute_quality_score(checks, missing)
        metadata["check_coverage"] = coverage
        metadata["checks_missing"] = sorted(set(missing))

        # --- Decision ---
        # Missing checks cap the decision at FLAGGED: a gate does not certify
        # what it did not measure.
        if errors:
            decision = VideoQualityDecision.REJECTED
        elif missing or warnings:
            decision = VideoQualityDecision.FLAGGED
        else:
            decision = VideoQualityDecision.APPROVED

        return VideoValidationResult(
            is_valid=decision != VideoQualityDecision.REJECTED,
            decision=decision,
            quality_score=quality_score,
            codec_ok=checks.get("codec_ok", False),
            resolution_ok=checks.get("resolution_ok", False),
            fps_ok=checks.get("fps_ok", False),
            duration_ok=checks.get("duration_ok", False),
            audio_ok=checks.get("audio_ok", False),
            corruption_ok=checks.get("corruption_ok", False),
            file_size_ok=file_size_ok,
            distinctness_ok=checks.get("distinctness_ok", False),
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
            distinctness=distinctness,
            checks_run=sorted(checks.keys()),
            checks_missing=sorted(set(missing)),
            check_coverage=coverage,
            quality_score_complete=not missing,
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
        expect_audio: bool = True,
        check_distinctness: bool = True,
    ) -> VideoValidationResult:
        """Validate video from bytes by writing to a temp file."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_data)
            tmp_path = tmp.name

        try:
            result = self.validate_file(
                tmp_path,
                expected_duration=expected_duration,
                expected_width=expected_width,
                expected_height=expected_height,
                expect_audio=expect_audio,
                check_distinctness=check_distinctness,
            )
            result.sha256_hash = hashlib.sha256(video_data).hexdigest()
            result.file_size_bytes = len(video_data)
            return result
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # -- frame distinctness -------------------------------------------------

    def measure_frame_distinctness(
        self, file_path: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Decode frames to greyscale and compare them pairwise.

        This is the WP-46 addendum's method, promoted to a standing check. That
        addendum decoded the first real Wan2.2-Animate render's 77 frames and
        found *77 distinct, zero identical consecutive pairs* — the measurement
        that established the output was an animation rather than a still.

        Returns ``(measurement, "")`` on success, or ``(None, reason)`` when
        the check could not run. It NEVER returns a synthesised measurement:
        a decode failure is a missing check, not a passing one.

        Frames are decoded at a fixed working resolution
        (``distinctness_working_size``) so the diff magnitudes below are
        comparable between assets of different geometry. ``frames_decoded`` is
        capped at ``distinctness_max_frames``; when the cap bites,
        ``frames_capped`` says so rather than letting the numbers imply full
        coverage.
        """
        try:
            import numpy as np
        except ImportError as exc:
            return None, f"numpy is unavailable ({exc})"

        size = self._thresholds.distinctness_working_size
        max_frames = self._thresholds.distinctness_max_frames

        cmd = [
            self._ffmpeg_path,
            "-v", "error",
            "-i", file_path,
            "-vf", f"scale={size}:{size},format=gray",
            "-frames:v", str(max_frames),
            "-f", "rawvideo",
            "-",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=180)
        except FileNotFoundError:
            return None, f"ffmpeg not found at {self._ffmpeg_path!r}"
        except subprocess.TimeoutExpired:
            return None, "ffmpeg decode timed out after 180s"

        if proc.returncode != 0:
            return None, (
                f"ffmpeg exited {proc.returncode}: "
                f"{proc.stderr.decode('utf-8', 'replace')[:200]}"
            )

        frame_bytes = size * size
        raw = proc.stdout
        n = len(raw) // frame_bytes
        if n < 2:
            return None, (
                f"only {n} frame(s) decoded at {size}×{size}; "
                f"distinctness needs at least 2"
            )

        frames = np.frombuffer(
            raw[: n * frame_bytes], dtype=np.uint8
        ).reshape(n, size, size).astype(np.int16)

        # Distinct = unique frame content, by exact bytes (the addendum's
        # "distinct frames" count).
        distinct = len({raw[i * frame_bytes:(i + 1) * frame_bytes] for i in range(n)})

        diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
        identical_pairs = int((diffs == 0).sum())
        first_vs_last = float(np.abs(frames[0] - frames[-1]).mean())

        return {
            "method": "greyscale_pairwise_abs_diff",
            "working_resolution": [size, size],
            "frames_decoded": n,
            "frames_capped": n >= max_frames,
            "distinct_frames": distinct,
            "distinct_frame_ratio": round(distinct / n, 4),
            "identical_consecutive_pairs": identical_pairs,
            "consecutive_pairs": n - 1,
            "consecutive_abs_diff_min": round(float(diffs.min()), 4),
            "consecutive_abs_diff_mean": round(float(diffs.mean()), 4),
            "consecutive_abs_diff_max": round(float(diffs.max()), 4),
            "first_vs_last_abs_diff": round(first_vs_last, 4),
            "scale": "0-255 greyscale",
        }, ""

    # -- internals ----------------------------------------------------------

    def _terminal(
        self,
        errors: List[str],
        missing: List[str],
        checks: Dict[str, bool],
        file_size: int = 0,
        sha256_hash: str = "",
    ) -> VideoValidationResult:
        """A rejection where most checks never got the chance to run.

        The un-run checks are named as MISSING rather than defaulting to False,
        so the record distinguishes "this failed" from "this was never tried".
        """
        quality_score, coverage = self._compute_quality_score(checks, missing)
        return VideoValidationResult(
            is_valid=False,
            decision=VideoQualityDecision.REJECTED,
            quality_score=quality_score,
            corruption_ok=checks.get("corruption_ok", False),
            file_size_ok=checks.get("file_size_ok", False),
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            checks_run=sorted(checks.keys()),
            checks_missing=sorted(set(missing)),
            check_coverage=coverage,
            quality_score_complete=False,
            errors=errors,
        )

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
        checks: Dict[str, bool], missing: List[str]
    ) -> Tuple[float, float]:
        """Weighted quality score over the checks that ACTUALLY RAN.

        Returns ``(quality_score, check_coverage)``. A missing check is removed
        from numerator and denominator alike, so it can neither award nor
        withhold credit; ``check_coverage`` is the fraction of total scoring
        weight that was exercised.
        """
        missing_set = set(missing)
        total_weight = sum(CHECK_WEIGHTS.values())

        ran_weight = 0.0
        earned = 0.0
        for name, weight in CHECK_WEIGHTS.items():
            if name in missing_set or name not in checks:
                continue
            ran_weight += weight
            if checks[name]:
                earned += weight

        if ran_weight <= 0.0:
            return 0.0, 0.0
        return round(earned / ran_weight, 4), round(ran_weight / total_weight, 4)
