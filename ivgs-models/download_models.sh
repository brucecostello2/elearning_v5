#!/bin/bash
# IVGS v5 — Model Download Orchestrator (§7.1)
# Run on node-01; models stored on NFS share accessible to all nodes.
#
# Prerequisites:
#   - huggingface-cli installed (pip install huggingface_hub[cli])
#   - HF_TOKEN set if downloading gated models
#   - NFS share mounted at SHARED_VOLUME_PATH
#
# Usage:
#   chmod +x download_models.sh
#   ./download_models.sh
set -euo pipefail

MODELS_DIR="${SHARED_VOLUME_PATH:-/mnt/ivgs-shared}/models"
mkdir -p "$MODELS_DIR"

echo "============================================="
echo "IVGS v5 — Model Download Orchestrator"
echo "Target: $MODELS_DIR"
echo "============================================="

# === vLLM Models (§7.1.1) ===

echo ""
echo "--- [1/7] Downloading Llama 3.3 70B Instruct (node-02 + node-03) ---"
huggingface-cli download meta-llama/Llama-3.3-70B-Instruct \
  --local-dir "$MODELS_DIR/llama-3.3-70b-instruct" \
  --local-dir-use-symlinks False

echo ""
echo "--- [2/7] Downloading Qwen2.5 72B Instruct (node-02 + node-03) ---"
huggingface-cli download Qwen/Qwen2.5-72B-Instruct \
  --local-dir "$MODELS_DIR/qwen2.5-72b-instruct" \
  --local-dir-use-symlinks False

echo ""
echo "--- [3/7] Downloading Mistral Small 24B Instruct (node-04) ---"
huggingface-cli download mistralai/Mistral-Small-24B-Instruct \
  --local-dir "$MODELS_DIR/mistral-small-24b" \
  --local-dir-use-symlinks False

# === ComfyUI / Image Models (§7.1.2) ===

echo ""
echo "--- [4/7] Downloading FLUX.1 Dev (node-04) ---"
huggingface-cli download black-forest-labs/FLUX.1-dev \
  --local-dir "$MODELS_DIR/flux1-dev" \
  --local-dir-use-symlinks False

echo ""
echo "--- [5/7] Downloading SDXL 1.0 (node-05) ---"
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  --local-dir "$MODELS_DIR/sdxl-base" \
  --local-dir-use-symlinks False

# === TTS Models (§7.1.3) ===

echo ""
echo "--- [6/7] Downloading Coqui XTTS v2 (node-04) ---"
huggingface-cli download coqui/XTTS-v2 \
  --local-dir "$MODELS_DIR/xtts-v2" \
  --local-dir-use-symlinks False

# === Video Models ===

echo ""
echo "--- [7/7] Downloading CogVideoX 5B (node-02/03) ---"
huggingface-cli download THUDM/CogVideoX-5b \
  --local-dir "$MODELS_DIR/cogvideox-5b" \
  --local-dir-use-symlinks False

# === Ollama Models (node-05) ===

echo ""
echo "--- Pulling Ollama models (node-05) ---"
OLLAMA_HOST="${OLLAMA_URL:-http://192.168.1.94:11434}"
export OLLAMA_HOST
ollama pull llama3.2:8b
ollama pull phi3:medium
ollama pull gemma2:9b

echo ""
echo "============================================="
echo "All models downloaded successfully."
echo "Run 'sha256sum -c checksums.sha256' to verify."
echo "============================================="
