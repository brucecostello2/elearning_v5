"""
WP-31 Lane C — the resume evidence, read off the Temporal EVENT HISTORY.

Companion to analyze_ledger.py. The ledger says what the activity BODIES did;
this says what the SERVER durably recorded. The two together are the proof,
and the gap between them is itself worth showing to the review board:

  * An activity whose ActivityTaskCompleted is in the history is never
    scheduled again. That is the property AD-05 section 12 test 5 asks for.
  * An activity whose body finished but whose completion had not yet been
    reported when the worker was SIGKILLed IS re-executed. That is
    at-least-once activity execution, exactly as documented -- Temporal
    guarantees the WORKFLOW advances once, not that an activity body runs
    once. Activities must therefore be idempotent. This is the single most
    important operational consequence of the migration and AD-05 should
    say so explicitly.

  python3 resume_evidence.py <workflow_id>
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict

from temporalio.api.enums.v1 import EventType
from temporalio.client import Client

TARGET = os.environ.get("TEMPORAL_TARGET", "127.0.0.1:7233")


async def main() -> None:
    wf_id = sys.argv[1]
    client = await Client.connect(TARGET)
    handle = client.get_workflow_handle(wf_id)

    scheduled = {}          # scheduled_event_id -> activity type
    started = defaultdict(int)
    completed = defaultdict(int)
    signals = []
    counts = defaultdict(int)

    async for ev in handle.fetch_history_events():
        # ev.event_type is a protobuf enum, which arrives as a plain int in
        # this SDK build -- `.name` does not exist on it. Map it explicitly.
        tname = EventType.Name(ev.event_type)
        counts[tname] += 1

        if tname.endswith("ACTIVITY_TASK_SCHEDULED"):
            a = ev.activity_task_scheduled_event_attributes
            scheduled[ev.event_id] = a.activity_type.name
        elif tname.endswith("ACTIVITY_TASK_STARTED"):
            a = ev.activity_task_started_event_attributes
            started[a.scheduled_event_id] += 1
        elif tname.endswith("ACTIVITY_TASK_COMPLETED"):
            a = ev.activity_task_completed_event_attributes
            completed[a.scheduled_event_id] += 1
        elif tname.endswith("WORKFLOW_EXECUTION_SIGNALED"):
            signals.append(ev.workflow_execution_signaled_event_attributes.signal_name)

    print(f"workflow_id: {wf_id}")
    print()
    print("event-type histogram:")
    for k in sorted(counts):
        print(f"  {counts[k]:>4}  {k}")
    print()
    print(f"signals received: {signals}")
    print()
    print(f"{'sched_evt':>9}  {'activity':<28} {'starts':>6} {'completes':>9}")
    print("-" * 60)
    multi = 0
    for sid in sorted(scheduled):
        s, c = started.get(sid, 0), completed.get(sid, 0)
        if s > 1:
            multi += 1
        print(f"{sid:>9}  {scheduled[sid]:<28} {s:>6} {c:>9}")

    print()
    print(f"activity SCHEDULES total          : {len(scheduled)}")
    print(f"schedules with >1 start (retried) : {multi}")
    print(f"schedules completed exactly once  : "
          f"{sum(1 for v in completed.values() if v == 1)}")
    print(f"schedules completed more than once: "
          f"{sum(1 for v in completed.values() if v > 1)}")
    print()
    bad = sum(1 for v in completed.values() if v > 1)
    print("PASS - no activity was completed twice in the durable history"
          if bad == 0 else f"FAIL - {bad} activities completed more than once")


if __name__ == "__main__":
    asyncio.run(main())
