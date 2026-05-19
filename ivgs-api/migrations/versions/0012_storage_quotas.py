"""
0012_storage_quotas — Table 21: storage_quotas

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_quotas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("max_bytes", sa.BigInteger, nullable=False),
        sa.Column("current_bytes", sa.BigInteger, nullable=False,
                  server_default="0"),
        sa.Column("tier", sa.Enum(
            "hot", "warm", "cold", "archived", "deleted",
            name="storage_tier", create_type=False),
            nullable=True),
        sa.Column("alert_threshold_pct", sa.Integer, nullable=False,
                  server_default="80"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_storage_quotas_entity",
        "storage_quotas",
        ["entity_type", "entity_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("storage_quotas")
