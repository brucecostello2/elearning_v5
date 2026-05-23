"""
0010_gpu_metrics — Table 19: gpu_metrics_history (daily partitioned)

Partitioned daily using PostgreSQL 17 native declarative partitioning.
30-day retention enforced via Celery Beat periodic task (retention_policies).

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
    # Create parent partitioned table (RANGE on recorded_at, daily)
    op.execute("""
        CREATE TABLE gpu_metrics_history (
            id          UUID NOT NULL DEFAULT uuid_generate_v4(),
            gpu_node_id UUID NOT NULL,
            gpu_util_pct        FLOAT,
            mem_util_pct        FLOAT,
            temperature_c       FLOAT,
            power_draw_w        FLOAT,
            active_job_count    INTEGER,
            queue_depth         INTEGER,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            FOREIGN KEY (gpu_node_id) REFERENCES gpu_nodes(id) ON DELETE CASCADE
        ) PARTITION BY RANGE (recorded_at)
    """)

    # Create index on the partitioned table
    op.execute("""
        CREATE INDEX ix_gpu_metrics_history_gpu_node_recorded
        ON gpu_metrics_history (gpu_node_id, recorded_at DESC)
    """)

    # Pre-create partitions: current month ± 1 month (enough for initial deployment)
    # Celery Beat periodic task will create future partitions and drop old ones
    op.execute("""
        DO $$ DECLARE
            start_date DATE;
            end_date   DATE;
            partition_name TEXT;
        BEGIN
            FOR i IN -1..2 LOOP
                start_date := date_trunc('day', NOW()) + (i || ' days')::INTERVAL;
                end_date   := start_date + INTERVAL '1 day';
                partition_name := 'gpu_metrics_history_'
                    || to_char(start_date, 'YYYY_MM_DD');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I
                     PARTITION OF gpu_metrics_history
                     FOR VALUES FROM (%L) TO (%L)',
                    partition_name, start_date, end_date
                );
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gpu_metrics_history CASCADE")
