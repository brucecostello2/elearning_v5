"""
WP-41 Task 3 (second half) -- one activity delivered twice, one effect.

The SIGKILL demonstration in ``demo_resume.sh`` shows this happening for real,
but it depends on the kill landing inside the ack window, so it cannot be the
only proof. This script forces the same delivery deterministically: it calls
one activity body twice with the SAME ``ActivityContext`` -- which is exactly
what a worker sees when the server redelivers an activity whose completion it
never heard -- and reads the two independent counts back out.

No cluster needed; it runs the activity bodies directly.

    IVGS_TEMPORAL_SHADOW_STATE=/tmp/ivgs-temporal-shadow \\
      PYTHONPATH=/opt/ivgs/ivgs-workers \\
      /home/dev/.venv-ivgs-temporal/bin/python -m \\
      temporal_pipeline.demos.demo_duplicate_delivery
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys

from temporal_pipeline import activities
from temporal_pipeline.dag import build_pipeline_dag
from temporal_pipeline.idempotency import IdempotencyKey
from temporal_pipeline.payloads import ActivityContext, RenderSceneImageInput
from temporal_pipeline.reference_storyboard import reference_storyboard

JOB_ID = "wp41-duplicate-delivery-demo"


def context_for(label: str, scene_index: int, attempt: int) -> ActivityContext:
    """
    Identical on both deliveries except for the attempt number.

    The key is built from the DagNode's stage token, never from anything the
    activity decides for itself -- the WP-39 rule.
    """
    node = next(
        n for n in build_pipeline_dag(reference_storyboard()) if n.label == label
    )
    key = IdempotencyKey(
        job_id=JOB_ID, stage=node.idempotency_stage, scene_index=scene_index
    )
    return ActivityContext(
        job_id=JOB_ID,
        project_id="c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
        label=label,
        idempotency_key=key.render(),
        queue=node.queue,
        scene_index=scene_index,
        attempt=attempt,
    )


async def deliver(label: str, scene_index: int, attempt: int):
    ctx = context_for(label, scene_index, attempt)
    scene = reference_storyboard()[scene_index]
    return await activities.render_scene_image(
        RenderSceneImageInput(
            ctx=ctx,
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            visual_description=scene.visual_description,
            media_type=scene.media_type,
            narration_text=scene.narration_text,
            # 0.0 so the demonstration is instant; the real body renders.
            duration_seconds=0.0,
        )
    )


async def main() -> int:
    shutil.rmtree(activities.job_root(JOB_ID), ignore_errors=True)
    store = activities.store_for(JOB_ID)

    # Scene 4 of the banked storyboard is an ANIMATION scene -- the branch
    # whose completion WP-39 lost. Delivered twice, as at-least-once allows.
    first = await deliver("animation_generation", 4, attempt=1)
    second = await deliver("animation_generation", 4, attempt=2)

    key = first.idempotency_key
    report = {
        "job_id": JOB_ID,
        "idempotency_key": key,
        "deliveries": store.delivery_count(key),
        "effects_total": store.effect_count(),
        "effect_keys": list(store.keys()),
        "first_delivery_artifact": first.asset_id,
        "second_delivery_artifact": second.asset_id,
        "artifacts_identical": first.asset_id == second.asset_id,
        "stage_label_on_both": [first.stage, second.stage],
        "attempt_recorded": [first.attempt, second.attempt],
    }
    print(json.dumps(report, indent=2))

    ok = (
        report["deliveries"] == 2
        and report["effects_total"] == 1
        and report["artifacts_identical"]
        and set(report["stage_label_on_both"]) == {"animation_generation"}
    )
    print()
    print(
        "PASS: two deliveries, one effect, identical artifact, "
        "labelled animation_generation on both."
        if ok
        else "FAIL: see the report above."
    )

    # A second scene, delivered once, so the numbers above cannot be trivially
    # true for a store that simply never writes anything.
    await deliver("image_generation", 17, attempt=1)
    print(
        f"control: one more scene delivered once -> effects_total="
        f"{store.effect_count()} (expected 2), keys={list(store.keys())}"
    )
    return 0 if ok and store.effect_count() == 2 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
