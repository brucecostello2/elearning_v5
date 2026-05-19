# IVGS v5 — Instructional Video Generation System

[![CI/CD](https://github.com/brucecostello2/elearning_v5/actions/workflows/ci.yml/badge.svg)](https://github.com/brucecostello2/elearning_v5/actions/workflows/ci.yml)
[![License: Private](https://img.shields.io/badge/License-Private-red.svg)]()

> **Self-hosted, GPU-accelerated instructional video generation platform.**  
> All AI inference runs on-premises — zero cloud API dependencies (§7.2).

---

## Architecture Overview

IVGS v5 runs on a **6-node Proxmox cluster** with dedicated GPU allocation:

| Node | IP | Role | GPU |
|------|------|------|-----|
| node-01 | 10.10.0.1 | Frontend, API, DB, Monitoring | — (CPU only) |
| node-02 | 10.10.0.2 | vLLM (Llama 3.1 70B), FLUX.1 Dev | 2× A6000 |
| node-03 | 10.10.0.3 | CogVideoX-5B, Wav2Lip | 2× A6000 |
| node-04 | 10.10.0.4 | Coqui TTS, Whisper, WhisperX | 1× A6000 |
| node-05 | 10.10.0.5 | Ollama (fallback), Kokoro TTS | 1× RTX 4090 |
| node-06 | 10.10.0.6 | Celery workers, GPU Scheduler | 1× RTX 4090 |

## 8-Stage Pipeline (§6.1)

1. **Transcript Refinement** — vLLM (Llama 3.1 70B)
2. **Storyboard Generation** — vLLM structured output
3. **Media Generation** — FLUX.1 Dev (images), CogVideoX/Wan2.1 (video)
4. **Composition Manifest** — Automated scene assembly
5. **Audio/TTS** — Coqui XTTS v2 (primary), Kokoro TTS (fallback)
6. **Talking Head** — LatentSync / SadTalker
7. **Prototype Draft** — FFmpeg composition
8. **Final Render** — Remotion + FFmpeg

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI, Python 3.11, SQLAlchemy, Alembic |
| Workers | Celery 5.4, Redis 7 (broker) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Database | PostgreSQL 17 + TimescaleDB |
| Storage | SeaweedFS (hot/warm/cold tiers) |
| Monitoring | Prometheus, Grafana, Loki, AlertManager |
| Deployment | Docker Compose (per-node) |

## Quick Start (Development)

```bash
# 1. Clone
git clone https://github.com/brucecostello2/elearning_v5.git
cd elearning_v5

# 2. Copy environment template
cp .env.template .env
# Edit .env with your secrets

# 3. Start local development stack
docker compose -f docker-compose.base.yml up -d

# 4. Run database migrations
docker compose exec ivgs-api alembic upgrade head

# 5. Seed initial data
docker compose exec ivgs-api python scripts/seed_data.py

# 6. Access
#   API:      http://localhost:8001/docs
#   Frontend: http://localhost:3000
```

## Project Structure

```
/ivgs/
├── ivgs-api/              # FastAPI backend (Python 3.11)
│   ├── app/
│   │   ├── api/v1/        # REST + WebSocket endpoints
│   │   ├── models/        # SQLAlchemy ORM models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── services/      # Business logic layer
│   │   ├── middleware/     # CORS, auth, rate limiting
│   │   └── main.py        # FastAPI application entry
│   ├── migrations/        # Alembic migrations (0001-0017)
│   └── tests/
├── ivgs-workers/          # Celery task workers
│   ├── clients/           # AI model HTTP clients (ABC-based)
│   ├── tasks/             # Pipeline stage tasks
│   ├── validators/        # Quality validation
│   └── tests/
├── ivgs-frontend/         # Next.js 14 dashboard
│   └── src/
│       ├── app/           # App Router pages
│       ├── components/    # React components
│       ├── hooks/         # SWR data hooks
│       └── contexts/      # Auth, theme contexts
├── ivgs-scheduler/        # GPU resource scheduler
├── shared/                # Cross-service libraries
│   ├── providers/         # ABC provider interfaces
│   ├── config.py          # Pydantic settings
│   └── database.py        # Async SQLAlchemy engine
├── configs/               # Service configurations
├── scripts/               # Deployment & maintenance scripts
├── docs/                  # Architecture Decision Records
└── tests/                 # Integration tests
```

## Compliance

- **§7.2 Self-Hosted Mandate:** All AI inference is local. Cloud API keys are prohibited and detected by CI.
- **§19.1 Provider Abstraction:** All AI clients inherit from ABC interfaces (`LLMProvider`, `ImageProvider`, `TTSProvider`, `VideoProvider`, `STTProvider`).
- **§16.1 Authentication:** JWT-based with RBAC (Admin, Editor, Viewer roles).
- **§14.1 Backup:** Automated daily backups with GPG encryption and NAS storage.
- **§13.x Monitoring:** Full observability stack with Prometheus, Grafana, Loki, and AlertManager.

## Environment Variables

See [`.env.template`](.env.template) for all required configuration.

**⚠️ PROHIBITED environment variables (§7.2):**
- `OPENAI_API_KEY` — NEVER
- `ANTHROPIC_API_KEY` — NEVER
- `ELEVENLABS_API_KEY` — NEVER
- `DID_API_KEY` — NEVER

## Testing

```bash
# Unit tests
pytest ivgs-api/tests/ -v
pytest ivgs-workers/tests/ -v
pytest ivgs-scheduler/tests/ -v

# Integration tests
pytest tests/ -v

# Compliance scan
python scripts/compliance_scanner.py /ivgs/

# Lint & type check
black --check .
flake8 .
mypy ivgs-api/ ivgs-workers/
```

## Deployment

See [`docs/deployment/`](docs/deployment/) for per-node deployment guides.

```bash
# Deploy to a specific node
./scripts/deploy-node.sh node-01
```

## License

**Private** — All rights reserved. Not for redistribution.
