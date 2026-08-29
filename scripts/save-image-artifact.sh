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

# WP-58 Task 4: the derivation moved to scripts/lib/artifact_name.sh so there is
# ONE definition. This script is no longer the only place that knows the name,
# which is what let a hand-rolled `docker save | zstd -o <name>` produce a file
# no deploy path could find (2026-08-25).
# shellcheck source=lib/artifact_name.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/artifact_name.sh"

NAME="$(artifact_name_for "$REF")"

if command -v zstd >/dev/null 2>&1; then
  EXT="tar.zst"; COMP="zstd -T0"; DECOMP="zstd -d -c"
elif command -v pigz >/dev/null 2>&1; then
  EXT="tar.gz"; COMP="pigz"; DECOMP="gunzip -c"
else
  EXT="tar.gz"; COMP="gzip"; DECOMP="gunzip -c"
fi
OUT="$STORE/$NAME.$EXT"

# Registration happens ONLY on an actual save. Before 2026-08-22 the MANIFEST
# append sat outside this guard, so every re-run against an already-banked image
# added a duplicate line -- same path, same digest, new timestamp -- which made
# MANIFEST.txt a poor inventory over time. Ruling of 2026-08-22, P1.4j.
# ⛔ WP-IVGS-12b (RC-Q8). SKIP-IF-PRESENT IS VALID ONLY WHEN PRESENT MEANS SAME
# DIGEST. The name comes from the TAG, so a tag rebuilt mid-session used to skip
# silently and ship the OLD bytes to every remote node -- with DEPLOY VERIFIED
# green on all of them, because that check compares tags. Measured 2026-08-29:
# node-01 on e9c1001a while nodes 02/03/04 ran aa89c778 under one tag.
LOCAL_DIGEST="$(image_local_digest "$REF")"
BANKED_DIGEST="$(artifact_banked_digest "$REF")"
DIGEST_FILE="$(artifact_digest_path_for "$REF")"

if [ -z "$LOCAL_DIGEST" ]; then
  echo "ERROR: this host holds no image for $REF -- nothing to bank." >&2
  exit 1
fi

if [ -s "$OUT" ] && [ -n "$BANKED_DIGEST" ] && [ "$BANKED_DIGEST" != "$LOCAL_DIGEST" ]; then
  {
    echo "REFUSING: $REF names DIFFERENT BYTES than the banked artifact."
    echo "  banked  : $BANKED_DIGEST"
    echo "  local   : $LOCAL_DIGEST"
    echo "  artifact: $OUT"
    echo
    echo "  One tag, two images. Skipping would ship the banked bytes to every"
    echo "  node while this host runs the local ones, and"
    echo "  verify-deployed-image.sh would report DEPLOY VERIFIED for both,"
    echo "  because it compares TAGS. That is RC-Q8 and it cost a session."
    echo
    echo "  Decide which is correct, then either re-tag the new build and bank"
    echo "  that, or:  rm $OUT $OUT.sha256 $DIGEST_FILE  and re-run."
  } >&2
  exit 1
fi

if [ -s "$OUT" ] && [ "$BANKED_DIGEST" = "$LOCAL_DIGEST" ]; then
  echo "artifact already present and DIGEST MATCHES, skipping save: $OUT"
  echo "  image digest: $LOCAL_DIGEST"
  echo "not re-registering: MANIFEST.txt records saves, not invocations"
  if [ -s "$OUT.sha256" ]; then
    echo "to verify it: ( cd $STORE && sha256sum -c $(basename "$OUT").sha256 )"
  else
    echo "WARNING: $OUT.sha256 is missing for an artifact that is present" >&2
  fi
elif [ -s "$OUT" ]; then
  # Present, but no digest was ever recorded. Its provenance CANNOT be proved,
  # and stamping the local digest onto bytes nobody verified would be worse than
  # the bug this replaces -- it would make a lie checkable. So re-save.
  echo "artifact present but its provenance was never recorded (pre-12b);"
  echo "RE-SAVING so the bytes and the digest provably agree."
  echo "saving $REF -> $OUT"
  docker save "$REF" | $COMP > "$OUT"
  sha256sum "$OUT" | tee "$OUT.sha256"
  printf '%s\n' "$LOCAL_DIGEST" > "$DIGEST_FILE"
  echo "recorded image digest: $LOCAL_DIGEST -> $DIGEST_FILE"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  $REF  $OUT  $(du -h "$OUT" | cut -f1)  sha256:$(cut -d' ' -f1 "$OUT.sha256")  image:$LOCAL_DIGEST" >> "$STORE/MANIFEST.txt"
  echo "registered in $STORE/MANIFEST.txt"
else
  echo "saving $REF -> $OUT"
  docker save "$REF" | $COMP > "$OUT"
  sha256sum "$OUT" | tee "$OUT.sha256"
  SIZE="$(du -h "$OUT" | cut -f1)"
  SHA="$(cut -d' ' -f1 "$OUT.sha256")"
  printf '%s\n' "$LOCAL_DIGEST" > "$DIGEST_FILE"
  echo "recorded image digest: $LOCAL_DIGEST -> $DIGEST_FILE"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  $REF  $OUT  $SIZE  sha256:$SHA  image:$LOCAL_DIGEST" >> "$STORE/MANIFEST.txt"
  echo "registered in $STORE/MANIFEST.txt"
fi

echo "restore: $DECOMP $OUT | docker load"
