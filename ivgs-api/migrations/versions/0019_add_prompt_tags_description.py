"""
0019_add_prompt_tags_description — Add description to prompt_tags

Resolves Phase 0a schema audit: column defined in ORM model
(prompt_tag.py:62) but missing from migration 0007_composition_manifests.

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add description column to prompt_tags table.

    String(256) column, nullable=True.
    Matches ORM definition in app/models/prompt_tag.py:62.
    """
    op.add_column(
        "prompt_tags",
        sa.Column("description", sa.String(256), nullable=True),
    )


def downgrade() -> None:
    """Remove description column from prompt_tags table."""
    op.drop_column("prompt_tags", "description")
