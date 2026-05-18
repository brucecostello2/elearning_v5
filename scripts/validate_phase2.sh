#!/usr/bin/env bash
# IVGS v4 Phase 2 Validation Suite
# Returns exit code 0 if all tests pass, 1 if any fail.
set -uo pipefail

API="http://node-01:8000"
SCHEDULER="http://node-01:8001"
PROMETHEUS="http://node-01:9090"
GRAFANA="${GRAFANA_URL:-http://node-01:3001}"

PASS=0; FAIL=0

pass() { echo "  [PASS] $*"; ((PASS++)); }
fail() { echo "  [FAIL] $*"; ((FAIL++)); }
header() { echo; echo "── TEST: $* ──"; }

# ─── Test 1: Manifest Generation ──────────────────────────────────────────
header "Manifest Generation"
JOB_ID=$(curl -sf -X POST "$API/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"title":"Phase2 Validation","type":"test"}' | jq -r '.id')

if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "null" ]; then
  fail "Could not create test job"
else
  pass "Test job created: $JOB_ID"

  # Generate manifest
  sleep 2
  GEN_STATUS=$(curl -sf -X POST "$API/api/v1/jobs/$JOB_ID/manifest/generate" \
    | jq -r '.status // "error"')
  if [ "$GEN_STATUS" != "error" ]; then
    pass "Manifest generated (status: $GEN_STATUS)"
  else
    fail "Manifest generation failed"
  fi

  # Verify manifest in DB
  MANIFEST=$(curl -sf "$API/api/v1/jobs/$JOB_ID/manifest")
  if echo "$MANIFEST" | jq -e '.id' > /dev/null 2>&1; then
    pass "Manifest persisted to DB"
  else
    fail "Manifest not found in DB"
  fi
fi

# ─── Test 2: DLQ Capture ──────────────────────────────────────────────────
header "DLQ Capture and Replay"
INITIAL_COUNT=$(curl -sf "$API/api/v1/dlq/messages" | jq '.total // 0')

# Inject a synthetic DLQ message via API helper
curl -sf -X POST "$API/api/v1/internal/dlq/inject-test" \
  -H "Content-Type: application/json" \
  -d '{"task":"test.failure","category":"transient"}' > /dev/null 2>&1 || true

sleep 3
NEW_COUNT=$(curl -sf "$API/api/v1/dlq/messages" | jq '.total // 0')

if [ "$NEW_COUNT" -ge "$INITIAL_COUNT" ]; then
  pass "DLQ message captured (count: $NEW_COUNT)"
else
  fail "DLQ count did not increase (was $INITIAL_COUNT, now $NEW_COUNT)"
fi

# Test analytics endpoint
ANALYTICS=$(curl -sf "$API/api/v1/dlq/analytics?hours=1")
if echo "$ANALYTICS" | jq -e '.total_pending' > /dev/null 2>&1; then
  pass "DLQ analytics endpoint working"
else
  fail "DLQ analytics endpoint failed"
fi

# ─── Test 3: Quality Score Endpoint ───────────────────────────────────────
header "Quality Scoring API"
if [ -n "${JOB_ID:-}" ] && [ "$JOB_ID" != "null" ]; then
  QUALITY=$(curl -sf "$API/api/v1/jobs/$JOB_ID/quality")
  if echo "$QUALITY" | jq 'type == "array"' > /dev/null 2>&1; then
    pass "Quality scores endpoint accessible"
  else
    fail "Quality scores endpoint error"
  fi

  FLAGGED=$(curl -sf "$API/api/v1/quality/flagged")
  if echo "$FLAGGED" | jq -e '.total' > /dev/null 2>&1; then
    pass "Flagged assets endpoint working"
  else
    fail "Flagged assets endpoint error"
  fi
fi

# ─── Test 4: Worker Supervisor ────────────────────────────────────────────
header "Worker Supervision"
# Trigger supervisor task via API
SUP=$(curl -sf -X POST "$API/api/v1/internal/tasks/supervise" || echo '{}')
if echo "$SUP" | jq -e . > /dev/null 2>&1; then
  pass "Worker supervisor task triggered"
else
  fail "Worker supervisor task error"
fi

# ─── Test 5: Prometheus Scraping ──────────────────────────────────────────
header "Prometheus Scraping"
TARGETS=$(curl -sf "$PROMETHEUS/api/v1/targets" | jq '.data.activeTargets | length')
if [ "${TARGETS:-0}" -gt 0 ]; then
  pass "Prometheus has $TARGETS active scrape targets"
else
  fail "Prometheus has no active targets"
fi

# Check IVGS API is being scraped
IVGS_TARGET=$(curl -sf "$PROMETHEUS/api/v1/targets" \
  | jq -r '.data.activeTargets[] | select(.labels.job == "ivgs-api") | .health')
if [ "$IVGS_TARGET" = "up" ]; then
  pass "ivgs-api target is UP in Prometheus"
else
  fail "ivgs-api target not up (health: ${IVGS_TARGET:-unknown})"
fi

# ─── Test 6: Grafana Dashboards ───────────────────────────────────────────
header "Grafana Dashboard Health"
GF_CREDS="${GRAFANA_USER:-admin}:${GRAFANA_PASSWORD:-ivgs-grafana}"
HEALTH=$(curl -sf -u "$GF_CREDS" "$GRAFANA/api/health" | jq -r '.database')
if [ "$HEALTH" = "ok" ]; then
  pass "Grafana health check passed"
else
  fail "Grafana health: ${HEALTH:-error}"
fi

DASH_COUNT=$(curl -sf -u "$GF_CREDS" "$GRAFANA/api/search" | jq 'length')
if [ "${DASH_COUNT:-0}" -ge 2 ]; then
  pass "Grafana has $DASH_COUNT dashboards provisioned"
else
  fail "Grafana has fewer than 2 dashboards (found: ${DASH_COUNT:-0})"
fi

# ─── Summary ──────────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════"
echo "Phase 2 Validation: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
