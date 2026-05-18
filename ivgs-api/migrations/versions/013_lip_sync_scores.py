"""013_lip_sync_scores: lip sync validation tracking

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'lip_sync_validations',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('asset_id', sa.BigInteger,
                  sa.ForeignKey('assets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('job_id', sa.UUID(as_uuid=True),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('scene_id', sa.String(64), nullable=False),
        sa.Column('sync_score', sa.Float, nullable=False),
        sa.Column('scoring_model', sa.String(64),
                  nullable=False, server_default='syncnet_v2'),
        # Per-frame scores: [{"frame": 0, "offset_ms": 12, "score": 0.91}, ...]
        sa.Column('frame_level_scores', JSONB, nullable=True),
        sa.Column('mouth_movement_correlation', sa.Float, nullable=True),
        sa.Column('frozen_frame_count', sa.Integer,
                  nullable=False, server_default='0'),
        sa.Column('passed', sa.Boolean, nullable=False,
                  server_default='false'),
        sa.Column('threshold_used', sa.Float,
                  nullable=False, server_default='0.85'),
        sa.Column('validated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
    )

    op.create_index('ix_lip_sync_asset_id',
                    'lip_sync_validations', ['asset_id'])
    op.create_index('ix_lip_sync_job_id',
                    'lip_sync_validations', ['job_id'])
    # Partial index for failed validations (for quick failure queries)
    op.execute("""
        CREATE INDEX ix_lip_sync_failed
        ON lip_sync_validations (job_id, validated_at)
        WHERE passed = false
    """)


def downgrade():
    op.drop_table('lip_sync_validations')
