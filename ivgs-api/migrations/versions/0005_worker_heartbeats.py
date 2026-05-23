"""
0005_worker_heartbeats — Table 14: worker_heartbeats

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
CREATE TYPE heartbeat_status AS ENUM (
            'alive', 'suspected_dead', 'confirmed_dead'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "worker_heartbeats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("node_hostname", sa.String(64), nullable=True),
        sa.Column("gpu_index", sa.Integer, nullable=True),
        sa.Column("current_job_id", UUID(as_uuid=True),
                  sa.ForeignKey("render_jobs.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("heartbeat_data", JSONB, nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("status", postgresql.ENUM(
            "alive", "suspected_dead", "confirmed_dead",
            name="heartbeat_status", create_type=False),
            nullable=False, server_default="alive"),
    )
    op.create_index(
        "ix_worker_heartbeats_last_heartbeat",
        "worker_heartbeats",
        [sa.text("last_heartbeat_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.execute("DROP TYPE IF EXISTS heartbeat_status")
