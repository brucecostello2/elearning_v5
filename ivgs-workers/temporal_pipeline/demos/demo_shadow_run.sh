#!/usr/bin/env bash
# node-01. WP-41 Task 2 -- the full shadow run, start to final.
#
#   start -> GATE 1 signal -> media fan-out/join (three labels)
#         -> assembly stages -> GATE 2 signal -> final
#
# Uses the banked 2026-08-23 storyboard: 18 scenes, 4 image / 12 animation /
# 2 video_clip -- the same media mix that produced WP-39's lost join, so the
# three-label property is demonstrated on the shape that broke.
#
#   ./demo_shadow_run.sh [workflow_id]
#
# Evidence lands in $EVIDENCE_DIR (default /tmp/ivgs-temporal-shadow/evidence).

set -uo pipefail
cd "$(dirname "$0")"
. ./shadow_env.sh

WF="${1:-wp41-shadow-$(date +%Y%m%d-%H%M%S)}"
OUT="$EVIDENCE_DIR/$WF"
mkdir -p "$OUT"
rm -rf "${IVGS_TEMPORAL_SHADOW_STATE:?}/$WF"

echo "=== WP-41 shadow run: $WF ==="
echo "--- 0. worker ---"
stop_worker SIGTERM >/dev/null
# gpu-concurrency 4: AD-05 §4.2 says 1 and the worker defaults to 1. Raised
# here only so an 18-scene fan-out finishes in under a minute.
start_worker "$OUT/worker.log" --gpu-concurrency 4 | tee "$OUT/worker-banner.txt"

echo "--- 1. start ---"
drive start "$WF" --reference \
  --project-id c12fa967-f989-4ed4-8e20-3ea62cb92e8f \
  --project-name "double digit multiplication" | tee "$OUT/01-start.json"

sleep 14
echo "--- 2. state at GATE 1 ---"
drive state "$WF" | tee "$OUT/02-state-at-gate1.json"

echo "--- 3. signal storyboard_approved ---"
drive signal "$WF" storyboard_approved "approved by WP-41 shadow run" \
  | tee "$OUT/03-signal-gate1.txt"

sleep 40
echo "--- 4. state at GATE 2 (media join done) ---"
drive state "$WF" | tee "$OUT/04-state-at-gate2.json"

echo "--- 5. signal draft_approved ---"
drive signal "$WF" draft_approved | tee "$OUT/05-signal-gate2.txt"

sleep 12
echo "--- 6. result ---"
drive result "$WF" | tee "$OUT/06-result.json"

echo "--- 7. event history ---"
drive history "$WF" | tee "$OUT/07-history.txt"

echo "--- 8. evidence ---"
drive evidence "$WF" | tee "$OUT/08-evidence.json"

echo "--- 9. stop the worker ---"
# Leaving it running would make the NEXT demonstration start against a worker
# it did not launch, which is how the first resume run SIGKILLed a stranger.
stop_worker SIGTERM

echo
echo "evidence written to $OUT"
