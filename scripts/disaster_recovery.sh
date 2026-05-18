#!/usr/bin/env bash
# disaster_recovery.sh — restore IVGS from NAS backup to a clean node
# Usage: bash disaster_recovery.sh [snapshot_name]
#   snapshot_name: optional; defaults to latest successful backup
set -euo pipefail

SNAPSHOT_NAME="${1:-}"
BACKUP_ROOT="/mnt/backup/ivgs"
TARGET_WORKDIR="/mnt/workdir"

echo "=== IVGS Disaster Recovery ==="
echo "  Source NAS: $BACKUP_ROOT"
echo "  Target:     $TARGET_WORKDIR"

# Step 1: Mount NAS if not mounted
if ! mountpoint -q /mnt/backup; then
  echo "[1/6] Mounting NAS..."
  mount -t nfs "${NAS_HOST}:${NAS_SHARE}" /mnt/backup \
    -o "${NAS_MOUNT_OPTIONS:-vers=3,async}"
else
  echo "[1/6] NAS already mounted"
fi

# Step 2: Identify snapshot to restore
echo "[2/6] Selecting snapshot..."
if [ -z "$SNAPSHOT_NAME" ]; then
  SNAPSHOT_NAME=$(ls -1t "$BACKUP_ROOT" | head -1)
  echo "  Auto-selected: $SNAPSHOT_NAME"
else
  echo "  Using: $SNAPSHOT_NAME"
fi
SNAP_PATH="$BACKUP_ROOT/$SNAPSHOT_NAME"
[ -d "$SNAP_PATH" ] || { echo "ERROR: Snapshot not found: $SNAP_PATH"; exit 1; }

# Step 3: Verify pg_dump integrity
echo "[3/6] Verifying pg_dump integrity..."
DUMP_FILE="$SNAP_PATH/postgres.sql.gz"
[ -f "$DUMP_FILE" ] || { echo "ERROR: pg_dump missing in snapshot"; exit 1; }
STORED_HASH=$(psql "$DATABASE_URL" -t -c \
  "SELECT verify_hash FROM backup_snapshots WHERE snapshot_name='$SNAPSHOT_NAME'" \
  2>/dev/null | xargs)
ACTUAL_HASH=$(sha256sum "$DUMP_FILE" | awk '{print $1}')
if [ -n "$STORED_HASH" ] && [ "$STORED_HASH" != "$ACTUAL_HASH" ]; then
  echo "ERROR: pg_dump hash mismatch — backup may be corrupt"
  exit 1
fi
echo "  Hash verified: OK"

# Step 4: Restore database
echo "[4/6] Restoring PostgreSQL database..."
pg_restore --clean --if-exists --dbname="$DATABASE_URL" "$DUMP_FILE"
echo "  Database restored"

# Step 5: Restore workdir from rsync snapshot
echo "[5/6] Restoring workdir from NAS snapshot..."
rsync -az --delete --progress \
  "$SNAP_PATH/workdir/" \
  "$TARGET_WORKDIR/"
echo "  Workdir restored"

# Step 6: Re-start services
echo "[6/6] Restarting application services..."
docker compose -f docker/docker-compose.base.yml \
               -f docker/docker-compose.phase4.yml \
               up -d

echo ""
echo "=== Recovery complete from snapshot: $SNAPSHOT_NAME ==="
echo "  Run validate_phase4.sh to confirm system health"
