#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — image-artifact naming, in ONE place
# =============================================================================
# WP-58 Task 4.
#
# THE INCIDENT THIS EXISTS TO PREVENT. Every banked worker artifact is named
# `brucecostello2_ivgs-workers_<tag>.tar.zst`, derived from the image reference.
# WP-56 banked one by hand with `sudo docker save | sudo sh -c "zstd -o ..."`
# and chose `ivgs-workers-<tag>.tar.zst`. On 2026-08-25 three nodes had their
# .env tag bumped and then refused to recreate on a missing image, leaving
# configuration and running image inconsistent until it was corrected by hand.
#
# Nothing had required the use of save-image-artifact.sh, so the convention was
# a convention. It is now DERIVED IN ONE PLACE and CHECKABLE:
#
#   artifact_name_for <image-ref>   -> brucecostello2_ivgs-workers_v5.15.0-library
#   artifact_path_for <image-ref>   -> $STORE/<name>.tar.zst   (or .tar.gz)
#   artifact_require <image-ref>    -> resolves, or exits 1 BEFORE any node is touched
#
# A deploy that calls `artifact_require` fails on this node, with the expected
# path named, instead of failing on three remote nodes after their tags have
# already been changed.
# =============================================================================

# Derive the canonical artifact basename from a full image reference.
# Strips the registry host, then maps `/` and `:` to `_`. This is byte-identical
# to what save-image-artifact.sh has always done; it moved here so there is one
# definition rather than one per caller.
artifact_name_for() {
    local ref="${1:?usage: artifact_name_for <image-ref>}"
    echo "$ref" | sed 's#^[^/]*/##; s#[/:]#_#g'
}

# The extension depends on which compressor was available at SAVE time, so a
# lookup has to accept either rather than assume.
artifact_path_for() {
    local ref="${1:?usage: artifact_path_for <image-ref>}"
    local store="${IVGS_IMAGE_ARTIFACTS:-/mnt/ivgs-shared/image-artifacts}"
    local name; name="$(artifact_name_for "$ref")"
    local candidate
    for candidate in "$store/$name.tar.zst" "$store/$name.tar.gz"; do
        if [ -s "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# Gate for a deploy path. Prints the resolved artifact, or explains precisely
# what is missing and exits non-zero.
artifact_require() {
    local ref="${1:?usage: artifact_require <image-ref>}"
    local store="${IVGS_IMAGE_ARTIFACTS:-/mnt/ivgs-shared/image-artifacts}"
    local path
    if path="$(artifact_path_for "$ref")"; then
        echo "$path"
        return 0
    fi
    local name; name="$(artifact_name_for "$ref")"
    {
        echo "ERROR: no artifact for image reference: $ref"
        echo "  expected: $store/$name.tar.zst  (or .tar.gz)"
        echo "  Bank it first:  sudo scripts/save-image-artifact.sh $ref"
        echo "  Do NOT hand-roll 'docker save | zstd -o <name>' — a name that"
        echo "  does not match the derivation above is invisible to every"
        echo "  deploy path and is what broke the 2026-08-25 fleet roll-out."
    } >&2
    return 1
}
