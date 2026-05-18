#!/usr/bin/env bash
# validate_phase1.sh — IVGS Phase 1 post-deployment smoke tests
# Usage: ./scripts/validate_phase1.sh [--base-url http://node-01]
# Outputs a pass/fail table; exits 1 if any check fails.

set -uo pipefail

BASE_URL="${BASE_URL:-http://node-01}"
API_URL="${BASE_URL}/api/v4"
SCHEDULER_URL="${BASE_URL}:8001"
ENV_FILE="${1:-.env.phase1}"
PASS=0
FAIL=0
RESULTS=()

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }

check() {
    local name="$1"; shift
    local result
    if result=$(eval "$@" 2>&1); then
        RESULTS+=("  PASS  $name")
        ((PASS++))
    else
        RESULTS+=("  FAIL  $name  ($result)")
        ((FAIL++))
    fi
}

http_ok() {
    local url="$1"
    local code
    code=$(curl -sf -o /dev/null -w "%{http_code}" "$url")
    [[ "$code" == "200" ]] || { echo "HTTP ${code}"; return 1; }
}

json_field() {
    # json_field URL field expected_value
    local url="$1" field="$2" expected="$3"
    local actual
    actual=$(curl -sf "$url" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('${field}','MISSING'))")
    [[ "$actual" == "$expected" ]] || { echo "expected '${expected}', got '${actual}'"; return 1; }
}

# ── Load environment ──────────────────────────────────────────────────────────
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

log "IVGS Phase 1 Validation"
log "API base:       $API_URL"
log "Scheduler base: $SCHEDULER_URL"
echo

# ── 1. Infrastructure ─────────────────────────────────────────────────────────
log "Section 1: Infrastructure"

check "API /health returns 200" \
    "http_ok '${API_URL}/health'"

check "Scheduler /health returns 200" \
    "http_ok '${SCHEDULER_URL}/health'"

check "Scheduler status=healthy" \
    "json_field '${SCHEDULER_URL}/health' 'status' 'healthy'"

check "Redis connectivity (via scheduler)" \
    "json_field '${SCHEDULER_URL}/health' 'redis' 'ok'"

check "DB connectivity (via scheduler)" \
    "json_field '${SCHEDULER_URL}/health' 'db' 'ok'"

# ── 2. Database Schema ────────────────────────────────────────────────────────
log "Section 2: Database Schema"

check "Alembic current = head" \
    "alembic -c alembic/alembic.ini current 2>&1 | grep -q '(head)'"

check "Table pipeline_checkpoints exists" \
    "psql \"\${DATABASE_URL}\" -c '\d pipeline_checkpoints' -q 2>&1 | grep -q 'checkpoint_id'"

check "Table gpu_nodes exists" \
    "psql \"\${DATABASE_URL}\" -c '\d gpu_nodes' -q 2>&1 | grep -q 'node_id'"

check "Table gpu_allocations exists" \
    "psql \"\${DATABASE_URL}\" -c '\d gpu_allocations' -q 2>&1 | grep -q 'allocation_id'"

# ── 3. GPU Scheduler API ──────────────────────────────────────────────────────
log "Section 3: GPU Scheduler API"

check "GET /nodes returns array" \
    "curl -sf '${SCHEDULER_URL}/nodes' | python3 -c 'import sys,json; d=json.load(sys.stdin); assert isinstance(d,list)'"

check "GET /nodes has node-01 registered" \
    "curl -sf '${SCHEDULER_URL}/nodes' | python3 -c 'import sys,json; nodes=json.load(sys.stdin); ids=[n[\"node_id\"] for n in nodes]; assert \"node-01\" in ids, ids'"

check "GET /queue returns dict" \
    "curl -sf '${SCHEDULER_URL}/queue' | python3 -c 'import sys,json; d=json.load(sys.stdin); assert isinstance(d,dict)'"

# ── 4. Worker Heartbeats ──────────────────────────────────────────────────────
log "Section 4: Worker Heartbeats"

# Workers should have sent at least one heartbeat within the last 90s
check "At least 4 worker heartbeats received" \
    "curl -sf '${SCHEDULER_URL}/nodes' | python3 -c '
import sys,json,time
nodes = json.load(sys.stdin)
now = time.time()
recent = [n for n in nodes if n.get(\"last_heartbeat\") and (now - n[\"last_heartbeat\"]) < 90]
assert len(recent) >= 4, f\"Only {len(recent)} recent heartbeats\"
'"

# ── 5. Checkpoint API ─────────────────────────────────────────────────────────
log "Section 5: Checkpoint API"

check "GET /checkpoints/{job_id} returns 404 for unknown job" \
    "CODE=\$(curl -sf -o /dev/null -w '%{http_code}' '${API_URL}/checkpoints/unknown-job-id'); [[ \"\$CODE\" == '404' ]]"

# ── 6. End-to-End Smoke Job ───────────────────────────────────────────────────
log "Section 6: End-to-End Smoke Job"

SMOKE_JOB=$(curl -sf -X POST "${API_URL}/jobs" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"smoke test","duration_s":5,"budget_usd":0.1,"checkpoint_enabled":true}' \
    2>/dev/null || echo "SUBMIT_FAILED")

if [[ "$SMOKE_JOB" == "SUBMIT_FAILED" ]]; then
    RESULTS+=("  FAIL  Smoke job submission")
    ((FAIL++))
else
    SMOKE_ID=$(echo "$SMOKE_JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null || echo "PARSE_FAILED")
    if [[ "$SMOKE_ID" != "PARSE_FAILED" ]]; then
        RESULTS+=("  PASS  Smoke job submission (job_id=${SMOKE_ID})")
        ((PASS++))
        check "Smoke job status endpoint responds" \
            "http_ok '${API_URL}/jobs/${SMOKE_ID}/status'"
    else
        RESULTS+=("  FAIL  Smoke job response parse")
        ((FAIL++))
    fi
fi

# ── Print Results ─────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════"
echo " IVGS Phase 1 Validation Results"
echo "═══════════════════════════════════════════════════"
for line in "${RESULTS[@]}"; do
    echo "$line"
done
echo "───────────────────────────────────────────────────"
echo " PASSED: ${PASS}   FAILED: ${FAIL}"
echo "═══════════════════════════════════════════════════"

[[ "$FAIL" -eq 0 ]] || exit 1
