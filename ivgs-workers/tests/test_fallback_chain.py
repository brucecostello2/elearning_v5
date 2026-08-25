"""
IVGS v5 — Fallback Chain Tests
========================================

Tests for FallbackChainService per §6.3 Table 6-6.

Test coverage:
- Full chain execution L1→L2→L3→L4
- Per-scene-type policy loading
- Successful fallback at each level
- DLQ routing when all levels exhausted
- Title card skip of L1 (ai_video)
- Individual strategy execution
- Policy cache and database loading
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

# WP-32.3: was `ivgs_workers.services.fallback_chain`. There is no `ivgs_workers`
# package anywhere in the tree or on the path -- the name appears in
# pyproject's known-first-party and in mypy overrides, and in
# tasks/periodic_tasks.py, but the directory is `ivgs-workers` (hyphen),
# which is not an importable module name. The modules themselves are real
# and live at `services/fallback_chain.py`.
from services.fallback_chain import (
    DEFAULT_FALLBACK_POLICIES,
    FallbackChainService,
    FallbackLevel,
    FallbackStrategy,
    SceneType,
)

# WP-53 (P2.50). Imported from the REAL module, so the assertions below compare
# enum identity rather than whatever an AsyncMock happened to record. A mock
# accepts a wrong category, a string, or a stub silently -- which is how the
# broken `ivgs_workers.services.dlq_service` import survived: every test that
# reached the DLQ hand-off was asserting `assert_called_once()` and nothing about
# what was called with.
from services.dlq_service import FailureCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_session_factory() -> AsyncMock:
    """Create a mock async database session factory."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    factory = AsyncMock(return_value=session)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.fixture
def mock_dlq_service() -> AsyncMock:
    """Create a mock DLQ service."""
    service = AsyncMock()
    service.send_to_dlq = AsyncMock()
    return service


@pytest.fixture
def mock_motion_graphics() -> AsyncMock:
    """Create a mock motion graphics service."""
    service = AsyncMock()
    service.apply_ken_burns = AsyncMock(
        return_value={"asset_id": str(uuid.uuid4())}
    )
    service.apply_zoom_pan = AsyncMock(
        return_value={"asset_id": str(uuid.uuid4())}
    )
    return service


@pytest.fixture
def mock_media_dispatch() -> AsyncMock:
    """Create a mock media generation dispatch function."""
    dispatch = AsyncMock(
        return_value={"asset_id": str(uuid.uuid4())}
    )
    return dispatch


@pytest.fixture
def fallback_service(
    mock_db_session_factory: AsyncMock,
    mock_dlq_service: AsyncMock,
    mock_motion_graphics: AsyncMock,
    mock_media_dispatch: AsyncMock,
) -> FallbackChainService:
    """Create a FallbackChainService with mock dependencies."""
    service = FallbackChainService(
        db_session_factory=mock_db_session_factory,
        dlq_service=mock_dlq_service,
        motion_graphics_service=mock_motion_graphics,
        media_generation_dispatch=mock_media_dispatch,
    )
    # Pre-load default policies
    service._policies_cache = dict(DEFAULT_FALLBACK_POLICIES)
    return service


# ---------------------------------------------------------------------------
# Default Policy Tests
# ---------------------------------------------------------------------------

class TestFallbackPolicies:
    """Tests for fallback policy configuration per Table 6-6."""

    def test_action_scene_chain(self) -> None:
        """Action scenes: L1=ai_video, L2=animated_still, L3=zoom_pan, L4=static."""
        policy = DEFAULT_FALLBACK_POLICIES[SceneType.ACTION]
        assert policy.level_1_strategy == FallbackStrategy.AI_VIDEO
        assert policy.level_2_strategy == FallbackStrategy.ANIMATED_STILL
        assert policy.level_3_strategy == FallbackStrategy.ZOOM_PAN
        assert policy.level_4_strategy == FallbackStrategy.STATIC_IMAGE

    def test_title_card_skips_ai_video(self) -> None:
        """Title cards start at animated_still (no AI video)."""
        policy = DEFAULT_FALLBACK_POLICIES[SceneType.TITLE_CARD]
        assert policy.level_1_strategy == FallbackStrategy.ANIMATED_STILL
        assert policy.level_2_strategy == FallbackStrategy.ZOOM_PAN
        assert policy.level_3_strategy == FallbackStrategy.STATIC_IMAGE
        assert policy.level_4_strategy == FallbackStrategy.STATIC_IMAGE

    def test_all_scene_types_have_policies(self) -> None:
        """All four scene types must have default policies."""
        for scene_type in SceneType:
            assert scene_type in DEFAULT_FALLBACK_POLICIES


# ---------------------------------------------------------------------------
# Chain Execution Tests
# ---------------------------------------------------------------------------

class TestFallbackChainExecution:
    """Tests for fallback chain execution."""

    @pytest.mark.asyncio
    async def test_l1_success_stops_chain(
        self, fallback_service: FallbackChainService
    ) -> None:
        """L1 success should return immediately without trying L2–L4."""
        result = await fallback_service.execute_fallback_chain(
            job_id=str(uuid.uuid4()),
            scene_id=str(uuid.uuid4()),
            scene_type=SceneType.ACTION,
            original_prompt="A dynamic action scene",
        )

        assert result.success is True
        assert result.final_level == FallbackLevel.L1
        assert result.final_strategy == FallbackStrategy.AI_VIDEO
        assert len(result.attempts) == 1
        assert result.routed_to_dlq is False

    @pytest.mark.asyncio
    async def test_l1_fails_l2_succeeds(
        self,
        fallback_service: FallbackChainService,
        mock_media_dispatch: AsyncMock,
        mock_motion_graphics: AsyncMock,
    ) -> None:
        """L1 failure should cascade to L2 (Ken Burns)."""
        # L1 (ai_video) fails
        mock_media_dispatch.side_effect = [
            RuntimeError("CogVideoX timeout"),
            {"asset_id": str(uuid.uuid4())},  # image for L2
        ]

        result = await fallback_service.execute_fallback_chain(
            job_id=str(uuid.uuid4()),
            scene_id=str(uuid.uuid4()),
            scene_type=SceneType.ACTION,
            original_prompt="A dramatic scene",
        )

        assert result.success is True
        assert result.final_level == FallbackLevel.L2
        assert len(result.attempts) == 2

    @pytest.mark.asyncio
    async def test_all_levels_fail_routes_to_dlq(
        self,
        fallback_service: FallbackChainService,
        mock_media_dispatch: AsyncMock,
        mock_motion_graphics: AsyncMock,
        mock_dlq_service: AsyncMock,
    ) -> None:
        """All L1–L4 failures should route to DLQ."""
        mock_media_dispatch.side_effect = RuntimeError("Generation failed")
        mock_motion_graphics.apply_ken_burns.side_effect = RuntimeError("Ken Burns failed")
        mock_motion_graphics.apply_zoom_pan.side_effect = RuntimeError("Pan/zoom failed")

        result = await fallback_service.execute_fallback_chain(
            job_id=str(uuid.uuid4()),
            scene_id=str(uuid.uuid4()),
            scene_type=SceneType.ACTION,
            original_prompt="A failing scene",
        )

        assert result.success is False
        assert result.routed_to_dlq is True
        assert len(result.attempts) == 4
        mock_dlq_service.send_to_dlq.assert_called_once()

    @pytest.mark.asyncio
    async def test_dlq_receives_the_exhausted_chain_message(
        self,
        fallback_service: FallbackChainService,
        mock_media_dispatch: AsyncMock,
        mock_motion_graphics: AsyncMock,
        mock_dlq_service: AsyncMock,
    ) -> None:
        """The DLQ gets the MESSAGE, not just a call.

        WP-53 (P2.50). `test_all_levels_fail_routes_to_dlq` asserted
        `send_to_dlq.assert_called_once()` and stopped there, so it could not
        tell a correct hand-off from a hand-off that named the wrong queue,
        dropped the scene id, or passed a stubbed `FailureCategory` that an
        `AsyncMock` invented on attribute access. The import that fed it
        (`from ivgs_workers.services.dlq_service import FailureCategory`) had
        been raising `ModuleNotFoundError` on this exact path for as long as it
        has existed, and no assertion in this file could see that either --
        the raise happened before `send_to_dlq`, so the sibling test failed with
        an import error rather than an assertion error, which reads as
        environment noise.

        This pins the payload, and it pins `FailureCategory.EXTERNAL` by
        IDENTITY against the real enum -- which is only importable if the module
        path is right.
        """
        job_id = str(uuid.uuid4())
        scene_id = str(uuid.uuid4())

        mock_media_dispatch.side_effect = RuntimeError("Generation failed")
        mock_motion_graphics.apply_ken_burns.side_effect = RuntimeError("Ken Burns failed")
        mock_motion_graphics.apply_zoom_pan.side_effect = RuntimeError("Pan/zoom failed")

        result = await fallback_service.execute_fallback_chain(
            job_id=job_id,
            scene_id=scene_id,
            scene_type=SceneType.ACTION,
            original_prompt="A failing scene",
            original_queue="gpu_video",
        )

        assert result.routed_to_dlq is True
        kwargs = mock_dlq_service.send_to_dlq.await_args.kwargs

        # The queue the work came off, so a replay goes back where it belongs.
        assert kwargs["original_queue"] == "gpu_video"
        assert kwargs["task_name"] == "media_generation_task"

        # Enough to reconstruct and replay the scene.
        assert kwargs["task_kwargs"]["job_id"] == job_id
        assert kwargs["task_kwargs"]["scene_id"] == scene_id

        # Why it is here, in terms an operator can triage.
        assert kwargs["exception_type"] == "FallbackChainExhausted"
        assert scene_id in kwargs["exception_message"]
        assert kwargs["retry_count_exhausted"] == 4

        # The real enum member from the real module. `is`, not `==`: an
        # AsyncMock attribute would satisfy equality against itself and prove
        # nothing about the import.
        assert kwargs["failure_category"] is FailureCategory.EXTERNAL

    @pytest.mark.asyncio
    async def test_start_from_l2(
        self,
        fallback_service: FallbackChainService,
        mock_motion_graphics: AsyncMock,
    ) -> None:
        """Chain can start from L2 (skip L1)."""
        result = await fallback_service.execute_fallback_chain(
            job_id=str(uuid.uuid4()),
            scene_id=str(uuid.uuid4()),
            scene_type=SceneType.ACTION,
            original_prompt="A scene",
            image_asset_id=str(uuid.uuid4()),
            start_level=FallbackLevel.L2,
        )

        assert result.success is True
        assert result.final_level == FallbackLevel.L2

    @pytest.mark.asyncio
    async def test_existing_image_used_for_l4(
        self,
        fallback_service: FallbackChainService,
        mock_media_dispatch: AsyncMock,
        mock_motion_graphics: AsyncMock,
    ) -> None:
        """L4 should return existing image asset without generation."""
        mock_media_dispatch.side_effect = RuntimeError("L1 fail")
        mock_motion_graphics.apply_ken_burns.side_effect = RuntimeError("L2 fail")
        mock_motion_graphics.apply_zoom_pan.side_effect = RuntimeError("L3 fail")

        existing_image = str(uuid.uuid4())
        result = await fallback_service.execute_fallback_chain(
            job_id=str(uuid.uuid4()),
            scene_id=str(uuid.uuid4()),
            scene_type=SceneType.ACTION,
            original_prompt="A scene",
            image_asset_id=existing_image,
        )

        assert result.success is True
        assert result.final_level == FallbackLevel.L4
        assert result.output_asset_id == existing_image
