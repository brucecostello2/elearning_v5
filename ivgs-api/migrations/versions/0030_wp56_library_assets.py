"""
0030_wp56_library_assets — AD-09.4: the ``library_assets`` table and the
reference from project assets to their library origin.

Revision ID: 0030
Revises: 0029

WHY A NEW TABLE AND NOT ``assets.project_id NULL`` (AD-09.4.1, and this was
re-checked against the live schema before writing the migration, not taken on
the addendum's word):

  * ``assets.project_id`` is ``NOT NULL`` with ``ON DELETE CASCADE`` to
    ``projects.id`` — verified in ``\\d assets`` on node-01. Relaxing it would
    put library assets inside a cascade path, so deleting the FIRST project
    that happened to use a shared logo would take the logo with it.
  * ``storage_quotas`` and ``retention_policies`` key on project ownership.
    A nullable ``project_id`` puts library assets into per-project quota
    accounting, where by definition they do not belong — a library asset is
    charged to whoever uploaded it, forever, and freed when nobody deletes it.

Both of those are silent-wrong-answer failures rather than errors, which is why
the addendum rules a separate table and why this migration does not "simplify"
it back.

REFERENCE, DON'T COPY. ``assets.library_asset_id`` is the whole mechanism:
a project consuming a library asset records the origin instead of duplicating
the binary. ``ON DELETE SET NULL``, not CASCADE — the direction of ownership
runs the other way and a library retirement must not delete project work.

NEVER HARD-DELETED WHILE REFERENCED. ``superseded_by`` is a self-FK: replacing
a logo points the old row at the new one and leaves every historical project
resolvable. There is no delete path in this migration by design.

NOTHING IN THE PIPELINE READS THIS TABLE. WP-56 is a deliberate partial
pull-forward of AD-09 ahead of the Temporal cutover, and its boundary condition
is that no pre-cutover code path reads the new tables. Checked after writing:
``grep -rn library_asset ivgs-workers/`` is empty.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_ENUMS: dict[str, tuple[str, ...]] = {
    # AD-09.4.2. `document` and `font` are carried because the addendum lists
    # them; `font` has no render path yet (AD-09.14 open question 6, font
    # provisioning to the compositor node) and the library is where the file
    # will live when it does.
    "library_asset_kind": (
        "logo", "video_clip", "audio_clip", "music_bed",
        "reference_clip", "reference_image", "font", "document",
    ),
    # `global` is admin-mutable only; `user` is the default for upload-on-use.
    "library_owner_scope": ("global", "user"),
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

    op.create_table(
        "library_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("kind", _enum("library_asset_kind"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # Storage columns mirror `assets` exactly: same SeaweedFS path, same
        # upload route, different ownership. Divergence here would mean two
        # download paths and eventually two bugs.
        sa.Column("seaweedfs_fid", sa.String(255), nullable=True),
        sa.Column("seaweedfs_path", sa.String(1024), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("owner_scope", _enum("library_owner_scope"), nullable=False,
                  server_default="user"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("superseded_by", UUID(as_uuid=True),
                  sa.ForeignKey("library_assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # The library browser's only two filters, and the ordering it lists in.
    op.create_index(
        "ix_library_assets_kind_scope", "library_assets",
        ["kind", "owner_scope"],
    )
    # Partial: a superseded asset is history, and the browser never lists it.
    op.create_index(
        "ix_library_assets_current", "library_assets",
        ["kind", sa.text("created_at DESC")],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    # Upload-on-use dedup (AD-09.4.2's answer to ledger B3, duplicate-asset
    # accumulation): the same bytes uploaded twice into the same scope resolve
    # to the existing row instead of a second copy. Partial on NOT NULL so rows
    # predating a hash, and rows whose hash could not be computed, do not
    # collide with each other.
    op.create_index(
        "uq_library_assets_hash_scope", "library_assets",
        ["content_hash", "owner_scope"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL AND superseded_by IS NULL"),
    )

    # Reference-don't-copy. SET NULL: retiring a library asset must not delete
    # the project asset that was derived from it.
    op.add_column(
        "assets",
        sa.Column("library_asset_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_assets_library_asset_id_library_assets",
        "assets", "library_assets",
        ["library_asset_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_assets_library_asset_id", "assets", ["library_asset_id"],
        postgresql_where=sa.text("library_asset_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_assets_library_asset_id", table_name="assets")
    op.drop_constraint(
        "fk_assets_library_asset_id_library_assets", "assets", type_="foreignkey",
    )
    op.drop_column("assets", "library_asset_id")
    op.drop_index("uq_library_assets_hash_scope", table_name="library_assets")
    op.drop_index("ix_library_assets_current", table_name="library_assets")
    op.drop_index("ix_library_assets_kind_scope", table_name="library_assets")
    op.drop_table("library_assets")
    for name in _ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
