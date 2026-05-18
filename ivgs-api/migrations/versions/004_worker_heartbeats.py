"""Add worker_heartbeats table for crash detection.

Each Celery worker writes a heartbeat row every 10 seconds. The
WorkerSupervisor periodic task reads this table to detect workers
that have gone silent and reassigns their jobs.

Revision ID: 004_worker_heartbeats
Revises: 003_retry_tracking
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_worker_heartbeats"
down_revision = "003_retry_tracking"
branch_labels = None
depends_on = None

WORKER_STATUS_ENUM = postgresql.ENUM(
    "alive", "suspected_dead", "confirmed_dead",
    name="worker_status_enum",
    create_type=True,
)


def upgrade() -> None:
    WORKER_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("worker_id", sa.String(128), nullable=False, unique=True,
                  comment="Celery worker hostname + PID"),
        sa.Column("node_hostname", sa.String(128), nullable=False),
        sa.Column("gpu_index", sa.Integer(), nullable=True),
        sa.Column("current_job_id", sa.Integer(), nullable=True,
                  comment="Job currently being processed, null if idle"),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column(
            "heartbeat_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="GPU temp°C, mem_used_mb, util%, cpu%, memory_pct",
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("status", WORKER_STATUS_ENUM, nullable=False,
                  server_default="alive"),
        sa.Column("registered_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["current_job_id"], ["jobs.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Critical index for the supervisor heartbeat check query
    op.create_index("ix_heartbeats_last_seen", "worker_heartbeats",
                    ["last_heartbeat_at"])
    op.create_index("ix_heartbeats_status", "worker_heartbeats",
                    ["status"])
    op.create_index("ix_heartbeats_worker_id", "worker_heartbeats",
                    ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_heartbeats_worker_id")
    op.drop_index("ix_heartbeats_status")
    op.drop_index("ix_heartbeats_last_seen")
    op.drop_table("worker_heartbeats")
    WORKER_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
