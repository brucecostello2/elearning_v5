"""
0002_pipeline_checkpoints — Table 10: pipeline_checkpoints

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
CREATE TYPE checkpoint_status AS ENUM (
            'pending', 'complete', 'failed', 'skipped'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "pipeline_checkpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("render_jobs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("stage_name", sa.String(64), nullable=False),
        sa.Column("stage_index", sa.Integer, nullable=True),
        sa.Column("checkpoint_data", JSONB, nullable=True),
        sa.Column("output_refs", JSONB, nullable=True),
        sa.Column("version_fingerprint", sa.String(128), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "pending", "complete", "failed", "skipped",
            name="checkpoint_status", create_type=False),
            nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_pipeline_checkpoints_job_stage",
        "pipeline_checkpoints",
        ["job_id", "stage_name"],
    )


def downgrade() -> None:
    op.drop_table("pipeline_checkpoints")
    op.execute("DROP TYPE IF EXISTS checkpoint_status")
