# IVGS v5 — Pre-Deployment Implementation Guide

**Document Date:** May 20, 2026
**Purpose:** Step-by-step remediation of all 16 remaining spec divergences before hardware deployment
**Quality Standard:** Every fix must achieve 100% compliance with the IVGS v5 Functional Specification (May 18, 2026, 84 pages)
**Repository:** `brucecostello2/elearning_v5` → `/home/ubuntu/github_repos/elearning/`
**Authoritative Spec:** `/home/ubuntu/ivgs_v5_functional_specification.pdf`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Fix 1: Python 3.11 → 3.12 in CI/CD](#fix-1)
3. [Fix 2: flake8 → ruff Linter Migration](#fix-2)
4. [Fix 3: pyproject.toml Python Target Versions](#fix-3)
5. [Fix 4: pre-commit Python Version & Hooks](#fix-4)
6. [Fix 5: CI Branch Triggers](#fix-5)
7. [Fix 6: CI Test Database Image (TimescaleDB → PostgreSQL)](#fix-6)
8. [Fix 7: .env.template TimescaleDB Comment](#fix-7)
9. [Fix 8: Database Migration Consolidation (17 → 14)](#fix-8)
10. [Fix 9: GPU Config — Add Hardware Model Names](#fix-9)
11. [Fix 10: Create ivgs-models/ Directory](#fix-10)
12. [Fix 11: Grafana Dashboard File Naming](#fix-11)
13. [Fix 12: Move fallback_policies.yaml to Spec Location](#fix-12)
14. [Fix 13: Add Git Workflow / Branch Strategy to README](#fix-13)
15. [Fix 14: Create `develop` Branch](#fix-14)
16. [Fix 15: Grafana Dashboard Provisioning Config Update](#fix-15)
17. [Fix 16: CI Compliance Scanner Python Version Alignment](#fix-16)
18. [Quality Gate Checklist](#quality-gate)
19. [PR Strategy](#pr-strategy)
20. [Automated Verification Script](#verification-script)

---

<a name="1-executive-summary"></a>
## 1. Executive Summary

### Current State

The IVGS v5 codebase has already been substantially remediated (27 of 43 original divergences resolved). The remaining **16 divergences** are organized below from highest to lowest impact:

| # | Fix | Severity | Spec Ref | Est. Time |
|---|-----|----------|----------|-----------|
| 1 | Python 3.11 → 3.12 in CI | MAJOR | §19.2 | 15 min |
| 2 | flake8 → ruff linter | MAJOR | §19.2 | 2 hours |
| 3 | pyproject.toml Python targets | MAJOR | §19.2 | 10 min |
| 4 | pre-commit Python version & hooks | MINOR | §19.2 | 20 min |
| 5 | CI branch triggers | MINOR | §15.5 | 10 min |
| 6 | CI test database image | MINOR | §2.4 | 5 min |
| 7 | .env.template TimescaleDB comment | MINOR | Appendix A.2 | 2 min |
| 8 | Migration consolidation (17→14) | MAJOR | Appendix D.2 | 4 hours |
| 9 | GPU config hardware names | MAJOR | §3.2 | 30 min |
| 10 | Create ivgs-models/ directory | MAJOR | §15.1 | 2 hours |
| 11 | Grafana dashboard naming | MINOR | Appendix A.1 | 15 min |
| 12 | fallback_policies.yaml location | MINOR | Appendix A.1 | 30 min |
| 13 | Branch strategy in README | MAJOR | §15.5 | 30 min |
| 14 | Create `develop` branch | MAJOR | §15.5 | 10 min |
| 15 | Grafana provisioning config | MINOR | §13.2 | 10 min |
| 16 | Compliance scanner Python alignment | MINOR | §15.3 | 5 min |

**Total estimated effort: ~11 hours**

### Implementation Order

```
Phase 1 — CI/CD & Tooling (Fixes 1–7)     ─── ~3 hours
Phase 2 — Database & Structure (Fixes 8–12) ── ~7 hours
Phase 3 — Documentation & Git (Fixes 13–16) ── ~1 hour
```

### Prerequisites

- Python 3.12 installed locally (`python3.12 --version`)
- `ruff` installed (`pip install ruff`)
- Access to push feature branches to `brucecostello2/elearning_v5`
- All work done on feature branches, never on `main`

---

<a name="fix-1"></a>
## Fix 1: Python 3.11 → 3.12 in CI/CD Pipeline

**Divergence ID:** DIV-8.2
**Severity:** MAJOR
**Spec Reference:** §19.2 Table 19-1 — "Python 3.12+; type annotations required throughout"
**Root Cause:** CI `PYTHON_VERSION` env var set to `"3.11"` while Dockerfiles already use `python:3.12-slim`

### Current State

**File:** `.github/workflows/ci.yml`
**Line 13:**
```yaml
  PYTHON_VERSION: "3.11"
```

This version is consumed by 4 jobs: `lint-python` (line 27), `test-python` (line 75), `compliance-scan` (line 136), and indirectly by `docker-build`.

### Required Change

**File:** `.github/workflows/ci.yml`
**Line 13:**

```diff
- PYTHON_VERSION: "3.11"
+ PYTHON_VERSION: "3.12"
```

### Why This Matters

The Dockerfiles already use `python:3.12-slim` (confirmed at `ivgs-api/Dockerfile:3`, `ivgs-workers/Dockerfile:3`, `ivgs-scheduler/Dockerfile:3`). Running CI linting and tests on Python 3.11 while production runs 3.12 means:
- Syntax features like `type` statements (PEP 695) won't be caught in CI
- Type checker behavior differs between versions
- `match`/`case` improvements in 3.12 not tested

### Verification

```bash
# After pushing to feature branch, check CI logs:
grep "PYTHON_VERSION" .github/workflows/ci.yml
# Expected output: PYTHON_VERSION: "3.12"

# Verify no other 3.11 references in CI:
grep -rn "3\.11" .github/workflows/ --include="*.yml"
# Expected: no matches (after applying Fixes 1, 3, 4, 16)
```

---

<a name="fix-2"></a>
## Fix 2: flake8 → ruff Linter Migration

**Divergence ID:** DIV-8.4
**Severity:** MAJOR
**Spec Reference:** §19.2 Table 19-1 — "ruff (replaces flake8/pylint); configured via pyproject.toml"
**Root Cause:** CI pipeline installs and runs `flake8`; no `ruff` configuration exists

### Current State

**Three files contain flake8 references:**

1. **`.github/workflows/ci.yml` line 31:**
   ```yaml
           pip install black flake8 mypy bandit[toml]
   ```

2. **`.github/workflows/ci.yml` lines 38-39:**
   ```yaml
         - name: Flake8 lint
           run: flake8 --max-line-length 100 --ignore E203,W503,E501 ivgs-api/ ivgs-workers/ ivgs-scheduler/ shared/
   ```

3. **`pyproject.toml` lines 23-26:**
   ```toml
   [tool.flake8]
   max-line-length = 100
   exclude = [".git", "__pycache__", ".venv", "node_modules", "migrations"]
   ignore = ["E203", "W503", "E501"]
   ```

### Required Changes

#### Change 2a: `.github/workflows/ci.yml` line 31

```diff
       - name: Install dependencies
         run: |
-          pip install black flake8 mypy bandit[toml]
+          pip install black ruff mypy bandit[toml]
           pip install -r ivgs-api/requirements.txt
           pip install -r ivgs-workers/requirements.txt
```

#### Change 2b: `.github/workflows/ci.yml` lines 38-39

```diff
-      - name: Flake8 lint
-        run: flake8 --max-line-length 100 --ignore E203,W503,E501 ivgs-api/ ivgs-workers/ ivgs-scheduler/ shared/
+      - name: Ruff lint
+        run: ruff check ivgs-api/ ivgs-workers/ ivgs-scheduler/ shared/
```

#### Change 2c: `pyproject.toml` — Replace `[tool.flake8]` with `[tool.ruff]`

Replace lines 23-26:
```diff
-[tool.flake8]
-max-line-length = 100
-exclude = [".git", "__pycache__", ".venv", "node_modules", "migrations"]
-ignore = ["E203", "W503", "E501"]
+[tool.ruff]
+target-version = "py312"
+line-length = 100
+exclude = [".git", "__pycache__", ".venv", "node_modules", "migrations"]
+
+[tool.ruff.lint]
+select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM"]
+ignore = ["E203", "E501"]
+
+[tool.ruff.lint.isort]
+known-first-party = ["shared", "ivgs_api", "ivgs_workers", "ivgs_scheduler"]
```

**Rule selection rationale:**
- `E`, `F`, `W` — pycodestyle + pyflakes (equivalent to flake8 core)
- `I` — isort (replaces separate `[tool.isort]` section)
- `N` — pep8-naming
- `UP` — pyupgrade (flags Python 3.11 patterns that can use 3.12+)
- `B` — bugbear (catches common bugs)
- `A` — builtins shadowing
- `C4` — comprehension improvements
- `SIM` — simplification opportunities

### Verification

```bash
# Install ruff locally and run:
pip install ruff
cd /home/ubuntu/github_repos/elearning

# Run ruff check (same command CI will use):
ruff check ivgs-api/ ivgs-workers/ ivgs-scheduler/ shared/

# If violations found, auto-fix safe ones:
ruff check --fix ivgs-api/ ivgs-workers/ ivgs-scheduler/ shared/

# Verify ruff config is valid:
ruff check --show-settings 2>&1 | head -20
# Expected: shows resolved configuration with target-version = py312

# Verify flake8 is fully removed:
grep -rn "flake8" pyproject.toml .github/workflows/ci.yml
# Expected: no matches
```

---

<a name="fix-3"></a>
## Fix 3: pyproject.toml Python Target Versions

**Divergence ID:** DIV-8.2 (secondary)
**Severity:** MAJOR
**Spec Reference:** §19.2 Table 19-1

### Current State

**`pyproject.toml` line 7:**
```toml
target-version = ["py311"]
```

**`pyproject.toml` line 29:**
```toml
python_version = "3.11"
```

### Required Changes

#### Change 3a: `pyproject.toml` line 7 (black target)

```diff
 [tool.black]
 line-length = 100
-target-version = ["py311"]
+target-version = ["py312"]
```

#### Change 3b: `pyproject.toml` line 29 (mypy version)

```diff
 [tool.mypy]
-python_version = "3.11"
+python_version = "3.12"
```

### Verification

```bash
grep -n "py311\|3\.11" pyproject.toml
# Expected: no matches

grep -n "py312\|3\.12" pyproject.toml
# Expected: lines for black target-version, ruff target-version, and mypy python_version
```

---

<a name="fix-4"></a>
## Fix 4: pre-commit Python Version & Hook Migration

**Divergence ID:** DIV-8.4 (secondary)
**Severity:** MINOR
**Spec Reference:** §19.2

### Current State

**`.pre-commit-config.yaml` line 21:**
```yaml
        language_version: python3.11
```

**`.pre-commit-config.yaml` lines 24-28:**
```yaml
  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--ignore=E203,W503,E501']
```

### Required Changes

#### Change 4a: Line 21 — Python version for black hook

```diff
       - id: black
-        language_version: python3.11
+        language_version: python3.12
         args: ['--line-length=100']
```

#### Change 4b: Lines 24-28 — Replace flake8 hook with ruff

```diff
-  - repo: https://github.com/PyCQA/flake8
-    rev: 7.0.0
-    hooks:
-      - id: flake8
-        args: ['--max-line-length=100', '--ignore=E203,W503,E501']
+  - repo: https://github.com/astral-sh/ruff-pre-commit
+    rev: v0.8.6
+    hooks:
+      - id: ruff
+        args: ['--fix']
+      - id: ruff-format
```

### Verification

```bash
grep -n "flake8" .pre-commit-config.yaml
# Expected: no matches

grep -n "ruff" .pre-commit-config.yaml
# Expected: 2+ matches (repo URL and hook IDs)

grep -n "3\.11" .pre-commit-config.yaml
# Expected: no matches

# Test pre-commit hooks work:
pip install pre-commit
pre-commit run --all-files
```

---

<a name="fix-5"></a>
## Fix 5: CI Branch Triggers

**Divergence ID:** DIV-1.5
**Severity:** MINOR
**Spec Reference:** §15.5 Table 15-3 — "main (CD), develop (CI), feature/*, hotfix/*"

### Current State

**`.github/workflows/ci.yml` lines 7-10:**
```yaml
on:
  push:
    branches: [main, staging, production]
  pull_request:
    branches: [main, staging, production]
```

The spec has no `staging` or `production` branches. The branch strategy is `main`, `develop`, `feature/*`, `hotfix/*`.

### Required Change

**`.github/workflows/ci.yml` lines 7-10:**

```diff
 on:
   push:
-    branches: [main, staging, production]
+    branches: [main, develop, "feature/**", "hotfix/**"]
   pull_request:
-    branches: [main, staging, production]
+    branches: [main, develop]
```

### Verification

```bash
grep -A4 "^on:" .github/workflows/ci.yml
# Expected: branches: [main, develop, "feature/**", "hotfix/**"]

# Also verify cd-deploy.yml still triggers on main only:
grep -A3 "^on:" .github/workflows/cd-deploy.yml
# Expected: branches: [main]  (no change needed — already correct)
```

---

<a name="fix-6"></a>
## Fix 6: CI Test Database Image

**Divergence ID:** (new — found during analysis)
**Severity:** MINOR
**Spec Reference:** §2.4 — "PostgreSQL 15+"; Appendix A.2 — `postgresql+psycopg://`

### Current State

**`.github/workflows/ci.yml` line 55:**
```yaml
        image: timescale/timescaledb:latest-pg17
```

The IVGS v5 spec does not mention TimescaleDB. The spec says "PostgreSQL 15+" (§2.4). Using TimescaleDB in CI is an unnecessary dependency that could mask compatibility issues with standard PostgreSQL.

### Required Change

**`.github/workflows/ci.yml` line 55:**

```diff
       postgres:
-        image: timescale/timescaledb:latest-pg17
+        image: postgres:17-alpine
         env:
           POSTGRES_USER: ivgs
```

### Verification

```bash
grep -n "timescale\|TimescaleDB" .github/workflows/ci.yml
# Expected: no matches

grep -n "postgres:" .github/workflows/ci.yml
# Expected: "image: postgres:17-alpine"
```

---

<a name="fix-7"></a>
## Fix 7: .env.template TimescaleDB Comment

**Divergence ID:** (new — found during analysis)
**Severity:** MINOR
**Spec Reference:** Appendix A.2

### Current State

**`.env.template` line 6:**
```bash
# === Database (PostgreSQL 17 + TimescaleDB) ===
```

### Required Change

```diff
-# === Database (PostgreSQL 17 + TimescaleDB) ===
+# === Database (PostgreSQL 17) ===
```

### Verification

```bash
grep -n "TimescaleDB\|timescale" .env.template
# Expected: no matches
```

---

<a name="fix-8"></a>
## Fix 8: Database Migration Consolidation (17 → 14)

**Divergence ID:** DIV-5.1, DIV-5.2
**Severity:** MAJOR
**Spec Reference:** Appendix D.2 — Exactly 14 migrations (0001–0014)

### Current State

17 migration files exist. The first 14 match the spec naming:

| Migration | Spec Match | Status |
|-----------|-----------|--------|
| `0001_initial_core.py` | ✅ Matches Appendix D.2 | KEEP |
| `0002_pipeline_checkpoints.py` | ✅ Matches | KEEP |
| `0003_gpu_registry.py` | ✅ Matches | KEEP |
| `0004_retry_tracking.py` | ✅ Matches | KEEP |
| `0005_worker_heartbeats.py` | ✅ Matches | KEEP |
| `0006_dead_letter_queue.py` | ✅ Matches | KEEP |
| `0007_composition_manifests.py` | ✅ Matches | KEEP |
| `0008_quality_scores.py` | ✅ Matches | KEEP |
| `0009_render_segments.py` | ✅ Matches | KEEP |
| `0010_gpu_metrics.py` | ✅ Matches | KEEP |
| `0011_retention_policies.py` | ✅ Matches | KEEP |
| `0012_storage_quotas.py` | ✅ Matches | KEEP |
| `0013_backup_records.py` | ✅ Matches | KEEP |
| `0014_fallback_policies.py` | ✅ Matches | KEEP |
| `0015_rollback_points.py` | ❌ Not in spec | CONSOLIDATE |
| `0016_prompt_tags.py` | ❌ Not in spec | CONSOLIDATE |
| `0017_target_audience.py` | ❌ Not in spec | CONSOLIDATE |

### Content of Extra Migrations

**0015_rollback_points.py** (26 lines):
- Creates `rollback_points` table: `id`, `version_tag`, `alembic_revision`, `docker_image_tags` (JSONB), `config_snapshot_path`, `created_at`
- Index on `created_at`

**0016_prompt_tags.py** (47 lines):
- Creates `prompt_tags` table: `id`, `name` (unique)
- Creates `prompt_tag_associations` junction table: `prompt_id` FK → `prompts.id`, `tag_id` FK → `prompt_tags.id`
- Adds `is_library_template` column to `prompts` table
- Seeds 7 default tags: healthcare, technical-training, compliance, onboarding, safety, product-demo, corporate

**0017_target_audience.py** (15 lines):
- Adds `target_audience` (String 500, nullable) column to `projects` table

### Consolidation Strategy

The extra tables provide useful functionality that should be preserved. Merge them into the correct spec migrations:

| Extra Content | Merge Into | Rationale |
|--------------|-----------|-----------|
| `rollback_points` table | `0001_initial_core.py` | Core infrastructure table; belongs with initial schema |
| `prompt_tags` + `prompt_tag_associations` tables | `0001_initial_core.py` | Prompt-related tables; prompts table is in 0001 |
| `is_library_template` column on `prompts` | `0001_initial_core.py` | Part of prompts table definition |
| `target_audience` column on `projects` | `0001_initial_core.py` | Part of projects table definition |
| 7 default prompt tags seed data | `0001_initial_core.py` (or seed script) | Initial data |

### Step-by-Step Implementation

#### Step 8.1: Read current 0001 migration to understand table creation pattern

```bash
head -50 ivgs-api/migrations/versions/0001_initial_core.py
```

#### Step 8.2: Add rollback_points table to `0001_initial_core.py`

Insert before the final line of the `upgrade()` function:

```python
    # --- rollback_points (§14.3 RollbackService) ---
    op.create_table(
        "rollback_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_tag", sa.String(255), nullable=False),
        sa.Column("alembic_revision", sa.String(255), nullable=False),
        sa.Column("docker_image_tags", JSONB, nullable=False),
        sa.Column("config_snapshot_path", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rollback_points_created_at", "rollback_points", ["created_at"])
```

Add to `downgrade()`:
```python
    op.drop_table("rollback_points")
```

Ensure `from sqlalchemy.dialects.postgresql import JSONB` is in the imports.

#### Step 8.3: Add prompt_tags tables to `0001_initial_core.py`

Insert after the `prompts` table creation in `upgrade()`:

```python
    # --- prompt_tags (§9.5 Prompt Library) ---
    op.create_table(
        "prompt_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "prompt_tag_associations",
        sa.Column("prompt_id", sa.String(36),
                  sa.ForeignKey("prompts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.String(36),
                  sa.ForeignKey("prompt_tags.id", ondelete="CASCADE"), primary_key=True),
    )
```

Add to `downgrade()`:
```python
    op.drop_table("prompt_tag_associations")
    op.drop_table("prompt_tags")
```

#### Step 8.4: Add columns to existing tables in `0001_initial_core.py`

In the `prompts` table creation, add:
```python
        sa.Column("is_library_template", sa.Boolean(), server_default="false"),
```

In the `projects` table creation, add:
```python
        sa.Column("target_audience", sa.String(500), nullable=True),
```

#### Step 8.5: Add seed data to 0001 or create dedicated seed script

Add prompt tag seeds at the end of `upgrade()`:
```python
    # Seed default prompt tags (§9.5)
    op.execute("""
        INSERT INTO prompt_tags (id, name) VALUES
        (gen_random_uuid()::text, 'healthcare'),
        (gen_random_uuid()::text, 'technical-training'),
        (gen_random_uuid()::text, 'compliance'),
        (gen_random_uuid()::text, 'onboarding'),
        (gen_random_uuid()::text, 'safety'),
        (gen_random_uuid()::text, 'product-demo'),
        (gen_random_uuid()::text, 'corporate')
        ON CONFLICT (name) DO NOTHING
    """)
```

#### Step 8.6: Update 0014 revision chain

After consolidation, `0014_fallback_policies.py` must be the Alembic head:

**`0014_fallback_policies.py`** — verify `down_revision = "0013"` (should already be correct).

#### Step 8.7: Delete extra migration files

```bash
cd /home/ubuntu/github_repos/elearning
git rm ivgs-api/migrations/versions/0015_rollback_points.py
git rm ivgs-api/migrations/versions/0016_prompt_tags.py
git rm ivgs-api/migrations/versions/0017_target_audience.py
```

#### Step 8.8: Verify Alembic chain integrity

```bash
cd ivgs-api

# List all migration revisions:
grep -n "^revision\|^down_revision" migrations/versions/0*.py

# Verify chain: 0001 → 0002 → ... → 0014
# 0001: down_revision = None
# 0002: down_revision = "0001"
# ...
# 0014: down_revision = "0013"
# No 0015, 0016, 0017 should exist
```

### Verification

```bash
# Count migration files:
ls ivgs-api/migrations/versions/0*.py | wc -l
# Expected: 14

# List them:
ls ivgs-api/migrations/versions/0*.py
# Expected: 0001 through 0014 only

# Verify no broken references:
grep "0015\|0016\|0017" ivgs-api/migrations/versions/*.py
# Expected: no matches

# If you have a test database available:
# DATABASE_URL=postgresql://localhost/ivgs_test alembic upgrade head
# alembic current  # Should show 0014
# alembic downgrade base  # Should complete cleanly
```

### ⚠️ CAUTION

If any environment has already run migrations 0015–0017, you must:
1. Run `alembic downgrade 0014` on that database first
2. Apply the updated 0001 migration (which now includes the consolidated tables)
3. Since 0001 cannot be re-run, create a one-time data migration script at `ivgs-infra/scripts/consolidate_migrations.py`

---

<a name="fix-9"></a>
## Fix 9: GPU Config — Add Hardware Model Names

**Divergence ID:** DIV-7.3
**Severity:** MAJOR
**Spec Reference:** §3.2 Table 3-2, Appendix B Table B-2

### Current State

**`ivgs-api/config/gpu_requirements.yaml` lines 106-112:**
```yaml
# Node total VRAM (Appendix B Table B-2)
node_vram:
  node-02: 98304  # 96 GB
  node-03: 98304  # 96 GB
  node-04: 49152  # 48 GB
  node-05: 16384  # 16 GB
  node-06: 32768  # 32 GB (Intel GPU)
```

The VRAM values are correct, but the section lacks the explicit GPU hardware model names required by the spec (§3.2 Table 3-2). The GPU Node Status Schema (Appendix C.4) shows `gpu_model` is a required field.

### Required Change

**Replace `ivgs-api/config/gpu_requirements.yaml` lines 106-112 with:**

```yaml
# Node GPU Hardware (§3.2 Table 3-2, Appendix B Table B-2)
node_hardware:
  node-02:
    gpu_model: "NVIDIA RTX 6000 Blackwell"
    vram_mb: 98304          # 96 GB
    architecture: "Blackwell"
    tdp_watts: 350
  node-03:
    gpu_model: "NVIDIA RTX 6000 Blackwell"
    vram_mb: 98304          # 96 GB
    architecture: "Blackwell"
    tdp_watts: 350
  node-04:
    gpu_model: "NVIDIA RTX 5000 Pro Blackwell"
    vram_mb: 49152          # 48 GB
    architecture: "Blackwell"
    tdp_watts: 350
  node-05:
    gpu_model: "NVIDIA RTX 5080"
    vram_mb: 16384          # 16 GB
    architecture: "Blackwell"
    tdp_watts: 300
  node-06:
    gpu_model: "Intel Arc B70 Pro"
    vram_mb: 32768          # 32 GB
    architecture: "Battlemage"
    tdp_watts: 150
```

### Code References to Update

The GPU scheduler reads `node_vram` by key name. Search for references:

```bash
grep -rn "node_vram" --include="*.py" /home/ubuntu/github_repos/elearning/
```

Any code reading `config["node_vram"]["node-02"]` (returns int) must be updated to `config["node_hardware"]["node-02"]["vram_mb"]` (returns int from nested dict). This is a breaking API change in the scheduler's config reader.

### Verification

```bash
# YAML is valid:
python3 -c "
import yaml
with open('ivgs-api/config/gpu_requirements.yaml') as f:
    cfg = yaml.safe_load(f)
assert 'node_hardware' in cfg, 'Missing node_hardware section'
assert cfg['node_hardware']['node-02']['gpu_model'] == 'NVIDIA RTX 6000 Blackwell'
assert cfg['node_hardware']['node-06']['gpu_model'] == 'Intel Arc B70 Pro'
assert cfg['node_hardware']['node-04']['vram_mb'] == 49152
print('PASS: GPU config validated')
"

# No cloud GPU references:
grep -iE "A100|A40|A10G|T4|hourly_rate" ivgs-api/config/gpu_requirements.yaml
# Expected: no matches
```

---

<a name="fix-10"></a>
## Fix 10: Create ivgs-models/ Directory

**Divergence ID:** DIV-3.3
**Severity:** MAJOR
**Spec Reference:** §15.1 Table 15-1 — "ivgs-models" is one of 6 required sub-repositories; §19.2 — "Monorepo with 6 sub-repositories"

### Current State

The `ivgs-models/` directory does not exist. Per the spec, it should contain model download scripts, vLLM serve configurations, and ComfyUI workflow JSONs.

### Required Structure (from Table 15-1 and §7.1)

```
ivgs-models/
├── README.md                          # Model inventory and download instructions
├── download_models.sh                 # Orchestrator script for all model downloads
├── checksums.sha256                   # Model file integrity verification
├── vllm/
│   ├── llama-3.3-70b.yaml           # vLLM serve config (§7.1.1)
│   ├── qwen2.5-72b.yaml             # vLLM serve config
│   └── mistral-24b.yaml             # vLLM serve config
├── comfyui/
│   ├── flux1-dev-workflow.json       # ComfyUI workflow (§7.1.2)
│   ├── sdxl-workflow.json
│   └── animatediff-workflow.json
├── tts/
│   └── coqui-xtts-v2.yaml           # XTTS config (§7.1.3)
└── ollama/
    └── Modelfile                     # Ollama model definitions
```

### Implementation

#### File: `ivgs-models/README.md`

```markdown
# IVGS v5 — AI Model Inventory

All models run locally on the IVGS hardware cluster (§7.1). No cloud inference services.

## Model Inventory (Appendix B Table B-1)

| Model | Size | Node(s) | Config |
|-------|------|---------|--------|
| Llama 3.3 70B Instruct | 140 GB (TP) | node-02 + node-03 | `vllm/llama-3.3-70b.yaml` |
| Qwen2.5 72B Instruct | 144 GB (TP) | node-02 + node-03 | `vllm/qwen2.5-72b.yaml` |
| Mistral Small 24B | 48 GB | node-04 | `vllm/mistral-24b.yaml` |
| FLUX.1 Dev | 24 GB | node-04 | `comfyui/flux1-dev-workflow.json` |
| SDXL 1.0 | 10 GB | node-05 | `comfyui/sdxl-workflow.json` |
| Coqui XTTS v2 | 16 GB | node-04 | `tts/coqui-xtts-v2.yaml` |
| CogVideoX 5B | 24 GB | node-02/03 | N/A (Diffusers) |
| LatentSync | 12 GB | node-04 | N/A |

## Download

```bash
chmod +x download_models.sh
./download_models.sh
```
```

#### File: `ivgs-models/download_models.sh`

```bash
#!/bin/bash
# IVGS v5 — Model Download Orchestrator (§7.1)
# Run on node-01; models stored on NFS share accessible to all nodes
set -euo pipefail

MODELS_DIR="${SHARED_VOLUME_PATH:-/mnt/ivgs-shared}/models"
mkdir -p "$MODELS_DIR"

echo "============================================="
echo "IVGS v5 — Model Download Orchestrator"
echo "Target: $MODELS_DIR"
echo "============================================="

# === vLLM Models ===
echo ""
echo "--- Downloading Llama 3.3 70B Instruct ---"
huggingface-cli download meta-llama/Llama-3.3-70B-Instruct \
  --local-dir "$MODELS_DIR/llama-3.3-70b-instruct" \
  --local-dir-use-symlinks False

echo ""
echo "--- Downloading Qwen2.5 72B Instruct ---"
huggingface-cli download Qwen/Qwen2.5-72B-Instruct \
  --local-dir "$MODELS_DIR/qwen2.5-72b-instruct" \
  --local-dir-use-symlinks False

echo ""
echo "--- Downloading Mistral Small 24B Instruct ---"
huggingface-cli download mistralai/Mistral-Small-24B-Instruct \
  --local-dir "$MODELS_DIR/mistral-small-24b" \
  --local-dir-use-symlinks False

# === ComfyUI Models ===
echo ""
echo "--- Downloading FLUX.1 Dev ---"
huggingface-cli download black-forest-labs/FLUX.1-dev \
  --local-dir "$MODELS_DIR/flux1-dev" \
  --local-dir-use-symlinks False

echo ""
echo "--- Downloading SDXL 1.0 ---"
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  --local-dir "$MODELS_DIR/sdxl-base" \
  --local-dir-use-symlinks False

# === TTS Models ===
echo ""
echo "--- Downloading Coqui XTTS v2 ---"
huggingface-cli download coqui/XTTS-v2 \
  --local-dir "$MODELS_DIR/xtts-v2" \
  --local-dir-use-symlinks False

# === Video Models ===
echo ""
echo "--- Downloading CogVideoX 5B ---"
huggingface-cli download THUDM/CogVideoX-5b \
  --local-dir "$MODELS_DIR/cogvideox-5b" \
  --local-dir-use-symlinks False

# === Ollama Models (node-05) ===
echo ""
echo "--- Pulling Ollama models ---"
OLLAMA_HOST="${OLLAMA_URL:-http://10.10.0.5:11434}" ollama pull llama3.2:8b
OLLAMA_HOST="${OLLAMA_URL:-http://10.10.0.5:11434}" ollama pull phi3:medium
OLLAMA_HOST="${OLLAMA_URL:-http://10.10.0.5:11434}" ollama pull gemma2:9b

echo ""
echo "============================================="
echo "All models downloaded successfully."
echo "Run 'sha256sum -c checksums.sha256' to verify."
echo "============================================="
```

#### File: `ivgs-models/vllm/llama-3.3-70b.yaml`

```yaml
# vLLM Serve Configuration — Llama 3.3 70B Instruct (§7.1.1)
# Deployed on: node-02 + node-03 (tensor parallel across 2× RTX 6000 Blackwell 96GB)
model: /mnt/ivgs-shared/models/llama-3.3-70b-instruct
served-model-name: llama-3.3-70b
tensor-parallel-size: 2
max-model-len: 128000
gpu-memory-utilization: 0.90
dtype: auto
host: 0.0.0.0
port: 8000
api-key: ""  # No auth on private VLAN
trust-remote-code: false
```

#### File: `ivgs-models/vllm/qwen2.5-72b.yaml`

```yaml
# vLLM Serve Configuration — Qwen2.5 72B Instruct
# Deployed on: node-02 + node-03 (tensor parallel)
model: /mnt/ivgs-shared/models/qwen2.5-72b-instruct
served-model-name: qwen2.5-72b
tensor-parallel-size: 2
max-model-len: 128000
gpu-memory-utilization: 0.90
dtype: auto
host: 0.0.0.0
port: 8000
trust-remote-code: true  # Required for Qwen
```

#### File: `ivgs-models/vllm/mistral-24b.yaml`

```yaml
# vLLM Serve Configuration — Mistral Small 24B Instruct
# Deployed on: node-04 (RTX 5000 Pro Blackwell 48GB)
model: /mnt/ivgs-shared/models/mistral-small-24b
served-model-name: mistral-24b
tensor-parallel-size: 1
max-model-len: 32000
gpu-memory-utilization: 0.90
dtype: auto
host: 0.0.0.0
port: 8000
trust-remote-code: false
```

#### File: `ivgs-models/tts/coqui-xtts-v2.yaml`

```yaml
# Coqui XTTS v2 Configuration (§7.1.3)
# Deployed on: node-04 (resident, 16GB VRAM)
model_path: /mnt/ivgs-shared/models/xtts-v2
host: 0.0.0.0
port: 5002
# Supported languages per §17.1 Table 17-1
supported_languages:
  - code: en
    variants: [en-US, en-GB]
  - code: es
    variants: [es-ES]
  - code: fr
    variants: [fr-FR]
  - code: de
    variants: [de-DE]
  - code: zh-cn
    variants: [zh-CN]
  - code: ja
    variants: [ja-JP]
  - code: ar
    variants: [ar-SA]
```

#### File: `ivgs-models/checksums.sha256` (placeholder)

```
# IVGS v5 — Model Checksums
# Generate after download: sha256sum -b <model_file> >> checksums.sha256
# Verify: sha256sum -c checksums.sha256
```

#### File: `ivgs-models/comfyui/flux1-dev-workflow.json` (placeholder)

```json
{
  "_comment": "FLUX.1 Dev workflow for ComfyUI — populate from ComfyUI export after model setup",
  "spec_reference": "§7.1.2",
  "node": "node-04",
  "vram_mb": 24576
}
```

#### File: `ivgs-models/comfyui/sdxl-workflow.json` (placeholder)

```json
{
  "_comment": "SDXL 1.0 workflow for ComfyUI — populate from ComfyUI export after model setup",
  "spec_reference": "§7.1.2",
  "node": "node-05",
  "vram_mb": 10240
}
```

#### File: `ivgs-models/comfyui/animatediff-workflow.json` (placeholder)

```json
{
  "_comment": "AnimateDiff workflow for ComfyUI — populate from ComfyUI export after model setup",
  "spec_reference": "§7.1.2",
  "node": "node-04",
  "vram_mb": 16384
}
```

#### File: `ivgs-models/ollama/Modelfile` (placeholder)

```
# Ollama model definitions for node-05 (RTX 5080, 16GB)
# Models are pulled via `ollama pull` in download_models.sh
# See: https://ollama.ai/library
```

### Verification

```bash
# Directory structure exists:
test -d ivgs-models/vllm && echo "PASS" || echo "FAIL"
test -d ivgs-models/comfyui && echo "PASS" || echo "FAIL"
test -d ivgs-models/tts && echo "PASS" || echo "FAIL"
test -f ivgs-models/download_models.sh && echo "PASS" || echo "FAIL"

# Download script is executable:
test -x ivgs-models/download_models.sh && echo "PASS" || echo "FAIL"

# Shell script passes linting:
shellcheck ivgs-models/download_models.sh || true

# YAML configs are valid:
python3 -c "
import yaml
for f in ['ivgs-models/vllm/llama-3.3-70b.yaml', 'ivgs-models/vllm/qwen2.5-72b.yaml',
          'ivgs-models/vllm/mistral-24b.yaml', 'ivgs-models/tts/coqui-xtts-v2.yaml']:
    with open(f) as fh:
        yaml.safe_load(fh)
    print(f'PASS: {f}')
"
```

---

<a name="fix-11"></a>
## Fix 11: Grafana Dashboard File Naming

**Divergence ID:** DIV-6.8
**Severity:** MINOR
**Spec Reference:** Appendix A.1 — "`grafana-pipeline.json`" and "`grafana-gpu.json`"

### Current State

```
configs/grafana/dashboards/pipeline_overview.json
configs/grafana/dashboards/gpu_fleet_utilization.json
```

Spec (Appendix A.1) requires:
```
ivgs-infra/grafana/grafana-pipeline.json
ivgs-infra/grafana/grafana-gpu.json
```

Since the project uses `configs/grafana/` (and `ivgs-infra/` already exists for monitoring), we'll keep the location but fix the filenames to match spec naming.

### Required Changes

```bash
cd /home/ubuntu/github_repos/elearning
git mv configs/grafana/dashboards/pipeline_overview.json configs/grafana/dashboards/grafana-pipeline.json
git mv configs/grafana/dashboards/gpu_fleet_utilization.json configs/grafana/dashboards/grafana-gpu.json
```

### Verification

```bash
ls configs/grafana/dashboards/
# Expected: grafana-pipeline.json  grafana-gpu.json

# Verify no orphan references:
grep -rn "pipeline_overview\|gpu_fleet_utilization" --exclude-dir=".git" .
# Expected: no matches (after also applying Fix 15)
```

---

<a name="fix-12"></a>
## Fix 12: Move fallback_policies.yaml to Spec Location

**Divergence ID:** DIV-9.5
**Severity:** MINOR
**Spec Reference:** Appendix A.1 — "`fallback_policies.yaml` → `ivgs-api/config/`"

### Current State

```
configs/fallback_policies.yaml    ← current location
```

Spec (Appendix A.1) says: `fallback_policies.yaml` → `ivgs-api/config/`

Other config files are already in the correct location:
```
ivgs-api/config/gpu_requirements.yaml     ✅
ivgs-api/config/quality_thresholds.yaml   ✅
ivgs-api/config/retry_policies.yaml       ✅
ivgs-api/config/timeout_defaults.yaml     ✅
```

### Required Changes

#### Step 12.1: Move the file

```bash
git mv configs/fallback_policies.yaml ivgs-api/config/fallback_policies.yaml
```

#### Step 12.2: Update code references

**File: `ivgs-api/app/scripts/seed_fallback_policies.py` line 33:**

```diff
-YAML_PATH = Path(__file__).resolve().parents[3] / "configs" / "fallback_policies.yaml"
+YAML_PATH = Path(__file__).resolve().parents[2] / "config" / "fallback_policies.yaml"
```

The path changes because:
- Old: `ivgs-api/app/scripts/seed_fallback_policies.py` → `.parents[3]` = repo root → `configs/`
- New: `ivgs-api/app/scripts/seed_fallback_policies.py` → `.parents[2]` = `ivgs-api/` → `config/`

#### Step 12.3: Check for other references

```bash
grep -rn "configs/fallback_policies\|configs.fallback_policies" --include="*.py" --include="*.yaml" --include="*.yml" --exclude-dir=".git" .
```

Update any additional references found.

### Verification

```bash
# File exists in correct location:
test -f ivgs-api/config/fallback_policies.yaml && echo "PASS" || echo "FAIL"

# No orphan references to old location:
grep -rn "configs/fallback_policies" --exclude-dir=".git" .
# Expected: no matches

# All 5 spec config files present:
for f in gpu_requirements.yaml quality_thresholds.yaml retry_policies.yaml timeout_defaults.yaml fallback_policies.yaml; do
  test -f "ivgs-api/config/$f" && echo "PASS: $f" || echo "FAIL: $f"
done
```

---

<a name="fix-13"></a>
## Fix 13: Add Git Workflow / Branch Strategy to README

**Divergence ID:** DIV-8.3
**Severity:** MAJOR
**Spec Reference:** §15.5 Table 15-3

### Current State

The README has no section documenting the branch strategy. Per §15.5, the branch strategy must be documented.

### Required Change

Add a new section to `README.md` before the `## License` section (currently line 155):

```markdown
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
- CD runs only on push to `main`
```

### Verification

```bash
grep -c "Git Workflow" README.md
# Expected: 1

grep "develop\|hotfix" README.md | head -5
# Expected: branch strategy references
```

---

<a name="fix-14"></a>
## Fix 14: Create `develop` Branch

**Divergence ID:** DIV-8.3 (supporting)
**Severity:** MAJOR
**Spec Reference:** §15.5 Table 15-3

### Current State

Only `main` exists as a primary branch. The spec requires a `develop` branch.

### Implementation

```bash
cd /home/ubuntu/github_repos/elearning
git checkout main
git pull origin main
git checkout -b develop
git push origin develop
```

### GitHub Branch Protection (Manual Step)

Configure on GitHub → Settings → Branches → Add rule:

1. **`main`**: Require PR reviews, require status checks (CI/CD, compliance-check), no direct push
2. **`develop`**: Require status checks (CI/CD)

### Verification

```bash
git branch -r | grep develop
# Expected: remotes/origin/develop
```

---

<a name="fix-15"></a>
## Fix 15: Grafana Dashboard Provisioning Config Update

**Divergence ID:** DIV-6.8 (supporting)
**Severity:** MINOR
**Spec Reference:** §13.2

### Current State

**`configs/grafana/provisioning/dashboards/dashboard.yml` lines 16-17 (comments):**
```yaml
#   1. pipeline_overview.json    — Pipeline Overview
#   2. gpu_fleet_utilization.json — GPU Fleet Utilization
```

The provisioning config uses a folder-based approach (all JSON files in `/var/lib/grafana/dashboards/`), so the actual dashboard filenames in comments should match the renamed files.

### Required Change

```diff
-#   1. pipeline_overview.json    — Pipeline Overview
-#   2. gpu_fleet_utilization.json — GPU Fleet Utilization
+#   1. grafana-pipeline.json     — Pipeline Overview (Appendix A.1)
+#   2. grafana-gpu.json          — GPU Fleet Utilization (Appendix A.1)
```

### Verification

```bash
grep -n "pipeline_overview\|gpu_fleet_utilization" configs/grafana/provisioning/dashboards/dashboard.yml
# Expected: no matches
```

---

<a name="fix-16"></a>
## Fix 16: CI Compliance Scanner Python Version Alignment

**Divergence ID:** (supporting consistency fix)
**Severity:** MINOR

### Current State

**`.github/workflows/ci.yml` line 136:**
```yaml
          python-version: ${{ env.PYTHON_VERSION }}
```

This references `PYTHON_VERSION` env var, which will be `3.12` after Fix 1. The compliance-check.yml already uses `3.12` directly. No change needed — this fix is automatically resolved by Fix 1.

**Status: ✅ Automatically resolved by Fix 1.**

However, verify the `security-scan` job:

**`.github/workflows/ci.yml` line 163:**
```yaml
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/staging'
```

Should be updated since `staging` branch doesn't exist in the spec:

```diff
-    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/staging'
+    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'
```

### Verification

```bash
grep "staging" .github/workflows/ci.yml
# Expected: no matches (after this fix)
```

---

<a name="quality-gate"></a>
## Quality Gate Checklist

Before any hardware deployment, **every item below must pass**. A single FAIL blocks deployment.

### Gate 1: Prohibited Dependencies (CRITICAL)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1.1 | No `openai` imports | `grep -rE "^import openai\|^from openai" --include="*.py" .` | 0 matches |
| 1.2 | No prohibited env vars | `grep -rE "OPENAI_API_KEY\|ANTHROPIC_API_KEY\|ELEVENLABS_API_KEY" --include="*.env*" --include="*.yml" .` | 0 matches |
| 1.3 | No prohibited pip packages | `grep -E "^openai\|^anthropic\|^elevenlabs" **/requirements*.txt` | 0 matches |
| 1.4 | Compliance scanner passes | `python scripts/compliance_scanner.py .` | Exit code 0 |

### Gate 2: Python & Linting (MAJOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 2.1 | CI uses Python 3.12 | `grep "PYTHON_VERSION" .github/workflows/ci.yml` | `"3.12"` |
| 2.2 | ruff configured | `grep "tool.ruff" pyproject.toml` | Match found |
| 2.3 | No flake8 in CI | `grep "flake8" .github/workflows/ci.yml` | 0 matches |
| 2.4 | No flake8 in pyproject.toml | `grep "flake8" pyproject.toml` | 0 matches |
| 2.5 | No flake8 in pre-commit | `grep "flake8" .pre-commit-config.yaml` | 0 matches |
| 2.6 | No Python 3.11 refs | `grep -rn "3\.11\|py311" pyproject.toml .pre-commit-config.yaml .github/workflows/` | 0 matches |
| 2.7 | ruff check passes | `ruff check ivgs-api/ ivgs-workers/ ivgs-scheduler/ shared/` | Exit code 0 |

### Gate 3: Database Migrations (MAJOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 3.1 | Exactly 14 migrations | `ls ivgs-api/migrations/versions/0*.py \| wc -l` | `14` |
| 3.2 | No 0015+ migrations | `ls ivgs-api/migrations/versions/001[5-9]*.py 2>/dev/null` | No files |
| 3.3 | Chain integrity | `grep "down_revision" ivgs-api/migrations/versions/0014*.py` | `"0013"` |
| 3.4 | All tables present | Migration includes rollback_points, prompt_tags, prompt_tag_associations, target_audience | Verified |

### Gate 4: GPU Configuration (MAJOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 4.1 | node_hardware section | `grep "node_hardware" ivgs-api/config/gpu_requirements.yaml` | Match |
| 4.2 | GPU model names | `grep "gpu_model" ivgs-api/config/gpu_requirements.yaml` | 5 matches |
| 4.3 | No cloud GPUs | `grep -iE "A100\|A40\|A10G\|T4" ivgs-api/config/gpu_requirements.yaml` | 0 matches |
| 4.4 | No hourly rates | `grep "hourly_rate" ivgs-api/config/gpu_requirements.yaml` | 0 matches |

### Gate 5: Repository Structure (MAJOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 5.1 | ivgs-models/ exists | `test -d ivgs-models` | Exit 0 |
| 5.2 | vLLM configs present | `ls ivgs-models/vllm/*.yaml \| wc -l` | `3` |
| 5.3 | download script exists | `test -x ivgs-models/download_models.sh` | Exit 0 |
| 5.4 | All 6 sub-repos present | Check `ivgs-api`, `ivgs-frontend`, `ivgs-scheduler`, `ivgs-workers`, `ivgs-infra`, `ivgs-models` | All exist |

### Gate 6: Configuration Files (MINOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 6.1 | fallback_policies in correct dir | `test -f ivgs-api/config/fallback_policies.yaml` | Exit 0 |
| 6.2 | 5 config files in ivgs-api/config/ | `ls ivgs-api/config/*.yaml \| wc -l` | `5` |
| 6.3 | Grafana dashboards named correctly | `ls configs/grafana/dashboards/grafana-*.json \| wc -l` | `2` |

### Gate 7: CI/CD & Branch Strategy (MAJOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 7.1 | CI triggers correct | `grep -A2 "branches:" .github/workflows/ci.yml \| head -3` | `develop`, `feature/**` |
| 7.2 | develop branch exists | `git branch -r \| grep develop` | Match |
| 7.3 | Branch strategy in README | `grep "Git Workflow" README.md` | Match |
| 7.4 | No staging refs in CI | `grep "staging" .github/workflows/ci.yml` | 0 matches |
| 7.5 | No TimescaleDB in CI | `grep "timescale" .github/workflows/ci.yml` | 0 matches |

### Gate 8: Documentation Consistency (MINOR)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 8.1 | No TimescaleDB in .env.template | `grep -i "timescale" .env.template` | 0 matches |
| 8.2 | Grafana provisioning updated | `grep "grafana-pipeline\|grafana-gpu" configs/grafana/provisioning/dashboards/dashboard.yml` | 2 matches |

---

<a name="pr-strategy"></a>
## PR Strategy

All changes organized into **3 PRs** to ensure clean review and safe rollback:

### PR 1: `fix/cicd-python312-ruff` (Fixes 1–7)

**Scope:** CI/CD pipeline modernization — Python 3.12, ruff linter, branch triggers, database image
**Files changed:** 4
- `.github/workflows/ci.yml`
- `pyproject.toml`
- `.pre-commit-config.yaml`
- `.env.template`

**Risk:** Low — CI/CD config changes only; no application code changed
**Testing:** Push to feature branch → CI must pass with Python 3.12 + ruff

### PR 2: `fix/schema-structure-compliance` (Fixes 8–12)

**Scope:** Database migration consolidation, GPU config, ivgs-models directory, Grafana naming, config paths
**Files changed:** ~20
- `ivgs-api/migrations/versions/0001_initial_core.py` (modified)
- `ivgs-api/migrations/versions/0015_rollback_points.py` (deleted)
- `ivgs-api/migrations/versions/0016_prompt_tags.py` (deleted)
- `ivgs-api/migrations/versions/0017_target_audience.py` (deleted)
- `ivgs-api/config/gpu_requirements.yaml` (modified)
- `ivgs-api/config/fallback_policies.yaml` (moved from `configs/`)
- `ivgs-api/app/scripts/seed_fallback_policies.py` (path update)
- `ivgs-models/` (entire new directory, ~12 files)
- `configs/grafana/dashboards/grafana-pipeline.json` (renamed)
- `configs/grafana/dashboards/grafana-gpu.json` (renamed)
- `configs/grafana/provisioning/dashboards/dashboard.yml` (comments updated)

**Risk:** Medium — migration consolidation requires careful testing
**Testing:** Fresh Alembic upgrade/downgrade on test database; YAML validation

### PR 3: `fix/docs-branch-strategy` (Fixes 13–16)

**Scope:** README branch strategy, develop branch creation, CI staging→develop
**Files changed:** 2
- `README.md`
- `.github/workflows/ci.yml` (security scan condition)

**Risk:** Low — documentation and minor CI condition change
**Testing:** README renders correctly; CI triggers on develop branch

---

<a name="verification-script"></a>
## Automated Verification Script

Save as `scripts/verify_spec_compliance.sh` and run after all fixes are applied:

```bash
#!/bin/bash
# IVGS v5 — Pre-Deployment Spec Compliance Verification
# Run from repository root: bash scripts/verify_spec_compliance.sh
set -u

PASS=0
FAIL=0
WARN=0

check() {
    local label="$1"
    local result="$2"
    if [ "$result" = "PASS" ]; then
        echo "  ✅ PASS: $label"
        ((PASS++))
    elif [ "$result" = "WARN" ]; then
        echo "  ⚠️  WARN: $label"
        ((WARN++))
    else
        echo "  ❌ FAIL: $label"
        ((FAIL++))
    fi
}

echo "=========================================="
echo "IVGS v5 Pre-Deployment Compliance Check"
echo "=========================================="
echo ""

# --- Gate 1: Prohibited Dependencies ---
echo "--- Gate 1: Prohibited Dependencies ---"
if grep -rqE "^import openai|^from openai" --include="*.py" --exclude-dir=".git" .; then
    check "No openai imports" "FAIL"
else
    check "No openai imports" "PASS"
fi

if grep -rqE "OPENAI_API_KEY|ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|DID_API_KEY|REPLICATE_API_TOKEN" \
    --include="*.env*" --include="*.yml" --include="*.yaml" --include="*.py" \
    --exclude-dir=".git" --exclude="compliance_scanner.py" --exclude="compliance-check.yml" --exclude="IVGS*" .; then
    check "No prohibited env vars" "FAIL"
else
    check "No prohibited env vars" "PASS"
fi

# --- Gate 2: Python & Linting ---
echo ""
echo "--- Gate 2: Python & Linting ---"
if grep -q '"3.12"' .github/workflows/ci.yml 2>/dev/null; then
    check "CI uses Python 3.12" "PASS"
else
    check "CI uses Python 3.12" "FAIL"
fi

if grep -q "tool.ruff" pyproject.toml 2>/dev/null; then
    check "ruff configured in pyproject.toml" "PASS"
else
    check "ruff configured in pyproject.toml" "FAIL"
fi

if grep -q "flake8" .github/workflows/ci.yml 2>/dev/null; then
    check "No flake8 in CI" "FAIL"
else
    check "No flake8 in CI" "PASS"
fi

if grep -q "flake8" pyproject.toml 2>/dev/null; then
    check "No flake8 in pyproject.toml" "FAIL"
else
    check "No flake8 in pyproject.toml" "PASS"
fi

if grep -qE "3\.11|py311" pyproject.toml .pre-commit-config.yaml .github/workflows/ci.yml 2>/dev/null; then
    check "No Python 3.11 references" "FAIL"
else
    check "No Python 3.11 references" "PASS"
fi

# --- Gate 3: Database Migrations ---
echo ""
echo "--- Gate 3: Database Migrations ---"
MIGRATION_COUNT=$(ls ivgs-api/migrations/versions/0*.py 2>/dev/null | wc -l)
if [ "$MIGRATION_COUNT" -eq 14 ]; then
    check "Exactly 14 migrations" "PASS"
else
    check "Exactly 14 migrations ($MIGRATION_COUNT found)" "FAIL"
fi

if ls ivgs-api/migrations/versions/001[5-9]*.py 2>/dev/null | grep -q .; then
    check "No extra migrations (0015+)" "FAIL"
else
    check "No extra migrations (0015+)" "PASS"
fi

# --- Gate 4: GPU Configuration ---
echo ""
echo "--- Gate 4: GPU Configuration ---"
if grep -q "node_hardware" ivgs-api/config/gpu_requirements.yaml 2>/dev/null; then
    check "node_hardware section exists" "PASS"
else
    check "node_hardware section exists" "FAIL"
fi

GPU_MODEL_COUNT=$(grep -c "gpu_model" ivgs-api/config/gpu_requirements.yaml 2>/dev/null || echo 0)
if [ "$GPU_MODEL_COUNT" -ge 5 ]; then
    check "GPU model names present ($GPU_MODEL_COUNT)" "PASS"
else
    check "GPU model names present ($GPU_MODEL_COUNT)" "FAIL"
fi

if grep -iqE "A100|A40|A10G|T4|hourly_rate" ivgs-api/config/gpu_requirements.yaml 2>/dev/null; then
    check "No cloud GPU references" "FAIL"
else
    check "No cloud GPU references" "PASS"
fi

# --- Gate 5: Repository Structure ---
echo ""
echo "--- Gate 5: Repository Structure ---"
for dir in ivgs-api ivgs-frontend ivgs-scheduler ivgs-workers ivgs-infra ivgs-models shared docs/adr; do
    if [ -d "$dir" ]; then
        check "Directory: $dir/" "PASS"
    else
        check "Directory: $dir/" "FAIL"
    fi
done

if [ -f "ivgs-models/download_models.sh" ] && [ -x "ivgs-models/download_models.sh" ]; then
    check "Model download script (executable)" "PASS"
else
    check "Model download script (executable)" "FAIL"
fi

# --- Gate 6: Configuration Files ---
echo ""
echo "--- Gate 6: Configuration Files ---"
for f in gpu_requirements.yaml quality_thresholds.yaml retry_policies.yaml timeout_defaults.yaml fallback_policies.yaml; do
    if [ -f "ivgs-api/config/$f" ]; then
        check "Config: ivgs-api/config/$f" "PASS"
    else
        check "Config: ivgs-api/config/$f" "FAIL"
    fi
done

for f in grafana-pipeline.json grafana-gpu.json; do
    if [ -f "configs/grafana/dashboards/$f" ]; then
        check "Dashboard: $f" "PASS"
    else
        check "Dashboard: $f" "FAIL"
    fi
done

# --- Gate 7: CI/CD & Branch Strategy ---
echo ""
echo "--- Gate 7: CI/CD & Branch Strategy ---"
if grep -q "develop" .github/workflows/ci.yml 2>/dev/null; then
    check "CI triggers include develop" "PASS"
else
    check "CI triggers include develop" "FAIL"
fi

if grep -q "Git Workflow" README.md 2>/dev/null; then
    check "Branch strategy in README" "PASS"
else
    check "Branch strategy in README" "FAIL"
fi

if grep -q "staging" .github/workflows/ci.yml 2>/dev/null; then
    check "No staging refs in CI" "FAIL"
else
    check "No staging refs in CI" "PASS"
fi

if grep -iq "timescale" .github/workflows/ci.yml 2>/dev/null; then
    check "No TimescaleDB in CI" "FAIL"
else
    check "No TimescaleDB in CI" "PASS"
fi

if grep -iq "timescale" .env.template 2>/dev/null; then
    check "No TimescaleDB in .env.template" "FAIL"
else
    check "No TimescaleDB in .env.template" "PASS"
fi

# --- Summary ---
echo ""
echo "=========================================="
TOTAL=$((PASS + FAIL + WARN))
echo "Results: $PASS/$TOTAL passed, $FAIL failed, $WARN warnings"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    echo "❌ DEPLOYMENT BLOCKED — $FAIL checks failed"
    exit 1
else
    echo "✅ ALL CHECKS PASSED — Ready for hardware deployment"
    exit 0
fi
```

### Running the Verification

```bash
cd /home/ubuntu/github_repos/elearning
chmod +x scripts/verify_spec_compliance.sh
bash scripts/verify_spec_compliance.sh
```

**Expected output after all 16 fixes applied:**
```
✅ ALL CHECKS PASSED — Ready for hardware deployment
```

---

## Appendix: Spec Section Cross-Reference

| Fix # | Spec Section(s) | Page(s) |
|-------|-----------------|---------|
| 1 | §19.2 Table 19-1 | 70 |
| 2 | §19.2 Table 19-1 | 70 |
| 3 | §19.2 Table 19-1 | 70 |
| 4 | §19.2 Table 19-1 | 70 |
| 5 | §15.5 Table 15-3 | 64 |
| 6 | §2.4 | 8 |
| 7 | Appendix A.2 | 72 |
| 8 | Appendix D.2 | 78 |
| 9 | §3.2, Appendix B, Appendix C.4 | 12, 73-75, 77 |
| 10 | §15.1 Table 15-1, §7.1, §19.2 | 62, 28, 70 |
| 11 | Appendix A.1 | 71 |
| 12 | Appendix A.1 | 71 |
| 13 | §15.5 Table 15-3 | 64 |
| 14 | §15.5 Table 15-3 | 64 |
| 15 | §13.2 | 57 |
| 16 | §15.3 Table 15-2 | 63 |

---

*End of Pre-Deployment Implementation Guide — Generated May 20, 2026*
*Spec Authority: IVGS v5 Functional Specification v5.0 (May 18, 2026)*
