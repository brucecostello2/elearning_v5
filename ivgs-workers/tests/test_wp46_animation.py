"""
WP-46 — animation stops being a still.

Until this package ``STAGE_TASK_MAP[animation_generation]`` named the *image*
task, so every scene the storyboard marked ``animation`` was rendered as a
static PNG by FLUX. WP-39 had already given the branch its own label, its own
checkpoint row and its own Temporal node; what it did not have was a body.

These tests pin what makes the new body correct:

  * the wiring points somewhere else now, on a queue of its own;
  * the workflow graph is MBCP's certified one, byte for byte, and every slot
    in it is filled before the graph is ever POSTed;
  * a scene result is shaped exactly like a video scene result, so the media
    join and the composition manifest read it without knowing the difference;
  * checkpoints are keyed on ``join_stage``, terminal one included (WP-39 (c));
  * the branch refuses, by name, rather than substituting a still — which is
    the failure mode this whole package exists to end.
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

import tasks.animation_generation_task as anim
from clients.wan_animate_client import (
    CERTIFIED_DEFAULTS,
    GRAPH_PATH,
    WanAnimateClient,
    WanAnimateInputError,
    WanAnimateParams,
    WanAnimateWorkflowError,
)
from models.task_result import PipelineStage
from tasks.animation_generation_task import (
    SceneAnimationResult,
    generate_scene_animations,
)
from tasks.video_generation_task import SceneVideoResult


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

class TestWiring:
    def test_stage_task_map_no_longer_names_the_image_task(self):
        from tasks.pipeline_orchestrator_v2 import STAGE_TASK_MAP

        target = STAGE_TASK_MAP[PipelineStage.ANIMATION_GENERATION.value]
        assert target == "tasks.animation_generation_task.generate_scene_animations"
        assert target != STAGE_TASK_MAP[PipelineStage.IMAGE_GENERATION.value]

    def test_animation_has_its_own_queue(self):
        from tasks.pipeline_orchestrator_v2 import STAGE_QUEUE_MAP

        assert STAGE_QUEUE_MAP[PipelineStage.ANIMATION_GENERATION.value] == "gpu_animation"
        assert STAGE_QUEUE_MAP[PipelineStage.IMAGE_GENERATION.value] == "gpu_image"

    def test_the_queue_exists_and_is_routed(self):
        from celery_app import TASK_QUEUES, TASK_ROUTES

        assert "gpu_animation" in {q.name for q in TASK_QUEUES}
        assert (
            TASK_ROUTES["tasks.animation_generation_task.*"]["queue"] == "gpu_animation"
        )

    def test_the_task_is_registered_under_its_own_name(self):
        assert (
            generate_scene_animations.name
            == "tasks.animation_generation_task.generate_scene_animations"
        )
        assert generate_scene_animations.queue == "gpu_animation"

    def test_dispatch_plan_sends_animation_to_the_animation_queue(self):
        """The plan loop's queue must agree with STAGE_QUEUE_MAP.

        They are written in two places (the map, and the tuple the dispatcher
        iterates); a scene routed by one and consumed by the other is a job
        that hangs with its assets already in SeaweedFS.
        """
        import inspect

        from tasks.pipeline_orchestrator_v2 import (
            STAGE_QUEUE_MAP,
            dispatch_media_generation,
        )

        src = inspect.getsource(dispatch_media_generation)
        expected = STAGE_QUEUE_MAP[PipelineStage.ANIMATION_GENERATION.value]
        assert (
            f'(PipelineStage.ANIMATION_GENERATION.value, "{expected}", animation_scenes)'
            in src
        )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestCertifiedProvenance:
    #: sha256 of mbcp_adapters/comfyui_graphs/wan_animate.json at the commit
    #: this package read it from (/opt/MBCP @ ea7f91e).
    MBCP_GRAPH_SHA256 = (
        "84a00a2549c3802cdb9f2365430ebc0136cccb226c1c67eed491b0bac70b2525"
    )

    def test_graph_is_mbcps_certified_graph_byte_for_byte(self):
        """The render IVGS performs must be the render MBCP certified.

        A graph edited on this side — even a "harmless" one — invalidates the
        certificate's measured VRAM, its timing and its human-eval Elo, because
        none of those were measured against the edited graph.
        """
        digest = hashlib.sha256(GRAPH_PATH.read_bytes()).hexdigest()
        assert digest == self.MBCP_GRAPH_SHA256

    def test_defaults_are_mbcps_certified_family_spec(self):
        """Transcribed from MBCP migration 0053, family ``wan_animate``."""
        assert CERTIFIED_DEFAULTS["served_model_name"] == (
            "Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors"
        )
        assert CERTIFIED_DEFAULTS["steps"] == 6
        assert CERTIFIED_DEFAULTS["cfg"] == 1.0
        assert CERTIFIED_DEFAULTS["shift"] == 5.0
        assert CERTIFIED_DEFAULTS["scheduler"] == "dpm++_sde"
        assert CERTIFIED_DEFAULTS["output_width"] == 768
        assert CERTIFIED_DEFAULTS["output_height"] == 1408
        assert CERTIFIED_DEFAULTS["num_frames"] == 77
        assert CERTIFIED_DEFAULTS["frame_window_size"] == 77
        assert CERTIFIED_DEFAULTS["output_fps"] == 30

    def test_reservation_ask_is_mbcps_measured_peak(self):
        """44.392578125 GB, certificate eb032794 / result 661c5cd1."""
        assert anim.CERTIFIED_VRAM_MB == 45458

    def test_engine_key_and_env_var_are_the_documented_pair(self):
        """MBCP's engine for this family is ``comfyui``, so the env var is
        ``IVGS_COMFYUI_URL``. Stated here because getting this pair wrong is
        how the row was registered against ``animatediff`` in the first place.
        """
        from shared.providers.binding import _ENGINE_ENDPOINTS

        env_var, _default = _ENGINE_ENDPOINTS["comfyui"]
        assert env_var == "IVGS_COMFYUI_URL"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

class TestWorkflowBuild:
    def _client(self, **kw):
        return WanAnimateClient(base_url="http://stub:8188", **kw)

    def test_every_slot_is_filled_by_the_certified_defaults(self):
        from clients.wan_animate_client import _unresolved_slots

        graph = self._client().build_workflow(
            WanAnimateParams(), ref_image_file="r.png", driving_video_file="d.mp4"
        )
        assert _unresolved_slots(graph) == set()

    def test_numeric_slots_are_real_numbers_not_strings(self):
        """ComfyUI's INT/FLOAT sockets reject quoted numbers outright."""
        graph = self._client().build_workflow(
            WanAnimateParams(seed=7, steps=6, num_frames=77),
            ref_image_file="r.png",
            driving_video_file="d.mp4",
        )
        sampler = graph["15"]["inputs"]
        assert isinstance(sampler["seed"], int) and sampler["seed"] == 7
        assert isinstance(sampler["steps"], int)
        assert isinstance(sampler["cfg"], float)
        assert isinstance(graph["12"]["inputs"]["num_frames"], int)
        assert isinstance(graph["12"]["inputs"]["pose_strength"], float)

    def test_the_two_bytes_inputs_land_in_their_loader_nodes(self):
        graph = self._client().build_workflow(
            WanAnimateParams(),
            ref_image_file="ivgs_ref.png",
            driving_video_file="ivgs_drive.mp4",
        )
        assert graph["5"]["class_type"] == "LoadImage"
        assert graph["5"]["inputs"]["image"] == "ivgs_ref.png"
        assert graph["7"]["class_type"] == "VHS_LoadVideo"
        assert graph["7"]["inputs"]["video"] == "ivgs_drive.mp4"

    def test_store_default_params_override_the_certified_defaults(self):
        """ARCH-1: a model's parameters are data, not code."""
        client = self._client(default_params={"output_width": 1024, "steps": 8})
        graph = client.build_workflow(
            WanAnimateParams(output_width=1024, steps=8),
            ref_image_file="r.png",
            driving_video_file="d.mp4",
        )
        assert graph["12"]["inputs"]["width"] == 1024
        assert graph["15"]["inputs"]["steps"] == 8

    def test_engine_model_bridges_the_store_name_to_the_checkpoint(self):
        """``binding.name`` is "Wan2.2-Animate"; the engine wants a filename."""
        client = self._client(model="Wan22Animate/Some-Other.safetensors")
        graph = client.build_workflow(
            WanAnimateParams(), ref_image_file="r.png", driving_video_file="d.mp4"
        )
        assert graph["1"]["inputs"]["model"] == "Wan22Animate/Some-Other.safetensors"

    def test_the_terminal_node_is_cache_busted(self):
        """Certified params pin the seed, so an identical graph would cache-hit
        VHS_VideoCombine and the run would 'succeed' having saved nothing."""
        client = self._client()
        a = client.build_workflow(
            WanAnimateParams(), ref_image_file="r.png", driving_video_file="d.mp4"
        )
        b = client.build_workflow(
            WanAnimateParams(), ref_image_file="r.png", driving_video_file="d.mp4"
        )
        assert (
            a["17"]["inputs"]["filename_prefix"]
            != b["17"]["inputs"]["filename_prefix"]
        )
        # ...and the seed is untouched, so the frames stay reproducible.
        assert a["15"]["inputs"]["seed"] == b["15"]["inputs"]["seed"]

    def test_an_unfilled_slot_is_named_rather_than_POSTed(self, monkeypatch):
        client = self._client()
        client._graph_template = {
            "1": {"class_type": "X", "inputs": {"thing": "{no_such_slot}"}}
        }
        with pytest.raises(WanAnimateWorkflowError) as exc:
            client.build_workflow(
                WanAnimateParams(), ref_image_file="r.png", driving_video_file="d.mp4"
            )
        assert "no_such_slot" in str(exc.value)


# ---------------------------------------------------------------------------
# Refusal, not substitution
# ---------------------------------------------------------------------------

class TestRefusesRatherThanSubstituting:
    @pytest.mark.parametrize("missing", ["reference_image", "driving_video"])
    def test_a_missing_input_is_refused_by_name(self, missing):
        import asyncio

        client = WanAnimateClient(base_url="http://stub:8188")
        kwargs = {"reference_image": b"png", "driving_video": b"mp4"}
        kwargs[missing] = b""
        with pytest.raises(WanAnimateInputError) as exc:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                client.generate_animation(**kwargs)
            )
        assert missing in str(exc.value)
        assert "pose-reenactment" in str(exc.value)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

class TestSceneResultShape:
    def test_animation_scene_results_match_video_scene_results_field_for_field(self):
        """The media join and the manifest builder read all three branches with
        one shape. An animation result that carried an extra field, or lacked
        one, would be a per-branch special case downstream."""
        assert set(SceneAnimationResult.model_fields) == set(
            SceneVideoResult.model_fields
        )

    def test_defaults_match_too(self):
        for name, field in SceneVideoResult.model_fields.items():
            mine = SceneAnimationResult.model_fields[name]
            assert mine.annotation == field.annotation, name


# ---------------------------------------------------------------------------
# Checkpoints — WP-39 (c), carried into the new task
# ---------------------------------------------------------------------------

@pytest.fixture()
def stubbed(monkeypatch):
    """Stub every boundary the task crosses; keep its control flow."""
    calls = {}

    cfg = MagicMock()
    cfg.enable_checkpoint_saving = True
    monkeypatch.setattr(anim, "WorkerConfig", lambda *a, **k: cfg)

    monkeypatch.setattr(
        anim,
        "acquire_gpu_reservation",
        MagicMock(side_effect=RuntimeError("registry empty")),
    )
    released = MagicMock()
    monkeypatch.setattr(anim, "release_acquired_reservation", released)
    calls["release"] = released
    monkeypatch.setattr(anim, "update_job_status", MagicMock())

    saved = MagicMock(return_value=True)
    monkeypatch.setattr(anim, "save_checkpoint", saved)
    calls["save_checkpoint"] = saved

    sent = MagicMock(return_value=MagicMock(id="fake"))
    monkeypatch.setattr(anim.celery_app, "send_task", sent)
    calls["send_task"] = sent

    # The engine: reachable, Wan-capable, and never actually called because
    # _process_single_animation is stubbed below.
    client = MagicMock()

    async def _nodes():
        return set(anim.REQUIRED_NODE_TYPES)

    async def _close():
        return None

    client.available_node_types = _nodes
    client.close = _close
    monkeypatch.setattr(anim, "WanAnimateClient", lambda *a, **k: client)
    calls["client"] = client
    return calls


def _stub_scene_results(monkeypatch, statuses):
    seq = iter(statuses)

    async def _fake(scene, **kwargs):
        return SceneAnimationResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            status=next(seq),
            generation_time_seconds=1.0,
        )

    monkeypatch.setattr(anim, "_process_single_animation", _fake)


def _task_input(**over):
    base = {
        "job_id": "job-wp46",
        "project_id": "proj-wp46",
        "scenes": [
            {"scene_id": "s1", "scene_index": 0, "visual_description": "a hand"},
            {"scene_id": "s2", "scene_index": 1, "visual_description": "a board"},
        ],
        # Task 4's path: the store row is still a CANDIDATE, so get_binding
        # cannot resolve — the harness names the engine instead.
        "engine_endpoint_override": "http://stub:8188",
    }
    base.update(over)
    return base


class TestCheckpoints:
    def test_every_checkpoint_is_keyed_on_join_stage(self, stubbed, monkeypatch):
        """The hardcoded stage name is the exact defect that let a 12-scene
        animation run overwrite the 4-scene image run's row (job bd99fe37)."""
        _stub_scene_results(monkeypatch, ["success", "success"])
        generate_scene_animations(_task_input())

        names = {
            c.kwargs["stage_name"] for c in stubbed["save_checkpoint"].call_args_list
        }
        assert names == {PipelineStage.ANIMATION_GENERATION.value}
        assert PipelineStage.IMAGE_GENERATION.value not in names

    def test_an_explicit_join_stage_is_honoured_over_the_default(
        self, stubbed, monkeypatch
    ):
        _stub_scene_results(monkeypatch, ["success", "success"])
        generate_scene_animations(_task_input(join_stage="animation_generation"))
        for call in stubbed["save_checkpoint"].call_args_list:
            assert call.kwargs["stage_name"] == "animation_generation"

    def test_the_terminal_checkpoint_is_written(self, stubbed, monkeypatch):
        """WP-39 (c). Without it the row stops at the last per-scene write —
        status "running" / checkpoint_status 'pending' — and the database
        cannot tell "rendering" from "done"."""
        _stub_scene_results(monkeypatch, ["success", "success"])
        generate_scene_animations(_task_input())

        statuses = [
            c.kwargs["status"] for c in stubbed["save_checkpoint"].call_args_list
        ]
        assert statuses[-1] == "success"
        assert statuses[:-1] == ["running", "running"]

    def test_a_partial_run_lands_terminal_too(self, stubbed, monkeypatch):
        _stub_scene_results(monkeypatch, ["success", "failed"])
        out = generate_scene_animations(_task_input())
        assert out["status"] == "partial_success"
        assert stubbed["save_checkpoint"].call_args_list[-1].kwargs["status"] == (
            "partial_success"
        )

    def test_the_completion_reports_under_the_animation_label(
        self, stubbed, monkeypatch
    ):
        """WP-39: the media join counts one report per dispatched STAGE."""
        _stub_scene_results(monkeypatch, ["success", "success"])
        out = generate_scene_animations(_task_input())
        assert out["stage"] == PipelineStage.ANIMATION_GENERATION.value

        sent = stubbed["send_task"].call_args
        assert sent.args[0] == "tasks.pipeline_orchestrator_v2.handle_stage_completion"
        assert (
            sent.kwargs["kwargs"]["stage_output_dict"]["stage"]
            == PipelineStage.ANIMATION_GENERATION.value
        )

    def test_binding_source_is_recorded_so_an_override_cannot_pass_as_bound(
        self, stubbed, monkeypatch
    ):
        _stub_scene_results(monkeypatch, ["success", "success"])
        generate_scene_animations(_task_input())
        terminal = stubbed["save_checkpoint"].call_args_list[-1]
        assert terminal.kwargs["checkpoint_data"]["binding_source"] == (
            "explicit-override"
        )


class TestEngineCapabilityGate:
    def test_reaching_the_image_comfyui_fails_loudly_naming_the_variable(
        self, stubbed, monkeypatch
    ):
        """Both instances answer to ``comfyui`` and to ``IVGS_COMFYUI_URL``.
        Only one can run this graph, and the other must not be discovered a
        scene at a time.

        The batch fails, but it fails *reporting*: raising here would retry a
        deterministic wrong answer and then strand the media join.
        """
        _stub_scene_results(monkeypatch, ["success", "success"])

        async def _stock_comfyui():
            return {"KSampler", "CheckpointLoaderSimple", "WanImageToVideo"}

        stubbed["client"].available_node_types = _stock_comfyui

        out = generate_scene_animations(_task_input())

        assert out["status"] == "failed"
        assert out["total_scenes"] == 2
        assert out["failed_count"] == 2
        errors = " ".join(e for r in out["scene_results"] for e in r["errors"])
        assert "IVGS_COMFYUI_URL" in errors
        assert "WanVideoModelLoader" in errors

        # The join still closes, and the row still lands terminal.
        assert stubbed["send_task"].called
        assert stubbed["save_checkpoint"].call_args_list[-1].kwargs["status"] == "failed"
