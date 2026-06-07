# IVGS v5 — LatentSync 1.6 talking-head server
# Tag: ghcr.io/brucecostello2/ivgs-workers:latentsync-${IVGS_LATENTSYNC_TAG}
# Build context = ivgs-workers/servers (so we can COPY common + latentsync):
#   docker build -t ghcr.io/brucecostello2/ivgs-workers:latentsync-v5.2.7-h0 \
#       -f ivgs-workers/servers/latentsync/Dockerfile ivgs-workers/servers
#
# Blackwell (sm_120) needs CUDA 12.8 + torch cu128. LatentSync pins torch 2.5.1/cu121
# (sm_90 max) which FAILS on this card, so we install torch cu128 FIRST and strip the
# torch/torchvision/cu121 lines from LatentSync's requirements so they can't clobber it.
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    LATENTSYNC_DIR=/app/LatentSync \
    LATENTSYNC_WEIGHTS_DIR=/mnt/ivgs-shared/models/latentsync-1.6 \
    LATENTSYNC_UNET_CONFIG=configs/unet/stage2_512.yaml \
    LATENTSYNC_PORT=7860 \
    OUTPUT_DIR=/tmp/ivgs-latentsync-out

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-dev git ffmpeg curl \
        build-essential libgl1 libglib2.0-0 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch cu128 FIRST (Blackwell sm_120), matching the cogvideox image
RUN python3 -m pip install --upgrade pip \
 && python3 -m pip install torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu128

# Vendor LatentSync (pinned) + install its deps WITHOUT the torch pins
RUN git clone https://github.com/bytedance/LatentSync.git /app/LatentSync \
 && cd /app/LatentSync && (git checkout a229c39 || true)
RUN cd /app/LatentSync \
 && grep -vE '^(torch==|torchvision==|--extra-index-url)' requirements.txt > /tmp/ls-req.txt \
 && python3 -m pip install -r /tmp/ls-req.txt

# Harness deps (explicit, though gradio also pulls fastapi/uvicorn/multipart)
COPY latentsync/requirements.txt /tmp/svc-req.txt
RUN python3 -m pip install -r /tmp/svc-req.txt

# The wrapper: shared harness + our server
COPY common ./common
COPY latentsync/server.py ./server.py

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -sf http://localhost:${LATENTSYNC_PORT}/health || exit 1

CMD ["python", "server.py"]
