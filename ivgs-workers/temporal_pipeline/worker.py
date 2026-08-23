"""
The dev worker for the node-07 shadow cluster (WP-41 Task 2).

Runs on node-01, connects to ``192.168.1.96:7233``, and serves **one worker per
AD-05 §4.2 task queue** inside a single process:

    default, gpu_llm, gpu_image, gpu_video, gpu_tts, gpu_talking_head, composition

Seven queues in one process rather than seven processes, for one reason: the
resume demonstration needs a single pid to ``SIGKILL``. The queue names are
AD-05's own, unprefixed — the node-07 cluster has no other workers on it, and
a mangled name would make the evidence harder to read against §4.2.

GPU-queue concurrency
---------------------

AD-05 §4.2 pins GPU queues to ``max_concurrent_activities=1``, preserving
today's ``worker_prefetch_multiplier = 1``. The default here is 1, faithfully.
``--gpu-concurrency 2`` exists only so a fan-out demonstration finishes in
under a minute; WP-31's spike used 2 for the same reason and said so.

This process touches NO production path. It imports no Celery module, reaches
no engine, and writes only under ``IVGS_TEMPORAL_SHADOW_STATE``.

    python3 -m temporal_pipeline.worker --target 192.168.1.96:7233 --namespace dev
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from typing import List

from temporalio.client import Client
from temporalio.worker import Worker

from temporal_pipeline import activities
from temporal_pipeline.workflow import VideoPipelineWorkflow

DEFAULT_TARGET = os.environ.get("IVGS_TEMPORAL_TARGET", "192.168.1.96:7233")
DEFAULT_NAMESPACE = os.environ.get("IVGS_TEMPORAL_NAMESPACE", "dev")

# AD-05 §4.2, one queue per capability, mirroring spec Table 6-7's routing so
# node specialisation under AD-02 Draft 3 survives the migration.
QUEUES = (
    "default",
    "gpu_llm",
    "gpu_image",
    "gpu_video",
    "gpu_tts",
    "gpu_talking_head",
    "composition",
)
GPU_QUEUES = frozenset({"gpu_llm", "gpu_image", "gpu_video", "gpu_tts", "gpu_talking_head"})

# The workflow itself is scheduled on `default`, which is where a job is
# started from. Activities route themselves by policy.
WORKFLOW_QUEUE = "default"


def build_workers(client: Client, gpu_concurrency: int) -> List[Worker]:
    workers: List[Worker] = []
    for queue in QUEUES:
        concurrency = gpu_concurrency if queue in GPU_QUEUES else 8
        workers.append(
            Worker(
                client,
                task_queue=queue,
                workflows=[VideoPipelineWorkflow] if queue == WORKFLOW_QUEUE else [],
                activities=activities.ALL_ACTIVITIES,
                max_concurrent_activities=concurrency,
            )
        )
    return workers


async def main() -> int:
    ap = argparse.ArgumentParser(description="IVGS Temporal shadow dev worker")
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    ap.add_argument(
        "--gpu-concurrency",
        type=int,
        default=int(os.environ.get("IVGS_TEMPORAL_GPU_CONCURRENCY", "1")),
        help="AD-05 §4.2 says 1. Raise only to shorten a demonstration.",
    )
    ap.add_argument(
        "--fail-scenes",
        default="",
        help="job_id=0,3 -- make those scene indexes fail, to exercise "
             "AD-05 §12 test 4 partial-advance.",
    )
    args = ap.parse_args()

    if args.fail_scenes:
        job_id, _, indexes = args.fail_scenes.partition("=")
        activities.set_fail_scenes(
            job_id, [int(i) for i in indexes.split(",") if i.strip()]
        )

    client = await Client.connect(args.target, namespace=args.namespace)
    workers = build_workers(client, args.gpu_concurrency)

    print(
        f"shadow worker pid={os.getpid()} target={args.target} "
        f"namespace={args.namespace} queues={','.join(QUEUES)} "
        f"gpu_concurrency={args.gpu_concurrency}",
        flush=True,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    runner = asyncio.gather(*[w.run() for w in workers])
    waiter = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait(
        {runner, waiter}, return_when=asyncio.FIRST_COMPLETED
    )
    if waiter in done:
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
