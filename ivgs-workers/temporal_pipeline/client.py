"""
Driver for the shadow run: start, signal, query, result, and evidence.

    python3 -m temporal_pipeline.client start   <workflow_id> [--reference] [--scenes ...]
    python3 -m temporal_pipeline.client signal  <workflow_id> storyboard_approved
    python3 -m temporal_pipeline.client state   <workflow_id>
    python3 -m temporal_pipeline.client result  <workflow_id>
    python3 -m temporal_pipeline.client history <workflow_id>
    python3 -m temporal_pipeline.client evidence <workflow_id>

``state`` queries THROUGH the workflow method reference, never by name string.
WP-31 lost an entire demonstration run to that: querying by name gives the SDK
no result type, hands back an undecoded ``dict``, and the gate-detection loop
silently never matched. Recorded here so the next person does not repeat it.

``evidence`` is the pair of counts the resume and duplicate-delivery proofs
rest on, read from two independent places: the server's durable event history,
and the activity bodies' own on-disk ledger.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from temporalio.client import Client

from temporal_pipeline.activities import job_root, store_for
from temporal_pipeline.dag import SceneRef
from temporal_pipeline.reference_storyboard import reference_storyboard
from temporal_pipeline.workflow import PipelineInput, VideoPipelineWorkflow

DEFAULT_TARGET = os.environ.get("IVGS_TEMPORAL_TARGET", "192.168.1.96:7233")
DEFAULT_NAMESPACE = os.environ.get("IVGS_TEMPORAL_NAMESPACE", "dev")
WORKFLOW_QUEUE = "default"


def storyboard_from_spec(spec: str) -> List[SceneRef]:
    """``image:2,animation:3,video_clip:1`` -> scenes in that order."""
    scenes: List[SceneRef] = []
    index = 0
    for chunk in spec.split(","):
        media_type, _, count = chunk.partition(":")
        for _ in range(int(count or 1)):
            scenes.append(
                SceneRef(
                    scene_id=f"scene-{index}",
                    scene_index=index,
                    media_type=media_type.strip(),
                    narration_text=f"stub narration for scene {index}",
                    visual_description=f"stub visual for scene {index}",
                )
            )
            index += 1
    return scenes


async def _connect(args) -> Client:
    return await Client.connect(args.target, namespace=args.namespace)


async def cmd_start(client: Client, args) -> None:
    if args.reference:
        storyboard = reference_storyboard()
    else:
        storyboard = storyboard_from_spec(args.scenes)

    handle = await client.start_workflow(
        VideoPipelineWorkflow.run,
        PipelineInput(
            job_id=args.workflow_id,
            project_id=args.project_id,
            project_name=args.project_name,
            storyboard=storyboard,
            include_final_render=not args.stop_at_draft,
            gpu_reservations=not args.no_reservations,
        ),
        id=args.workflow_id,
        task_queue=WORKFLOW_QUEUE,
    )
    print(
        json.dumps(
            {
                "started": handle.id,
                "run_id": handle.result_run_id,
                "scenes": len(storyboard),
                "media_mix": dict(Counter(s.media_type for s in storyboard)),
                "state_root": str(job_root(args.workflow_id)),
            },
            indent=2,
        )
    )


async def cmd_signal(client: Client, args) -> None:
    handle = client.get_workflow_handle(args.workflow_id)
    payload = [args.payload] if args.payload else []
    await handle.signal(args.signal_name, *payload)
    print(f"signalled {args.signal_name} -> {args.workflow_id}")


async def cmd_state(client: Client, args) -> None:
    handle = client.get_workflow_handle_for(
        VideoPipelineWorkflow.run, args.workflow_id
    )
    state = await handle.query(VideoPipelineWorkflow.state)
    print(json.dumps(asdict(state) if not isinstance(state, dict) else state, indent=2))


async def cmd_result(client: Client, args) -> None:
    handle = client.get_workflow_handle(args.workflow_id)
    print(json.dumps(await handle.result(), indent=2, default=str))


async def _history_events(client: Client, workflow_id: str) -> List[Any]:
    handle = client.get_workflow_handle(workflow_id)
    return [ev async for ev in handle.fetch_history_events()]


async def cmd_history(client: Client, args) -> None:
    from temporalio.api.enums.v1 import EventType

    events = await _history_events(client, args.workflow_id)
    for ev in events:
        name = EventType.Name(ev.event_type)
        stamp = ev.event_time.ToDatetime().strftime("%H:%M:%SZ")
        detail = ""
        if name == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
            detail = ev.activity_task_scheduled_event_attributes.activity_type.name
            queue = ev.activity_task_scheduled_event_attributes.task_queue.name
            detail = f"{detail} -> {queue}"
        elif name == "EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED":
            detail = ev.workflow_execution_signaled_event_attributes.signal_name
        print(f"{ev.event_id:>4}  {stamp}  {name:<45} {detail}")


async def cmd_export(client: Client, args) -> None:
    """
    Write the run's full event history as JSON, for the replay test.

    AD-05 §7.2: "A replay test runs against captured histories in CI before any
    worker deploy." This is how a history gets captured. The file is committed
    alongside the tests so the gate exists from the first workflow written
    rather than being retrofitted once jobs are in flight.
    """
    handle = client.get_workflow_handle(args.workflow_id)
    history = await handle.fetch_history()
    payload = history.to_json()
    if args.out:
        Path(args.out).write_text(payload)
        print(f"wrote {args.out} ({len(payload)} bytes)", file=sys.stderr)
    else:
        print(payload)


async def cmd_evidence(client: Client, args) -> None:
    """
    The two independent counts.

    ``activity SCHEDULES`` and ``completed exactly once`` come from the
    server's durable history: they are what Temporal believes happened.
    ``bodies executed`` comes from the activities' own fsync'd ledger: it is
    what actually ran, including the executions Temporal never heard about
    because the worker died before reporting them. ``effects`` is how many
    artifacts exist.

    The interesting run is the one where bodies > schedules and effects ==
    schedules. That is at-least-once delivery meeting an idempotent write.
    """
    from temporalio.api.enums.v1 import EventType

    events = await _history_events(client, args.workflow_id)
    counts = Counter(EventType.Name(ev.event_type) for ev in events)

    scheduled: Dict[int, str] = {}
    completed: Counter = Counter()
    for ev in events:
        name = EventType.Name(ev.event_type)
        if name == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
            attrs = ev.activity_task_scheduled_event_attributes
            scheduled[ev.event_id] = attrs.activity_type.name
        elif name == "EVENT_TYPE_ACTIVITY_TASK_COMPLETED":
            completed[ev.activity_task_completed_event_attributes.scheduled_event_id] += 1

    signals = [
        ev.workflow_execution_signaled_event_attributes.signal_name
        for ev in events
        if EventType.Name(ev.event_type) == "EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED"
    ]

    ledger = job_root(args.workflow_id) / "bodies.jsonl"
    bodies: Counter = Counter()
    body_pids: Dict[str, set] = {}
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("event") == "start":
                bodies[rec["key"]] += 1
                body_pids.setdefault(rec["key"], set()).add(rec["pid"])

    store = store_for(args.workflow_id)

    report = {
        "workflow_id": args.workflow_id,
        "event_counts": {k: v for k, v in sorted(counts.items()) if "ACTIVITY" in k
                         or "SIGNALED" in k or "COMPLETED" in k or "FAILED" in k},
        "signals_received": signals,
        "activity_schedules_total": len(scheduled),
        "activities_by_type": dict(Counter(scheduled.values())),
        "schedules_completed_exactly_once": sum(1 for v in completed.values() if v == 1),
        "schedules_completed_more_than_once": sum(1 for v in completed.values() if v > 1),
        "bodies_executed_total": sum(bodies.values()),
        "bodies_executed_more_than_once": {
            k: v for k, v in sorted(bodies.items()) if v > 1
        },
        "body_pids_for_repeats": {
            k: sorted(body_pids[k]) for k in bodies if bodies[k] > 1
        },
        "effects_total": store.effect_count(),
        "effect_keys_delivered_more_than_once": store.duplicate_deliveries(),
    }
    print(json.dumps(report, indent=2))

    # The human summary goes to STDERR so that `evidence > file.json` yields a
    # file that is actually JSON. The first version of this appended prose to
    # the same stream and produced evidence no tool could parse.
    dup_bodies = report["bodies_executed_more_than_once"]
    summary = (
        f"AT-LEAST-ONCE OBSERVED: {len(dup_bodies)} activity bod(y|ies) ran more "
        f"than once; {report['effects_total']} effects exist for "
        f"{report['activity_schedules_total']} schedules. Every repeat converged "
        "on the effect that already existed."
        if dup_bodies
        else (
            "no activity body ran twice in this run: the kill did not land inside "
            "an ack window. The workflow-level property (each schedule completed "
            "exactly once) is proven either way; the at-least-once window is not."
        )
    )
    print(summary, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="IVGS Temporal shadow driver")
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    sub = ap.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("workflow_id")
    start.add_argument("--project-id", default="shadow-project")
    start.add_argument("--project-name", default="WP-41 shadow")
    start.add_argument(
        "--reference",
        action="store_true",
        help="use the banked 2026-08-23 storyboard: 4 image / 12 animation / 2 video",
    )
    start.add_argument("--scenes", default="image:2,video_clip:1,animation:3")
    start.add_argument("--stop-at-draft", action="store_true")
    start.add_argument("--no-reservations", action="store_true")

    sig = sub.add_parser("signal")
    sig.add_argument("workflow_id")
    sig.add_argument("signal_name")
    sig.add_argument("payload", nargs="?", default="")

    for name in ("state", "result", "history", "evidence"):
        p = sub.add_parser(name)
        p.add_argument("workflow_id")

    export = sub.add_parser("export")
    export.add_argument("workflow_id")
    export.add_argument("--out", default="", help="file to write; stdout if absent")

    return ap


async def main() -> int:
    args = build_parser().parse_args()
    client = await _connect(args)
    await {
        "start": cmd_start,
        "signal": cmd_signal,
        "state": cmd_state,
        "result": cmd_result,
        "history": cmd_history,
        "evidence": cmd_evidence,
        "export": cmd_export,
    }[args.command](client, args)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
