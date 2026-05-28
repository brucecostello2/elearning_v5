# Baseline Divergence Report: Sandbox vs. Origin/Main

**Project:** IVGS v5 — Intelligent Video Game Suggestion API  
**Repository:** `brucecostello2/elearning_v5`  
**Comparison:** Sandbox initial commit `634ec66` vs. Origin/main HEAD `b1082d7`  
**Analysis Date:** 2026-05-27  
**Analyst:** Abacus AI Agent  
**Classification:** Pre-Phase 6 Foundation Verification  

---

## 1. Executive Summary

The sandbox workspace at `/home/ubuntu/test_workspace/` was created with a **fresh `git init`** rather than a `git clone` from `origin/main`. As a result, the two histories are **completely disjoint** — `git merge-base` returns no common ancestor (exit code 1). Despite this, file-level forensics confirm the sandbox source code is authentically derived from the same IVGS v5 codebase.

### Key Findings at a Glance

| Finding | Impact |
|---------|--------|
| **No common git ancestor** | Standard `git merge` will fail; `--allow-unrelated-histories` required |
| **112 of 143 common files byte-identical (78.3%)** | Strong confirmation of shared codebase lineage |
| **31 files already modified before first sandbox commit** | Sandbox did NOT start from pristine origin/main |
| **Migration chain diverges at revision 0015** | Database schemas cannot be reconciled by simple replay |
| **Origin's 0016 (power_tdp_w) has no sandbox equivalent** | Schema gap: `gpu_nodes.power_tdp_w` missing from sandbox |
| **GPU subsystem reduced by 306 lines in sandbox** | Functional scope divergence in GPU management |
| **Prompts subsystem reduced by 399 lines in sandbox** | Functional scope divergence in prompt management |
| **conftest.py expanded from 214 → 1,271 lines** | Sandbox built extensive test infrastructure not present in origin |
| **shared/ directory 100% identical (11/11 files)** | Common dependency layer has zero divergence |

### Bottom Line

The sandbox test suite (513 tests, 83.5% coverage) is **valid for the code it tests**, but it tests a **modified version** of the origin/main codebase. Integration back to `origin/main` requires careful reconciliation of 31 source files and a forked migration chain.

---

## 2. Origin/Main Confirmation

### Verification

```
$ git fetch origin main
$ git rev-parse origin/main
b1082d78362d02b15499fc90f35f2eea8fd67efc
```

| Property | Value |
|----------|-------|
| **SHA** | `b1082d78362d02b15499fc90f35f2eea8fd67efc` |
| **Short SHA** | `b1082d7` |
| **Author** | Node-01 Deploy `<deploy@ivgs.local>` |
| **Date** | 2026-05-26 22:51:54 UTC |
| **Subject** | `chore: gitignore rollback-storage and configs/grafana` |
| **Status** | ✅ Confirmed — has not advanced since sandbox creation |

### Origin/Main Initial Commit

| Property | Value |
|----------|-------|
| **SHA** | `0962319f6975d6c9efa6db677514078a1313e519` |
| **Author** | brucecostello2 |
| **Date** | 2026-05-19 20:17:58 UTC |
| **Subject** | `feat: IVGS v5 production-ready initial release` |
| **Total commits** | 85 |

---

## 3. Structural Analysis: Monorepo vs. Subset Extraction

### Origin/Main Is a Full Monorepo

`origin/main` contains the complete IVGS v5 system — six service directories plus infrastructure, documentation, CI/CD, and deployment tooling:

```
origin/main (b1082d7) — 311 non-ivgs-api files
├── .env.node01.template … .env.node06.template
├── .github/                    ← CI/CD workflows, Dependabot config
├── configs/                    ← nginx, postgres, redis, seaweedfs configs
├── docs/                       ← ADRs, runbook, troubleshooting
├── ivgs-api/        (145 files) ← The service under test
├── ivgs-frontend/   (Next.js)  ← Web UI
├── ivgs-infra/      (Docker)   ← Docker compose, monitoring, deployment
├── ivgs-models/     (AI/ML)    ← Model configs, download scripts
├── ivgs-scheduler/  (Python)   ← GPU scheduling, load balancing
├── ivgs-workers/    (Celery)   ← Pipeline tasks, media processing
├── scripts/                    ← Deployment, backup, compliance scripts
├── shared/          (11 files) ← Common Python libraries
├── tests/                      ← Integration, e2e, smoke tests
├── pyproject.toml
├── README.md
└── DEPLOYMENT_SUMMARY.md
```

### Sandbox Is a Subset Extraction

The sandbox contains only the `ivgs-api/` service, the `shared/` dependency layer, and workspace-specific documentation:

```
sandbox (634ec66) — 17 non-ivgs-api files
├── .abacus.donotdelete
├── .gitignore
├── TEST_SUITE_WORKING_SOLUTION.docx
├── TEST_SUITE_WORKING_SOLUTION.md
├── TEST_SUITE_WORKING_SOLUTION.pdf
├── ivgs-api/        (144 files) ← The service under test
├── shared/          (11 files)  ← Common Python libraries
└── pyproject.toml
```

### Implication

The sandbox is a **targeted extraction** of the API service and its shared dependencies, stripped of the frontend, workers, scheduler, infrastructure, and CI/CD components. This is consistent with a development workspace focused specifically on the `ivgs-api` test suite.

---

## 4. File Set Comparison

### Scope: `ivgs-api/` (The Service Under Test)

| Metric | Sandbox `634ec66` | Origin `b1082d7` |
|--------|-------------------|-------------------|
| Total files | 144 | 145 |
| Common files | 143 | 143 |
| Unique files | 1 | 2 |

### Scope: `shared/` (Common Dependency Layer)

| Metric | Sandbox `634ec66` | Origin `b1082d7` |
|--------|-------------------|-------------------|
| Total files | 11 | 11 |
| Common files | 11 | 11 |
| Byte-identical | **11 (100%)** | **11 (100%)** |
| Different | **0** | **0** |

### Scope: Non-ivgs-api (Rest of Monorepo)

| Metric | Sandbox `634ec66` | Origin `b1082d7` |
|--------|-------------------|-------------------|
| Total files | 17 | 311 |
| Description | Workspace docs + pyproject.toml | Full monorepo (6 services + infra) |

### Files Unique to Sandbox

| File | Lines | Purpose |
|------|-------|---------|
| `ivgs-api/tests/test_rollback_probe.py` | 40 | Phase 0.5 test verifying db_session rollback between tests |

### Files Unique to Origin/Main

| File | Lines | Purpose |
|------|-------|---------|
| `ivgs-api/migrations/versions/0015_add_user_is_active.py` | 34 | Adds `is_active` column to `users` table |
| `ivgs-api/migrations/versions/0016_add_power_tdp_w.py` | 43 | Adds `power_tdp_w` column to `gpu_nodes` table |

---

## 5. Content Divergence Analysis

### Overall Identity Metrics

| Scope | Common Files | Byte-Identical | Different | Identity % |
|-------|-------------|----------------|-----------|------------|
| **ivgs-api/** | 143 | 112 | 31 | **78.3%** |
| **shared/** | 11 | 11 | 0 | **100.0%** |
| **Combined** | 154 | 123 | 31 | **79.9%** |

### Diff Magnitude Summary (31 Different Files)

| Metric | Value |
|--------|-------|
| Total lines added (origin → sandbox) | **+1,314** |
| Total lines removed (origin → sandbox) | **-1,055** |
| Net change | **+259 lines** |
| Largest single file change | `tests/conftest.py` (+1,057 net) |
| Largest reduction | `app/api/v1/prompts.py` (-273 net) |

### Categorization of Changes

| Category | Files | Net Lines Changed | Description |
|----------|-------|-------------------|-------------|
| Source code (API, models, schemas, services) | 17 | ~-565 | Bug fixes + structural reductions |
| Migrations (0001-0013 metadata) | 13 | ~-98 | Revision ID chain differences |
| Test infrastructure | 1 | +1,057 | conftest.py massive expansion |
| **Total** | **31** | **+259** | |

---

## 6. Detailed File-by-File Modifications

### Complete Diff Table: All 31 Modified Files

Direction: origin/main (`b1082d7`) → sandbox initial (`634ec66`).  
Positive `+ADD` means lines present in sandbox but not origin. Negative `NET` means sandbox is smaller.

| # | File | Origin Lines | Sandbox Lines | +Added | -Removed | Net |
|---|------|-------------|---------------|--------|----------|-----|
| | **API Layer** | | | | | |
| 1 | `app/api/deps.py` | 29 | 13 | 9 | 25 | **-16** |
| 2 | `app/api/v1/__init__.py` | 102 | 98 | 4 | 8 | **-4** |
| 3 | `app/api/v1/gpus.py` | 280 | 217 | 0 | 63 | **-63** |
| 4 | `app/api/v1/projects.py` | 238 | 238 | 1 | 1 | **0** |
| 5 | `app/api/v1/prompts.py` | 537 | 264 | 6 | 279 | **-273** |
| | **Models** | | | | | |
| 6 | `app/models/gpu_node.py` | 119 | 131 | 17 | 5 | **+12** |
| 7 | `app/models/project.py` | 89 | 94 | 5 | 0 | **+5** |
| 8 | `app/models/prompt.py` | 90 | 83 | 4 | 11 | **-7** |
| 9 | `app/models/quality_score.py` | 61 | 66 | 5 | 0 | **+5** |
| 10 | `app/models/retention_policy.py` | 66 | 69 | 4 | 1 | **+3** |
| 11 | `app/models/user.py` | 58 | 50 | 7 | 15 | **-8** |
| | **Schemas** | | | | | |
| 12 | `app/schemas/gpu.py` | 171 | 121 | 0 | 50 | **-50** |
| 13 | `app/schemas/prompt.py` | 162 | 138 | 1 | 25 | **-24** |
| | **Services** | | | | | |
| 14 | `app/services/gpu_service.py` | 518 | 325 | 2 | 195 | **-193** |
| 15 | `app/services/prompt_service.py` | 456 | 354 | 14 | 116 | **-102** |
| 16 | `app/services/quality_service.py` | 235 | 235 | 2 | 2 | **0** |
| 17 | `app/services/retention_service.py` | 224 | 224 | 4 | 4 | **0** |
| | **Migrations** | | | | | |
| 18 | `migrations/versions/0001_initial_core.py` | 482 | 445 | 37 | 74 | **-37** |
| 19 | `migrations/versions/0002_pipeline_checkpoints.py` | 58 | 54 | 4 | 8 | **-4** |
| 20 | `migrations/versions/0003_gpu_registry.py` | 83 | 76 | 7 | 14 | **-7** |
| 21 | `migrations/versions/0004_retry_tracking.py` | 41 | 40 | 1 | 2 | **-1** |
| 22 | `migrations/versions/0005_worker_heartbeats.py` | 56 | 52 | 4 | 8 | **-4** |
| 23 | `migrations/versions/0006_dead_letter_queue.py` | 62 | 58 | 5 | 9 | **-4** |
| 24 | `migrations/versions/0007_composition_manifests.py` | 54 | 50 | 4 | 8 | **-4** |
| 25 | `migrations/versions/0008_quality_scores.py` | 51 | 47 | 4 | 8 | **-4** |
| 26 | `migrations/versions/0009_render_segments.py` | 53 | 49 | 4 | 8 | **-4** |
| 27 | `migrations/versions/0010_gpu_metrics.py` | 68 | 62 | 37 | 43 | **-6** |
| 28 | `migrations/versions/0011_retention_policies.py` | 48 | 48 | 1 | 1 | **0** |
| 29 | `migrations/versions/0012_storage_quotas.py` | 48 | 47 | 1 | 2 | **-1** |
| 30 | `migrations/versions/0013_backup_records.py` | 65 | 58 | 8 | 15 | **-7** |
| | **Test Infrastructure** | | | | | |
| 31 | `tests/conftest.py` | 214 | 1,271 | 1,112 | 55 | **+1,057** |
| | **TOTALS** | | | **1,314** | **1,055** | **+259** |

### Subsystem Impact Analysis

#### GPU Subsystem (306 lines removed)

| File | Net Change | Significance |
|------|-----------|-------------|
| `app/api/v1/gpus.py` | -63 | API endpoint simplification |
| `app/services/gpu_service.py` | -193 | Service layer reduction — largest single reduction |
| `app/schemas/gpu.py` | -50 | Schema simplification |
| **Total** | **-306** | GPU management significantly stripped down |

#### Prompts Subsystem (399 lines removed)

| File | Net Change | Significance |
|------|-----------|-------------|
| `app/api/v1/prompts.py` | -273 | API endpoint reduction — second largest reduction |
| `app/services/prompt_service.py` | -102 | Service layer reduction |
| `app/schemas/prompt.py` | -24 | Schema trimming |
| **Total** | **-399** | Prompt management significantly stripped down |

#### Models with Column Additions (+30 lines)

| File | Net Change | Likely Cause |
|------|-----------|-------------|
| `app/models/gpu_node.py` | +12 | Additional columns for sandbox testing |
| `app/models/project.py` | +5 | `created_by` FK added (Phase 0a gap) |
| `app/models/quality_score.py` | +5 | `job_id` FK added (Phase 0a gap) |
| `app/models/retention_policy.py` | +3 | `description` column added (Phase 0a gap) |
| **Total** | **+25** | Schema gap closures from Phase 0a audit |

---

## 7. Critical Migration Collision

### The Divergence Point: Revision 0015

Both origin/main and the sandbox independently created migration `0015`, each addressing the same missing `is_active` column on the `users` table, but with **different filenames and different content**.

| Property | Origin/Main | Sandbox |
|----------|-------------|---------|
| **Filename** | `0015_add_user_is_active.py` (singular) | `0015_add_users_is_active.py` (plural) |
| **Lines** | 34 | Similar |
| **Column added** | `users.is_active` (Boolean, NOT NULL, default TRUE) | `users.is_active` (Boolean, NOT NULL, default TRUE) |
| **Docstring** | "Adds the soft-disable flag referenced by app.core.auth" | "Resolves Phase 0a schema audit: column defined in ORM model" |
| **Effect** | Functionally identical | Functionally identical |

### The Missing Migration: Origin's 0016

Origin/main has migration `0016_add_power_tdp_w.py` which adds `power_tdp_w` (Float) to the `gpu_nodes` table. This migration **does not exist in the sandbox**.

> **Impact:** The sandbox's `gpu_nodes` table is missing the `power_tdp_w` column that origin/main expects. Any code on origin/main that references `gpu_nodes.power_tdp_w` will fail against the sandbox database schema.

### Complete Migration Chain Comparison

| Revision | Origin/Main | Sandbox | Status |
|----------|-------------|---------|--------|
| 0001 | `0001_initial_core.py` | `0001_initial_core.py` | ⚠️ Different content |
| 0002 | `0002_pipeline_checkpoints.py` | `0002_pipeline_checkpoints.py` | ⚠️ Different content |
| 0003 | `0003_gpu_registry.py` | `0003_gpu_registry.py` | ⚠️ Different content |
| 0004 | `0004_retry_tracking.py` | `0004_retry_tracking.py` | ⚠️ Different content |
| 0005 | `0005_worker_heartbeats.py` | `0005_worker_heartbeats.py` | ⚠️ Different content |
| 0006 | `0006_dead_letter_queue.py` | `0006_dead_letter_queue.py` | ⚠️ Different content |
| 0007 | `0007_composition_manifests.py` | `0007_composition_manifests.py` | ⚠️ Different content |
| 0008 | `0008_quality_scores.py` | `0008_quality_scores.py` | ⚠️ Different content |
| 0009 | `0009_render_segments.py` | `0009_render_segments.py` | ⚠️ Different content |
| 0010 | `0010_gpu_metrics.py` | `0010_gpu_metrics.py` | ⚠️ Different content |
| 0011 | `0011_retention_policies.py` | `0011_retention_policies.py` | ⚠️ Different content |
| 0012 | `0012_storage_quotas.py` | `0012_storage_quotas.py` | ⚠️ Different content |
| 0013 | `0013_backup_records.py` | `0013_backup_records.py` | ⚠️ Different content |
| 0014 | `0014_fallback_policies.py` | `0014_fallback_policies.py` | ✅ Identical |
| **0015** | **`0015_add_user_is_active.py`** | **`0015_add_users_is_active.py`** | **❌ COLLISION — different files, same purpose** |
| **0016** | **`0016_add_power_tdp_w.py`** | `0016_add_projects_created_by.py` | **❌ DIVERGED — completely different purposes** |
| 0017 | — | `0017_add_quality_scores_job_id.py` | Sandbox-only |
| 0018 | — | `0018_add_retention_policies_description.py` | Sandbox-only |
| 0019 | — | `0019_add_prompt_tags_description.py` | Sandbox-only |
| 0020 | — | `0020_add_backup_records_error_message.py` | Sandbox-only |
| 0021 | — | `0021_add_quality_scores_review_notes.py` | Sandbox-only |
| 0022 | — | `0022_add_storage_quotas_unique_index.py` | Sandbox-only |

### Migration Divergence Diagram

```
                   0001 ──── 0014 (shared, but content differs in 0001-0013)
                               │
               ┌───────────────┼───────────────┐
               │               │               │
          ORIGIN/MAIN      (diverge)        SANDBOX
               │                               │
      0015_add_user_is_active      0015_add_users_is_active
               │                               │
      0016_add_power_tdp_w         0016_add_projects_created_by
               │                               │
             (END)                 0017_add_quality_scores_job_id
                                               │
                                   0018_add_retention_policies_description
                                               │
                                   0019_add_prompt_tags_description
                                               │
                                   0020_add_backup_records_error_message
                                               │
                                   0021_add_quality_scores_review_notes
                                               │
                                   0022_add_storage_quotas_unique_index
                                               │
                                             (HEAD)
```

### Schema Columns: Origin vs. Sandbox

| Column | Table | In Origin? | In Sandbox? | Notes |
|--------|-------|-----------|-------------|-------|
| `is_active` | `users` | ✅ (0015) | ✅ (0015) | Both add it, different migration files |
| `power_tdp_w` | `gpu_nodes` | ✅ (0016) | **❌ MISSING** | **Schema gap** |
| `created_by` | `projects` | ❌ | ✅ (0016) | Sandbox-only schema addition |
| `job_id` | `quality_scores` | ❌ | ✅ (0017) | Sandbox-only schema addition |
| `description` | `retention_policies` | ❌ | ✅ (0018) | Sandbox-only schema addition |
| `description` | `prompt_tags` | ❌ | ✅ (0019) | Sandbox-only schema addition |
| `error_message` | `backup_records` | ❌ | ✅ (0020) | Sandbox-only schema addition |
| `review_notes` | `quality_scores` | ❌ | ✅ (0021) | Sandbox-only schema addition |
| unique index | `storage_quotas` | ❌ | ✅ (0022) | Sandbox-only index |

---

## 8. Timeline Analysis

### 8-Day Gap Between Origin Creation and Sandbox Creation

```
2026-05-19  origin/main initial commit (0962319)
            "feat: IVGS v5 production-ready initial release"
            Author: brucecostello2
            │
            │  85 commits on origin/main over 7 days
            │  (Node-01 Deploy, brucecostello2, dependabot)
            │
2026-05-26  origin/main latest commit (b1082d7)
            "chore: gitignore rollback-storage and configs/grafana"
            Author: Node-01 Deploy
            │
            │  ~3 hours gap
            │
2026-05-27  Sandbox root commit (634ec66) — 02:04:41 UTC
  02:04     "fix: restore full test suite — 153/153 passing"
            Author: Abacus AI Agent
            │
            │  50 commits over ~22 hours
            │  Phases 0-5: Bug fixes, migrations, test buildout
            │
2026-05-27  Sandbox HEAD (e94fbf3) — 23:32:35 UTC
  23:32     "Item 12: SANDBOX_PRESERVATION_VALIDATION.md"
            Author: brucecostello2
```

### Key Observation

The sandbox was created approximately **3 hours after origin/main's last commit**. The source files were extracted from the monorepo at that point, with some modifications already applied before the initial commit. This timing is consistent with a developer extracting the `ivgs-api/` subtree for focused test development work.

---

## 9. Quantitative Metrics

### File Counts

| Metric | Value |
|--------|-------|
| Total files in sandbox initial commit (`634ec66`) | 161 (144 ivgs-api + 17 other) |
| Total files in origin/main (`b1082d7`) | 456 (145 ivgs-api + 311 other) |
| Common `ivgs-api/` files | 143 |
| Byte-identical `ivgs-api/` files | 112 (78.3%) |
| Different `ivgs-api/` files | 31 (21.7%) |
| Common `shared/` files | 11 |
| Byte-identical `shared/` files | 11 (100.0%) |

### Line Change Metrics

| Metric | Value |
|--------|-------|
| Total lines added (origin → sandbox) | +1,314 |
| Total lines removed (origin → sandbox) | -1,055 |
| Net change | +259 lines |
| Largest addition | `tests/conftest.py` (+1,057) |
| Largest removal | `app/api/v1/prompts.py` (-273) |
| Files with zero net change | 4 (`projects.py`, `quality_service.py`, `retention_service.py`, `0011_retention_policies.py`) |

### Subsystem Impact

| Subsystem | Files Changed | Lines Removed | Lines Added | Net |
|-----------|--------------|---------------|-------------|-----|
| GPU (api + schema + service) | 3 | -308 | +2 | **-306** |
| Prompts (api + schema + service) | 3 | -420 | +21 | **-399** |
| Models (6 files) | 6 | -32 | +42 | **+10** |
| Migrations (0001-0013) | 13 | -189 | +91 | **-98** |
| Test infrastructure (conftest.py) | 1 | -55 | +1,112 | **+1,057** |
| Other API/deps | 2 | -33 | +13 | **-20** |

### Git Topology Metrics

| Metric | Sandbox | Origin/Main |
|--------|---------|-------------|
| Root commit SHA | `634ec66` | `0962319` |
| HEAD commit SHA | `e94fbf3` | `b1082d7` |
| Total commits | 50 | 85 |
| Root commit date | 2026-05-27 02:04 UTC | 2026-05-19 20:17 UTC |
| Common ancestor | **NONE** | **NONE** |
| `git merge-base` exit code | **1** (disjoint) | **1** (disjoint) |

---

## 10. Foundation Verification Failures

### Acknowledged Issues

The following issues are documented as **known conditions** arising from the disjoint history:

#### Issue 1: No Git Ancestry (CRITICAL)

- **Expected:** Sandbox history descends from `origin/main` via `git clone` or `git checkout`
- **Actual:** Histories are completely independent (`git merge-base` → exit code 1)
- **Impact:** Standard PR merge workflow will fail
- **Mitigation:** Use `--allow-unrelated-histories` or diff-based integration

#### Issue 2: Pre-Modified Baseline (HIGH)

- **Expected:** Sandbox initial commit matches origin/main's `ivgs-api/` state exactly
- **Actual:** 31 of 143 files were already modified before the first sandbox commit
- **Impact:** Cannot determine which changes were intentional fixes vs. accidental divergence at sandbox creation time
- **Mitigation:** All 31 files have been catalogued with line-level diff statistics

#### Issue 3: Migration Chain Fork (HIGH)

- **Expected:** Sandbox migrations extend origin/main's chain sequentially
- **Actual:** Migration chains diverge at revision 0015 with incompatible content
- **Impact:** Database schemas cannot be merged by simple migration replay
- **Mitigation:** Manual migration reconciliation required — origin's `0015` + `0016` must be integrated with sandbox's `0015` through `0022`

#### Issue 4: Missing `power_tdp_w` Column (MEDIUM)

- **Expected:** All origin/main schema additions present in sandbox
- **Actual:** `gpu_nodes.power_tdp_w` (origin's migration 0016) has no sandbox equivalent
- **Impact:** Any origin/main code referencing this column will fail against sandbox schema
- **Mitigation:** Add the column during Phase 6 integration or create a compatibility migration

#### Issue 5: Functional Scope Reduction (MEDIUM)

- **Expected:** Sandbox has same or expanded functionality vs. origin/main
- **Actual:** GPU subsystem (-306 lines) and Prompts subsystem (-399 lines) significantly reduced
- **Impact:** Some origin/main API capabilities may not be testable in the sandbox
- **Mitigation:** These correspond to the documented low-coverage modules (`prompt_service` 61%, `quality_service` 64%)

### What Is NOT a Problem

| Aspect | Status | Why |
|--------|--------|-----|
| Test suite validity | ✅ | Tests exercise the sandbox codebase correctly |
| Coverage accuracy | ✅ | 83.5% is measured against sandbox source |
| Bug fixes (BUG-001 to BUG-015) | ✅ | Fixes are correct for the code they patch |
| `shared/` dependency layer | ✅ | 100% byte-identical — no divergence |
| Sandbox preservation | ✅ | All 50 commits, 7 tags, and artifacts safely pushed |

---

## 11. Conclusions

### Assessment of Current State

The sandbox workspace is a **functional, well-tested, self-consistent development environment** that was built from the IVGS v5 codebase but is **not git-integrated** with `origin/main`. The 513-test suite and 83.5% coverage are valid metrics for the sandbox's version of the code, but they cannot be directly applied to `origin/main` without reconciliation.

### Assessment of Recoverability

| Aspect | Recoverable? | Effort | Notes |
|--------|-------------|--------|-------|
| Git history integration | ✅ Yes | Medium | `--allow-unrelated-histories` + conflict resolution |
| Source code reconciliation (31 files) | ✅ Yes | Medium | File-by-file review of 31 diffs |
| Migration chain reconciliation | ⚠️ Partial | High | Must reconcile 0015 collision + missing 0016 + sandbox 0016-0022 |
| `power_tdp_w` schema gap | ✅ Yes | Low | Single column addition migration |
| Test suite portability | ⚠️ Partial | High | conftest.py (1,271 lines) may need adaptation for origin/main's schema |
| Full monorepo alignment | ✅ Yes | Medium-High | Sandbox covers only ivgs-api; other 5 services unaffected |

### Recommended Integration Path

1. **Create integration branch** from `origin/main`
2. **Cherry-pick or squash-merge** sandbox commits using `--allow-unrelated-histories`
3. **Reconcile migration 0015** — adopt sandbox's version (same effect, more detailed docstring)
4. **Add origin's 0016** (`power_tdp_w`) into the sandbox chain as 0023 or equivalent
5. **Rebase sandbox 0016-0022** to follow origin's 0016 in the chain
6. **Review 31 source file diffs** — accept intentional fixes, flag unintentional changes
7. **Run full test suite** against reconciled codebase
8. **PR for operator review**

### Final Statement

The sandbox is **preserved, validated, and documented**. The divergence from `origin/main` is **quantified and bounded** — 31 files with 1,314 added and 1,055 removed lines, plus a forked migration chain. Integration is achievable but requires deliberate effort, particularly around the migration collision at revision 0015 and the missing `power_tdp_w` column.

**No recovery actions have been taken.** This report is informational only. All decisions on how to proceed rest with the operator.

---

## Appendix A: Verification Commands

All commands were executed read-only from `/home/ubuntu/test_workspace/` (git root).

```bash
# Confirm origin/main HEAD
git fetch origin main
git rev-parse origin/main  # → b1082d7

# Merge-base test (disjoint history proof)
git merge-base HEAD origin/main  # → exit code 1

# Root commit discovery
git rev-list --max-parents=0 HEAD        # → 634ec66
git rev-list --max-parents=0 origin/main # → 0962319

# File list extraction
git ls-tree -r --name-only 634ec66 -- ivgs-api/ | sort > sandbox_files.txt
git ls-tree -r --name-only b1082d7 -- ivgs-api/ | sort > origin_files.txt

# Set analysis
comm -12 sandbox_files.txt origin_files.txt  # → 143 common
comm -23 sandbox_files.txt origin_files.txt  # → 1 sandbox-only
comm -13 sandbox_files.txt origin_files.txt  # → 2 origin-only

# Byte comparison (for each common file)
git ls-tree 634ec66 "$file" | awk '{print $3}'  # blob hash
git ls-tree b1082d7 "$file" | awk '{print $3}'  # blob hash

# Diff statistics
git diff --numstat b1082d7 634ec66 -- "$file"
```

## Appendix B: Complete List of 112 Identical Files

<details>
<summary>Click to expand — all 112 byte-identical files</summary>

```
ivgs-api/Dockerfile
ivgs-api/alembic.ini
ivgs-api/app/__init__.py
ivgs-api/app/api/__init__.py
ivgs-api/app/api/v1/alerts.py
ivgs-api/app/api/v1/assets.py
ivgs-api/app/api/v1/auth.py
ivgs-api/app/api/v1/backup.py
ivgs-api/app/api/v1/checkpoints.py
ivgs-api/app/api/v1/dlq.py
ivgs-api/app/api/v1/health.py
ivgs-api/app/api/v1/jobs.py
ivgs-api/app/api/v1/languages.py
ivgs-api/app/api/v1/manifests.py
ivgs-api/app/api/v1/nodes.py
ivgs-api/app/api/v1/quality.py
ivgs-api/app/api/v1/quotas.py
ivgs-api/app/api/v1/retention.py
ivgs-api/app/api/v1/rollback.py
ivgs-api/app/api/v1/storyboard.py
ivgs-api/app/api/v1/transcripts.py
ivgs-api/app/api/v1/users.py
ivgs-api/app/api/v1/ws_logs.py
ivgs-api/app/core/__init__.py
ivgs-api/app/core/auth.py
ivgs-api/app/core/rbac.py
ivgs-api/app/core/security.py
ivgs-api/app/middleware/__init__.py
ivgs-api/app/middleware/audit.py
ivgs-api/app/middleware/error_handler.py
ivgs-api/app/middleware/rate_limit.py
ivgs-api/app/models/__init__.py
ivgs-api/app/models/asset.py
ivgs-api/app/models/audit_log.py
ivgs-api/app/models/backup_record.py
ivgs-api/app/models/checkpoint.py
ivgs-api/app/models/composition_manifest.py
ivgs-api/app/models/dead_letter_queue.py
ivgs-api/app/models/fallback_policy.py
ivgs-api/app/models/gpu_metrics_history.py
ivgs-api/app/models/language_variant.py
ivgs-api/app/models/prompt_tag.py
ivgs-api/app/models/render_job.py
ivgs-api/app/models/render_segment.py
ivgs-api/app/models/storage_quota.py
ivgs-api/app/models/storyboard_scene.py
ivgs-api/app/models/task_retry.py
ivgs-api/app/models/transcript.py
ivgs-api/app/models/worker_heartbeat.py
ivgs-api/app/schemas/__init__.py
ivgs-api/app/schemas/asset.py
ivgs-api/app/schemas/auth.py
ivgs-api/app/schemas/base.py
ivgs-api/app/schemas/checkpoint.py
ivgs-api/app/schemas/dlq.py
ivgs-api/app/schemas/language_variant.py
ivgs-api/app/schemas/project.py
ivgs-api/app/schemas/quality.py
ivgs-api/app/schemas/render_job.py
ivgs-api/app/schemas/retention.py
ivgs-api/app/schemas/storyboard.py
ivgs-api/app/schemas/transcript.py
ivgs-api/app/schemas/user.py
ivgs-api/app/scripts/__init__.py
ivgs-api/app/scripts/create_admin.py
ivgs-api/app/scripts/seed_fallback_policies.py
ivgs-api/app/scripts/seed_prompts.py
ivgs-api/app/services/__init__.py
ivgs-api/app/services/asset_service.py
ivgs-api/app/services/auth_service.py
ivgs-api/app/services/checkpoint_service.py
ivgs-api/app/services/dlq_service.py
ivgs-api/app/services/job_service.py
ivgs-api/app/services/language_service.py
ivgs-api/app/services/project_service.py
ivgs-api/app/services/rollback_service.py
ivgs-api/app/services/storyboard_service.py
ivgs-api/app/services/transcript_service.py
ivgs-api/app/services/user_service.py
ivgs-api/config/fallback_policies.yaml
ivgs-api/config/gpu_requirements.yaml
ivgs-api/config/quality_thresholds.yaml
ivgs-api/config/retry_policies.yaml
ivgs-api/config/timeout_defaults.yaml
ivgs-api/main.py
ivgs-api/migrations/env.py
ivgs-api/migrations/versions/0014_fallback_policies.py
ivgs-api/requirements.txt
ivgs-api/seed/default_prompts/animation_generation.j2
ivgs-api/seed/default_prompts/composition.j2
ivgs-api/seed/default_prompts/image_generation.j2
ivgs-api/seed/default_prompts/master.j2
ivgs-api/seed/default_prompts/storyboard_generation.j2
ivgs-api/seed/default_prompts/talking_head.j2
ivgs-api/seed/default_prompts/transcript_refinement.j2
ivgs-api/seed/default_prompts/translation.j2
ivgs-api/seed/default_prompts/tts_voice.j2
ivgs-api/seed/default_prompts/video_generation.j2
ivgs-api/tests/__init__.py
ivgs-api/tests/test_assets.py
ivgs-api/tests/test_auth.py
ivgs-api/tests/test_checkpoint_api.py
ivgs-api/tests/test_dlq_api.py
ivgs-api/tests/test_gpu_api.py
ivgs-api/tests/test_health.py
ivgs-api/tests/test_projects.py
ivgs-api/tests/test_prompts.py
ivgs-api/tests/test_quality_api.py
ivgs-api/tests/test_retention_api.py
ivgs-api/tests/test_storyboard.py
ivgs-api/tests/test_transcripts.py
ivgs-api/tests/test_users.py
```

</details>

## Appendix C: Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| `BASELINE_DIVERGENCE_ANALYSIS.log` | `ivgs-api/` | Raw investigation output (813 lines) |
| `MERGE_BASE_VERIFICATION.log` | `ivgs-api/` | Git merge-base investigation |
| `GIT_HISTORY_INVESTIGATION_REPORT.md` | `ivgs-api/` | Comprehensive git topology analysis |
| `SANDBOX_PRESERVATION_VALIDATION.md` | `ivgs-api/` | 12-item validation checklist (all PASS) |
| `CURRENT_STATE.md` | `ivgs-api/` | System state snapshot |
| `VALIDATION_REPORT.log` | `ivgs-api/` | Running validation log |
| `BUGS_FOUND.md` | `ivgs-api/` | Bug inventory (BUG-001 through BUG-015) |
| `SCHEMA_MIGRATION_GAP_REPORT.md` | `ivgs-api/` | Phase 0a schema audit |

---

*Generated by Abacus AI Agent — 2026-05-27*  
*This report is read-only analysis. No source code, migrations, or remote state was modified.*
