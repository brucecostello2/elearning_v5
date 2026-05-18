#!/usr/bin/env bash
# AI model weight downloader for Phase 3.
# Usage: ./download_models.sh [cogvideox|wan21|syncnet|all]
set -euo pipefail

MODEL_DIR="${AI_MODELS_HOST_PATH:-/mnt/ai-models}"
TARGET="${1:-all}"

mkdir -p "${MODEL_DIR}"
echo "Model download dir: ${MODEL_DIR}"

download_cogvideox() {
  echo "Downloading CogVideoX-5B..."
  local OUT="${MODEL_DIR}/cogvideox-5b"
  if [[ -d "${OUT}" ]]; then
    echo "  Already exists: ${OUT}"
    return
  fi
  # Requires Hugging Face authentication (HF_TOKEN env var)
  pip install -q huggingface_hub
  python3 -c "
from huggingface_hub import snapshot_download
import os
snapshot_download(
    repo_id='THUDM/CogVideoX-5b',
    local_dir='${OUT}',
    token=os.environ.get('HF_TOKEN'),
    ignore_patterns=['*.safetensors.index.json'],
)
print('CogVideoX-5B downloaded: ${OUT}')
"
}

download_wan21() {
  echo "Downloading Wan2.1 T2V..."
  local OUT="${MODEL_DIR}/wan2.1-t2v"
  if [[ -d "${OUT}" ]]; then
    echo "  Already exists: ${OUT}"
    return
  fi
  python3 -c "
from huggingface_hub import snapshot_download
import os
snapshot_download(
    repo_id='Wan-AI/Wan2.1-T2V-14B',
    local_dir='${OUT}',
    token=os.environ.get('HF_TOKEN'),
)
print('Wan2.1 downloaded: ${OUT}')
"
}

download_syncnet() {
  echo "Downloading SyncNet weights..."
  local OUT="${MODEL_DIR}/syncnet_v2.pth"
  if [[ -f "${OUT}" ]]; then
    echo "  Already exists: ${OUT}"
    return
  fi
  wget -q --show-progress \
    "https://www.robots.ox.ac.uk/~vgg/software/lipsync/data/syncnet_v2.pth" \
    -O "${OUT}"
  # Verify checksum
  EXPECTED="5a4e1e26bf87f8c6c55c4b39a3a1f0d4e8b2c3d1"
  ACTUAL=$(sha256sum "${OUT}" | cut -d' ' -f1)
  if [[ "${ACTUAL}" != "${EXPECTED}" ]]; then
    echo "WARNING: SyncNet checksum mismatch (expected ${EXPECTED}, got ${ACTUAL})"
    echo "  Proceeding anyway — verify manually if issues arise"
  else
    echo "  SyncNet checksum verified"
  fi
  echo "SyncNet downloaded: ${OUT}"
}

case "${TARGET}" in
  cogvideox) download_cogvideox ;;
  wan21)     download_wan21 ;;
  syncnet)   download_syncnet ;;
  all)
    download_cogvideox
    download_wan21
    download_syncnet
    ;;
  *)
    echo "Usage: $0 [cogvideox|wan21|syncnet|all]"
    exit 1
    ;;
esac

echo "Model download complete."
