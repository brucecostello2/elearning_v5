"""
Redis-backed rate limiting middleware per §16.3.

Limits:
- Content CRUD: 60 requests/minute per user
- Job triggers: 10 requests/minute per user
- Login: 5 attempts/minute per IP, lockout after 10 consecutive failures (15 min)

Uses Redis sliding window counters.
"""
import hmac
import logging
import os
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from shared.config import settings
from shared.redis_client import redis_client

logger = logging.getLogger(__name__)

# WP-58 Task 4 — a second instance of the retention defect, found by the sweep.
#
# `ivgs-infra/.env` and `.env.node01` have both set RATE_LIMIT_AUTH_LOGIN,
# RATE_LIMIT_JOB_TRIGGERS and RATE_LIMIT_CONTENT_CRUD since they were written,
# and NOTHING HAS EVER READ ANY OF THEM. This table was a Python literal, so the
# §16.3 abuse controls were not configurable and an operator editing .env to
# loosen or tighten a limit changed nothing at all. Same shape as the four
# BACKUP_RETENTION_* variables: a setting that looks live and is decorative.
#
# The configured values happen to equal the literals below (5, 10 and 60 per
# minute), which is exactly why this went unnoticed — as with retention, the
# defect is invisible until someone tries to change a value.
#
# The literals are kept as DEFAULTS, so an unset or malformed variable produces
# today's behaviour rather than an unlimited bucket. A rate limiter that fails
# open because its configuration is unparseable is worse than one that is not
# configurable, so `_parse_rate` never widens a limit on bad input.

_WINDOW_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def _parse_rate(raw: str | None, fallback: tuple[int, int]) -> tuple[int, int]:
    """Parse a ``"N/period"`` rate string into ``(max_requests, window_seconds)``.

    Returns ``fallback`` for anything it cannot parse, and says so in the log.
    Deliberately conservative: an unreadable limit must not become no limit.
    """
    if not raw:
        return fallback
    try:
        count_text, _, period = raw.strip().partition("/")
        count = int(count_text)
        window = _WINDOW_SECONDS[period.strip().lower().rstrip("s")]
        if count < 1:
            raise ValueError(f"rate count must be >= 1, got {count}")
        return count, window
    except (ValueError, KeyError) as exc:
        logger.warning(
            "Unparseable rate limit %r (%s); falling back to %s req / %ss",
            raw, exc, fallback[0], fallback[1],
        )
        return fallback


# Rate limit configurations: (max_requests, window_seconds)
RATE_LIMITS = {
    "login": _parse_rate(os.environ.get("RATE_LIMIT_AUTH_LOGIN"), (5, 60)),
    "job_trigger": _parse_rate(os.environ.get("RATE_LIMIT_JOB_TRIGGERS"), (10, 60)),
    "default": _parse_rate(os.environ.get("RATE_LIMIT_CONTENT_CRUD"), (60, 60)),
}

LOGIN_LOCKOUT_THRESHOLD = 10   # consecutive failures
LOGIN_LOCKOUT_SECONDS = 900    # 15 minutes


# WP-59 Task 6. `DELETE /api/v1/projects/{uuid}` and nothing else -- not the
# sub-resources (`/projects/{id}/languages/{id}`, `/projects/{id}/assets/...`),
# which are ordinary content CRUD and belong in the 60/min bucket. Anchored at
# the end of the path so a longer route cannot fall into the job-trigger bucket
# by accident.
_PROJECT_DELETE_PATH = re.compile(
    r"/projects/[0-9a-fA-F-]{36}/?$"
)


def _classify_request(path: str, method: str) -> str:
    """Classify the request into a rate limit bucket."""
    if "/auth/login" in path and method == "POST":
        return "login"
    if "/trigger" in path and method == "POST":
        return "job_trigger"
    # WP-59 Task 6: "rate-limit it like the other job triggers". A project
    # deletion is the most destructive single call the API offers and it is
    # exactly as scriptable as a trigger, so it belongs in the 10/min bucket
    # rather than the 60/min content bucket it fell into as a bare DELETE.
    if method == "DELETE" and _PROJECT_DELETE_PATH.search(path):
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


def _is_internal_service_call(request: Request) -> bool:
    """Is this the worker fleet calling the API with the internal service token?

    WP-45. These limits are a §16.3 abuse control aimed at PEOPLE: 60 writes a
    minute is generous for a browser and far too small for a pipeline. Stage 5
    alone makes roughly three writes per scene - the asset upload, the scene
    audio link, the quality verdict - so an 18-scene project produces ~55 writes
    back to back, plus its stage checkpoint. Every one of them authenticates as
    the same `svc-pipeline` account, so the fleet shares ONE 60/min bucket with
    itself.

    Observed 2026-08-25 on the reference project, and it is not a theoretical
    margin: Stage 5 synthesised all 18 voiceovers successfully and then died
    writing its own checkpoint -

        CheckpointWriteError: checkpoint write for job b3df6eb6 stage tts_audio
        returned HTTP 429 ... The stage is not resumable without it.

    That is WP-07's guard behaving exactly as designed - a checkpoint that
    cannot be written must not be reported as written - firing on a stage whose
    work had actually completed. The pipeline was throttling itself out of its
    own back half.

    The service token is not a user and must not share a user's ceiling. It is
    compared in constant time against the same secret ``get_service_or_user``
    accepts, so this exempts exactly the fleet and nothing else: a JWT, however
    privileged, still gets a user's limit. The login bucket is deliberately NOT
    exempted below - nothing about being the pipeline should ease a brute-force
    control.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]
    service_token = getattr(settings, "IVGS_SERVICE_TOKEN", "") or ""
    if not service_token:
        return False
    return hmac.compare_digest(token, service_token)


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

        # WP-45: the worker fleet is not a user. See _is_internal_service_call.
        # Checked after bucket classification and BEFORE the login branch below,
        # so the exemption cannot reach the login limiter even if a future
        # classifier change put a service path in that bucket.
        if bucket != "login" and _is_internal_service_call(request):
            return await call_next(request)
        client_ip = _get_client_ip(request)

        # --- Pre-request Redis-backed rate limit checks (BUG-011) ---
        # Degradation policy when Redis is unavailable:
        #   - login bucket  -> FAIL CLOSED (deny): the login limiter is
        #     brute-force protection; silently disabling it under a Redis
        #     outage would reopen credential-stuffing. Return 503.
        #   - other buckets -> FAIL OPEN (allow): general abuse-throttling
        #     should not take down the whole API write-path on a Redis blip.
        try:
            # --- Login-specific lockout check ---
            if bucket == "login":
                lockout_key = f"ratelimit:lockout:{client_ip}"
                if await redis_client.exists(lockout_key):
                    logger.warning("Rate limit lockout active for IP=%s", client_ip)
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
        except Exception:
            if bucket == "login":
                # FAIL CLOSED on login: deny rather than allow unlimited attempts.
                logger.error(
                    "Redis unavailable for login rate limiting (ip=%s); "
                    "failing CLOSED — login denied",
                    client_ip,
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "SERVICE_UNAVAILABLE",
                            "message": "Login temporarily unavailable. Please try again shortly.",
                        }
                    },
                    headers={"Retry-After": "30"},
                )
            # FAIL OPEN on non-login buckets: allow through, do not crash the API.
            logger.warning(
                "Redis unavailable for rate limiting (bucket=%s, ip=%s); "
                "failing OPEN — request allowed without rate limit check",
                bucket,
                client_ip,
            )

        # Execute request
        response = await call_next(request)

        # --- Track consecutive login failures for lockout ---
        if bucket == "login":
            try:
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
            except Exception:
                logger.warning(
                    "Redis unavailable for login failure tracking (ip=%s); "
                    "lockout counters not updated",
                    client_ip,
                )

        return response
