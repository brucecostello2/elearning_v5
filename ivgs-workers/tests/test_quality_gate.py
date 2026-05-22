"""
IVGS v5 — Quality Gate Workflow Tests
=========================================

Tests for the quality gate workflow per §11.3.

Test coverage:
- Approved assets proceed to next stage
- Flagged assets pause pipeline for human review
- Rejected assets trigger regeneration (max 2 attempts)
- DLQ escalation after max regeneration failures
- Human override (approve/reject)
- Project gate readiness (all approved required for composition)
- Asset registration and history tracking
- Review queue listing
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.quality_gate import (
    GateAction,
    QualityGateService,
)
from services.quality_validator import (
    AssetType,
    QualityDecision,
    QualityMetric,
    QualityReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    """In-memory Redis mock."""
    from test_scheduler import FakeRedis
    return FakeRedis()


@pytest.fixture
def mock_regeneration_callback():
    return AsyncMock()


@pytest.fixture
def mock_dlq_callback():
    return AsyncMock()


@pytest.fixture
def gate_service(fake_redis, mock_regeneration_callback, mock_dlq_callback):
    return QualityGateService(
        redis=fake_redis,
        max_regeneration_attempts=2,
        regeneration_callback=mock_regeneration_callback,
        dlq_callback=mock_dlq_callback,
    )


def _make_quality_report(
    asset_id: str = "asset-1",
    project_id: str = "proj-1",
    decision: QualityDecision = QualityDecision.APPROVED,
    asset_type: AssetType = AssetType.IMAGE,
    scene_id: str = "scene-1",
) -> QualityReport:
    """Helper to create a QualityReport."""
    return QualityReport(
        asset_id=asset_id,
        asset_type=asset_type,
        project_id=project_id,
        scene_id=scene_id,
        overall_decision=decision,
        metrics=[
            QualityMetric(
                metric_name="clip_score",
                value=0.95 if decision == QualityDecision.APPROVED else 0.6,
                threshold_approve=0.9,
                threshold_reject=0.75,
                decision=decision,
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


# ---------------------------------------------------------------------------
# Approved Flow Tests per §11.3 Step 3
# ---------------------------------------------------------------------------

class TestApprovedFlow:
    """Test approved assets proceed to next stage per §11.3."""

    @pytest.mark.asyncio
    async def test_approved_asset_proceeds(self, gate_service):
        """Approved asset should trigger PROCEED action."""
        report = _make_quality_report(decision=QualityDecision.APPROVED)

        decision = await gate_service.process_quality_report(report)

        assert decision.gate_action == GateAction.PROCEED
        assert decision.quality_decision == QualityDecision.APPROVED

    @pytest.mark.asyncio
    async def test_approved_asset_added_to_approved_set(
        self, gate_service, fake_redis
    ):
        """Approved asset should be added to project's approved set."""
        report = _make_quality_report(
            asset_id="asset-approved", project_id="proj-1"
        )

        await gate_service.process_quality_report(report)

        approved = await fake_redis.smembers("qg:project_approved:proj-1")
        assert "asset-approved" in approved


# ---------------------------------------------------------------------------
# Flagged Flow Tests per §11.3 Step 4
# ---------------------------------------------------------------------------

class TestFlaggedFlow:
    """Test flagged assets pause pipeline per §11.3."""

    @pytest.mark.asyncio
    async def test_flagged_asset_pauses(self, gate_service):
        """Flagged asset should trigger PAUSE action."""
        report = _make_quality_report(decision=QualityDecision.FLAGGED)

        decision = await gate_service.process_quality_report(report)

        assert decision.gate_action == GateAction.PAUSE

    @pytest.mark.asyncio
    async def test_flagged_asset_in_review_queue(
        self, gate_service, fake_redis
    ):
        """Flagged asset should be added to flagged set."""
        report = _make_quality_report(
            asset_id="asset-flagged",
            decision=QualityDecision.FLAGGED,
        )

        await gate_service.process_quality_report(report)

        flagged = await fake_redis.smembers("qg:project_flagged:proj-1")
        assert "asset-flagged" in flagged


# ---------------------------------------------------------------------------
# Rejected Flow Tests per §11.3 Step 5
# ---------------------------------------------------------------------------

class TestRejectedFlow:
    """Test rejected assets trigger regeneration per §11.3."""

    @pytest.mark.asyncio
    async def test_first_rejection_triggers_regeneration(
        self, gate_service, mock_regeneration_callback
    ):
        """First rejection should trigger regeneration (attempt 1/2)."""
        report = _make_quality_report(decision=QualityDecision.REJECTED)

        decision = await gate_service.process_quality_report(report)

        assert decision.gate_action == GateAction.REGENERATE
        assert decision.regeneration_attempt == 1
        mock_regeneration_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_rejection_triggers_regeneration(
        self, gate_service, fake_redis, mock_regeneration_callback
    ):
        """Second rejection should trigger regeneration (attempt 2/2)."""
        # Set first attempt already done
        await fake_redis.set("qg:regeneration:asset-1", "1")

        report = _make_quality_report(decision=QualityDecision.REJECTED)

        decision = await gate_service.process_quality_report(report)

        assert decision.gate_action == GateAction.REGENERATE
        assert decision.regeneration_attempt == 2

    @pytest.mark.asyncio
    async def test_third_rejection_escalates_to_dlq(
        self, gate_service, fake_redis, mock_dlq_callback
    ):
        """Third rejection should escalate to DLQ per §11.3 step 6."""
        # Set two attempts already done
        await fake_redis.set("qg:regeneration:asset-1", "2")

        report = _make_quality_report(decision=QualityDecision.REJECTED)

        decision = await gate_service.process_quality_report(report)

        assert decision.gate_action == GateAction.ESCALATE_DLQ
        mock_dlq_callback.assert_called_once()
        # Verify DLQ category is 'external' per §11.3
        call_kwargs = mock_dlq_callback.call_args[1]
        assert call_kwargs["category"] == "external"


# ---------------------------------------------------------------------------
# Human Override Tests per §11.3 Step 4
# ---------------------------------------------------------------------------

class TestHumanOverride:
    """Test human override of quality gate decisions per §11.3."""

    @pytest.mark.asyncio
    async def test_human_approve_override(self, gate_service, fake_redis):
        """Human can override a flagged asset to approved."""
        # Flag an asset first
        report = _make_quality_report(
            asset_id="asset-override",
            decision=QualityDecision.FLAGGED,
        )
        await gate_service.process_quality_report(report)

        # Human approves
        decision = await gate_service.apply_human_override(
            asset_id="asset-override",
            project_id="proj-1",
            override_decision="approve",
            reviewer_id="reviewer-1",
            notes="Looks fine on manual review",
        )

        assert decision.gate_action == GateAction.HUMAN_OVERRIDE
        assert decision.quality_decision == QualityDecision.APPROVED

        # Verify asset moved to approved set
        approved = await fake_redis.smembers("qg:project_approved:proj-1")
        assert "asset-override" in approved

    @pytest.mark.asyncio
    async def test_human_reject_override(
        self, gate_service, mock_dlq_callback
    ):
        """Human can reject a flagged asset (routes to DLQ)."""
        decision = await gate_service.apply_human_override(
            asset_id="asset-reject",
            project_id="proj-1",
            override_decision="reject",
            reviewer_id="reviewer-1",
            notes="Quality too low",
        )

        assert decision.gate_action == GateAction.ESCALATE_DLQ
        mock_dlq_callback.assert_called_once()


# ---------------------------------------------------------------------------
# Project Gate Readiness Tests per §11.3
# ---------------------------------------------------------------------------

class TestProjectGateReadiness:
    """Test project-level gate readiness per §11.3."""

    @pytest.mark.asyncio
    async def test_all_approved_can_advance(
        self, gate_service, fake_redis
    ):
        """Project with all approved assets can advance."""
        await fake_redis.sadd("qg:project_approved:proj-1", "a1", "a2", "a3")

        status = await gate_service.check_project_gate("proj-1")

        assert status.can_advance is True
        assert status.approved_count == 3
        assert status.flagged_count == 0

    @pytest.mark.asyncio
    async def test_flagged_assets_block_advance(
        self, gate_service, fake_redis
    ):
        """Project with flagged assets cannot advance to composition."""
        await fake_redis.sadd("qg:project_approved:proj-1", "a1", "a2")
        await fake_redis.sadd("qg:project_flagged:proj-1", "a3")

        status = await gate_service.check_project_gate("proj-1")

        assert status.can_advance is False
        assert status.flagged_count == 1

    @pytest.mark.asyncio
    async def test_pending_assets_block_advance(
        self, gate_service, fake_redis
    ):
        """Project with pending assets cannot advance."""
        await fake_redis.sadd("qg:project_approved:proj-1", "a1")
        await fake_redis.sadd("qg:project_pending:proj-1", "a2")

        status = await gate_service.check_project_gate("proj-1")

        assert status.can_advance is False
        assert status.pending_count == 1

    @pytest.mark.asyncio
    async def test_empty_project_cannot_advance(
        self, gate_service, fake_redis
    ):
        """Project with no assets cannot advance."""
        status = await gate_service.check_project_gate("proj-empty")

        assert status.can_advance is False
        assert status.total_assets == 0


# ---------------------------------------------------------------------------
# Asset Registration Tests
# ---------------------------------------------------------------------------

class TestAssetRegistration:
    """Test asset registration for quality gate tracking."""

    @pytest.mark.asyncio
    async def test_register_asset_adds_to_pending(
        self, gate_service, fake_redis
    ):
        """Registering an asset adds it to the project's pending set."""
        await gate_service.register_asset(
            asset_id="asset-new",
            project_id="proj-1",
            asset_type="image",
            scene_id="scene-1",
        )

        pending = await fake_redis.smembers("qg:project_pending:proj-1")
        assert "asset-new" in pending


# ---------------------------------------------------------------------------
# History Tests
# ---------------------------------------------------------------------------

class TestGateHistory:
    """Test quality gate decision history."""

    @pytest.mark.asyncio
    async def test_history_recorded(self, gate_service, fake_redis):
        """Gate decisions should be recorded in history."""
        report = _make_quality_report(
            asset_id="asset-history",
            decision=QualityDecision.APPROVED,
        )

        await gate_service.process_quality_report(report)

        history = await gate_service.get_asset_history("asset-history")
        assert len(history) == 1
        assert history[0]["action"] == "proceed"
