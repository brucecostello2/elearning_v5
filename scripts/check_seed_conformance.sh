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
# WP-64 EXTENDS IT TO THE WORKERS' STAGE TEMPLATES, and the reason is the
# reason this file exists. WP-64 Task 4(b) amends
# `ivgs-workers/prompts/stage3_system.j2`, which is versioned data exactly as a
# seed prompt is — and NOTHING COMPARED IT TO ANYTHING. It is a different
# artefact from the seed prompts in two ways that matter, and both are stated
# here because the brief assumed otherwise:
#
#   * it ships in the WORKERS image (`/app/prompts`), not the api image, so
#     amending it needs a workers rebuild and a redeploy of every worker;
#   * it never reaches the `prompts` table at all. `stage3_images._load_system_prompt`
#     reads it off disk (`stage3_images.py:177-184`); the `image_generation` row
#     in `prompts` is not what Stage 3 renders.
#
# So a stale baked copy of it would have shipped as silently as a stale seed
# prompt would have, with one fewer place to notice. Same comparison, same two
# directions, second directory.
#
# USAGE
#   scripts/check_seed_conformance.sh [API_IMAGE] [WORKERS_IMAGE]
#     API_IMAGE defaults to the image the running ivgs-fastapi container was
#     created from and WORKERS_IMAGE to the running ivgs-celery-default's, both
#     read with `docker inspect` — never from a *_TAG variable inside the
#     container, which dev/CLAUDE.md §6 records as always stale.
#
#     A directory absent from the tree, or an image that cannot be resolved, is
#     reported as SKIPPED by name and does not fail the run. It also does not
#     pass it: silence is what this script exists to remove.
#
# EXIT
#   0  every tracked template checked matches the baked one
#   1  at least one differs, or is missing on one side (each named)
#   2  no directory could be checked at all
# =============================================================================
set -uo pipefail

SEED_DIR_REL="ivgs-api/seed/default_prompts"
SEED_DIR_IMG="/app/seed/default_prompts"

# WP-64. The workers' stage templates: same kind of artefact, different image.
WORKER_DIR_REL="ivgs-workers/prompts"
WORKER_DIR_IMG="/app/prompts"

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
WORKER_IMAGE="${2:-}"
if [ -z "$WORKER_IMAGE" ]; then
  WORKER_IMAGE="$(docker inspect ivgs-celery-default --format '{{.Config.Image}}' 2>/dev/null)"
fi

rc=0
checked=0

# ---------------------------------------------------------------------------
# One directory, both directions. Bytes on both sides — `sha256sum` is what a
# human would run themselves, and introducing a third normalisation here would
# be the original defect again.
# ---------------------------------------------------------------------------
check_dir() {
  local label="$1" img="$2" rel="$3" imgdir="$4"

  echo "--- $label ---"
  if [ -z "$img" ]; then
    echo "SKIPPED: no image given for $label and its container is not running."
    echo
    return 0
  fi
  if [ ! -d "$REPO/$rel" ]; then
    echo "SKIPPED: $REPO/$rel does not exist in this tree."
    echo
    return 0
  fi

  echo "image : $img"
  echo "tree  : $REPO/$rel"
  echo

  local baked_all
  baked_all="$(docker run --rm --entrypoint sh "$img" -c \
                "cd $imgdir 2>/dev/null && sha256sum *.j2" 2>/dev/null)"
  if [ -z "$baked_all" ]; then
    echo "SKIPPED: could not read $imgdir from $img."
    echo "         Either the image has no such directory or it could not be run."
    echo
    return 0
  fi

  checked=$((checked + 1))

  local path name tracked baked
  for path in "$REPO/$rel"/*.j2; do
    name="$(basename "$path")"
    tracked="$(sha256sum "$path" | cut -d' ' -f1)"
    baked="$(printf '%s\n' "$baked_all" | awk -v n="$name" '$2 == n {print $1}')"
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
    if [ ! -f "$REPO/$rel/$name" ]; then
      echo "EXTRA IN IMAGE    $name  $baked"
      echo "                  present in the image, absent from the tree"
      rc=1
    fi
  done <<< "$baked_all"
  echo
}

check_dir "api seed prompts" "$IMAGE" "$SEED_DIR_REL" "$SEED_DIR_IMG"
check_dir "workers stage prompts" "$WORKER_IMAGE" "$WORKER_DIR_REL" "$WORKER_DIR_IMG"

if [ "$checked" -eq 0 ]; then
  echo "ABORT: no directory could be checked. Nothing was compared."
  exit 2
fi

if [ $rc -eq 0 ]; then
  echo "PASS: every baked template checked is byte-identical to the tracked one."
else
  echo "FAIL: the image's templates are not the tracked ones."
  echo "      Rebuild before deploying. A prompt published from a stale"
  echo "      template is a contract change nobody made."
fi
exit $rc
