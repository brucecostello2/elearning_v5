"""
IVGS v5 — quality verdict reporting  (WP-44-QUALITY)
======================================================

One place that submits an automated quality verdict to the API, and one place
that maps a validation result onto a task result's quality fields.

Why this module exists
----------------------
Before WP-44 the submission lived as a private helper inside
``tasks/stage3_images.py`` and no other media task had one at all — which is
part of why the first e2e run's two video assets carry ``quality_decision: ""``
and ``quality_score: 0.0``. Image, video and animation all produce assets that
belong in the same review queue, so they share the same reporting path.

The submission is deliberately non-fatal and deliberately NOT silent. A failed
submission never fails the scene — the asset exists and is already uploaded —
but a non-2xx is logged as a warning naming the status and URL. The old code
awaited the POST inside a bare ``except Exception``; a 404 raises nothing, and
``POST /api/v1/quality-scores`` did not exist, so every verdict of the first
run was discarded without a log line.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger("ivgs.quality_reporting")


async def submit_quality_score(
    asset_id: str,
    quality_score: float,
    quality_decision: str,
    scoring_details: Dict[str, Any],
    config: Any,
    job_id: Optional[str] = None,
) -> bool:
    """POST one automated verdict to ``/api/v1/quality-scores``.

    Returns True when the API accepted it. Never raises: a scene is not failed
    because its paperwork failed, but the failure is always logged.
    """
    if not asset_id:
        logger.warning("quality_score_submit_skipped", reason="no_asset_id")
        return False

    url = f"{config.pipeline_api.full_base_url}/quality-scores"
    body: Dict[str, Any] = {
        "asset_id": asset_id,
        "quality_score": quality_score,
        "decision": quality_decision,
        "scoring_details": scoring_details,
    }
    if job_id:
        body["job_id"] = job_id

    async with httpx.AsyncClient(
        timeout=15.0,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        try:
            resp = await client.post(url, json=body)
        except Exception as e:  # noqa: BLE001 - reported, not swallowed
            logger.warning(
                "quality_score_submit_failed",
                reason="transport",
                error=str(e),
                url=url,
                asset_id=asset_id,
            )
            return False

    if resp.status_code not in (200, 201):
        logger.warning(
            "quality_score_submit_failed",
            reason="http_status",
            status_code=resp.status_code,
            url=url,
            asset_id=asset_id,
            body=resp.text[:200],
        )
        return False

    logger.info(
        "quality_score_submitted",
        asset_id=asset_id,
        decision=quality_decision,
        quality_score=quality_score,
        complete=scoring_details.get("quality_score_complete"),
    )
    return True


def video_quality_fields(validation: Any) -> Dict[str, Any]:
    """The quality half of a video/animation scene result.

    Mirrors ``tasks.stage3_images._quality_fields`` so an image result and a
    video result carry the same honesty fields under the same names, and the
    review queue does not have to special-case the media type.
    """
    return {
        "quality_score": validation.quality_score,
        "quality_decision": validation.decision.value,
        "checks_missing": list(validation.checks_missing),
        "check_coverage": validation.check_coverage,
        "quality_score_complete": validation.quality_score_complete,
    }
