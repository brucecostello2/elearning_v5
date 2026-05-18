"""018 – backup_snapshots table (NAS rsync tracking)
Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"

def upgrade():
    op.create_table(
        "backup_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("snapshot_name", sa.String(128), nullable=False, unique=True,
                  comment="e.g. ivgs_2026_05_17T020000Z"),
        sa.Column("backup_type", sa.String(20), nullable=False,
                  comment="incremental | full"),
        sa.Column("source_path", sa.String(512), nullable=False,
                  comment="Source path on cluster, e.g. /mnt/workdir"),
        sa.Column("dest_path", sa.String(512), nullable=False,
                  comment="NAS destination, e.g. /mnt/backup/ivgs/2026-05-17"),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending",
                  comment="pending | running | success | failed | restored"),
        sa.Column("rsync_exit_code", sa.Integer, nullable=True),
        sa.Column("db_dump_path", sa.String(512), nullable=True,
                  comment="Path to pg_dump .sql.gz on NAS"),
        sa.Column("bytes_transferred", sa.BigInteger, nullable=True),
        sa.Column("files_transferred", sa.Integer, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True,
                  comment="When this snapshot is eligible for NAS rotation"),
        sa.Column("verify_hash", sa.String(64), nullable=True,
                  comment="SHA-256 of the pg_dump file for integrity check"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_backup_snapshots_status",
                    "backup_snapshots", ["status", "created_at"])

def downgrade():
    op.drop_table("backup_snapshots")
