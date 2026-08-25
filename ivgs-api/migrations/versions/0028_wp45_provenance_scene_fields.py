"""0028 — WP-45: asset provenance, the five scene fields, and a vetting reference that fits.

Three unrelated columns families, one migration, because they ship in one deploy:

1. ``assets.generation_metadata`` (JSONB) — every media task in the fleet already
   sends a ``metadata`` form field to ``POST /projects/{id}/assets/upload`` and the
   route dropped it on the floor (WP-46 addendum A5.2 / ledger L-7). The four facts
   that reconstruct how a clip was made — engine, prompt id, engine model, input
   asset ids — had nowhere to land.

2. ``storyboard_scenes``: ``camera_angle``, ``transition_type``, ``effects``,
   ``timing_offset_ms``, ``generation_params`` — WP-43 D-2, ruled EXTEND. The Edit
   Scene modal has always sent these five keys; ``SceneUpdate`` declared four, so
   Pydantic discarded them silently and the UI looked as though it had saved.

3. ``render_jobs.language_code`` — WP-45 Task 6(c). Per-language progress is
   RULED derived, never a written column (WP-43 D-1), and it is derived from
   that variant's ``pipeline_checkpoints``. But nothing recorded WHICH language a
   job was rendering, so there was no join from a variant to its checkpoints and
   the derivation was impossible for any language. This column is the
   attribution, not the measure: it says which variant a job belongs to, and the
   progress figure is still computed from the checkpoints every time it is asked
   for. NULL means the project's source language, which is what every existing
   row is.

4. ``model_approvals.vetting_reference`` VARCHAR(512) -> TEXT — WP-45 Task 6(e).
   A real AD-01 attestation reference is not 512 characters. WP-46 §A8's is 1,912,
   and it is a *short* one: it names the certification, the run, the result, the
   hardware profile, the measured numbers and the evidence report. Truncating a
   provenance record to make it fit a column is the one thing an attestation may
   not do, so the column becomes TEXT and the schema states a generous cap inline.

Revision ID: 0028
Revises: 0027
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. asset generation provenance ---
    op.add_column(
        "assets",
        sa.Column(
            "generation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Caller-supplied provenance for a generated asset: engine, model, "
                "prompt id, input asset ids, generation parameters. Written by the "
                "upload route from the `metadata` form field."
            ),
        ),
    )
    # Dedup reads this column on every media upload; without an index the lookup
    # is a sequential scan over every asset in the system.
    op.create_index(
        "ix_assets_generation_params_hash",
        "assets",
        ["generation_params_hash"],
        unique=False,
        postgresql_where=sa.text("generation_params_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_assets_content_hash",
        "assets",
        ["content_hash"],
        unique=False,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )

    # --- 2. the five scene fields (WP-43 D-2) ---
    op.add_column(
        "storyboard_scenes",
        sa.Column("camera_angle", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("transition_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column(
            "effects",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="List of effect identifiers applied to this scene.",
        ),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("timing_offset_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column(
            "generation_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Per-scene generation parameter overrides (seed, steps, guidance...).",
        ),
    )

    # --- 3. language attribution for jobs (WP-45 Task 6c) ---
    op.add_column(
        "render_jobs",
        sa.Column(
            "language_code",
            sa.String(length=10),
            nullable=True,
            comment=(
                "The language variant this job renders. NULL = the project's "
                "source language. Attribution only: per-language progress is "
                "derived from pipeline_checkpoints, never stored."
            ),
        ),
    )
    op.create_index(
        "ix_render_jobs_project_language",
        "render_jobs",
        ["project_id", "language_code"],
        unique=False,
    )

    # --- 4. attestation evidence length (WP-45 Task 6e) ---
    op.alter_column(
        "model_approvals",
        "vetting_reference",
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "model_approvals",
        "attested_by",
        existing_type=sa.String(length=128),
        type_=sa.String(length=256),
        existing_nullable=False,
    )


def downgrade() -> None:
    # A vetting_reference longer than 512 characters cannot survive the reverse
    # cast, so refuse rather than truncate an attestation record.
    conn = op.get_bind()
    too_long = conn.execute(
        sa.text(
            "SELECT count(*) FROM model_approvals "
            "WHERE length(vetting_reference) > 512"
        )
    ).scalar()
    if too_long:
        raise RuntimeError(
            f"{too_long} model_approvals row(s) have a vetting_reference longer "
            "than 512 characters. Downgrading would truncate an attestation "
            "record. Shorten or archive them deliberately first."
        )
    op.alter_column(
        "model_approvals",
        "attested_by",
        existing_type=sa.String(length=256),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.alter_column(
        "model_approvals",
        "vetting_reference",
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=False,
    )

    op.drop_index("ix_render_jobs_project_language", table_name="render_jobs")
    op.drop_column("render_jobs", "language_code")

    op.drop_column("storyboard_scenes", "generation_params")
    op.drop_column("storyboard_scenes", "timing_offset_ms")
    op.drop_column("storyboard_scenes", "effects")
    op.drop_column("storyboard_scenes", "transition_type")
    op.drop_column("storyboard_scenes", "camera_angle")

    op.drop_index("ix_assets_content_hash", table_name="assets")
    op.drop_index("ix_assets_generation_params_hash", table_name="assets")
    op.drop_column("assets", "generation_metadata")
