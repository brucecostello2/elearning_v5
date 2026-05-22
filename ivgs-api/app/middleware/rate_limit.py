"""
Redis-backed rate limiting middleware per §16.3.

Limits:
- Content CRUD: 60 requests/minute per user
- Job triggers: 10 requests/minute per user
- Login: 5 attempts/minute per IP, lockout after 10 consecutive failures (15 min)

Uses Redis sliding window counters.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from shared.redis_client import redis_client

logger = logging.getLogger(__name__)

# Rate limit configurations: (max_requests, window_seconds)
RATE_LIMITS = {
    "login": (5, 60),       # 5 attempts/min per IP
    "job_trigger": (10, 60), # 10 req/min per user
    "default": (60, 60),     # 60 req/min per user
}

LOGIN_LOCKOUT_THRESHOLD = 10   # consecutive failures
LOGIN_LOCKOUT_SECONDS = 900    # 15 minutes


def _classify_request(path: str, method: str) -> str:
    """Classify the request into a rate limit bucket."""
    if "/auth/login" in path and method == "POST":
        return "login"
    if "/trigger" in path and method == "POST":
        return "job_trigger"
    return "default"


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _get_user_id_from_token(request: Request) -> str:
    """Extract user_id from Bearer token without full validation (for rate limiting key)."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_token

            payload = decode_token(auth_header[7:])
            if payload and "sub" in payload:
                return payload["sub"]
        except Exception:
            pass
    return ""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware enforcing per-user and per-IP rate limits via Redis."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        method = request.method

        # Skip rate limiting for GET requests and non-API paths
        if method == "GET" or not path.startswith("/api/"):
            return await call_next(request)

        bucket = _classify_request(path, method)
        client_ip = _get_client_ip(request)

        # --- Login-specific lockout check ---
        if bucket == "login":
            lockout_key = f"ratelimit:lockout:{client_ip}"
            if await redis_client.exists(lockout_key):
                logger.warning(f"Rate limit lockout active for IP={client_ip}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Too many failed login attempts. Try again in 15 minutes.",
                        }
                    },
                    headers={"Retry-After": "900"},
                )

        # --- Sliding window rate limit ---
        max_requests, window_seconds = RATE_LIMITS[bucket]

        if bucket == "login":
            rate_key = f"ratelimit:{bucket}:{client_ip}"
        else:
            user_id = _get_user_id_from_token(request)
            identity = user_id if user_id else client_ip
            rate_key = f"ratelimit:{bucket}:{identity}"

        current_count = await redis_client.incr(rate_key)
        if current_count == 1:
            await redis_client.expire(rate_key, window_seconds)

        if current_count is not None and current_count > max_requests:
            logger.warning(
                f"Rate limit exceeded: bucket={bucket} key={rate_key} "
                f"count={current_count}/{max_requests}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded: {max_requests} requests per {window_seconds}s",
                    }
                },
                headers={"Retry-After": str(window_seconds)},
            )

        # Execute request
        response = await call_next(request)

        # --- Track consecutive login failures for lockout ---
        if bucket == "login":
            fail_counter_key = f"ratelimit:login_failures:{client_ip}"
            if response.status_code == 401:
                fail_count = await redis_client.incr(fail_counter_key)
                if fail_count == 1:
                    await redis_client.expire(fail_counter_key, 3600)
                if fail_count is not None and fail_count >= LOGIN_LOCKOUT_THRESHOLD:
                    lockout_key = f"ratelimit:lockout:{client_ip}"
                    await redis_client.set(lockout_key, "1", ex=LOGIN_LOCKOUT_SECONDS)
                    logger.warning(
                        f"Login lockout activated for IP={client_ip} "
                        f"after {fail_count} consecutive failures"
                    )
            elif response.status_code == 200:
                # Successful login — reset failure counter
                await redis_client.delete(fail_counter_key)

        return response
