#!/usr/bin/env bash
# =============================================================================
# check_seed_conformance.sh — the seed templates baked into an image must equal
# the seed templates in the tree at the commit that built it.
# =============================================================================
# WP-62 Task 8(e).
#
# WHY THIS EXISTS, and it is not the reason it was asked for.
#
# WP-62 was told the image's baked `translation.j2` differed from the tracked
# one — container `205ddaba…` against tracked `67be5991…` — and asked to find
# the build-context / .dockerignore / stale-layer cause. Measured on the
# running stack 2026-08-26: THERE IS NO DIVERGENCE.
# `sha256sum /app/seed/default_prompts/translation.j2` inside `ivgs-fastapi`
# (`ivgs-api:v5.20.0-qwen`) returns `67be5991ad4819…`, byte-identical to the
# tree. `205ddaba…` is the sha of the SAME BYTES WITH THE TRAILING NEWLINE
# STRIPPED, which is what `app/scripts/wp61_publish_prompt.py` computes and
# printed under the label `sha256`. Two digests, two byte strings, one label.
# That half is fixed in the script.
#
# This script is the other half, and it is the half that matters going forward:
# nothing anywhere compared the baked seed with the tracked seed, so a
# genuinely divergent one WOULD have shipped silently, and the only reason it
# had not is that nobody had changed a template since the last build. A
# template that reaches the prompts table is a contract — `TranslationService`
# REFUSES to run under a prompt that does not carry the fail-and-flag marker —
# so shipping a stale one is not a cosmetic drift.
#
# IT COMPARES FILE BYTES, NOT STRIPPED TEXT. `sha256sum` on both sides, so the
# two numbers this script prints are the two numbers a human gets by running
# `sha256sum` themselves. Introducing a third normalisation here would be the
# original defect again.
#
# USAGE
#   scripts/check_seed_conformance.sh [IMAGE]
#     IMAGE defaults to the image the running ivgs-fastapi container was
#     created from, read with `docker inspect` — never from a *_TAG variable
#     inside the container, which dev/CLAUDE.md §6 records as always stale.
#
# EXIT
#   0  every tracked seed template matches the baked one
#   1  at least one differs, or is missing on one side (each named)
#   2  the image could not be read at all
# =============================================================================
set -uo pipefail

SEED_DIR_REL="ivgs-api/seed/default_prompts"
SEED_DIR_IMG="/app/seed/default_prompts"

# Find the repo root from this script's location, tolerating a process
# substitution (`. <(...)`) where BASH_SOURCE is /dev/fd/NN — the trap WP-60
# recorded after nine tests died on `dirname "${BASH_SOURCE[0]}"`.
_self="${BASH_SOURCE[0]:-$0}"
if [ -f "$_self" ]; then
  REPO="$(cd "$(dirname "$_self")/.." && pwd)"
else
  REPO="$(pwd)"
fi

IMAGE="${1:-}"
if [ -z "$IMAGE" ]; then
  IMAGE="$(docker inspect ivgs-fastapi --format '{{.Config.Image}}' 2>/dev/null)"
fi
if [ -z "$IMAGE" ]; then
  echo "ABORT: no image given and ivgs-fastapi is not running."
  echo "       usage: scripts/check_seed_conformance.sh <image>"
  exit 2
fi

if [ ! -d "$REPO/$SEED_DIR_REL" ]; then
  echo "ABORT: $REPO/$SEED_DIR_REL does not exist."
  exit 2
fi

echo "image : $IMAGE"
echo "tree  : $REPO/$SEED_DIR_REL"
echo

BAKED="$(docker run --rm --entrypoint sh "$IMAGE" -c \
          "cd $SEED_DIR_IMG 2>/dev/null && sha256sum *.j2" 2>/dev/null)"
if [ -z "$BAKED" ]; then
  echo "ABORT: could not read $SEED_DIR_IMG from $IMAGE."
  echo "       Either the image has no seed directory or it could not be run."
  exit 2
fi

rc=0
for path in "$REPO/$SEED_DIR_REL"/*.j2; do
  name="$(basename "$path")"
  tracked="$(sha256sum "$path" | cut -d' ' -f1)"
  baked="$(printf '%s\n' "$BAKED" | awk -v n="$name" '$2 == n {print $1}')"
  if [ -z "$baked" ]; then
    echo "MISSING IN IMAGE  $name"
    echo "                  tracked $tracked"
    rc=1
  elif [ "$tracked" != "$baked" ]; then
    echo "DIVERGED          $name"
    echo "                  tracked $tracked"
    echo "                  baked   $baked"
    rc=1
  else
    echo "ok                $name  $tracked"
  fi
done

# The other direction. A template deleted from the tree but still baked in is
# also a divergence, and it is the one that survives a one-way check.
while read -r baked name; do
  [ -n "$name" ] || continue
  if [ ! -f "$REPO/$SEED_DIR_REL/$name" ]; then
    echo "EXTRA IN IMAGE    $name  $baked"
    echo "                  present in the image, absent from the tree"
    rc=1
  fi
done <<< "$BAKED"

echo
if [ $rc -eq 0 ]; then
  echo "PASS: every baked seed template is byte-identical to the tracked one."
else
  echo "FAIL: the image's seed templates are not the tracked ones."
  echo "      Rebuild before deploying. A prompt published from a stale"
  echo "      template is a contract change nobody made."
fi
exit $rc
