"""0039 — WP-65: model_weight_placements, the record that bytes reached a node.

Revision ID: 0039
Revises: 0038

ONE NEW TABLE and ONE NEW ENUM TYPE. Nothing existing is altered, so this
migration adds no risk to any live row.

WHY A TABLE AND NOT COLUMNS ON ``model_node_availability``
----------------------------------------------------------
``model_node_availability`` is owned by a poller that runs every 30 seconds
(``ivgs-workers/celery_app.py:380``) and whose reconcile flips every AVAILABLE
row not present in the current GPU-scheduler fleet snapshot to UNAVAILABLE
(``ivgs-workers/tasks/periodic_tasks.py:996-1000``). The poller derives its
snapshot from a Redis LRU of models a JOB once loaded, and knows nothing about
bytes; a fetch result stored in that table would be reverted within half a
minute of being written. The two also disagree about what a node is —
availability keys on the scheduler's ``node-04:gpu0``, weights live on
``node-03``'s filesystem. See ``ModelWeightPlacement``'s docstring for the
measurements behind both statements.

DOWNGRADE IS EXERCISED AND COMPLETE. Unlike the enum-label migrations either
side of it (0027, 0033, 0034, 0038, whose downgrades are deliberate no-ops
because PostgreSQL cannot remove an enum value in place), this one creates a
NEW type and a NEW table and can therefore drop both cleanly: no pre-existing
row carries the type, so nothing is destroyed by removing it. ``downgrade()``
drops the table first and the type second — the reverse of creation order, and
required, because the type cannot be dropped while a column still uses it.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_STATUS_VALUES = ("fetching", "verified", "failed", "removed")


def upgrade() -> None:
    vals = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
    op.execute(f"""
DO $$ BEGIN
CREATE TYPE weight_placement_status AS ENUM ({vals});
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
""")

    op.create_table(
        "model_weight_placements",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "model_id", UUID(as_uuid=True),
            sa.ForeignKey("models.id", ondelete="CASCADE"), nullable=False,
        ),
        # The fleet node name (node-03), not the scheduler's node-03:gpu0.
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(*_STATUS_VALUES, name="weight_placement_status",
                            create_type=False),
            nullable=False, server_default="fetching",
        ),
        sa.Column("dest_dir", sa.String(512), nullable=True),
        sa.Column("engine_container", sa.String(128), nullable=True),
        # The digest actually fetched — NOT models.weights_checksum, which for
        # an engine-only certification holds the engine image digest (five live
        # rows share one value for that reason).
        sa.Column("bundle_digest", sa.String(128), nullable=True),
        sa.Column("file_count", sa.BigInteger, nullable=True),
        sa.Column("bytes_on_disk", sa.BigInteger, nullable=True),
        sa.Column("checksum_verified", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("signature_verified", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("last_error_reason", sa.String(64), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("model_id", "node_id",
                            name="uq_placement_model_node"),
    )
    op.create_index("ix_placement_node", "model_weight_placements", ["node_id"])
    op.create_index("ix_placement_status", "model_weight_placements", ["status"])


def downgrade() -> None:
    op.drop_index("ix_placement_status", table_name="model_weight_placements")
    op.drop_index("ix_placement_node", table_name="model_weight_placements")
    op.drop_table("model_weight_placements")
    # Safe: the type was created by this migration and no other column uses it.
    op.execute("DROP TYPE IF EXISTS weight_placement_status")
