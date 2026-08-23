#!/usr/bin/env bash
# node-01. WP-41 Task 3 -- resume across a SIGKILL, on the real workflow shape.
#
# WP-31 proved this on a spike. This proves it on the workflow that AD-05
# actually prescribes: 18 scenes, three media branches, both gates, GPU
# reservation brackets, the whole graph.
#
# What it does:
#   worker A -> start -> GATE 1 -> mid-fan-out SIGKILL -> worker B -> GATE 2
#
# What to read afterwards, in 09-evidence.json:
#   * schedules_completed_more_than_once  MUST be 0
#     -- the workflow advanced exactly once per activity;
#   * bodies_executed_more_than_once      MAY be non-empty
#     -- at-least-once activity delivery, WP-31 Lane C's measured finding;
#   * effect_keys_delivered_more_than_once, against effects_total
#     -- every repeat converged on the artifact that already existed.
#
#   ./demo_resume.sh [workflow_id]

set -uo pipefail
cd "$(dirname "$0")"
. ./shadow_env.sh

WF="${1:-wp41-resume-$(date +%Y%m%d-%H%M%S)}"
OUT="$EVIDENCE_DIR/$WF"
KILL_AFTER="${KILL_AFTER:-11}"
mkdir -p "$OUT"
rm -rf "${IVGS_TEMPORAL_SHADOW_STATE:?}/$WF"

echo "=== WP-41 resume demonstration: $WF ==="
stop_worker SIGTERM >/dev/null

echo "--- 1. worker A ---"
# Concurrency 2 so an 18-scene fan-out takes long enough to have a real
# mid-flight moment to kill. AD-05 §4.2's production value is 1.
start_worker "$OUT/worker-a.log" --gpu-concurrency 2 > "$OUT/01-worker-a.txt"
cat "$OUT/01-worker-a.txt"
PID_A="$WORKER_PID"
echo "worker A pid=$PID_A"
grep -q "pid=$PID_A " "$OUT/01-worker-a.txt" || {
  echo "REFUSING: \$WORKER_PID ($PID_A) is not the pid the worker printed."
  exit 1
}

echo "--- 2. start ---"
drive start "$WF" --reference \
  --project-id c12fa967-f989-4ed4-8e20-3ea62cb92e8f > "$OUT/02-start.json"
cat "$OUT/02-start.json"

sleep 14
echo "--- 3. release GATE 1 ---"
drive state "$WF" > "$OUT/03-state-at-gate1.json"
drive signal "$WF" storyboard_approved "approved before the kill"

echo "--- 4. let the fan-out get going, then SIGKILL worker A ---"
sleep "$KILL_AFTER"
drive state "$WF" > "$OUT/04-state-before-kill.json"
python3 -c "
import json;d=json.load(open('$OUT/04-state-before-kill.json'))
print('  scenes completed before the kill:', len(d['scenes_completed']))
print('  media labels closed so far      :', d['media_labels_completed'])"
kill -SIGKILL "$PID_A" && echo "  SIGKILL -> $PID_A"
sleep 3
echo "  workers alive after kill: [$(worker_pids | tr '\n' ' ')]"

echo "--- 5. worker B ---"
start_worker "$OUT/worker-b.log" --gpu-concurrency 2 > "$OUT/05-worker-b.txt"
cat "$OUT/05-worker-b.txt"

echo "--- 6. wait for the draft, then release GATE 2 ---"
for _ in $(seq 1 30); do
  sleep 4
  drive state "$WF" > "$OUT/06-state.json" 2>/dev/null || continue
  if grep -q '"waiting_on_signal": "draft_approved"' "$OUT/06-state.json"; then
    break
  fi
done
cat "$OUT/06-state.json"
drive signal "$WF" draft_approved

sleep 10
echo "--- 7. result ---"
drive result "$WF" > "$OUT/07-result.json"; cat "$OUT/07-result.json"

echo "--- 8. event history ---"
drive history "$WF" > "$OUT/08-history.txt"

echo "--- 9. evidence ---"
drive evidence "$WF" | tee "$OUT/09-evidence.json"

echo "--- 10. body ledger, per key ---"
python3 - "$IVGS_TEMPORAL_SHADOW_STATE/$WF/bodies.jsonl" > "$OUT/10-ledger.txt" <<'PYEOF'
import json, sys
from collections import defaultdict
starts, completes, pids = defaultdict(int), defaultdict(int), defaultdict(set)
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if r["event"] == "start":
        starts[r["key"]] += 1; pids[r["key"]].add(r["pid"])
    elif r["event"] == "complete":
        completes[r["key"]] += 1
print(f"{'key':<34}{'starts':>7}{'completes':>11}  pids                verdict")
for key in sorted(starts):
    n, c, p = starts[key], completes[key], sorted(pids[key])
    verdict = "ran exactly once" if n == 1 else "body ran twice (killed inside the ack window)"
    print(f"{key:<34}{n:>7}{c:>11}  {str(p):<20}{verdict}")
PYEOF
cat "$OUT/10-ledger.txt"

echo "--- 11. stop worker B ---"
# Same reason demo_shadow_run.sh stops its own: a worker left running is a
# worker the NEXT demonstration will find with pgrep and mistake for its own.
stop_worker SIGTERM

echo
echo "evidence written to $OUT"
