"""
0020_add_prompt_tags_description — Add/converge description on prompt_tags
Resolves Phase 0a schema audit: column defined in ORM model
(prompt_tag.py:62) as String(256) but missing from migration 0001.

Defensive convergence migration. The live ivgs database has this column
as VARCHAR(500) (added out-of-band, not via any committed migration),
while the ORM contract and all code expect VARCHAR(256). This migration
converges all environments to VARCHAR(256):
  - column absent (fresh DB): create as VARCHAR(256)
  - column present, wider (live DB drift at 500): narrow to VARCHAR(256)
  - column already VARCHAR(256): no-op
The ALTER ... TYPE fails safely (rolls back) if any row exceeds 256 chars;
verified 0 such rows in live DB at reconciliation time.

NOTE ON DOWNGRADE: downgrade drops the column. On databases where the
column pre-existed as drift (e.g. live ivgs), downgrade removes it
entirely rather than restoring the prior width. Restore from backup if
a downgrade is ever required on such a database.

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Converge prompt_tags.description to VARCHAR(256) to match ORM contract."""
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prompt_tags' AND column_name = 'description'
            ) THEN
                ALTER TABLE prompt_tags ADD COLUMN description VARCHAR(256);
            ELSE
                ALTER TABLE prompt_tags ALTER COLUMN description TYPE VARCHAR(256);
            END IF;
        END$$;
    """)


def downgrade() -> None:
    """Remove description column from prompt_tags. See module docstring re: drift."""
    op.execute("ALTER TABLE prompt_tags DROP COLUMN IF EXISTS description")
