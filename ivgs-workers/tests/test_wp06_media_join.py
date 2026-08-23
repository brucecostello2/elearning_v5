"""
WP-06-MEDIA-JOIN - ledger P1.1

Three defects, one join:

1. `_decrement_media_task_count` returned 0 from its exception handler, and the
   caller reads `remaining <= 0` as "all media reported, dispatch Stage 4". One
   transient Redis error advanced the pipeline on incomplete footage.
2. `_store_media_task_count` swallowed its failure, so the counter key could be
   absent; `DECR` on a missing key returns -1, `max(0, -1) == 0`, and the join
   collapsed on the first stage to report.
3. No idempotency. The completion callback fires before the ack
   (stage3_images.py:757, video_generation_task.py:576) and acks_late +
   task_reject_on_worker_lost requeue the media task if the worker dies in that
   window - so the same stage reported twice and decremented twice.

These tests run against a REAL Redis, because the fix is a Lua script and a
mock cannot prove a server-side script is atomic or even syntactically valid.
Point IVGS_TEST_REDIS_URL at a throwaway instance:

    docker run -d --rm --name wp06-redis -p 127.0.0.1:16380:6379 redis:7.4
    IVGS_TEST_REDIS_URL=redis://127.0.0.1:16380/0 pytest ivgs-workers/tests/test_wp06_media_join.py
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

import pytest

from tasks.pipeline_orchestrator_v2 import (
    JOIN_DECREMENTED,
    JOIN_DUPLICATE,
    JOIN_UNKNOWN,
    MEDIA_GENERATION_STAGES,
    MediaJoinStoreError,
    MediaJoinUnknownError,
    _decrement_media_task_count,
    _handle_media_generation_completion,
    _media_join_seen_key,
    _store_media_task_count,
)

TEST_REDIS_URL = os.environ.get("IVGS_TEST_REDIS_URL", "redis://127.0.0.1:16380/0")


def _redis_available() -> bool:
    try:
        import redis

        redis.Redis.from_url(TEST_REDIS_URL, socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason=f"no Redis at {TEST_REDIS_URL}; see this module's docstring",
)


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    """Nothing in this module may reach a real broker. AUTOUSE, deliberately.

    Learned the hard way on 2026-08-23: an earlier draft of these tests called
    _handle_media_generation_completion for real, which calls
    celery_app.send_task, which resolved `node-01` from /etc/hosts and published
    four genuine tasks.stage4_manifest.build_composition_manifest messages onto
    the PRODUCTION broker with fabricated job ids. The live default worker
    consumed them and retried them against a 500 from the API until they were
    revoked. See the WP-06 report, "Incident".

    Patching send_task is also better testing: it lets a test assert that the
    dispatch happened exactly once, which a live send cannot.
    """
    import tasks.pipeline_orchestrator_v2 as orch

    sent = MagicMock()
    sent.return_value = MagicMock(id="fake-task-id")
    monkeypatch.setattr(orch.celery_app, "send_task", sent)
    return sent


@pytest.fixture()
def cfg():
    """A WorkerConfig stand-in carrying only what the join helpers read."""
    c = MagicMock()
    c.redis_url = TEST_REDIS_URL
    return c


@pytest.fixture()
def job_id():
    return f"wp06-{uuid.uuid4()}"


@pytest.fixture()
def r():
    import redis

    return redis.Redis.from_url(TEST_REDIS_URL)


@pytest.fixture()
def broken_cfg():
    """Points at a port with nothing on it - a real connection failure."""
    c = MagicMock()
    c.redis_url = "redis://127.0.0.1:16399/0"
    return c


STAGE_IMAGE = "image_generation"
STAGE_VIDEO = "video_generation"


class TestUnknownIsNotZero:
    """Exit-gate clause 1: a simulated Redis error must NOT advance the pipeline."""

    def test_connection_failure_reports_unknown_not_complete(self, broken_cfg, job_id):
        outcome, remaining = _decrement_media_task_count(job_id, STAGE_IMAGE, broken_cfg)
        assert outcome == JOIN_UNKNOWN
        # The pre-fix code returned 0 here, and the caller reads `remaining <= 0`
        # as "all media reported". The outcome, not the number, is now what the
        # caller branches on.
        assert outcome != JOIN_DECREMENTED

    def test_the_caller_raises_rather_than_dispatching_stage_4(
        self, broken_cfg, job_id, no_broker
    ):
        """The whole point: no send_task, no advance."""
        log = MagicMock()
        with pytest.raises(MediaJoinUnknownError) as exc:
            _handle_media_generation_completion(
                completed_stage=STAGE_IMAGE,
                stage_output={"job_id": job_id, "status": "success"},
                config=broken_cfg,
                log=log,
            )
        assert "not advancing" in str(exc.value).lower()
        assert job_id in str(exc.value)
        no_broker.assert_not_called()

    def test_a_failed_media_stage_also_reports_unknown_not_complete(
        self, broken_cfg, job_id
    ):
        """Partial-advance must not become a back door for the unknown case."""
        log = MagicMock()
        with pytest.raises(MediaJoinUnknownError):
            _handle_media_generation_completion(
                completed_stage=STAGE_VIDEO,
                stage_output={"job_id": job_id, "status": "failed"},
                config=broken_cfg,
                log=log,
            )


class TestMissingKeyCannotReadAsComplete:
    """Exit-gate clause 3."""

    def test_unarmed_counter_reports_unknown(self, cfg, job_id):
        # No _store_media_task_count call at all - the key does not exist.
        outcome, remaining = _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        assert outcome == JOIN_UNKNOWN

    def test_pre_fix_arithmetic_would_have_read_it_as_complete(self, cfg, job_id, r):
        """Demonstrates the defect against the pre-fix expression, executably.

        This is the "tests fail against the pre-fix code" requirement: the old
        body was `max(0, r.decr(key))`, and here it is, on a missing key.
        """
        pre_fix_value = max(0, r.decr(f"ivgs:media_tasks:{job_id}"))
        assert pre_fix_value == 0, "pre-fix: a missing key reads as 'all complete'"
        r.delete(f"ivgs:media_tasks:{job_id}")

        # The fix, same starting state:
        outcome, _ = _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        assert outcome == JOIN_UNKNOWN

    def test_watchdog_claim_leaves_unknown_not_complete(self, cfg, job_id, r):
        """media_join_watchdog deletes the counter when it claims a stalled job."""
        _store_media_task_count(job_id, 3, cfg)
        r.delete(f"ivgs:media_tasks:{job_id}")  # what the watchdog does, :1123-1127
        outcome, _ = _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        assert outcome == JOIN_UNKNOWN


class TestIdempotency:
    """Exit-gate clause 2: a duplicate callback decrements exactly once."""

    def test_duplicate_report_for_same_stage_decrements_once(self, cfg, job_id, r):
        _store_media_task_count(job_id, 3, cfg)

        first = _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        second = _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        third = _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)

        assert first == (JOIN_DECREMENTED, 2)
        assert second == (JOIN_DUPLICATE, 0)
        assert third == (JOIN_DUPLICATE, 0)
        assert int(r.get(f"ivgs:media_tasks:{job_id}")) == 2, (
            "three deliveries of one stage's completion moved the counter once"
        )

    def test_different_stages_each_decrement(self, cfg, job_id, r):
        _store_media_task_count(job_id, 3, cfg)
        assert _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)[0] == JOIN_DECREMENTED
        assert _decrement_media_task_count(job_id, STAGE_VIDEO, cfg)[0] == JOIN_DECREMENTED
        assert int(r.get(f"ivgs:media_tasks:{job_id}")) == 1

    def test_duplicate_does_not_dispatch_stage_4(self, cfg, job_id, no_broker):
        _store_media_task_count(job_id, 1, cfg)
        log = MagicMock()

        first = _handle_media_generation_completion(
            completed_stage=STAGE_IMAGE,
            stage_output={"job_id": job_id, "status": "success"},
            config=cfg,
            log=log,
        )
        assert first["action"] == "dispatched", "the genuine report must advance"
        assert no_broker.call_count == 1, "exactly one Stage 4 dispatch"

        second = _handle_media_generation_completion(
            completed_stage=STAGE_IMAGE,
            stage_output={"job_id": job_id, "status": "success"},
            config=cfg,
            log=log,
        )
        assert second["action"] == "duplicate_ignored"
        assert "celery_task_id" not in second, "a duplicate must not dispatch again"
        assert no_broker.call_count == 1, "still one - the duplicate dispatched nothing"

    def test_pre_fix_would_have_double_decremented(self, cfg, job_id, r):
        """The pre-fix body again, executably: two DECRs, counter drops by two."""
        r.set(f"ivgs:media_tasks:{job_id}", 3)
        max(0, r.decr(f"ivgs:media_tasks:{job_id}"))
        max(0, r.decr(f"ivgs:media_tasks:{job_id}"))
        assert int(r.get(f"ivgs:media_tasks:{job_id}")) == 1, (
            "pre-fix: one stage reporting twice consumed two of three slots"
        )
        r.delete(f"ivgs:media_tasks:{job_id}")

    def test_guard_key_uses_stage_not_scene(self, job_id):
        """The brief says (job_id, scene_id); the code has no scene granularity."""
        key = _media_join_seen_key(job_id, STAGE_IMAGE)
        assert key == f"ivgs:media_join_seen:{job_id}:{STAGE_IMAGE}"

    def test_guard_key_carries_a_ttl(self, cfg, job_id, r):
        _store_media_task_count(job_id, 3, cfg)
        _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        ttl = r.ttl(_media_join_seen_key(job_id, STAGE_IMAGE))
        assert ttl > 0, "an immortal guard key would leak one entry per job forever"


class TestStoreFailsLoudly:
    def test_store_raises_when_redis_is_unreachable(self, broken_cfg, job_id):
        with pytest.raises(MediaJoinStoreError) as exc:
            _store_media_task_count(job_id, 3, broken_cfg)
        assert job_id in str(exc.value)

    def test_store_clears_stale_guards_so_a_redispatch_rearms(self, cfg, job_id, r):
        _store_media_task_count(job_id, 3, cfg)
        _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        assert r.exists(_media_join_seen_key(job_id, STAGE_IMAGE))

        _store_media_task_count(job_id, 3, cfg)  # re-dispatch
        assert not r.exists(_media_join_seen_key(job_id, STAGE_IMAGE))
        assert _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)[0] == JOIN_DECREMENTED

    def test_store_clears_the_failure_counter(self, cfg, job_id, r):
        r.set(f"ivgs:media_failures:{job_id}", 7)
        _store_media_task_count(job_id, 3, cfg)
        assert not r.exists(f"ivgs:media_failures:{job_id}")

    def test_every_media_stage_guard_is_cleared(self, cfg, job_id, r):
        _store_media_task_count(job_id, 3, cfg)
        for stage in MEDIA_GENERATION_STAGES:
            _decrement_media_task_count(job_id, stage, cfg)
        _store_media_task_count(job_id, 3, cfg)
        for stage in MEDIA_GENERATION_STAGES:
            assert not r.exists(_media_join_seen_key(job_id, stage))


class TestPartialAdvanceSurvives:
    """Commit 35d9226 behaviour: a failed scene drains, it does not fail-fast."""

    def test_failed_stage_still_decrements_and_advances(self, cfg, job_id):
        _store_media_task_count(job_id, 1, cfg)
        log = MagicMock()
        result = _handle_media_generation_completion(
            completed_stage=STAGE_IMAGE,
            stage_output={"job_id": job_id, "status": "failed"},
            config=cfg,
            log=log,
        )
        assert result["action"] == "dispatched"
        assert result["failed_count"] == 1, "the failure is carried, not swallowed"

    def test_partial_failure_advances_with_a_failed_count(self, cfg, job_id):
        _store_media_task_count(job_id, 2, cfg)
        log = MagicMock()
        first = _handle_media_generation_completion(
            completed_stage=STAGE_IMAGE,
            stage_output={"job_id": job_id, "status": "failed"},
            config=cfg,
            log=log,
        )
        assert first["action"] == "waiting"
        assert first["remaining_tasks"] == 1

        second = _handle_media_generation_completion(
            completed_stage=STAGE_VIDEO,
            stage_output={"job_id": job_id, "status": "success"},
            config=cfg,
            log=log,
        )
        assert second["action"] == "dispatched"
        assert second["failed_count"] == 1

    def test_all_success_advances_with_zero_failures(self, cfg, job_id):
        _store_media_task_count(job_id, 1, cfg)
        log = MagicMock()
        result = _handle_media_generation_completion(
            completed_stage=STAGE_VIDEO,
            stage_output={"job_id": job_id, "status": "success"},
            config=cfg,
            log=log,
        )
        assert result["action"] == "dispatched"
        assert result["failed_count"] == 0
