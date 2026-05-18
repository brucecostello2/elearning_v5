"""012_localization: multi-language support tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TYPE localization_status_enum AS ENUM (
            'pending', 'translating', 'tts_generating', 'captions_generating',
            'composing', 'complete', 'failed'
        )
    """)

    op.execute("""
        CREATE TYPE localized_asset_type_enum AS ENUM (
            'transcript', 'tts_audio', 'caption_srt', 'caption_vtt',
            'composed_video'
        )
    """)

    op.create_table(
        'localization_configs',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.UUID(as_uuid=True),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('source_language', sa.String(10),
                  nullable=False, server_default='en'),
        sa.Column('target_language', sa.String(10), nullable=False),
        sa.Column('translation_provider', sa.String(32),
                  nullable=False, server_default='openai_gpt4'),
        sa.Column('tts_voice_id', sa.String(128), nullable=True),
        sa.Column('tts_provider', sa.String(32),
                  nullable=False, server_default='openai'),
        sa.Column('status', sa.Enum(
            'pending', 'translating', 'tts_generating', 'captions_generating',
            'composing', 'complete', 'failed',
            name='localization_status_enum'),
            nullable=False, server_default='pending'),
        sa.Column('celery_task_id', sa.String(64), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('job_id', 'target_language',
                            name='uq_localization_job_lang'),
    )

    op.create_table(
        'localized_assets',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('localization_config_id', sa.BigInteger,
                  sa.ForeignKey('localization_configs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('job_id', sa.UUID(as_uuid=True),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('scene_id', sa.String(64), nullable=True),
        sa.Column('asset_type', sa.Enum(
            'transcript', 'tts_audio', 'caption_srt', 'caption_vtt',
            'composed_video', name='localized_asset_type_enum'),
            nullable=False),
        sa.Column('asset_path', sa.Text, nullable=True),
        sa.Column('quality_score', sa.Float, nullable=True),
        sa.Column('status', sa.String(32), nullable=False,
                  server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
    )

    op.create_index('ix_localization_configs_job_id',
                    'localization_configs', ['job_id'])
    op.create_index('ix_localized_assets_config_id',
                    'localized_assets', ['localization_config_id'])


def downgrade():
    op.drop_table('localized_assets')
    op.drop_table('localization_configs')
    op.execute("DROP TYPE IF EXISTS localization_status_enum")
    op.execute("DROP TYPE IF EXISTS localized_asset_type_enum")
