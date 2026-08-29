"""0049 — widen storyboard_design_briefs.contract_version

WP-IVGS-12, and it is my own off-by-one, found by the first acceptance run.

⛔ WHAT HAPPENED. 0048 declared `contract_version VARCHAR(16)`. The value the
worker sends is `design-contract-1` — **seventeen characters**. Every
design-brief ingest therefore failed with

    asyncpg.exceptions.StringDataRightTruncationError:
    value too long for type character varying(16)

and the endpoint returned HTTP 500. Measured on project e32ba6f5, 2026-08-29:
the contract WAS emitted (4,335 completion tokens, 13 scenes, schema-conformant)
and the brief could not be stored.

⛳ TWO THINGS WORKED EXACTLY AS DESIGNED WHILE IT FAILED, AND BOTH ARE WORTH
RECORDING RATHER THAN QUIETLY ENJOYING.

  * The capture RAISED instead of swallowing. `design_core.capture._post` refuses
    to reproduce `_save_storyboard_scenes`'s swallow (recovery-plan RC-E), so the
    worker logged `design_contract_capture_failed` with the HTTP status and the
    body. The defect was one grep away rather than invisible.
  * The stage still completed. The observer is non-fatal by construction, so
    thirteen scenes landed and the run reached the gate. A capture problem
    degraded the review; it did not cost a render.

WIDENED TO 64 RATHER THAN TO 17. Sixteen was an arbitrary guess and the next
label will be longer than this one too. A version string is a label, not a key,
and there is no cost to giving it room.

Revision ID: 0049
Revises: 0048
"""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "storyboard_design_briefs",
        "contract_version",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Narrowing back to 16 would truncate every row this package writes, so the
    downgrade DELETES the values it cannot represent rather than letting
    PostgreSQL refuse the ALTER with a message about one row. Loud, and stated.

    A brief with no `contract_version` still renders: the gate reads the
    outcomes, the arc and the evidence map, none of which live in this column.
    """
    op.execute(
        "UPDATE storyboard_design_briefs SET contract_version = NULL "
        "WHERE length(contract_version) > 16"
    )
    op.alter_column(
        "storyboard_design_briefs",
        "contract_version",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
