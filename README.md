# IVGS v5 — Instructional Video Generation System

[![CI/CD](https://github.com/brucecostello2/elearning_v5/actions/workflows/ci.yml/badge.svg)](https://github.com/brucecostello2/elearning_v5/actions/workflows/ci.yml)
[![License: Private](https://img.shields.io/badge/License-Private-red.svg)]()

> **Self-hosted, GPU-accelerated instructional video generation platform.**  
> All AI inference runs on-premises — zero cloud API dependencies (§7.2).

---

## Architecture Overview

IVGS v5 runs on a **6-node Proxmox cluster** with dedicated GPU allocation:

| Node | IP | Role | GPU | VRAM |
|------|------|------|-----|------|
| node-01 | 10.10.0.1 | Frontend, API, DB, Redis, Prometheus, Grafana, GPU Scheduler, CI/CD | — (CPU only) | — |
| node-02 | 10.10.0.2 | vLLM (Llama 3.3 70B TP), CogVideoX/Wan2.1 | NVIDIA RTX 6000 Blackwell | 96 GB |
| node-03 | 10.10.0.3 | vLLM (Qwen2.5 72B TP), CogVideoX/Wan2.1 | NVIDIA RTX 6000 Blackwell | 96 GB |
| node-04 | 10.10.0.4 | ComfyUI (FLUX.1 Dev), XTTS v2, WhisperX, LatentSync, vLLM Mistral 24B | NVIDIA RTX 5000 Pro Blackwell | 48 GB |
| node-05 | 10.10.0.5 | ComfyUI (SDXL/SD3.5 fallback), Ollama, FFmpeg | NVIDIA RTX 5080 | 16 GB |
| node-06 | 10.10.0.6 | Remotion renderer, FFmpeg overflow, Celery overflow | Intel B70 Pro | 32 GB |

## 8-Stage Pipeline (§6.1)

1. **Transcript Refinement** — vLLM (Llama 3.3 70B)
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
| Backend API | FastAPI, Python 3.12+, SQLAlchemy, Alembic |
| Workers | Celery 5.4, Redis 7 (broker) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Database | PostgreSQL 15+ |
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
#   Frontend: http://localhost:3001
```

## Project Structure

```
/ivgs/
├── ivgs-api/              # FastAPI backend (Python 3.12+)
│   ├── app/
│   │   ├── api/v1/        # REST + WebSocket endpoints
│   │   ├── models/        # SQLAlchemy ORM models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── services/      # Business logic layer
│   │   ├── middleware/     # CORS, auth, rate limiting
│   │   └── main.py        # FastAPI application entry
│   ├── migrations/        # Alembic migrations (0001-0014)
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
- **§16.1 Authentication:** JWT-based with RBAC (Admin, Operator, Viewer roles).
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
ruff check .
black --check .
mypy ivgs-api/ ivgs-workers/
```

## Deployment

See [`docs/deployment/`](docs/deployment/) for per-node deployment guides.

```bash
# Deploy to a specific node
./scripts/deploy-node.sh node-01
```

## Git Workflow (§15.5)

| Branch | Purpose | Protection |
|--------|---------|-----------|
| `main` | Production-ready; triggers CD pipeline | PR required, CI pass (including compliance audit), no direct push |
| `develop` | Integration branch; triggers CI only | CI pass required |
| `feature/*` | Feature branches from `develop` | No protection; PR into `develop` |
| `hotfix/*` | Emergency fixes from `main` | PR into `main` with CI pass |

### Branch Rules

- All production changes flow through `develop` → PR → `main`
- Hotfixes go directly to `main` via PR (emergency only)
- Feature branches are deleted after merge
- CI runs on all pushes to `main`, `develop`, `feature/**`, and `hotfix/**`
- CD pipeline triggers only on push to `main`

## License

**Private** — All rights reserved. Not for redistribution.
