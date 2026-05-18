"""008_quality_scores

Revision ID: 008
Revises: 007
Create Date: 2026-05-17

Creates asset_quality_scores table.
Stores automated quality assessment for every generated media asset.
Scoring covers semantic relevance (CLIP for images), artifact detection
(FFprobe for video), and audio quality metrics (SNR, clipping).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE asset_type_enum AS ENUM
        ('image', 'video', 'audio', 'caption', 'thumbnail')
    """)
    op.execute("""
        CREATE TYPE quality_decision_enum AS ENUM
        ('approved', 'flagged', 'rejected', 'pending')
    """)

    op.create_table(
        'asset_quality_scores',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('asset_id', sa.String(255), nullable=False),
        sa.Column('job_id', sa.String(255),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('scene_id', sa.String(255), nullable=True),
        sa.Column('asset_type',
                  sa.Enum('image', 'video', 'audio', 'caption', 'thumbnail',
                          name='asset_type_enum'),
                  nullable=False),
        sa.Column('quality_score', sa.Float(), nullable=False),
        sa.Column('safety_score', sa.Float(), nullable=True),
        sa.Column('scoring_model', sa.String(128), nullable=False),
        # Breakdown: {clip_score, artifact_ratio, frame_consistency, snr_db, ...}
        sa.Column('scoring_details', JSONB, nullable=True),
        sa.Column('decision',
                  sa.Enum('approved', 'flagged', 'rejected', 'pending',
                          name='quality_decision_enum'),
                  nullable=False, server_default='pending'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.String(255), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_index('ix_quality_job_id', 'asset_quality_scores', ['job_id'])
    op.create_index('ix_quality_decision', 'asset_quality_scores',
                    ['decision', 'created_at'])
    op.create_index('ix_quality_asset_id', 'asset_quality_scores', ['asset_id'])


def downgrade() -> None:
    op.drop_table('asset_quality_scores')
    op.execute("DROP TYPE IF EXISTS asset_type_enum")
    op.execute("DROP TYPE IF EXISTS quality_decision_enum")
