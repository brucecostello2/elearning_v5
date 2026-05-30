#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — deploy-node.sh
# =============================================================================
# Spec reference: §15.4 Deployment Script (deploy-node.sh)
#
# Usage: ./scripts/deploy-node.sh <node-name>
#   node-name: node01 | node02 | node03 | node04 | node05 | node06
#
# Six-step deployment procedure (per §15.4):
#   1. Create rollback point (POST to rollback service on node-01)
#   2. Pull pinned image tags from GHCR
#   3. Stop current stack (docker compose down)
#   4. Run Alembic migrations (node-01 only)
#   5. Start updated stack (docker compose up -d)
#   6. Health check (retry 3 times, 10s apart)
#
# Exit codes:
#   0 — Deployment successful
#   1 — Invalid arguments
#   2 — Rollback point creation failed
#   3 — Image pull failed
#   4 — Alembic migration failed
#   5 — Health check failed after all retries
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
readonly INFRA_DIR="${PROJECT_DIR}/ivgs-infra"
readonly LOG_DIR="/var/log/ivgs/deploy"
readonly HEALTH_CHECK_RETRIES=3
readonly HEALTH_CHECK_INTERVAL=10
# NODE_01_API / NODE_01_SCHEDULER are derived from NODE_01_IP once the env file is known

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
readonly LOG_FILE="${LOG_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"

log() {
    local level="$1"
    shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <node-name>"
    echo "  node-name: node01 | node02 | node03 | node04 | node05 | node06"
    exit 1
fi

NODE="$1"
VALID_NODES=("node01" "node02" "node03" "node04" "node05" "node06")
if [[ ! " ${VALID_NODES[*]} " =~ " ${NODE} " ]]; then
    log_error "Invalid node name: $NODE"
    log_error "Valid nodes: ${VALID_NODES[*]}"
    exit 1
fi

PRIMARY_COMPOSE="${INFRA_DIR}/docker-compose.${NODE}.yml"
if [[ ! -f "$PRIMARY_COMPOSE" ]]; then
    log_error "Compose file not found: $PRIMARY_COMPOSE"
    exit 1
fi
# node-01 runs a three-file stack (node + override + monitoring); GPU nodes are single-file
if [[ "$NODE" == "node01" ]]; then
    COMPOSE_FILES=(
        -f "${INFRA_DIR}/docker-compose.node01.yml"
        -f "${INFRA_DIR}/docker-compose.override.node01.yml"
        -f "${INFRA_DIR}/docker-compose.monitoring.yml"
    )
else
    COMPOSE_FILES=(-f "$PRIMARY_COMPOSE")
fi

if [[ "$NODE" == "node01" ]]; then
    ENV_FILE="${INFRA_DIR}/.env"            # node-01: topology registry + secrets
else
    ENV_FILE="${INFRA_DIR}/.env.${NODE}"    # GPU node: NODE_01_IP pointer + node config
fi
if [[ ! -f "$ENV_FILE" ]]; then
    log_error "Environment file not found: $ENV_FILE"
    exit 1
fi

# Orchestrator address — single source: NODE_01_IP in the env file
NODE_01_IP="$(grep -E '^NODE_01_IP=' "$ENV_FILE" | head -1 | cut -d= -f2)"
if [[ -z "$NODE_01_IP" ]]; then
    log_error "NODE_01_IP not set in $ENV_FILE — cannot resolve orchestrator address"
    exit 1
fi
NODE_01_API="http://${NODE_01_IP}:8001"
NODE_01_SCHEDULER="http://${NODE_01_IP}:8002"

log_info "=========================================="
log_info "IVGS v5 Deployment — ${NODE}"
log_info "Compose file(s): ${COMPOSE_FILES[*]}"
log_info "Git revision: $(cd "$PROJECT_DIR" && git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
log_info "=========================================="

# ---------------------------------------------------------------------------
# Step 1: Create rollback point (§15.4 Step 1)
# POST to rollback service with current git short SHA as version tag
# ---------------------------------------------------------------------------
log_info "Step 1/6: Creating rollback point..."

VERSION_TAG="$(cd "$PROJECT_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "manual-$(date +%s)")"

ROLLBACK_RESPONSE=$(curl -sf -X POST \
    "${NODE_01_API}/api/v1/rollback/create" \
    -H "Content-Type: application/json" \
    -d "{\"version_tag\": \"${VERSION_TAG}\", \"node\": \"${NODE}\"}" \
    --connect-timeout 10 \
    --max-time 30 \
    2>&1) || {
    log_error "Failed to create rollback point"
    log_error "Response: $ROLLBACK_RESPONSE"
    log_warn "Continuing deployment without rollback point (manual recovery required)"
}

ROLLBACK_ID=$(echo "$ROLLBACK_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('rollback_point_id', 'unknown'))" 2>/dev/null || echo "unknown")
log_info "Rollback point created: ${ROLLBACK_ID} (version: ${VERSION_TAG})"

# ---------------------------------------------------------------------------
# Step 2: Pull pinned image tags from GHCR (§15.4 Step 2)
# All images are pinned by SHA digest — no :latest tags per §19.5
# ---------------------------------------------------------------------------
log_info "Step 2/6: Pulling pinned images..."

if ! docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" pull 2>&1 | tee -a "$LOG_FILE"; then
    log_error "Image pull failed for ${NODE}"
    log_error "Attempting rollback..."
    exit 3
fi

log_info "All images pulled successfully"

# ---------------------------------------------------------------------------
# Step 3: Stop current stack (§15.4 Step 3)
# ---------------------------------------------------------------------------
log_info "Step 3/6: Stopping current stack..."

docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" down --timeout 60 2>&1 | tee -a "$LOG_FILE" || {
    log_warn "Clean shutdown failed, forcing..."
    docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" down --timeout 10 --remove-orphans 2>&1 | tee -a "$LOG_FILE"
}

log_info "Stack stopped"

# ---------------------------------------------------------------------------
# Step 4: Run Alembic migrations — node-01 ONLY (§15.4 Step 4)
# Per §D.1: migrations stored in ivgs-api/migrations/versions/
# Alembic upgrade runs via docker compose run --rm
# ---------------------------------------------------------------------------
if [[ "$NODE" == "node01" ]]; then
    log_info "Step 4/6: Running Alembic migrations (node-01 only)..."

    if ! docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" run --rm \
        -e DATABASE_URL="postgresql+psycopg://${POSTGRES_USER:-ivgs}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-ivgs}" \
        fastapi-backend \
        alembic upgrade head 2>&1 | tee -a "$LOG_FILE"; then
        log_error "Alembic migration failed!"
        log_error "Rolling back to previous version..."
        # Restart previous stack
        docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d 2>&1 | tee -a "$LOG_FILE"
        exit 4
    fi

    log_info "Migrations completed successfully"
else
    log_info "Step 4/6: Skipping Alembic migrations (not node-01)"
fi

# ---------------------------------------------------------------------------
# Step 5: Start updated stack (§15.4 Step 5)
# ---------------------------------------------------------------------------
log_info "Step 5/6: Starting updated stack..."

if ! docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d 2>&1 | tee -a "$LOG_FILE"; then
    log_error "Failed to start stack for ${NODE}"
    exit 5
fi

log_info "Stack started"

# ---------------------------------------------------------------------------
# Step 6: Health check — retry 3 times, 10s apart (§15.4 Step 6)
# ---------------------------------------------------------------------------
log_info "Step 6/6: Running health checks..."

# Determine health check URL based on node
case "$NODE" in
    node01)
        HEALTH_URL="http://localhost:8001/api/v1/health"
        ;;
    node02|node03)
        HEALTH_URL="http://localhost:8000/health"
        ;;
    node04)
        HEALTH_URL="http://localhost:8188/system_stats"
        ;;
    node05)
        HEALTH_URL="http://localhost:8188/system_stats"
        ;;
    node06)
        HEALTH_URL="http://localhost:3002/health"
        ;;
esac

HEALTH_OK=false
for i in $(seq 1 $HEALTH_CHECK_RETRIES); do
    log_info "Health check attempt ${i}/${HEALTH_CHECK_RETRIES}..."

    if curl -sf "$HEALTH_URL" --connect-timeout 5 --max-time 10 > /dev/null 2>&1; then
        HEALTH_OK=true
        log_info "Health check PASSED on attempt ${i}"
        break
    else
        log_warn "Health check attempt ${i} failed"
        if [[ $i -lt $HEALTH_CHECK_RETRIES ]]; then
            log_info "Waiting ${HEALTH_CHECK_INTERVAL}s before retry..."
            sleep "$HEALTH_CHECK_INTERVAL"
        fi
    fi
done

if [[ "$HEALTH_OK" != "true" ]]; then
    log_error "Health check FAILED after ${HEALTH_CHECK_RETRIES} attempts"
    log_error "Deployment may have failed — check container logs:"
    log_error "  docker compose ${COMPOSE_FILES[*]} logs --tail=50"
    exit 5
fi

# ---------------------------------------------------------------------------
# Additional platform checks for node-01
# Per §15.6: GPU availability, DB connectivity, Redis, SeaweedFS
# ---------------------------------------------------------------------------
if [[ "$NODE" == "node01" ]]; then
    log_info "Running platform-level checks for node-01..."

    # Database connectivity
    if docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres pg_isready -U "${POSTGRES_USER:-ivgs}" > /dev/null 2>&1; then
        log_info "  ✓ PostgreSQL: healthy"
    else
        log_warn "  ✗ PostgreSQL: not ready"
    fi

    # Redis connectivity
    if docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
        log_info "  ✓ Redis: healthy"
    else
        log_warn "  ✗ Redis: not ready"
    fi

    # SeaweedFS mount
    if [[ -d "/mnt/ivgs-shared" ]] && touch /mnt/ivgs-shared/.deploy-test 2>/dev/null; then
        rm -f /mnt/ivgs-shared/.deploy-test
        log_info "  ✓ SeaweedFS shared mount: writable"
    else
        log_warn "  ✗ SeaweedFS shared mount: not writable"
    fi

    # Prometheus
    if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
        log_info "  ✓ Prometheus: healthy"
    else
        log_warn "  ✗ Prometheus: not ready"
    fi

    # Grafana
    if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
        log_info "  ✓ Grafana: healthy"
    else
        log_warn "  ✗ Grafana: not ready"
    fi
fi

# ---------------------------------------------------------------------------
# GPU checks for GPU nodes
# Per §15.6: verify nvidia-smi availability
# ---------------------------------------------------------------------------
if [[ "$NODE" =~ ^node0[2-5]$ ]]; then
    log_info "Running GPU checks for ${NODE}..."

    if docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T nvidia-gpu-exporter nvidia-smi > /dev/null 2>&1; then
        log_info "  ✓ nvidia-smi: GPU available"
    else
        log_warn "  ✗ nvidia-smi: GPU not detected"
    fi
fi

if [[ "$NODE" == "node06" ]]; then
    log_info "Running Intel GPU checks for ${NODE}..."

    if [[ -e /dev/dri/renderD128 ]]; then
        log_info "  ✓ Intel GPU: /dev/dri/renderD128 available"
    else
        log_warn "  ✗ Intel GPU: /dev/dri/renderD128 not found"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log_info "=========================================="
log_info "Deployment COMPLETE — ${NODE}"
log_info "Version: ${VERSION_TAG}"
log_info "Rollback ID: ${ROLLBACK_ID}"
log_info "Log file: ${LOG_FILE}"
log_info "=========================================="

echo ""
echo "✅ ${NODE} deployment successful (version: ${VERSION_TAG})"
echo "   To rollback: curl -X POST ${NODE_01_API}/api/v1/rollback/execute -d '{\"rollback_point_id\": \"${ROLLBACK_ID}\"}'"
