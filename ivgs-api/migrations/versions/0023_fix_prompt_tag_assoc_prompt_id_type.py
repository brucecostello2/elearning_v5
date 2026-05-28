"""
0023_fix_prompt_tag_assoc_prompt_id_type — Ensure prompt_id is UUID

Defensive type-convergence migration for prompt_tag_associations.prompt_id.

Origin migration 0001 defines this column as UUID, and the live ivgs
database already has it as uuid (verified at reconciliation time). The
sandbox baseline (derived from v5.1.0) had it as String(36); origin
later corrected it to UUID. This migration ensures the column is uuid
in ANY environment:
  - already uuid (live DB, fresh DB from origin 0001): no-op
  - varchar(36) (legacy/v5.1.0-derived DB): convert to uuid

The conversion is safe: prompt_id is a FK to prompts.id (which is uuid),
so all stored values are valid UUIDs and cast cleanly. The IF guard
makes the migration a deliberate no-op where conversion is unneeded —
this is intentional, not dead code.

Revision ID: 0023
Revises: 0022
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Ensure prompt_tag_associations.prompt_id is uuid (no-op if already uuid)."""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prompt_tag_associations'
                  AND column_name = 'prompt_id'
                  AND data_type <> 'uuid'
            ) THEN
                ALTER TABLE prompt_tag_associations
                ALTER COLUMN prompt_id TYPE uuid USING prompt_id::uuid;
            END IF;
        END$$;
    """)


def downgrade() -> None:
    """No-op. Reverting uuid->varchar is intentionally not supported.

    The column is uuid in the canonical schema (origin migration 0001).
    Downgrading the type would diverge from the canonical definition and
    risks data-format issues, so this downgrade deliberately does nothing.
    """
    pass
