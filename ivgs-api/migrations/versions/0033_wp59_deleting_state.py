"""0033 — WP-59: the DELETING project state, and a backup_type for the physical base.

Revision ID: 0033
Revises: 0032

TWO ENUM ADDITIONS, FOR TWO PACKAGE TASKS.

``project_state.DELETING`` (Task 2). Multi-store deletion spans Postgres,
SeaweedFS and Redis and therefore cannot be atomic. The ORDER is what makes a
crash survivable: the project is marked DELETING and COMMITTED before the first
row is destroyed, so a process that dies half way leaves a project that is
visibly mid-delete rather than one that looks alive with missing organs.

DELETING IS TERMINAL BY CONSTRUCTION. It is deliberately absent from every
value list in ``PROJECT_STATE_TRANSITIONS`` — nothing transitions INTO it via
``transition_state`` (the deletion service writes it directly) and nothing
transitions OUT of it at all. ``trigger_pipeline`` accepts only DRAFT and
USER_REVIEW, so a DELETING project cannot start a pipeline; the deletion
service additionally refuses to begin while any job is non-terminal, which is
the case ``trigger_pipeline``'s own state gate cannot cover.

``backup_type.physical_base_backup`` (Task 8). ``pg_basebackup`` produces a
PHYSICAL base — a byte-level copy of the data directory — which is a different
artefact from the ``full_database`` logical ``pg_dump`` this system has always
taken. They are not interchangeable and must not share a row type: the WAL
archive can be replayed onto the first and cannot be replayed onto the second,
which is exactly the distinction WP-57 Task 6 found and D-2 rules on. Reusing
``full_database`` would have made the recovery promise unreadable from the
table.

DOWNGRADE IS A NO-OP AND THAT IS DELIBERATE. PostgreSQL cannot remove a value
from an enum in place; the alternative is to rebuild the type, which requires
rewriting every column that uses it and would fail outright on any row already
carrying the new value. A downgrade that destroys data to restore a type
definition is worse than a downgrade that leaves one unused label behind. Same
reasoning as 0027.
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the new value is
    # not USED in the same transaction. Neither is: the deletion service and
    # the base-backup job both write these labels in later, separate sessions.
    op.execute("ALTER TYPE project_state ADD VALUE IF NOT EXISTS 'DELETING'")
    op.execute(
        "ALTER TYPE backup_type ADD VALUE IF NOT EXISTS 'physical_base_backup'"
    )


def downgrade() -> None:
    # See the module docstring. Removing an enum value in PostgreSQL means
    # rebuilding the type; rows already carrying the value would have to be
    # destroyed to do it. Left in place, unused.
    pass
