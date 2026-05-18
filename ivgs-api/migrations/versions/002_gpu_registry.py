"""Add gpu_nodes and gpu_reservations tables.

Creates the GPU capability registry, enabling VRAM-aware scheduling.
Workers register their GPUs on startup. The GPU Scheduler reads this
table to find capable nodes before assigning tasks.

Revision ID: 002_gpu_registry
Revises: 001_pipeline_checkpoints
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_gpu_registry"
down_revision = "001_pipeline_checkpoints"
branch_labels = None
depends_on = None

GPU_STATUS_ENUM = postgresql.ENUM(
    "online", "offline", "draining",
    name="gpu_status_enum",
    create_type=True,
)
RESERVATION_STATUS_ENUM = postgresql.ENUM(
    "reserved", "active", "released", "expired",
    name="gpu_reservation_status_enum",
    create_type=True,
)


def upgrade() -> None:
    GPU_STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    RESERVATION_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "gpu_nodes",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("node_hostname", sa.String(128), nullable=False),
        sa.Column("gpu_index", sa.Integer(), nullable=False, default=0),
        sa.Column("gpu_model", sa.String(128), nullable=False,
                  comment="e.g. NVIDIA RTX 3090"),
        sa.Column("total_vram_mb", sa.Integer(), nullable=False),
        sa.Column("compute_capability", sa.String(8), nullable=True,
                  comment="e.g. 8.6"),
        sa.Column("status", GPU_STATUS_ENUM, nullable=False,
                  server_default="online"),
        sa.Column("registered_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_hostname", "gpu_index",
                            name="uq_gpu_node_hostname_index"),
    )

    op.create_table(
        "gpu_reservations",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("gpu_node_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("reserved_vram_mb", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=True,
                  comment="Model to be loaded (for residency tracking)"),
        sa.Column("status", RESERVATION_STATUS_ENUM, nullable=False,
                  server_default="reserved"),
        sa.Column("reserved_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["gpu_node_id"], ["gpu_nodes.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_gpu_nodes_status", "gpu_nodes", ["status"])
    op.create_index("ix_gpu_nodes_heartbeat", "gpu_nodes",
                    ["last_heartbeat_at"])
    op.create_index("ix_gpu_reservations_status", "gpu_reservations",
                    ["status"])
    op.create_index("ix_gpu_reservations_node", "gpu_reservations",
                    ["gpu_node_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_gpu_reservations_node")
    op.drop_index("ix_gpu_reservations_status")
    op.drop_index("ix_gpu_nodes_heartbeat")
    op.drop_index("ix_gpu_nodes_status")
    op.drop_table("gpu_reservations")
    op.drop_table("gpu_nodes")
    RESERVATION_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    GPU_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
