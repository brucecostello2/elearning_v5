"""
0015_add_user_is_active — Add is_active column to users table

Adds the soft-disable flag referenced by app.core.auth and
app.services.auth_service. Backfills existing rows to TRUE via
server_default so no row-level UPDATE is required.

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
    op.drop_column("users", "is_active")
