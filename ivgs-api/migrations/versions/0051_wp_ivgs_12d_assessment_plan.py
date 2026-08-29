"""0051 — the assessment plan the model writes BEFORE it designs a scene

WP-IVGS-12d, closing RC-Q9c.

WHAT THE COLUMN HOLDS

    {outcome_id: {"evidence_kind": "practice"|"assess", "learner_does": str}}

The model's commitment to what would PROVE each outcome, made while the scene
list is still empty. Foundation §1 puts "determine acceptable evidence" at
stage 2, before "plan the learning experiences" at stage 3; until contract-4
that ordering existed only as a sentence in a prompt, and the model did not
follow it.

⛳ WHY IT IS NOW REAL AND NOT ADVISORY. `assessment_plan` is the FIRST property
of contract-4's JSON Schema, and schema declaration order was MEASURED to bind
generation order on the pinned engine — in both directions, against a prompt
explicitly ordering the model to emit `scenes` first (WP-IVGS-12d Task 1).
`properties` order controls; `required` order does not. So the plan is produced
before any scene token exists, and `PLAN_ENTRY_UNREALIZED` checks the finished
design against the promise.

⚠ AND `evidence_map` IS NOT TOUCHED BY THIS MIGRATION, deliberately. It keeps
its column and its type; what changed is who writes it. It used to be emitted by
the model and it is now DERIVED from the scenes by
`shared.design.evidence.derive_evidence_map`. **Existing rows keep the map the
model wrote**, which is honest: those briefs were produced under contract-3 and
their `contract_version` says so. Rewriting history to make old rows look like
new ones would destroy the only evidence that RC-Q9c happened.

ADDITIVE AND NON-DESTRUCTIVE. A new nullable=False column with a server default
of `'{}'::jsonb`, so every existing brief gets an empty plan and the gate reads
that as "nothing was promised" — which for a contract-3 brief is exactly true.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

TABLE = "storyboard_design_briefs"
COLUMN = "assessment_plan"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN, JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        f"COMMENT ON COLUMN {TABLE}.{COLUMN} IS "
        "'WP-IVGS-12d. {outcome_id: {evidence_kind, learner_does}} - what the "
        "model promised would PROVE each outcome, emitted BEFORE any scene "
        "because it is the first property of the contract-4 schema and "
        "declaration order binds generation order on the pinned engine. "
        "Empty on any brief written before contract-4, which is accurate.'"
    )


def downgrade() -> None:
    """Drops the column.

    ⚠ LOSSY, and it says so rather than pretending otherwise: the plans
    themselves are gone. They remain recoverable from `raw_contract`, which
    stores the model's emission verbatim and is the evidence limb precisely so
    that a derived column can be dropped without losing what was said.
    """
    op.drop_column(TABLE, COLUMN)
