"""
Audit logging middleware per §4.1 Table 9 and §16.3.

Captures all state-changing HTTP operations (POST, PUT, PATCH, DELETE)
and writes before/after state to the audit_log table.

Fields: user_id, action_type, resource_type, resource_id,
        before_payload, after_payload, client_ip, timestamp.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shared.database import get_db_context

logger = logging.getLogger(__name__)

# Methods that trigger audit logging
AUDITABLE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths to skip audit logging (health, docs, auth login)
SKIP_PATHS = {"/api/v1/health", "/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json", "/"}


def _extract_resource_info(path: str, method: str) -> tuple[str, Optional[str]]:
    """
    Extract resource_type and resource_id from URL path.

    Returns:
        (resource_type, resource_id) — resource_id may be None for collection-level ops.
    """
    parts = [p for p in path.strip("/").split("/") if p]

    # Expected pattern: api/v1/{resource_type}/{resource_id?}/...
    resource_type = "unknown"
    resource_id = None

    if len(parts) >= 3:
        resource_type = parts[2]  # e.g., "auth", "users", "projects"

    if len(parts) >= 4:
        candidate = parts[3]
        # Simple UUID detection
        if len(candidate) == 36 and candidate.count("-") == 4:
            resource_id = candidate
        elif len(candidate) == 32:
            resource_id = candidate

    return resource_type, resource_id


def _map_method_to_action(method: str) -> str:
    """Map HTTP method to audit action type."""
    mapping = {
        "POST": "CREATE",
        "PUT": "UPDATE",
        "PATCH": "UPDATE",
        "DELETE": "DELETE",
    }
    return mapping.get(method, method)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that logs mutations to the audit_log table.

    For POST/PUT/PATCH/DELETE requests:
    - Captures request body as before_payload context
    - Captures response body as after_payload context
    - Extracts user_id from JWT sub claim in Authorization header
    - Writes audit record to database
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in AUDITABLE_METHODS:
            return await call_next(request)

        path = request.url.path
        if path in SKIP_PATHS:
            return await call_next(request)

        # Capture request body for audit
        request_body = None
        try:
            body_bytes = await request.body()
            if body_bytes:
                request_body = json.loads(body_bytes.decode("utf-8", errors="replace"))
                # Redact password fields
                if isinstance(request_body, dict):
                    for key in ("password", "new_password", "current_password"):
                        if key in request_body:
                            request_body[key] = "***REDACTED***"
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_body = None

        # Execute the actual request
        response = await call_next(request)

        # Capture response body for audit
        response_body = None
        response_body_bytes = b""
        try:
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    response_body_bytes += chunk.encode("utf-8")
                else:
                    response_body_bytes += chunk

            # Try to parse response as JSON for after_payload
            if response_body_bytes:
                try:
                    response_body = json.loads(response_body_bytes)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_body = None
        except Exception:
            response_body_bytes = b""

        # Rebuild the response with the consumed body
        from starlette.responses import Response as StarletteResponse

        new_response = StarletteResponse(
            content=response_body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

        # Only audit successful mutations (2xx status codes)
        if 200 <= response.status_code < 300:
            await self._write_audit_log(
                request=request,
                request_body=request_body,
                response_body=response_body,
            )

        return new_response

    async def _write_audit_log(
        self,
        request: Request,
        request_body: Optional[dict],
        response_body: Optional[dict],
    ) -> None:
        """Write an audit log entry to the database."""
        try:
            from app.core.security import decode_token

            # Extract user_id from Authorization header
            user_id = None
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                payload = decode_token(token)
                if payload and "sub" in payload:
                    user_id = payload["sub"]

            resource_type, resource_id = _extract_resource_info(
                request.url.path, request.method
            )
            action_type = _map_method_to_action(request.method)

            # Get client IP
            client_ip = request.client.host if request.client else "unknown"
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()

            async with get_db_context() as db:
                from app.models.audit_log import AuditLog

                audit_entry = AuditLog(
                    user_id=user_id,
                    action_type=action_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    before_payload=request_body,
                    after_payload=response_body,
                    client_ip=client_ip,
                )
                db.add(audit_entry)
                await db.flush()

            logger.debug(
                f"Audit: user={user_id} action={action_type} "
                f"resource={resource_type}/{resource_id}"
            )

        except Exception as e:
            # Audit failures must not break the request
            logger.error(f"Audit logging failed: {e}", exc_info=True)
