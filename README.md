# IVGS v5 — Instructional Video Generation System

[![CI/CD](https://github.com/brucecostello2/elearning_v5/actions/workflows/ci.yml/badge.svg)](https://github.com/brucecostello2/elearning_v5/actions/workflows/ci.yml)
[![License: Private](https://img.shields.io/badge/License-Private-red.svg)]()

> **Self-hosted, GPU-accelerated instructional video generation platform.**  
> All AI inference runs on-premises — zero cloud API dependencies (§7.2).

---

## Architecture Overview

IVGS v5 runs on a **6-node Proxmox cluster** with dedicated GPU allocation (§2.2, §3.1–3.2):

#### GPU Allocations (Table 3-2)

| Node | GPU | VRAM | Primary Models / Services |
|------|-----|------|--------------------------|
| node-01 | — (CPU only) | — | Infrastructure only (no GPU) |
| node-02 | NVIDIA RTX 6000 Blackwell | 96 GB | vLLM — Llama 3.3 70B (tensor parallel w/ node-03), CogVideoX 5B, Wan2.1 |
| node-03 | NVIDIA RTX 6000 Blackwell | 96 GB | vLLM — Qwen2.5 72B (tensor parallel w/ node-02), CogVideoX 5B, Wan2.1 |
| node-04 | NVIDIA RTX 5000 Pro Blackwell | 48 GB | ComfyUI (FLUX.1 Dev, AnimateDiff), Coqui XTTS v2, Kokoro TTS, WhisperX, LatentSync, SadTalker, vLLM Mistral 24B |
| node-05 | NVIDIA RTX 5080 | 16 GB | ComfyUI (SDXL / SD3.5 fallback), Ollama (small models), FFmpeg composition |
| node-06 | Intel B70 Pro | 32 GB | Remotion renderer (lower-thirds, animations), FFmpeg overflow, Celery overflow workers |

> NVIDIA driver ≥ 570.x, CUDA ≥ 12.4 (Blackwell). Intel oneAPI 2024.x on node-06.

#### Proxmox VM Specifications (Tables 2-3 / 3-1)

| Node | IP | vCPUs | RAM | Boot Disk | Data Disk | GPU Passthrough |
|------|-----|-------|-----|-----------|-----------|-----------------|
| node-01 | 10.10.0.1 | 8 | 16 GB | 500 GB SSD | — | None |
| node-02 | 10.10.0.2 | 16 | 48 GB | 200 GB SSD | 2 TB NVMe | RTX 6000 Blackwell 96 GB (#1) |
| node-03 | 10.10.0.3 | 16 | 48 GB | 200 GB SSD | 2 TB NVMe | RTX 6000 Blackwell 96 GB (#2) |
| node-04 | 10.10.0.4 | 12 | 32 GB | 200 GB SSD | 1 TB NVMe | RTX 5000 Pro Blackwell 48 GB |
| node-05 | 10.10.0.5 | 8 | 24 GB | 200 GB SSD | 1 TB NVMe | RTX 5080 16 GB |
| node-06 | 10.10.0.6 | 8 | 24 GB | 200 GB SSD | 1 TB NVMe | Intel B70 Pro 32 GB |

#### Node Roles (Table 2-2)

| Node | Services |
|------|----------|
| node-01 | Nginx, Next.js frontend, FastAPI backend, PostgreSQL 17, SeaweedFS (master/volume/filer), Redis, Prometheus, Grafana, GPU Scheduler, CI/CD runner, Celery Beat, Celery default worker |
| node-02 | vLLM (70B+ TP), CogVideoX/Wan2.1 worker, Celery worker, node-exporter, nvidia-gpu-exporter |
| node-03 | vLLM (70B+ TP), CogVideoX/Wan2.1 worker, Celery worker, node-exporter, nvidia-gpu-exporter |
| node-04 | vLLM (mid-size), ComfyUI, Coqui TTS, Kokoro TTS, WhisperX, LatentSync, SadTalker, Celery worker, node-exporter, nvidia-gpu-exporter |
| node-05 | ComfyUI (SDXL/SD3.5), Ollama, FFmpeg worker, Celery worker, node-exporter, nvidia-gpu-exporter |
| node-06 | Remotion renderer, FFmpeg worker, Celery worker, node-exporter, intel-gpu-exporter |

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
| Database | PostgreSQL 17 |
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
