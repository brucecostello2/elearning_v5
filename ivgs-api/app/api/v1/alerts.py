"""Alertmanager webhook receiver — stores alerts in database for dashboard display."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("ivgs.api.alerts")

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/webhook")
async def alertmanager_webhook(request: Request):
    """Receive alerts from Alertmanager and broadcast to dashboard."""
    payload = await request.json()

    for alert in payload.get("alerts", []):
        logger.warning(
            "Alert received",
            extra={
                "alertname": alert.get("labels", {}).get("alertname"),
                "severity": alert.get("labels", {}).get("severity"),
                "status": alert.get("status"),
                "summary": alert.get("annotations", {}).get("summary"),
            },
        )

    # Publish to Redis for dashboard WebSocket consumers
    import redis.asyncio as aioredis
    from shared.config import settings
    import json

    redis_client = aioredis.from_url(settings.REDIS_URL)
    await redis_client.publish(
        "ivgs:alerts",
        json.dumps(payload),
    )
    await redis_client.close()

    return {"status": "ok", "alerts_received": len(payload.get("alerts", []))}
