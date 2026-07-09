"""
0026_ad01_model_store — AD-01.5.2: models, model_capability_tags,
model_node_availability, model_approvals, project_model_selections.

Revision ID: 0026
Revises: 0025

DB-enforced invariants (PostgreSQL partial unique indexes):
  * uq_models_default_per_stage_tier — at most one is_default=true model
    per (stage, tier)
  * uq_selection_auto_project_scope / uq_selection_auto_scene_scope —
    at most one selected_by='auto' row per selection scope
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

_ENUMS: dict[str, tuple[str, ...]] = {
    "model_stage": (
        "transcript_refinement", "storyboard_generation", "image_generation",
        "video_generation", "animation_generation", "voiceover_tts",
        "talking_head", "composition", "translation",
    ),
    "model_engine": (
        "vllm", "ollama", "comfyui", "coqui", "kokoro", "cogvideox",
        "wan21", "animatediff", "latentsync", "sadtalker", "remotion",
    ),
    "model_tier": ("prototype", "production", "both"),
    "model_state": ("candidate", "approved", "deprecated", "retired"),
    "capability_dimension": (
        "visual_style", "subject_affinity", "motion_profile",
        "voice_profile", "language", "quality_bias",
    ),
    "node_availability_status": ("available", "loading", "unavailable"),
    "selection_source": ("auto", "manual"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    for name, values in _ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"""
DO $$ BEGIN
CREATE TYPE {name} AS ENUM ({vals});
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    # --- models ---
    op.create_table(
        "models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("stage", _enum("model_stage"), nullable=False),
        sa.Column("engine", _enum("model_engine"), nullable=False),
        sa.Column("tier", _enum("model_tier"), nullable=False,
                  server_default="both"),
        sa.Column("state", _enum("model_state"), nullable=False,
                  server_default="candidate"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("strengths", postgresql.JSONB, nullable=True),
        sa.Column("weaknesses", postgresql.JSONB, nullable=True),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("weights_ref", sa.String(512), nullable=True),
        sa.Column("weights_checksum", sa.String(128), nullable=True),
        sa.Column("license", sa.String(128), nullable=True),
        sa.Column("vram_gb", sa.Numeric(6, 2), nullable=True),
        sa.Column("dynamically_loadable", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("default_params", postgresql.JSONB, nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_models_stage_tier_state", "models", ["stage", "tier", "state"],
    )
    op.create_index(
        "uq_models_default_per_stage_tier", "models", ["stage", "tier"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    # --- model_capability_tags ---
    op.create_table(
        "model_capability_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("model_id", UUID(as_uuid=True),
                  sa.ForeignKey("models.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("dimension", _enum("capability_dimension"), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("weight", sa.Numeric(4, 3), nullable=True),
        sa.UniqueConstraint("model_id", "dimension", "value",
                            name="uq_capability_model_dim_value"),
    )
    op.create_index(
        "ix_capability_dimension_value", "model_capability_tags",
        ["dimension", "value"],
    )

    # --- model_node_availability ---
    op.create_table(
        "model_node_availability",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("model_id", UUID(as_uuid=True),
                  sa.ForeignKey("models.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("status", _enum("node_availability_status"),
                  nullable=False, server_default="unavailable"),
        sa.Column("served", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("last_health_check", sa.DateTime(timezone=True),
                  nullable=True),
        sa.UniqueConstraint("model_id", "node_id",
                            name="uq_availability_model_node"),
    )
    op.create_index(
        "ix_availability_node", "model_node_availability", ["node_id"],
    )

    # --- model_approvals ---
    op.create_table(
        "model_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("model_id", UUID(as_uuid=True),
                  sa.ForeignKey("models.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("attested_by", sa.String(128), nullable=False),
        sa.Column("vetting_reference", sa.String(512), nullable=False),
        sa.Column("checklist", postgresql.JSONB, nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # --- project_model_selections ---
    op.create_table(
        "project_model_selections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("scene_id", UUID(as_uuid=True),
                  sa.ForeignKey("storyboard_scenes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("stage", _enum("model_stage"), nullable=False),
        sa.Column("tier", _enum("model_tier"), nullable=False),
        sa.Column("model_id", UUID(as_uuid=True),
                  sa.ForeignKey("models.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("selected_by", _enum("selection_source"), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_selections_scope", "project_model_selections",
        ["project_id", "stage", "tier", "scene_id"],
    )
    op.create_index(
        "uq_selection_auto_project_scope", "project_model_selections",
        ["project_id", "stage", "tier"],
        unique=True,
        postgresql_where=sa.text("selected_by = 'auto' AND scene_id IS NULL"),
    )
    op.create_index(
        "uq_selection_auto_scene_scope", "project_model_selections",
        ["project_id", "stage", "tier", "scene_id"],
        unique=True,
        postgresql_where=sa.text("selected_by = 'auto' AND scene_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("project_model_selections")
    op.drop_table("model_approvals")
    op.drop_table("model_node_availability")
    op.drop_table("model_capability_tags")
    op.drop_table("models")
    for name in reversed(list(_ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
