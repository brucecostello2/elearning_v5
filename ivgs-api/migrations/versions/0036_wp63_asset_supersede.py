"""0036 — WP-63: a regenerated asset supersedes the old one; the old one stays.

Revision ID: 0036
Revises: 0035

WHY THIS COLUMN EXISTS.

WP-63 Task 7 makes per-scene regeneration real. The moment it is real, a scene
can have two images: the one that was there and the one the operator asked for.
Something has to say which is current, and something has to keep the other.

`library_assets` has had `superseded_by` since WP-56, under the rule stated
there: *bytes are immutable; replacing a file is a supersede, not an update*.
The `assets` table — the project-scoped one every media task writes to — had no
such column, so a regenerated frame arrived beside its predecessor with nothing
distinguishing them but `created_at`. Every reader that wanted "the current
image for this scene" was left to sort by timestamp and hope, and the composition
manifest is one of those readers.

DELETION IS NOT THE ALTERNATIVE, and this is the WP-45 supersede pattern
verbatim. The superseded asset is retained:

  * a quality score row points at it (`asset_quality_scores.asset_id` is NOT
    NULL with ON DELETE CASCADE), and that score is the evidence for why the
    operator regenerated;
  * an already-locked composition manifest may reference it, and a manifest
    that names a row that no longer exists cannot be replayed;
  * "what did this look like before?" is a question an operator asks after a
    regeneration, not before it.

Retention (WP-58/WP-59) is what eventually removes it, under a policy, with an
audit trail — not a media task deciding on the spot.

BOTH COLUMNS ARE NULLABLE AND NOTHING IS BACKFILLED. A NULL `superseded_by`
means "current", which is true of every row that exists today. There is no
honest way to reconstruct which of the historical duplicates on this fleet
replaced which, and inventing an ordering now would be this package's guess
presented as the pipeline's record — the same defect WP-58 refused to commit
when it declined to backfill `failure_category`.

The FK is ON DELETE SET NULL: if the replacement is ever deleted, the row it
replaced becomes current again rather than pointing at nothing. That is also
the correct meaning.
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("superseded_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column(
            "superseded_at", sa.DateTime(timezone=True), nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_assets_superseded_by_assets",
        "assets",
        "assets",
        ["superseded_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Partial: the overwhelmingly common query is "the CURRENT asset for this
    # scene", which is a lookup for NULL. Indexing the non-NULLs as well would
    # be indexing the smaller and less-asked-for half.
    op.create_index(
        "ix_assets_scene_current",
        "assets",
        ["scene_id", "asset_type"],
        unique=False,
        postgresql_where=sa.text("superseded_by IS NULL AND scene_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_assets_scene_current", table_name="assets")
    op.drop_constraint("fk_assets_superseded_by_assets", "assets", type_="foreignkey")
    op.drop_column("assets", "superseded_at")
    op.drop_column("assets", "superseded_by")
