"""0043  drop the models.dynamically_loadable server default

WP-IVGS-08 Task 4(b).

THE DEFAULT WAS AN UNCONDITIONAL TRUE, and the column is NOT NULL. So every
row written without an explicit value claimed the engine could hot-swap it --
including vLLM, which AD-01 S211 states cannot: "vLLM serves a fixed model per
process and cannot hot-swap arbitrary large models at request time". The
planner reads this flag to decide what it may select, so a wrong TRUE lets it
choose a model the node is not serving.

Dropping the default makes an unset value an ERROR at insert time rather than
a silent, confident, wrong TRUE. `ad01_ingest.is_dynamically_loadable()` now
supplies it explicitly on every path.

The column stays NOT NULL: nullable would trade a wrong answer for an unknown
one, and every caller can answer.

Revision ID: 0043
Revises: 0042
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE models ALTER COLUMN dynamically_loadable DROP DEFAULT")


def downgrade() -> None:
    # Restores the defect deliberately: this is what the column had before.
    op.execute("ALTER TABLE models ALTER COLUMN dynamically_loadable SET DEFAULT true")
