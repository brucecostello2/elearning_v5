#!/usr/bin/env bash
set -uo pipefail

API="${IVGS_API_URL:-http://localhost:8000}"
PASS=0; FAIL=0

pass() { echo "  [PASS] $1"; ((PASS++)); }
fail() { echo "  [FAIL] $1"; ((FAIL++)); }

echo "=== Phase 3 Validation ==="

# ── Test 1: Remotion service health ─────────────────────────────
echo ""
echo "[Test 1] Remotion service health"
STATUS=$(curl -sf http://localhost:3002/health | jq -r '.status' 2>/dev/null)
if [[ "$STATUS" == "ok" ]]; then
  pass "Remotion service healthy"
else
  fail "Remotion service not responding (got: ${STATUS:-none})"
fi

# ── Test 2: Remotion renders a template ──────────────────────────
echo ""
echo "[Test 2] Remotion title card render"
RENDER_OUT=$(curl -sf -X POST http://localhost:3002/render \
  -H 'Content-Type: application/json' \
  -d '{
    "composition": "title_card",
    "outputFile": "/tmp/ivgs_test_title.mp4",
    "inputProps": {"title": "Phase 3 Test", "durationFrames": 30},
    "codec": "h264"
  }' 2>/dev/null)
if echo "$RENDER_OUT" | jq -e '.success == true' >/dev/null 2>&1; then
  pass "Remotion title card rendered successfully"
else
  fail "Remotion render failed: ${RENDER_OUT:-no response}"
fi

# ── Test 3: AI video generation tables migrated ──────────────────
echo ""
echo "[Test 3] Migration 011-014 applied"
for TABLE in ai_video_generations localization_configs localized_assets \
             lip_sync_validations caption_alignments; do
  COUNT=$(docker exec ivgs-db psql -U ivgs -d ivgs -At \
    -c "SELECT COUNT(*) FROM information_schema.tables \
        WHERE table_name='${TABLE}'" 2>/dev/null)
  if [[ "${COUNT:-0}" == "1" ]]; then
    pass "Table ${TABLE} exists"
  else
    fail "Table ${TABLE} missing"
  fi
done

# ── Test 4: Localization API endpoint reachable ──────────────────
echo ""
echo "[Test 4] Localization API endpoints"
HTTP_CODE=$(curl -so /dev/null -w "%{http_code}" \
  "${API}/api/v1/localization/languages")
if [[ "$HTTP_CODE" == "200" ]]; then
  LANG_COUNT=$(curl -sf "${API}/api/v1/localization/languages" \
    | jq '.languages | length')
  pass "Localization languages endpoint: ${LANG_COUNT} languages"
else
  fail "Localization languages endpoint: HTTP ${HTTP_CODE}"
fi

# ── Test 5: CogVideoX service availability check via API ─────────
echo ""
echo "[Test 5] AI video stats endpoint"
HTTP_CODE=$(curl -so /dev/null -w "%{http_code}" \
  "${API}/api/v1/ai-video/stats?hours=1")
if [[ "$HTTP_CODE" == "200" ]]; then
  pass "AI video stats endpoint accessible"
else
  fail "AI video stats endpoint: HTTP ${HTTP_CODE}"
fi

# ── Test 6: Lip sync endpoint reachable ──────────────────────────
echo ""
echo "[Test 6] Lip sync validation endpoint"
JOB_ID="00000000-0000-0000-0000-000000000001"
HTTP_CODE=$(curl -so /dev/null -w "%{http_code}" \
  "${API}/api/v1/jobs/${JOB_ID}/lip-sync/validations")
if [[ "$HTTP_CODE" =~ ^(200|404)$ ]]; then
  pass "Lip sync endpoint accessible (HTTP ${HTTP_CODE})"
else
  fail "Lip sync endpoint: HTTP ${HTTP_CODE}"
fi

# ── Test 7: Enqueue AI video task and verify DB record ───────────
echo ""
echo "[Test 7] AI video task dispatch (dry run)"
# Celery inspect to confirm gpu_video queue workers registered
TASK_REGISTERED=$(celery -A ivgs_workers.celeryconfig inspect registered \
  --timeout=10 2>/dev/null | grep "tasks.generate_ai_video" | wc -l || echo 0)
if [[ "${TASK_REGISTERED:-0}" -gt "0" ]]; then
  pass "generate_ai_video task registered on gpu_video workers"
else
  fail "generate_ai_video task not registered (no gpu_video workers?)"
fi

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo "=== Validation Summary: ${PASS} passed, ${FAIL} failed ==="
if [[ "${FAIL}" -gt "0" ]]; then
  echo "ATTENTION: ${FAIL} test(s) failed. Check logs above."
  exit 1
fi
echo "Phase 3 validation PASSED."
