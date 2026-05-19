"""Add target_audience to projects table

Revision ID: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"

def upgrade():
    op.add_column("projects", sa.Column("target_audience", sa.String(500), nullable=True))

def downgrade():
    op.drop_column("projects", "target_audience")
