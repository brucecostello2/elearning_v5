"""
0032_wp56_presets — AD-09.5: a named, VERSIONED bundle of choices applied at
project creation, plus the provenance columns on ``projects``.

Revision ID: 0032
Revises: 0031

VERSIONED RATHER THAN MUTATED, and the table shape is what enforces it. A
preset is identified by ``(name, version)``, not by ``id`` alone. Editing a
preset INSERTS a new row with ``version = max + 1`` and flips ``is_active``;
it never UPDATEs a payload. That is the only way "a course records which preset
VERSION produced it" can be true a year later — an in-place edit would silently
rewrite the provenance of every project that had already used it.

PRESETS ARE DEFAULTS, NOT CONSTRAINTS. Applying a preset writes concrete values
into the project. Nothing downstream re-reads the preset at render time, so a
later preset edit cannot change what an existing project renders. ``projects``
therefore carries ``preset_id`` and ``preset_version`` for PROVENANCE only.

``preset_version`` IS DENORMALISED ON PURPOSE. It duplicates a column reachable
through ``preset_id``, which normally would be a defect. Here the FK is
``ON DELETE SET NULL`` — deleting a preset must not delete projects — and when
that fires, ``preset_version`` is the only surviving record that the project
was created from version 3 of something. Provenance that a delete can erase is
not provenance.

NO ``preset_drift`` COLUMN IN THIS MIGRATION, DELIBERATELY. AD-09.14 open
question 8 — whether to surface divergence between a project and its preset or
ignore it — is UNRULED as of 2026-08-25. WP-56 was instructed not to decide it
and has not: the decision point is recorded in the report instead. Adding the
column now would pick "surface it" by default and then leave a column nothing
computes, which is the green-surface-over-empty-action shape AD-09.3 names as a
blocking precondition. It is one additive migration whenever it is ruled.

PAYLOAD IS OPAQUE JSONB AND IS VALIDATED IN THE API, NOT HERE. The payload
spans branding, actor, model selections, media defaults, typography tokens and
logo policy — six subsystems, four of which are still moving. A CHECK
constraint here would be a fourth statement of a contract that already has
three, which is precisely how the alert-metric names came to be wrong three
times over (WP-54).

NOTHING IN THE PIPELINE READS THIS TABLE (WP-56 boundary condition).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("payload", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("owner_scope",
                  postgresql.ENUM("global", "user", name="library_owner_scope",
                                  create_type=False),
                  nullable=False, server_default="user"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # The identity of a preset. A second row for the same (name, version)
        # is an attempt to mutate history and the database refuses it.
        sa.UniqueConstraint("name", "version", name="uq_presets_name_version"),
        sa.CheckConstraint("version >= 1", name="ck_presets_version_positive"),
    )
    # Exactly one ACTIVE version per preset name. This is the constraint that
    # makes "the current version of 'Corporate 2026'" a well-defined phrase
    # instead of a convention someone has to remember.
    op.create_index(
        "uq_presets_active_per_name", "presets", ["name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_presets_scope_active", "presets", ["owner_scope", "name"],
        postgresql_where=sa.text("is_active"),
    )

    # --- provenance on projects ---
    op.add_column(
        "projects",
        sa.Column("preset_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("preset_version", sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_preset_id_presets",
        "projects", "presets",
        ["preset_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_preset_id_presets", "projects", type_="foreignkey")
    op.drop_column("projects", "preset_version")
    op.drop_column("projects", "preset_id")
    op.drop_index("ix_presets_scope_active", table_name="presets")
    op.drop_index("uq_presets_active_per_name", table_name="presets")
    op.drop_table("presets")
