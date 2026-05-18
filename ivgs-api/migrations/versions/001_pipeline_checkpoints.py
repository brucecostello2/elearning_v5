"""Add pipeline_checkpoints table for resumable pipeline execution.

Creates the pipeline_checkpoints table which stores per-stage completion
status and output references, enabling jobs to resume from the last
successful stage after any failure.

Revision ID: 001_pipeline_checkpoints
Revises: (base v3 migration)
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Alembic revision identifiers
revision = "001_pipeline_checkpoints"
down_revision = None  # Set to last v3 migration revision ID
branch_labels = None
depends_on = None

STAGE_STATUS_ENUM = postgresql.ENUM(
    "pending", "running", "complete", "failed", "skipped",
    name="stage_status_enum",
    create_type=True,
)


def upgrade() -> None:
    """Create pipeline_checkpoints table with indexes."""
    STAGE_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "pipeline_checkpoints",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(64), nullable=False),
        sa.Column("stage_index", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "checkpoint_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Input parameters and intermediate data for stage",
        ),
        sa.Column(
            "output_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Output file paths/URLs produced by stage",
        ),
        sa.Column(
            "version_fingerprint",
            sa.String(64),
            nullable=True,
            comment="SHA-256 of input params for cache invalidation",
        ),
        sa.Column(
            "status",
            STAGE_STATUS_ENUM,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"],
            name="fk_checkpoints_job_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "stage_name",
            name="uq_checkpoint_job_stage",
        ),
    )

    # Composite index for the most common query: fetch all checkpoints for job
    op.create_index(
        "ix_checkpoints_job_stage",
        "pipeline_checkpoints",
        ["job_id", "stage_name"],
        unique=False,
    )
    # Index for querying by status (e.g., find all running stages)
    op.create_index(
        "ix_checkpoints_status",
        "pipeline_checkpoints",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop pipeline_checkpoints table and enum."""
    op.drop_index("ix_checkpoints_status", table_name="pipeline_checkpoints")
    op.drop_index("ix_checkpoints_job_stage", table_name="pipeline_checkpoints")
    op.drop_table("pipeline_checkpoints")
    STAGE_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
