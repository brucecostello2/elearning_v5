"""
0013_backup_records — Table 22: backup_records

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
CREATE TYPE backup_type AS ENUM (
            'full_database', 'wal_archive', 'asset_backup',
            'config_backup', 'vm_snapshot'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE backup_status AS ENUM (
            'running', 'completed', 'failed', 'verified'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "backup_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("backup_type", postgresql.ENUM(
            "full_database", "wal_archive", "asset_backup",
            "config_backup", "vm_snapshot",
            name="backup_type", create_type=False),
            nullable=False),
        sa.Column("scope", sa.String(128), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "running", "completed", "failed", "verified",
            name="backup_status", create_type=False),
            nullable=False, server_default="running"),
        sa.Column("backup_path", sa.String(1024), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_checksum", sa.String(64), nullable=True),
        sa.Column("retention_days", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("backup_records")
    op.execute("DROP TYPE IF EXISTS backup_status")
    op.execute("DROP TYPE IF EXISTS backup_type")
