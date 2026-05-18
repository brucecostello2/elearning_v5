"""015 – retention_policies table and storage_tier ENUM
Revision ID: 015
Revises: 014
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"

def upgrade():
    # Create storage tier ENUM (no S3 storage class names)
    op.execute("""
        CREATE TYPE storage_tier AS ENUM (
            'hot', 'warm', 'cold', 'archive'
        )
    """)

    op.create_table(
        "retention_policies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("project_type", sa.String(50), nullable=True,
                  comment="NULL = global default; else project-specific"),
        sa.Column("hot_days", sa.Integer, nullable=False, default=7,
                  comment="Days before HOT→WARM transition"),
        sa.Column("warm_days", sa.Integer, nullable=False, default=30,
                  comment="Days before WARM→COLD transition"),
        sa.Column("cold_days", sa.Integer, nullable=False, default=180,
                  comment="Days before COLD→ARCHIVE transition"),
        sa.Column("delete_after_days", sa.Integer, nullable=True,
                  comment="Days before ARCHIVE deletion; NULL = keep forever"),
        sa.Column("preserve_on_download", sa.Boolean, default=True,
                  comment="Reset to HOT on user download"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"),
                  onupdate=sa.text("NOW()")),
    )

    # Add storage_tier column to render_outputs (existing table)
    op.add_column(
        "render_outputs",
        sa.Column("storage_tier", sa.Enum(name="storage_tier"),
                  nullable=False, server_default="hot")
    )
    op.add_column(
        "render_outputs",
        sa.Column("retention_policy_id", sa.Integer,
                  sa.ForeignKey("retention_policies.id"), nullable=True)
    )
    op.add_column(
        "render_outputs",
        sa.Column("preserve_flag", sa.Boolean, default=False)
    )
    op.add_column(
        "render_outputs",
        sa.Column("last_accessed_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )

    # Default global policy
    op.execute("""
        INSERT INTO retention_policies
            (name, project_type, hot_days, warm_days, cold_days,
             delete_after_days, preserve_on_download)
        VALUES
            ('global_default', NULL, 7, 30, 180, 365, TRUE)
    """)

def downgrade():
    op.drop_column("render_outputs", "last_accessed_at")
    op.drop_column("render_outputs", "preserve_flag")
    op.drop_column("render_outputs", "retention_policy_id")
    op.drop_column("render_outputs", "storage_tier")
    op.drop_table("retention_policies")
    op.execute("DROP TYPE storage_tier")
