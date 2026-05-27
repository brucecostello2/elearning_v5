"""
0020_add_backup_records_error_message — Add error_message to backup_records

Resolves BUG-006: backup.py references error_message in multiple UPDATE
statements, but the column does not exist in the model or DB.
Operator approved Option A (add column).

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
    """Add error_message column to backup_records table.

    Text column, nullable=True.
    Stores error details when backup operations fail.
    """
    op.add_column(
        "backup_records",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove error_message column from backup_records table."""
    op.drop_column("backup_records", "error_message")
