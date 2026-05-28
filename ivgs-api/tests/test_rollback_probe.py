"""
Phase 0.5: Rollback Probe Test

Verifies that db_session actually rolls back between tests.
If these fail, test isolation is broken — stop and fix db_session.

Test order matters:
1. test_rollback_probe_insert: inserts a canary row, verifies it exists
2. test_rollback_probe_verify: checks the canary was rolled back (count = 0)
"""
import pytest
from sqlalchemy import text


async def test_rollback_probe_insert(db_session):
    """Insert a canary row. The NEXT test checks it was rolled back."""
    await db_session.execute(
        text(
            "INSERT INTO users (id, username, password_hash, role) "
            "VALUES (uuid_generate_v4(), 'rollback_canary', 'fakehash', 'viewer')"
        )
    )
    await db_session.flush()
    result = await db_session.execute(
        text("SELECT count(*) FROM users WHERE username = 'rollback_canary'")
    )
    count = result.scalar()
    assert count == 1, f"Canary insert failed: got {count}"


async def test_rollback_probe_verify(db_session):
    """Verify the canary row from the previous test was rolled back."""
    result = await db_session.execute(
        text("SELECT count(*) FROM users WHERE username = 'rollback_canary'")
    )
    count = result.scalar()
    assert count == 0, (
        f"ROLLBACK BROKEN: found {count} canary rows from previous test. "
        f"db_session is not isolating tests. Fix the savepoint pattern."
    )
