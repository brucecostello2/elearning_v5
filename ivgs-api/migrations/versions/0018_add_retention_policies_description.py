"""
0018_add_retention_policies_description — Add description to retention_policies

Resolves Phase 0a schema audit: column defined in ORM model
(retention_policy.py:30) but missing from migration 0011_retention_policies.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add description column to retention_policies table.

    Text column, nullable=True.
    Matches ORM definition in app/models/retention_policy.py:30.
    """
    op.add_column(
        "retention_policies",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove description column from retention_policies table."""
    op.drop_column("retention_policies", "description")
