"""
0021_add_quality_scores_review_notes — Add review_notes to asset_quality_scores

Resolves BUG-007: quality_service.py sets score.review_notes on approve/reject,
but the column does not exist in the AssetQualityScore model.
Investigation confirmed review_notes is a designed feature with request schema,
response schema, and service implementation — only the model column was missing.
Operator approved Option A (add column).

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add review_notes column to asset_quality_scores table.

    Text column, nullable=True.
    Stores reviewer notes when approving or rejecting quality scores.
    """
    op.add_column(
        "asset_quality_scores",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove review_notes column from asset_quality_scores table."""
    op.drop_column("asset_quality_scores", "review_notes")
