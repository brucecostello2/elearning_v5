#!/usr/bin/env bash
# deploy_phase4.sh — Deploy Phase 4: SeaweedFS cluster + all Phase 4 services
# Prereq: Phase 3 deployed, NAS mounted at /mnt/backup on all nodes
set -euo pipefail

CLUSTER_NODES=(node-01 node-02 node-03 node-04 node-05 node-06)
COMPOSE_BASE="docker/docker-compose.base.yml"
COMPOSE_P4="docker/docker-compose.phase4.yml"

echo "=== IVGS v4 Phase 4 Deploy ==="
echo "  Storage: SeaweedFS self-hosted (zero cloud dependencies)"
echo "  NAS backup target: /mnt/backup"

# 1. Verify NAS mount
echo "[1/7] Verifying NAS mount..."
if ! mountpoint -q /mnt/backup; then
  echo "ERROR: /mnt/backup is not mounted. Mount NAS before deploying."
  exit 1
fi
echo "  NAS mounted OK"

# 2. Verify tier mount points on storage nodes
echo "[2/7] Checking storage tier mounts..."
declare -A TIER_MOUNTS=(
  [node-02]="/mnt/nvme"
  [node-03]="/mnt/ssd"
  [node-04]="/mnt/hdd"
  [node-05]="/mnt/archive"
)
for node in "${!TIER_MOUNTS[@]}"; do
  mount="${TIER_MOUNTS[$node]}"
  ssh "$node" "mountpoint -q $mount" \
    && echo "  $node:$mount OK" \
    || { echo "ERROR: $node:$mount not mounted"; exit 1; }
done

# 3. Create rollback point before migrations
echo "[3/7] Creating rollback point..."
CURRENT_REV=$(alembic current 2>&1 | grep -oE '[a-f0-9]{12}' | head -1)
python3 - << 'PYEOF'
from app.db.session import get_db_context
from app.services.rollback_service import RollbackService
import os
with get_db_context() as db:
    svc = RollbackService(db)
    svc.create_rollback_point(
        label="pre_phase4",
        migration_revision=os.environ.get("CURRENT_REV", "014"),
        deployed_by="deploy_phase4.sh"
    )
PYEOF
echo "  Rollback point created"

# 4. Run Alembic migrations 015–019
echo "[4/7] Running database migrations 015–019..."
alembic upgrade 015
alembic upgrade 016
alembic upgrade 017
alembic upgrade 018
alembic upgrade 019
echo "  Migrations complete"

# 5. Deploy SeaweedFS cluster via Docker Compose
echo "[5/7] Starting SeaweedFS cluster..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_P4" up -d \
  seaweedfs-master seaweedfs-filer \
  seaweedfs-volume-hot seaweedfs-volume-warm \
  seaweedfs-volume-cold seaweedfs-volume-archive

echo "  Waiting for SeaweedFS master health..."
for i in $(seq 1 30); do
  if curl -sf http://node-01:9333/cluster/status > /dev/null 2>&1; then
    echo "  SeaweedFS master ready (${i}s)"
    break
  fi
  sleep 2
done

# 6. Start Phase 4 services
echo "[6/7] Starting Celery Beat and ops worker..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_P4" up -d \
  celery-beat celery-worker-ops

# 7. Seed default retention policies and quotas
echo "[7/7] Seeding Phase 4 configuration..."
python3 scripts/seed_phase4_config.py

echo ""
echo "=== Phase 4 deploy complete ==="
echo "  Run: bash scripts/validate_phase4.sh"
echo "  SeaweedFS UI: http://node-01:9333/"
echo "  Filer:        http://node-01:8888/"
echo "  Grafana:      http://node-01:3000/ (import dashboards from grafana/)"
