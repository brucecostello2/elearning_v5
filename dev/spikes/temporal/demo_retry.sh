#!/usr/bin/env bash
# WP-31 Lane C demonstration 3 — bounded retries, failure surfaced not swallowed.
set -uo pipefail
WF_ID="${1:-ivgs-retry-demo}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export SPIKE_LEDGER="${SPIKE_LEDGER:-/tmp/ivgs-temporal-spike/${WF_ID}.jsonl}"
export TEMPORAL_TARGET="${TEMPORAL_TARGET:-127.0.0.1:7233}"
PY="${HERE}/.venv/bin/python3"
rm -f "$SPIKE_LEDGER"; mkdir -p "$(dirname "$SPIKE_LEDGER")"

"$PY" "$HERE/worker.py" > "/tmp/ivgs-temporal-spike/${WF_ID}.worker.log" 2>&1 &
W=$!; sleep 5
"$PY" "$HERE/run_demo.py" start "$WF_ID" --scenes 2 --fail
for i in $(seq 1 30); do
    sig=$("$PY" "$HERE/run_demo.py" state "$WF_ID" 2>/dev/null | grep -o '"waiting_on_signal": "[^"]*"' | cut -d'"' -f4)
    [ "$sig" = "storyboard_approved" ] && break; sleep 2
done
"$PY" "$HERE/run_demo.py" signal "$WF_ID" storyboard_approved
for i in $(seq 1 60); do
    sig=$("$PY" "$HERE/run_demo.py" state "$WF_ID" 2>/dev/null | grep -o '"waiting_on_signal": "[^"]*"' | cut -d'"' -f4)
    [ "$sig" = "draft_approved" ] && break; sleep 2
done
"$PY" "$HERE/run_demo.py" signal "$WF_ID" draft_approved
sleep 20
echo "=== final workflow state (note the failure field) ==="
"$PY" "$HERE/run_demo.py" state "$WF_ID"
echo "=== flaky activity attempts in the ledger ==="
grep flaky "$SPIKE_LEDGER"
kill "$W" 2>/dev/null
