"""Add task_retries table and retry columns to jobs.

Tracks every retry attempt with failure classification for analytics
and the cost-aware ceiling feature (halt retries if cumulative cost
exceeds configured threshold).

Revision ID: 003_retry_tracking
Revises: 002_gpu_registry
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_retry_tracking"
down_revision = "002_gpu_registry"
branch_labels = None
depends_on = None

FAILURE_TYPE_ENUM = postgresql.ENUM(
    "transient", "config", "external", "resource",
    name="failure_type_enum",
    create_type=True,
)


def upgrade() -> None:
    FAILURE_TYPE_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_retries",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("failure_type", FAILURE_TYPE_ENUM, nullable=False,
                  server_default="transient"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_traceback", sa.Text(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True,
                  comment="Backoff delay before next attempt"),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 4), nullable=True,
                  comment="Estimated API cost of this attempt"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add retry metadata columns to existing jobs table
    op.add_column("jobs", sa.Column("retry_count", sa.Integer(),
                                    nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("max_retries", sa.Integer(),
                                    nullable=False, server_default="4"))
    op.add_column("jobs", sa.Column("failure_category",
                                    FAILURE_TYPE_ENUM, nullable=True))
    op.add_column("jobs", sa.Column("cumulative_cost_usd",
                                    sa.Numeric(10, 4),
                                    nullable=False, server_default="0"))

    op.create_index("ix_task_retries_job_stage", "task_retries",
                    ["job_id", "stage_name"])
    op.create_index("ix_task_retries_failure_type", "task_retries",
                    ["failure_type"])


def downgrade() -> None:
    op.drop_index("ix_task_retries_failure_type")
    op.drop_index("ix_task_retries_job_stage")
    op.drop_column("jobs", "cumulative_cost_usd")
    op.drop_column("jobs", "failure_category")
    op.drop_column("jobs", "max_retries")
    op.drop_column("jobs", "retry_count")
    op.drop_table("task_retries")
    FAILURE_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
