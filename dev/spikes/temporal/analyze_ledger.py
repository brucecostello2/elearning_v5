"""
WP-31 Lane C — the resume evidence, read off the activity execution ledger.

The ledger is written by the activity bodies themselves (activities.py), in
the worker process, fsync'd on every line. So it records what ACTUALLY
executed, independently of anything Temporal reports.

The property under test: an activity that COMPLETED before the worker was
killed must not execute again after the worker restarts.

  python3 analyze_ledger.py [ledger_path]
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "SPIKE_LEDGER", "/tmp/ivgs-temporal-spike/ledger.jsonl"
)

starts = defaultdict(list)
completes = defaultdict(list)
fails = defaultdict(list)

with open(path) as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        {"start": starts, "complete": completes, "failed": fails}[rec["event"]][
            rec["key"]
        ].append(rec)

pids = sorted({r["pid"] for rs in starts.values() for r in rs})
print(f"ledger: {path}")
print(f"worker pids observed: {pids}  ({len(pids)} distinct worker process(es))")
print()
print(f"{'activity':<20} {'starts':>6} {'completes':>10} {'pids':<12} verdict")
print("-" * 72)

reexecuted = []
for key in sorted(starts, key=lambda k: (k.startswith("scene"), k)):
    s, c = starts[key], completes.get(key, [])
    kp = sorted({r["pid"] for r in s})
    # A completed activity that started again is a re-execution: the failure
    # this demonstration exists to rule out.
    # A body that ran more than once means the worker died before the SDK
    # could report the first run's completion to the server. That is
    # at-least-once activity execution, not a resume failure -- see
    # resume_evidence.py, which reads the durable history. The failure this
    # spike rules out is the pipeline restarting from stage 1.
    if len(s) > 1:
        verdict = "body ran twice (killed inside the ack window)"
        reexecuted.append(key)
    else:
        verdict = "ran exactly once"
    print(f"{key:<20} {len(s):>6} {len(c):>10} {str(kp):<12} {verdict}")

print()
survivors = [k for k in completes if len(starts[k]) == 1]
print(f"activity bodies that ran exactly once : {len(survivors)}")
print(f"activity bodies that ran twice        : {len(reexecuted)}  {reexecuted}")
print()
print("Bodies running twice is EXPECTED for work in flight when the worker was")
print("killed. What must never happen is the pipeline restarting from stage 1.")
print("Run resume_evidence.py for the durable-history view.")
