"""
0020_add_reference_clip_asset_type — Add 'reference_clip' to asset_type enum

Enables Stage 6 (talking_head_render). The orchestrator _fetch_reference_clip_id
queries assets with asset_type=reference_clip (pipeline_orchestrator_v2.py:1231);
the asset_type enum lacked that value, so the query 500'd -> None -> task skip.

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG 12+ permits ADD VALUE inside a transaction if the new value is not used
    # in the same transaction (we only add it here). PG server is 17.2.
    op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'reference_clip'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value without recreating the type;
    # intentionally irreversible.
    pass
