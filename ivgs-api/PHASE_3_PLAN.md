# Phase 3: API Endpoint Tests

**Status:** In Progress  
**Started:** 2026-05-27

## Scope

Comprehensive API endpoint testing focused on gaps in existing coverage.
Existing tests (203 passing) already cover most CRUD operations. Phase 3 adds:

1. **Jobs API** — list, detail, cancel (no existing test file)
2. **Language Variants API** — create, list, retry (no existing test file)
3. **Nodes API** — list, detail (stub endpoints, no test file)
4. **Backup API** — trigger, verify, list (only bug-specific tests exist)
5. **Cross-cutting pagination** — boundary cases for all paginated endpoints
6. **RBAC enforcement** — systematic verification of admin-only endpoints
7. **404/validation edge cases** — UUID format, nonexistent resources

## Estimated Tests: 80-120 new tests
## Expected Bugs: 3-8 based on patterns from Phase 0-2

## Test Organization
- `tests/test_api_jobs.py` — Job list, detail, cancel, filters
- `tests/test_api_languages.py` — Language variant CRUD
- `tests/test_api_nodes.py` — Node stub endpoints
- `tests/test_api_backup.py` — Backup trigger, verify, list
- `tests/test_api_pagination.py` — Pagination edge cases across endpoints
- `tests/test_api_rbac.py` — Admin-only endpoint RBAC checks

## Exit Criteria
- [ ] 80+ new tests passing or xfail
- [ ] All gaps covered
- [ ] Bugs documented in BUGS_FOUND.md
- [ ] Summary report created
