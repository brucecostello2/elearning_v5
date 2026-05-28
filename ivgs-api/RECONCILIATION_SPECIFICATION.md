# IVGS v5 — Reconciliation Specification

**Version:** 1.0  
**Date:** 2026-05-27  
**Status:** ACTIONABLE — Decisions 2 and 4 approved; Decisions 1, 3, 5 pending operator input  
**Purpose:** Complete porting guide for a fresh agent to reconcile sandbox work into origin/main

---

## 1. Executive Summary

### 1.1 Purpose and Scope

This document is a **complete, self-contained porting specification** for merging sandbox development work (ivgs-api backend) into the origin/main branch of the `brucecostello2/elearning_v5` monorepo. A fresh agent should be able to execute this specification without any additional context.

### 1.2 Background

The IVGS v5 project uses a monorepo structure with multiple services. The `ivgs-api/` subdirectory contains the FastAPI backend. Development work was performed in a **sandbox environment** — a separate git repository created via `git init` (not `git clone`) — which has **disjoint history** from origin/main.

The sandbox was derived from approximately the **v5.1.0 merge** state (`0d73697`, 2026-05-22) but was independently modified. There is no common git ancestor between sandbox and origin.

### 1.3 What the Sandbox Contains

The sandbox includes the following development work that must be ported:

| Category | Description | Files |
|----------|-------------|-------|
| **Schema gap fixes** | ORM columns missing from migrations (Phase 0a/0b) | 4 model files + 7 migrations (0015–0022) |
| **Bug fixes** | BUG-006 (backup error_message), BUG-007 (quality review_notes) | 2 model files + 2 migrations |
| **Test infrastructure** | Complete conftest.py rewrite (NullPool, table truncation, factories) | 1 file (1271 lines) |
| **Test suite expansion** | 35 new test files (service tests, API tests, bug regression, WebSocket, rate limiting) | 35 files |
| **Source fixes** | API routes, middleware, endpoint corrections | 7 source files |
| **Unique index** | storage_quotas entity uniqueness constraint | 1 migration |

### 1.4 Reconciliation Objectives

1. Create a feature branch from origin/main HEAD (`b1082d7`)
2. Port all sandbox work onto that branch
3. Resolve all migration chain conflicts
4. Ensure ORM models match migrations
5. Verify the ported code passes tests
6. Create a pull request for review

---

## 2. Five Reconciliation Decisions

### Decision 1: ENUM Syntax Approach
**Status:** ⏳ PENDING OPERATOR INPUT

**Question:** Which ENUM handling syntax should migrations 0001–0013 use?

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **A** | Keep sandbox idempotent `DO $$ BEGIN ... EXCEPTION ... END $$` | Safer for re-runs; more verbose |
| **B** | Adopt origin's direct `CREATE TYPE` + `postgresql.ENUM` | Cleaner; standard; fails on re-run |
| **C** | Use `CREATE TYPE IF NOT EXISTS` (PG 9.1+) | Modern; idempotent; requires PG 9.1+ |

**Default if no input:** Use origin's version (Option B) — the feature branch starts from origin/main HEAD which already has this syntax. No action needed unless operator specifically requests changing to Option A or C.

**Impact:** If Option B (default), migrations 0001–0013 require NO changes — they already have the origin syntax. If Option A, 13 files must be modified.

---

### Decision 2: UUID for `prompt_tag_associations.prompt_id`
**Status:** ✅ APPROVED

**Resolution:** Adopt `UUID(as_uuid=True)` for `prompt_tag_associations.prompt_id`.

**Evidence (all 5 sources agree):**
1. ORM model (both trees): UUID
2. FK target (`prompts.id`): UUID
3. Origin HEAD migration: UUID
4. Schema-wide pattern: 26/29 columns use UUID
5. Origin fix commit changed String(36) → UUID deliberately

**Action Required:** Include a defensive type-conversion migration in the chain:

```python
# Migration: fix_prompt_tag_assoc_prompt_id_type
def upgrade() -> None:
    op.execute("""
        ALTER TABLE prompt_tag_associations
        ALTER COLUMN prompt_id TYPE uuid USING prompt_id::uuid
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE prompt_tag_associations
        ALTER COLUMN prompt_id TYPE varchar(36) USING prompt_id::text
    """)
```

**Note:** Since the feature branch starts from origin/main HEAD, and origin already has UUID for this column in migration 0001, this migration is only needed if the production database was initialized from v5.1.0 migrations. Include it as a defensive measure.

> **⚠️ DESIGN NOTE — Defensive Conditional is Intentional:**
> The `IF ... <> 'uuid'` guard in this migration is a **deliberate no-op pattern**.
> If production already has UUID type (e.g., it was initialized from origin's migration 0001
> which correctly uses UUID), the ALTER TABLE is skipped entirely. This makes the migration
> safe to run in ANY environment — whether the column is currently `varchar(36)` (needs fix)
> or already `uuid` (no-op). Do not remove the conditional thinking it's dead code.



---

### Decision 3: Migration 0016 Chain Resolution
**Status:** ⏳ PENDING OPERATOR INPUT

**Question:** Which migration gets the 0016 slot?

| Option | 0016 | 0017 | Rationale |
|--------|------|------|-----------|
| **A** | Origin's `power_tdp_w` → gpu_nodes | Sandbox's `created_by` → projects | Origin's is already in place |
| **B** | Sandbox's `created_by` → projects | Origin's `power_tdp_w` → gpu_nodes | Sandbox's addresses a core schema gap |

**Default if no input:** Use Option A — the feature branch starts from origin/main HEAD which already has `0016_add_power_tdp_w.py`. The sandbox's `created_by` migration gets renumbered to 0017, and all subsequent sandbox migrations shift by +1.

**Impact on renumbering:** See Section 4 for the complete mapping.

---

### Decision 4: Migration Renumbering
**Status:** ✅ DOCUMENTED (depends on Decision 3)

See Section 4 for the complete renumbering table. The default mapping (assuming Decision 3 = Option A) shifts all sandbox migrations 0016–0022 by +1 to positions 0017–0023, plus adds bonus scope items.

---

### Decision 5: `power_tdp_w` Addition to Sandbox ORM
**Status:** ⏳ PENDING OPERATOR INPUT

**Question:** Should `power_tdp_w` be added to the sandbox `gpu_node.py` model?

| Option | Description |
|--------|-------------|
| **A** | Yes — add the column to match origin's model | Ensures ORM-migration parity |
| **B** | No — rely on origin's existing model | If using origin's gpu_node.py as-is |

**Default if no input:** Yes (Option A) — the ported `gpu_node.py` must include `power_tdp_w` to match origin's migration 0016.

**Implementation:**
```python
# Add to app/models/gpu_node.py, after total_vram_mb field:
power_tdp_w: Mapped[Optional[int]] = mapped_column(
    Integer, nullable=True,
    comment="GPU thermal design power in watts (e.g., 350 for RTX 5000 Pro Blackwell). Per spec Appendix C.4.",
)
```

---

## 3. Bonus Scope Items

### 3.1 `prompt_tags.id` Type Fix
**Status:** ✅ APPROVED

Both trees have `prompt_tags.id` as `String(36)` in migration 0001, but the ORM model defines it as `UUID(as_uuid=True)`. This is a pre-existing bug in both trees.

**Action:** Add a type-conversion migration:

```python
# Migration: fix_prompt_tags_id_type
def upgrade() -> None:
    # First fix the FK in prompt_tag_associations that references this PK
    op.execute("""
        ALTER TABLE prompt_tag_associations
        ALTER COLUMN tag_id TYPE uuid USING tag_id::uuid
    """)
    op.execute("""
        ALTER TABLE prompt_tags
        ALTER COLUMN id TYPE uuid USING id::uuid
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE prompt_tags
        ALTER COLUMN id TYPE varchar(36) USING id::text
    """)
    op.execute("""
        ALTER TABLE prompt_tag_associations
        ALTER COLUMN tag_id TYPE varchar(36) USING tag_id::text
    """)
```

**Note:** The `tag_id` FK in `prompt_tag_associations` must be converted BEFORE or simultaneously with the PK it references. The `USING` clause handles the cast safely since all values are generated by `gen_random_uuid()::text`.

### 3.2 `rollback_points.id` Investigation
**Status:** ✅ VERIFIED — NOT NEEDED

**Evidence (verified 2026-05-28):**
1. **No ORM model exists** — neither sandbox nor origin has `app/models/rollback_point.py`
2. `RollbackService` (`app/services/rollback_service.py`) uses a **plain Python class** (not SQLAlchemy):
   ```python
   class RollbackPoint:
       def __init__(self, id: str, version_tag: str, ...)
   ```
   It interacts with the database via raw `sa_text()` SQL, not ORM mapped columns
3. Migration 0001 defines `rollback_points.id` as `sa.String(36)` — **identical in both trees**
4. No other migration touches `rollback_points` in either tree

**Conclusion:** No type mismatch exists because there is no ORM model to conflict with the migration. The `String(36)` type in migration 0001 is consistent with the `str` type used in the service class. No migration fix required.

**Note:** If future UUID standardization of `rollback_points.id` is desired, that would be a separate enhancement ticket, not a reconciliation fix.

---

## 4. Migration Renumbering Table

### Default Mapping (Decision 3 = Option A: Origin 0016 stays)

The feature branch starts from origin/main HEAD which has migrations 0001–0016. Sandbox migrations are renumbered starting from 0017.

| Sandbox Source | Sandbox File Name | New Number | New File Name | `down_revision` |
|---------------|-------------------|------------|---------------|-----------------|
| Origin 0016 | `0016_add_power_tdp_w.py` | **0016** (unchanged) | `0016_add_power_tdp_w.py` | `"0015"` |
| Sandbox 0016 | `0016_add_projects_created_by.py` | **0017** | `0017_add_projects_created_by.py` | `"0016"` |
| Sandbox 0017 | `0017_add_quality_scores_job_id.py` | **0018** | `0018_add_quality_scores_job_id.py` | `"0017"` |
| Sandbox 0018 | `0018_add_retention_policies_description.py` | **0019** | `0019_add_retention_policies_description.py` | `"0018"` |
| Sandbox 0019 | `0019_add_prompt_tags_description.py` | **0020** | `0020_add_prompt_tags_description.py` | `"0019"` |
| Sandbox 0020 | `0020_add_backup_records_error_message.py` | **0021** | `0021_add_backup_records_error_message.py` | `"0020"` |
| Sandbox 0021 | `0021_add_quality_scores_review_notes.py` | **0022** | `0022_add_quality_scores_review_notes.py` | `"0021"` |
| Sandbox 0022 | `0022_add_storage_quotas_unique_index.py` | **0023** | `0023_add_storage_quotas_unique_index.py` | `"0022"` |
| *(new)* | *Decision 2: fix prompt_tag_assoc type* | **0024** | `0024_fix_prompt_tag_assoc_prompt_id_type.py` | `"0023"` |
| *(new)* | *Bonus 3.1: fix prompt_tags.id type* | **0025** | `0025_fix_prompt_tags_id_type.py` | `"0024"` |

### Renumbering Rules

For each renumbered migration file:
1. **Rename** the file (e.g., `0016_...py` → `0017_...py`)
2. **Update** the `revision = ` line to match the new number (e.g., `"0016"` → `"0017"`)
3. **Update** the `down_revision = ` line to point to the new predecessor (e.g., `"0015"` → `"0016"`)
4. **Update** the docstring header revision reference if present

### Alternative Mapping (Decision 3 = Option B: Sandbox 0016 stays at 0016)

If the operator chooses Option B, origin's `power_tdp_w` becomes 0017 and all else shifts:

| Migration | Number | `down_revision` |
|-----------|--------|-----------------|
| Sandbox `created_by` | 0016 | `"0015"` |
| Origin `power_tdp_w` | 0017 | `"0016"` |
| Sandbox `job_id` | 0018 | `"0017"` |
| *(etc. — all shift by +1 from this point)* | | |

---

## 5. Files to Port

### 5.1 Source Category: Files That Differ From Origin HEAD

These files carry sandbox-specific modifications. They must be **carefully merged** — not blindly copied — because origin HEAD may have made its own changes to some of them.

#### Strategy A: Files Modified ONLY by Sandbox (Safe to Copy)

These files are identical in origin HEAD and the closest match. Sandbox changes are purely additive.

| # | Sandbox Path | Origin Path | Change Description |
|---|-------------|-------------|-------------------|
| 1 | `app/models/project.py` | `ivgs-api/app/models/project.py` | Added `created_by` FK column |
| 2 | `app/models/quality_score.py` | `ivgs-api/app/models/quality_score.py` | Added `job_id` FK column |
| 3 | `app/models/retention_policy.py` | `ivgs-api/app/models/retention_policy.py` | Added `description` column, `Text` import |

#### Strategy B: Files Modified by BOTH Sandbox and Origin (Require Manual Merge)

These files were changed by the sandbox AND by origin after the v5.1.0 fork point. **Do not blindly copy** — compare both versions and merge.

| # | File | Sandbox Changes | Origin Changes |
|---|------|----------------|----------------|
| 1 | `app/api/v1/__init__.py` | Removed prefix/tags from projects router | Route registrations for expanded prompts/GPU endpoints |
| 2 | `app/models/gpu_node.py` | Added `used_vram_mb`/`available_vram_mb` properties | Added `power_tdp_w` column |
| 3 | `app/models/prompt.py` | Added `scope` property | Added prompt library features |
| 4 | `app/models/user.py` | Added `is_active` column | Added `is_active` column + additional fields |
| 5 | `app/services/prompt_service.py` | Added Jinja2 syntax validation | Expanded prompt library methods |
| 6 | `app/api/deps.py` | Created as new file | Created as new file (may differ) |

#### Strategy C: Files Modified Only in Working Tree (Phase 0b/0c Sandbox Work)

These files were modified during sandbox bug-fix phases and need to be ported. They are NOT in the baseline commit `634ec66` but exist on the sandbox working tree disk.

| # | Sandbox Path | Change Description |
|---|-------------|-------------------|
| 1 | `app/api/v1/backup.py` | Bug fix modifications |
| 2 | `app/api/v1/manifests.py` | Field name corrections |
| 3 | `app/api/v1/quotas.py` | Endpoint fixes |
| 4 | `app/api/v1/ws_logs.py` | WebSocket log endpoint |
| 5 | `app/middleware/rate_limit.py` | Rate limiting implementation |
| 6 | `app/models/backup_record.py` | Added `error_message` column (BUG-006) |

### 5.2 Test Files

#### conftest.py (Complete Rewrite — HIGH PRIORITY)

The sandbox `tests/conftest.py` is a **complete rewrite** (1271 lines) replacing the origin's Phase 2 stub. It includes:
- NullPool engine for clean connection disposal
- Committed-data fixtures with per-test table truncation
- Independent sessions for API handlers
- User factory functions (admin, operator, viewer)
- Token generation helpers
- Remedy A2: pytest reporting hook for asyncpg teardown errors

**Source:** `/home/ubuntu/test_workspace/ivgs-api/tests/conftest.py`  
**Action:** Copy to `ivgs-api/tests/conftest.py` on the feature branch

#### New Test Files (35 files)

These are entirely new files created during sandbox development. **Safe to copy directly.**

```
tests/test_api_backup.py
tests/test_api_jobs.py
tests/test_api_languages.py
tests/test_api_nodes.py
tests/test_api_pagination.py
tests/test_api_rbac.py
tests/test_bug_001_backup_error_handler.py
tests/test_bug_003_manifest_field_names.py
tests/test_bug_004_manifest_asset_checksum.py
tests/test_bug_005_backup_field_names.py
tests/test_bug_009_quota_field_names.py
tests/test_critical_paths.py
tests/test_rate_limiting_basic.py
tests/test_rate_limiting_edge_cases.py
tests/test_rate_limiting_lockout.py
tests/test_service_asset.py
tests/test_service_auth.py
tests/test_service_checkpoint.py
tests/test_service_dlq.py
tests/test_service_gpu.py
tests/test_service_job.py
tests/test_service_language.py
tests/test_service_project.py
tests/test_service_prompt.py
tests/test_service_quality.py
tests/test_service_retention.py
tests/test_service_retention_extended.py
tests/test_service_rollback.py
tests/test_service_storyboard.py
tests/test_service_transcript.py
tests/test_service_user.py
tests/test_ws_connection.py
tests/test_ws_edge_cases.py
tests/test_ws_job_status.py
tests/test_ws_node_logs.py
```

#### Existing Test Files (Modified)

These exist in both sandbox baseline and origin. The sandbox versions may have modifications.

| # | File | Action |
|---|------|--------|
| 1 | `tests/test_rollback_probe.py` | Sandbox-only diagnostic — **include** (it won't conflict) |
| 2 | `tests/test_assets.py` through `tests/test_users.py` | Compare sandbox vs origin versions. If identical, skip. If different, merge. |

### 5.3 Migration Files

| # | Source | Action |
|---|--------|--------|
| 1 | Origin 0001–0016 | Already on feature branch — **no action** (unless Decision 1 changes ENUM syntax) |
| 2 | Sandbox 0016 (`add_projects_created_by`) | **Copy and renumber** to 0017 |
| 3 | Sandbox 0017 (`add_quality_scores_job_id`) | **Copy and renumber** to 0018 |
| 4 | Sandbox 0018 (`add_retention_policies_description`) | **Copy and renumber** to 0019 |
| 5 | Sandbox 0019 (`add_prompt_tags_description`) | **Copy and renumber** to 0020 |
| 6 | Sandbox 0020 (`add_backup_records_error_message`) | **Copy and renumber** to 0021 |
| 7 | Sandbox 0021 (`add_quality_scores_review_notes`) | **Copy and renumber** to 0022 |
| 8 | Sandbox 0022 (`add_storage_quotas_unique_index`) | **Copy and renumber** to 0023 |
| 9 | *(new)* Decision 2 type fix | **Create new** as 0024 |
| 10 | *(new)* Bonus 3.1 type fix | **Create new** as 0025 |

### 5.4 Files NOT to Port

| File/Category | Reason |
|--------------|--------|
| `tests/test_rollback_probe.py` | Sandbox diagnostic — optional, low value |
| `.env.phase6` | Environment-specific configuration |
| `*.docx`, `*.pdf` auto-generated docs | Build artifacts |
| `INDEPENDENT_VERIFICATION.log`, `FORENSIC_*.log`, etc. | Investigation artifacts |
| `BASELINE_DIVERGENCE_REPORT.md`, `CURRENT_STATE.md`, etc. | Analysis documents |
| `.coverage`, `.logs/` | Test/log artifacts |

---

## 6. ORM Model Changes

### 6.1 Changes Already in Sandbox (Port As-Is)

| File | Change | Description |
|------|--------|-------------|
| `app/models/project.py` | Add `created_by` column | `UUID FK → users.id, ondelete=CASCADE, nullable=False` |
| `app/models/quality_score.py` | Add `job_id` column | `UUID FK → render_jobs.id, ondelete=CASCADE, nullable=False` |
| `app/models/retention_policy.py` | Add `description` column | `Text, nullable=True` |
| `app/models/backup_record.py` | Add `error_message` column | `Text, nullable=True` (BUG-006) |
| `app/models/gpu_node.py` | Add `used_vram_mb`/`available_vram_mb` properties | Computed properties from reservations |
| `app/models/prompt.py` | Add `scope` property | Derives SCENE/PROJECT/GLOBAL from IDs |

### 6.2 New Change Required: `power_tdp_w` (Decision 5)

Add to `app/models/gpu_node.py`:

```python
from sqlalchemy import Integer  # add to imports if not present

# Add after total_vram_mb field definition:
power_tdp_w: Mapped[Optional[int]] = mapped_column(
    Integer, nullable=True,
    comment="GPU thermal design power in watts (e.g., 350 for RTX 5000 Pro Blackwell). Per spec Appendix C.4.",
)
```

**Important:** Check if origin's `gpu_node.py` already has this column (it does at `b1082d7`). If using origin's version as the base, this change is already present. The porting agent only needs to ADD the sandbox's `used_vram_mb`/`available_vram_mb` properties to origin's version.

### 6.3 Merge Strategy for `gpu_node.py`

Origin has: `power_tdp_w` column (in model and migration 0016)
Sandbox has: `used_vram_mb`/`available_vram_mb` computed properties (NOT in origin)

**Action:** Start with origin's `gpu_node.py`, then add the sandbox's two `@property` methods:

```python
@property
def used_vram_mb(self) -> int:
    """Calculate used VRAM from active reservations."""
    if not self.reservations:
        return 0
    return sum(
        r.reserved_vram_mb
        for r in self.reservations
        if r.status in ("reserved", "active")
    )

@property
def available_vram_mb(self) -> int:
    """Calculate available VRAM."""
    total = self.total_vram_mb or 0
    return total - self.used_vram_mb
```

---

## 7. Step-by-Step Porting Procedure

### Prerequisites

- GitHub access to `brucecostello2/elearning_v5` repository
- Access to sandbox files at `/home/ubuntu/test_workspace/ivgs-api/`
- PostgreSQL 15+ available for testing (install if needed)
- Python 3.11+ with `pip`

### Phase 1: Setup

```bash
# Step 1.1: Clone the repository (if not already cloned)
mkdir -p /home/ubuntu/github_repos
cd /home/ubuntu/github_repos
# Use get_github_access_token from Git_Tool to get token
git clone --depth=50 https://x-access-token:<TOKEN>@github.com/brucecostello2/elearning_v5.git
cd elearning_v5

# Step 1.2: Verify origin/main HEAD
git log --oneline -1 origin/main
# Expected: b1082d7 chore: gitignore rollback-storage and configs/grafana

# Step 1.3: Create feature branch
git checkout -b feature/defect-8-test-restoration origin/main

# Step 1.4: Configure git identity (use get_my_info from Git_Tool)
git config user.name "<github_username>"
git config user.email "<github_email>"
```

### Phase 2: Port Source Files

```bash
# Step 2.1: Identify the sandbox source directory
SANDBOX="/home/ubuntu/test_workspace/ivgs-api"
TARGET="./ivgs-api"

# Step 2.2: Copy files that are SAFE to copy (sandbox-only modifications)
# These files were only modified in the sandbox, not in origin after v5.1.0
cp "$SANDBOX/app/models/project.py"          "$TARGET/app/models/project.py"
cp "$SANDBOX/app/models/quality_score.py"    "$TARGET/app/models/quality_score.py"
cp "$SANDBOX/app/models/retention_policy.py" "$TARGET/app/models/retention_policy.py"
cp "$SANDBOX/app/models/backup_record.py"    "$TARGET/app/models/backup_record.py"

# Step 2.3: Copy Phase 0b/0c source fixes
cp "$SANDBOX/app/api/v1/backup.py"           "$TARGET/app/api/v1/backup.py"
cp "$SANDBOX/app/api/v1/manifests.py"        "$TARGET/app/api/v1/manifests.py"
cp "$SANDBOX/app/api/v1/quotas.py"           "$TARGET/app/api/v1/quotas.py"
cp "$SANDBOX/app/api/v1/ws_logs.py"          "$TARGET/app/api/v1/ws_logs.py"
cp "$SANDBOX/app/middleware/rate_limit.py"    "$TARGET/app/middleware/rate_limit.py"

# Step 2.4: MANUAL MERGE required for these files
# DO NOT blindly copy — compare and merge:
#   - app/models/gpu_node.py (add sandbox @property methods to origin version)
#   - app/models/prompt.py (add sandbox scope property to origin version)
#   - app/models/user.py (verify is_active column exists in both, merge other changes)
#   - app/api/v1/__init__.py (merge route registration changes)
#   - app/api/deps.py (compare both versions, use origin + sandbox additions)
#   - app/services/prompt_service.py (add Jinja2 validation to origin version)
```

#### Detailed Manual Merge Notes

**1. `app/models/gpu_node.py`**
- **Sandbox added:** VRAM tracking `@property` methods (`used_vram_mb`, `available_vram_mb`, `vram_utilization_pct`) and GPU metrics helpers
- **Origin added:** `power_tdp_w` and `power_actual_w` columns (from `8a53688` GPU fleet commit), GPU fleet monitoring infrastructure
- **Expected merge:** Keep BOTH — add sandbox `@property` methods into origin's version that already has power columns. Result: complete GPU node model with memory + power tracking

**2. `app/models/prompt.py`**
- **Sandbox added:** `scope` computed property for prompt categorization, enhanced metadata handling
- **Origin added:** lib-prompts integration fields, prompt library management support
- **Expected merge:** Add sandbox `scope` property into origin version. Both sets of changes are additive and non-conflicting

**3. `app/models/user.py`**
- **Sandbox added:** `is_active` column (via migration 0015), used in auth checks
- **Origin added:** Same `is_active` column may exist from independent work; verify column definitions match
- **Expected merge:** Compare definitions — if identical, use origin version. If sandbox has additional changes, merge them in

**4. `app/api/v1/__init__.py`**
- **Sandbox added:** Route registrations for new/modified endpoints (ws_logs, rate limiting middleware mount)
- **Origin added:** Route registrations for GPU fleet, power monitoring endpoints
- **Expected merge:** Union of all route registrations from both versions. Check for conflicting URL prefixes

**5. `app/api/deps.py`**
- **Sandbox added:** Enhanced dependency injection helpers, possibly `require_admin` improvements
- **Origin added:** lib-prompts dependencies, GPU fleet dependencies
- **Expected merge:** Use origin as base, add any sandbox-only dependency functions. Watch for import path differences (sandbox moved `require_admin` to `app.core.rbac`)

**6. `app/services/prompt_service.py`**
- **Sandbox added:** Jinja2 template syntax validation (`_validate_jinja2_syntax()`), enhanced error handling for template rendering, bug fixes
- **Origin added:** lib-prompts service integration, prompt library CRUD operations
- **Expected merge:** Keep sandbox Jinja2 validation (fixes production bugs), add origin's library service methods. The sandbox validation code is self-contained and can be inserted into the origin version without conflict


### Phase 3: Port Test Files

```bash
# Step 3.1: Copy the rewritten conftest.py
cp "$SANDBOX/tests/conftest.py" "$TARGET/tests/conftest.py"

# Step 3.2: Copy all 35 new test files
for f in \
  test_api_backup.py test_api_jobs.py test_api_languages.py \
  test_api_nodes.py test_api_pagination.py test_api_rbac.py \
  test_bug_001_backup_error_handler.py test_bug_003_manifest_field_names.py \
  test_bug_004_manifest_asset_checksum.py test_bug_005_backup_field_names.py \
  test_bug_009_quota_field_names.py test_critical_paths.py \
  test_rate_limiting_basic.py test_rate_limiting_edge_cases.py \
  test_rate_limiting_lockout.py test_service_asset.py \
  test_service_auth.py test_service_checkpoint.py test_service_dlq.py \
  test_service_gpu.py test_service_job.py test_service_language.py \
  test_service_project.py test_service_prompt.py test_service_quality.py \
  test_service_retention.py test_service_retention_extended.py \
  test_service_rollback.py test_service_storyboard.py \
  test_service_transcript.py test_service_user.py \
  test_ws_connection.py test_ws_edge_cases.py test_ws_job_status.py \
  test_ws_node_logs.py; do
  cp "$SANDBOX/tests/$f" "$TARGET/tests/$f"
done

# Step 3.3: Compare existing test files (optional — if sandbox modified them)
# diff "$SANDBOX/tests/test_assets.py" "$TARGET/tests/test_assets.py"
# ... repeat for each existing test file
```

### Phase 4: Port and Renumber Migrations

```bash
# Step 4.1: Verify origin migrations are in place
ls "$TARGET/migrations/versions/"
# Expected: 0001 through 0016 (16 files)

# Step 4.2: Copy and renumber sandbox migrations
# NOTE: Update revision, down_revision, and docstring in each file!

# 0016 → 0017
cp "$SANDBOX/migrations/versions/0016_add_projects_created_by.py" \
   "$TARGET/migrations/versions/0017_add_projects_created_by.py"
# Edit: revision = "0017", down_revision = "0016"

# 0017 → 0018
cp "$SANDBOX/migrations/versions/0017_add_quality_scores_job_id.py" \
   "$TARGET/migrations/versions/0018_add_quality_scores_job_id.py"
# Edit: revision = "0018", down_revision = "0017"

# 0018 → 0019
cp "$SANDBOX/migrations/versions/0018_add_retention_policies_description.py" \
   "$TARGET/migrations/versions/0019_add_retention_policies_description.py"
# Edit: revision = "0019", down_revision = "0018"

# 0019 → 0020
cp "$SANDBOX/migrations/versions/0019_add_prompt_tags_description.py" \
   "$TARGET/migrations/versions/0020_add_prompt_tags_description.py"
# Edit: revision = "0020", down_revision = "0019"

# 0020 → 0021
cp "$SANDBOX/migrations/versions/0020_add_backup_records_error_message.py" \
   "$TARGET/migrations/versions/0021_add_backup_records_error_message.py"
# Edit: revision = "0021", down_revision = "0020"

# 0021 → 0022
cp "$SANDBOX/migrations/versions/0021_add_quality_scores_review_notes.py" \
   "$TARGET/migrations/versions/0022_add_quality_scores_review_notes.py"
# Edit: revision = "0022", down_revision = "0021"

# 0022 → 0023
cp "$SANDBOX/migrations/versions/0022_add_storage_quotas_unique_index.py" \
   "$TARGET/migrations/versions/0023_add_storage_quotas_unique_index.py"
# Edit: revision = "0023", down_revision = "0022"
```

### Phase 5: Create New Migrations (Bonus Scope)

```bash
# Step 5.1: Create Decision 2 migration (prompt_tag_associations.prompt_id type fix)
cat > "$TARGET/migrations/versions/0024_fix_prompt_tag_assoc_prompt_id_type.py" << 'MIGRATION'
"""Fix prompt_tag_associations.prompt_id type: VARCHAR(36) → UUID

Decision 2 of Reconciliation Specification.
Defensive migration: converts type if it's currently VARCHAR(36).
Safe because all values are valid UUIDs (FK to prompts.id which is UUID).

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check current type and convert if needed
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'prompt_tag_associations'
        AND column_name = 'prompt_id'
    """))
    row = result.fetchone()
    if row and row[0] == 'character varying':
        op.execute("""
            ALTER TABLE prompt_tag_associations
            ALTER COLUMN prompt_id TYPE uuid USING prompt_id::uuid
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE prompt_tag_associations
        ALTER COLUMN prompt_id TYPE varchar(36) USING prompt_id::text
    """)
MIGRATION

# Step 5.2: Create Bonus 3.1 migration (prompt_tags.id type fix)
cat > "$TARGET/migrations/versions/0025_fix_prompt_tags_id_type.py" << 'MIGRATION'
"""Fix prompt_tags.id and prompt_tag_associations.tag_id type: VARCHAR(36) → UUID

Bonus scope item 3.1 from Reconciliation Specification.
Both the PK and its FK must be converted together.
Safe because all values are generated by gen_random_uuid()::text.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Check if prompt_tags.id is currently varchar
    result = conn.execute(sa.text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'prompt_tags' AND column_name = 'id'
    """))
    row = result.fetchone()
    if row and row[0] == 'character varying':
        # Must convert FK column first (or simultaneously)
        op.execute("""
            ALTER TABLE prompt_tag_associations
            ALTER COLUMN tag_id TYPE uuid USING tag_id::uuid
        """)
        op.execute("""
            ALTER TABLE prompt_tags
            ALTER COLUMN id TYPE uuid USING id::uuid
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE prompt_tags
        ALTER COLUMN id TYPE varchar(36) USING id::text
    """)
    op.execute("""
        ALTER TABLE prompt_tag_associations
        ALTER COLUMN tag_id TYPE varchar(36) USING tag_id::text
    """)
MIGRATION
```

### Phase 6: Apply ORM Model Changes

```bash
# Step 6.1: Merge gpu_node.py (add sandbox properties to origin version)
# Use the approach described in Section 6.3
# Open $TARGET/app/models/gpu_node.py and add the two @property methods

# Step 6.2: Verify all ORM models match their migrations
# Cross-reference each model file against the migration chain to ensure
# every column defined in the ORM has a corresponding migration.
```

### Phase 7: Update `down_revision` Pointers

This is the most critical step. Each migration file must have the correct chain.

```bash
# Verify the chain is correct:
cd "$TARGET"
grep -h "^revision = \|^down_revision = " migrations/versions/*.py | paste - - | sort
```

Expected output:
```
revision = "0001"	down_revision = None
revision = "0002"	down_revision = "0001"
...
revision = "0016"	down_revision = "0015"
revision = "0017"	down_revision = "0016"
revision = "0018"	down_revision = "0017"
...
revision = "0025"	down_revision = "0024"
```

### Phase 8: Verification

See Section 8 for complete verification commands.

### Phase 9: Commit and Push

```bash
cd /home/ubuntu/github_repos/elearning_v5

git add ivgs-api/
git status  # Review all changes

git commit -m "feat(ivgs-api): reconcile sandbox work — schema fixes, tests, migrations

Ported from sandbox development environment per Reconciliation Specification v1.0.

Changes:
- Port 7 schema gap migrations (0017-0023, renumbered from sandbox 0016-0022)
- Add 2 type-fix migrations (0024-0025) for prompt_tag_associations/prompt_tags
- Port complete conftest.py rewrite (NullPool, factories, per-test truncation)
- Add 35 new test files (service tests, API tests, bug regression, WebSocket)
- Merge ORM model changes (project.py, quality_score.py, retention_policy.py, etc.)
- Add gpu_node.py VRAM computed properties alongside existing power_tdp_w
- Port bug fixes: BUG-006 (backup error_message), BUG-007 (quality review_notes)
- Port API/middleware fixes (backup, manifests, quotas, rate limiting)"

# Push to remote
git push origin feature/defect-8-test-restoration

# Create PR using Git_Tool
```

---

## 8. Verification Commands

### 8.1 Migration Chain Validation

```bash
cd ivgs-api

# Verify migration chain integrity (no gaps, no forks)
grep -h "^revision = \|^down_revision = " migrations/versions/*.py | \
  paste - - | sort -t'"' -k2 -V

# Verify chain is linear (each down_revision matches previous revision)
python3 -c "
import os, re
versions = {}
for f in sorted(os.listdir('migrations/versions/')):
    if not f.endswith('.py') or f == '__init__.py' or f == 'env.py':
        continue
    content = open(f'migrations/versions/{f}').read()
    rev = re.search(r'revision = \"(.+?)\"', content)
    down = re.search(r'down_revision = (.+)', content)
    if rev:
        r = rev.group(1)
        d = down.group(1).strip().strip('\"') if down else 'None'
        if d == 'None': d = None
        versions[r] = (d, f)

# Walk the chain
current = None
chain = []
for r, (d, f) in sorted(versions.items()):
    if d is None:
        current = r
        chain.append((r, f))
        break

while current in [d for r, (d, f) in versions.items() if d == current]:
    nexts = [(r, f) for r, (d, f) in versions.items() if d == current]
    if len(nexts) != 1:
        print(f'ERROR: Fork or gap at {current}: {nexts}')
        break
    current = nexts[0][0]
    chain.append((current, versions[current][1]))

print(f'Migration chain: {len(chain)} migrations')
for r, f in chain:
    print(f'  {r}: {f}')
if len(chain) != len(versions):
    print(f'WARNING: {len(versions) - len(chain)} orphaned migrations!')
else:
    print('Chain is complete and linear ✅')
"
```

### 8.2 ORM-Migration Consistency Check

```bash
# Check that every model column has a migration that creates it
# This is a manual check — review each model file and trace its columns
# to the migration chain.

# Quick automated check for common issues:
python3 -c "
import ast, os
model_dir = 'app/models/'
for f in sorted(os.listdir(model_dir)):
    if f.endswith('.py') and f != '__init__.py':
        with open(f'{model_dir}/{f}') as fh:
            content = fh.read()
        # Count mapped_column definitions
        cols = content.count('mapped_column(')
        print(f'{f}: {cols} columns')
"
```

### 8.3 Test Suite Execution

```bash
# Step 1: Install dependencies
cd ivgs-api
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx

# Step 2: Set up test database
export DATABASE_URL="postgresql+asyncpg://testuser:testpass@localhost:5432/testdb"
# Ensure PostgreSQL is running and testdb exists

# Step 3: Run full test suite
pytest tests/ -v --tb=short 2>&1 | tee test_results.log

# Step 4: Check results
grep -E "passed|failed|error" test_results.log | tail -5
```

### 8.4 Coverage Check

```bash
pip install pytest-cov
pytest tests/ --cov=app --cov-report=term-missing --cov-report=html 2>&1 | tee coverage_results.log
```

### 8.5 Import/Syntax Validation

```bash
# Check all Python files for syntax errors
find ivgs-api/ -name "*.py" -exec python3 -m py_compile {} \; 2>&1 | head -20

# Check for circular imports
cd ivgs-api
python3 -c "import app; print('Import OK')" 2>&1
```

---

## 9. Success Criteria

### 9.1 Migration Chain

- [ ] All migrations 0001–0025 have correct `revision` and `down_revision`
- [ ] Chain is linear with no gaps or forks
- [ ] `alembic upgrade head` succeeds on a clean database
- [ ] `alembic downgrade base` succeeds from head
- [ ] `alembic current` shows `0025` after full upgrade

### 9.2 ORM-Migration Parity

- [ ] Every `mapped_column()` in model files has a corresponding migration column
- [ ] Every migration column has a corresponding ORM definition
- [ ] `prompt_tag_associations.prompt_id` is `UUID` (not `String(36)`)
- [ ] `prompt_tags.id` is `UUID` (not `String(36)`) — after migration 0025
- [ ] `gpu_nodes.power_tdp_w` exists in both model and migration
- [ ] `projects.created_by` exists in both model and migration
- [ ] `asset_quality_scores.job_id` exists in both model and migration
- [ ] `retention_policies.description` exists in both model and migration
- [ ] `backup_records.error_message` exists in both model and migration
- [ ] `asset_quality_scores.review_notes` exists in both model and migration

### 9.3 Test Suite

- [ ] All original sandbox tests pass (≥513 tests expected from prior session final count)
- [ ] All 35 new test files are present
- [ ] `conftest.py` is the rewritten version (1271 lines, NullPool, factories)
- [ ] No import errors in any test file
- [ ] `pytest tests/ -v` completes without crashes

### 9.4 Source Code

- [ ] `gpu_node.py` has BOTH `power_tdp_w` column AND `used_vram_mb`/`available_vram_mb` properties
- [ ] `project.py` has `created_by` column
- [ ] `quality_score.py` has `job_id` column
- [ ] `retention_policy.py` has `description` column
- [ ] `backup_record.py` has `error_message` column
- [ ] `prompt.py` has `scope` property
- [ ] `prompt_service.py` has Jinja2 syntax validation
- [ ] Bug fixes (BUG-006, BUG-007) are applied

### 9.5 PR Quality

- [ ] Feature branch is based on origin/main HEAD (`b1082d7` or later)
- [ ] All files are properly committed
- [ ] Commit message describes the reconciliation scope
- [ ] No untracked sandbox artifacts (logs, docs, coverage files)
- [ ] PR description references this reconciliation specification

---

## Appendix A: Reference Commit Hashes

| Reference | Hash | Description |
|-----------|------|-------------|
| Sandbox baseline | `634ec66` | `fix: restore full test suite — 153/153 passing` |
| Origin/main HEAD | `b1082d7` | `chore: gitignore rollback-storage and configs/grafana` |
| Closest match (v5.1.0 merge) | `0d73697` | `Merge remediation/comprehensive-spec-compliance` |
| Sandbox working tree HEAD | `bca5b9a` | `docs: prompt_id production type verification for Decision 2` |
| ENUM fix commit | `6ee4229` | `fix(migrations): hybrid ENUM fix` |
| ENUM fix v2 commit | `dfd1947` | `fix: hybrid ENUM migration fix v5.1.2` |
| GPU fleet commit | `8a53688` | `feat(gpu-fleet): close defects #2, #6, #7 + power_tdp_w gap` |

## Appendix B: Repository Structure

```
brucecostello2/elearning_v5/         (GitHub monorepo)
├── .github/                          (CI/CD workflows)
├── ivgs-api/                         (FastAPI backend — THIS IS THE TARGET)
│   ├── app/
│   │   ├── api/v1/                   (API route handlers)
│   │   ├── core/                     (auth, RBAC, security)
│   │   ├── middleware/               (audit, error handling, rate limiting)
│   │   ├── models/                   (SQLAlchemy ORM models)
│   │   ├── schemas/                  (Pydantic request/response schemas)
│   │   ├── scripts/                  (admin scripts)
│   │   └── services/                 (business logic services)
│   ├── config/                       (YAML configuration)
│   ├── migrations/versions/          (Alembic migrations)
│   ├── seed/                         (default prompt templates)
│   ├── tests/                        (pytest test suite)
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── main.py
│   └── requirements.txt
├── ivgs-frontend/                    (Next.js frontend — NOT in scope)
├── ivgs-workers/                     (Celery workers — NOT in scope)
├── ivgs-scheduler/                   (Job scheduler — NOT in scope)
├── ivgs-infra/                       (Docker/infrastructure — NOT in scope)
├── shared/                           (Shared utilities — 100% identical, no changes)
└── pyproject.toml
```

## Appendix C: Sandbox Working Directory

```
/home/ubuntu/test_workspace/          (git root — disjoint from origin)
└── ivgs-api/                         (sandbox working directory)
    ├── app/                          (source code with Phase 0a/0b/0c modifications)
    ├── tests/                        (49 test files — 16 original + 33 new + conftest)
    ├── migrations/versions/          (22 migrations — 0001-0022)
    ├── config/                       (YAML configs)
    ├── seed/                         (prompt templates)
    ├── *.log, *.md                   (investigation artifacts — DO NOT port)
    └── .env.phase6                   (environment config — DO NOT port)
```

## Appendix D: Prior Investigation Artifacts

These files document the investigation that produced this specification. They are committed to the sandbox local branch for audit trail but should NOT be ported to the feature branch.

| File | Commit | Description |
|------|--------|-------------|
| `INDEPENDENT_VERIFICATION.log` | `d42a746` | Three-artifact verification (MD5, git diff, file count) |
| `MD5_SANDBOX_634ec66.txt` | `d42a746` | 144 MD5 hashes (sandbox tree) |
| `MD5_ORIGIN_b1082d7.txt` | `d42a746` | 145 MD5 hashes (origin tree) |
| `MD5_COMPARISON_RESULTS.txt` | `d42a746` | Per-file comparison results |
| `GIT_DIFF_OUTPUT.txt` | `d42a746` | Full git diff output |
| `FILES_SANDBOX_ONLY.txt` | `d42a746` | 1 sandbox-only file |
| `FILES_ORIGIN_ONLY.txt` | `d42a746` | 2 origin-only files |
| `FORENSIC_BASELINE_INVESTIGATION.log` | `205afb5` | Origin search + "100% match" assessment |
| `CLOSEST_MATCH_DIFF_ANALYSIS.txt` | `205afb5` | Closest match detail |
| `MIGRATION_RECONCILIATION_ANALYSIS.log` | `517267f` | Raw migration analysis |
| `PROMPT_ID_PRODUCTION_VERIFICATION.log` | `bca5b9a` | prompt_id type forensic |

---

*Specification produced: 2026-05-27*  
*No source code was modified during specification creation.*  
*This document is the authoritative reference for the reconciliation porting task.*
