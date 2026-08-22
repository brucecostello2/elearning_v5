"""
WP-31 Lane B step 4 — hello-world smoke test against the node-07 cluster.

Separate from the Lane C shadow workflow on purpose: this proves the cluster
and the Python SDK talk to each other at all, before any pipeline modelling
is layered on top. Run it with its own inline worker:

  python3 smoke_hello.py <workflow_id>

Then verify from the CLI, not from this script's stdout:

  docker exec temporal-admin-tools temporal workflow show \
      --address temporal:7233 --workflow-id <workflow_id>
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

TARGET = os.environ.get("TEMPORAL_TARGET", "127.0.0.1:7233")
TASK_QUEUE = "ivgs-smoke"


@activity.defn
async def say_hello(name: str) -> str:
    return f"Hello, {name}! -- from Temporal on node-07"


@workflow.defn
class HelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            say_hello, name, start_to_close_timeout=timedelta(seconds=30)
        )


async def main() -> None:
    wf_id = sys.argv[1] if len(sys.argv) > 1 else "ivgs-smoke-hello"
    client = await Client.connect(TARGET)
    async with Worker(
        client, task_queue=TASK_QUEUE,
        workflows=[HelloWorkflow], activities=[say_hello],
    ):
        result = await client.execute_workflow(
            HelloWorkflow.run, "IVGS", id=wf_id, task_queue=TASK_QUEUE,
        )
    print(f"workflow_id={wf_id}")
    print(f"client_result={result}")


if __name__ == "__main__":
    asyncio.run(main())
