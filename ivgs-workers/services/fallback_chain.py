"""
IVGS v5 — Fallback Chain Service
========================================

L1→L2→L3→L4 fallback logic per §6.3 Table 6-6.

Fallback levels:
- L1 — AI Video:      CogVideoX 5B or Wan2.1 video clip generation
- L2 — Animated Still: Ken Burns pan/zoom on generated image (MotionGraphicsService)
- L3 — Static Pan/Zoom: Simple FFmpeg zoom and pan on static image
- L4 — Static Image:  Static image only, no motion (last resort before DLQ)

Configuration source: fallback_policies table (Table 23)
  scene_type, level_1_strategy, level_2_strategy, level_3_strategy, level_4_strategy

Configurable per scene type:
- action:       L1=ai_video, L2=animated_still, L3=zoom_pan, L4=static_image
- talking_head: L1=ai_video, L2=animated_still, L3=zoom_pan, L4=static_image
- broll:        L1=ai_video, L2=animated_still, L3=zoom_pan, L4=static_image
- title_card:   L1=animated_still, L2=zoom_pan, L3=static_image, L4=static_image

Integration:
- RetryEngine calls trigger_fallback() when exhaustion_action is FALLBACK_AND_DLQ
- Each fallback level is itself retryable (1 retry per level)
- If L4 fails → DLQ
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FallbackLevel(str, Enum):
    """Fallback levels per §6.3 Table 6-6."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class FallbackStrategy(str, Enum):
    """Fallback strategy names per Table 6-6."""

    AI_VIDEO = "ai_video"
    ANIMATED_STILL = "animated_still"
    ZOOM_PAN = "zoom_pan"
    STATIC_IMAGE = "static_image"


class SceneType(str, Enum):
    """Scene types for fallback policy lookup per Table 23."""

    ACTION = "action"
    TALKING_HEAD = "talking_head"
    BROLL = "broll"
    TITLE_CARD = "title_card"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class FallbackPolicy(BaseModel):
    """Fallback chain configuration per scene type from Table 23."""

    scene_type: SceneType
    level_1_strategy: FallbackStrategy
    level_2_strategy: FallbackStrategy
    level_3_strategy: FallbackStrategy
    level_4_strategy: FallbackStrategy

    def get_strategy(self, level: FallbackLevel) -> FallbackStrategy:
        """
        Get the fallback strategy for a specific level.

        Args:
            level: Fallback level L1–L4.

        Returns:
            FallbackStrategy for the specified level.
        """
        mapping = {
            FallbackLevel.L1: self.level_1_strategy,
            FallbackLevel.L2: self.level_2_strategy,
            FallbackLevel.L3: self.level_3_strategy,
            FallbackLevel.L4: self.level_4_strategy,
        }
        return mapping[level]


class FallbackAttempt(BaseModel):
    """Record of a single fallback attempt."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    scene_id: str
    scene_type: SceneType
    level: FallbackLevel
    strategy: FallbackStrategy
    success: bool = False
    error_message: str = ""
    output_asset_id: Optional[str] = None
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0


class FallbackResult(BaseModel):
    """Result of a complete fallback chain execution."""

    job_id: str
    scene_id: str
    scene_type: SceneType
    success: bool
    final_level: FallbackLevel
    final_strategy: FallbackStrategy
    output_asset_id: Optional[str] = None
    attempts: list[FallbackAttempt] = Field(default_factory=list)
    routed_to_dlq: bool = False


# ---------------------------------------------------------------------------
# Default Policies (matches fallback_policies.yaml / Table 6-6)
# ---------------------------------------------------------------------------

DEFAULT_FALLBACK_POLICIES: dict[SceneType, FallbackPolicy] = {
    SceneType.ACTION: FallbackPolicy(
        scene_type=SceneType.ACTION,
        level_1_strategy=FallbackStrategy.AI_VIDEO,
        level_2_strategy=FallbackStrategy.ANIMATED_STILL,
        level_3_strategy=FallbackStrategy.ZOOM_PAN,
        level_4_strategy=FallbackStrategy.STATIC_IMAGE,
    ),
    SceneType.TALKING_HEAD: FallbackPolicy(
        scene_type=SceneType.TALKING_HEAD,
        level_1_strategy=FallbackStrategy.AI_VIDEO,
        level_2_strategy=FallbackStrategy.ANIMATED_STILL,
        level_3_strategy=FallbackStrategy.ZOOM_PAN,
        level_4_strategy=FallbackStrategy.STATIC_IMAGE,
    ),
    SceneType.BROLL: FallbackPolicy(
        scene_type=SceneType.BROLL,
        level_1_strategy=FallbackStrategy.AI_VIDEO,
        level_2_strategy=FallbackStrategy.ANIMATED_STILL,
        level_3_strategy=FallbackStrategy.ZOOM_PAN,
        level_4_strategy=FallbackStrategy.STATIC_IMAGE,
    ),
    SceneType.TITLE_CARD: FallbackPolicy(
        scene_type=SceneType.TITLE_CARD,
        level_1_strategy=FallbackStrategy.ANIMATED_STILL,
        level_2_strategy=FallbackStrategy.ZOOM_PAN,
        level_3_strategy=FallbackStrategy.STATIC_IMAGE,
        level_4_strategy=FallbackStrategy.STATIC_IMAGE,
    ),
}


# ---------------------------------------------------------------------------
# Fallback Chain Service
# ---------------------------------------------------------------------------

class FallbackChainService:
    """
    Four-level media generation fallback chain per §6.3 Table 6-6.

    When a media generation task fails after retry exhaustion with
    exhaustion_action=FALLBACK_AND_DLQ, this service executes the
    configured fallback chain for the scene type:

    1. Try L1 strategy (ai_video)
    2. On L1 failure → try L2 strategy (animated_still / Ken Burns)
    3. On L2 failure → try L3 strategy (zoom_pan)
    4. On L3 failure → try L4 strategy (static_image)
    5. On L4 failure → route to DLQ

    Each level gets one retry attempt. Configuration from fallback_policies
    table (Table 23) allows per-scene-type customization.

    Dependencies:
    - MotionGraphicsService: Ken Burns + pan/zoom for L2/L3
    - ComfyUI client: Image generation for L4 static recovery
    - CogVideoX / Wan2.1 clients: L1 AI video generation
    - DLQService: L4 exhaustion routing
    """

    # Fallback level progression order
    LEVEL_ORDER: list[FallbackLevel] = [
        FallbackLevel.L1,
        FallbackLevel.L2,
        FallbackLevel.L3,
        FallbackLevel.L4,
    ]

    def __init__(
        self,
        db_session_factory: Any,
        dlq_service: Any,
        motion_graphics_service: Any,
        media_generation_dispatch: Any,
    ) -> None:
        """
        Initialize fallback chain service.

        Args:
            db_session_factory: Async SQLAlchemy session factory for
                fallback_policies table access.
            dlq_service: DLQService instance for L4 exhaustion routing.
            motion_graphics_service: MotionGraphicsService for L2/L3
                Ken Burns and pan/zoom effects.
            media_generation_dispatch: Callable to dispatch media generation
                tasks (L1 AI video, L4 static image recovery).
        """
        self._db_session_factory = db_session_factory
        self._dlq_service = dlq_service
        self._motion_graphics = motion_graphics_service
        self._media_dispatch = media_generation_dispatch
        self._policies_cache: dict[SceneType, FallbackPolicy] = {}
        self._log = logger.bind(service="fallback_chain")

    async def load_policies(self) -> None:
        """
        Load fallback policies from the database (Table 23).

        Falls back to DEFAULT_FALLBACK_POLICIES if database is empty
        or unreachable.
        """
        try:
            async with self._db_session_factory() as session:
                from sqlalchemy import select
                from ivgs_api.app.models import FallbackPolicyModel

                result = await session.execute(
                    select(FallbackPolicyModel.__table__)
                )
                rows = result.fetchall()

                if rows:
                    for row in rows:
                        try:
                            scene_type = SceneType(row.scene_type)
                            policy = FallbackPolicy(
                                scene_type=scene_type,
                                level_1_strategy=FallbackStrategy(
                                    row.level_1_strategy
                                ),
                                level_2_strategy=FallbackStrategy(
                                    row.level_2_strategy
                                ),
                                level_3_strategy=FallbackStrategy(
                                    row.level_3_strategy
                                ),
                                level_4_strategy=FallbackStrategy(
                                    row.level_4_strategy
                                ),
                            )
                            self._policies_cache[scene_type] = policy
                        except (ValueError, KeyError) as exc:
                            self._log.warning(
                                "invalid_fallback_policy_row",
                                scene_type=getattr(row, "scene_type", None),
                                error=str(exc),
                            )

                    self._log.info(
                        "fallback_policies_loaded_from_db",
                        count=len(self._policies_cache),
                    )
                    return

        except Exception as exc:
            self._log.warning(
                "fallback_policies_db_load_failed",
                error=str(exc),
            )

        # Fall back to defaults
        self._policies_cache = dict(DEFAULT_FALLBACK_POLICIES)
        self._log.info(
            "fallback_policies_loaded_defaults",
            count=len(self._policies_cache),
        )

    def get_policy(self, scene_type: SceneType) -> FallbackPolicy:
        """
        Get fallback policy for a scene type.

        Args:
            scene_type: Scene type per Table 23.

        Returns:
            FallbackPolicy: Configured chain for this scene type.
        """
        if scene_type in self._policies_cache:
            return self._policies_cache[scene_type]

        # Default to ACTION policy if scene type not configured
        default = DEFAULT_FALLBACK_POLICIES.get(
            scene_type,
            DEFAULT_FALLBACK_POLICIES[SceneType.ACTION],
        )
        self._log.warning(
            "fallback_policy_not_cached",
            scene_type=scene_type.value,
            using_default=True,
        )
        return default

    async def execute_fallback_chain(
        self,
        *,
        job_id: str,
        scene_id: str,
        scene_type: SceneType,
        original_prompt: str,
        image_asset_id: str | None = None,
        start_level: FallbackLevel = FallbackLevel.L1,
        original_error: str = "",
        original_queue: str = "gpu_video",
        task_name: str = "",
        task_kwargs: dict[str, Any] | None = None,
    ) -> FallbackResult:
        """
        Execute the fallback chain for a failed media generation.

        Iterates through fallback levels starting from start_level.
        Each level attempts the configured strategy once. On failure,
        advances to the next level. If L4 fails, routes to DLQ.

        Args:
            job_id: Parent render job UUID.
            scene_id: Scene UUID for which media generation failed.
            scene_type: Scene type for policy lookup.
            original_prompt: The generation prompt for recovery attempts.
            image_asset_id: Existing image asset for L2/L3 fallbacks.
            start_level: Level to start from (default L1).
            original_error: Error message from the original failure.
            original_queue: Celery queue of the original task.
            task_name: Original Celery task name.
            task_kwargs: Original task kwargs (for DLQ entry if needed).

        Returns:
            FallbackResult: Outcome of the chain with attempt history.
        """
        policy = self.get_policy(scene_type)
        attempts: list[FallbackAttempt] = []
        start_index = self.LEVEL_ORDER.index(start_level)

        self._log.info(
            "fallback_chain_started",
            job_id=job_id,
            scene_id=scene_id,
            scene_type=scene_type.value,
            start_level=start_level.value,
            original_error=original_error[:200],
        )

        for level in self.LEVEL_ORDER[start_index:]:
            strategy = policy.get_strategy(level)
            attempt = FallbackAttempt(
                job_id=job_id,
                scene_id=scene_id,
                scene_type=scene_type,
                level=level,
                strategy=strategy,
            )

            self._log.info(
                "fallback_level_attempting",
                job_id=job_id,
                scene_id=scene_id,
                level=level.value,
                strategy=strategy.value,
            )

            try:
                asset_id = await self._execute_strategy(
                    strategy=strategy,
                    job_id=job_id,
                    scene_id=scene_id,
                    prompt=original_prompt,
                    image_asset_id=image_asset_id,
                )

                now = datetime.now(timezone.utc)
                attempt.success = True
                attempt.output_asset_id = asset_id
                attempt.completed_at = now
                attempt.duration_seconds = (
                    now - attempt.started_at
                ).total_seconds()
                attempts.append(attempt)

                self._log.info(
                    "fallback_level_succeeded",
                    job_id=job_id,
                    scene_id=scene_id,
                    level=level.value,
                    strategy=strategy.value,
                    asset_id=asset_id,
                    duration_seconds=attempt.duration_seconds,
                )

                return FallbackResult(
                    job_id=job_id,
                    scene_id=scene_id,
                    scene_type=scene_type,
                    success=True,
                    final_level=level,
                    final_strategy=strategy,
                    output_asset_id=asset_id,
                    attempts=attempts,
                    routed_to_dlq=False,
                )

            except Exception as exc:
                now = datetime.now(timezone.utc)
                attempt.success = False
                attempt.error_message = str(exc)
                attempt.completed_at = now
                attempt.duration_seconds = (
                    now - attempt.started_at
                ).total_seconds()
                attempts.append(attempt)

                self._log.warning(
                    "fallback_level_failed",
                    job_id=job_id,
                    scene_id=scene_id,
                    level=level.value,
                    strategy=strategy.value,
                    error=str(exc),
                    duration_seconds=attempt.duration_seconds,
                )

        # All levels exhausted — route to DLQ
        self._log.error(
            "fallback_chain_exhausted",
            job_id=job_id,
            scene_id=scene_id,
            scene_type=scene_type.value,
            total_attempts=len(attempts),
        )

        from ivgs_workers.services.dlq_service import (
            FailureCategory,
        )

        await self._dlq_service.send_to_dlq(
            original_queue=original_queue,
            task_name=task_name or "media_generation_task",
            task_kwargs=task_kwargs or {
                "job_id": job_id,
                "scene_id": scene_id,
            },
            exception_type="FallbackChainExhausted",
            exception_message=(
                f"All fallback levels L1–L4 exhausted for "
                f"scene {scene_id} (type: {scene_type.value})"
            ),
            failure_category=FailureCategory.EXTERNAL,
            retry_count_exhausted=len(attempts),
        )

        return FallbackResult(
            job_id=job_id,
            scene_id=scene_id,
            scene_type=scene_type,
            success=False,
            final_level=FallbackLevel.L4,
            final_strategy=policy.get_strategy(FallbackLevel.L4),
            output_asset_id=None,
            attempts=attempts,
            routed_to_dlq=True,
        )

    # ------------------------------------------------------------------
    # Strategy Execution
    # ------------------------------------------------------------------

    async def _execute_strategy(
        self,
        *,
        strategy: FallbackStrategy,
        job_id: str,
        scene_id: str,
        prompt: str,
        image_asset_id: str | None = None,
    ) -> str:
        """
        Execute a single fallback strategy.

        Routes to the appropriate service based on strategy type:
        - ai_video → CogVideoX/Wan2.1 via media_generation_dispatch
        - animated_still → MotionGraphicsService Ken Burns
        - zoom_pan → MotionGraphicsService zoom/pan
        - static_image → ComfyUI image generation or existing image

        Args:
            strategy: Fallback strategy to execute.
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            prompt: Generation prompt.
            image_asset_id: Existing image for motion effects.

        Returns:
            Asset UUID of the generated/recovered media.

        Raises:
            RuntimeError: If strategy execution fails.
        """
        strategy_handlers = {
            FallbackStrategy.AI_VIDEO: self._execute_ai_video,
            FallbackStrategy.ANIMATED_STILL: self._execute_animated_still,
            FallbackStrategy.ZOOM_PAN: self._execute_zoom_pan,
            FallbackStrategy.STATIC_IMAGE: self._execute_static_image,
        }

        handler = strategy_handlers.get(strategy)
        if handler is None:
            raise RuntimeError(f"Unknown fallback strategy: {strategy.value}")

        return await handler(
            job_id=job_id,
            scene_id=scene_id,
            prompt=prompt,
            image_asset_id=image_asset_id,
        )

    async def _execute_ai_video(
        self,
        *,
        job_id: str,
        scene_id: str,
        prompt: str,
        image_asset_id: str | None = None,
    ) -> str:
        """
        L1 — AI Video generation via CogVideoX/Wan2.1 per Table 6-6.

        Dispatches to the media generation pipeline for video clip
        creation using the original prompt.

        Args:
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            prompt: CogVideoX/Wan2.1 compatible generation prompt.
            image_asset_id: Optional reference image for img2vid.

        Returns:
            Asset UUID of the generated video clip.

        Raises:
            RuntimeError: If video generation fails.
        """
        try:
            result = await self._media_dispatch(
                media_type="video_clip",
                job_id=job_id,
                scene_id=scene_id,
                prompt=prompt,
                image_asset_id=image_asset_id,
            )
            return result["asset_id"]
        except Exception as exc:
            raise RuntimeError(
                f"L1 AI video fallback failed: {exc}"
            ) from exc

    async def _execute_animated_still(
        self,
        *,
        job_id: str,
        scene_id: str,
        prompt: str,
        image_asset_id: str | None = None,
    ) -> str:
        """
        L2 — Ken Burns animated still per Table 6-6 and §7.1.8.

        Uses MotionGraphicsService to apply Ken Burns pan/zoom effect
        to an existing static image. If no image exists, generates one
        first via ComfyUI.

        Args:
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            prompt: Image generation prompt (if image needed).
            image_asset_id: Existing image to animate.

        Returns:
            Asset UUID of the animated still video.

        Raises:
            RuntimeError: If Ken Burns animation fails.
        """
        source_image_id = image_asset_id

        # If no image exists, generate one first
        if source_image_id is None:
            try:
                image_result = await self._media_dispatch(
                    media_type="image",
                    job_id=job_id,
                    scene_id=scene_id,
                    prompt=prompt,
                )
                source_image_id = image_result["asset_id"]
            except Exception as exc:
                raise RuntimeError(
                    f"L2 animated still — image generation failed: {exc}"
                ) from exc

        try:
            result = await self._motion_graphics.apply_ken_burns(
                image_asset_id=source_image_id,
                job_id=job_id,
                scene_id=scene_id,
                duration_seconds=6.0,
            )
            return result["asset_id"]
        except Exception as exc:
            raise RuntimeError(
                f"L2 animated still — Ken Burns failed: {exc}"
            ) from exc

    async def _execute_zoom_pan(
        self,
        *,
        job_id: str,
        scene_id: str,
        prompt: str,
        image_asset_id: str | None = None,
    ) -> str:
        """
        L3 — Static zoom/pan effect per Table 6-6.

        Uses MotionGraphicsService to apply simple FFmpeg zoom and
        pan effect to an existing static image.

        Args:
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            prompt: Image generation prompt (if image needed).
            image_asset_id: Existing image for zoom/pan.

        Returns:
            Asset UUID of the zoom/pan video.

        Raises:
            RuntimeError: If zoom/pan processing fails.
        """
        source_image_id = image_asset_id

        if source_image_id is None:
            try:
                image_result = await self._media_dispatch(
                    media_type="image",
                    job_id=job_id,
                    scene_id=scene_id,
                    prompt=prompt,
                )
                source_image_id = image_result["asset_id"]
            except Exception as exc:
                raise RuntimeError(
                    f"L3 zoom/pan — image generation failed: {exc}"
                ) from exc

        try:
            result = await self._motion_graphics.apply_zoom_pan(
                image_asset_id=source_image_id,
                job_id=job_id,
                scene_id=scene_id,
                duration_seconds=6.0,
            )
            return result["asset_id"]
        except Exception as exc:
            raise RuntimeError(
                f"L3 zoom/pan effect failed: {exc}"
            ) from exc

    async def _execute_static_image(
        self,
        *,
        job_id: str,
        scene_id: str,
        prompt: str,
        image_asset_id: str | None = None,
    ) -> str:
        """
        L4 — Static image (last resort) per Table 6-6.

        Returns the existing image asset if available, or generates
        a new static image via ComfyUI. No motion effects applied.

        Args:
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            prompt: Image generation prompt.
            image_asset_id: Existing image asset (returned directly).

        Returns:
            Asset UUID of the static image.

        Raises:
            RuntimeError: If no image available and generation fails.
        """
        if image_asset_id is not None:
            self._log.info(
                "l4_static_image_existing",
                job_id=job_id,
                scene_id=scene_id,
                asset_id=image_asset_id,
            )
            return image_asset_id

        try:
            result = await self._media_dispatch(
                media_type="image",
                job_id=job_id,
                scene_id=scene_id,
                prompt=prompt,
            )
            return result["asset_id"]
        except Exception as exc:
            raise RuntimeError(
                f"L4 static image generation failed: {exc}"
            ) from exc
