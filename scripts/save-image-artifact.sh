#!/usr/bin/env bash
# save-image-artifact.sh -- capture a built image to owned storage for recovery.
# NOT a registry push. Usage: sudo scripts/save-image-artifact.sh <image-ref>
# e.g. sudo scripts/save-image-artifact.sh ghcr.io/brucecostello2/ivgs-workers:comfyui-v5.2.7-h0
#
# MUST RUN AS ROOT. The store is root:root drwxr-xr-x, so an unprivileged run
# fails "Permission denied" at the output redirect -- AFTER docker save has
# already begun, which reads like a save failure and is not. Guarded below and
# documented 2026-08-22 after exactly that (WP-DEPLOY-R2-R5-NODE04 section 5).
set -euo pipefail

_PRECHECK="${IVGS_IMAGE_ARTIFACTS:-/mnt/ivgs-shared/image-artifacts}"
if ! mkdir -p "$_PRECHECK" 2>/dev/null || [ ! -w "$_PRECHECK" ]; then
  echo "ERROR: $_PRECHECK is not writable by $(id -un). Re-run with sudo." >&2
  exit 1
fi

REF="${1:?usage: save-image-artifact.sh <image-ref>}"
STORE="${IVGS_IMAGE_ARTIFACTS:-/mnt/ivgs-shared/image-artifacts}"
mkdir -p "$STORE"

NAME="$(echo "$REF" | sed 's#^[^/]*/##; s#[/:]#_#g')"

if command -v zstd >/dev/null 2>&1; then
  EXT="tar.zst"; COMP="zstd -T0"; DECOMP="zstd -d -c"
elif command -v pigz >/dev/null 2>&1; then
  EXT="tar.gz"; COMP="pigz"; DECOMP="gunzip -c"
else
  EXT="tar.gz"; COMP="gzip"; DECOMP="gunzip -c"
fi
OUT="$STORE/$NAME.$EXT"

if [ -s "$OUT" ]; then
  echo "artifact already present, skipping save: $OUT"
else
  echo "saving $REF -> $OUT"
  docker save "$REF" | $COMP > "$OUT"
fi

sha256sum "$OUT" | tee "$OUT.sha256"
SIZE="$(du -h "$OUT" | cut -f1)"
SHA="$(cut -d' ' -f1 "$OUT.sha256")"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  $REF  $OUT  $SIZE  sha256:$SHA" >> "$STORE/MANIFEST.txt"

echo "registered in $STORE/MANIFEST.txt"
echo "restore: $DECOMP $OUT | docker load"
