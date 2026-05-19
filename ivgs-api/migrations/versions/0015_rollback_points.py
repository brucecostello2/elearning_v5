"""Add rollback_points table for RollbackService

Revision ID: 0015
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"

def upgrade():
    op.create_table(
        "rollback_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_tag", sa.String(255), nullable=False),
        sa.Column("alembic_revision", sa.String(255), nullable=False),
        sa.Column("docker_image_tags", JSONB, nullable=False),
        sa.Column("config_snapshot_path", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rollback_points_created_at", "rollback_points", ["created_at"])

def downgrade():
    op.drop_table("rollback_points")
