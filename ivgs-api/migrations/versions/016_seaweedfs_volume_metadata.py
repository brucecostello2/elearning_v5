"""016 – SeaweedFS volume metadata columns
Revision ID: 016
Revises: 015
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"

def upgrade():
    # SeaweedFS file identifier: format "{volume_id},{cookie}"
    op.add_column("render_outputs",
        sa.Column("seaweedfs_fid", sa.String(64), nullable=True,
                  comment="SeaweedFS file ID, format: volumeId,cookie"))
    op.add_column("render_outputs",
        sa.Column("seaweedfs_volume_id", sa.Integer, nullable=True,
                  comment="Volume server ID within the collection"))
    op.add_column("render_outputs",
        sa.Column("seaweedfs_collection", sa.String(20), nullable=True,
                  comment="Collection name: hot | warm | cold | archive"))
    op.add_column("render_outputs",
        sa.Column("tier_transition_date", sa.TIMESTAMP(timezone=True),
                  nullable=True,
                  comment="Timestamp of most recent tier transition"))
    op.add_column("render_outputs",
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True))

    # Index for efficient fid lookups
    op.create_index("ix_render_outputs_seaweedfs_fid",
                    "render_outputs", ["seaweedfs_fid"])
    op.create_index("ix_render_outputs_tier_transition",
                    "render_outputs", ["storage_tier", "tier_transition_date"])

    # Tier transition audit log
    op.create_table(
        "tier_transition_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("render_output_id", sa.Integer,
                  sa.ForeignKey("render_outputs.id"), nullable=False),
        sa.Column("from_tier", sa.Enum(name="storage_tier"), nullable=True),
        sa.Column("to_tier", sa.Enum(name="storage_tier"), nullable=False),
        sa.Column("old_fid", sa.String(64), nullable=True),
        sa.Column("new_fid", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("migrated_by", sa.String(50), nullable=False,
                  comment="retention_service | manual | archive_service"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_tier_transition_log_output_id",
                    "tier_transition_log", ["render_output_id"])

def downgrade():
    op.drop_table("tier_transition_log")
    op.drop_index("ix_render_outputs_tier_transition")
    op.drop_index("ix_render_outputs_seaweedfs_fid")
    for col in ["file_size_bytes", "tier_transition_date",
                "seaweedfs_collection", "seaweedfs_volume_id", "seaweedfs_fid"]:
        op.drop_column("render_outputs", col)
