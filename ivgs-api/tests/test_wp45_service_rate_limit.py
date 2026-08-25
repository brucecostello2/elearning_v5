"""WP-45 — the worker fleet is not a user, and must not share a user's ceiling.

Found by running the back half for the first time. Stage 5 synthesised all 18
voiceovers on the reference project, then died writing its own checkpoint:

    CheckpointWriteError: checkpoint write for job b3df6eb6 stage tts_audio
    returned HTTP 429 ... The stage is not resumable without it.

That is WP-07's guard behaving exactly as designed — a checkpoint that cannot be
written must never be reported as written — firing on a stage whose work had
completed. The cause is one bucket up the stack: the §16.3 rate limits are an
abuse control aimed at PEOPLE, and every worker on the fleet authenticates as
the same `svc-pipeline` account, so the whole pipeline shares one 60-writes-a-
minute allowance with itself. Stage 5 alone makes roughly three writes per scene.

The exemption is scoped by the token, not by a role: a JWT, however privileged,
still gets a user's limit. And the login bucket is never exempted — nothing
about being the pipeline should ease a brute-force control.
"""
import hmac
from unittest.mock import MagicMock, patch

import pytest


def _request(auth_header: str = "", path: str = "/api/v1/jobs/x/checkpoints", method: str = "POST"):
    req = MagicMock()
    req.headers = {"authorization": auth_header} if auth_header else {}
    req.url.path = path
    req.method = method
    req.client.host = "192.168.1.93"
    return req


class TestTheServiceTokenIsExempt:

    def test_the_service_token_is_recognised(self):
        from app.middleware import rate_limit

        with patch.object(rate_limit.settings, "IVGS_SERVICE_TOKEN", "s3cr3t-fleet"):
            assert rate_limit._is_internal_service_call(
                _request("Bearer s3cr3t-fleet")
            ) is True

    def test_a_user_jwt_is_not(self):
        # The exemption is by TOKEN, not by role. An admin JWT is still a person
        # driving a browser and still gets a person's ceiling.
        from app.middleware import rate_limit

        with patch.object(rate_limit.settings, "IVGS_SERVICE_TOKEN", "s3cr3t-fleet"):
            assert rate_limit._is_internal_service_call(
                _request("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def")
            ) is False

    def test_no_authorization_header_is_not(self):
        from app.middleware import rate_limit

        with patch.object(rate_limit.settings, "IVGS_SERVICE_TOKEN", "s3cr3t-fleet"):
            assert rate_limit._is_internal_service_call(_request()) is False

    def test_an_unconfigured_service_token_exempts_NOTHING(self):
        # Fail closed. An empty configured secret must not turn every empty or
        # absent bearer token into a free pass.
        from app.middleware import rate_limit

        with patch.object(rate_limit.settings, "IVGS_SERVICE_TOKEN", ""):
            assert rate_limit._is_internal_service_call(_request("Bearer ")) is False
            assert rate_limit._is_internal_service_call(_request("Bearer x")) is False

    def test_a_near_miss_token_is_not_exempt(self):
        from app.middleware import rate_limit

        with patch.object(rate_limit.settings, "IVGS_SERVICE_TOKEN", "s3cr3t-fleet"):
            assert rate_limit._is_internal_service_call(
                _request("Bearer s3cr3t-fleeu")
            ) is False

    def test_the_comparison_is_constant_time(self):
        # Same primitive get_service_or_user uses. A rate limiter that leaks the
        # service token through timing would be a worse bug than the one this
        # fixes.
        import inspect

        from app.middleware import rate_limit

        source = inspect.getsource(rate_limit._is_internal_service_call)
        assert "hmac.compare_digest" in source
        assert "==" not in source.split("return")[-1]


class TestTheLoginBucketIsNeverExempt:

    def test_the_login_classifier_is_unchanged(self):
        from app.middleware.rate_limit import _classify_request

        assert _classify_request("/api/v1/auth/login", "POST") == "login"

    def test_the_exemption_is_gated_on_the_bucket_not_only_the_token(self):
        # Read from the source rather than asserted behaviourally, because the
        # login path fails CLOSED on a Redis error and cannot be exercised here
        # without a Redis. The guard that matters is that the exemption is
        # conditioned on `bucket != "login"`.
        import inspect

        from app.middleware.rate_limit import RateLimitMiddleware

        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert 'bucket != "login" and _is_internal_service_call(request)' in source


class TestTheLimitsThemselvesAreUnchanged:
    """This package widened WHO is exempt, not the ceilings for everyone else."""

    def test_the_three_buckets_keep_their_values(self):
        from app.middleware.rate_limit import RATE_LIMITS

        assert RATE_LIMITS["login"] == (5, 60)
        assert RATE_LIMITS["job_trigger"] == (10, 60)
        assert RATE_LIMITS["default"] == (60, 60)

    def test_get_requests_are_still_skipped_entirely(self):
        import inspect

        from app.middleware.rate_limit import RateLimitMiddleware

        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert 'method == "GET"' in source
