"""
0024_add_render_jobs_resume_from_stage — Add resume_from_stage to render_jobs

Resolves BUG-CHECKPOINT-STAGE: checkpoint_service.resume_from_checkpoint
previously wrote stage_name into the job_type column, but 3 of 8 stage
names (media_generation, manifest_generation, audio_generation) are not
valid values of the job_type enum. Every resume from those stages
crashed with InvalidTextRepresentationError in production. Hidden by
SQLite-era tests; surfaced by the reconciled PostgreSQL suite.

This migration separates the two concepts at the schema level:
  job_type — the kind of work (valid job_type enum value)
  resume_from_stage — the stage the resume picked up from (free text)

Pre-existing rows: resume_from_stage NULL (column is nullable; non-resume
jobs never set it). The column is VARCHAR(64) — generous enough for any
stage_name string, no constraint to a fixed list since stage names are
operator-facing labels, not an enum.

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add resume_from_stage column to render_jobs table.

    VARCHAR(64), nullable=True. Populated only on jobs created by
    checkpoint_service.resume_from_checkpoint; NULL for all others.
    """
    op.add_column(
        "render_jobs",
        sa.Column("resume_from_stage", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    """Remove resume_from_stage column from render_jobs table."""
    op.drop_column("render_jobs", "resume_from_stage")
