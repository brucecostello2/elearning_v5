#!/usr/bin/env bash
# node-01. Shared settings for the WP-41 shadow demonstrations.
#
# The shadow worker needs the Temporal SDK, which is deliberately NOT in the
# repo venv: /opt/ivgs/.venv is the venv the Python test suite runs in, and
# adding temporalio to it would put a new dependency under every existing test
# for the sake of a package that no production path imports. The shadow venv
# lives outside the repo entirely so it cannot be committed by accident.
#
#   python3 -m venv /home/dev/.venv-ivgs-temporal
#   /home/dev/.venv-ivgs-temporal/bin/pip install temporalio==1.31.0 pydantic==2.10.4

set -uo pipefail

IVGS_ROOT="${IVGS_ROOT:-/opt/ivgs}"
export PYTHONPATH="${IVGS_ROOT}/ivgs-workers"
export IVGS_TEMPORAL_TARGET="${IVGS_TEMPORAL_TARGET:-192.168.1.96:7233}"
export IVGS_TEMPORAL_NAMESPACE="${IVGS_TEMPORAL_NAMESPACE:-dev}"
export IVGS_TEMPORAL_SHADOW_STATE="${IVGS_TEMPORAL_SHADOW_STATE:-/tmp/ivgs-temporal-shadow}"

# models.task_result is imported for its enums; config.py is not imported at
# all by this package, but ivgs-workers' package root reads these at import
# time in other modules and a stray import would otherwise fail loudly.
export VLLM_PRIMARY_URL="${VLLM_PRIMARY_URL:-http://192.168.1.91:8000}"
export VLLM_SECONDARY_URL="${VLLM_SECONDARY_URL:-http://192.168.1.92:8000}"
export VLLM_MIDSIZE_URL="${VLLM_MIDSIZE_URL:-http://192.168.1.93:8000}"

PY="${IVGS_TEMPORAL_PYTHON:-/home/dev/.venv-ivgs-temporal/bin/python}"
EVIDENCE_DIR="${EVIDENCE_DIR:-/tmp/ivgs-temporal-shadow/evidence}"
mkdir -p "$EVIDENCE_DIR"

# Matches ONLY the worker module, and never this script's own command line --
# a bare `pkill -f temporal_pipeline.worker` also matches the shell running it.
WORKER_PATTERN='[t]emporal_pipeline\.worker'

worker_pids() { pgrep -f "$WORKER_PATTERN" || true; }

start_worker() {   # start_worker <logfile> [extra args...]
  local log="$1"; shift
  : >"$log"
  # `exec` matters. Without it the backgrounded subshell forks the worker and
  # then WAITS on it; if start_worker is used in a pipeline, that waiting
  # subshell holds the pipe open forever -- which is exactly how the first
  # version of this script hung, silently, after printing the worker banner.
  # With exec the subshell BECOMES the worker, so nothing is left waiting.
  ( cd "${IVGS_ROOT}/ivgs-workers" && exec "$PY" -m temporal_pipeline.worker "$@" \
      >"$log" 2>&1 </dev/null ) &
  # Because of the exec, $! IS the worker. Never re-derive it from pgrep: a
  # leftover worker from an earlier demonstration would be picked up instead,
  # and the resume demonstration would SIGKILL the wrong process and then
  # report a resume that never happened.
  WORKER_PID=$!
  disown 2>/dev/null || true
  sleep 6
  head -1 "$log"
}

stop_worker() {    # stop_worker <SIGTERM|SIGKILL>
  local sig="${1:-SIGTERM}" pid pids i
  pids="$(worker_pids)"
  [ -z "$pids" ] && { echo "no worker running"; return 0; }
  for pid in $pids; do kill "-$sig" "$pid" 2>/dev/null && echo "sent $sig to $pid"; done
  # Wait for them to actually go, then escalate. A demonstration that starts
  # while a previous worker is still draining is a demonstration of nothing.
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ -z "$(worker_pids)" ] && return 0
  done
  for pid in $(worker_pids); do kill -9 "$pid" 2>/dev/null && echo "escalated SIGKILL to $pid"; done
  sleep 1
}

drive() { "$PY" -m temporal_pipeline.client "$@"; }
