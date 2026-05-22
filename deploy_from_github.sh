#!/usr/bin/env bash
###############################################################################
# IVGS v5 Node-01 Deployment Script
# -----------------------------------
# Pulls the fix branch from GitHub, rebuilds the ivgs-workers image, and
# restarts the affected Celery services on node-01.
#
# Prerequisites:
#   - Run this script ON node-01 (192.168.1.71)
#   - Git credentials configured (SSH key or token) for the repo
#   - Docker & Docker Compose installed and operational
#   - Current working directory should be /opt/ivgs (the repo root)
#
# Usage:
#   chmod +x deploy_from_github.sh
#   cd /opt/ivgs
#   ./deploy_from_github.sh          # default: deploy fix branch
#   SKIP_BUILD=1 ./deploy_from_github.sh  # skip Docker build (image exists)
###############################################################################
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_ROOT="${REPO_ROOT:-/opt/ivgs}"
BRANCH="fix/add-worker-models-task-result"
WORKERS_IMAGE="ivgs-workers:v5.1.0"
COMPOSE_FILE="ivgs-infra/docker-compose.node01.yml"
ENV_FILE=".env.node01"
CELERY_SERVICES="celery-worker-default celery-beat"
SKIP_BUILD="${SKIP_BUILD:-0}"
LOG_FILE="/tmp/ivgs_deploy_$(date +%Y%m%d_%H%M%S).log"

# ── Colours & helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*" | tee -a "$LOG_FILE"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*" | tee -a "$LOG_FILE"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*" | tee -a "$LOG_FILE"; exit 1; }

# ── Pre-flight checks ────────────────────────────────────────────────────────
info "=== IVGS v5 Node-01 Deployment — $(date) ==="
info "Log file: $LOG_FILE"

cd "$REPO_ROOT" || fail "Cannot cd to $REPO_ROOT — is the repo cloned?"

command -v git          >/dev/null 2>&1 || fail "git not found"
command -v docker       >/dev/null 2>&1 || fail "docker not found"
command -v docker compose >/dev/null 2>&1 && COMPOSE_CMD="docker compose" || {
    command -v docker-compose >/dev/null 2>&1 && COMPOSE_CMD="docker-compose" || \
        fail "Neither 'docker compose' nor 'docker-compose' found"
}
info "Using compose command: $COMPOSE_CMD"

[ -f "$COMPOSE_FILE" ] || fail "Compose file not found: $COMPOSE_FILE"

# ── Phase 1: Git — fetch & checkout ──────────────────────────────────────────
info "Phase 1/5: Fetching latest from origin..."
git fetch origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"

CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    info "Checking out $BRANCH (currently on $CURRENT_BRANCH)..."
    git checkout "$BRANCH" 2>&1 | tee -a "$LOG_FILE"
fi

info "Pulling latest changes..."
git pull origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"

COMMIT=$(git rev-parse --short HEAD)
info "Now at commit $COMMIT on branch $BRANCH"

# ── Phase 2: Verify critical files ──────────────────────────────────────────
info "Phase 2/5: Verifying critical fix files exist..."
CRITICAL_FILES=(
    "ivgs-workers/models/task_result.py"
    "ivgs-workers/models/__init__.py"
    "ivgs-workers/clients/vllm_client.py"
    "ivgs-workers/Dockerfile"
    "ivgs-workers/requirements.txt"
    "$COMPOSE_FILE"
)
ALL_OK=true
for f in "${CRITICAL_FILES[@]}"; do
    if [ -f "$f" ]; then
        info "  ✅ $f"
    else
        warn "  ❌ MISSING: $f"
        ALL_OK=false
    fi
done
$ALL_OK || fail "Critical files missing — aborting. Check branch contents."

# Quick sanity: Dockerfile should reference celery_app, not ivgs.celery_app
if grep -q "ivgs\.celery_app" ivgs-workers/Dockerfile; then
    fail "Dockerfile still contains 'ivgs.celery_app' — fix was not applied!"
fi
if grep -q "\-A celery_app" ivgs-workers/Dockerfile; then
    info "  ✅ Dockerfile uses correct '-A celery_app'"
else
    warn "  ⚠️  Dockerfile may not contain '-A celery_app' — please verify manually"
fi

# ── Phase 3: Docker build ───────────────────────────────────────────────────
if [ "$SKIP_BUILD" = "1" ]; then
    warn "Phase 3/5: SKIP_BUILD=1 — skipping Docker image build"
else
    info "Phase 3/5: Building $WORKERS_IMAGE (context: $REPO_ROOT)..."
    info "  ⚠️  Build context MUST be repo root (not ivgs-workers/) for COPY shared/ to work"
    docker build \
        -f ivgs-workers/Dockerfile \
        -t "$WORKERS_IMAGE" \
        --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --build-arg VCS_REF="$COMMIT" \
        . 2>&1 | tee -a "$LOG_FILE"

    if docker image inspect "$WORKERS_IMAGE" >/dev/null 2>&1; then
        info "  ✅ Image $WORKERS_IMAGE built successfully"
    else
        fail "Image build appeared to succeed but image not found!"
    fi
fi

# ── Phase 4: Restart Celery services ────────────────────────────────────────
info "Phase 4/5: Restarting Celery services..."

# Stop existing containers first (graceful)
$COMPOSE_CMD -f "$COMPOSE_FILE" --env-file "$ENV_FILE" stop $CELERY_SERVICES 2>&1 | tee -a "$LOG_FILE" || true

# Remove old containers
$COMPOSE_CMD -f "$COMPOSE_FILE" --env-file "$ENV_FILE" rm -f $CELERY_SERVICES 2>&1 | tee -a "$LOG_FILE" || true

# Start fresh
$COMPOSE_CMD -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d $CELERY_SERVICES 2>&1 | tee -a "$LOG_FILE"

info "Waiting 15s for services to initialise..."
sleep 15

# ── Phase 5: Health checks ─────────────────────────────────────────────────
info "Phase 5/5: Running health checks..."

HEALTHY=true
for svc in $CELERY_SERVICES; do
    STATUS=$($COMPOSE_CMD -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps --format '{{.State}}' "$svc" 2>/dev/null || echo "unknown")
    if echo "$STATUS" | grep -qi "running\|up"; then
        info "  ✅ $svc — $STATUS"
    else
        warn "  ❌ $svc — $STATUS"
        HEALTHY=false
    fi
done

# Check container logs for import errors
info "Checking last 30 lines of celery-worker-default logs for errors..."
WORKER_LOGS=$($COMPOSE_CMD -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=30 celery-worker-default 2>&1)
echo "$WORKER_LOGS" | tee -a "$LOG_FILE"

if echo "$WORKER_LOGS" | grep -qi "ModuleNotFoundError\|ImportError\|No module named"; then
    warn "  ⚠️  Import errors detected in worker logs — check module paths!"
    HEALTHY=false
elif echo "$WORKER_LOGS" | grep -qi "celery@.*ready\|mingle: all alone\|connected to redis"; then
    info "  ✅ Worker appears to have started successfully"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
info "═══════════════════════════════════════════════════"
if $HEALTHY; then
    info "  ✅  DEPLOYMENT SUCCESSFUL"
else
    warn "  ⚠️   DEPLOYMENT COMPLETED WITH WARNINGS"
    warn "  Review the log file: $LOG_FILE"
    warn "  Check: $COMPOSE_CMD -f $COMPOSE_FILE --env-file $ENV_FILE logs -f $CELERY_SERVICES"
fi
info "  Branch:  $BRANCH"
info "  Commit:  $COMMIT"
info "  Image:   $WORKERS_IMAGE"
info "  Log:     $LOG_FILE"
info "═══════════════════════════════════════════════════"

# ── Optional: Celery inspect (requires celery CLI in container) ─────────────
info ""
info "Post-deploy verification commands (run manually if needed):"
info "  # Check Celery worker registered tasks:"
info "  docker exec \$(docker ps -qf name=celery-worker-default) celery -A celery_app inspect registered"
info ""
info "  # Check Celery beat schedule:"
info "  docker exec \$(docker ps -qf name=celery-beat) celery -A celery_app inspect scheduled"
info ""
info "  # Tail logs in real-time:"
info "  $COMPOSE_CMD -f $COMPOSE_FILE --env-file $ENV_FILE logs -f $CELERY_SERVICES"
