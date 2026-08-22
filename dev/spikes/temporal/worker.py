"""
WP-31 Lane C spike — the worker process. Kill this one; that is the point.

THIS IS THROWAWAY EVIDENCE, NOT FOUNDATION. See README.md.

  python3 worker.py

Environment:
  TEMPORAL_TARGET   default 127.0.0.1:7233
  SPIKE_TASK_QUEUE  default ivgs-shadow-spike
  SPIKE_LEDGER      default /tmp/ivgs-temporal-spike/ledger.jsonl
"""

from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

import activities
from workflow import VideoPipelineShadowWorkflow

TARGET = os.environ.get("TEMPORAL_TARGET", "127.0.0.1:7233")
TASK_QUEUE = os.environ.get("SPIKE_TASK_QUEUE", "ivgs-shadow-spike")

# Two at a time, so the six-scene fan-out takes three waves and there is a
# real mid-fan-out moment to kill the worker in. AD-05 section 4.2 pins GPU
# queues to concurrency 1 for the same reason Celery uses prefetch 1; this is
# 2 purely to keep the demonstration short.
MAX_CONCURRENT_ACTIVITIES = 2


async def main() -> None:
    client = await Client.connect(TARGET)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[VideoPipelineShadowWorkflow],
        activities=[
            activities.run_stage,
            activities.render_scene,
            activities.flaky_stage,
        ],
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )
    print(f"worker pid={os.getpid()} queue={TASK_QUEUE} target={TARGET}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
