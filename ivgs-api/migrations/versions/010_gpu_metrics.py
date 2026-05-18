"""010_gpu_metrics

Revision ID: 010
Revises: 009
Create Date: 2026-05-17

Creates gpu_metrics_history time-series table.
Records GPU utilization snapshots every 15 seconds from
worker heartbeats. Used by LoadBalancer for weighted scheduling.
Daily partitioning with 30-day retention enforced by cleanup task.
"""

from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gpu_metrics_history',
        sa.Column('id', sa.BigInteger(), nullable=False, primary_key=True),
        sa.Column('gpu_node_id', sa.Integer(),
                  sa.ForeignKey('gpu_nodes.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('gpu_util_pct', sa.Float(), nullable=False),
        sa.Column('mem_util_pct', sa.Float(), nullable=False),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('power_draw_w', sa.Float(), nullable=True),
        sa.Column('active_job_count', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('queue_depth', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('recorded_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Primary time-series index
    op.create_index(
        'ix_gpu_metrics_node_time',
        'gpu_metrics_history',
        ['gpu_node_id', 'recorded_at']
    )
    # Recent data query index (LoadBalancer reads last 5 minutes)
    op.create_index(
        'ix_gpu_metrics_recorded_at',
        'gpu_metrics_history',
        ['recorded_at']
    )

    # Retention policy via PostgreSQL function
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_gpu_metrics_history()
        RETURNS void AS $$
        BEGIN
            DELETE FROM gpu_metrics_history
            WHERE recorded_at < NOW() - INTERVAL '30 days';
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS cleanup_gpu_metrics_history()")
    op.drop_table('gpu_metrics_history')
