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
#
# =============================================================================
# WP-IVGS-12b Task 2 — THE ARTIFACT IDENTITY IS NAME + DIGEST, NOT NAME
# =============================================================================
# THE SECOND INCIDENT, MEASURED 2026-08-29 (RC-Q8). `save-image-artifact.sh`
# skips when a file of that name exists, and THE NAME COMES FROM THE TAG. A tag
# rebuilt mid-session — which is what every mid-deploy fix produces — re-saved
# nothing; `docker load` restored the OLD image under the same tag on three
# nodes; and `verify-deployed-image.sh` reported DEPLOY VERIFIED on all of them
# because it compares tags. node-01 ran `e9c1001a` while nodes 02/03/04 ran
# `aa89c778` under one tag, with a timeout fix present on one node and absent on
# three. Nothing in the pipeline could see it.
#
# ⛳ WHY THE DIGEST GOES IN A SIDECAR AND NOT IN THE NAME — ARGUED FROM EVERY
# CONSUMER, because the WP-58 one-definition rule is the whole point:
#
#   artifact_path_for / artifact_require  resolve from an image REF and nothing
#       else. That IS the deploy contract: a remote node has the tag, does not
#       have the image, and the artifact exists precisely to carry the image it
#       does not have. A digest in the NAME would force every deploy caller to
#       know the digest before it can find the file — backwards.
#   save-image-artifact.sh                writes one artifact per tag; a deploy
#       then resolves that one. Digest-in-name means N files per tag and a
#       lookup with no way to choose between them.
#   check-image-artifacts.sh              pins the NAME SHAPE. Digest-in-name
#       changes that shape and the gate goes red for every artifact ever banked.
#   tests_system/test_wp58_retention.py   asserts `artifact_name_for`'s exact
#       output. Changing it rewrites a test that is doing its job correctly.
#
# So the NAME stays derived from the tag, and identity gains a `.digest`
# sidecar. The fix is in the SKIP LOGIC, which is where the defect actually was:
# **skip-if-present is valid only when present means SAME DIGEST.**
#
#   image_local_digest <image-ref>  -> sha256:… of the image this host holds
#   artifact_digest_path_for <ref>  -> $STORE/<name>.digest
#   artifact_banked_digest <ref>    -> the digest recorded beside the artifact
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


# ── WP-IVGS-12b: identity ─────────────────────────────────────────────────

# The image id this host actually holds for a reference. Empty when absent.
# `.Id` and not `.RepoDigests`: a locally built image has no repo digest until
# it is pushed, and these images travel as artifacts precisely because they are
# never pushed (§6.1).
image_local_digest() {
    local ref="${1:?usage: image_local_digest <image-ref>}"
    docker image inspect "$ref" --format '{{.Id}}' 2>/dev/null || true
}

# Where the digest of a banked artifact is recorded.
artifact_digest_path_for() {
    local ref="${1:?usage: artifact_digest_path_for <image-ref>}"
    local store="${IVGS_IMAGE_ARTIFACTS:-/mnt/ivgs-shared/image-artifacts}"
    echo "$store/$(artifact_name_for "$ref").digest"
}

# The digest recorded beside the artifact, or empty when none was recorded.
# Empty is meaningful: it means the artifact predates this rule and its
# provenance CANNOT be proved, which callers must treat as "unknown", never as
# "matches".
artifact_banked_digest() {
    local ref="${1:?usage: artifact_banked_digest <image-ref>}"
    local f; f="$(artifact_digest_path_for "$ref")"
    [ -s "$f" ] && head -n1 "$f" | tr -d '[:space:]' || true
}
