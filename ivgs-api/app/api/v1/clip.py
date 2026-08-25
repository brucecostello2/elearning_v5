"""
CLIP image/text scoring — the route stage 3 has always called (WP-44).

Endpoints:
- POST /api/v1/clip/score    — cosine similarity between an image and a prompt
- GET  /api/v1/clip/health   — is a real scorer behind this route?

WHY THIS IS A PROXY AND NOT A WORKER-SIDE REPOINT
==================================================

`tasks/stage3_images.py` builds its scorer URL as
``f"{config.pipeline_api.base_url}/api/v1/clip"`` and POSTs to ``…/score``.
That URL resolved to node-01's API, which had no such route, so every call
404'd. The old ``ImageValidator`` read the 404 as ``None`` and then *awarded*
the full CLIP weight for it — swallow register instance 24.

Two ways to end that. Repoint the worker at node-05 directly
(``IVGS_CLIP_URL=http://node-05:8300``), or implement the route the worker
already speaks as a thin proxy. **This package implements the route.** Reasons,
in the order they decided it:

1. **One deployment surface, not four.** A worker-side repoint is a new
   environment variable that has to be set correctly in four `.env` files on
   four nodes and stay correct through every future recreate. Every fleet
   incident in this repo's history involving per-node env drift (node-04's
   VRAM figure, node-02's orphaned compose network, the `IVGS_VLLM_URL`
   overrides) argues against adding another one. The API already is the
   workers' single callback hub — checkpoints, DLQ, assets, prompts, job
   status all come here.
2. **The scorer stays off the worker network path.** node-05 is reachable only
   from the API, which is the same containment the node-logs source got in
   WP-48. Workers do not gain a new outbound dependency.
3. **The contract stage 3 speaks is honoured verbatim**, so no already-deployed
   worker image is left pointing at a URL that does not answer. That is the
   failure mode being fixed; recreating it in a different place would be
   perverse.
4. **The status of the scorer becomes observable in one place** — `/clip/health`
   answers for the fleet, and the proxy is where a missing backend turns into
   an honest 503 instead of a silent zero.

The cost is one extra LAN hop for a base64 payload. Measured in the WP-44
report, S3: it is a small fraction of scoring latency and is reported rather
than assumed.

HONESTY CONTRACT
================

This route never invents a score. If ``IVGS_CLIP_SERVICE_URL`` is unset or the
backend does not answer, it returns **503 with no ``score`` field**. The
validator's ``_compute_clip_score`` maps any non-200 to
``ClipStatus.UNAVAILABLE``, which contributes nothing to ``quality_score`` and
is recorded as the literal string ``"unavailable"``. There is no code path in
which an absent scorer produces a number.
"""
import logging
import os
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.rbac import require_service_or_privileged_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clip", tags=["Quality Assurance"])

#: node-05's scoring service. Unset = no scorer; the route says so with a 503.
CLIP_SERVICE_URL = os.getenv("IVGS_CLIP_SERVICE_URL", "").rstrip("/")

#: Scoring a 1920×1080 PNG includes base64 transfer of ~1.5 MB plus a forward
#: pass. 30 s is the worker-side client timeout; stay under it so the proxy is
#: never the thing that times the worker out.
CLIP_TIMEOUT_S = float(os.getenv("IVGS_CLIP_TIMEOUT_S", "25"))


class ClipScoreRequest(BaseModel):
    """The body stage 3 has always sent."""

    image_base64: str = Field(description="Base64-encoded image bytes")
    text: str = Field(description="Prompt to compare the image against")


class ClipScoreResponse(BaseModel):
    score: float = Field(description="Cosine similarity, image vs text")
    model: str = Field(description="Scoring model identifier")
    served_by: str = Field(description="Node/service that computed the score")
    latency_ms: Optional[float] = None
    device: Optional[str] = None


def _unavailable(reason: str, **fields: Any) -> HTTPException:
    """A 503 that names why, and carries no score field of any kind."""
    logger.warning("clip_scorer_unavailable reason=%s %s", reason, fields)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": {
                "code": "SCORER_UNAVAILABLE",
                "message": (
                    f"CLIP scoring is unavailable ({reason}). No score was "
                    f"computed and none is being returned."
                ),
                **fields,
            }
        },
    )


@router.post(
    "/score",
    response_model=ClipScoreResponse,
    summary="Score an image against a text prompt",
)
async def score_image(
    data: ClipScoreRequest,
    current_user: User = Depends(require_service_or_privileged_user),
) -> ClipScoreResponse:
    """Proxy one scoring request to the node-05 CLIP service.

    Returns 503 — never a fabricated number — when the scorer cannot be
    reached or does not return a usable score.
    """
    if not CLIP_SERVICE_URL:
        raise _unavailable("IVGS_CLIP_SERVICE_URL is not configured")

    try:
        async with httpx.AsyncClient(timeout=CLIP_TIMEOUT_S) as client:
            resp = await client.post(
                f"{CLIP_SERVICE_URL}/score",
                json={"image_base64": data.image_base64, "text": data.text},
            )
    except httpx.HTTPError as exc:
        raise _unavailable("backend unreachable", backend=CLIP_SERVICE_URL,
                           detail_text=str(exc)[:200])

    if 400 <= resp.status_code < 500:
        # The backend rejected the REQUEST — a malformed image, usually. That is
        # not an unavailable scorer, and calling it one would be the same
        # imprecision this package exists to remove: the caller would be told
        # "no scorer" when what it actually got was "your bytes are not an
        # image". Passed through with its own status.
        logger.warning(
            "clip_score_bad_request status=%s body=%s",
            resp.status_code, resp.text[:200],
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "error": {
                    "code": "BAD_SCORING_REQUEST",
                    "message": (
                        "The scoring service rejected this request. The scorer "
                        "is reachable; the input was not usable."
                    ),
                    "backend_status": resp.status_code,
                    "backend_body": resp.text[:200],
                }
            },
        )

    if resp.status_code != 200:
        raise _unavailable(
            f"backend returned HTTP {resp.status_code}",
            backend=CLIP_SERVICE_URL,
            body=resp.text[:200],
        )

    try:
        payload: Dict[str, Any] = resp.json()
        raw = payload.get("score", payload.get("similarity"))
        if raw is None:
            raise KeyError("score")
        score = float(raw)
    except Exception as exc:
        raise _unavailable("backend returned no usable score",
                           backend=CLIP_SERVICE_URL, detail_text=str(exc)[:200])

    return ClipScoreResponse(
        score=score,
        model=str(payload.get("model", "unknown")),
        served_by=str(payload.get("served_by", CLIP_SERVICE_URL)),
        latency_ms=payload.get("latency_ms"),
        device=payload.get("device"),
    )


@router.get(
    "/health",
    summary="Is a real CLIP scorer behind this route?",
)
async def clip_health(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Report the scorer's real state.

    ``available: false`` with a reason is the answer whenever a score could not
    be obtained — this endpoint exists so "the gate is scoring" is a checkable
    claim rather than an assumption.
    """
    if not CLIP_SERVICE_URL:
        return {
            "available": False,
            "reason": "IVGS_CLIP_SERVICE_URL is not configured",
            "backend": None,
        }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{CLIP_SERVICE_URL}/health")
        if resp.status_code != 200:
            return {
                "available": False,
                "reason": f"backend returned HTTP {resp.status_code}",
                "backend": CLIP_SERVICE_URL,
            }
        body = resp.json()
        return {
            "available": bool(body.get("model_loaded")),
            "backend": CLIP_SERVICE_URL,
            "backend_health": body,
        }
    except httpx.HTTPError as exc:
        return {
            "available": False,
            "reason": f"backend unreachable: {exc}",
            "backend": CLIP_SERVICE_URL,
        }
