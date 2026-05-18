"""011_ai_video_generation: track AI video generation attempts

Revision ID: a1b2c3d4e5f6
Revises: f5e4d3c2b1a0
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'a1b2c3d4e5f6'
down_revision = 'f5e4d3c2b1a0'  # 010_gpu_metrics
branch_labels = None
depends_on = None


def upgrade():
    # Enum for model names
    op.execute("""
        CREATE TYPE ai_video_model_enum AS ENUM (
            'cogvideox_5b', 'cogvideox_2b', 'wan21_t2v', 'wan21_i2v'
        )
    """)

    # Enum for generation status
    op.execute("""
        CREATE TYPE ai_video_status_enum AS ENUM (
            'queued', 'loading_model', 'generating',
            'validating', 'complete', 'failed', 'timed_out'
        )
    """)

    op.create_table(
        'ai_video_generations',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.UUID(as_uuid=True), sa.ForeignKey(
            'jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scene_id', sa.String(64), nullable=False),
        sa.Column('model_name', sa.Enum('cogvideox_5b', 'cogvideox_2b',
            'wan21_t2v', 'wan21_i2v', name='ai_video_model_enum'),
            nullable=False),
        sa.Column('prompt', sa.Text, nullable=False),
        sa.Column('generation_params', JSONB, nullable=False,
                  server_default='{}'),
        sa.Column('vram_used_mb', sa.Integer, nullable=True),
        sa.Column('generation_duration_seconds', sa.Float, nullable=True),
        sa.Column('output_path', sa.Text, nullable=True),
        sa.Column('quality_score', sa.Float, nullable=True),
        sa.Column('fallback_level_used', sa.Integer,
                  nullable=False, server_default='1'),
        sa.Column('status', sa.Enum('queued', 'loading_model', 'generating',
            'validating', 'complete', 'failed', 'timed_out',
            name='ai_video_status_enum'),
            nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for analytics queries
    op.create_index('ix_ai_video_gen_job_id',
                    'ai_video_generations', ['job_id'])
    op.create_index('ix_ai_video_gen_model_status',
                    'ai_video_generations', ['model_name', 'status'])
    op.create_index('ix_ai_video_gen_created_at',
                    'ai_video_generations', ['created_at'])


def downgrade():
    op.drop_table('ai_video_generations')
    op.execute("DROP TYPE IF EXISTS ai_video_model_enum")
    op.execute("DROP TYPE IF EXISTS ai_video_status_enum")
