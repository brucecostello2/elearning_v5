"""
0006_dead_letter_queue — Table 15: dead_letter_messages

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE dlq_resolution AS ENUM (
            'replayed', 'discarded', 'escalated'
        )
    """)

    op.create_table(
        "dead_letter_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("original_queue", sa.String(128), nullable=True),
        sa.Column("task_name", sa.String(255), nullable=True),
        sa.Column("task_args", JSONB, nullable=True),
        sa.Column("task_kwargs", JSONB, nullable=True),
        sa.Column("exception_type", sa.String(255), nullable=True),
        sa.Column("exception_message", sa.Text, nullable=True),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column("failure_category", sa.Enum(
            "transient", "config", "external", "resource",
            name="failure_category", create_type=False),
            nullable=True),
        sa.Column("retry_count_exhausted", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("resolution", sa.Enum(
            "replayed", "discarded", "escalated",
            name="dlq_resolution", create_type=False),
            nullable=True),
    )
    op.create_index(
        "ix_dlq_category_created",
        "dead_letter_messages",
        ["failure_category", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("dead_letter_messages")
    op.execute("DROP TYPE IF EXISTS dlq_resolution")
