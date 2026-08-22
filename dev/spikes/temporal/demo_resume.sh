#!/usr/bin/env bash
# WP-31 Lane C demonstration 2 — THE HEADLINE.
#
# Start a run, kill the worker mid per-scene fan-out, restart it, and show the
# workflow completes without re-executing the activities that already finished.
#
# Progress-gated, not clock-gated: the kill fires once the ledger shows the
# required number of scenes have COMPLETED, so the demonstration does not
# depend on guessing how fast the node is.
#
# Usage:  ./demo_resume.sh [workflow_id]

set -uo pipefail

WF_ID="${1:-ivgs-resume-demo}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export SPIKE_LEDGER="${SPIKE_LEDGER:-/tmp/ivgs-temporal-spike/${WF_ID}.jsonl}"
export TEMPORAL_TARGET="${TEMPORAL_TARGET:-127.0.0.1:7233}"
PY="${HERE}/.venv/bin/python3"
KILL_AFTER_SCENES="${KILL_AFTER_SCENES:-2}"
# Wait this long AFTER the threshold before killing, so the SIGKILL lands in
# the middle of the next scene rather than exactly on a completion boundary.
# Killing on the boundary kills inside the completion-report window, which
# makes an already-finished body run again and muddies the demonstration.
KILL_DELAY_S="${KILL_DELAY_S:-8}"

rm -f "$SPIKE_LEDGER"
mkdir -p "$(dirname "$SPIKE_LEDGER")"

completed_scenes() {
    # Single value, always, even on no-match (grep -c exits 1 on zero hits).
    if [ -f "$SPIKE_LEDGER" ]; then
        grep '"event": "complete"' "$SPIKE_LEDGER" 2>/dev/null \
            | grep -c '"key": "scene-' 2>/dev/null | head -1
    else
        echo 0
    fi
}

echo "=============================================================="
echo "WP-31 Lane C — resume demonstration"
echo "workflow_id : $WF_ID"
echo "ledger      : $SPIKE_LEDGER"
echo "=============================================================="

echo
echo "--- [1/7] starting worker A ---"
"$PY" "$HERE/worker.py" > "/tmp/ivgs-temporal-spike/${WF_ID}.workerA.log" 2>&1 &
WORKER_A=$!
sleep 5
echo "worker A pid=$WORKER_A"

echo
echo "--- [2/7] starting workflow ---"
"$PY" "$HERE/run_demo.py" start "$WF_ID" --scenes 6

echo
echo "--- [3/7] waiting for GATE 1, then signalling storyboard_approved ---"
for i in $(seq 1 30); do
    sig=$("$PY" "$HERE/run_demo.py" state "$WF_ID" 2>/dev/null \
          | grep -o '"waiting_on_signal": "[^"]*"' | cut -d'"' -f4)
    [ "$sig" = "storyboard_approved" ] && break
    sleep 2
done
"$PY" "$HERE/run_demo.py" signal "$WF_ID" storyboard_approved

echo
echo "--- [4/7] waiting for $KILL_AFTER_SCENES scenes to COMPLETE, then SIGKILL ---"
for i in $(seq 1 90); do
    n=$(completed_scenes)
    echo "    scenes completed: $n"
    [ "$n" -ge "$KILL_AFTER_SCENES" ] && break
    sleep 2
done
echo "    threshold reached; sleeping ${KILL_DELAY_S}s so the kill lands mid-activity"
sleep "$KILL_DELAY_S"
echo "    >>> SIGKILL worker A (pid $WORKER_A) mid-fan-out"
kill -9 "$WORKER_A" 2>/dev/null
wait "$WORKER_A" 2>/dev/null
echo "    worker A dead"
cp "$SPIKE_LEDGER" "${SPIKE_LEDGER%.jsonl}.at-kill.jsonl"

echo
echo "--- [5/7] ledger state AT THE MOMENT OF THE KILL ---"
"$PY" "$HERE/analyze_ledger.py" "${SPIKE_LEDGER%.jsonl}.at-kill.jsonl"

echo
echo "--- [6/7] restarting worker B ---"
sleep 3
"$PY" "$HERE/worker.py" > "/tmp/ivgs-temporal-spike/${WF_ID}.workerB.log" 2>&1 &
WORKER_B=$!
echo "worker B pid=$WORKER_B"

echo "    waiting for GATE 2, then signalling draft_approved"
for i in $(seq 1 120); do
    sig=$("$PY" "$HERE/run_demo.py" state "$WF_ID" 2>/dev/null \
          | grep -o '"waiting_on_signal": "[^"]*"' | cut -d'"' -f4)
    [ "$sig" = "draft_approved" ] && break
    sleep 2
done
"$PY" "$HERE/run_demo.py" signal "$WF_ID" draft_approved

echo "    waiting for completion"
"$PY" "$HERE/run_demo.py" result "$WF_ID"
kill "$WORKER_B" 2>/dev/null

echo
echo "--- [7/7] FINAL LEDGER — did any completed activity run twice? ---"
"$PY" "$HERE/analyze_ledger.py" "$SPIKE_LEDGER"
