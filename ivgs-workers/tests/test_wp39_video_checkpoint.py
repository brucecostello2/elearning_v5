"""
WP-39 ledger (c) — the video stage never recorded that it finished

Both clips of job bd99fe37 rendered and uploaded, and `pipeline_checkpoints`
still read:

    video_generation   3   pending   2026-08-23 16:47:01Z

The task wrote a checkpoint after every scene with status="running", which the
API maps to the 'pending' enum label, and then wrote nothing at the end. Stage 3
writes a terminal checkpoint at exactly that point (stage3_images.py); the video
stage did not, so the database could not distinguish "still rendering" from
"finished" for the whole of the stage's life and the operator triaging the
stalled job read a completed stage as in-flight.

This drives the real task body with every I/O boundary stubbed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import tasks.video_generation_task as vid
from tasks.video_generation_task import SceneVideoResult, generate_video_clips


@pytest.fixture()
def stubbed(monkeypatch):
    """Stub every boundary the task crosses, keep its control flow."""
    calls = {}

    cfg = MagicMock()
    cfg.enable_checkpoint_saving = True
    cfg.get_vllm_config_for_stage.return_value = MagicMock(base_url="http://stub")
    monkeypatch.setattr(vid, "WorkerConfig", lambda *a, **k: cfg)

    monkeypatch.setattr(vid, "VLLMClient", MagicMock())
    monkeypatch.setattr(
        vid, "acquire_gpu_reservation", MagicMock(side_effect=RuntimeError("no registry")),
    )
    monkeypatch.setattr(vid, "release_acquired_reservation", MagicMock())
    monkeypatch.setattr(vid, "update_job_status", MagicMock())

    saved = MagicMock(return_value=True)
    monkeypatch.setattr(vid, "save_checkpoint", saved)
    calls["save_checkpoint"] = saved

    sent = MagicMock(return_value=MagicMock(id="fake"))
    monkeypatch.setattr(vid.celery_app, "send_task", sent)
    calls["send_task"] = sent

    calls["config"] = cfg
    return calls


def _stub_scene_results(monkeypatch, statuses):
    seq = iter(statuses)

    async def _fake(scene, **kwargs):
        return SceneVideoResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            status=next(seq),
            generation_time_seconds=1.0,
        )

    monkeypatch.setattr(vid, "_process_single_video", _fake)


def _task_input(**over):
    base = {
        "job_id": "job-wp39",
        "project_id": "proj-wp39",
        "scenes": [
            {
                "scene_id": "s1",
                "scene_index": 0,
                "visual_description": "a street",
                "duration_seconds": 5.0,
            },
            {
                "scene_id": "s2",
                "scene_index": 1,
                "visual_description": "a laptop",
                "duration_seconds": 5.0,
            },
        ],
    }
    base.update(over)
    return base


def _terminal(saved):
    """Checkpoint writes that are not the per-scene status='running' ones."""
    return [c for c in saved.call_args_list if c.kwargs["status"] != "running"]


class TestTerminalCheckpoint:

    def test_both_clips_succeeding_writes_a_success_checkpoint(
        self, stubbed, monkeypatch,
    ):
        _stub_scene_results(monkeypatch, ["success", "success"])

        out = generate_video_clips.run(_task_input())

        assert out["status"] == "success"
        saved = stubbed["save_checkpoint"]

        # The pre-fix behaviour: two per-scene writes, both 'running', nothing else.
        running = [c for c in saved.call_args_list if c.kwargs["status"] == "running"]
        assert len(running) == 2

        terminal = _terminal(saved)
        assert len(terminal) == 1, "the stage must record that it finished"
        assert terminal[0].kwargs["status"] == "success"
        assert terminal[0].kwargs["stage_name"] == "video_generation"
        assert terminal[0].kwargs["stage_index"] == 3
        assert terminal[0].kwargs["checkpoint_data"]["successful_count"] == 2
        assert terminal[0].kwargs["checkpoint_data"]["failed_count"] == 0

    def test_a_failed_clip_is_recorded_as_partial_success(self, stubbed, monkeypatch):
        _stub_scene_results(monkeypatch, ["success", "failed"])

        out = generate_video_clips.run(_task_input())

        assert out["status"] == "partial_success"
        terminal = _terminal(stubbed["save_checkpoint"])
        assert [c.kwargs["status"] for c in terminal] == ["partial_success"]

    def test_the_checkpoint_precedes_the_completion_report(self, stubbed, monkeypatch):
        """Order matters: the join advances on the report, so the durable record
        of this stage must already exist when it fires."""
        order = []
        stubbed["save_checkpoint"].side_effect = lambda **kw: order.append(
            ("checkpoint", kw["status"])
        ) or True
        stubbed["send_task"].side_effect = lambda *a, **kw: order.append(
            ("send_task", a[0])
        ) or MagicMock(id="fake")

        _stub_scene_results(monkeypatch, ["success", "success"])
        generate_video_clips.run(_task_input())

        assert order[-2] == ("checkpoint", "success")
        assert order[-1] == (
            "send_task", "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        )

    def test_disabled_checkpointing_is_still_honoured(self, stubbed, monkeypatch):
        stubbed["config"].enable_checkpoint_saving = False
        _stub_scene_results(monkeypatch, ["success", "success"])

        generate_video_clips.run(_task_input())

        assert _terminal(stubbed["save_checkpoint"]) == []


class TestJoinStageOnTheOutput:

    def test_default_is_the_video_stage(self, stubbed, monkeypatch):
        _stub_scene_results(monkeypatch, ["success", "success"])
        out = generate_video_clips.run(_task_input())
        assert out["stage"] == "video_generation"

    def test_the_dispatched_label_is_echoed_back(self, stubbed, monkeypatch):
        _stub_scene_results(monkeypatch, ["success", "success"])
        out = generate_video_clips.run(_task_input(join_stage="video_generation"))
        assert out["stage"] == "video_generation"
