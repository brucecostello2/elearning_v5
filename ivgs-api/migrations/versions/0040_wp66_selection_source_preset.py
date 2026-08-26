"""0040 — WP-66: `selection_source.preset`, so provenance is a column.

Revision ID: 0040
Revises: 0039

ONE ENUM LABEL. `selection_source` gains `preset` alongside `auto` and `manual`.

WHY IT IS NEEDED. WP-66 Task 6 asked whether a preset's model selections really
reach `project_model_selections` or whether that is another declared-but-inert
path. **They reach it.** `app/services/preset_service.py:246` calls
`model_selection.manual_override` for every entry, and that call is real — the
panel's claim is true.

What it loses is WHICH of them it was. `manual_override` hardcodes
`selected_by=SelectionSource.MANUAL` (`model_selection.py:300`), so a selection
a preset wrote is indistinguishable, in the column that exists to say so, from
one an operator chose by hand. The only surviving trace is the free-text
rationale, which `preset_service.py:253` sets to ``preset 'name' vN``.

WP-66 Task 3 requires the UI to show WHERE a binding came from, because WP-60
Task 5 established that a surface presenting mixed provenance as one fact is
this codebase's recurring defect. Deriving that from a rationale prefix would be
string-sniffing a field an operator can freely edit. So the enum gains the value
it was always missing.

NOTHING SWITCHES ON THE VALUE AT DISPATCH, so adding it is safe:
`shared/providers/factory.py:113-165` reads the selection row, resolves the
model and passes `selected_by` through to the `ModelBinding` as a string. It
never compares it. A `preset` row dispatches exactly as a `manual` row does,
which is correct — the preset IS the operator's choice, made earlier.

EXISTING ROWS ARE NOT REWRITTEN. There are none (measured: `SELECT count(*) FROM
project_model_selections` = 0 fleet-wide, 2026-08-26), and had there been, a
migration cannot tell a preset-written row from a hand-written one any better
than the runtime can — that is the defect being fixed, not one to backfill over.

DOWNGRADE IS A DELIBERATE NO-OP. PostgreSQL cannot remove a value from an enum
in place; rebuilding the type would require destroying any row carrying the
label. Same treatment, and the same reason, as 0027, 0033, 0034 and 0038.
"""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the new value is
    # not USED in the same transaction. It is not: nothing here writes a row.
    op.execute("ALTER TYPE selection_source ADD VALUE IF NOT EXISTS 'preset'")


def downgrade() -> None:
    # See the module docstring. Left in place, unused.
    pass
