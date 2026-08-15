# WP-11-TEST-UNIFICATION — One pytest invocation for all three suites

| | |
|---|---|
| **Ledger** | P2.26 + P2.27 |
| **Tier** | A · **Track P** (worktree-safe) |
| **Report** | `reports/WP-11-TEST-UNIFICATION-report_<YYYY-MM-DD>.md` |

## Objective

Three test trees — `tests/` (9), `ivgs-workers/tests/` (16), `ivgs-scheduler/tests/`
(4) — cannot run as one: a `conftest.py` collision blocks a unified `testpaths`, and
`tests/` collection fails on SQLite because `shared/database.py:31` passes
`pool_size`/`max_overflow`/`pool_timeout` unconditionally (SQLite/NullPool →
TypeError at `create_engine`).

## Tasks

1. Make the engine factory dialect-aware (pool kwargs only where the dialect
   supports them).
2. Resolve the collection collision via `importmode=importlib`; wire a unified
   `pytest` entry (root `pytest.ini`/`pyproject` section).
3. Wire testcontainers + Alembic where suites need a real Postgres, per the ledger
   note — propose rather than build if it turns out to be a session on its own;
   the unification itself is the deliverable.

## Scope

**In:** test configuration, `conftest.py` files, `shared/database.py:31` factory.
**Out:** fixing individual failing tests beyond collection (list failures; fixing
them is separate work); any production code beyond the factory.

## Exit gate

A single `pytest` invocation collects all three suites. All previously-passing tests
still pass; anything newly-failing is enumerated with cause. The factory change is
covered by a test (SQLite engine builds clean; Postgres kwargs preserved).
