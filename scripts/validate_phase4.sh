#!/usr/bin/env bash
# validate_phase4.sh — health-check all Phase 4 components
set -uo pipefail

PASS=0
FAIL=0
check() {
  local desc="$1"
  local cmd="$2"
  if eval "$cmd" > /dev/null 2>&1; then
    echo "  PASS  $desc"
    ((PASS++))
  else
    echo "  FAIL  $desc"
    ((FAIL++))
  fi
}

echo "=== Phase 4 Validation ==="

echo "--- SeaweedFS Cluster ---"
check "Master responds"     "curl -sf http://node-01:9333/cluster/status"
check "Filer responds"      "curl -sf http://node-01:8888/"
check "HOT volume (node-02)" "curl -sf http://node-02:8080/status"
check "WARM volume (node-03)" "curl -sf http://node-03:8081/status"
check "COLD volume (node-04)" "curl -sf http://node-04:8082/status"
check "ARCHIVE volume (node-05)" "curl -sf http://node-05:8083/status"

echo "--- Database Migrations ---"
check "Migration 015 (retention_policies)"   \
  "psql \$DATABASE_URL -c '\\d retention_policies' -q"
check "Migration 016 (seaweedfs_fid column)" \
  "psql \$DATABASE_URL -c '\\d render_outputs' -q | grep seaweedfs_fid"
check "Migration 017 (storage_quotas)"       \
  "psql \$DATABASE_URL -c '\\d storage_quotas' -q"
check "Migration 018 (backup_snapshots)"     \
  "psql \$DATABASE_URL -c '\\d backup_snapshots' -q"
check "Migration 019 (deduplication_index)"  \
  "psql \$DATABASE_URL -c '\\d deduplication_index' -q"

echo "--- NAS Backup ---"
check "NAS mounted"         "mountpoint -q /mnt/backup"
check "NAS writable"        "touch /mnt/backup/.ivgs_write_test && rm /mnt/backup/.ivgs_write_test"

echo "--- API Endpoints ---"
check "Retention policies API" "curl -sf http://node-01:8000/api/v1/retention/policies"
check "Storage analytics API"  "curl -sf http://node-01:8000/api/v1/storage-analytics/capacity"

echo "--- Celery Beat ---"
check "Beat process running"  "docker compose ps celery-beat | grep -q Up"
check "Ops worker running"    "docker compose ps celery-worker-ops | grep -q Up"

echo ""
echo "Results: PASS=$PASS  FAIL=$FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "Phase 4 validation FAILED — review above errors"
  exit 1
fi
echo "Phase 4 validation PASSED"
