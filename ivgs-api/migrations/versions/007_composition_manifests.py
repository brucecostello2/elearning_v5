"""007_composition_manifests

Revision ID: 007
Revises: 006
Create Date: 2026-05-17

Creates composition_manifests table for deterministic render timelines.
Once locked, a manifest defines the authoritative timeline — no asset
generation can change timing without unlocking and regenerating.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE manifest_status_type AS ENUM
        ('draft', 'locked', 'rendered', 'invalid')
    """)

    op.create_table(
        'composition_manifests',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('job_id', sa.String(255),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('manifest_version', sa.Integer(), nullable=False,
                  server_default='1'),
        sa.Column('total_duration_ms', sa.Integer(), nullable=False),
        sa.Column('resolution_width', sa.Integer(), nullable=False,
                  server_default='1920'),
        sa.Column('resolution_height', sa.Integer(), nullable=False,
                  server_default='1080'),
        sa.Column('framerate', sa.Float(), nullable=False,
                  server_default='25.0'),
        sa.Column('audio_sample_rate', sa.Integer(), nullable=False,
                  server_default='44100'),
        # Full timeline: array of scene objects each with layers
        # [{scene_id, start_ms, duration_ms, layers: [{type, path,
        #   start_ms, duration_ms, z_index}]}]
        sa.Column('timeline', JSONB, nullable=False),
        sa.Column('status',
                  sa.Enum('draft', 'locked', 'rendered', 'invalid',
                          name='manifest_status_type'),
                  nullable=False, server_default='draft'),
        sa.Column('checksum', sa.String(64), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rendered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    op.create_index('ix_manifest_job_id', 'composition_manifests', ['job_id'])
    op.create_index('ix_manifest_status', 'composition_manifests', ['status'])


def downgrade() -> None:
    op.drop_table('composition_manifests')
    op.execute("DROP TYPE IF EXISTS manifest_status_type")
