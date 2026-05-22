"""
IVGS v5 — Audio Validator
===========================

Validates generated audio per §11.1 quality thresholds.

Checks:
- Format: WAV required
- Sample rate: 48kHz expected
- Bit depth: 24-bit expected
- Channels: mono (1 channel) expected
- Duration: must match expected ± tolerance
- SNR: > 20 dB (§11.1)
- Clipping: < 1% of samples (§11.1)
- Silence: no extended silent segments (> 3 seconds)
- Corruption: valid WAV header and data

Quality decisions:
- approved: all checks pass
- flagged: marginal scores
- rejected: below thresholds or corrupted
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("ivgs.audio_validator")


# ---------------------------------------------------------------------------
# Enums and thresholds
# ---------------------------------------------------------------------------

class AudioQualityDecision(str, Enum):
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AudioQualityThresholds:
    """Quality thresholds per §11.1."""
    expected_sample_rate: int = 48000
    expected_bit_depth: int = 24
    expected_channels: int = 1
    min_duration_seconds: float = 0.5
    max_duration_seconds: float = 600.0
    duration_tolerance_pct: float = 0.15
    min_snr_db: float = 20.0
    snr_flagged_db: float = 25.0
    max_clipping_pct: float = 1.0
    clipping_flagged_pct: float = 0.5
    max_silence_seconds: float = 3.0
    min_file_size_bytes: int = 1024
    max_file_size_bytes: int = 524288000  # 500MB
    clipping_threshold_ratio: float = 0.99


@dataclass
class AudioValidationResult:
    """Comprehensive audio validation result."""
    is_valid: bool
    decision: AudioQualityDecision
    quality_score: float = 0.0
    format_ok: bool = False
    sample_rate_ok: bool = False
    bit_depth_ok: bool = False
    channels_ok: bool = False
    duration_ok: bool = False
    snr_ok: bool = False
    clipping_ok: bool = False
    silence_ok: bool = True
    corruption_ok: bool = False
    actual_sample_rate: int = 0
    actual_bit_depth: int = 0
    actual_channels: int = 0
    actual_duration_seconds: float = 0.0
    snr_db: Optional[float] = None
    clipping_pct: Optional[float] = None
    max_silence_duration: float = 0.0
    file_size_bytes: int = 0
    sha256_hash: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Audio Validator
# ---------------------------------------------------------------------------

class AudioValidator:
    """Validates generated audio against quality thresholds."""

    def __init__(
        self,
        thresholds: Optional[AudioQualityThresholds] = None,
    ):
        self._thresholds = thresholds or AudioQualityThresholds()

    def validate(
        self,
        audio_data: bytes,
        expected_duration: Optional[float] = None,
    ) -> AudioValidationResult:
        """
        Run all validation checks on audio data.

        Parameters
        ----------
        audio_data : bytes
            Raw WAV audio bytes.
        expected_duration : float, optional
            Expected duration in seconds for tolerance check.
        """
        errors: List[str] = []
        warnings: List[str] = []
        metadata: Dict[str, Any] = {}

        file_size = len(audio_data)
        sha256_hash = hashlib.sha256(audio_data).hexdigest()

        # --- File size ---
        if file_size < self._thresholds.min_file_size_bytes:
            errors.append(f"Audio too small: {file_size} bytes")
        elif file_size > self._thresholds.max_file_size_bytes:
            errors.append(f"Audio too large: {file_size} bytes")

        # --- Parse WAV header ---
        wav_info = self._parse_wav_header(audio_data)
        corruption_ok = wav_info.get("valid", False)
        if not corruption_ok:
            errors.append("Invalid WAV file: corrupt or missing header")
            return AudioValidationResult(
                is_valid=False,
                decision=AudioQualityDecision.REJECTED,
                corruption_ok=False,
                file_size_bytes=file_size,
                sha256_hash=sha256_hash,
                errors=errors,
            )

        sample_rate = wav_info.get("sample_rate", 0)
        bit_depth = wav_info.get("bit_depth", 0)
        channels = wav_info.get("channels", 0)
        duration = wav_info.get("duration", 0.0)
        audio_format = wav_info.get("audio_format", 0)

        # --- Format check ---
        format_ok = audio_format in (1, 3)  # 1=PCM, 3=IEEE Float
        if not format_ok:
            errors.append(f"Unsupported audio format code: {audio_format}")

        # --- Sample rate ---
        sample_rate_ok = sample_rate == self._thresholds.expected_sample_rate
        if not sample_rate_ok:
            warnings.append(
                f"Sample rate mismatch: expected {self._thresholds.expected_sample_rate}Hz, "
                f"got {sample_rate}Hz"
            )

        # --- Bit depth ---
        bit_depth_ok = bit_depth == self._thresholds.expected_bit_depth
        if not bit_depth_ok:
            warnings.append(
                f"Bit depth mismatch: expected {self._thresholds.expected_bit_depth}, "
                f"got {bit_depth}"
            )

        # --- Channels ---
        channels_ok = channels == self._thresholds.expected_channels
        if not channels_ok:
            warnings.append(
                f"Channel count mismatch: expected {self._thresholds.expected_channels}, "
                f"got {channels}"
            )

        # --- Duration ---
        duration_ok = (
            self._thresholds.min_duration_seconds
            <= duration
            <= self._thresholds.max_duration_seconds
        )
        if not duration_ok:
            errors.append(
                f"Duration out of range: {duration:.2f}s "
                f"(range: {self._thresholds.min_duration_seconds}–"
                f"{self._thresholds.max_duration_seconds})"
            )

        if expected_duration and duration_ok:
            tolerance = expected_duration * self._thresholds.duration_tolerance_pct
            if abs(duration - expected_duration) > tolerance:
                warnings.append(
                    f"Duration deviation: expected {expected_duration:.2f}s, "
                    f"got {duration:.2f}s (tolerance: ±{tolerance:.2f}s)"
                )

        metadata["duration_seconds"] = round(duration, 3)
        metadata["sample_rate"] = sample_rate
        metadata["bit_depth"] = bit_depth
        metadata["channels"] = channels

        # --- SNR and clipping analysis ---
        snr_db: Optional[float] = None
        clipping_pct: Optional[float] = None
        max_silence_duration: float = 0.0

        pcm_data = wav_info.get("pcm_data")
        if pcm_data and len(pcm_data) > 0:
            try:
                samples = self._decode_pcm_samples(
                    pcm_data, bit_depth, channels
                )
                if samples:
                    snr_db = self._compute_snr(samples)
                    clipping_pct = self._compute_clipping_rate(
                        samples, bit_depth
                    )
                    max_silence_duration = self._detect_silence(
                        samples, sample_rate
                    )

                    metadata["snr_db"] = round(snr_db, 2) if snr_db else None
                    metadata["clipping_pct"] = (
                        round(clipping_pct, 4) if clipping_pct is not None else None
                    )
                    metadata["max_silence_seconds"] = round(max_silence_duration, 2)

            except Exception as e:
                warnings.append(f"Audio analysis failed: {e}")

        # --- SNR check ---
        snr_ok = True
        if snr_db is not None:
            if snr_db < self._thresholds.min_snr_db:
                errors.append(
                    f"SNR too low: {snr_db:.1f}dB (min: {self._thresholds.min_snr_db}dB)"
                )
                snr_ok = False
            elif snr_db < self._thresholds.snr_flagged_db:
                warnings.append(
                    f"SNR marginal: {snr_db:.1f}dB (recommended: >{self._thresholds.snr_flagged_db}dB)"
                )

        # --- Clipping check ---
        clipping_ok = True
        if clipping_pct is not None:
            if clipping_pct > self._thresholds.max_clipping_pct:
                errors.append(
                    f"Clipping too high: {clipping_pct:.2f}% "
                    f"(max: {self._thresholds.max_clipping_pct}%)"
                )
                clipping_ok = False
            elif clipping_pct > self._thresholds.clipping_flagged_pct:
                warnings.append(
                    f"Clipping marginal: {clipping_pct:.2f}% "
                    f"(recommended: <{self._thresholds.clipping_flagged_pct}%)"
                )

        # --- Silence check ---
        silence_ok = True
        if max_silence_duration > self._thresholds.max_silence_seconds:
            warnings.append(
                f"Extended silence detected: {max_silence_duration:.1f}s "
                f"(max: {self._thresholds.max_silence_seconds}s)"
            )
            silence_ok = False

        # --- Quality score ---
        quality_score = self._compute_quality_score(
            corruption_ok=corruption_ok,
            format_ok=format_ok,
            sample_rate_ok=sample_rate_ok,
            bit_depth_ok=bit_depth_ok,
            channels_ok=channels_ok,
            duration_ok=duration_ok,
            snr_ok=snr_ok,
            clipping_ok=clipping_ok,
            silence_ok=silence_ok,
            snr_db=snr_db,
        )

        # --- Decision ---
        if errors:
            decision = AudioQualityDecision.REJECTED
        elif warnings:
            decision = AudioQualityDecision.FLAGGED
        else:
            decision = AudioQualityDecision.APPROVED

        is_valid = decision != AudioQualityDecision.REJECTED

        return AudioValidationResult(
            is_valid=is_valid,
            decision=decision,
            quality_score=quality_score,
            format_ok=format_ok,
            sample_rate_ok=sample_rate_ok,
            bit_depth_ok=bit_depth_ok,
            channels_ok=channels_ok,
            duration_ok=duration_ok,
            snr_ok=snr_ok,
            clipping_ok=clipping_ok,
            silence_ok=silence_ok,
            corruption_ok=corruption_ok,
            actual_sample_rate=sample_rate,
            actual_bit_depth=bit_depth,
            actual_channels=channels,
            actual_duration_seconds=round(duration, 3),
            snr_db=snr_db,
            clipping_pct=clipping_pct,
            max_silence_duration=max_silence_duration,
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
        )

    # ----- Internal analysis methods -----

    @staticmethod
    def _parse_wav_header(data: bytes) -> Dict[str, Any]:
        """Parse WAV header and extract PCM data chunk."""
        info: Dict[str, Any] = {"valid": False}

        if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return info

        try:
            pos = 12
            pcm_data = b""

            while pos < len(data) - 8:
                chunk_id = data[pos:pos + 4]
                chunk_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]

                if chunk_id == b"fmt ":
                    if chunk_size >= 16:
                        fmt = data[pos + 8:pos + 8 + min(chunk_size, 40)]
                        info["audio_format"] = struct.unpack("<H", fmt[0:2])[0]
                        info["channels"] = struct.unpack("<H", fmt[2:4])[0]
                        info["sample_rate"] = struct.unpack("<I", fmt[4:8])[0]
                        info["byte_rate"] = struct.unpack("<I", fmt[8:12])[0]
                        info["block_align"] = struct.unpack("<H", fmt[12:14])[0]
                        info["bit_depth"] = struct.unpack("<H", fmt[14:16])[0]

                elif chunk_id == b"data":
                    pcm_start = pos + 8
                    pcm_end = min(pcm_start + chunk_size, len(data))
                    pcm_data = data[pcm_start:pcm_end]

                    if info.get("byte_rate", 0) > 0:
                        info["duration"] = len(pcm_data) / info["byte_rate"]
                    info["data_size"] = len(pcm_data)

                pos += 8 + chunk_size
                if chunk_size % 2 == 1:
                    pos += 1

            if "sample_rate" in info:
                info["valid"] = True
                info["pcm_data"] = pcm_data

        except (struct.error, IndexError):
            pass

        return info

    @staticmethod
    def _decode_pcm_samples(
        pcm_data: bytes, bit_depth: int, channels: int
    ) -> List[float]:
        """Decode PCM bytes to normalized float samples [-1.0, 1.0]."""
        samples: List[float] = []

        if bit_depth == 16:
            max_val = 32767.0
            step = 2 * channels
            for i in range(0, len(pcm_data) - step + 1, step):
                val = struct.unpack("<h", pcm_data[i:i + 2])[0]
                samples.append(val / max_val)

        elif bit_depth == 24:
            max_val = 8388607.0
            step = 3 * channels
            for i in range(0, len(pcm_data) - step + 1, step):
                b = pcm_data[i:i + 3]
                val = b[0] | (b[1] << 8) | (b[2] << 16)
                if val >= 0x800000:
                    val -= 0x1000000
                samples.append(val / max_val)

        elif bit_depth == 32:
            max_val = 2147483647.0
            step = 4 * channels
            for i in range(0, len(pcm_data) - step + 1, step):
                val = struct.unpack("<i", pcm_data[i:i + 4])[0]
                samples.append(val / max_val)

        # Downsample for analysis if too many samples (> 1M)
        if len(samples) > 1_000_000:
            stride = len(samples) // 1_000_000
            samples = samples[::stride]

        return samples

    @staticmethod
    def _compute_snr(samples: List[float]) -> float:
        """
        Estimate Signal-to-Noise Ratio in dB.

        Uses a simple RMS-based approach: signal power is RMS of all samples,
        noise is estimated from the quietest 10% of windowed segments.
        """
        if not samples:
            return 0.0

        # Overall RMS
        rms_signal = math.sqrt(sum(s * s for s in samples) / len(samples))
        if rms_signal == 0:
            return 0.0

        # Estimate noise from quietest segments
        window_size = min(1024, len(samples) // 10)
        if window_size < 64:
            return 40.0  # Assume good SNR for very short clips

        window_rms_values = []
        for i in range(0, len(samples) - window_size, window_size):
            window = samples[i:i + window_size]
            wrms = math.sqrt(sum(s * s for s in window) / len(window))
            window_rms_values.append(wrms)

        if not window_rms_values:
            return 40.0

        window_rms_values.sort()
        noise_count = max(1, len(window_rms_values) // 10)
        noise_rms = sum(window_rms_values[:noise_count]) / noise_count

        if noise_rms == 0:
            return 60.0  # Very clean signal

        snr = 20 * math.log10(rms_signal / noise_rms)
        return max(0.0, snr)

    def _compute_clipping_rate(
        self, samples: List[float], bit_depth: int
    ) -> float:
        """Compute percentage of samples at or near clipping threshold."""
        if not samples:
            return 0.0

        threshold = self._thresholds.clipping_threshold_ratio
        clipped = sum(1 for s in samples if abs(s) >= threshold)
        return (clipped / len(samples)) * 100.0

    @staticmethod
    def _detect_silence(
        samples: List[float], sample_rate: int, threshold: float = 0.01
    ) -> float:
        """
        Detect longest silent segment in seconds.

        A sample is "silent" if its absolute value is below threshold.
        """
        if not samples or sample_rate == 0:
            return 0.0

        max_silence = 0
        current_silence = 0

        for s in samples:
            if abs(s) < threshold:
                current_silence += 1
                max_silence = max(max_silence, current_silence)
            else:
                current_silence = 0

        return max_silence / sample_rate

    @staticmethod
    def _compute_quality_score(
        corruption_ok: bool,
        format_ok: bool,
        sample_rate_ok: bool,
        bit_depth_ok: bool,
        channels_ok: bool,
        duration_ok: bool,
        snr_ok: bool,
        clipping_ok: bool,
        silence_ok: bool,
        snr_db: Optional[float],
    ) -> float:
        """Compute weighted quality score."""
        score = 0.0
        weights = {
            "corruption": (corruption_ok, 0.25),
            "format": (format_ok, 0.10),
            "sample_rate": (sample_rate_ok, 0.10),
            "bit_depth": (bit_depth_ok, 0.05),
            "channels": (channels_ok, 0.05),
            "duration": (duration_ok, 0.10),
            "snr": (snr_ok, 0.20),
            "clipping": (clipping_ok, 0.10),
            "silence": (silence_ok, 0.05),
        }

        for _, (passed, weight) in weights.items():
            if passed:
                score += weight

        return round(min(score, 1.0), 4)
