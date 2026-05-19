"""Add prompt library tag support

Revision ID: 0016
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"

def upgrade():
    # Create tags table
    op.create_table(
        "prompt_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create junction table
    op.create_table(
        "prompt_tag_associations",
        sa.Column("prompt_id", sa.String(36), sa.ForeignKey("prompts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.String(36), sa.ForeignKey("prompt_tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # Add is_library flag to prompts
    op.add_column("prompts", sa.Column("is_library_template", sa.Boolean(), server_default="false"))

    # Seed default tags per §9.5
    op.execute("""
        INSERT INTO prompt_tags (id, name) VALUES
        (gen_random_uuid()::text, 'healthcare'),
        (gen_random_uuid()::text, 'technical-training'),
        (gen_random_uuid()::text, 'compliance'),
        (gen_random_uuid()::text, 'onboarding'),
        (gen_random_uuid()::text, 'safety'),
        (gen_random_uuid()::text, 'product-demo'),
        (gen_random_uuid()::text, 'corporate')
        ON CONFLICT (name) DO NOTHING
    """)

def downgrade():
    op.drop_table("prompt_tag_associations")
    op.drop_table("prompt_tags")
    op.drop_column("prompts", "is_library_template")
