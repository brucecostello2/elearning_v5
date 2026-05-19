"""
0014_fallback_policies — Table 23: fallback_policies

Seeds default fallback chains per §6.3 and Appendix D.4.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fallback_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("scene_type", sa.String(64), unique=True, nullable=False),
        sa.Column("level_1_strategy", sa.String(64), nullable=False),
        sa.Column("level_2_strategy", sa.String(64), nullable=False),
        sa.Column("level_3_strategy", sa.String(64), nullable=False),
        sa.Column("level_4_strategy", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Seed default fallback policies per §6.3 Table 6-6 and Appendix D.4
    op.execute("""
        INSERT INTO fallback_policies (scene_type, level_1_strategy, level_2_strategy, level_3_strategy, level_4_strategy)
        VALUES
            ('action', 'ai_video', 'animated_still', 'zoom_pan', 'static_image'),
            ('talking_head', 'ai_video', 'animated_still', 'zoom_pan', 'static_image'),
            ('broll', 'ai_video', 'animated_still', 'zoom_pan', 'static_image'),
            ('title_card', 'ai_video', 'animated_still', 'zoom_pan', 'static_image')
    """)


def downgrade() -> None:
    op.drop_table("fallback_policies")
