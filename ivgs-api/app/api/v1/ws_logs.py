"""
IVGS v5 — WebSocket Log Streaming
===================================

Implements §13.4 minimum requirement: stream docker logs to dashboard.
Endpoints:
  WS /ws/jobs/{job_id}/status   — Real-time job progress (§5.1.7)

Node log streaming used to live here and did not work; see the block below the
imports. Node logs are now GET /api/v1/nodes/{node_id}/logs (app/core/node_logs.py).
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

logger = logging.getLogger("ivgs.api.ws")

router = APIRouter(tags=["websocket"])


async def _authenticate_ws(websocket: WebSocket) -> bool:
    """Validate JWT token from WebSocket query parameter.

    Expects ``?token=<JWT>`` on the WebSocket URL.  Returns *True* if the
    token is valid and the user exists + is active, otherwise closes the
    connection with code **1008** (Policy Violation) and returns *False*.
    """
    from app.core.security import decode_token
    from shared.database import get_session
    from app.models.user import User

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return False

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=1008, reason="Invalid authentication token")
        return False

    user_id_str = payload.get("sub")
    if user_id_str is None:
        await websocket.close(code=1008, reason="Invalid token payload")
        return False

    # Verify user exists and is active
    async for db in get_session():
        try:
            from uuid import UUID
            result = await db.execute(select(User).where(User.id == UUID(user_id_str)))
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                await websocket.close(code=1008, reason="User not found or inactive")
                return False
        except Exception:
            await websocket.close(code=1008, reason="Authentication error")
            return False

    return True

# ---------------------------------------------------------------------------
# REMOVED 2026-08-25 (WP-48-TELEMETRY Task 3): `WS /ws/nodes/{node_id}/logs`.
#
# It could never have produced a line. The handler ran
#     ssh <node_ip> 'docker compose logs --follow --tail 100'
# with `asyncio.create_subprocess_shell` from inside this container, and this
# container has no `ssh` binary, no key and no `docker` CLI -- measured
# 2026-08-25 in the running `ivgs-fastapi`: `command -v ssh` and `command -v
# docker` both return nothing. The subprocess exits immediately, `readline()`
# returns empty, the loop breaks, and the socket closes having sent nothing.
# It never raised, so it never surfaced: exactly the WP-00 swallow shape.
#
# It was also not the endpoint the UI advertised. The Node Monitor modal named
#     ws://node-01:8000/api/v1/nodes/{id}/logs/stream
# which has never been a registered route on this app at all.
#
# Replaced by a real, polled source that is proven to work end to end:
#     GET /api/v1/nodes/{node_id}/containers
#     GET /api/v1/nodes/{node_id}/logs?container=&tail=
# backed by `app/core/node_logs.py` and the per-node `ivgs-node-logs` service in
# ivgs-infra/docker-compose.telemetry.yml. Deleted rather than left in place:
# a route that cannot work is worse than no route, because the page kept
# pointing at it.
# ---------------------------------------------------------------------------


@router.websocket("/ws/jobs/{job_id}/status")
async def stream_job_status(
    websocket: WebSocket,
    job_id: str,
):
    """
    WebSocket stream for real-time job progress updates.
    Polls database for job status changes and pushes to client.
    Requires JWT token via ``?token=<JWT>`` query parameter (BUG-012 fix).
    """
    if not await _authenticate_ws(websocket):
        return
    await websocket.accept()

    import redis.asyncio as aioredis
    from shared.config import settings

    redis_client = aioredis.from_url(settings.REDIS_URL)
    pubsub = None  # Initialize before try block (UnboundLocalError guard, same class as BUG-013)

    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:{job_id}:status")

        last_status = None
        while True:
            # Check for Redis pub/sub messages
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
                last_status = data.get("status")
                if last_status in ("COMPLETE", "ERROR"):
                    break
            else:
                # Heartbeat every 5 seconds
                await asyncio.sleep(5)
                await websocket.send_json({"type": "heartbeat", "job_id": job_id})

    except WebSocketDisconnect:
        logger.info("Job status WebSocket disconnected for %s", job_id)
    except Exception as exc:
        logger.exception(f"Job status streaming error: {exc}")
    finally:
        if pubsub is not None:
            await pubsub.unsubscribe(f"job:{job_id}:status")
        await redis_client.close()
