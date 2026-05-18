"""014_caption_alignment: caption forced alignment tracking

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TYPE caption_alignment_status_enum AS ENUM (
            'pending', 'stt_running', 'aligning', 'aligned',
            'drifted', 'failed', 'review_required'
        )
    """)

    op.create_table(
        'caption_alignments',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.UUID(as_uuid=True),
                  sa.ForeignKey('jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('scene_id', sa.String(64), nullable=False),
        sa.Column('language_code', sa.String(10),
                  nullable=False, server_default='en'),
        sa.Column('original_text', sa.Text, nullable=False),
        sa.Column('spoken_text', sa.Text, nullable=True,
                  comment='STT transcript of actual audio'),
        sa.Column('text_match_ratio', sa.Float, nullable=True,
                  comment='SequenceMatcher ratio: spoken vs original'),
        sa.Column('alignment_confidence', sa.Float, nullable=True),
        # [{"word": "hello", "start_ms": 120, "end_ms": 450, "score": 0.97}]
        sa.Column('word_timestamps', JSONB, nullable=True),
        sa.Column('drift_ms_max', sa.Float, nullable=True,
                  comment='Max ms of drift across all words in scene'),
        sa.Column('drift_ms_p95', sa.Float, nullable=True),
        sa.Column('output_srt_path', sa.Text, nullable=True),
        sa.Column('output_vtt_path', sa.Text, nullable=True),
        sa.Column('status', sa.Enum(
            'pending', 'stt_running', 'aligning', 'aligned',
            'drifted', 'failed', 'review_required',
            name='caption_alignment_status_enum'),
            nullable=False, server_default='pending'),
        sa.Column('aligner_tool', sa.String(32),
                  nullable=False, server_default='mfa'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('ix_caption_alignment_job_scene',
                    'caption_alignments', ['job_id', 'scene_id'])
    op.execute("""
        CREATE INDEX ix_caption_alignment_drifted
        ON caption_alignments (job_id, drift_ms_max)
        WHERE status = 'drifted'
    """)


def downgrade():
    op.drop_table('caption_alignments')
    op.execute("DROP TYPE IF EXISTS caption_alignment_status_enum")
