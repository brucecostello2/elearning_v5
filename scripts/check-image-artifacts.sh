#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — image-artifact store conformance check
# =============================================================================
# WP-58 Task 4. Makes the naming convention ENFORCED rather than conventional.
#
# Every artifact in the store must be named as `artifact_name_for` derives it
# from an image reference: <namespace>_<repo>_<tag>.tar.(zst|gz). A file that
# does not match is unreachable from every deploy path — which is not a tidiness
# problem, it is the 2026-08-25 fleet incident: three nodes had their .env tag
# bumped, then refused to recreate on a missing image, and configuration and
# running image stayed inconsistent until a human noticed.
#
# Exit 0 — every artifact conforms.
# Exit 1 — at least one does not; each is named on stderr.
#
# Usage:  scripts/check-image-artifacts.sh [store-dir]
# =============================================================================
set -uo pipefail

STORE="${1:-${IVGS_IMAGE_ARTIFACTS:-/mnt/ivgs-shared/image-artifacts}}"

if [ ! -d "$STORE" ]; then
    echo "ERROR: artifact store not found: $STORE" >&2
    exit 1
fi

# <namespace>_<repo>_<tag>.tar.zst|gz — the shape `artifact_name_for` produces
# after mapping `/` and `:` to `_`. A tag may itself contain `_` (e.g.
# `comfyui-v5.2.7-h0`), so the tag segment is permissive; what is pinned is that
# there are at least two `_`-separated segments ahead of it.
readonly CONFORMING='^[A-Za-z0-9.-]+_[A-Za-z0-9.-]+_[A-Za-z0-9._-]+\.tar\.(zst|gz)$'

# PRE-EXISTING EXCEPTIONS, each with a stated reason. This list exists so the
# gate can be GREEN and therefore believed. WP-56 Task 0 closed a CI rule that
# had been red since it was written, on the grounds that a permanently-red gate
# trains people to ignore CI; adding a new one here would repeat that mistake.
#
# The bar for adding a line is a reason, not convenience. Neither of these is an
# IVGS image banked by a deploy, which is what the convention governs.
allowlisted() {
    case "$1" in
        # Third-party upstream image (vllm/vllm-openai), banked by hand before
        # this convention existed. Not one of ours; no deploy path resolves it
        # by derived name.
        vllm-openai-cu130-nightly.tar.zst) return 0 ;;
        # Legacy duplicate of brucecostello2_ivgs-workers_comfyui-v5.2.7-h0.tar.zst,
        # kept because it is the only .tar.gz-era copy. The conforming .tar.zst
        # exists alongside it and is what a deploy resolves.
        comfyui-v5.2.7-h0.tar.gz) return 0 ;;
    esac
    return 1
}

bad=0
checked=0
skipped=0
while IFS= read -r f; do
    base="$(basename "$f")"
    if allowlisted "$base"; then
        skipped=$((skipped + 1))
        continue
    fi
    checked=$((checked + 1))
    if ! [[ "$base" =~ $CONFORMING ]]; then
        bad=$((bad + 1))
        {
            echo "NON-CONFORMING: $base"
            echo "  Artifact names are derived from the image reference by"
            echo "  scripts/lib/artifact_name.sh and must look like"
            echo "  <namespace>_<repo>_<tag>.tar.zst — e.g."
            echo "  brucecostello2_ivgs-workers_v5.15.0-library.tar.zst"
            echo "  Re-bank it: sudo scripts/save-image-artifact.sh <image-ref>"
        } >&2
    fi
done < <(find "$STORE" -maxdepth 1 -type f \( -name '*.tar.zst' -o -name '*.tar.gz' \) 2>/dev/null | sort)

if [ "$bad" -gt 0 ]; then
    echo "FAIL: ${bad} of ${checked} artifacts do not follow the naming convention" >&2
    exit 1
fi

echo "OK: ${checked} artifacts conforming, ${skipped} allowlisted"
