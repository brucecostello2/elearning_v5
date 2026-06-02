# IVGS — Recovery & Image-Artifact Strategy

Interim guidance for recovering the fleet WITHOUT a paid container registry.
A comprehensive DR design (local NAS + offsite, covering data as well as images)
is tracked in OUTSTANDING_WORK.md and will be built once all nodes are up and
AD-01 (model management) is implemented.

## Why no registry push

Large GPU images (CUDA + PyTorch + framework, ~5-15 GB each) blow past the GHCR
free tier and are billed. Recovery does not need a registry. It rests on three
independent legs:

1. Build recipe (git). Each server has a Dockerfile under
   ivgs-workers/servers/<name>/ pinning framework ref, torch channel, base image.
   "docker build" reconstructs it. Caveat: Blackwell (sm_120) needs nightly torch
   wheels that age out of the index, so a late rebuild may not be byte-identical
   -- leg 2 covers that.
2. Exact artifact (docker save -> owned storage). A compressed "docker save"
   tarball is the image bit-for-bit. Stored under /mnt/ivgs-shared/image-artifacts/
   by scripts/save-image-artifact.sh (records SHA-256 + a MANIFEST line). This
   replaces the GHCR push.
3. Weights (re-acquirable, never baked). Mounted at runtime from /mnt/models;
   re-download from source with the SHA-256 recorded by the model tooling
   (AD-01 / download_models.sh).

## Compose wiring

GPU-server services set "pull_policy: never" so the node uses the locally built
or loaded image. The ghcr.io/... string is only a name; a local image with that
tag satisfies compose with no pull.

## Build-loop convention

build on node -> health 200 -> validate via the real *_client.py ->
scripts/save-image-artifact.sh <image-ref>. Do NOT docker push large GPU images.

## Restore a node

1. Restore the repo (git) and checkout the working branch.
2. Per image: rebuild from the Dockerfile, OR load the artifact
   (<decompressor> <artifact> | docker load). MANIFEST records the exact command
   and SHA per image.
3. Ensure /mnt/models has the weights (re-download + verify SHA if missing).
4. docker compose -f docker-compose.node0X.yml up -d.

## CAVEAT — backups must leave the cluster

/mnt/ivgs-shared is NFS from node-01, so artifacts physically sit on node-01's
disk. A node-01 disk failure loses the running system AND these backups together.
True DR needs an off-cluster copy of image-artifacts/, the git repo, and
optionally /mnt/models. Until the comprehensive design lands, keep at least one
copy on separate hardware.
