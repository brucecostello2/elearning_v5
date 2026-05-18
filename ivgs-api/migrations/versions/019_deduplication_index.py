"""019 – deduplication_index table (SHA-256 content-addressable storage)
Revision ID: 019
Revises: 018
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"

def upgrade():
    op.create_table(
        "deduplication_index",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sha256_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("canonical_fid", sa.String(64), nullable=False,
                  comment="SeaweedFS FID of the single authoritative copy"),
        sa.Column("canonical_collection", sa.String(20), nullable=False,
                  comment="hot | warm | cold | archive (tier of canonical copy)"),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("reference_count", sa.Integer, nullable=False,
                  server_default="1"),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("last_referenced_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_dedup_hash", "deduplication_index", ["sha256_hash"])

    # Link render_outputs back to their dedup entry
    op.add_column("render_outputs",
        sa.Column("dedup_index_id", sa.Integer,
                  sa.ForeignKey("deduplication_index.id"), nullable=True))
    op.add_column("render_outputs",
        sa.Column("sha256_hash", sa.String(64), nullable=True))

    # asset_invalidation_log for orphan tracking
    op.create_table(
        "asset_invalidation_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("seaweedfs_fid", sa.String(64), nullable=False),
        sa.Column("filer_path", sa.String(512), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("action", sa.String(30), nullable=False,
                  comment="quarantined | deleted | restored"),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("quarantine_expires_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_invalidation_log_fid",
                    "asset_invalidation_log", ["seaweedfs_fid"])

def downgrade():
    op.drop_table("asset_invalidation_log")
    op.drop_column("render_outputs", "sha256_hash")
    op.drop_column("render_outputs", "dedup_index_id")
    op.drop_table("deduplication_index")
