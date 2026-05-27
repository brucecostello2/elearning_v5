# Phase 0c Summary: Bug Documentation & Exposing Tests (Steps 1–3)

**Date:** 2026-05-27  
**Phase:** 0c — Bug Documentation & Fixes (Steps 1–3 Complete)  
**Status:** 🛑 HALT — Awaiting Operator Approval for Fixes

---

## What Was Done

### Step 1: Created BUGS_FOUND.md

Comprehensive documentation of all 10 bugs discovered in Phase 0a, including:
- Exact file locations and line numbers
- Code evidence (before/after)
- Impact analysis with affected endpoints
- Proposed fixes aligned to operator decision Q1 (fix API to match model)

### Step 2: Wrote Exposing Tests

| Bug | Test File | Tests | xfail? | Verified? |
|-----|-----------|-------|--------|-----------|
| BUG-001 | `test_bug_001_backup_error_handler.py` | 1 | ✅ | ✅ |
| BUG-002 | *(no test — dead code deletion)* | — | — | — |
| BUG-003 | `test_bug_003_manifest_field_names.py` | 2 | ✅ | ✅ |
| BUG-004 | `test_bug_004_manifest_asset_checksum.py` | 1 | ✅ | ✅ |
| BUG-005 | `test_bug_005_backup_field_names.py` | 1 | ✅ | ✅ |
| BUG-009/010 | `test_bug_009_quota_field_names.py` | 2 | ✅ | ✅ |

**Total:** 7 xfail tests across 5 test files

### Step 3: Committed All Artifacts

7 git commits (1 for docs + 5 for test files + 1 for this summary).

### Test Suite Status

```
153 passed, 7 xfailed in 58.06s
```

Zero regressions. All original tests pass. All new tests correctly xfail.

---

## Git Commits Created

```
e229e1c test: Add xfail tests exposing BUG-009/010 (wrong quota column names)
f55baf3 test: Add xfail test exposing BUG-005 (storage_path → backup_path)
170e60e test: Add xfail test exposing BUG-004 (sha256_hash → content_hash)
0c3f8b7 test: Add xfail tests exposing BUG-003 (wrong manifest column names)
e770c4a test: Add xfail test exposing BUG-001 (NameError in backup error handler)
134060d docs: Add comprehensive bug inventory (BUGS_FOUND.md)
```

---

## Proposed Fixes Ready for Operator Approval

### Fix 1: BUG-001 — NameError in backup error handler

**File:** `app/api/v1/backup.py`, line 299  
**Change:** `str(exc)` → `str(_exc)`

### Fix 2: BUG-002 — Dead code in manifests

**File:** `app/api/v1/manifests.py`, lines 85–92  
**Change:** Delete the unused `_result = await db.execute(...)` block  
**Status:** Pre-approved by operator (Q5 decision)

### Fix 3: BUG-003 — Wrong column names in manifests

**File:** `app/api/v1/manifests.py`  
**Changes:**
- `timeline_json` → `timeline` (in SELECT, INSERT, and Python)
- Remove `scene_count` from SQL (not a real column — compute from timeline)
- Remove `created_at` from INSERT (not in composition_manifests table)

### Fix 4: BUG-004 — sha256_hash → content_hash

**File:** `app/api/v1/manifests.py`, lines 176, 201, 345, 354, 359  
**Change:** `sha256_hash` → `content_hash` in SQL and attribute access

### Fix 5: BUG-005 — storage_path → backup_path

**File:** `app/api/v1/backup.py`  
**Change:** `storage_path` → `backup_path` in SQL, Pydantic schema, and Python

### Fix 6: BUG-009 — quota_bytes → max_bytes

**File:** `app/api/v1/quotas.py`  
**Change:** `quota_bytes` → `max_bytes` in SQL and attribute access

### Fix 7: BUG-010 — used_bytes → current_bytes

**File:** `app/api/v1/quotas.py`  
**Change:** `used_bytes` → `current_bytes` in attribute access

---

## Operator Decisions Still Needed

### BUG-006: error_message column in backup_records

The code references `error_message` in multiple UPDATE statements, but this column does not exist in the model or DB.

**Option A (recommended):** Add `error_message` to BackupRecord model + create migration 0020  
**Option B:** Remove all `error_message` references from backup.py

### BUG-007: review_notes attribute in quality service

Quality service code references `review_notes` which doesn't exist in AssetQualityScore model.

**Option A (recommended):** Add `review_notes` to AssetQualityScore model + create migration 0021  
**Option B:** Remove `review_notes` references from quality service

---

## Phase 0c Exit Criteria (Steps 1–3)

- [x] BUGS_FOUND.md created and committed
- [x] All testable bugs have xfail tests written
- [x] All tests marked `@pytest.mark.xfail(strict=True)`
- [x] All test files committed separately
- [x] BUG-002 documented (no test — dead code)
- [x] Full test suite verified: 153 passed, 7 xfailed
- [x] Summary document created

**Status:** ✅ Steps 1–3 COMPLETE

---

**Next:** Operator approves proposed fixes → Phase 0c Steps 4–6 (apply fixes, remove xfail, verify)
