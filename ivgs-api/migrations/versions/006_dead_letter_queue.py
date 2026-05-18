"""006_dead_letter_queue

Revision ID: 006
Revises: 005
Create Date: 2026-05-17

Creates dead_letter_messages table for DLQ management.
Captures every task that has exhausted its retry policy with
full traceback, failure category, and review/resolution tracking.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create resolution enum
    op.execute("""
        CREATE TYPE dlq_resolution_type AS ENUM
        ('replayed', 'discarded', 'escalated', 'pending')
    """)

    # Create failure category enum
    op.execute("""
        CREATE TYPE failure_category_type AS ENUM
        ('transient', 'config', 'external', 'resource',
         'data_corruption', 'timeout', 'unknown')
    """)

    op.create_table(
        'dead_letter_messages',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('original_queue', sa.String(128), nullable=False),
        sa.Column('task_name', sa.String(255), nullable=False),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('task_args', JSONB, nullable=True),
        sa.Column('task_kwargs', JSONB, nullable=True),
        sa.Column('exception_type', sa.String(255), nullable=False),
        sa.Column('exception_message', sa.Text(), nullable=False),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('failure_category',
                  sa.Enum('transient', 'config', 'external', 'resource',
                          'data_corruption', 'timeout', 'unknown',
                          name='failure_category_type'),
                  nullable=False, server_default='unknown'),
        sa.Column('retry_count_exhausted', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('job_id', sa.String(255), sa.ForeignKey('jobs.id',
                  ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.String(255), nullable=True),
        sa.Column('resolution',
                  sa.Enum('replayed', 'discarded', 'escalated', 'pending',
                          name='dlq_resolution_type'),
                  nullable=False, server_default='pending'),
        sa.Column('replay_task_id', sa.String(255), nullable=True),
    )

    # Composite index for analytics queries
    op.create_index(
        'ix_dlq_category_created',
        'dead_letter_messages',
        ['failure_category', 'created_at']
    )
    # Index for pending messages (most common query)
    op.create_index(
        'ix_dlq_resolution_created',
        'dead_letter_messages',
        ['resolution', 'created_at']
    )
    # Index for task-level failure analysis
    op.create_index(
        'ix_dlq_task_name',
        'dead_letter_messages',
        ['task_name']
    )


def downgrade() -> None:
    op.drop_table('dead_letter_messages')
    op.execute("DROP TYPE IF EXISTS dlq_resolution_type")
    op.execute("DROP TYPE IF EXISTS failure_category_type")
