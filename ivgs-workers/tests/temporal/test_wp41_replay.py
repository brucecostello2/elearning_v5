"""
WP-41 — the replay gate (AD-05 §7.2).

    "Every workflow-logic change ships behind workflow.patched() / worker
     versioning. Deploys never assume an empty workflow set. A replay test runs
     against captured histories in CI before any worker deploy. Adopt this on
     the first workflow written, not retrofitted."

This is that test, on the first workflow written. It replays a real captured
history against the CURRENT workflow code. If an edit changes the sequence of
commands the workflow issues -- a stage reordered, an activity added outside a
patch, a gate moved -- replay raises ``NondeterminismError`` here rather than
stranding a multi-day job parked at a human gate on the next deploy.

Multi-hour renders plus multi-day gates mean workflows will ALWAYS be in flight
during a deploy. That is why §7.2 calls this the most common way teams are hurt.

The histories in ``histories/`` were exported from the node-07 dev cluster with:

    python3 -m temporal_pipeline.client export <workflow_id> --out <file>.json

Needs the Temporal SDK, so it skips in the repo venv. A skip is not a pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip(
    "temporalio",
    reason="Temporal SDK is installed in /home/dev/.venv-ivgs-temporal, not the repo venv",
)

from temporalio.client import WorkflowHistory  # noqa: E402
from temporalio.worker import Replayer  # noqa: E402

from temporal_pipeline.workflow import VideoPipelineWorkflow  # noqa: E402

HISTORY_DIR = Path(__file__).parent / "histories"
HISTORIES = sorted(HISTORY_DIR.glob("*.json"))


def test_there_is_at_least_one_captured_history():
    """
    An empty history directory would make every test below vacuously pass --
    which is exactly the false-PASS shape WP-31 recorded when its evidence
    script counted zero activities and reported success.
    """
    assert HISTORIES, f"no captured histories in {HISTORY_DIR}"


@pytest.mark.parametrize("path", HISTORIES, ids=[p.stem for p in HISTORIES])
async def test_current_workflow_code_replays_the_captured_history(path):
    replayer = Replayer(workflows=[VideoPipelineWorkflow])
    history = WorkflowHistory.from_json(path.stem, path.read_text())
    await replayer.replay_workflow(history)


@pytest.mark.parametrize("path", HISTORIES, ids=[p.stem for p in HISTORIES])
def test_the_captured_history_is_a_complete_run_worth_replaying(path):
    """
    A history that stopped at the first gate would replay trivially and prove
    nothing about the fan-out, the join or the second gate.
    """
    events = json.loads(path.read_text())["events"]
    types = [e["eventType"] for e in events]

    assert types[-1] == "EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED"
    assert types.count("EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED") == 2, (
        "both human gates must have been released in the captured run"
    )

    scheduled = [
        e["activityTaskScheduledEventAttributes"]["activityType"]["name"]
        for e in events
        if e["eventType"] == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED"
    ]
    # All three media branches, as distinct activity types in the history --
    # readable without decoding a single payload.
    assert scheduled.count("render_scene_image") == 4
    assert scheduled.count("render_scene_video") == 2
    assert scheduled.count("render_scene_animation") == 12
    assert scheduled.count("render_final") == 1


# ---------------------------------------------------------------------------
# The replay gate, proven not to be vacuous
# ---------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402

from temporalio import workflow as _workflow  # noqa: E402
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner  # noqa: E402


@_workflow.defn(name="VideoPipelineWorkflow", sandboxed=False)
class DivergentPipelineWorkflow:
    """
    A workflow registered under the same name that issues a different first
    command: one extra activity, outside any patch, before anything else.

    This is what an ordinary careless edit looks like -- "just add a
    validation step at the top" -- and it is why §7.2 exists. A worker
    deployed with this change, against a job parked at a human gate, would
    fail the job on its next workflow task.
    """

    @_workflow.run
    async def run(self, inp) -> dict:
        await _workflow.execute_activity(
            "some_new_first_activity",
            task_queue="default",
            start_to_close_timeout=timedelta(seconds=60),
        )
        return {"status": "never reached"}

    @_workflow.query
    def state(self):
        return {}


async def test_a_divergent_workflow_fails_replay():
    """
    Without this, ``test_current_workflow_code_replays_the_captured_history``
    could be passing because the Replayer is lenient rather than because the
    code is unchanged.
    """
    from temporalio.workflow import NondeterminismError

    path = HISTORY_DIR / "wp41-shadow-final.json"
    replayer = Replayer(
        workflows=[DivergentPipelineWorkflow],
        workflow_runner=SandboxedWorkflowRunner(),
    )
    with pytest.raises(NondeterminismError):
        await replayer.replay_workflow(
            WorkflowHistory.from_json(path.stem, path.read_text())
        )
