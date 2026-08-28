"""Client for ``ivgs-motion-renderer`` — the ``motion_graphics`` engine.

WP-IVGS-09 Task 1. **This module is also a defect being closed.**

``shared/providers/client_registry.py:453`` has named
``clients.motion_graphics_client.MotionGraphicsClient`` since WP-68 (2026-08-26)
and **the module did not exist**. It never raised, because ``client_path`` is a
declarative string the registry stores and never imports — so the Model Store
admin surface has been reporting a client for ``maths_motion`` that could not
have been constructed. Measured on 2026-08-28: ``resolve_client`` returns the
path, ``import`` of the path fails. Registering a client is a claim about what
IVGS can run; this file makes the claim true rather than deleting it, because
the renderer now exists.

WHAT IT TALKS TO
----------------

A small FastAPI service (``ivgs-motion-renderer/main.py``) wrapping the Pillow
reference rasteriser. CPU-only, no weights, no GPU. Endpoint comes from
``resolve_endpoint("motion_graphics")`` i.e. ``IVGS_MOTION_GRAPHICS_URL``, which
carries **no default** by deliberate WP-68 design: an unset variable raises
``EndpointResolutionError`` by name rather than silently resolving to some
other service that would answer 400.

THE REQUEST IS THE SCENE'S OWN PARAMETERS
-----------------------------------------

``render()`` takes the ``generation_params`` object a ``motion_graphics`` scene
stores and posts it unwrapped. There is no translation step, because a
translation step is a place for a parameter to be quietly dropped — the
storyboard asked for ``{"template": "place_value_split", "number": 23}`` and the
renderer is asked exactly that.
"""
from __future__ import annotations

from typing import Any, Dict

import httpx
import structlog

logger = structlog.get_logger(__name__)


class MotionGraphicsError(RuntimeError):
    """The renderer refused, failed, or could not be reached.

    One exception type, always carrying the renderer's own words. A caller that
    catches this must not substitute a picture — see ``MotionRenderResult``.
    """


class MotionRenderResult:
    """One rendered template: the MP4 bytes and what the renderer said about them.

    ``frames_digest`` is the sha256 the renderer computed over the PNG bytes of
    every frame. It is the determinism claim in a checkable form, and it is
    recorded on the asset so a later run can be compared against it without
    re-rendering.
    """

    __slots__ = ("data", "template", "frames", "fps", "duration_seconds",
                 "frames_digest", "build_ref")

    def __init__(
        self,
        *,
        data: bytes,
        template: str,
        frames: int,
        fps: int,
        duration_seconds: float,
        frames_digest: str,
        build_ref: str,
    ) -> None:
        self.data = data
        self.template = template
        self.frames = frames
        self.fps = fps
        self.duration_seconds = duration_seconds
        self.frames_digest = frames_digest
        self.build_ref = build_ref


class MotionGraphicsClient:
    """HTTP client for the motion-graphics renderer.

    Synchronous-friendly async client, in the shape of the other engine clients
    in this package (``WanAnimateClient``, ``FluxClient``): construct with a
    base URL, ``await`` the calls, ``await close()``.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 300.0,
        connect_timeout_seconds: float = 5.0,
        model: str | None = None,
        default_params: Dict[str, Any] | None = None,
    ) -> None:
        if not base_url:
            # Belt and braces: `resolve_endpoint` already refuses an empty
            # endpoint by name. Repeated here because a caller that builds this
            # client from somewhere else must not get a client that silently
            # posts to a relative URL.
            raise MotionGraphicsError(
                "motion_graphics client constructed with no base URL. The "
                "engine's endpoint is IVGS_MOTION_GRAPHICS_URL and it has no "
                "default by design (shared/providers/binding.py:45)."
            )
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds)
        #: Carried for parity with the other clients and for logging. A template
        #: renderer has no model, and pretending otherwise would put a
        #: fabricated model name on the asset's metadata.
        self.model = model
        self.default_params = dict(default_params or {})
        self._client: httpx.AsyncClient | None = None
        self._log = logger.bind(client="motion_graphics", base_url=self._base_url)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def health(self) -> Dict[str, Any]:
        """``/healthz``: build ref, template inventory, font and ffmpeg state.

        Raises rather than returning a falsy value. "Unreachable" and "reachable
        but degraded" are different facts and both are worth the caller's
        attention; a boolean would collapse them.
        """
        try:
            resp = await (await self._http()).get(f"{self._base_url}/healthz")
        except httpx.HTTPError as exc:
            raise MotionGraphicsError(
                f"motion-graphics renderer at {self._base_url} is not reachable: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        body: Dict[str, Any]
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:300]}
        if resp.status_code != 200:
            raise MotionGraphicsError(
                f"motion-graphics renderer at {self._base_url} is not ready "
                f"(HTTP {resp.status_code}): {body}"
            )
        return body

    async def render(self, params: Dict[str, Any]) -> MotionRenderResult:
        """Render one template. ``params`` is the scene's ``generation_params``.

        :raises MotionGraphicsError: unreachable, refused (4xx — a real problem
            with the request that a retry will reproduce), or failed (5xx).
            **Never returns a substitute.** A motion graphic that is not the one
            the storyboard asked for is worse than none, because nothing
            downstream can tell the difference.
        """
        payload = {**self.default_params, **dict(params)}
        try:
            resp = await (await self._http()).post(
                f"{self._base_url}/render", json=payload,
            )
        except httpx.HTTPError as exc:
            raise MotionGraphicsError(
                f"motion-graphics render failed to reach {self._base_url}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if resp.status_code != 200:
            detail = resp.text[:500]
            try:
                detail = str(resp.json().get("detail", detail))
            except ValueError:
                pass
            raise MotionGraphicsError(
                f"motion-graphics renderer refused (HTTP {resp.status_code}) "
                f"for {payload}: {detail}"
            )

        data = resp.content
        if not data:
            raise MotionGraphicsError(
                f"motion-graphics renderer returned HTTP 200 with an empty body "
                f"for {payload}. An empty asset is a failure, not a render."
            )

        h = resp.headers
        result = MotionRenderResult(
            data=data,
            template=h.get("X-IVGS-Template", str(payload.get("template", ""))),
            frames=int(h.get("X-IVGS-Frames", "0") or 0),
            fps=int(h.get("X-IVGS-Fps", "0") or 0),
            duration_seconds=float(h.get("X-IVGS-Duration-Seconds", "0") or 0.0),
            frames_digest=h.get("X-IVGS-Frames-Digest", ""),
            build_ref=h.get("X-IVGS-Build-Ref", "unknown"),
        )
        self._log.info(
            "motion_graphics_rendered",
            template=result.template,
            frames=result.frames,
            duration_seconds=result.duration_seconds,
            frames_digest=result.frames_digest,
            renderer_build=result.build_ref,
            bytes=len(data),
        )
        return result
