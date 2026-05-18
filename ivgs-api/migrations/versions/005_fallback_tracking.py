"""Add fallback tracking columns and policies table.

Records which fallback level was used for each scene's generation,
and stores per-scene-type fallback policy configuration.

Revision ID: 005_fallback_tracking
Revises: 004_worker_heartbeats
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_fallback_tracking"
down_revision = "004_worker_heartbeats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add fallback tracking to job_scenes (create table if v3 didn't add it)
    # Using try/except to handle both cases gracefully
    try:
        op.add_column(
            "job_scenes",
            sa.Column("generation_level", sa.Integer(), nullable=False,
                      server_default="2",
                      comment="1=AI video, 2=animated still, 3=zoom/pan, 4=static"),
        )
        op.add_column(
            "job_scenes",
            sa.Column("fallback_reason", sa.Text(), nullable=True),
        )
        op.add_column(
            "job_scenes",
            sa.Column("original_level", sa.Integer(), nullable=True,
                      comment="Level originally attempted before fallback"),
        )
        op.add_column(
            "job_scenes",
            sa.Column(
                "fallback_attempts",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment="Array of {level, error, timestamp} for each attempt",
            ),
        )
    except Exception:
        # job_scenes may not exist in this v3 variant; create minimal version
        op.create_table(
            "job_scenes",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("scene_index", sa.Integer(), nullable=False),
            sa.Column("scene_type", sa.String(64), nullable=True),
            sa.Column("generation_level", sa.Integer(), nullable=False,
                      server_default="2"),
            sa.Column("fallback_reason", sa.Text(), nullable=True),
            sa.Column("original_level", sa.Integer(), nullable=True),
            sa.Column("fallback_attempts",
                      postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"],
                                    ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # Fallback policies per scene type (configurable without redeploy)
    op.create_table(
        "fallback_policies",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("scene_type", sa.String(64), nullable=False, unique=True),
        sa.Column("level_1_strategy", sa.String(128), nullable=True,
                  comment="Phase 3: AI video (cogvideox/wan21)"),
        sa.Column("level_2_strategy", sa.String(128), nullable=False,
                  server_default="ken_burns"),
        sa.Column("level_3_strategy", sa.String(128), nullable=False,
                  server_default="zoom_pan"),
        sa.Column("level_4_strategy", sa.String(128), nullable=False,
                  server_default="static"),
        sa.Column("phase1_start_level", sa.Integer(), nullable=False,
                  server_default="2",
                  comment="Phase 1 starts at L2 (no AI video)"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed default policies
    op.execute("""
        INSERT INTO fallback_policies
            (scene_type, level_2_strategy, level_3_strategy,
             level_4_strategy, phase1_start_level)
        VALUES
            ('action',       'ken_burns', 'zoom_pan', 'static', 2),
            ('talking_head', 'ken_burns', 'zoom_pan', 'static', 2),
            ('broll',        'ken_burns', 'zoom_pan', 'static', 2),
            ('title_card',   'static',    'static',   'static', 4),
            ('default',      'ken_burns', 'zoom_pan', 'static', 2)
        ON CONFLICT (scene_type) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("fallback_policies")
    for col in ["generation_level", "fallback_reason",
                "original_level", "fallback_attempts"]:
        try:
            op.drop_column("job_scenes", col)
        except Exception:
            pass
