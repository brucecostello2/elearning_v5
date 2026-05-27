# Phase 1: Rate Limiting Tests

**Scope:** Authentication rate limiting with Redis TTL  
**Target:** 15 tests covering rate limit enforcement, lockout behavior, edge cases  
**Status:** Initial test run complete — 14 passed, 1 xfailed (BUG-011)

---

## Test Coverage Areas

### 1. Basic Rate Limiting (5 tests) — `test_rate_limiting_basic.py`

| Test | Status |
|------|--------|
| `test_rate_limit_allows_under_threshold` | ✅ PASSED |
| `test_rate_limit_blocks_at_threshold` | ✅ PASSED |
| `test_rate_limit_response_body` | ✅ PASSED |
| `test_rate_limit_get_requests_exempt` | ✅ PASSED |
| `test_default_bucket_60_per_minute` | ✅ PASSED |

### 2. Login Lockout (5 tests) — `test_rate_limiting_lockout.py`

| Test | Status |
|------|--------|
| `test_lockout_after_10_consecutive_failures` | ✅ PASSED |
| `test_lockout_response_format` | ✅ PASSED |
| `test_lockout_includes_retry_after_header` | ✅ PASSED |
| `test_successful_login_resets_failure_counter` | ✅ PASSED |
| `test_lockout_persists_across_requests` | ✅ PASSED |

### 3. Edge Cases (5 tests) — `test_rate_limiting_edge_cases.py`

| Test | Status |
|------|--------|
| `test_login_and_default_have_separate_counters` | ✅ PASSED |
| `test_different_ips_have_separate_counters` | ✅ PASSED |
| `test_rate_limit_window_does_not_reset_without_ttl` | ✅ PASSED |
| `test_rate_limit_redis_incr_failure` | ❌ XFAIL (BUG-011) |
| `test_lockout_blocks_before_rate_limit_check` | ✅ PASSED |

---

## Bug Discovered

### BUG-011: Rate limiter does not handle Redis failures gracefully

- **Severity:** HIGH
- **Location:** `app/middleware/rate_limit.py:67-147`
- **Issue:** Redis calls not wrapped in try/except; Redis failure crashes all non-GET API requests
- **Proposed Fix:** Fail-open pattern with try/except around Redis calls
- **Status:** xfail test written, awaiting operator approval to fix

---

## Key Findings

1. **Rate limiting works correctly** — 5/min login, 10/min job trigger, 60/min default
2. **Lockout mechanism works** — 10 consecutive failures trigger 15-min lockout
3. **Per-IP isolation works** — X-Forwarded-For header correctly separates rate limit counters
4. **Failure counter reset works** — Successful login clears failure counter via `redis_client.delete()`
5. **GET requests exempt** — Middleware skips all GET and non-`/api/` paths
6. **Mock Redis limitation** — TTL not enforced (expire is no-op); tests document this
7. **BUG-011 found** — Redis failure causes unhandled crash (no try/except in middleware)

### Interaction between Rate Limit and Lockout

Important design observation: The rate limit (5/min) and lockout (10 failures) interact:
- Rate limit blocks at 6th request → only first 5 reach auth handler
- Only 401 responses increment failure counter
- 429 (rate-limited) responses do NOT increment failure counter
- With mock Redis (no TTL), after rate limit window "expires" more failures can accumulate
- In test mock, keys persist forever, so both mechanisms keep working across the full test

---

## Full Test Suite Status

```
174 passed, 1 xfailed in 75.25s
```

- 160 original + Phase 0c tests: all passing
- 15 new Phase 1 rate limiting tests: 14 passed, 1 xfailed

---

## Next Steps

1. **Await operator decision on BUG-011** — fail-open vs 503 response
2. **Apply BUG-011 fix** after approval
3. **Remove xfail marker** from `test_rate_limit_redis_incr_failure`
4. **Proceed to Phase 2** (or additional Phase 1 coverage if requested)
