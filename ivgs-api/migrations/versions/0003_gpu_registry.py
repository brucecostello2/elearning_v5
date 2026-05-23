"""
0003_gpu_registry — Tables 11-12: gpu_nodes, gpu_reservations

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
CREATE TYPE gpu_node_status AS ENUM ('online', 'offline', 'draining');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE reservation_status AS ENUM (
            'reserved', 'active', 'released', 'expired'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    # --- gpu_nodes ---
    op.create_table(
        "gpu_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("node_hostname", sa.String(64), nullable=False),
        sa.Column("gpu_index", sa.Integer, nullable=False),
        sa.Column("gpu_model", sa.String(128), nullable=True),
        sa.Column("total_vram_mb", sa.Integer, nullable=True),
        sa.Column("compute_capability", sa.String(16), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "online", "offline", "draining",
            name="gpu_node_status", create_type=False),
            nullable=False, server_default="online"),
        sa.Column("registered_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.UniqueConstraint("node_hostname", "gpu_index",
                            name="uq_gpu_nodes_host_index"),
    )

    # --- gpu_reservations ---
    op.create_table(
        "gpu_reservations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("gpu_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("gpu_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("render_jobs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("reserved_vram_mb", sa.Integer, nullable=False),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "reserved", "active", "released", "expired",
            name="reservation_status", create_type=False),
            nullable=False, server_default="reserved"),
        sa.Column("reserved_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gpu_reservations")
    op.drop_table("gpu_nodes")
    op.execute("DROP TYPE IF EXISTS reservation_status")
    op.execute("DROP TYPE IF EXISTS gpu_node_status")
