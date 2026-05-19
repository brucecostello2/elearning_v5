"""
IVGS v5 — Retry Engine Tests
========================================

Tests for RetryEngine per §6.2 Table 6-4.

Test coverage:
- Policy lookup for all 6 stage types
- Backoff sequence validation (exact values per Table 6-4)
- Retry evaluation logic (should_retry vs exhaustion)
- Config errors skip retry (immediate DLQ)
- Exhaustion action correctness per stage type
- Attempt recording in task_retries table
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ivgs_workers.services.retry_engine import (
    ExhaustionAction,
    RetryAttemptRecord,
    RetryDecision,
    RetryEngine,
    RetryPolicy,
    RETRY_POLICIES,
    StageType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_session_factory() -> AsyncMock:
    """Create a mock async database session factory."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()

    factory = AsyncMock(return_value=session)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.fixture
def retry_engine(mock_db_session_factory: AsyncMock) -> RetryEngine:
    """Create a RetryEngine instance with mock dependencies."""
    return RetryEngine(db_session_factory=mock_db_session_factory)


# ---------------------------------------------------------------------------
# Policy Configuration Tests
# ---------------------------------------------------------------------------

class TestRetryPolicies:
    """Validate retry policies match §6.2 Table 6-4 exactly."""

    def test_llm_policy(self) -> None:
        """LLM: 4 retries, 5s→15s→45s→135s, → DLQ."""
        policy = RETRY_POLICIES[StageType.LLM]
        assert policy.max_retries == 4
        assert policy.backoff_sequence == (5.0, 15.0, 45.0, 135.0)
        assert policy.on_exhaustion == ExhaustionAction.DLQ

    def test_image_policy(self) -> None:
        """Image: 3 retries, 10s→30s→90s, → Fallback + DLQ."""
        policy = RETRY_POLICIES[StageType.IMAGE]
        assert policy.max_retries == 3
        assert policy.backoff_sequence == (10.0, 30.0, 90.0)
        assert policy.on_exhaustion == ExhaustionAction.FALLBACK_AND_DLQ

    def test_video_policy(self) -> None:
        """Video: 2 retries, 30s→90s, → Fallback chain + DLQ."""
        policy = RETRY_POLICIES[StageType.VIDEO]
        assert policy.max_retries == 2
        assert policy.backoff_sequence == (30.0, 90.0)
        assert policy.on_exhaustion == ExhaustionAction.FALLBACK_AND_DLQ

    def test_tts_policy(self) -> None:
        """TTS: 3 retries, 10s→30s→90s, → Kokoro fallback + DLQ."""
        policy = RETRY_POLICIES[StageType.TTS]
        assert policy.max_retries == 3
        assert policy.backoff_sequence == (10.0, 30.0, 90.0)
        assert policy.on_exhaustion == ExhaustionAction.KOKORO_FALLBACK_AND_DLQ

    def test_talking_head_policy(self) -> None:
        """Talking head: 2 retries, 30s→90s, → SadTalker fallback + DLQ."""
        policy = RETRY_POLICIES[StageType.TALKING_HEAD]
        assert policy.max_retries == 2
        assert policy.backoff_sequence == (30.0, 90.0)
        assert policy.on_exhaustion == ExhaustionAction.SADTALKER_FALLBACK_AND_DLQ

    def test_composition_policy(self) -> None:
        """Composition: 2 retries, 30s→90s, → DLQ."""
        policy = RETRY_POLICIES[StageType.COMPOSITION]
        assert policy.max_retries == 2
        assert policy.backoff_sequence == (30.0, 90.0)
        assert policy.on_exhaustion == ExhaustionAction.DLQ


# ---------------------------------------------------------------------------
# Backoff Calculation Tests
# ---------------------------------------------------------------------------

class TestBackoffCalculation:
    """Tests for backoff delay calculation."""

    def test_llm_backoff_sequence(self, retry_engine: RetryEngine) -> None:
        """Verify LLM backoff: 5s, 15s, 45s, 135s."""
        assert retry_engine.calculate_backoff(StageType.LLM, 1) == 5.0
        assert retry_engine.calculate_backoff(StageType.LLM, 2) == 15.0
        assert retry_engine.calculate_backoff(StageType.LLM, 3) == 45.0
        assert retry_engine.calculate_backoff(StageType.LLM, 4) == 135.0

    def test_image_backoff_sequence(self, retry_engine: RetryEngine) -> None:
        """Verify image backoff: 10s, 30s, 90s."""
        assert retry_engine.calculate_backoff(StageType.IMAGE, 1) == 10.0
        assert retry_engine.calculate_backoff(StageType.IMAGE, 2) == 30.0
        assert retry_engine.calculate_backoff(StageType.IMAGE, 3) == 90.0

    def test_video_backoff_sequence(self, retry_engine: RetryEngine) -> None:
        """Verify video backoff: 30s, 90s."""
        assert retry_engine.calculate_backoff(StageType.VIDEO, 1) == 30.0
        assert retry_engine.calculate_backoff(StageType.VIDEO, 2) == 90.0

    def test_backoff_clamps_to_last_value(
        self, retry_engine: RetryEngine
    ) -> None:
        """Verify backoff clamps to last sequence value if exceeded."""
        assert retry_engine.calculate_backoff(StageType.VIDEO, 5) == 90.0
        assert retry_engine.calculate_backoff(StageType.LLM, 10) == 135.0


# ---------------------------------------------------------------------------
# Retry Evaluation Tests
# ---------------------------------------------------------------------------

class TestRetryEvaluation:
    """Tests for retry evaluation logic."""

    def test_should_retry_on_first_attempt(
        self, retry_engine: RetryEngine
    ) -> None:
        """First attempt of any stage type should allow retry."""
        for stage_type in StageType:
            decision = retry_engine.evaluate(stage_type, 1, "transient")
            assert decision.should_retry is True
            assert decision.exhaustion_action is None
            assert decision.backoff_seconds > 0

    def test_llm_exhaustion_after_4_retries(
        self, retry_engine: RetryEngine
    ) -> None:
        """LLM should exhaust after 4 retries → DLQ."""
        decision = retry_engine.evaluate(StageType.LLM, 4, "transient")
        assert decision.should_retry is False
        assert decision.exhaustion_action == ExhaustionAction.DLQ

    def test_image_exhaustion_triggers_fallback(
        self, retry_engine: RetryEngine
    ) -> None:
        """Image should exhaust after 3 retries → Fallback + DLQ."""
        decision = retry_engine.evaluate(StageType.IMAGE, 3, "transient")
        assert decision.should_retry is False
        assert decision.exhaustion_action == ExhaustionAction.FALLBACK_AND_DLQ

    def test_config_errors_skip_retry(
        self, retry_engine: RetryEngine
    ) -> None:
        """Config errors should never retry — immediate exhaustion."""
        for stage_type in StageType:
            decision = retry_engine.evaluate(stage_type, 1, "config")
            assert decision.should_retry is False
            assert decision.exhaustion_action is not None

    def test_retry_decision_includes_correct_metadata(
        self, retry_engine: RetryEngine
    ) -> None:
        """Verify RetryDecision includes correct attempt and max info."""
        decision = retry_engine.evaluate(StageType.VIDEO, 1, "transient")
        assert decision.attempt_number == 1
        assert decision.max_retries == 2
        assert decision.stage_type == StageType.VIDEO


# ---------------------------------------------------------------------------
# Attempt Recording Tests
# ---------------------------------------------------------------------------

class TestAttemptRecording:
    """Tests for retry attempt recording in task_retries table."""

    @pytest.mark.asyncio
    async def test_record_attempt_creates_entry(
        self, retry_engine: RetryEngine
    ) -> None:
        """Test that record_attempt creates a task_retries entry."""
        record = await retry_engine.record_attempt(
            job_id=str(uuid.uuid4()),
            stage_name="image_generation",
            attempt_number=2,
            failure_type="transient",
            error_message="ComfyUI timeout",
            retry_after_seconds=30.0,
        )

        assert isinstance(record, RetryAttemptRecord)
        assert record.attempt_number == 2
        assert record.failure_type == "transient"
        assert record.retry_after_seconds == 30.0

    @pytest.mark.asyncio
    async def test_record_attempt_with_traceback(
        self, retry_engine: RetryEngine
    ) -> None:
        """Test attempt recording with full traceback."""
        record = await retry_engine.record_attempt(
            job_id=str(uuid.uuid4()),
            stage_name="video_generation",
            attempt_number=1,
            failure_type="resource",
            error_message="CUDA out of memory",
            error_traceback="Traceback...\nRuntimeError: CUDA OOM",
            retry_after_seconds=30.0,
        )

        assert record.error_traceback == "Traceback...\nRuntimeError: CUDA OOM"
        assert record.failure_type == "resource"
