"""
0004_retry_tracking — Table 13: task_retries

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_retries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("render_jobs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("stage_name", sa.String(64), nullable=True),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("failure_type", sa.Enum(
            "transient", "config", "external", "resource",
            name="failure_category", create_type=False),
            nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_traceback", sa.Text, nullable=True),
        sa.Column("retry_after_seconds", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("task_retries")
