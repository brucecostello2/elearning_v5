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
RUN python3 -m pip install --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY server.py .

EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/health || exit 1

CMD ["python", "server.py"]
