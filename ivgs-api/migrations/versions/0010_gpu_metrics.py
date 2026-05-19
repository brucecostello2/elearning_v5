"""
0010_gpu_metrics — Table 19: gpu_metrics_history (TimescaleDB hypertable)

Partitioned daily with 30-day retention via TimescaleDB.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gpu_metrics_history",
        sa.Column("id", UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("gpu_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("gpu_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("gpu_util_pct", sa.Float, nullable=True),
        sa.Column("mem_util_pct", sa.Float, nullable=True),
        sa.Column("temperature_c", sa.Float, nullable=True),
        sa.Column("power_draw_w", sa.Float, nullable=True),
        sa.Column("active_job_count", sa.Integer, nullable=True),
        sa.Column("queue_depth", sa.Integer, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Convert to TimescaleDB hypertable partitioned by recorded_at
    op.execute("""
        SELECT create_hypertable(
            'gpu_metrics_history',
            'recorded_at',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        )
    """)

    # 30-day automatic retention policy
    op.execute("""
        SELECT add_retention_policy(
            'gpu_metrics_history',
            INTERVAL '30 days',
            if_not_exists => TRUE
        )
    """)


def downgrade() -> None:
    # Remove retention policy first
    op.execute("""
        SELECT remove_retention_policy('gpu_metrics_history', if_exists => TRUE)
    """)
    op.drop_table("gpu_metrics_history")
