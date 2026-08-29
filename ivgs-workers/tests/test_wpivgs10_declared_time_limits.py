"""WP-IVGS-10 addendum — AD-05's declared time limits are APPLIED, not documented.

⛔ THE DEFECT, MEASURED ON THE OPERATOR'S OWN GOLDEN RUN.

Project 4ca0d5c5, job 213171b5, task a34a33ab: `SoftTimeLimitExceeded` at
**exactly 120 s**, during `vllm_storyboard_request_starting`. Node-02's vLLM log
for the 03:48-03:54 window shows the request ARRIVED and was BEING SERVED —
`POST /v1/chat/completions 200 OK` at 03:49:38, prefill at 809.8 tok/s, then
~20 tok/s continuously with `Running: 1 reqs` until 03:51:35. **The client gave
up while the server was mid-generation.**

`temporal_pipeline/policies.py` had declared `start_to_close_s = 300` for that
activity since WP-41. The decorator said `soft_time_limit=120`. **The table was
a mirror with no authority**, so the stage ran at 2.5x under its own declared
policy and nothing could notice.

⛳ AND THE FIX IS A WRAP, NOT AN EDIT. Those limits live in decorators inside the
eight FROZEN stage task bodies. `task_annotations` reaches the same task objects
from outside — the seam `dev/CLAUDE.md` §3 sanctions — and fixes every stage at
once rather than one literal at a time.
"""
from __future__ import annotations

import pytest

from celery_app import (
    apply_declared_time_limits,
    celery_app,
    check_visibility_timeout,
    collect_task_time_limits,
)
from temporal_pipeline.policies import ALL_POLICIES, GENERATE_STORYBOARD


@pytest.fixture(scope="module", autouse=True)
def _applied():
    """Apply once for the module, as `on_worker_init` does at worker start."""
    return apply_declared_time_limits(celery_app)


def test_stage2_carries_its_declared_limit_and_not_the_decorator_literal():
    """⛔ THE ONE THAT WOULD HAVE SAVED THE GOLDEN RUN."""
    task = celery_app.tasks["tasks.stage2_storyboard.generate_storyboard_task"]
    assert task.soft_time_limit == 270
    assert task.time_limit == 300


def test_stage2_has_real_margin_over_the_observed_generation_time():
    """The measurement, as a number rather than a hope.

    The v7 re-proof completed at ~110 s and the operator's run was still
    generating at 120 s. 270 s of soft budget is a bit over twice the longest
    run actually observed. This asserts the margin exists; it is not a claim
    that 270 is provably enough forever.
    """
    observed_longest_s = 130
    assert GENERATE_STORYBOARD.celery_soft_time_limit_s >= 2 * observed_longest_s


@pytest.mark.parametrize(
    "policy", [p for p in ALL_POLICIES if p.celery_time_limit_s is not None],
    ids=lambda p: p.activity,
)
def test_every_declared_policy_reaches_its_live_task(policy):
    """The table is the definition, so every row must land on a real task."""
    task = celery_app.tasks.get(policy.celery_task_name)
    assert task is not None, policy.celery_task_name
    assert task.soft_time_limit == policy.celery_soft_time_limit_s
    assert task.time_limit == policy.celery_time_limit_s


def test_a_policy_naming_an_unregistered_task_is_REFUSED_not_warned():
    """⛔ A SILENT NO-OP THAT REPORTS SUCCESS IS THE FAILURE MODE HERE.

    The first cut of `apply_declared_time_limits` skipped tasks it could not
    find and still returned a full `applied` dict — so a caller was told the
    policy had landed when the registry was empty and nothing had changed. It
    now raises, and this pins that.
    """
    from unittest.mock import patch

    class _EmptyRegistry(dict):
        def get(self, key, default=None):
            return None

    with patch.object(celery_app, "tasks", _EmptyRegistry()):
        with pytest.raises(ValueError, match="not registered"):
            apply_declared_time_limits(celery_app)


def test_soft_is_always_below_hard():
    """A soft limit at or above the hard one never fires: the task is killed
    with no chance to clean up, and the failure arrives as a worker-lost rather
    than as a stage error anyone can read."""
    for policy in ALL_POLICIES:
        if policy.celery_soft_time_limit_s is None:
            continue
        assert policy.celery_soft_time_limit_s < policy.celery_time_limit_s, policy.activity


def test_p0_1_still_holds_after_the_widening():
    """⛔ LEDGER P0.1. `broker_visibility_timeout` must exceed every hard limit,
    or a long task is redelivered mid-flight and runs twice.

    Asserted against the limits as APPLIED, which is the point: before this
    package the gate checked decorator literals that the policy did not govern.
    """
    limits = collect_task_time_limits(celery_app)
    visibility = celery_app.conf.broker_transport_options.get("visibility_timeout")
    assert visibility == 7200
    assert max(limits.values()) < visibility
    check_visibility_timeout(visibility, limits)      # raises if violated


def test_the_widening_did_not_touch_any_other_stage():
    """Stage 2 is the only row this addendum moved. Every other stage keeps the
    limits it had, and the ones sitting under Appendix C are REGISTER ROWS, not
    silent fixes — the order was explicit about that."""
    unchanged = {
        "tasks.stage1_transcript.refine_transcript_task": (120, 150),
        "tasks.stage3_images.generate_scene_images_task": (1800, 2100),
        "tasks.stage4_voiceover.generate_voiceover_task": (900, 1200),
        "tasks.video_generation_task.generate_video_clips": (3600, 3900),
        "tasks.talking_head_task.render_talking_head": (3600, 3900),
        "tasks.animation_generation_task.generate_scene_animations": (3600, 3900),
        "tasks.prototype_draft_task.assemble_prototype_draft": (900, 960),
        "tasks.final_render_task.render_final": (1800, 1860),
    }
    for name, (soft, hard) in unchanged.items():
        task = celery_app.tasks[name]
        assert (task.soft_time_limit, task.time_limit) == (soft, hard), name


def test_the_policy_import_does_not_depend_on_the_WORKING_DIRECTORY():
    """⛔ THIS TOOK THE WORKERS DOWN ON ALL FOUR NODES, AND EVERY CHECK I RAN
    BEFOREHAND PASSED.

    `cd /app && python -c "import temporal_pipeline"` SUCCEEDS.
    `cd /app && celery -A celery_app worker` FAILS with `No module named
    'temporal_pipeline'`.

    `python -c` puts the cwd on `sys.path` as `''`; a console-script entry point
    puts the SCRIPT's directory there instead, and Celery's `-A` resolution only
    fixes the path far enough to import the app module itself. So the mechanism
    verified clean under `docker run ... python -c` and killed the worker that
    actually runs — a false green produced by testing through a different door
    from the one production uses.

    The import is now anchored to `celery_app.__file__`. This test asserts that
    anchoring rather than the symptom, because reproducing the symptom needs a
    console script and this suite has none.
    """
    import inspect

    import celery_app as module

    source = inspect.getsource(module.apply_declared_time_limits)
    assert "__file__" in source, (
        "the policy import is no longer anchored to this module's own location; "
        "it will work under `python -c` and fail under `celery -A`"
    )
    # ...and it must still resolve from a foreign working directory.
    import os
    import subprocess

    here = os.path.dirname(os.path.abspath(module.__file__))
    proc = subprocess.run(
        [__import__("sys").executable, "-c",
         "import sys; sys.path.insert(0, %r); "
         "import celery_app; "
         "print('resolved', bool(celery_app.apply_declared_time_limits))" % here],
        cwd="/", capture_output=True, text=True,
    )
    assert "resolved True" in proc.stdout, proc.stderr[-500:]
