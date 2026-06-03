# IVGS v5 - Coqui XTTS v2 TTS server (sync; primary). Port 5002.
# Tag: ghcr.io/brucecostello2/ivgs-workers:coqui-${IVGS_WORKERS_TAG}
#
# BUILD CONTEXT = ivgs-workers/servers (so it can COPY common):
#   docker build -t ghcr.io/brucecostello2/ivgs-workers:coqui-${IVGS_WORKERS_TAG} \
#       -f ivgs-workers/servers/coqui/Dockerfile ivgs-workers/servers
#
# cu128 Blackwell base (sm_120), same as the rest of the fleet.
# XTTS-v2 ships under the Coqui Public Model License (non-commercial); COQUI_TOS_AGREED=1
# auto-accepts it for the non-interactive download (per the spec's choice of XTTS-v2).
#
# VERIFY-ON-NODE after build:
#   - torch stayed cu128, torchcodec loads, XTTS imports:
#       docker run --rm --gpus all <img> python -c \
#         "import torch, torchcodec; print(torch.__version__, torch.cuda.is_available()); from TTS.api import TTS; print('ok')"
#   - XTTS-v2 (~1.8 GB) downloads into the mounted /data/models (TTS_HOME / HF_HOME); if it
#     instead lands in /root/.local/share/tts, mount that path or set HOME to the mount.
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=5002 \
    DEVICE=cuda \
    COQUI_TOS_AGREED=1 \
    XTTS_MODEL=tts_models/multilingual/multi-dataset/xtts_v2 \
    XTTS_DEFAULT_SPEAKER="Claribel Dervla" \
    TTS_HOME=/data/models/tts \
    HF_HOME=/data/models/hf-cache

# python + espeak-ng (phonemizer fallback) + libsndfile1 (soundfile) + curl (healthcheck)
# + ffmpeg: coqui-tts 0.27.4+ on torch >=2.9 routes audio IO through torchcodec, and
#   torchcodec dynamically loads the FFmpeg shared libs (libav*, FFmpeg 4-8) at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip espeak-ng libsndfile1 ffmpeg libpython3.10 curl \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch + torchaudio + torchcodec cu128 / sm_120, ALL from the cu128 nightly index in ONE
# line so they are an ABI-matched set (torchcodec is locked to the exact torch build).
# coqui-tts requires torchcodec on torch >=2.9; installing it here (before requirements)
# keeps the cu128 stack intact through the coqui-tts install.
RUN python3 -m pip install --pre torch torchaudio torchcodec --index-url https://download.pytorch.org/whl/nightly/cu128

COPY coqui/requirements.txt ./requirements.txt
RUN python3 -m pip install -r requirements.txt

COPY common ./common
COPY coqui/server.py ./server.py

EXPOSE 5002
# start-period covers the first-run XTTS-v2 download (~1.8 GB) into the mounted cache.
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/health || exit 1

CMD ["python", "server.py"]
