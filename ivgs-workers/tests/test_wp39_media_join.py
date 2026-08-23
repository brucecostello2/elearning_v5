"""
WP-39-MEDIA-JOIN — the join that could not be closed

Job bd99fe37 (2026-08-23) rendered all 18 media assets and then stopped. The
storyboard had 4 image scenes, 12 animation scenes and 2 video_clip scenes, so
dispatch_media_generation armed the join at 3. What the log shows:

    16:45:27  image_generation      media_stage_completed          remaining 2
    16:46:55  image_generation      media_stage_duplicate_report_ignored
    16:49:43  video_generation      media_stage_completed          remaining 1

The middle line is the ANIMATION run finishing - 12 scenes on node-04 - not a
duplicate of anything. STAGE_TASK_MAP routes animation_generation to the same
Celery task as image_generation, and that task stamped its output with a
hardcoded "image_generation", so the join's (job_id, stage) idempotency guard
could not tell the two apart and dropped the second report. The counter stuck at
1 with every asset already in SeaweedFS.

`join_stage` travels with the dispatch and comes back on the completion, so two
runs of one task report under two labels.

These tests run against a REAL Redis, for the reason the WP-06 module gives:
the join is a server-side Lua script and a mock cannot prove it.

    docker run -d --rm --name wp39-redis -p 127.0.0.1:16380:6379 redis:7.4
    IVGS_TEST_REDIS_URL=redis://127.0.0.1:16380/0 \
        pytest ivgs-workers/tests/test_wp39_media_join.py
"""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import MagicMock

import pytest

import tasks.pipeline_orchestrator_v2 as orch
from tasks.pipeline_orchestrator_v2 import (
    JOIN_DECREMENTED,
    JOIN_DUPLICATE,
    MEDIA_JOIN_TTL_SECONDS,
    _decrement_media_task_count,
    _handle_media_generation_completion,
    _outstanding_media_stages,
    _store_job_context,
    _store_media_task_count,
    dispatch_media_generation,
    media_join_watchdog,
)

TEST_REDIS_URL = os.environ.get("IVGS_TEST_REDIS_URL", "redis://127.0.0.1:16380/0")

STAGE_IMAGE = "image_generation"
STAGE_VIDEO = "video_generation"
STAGE_ANIM = "animation_generation"


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
    """Nothing here may reach a real broker — see the WP-06 module's Incident."""
    sent = MagicMock()
    sent.return_value = MagicMock(id="fake-task-id")
    monkeypatch.setattr(orch.celery_app, "send_task", sent)
    return sent


@pytest.fixture()
def cfg():
    c = MagicMock()
    c.redis_url = TEST_REDIS_URL
    return c


@pytest.fixture(autouse=True)
def worker_config(monkeypatch, cfg):
    """dispatch_media_generation and the watchdog build their own WorkerConfig."""
    monkeypatch.setattr(orch, "WorkerConfig", lambda *a, **k: cfg)
    return cfg


@pytest.fixture(autouse=True)
def no_job_status(monkeypatch):
    monkeypatch.setattr(orch, "update_job_status", MagicMock())


@pytest.fixture()
def job_id():
    return f"wp39-{uuid.uuid4()}"


@pytest.fixture()
def r():
    import redis

    return redis.Redis.from_url(TEST_REDIS_URL)


def _scene(idx: int, media_type: str) -> dict:
    return {
        "scene_id": f"scene-{idx}",
        "scene_index": idx,
        "visual_description": "a thing",
        "narration_text": "words",
        "duration_seconds": 5.0,
        "media_type": media_type,
    }


# The real storyboard for project c12fa967: 4 image, 12 animation, 2 video_clip.
BD99FE37_SCENES = (
    [_scene(i, "image") for i in range(4)]
    + [_scene(100 + i, "animation") for i in range(12)]
    + [_scene(200 + i, "video_clip") for i in range(2)]
)


class TestDispatchLabelsEveryStageDistinctly:
    """Each dispatched media task must be able to report as itself."""

    def test_three_stages_dispatch_with_three_distinct_join_stages(
        self, job_id, no_broker, r,
    ):
        result = dispatch_media_generation(
            {
                "job_id": job_id,
                "project_id": "proj-c12fa967",
                "project_name": "double digit multiplication",
                "scenes": BD99FE37_SCENES,
            }
        )

        assert result["total_tasks"] == 3
        assert no_broker.call_count == 3

        labels = [
            call.kwargs["kwargs"]["task_input_dict"]["join_stage"]
            for call in no_broker.call_args_list
        ]
        assert labels == [STAGE_IMAGE, STAGE_VIDEO, STAGE_ANIM]
        assert len(set(labels)) == 3, "two dispatches sharing a label re-opens WP-39"
        assert result["expected_stages"] == [STAGE_IMAGE, STAGE_VIDEO, STAGE_ANIM]

        # The animation dispatch carries the 12 animation scenes and rides the
        # image task — the exact pair that used to collide.
        by_label = {
            call.kwargs["kwargs"]["task_input_dict"]["join_stage"]: call
            for call in no_broker.call_args_list
        }
        anim = by_label[STAGE_ANIM]
        image = by_label[STAGE_IMAGE]
        assert anim.args[0] == image.args[0] == "tasks.stage3_images.generate_scene_images_task"
        assert len(anim.kwargs["kwargs"]["task_input_dict"]["scenes"]) == 12
        assert len(image.kwargs["kwargs"]["task_input_dict"]["scenes"]) == 4

        assert int(r.get(f"ivgs:media_tasks:{job_id}")) == 3

    def test_join_context_records_what_was_dispatched(self, job_id, r):
        dispatch_media_generation(
            {"job_id": job_id, "project_id": "p", "scenes": BD99FE37_SCENES}
        )
        ctx = json.loads(r.get(f"ivgs:media_join_ctx:{job_id}"))
        assert ctx["expected_stages"] == [STAGE_IMAGE, STAGE_VIDEO, STAGE_ANIM]

    def test_a_storyboard_with_no_animation_arms_only_two(self, job_id, r):
        scenes = [_scene(0, "image"), _scene(1, "video_clip")]
        result = dispatch_media_generation(
            {"job_id": job_id, "project_id": "p", "scenes": scenes}
        )
        assert result["expected_stages"] == [STAGE_IMAGE, STAGE_VIDEO]
        assert int(r.get(f"ivgs:media_tasks:{job_id}")) == 2

    def test_stage3_input_keeps_join_stage(self, job_id, no_broker):
        """Without the model field pydantic drops the key and nothing changes."""
        from tasks.stage3_images import Stage3Input

        dispatch_media_generation(
            {"job_id": job_id, "project_id": "p", "scenes": BD99FE37_SCENES}
        )
        anim_input = next(
            call.kwargs["kwargs"]["task_input_dict"]
            for call in no_broker.call_args_list
            if call.kwargs["kwargs"]["task_input_dict"]["join_stage"] == STAGE_ANIM
        )
        assert Stage3Input(**anim_input).join_stage == STAGE_ANIM

    def test_video_input_keeps_join_stage(self, job_id, no_broker):
        from tasks.video_generation_task import VideoGenerationInput

        dispatch_media_generation(
            {"job_id": job_id, "project_id": "p", "scenes": BD99FE37_SCENES}
        )
        vid_input = next(
            call.kwargs["kwargs"]["task_input_dict"]
            for call in no_broker.call_args_list
            if call.kwargs["kwargs"]["task_input_dict"]["join_stage"] == STAGE_VIDEO
        )
        assert VideoGenerationInput(**vid_input).join_stage == STAGE_VIDEO


class TestTheJoinNowCloses:

    def test_pre_fix_shape_strands_the_job(self, cfg, job_id):
        """Executable reproduction of bd99fe37, using the pre-fix labels.

        Three tasks were dispatched; two of them reported as image_generation.
        """
        _store_media_task_count(job_id, 3, cfg)

        assert _decrement_media_task_count(job_id, STAGE_IMAGE, cfg) == (
            JOIN_DECREMENTED, 2,
        )
        # the animation run, wearing the image run's label
        assert _decrement_media_task_count(job_id, STAGE_IMAGE, cfg) == (
            JOIN_DUPLICATE, 0,
        )
        assert _decrement_media_task_count(job_id, STAGE_VIDEO, cfg) == (
            JOIN_DECREMENTED, 1,
        )
        # 1, forever. No fourth report exists.

    def test_three_distinct_labels_close_the_join(self, cfg, job_id):
        _store_media_task_count(job_id, 3, cfg)

        assert _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)[1] == 2
        assert _decrement_media_task_count(job_id, STAGE_ANIM, cfg)[1] == 1
        outcome, remaining = _decrement_media_task_count(job_id, STAGE_VIDEO, cfg)
        assert (outcome, remaining) == (JOIN_DECREMENTED, 0)

    def test_the_last_report_dispatches_the_composition_manifest(
        self, cfg, job_id, no_broker,
    ):
        _store_job_context(job_id, {"job_id": job_id, "project_id": "p"}, cfg)
        _store_media_task_count(job_id, 3, cfg)
        log = MagicMock()

        for stage in (STAGE_IMAGE, STAGE_ANIM):
            out = _handle_media_generation_completion(
                completed_stage=stage,
                stage_output={"job_id": job_id, "status": "success"},
                config=cfg,
                log=log,
            )
            assert out["action"] == "waiting"

        out = _handle_media_generation_completion(
            completed_stage=STAGE_VIDEO,
            stage_output={"job_id": job_id, "status": "success"},
            config=cfg,
            log=log,
        )
        assert out["action"] == "dispatched"
        assert out["next_stage"] == "composition_manifest"
        assert out["failed_count"] == 0
        no_broker.assert_called_once()
        assert no_broker.call_args.args[0] == "tasks.stage4_manifest.build_composition_manifest"

    def test_a_genuine_redelivery_is_still_a_duplicate(self, cfg, job_id):
        """join_stage must not weaken the WP-06 idempotency guard."""
        _store_media_task_count(job_id, 3, cfg)
        assert _decrement_media_task_count(job_id, STAGE_ANIM, cfg)[0] == JOIN_DECREMENTED
        assert _decrement_media_task_count(job_id, STAGE_ANIM, cfg)[0] == JOIN_DUPLICATE


class TestOutstandingStagesAreNamed:

    def test_it_names_the_stage_that_never_reported(self, cfg, job_id):
        _store_media_task_count(job_id, 3, cfg)
        ctx = {"expected_stages": [STAGE_IMAGE, STAGE_VIDEO, STAGE_ANIM]}

        _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        _decrement_media_task_count(job_id, STAGE_VIDEO, cfg)

        assert _outstanding_media_stages(job_id, ctx, cfg) == [STAGE_ANIM]

    def test_every_stage_reporting_is_an_empty_list(self, cfg, job_id):
        _store_media_task_count(job_id, 2, cfg)
        ctx = {"expected_stages": [STAGE_IMAGE, STAGE_VIDEO]}
        _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)
        _decrement_media_task_count(job_id, STAGE_VIDEO, cfg)

        assert _outstanding_media_stages(job_id, ctx, cfg) == []

    def test_could_not_tell_is_none_not_an_empty_list(self, cfg, job_id):
        """The distinction this whole package is about: unknown != nothing."""
        assert _outstanding_media_stages(job_id, None, cfg) is None
        assert _outstanding_media_stages(job_id, {}, cfg) is None
        assert _outstanding_media_stages(job_id, {"expected_stages": []}, cfg) is None


class TestWatchdogIsAudible:
    """The recovery mechanism must say it ran. WP-39 swallow-register entry."""

    @pytest.fixture()
    def caught(self, monkeypatch):
        bound = MagicMock()
        logger = MagicMock()
        logger.bind.return_value = bound
        monkeypatch.setattr(orch, "logger", logger)
        return bound

    @staticmethod
    def _events(bound, level):
        return [c.args[0] for c in getattr(bound, level).call_args_list if c.args]

    def test_a_sweep_that_finds_nothing_still_logs(self, caught):
        out = media_join_watchdog()
        assert out["status"] == "ok"
        assert "media_join_watchdog_sweep" in self._events(caught, "info")

    def test_an_outstanding_join_is_named_every_sweep(self, cfg, job_id, caught):
        _store_media_task_count(job_id, 3, cfg)
        orch._store_media_join_context(
            job_id, {"job_id": job_id, "expected_stages": [STAGE_IMAGE, STAGE_ANIM]}, cfg,
        )
        _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)

        media_join_watchdog()

        named = [
            c for c in caught.info.call_args_list
            if c.args and c.args[0] == "media_join_watchdog_join_outstanding"
            and c.kwargs.get("job_id") == job_id
        ]
        assert named, "an outstanding join must be named on every sweep, not only at the deadline"
        assert named[0].kwargs["outstanding_stages"] == [STAGE_ANIM]
        assert named[0].kwargs["remaining_tasks"] == 2

    def test_it_advances_a_join_past_the_deadline(
        self, cfg, job_id, caught, no_broker, r, monkeypatch,
    ):
        monkeypatch.setenv("IVGS_MEDIA_JOIN_TIMEOUT_SECONDS", "7200")
        _store_job_context(job_id, {"job_id": job_id, "project_id": "p"}, cfg)
        _store_media_task_count(job_id, 2, cfg)
        orch._store_media_join_context(
            job_id, {"job_id": job_id, "expected_stages": [STAGE_IMAGE, STAGE_ANIM]}, cfg,
        )
        _decrement_media_task_count(job_id, STAGE_IMAGE, cfg)

        # Age the counter past the deadline, exactly as time would.
        r.expire(f"ivgs:media_tasks:{job_id}", MEDIA_JOIN_TTL_SECONDS - 7300)

        out = media_join_watchdog()

        assert out["advanced"] >= 1
        assert r.get(f"ivgs:media_tasks:{job_id}") is None
        dispatches = [
            c for c in no_broker.call_args_list
            if c.args and c.args[0] == "tasks.stage4_manifest.build_composition_manifest"
        ]
        assert len(dispatches) == 1
        assert dispatches[0].kwargs["kwargs"]["task_input_dict"]["job_id"] == job_id

        stranded = [
            c for c in caught.warning.call_args_list
            if c.args and c.args[0] == "media_join_watchdog_stranded_job"
            and c.kwargs.get("job_id") == job_id
        ]
        assert stranded, "a claimed join must be reported"
        assert stranded[0].kwargs["outstanding_stages"] == [STAGE_ANIM]
