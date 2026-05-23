"""
0001_initial_core — Create core tables.

Tables: users, projects, transcripts, storyboard_scenes, assets,
        prompts, render_jobs, language_variants, audit_log,
        rollback_points, prompt_tags, prompt_tag_associations

Revision ID: 0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure uuid-ossp extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # --- ENUM types ---
    op.execute("""
DO $$ BEGIN
CREATE TYPE project_state AS ENUM (
            'DRAFT', 'TRANSCRIPT_REFINEMENT', 'STORYBOARD_GENERATION',
            'MEDIA_GENERATION', 'MANIFEST_GENERATION', 'AUDIO_GENERATION',
            'TALKING_HEAD_RENDER', 'PROTOTYPE_DRAFT', 'USER_REVIEW',
            'FINAL_RENDER', 'COMPLETE', 'LOCALISATION', 'ERROR'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE asset_type AS ENUM (
            'image', 'video', 'audio', 'document', 'talking_head', 'final_render'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE media_type AS ENUM ('image', 'video_clip', 'animation');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE prompt_type AS ENUM (
            'master', 'transcript_refinement', 'storyboard_generation',
            'image_generation', 'video_generation', 'animation_generation',
            'tts_voice', 'talking_head', 'composition', 'translation'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE user_role AS ENUM ('admin', 'operator', 'viewer');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE job_status AS ENUM ('pending', 'running', 'success', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE job_type AS ENUM (
            'transcript_refinement', 'storyboard_generation',
            'image_generation', 'video_generation', 'animation_generation',
            'tts_audio', 'talking_head_render', 'prototype_draft',
            'final_render', 'localisation'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE language_variant_state AS ENUM (
            'pending', 'processing', 'complete', 'failed'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE storage_tier AS ENUM (
            'hot', 'warm', 'cold', 'archived', 'deleted'
        );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")
    op.execute("""
DO $$ BEGIN
CREATE TYPE failure_category AS ENUM (
    'transient', 'config', 'external', 'resource'
);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")


    # ===================================================================
    # Table 6: users (§4.1)
    # ===================================================================
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM("admin", "operator", "viewer",
                                  name="user_role", create_type=False),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ===================================================================
    # Table 1: projects (§4.1)
    # ===================================================================
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("max_runtime_seconds", sa.Integer, nullable=True),
        sa.Column("state", postgresql.ENUM(
            "DRAFT", "TRANSCRIPT_REFINEMENT", "STORYBOARD_GENERATION",
            "MEDIA_GENERATION", "MANIFEST_GENERATION", "AUDIO_GENERATION",
            "TALKING_HEAD_RENDER", "PROTOTYPE_DRAFT", "USER_REVIEW",
            "FINAL_RENDER", "COMPLETE", "LOCALISATION", "ERROR",
            name="project_state", create_type=False),
            nullable=False, server_default="DRAFT"),
        sa.Column("hero_image_asset_id", UUID(as_uuid=True), nullable=True),
        sa.Column("talking_head_asset_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_audience", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ===================================================================
    # Table 4: assets (§4.1 — extended with v4 tier columns)
    # ===================================================================
    op.create_table(
        "assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("scene_id", UUID(as_uuid=True), nullable=True),
        sa.Column("asset_type", postgresql.ENUM(
            "image", "video", "audio", "document", "talking_head", "final_render",
            name="asset_type", create_type=False),
            nullable=False),
        sa.Column("seaweedfs_fid", sa.String(255), nullable=True),
        sa.Column("seaweedfs_path", sa.String(1024), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("language_code", sa.String(10), nullable=True),
        sa.Column("generation_prompt_id", UUID(as_uuid=True), nullable=True),
        # v4 additions
        sa.Column("storage_tier", postgresql.ENUM(
            "hot", "warm", "cold", "archived", "deleted",
            name="storage_tier", create_type=False),
            nullable=False, server_default="hot"),
        sa.Column("tier_transition_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("preserve_flag", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("reference_count", sa.Integer, nullable=False,
                  server_default="1"),
        sa.Column("generation_params_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ===================================================================
    # Table 2: transcripts (§4.1)
    # ===================================================================
    op.create_table(
        "transcripts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sequence_order", sa.Integer, nullable=False),
        sa.Column("original_asset_id", UUID(as_uuid=True),
                  sa.ForeignKey("assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("refined_text", sa.Text, nullable=True),
        sa.Column("language_code", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_transcripts_project_sequence",
        "transcripts",
        ["project_id", "sequence_order"],
    )

    # ===================================================================
    # Table 3: storyboard_scenes (§4.1)
    # ===================================================================
    op.create_table(
        "storyboard_scenes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("scene_index", sa.Integer, nullable=False),
        sa.Column("narration_text", sa.Text, nullable=True),
        sa.Column("visual_description", sa.Text, nullable=True),
        sa.Column("media_type", postgresql.ENUM(
            "image", "video_clip", "animation",
            name="media_type", create_type=False),
            nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_storyboard_scenes_project_index",
        "storyboard_scenes",
        ["project_id", "scene_index"],
    )

    # Now add the FK from assets.scene_id → storyboard_scenes.id
    op.create_foreign_key(
        "fk_assets_scene_id",
        "assets", "storyboard_scenes",
        ["scene_id"], ["id"],
        ondelete="SET NULL",
    )

    # Add FK from assets.generation_prompt_id (deferred to after prompts table)

    # ===================================================================
    # Table 5: prompts (§4.1)
    # ===================================================================
    op.create_table(
        "prompts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("scene_id", UUID(as_uuid=True),
                  sa.ForeignKey("storyboard_scenes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("prompt_type", postgresql.ENUM(
            "master", "transcript_refinement", "storyboard_generation",
            "image_generation", "video_generation", "animation_generation",
            "tts_voice", "talking_head", "composition", "translation",
            name="prompt_type", create_type=False),
            nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.Column("is_library_template", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("change_note", sa.Text, nullable=True),
    )

    # Add FK from assets.generation_prompt_id → prompts.id
    op.create_foreign_key(
        "fk_assets_generation_prompt_id",
        "assets", "prompts",
        ["generation_prompt_id"], ["id"],
        ondelete="SET NULL",
    )

    # Add FKs from projects to assets (hero_image, talking_head)
    op.create_foreign_key(
        "fk_projects_hero_image",
        "projects", "assets",
        ["hero_image_asset_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projects_talking_head",
        "projects", "assets",
        ["talking_head_asset_id"], ["id"],
        ondelete="SET NULL",
    )

    # ===================================================================
    # Table 7: render_jobs (§4.1)
    # ===================================================================
    op.create_table(
        "render_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("job_type", postgresql.ENUM(
            "transcript_refinement", "storyboard_generation",
            "image_generation", "video_generation", "animation_generation",
            "tts_audio", "talking_head_render", "prototype_draft",
            "final_render", "localisation",
            name="job_type", create_type=False),
            nullable=False),
        sa.Column("node_id", sa.String(32), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "pending", "running", "success", "failed",
            name="job_status", create_type=False),
            nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        # v4 retry columns
        sa.Column("retry_count", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=True),
        sa.Column("failure_category", postgresql.ENUM(
            "transient", "config", "external", "resource",
            name="failure_category", create_type=False),
            nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ===================================================================
    # Table 8: language_variants (§4.1)
    # ===================================================================
    op.create_table(
        "language_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("language_code", sa.String(10), nullable=False),
        sa.Column("state", postgresql.ENUM(
            "pending", "processing", "complete", "failed",
            name="language_variant_state", create_type=False),
            nullable=False, server_default="pending"),
        sa.Column("final_render_1080p_id", UUID(as_uuid=True),
                  sa.ForeignKey("assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("final_render_4k_id", UUID(as_uuid=True),
                  sa.ForeignKey("assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ===================================================================
    # Table 9: audit_log (§4.1)
    # ===================================================================
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("before_payload", JSONB, nullable=True),
        sa.Column("after_payload", JSONB, nullable=True),
        sa.Column("client_ip", INET, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_audit_log_resource",
        "audit_log",
        ["resource_type", "resource_id"],
    )
    op.create_index(
        "ix_audit_log_timestamp",
        "audit_log",
        [sa.text("timestamp DESC")],
    )

    # ===================================================================
    # Table: rollback_points (§14.3 RollbackService)
    # ===================================================================
    op.create_table(
        "rollback_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_tag", sa.String(255), nullable=False),
        sa.Column("alembic_revision", sa.String(255), nullable=False),
        sa.Column("docker_image_tags", JSONB, nullable=False),
        sa.Column("config_snapshot_path", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rollback_points_created_at",
        "rollback_points",
        ["created_at"],
    )

    # ===================================================================
    # Table: prompt_tags (§9.5 Prompt Library)
    # ===================================================================
    op.create_table(
        "prompt_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ===================================================================
    # Table: prompt_tag_associations (§9.5)
    # ===================================================================
    op.create_table(
        "prompt_tag_associations",
        sa.Column("prompt_id", sa.String(36),
                  sa.ForeignKey("prompts.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("tag_id", sa.String(36),
                  sa.ForeignKey("prompt_tags.id", ondelete="CASCADE"),
                  primary_key=True),
    )

    # Seed default prompt tags (§9.5)
    op.execute("""
        INSERT INTO prompt_tags (id, name) VALUES
        (gen_random_uuid()::text, 'healthcare'),
        (gen_random_uuid()::text, 'technical-training'),
        (gen_random_uuid()::text, 'compliance'),
        (gen_random_uuid()::text, 'onboarding'),
        (gen_random_uuid()::text, 'safety'),
        (gen_random_uuid()::text, 'product-demo'),
        (gen_random_uuid()::text, 'corporate')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("prompt_tag_associations")
    op.drop_table("prompt_tags")
    op.drop_table("rollback_points")
    op.drop_table("audit_log")
    op.drop_table("language_variants")
    op.drop_table("render_jobs")
    op.drop_table("prompts")
    op.drop_table("storyboard_scenes")
    op.drop_table("transcripts")
    op.drop_table("assets")
    op.drop_table("projects")
    op.drop_table("users")
    # Drop ENUMs
    for enum_name in [
        "language_variant_state", "failure_category", "job_status",
        "job_type", "storage_tier", "prompt_type", "user_role",
        "media_type", "asset_type", "project_state",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
