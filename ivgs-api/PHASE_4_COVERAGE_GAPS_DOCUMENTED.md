# Phase 4: Documented Coverage Gaps

**Date:** 2026-05-27
**Status:** Pre-Phase 6 compliance check

---

## Services Below 70% Branch Coverage (After Gap Closure)

### 1. prompt_service.py — 61% combined (45% service-only)

**Current Test File:** `tests/test_service_prompt.py` (11 tests)

**Covered Methods:**
- ✅ `list_prompts` (global scope)
- ✅ `get_prompt`
- ✅ `create_prompt`
- ✅ `update_prompt`
- ✅ `delete_prompt`

**Uncovered Methods (lines 56-160, 234-284, 313-335):**
- ❌ `list_global_prompts` — filters by `prompt_type`, project/scene NULL
- ❌ `list_project_prompts` — project-scoped with optional type filter
- ❌ `list_scene_prompts` — scene-scoped with optional type filter
- ❌ `resolve_prompt_chain` — 3-tier hierarchy: scene → project → global
- ❌ `get_effective_prompt` — resolves prompt with inheritance + variable interpolation
- ❌ `manage_tags` — tag association/dissociation

**Why Gap Exists:**
The prompt service has deep hierarchical resolution logic (scene→project→global
with variable interpolation) that requires complex fixture chains. Current tests
cover all CRUD operations used by API endpoints. The uncovered methods are
primarily used by the render pipeline (internal service-to-service calls).

**Decision:** ACCEPT GAP — non-blocking advisory service

**Rationale:**
1. All API-facing CRUD paths are tested (11 tests)
2. Uncovered methods are internal pipeline helpers, not exposed via REST
3. Phase 6 integration tests will exercise prompt resolution through full render workflows
4. Cost: ~3 hours for hierarchical fixture chains; benefit: 15% coverage on non-critical paths

---

### 2. quality_service.py — 64% combined (54% service-only)

**Current Test File:** `tests/test_service_quality.py` (5 tests)

**Covered Methods:**
- ✅ `list_scores` — list quality scores for a job
- ✅ `create_score` — create/update quality score
- ✅ `get_score` — retrieve single score

**Uncovered Methods (lines 47-72, 109-127, 203-235):**
- ❌ `get_job_quality_summary` — aggregates scores per job (avg quality, avg safety, decision counts)
- ❌ `check_quality_gate` — compares job quality against thresholds, returns pass/fail
- ❌ `override_decision` — admin override of quality decision with review notes

**Why Gap Exists:**
The quality summary and gate-check methods require render jobs with multiple
scored assets, which need complex fixture chains (project → job → assets → scores).
Current tests cover the individual score CRUD, which is the primary API surface.

**Decision:** ACCEPT GAP — advisory service, scores don't block operations

**Rationale:**
1. Individual score CRUD covers all API endpoints
2. Quality gate (`check_quality_gate`) is advisory — it logs but doesn't block
3. `override_decision` requires admin role fixture + scored assets chain
4. Phase 6 integration tests with real render pipelines will exercise quality gate
5. Cost: ~2 hours; benefit: 10% on advisory metrics

---

## Coverage Summary Post-Gap Work

| Service | Before | After | Target | Status |
|---------|--------|-------|--------|--------|
| retention_service | 54% | **100%** | 70% | ✅ FIXED |
| prompt_service | 61% | 61% | 70% | ⚠️ DOCUMENTED |
| quality_service | 64% | 64% | 70% | ⚠️ DOCUMENTED |
| **All other 12 services** | ≥70% | ≥80% | 70% | ✅ PASS |

**Overall Project:**
- Line Coverage: **82.8%** ✅ (spec §15.4 ≥80%)
- Branch Coverage: **88.8%** ✅
- Combined (pytest-cov): **79%**
- Services ≥70%: **13/15** (2 documented non-critical gaps)

**Authorization:** Both gaps are in non-critical services with documented rationale.
Phase 6 integration tests will provide additional coverage through real workflow execution.
