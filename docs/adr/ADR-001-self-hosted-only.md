# ADR-001: Self-Hosted AI Services Only

## Context
IVGS v5 specification §7.2 mandates that all AI services must be self-hosted.
No cloud APIs (OpenAI, Anthropic, ElevenLabs, D-ID, Synthesia) are permitted.

## Decision
All AI inference runs on the 6-node Proxmox cluster using:
- vLLM for LLM inference (Llama 3.1 70B)
- ComfyUI + FLUX.1 Dev for image generation
- CogVideoX 5B and Wan2.1 for video generation
- Coqui XTTS v2 for TTS
- WhisperX for STT
- Ollama + Kokoro TTS as fallbacks

## Status
Implemented. Compliance scanner enforces prohibition at CI level.
