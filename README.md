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

## User Workflow

The 8-stage pipeline runs automatically once triggered, but requires user setup first. The end-to-end video creation workflow is:

```
Create Project → Upload Transcripts → Upload Talking Head →
  (Optional) Customize Prompts → Trigger Pipeline →
  Review Storyboard → Review / Regenerate Media →
  Preview Draft → Download Final Renders
```

| Step | UI Page | API Endpoint | Description |
|------|---------|-------------|-------------|
| 1. Create Project | `/projects/new` | `POST /api/v1/projects` | Set name, description, max runtime, target languages |
| 2. Upload Transcripts | New Project form | `POST /api/v1/projects/{id}/transcripts/upload` | Multi-file PDF/DOCX/TXT; text extracted server-side |
| 3. Reorder Transcripts | New Project form | `POST /api/v1/projects/{id}/transcripts/reorder` | Drag-and-drop sequence ordering |
| 4. Upload Talking Head | New Project form | `POST /api/v1/projects/{id}/upload-talking-head` | MP4/MOV presenter clip, max 500 MB (required) |
| 5. Customize Prompts | `/prompts` or Project → Prompts tab | `POST /api/v1/projects/{id}/prompts` | Override any of 10 prompt types at project or scene level |
| 6. Trigger Pipeline | Project detail page | `POST /api/v1/projects/{id}/trigger` | Queues all 8 pipeline stages for execution |
| 7. Review Storyboard | `/projects/{id}/storyboard` | `GET /api/v1/projects/{id}/scenes` | Edit narration, visuals, duration per scene |
| 8. Review Assets | `/projects/{id}/assets` | `GET /api/v1/projects/{id}/assets` | Browse, filter, and regenerate generated media |
| 9. Preview Draft | `/projects/{id}/preview` | — (video player component) | Review composed video before final render |
| 10. Download Finals | `/projects/{id}/renders` | `GET /api/v1/assets/{id}/download` | Download final renders per target language |

After the pipeline completes, users can iterate — editing storyboard scenes, regenerating individual assets, adjusting prompts — without re-running the entire pipeline.

## Creating a Project (§8.1.2)

All video creation begins at the **New Project** form (`/projects/new`).

#### Required Inputs

| Field | Format | Constraints | Notes |
|-------|--------|------------|-------|
| **Voice Transcripts** | PDF, DOCX, or TXT | At least one file required | Text extracted server-side; multiple files supported with drag-and-drop reordering |
| **Talking Head Clip** | MP4 or MOV | Max 500 MB | Presenter video used for lip-sync in Stage 6 |

#### Optional Inputs

| Field | Format | Notes |
|-------|--------|-------|
| Project Name | Text | Descriptive label for the project |
| Description | Text | Optional project notes |
| Max Runtime | Integer (seconds) | Target duration limit for the generated video |
| Target Languages | Multi-select | Languages for translation & localized TTS (e.g., `en-US`, `es-ES`, `fr-FR`) |
| Existing Storyboard | File upload | Skip AI storyboard generation and use a pre-built scene breakdown |

Once created, the project detail page provides tabbed navigation for: **Transcripts**, **Storyboard**, **Media**, **Audio**, **Talking Head**, **Draft Preview**, **Final Renders**, **Prompts**, **Jobs**, and **Languages** (§8.1.3).

## Prompt Management (§9)

IVGS v5 uses a **3-tier Jinja2 prompt hierarchy** that controls every AI-driven pipeline stage. Prompts can be customized without modifying application code.

#### Hierarchy

```
Global (default) → Project override → Scene override
```

The most specific level wins. If a scene has no override, the project-level prompt is used; if no project override exists, the global default applies.

#### 10 Prompt Types (Table 9-2)

| Type | Controls |
|------|----------|
| `master` | Master orchestration / system prompt |
| `transcript_refinement` | How raw transcripts are cleaned and structured (Stage 1) |
| `storyboard_generation` | How scenes are broken down from transcripts (Stage 2) |
| `image_generation` | Visual asset prompts for FLUX.1/SDXL (Stage 3) |
| `video_generation` | Video clip generation via CogVideoX/Wan2.1 (Stage 3) |
| `animation_generation` | AnimateDiff animation prompts (Stage 3) |
| `tts_voice` | Voice direction for Coqui XTTS / Kokoro TTS (Stage 5) |
| `talking_head` | Presenter integration for LatentSync/SadTalker (Stage 6) |
| `composition` | Final video composition instructions (Stages 7–8) |
| `translation` | Multi-language translation prompts |

#### Key Features

- **Jinja2 Templates** — Prompts support variable interpolation (up to 50,000 characters). Template variables include `{{ project_name }}`, `{{ scene_number }}`, `{{ narration_text }}`, `{{ target_language }}`, and more (§9.4).
- **Prompt Playground** — Test any prompt against the self-hosted LLM (default: Llama 3.3 70B) before applying it to a project. Accessible from the `/prompts` dashboard page or via `POST /api/v1/prompts/test`.
- **Version History & Rollback** — Every prompt edit creates a new version. Previous versions can be restored via `POST /api/v1/prompts/{id}/restore`.
- **Prompt Library** — Save and share effective prompts across projects via the Library panel.

#### Prompt API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/v1/prompts` | List all global prompts |
| `POST` | `/api/v1/prompts` | Create / update a global prompt version |
| `POST` | `/api/v1/prompts/{id}/restore` | Restore a previous prompt version |
| `POST` | `/api/v1/prompts/test` | Prompt Playground — test against self-hosted LLM |
| `GET` | `/api/v1/projects/{id}/prompts` | List project prompts with effective source (global/project/scene) |
| `POST` | `/api/v1/projects/{id}/prompts` | Create a project-level prompt override |
| `POST` | `/api/v1/projects/{id}/scenes/{sid}/prompts` | Create a scene-level prompt override |

Default global prompts are seeded from Jinja2 templates in `ivgs-api/seed/default_prompts/` during initial setup (`seed_prompts.py`).

#### Frontend

The Prompt Management dashboard is at `/prompts` and includes: **PromptManager** (list/CRUD), **PromptEditor** (Jinja2 editor), **PromptPlayground** (live testing), **PromptHistory** (version browser), and **PromptLibrary** (shared templates).

## Asset Management (§10)

All media files — uploaded source materials and AI-generated outputs — are stored in **SeaweedFS** with a 4-tier storage architecture.

#### Upload Workflows

| Workflow | Endpoint | Formats | Limits |
|----------|----------|---------|--------|
| **Transcript Upload** | `POST /api/v1/projects/{id}/transcripts/upload` | PDF, DOCX, TXT | Multi-file; text extracted server-side |
| **Talking Head Upload** | `POST /api/v1/projects/{id}/upload-talking-head` | MP4, MOV | Max 500 MB |
| **General Asset Upload** | `POST /api/v1/projects/{id}/assets/upload` | Any media type | Filterable by scene and language |

The frontend provides a drag-and-drop **AssetUploader** component with file validation and a **TranscriptEditor** with side-by-side diff view (original vs. AI-refined text).

#### SeaweedFS Storage Tiers

| Tier | Storage | Use Case |
|------|---------|----------|
| **Hot** | NVMe | Active project assets, currently rendering |
| **Warm** | SSD | Recent projects, frequently accessed |
| **Cold** | HDD | Archived projects, infrequent access |
| **Archive** | Compressed HDD | Long-term retention |

Files are organized as `/projects/{id}/{type}/{scene_id}/{language}/` with SHA-256 content-addressed deduplication.

#### Asset API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/projects/{id}/assets/upload` | Upload asset to SeaweedFS |
| `GET` | `/api/v1/projects/{id}/assets` | List assets (filter by scene_id, asset_type, language_code) |
| `GET` | `/api/v1/assets/{id}/download` | Download asset (proxy from SeaweedFS) |
| `POST` | `/api/v1/assets/{id}/regenerate` | Queue asset regeneration via pipeline |
| `DELETE` | `/api/v1/assets/{id}` | Delete asset from SeaweedFS and database |

#### Storyboard Editing

After the pipeline generates scenes, users can edit them individually:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/v1/projects/{id}/scenes` | List all scenes |
| `PATCH` | `/api/v1/projects/{id}/scenes/{sid}` | Edit narration, visual description, media type, duration |
| `POST` | `/api/v1/projects/{id}/scenes/reorder` | Bulk reorder scenes |
| `POST` | `/api/v1/projects/{id}/scenes/{sid}/regenerate` | Queue LLM-based scene regeneration |

## API Reference

All endpoints are served under `/api/v1/`. Full OpenAPI documentation is available at `http://localhost:8001/docs` when the API is running.

#### Projects (7 endpoints)

```
GET    /api/v1/projects                              # List all projects
POST   /api/v1/projects                              # Create project
GET    /api/v1/projects/{id}                          # Get project details
PUT    /api/v1/projects/{id}                          # Update project metadata
DELETE /api/v1/projects/{id}                          # Delete project and all assets
POST   /api/v1/projects/{id}/trigger                  # Trigger full pipeline execution
POST   /api/v1/projects/{id}/upload-talking-head      # Upload presenter clip
```

#### Transcripts (5 endpoints)

```
POST   /api/v1/projects/{id}/transcripts/upload       # Upload transcript files (PDF/DOCX/TXT)
GET    /api/v1/projects/{id}/transcripts              # List transcripts (ordered by sequence)
PATCH  /api/v1/projects/{id}/transcripts/{tid}        # Update refined text
POST   /api/v1/projects/{id}/transcripts/reorder      # Bulk reorder transcripts
DELETE /api/v1/projects/{id}/transcripts/{tid}        # Delete transcript
```

#### Storyboard / Scenes (4 endpoints)

```
GET    /api/v1/projects/{id}/scenes                   # List scenes
PATCH  /api/v1/projects/{id}/scenes/{sid}             # Edit scene (narration, visuals, duration)
POST   /api/v1/projects/{id}/scenes/reorder           # Bulk reorder scenes
POST   /api/v1/projects/{id}/scenes/{sid}/regenerate  # Queue LLM regeneration
```

#### Assets (5 endpoints)

```
POST   /api/v1/projects/{id}/assets/upload            # Upload asset to SeaweedFS
GET    /api/v1/projects/{id}/assets                   # List assets (with filters)
GET    /api/v1/assets/{id}/download                   # Download asset
POST   /api/v1/assets/{id}/regenerate                 # Queue asset regeneration
DELETE /api/v1/assets/{id}                            # Delete asset
```

#### Prompts (7 endpoints)

```
GET    /api/v1/prompts                                # List global prompts
POST   /api/v1/prompts                                # Create/update global prompt
POST   /api/v1/prompts/{id}/restore                   # Restore previous version
POST   /api/v1/prompts/test                           # Prompt Playground (test against LLM)
GET    /api/v1/projects/{id}/prompts                  # List project prompts (with effective source)
POST   /api/v1/projects/{id}/prompts                  # Create project-level override
POST   /api/v1/projects/{id}/scenes/{sid}/prompts     # Create scene-level override
```

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

# 7. Create your first project
#   Navigate to http://localhost:3001
#   Click "New Project"
#   Upload at least one transcript file (PDF/DOCX/TXT)
#   Upload a talking head clip (MP4/MOV, max 500 MB)
#   Set target languages and click "Create Project"
#   Trigger the pipeline from the project detail page
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
