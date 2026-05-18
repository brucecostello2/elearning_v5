"""017 – storage_quotas and storage_usage_log tables
Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"

def upgrade():
    op.create_table(
        "storage_quotas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer,
                  sa.ForeignKey("projects.id"), nullable=False, unique=True),
        sa.Column("quota_tier", sa.String(20), nullable=False,
                  server_default="free",
                  comment="free | standard | enterprise | custom"),
        sa.Column("max_bytes", sa.BigInteger, nullable=False,
                  comment="Total storage quota in bytes"),
        sa.Column("used_bytes", sa.BigInteger, nullable=False,
                  server_default="0"),
        sa.Column("hot_bytes", sa.BigInteger, server_default="0"),
        sa.Column("warm_bytes", sa.BigInteger, server_default="0"),
        sa.Column("cold_bytes", sa.BigInteger, server_default="0"),
        sa.Column("archive_bytes", sa.BigInteger, server_default="0"),
        sa.Column("warning_threshold", sa.Float, server_default="0.75",
                  comment="Fraction of max_bytes that triggers warning alert"),
        sa.Column("critical_threshold", sa.Float, server_default="0.90",
                  comment="Fraction of max_bytes that triggers critical alert"),
        sa.Column("soft_limit_active", sa.Boolean, server_default="FALSE",
                  comment="True = warn but allow; False = hard block on exceed"),
        sa.Column("last_updated", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )

    op.create_table(
        "storage_usage_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer,
                  sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("event", sa.String(50), nullable=False,
                  comment="file_added | file_deleted | tier_migrated | quota_enforced"),
        sa.Column("delta_bytes", sa.BigInteger, nullable=False),
        sa.Column("resulting_used_bytes", sa.BigInteger, nullable=False),
        sa.Column("tier", sa.Enum(name="storage_tier"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_usage_log_project_created",
                    "storage_usage_log", ["project_id", "created_at"])

def downgrade():
    op.drop_table("storage_usage_log")
    op.drop_table("storage_quotas")
