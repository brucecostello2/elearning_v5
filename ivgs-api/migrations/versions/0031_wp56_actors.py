"""
0031_wp56_actors — AD-09.4.3: presenter identity as a first-class entity.

Revision ID: 0031
Revises: 0030

"Same actor with the same voice across two courses" is not expressible as a
file, which is why this is an entity and not another asset kind. A reference
clip is the INPUT to an identity; the identity is the clip plus the voice
profile plus the per-engine parameters that reproduce it.

``engine_bindings`` — READ THIS BEFORE POPULATING IT.
AD-09.14 open question 1 is OPEN. The concrete MagiHuman parameter set for
(a) working generation and (b) actor/voice consistency is OPERATOR KNOWLEDGE
THAT HAS NOT BEEN RECORDED ANYWHERE IN THIS REPOSITORY. WP-56 designs the
column to hold it and deliberately does NOT invent its contents: a plausible
guess written into a schema is indistinguishable from a recorded fact six
months later, and this is exactly the class of defect the fleet table in
CLAUDE.md §2 has been corrected for twice.

The column is therefore JSONB and OPAQUE, keyed by engine name, with no
server-side schema and nothing that reads it. Shape intended:

    {"latentsync": {...}, "magihuman": {...}}

The per-engine keys are what makes the AD-09.4.3 constraint enforceable later:
an actor's identity is only reproducible on the engine it was established
against, so changing the bound engine is an IDENTITY CHANGE. This migration
records that constraint in ``certified_model_id`` (the AD-01 model the identity
was established against) and the UI must say so rather than silently producing
a different-sounding presenter.

``voice_profile`` is separate from ``engine_bindings`` on purpose. AD-09.6.1
rules audio and video are always persisted as separate assets regardless of
which engine produced them; a joint audio+video engine would write into both
columns, a split pipeline into one each, and the downstream contract does not
change either way.

NOTHING IN THE PIPELINE READS THIS TABLE (WP-56 boundary condition).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

# AD-09.9: orientation is not a crop. A portrait presenter must be RENDERED
# portrait by the engine; scaling a landscape render into a portrait box gives
# pillarboxing or a bad crop. The value therefore belongs on the actor (and in
# the Stage-6 generation request), not only in the composition layer.
_ORIENTATIONS = ("landscape", "portrait")


def upgrade() -> None:
    vals = ", ".join(f"'{v}'" for v in _ORIENTATIONS)
    op.execute(f"""
DO $$ BEGIN
CREATE TYPE presenter_orientation AS ENUM ({vals});
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "actors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # "Whichever the bound engine requires" (AD-09.4.3) — both nullable,
        # and neither is required at creation because which one is needed is a
        # property of the engine, which may not be chosen yet.
        sa.Column("reference_clip_id", UUID(as_uuid=True),
                  sa.ForeignKey("library_assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("reference_image_id", UUID(as_uuid=True),
                  sa.ForeignKey("library_assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("voice_profile", postgresql.JSONB, nullable=True),
        # AD-09.14 open question 1 — AWAITING THE OPERATOR. See module docstring.
        sa.Column("engine_bindings", postgresql.JSONB, nullable=True),
        sa.Column("default_orientation",
                  postgresql.ENUM(*_ORIENTATIONS, name="presenter_orientation",
                                  create_type=False),
                  nullable=False, server_default="landscape"),
        # The AD-01 model this identity was established against. SET NULL
        # rather than RESTRICT: retiring a model must not block the actor row,
        # but losing the pin is itself information the UI has to surface.
        sa.Column("certified_model_id", UUID(as_uuid=True),
                  sa.ForeignKey("models.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("owner_scope",
                  postgresql.ENUM("global", "user", name="library_owner_scope",
                                  create_type=False),
                  nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # Operator-facing identity: two actors named "Sarah — corporate" in the
    # same scope is a mistake every time. Partial on is_active so a retired
    # actor's name can be reused.
    op.create_index(
        "uq_actors_name_scope", "actors", ["name", "owner_scope"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_actors_active", "actors", ["owner_scope", sa.text("name ASC")],
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("ix_actors_active", table_name="actors")
    op.drop_index("uq_actors_name_scope", table_name="actors")
    op.drop_table("actors")
    op.execute("DROP TYPE IF EXISTS presenter_orientation")
