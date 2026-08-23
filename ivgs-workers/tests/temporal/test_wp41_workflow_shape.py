"""
WP-41 — assertions that need the Temporal SDK loaded.

The SDK is deliberately NOT in ``/opt/ivgs/.venv``: that venv runs the repo's
whole Python suite, and adding ``temporalio`` to it would put a new dependency
under every existing test for the sake of a package no production path
imports. The shadow runs from ``/home/dev/.venv-ivgs-temporal``.

So this file skips when the SDK is absent, and everything that can be asserted
without it lives in the other four files -- which is most of it. Run this one
with:

    PYTHONPATH=/opt/ivgs/ivgs-workers \\
      /home/dev/.venv-ivgs-temporal/bin/python -m pytest \\
      /opt/ivgs/ivgs-workers/tests/temporal/test_wp41_workflow_shape.py

A skip here is reported as a skip, not as a pass. If this file is silent in a
run, the SDK was not installed for that interpreter.
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "temporalio",
    reason="Temporal SDK is installed in /home/dev/.venv-ivgs-temporal, not the repo venv",
)

from temporal_pipeline import activities, policies  # noqa: E402
from temporal_pipeline.payloads import RenderSceneImageInput  # noqa: E402
from temporal_pipeline.workflow import (  # noqa: E402
    GPU_QUEUES,
    WORKFLOW_PATCH_GPU_BRACKET,
    PipelineInput,
    PipelineState,
    VideoPipelineWorkflow,
)


class TestActivityRegistration:
    def test_every_policy_has_an_activity_and_vice_versa(self):
        registered = {getattr(a, "__name__", "") for a in activities.ALL_ACTIVITIES}
        assert registered == set(policies.POLICY_BY_ACTIVITY)

    def test_image_and_animation_are_two_names_over_one_implementation(self):
        """
        Two registered names so the event history answers "which stage ran"
        without decoding a payload -- the question WP-39 could not answer for
        three hours. One implementation because they genuinely are one task.
        """
        import typing

        assert activities.render_scene_image is not activities.render_scene_animation
        # `from __future__ import annotations` leaves these as strings until
        # resolved, so compare the resolved types, not the raw __annotations__.
        image = typing.get_type_hints(activities.render_scene_image)
        animation = typing.get_type_hints(activities.render_scene_animation)
        assert image["inp"] is animation["inp"] is RenderSceneImageInput
        assert image["return"] is animation["return"]

    def test_reservation_activities_exist_as_a_pair(self):
        names = {getattr(a, "__name__", "") for a in activities.ALL_ACTIVITIES}
        assert {"acquire_gpu_reservation", "release_gpu_reservation"} <= names


class TestWorkflowSurface:
    def test_both_gates_and_the_two_extra_signals_are_declared(self):
        """
        AD-05 §5.3 requires storyboard_rejected/regenerate and cancel_job as
        well as the two gates -- "neither exists today".
        """
        for name in (
            "storyboard_approved",
            "draft_approved",
            "storyboard_rejected",
            "cancel_job",
        ):
            assert callable(getattr(VideoPipelineWorkflow, name)), name

    def test_state_query_exists(self):
        assert callable(VideoPipelineWorkflow.state)

    def test_gpu_queues_exclude_the_cpu_queues(self):
        assert "default" not in GPU_QUEUES
        assert "composition" not in GPU_QUEUES
        assert GPU_QUEUES == {
            "gpu_llm", "gpu_image", "gpu_video", "gpu_tts", "gpu_talking_head",
        }

    def test_a_patch_id_exists_before_the_first_logic_change(self):
        """
        AD-05 §7.2: adopt versioning on the first workflow written, because
        retrofitting it once in-flight jobs exist is the failure mode.
        """
        assert WORKFLOW_PATCH_GPU_BRACKET


class TestRetryPolicyConstruction:
    def test_every_policy_builds_a_real_retry_policy(self):
        from datetime import timedelta

        for policy in policies.ALL_POLICIES:
            built = policies.as_temporal_retry_policy(policy)
            assert built.maximum_attempts == policy.celery_max_retries + 1
            assert built.initial_interval == timedelta(seconds=policy.initial_interval_s)
            assert built.maximum_interval == timedelta(seconds=300)

    def test_activity_options_carry_queue_timeout_and_heartbeat(self):
        opts = VideoPipelineWorkflow._activity_opts(policies.RENDER_SCENE_VIDEO)
        assert opts["task_queue"] == "gpu_video"
        assert opts["start_to_close_timeout"].total_seconds() == 90 * 60
        assert opts["heartbeat_timeout"].total_seconds() == 60

    def test_reservation_options_carry_no_heartbeat(self):
        opts = VideoPipelineWorkflow._activity_opts(policies.ACQUIRE_GPU_RESERVATION)
        assert "heartbeat_timeout" not in opts


class TestWorkflowInput:
    def test_input_defaults_run_the_whole_graph_with_reservations(self):
        inp = PipelineInput(job_id="job-1")
        assert inp.include_final_render is True
        assert inp.gpu_reservations is True
        assert inp.storyboard == []

    def test_state_starts_empty_and_unfinished(self):
        state = PipelineState()
        assert state.finished is False
        assert state.completed_nodes == []
        assert state.media_labels_completed == []
