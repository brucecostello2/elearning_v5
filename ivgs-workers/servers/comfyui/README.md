# ComfyUI / FLUX.1 image server (node-04)  -- spec §19.1 FluxProvider, Build Plan §3.1
Vanilla ComfyUI (no wrapper); flux_client drives native /prompt,/history,/view on :8188.
FLUX loads via CheckpointLoaderSimple from a single all-in-one fp8 checkpoint.

## Weights -- MOUNTED ro, NOT baked (D-weights resolved: AD-01 dynamically_loadable + cogvideox precedent)
  flux1-schnell-fp8.safetensors  Comfy-Org/flux1-schnell 17.2GB apache-2.0 (ungated)            prototype, 4 steps
  flux1-dev-fp8.safetensors      Comfy-Org/flux1-dev     17.2GB flux-dev-noncommercial (GATED)  production, 50 steps
  Stage locally on node-04: /data/models/comfyui/checkpoints  (ComfyUI hot-loads by ckpt_name)

## Build (on node-04; pin latest stable ComfyUI tag)
  REF=$(git ls-remote --tags --refs https://github.com/comfyanonymous/ComfyUI.git | awk -F/ '{print $NF}' | grep -E '^v[0-9]' | sort -V | tail -1)
  docker build --build-arg COMFYUI_REF=$REF -t ghcr.io/brucecostello2/ivgs-workers:comfyui-v5.2.7-h0 \
    -f ivgs-workers/servers/comfyui/Dockerfile ivgs-workers/servers/comfyui

## Run (smoke)
  docker run -d --name ivgs-comfyui-primary --gpus all -p 8188:8188 \
    -v /data/models/comfyui/checkpoints:/app/ComfyUI/models/checkpoints:ro \
    ghcr.io/brucecostello2/ivgs-workers:comfyui-v5.2.7-h0

## DONE (Build Plan §4): health 200 -> real flux_client request returns image bytes (schnell steps=4, cfg~1.0) -> docker push to GHCR.
