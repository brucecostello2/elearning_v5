"""
0007_composition_manifests — Table 16: composition_manifests

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE manifest_status AS ENUM (
            'draft', 'locked', 'rendered', 'invalid'
        )
    """)

    op.create_table(
        "composition_manifests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("render_jobs.id", ondelete="CASCADE"),
                  unique=True, nullable=False),
        sa.Column("manifest_version", sa.String(32), nullable=True),
        sa.Column("total_duration_ms", sa.Integer, nullable=True),
        sa.Column("resolution_width", sa.Integer, nullable=True),
        sa.Column("resolution_height", sa.Integer, nullable=True),
        sa.Column("framerate", sa.Integer, nullable=True),
        sa.Column("audio_sample_rate", sa.Integer, nullable=True),
        sa.Column("timeline", JSONB, nullable=True),
        sa.Column("status", sa.Enum(
            "draft", "locked", "rendered", "invalid",
            name="manifest_status", create_type=False),
            nullable=False, server_default="draft"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("composition_manifests")
    op.execute("DROP TYPE IF EXISTS manifest_status")
