"""0044 — add `motion_graphics` to the model_engine enum

WP-IVGS-09 Task 1(e), executing ledger RC-I1.

WHY IT WAS MISSING, AND WHY THAT WAS NOT VISIBLE.

WP-68 declared the `motion_graphics` engine in three places that are NOT the
database: the endpoint table (`shared/providers/binding.py:45`), the capability
registry (`shared/providers/client_registry.py:444`, family `maths_motion`) and
the weightless-engine map (`shared/weights/placement.py`). None of those touch
`models.engine`, which is a closed PostgreSQL enum — so the engine existed to
every part of the system EXCEPT the one place a Model Store row has to name it.

Nothing failed, because nothing had tried: WP-68 could not register a row for an
engine with no renderer, so the gap never met an INSERT. It meets one now.

WHAT IT IS, AND WHY IT IS A RUNTIME RATHER THAN A FAMILY.

`motion_graphics` names the RUNTIME `ivgs-motion-renderer` serves, exactly as
`tts` names the runtime that serves both XTTS-v2 and Kokoro (0042). The FAMILY
is `maths_motion`, which is where WP-67's registry puts it. One renderer could
later serve a second family of templates without a second engine value, which is
the property that makes the distinction worth keeping.

⛔ NOTHING IS REMOVED, and `ffmpeg` is NOT reused. They are different things:
`ffmpeg` is a local binary the compositor invokes and has no endpoint at all
(`client_registry.py:414`), while this is an HTTP service with a URL, a health
endpoint and a build ref. Overloading `ffmpeg` would make
`resolve_endpoint("ffmpeg")` — which correctly refuses today, measured in
WP-IVGS-09 Task 0(b) — have to start answering.

Precedent: `e613e84` / migration `0027` (add `ffmpeg`) and `0042` (add MBCP's
four runtimes) — same shape, same reason, same deliberate no-op downgrade.

Revision ID: 0044
Revises: 0043
"""
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction as long as the new value is
    # not used in the same transaction. It is not: the Model Store row that uses
    # it is written afterwards, and by an operator-attended path, not by this
    # migration.
    op.execute("ALTER TYPE model_engine ADD VALUE IF NOT EXISTS 'motion_graphics'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value; downgrade is a deliberate no-op,
    # as in 0027, 0040, 0041 and 0042. Dropping a value would also require
    # proving no row references it, which a downgrade cannot do safely against
    # live data.
    pass
