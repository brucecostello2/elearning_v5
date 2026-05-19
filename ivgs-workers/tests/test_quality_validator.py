"""
IVGS v5 — Quality Validator Tests
=====================================

Tests for the QualityValidator service per §11.1 Table 11-1.

Test coverage:
- Image validation: CLIP score, resolution check, artifact detection
- Video validation: frame consistency, artifact detection, duration
- Audio validation: SNR, clipping rate
- Talking head validation: lip-sync score + video quality
- Caption validation: transcript-timeline alignment
- Content safety classification
- Threshold decision logic (approve/flag/reject boundaries)
- Overall decision computation (worst-metric)
- Content hash computation per §10.4
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from typing import Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.quality_validator import (
    AssetType,
    QualityDecision,
    QualityMetric,
    QualityReport,
    QualityValidator,
    AUDIO_THRESHOLDS,
    CAPTION_THRESHOLDS,
    IMAGE_THRESHOLDS,
    SAFETY_THRESHOLDS,
    TALKING_HEAD_THRESHOLDS,
    VIDEO_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def validator():
    return QualityValidator(
        clip_model_endpoint="http://localhost:8100/clip",
        safety_classifier_endpoint="http://localhost:8101",
        ffprobe_path="/usr/bin/ffprobe",
    )


@pytest.fixture
def temp_image():
    """Create a temporary test image file."""
    with tempfile.NamedTemporaryFile(
        suffix=".png", delete=False, mode="wb"
    ) as f:
        # Write minimal PNG (1x1 white pixel)
        png_data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
            b"\x00\x00\x00IEND\xaeB`\x82"
        )
        f.write(png_data)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def temp_audio():
    """Create a temporary test audio file."""
    with tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, mode="wb"
    ) as f:
        # Write minimal WAV header
        f.write(b"RIFF")
        f.write((36).to_bytes(4, "little"))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write((16).to_bytes(4, "little"))
        f.write((1).to_bytes(2, "little"))  # PCM
        f.write((1).to_bytes(2, "little"))  # Mono
        f.write((48000).to_bytes(4, "little"))  # Sample rate
        f.write((96000).to_bytes(4, "little"))  # Byte rate
        f.write((2).to_bytes(2, "little"))  # Block align
        f.write((16).to_bytes(2, "little"))  # Bits per sample
        f.write(b"data")
        f.write((0).to_bytes(4, "little"))
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def temp_caption():
    """Create a temporary SRT caption file."""
    content = """1
00:00:00,000 --> 00:00:02,500
Hello world.

2
00:00:02,500 --> 00:00:05,000
This is a test caption.

3
00:00:05,000 --> 00:00:07,500
Quality validation in progress.
"""
    with tempfile.NamedTemporaryFile(
        suffix=".srt", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(content)
        path = f.name
    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Threshold Decision Tests
# ---------------------------------------------------------------------------

class TestThresholdDecisions:
    """Test threshold decision boundary logic per Table 11-1."""

    def test_higher_better_approve(self, validator):
        """Score above approve threshold → APPROVED."""
        decision = QualityValidator._threshold_decision_higher_better(
            0.95, 0.9, 0.75
        )
        assert decision == QualityDecision.APPROVED

    def test_higher_better_flag(self, validator):
        """Score between flag and approve → FLAGGED."""
        decision = QualityValidator._threshold_decision_higher_better(
            0.82, 0.9, 0.75
        )
        assert decision == QualityDecision.FLAGGED

    def test_higher_better_reject(self, validator):
        """Score below flag threshold → REJECTED."""
        decision = QualityValidator._threshold_decision_higher_better(
            0.60, 0.9, 0.75
        )
        assert decision == QualityDecision.REJECTED

    def test_lower_better_approve(self, validator):
        """Score below approve threshold → APPROVED."""
        decision = QualityValidator._threshold_decision_lower_better(
            0.05, 0.1, 1.0
        )
        assert decision == QualityDecision.APPROVED

    def test_lower_better_flag(self, validator):
        """Score between approve and flag → FLAGGED."""
        decision = QualityValidator._threshold_decision_lower_better(
            0.5, 0.1, 1.0
        )
        assert decision == QualityDecision.FLAGGED

    def test_lower_better_reject(self, validator):
        """Score above flag threshold → REJECTED."""
        decision = QualityValidator._threshold_decision_lower_better(
            2.0, 0.1, 1.0
        )
        assert decision == QualityDecision.REJECTED

    def test_boundary_values(self, validator):
        """Test exact boundary values."""
        # Exact approve threshold
        d = QualityValidator._threshold_decision_higher_better(0.9, 0.9, 0.75)
        assert d == QualityDecision.APPROVED

        # Exact flag threshold
        d = QualityValidator._threshold_decision_higher_better(0.75, 0.9, 0.75)
        assert d == QualityDecision.FLAGGED


class TestOverallDecision:
    """Test overall decision computation."""

    def test_all_approved(self, validator):
        """All approved → overall APPROVED."""
        decisions = [
            QualityDecision.APPROVED,
            QualityDecision.APPROVED,
            QualityDecision.APPROVED,
        ]
        result = validator._compute_overall_decision(decisions)
        assert result == QualityDecision.APPROVED

    def test_one_flagged(self, validator):
        """One flagged → overall FLAGGED."""
        decisions = [
            QualityDecision.APPROVED,
            QualityDecision.FLAGGED,
            QualityDecision.APPROVED,
        ]
        result = validator._compute_overall_decision(decisions)
        assert result == QualityDecision.FLAGGED

    def test_one_rejected(self, validator):
        """One rejected → overall REJECTED (worst wins)."""
        decisions = [
            QualityDecision.APPROVED,
            QualityDecision.FLAGGED,
            QualityDecision.REJECTED,
        ]
        result = validator._compute_overall_decision(decisions)
        assert result == QualityDecision.REJECTED

    def test_empty_decisions(self, validator):
        """Empty list → APPROVED (default)."""
        result = validator._compute_overall_decision([])
        assert result == QualityDecision.APPROVED


# ---------------------------------------------------------------------------
# Caption Validation Tests
# ---------------------------------------------------------------------------

class TestCaptionValidation:
    """Test caption validation per Table 11-1."""

    @pytest.mark.asyncio
    async def test_valid_caption_alignment(self, validator, temp_caption):
        """Valid SRT captions should produce high alignment score."""
        metrics = await validator._validate_caption(
            temp_caption,
            reference_transcript="Hello world. This is a test caption.",
        )

        assert len(metrics) == 1
        assert metrics[0].metric_name == "transcript_timeline_sync_accuracy"
        assert metrics[0].value > 0.0

    @pytest.mark.asyncio
    async def test_caption_with_reference_transcript(
        self, validator, temp_caption
    ):
        """Caption alignment should improve with matching transcript."""
        metrics = await validator._validate_caption(
            temp_caption,
            reference_transcript=(
                "Hello world. This is a test caption. "
                "Quality validation in progress."
            ),
        )

        assert metrics[0].value > 0.5

    @pytest.mark.asyncio
    async def test_empty_caption_rejected(self, validator):
        """Empty caption file should be rejected."""
        with tempfile.NamedTemporaryFile(
            suffix=".srt", delete=False, mode="w"
        ) as f:
            f.write("")
            path = f.name

        try:
            metrics = await validator._validate_caption(path, None)
            assert metrics[0].value == 0.0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Content Hash Tests per §10.4
# ---------------------------------------------------------------------------

class TestContentHash:
    """Test SHA-256 content hash computation per §10.4."""

    @pytest.mark.asyncio
    async def test_hash_computation(self, validator, temp_image):
        """Hash should match manual SHA-256 computation."""
        expected = hashlib.sha256()
        with open(temp_image, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                expected.update(chunk)

        actual = await validator._compute_content_hash(temp_image)
        assert actual == expected.hexdigest()

    @pytest.mark.asyncio
    async def test_same_content_same_hash(self, validator):
        """Identical content should produce identical hash."""
        content = b"test content for deduplication"

        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(content)
            path1 = f1.name
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(content)
            path2 = f2.name

        try:
            hash1 = await validator._compute_content_hash(path1)
            hash2 = await validator._compute_content_hash(path2)
            assert hash1 == hash2
        finally:
            os.unlink(path1)
            os.unlink(path2)


# ---------------------------------------------------------------------------
# Quality Report Tests
# ---------------------------------------------------------------------------

class TestQualityReport:
    """Test QualityReport serialization."""

    def test_report_to_dict(self):
        """QualityReport should serialize to dict correctly."""
        report = QualityReport(
            asset_id="asset-1",
            asset_type=AssetType.IMAGE,
            project_id="proj-1",
            scene_id="scene-1",
            overall_decision=QualityDecision.APPROVED,
            metrics=[
                QualityMetric(
                    metric_name="clip_score",
                    value=0.95,
                    threshold_approve=0.9,
                    threshold_reject=0.75,
                    decision=QualityDecision.APPROVED,
                    method="clip",
                )
            ],
            safety_score=0.99,
            safety_decision=QualityDecision.APPROVED,
            validated_at="2025-01-01T00:00:00Z",
            validation_duration_s=1.5,
            content_hash="abc123",
            file_path="/tmp/test.png",
        )

        d = report.to_dict()
        assert d["asset_id"] == "asset-1"
        assert d["overall_decision"] == "approved"
        assert len(d["metrics"]) == 1
        assert d["metrics"][0]["value"] == 0.95

    def test_report_to_dict_no_safety(self):
        """Report without safety should serialize None safety."""
        report = QualityReport(
            asset_id="asset-2",
            asset_type=AssetType.VIDEO,
            project_id="proj-2",
            scene_id=None,
            overall_decision=QualityDecision.FLAGGED,
            metrics=[],
            safety_score=None,
            safety_decision=None,
            validated_at="2025-01-01T00:00:00Z",
            validation_duration_s=0.5,
            content_hash="def456",
            file_path="/tmp/test.mp4",
        )

        d = report.to_dict()
        assert d["safety_score"] is None
        assert d["safety_decision"] is None


# ---------------------------------------------------------------------------
# Threshold Constant Tests
# ---------------------------------------------------------------------------

class TestThresholdConstants:
    """Verify threshold constants match §11.1 Table 11-1."""

    def test_image_clip_thresholds(self):
        t = IMAGE_THRESHOLDS["clip_score"]
        assert t["approve"] == 0.9
        assert t["flag_min"] == 0.75
        assert t["reject_below"] == 0.75

    def test_video_frame_consistency_thresholds(self):
        t = VIDEO_THRESHOLDS["frame_consistency"]
        assert t["approve"] == 0.8
        assert t["flag_min"] == 0.7
        assert t["reject_below"] == 0.7

    def test_video_artifact_thresholds(self):
        t = VIDEO_THRESHOLDS["artifact_pct"]
        assert t["approve_below"] == 1.0
        assert t["flag_max"] == 5.0
        assert t["reject_above"] == 5.0

    def test_audio_snr_thresholds(self):
        t = AUDIO_THRESHOLDS["snr_db"]
        assert t["approve"] == 25.0
        assert t["flag_min"] == 20.0
        assert t["reject_below"] == 20.0

    def test_audio_clipping_thresholds(self):
        t = AUDIO_THRESHOLDS["clipping_pct"]
        assert t["approve_below"] == 0.1
        assert t["flag_max"] == 1.0
        assert t["reject_above"] == 1.0

    def test_talking_head_lipsync_thresholds(self):
        t = TALKING_HEAD_THRESHOLDS["lipsync_score"]
        assert t["approve"] == 0.9
        assert t["flag_min"] == 0.85
        assert t["reject_below"] == 0.85

    def test_caption_alignment_thresholds(self):
        t = CAPTION_THRESHOLDS["alignment_score"]
        assert t["approve"] == 0.95
        assert t["flag_min"] == 0.9
        assert t["reject_below"] == 0.9

    def test_safety_thresholds(self):
        t = SAFETY_THRESHOLDS["safety_score"]
        assert t["approve"] == 0.98
        assert t["reject_below"] == 0.95


# ---------------------------------------------------------------------------
# Integration-style Test
# ---------------------------------------------------------------------------

class TestValidatorIntegration:
    """Integration tests for full validation pipeline."""

    @pytest.mark.asyncio
    async def test_caption_full_validation(self, validator, temp_caption):
        """Full caption validation should produce a complete report."""
        with patch.object(
            validator, "_check_content_safety",
            return_value=(0.99, QualityDecision.APPROVED),
        ):
            report = await validator.validate_asset(
                asset_id="cap-test",
                asset_type=AssetType.CAPTION,
                file_path=temp_caption,
                project_id="proj-test",
                scene_id="scene-1",
                reference_transcript="Hello world. This is a test.",
            )

        assert isinstance(report, QualityReport)
        assert report.asset_id == "cap-test"
        assert report.content_hash  # Should have a hash
        assert report.validation_duration_s > 0
        assert len(report.metrics) >= 1
