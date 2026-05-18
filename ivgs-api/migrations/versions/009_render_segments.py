"""009_render_segments

Revision ID: 009
Revises: 008
Create Date: 2026-05-17

Creates render_segments table for segment-based partial recovery.
Each segment is an independently renderable 30-second chunk.
Failed segments can be individually retried without losing completed work.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE segment_status_enum AS ENUM
        ('pending', 'rendering', 'complete', 'failed', 'validating')
    """)

    op.create_table(
        'render_segments',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('job_id', sa.String(255),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('segment_index', sa.Integer(), nullable=False),
        sa.Column('start_ms', sa.Integer(), nullable=False),
        sa.Column('end_ms', sa.Integer(), nullable=False),
        # References to input assets from manifest:
        # [{asset_path, asset_type, start_offset_ms, duration_ms}]
        sa.Column('input_assets', JSONB, nullable=True),
        sa.Column('output_path', sa.Text(), nullable=True),
        sa.Column('output_checksum', sa.String(64), nullable=True),
        sa.Column('output_duration_ms', sa.Integer(), nullable=True),
        sa.Column('status',
                  sa.Enum('pending', 'rendering', 'complete', 'failed',
                          'validating', name='segment_status_enum'),
                  nullable=False, server_default='pending'),
        sa.Column('render_duration_seconds', sa.Float(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('worker_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        # Unique constraint: one segment_index per job
        sa.UniqueConstraint('job_id', 'segment_index',
                            name='uq_segment_job_index'),
    )

    op.create_index('ix_segment_job_id', 'render_segments', ['job_id'])
    op.create_index('ix_segment_status', 'render_segments',
                    ['status', 'created_at'])


def downgrade() -> None:
    op.drop_table('render_segments')
    op.execute("DROP TYPE IF EXISTS segment_status_enum")
