#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="/var/log/ivgs/deploy_phase3_$(date +%Y%m%d_%H%M%S).log"

mkdir -p /var/log/ivgs
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== IVGS v4 Phase 3 Deployment ==="
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Host: $(hostname)"

# -- 0. Verify Phase 2 prerequisite --------------------------------
echo "[0/7] Verifying Phase 2 deployment..."
if ! docker ps --filter "name=ivgs-api" --filter "status=running" -q | grep -q .; then
  echo "ERROR: ivgs-api container not running. Deploy Phase 2 first."
  exit 1
fi
echo "  Phase 2: OK"

# -- 1. Download AI model weights ----------------------------------
echo "[1/7] Checking AI model weights..."
if [[ -n "${COGVIDEOX_MODEL_PATH:-}" && ! -d "${COGVIDEOX_MODEL_PATH}" ]]; then
  echo "  Downloading CogVideoX model weights..."
  bash "${SCRIPT_DIR}/download_models.sh" cogvideox
fi
if [[ -n "${WAN21_MODEL_PATH:-}" && ! -d "${WAN21_MODEL_PATH}" ]]; then
  echo "  Downloading Wan2.1 model weights..."
  bash "${SCRIPT_DIR}/download_models.sh" wan21
fi
if [[ -n "${SYNCNET_MODEL_PATH:-}" && ! -f "${SYNCNET_MODEL_PATH}" ]]; then
  echo "  Downloading SyncNet weights..."
  bash "${SCRIPT_DIR}/download_models.sh" syncnet
fi
echo "  Model weights: OK"

# -- 2. Run Alembic migrations 011–014 ----------------------------
echo "[2/7] Running database migrations 011–014..."
docker exec ivgs-api \
  alembic -c /app/alembic.ini upgrade 011_ai_video_generation
docker exec ivgs-api \
  alembic -c /app/alembic.ini upgrade 012_localization
docker exec ivgs-api \
  alembic -c /app/alembic.ini upgrade 013_lip_sync_scores
docker exec ivgs-api \
  alembic -c /app/alembic.ini upgrade 014_caption_alignment
echo "  Migrations: OK"

# -- 3. Build and deploy Remotion service -------------------------
echo "[3/7] Building and deploying Remotion service..."
cd "${PROJECT_ROOT}"
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase2.yml \
  
  -f infra/docker-compose.phase3.yml \
  build ivgs-remotion
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase2.yml \
  -f infra/docker-compose.phase3.yml \
  up -d ivgs-remotion
echo "  Remotion service: OK"

# -- 4. Deploy MFA service -----------------------------------------
echo "[4/7] Deploying Montreal Forced Aligner service..."
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase2.yml \
  -f infra/docker-compose.phase3.yml \
  up -d ivgs-mfa

# Wait for MFA to be ready (downloads pretrained models on first run)
echo "  Waiting for MFA to initialise (may take 2-5 min on first run)..."
for i in $(seq 1 30); do
  if docker exec ivgs-mfa mfa version >/dev/null 2>&1; then
    echo "  MFA: OK"
    break
  fi
  sleep 10
done

# -- 5. Restart GPU workers with Phase 3 env ----------------------
echo "[5/7] Restarting GPU workers with Phase 3 model support..."
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase2.yml \
  -f infra/docker-compose.phase3.yml \
  up -d --force-recreate ivgs-worker-gpu

# Wait for workers to reconnect
sleep 20
WORKER_COUNT=$(celery -A ivgs_workers.celeryconfig inspect active_queues \
  --timeout=10 2>/dev/null | grep -c "gpu_video" || echo "0")
echo "  GPU workers with gpu_video queue: ${WORKER_COUNT}"

# -- 6. Restart API with Phase 3 env vars -------------------------
echo "[6/7] Restarting API service..."
docker compose \
  -f infra/docker-compose.base.yml \
  -f infra/docker-compose.phase2.yml \
  -f infra/docker-compose.phase3.yml \
  up -d --force-recreate ivgs-api
sleep 10

# -- 7. Run smoke validation ---------------------------------------
echo "[7/7] Running Phase 3 validation..."
bash "${SCRIPT_DIR}/validate_phase3.sh"

echo ""
echo "=== Phase 3 Deployment Complete ==="
echo "Log: ${LOG_FILE}"
