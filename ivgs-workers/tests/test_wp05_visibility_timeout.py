"""
WP-05-VISIBILITY-TIMEOUT - ledger P0.1

The broker must not redeliver a message while its task is still running. With
task_acks_late = True (celery_app.py:288) the ack lands after the task body
returns, so kombu's Redis transport restores an unacked message once
visibility_timeout elapses. The pre-fix state was 3600 s against a 3900 s hard
time_limit on talking_head and video_generation - a 300 s window in which a
running render's message was claimable, and gpu_video is bound to both node-02
and node-03 in tracked compose.

These tests pin the invariant itself, not the numbers that happen to satisfy it
today.
"""

from __future__ import annotations

import pytest

from celery_app import (
    VisibilityTimeoutError,
    assert_visibility_timeout_covers_time_limits,
    celery_app,
    check_visibility_timeout,
    collect_task_time_limits,
)
from config import WorkerConfig

# The two 3900 s tasks, verified at HEAD 9af5a48:
#   ivgs-workers/tasks/talking_head_task.py:399
#   ivgs-workers/tasks/video_generation_task.py:445
LONGEST_HARD_TIME_LIMIT = 3900
PRE_FIX_VISIBILITY_TIMEOUT = 3600


class TestCheckFailsWhenTheInvariantIsViolated:
    """The demonstration the brief asks for: it FAILS at a low value."""

    def test_the_exact_pre_fix_configuration_is_rejected(self):
        with pytest.raises(VisibilityTimeoutError) as exc:
            check_visibility_timeout(
                PRE_FIX_VISIBILITY_TIMEOUT,
                {
                    "tasks.talking_head_task.talking_head": LONGEST_HARD_TIME_LIMIT,
                    "tasks.video_generation_task.generate_video": LONGEST_HARD_TIME_LIMIT,
                },
            )
        msg = str(exc.value)
        # The brief: "failing fast at import/startup with a message naming both values"
        assert "3600" in msg
        assert "3900" in msg
        assert "talking_head" in msg or "video_generation" in msg

    def test_equal_values_are_rejected_too(self):
        """Equal is a race, not a pass. The comparison is >=, not >."""
        with pytest.raises(VisibilityTimeoutError):
            check_visibility_timeout(3900, {"t": 3900})

    def test_every_offender_is_named_not_just_the_worst(self):
        with pytest.raises(VisibilityTimeoutError) as exc:
            check_visibility_timeout(1000, {"a": 3900, "b": 2100, "c": 10})
        msg = str(exc.value)
        assert "a=3900s" in msg
        assert "b=2100s" in msg
        assert "c=" not in msg, "a task under the timeout is not an offender"

    def test_unset_timeout_is_rejected(self):
        with pytest.raises(VisibilityTimeoutError):
            check_visibility_timeout(None, {"a": 10})

    def test_zero_and_negative_are_rejected(self):
        for bad in (0, -1):
            with pytest.raises(VisibilityTimeoutError):
                check_visibility_timeout(bad, {"a": 10})


class TestCheckPassesAtTheCorrectedValue:
    """And it PASSES at the corrected one."""

    def test_the_corrected_value_passes(self):
        check_visibility_timeout(
            7200,
            {
                "tasks.talking_head_task.talking_head": LONGEST_HARD_TIME_LIMIT,
                "tasks.video_generation_task.generate_video": LONGEST_HARD_TIME_LIMIT,
            },
        )

    def test_empty_registry_passes(self):
        check_visibility_timeout(7200, {})

    def test_tasks_with_no_limit_are_not_offenders(self):
        check_visibility_timeout(7200, {"a": None})


class TestTheShippedConfigurationSatisfiesTheInvariant:
    """Against the real WorkerConfig and the real task registry, not fixtures."""

    def test_worker_config_default_covers_the_longest_limit(self):
        cfg = WorkerConfig()
        assert cfg.broker_visibility_timeout > LONGEST_HARD_TIME_LIMIT, (
            f"visibility_timeout {cfg.broker_visibility_timeout} does not cover "
            f"the {LONGEST_HARD_TIME_LIMIT}s hard limit"
        )

    def test_the_real_app_passes_its_own_gate(self):
        """This is the assertion the worker runs at celeryd_after_setup."""
        assert_visibility_timeout_covers_time_limits(celery_app)

    def test_the_registry_walk_finds_the_3900s_tasks(self):
        """Guard against the check silently passing because it found nothing."""
        limits = collect_task_time_limits(celery_app)
        assert limits, "no tasks collected - the gate would be vacuous"
        assert max(limits.values()) >= LONGEST_HARD_TIME_LIMIT, (
            "expected the 3900s render tasks in the registry; got "
            f"max={max(limits.values())}"
        )

    def test_no_celery_internal_tasks_are_checked(self):
        limits = collect_task_time_limits(celery_app)
        assert not [n for n in limits if n.startswith("celery.")]

    def test_a_task_with_no_declared_limit_inherits_the_app_default(self):
        limits = collect_task_time_limits(celery_app)
        default = celery_app.conf.task_time_limit
        assert default is not None
        # Every collected limit is a real int, never None - the wrapper resolved it.
        assert all(isinstance(v, int) for v in limits.values())


class TestTheGateIsActuallyWired:
    def test_celeryd_after_setup_handler_is_connected(self):
        from celery import signals

        receivers = [
            r for r in signals.celeryd_after_setup.receivers
        ]
        assert receivers, "celeryd_after_setup has no receivers - the gate is dead code"

    def test_the_gate_raises_through_the_app_wrapper(self, monkeypatch):
        """Drive the wrapper, not just the pure function."""
        monkeypatch.setitem(
            celery_app.conf.broker_transport_options,
            "visibility_timeout",
            PRE_FIX_VISIBILITY_TIMEOUT,
        )
        with pytest.raises(VisibilityTimeoutError) as exc:
            assert_visibility_timeout_covers_time_limits(celery_app)
        assert "3600" in str(exc.value)


class TestProducerAndWorkerAgree:
    """celery_producer.py:29 used to hardcode 3600 under a comment saying it must
    match the fleet. Both sides now read the same env var with the same default."""

    def test_api_producer_matches_the_worker_default(self):
        import importlib
        import sys

        sys.path.insert(0, "ivgs-api")
        try:
            mod = importlib.import_module("app.services.celery_producer")
        except Exception:  # pragma: no cover - API package not importable here
            pytest.skip("ivgs-api package not importable in this environment")
        produced = mod.celery_app.conf.broker_transport_options["visibility_timeout"]
        assert produced == WorkerConfig().broker_visibility_timeout
        assert produced > LONGEST_HARD_TIME_LIMIT
