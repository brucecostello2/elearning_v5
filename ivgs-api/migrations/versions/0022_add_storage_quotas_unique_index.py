"""add storage_quotas unique index

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-27

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add unique index on storage_quotas (entity_type, entity_id).

    This index enforces one quota per entity and supports the
    ON CONFLICT clause in the storage quota PUT endpoint.

    Formalizes manually-added index from sandbox testing.
    """
    op.create_index(
        'uq_storage_quotas_entity',
        'storage_quotas',
        ['entity_type', 'entity_id'],
        unique=True,
    )


def downgrade() -> None:
    """Remove unique index from storage_quotas."""
    op.drop_index('uq_storage_quotas_entity', table_name='storage_quotas')
