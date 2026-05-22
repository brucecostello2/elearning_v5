"""
IVGS v5 — Corruption Detector Tests
=======================================

Test suite for §11.2 corruption detection:
- Video file validation
- Audio file validation
- Codec checking
- Resolution verification
- Duration validation
- Truncation detection
- Checksum verification
"""

from __future__ import annotations

import os
import struct
import tempfile

import pytest

from validators.corruption_detector import (
    CorruptionCheck,
    CorruptionDetector,
    CorruptionSeverity,
    CorruptionValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector() -> CorruptionDetector:
    return CorruptionDetector()


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def minimal_mp4_file(temp_dir) -> str:
    """Create a minimal valid MP4 file."""
    ftyp = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41"
    moov = b"\x00\x00\x00\x08moov"
    mdat = b"\x00\x00\x00\x10mdat" + b"\xff" * 8
    path = os.path.join(temp_dir, "test.mp4")
    with open(path, "wb") as f:
        f.write(ftyp + moov + mdat)
    return path


@pytest.fixture
def minimal_wav_file(temp_dir) -> str:
    """Create a minimal valid WAV file."""
    sample_rate = 48000
    bit_depth = 16
    channels = 1
    num_samples = 48000  # 1 second
    byte_rate = sample_rate * channels * (bit_depth // 8)
    block_align = channels * (bit_depth // 8)
    data_size = num_samples * block_align
    pcm_data = b"\x00" * data_size

    path = os.path.join(temp_dir, "test.wav")
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 1))
        f.write(struct.pack("<H", channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bit_depth))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm_data)
    return path


@pytest.fixture
def empty_file(temp_dir) -> str:
    path = os.path.join(temp_dir, "empty.mp4")
    with open(path, "wb"):
        pass
    return path


@pytest.fixture
def truncated_file(temp_dir) -> str:
    """File with ftyp header but no moov atom and zeros at end."""
    path = os.path.join(temp_dir, "truncated.mp4")
    with open(path, "wb") as f:
        f.write(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41")
        f.write(b"\x00" * 64)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCorruptionDetectorVideo:
    """Test video file corruption detection."""

    def test_nonexistent_file(self, detector):
        result = detector.validate_video("/nonexistent/file.mp4")
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_empty_file(self, detector, empty_file):
        result = detector.validate_video(empty_file)
        assert result.is_valid is False
        critical = [c for c in result.checks if c.severity == CorruptionSeverity.CRITICAL]
        assert len(critical) > 0

    def test_truncated_file_detection(self, detector, truncated_file):
        result = detector.validate_video(truncated_file)
        truncation_checks = [c for c in result.checks if c.check_name == "truncation"]
        if truncation_checks:
            assert truncation_checks[0].passed is False

    def test_file_size_check(self, detector, minimal_mp4_file):
        result = detector.validate_video(minimal_mp4_file)
        size_checks = [c for c in result.checks if c.check_name == "file_size"]
        assert len(size_checks) == 1
        assert size_checks[0].passed is True

    def test_sha256_computed(self, detector, minimal_mp4_file):
        result = detector.validate_video(minimal_mp4_file)
        assert result.sha256_hash != ""
        assert len(result.sha256_hash) == 64


class TestCorruptionDetectorAudio:
    """Test audio file corruption detection."""

    def test_valid_wav(self, detector, minimal_wav_file):
        result = detector.validate_audio(
            minimal_wav_file,
            expected_codec="pcm_s16le",
            expected_sample_rate=48000,
            expected_channels=1,
        )
        assert result.file_size_bytes > 0
        assert result.sha256_hash != ""

    def test_nonexistent_audio(self, detector):
        result = detector.validate_audio("/nonexistent/audio.wav")
        assert result.is_valid is False

    def test_empty_audio(self, detector, empty_file):
        result = detector.validate_audio(empty_file)
        assert result.is_valid is False


class TestChecksumVerification:
    """Test SHA-256 checksum verification."""

    def test_matching_checksum(self, detector, minimal_mp4_file):
        # First compute the actual hash
        actual_hash = detector._compute_sha256(minimal_mp4_file)
        check = detector.verify_checksum(minimal_mp4_file, actual_hash)
        assert check.passed is True

    def test_mismatched_checksum(self, detector, minimal_mp4_file):
        check = detector.verify_checksum(minimal_mp4_file, "wrong_hash_value")
        assert check.passed is False
        assert check.severity == CorruptionSeverity.CRITICAL
        assert "mismatch" in check.message.lower()


class TestCorruptionValidationResult:
    """Test result model properties."""

    def test_critical_failures_property(self):
        result = CorruptionValidationResult(
            is_valid=False,
            file_path="/test",
            checks=[
                CorruptionCheck(
                    check_name="codec",
                    passed=False,
                    severity=CorruptionSeverity.CRITICAL,
                ),
                CorruptionCheck(
                    check_name="duration",
                    passed=False,
                    severity=CorruptionSeverity.WARNING,
                ),
                CorruptionCheck(
                    check_name="size",
                    passed=True,
                ),
            ],
        )
        assert len(result.critical_failures) == 1
        assert len(result.warnings) == 1
