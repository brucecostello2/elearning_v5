# IVGS v5 — AI Model Inventory

All models run locally on the IVGS hardware cluster (§7.1). **No cloud inference services.**

## Model Inventory (Appendix B Table B-1)

| Model | VRAM | Node(s) | Config |
|-------|------|---------|--------|
| Llama 3.3 70B Instruct | 140 GB (TP) | node-02 + node-03 | `vllm/llama-3.3-70b.yaml` |
| Qwen2.5 72B Instruct | 144 GB (TP) | node-02 + node-03 | `vllm/qwen2.5-72b.yaml` |
| Mistral Small 24B | 48 GB | node-04 | `vllm/mistral-24b.yaml` |
| Llama 3.2 8B (Q4) | 5 GB | node-05 | Ollama |
| Phi3 Medium | 8 GB | node-05 | Ollama |
| Gemma2 9B | 8 GB | node-05 | Ollama |
| FLUX.1 Dev | 24 GB | node-04 | `comfyui/flux1-dev-workflow.json` |
| FLUX.1 Schnell | 16 GB | node-04 | `comfyui/flux1-schnell-workflow.json` |
| SDXL 1.0 | 10 GB | node-05 | `comfyui/sdxl-workflow.json` |
| AnimateDiff | 16 GB | node-04 | `comfyui/animatediff-workflow.json` |
| CogVideoX 5B | 24 GB | node-02/03 | Diffusers |
| CogVideoX 2B | 14 GB | node-02/03 | Diffusers |
| Wan2.1 | 16 GB | node-02/03 | Diffusers |
| Coqui XTTS v2 | 16 GB | node-04 | `tts/coqui-xtts-v2.yaml` |
| Kokoro TTS | 4 GB | node-04 | N/A |
| WhisperX large-v3 | 8 GB | node-04 | N/A |
| LatentSync | 12 GB | node-04 | N/A |
| SadTalker | 8 GB | node-04 | N/A |

## Download

```bash
chmod +x download_models.sh
./download_models.sh
```

## Checksums

After download, verify model file integrity:

```bash
sha256sum -c checksums.sha256
```
