"""
0017_add_projects_created_by — Add created_by column to projects table

Resolves Phase 0a schema audit: column defined in ORM model (project.py:48)
but missing from migration 0001_initial_core.

Note: ORM defines nullable=False with FK to users.id (ondelete=CASCADE).
Migration uses nullable=True to accommodate existing rows without a value.
A follow-up data migration can backfill and tighten the constraint.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add created_by column to projects table.

    UUID column with FK to users.id.
    Nullable=True for safe migration of existing rows.
    Matches ORM definition in app/models/project.py:48.
    """
    op.add_column(
        "projects",
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_created_by_users",
        "projects",
        "users",
        ["created_by"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove created_by column and FK from projects table."""
    op.drop_constraint(
        "fk_projects_created_by_users", "projects", type_="foreignkey"
    )
    op.drop_column("projects", "created_by")
