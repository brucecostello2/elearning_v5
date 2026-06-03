# IVGS v5 - WhisperX large-v3 STT/alignment server (sync, port 9000).
# Base matches the fleet: CUDA 12.8 + cuDNN runtime on Ubuntu 22.04 (python3.10).
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/data/models/hf-cache \
    TORCH_HOME=/data/models/torch-cache

# ffmpeg: whisperx.load_audio shells out to ffmpeg for decoding.
# libsndfile1: audio IO. libpython3.10: needed by some torch / ctranslate2 extension .so files.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip ffmpeg libsndfile1 libpython3.10 git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Torch FIRST, cu128 nightly, matching the rest of the fleet (Blackwell sm_120).
#    whisperx uses torch/torchaudio for the wav2vec2 alignment pass and VAD.
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install --pre torch torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

# 2) whisperx + pinned deps. transformers<5: the same constraint that bit Coqui (the
#    wav2vec2 alignment path imports symbols 5.x removed). faster-whisper/ctranslate2 (pulled
#    by whisperx) provide the ASR CUDA runtime. If this step downgrades torch off the nightly,
#    we switch whisperx to --no-deps + explicit deps (the Coqui-style reconciliation).
COPY whisperx/requirements.txt /app/requirements.txt
RUN python3 -m pip install -r /app/requirements.txt

# App: shared skeleton + this server.
COPY common /app/common
COPY whisperx/server.py /app/server.py

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=5 \
    CMD curl -sf http://localhost:9000/health || exit 1

CMD ["python3", "/app/server.py"]
