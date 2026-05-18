#!/usr/bin/env bash
# deploy_phase1.sh — IVGS Phase 1 deployment automation
# Usage: ./scripts/deploy_phase1.sh [--env .env.phase1] [--skip-build]
# Exit codes: 0 = success, 1 = preflight failure, 2 = migration failure,
#             3 = build/push failure, 4 = deploy failure, 5 = healthcheck failure

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
ENV_FILE="${1:-.env.phase1}"
SKIP_BUILD="${SKIP_BUILD:-false}"
NODES=(node-02 node-03 node-04 node-05 node-06)
SSH_USER="${SSH_USER:-ivgs}"
REGISTRY="${REGISTRY:-ghcr.io/ivgs}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SCHEDULER_HEALTH_URL="http://node-01:8001/health"
MIGRATION_RETRIES=3

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit "${2:-1}"; }

# ── Load environment ──────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    die "Environment file '$ENV_FILE' not found. Copy from configs/.env.phase1.template" 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
log "Loaded environment from $ENV_FILE"

# ── Preflight checks ──────────────────────────────────────────────────────────
log "Running preflight checks..."
command -v docker   >/dev/null 2>&1 || die "docker not found" 1
command -v ssh      >/dev/null 2>&1 || die "ssh not found" 1
command -v alembic  >/dev/null 2>&1 || die "alembic not found (activate venv?)" 1

# Verify node connectivity
for node in "${NODES[@]}"; do
    ssh -o ConnectTimeout=5 -o BatchMode=yes "${SSH_USER}@${node}" true \
        || die "Cannot SSH to ${node}" 1
done
log "All ${#NODES[@]} worker nodes reachable"

# ── Database migrations ───────────────────────────────────────────────────────
log "Running Alembic migrations (attempt up to ${MIGRATION_RETRIES}x)..."
for attempt in $(seq 1 "$MIGRATION_RETRIES"); do
    if alembic -c alembic/alembic.ini upgrade head; then
        log "Migrations complete"
        break
    fi
    if [[ "$attempt" -eq "$MIGRATION_RETRIES" ]]; then
        die "Alembic migration failed after ${MIGRATION_RETRIES} attempts" 2
    fi
    log "Migration attempt ${attempt} failed, retrying in 10s..."
    sleep 10
done

# ── Build and push Docker images ──────────────────────────────────────────────
if [[ "$SKIP_BUILD" != "true" ]]; then
    log "Building and pushing images (tag: ${IMAGE_TAG})..."

    docker build -f infra/docker/Dockerfile.api \
        -t "${REGISTRY}/ivgs-api:${IMAGE_TAG}" \
        -t "${REGISTRY}/ivgs-api:latest" . \
        || die "API image build failed" 3

    docker build -f infra/docker/Dockerfile.scheduler \
        -t "${REGISTRY}/ivgs-scheduler:${IMAGE_TAG}" \
        -t "${REGISTRY}/ivgs-scheduler:latest" . \
        || die "Scheduler image build failed" 3

    docker push "${REGISTRY}/ivgs-api:${IMAGE_TAG}" \
        || die "API image push failed" 3
    docker push "${REGISTRY}/ivgs-scheduler:${IMAGE_TAG}" \
        || die "Scheduler image push failed" 3

    log "Images pushed: ${REGISTRY}/ivgs-api:${IMAGE_TAG}, ${REGISTRY}/ivgs-scheduler:${IMAGE_TAG}"
else
    log "Skipping build (SKIP_BUILD=true)"
fi

# ── Deploy on node-01 (API + Scheduler) ───────────────────────────────────────
log "Deploying Scheduler + API on node-01..."
docker compose \
    -f docker-compose.yml \
    -f infra/docker-compose.phase1.yml \
    pull ivgs-scheduler ivgs-api ivgs-celery-beat \
    || die "docker compose pull failed on node-01" 4

docker compose \
    -f docker-compose.yml \
    -f infra/docker-compose.phase1.yml \
    up -d --no-deps ivgs-scheduler ivgs-api ivgs-celery-beat \
    || die "docker compose up failed on node-01" 4
log "node-01 updated"

# ── Rolling restart on worker nodes ──────────────────────────────────────────
log "Rolling restart of worker nodes..."
for node in "${NODES[@]}"; do
    log "  Updating ${node}..."
    ssh "${SSH_USER}@${node}" \
        "cd /opt/ivgs && \
         docker compose pull ivgs-worker && \
         docker compose up -d --no-deps ivgs-worker" \
        || die "Worker update failed on ${node}" 4
    sleep 5   # brief pause between nodes for graceful drain
done

# ── Scheduler healthcheck ─────────────────────────────────────────────────────
log "Waiting for GPU Scheduler to become healthy..."
RETRIES=12
for i in $(seq 1 "$RETRIES"); do
    STATUS=$(curl -sf "${SCHEDULER_HEALTH_URL}" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unreachable")
    if [[ "$STATUS" == "healthy" ]]; then
        log "GPU Scheduler is healthy"
        break
    fi
    if [[ "$i" -eq "$RETRIES" ]]; then
        die "GPU Scheduler did not become healthy within $((RETRIES * 10))s — status: ${STATUS}" 5
    fi
    log "  Attempt ${i}/${RETRIES}: ${STATUS}, waiting 10s..."
    sleep 10
done

log "Phase 1 deployment complete. Run scripts/validate_phase1.sh to verify."
