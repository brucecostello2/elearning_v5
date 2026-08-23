"""
WP-41 — retry / timeout / liveness policy (AD-05 §9, Draft 2 Appendix C).

§9 says spec Table 6-4's values are "preserved as values, not redesigned."
This file is what makes that checkable: it reads the constants off the LIVE
Celery task objects and asserts the policy table carries the same numbers.

That is not ceremony. Writing this test found a real error: the first draft of
``policies.py`` used Celery's documented default retry delay of 180 s for
stages 1 and 2, which declare no ``default_retry_delay`` of their own. They do
not get 180 -- ``IVGSBaseTask`` sets 5 (``celery_app.py:694``). A 36x wrong
first-retry interval on both LLM stages, from reading the docs instead of the
base class.
"""

from __future__ import annotations

import importlib

import pytest

# The stage task modules import celery_app, WorkerConfig and httpx. They are
# present in /opt/ivgs/.venv (where the repo suite runs) and absent from the
# shadow venv, which carries only the Temporal SDK. Gated at module level so a
# full-directory run in EITHER venv is clean: here the file skips, and in the
# repo venv the two SDK files skip. A skip is visible; a failure that means
# "wrong interpreter" is noise that hides real ones.
pytest.importorskip(
    "celery",
    reason="reads the live Celery task objects; run this file in /opt/ivgs/.venv",
)

from temporal_pipeline import policies
from temporal_pipeline.policies import (
    ALL_POLICIES,
    RESERVATION_POLICIES,
    STAGE_POLICIES,
)

# (policy, module, attribute holding the live Celery task)
LIVE_TASKS = [
    (policies.REFINE_TRANSCRIPT, "tasks.stage1_transcript", "refine_transcript_task"),
    (policies.GENERATE_STORYBOARD, "tasks.stage2_storyboard", "generate_storyboard_task"),
    (policies.RENDER_SCENE_IMAGE, "tasks.stage3_images", "generate_scene_images_task"),
    (policies.RENDER_SCENE_ANIMATION, "tasks.stage3_images", "generate_scene_images_task"),
    (policies.RENDER_SCENE_VIDEO, "tasks.video_generation_task", "generate_video_clips"),
    (policies.BUILD_COMPOSITION_MANIFEST, "tasks.stage4_manifest", "build_composition_manifest"),
    (policies.GENERATE_VOICEOVER, "tasks.stage5_voiceover", "generate_voiceover_task"),
    (policies.RENDER_TALKING_HEAD, "tasks.talking_head_task", "render_talking_head"),
    (policies.ASSEMBLE_PROTOTYPE_DRAFT, "tasks.stage7_prototype_draft", "assemble_prototype_draft"),
    (policies.RENDER_FINAL, "tasks.stage8_final_render", "render_final"),
]


def live_task(module: str, attribute: str):
    return getattr(importlib.import_module(module), attribute)


@pytest.mark.parametrize(
    "policy, module, attribute",
    LIVE_TASKS,
    ids=[p.activity for p, _, _ in LIVE_TASKS],
)
class TestAgainstTheLiveTasks:
    def test_registered_name_matches(self, policy, module, attribute):
        """
        Including the three that do not match their filename:
        stage5_voiceover.py -> tasks.stage4_voiceover.*,
        stage7_prototype_draft.py -> tasks.prototype_draft_task.*,
        stage8_final_render.py -> tasks.final_render_task.*  (ledger P2.3).
        """
        assert policy.celery_task_name == live_task(module, attribute).name

    def test_retry_and_timeout_constants_match(self, policy, module, attribute):
        task = live_task(module, attribute)
        assert policy.celery_max_retries == task.max_retries
        assert policy.celery_retry_delay_s == task.default_retry_delay
        assert policy.celery_soft_time_limit_s == task.soft_time_limit
        assert policy.celery_time_limit_s == task.time_limit


class TestTranslation:
    def test_attempts_are_retries_plus_one(self):
        """
        Celery's max_retries=N is N+1 executions. Temporal's maximum_attempts
        is the total. Copying the integer across would silently delete one
        execution from every stage.
        """
        for policy in ALL_POLICIES:
            assert policy.maximum_attempts == policy.celery_max_retries + 1

    def test_known_attempt_counts(self):
        assert policies.REFINE_TRANSCRIPT.maximum_attempts == 5      # retries 4
        assert policies.GENERATE_VOICEOVER.maximum_attempts == 4     # retries 3
        assert policies.RENDER_SCENE_VIDEO.maximum_attempts == 3     # retries 2

    def test_backoff_ceiling_preserves_retry_backoff_max(self):
        """IVGSBaseTask.retry_backoff_max = 300 (celery_app.py:696)."""
        for policy in ALL_POLICIES:
            assert policy.maximum_interval_s == 300

    def test_start_to_close_is_never_below_todays_hard_limit(self):
        """
        §9 relaxes the hard ceiling because heartbeat_timeout now carries
        liveness. Relaxing is intended; TIGHTENING would silently start
        failing renders that succeed today.
        """
        for policy in STAGE_POLICIES:
            if policy.celery_time_limit_s is None:
                continue
            assert policy.start_to_close_s >= policy.celery_time_limit_s, policy.activity


class TestLiveness:
    def test_every_stage_activity_heartbeats(self):
        """
        AD-05 §9: heartbeating is a requirement on the wrapper, not an option.
        It is what removes D1's guessed visibility timeout.
        """
        for policy in STAGE_POLICIES:
            assert policy.heartbeat_s is not None, policy.activity
            assert 0 < policy.heartbeat_s < policy.start_to_close_s

    def test_reservation_activities_do_not_heartbeat(self):
        """Sub-second calls into ivgs-scheduler. Appendix C: "s2c 60 s, no hb"."""
        for policy in RESERVATION_POLICIES:
            assert policy.heartbeat_s is None
            assert policy.start_to_close_s == 60

    def test_retry_intervals_are_positive(self):
        """Temporal rejects a zero initial_interval outright."""
        for policy in ALL_POLICIES:
            assert policy.initial_interval_s > 0, policy.activity


class TestQueues:
    def test_queues_match_ad05_section_4_2(self):
        assert {p.queue for p in ALL_POLICIES} <= {
            "default", "gpu_llm", "gpu_image", "gpu_video",
            "gpu_tts", "gpu_talking_head", "composition",
        }

    def test_queue_matches_celery_routing(self):
        """
        Where a decorator carries queue= we compare against it; where it does
        not (stages 3 and 5), the queue comes from TASK_ROUTES.
        """
        from celery_app import TASK_ROUTES

        for policy, module, attribute in LIVE_TASKS:
            task = live_task(module, attribute)
            declared = getattr(task, "queue", None)
            if declared:
                assert policy.queue == declared, policy.activity
                continue
            prefix = policy.celery_task_name.rsplit(".", 1)[0] + ".*"
            assert policy.queue == TASK_ROUTES[prefix]["queue"], policy.activity

    def test_image_and_animation_share_gpu_image(self):
        assert policies.RENDER_SCENE_IMAGE.queue == "gpu_image"
        assert policies.RENDER_SCENE_ANIMATION.queue == "gpu_image"
        assert policies.RENDER_SCENE_VIDEO.queue == "gpu_video"


class TestNonRetryable:
    def test_deterministic_failures_do_not_burn_attempts(self):
        for policy in STAGE_POLICIES:
            assert "ValueError" in policy.non_retryable_error_types, policy.activity

    def test_stage7_render_error_is_non_retryable(self):
        """
        WP-27 / swallow-register 14. Stage 7 raises rather than returning
        status=failed; retrying an ffmpeg composition that produced no draft
        produces no draft again.
        """
        assert (
            "Stage7RenderError"
            in policies.ASSEMBLE_PROTOTYPE_DRAFT.non_retryable_error_types
        )


class TestCoverage:
    def test_every_pipeline_stage_has_exactly_one_policy(self):
        from temporal_pipeline.dag import build_pipeline_dag
        from temporal_pipeline.reference_storyboard import reference_storyboard

        labels = {
            n.label
            for n in build_pipeline_dag(reference_storyboard())
            if not n.is_gate
        }
        assert labels == {p.label for p in STAGE_POLICIES}

    def test_policy_lookup_tables_agree(self):
        assert len(policies.POLICY_BY_LABEL) == len(STAGE_POLICIES)
        assert len(policies.POLICY_BY_ACTIVITY) == len(ALL_POLICIES)


def test_gpu_reservation_failure_is_not_fatal_while_the_registry_is_empty():
    """
    AD-05 O-3 was ruled (a) fatal-with-retry, explicitly contingent on ledger
    P2.6 having made the heartbeat registry real. It has not: the registry
    reports total_nodes:0 and /fleet shows 23 stranded urgent requests
    (CLAUDE.md §7, measured under WP-08 on 2026-08-23). Shipping fatal against
    an empty registry would fail every GPU stage, which is precisely what the
    ruling's contingency exists to prevent.

    When P2.6 lands, flipping this constant is the whole change -- and this
    test is where the reason it was False gets read and retired.
    """
    assert policies.GPU_RESERVATION_FAILURE_IS_FATAL is False
