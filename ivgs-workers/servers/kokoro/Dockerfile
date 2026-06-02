# IVGS v5 - Kokoro TTS server image (sync; English-only fallback). Port 5003.
# Tag: ghcr.io/brucecostello2/ivgs-workers:kokoro-${IVGS_WORKERS_TAG}
#
# BUILD CONTEXT = ivgs-workers/servers  (parent of common/ and kokoro/), so the shared
# skeleton can be copied in:
#   docker build -t ghcr.io/brucecostello2/ivgs-workers:kokoro-${IVGS_WORKERS_TAG} \
#       -f ivgs-workers/servers/kokoro/Dockerfile ivgs-workers/servers
#
# GPU/BASE-IMAGE: Blackwell (sm_120) needs CUDA 12.8 + torch cu128 (same base as
# servers/cogvideox). Kokoro-82M is tiny and would even run on CPU, but we keep the
# fleet on one cu128 base for consistency.
# VERIFY-ON-NODE: after build, confirm kokoro did not downgrade torch off cu128:
#   docker run --rm --gpus all <img> python -c \
#     "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_arch_list())"
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=5003 \
    KOKORO_LANG_CODE=a \
    KOKORO_VOICE=af_heart \
    HF_HOME=/data/models/hf-cache

# python + espeak-ng (Kokoro out-of-dictionary G2P fallback) + libsndfile1 (soundfile)
# + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip espeak-ng libsndfile1 curl \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch (+ torchaudio) cu128 / sm_120 FIRST, from the cu128 nightly index (as cogvideox).
RUN python3 -m pip install --pre torch torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128

COPY kokoro/requirements.txt ./requirements.txt
RUN python3 -m pip install -r requirements.txt

# Bake the spaCy English model misaki uses for G2P so startup never pip-installs it at
# runtime - keeps the image self-contained and recovery-complete. Pinned to 3.8.0 (the
# version misaki resolves). The Kokoro-82M *weights* stay mounted (HF cache), per AD-01.
RUN python3 -m pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

COPY common ./common
COPY kokoro/server.py ./server.py

EXPOSE 5003
# start-period covers the first-run HuggingFace weight download into the mounted HF_HOME.
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/health || exit 1

CMD ["python", "server.py"]
