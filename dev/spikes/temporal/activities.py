"""
WP-31 Lane C spike — stub activities. Sleep and log. ZERO IVGS imports.

Every activity body appends to an execution ledger (JSONL) BEFORE and AFTER it
does its work. That ledger is the resume evidence: if Temporal re-executed an
activity that had already completed, the ledger would carry a second `start`
line for the same key. It does not. The ledger is written by the activity, in
the worker process, so it survives the worker being killed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError

from shared_types import (
    FlakyInput,
    SceneInput,
    SceneResult,
    StageInput,
    StageResult,
)

LEDGER = Path(os.environ.get("SPIKE_LEDGER", "/tmp/ivgs-temporal-spike/ledger.jsonl"))


def _record(event: str, key: str, attempt: int) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": round(time.time(), 3),
            "event": event,
            "key": key,
            "attempt": attempt,
            "pid": os.getpid(),
        }
    )
    # Append-and-flush: the worker is about to be SIGKILLed on purpose.
    with LEDGER.open("a") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


async def _sleep_with_heartbeat(total_s: float) -> None:
    """
    AD-05 section 9 makes heartbeating a requirement on the activity wrapper,
    not an option. Stub activities heartbeat on the same cadence so the
    heartbeat_timeout in the workflow is actually exercised.
    """
    waited = 0.0
    while waited < total_s:
        step = min(2.0, total_s - waited)
        await asyncio.sleep(step)
        waited += step
        activity.heartbeat(f"{waited:.1f}/{total_s:.1f}s")


@activity.defn
async def run_stage(inp: StageInput) -> StageResult:
    attempt = activity.info().attempt
    _record("start", inp.node_id, attempt)
    activity.logger.info("stub stage start: %s (%s)", inp.node_id, inp.queue)
    await _sleep_with_heartbeat(inp.duration_s)
    _record("complete", inp.node_id, attempt)
    return StageResult(
        node_id=inp.node_id,
        artifact=f"stub://{inp.job_id}/{inp.node_id}",
        ran_on_pid=os.getpid(),
        attempt=attempt,
    )


@activity.defn
async def render_scene(inp: SceneInput) -> SceneResult:
    key = f"scene-{inp.scene_index}"
    attempt = activity.info().attempt
    _record("start", key, attempt)
    activity.logger.info("stub scene start: %s", key)
    await _sleep_with_heartbeat(inp.duration_s)
    _record("complete", key, attempt)
    return SceneResult(
        scene_index=inp.scene_index,
        artifact=f"stub://{inp.job_id}/{key}",
        ran_on_pid=os.getpid(),
        attempt=attempt,
    )


@activity.defn
async def flaky_stage(inp: FlakyInput) -> str:
    """
    Demonstration 3. Fails on purpose. The retry policy in the workflow bounds
    the attempts; the final failure must surface in workflow state rather than
    being swallowed -- the failure mode the IVGS swallowed-failures register
    exists to track.
    """
    attempt = activity.info().attempt
    _record("start", "flaky", attempt)
    await asyncio.sleep(0.5)
    if attempt <= inp.fail_times:
        _record("failed", "flaky", attempt)
        raise ApplicationError(
            f"deliberate stub failure on attempt {attempt}",
            type="StubTransientError",
        )
    _record("complete", "flaky", attempt)
    return f"recovered on attempt {attempt}"
