"""
0008_quality_scores — Table 17: asset_quality_scores

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
CREATE TYPE quality_decision AS ENUM (
            'approved', 'flagged', 'rejected'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "asset_quality_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("safety_score", sa.Float, nullable=True),
        sa.Column("scoring_details", JSONB, nullable=True),
        sa.Column("decision", postgresql.ENUM(
            "approved", "flagged", "rejected",
            name="quality_decision", create_type=False),
            nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("asset_quality_scores")
    op.execute("DROP TYPE IF EXISTS quality_decision")
