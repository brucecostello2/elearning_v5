"""
0009_render_segments — Table 18: render_segments

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
CREATE TYPE segment_status AS ENUM (
            'pending', 'rendering', 'complete', 'failed'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "render_segments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("render_jobs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("segment_index", sa.Integer, nullable=False),
        sa.Column("start_ms", sa.Integer, nullable=False),
        sa.Column("end_ms", sa.Integer, nullable=False),
        sa.Column("output_path", sa.String(1024), nullable=True),
        sa.Column("output_checksum", sa.String(64), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "pending", "rendering", "complete", "failed",
            name="segment_status", create_type=False),
            nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("render_segments")
    op.execute("DROP TYPE IF EXISTS segment_status")
