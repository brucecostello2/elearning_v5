"""
IVGS v5 — WebSocket Log Streaming
===================================

Implements §13.4 minimum requirement: stream docker logs to dashboard.
Endpoints:
  WS /ws/nodes/{node_id}/logs   — Live log stream from node
  WS /ws/jobs/{job_id}/status   — Real-time job progress (§5.1.7)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
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

# Node SSH connection map
NODE_HOSTS = {
    "node-01": "10.10.0.1",
    "node-02": "10.10.0.2",
    "node-03": "10.10.0.3",
    "node-04": "10.10.0.4",
    "node-05": "10.10.0.5",
    "node-06": "10.10.0.6",
}


@router.websocket("/ws/nodes/{node_id}/logs")
async def stream_node_logs(
    websocket: WebSocket,
    node_id: str,
    service: Optional[str] = Query(None),
    tail: int = Query(100),
):
    """
    WebSocket stream for live log output from a node.
    Streams docker logs from the specified node via SSH.
    Requires JWT token via ``?token=<JWT>`` query parameter (BUG-012 fix).
    """
    if not await _authenticate_ws(websocket):
        return
    await websocket.accept()

    if node_id not in NODE_HOSTS:
        await websocket.send_json(
            {"error": f"Unknown node: {node_id}"}
        )
        await websocket.close(code=1008)
        return

    host = NODE_HOSTS[node_id]
    docker_cmd = "docker compose logs --follow --tail"
    if service:
        cmd = f"ssh {host} '{docker_cmd} {tail} {service}'"
    else:
        cmd = f"ssh {host} '{docker_cmd} {tail}'"

    process = None  # Initialize before try block (BUG-013 fix)
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def read_output():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    await websocket.send_json({
                        "node_id": node_id,
                        "log": line.decode("utf-8", errors="replace").strip(),
                        "timestamp": __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat(),
                    })
                except WebSocketDisconnect:
                    break

        await read_output()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for node %s", node_id)
    except Exception as exc:
        logger.exception(f"Log streaming error for {node_id}: {exc}")
        try:
            await websocket.send_json({"error": str(exc)})
        except Exception:
            pass
    finally:
        if process and process.returncode is None:
            process.terminate()


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
        await pubsub.unsubscribe(f"job:{job_id}:status")
        await redis_client.close()
