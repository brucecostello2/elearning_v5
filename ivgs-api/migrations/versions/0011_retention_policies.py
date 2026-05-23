"""
0011_retention_policies — Table 20: retention_policies

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("hot_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("warm_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("cold_days", sa.Integer, nullable=False, server_default="365"),
        sa.Column("archive_days", sa.Integer, nullable=True),
        sa.Column("delete_after_days", sa.Integer, nullable=True),
        sa.Column("applies_to", sa.String(64), nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Seed default retention policies per Appendix D.4
    op.execute("""
        INSERT INTO retention_policies (name, hot_days, warm_days, cold_days, archive_days, delete_after_days, applies_to, is_default)
        VALUES
            ('standard', 30, 90, 365, NULL, NULL, 'all', true),
            ('long-term', 90, 180, 730, NULL, NULL, 'all', false),
            ('compliance', 365, 730, 3650, NULL, NULL, 'all', false)
    """)


def downgrade() -> None:
    op.drop_table("retention_policies")
