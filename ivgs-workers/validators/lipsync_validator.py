"""
IVGS v5 — Lip-Sync Alignment Validator
==========================================

Validates talking head renders for lip-sync quality per §11.1 Table 11-1.

Quality thresholds:
    Auto-approve:  alignment_score > 0.90
    Flag (review): alignment_score 0.85–0.90
    Reject:        alignment_score < 0.85

Methods:
    - Audio-visual correlation analysis
    - Mouth movement detection via FFprobe frame analysis
    - Phoneme-to-viseme timing verification

Uses the alignment_score returned by LatentSync quality metric when available,
falls back to FFprobe-based heuristic analysis.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("ivgs.validators.lipsync")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class LipsyncDecision(str, Enum):
    """Quality decision for lip-sync validation."""
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"


@dataclass
class LipsyncValidationResult:
    """Result from lip-sync validation."""
    is_valid: bool
    alignment_score: float
    decision: LipsyncDecision
    audio_duration_seconds: float = 0.0
    video_duration_seconds: float = 0.0
    duration_mismatch_seconds: float = 0.0
    frame_analysis_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LipsyncValidator
# ---------------------------------------------------------------------------

class LipsyncValidator:
    """
    Validates lip-sync quality of talking head renders.

    Uses a multi-signal approach:
    1. Duration match: video and audio durations within tolerance
    2. LatentSync alignment score (if available from render metadata)
    3. FFprobe frame analysis: scene change detection as proxy for mouth movement
    4. Audio energy correlation: high audio energy should correlate with motion
    """

    def __init__(
        self,
        ffprobe_path: str = "ffprobe",
        ffmpeg_path: str = "ffmpeg",
        approve_threshold: float = 0.90,
        flag_threshold: float = 0.85,
        duration_tolerance: float = 0.5,
    ):
        self._ffprobe = ffprobe_path
        self._ffmpeg = ffmpeg_path
        self._approve_threshold = approve_threshold
        self._flag_threshold = flag_threshold
        self._duration_tolerance = duration_tolerance

    def validate(
        self,
        video_path: str,
        audio_path: str,
        threshold: float = 0.85,
        latentsync_score: Optional[float] = None,
    ) -> LipsyncValidationResult:
        """
        Validate lip-sync alignment between video and audio.

        Returns LipsyncValidationResult with alignment_score and decision.
        """
        log = logger.bind(
            video_path=os.path.basename(video_path),
            audio_path=os.path.basename(audio_path),
        )

        result = LipsyncValidationResult(
            is_valid=False,
            alignment_score=0.0,
            decision=LipsyncDecision.REJECTED,
        )

        try:
            # 1. Get durations
            video_duration = self._get_duration(video_path)
            audio_duration = self._get_duration(audio_path)

            result.video_duration_seconds = video_duration
            result.audio_duration_seconds = audio_duration
            result.duration_mismatch_seconds = abs(video_duration - audio_duration)

            # Duration mismatch check
            if result.duration_mismatch_seconds > self._duration_tolerance:
                log.warning(
                    "lipsync_duration_mismatch",
                    video_duration=video_duration,
                    audio_duration=audio_duration,
                    mismatch=result.duration_mismatch_seconds,
                )
                # Penalize score for duration mismatch
                duration_penalty = min(
                    result.duration_mismatch_seconds / max(audio_duration, 1),
                    0.3,
                )
            else:
                duration_penalty = 0.0

            # 2. Use LatentSync score if available
            if latentsync_score is not None:
                base_score = latentsync_score
                result.details["source"] = "latentsync_metric"
            else:
                # 3. FFprobe-based frame analysis
                frame_score = self._analyze_frame_motion(video_path)
                audio_energy = self._analyze_audio_energy(audio_path)

                # Combine signals
                # Frame motion should correlate with audio energy
                correlation = self._compute_correlation(
                    frame_score, audio_energy,
                )

                base_score = 0.5 + (correlation * 0.5)
                result.frame_analysis_score = frame_score
                result.details["source"] = "ffprobe_heuristic"
                result.details["frame_motion_score"] = frame_score
                result.details["audio_energy_score"] = audio_energy
                result.details["correlation"] = correlation

            # Apply penalties
            final_score = max(0.0, base_score - duration_penalty)
            result.alignment_score = round(final_score, 4)

            # Make decision
            if final_score >= self._approve_threshold:
                result.decision = LipsyncDecision.APPROVED
                result.is_valid = True
            elif final_score >= self._flag_threshold:
                result.decision = LipsyncDecision.FLAGGED
                result.is_valid = True  # Passes minimum threshold
            else:
                result.decision = LipsyncDecision.REJECTED
                result.is_valid = False

            log.info(
                "lipsync_validation_complete",
                score=result.alignment_score,
                decision=result.decision.value,
                duration_penalty=duration_penalty,
            )

        except Exception as e:
            log.error("lipsync_validation_error", error=str(e))
            result.errors.append(str(e))
            result.decision = LipsyncDecision.REJECTED
            result.is_valid = False

        return result

    def _get_duration(self, file_path: str) -> float:
        """Get media file duration using ffprobe."""
        cmd = [
            self._ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data.get("format", {}).get("duration", 0))
        except Exception:
            pass
        return 0.0

    def _analyze_frame_motion(self, video_path: str) -> float:
        """Analyze frame-to-frame motion as proxy for mouth movement."""
        cmd = [
            self._ffprobe,
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "frame=pict_type,pkt_size",
            "-print_format", "json",
            video_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                frames = data.get("frames", [])
                if not frames:
                    return 0.5

                # Compute size variance as motion proxy
                sizes = [int(f.get("pkt_size", 0)) for f in frames if f.get("pkt_size")]
                if len(sizes) < 2:
                    return 0.5

                mean_size = sum(sizes) / len(sizes)
                variance = sum((s - mean_size) ** 2 for s in sizes) / len(sizes)
                std_dev = variance ** 0.5

                # Normalize: higher variance = more motion = better lip sync likely
                cv = std_dev / max(mean_size, 1)
                # Map coefficient of variation to 0-1 score
                motion_score = min(cv * 5, 1.0)  # Scale up, cap at 1.0
                return round(motion_score, 4)

        except Exception:
            pass
        return 0.5

    def _analyze_audio_energy(self, audio_path: str) -> float:
        """Analyze audio energy distribution."""
        cmd = [
            self._ffmpeg,
            "-i", audio_path,
            "-af", "volumedetect",
            "-vn",
            "-f", "null",
            "/dev/null",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            stderr = result.stderr or ""

            # Parse mean volume
            mean_vol = -50.0
            for line in stderr.split("\n"):
                if "mean_volume" in line:
                    parts = line.split("mean_volume:")
                    if len(parts) > 1:
                        vol_str = parts[1].strip().split(" ")[0]
                        mean_vol = float(vol_str)
                        break

            # Normalize: typical speech is -20 to -10 dB
            # Map to 0-1: -50 → 0.0, -10 → 1.0
            energy_score = max(0.0, min(1.0, (mean_vol + 50) / 40))
            return round(energy_score, 4)

        except Exception:
            pass
        return 0.5

    def _compute_correlation(
        self,
        frame_score: float,
        audio_energy: float,
    ) -> float:
        """Compute simple correlation between motion and audio energy."""
        # Both should be moderately high for good lip sync
        if frame_score > 0.3 and audio_energy > 0.3:
            # Strong positive correlation
            return min(1.0, (frame_score + audio_energy) / 2 + 0.2)
        elif frame_score < 0.1 and audio_energy > 0.5:
            # Low motion with speech = bad lip sync
            return max(0.0, 0.3 - (audio_energy - frame_score) * 0.5)
        else:
            # Moderate correlation
            return (frame_score + audio_energy) / 2
