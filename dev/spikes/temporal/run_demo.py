"""
WP-31 Lane C spike — driver. Start runs, send signals, read state.

THIS IS THROWAWAY EVIDENCE, NOT FOUNDATION. See README.md.

  python3 run_demo.py start   <workflow_id> [--scenes 6] [--fail]
  python3 run_demo.py signal  <workflow_id> <storyboard_approved|draft_approved>
  python3 run_demo.py state   <workflow_id>
  python3 run_demo.py result  <workflow_id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from temporalio.client import Client

from shared_types import PipelineInput
from workflow import VideoPipelineShadowWorkflow

TARGET = os.environ.get("TEMPORAL_TARGET", "127.0.0.1:7233")
TASK_QUEUE = os.environ.get("SPIKE_TASK_QUEUE", "ivgs-shadow-spike")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["start", "signal", "state", "result"])
    ap.add_argument("workflow_id")
    ap.add_argument("signal_name", nargs="?", default="")
    ap.add_argument("--scenes", type=int, default=6)
    ap.add_argument("--fail", action="store_true",
                    help="append the deliberately failing activity")
    args = ap.parse_args()

    client = await Client.connect(TARGET)

    if args.command == "start":
        handle = await client.start_workflow(
            VideoPipelineShadowWorkflow.run,
            PipelineInput(
                job_id=args.workflow_id,
                scene_count=args.scenes,
                include_failing_activity=args.fail,
                failing_activity_fails=99,
            ),
            id=args.workflow_id,
            task_queue=TASK_QUEUE,
        )
        print(f"started {handle.id} run_id={handle.result_run_id}")
        return

    handle = client.get_workflow_handle(args.workflow_id)

    if args.command == "signal":
        await handle.signal(args.signal_name)
        print(f"signalled {args.signal_name} -> {args.workflow_id}")
    elif args.command == "state":
        # Query THROUGH the workflow method, not by name string: without the
        # method reference the SDK has no result type and hands back a raw
        # dict, which then has no __dict__. Cost an entire demo run to find.
        state = await handle.query(VideoPipelineShadowWorkflow.state)
        payload = state if isinstance(state, dict) else state.__dict__
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(await handle.result(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
