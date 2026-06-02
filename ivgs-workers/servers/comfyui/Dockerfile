# IVGS v5 — ComfyUI + FLUX.1 image server (node-04 primary image tier)
# Tag: ghcr.io/brucecostello2/ivgs-workers:comfyui-${IVGS_WORKERS_TAG}
# Serves ComfyUI's native API on :8188; flux_client (ImageProvider, spec §19.1) drives /prompt,/history,/view.
# Build plan: ComfyUI = "stock server, no wrapper" (Nodes_02-06_Model_Server_Build_Plan §3.1).
#
# Blackwell sm_120 (RTX PRO 5000/6000): CUDA 12.8 + torch cu128 - same proven base as servers/cogvideox.
# ComfyUI's own pip would pull a torch lacking sm_120, so install torch cu128 FIRST, then ComfyUI deps minus torch*.
# Weights are MOUNTED, not baked (AD-01: checkpoints are dynamically_loadable; ivgs-models owns acquisition).
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive COMFYUI_PORT=8188
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip git ffmpeg curl ca-certificates \
    && ln -sf /usr/bin/python3 /usr/bin/python && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN python3 -m pip install --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128
ARG COMFYUI_REF=master
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI \
    && cd /app/ComfyUI && git checkout "${COMFYUI_REF}"
RUN cd /app/ComfyUI \
    && grep -viE '^(torch|torchvision|torchaudio)([=<>! ]|$)' requirements.txt > /tmp/comfy-reqs.txt \
    && python3 -m pip install -r /tmp/comfy-reqs.txt
EXPOSE 8188
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD curl -sf http://localhost:${COMFYUI_PORT}/system_stats || exit 1
CMD ["sh","-c","python /app/ComfyUI/main.py --listen 0.0.0.0 --port ${COMFYUI_PORT}"]
