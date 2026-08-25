# =============================================================================
# IVGS v5 — CLIP image/text scoring service   (WP-44-QUALITY, node-05)
# =============================================================================
# An ADDITIVE service, in the WP-48 telemetry-overlay tradition: it is deployed
# by its own compose project to one node and touches nothing that already runs.
#
# WEIGHTS ARE BAKED IN, DELIBERATELY. The model is downloaded once at BUILD
# time on node-01 and committed to the image, so:
#   * the running container needs no network at all;
#   * the artifact banked to /mnt/ivgs-shared is self-contained and restorable
#     with `docker load` alone, per the recovery policy (RECOVERY.md);
#   * the exact weights are pinned by the image digest rather than by whatever
#     HuggingFace serves on the day of a restart.
# =============================================================================
FROM nvidia/cuda:12.8.0-base-ubuntu24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CUDA 12.8 wheels, matching node-05's driver (580.173.02) and its Blackwell
# card (RTX PRO 5000, sm_120 — the first torch line that ships sm_120 kernels
# is the cu128 one, which is why the base image is 12.8 and not the fleet's
# older 12.4). The wheels carry their own CUDA runtime/cuDNN/cuBLAS, so the
# `-base-` image is the correct starting point: a `-cudnn-runtime-` base would
# ship a second copy of libraries torch does not use.
RUN pip install --no-cache-dir torch==2.8.0 \
        --index-url https://download.pytorch.org/whl/cu128

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# --- Bake the weights ---
# A separate script rather than an inline heredoc: heredocs in RUN need the
# dockerfile:1.4+ frontend, and this file must build under the plain builder
# too. ARGs are promoted to ENV so bake_model.py can read them.
ARG CLIP_MODEL=openai/clip-vit-base-patch32
ARG CLIP_REVISION=main
ENV CLIP_MODEL=${CLIP_MODEL} \
    CLIP_REVISION=${CLIP_REVISION} \
    CLIP_DEST=/models/clip \
    HF_HUB_DISABLE_TELEMETRY=1
COPY bake_model.py /tmp/bake_model.py
RUN python /tmp/bake_model.py

# --- Runtime ---
FROM nvidia/cuda:12.8.0-base-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    IVGS_CLIP_MODEL_DIR=/models/clip

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r ivgs && useradd -r -g ivgs -m ivgs

# --chown on the COPY rather than a RUN chown afterwards: a `chown -R` over the
# 610 MB weights directory rewrites every file and lands a second full copy of
# it in the image. Same for /app.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=ivgs:ivgs /models /models

WORKDIR /app
COPY --chown=ivgs:ivgs app.py /app/app.py

USER ivgs

EXPOSE 8300

# model_loaded, not process-is-up. A container whose model failed to load is
# UNHEALTHY, so a degraded scorer is visible before it is depended on.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -fsS http://127.0.0.1:8300/health | grep -q '"model_loaded":true' || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8300", "--workers", "1"]
