"""
0015_add_users_is_active — Add is_active column to users table

Resolves Phase 0a schema audit: column defined in ORM model (user.py:42)
but missing from migration 0001_initial_core.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_active column to users table.

    Boolean column with server_default=true, nullable=False.
    Matches ORM definition in app/models/user.py:42.
    """
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    """Remove is_active column from users table."""
    op.drop_column("users", "is_active")
