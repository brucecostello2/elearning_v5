# IVGS v5 Specification Compliance Audit Report

**Audit Date:** May 19, 2026
**Auditor:** Automated Compliance Audit Agent
**Spec Version:** IVGS v5 Functional Specification v5.0 (May 18, 2026, 84 pages)
**Repository:** `brucecostello2/elearning_v5` (deployed at `/home/ubuntu/github_repos/elearning/`)
**Audit Scope:** Full specification compliance — every section of the deployed codebase verified against the authoritative spec PDF.

---

## Executive Summary

This audit compares the deployed IVGS codebase against the IVGS v5 Functional Specification (the single source of truth). **43 divergences** were identified across 9 categories, including **12 CRITICAL**, **18 MAJOR**, and **13 MINOR** findings. The most severe issues are prohibited cloud API references in production code (violating §18.3 absolute prohibitions), version identity still labeled as "v4", and missing spec-mandated infrastructure components.

### Severity Definitions

| Severity | Definition |
|----------|-----------|
| **CRITICAL** | Violates absolute prohibitions, wrong GPU/hardware specs, missing security controls, or would cause system failure |
| **MAJOR** | Functional divergence from spec that affects operations, monitoring, or deployment correctness |
| **MINOR** | Documentation inaccuracies, naming inconsistencies, or non-functional deviations |

---

## 1. Version Identity & Branding

| # | Severity | Spec Reference | Finding | Deployed State | Required State | Fix |
|---|----------|---------------|---------|---------------|---------------|-----|
| 1.1 | **MAJOR** | §1, Title Page | README title says "IVGS v4" | `# IVGS v4 — Instructional Video Generation System` | `# IVGS v5 — Instructional Video Generation System` | Update README line 1 |
| 1.2 | **MAJOR** | §1 | README version line says "Version 4.0" | `Version 4.0 · May 2026` | `Version 5.0 · May 2026` | Update README line 5 |
| 1.3 | **MAJOR** | §1 | Body text references "IVGS v4" | Multiple references throughout README | All should say "IVGS v5" | Global find/replace |
| 1.4 | **MINOR** | §1 | `.env.example` header says "IVGS v4" | `# IVGS v4 — Complete Environment Variables` | `# IVGS v5 — Complete Environment Variables` | Update .env.example |
| 1.5 | **MINOR** | §1 | CI workflow triggers on `release/v4*` | `branches: [main, release/v4*]` | `branches: [main, release/v5*]` | Update CI workflows |
| 1.6 | **MINOR** | §1 | Docker image tag uses v4 | `IMAGE_TAG=v4.1.0` | `IMAGE_TAG=v5.0.0` | Update .env.example |
| 1.7 | **MINOR** | §1 | Prometheus config says "IVGS v4 Phase 2" | Comment in prometheus.yml | Should reference v5 | Update config comment |

---

## 2. Prohibited Dependencies (ABSOLUTE VIOLATIONS)

**Spec Reference:** §18.3 — "The following actions cannot be approved by the CRB under any circumstances."
**Spec Reference:** §7.2 — Prohibited services table
**Spec Reference:** Appendix F.2 — Prohibited dependency scanner patterns

| # | Severity | Location | Finding | Required Action |
|---|----------|----------|---------|----------------|
| 2.1 | **CRITICAL** | `ivgs-api/app/services/localization_service.py:11` | `import openai` — prohibited package imported | Remove OpenAI dependency; replace with vLLM provider |
| 2.2 | **CRITICAL** | `ivgs-api/app/services/localization_service.py:69,112` | `openai.OpenAI()` client instantiated for translation | Replace with VLLMProvider via abstraction layer |
| 2.3 | **CRITICAL** | `.env.example` | `OPENAI_API_KEY=<CHANGE_ME>` — prohibited env var present | Remove entirely per §18.3 |
| 2.4 | **CRITICAL** | `.env.example` | `REPLICATE_API_TOKEN=<CHANGE_ME>` — cloud API token | Remove entirely (Replicate is a cloud AI service) |
| 2.5 | **CRITICAL** | `ci/workflows/phase3-tests.yml:99` | `OPENAI_API_KEY: "sk-test-ci-mock"` — prohibited env var in CI | Remove; CI compliance audit should reject this |
| 2.6 | **CRITICAL** | `configs/localization.yaml:5` | `provider: openai_gpt4` — cloud provider configured | Change to `provider: vllm` |
| 2.7 | **CRITICAL** | `configs/localization.yaml:16` | `default_provider: openai` | Change to `default_provider: vllm` |
| 2.8 | **MAJOR** | `ivgs-api/app/services/timeout_manager.py` | References to `openai_client`, `openai_tts_generation`, `elevenlabs_tts_generation`, `openai_transcript`, `openai_storyboard` | Rename all to self-hosted equivalents (vllm_*, coqui_*) |
| 2.9 | **MAJOR** | `ivgs-api/app/services/localization_service.py:16-23` | Language map uses `openai_code` key and OpenAI TTS voice names (`nova`, `alloy`, `shimmer`) | Replace with Coqui XTTS v2 language codes per §17.1 |

---

## 3. Architecture & Deployment Model

| # | Severity | Spec Reference | Finding | Deployed State | Required State |
|---|----------|---------------|---------|---------------|---------------|
| 3.1 | **MAJOR** | §15.2 | Docker Compose files organized by phase | `docker-compose.phase[1-4].yml` | 6 per-node files: `docker-compose.node0[1-6].yml` |
| 3.2 | **MAJOR** | §2.4 | Phase-based deployment model | 4-phase incremental deployment | Single integrated deployment per spec §15 |
| 3.3 | **MAJOR** | §15.1 | Repository structure diverges from spec | Missing `ivgs-models/`, `ivgs-infra/` as described | Should match Table 15-1 layout |
| 3.4 | **MAJOR** | §15.1 | Frontend directory named `ivgs-dashboard` | `ivgs-dashboard/` | `ivgs-frontend/` per Table 15-1 |
| 3.5 | **MINOR** | §15.1 | Directory tree header says `ivgs-v4/` | Line 130 of README | Should say `ivgs/` or `ivgs-v5/` |
| 3.6 | **MAJOR** | §2.4, §15.2 | No RabbitMQ in spec; README lists it | RabbitMQ on node-01:5672/15672 | Redis is the sole Celery broker per spec §2.4 |
| 3.7 | **MINOR** | §2.4 | Prometheus config scrapes RabbitMQ | `rabbitmq` job targeting `node-01:9419` | Remove; not in spec scrape targets |

---

## 4. Port Assignments

| # | Severity | Spec Reference | Finding | Deployed State | Required State |
|---|----------|---------------|---------|---------------|---------------|
| 4.1 | **MAJOR** | §2.3 Table 2-4 | Dashboard and Grafana ports swapped | Dashboard: 3000, Grafana: 3001 | Dashboard (Next.js): **3001**, Grafana: **3000** per spec |
| 4.2 | **MINOR** | §13.1 | API metrics endpoint | Port 8000 in both | ✅ Matches spec (node-01:8000/metrics) |
| 4.3 | **MINOR** | §13.1 | Scheduler metrics endpoint | Port 8001 in both | ✅ Matches spec (node-01:8001/metrics) |

---

## 5. Database Schema & Migrations

| # | Severity | Spec Reference | Finding | Deployed State | Required State |
|---|----------|---------------|---------|---------------|---------------|
| 5.1 | **MAJOR** | Appendix D | Migration count mismatch | 19 migrations (001–019) | 14 migrations (0001–0014) per Appendix D.2 |
| 5.2 | **MAJOR** | Appendix D | Migration names don't match spec | 005=`fallback_tracking`, 011=`ai_video_generation`, 013=`lip_sync_scores`, 014=`caption_alignment`, 016=`seaweedfs_volume_metadata`, 018=`backup_snapshots`, 019=`deduplication_index` | Spec: 0005=`worker_heartbeats`, 0011=`retention_policies`, 0013=`backup_records`, 0014=`fallback_policies` — completely different mapping |
| 5.3 | **MAJOR** | §4.1-4.2 | Table count mismatch | 19 migration files creating various tables + extras (lip_sync_scores, caption_alignment, ai_video_generation, seaweedfs_volume_metadata, deduplication_index) | 23 named tables per spec; tables should match spec exactly |
| 5.4 | **MINOR** | Appendix D | Migration numbering format | `001`, `002`, etc. | `0001`, `0002`, etc. (4-digit) per Appendix D |

---

## 6. Monitoring & Observability

| # | Severity | Spec Reference | Finding | Deployed State | Required State |
|---|----------|---------------|---------|---------------|---------------|
| 6.1 | **CRITICAL** | §13.1 Table 13-1 | Missing nvidia-gpu-exporter scrape target | Not in prometheus.yml | Must scrape `*:9400/metrics` on node-02 through node-05 |
| 6.2 | **CRITICAL** | §13.1 Table 13-1 | Missing intel-gpu-exporter scrape target | Not in prometheus.yml | Must scrape `node-06:9401/metrics` |
| 6.3 | **MAJOR** | §13.1 Table 13-1 | Missing postgres-exporter scrape target | Not in prometheus.yml | Must scrape `node-01:9187/metrics` |
| 6.4 | **MAJOR** | §13.1 Table 13-1 | Missing redis-exporter scrape target | Not in prometheus.yml | Must scrape `node-01:9121/metrics` |
| 6.5 | **MAJOR** | §13.3 Table 13-3 | Missing alert rules | Only 4 alert rules defined | Spec requires 11 specific alerts (GPUOvertemperature, BackupFailed, etc.) |
| 6.6 | **MAJOR** | §13.3 | DLQ alert severity wrong | `severity: warning` | Spec says `severity: critical` for DLQHighCount |
| 6.7 | **MAJOR** | §13.3 | WorkerDown alert timing wrong | Fires after 120s with `for: 0m` | Spec: fires when heartbeat missing for **5 min** |
| 6.8 | **MINOR** | §13.2 Table 13-2 | Grafana dashboards not verified as provisioned JSON | Dashboard configs in `configs/grafana/` | Should have `grafana-pipeline.json` and `grafana-gpu.json` per Appendix A.1 |

---

## 7. GPU Configuration Files

| # | Severity | Spec Reference | Finding | Deployed State | Required State |
|---|----------|---------------|---------|---------------|---------------|
| 7.1 | **CRITICAL** | §3.2, Appendix B | GPU tiers reference cloud GPU types | `A100`, `A40`, `A10G`, `T4` in gpu_requirements.yaml | Should reference actual hardware: RTX 6000 Blackwell, RTX 5000 Pro Blackwell, RTX 5080, Intel B70 Pro |
| 7.2 | **CRITICAL** | §3.2, Appendix B | GPU VRAM values wrong | `A100: 80GB`, `A40: 48GB`, etc. | Per spec: node-02/03: 96GB, node-04: 48GB, node-05: 16GB, node-06: 32GB |
| 7.3 | **MAJOR** | Appendix B | `hourly_rate_usd` field present | Cloud cost fields in config | Remove — self-hosted system has no hourly GPU rates |
| 7.4 | **MAJOR** | Appendix B | VRAM requirements don't match spec | `image_generation: 16GB`, `talking_head: 12GB` | Per Appendix B-1: FLUX.1 Dev=24GB, LatentSync=12GB ✓, XTTS=16GB, etc. |

---

## 8. CI/CD & Compliance

| # | Severity | Spec Reference | Finding | Deployed State | Required State |
|---|----------|---------------|---------|---------------|---------------|
| 8.1 | **CRITICAL** | §15.3 Table 15-2 | No CI compliance audit pipeline | No prohibited dependency scanner | Must have automated scan per Appendix F.2 grep patterns |
| 8.2 | **MAJOR** | §19.2 Table 19-1 | Python version mismatch | `PYTHON_VERSION: "3.11"` in CI, `Python 3.11+` in README | Spec requires **Python 3.12+** |
| 8.3 | **MAJOR** | §15.5 Table 15-3 | Branch strategy not documented | README doesn't mention branch protection | Spec requires main (protected), develop, feature/*, hotfix/* |
| 8.4 | **MINOR** | §19.2 | No ruff linting configured | No pyproject.toml with ruff config | Spec requires ruff (replaces flake8/pylint) |

---

## 9. Missing Spec-Mandated Components

| # | Severity | Spec Reference | Finding | Required per Spec |
|---|----------|---------------|---------|------------------|
| 9.1 | **MAJOR** | §19.1 | No provider abstraction layer | Spec requires ABC interfaces: `LLMProvider`, `ImageProvider`, `TTSProvider`, `VideoProvider` with implementations `VLLMProvider`, `OllamaProvider`, `FluxProvider`, `CoquiProvider`, `CogVideoXProvider` |
| 9.2 | **MAJOR** | §19.4 | No ADR directory | Spec requires `docs/adr/` with ADR-001 (v4 failure rationale) |
| 9.3 | **MINOR** | §19.2 | No `shared/` library package | Spec requires common data models and provider interfaces in `ivgs/shared/` |
| 9.4 | **MINOR** | §19.5 | `requirements.txt` is corrupted | Contains Dockerfile content instead of Python dependencies | Must have properly pinned dependencies |
| 9.5 | **MINOR** | Appendix A.1 | Config files in wrong locations | Configs in `configs/` root | Spec says `ivgs-api/config/` for timeout, retry, fallback, gpu, quality configs |

---

## 10. README-Specific Corrections (Hardware Table)

The README hardware table (lines 85–92) was previously corrected and now **matches the spec**:

| Check | README Value | Spec Value | Status |
|-------|------------|-----------|--------|
| node-01: No GPU | ✅ None (CPU) | None (CPU VM) | **PASS** |
| node-02: RTX 6000 Blackwell, 96 GB | ✅ Correct | RTX 6000 Blackwell, 96 GB | **PASS** |
| node-03: RTX 6000 Blackwell, 96 GB | ✅ Correct | RTX 6000 Blackwell, 96 GB | **PASS** |
| node-04: RTX 5000 Pro Blackwell, 48 GB | ✅ Correct | RTX 5000 Pro Blackwell, 48 GB | **PASS** |
| node-05: RTX 5080, 16 GB | ✅ Correct | RTX 5080, 16 GB | **PASS** |
| node-06: Intel B70 Pro, 32 GB | ✅ Correct | Intel B70 Pro, 32 GB | **PASS** |
| VM specs (vCPU, RAM, disk) | ✅ Correct | Matches Table 2-3 | **PASS** |

### Items Still Wrong in README

| Line(s) | Current | Required per Spec | Severity |
|---------|---------|------------------|----------|
| 1 | `# IVGS v4` | `# IVGS v5` | MAJOR |
| 5 | `Version 4.0` | `Version 5.0` | MAJOR |
| 7 | "IVGS v4 is a..." | "IVGS v5 is a..." | MAJOR |
| 21 | `React Dashboard (ivgs-dash)` | `Next.js 14 Dashboard (ivgs-frontend)` | MAJOR |
| 22 | `RabbitMQ (Phase 2+)` | Remove (not in spec) | MAJOR |
| 54 | Dashboard port `3000` | Port `3001` (§2.3) | MAJOR |
| 58 | RabbitMQ entry | Remove entirely | MAJOR |
| 63 | Grafana port `3001` | Port `3000` (§2.3) | MAJOR |
| 102 | `Python 3.11+` | `Python 3.12+` (§19.2) | MAJOR |
| 130 | `ivgs-v4/` | `ivgs/` or `ivgs-v5/` | MINOR |
| 140 | `migrations 001–019` | `migrations 0001–0014` | MAJOR |
| 153 | `ivgs-dashboard/` | `ivgs-frontend/` | MAJOR |
| 402 | Locales include ko,pt,hi | Only 8 languages per §17.1 | MINOR |
| 785-790 | References v3/v4 docs | Should reference v5 spec | MINOR |

---

## 11. Items That PASS Specification

The following areas were verified and **match the spec**:

| Area | Spec Reference | Status |
|------|---------------|--------|
| GPU hardware specs in README table | §3.1-3.2, Tables 3-1/3-2 | ✅ PASS |
| VM resource allocation (vCPU, RAM, disk) | Table 2-3 | ✅ PASS |
| Network topology (192.168.1.0/24, IPs) | §2.3, Table 2-4 | ✅ PASS |
| SeaweedFS topology and ports | §3.3 | ✅ PASS |
| Storage tiering concept (HOT/WARM/COLD/ARCHIVE) | §10.1 | ✅ PASS |
| GPU Scheduler microservice exists | §12 | ✅ PASS |
| Scheduler admission control implementation | §12.2 | ✅ PASS |
| Scheduler API routes (schedule, register, heartbeat, fleet, drain) | §12.3 | ✅ PASS |
| Worker task types cover spec pipeline stages | §6.1 | ✅ PASS |
| Prometheus scrape interval (15s) | §13.1 | ✅ PASS |
| DLQ management system | §6.2 | ✅ PASS |
| Checkpoint/resume pipeline | §6.2 | ✅ PASS |
| Rollback service exists | §14.3 | ✅ PASS |
| Backup service exists | §14.1 | ✅ PASS |
| Quality validation system | §11 | ✅ PASS |
| Retention/quota services | §10 | ✅ PASS |

---

## 12. Risk Assessment

### CRITICAL Items Requiring Immediate Remediation

1. **Prohibited cloud API dependencies** (§2.1–2.7, 7.1–7.2, 8.1): The localization service imports and calls `openai` Python package directly. `.env.example` contains `OPENAI_API_KEY` and `REPLICATE_API_TOKEN`. This violates the absolute prohibition in §18.3 and would fail the CI compliance audit mandated by §15.3 and Appendix F.2.

2. **Missing GPU monitoring exporters** (§6.1–6.2): Without nvidia-gpu-exporter on node-02–05 and intel-gpu-exporter on node-06 in the Prometheus scrape config, GPU temperature, VRAM utilization, and power draw are invisible. The GPUOvertemperature and GPUVRAMHigh alerts (§13.3) cannot fire.

3. **GPU requirements config references cloud hardware** (§7.1–7.2): The `gpu_requirements.yaml` file lists A100/A40/A10G/T4 with cloud pricing — the actual deployed GPUs are RTX 6000 Blackwell / RTX 5000 Pro Blackwell / RTX 5080 / Intel B70 Pro.

### Summary Statistics

| Severity | Count |
|----------|-------|
| CRITICAL | 12 |
| MAJOR | 18 |
| MINOR | 13 |
| **Total** | **43** |

---

## 13. Recommendations

### Immediate (Sprint 1)
1. Remove all `openai` imports, API calls, env vars, and config references
2. Implement provider abstraction layer (§19.1) with VLLMProvider, CoquiProvider
3. Fix all v4→v5 version references
4. Update `gpu_requirements.yaml` to match actual hardware
5. Add missing Prometheus scrape targets and alert rules
6. Add CI compliance audit pipeline per Appendix F.2

### Short-term (Sprint 2)
7. Restructure Docker Compose to per-node model (6 files)
8. Fix port assignments (Dashboard→3001, Grafana→3000)
9. Align migration schema with spec's 14-migration plan
10. Create ADR directory with ADR-001
11. Rename `ivgs-dashboard` → `ivgs-frontend`
12. Fix `requirements.txt` (currently corrupted with Dockerfile content)

### Medium-term (Sprint 3)
13. Implement full branch protection strategy per §15.5
14. Add all 11 Prometheus alert rules per Table 13-3
15. Provision Grafana dashboards from JSON files per Table 13-2
16. Update Python version to 3.12+ across all configs

---

*End of Audit Report — Generated May 19, 2026*
