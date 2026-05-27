# Phase 0c — Steps 4-6 Summary

## Overview

Steps 4-6 of the Test Implementation Plan v3 completed all bug investigations,
applied all 10 approved fixes, removed xfail markers, and achieved a fully
passing test suite (160 tests, 0 failures, 0 xfails).

---

## Step 4: Investigations

### BUG-003 — `scene_count` references
- **File:** `BUG_003_INVESTIGATION.md`
- **Finding:** `scene_count` only exists in `manifests.py` raw SQL and `ManifestResponse` Pydantic model. The `composition_manifests` table has no `scene_count` column.
- **Resolution:** Compute `scene_count` from `len(timeline.get("scenes", []))` at response time.

### BUG-007 — `review_notes` usage
- **File:** `BUG_007_INVESTIGATION.md`
- **Finding:** `review_notes` is a designed feature with full request→service→response flow. Only the DB column was missing from `asset_quality_scores`.
- **Resolution:** Add the column via migration 0021 (Option A — add column to align model to code).

---

## Step 5: Bug Fixes Applied

| Bug | Commit | Summary |
|-----|--------|---------|
| BUG-001 | `f8df1ba` | `str(exc)` → `str(_exc)` in backup error handler |
| BUG-002 | `0d0de80` | Deleted dead code block + unused `select` import in manifests GET |
| BUG-003 | `743d6f1` | `timeline_json` → `timeline` in SQL; `scene_count` computed from JSON; `created_at` removed from INSERT; ORDER BY changed to `locked_at DESC NULLS LAST` |
| BUG-004 | `743d6f1` | `sha256_hash` → `content_hash` in all manifest SQL queries |
| BUG-005 | `db4e3c8` | `storage_path` → `backup_path` everywhere in backup.py (Pydantic, SQL, variables) |
| BUG-006 | `b33e1c5` | Added `error_message` Text column to `backup_records` + migration 0020 |
| BUG-007 | `cf0ae31` | Added `review_notes` Text column to `asset_quality_scores` + migration 0021 |
| BUG-008 | — | Pre-existing fix (verified no action needed) |
| BUG-009 | `8663c1b` | `row.used_bytes` → `row.current_bytes`, `row.quota_bytes` → `row.max_bytes` in quota SQL |
| BUG-010 | `8663c1b` | SQL INSERT `quota_bytes` → `max_bytes` in quota PUT endpoint |

### Migrations Added
- `migrations/versions/0020_add_backup_records_error_message.py` — `error_message` Text column
- `migrations/versions/0021_add_quality_scores_review_notes.py` — `review_notes` Text column

### Model Changes
- `app/models/backup_record.py` — added `error_message = Column(Text, nullable=True)`
- `app/models/quality_score.py` — added `review_notes = Column(Text, nullable=True)`

---

## Step 6: Test Suite Verification

### xfail Markers Removed
All `@pytest.mark.xfail` decorators removed from:
- `tests/test_bug_001_backup_error_handler.py`
- `tests/test_bug_003_manifest_field_names.py`
- `tests/test_bug_004_manifest_asset_checksum.py`
- `tests/test_bug_005_backup_field_names.py`
- `tests/test_bug_009_quota_field_names.py`

### Test Results
```
160 passed, 0 failed, 0 xfailed in 61.54s
```

Breakdown:
- 153 original tests — all passing
- 7 bug-exposing tests (across 5 files) — all now passing after fixes

### Test Commits
- `2428791` — Remove xfail markers and update bug test assertions

---

## Decision Log

| Question | Decision | Applied |
|----------|----------|---------|
| Q1: Fix API or update models? | Fix API to align to models | All SQL fixes |
| Q5: Dead code in BUG-002? | Delete approved | `0d0de80` |

---

## Notes

1. **BUG-003 + BUG-004** committed together (both affect `manifests.py`, interrelated).
2. **BUG-009 + BUG-010** committed together (both affect `quotas.py`, interrelated).
3. **Pydantic field names preserved** for API contract stability:
   - `QuotaResponse` uses `quota_bytes`/`used_bytes` (API names) while SQL uses `max_bytes`/`current_bytes`
   - `ManifestResponse` uses `timeline_json` (API name) while SQL column is `timeline`
4. **Unique index** `uq_storage_quotas_entity` on `(entity_type, entity_id)` required for `ON CONFLICT` in quota PUT — added manually; should be formalized in a future migration.
