#!/usr/bin/env bash
# IVGS v4 Phase 2 Deployment Script
# Idempotent — safe to re-run on partial failures.
# Prerequisites: Phase 1 fully deployed and validated.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/var/log/ivgs/deploy_phase2_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname "$LOG_FILE")"

log()  { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }
ok()   { echo "  ✓ $*" | tee -a "$LOG_FILE"; }
fail() { echo "  ✗ $*" | tee -a "$LOG_FILE"; exit 1; }

log "=== IVGS v4 Phase 2 Deployment ==="
log "Root: $ROOT_DIR"
log "Log:  $LOG_FILE"

# ─── Step 1: Pre-flight checks ────────────────────────────────────────────
log "Step 1: Pre-flight checks"

# Verify Phase 1 is deployed (migrations 001-005 must exist)
P1_COUNT=$(psql "$DATABASE_URL" -tAc \
  "SELECT COUNT(*) FROM alembic_version WHERE version_num IN ('001','002','003','004','005')")
[ "$P1_COUNT" -eq 5 ] || fail "Phase 1 migrations not found. Deploy Phase 1 first."
ok "Phase 1 migrations verified"

# Check API is healthy
curl -sf "http://node-01:8000/health" > /dev/null || fail "API not reachable"
ok "API health check passed"

# Check GPU Scheduler
curl -sf "http://node-01:8001/health" > /dev/null || fail "GPU Scheduler not reachable"
ok "Scheduler health check passed"

# ─── Step 2: Database Migrations (006-010) ────────────────────────────────
log "Step 2: Applying database migrations 006-010"
cd "$ROOT_DIR/ivgs-api"
for rev in 006 007 008 009 010; do
  log "  Applying migration $rev..."
  alembic upgrade "$rev" 2>&1 | tee -a "$LOG_FILE" || fail "Migration $rev failed"
  ok "Migration $rev applied"
done

# ─── Step 3: Configure RabbitMQ DLQ exchanges ─────────────────────────────
log "Step 3: Configuring RabbitMQ DLQ exchanges"
RABBITMQ_MGMT="${RABBITMQ_MGMT_URL:-http://node-01:15672}"
RABBITMQ_CREDS="${RABBITMQ_USER:-ivgs}:${RABBITMQ_PASS:-changeme}"

# Upload definitions (idempotent — RabbitMQ merges with existing config)
curl -sf -u "$RABBITMQ_CREDS" \
  -H "Content-Type: application/json" \
  -X POST "$RABBITMQ_MGMT/api/definitions" \
  -d @"$ROOT_DIR/infra/rabbitmq/definitions.json" > /dev/null \
  || fail "RabbitMQ definitions upload failed"
ok "RabbitMQ DLQ exchanges configured"

# ─── Step 4: Deploy Prometheus + Grafana ──────────────────────────────────
log "Step 4: Deploying observability stack"
cd "$ROOT_DIR"
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase1.yml \
  -f infra/docker-compose.phase2.yml \
  up -d prometheus grafana node-exporter 2>&1 | tee -a "$LOG_FILE"
ok "Prometheus and Grafana started"

# Wait for Prometheus to be ready
log "  Waiting for Prometheus..."
for i in $(seq 1 20); do
  curl -sf "http://node-01:9090/-/ready" > /dev/null 2>&1 && break
  [ "$i" -eq 20 ] && fail "Prometheus did not become ready"
  sleep 3
done
ok "Prometheus ready"

# ─── Step 5: Provision Grafana dashboards ─────────────────────────────────
log "Step 5: Provisioning Grafana dashboards"
GF_URL="${GRAFANA_URL:-http://node-01:3001}"
GF_CREDS="${GRAFANA_USER:-admin}:${GRAFANA_PASSWORD:-ivgs-grafana}"

# Wait for Grafana
for i in $(seq 1 20); do
  curl -sf "$GF_URL/api/health" > /dev/null 2>&1 && break
  [ "$i" -eq 20 ] && fail "Grafana did not become ready"
  sleep 3
done

# Import dashboards
for dashboard in "$ROOT_DIR"/configs/grafana/dashboards/*.json; do
  NAME=$(basename "$dashboard")
  log "  Importing dashboard: $NAME"
  PAYLOAD=$(python3 -c "
import json, sys
d = json.load(open('$dashboard'))
print(json.dumps({'dashboard': d, 'overwrite': True, 'folderId': 0}))
")
  curl -sf -u "$GF_CREDS" \
    -H "Content-Type: application/json" \
    -X POST "$GF_URL/api/dashboards/import" \
    -d "$PAYLOAD" > /dev/null \
    || log "  Warning: dashboard $NAME import returned error (may already exist)"
done
ok "Grafana dashboards provisioned"

# ─── Step 6: Restart workers with Phase 2 config ─────────────────────────
log "Step 6: Restarting Celery workers"
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase1.yml \
  -f infra/docker-compose.phase2.yml \
  restart ivgs-celery-default ivgs-celery-beat-p2 2>&1 | tee -a "$LOG_FILE"
ok "Workers restarted"

sleep 10  # Allow workers to register

# ─── Step 7: Run validation ───────────────────────────────────────────────
log "Step 7: Running Phase 2 validation suite"
bash "$SCRIPT_DIR/validate_phase2.sh" 2>&1 | tee -a "$LOG_FILE"

log ""
log "=== Phase 2 Deployment Complete ==="
log "Prometheus:  http://node-01:9090"
log "Grafana:     http://node-01:3001  (admin / \$GRAFANA_PASSWORD)"
log "RabbitMQ:    http://node-01:15672"
log "Full log:    $LOG_FILE"
