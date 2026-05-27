"""
0017_add_quality_scores_job_id — Add job_id column to asset_quality_scores

Resolves Phase 0a schema audit: column defined in ORM model
(quality_score.py:32) but missing from migration 0008_quality_scores.

Note: ORM defines nullable=False with FK to render_jobs.id (ondelete=CASCADE).
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
    """Add job_id column to asset_quality_scores table.

    UUID column with FK to render_jobs.id.
    Nullable=True for safe migration of existing rows.
    Matches ORM definition in app/models/quality_score.py:32.
    """
    op.add_column(
        "asset_quality_scores",
        sa.Column("job_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_asset_quality_scores_job_id_render_jobs",
        "asset_quality_scores",
        "render_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove job_id column and FK from asset_quality_scores table."""
    op.drop_constraint(
        "fk_asset_quality_scores_job_id_render_jobs",
        "asset_quality_scores",
        type_="foreignkey",
    )
    op.drop_column("asset_quality_scores", "job_id")
