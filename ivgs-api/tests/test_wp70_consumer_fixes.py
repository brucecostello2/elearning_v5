"""
WP-70 — CONSUMER FIXES 1: the API side of the nine WP-69 §2 defects.

Each test was written before its fix and fails on the pre-fix tree (the
report records the failing run). Frontend-side checks live in
ivgs-frontend/src/lib/__tests__/wp70-consumer-fixes.test.mjs.
"""
import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── S11: DLQMessageResponse must carry the timestamp the table renders ────

@pytest.mark.asyncio
class TestS11DLQEnteredAt:
    async def test_every_listed_message_carries_entered_dlq_at(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """The DLQ table's "Entered DLQ" column reads `entered_dlq_at`.
        The row has a timestamp (`created_at`); the response must expose it
        under the name the consumer reads, equal to the row's own value."""
        r = await client.get("/api/v1/dlq/messages", headers=_auth(operator_token))
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) >= len(dlq_messages)
        for row in rows:
            assert "entered_dlq_at" in row, f"missing on {sorted(row)}"
            assert row["entered_dlq_at"] == row["created_at"]
