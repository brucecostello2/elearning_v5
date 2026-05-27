# Schema Migration Gap Report

**Phase:** 0a — Schema Audit (Investigation Only, No Code Changes)
**Date:** 2026-05-27
**Commit:** `d09d98a` (TEST_IMPLEMENTATION_PLAN_v3.md)
**Workspace:** `/home/ubuntu/test_workspace/ivgs-api/`
**Baseline Tests:** 153 passed (56.52s)

---

## Executive Summary

Comprehensive line-by-line audit of all 24 ORM models (23 files) against
14 Alembic migration files. Additionally scanned all API endpoint and
service files for raw SQL referencing columns that don't exist in ORM models.

### Key Findings

| Category | Count | Severity |
|---|---|---|
| Bugs total | **10** | 8 HIGH, 1 MEDIUM, 1 LOW |
| Model columns missing from migrations | **5** | HIGH — deployment blockers |
| API column name mismatches (raw SQL vs ORM) | **4 files** | HIGH — runtime errors |
| Tables matched perfectly | **19 of 24** | ✅ No issues |
| Tables in migration but no ORM class | 2 | Expected (association table + legacy) |

### Critical Finding

**Tests pass because `conftest.py` uses `Base.metadata.create_all()` which
reads the ORM models directly.** But production deployment uses
`alembic upgrade head` which reads migration files. The 5 missing columns
would not be created in production, causing runtime crashes.

The 4 API files with column name mismatches (`manifests.py`, `backup.py`,
`quotas.py`, `quality_service.py`) use hardcoded raw SQL strings that
reference columns by the wrong name. These endpoints **cannot work in
production** regardless of migration status.

---

## 1. Table-Level Audit

### 1.1 All 24 ORM Models

| # | Table | Model File | Class | Cols | Migration | Match? |
|---|---|---|---|---|---|---|
| 1 | `asset_quality_scores` | quality_score.py | AssetQualityScore | 10 | 0008_quality_scores.py | ⚠️ 1 col missing |
| 2 | `assets` | asset.py | Asset | 19 | 0001_initial_core.py | ✅ |
| 3 | `audit_log` | audit_log.py | AuditLog | 9 | 0001_initial_core.py | ✅ |
| 4 | `backup_records` | backup_record.py | BackupRecord | 11 | 0013_backup_records.py | ✅ |
| 5 | `composition_manifests` | composition_manifest.py | CompositionManifest | 13 | 0007_composition_manifests.py | ✅ |
| 6 | `dead_letter_messages` | dead_letter_queue.py | DeadLetterMessage | 14 | 0006_dead_letter_queue.py | ✅ |
| 7 | `fallback_policies` | fallback_policy.py | FallbackPolicy | 8 | 0014_fallback_policies.py | ✅ |
| 8 | `gpu_metrics_history` | gpu_metrics_history.py | GpuMetricsHistory | 9 | 0010_gpu_metrics.py | ✅ |
| 9 | `gpu_nodes` | gpu_node.py | GpuNode | 9 | 0003_gpu_registry.py | ✅ |
| 10 | `gpu_reservations` | gpu_node.py | GpuReservation | 8 | 0003_gpu_registry.py | ✅ |
| 11 | `language_variants` | language_variant.py | LanguageVariant | 7 | 0001_initial_core.py | ✅ |
| 12 | `pipeline_checkpoints` | checkpoint.py | PipelineCheckpoint | 11 | 0002_pipeline_checkpoints.py | ✅ |
| 13 | `projects` | project.py | Project | 11 | 0001_initial_core.py | ⚠️ 1 col missing |
| 14 | `prompt_tags` | prompt_tag.py | PromptTag | 4 | 0001_initial_core.py | ⚠️ 1 col missing |
| 15 | `prompts` | prompt.py | Prompt | 11 | 0001_initial_core.py | ✅ |
| 16 | `render_jobs` | render_job.py | RenderJob | 13 | 0001_initial_core.py | ✅ |
| 17 | `render_segments` | render_segment.py | RenderSegment | 10 | 0009_render_segments.py | ✅ |
| 18 | `retention_policies` | retention_policy.py | RetentionPolicy | 12 | 0011_retention_policies.py | ⚠️ 1 col missing |
| 19 | `storage_quotas` | storage_quota.py | StorageQuota | 9 | 0012_storage_quotas.py | ✅ |
| 20 | `storyboard_scenes` | storyboard_scene.py | StoryboardScene | 9 | 0001_initial_core.py | ✅ |
| 21 | `task_retries` | task_retry.py | TaskRetry | 9 | 0004_retry_tracking.py | ✅ |
| 22 | `transcripts` | transcript.py | Transcript | 8 | 0001_initial_core.py | ✅ |
| 23 | `users` | user.py | User | 7 | 0001_initial_core.py | ⚠️ 1 col missing |
| 24 | `worker_heartbeats` | worker_heartbeat.py | WorkerHeartbeat | 9 | 0005_worker_heartbeats.py | ✅ |

### 1.2 Tables in Migrations Without ORM Classes (Expected)

| Table | Migration | Reason |
|---|---|---|
| `prompt_tag_associations` | 0001_initial_core.py | M2M association table — defined as `Table()` in `prompt_tag.py`, not as a class |
| `rollback_points` | 0001_initial_core.py | Used by `rollback_service.py` via raw SQL — no ORM class needed |

**Verdict:** Both are legitimate. No action required.

---

## 2. Column-Level Gaps (BUG-008)

### 5 Columns in Models Missing from Migrations

| # | Table | Column | Model File : Line | Type | FK? | Impact |
|---|---|---|---|---|---|---|
| 1 | `users` | `is_active` | user.py:42 | `Boolean, default=True` | No | Users cannot be deactivated via Alembic deploy |
| 2 | `projects` | `created_by` | project.py:48 | `UUID, FK→users.id` | Yes | Project ownership missing — RBAC broken |
| 3 | `asset_quality_scores` | `job_id` | quality_score.py:32 | `UUID, FK→render_jobs.id` | Yes | Cannot link scores to jobs |
| 4 | `retention_policies` | `description` | retention_policy.py:30 | `Text, nullable=True` | No | Description field missing (non-breaking but incomplete) |
| 5 | `prompt_tags` | `description` | prompt_tag.py:62 | `Text, nullable=True` | No | Description field missing (non-breaking but incomplete) |

### Evidence: Database vs. Migration

The test database (created by `Base.metadata.create_all()`) **does** have
these columns. The migrations **do not** create them. This means:

```
Test environment:  create_all() → all 5 columns EXIST     → tests pass ✅
Production deploy: alembic upgrade head → 5 columns MISSING → app crashes ❌
```

### Required Migrations (Phase 0b)

```
0015_add_users_is_active.py
  → op.add_column('users', sa.Column('is_active', sa.Boolean(), 
    server_default='true', nullable=False))

0016_add_projects_created_by.py
  → op.add_column('projects', sa.Column('created_by', UUID(as_uuid=True),
    sa.ForeignKey('users.id'), nullable=True))

0017_add_quality_scores_job_id.py
  → op.add_column('asset_quality_scores', sa.Column('job_id', UUID(as_uuid=True),
    sa.ForeignKey('render_jobs.id', ondelete='SET NULL'), nullable=True))

0018_add_retention_description.py
  → op.add_column('retention_policies', sa.Column('description', sa.Text(), nullable=True))

0019_add_prompt_tags_description.py
  → op.add_column('prompt_tags', sa.Column('description', sa.Text(), nullable=True))
```

---

## 3. Complete Bug Inventory (10 Bugs)

### BUG-001 [HIGH] — NameError in backup error handler

**File:** `app/api/v1/backup.py`
**Lines:** 292, 299
**Type:** NameError (runtime crash)

```python
# Line 292:
    except Exception as _exc:  # noqa: F841    ← binds as _exc
# Line 299:
            {"id": backup_id, "error": str(exc)[:2000]},   ← references exc (UNDEFINED)
```

**Impact:** When a backup task fails, the error handler itself crashes with
`NameError: name 'exc' is not defined`. The backup status is never updated
to 'failed'.

**Fix:** Rename `_exc` to `exc` on line 292.
**Migration:** No.

---

### BUG-002 [LOW] — Dead code in manifests.py

**File:** `app/api/v1/manifests.py`
**Lines:** 85-92
**Type:** Dead code

```python
# Lines 85-92:
    _result = await db.execute(  # noqa: F841
        select("*").select_from(
            __import__("sqlalchemy").text("composition_manifests")
        ).where(
            __import__("sqlalchemy").text("job_id = :job_id")
        ),
        {"job_id": job_id},
    )
```

**Impact:** None — code is unreachable (result never used). The `# noqa: F841`
confirms the developer knew it was unused. `select("*")` is invalid
SQLAlchemy 2.0 syntax anyway.

**Fix:** Delete lines 85-92 (operator approved).
**Migration:** No.

---

### BUG-003 [HIGH] — manifests.py uses wrong column names

**File:** `app/api/v1/manifests.py`
**Lines:** 55, 99, 119, 227-228, 234, 246
**Type:** Schema mismatch (3 wrong column names)

| API Uses | ORM Model Has | Occurrences |
|---|---|---|
| `timeline_json` | `timeline` | 6 |
| `scene_count` | *(does not exist)* | 4 |
| `created_at` | *(does not exist)* | 3 |

**Evidence:**

```python
# manifests.py line 99 (raw SQL):
"SELECT id, job_id, status, timeline_json, total_duration_ms, "
"scene_count, created_at, locked_at "

# composition_manifest.py line 43 (ORM model):
timeline: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
# No scene_count column. No created_at column.
```

**Impact:** Every endpoint in `manifests.py` will fail with
`UndefinedColumn: column "timeline_json" does not exist`.

**Fix (per Q1 — align API to model):**
- Rename `timeline_json` → `timeline` in all SQL strings
- Remove `scene_count` references (compute dynamically from timeline JSON)
- Remove `created_at` references or compute from `locked_at`

**Migration:** No.

---

### BUG-004 [HIGH] — manifests.py uses sha256_hash (assets table)

**File:** `app/api/v1/manifests.py`
**Lines:** 176, 201, 345, 354, 359
**Type:** Column name mismatch

| API Uses | ORM Model Has |
|---|---|
| `sha256_hash` | `content_hash` |

**Evidence:**

```python
# manifests.py line 176 (raw SQL):
"SELECT id, scene_id, asset_type, seaweedfs_fid, sha256_hash "

# asset.py line 81 (ORM model):
content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
```

**Impact:** Asset checksum validation in manifest generation will fail.

**Fix (per Q1):** Rename `sha256_hash` → `content_hash` (5 occurrences).
**Migration:** No.

---

### BUG-005 [HIGH] — backup.py uses storage_path

**File:** `app/api/v1/backup.py`
**Lines:** 42, 141, 227, 263, 268, 274, 304, 312
**Type:** Column name mismatch

| API Uses | ORM Model Has |
|---|---|
| `storage_path` | `backup_path` |

**Evidence:**

```python
# backup.py line 42 (Pydantic schema):
    storage_path: Optional[str] = None

# backup.py line 141 (response mapping):
    storage_path=r.storage_path,   # ← r is Row from backup_records

# backup_record.py line 41 (ORM model):
    backup_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
```

**Impact:** Listing and reading backup records will fail with
`AttributeError: 'Row' object has no attribute 'storage_path'`.

**Fix (per Q1):** Rename `storage_path` → `backup_path` (8 occurrences).
**Migration:** No.

---

### BUG-006 [HIGH] — backup.py uses error_message (column doesn't exist)

**File:** `app/api/v1/backup.py`
**Lines:** 43, 142, 282, 297
**Type:** Missing column

```python
# backup.py line 43 (Pydantic schema):
    error_message: Optional[str] = None

# backup.py line 282 (raw SQL UPDATE):
    "error_message = :error, completed_at = :completed_at "

# backup_record.py (ORM model):
    # ← NO error_message column defined anywhere
```

**Impact:** Backup failure recording and response serialization will crash.

**Fix decision needed from operator:**
- **Option A:** Add `error_message` column to BackupRecord model + migration
  (preserves API design intent — backups *should* report error reasons)
- **Option B:** Remove `error_message` from API schema and SQL
  (simpler, but loses error context)

**Recommendation:** Option A — add column. Error messages are operationally
important for backup monitoring.

**Migration:** Yes (if Option A).

---

### BUG-007 [MEDIUM] — quality_service.py uses review_notes (attribute doesn't exist)

**File:** `app/services/quality_service.py`
**Lines:** 172, 212
**Type:** Missing attribute

```python
# quality_service.py line 172:
    score.review_notes = notes

# quality_score.py (ORM model):
    # ← NO review_notes column defined
```

**Impact:** Approving or rejecting quality scores will fail with
`AttributeError: type object 'AssetQualityScore' has no attribute 'review_notes'`.

**Fix decision needed from operator:**
- **Option A:** Add `review_notes` column to AssetQualityScore model + migration
- **Option B:** Remove `review_notes` assignment from service

**Recommendation:** Option A — review notes are useful for audit trail.

**Migration:** Yes (if Option A).

---

### BUG-008 [HIGH] — 5 migration gaps (detailed in Section 2)

5 model columns have no Alembic migration. See Section 2 for full details.

**Migration:** Yes — 5 new migration files needed.

---

### BUG-009 [HIGH] — quotas.py uses quota_bytes (NEW — not in v2 plan)

**File:** `app/api/v1/quotas.py`
**Lines:** 20, 29, 61, 69, 91, 94, 99
**Type:** Column name mismatch

| API Uses | ORM Model Has |
|---|---|
| `quota_bytes` | `max_bytes` |

**Evidence:**

```python
# quotas.py line 91 (raw SQL INSERT):
"INSERT INTO storage_quotas (entity_type, entity_id, quota_bytes, alert_threshold_pct) "

# storage_quota.py line 34 (ORM model):
max_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

**Impact:** Setting quotas via API will fail with
`UndefinedColumn: column "quota_bytes" does not exist`.

**Fix (per Q1):** Rename `quota_bytes` → `max_bytes` (7 occurrences).
**Migration:** No.

---

### BUG-010 [HIGH] — quotas.py uses used_bytes (NEW — not in v2 plan)

**File:** `app/api/v1/quotas.py`
**Lines:** 21, 60, 70
**Type:** Column name mismatch

| API Uses | ORM Model Has |
|---|---|
| `used_bytes` | `current_bytes` |

**Evidence:**

```python
# quotas.py line 60 (row attribute access):
    used = row.used_bytes or 0

# storage_quota.py line 35 (ORM model):
    current_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
```

**Impact:** Reading quota information will fail with
`AttributeError: 'Row' object has no attribute 'used_bytes'`.

**Fix (per Q1):** Rename `used_bytes` → `current_bytes` (3 occurrences).
**Migration:** No.

---

## 4. Summary by Affected File

| File | Bugs | Severity | Tests Blocked? |
|---|---|---|---|
| `app/api/v1/manifests.py` | BUG-002, BUG-003, BUG-004 | HIGH | Yes — all manifest tests |
| `app/api/v1/backup.py` | BUG-001, BUG-005, BUG-006 | HIGH | Yes — all backup tests |
| `app/api/v1/quotas.py` | BUG-009, BUG-010 | HIGH | Yes — all quota tests |
| `app/services/quality_service.py` | BUG-007 | MEDIUM | Partially — approve/reject tests |
| `migrations/` | BUG-008 | HIGH | No — tests use create_all |

### Files That CANNOT Function in Production

1. **`manifests.py`** — References 3 columns that don't exist (`timeline_json`, `scene_count`, `created_at`) and 1 wrong name (`sha256_hash` → `content_hash`)
2. **`backup.py`** — References 2 wrong column names (`storage_path` → `backup_path`, `error_message` → doesn't exist) + has NameError in error handler
3. **`quotas.py`** — References 2 wrong column names (`quota_bytes` → `max_bytes`, `used_bytes` → `current_bytes`)

---

## 5. Affected Endpoints (Cannot Work in Production)

| Endpoint | File | Bugs | Status |
|---|---|---|---|
| `GET /api/v1/jobs/{id}/manifest` | manifests.py | BUG-002, BUG-003 | ❌ Broken |
| `POST /api/v1/jobs/{id}/manifest` | manifests.py | BUG-003, BUG-004 | ❌ Broken |
| `POST /api/v1/jobs/{id}/manifest/lock` | manifests.py | BUG-003 | ❌ Broken |
| `POST /api/v1/jobs/{id}/manifest/validate` | manifests.py | BUG-004 | ❌ Broken |
| `GET /api/v1/backup/records` | backup.py | BUG-005, BUG-006 | ❌ Broken |
| `POST /api/v1/backup/create` | backup.py | BUG-001, BUG-005, BUG-006 | ❌ Broken |
| `POST /api/v1/backup/{id}/verify` | backup.py | BUG-001, BUG-005 | ❌ Broken |
| `GET /api/v1/quotas/{type}/{id}` | quotas.py | BUG-009, BUG-010 | ❌ Broken |
| `PUT /api/v1/quotas/{type}/{id}` | quotas.py | BUG-009 | ❌ Broken |
| `POST /api/v1/quality/scores/{id}/approve` | quality_service.py | BUG-007 | ❌ Broken |
| `POST /api/v1/quality/scores/{id}/reject` | quality_service.py | BUG-007 | ❌ Broken |

**11 endpoints are non-functional** due to these 10 bugs.

---

## 6. Tables in Migrations Without ORM Classes

| Table | Migration | Purpose | Action |
|---|---|---|---|
| `prompt_tag_associations` | 0001_initial_core.py | M2M via `Table()` in `prompt_tag.py` | None — expected |
| `rollback_points` | 0001_initial_core.py | Used via raw SQL in `rollback_service.py` | None — expected |

---

## 7. Required Actions for Phase 0b/0c

### Phase 0b: Migration Fixes (BUG-008)

| Migration File | Action | Estimated Time |
|---|---|---|
| `0015_add_users_is_active.py` | `add_column('users', 'is_active', Boolean, default=True)` | 15 min |
| `0016_add_projects_created_by.py` | `add_column('projects', 'created_by', UUID, FK→users.id)` | 15 min |
| `0017_add_quality_scores_job_id.py` | `add_column('asset_quality_scores', 'job_id', UUID, FK→render_jobs.id)` | 15 min |
| `0018_add_retention_description.py` | `add_column('retention_policies', 'description', Text)` | 10 min |
| `0019_add_prompt_tags_description.py` | `add_column('prompt_tags', 'description', Text)` | 10 min |

### Phase 0c: Bug Fixes (Operator Approval Required)

| Bug | Fix | Decision Needed? | Estimated Time |
|---|---|---|---|
| BUG-001 | Rename `_exc` → `exc` in backup.py:292 | Straightforward | 5 min |
| BUG-002 | Delete manifests.py lines 85-92 | Approved by operator | 5 min |
| BUG-003 | Rename `timeline_json`→`timeline`, remove `scene_count`/`created_at` | Per Q1: align to model | 30 min |
| BUG-004 | Rename `sha256_hash`→`content_hash` in manifests.py | Per Q1: align to model | 15 min |
| BUG-005 | Rename `storage_path`→`backup_path` in backup.py | Per Q1: align to model | 15 min |
| BUG-006 | Add `error_message` to model + migration, OR remove from API | **Decision needed** | 20 min |
| BUG-007 | Add `review_notes` to model + migration, OR remove from service | **Decision needed** | 15 min |
| BUG-009 | Rename `quota_bytes`→`max_bytes` in quotas.py | Per Q1: align to model | 15 min |
| BUG-010 | Rename `used_bytes`→`current_bytes` in quotas.py | Per Q1: align to model | 10 min |

### Operator Decisions Required Before Phase 0c

1. **BUG-006:** Add `error_message` column to BackupRecord model + migration?
   Or remove from API?
   *Recommendation:* Add column — error context is operationally important.

2. **BUG-007:** Add `review_notes` column to AssetQualityScore model + migration?
   Or remove from service?
   *Recommendation:* Add column — review audit trail is valuable.

---

## 8. Verification Plan (Phase 0d)

After all Phase 0b/0c fixes:

```bash
# 1. Verify migrations apply cleanly
alembic downgrade base
alembic upgrade head

# 2. Verify schema matches models
python3 -c "
from sqlalchemy import inspect
from shared.database import engine
import asyncio
async def check():
    async with engine.connect() as conn:
        inspector = await conn.run_sync(lambda c: inspect(c))
        # Compare column names for each table
asyncio.run(check())
"

# 3. All 153 existing tests still pass
pytest tests/ -q --tb=short

# 4. Coverage baseline saved
pytest tests/ --cov=app --cov-branch --cov-report=json
cp coverage.json coverage_baseline.json
```

---

## 9. Phase 0a Exit Criteria

- [x] All 24 model files scanned (23 files, 24 tables)
- [x] All 14 migration files scanned (26 tables including association + legacy)
- [x] 24/24 tables matched between models and migrations
- [x] 5 missing columns identified with line-level evidence
- [x] 10 bugs documented with file, line, evidence, severity, and fix direction
- [x] 2 NEW bugs discovered beyond v2 plan (BUG-009, BUG-010 in quotas.py)
- [x] 11 broken endpoints catalogued
- [x] Required migrations listed for Phase 0b
- [x] Operator decisions identified for Phase 0c
- [x] Report produced — this document

**Status:** ✅ **Phase 0a COMPLETE**

**Next:** Halt-and-report to operator. Await decisions on BUG-006 and
BUG-007 before proceeding to Phase 0b.

---

## Appendix A: Complete Model Column Inventory

```
asset_quality_scores (quality_score.py :: AssetQualityScore)
  id, asset_id, job_id*, quality_score, safety_score, scoring_details,
  decision, reviewed_by, reviewed_at, created_at
  * = missing from migration

assets (asset.py :: Asset)
  id, project_id, scene_id, asset_type, seaweedfs_fid, seaweedfs_path,
  mime_type, file_size_bytes, duration_seconds, language_code,
  generation_prompt_id, storage_tier, tier_transition_at, preserve_flag,
  last_accessed_at, content_hash, reference_count, generation_params_hash,
  created_at

audit_log (audit_log.py :: AuditLog)
  id, user_id, action_type, resource_type, resource_id, before_payload,
  after_payload, client_ip, timestamp

backup_records (backup_record.py :: BackupRecord)
  id, backup_type, scope, status, backup_path, size_bytes, started_at,
  completed_at, verified_at, verification_checksum, retention_days

composition_manifests (composition_manifest.py :: CompositionManifest)
  id, job_id, manifest_version, total_duration_ms, resolution_width,
  resolution_height, framerate, audio_sample_rate, timeline, status,
  locked_at, rendered_at, checksum

dead_letter_messages (dead_letter_queue.py :: DeadLetterMessage)
  id, original_queue, task_name, task_args, task_kwargs, exception_type,
  exception_message, traceback, failure_category, retry_count_exhausted,
  created_at, reviewed_at, reviewed_by, resolution

fallback_policies (fallback_policy.py :: FallbackPolicy)
  id, scene_type, level_1_strategy, level_2_strategy, level_3_strategy,
  level_4_strategy, created_at, updated_at

gpu_metrics_history (gpu_metrics_history.py :: GpuMetricsHistory)
  id, gpu_node_id, gpu_util_pct, mem_util_pct, temperature_c, power_draw_w,
  active_job_count, queue_depth, recorded_at

gpu_nodes (gpu_node.py :: GpuNode)
  id, node_hostname, gpu_index, gpu_model, total_vram_mb,
  compute_capability, status, registered_at, last_heartbeat_at

gpu_reservations (gpu_node.py :: GpuReservation)
  id, gpu_node_id, job_id, reserved_vram_mb, model_name, status,
  reserved_at, expires_at

language_variants (language_variant.py :: LanguageVariant)
  id, project_id, language_code, state, created_at,
  final_render_1080p_id, final_render_4k_id

pipeline_checkpoints (checkpoint.py :: PipelineCheckpoint)
  id, job_id, stage_name, stage_index, status, checkpoint_data,
  output_refs, version_fingerprint, created_at, started_at, completed_at

projects (project.py :: Project)
  id, name, description, max_runtime_seconds, state, hero_image_asset_id,
  talking_head_asset_id, created_by*, target_audience, created_at, updated_at
  * = missing from migration

prompt_tags (prompt_tag.py :: PromptTag)
  id, name, description*, created_at
  * = missing from migration

prompts (prompt.py :: Prompt)
  id, prompt_type, prompt_text, version, is_active, is_library_template,
  project_id, scene_id, created_by, created_at, change_note

render_jobs (render_job.py :: RenderJob)
  id, project_id, job_type, status, node_id, celery_task_id, retry_count,
  max_retries, error_message, failure_category, created_at, started_at,
  completed_at

render_segments (render_segment.py :: RenderSegment)
  id, job_id, segment_index, start_ms, end_ms, status, output_path,
  output_checksum, attempts, created_at

retention_policies (retention_policy.py :: RetentionPolicy)
  id, name, description*, hot_days, warm_days, cold_days, archive_days,
  delete_after_days, applies_to, is_default, created_at, updated_at
  * = missing from migration

storage_quotas (storage_quota.py :: StorageQuota)
  id, entity_type, entity_id, max_bytes, current_bytes, tier,
  alert_threshold_pct, created_at, updated_at

storyboard_scenes (storyboard_scene.py :: StoryboardScene)
  id, project_id, scene_index, visual_description, narration_text,
  media_type, duration_seconds, created_at, updated_at

task_retries (task_retry.py :: TaskRetry)
  id, job_id, stage_name, attempt_number, failure_type, error_message,
  error_traceback, retry_after_seconds, created_at

transcripts (transcript.py :: Transcript)
  id, project_id, original_asset_id, refined_text, sequence_order,
  language_code, created_at, updated_at

users (user.py :: User)
  id, username, password_hash, role, created_at, is_active*, last_login_at
  * = missing from migration

worker_heartbeats (worker_heartbeat.py :: WorkerHeartbeat)
  id, worker_id, node_hostname, gpu_index, current_job_id, current_stage,
  status, heartbeat_data, last_heartbeat_at
```

---

## Appendix B: Migration Inventory

| File | Revision | Tables Created |
|---|---|---|
| `0001_initial_core.py` | 0001 | users, projects, transcripts, storyboard_scenes, assets, prompts, prompt_tags, prompt_tag_associations, render_jobs, language_variants, audit_log, rollback_points |
| `0002_pipeline_checkpoints.py` | 0002 | pipeline_checkpoints |
| `0003_gpu_registry.py` | 0003 | gpu_nodes, gpu_reservations |
| `0004_retry_tracking.py` | 0004 | task_retries |
| `0005_worker_heartbeats.py` | 0005 | worker_heartbeats |
| `0006_dead_letter_queue.py` | 0006 | dead_letter_messages |
| `0007_composition_manifests.py` | 0007 | composition_manifests |
| `0008_quality_scores.py` | 0008 | asset_quality_scores |
| `0009_render_segments.py` | 0009 | render_segments |
| `0010_gpu_metrics.py` | 0010 | gpu_metrics_history |
| `0011_retention_policies.py` | 0011 | retention_policies |
| `0012_storage_quotas.py` | 0012 | storage_quotas |
| `0013_backup_records.py` | 0013 | backup_records |
| `0014_fallback_policies.py` | 0014 | fallback_policies |

---

*End of Schema Migration Gap Report.*
*Generated by Phase 0a Schema Audit — investigation only, no code changes made.*
