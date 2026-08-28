# IVGS v5 — CogVideoX / Wan2.1 model server image (REFERENCE)
# Tag: ghcr.io/brucecostello2/ivgs-workers:cogvideox-${IVGS_WORKERS_TAG}
# Serves BOTH CogVideoX and Wan2.1 (variant via MODEL_VARIANT env).
#
# Build context = this dir:
#   docker build -t ghcr.io/brucecostello2/ivgs-workers:cogvideox-${IVGS_WORKERS_TAG} \
#       -f ivgs-workers/servers/cogvideox/Dockerfile ivgs-workers/servers/cogvideox
#
# GPU/BASE-IMAGE — VERIFIED REQUIREMENT for the RTX PRO 6000 Blackwell (sm_120):
# Blackwell needs CUDA 12.8 + PyTorch cu128. Stock pytorch images on cu12.1-12.4
# (torch <=2.6) support only up to sm_90 and FAIL with "sm_120 is not compatible".
# So we start from an NVIDIA CUDA 12.8 runtime and install torch cu128 explicitly.
#
# VERIFY-ON-NODE: confirm the torch cu128 build lists sm_120 with:
#   docker run --rm --gpus all <thisimage> python -c \
#     "import torch; print(torch.__version__, torch.cuda.get_arch_list())"
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    MODEL_VARIANT=cogvideox \
    MODEL_PATH=/mnt/models/cogvideox-5b \
    OUTPUT_DIR=/tmp/ivgs-video-out \
    PORT=8200

# Python + ffmpeg (for export_to_video) + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip ffmpeg curl \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch with CUDA 12.8 (sm_120 / Blackwell) FIRST, from the cu128 index.
#
# ⛔ THIS LAYER NO LONGER BUILDS, AND THE PIN THAT WOULD FIX IT IS GONE.
# Measured on node-03, 2026-08-28 (RC-M5 / RC-M8):
#   - Run as written, pip resolution FAILS outright:
#       ERROR: Cannot install torch and torchvision==0.27.0.dev20260407+cu128
#       because these package versions have conflicting dependencies.
#     Unpinned `--pre` against a moving nightly index is not reproducible; it was
#     only ever going to work on the day it was first run.
#   - The running cogvideox-pilot-1 image carries torch 2.12.0.dev20260407+cu128,
#     torchvision 0.27.0.dev20260407+cu128, torchaudio 2.11.0.dev20260407+cu128 —
#     and `dev20260407` HAS BEEN GARBAGE-COLLECTED from the nightly index, so
#     pinning to the known-good set does not build either. The wheels are gone.
#
# Consequence: this image cannot currently be reproduced from this file. RC-M5's
# server-code change was therefore deployed as a pinned-base derived layer
# (Dockerfile.serverpatch), which moves server.py and nothing else, rather than
# swapping the whole CUDA/torch stack under a working sm_120 GPU server.
#
# TO ACTUALLY FIX (needs a GPU window and an sm_120 re-verification, NOT a
# drive-by edit): move to a RELEASED cu128 torch — `torch==2.7.*` and matching
# torchvision/torchaudio from https://download.pytorch.org/whl/cu128 — pin all
# three exactly, and re-run the arch-list check in the header above before
# accepting the image.
RUN python3 -m pip install --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY server.py .

EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/health || exit 1

CMD ["python", "server.py"]
