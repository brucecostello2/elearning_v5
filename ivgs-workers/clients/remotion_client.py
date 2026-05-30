"""
IVGS v5 — Remotion Animation Renderer Client
================================================

HTTP client for the Remotion render server (node-06) per §7.1.8.

Remotion capabilities:
- Lower-third overlays (scene title / key terms)
- Animated title cards
- Data visualization animations
- Scene transition graphics
- Ken Burns animated stills (L2 fallback per §6.3)

API contract (self-hosted Remotion render server):
- POST /render       — submit render job
- GET  /status/{id}  — poll render status
- GET  /result/{id}  — download rendered asset (MP4 or transparent WebM)
- GET  /health       — health check
- GET  /compositions — list available compositions

Rendered assets are transparent overlays (WebM VP9 with alpha) or opaque
MP4 clips depending on composition type. All stored in SeaweedFS at /ivgs/animations/.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
import os
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger("ivgs.remotion_client")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RemotionError(Exception):
    """Base exception for Remotion client errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        render_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.render_id = render_id


class RemotionConnectionError(RemotionError):
    """Remotion server unreachable."""


class RemotionTimeoutError(RemotionError):
    """Remotion render timed out."""


class RemotionRenderError(RemotionError):
    """Remotion render failed."""


class RemotionDownloadError(RemotionError):
    """Failed to download rendered asset from Remotion."""


# ---------------------------------------------------------------------------
# Enums and config
# ---------------------------------------------------------------------------

class CompositionType(str, Enum):
    """Available Remotion compositions."""
    LOWER_THIRD = "LowerThird"
    TITLE_CARD = "TitleCard"
    DATA_VIS = "DataVisualization"
    TRANSITION = "SceneTransition"
    KEN_BURNS = "KenBurns"
    ANIMATED_TITLE = "AnimatedTitle"
    KEY_TERM = "KeyTermOverlay"
    PROGRESS_BAR = "ProgressBar"


class OutputFormat(str, Enum):
    """Render output formats."""
    MP4 = "mp4"
    WEBM = "webm"
    PNG_SEQUENCE = "png_sequence"


@dataclass(frozen=True)
class RemotionRenderParams:
    """Parameters for a Remotion render job."""
    composition_id: CompositionType
    input_props: Dict[str, Any]
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration_in_frames: int = 150  # 5s at 30fps
    output_format: OutputFormat = OutputFormat.WEBM
    codec: str = "vp9"
    pixel_format: str = "yuva420p"  # Alpha channel for overlays
    crf: int = 18
    concurrency: int = 50  # Remotion parallel rendering threads
    image_format: str = "png"  # Frame format for rendering pipeline
    scale: float = 1.0

    def compute_hash(self) -> str:
        """SHA-256 hash for idempotency."""
        data = {
            "composition_id": self.composition_id.value,
            "input_props": self.input_props,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_in_frames": self.duration_in_frames,
            "output_format": self.output_format.value,
        }
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class RemotionRenderResult:
    """Result from a Remotion render."""
    render_id: str
    asset_data: bytes
    composition_id: str
    width: int
    height: int
    fps: int
    duration_seconds: float
    file_size_bytes: int
    output_format: str
    has_alpha: bool
    render_time_seconds: float
    params_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Default lower-third props
# ---------------------------------------------------------------------------

DEFAULT_LOWER_THIRD_PROPS: Dict[str, Any] = {
    "title": "",
    "subtitle": "",
    "backgroundColor": "rgba(0, 0, 0, 0.7)",
    "textColor": "#FFFFFF",
    "accentColor": "#4A90D9",
    "fontFamily": "Noto Sans",
    "fontSize": 36,
    "animationDuration": 30,  # frames
    "holdDuration": 120,      # frames
    "position": "bottom",
    "height": 0.2,           # 20% of frame height
    "padding": 20,
}

DEFAULT_TITLE_CARD_PROPS: Dict[str, Any] = {
    "title": "",
    "subtitle": "",
    "backgroundColor": "#1A1A2E",
    "textColor": "#FFFFFF",
    "accentColor": "#E94560",
    "fontFamily": "Noto Sans",
    "titleFontSize": 72,
    "subtitleFontSize": 36,
    "animationType": "fade_scale",
    "animationDuration": 30,
}


# ---------------------------------------------------------------------------
# RemotionClient
# ---------------------------------------------------------------------------

class RemotionClient:
    """
    Async HTTP client for the Remotion render server on node-06.

    Lifecycle:
    1. POST /render with composition + props
    2. Poll GET /status/{render_id} until complete
    3. Download rendered asset via GET /result/{render_id}
    4. Return raw asset bytes + metadata

    Supports transparent WebM overlays for compositing in FFmpeg.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
        max_concurrent: int = 4,
    ):
        self._base_url = base_url or os.environ["REMOTION_URL"]
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._max_concurrent = max_concurrent
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self._timeout,
                    write=30.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_connections=self._max_concurrent,
                    max_keepalive_connections=2,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("remotion_client_closed")
        self._client = None

    # ----- Health check -----

    async def check_health(self) -> bool:
        """Check Remotion server health."""
        try:
            client = await self._get_client()
            resp = await client.get("/health", timeout=5.0)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("remotion_health_check_failed", error=str(e))
            return False

    async def list_compositions(self) -> List[str]:
        """List available Remotion compositions."""
        try:
            client = await self._get_client()
            resp = await client.get("/compositions", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return [c.get("id", "") for c in data.get("compositions", [])]
            return []
        except Exception as e:
            logger.warning("remotion_list_compositions_failed", error=str(e))
            return []

    # ----- Core rendering -----

    async def render(
        self,
        params: RemotionRenderParams,
    ) -> RemotionRenderResult:
        """
        Render a Remotion composition.

        1. Submit render job
        2. Poll for completion
        3. Download and return rendered asset bytes
        """
        start_time = time.monotonic()
        params_hash = params.compute_hash()
        render_id = str(uuid.uuid4())

        log = logger.bind(
            render_id=render_id,
            composition=params.composition_id.value,
            width=params.width,
            height=params.height,
            duration_frames=params.duration_in_frames,
            params_hash=params_hash[:12],
        )

        client = await self._get_client()

        # 1. Submit render job
        payload = {
            "render_id": render_id,
            "composition_id": params.composition_id.value,
            "input_props": params.input_props,
            "width": params.width,
            "height": params.height,
            "fps": params.fps,
            "duration_in_frames": params.duration_in_frames,
            "output_format": params.output_format.value,
            "codec": params.codec,
            "pixel_format": params.pixel_format,
            "crf": params.crf,
            "concurrency": params.concurrency,
            "image_format": params.image_format,
            "scale": params.scale,
        }

        try:
            submit_resp = await client.post("/render", json=payload)
        except httpx.ConnectError as e:
            raise RemotionConnectionError(
                f"Cannot connect to Remotion at {self._base_url}: {e}",
                render_id=render_id,
            ) from e
        except httpx.TimeoutException as e:
            raise RemotionTimeoutError(
                f"Remotion submit timed out: {e}",
                render_id=render_id,
            ) from e

        if submit_resp.status_code not in (200, 201, 202):
            raise RemotionRenderError(
                f"Remotion submit failed: HTTP {submit_resp.status_code} — {submit_resp.text}",
                status_code=submit_resp.status_code,
                render_id=render_id,
            )

        server_data = submit_resp.json()
        server_render_id = server_data.get("render_id", render_id)
        log = log.bind(server_render_id=server_render_id)

        # 2. Poll for completion
        deadline = start_time + self._timeout
        last_status = "unknown"
        last_progress = 0.0

        while time.monotonic() < deadline:
            try:
                status_resp = await client.get(
                    f"/status/{server_render_id}",
                    timeout=10.0,
                )
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    last_status = status_data.get("status", "unknown")
                    last_progress = status_data.get("progress", 0.0)

                    if last_status == "completed":
                        log.info(
                            "remotion_render_completed",
                            progress=last_progress,
                        )
                        break
                    elif last_status == "failed":
                        error_msg = status_data.get("error", "Unknown render error")
                        raise RemotionRenderError(
                            f"Remotion render failed: {error_msg}",
                            render_id=server_render_id,
                        )

                    if last_progress > 0:
                        log.debug(
                            "remotion_render_progress",
                            progress=round(last_progress, 2),
                        )

            except (httpx.ConnectError, httpx.TimeoutException):
                pass  # Transient polling error; continue

            import asyncio
            await asyncio.sleep(self._poll_interval)

        else:
            raise RemotionTimeoutError(
                f"Remotion render timed out after {self._timeout}s "
                f"(last status: {last_status}, progress: {last_progress:.1%})",
                render_id=server_render_id,
            )

        # 3. Download rendered asset
        try:
            result_resp = await client.get(
                f"/result/{server_render_id}",
                timeout=60.0,
            )
        except httpx.TimeoutException as e:
            raise RemotionDownloadError(
                f"Remotion result download timed out: {e}",
                render_id=server_render_id,
            ) from e

        if result_resp.status_code != 200:
            raise RemotionDownloadError(
                f"Remotion result download failed: HTTP {result_resp.status_code}",
                status_code=result_resp.status_code,
                render_id=server_render_id,
            )

        asset_data = result_resp.content
        elapsed = time.monotonic() - start_time
        duration_seconds = params.duration_in_frames / params.fps
        has_alpha = params.pixel_format in ("yuva420p", "rgba")

        log.info(
            "remotion_render_success",
            elapsed=round(elapsed, 2),
            asset_size=len(asset_data),
            has_alpha=has_alpha,
        )

        return RemotionRenderResult(
            render_id=server_render_id,
            asset_data=asset_data,
            composition_id=params.composition_id.value,
            width=params.width,
            height=params.height,
            fps=params.fps,
            duration_seconds=duration_seconds,
            file_size_bytes=len(asset_data),
            output_format=params.output_format.value,
            has_alpha=has_alpha,
            render_time_seconds=round(elapsed, 2),
            params_hash=params_hash,
            metadata={
                "input_props": params.input_props,
                "codec": params.codec,
                "crf": params.crf,
            },
        )

    # ----- Convenience methods -----

    async def render_lower_third(
        self,
        title: str,
        subtitle: str = "",
        duration_seconds: float = 5.0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        **extra_props: Any,
    ) -> RemotionRenderResult:
        """Render a lower-third overlay for scene composition."""
        props = {**DEFAULT_LOWER_THIRD_PROPS, **extra_props}
        props["title"] = title
        props["subtitle"] = subtitle

        params = RemotionRenderParams(
            composition_id=CompositionType.LOWER_THIRD,
            input_props=props,
            width=width,
            height=height,
            fps=fps,
            duration_in_frames=int(duration_seconds * fps),
            output_format=OutputFormat.WEBM,
            codec="vp9",
            pixel_format="yuva420p",
        )
        return await self.render(params)

    async def render_title_card(
        self,
        title: str,
        subtitle: str = "",
        duration_seconds: float = 5.0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        **extra_props: Any,
    ) -> RemotionRenderResult:
        """Render a full-frame title card."""
        props = {**DEFAULT_TITLE_CARD_PROPS, **extra_props}
        props["title"] = title
        props["subtitle"] = subtitle

        params = RemotionRenderParams(
            composition_id=CompositionType.TITLE_CARD,
            input_props=props,
            width=width,
            height=height,
            fps=fps,
            duration_in_frames=int(duration_seconds * fps),
            output_format=OutputFormat.MP4,
            codec="h264",
            pixel_format="yuv420p",
        )
        return await self.render(params)

    async def render_ken_burns(
        self,
        image_url: str,
        duration_seconds: float = 8.0,
        zoom_start: float = 1.0,
        zoom_end: float = 1.3,
        pan_direction: str = "left_to_right",
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ) -> RemotionRenderResult:
        """Render Ken Burns pan/zoom effect on a static image (L2 fallback §6.3)."""
        props = {
            "imageUrl": image_url,
            "zoomStart": zoom_start,
            "zoomEnd": zoom_end,
            "panDirection": pan_direction,
            "easing": "easeInOutCubic",
        }

        params = RemotionRenderParams(
            composition_id=CompositionType.KEN_BURNS,
            input_props=props,
            width=width,
            height=height,
            fps=fps,
            duration_in_frames=int(duration_seconds * fps),
            output_format=OutputFormat.MP4,
            codec="h264",
            pixel_format="yuv420p",
        )
        return await self.render(params)

    async def render_batch(
        self,
        params_list: List[RemotionRenderParams],
        max_parallel: int = 4,
    ) -> List[RemotionRenderResult]:
        """Render multiple compositions with bounded concurrency."""
        import asyncio

        semaphore = asyncio.Semaphore(max_parallel)
        results: List[Optional[RemotionRenderResult]] = [None] * len(params_list)

        async def _render(idx: int, params: RemotionRenderParams) -> None:
            async with semaphore:
                results[idx] = await self.render(params)

        tasks = [_render(i, p) for i, p in enumerate(params_list)]
        await asyncio.gather(*tasks, return_exceptions=False)

        return [r for r in results if r is not None]
