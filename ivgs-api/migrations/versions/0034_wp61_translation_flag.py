"""0034 — WP-61: the `flagged` variant state, and somewhere to put a translation.

Revision ID: 0034
Revises: 0033

TRANSLATION HAS NEVER RUN. Every one of the 16 rows in ``language_variants`` is
``pending`` (measured 2026-08-26), so there is no baseline to contaminate and no
stored translation anywhere in this schema — ``language_variants`` carries a
language code, a state and two render-asset ids, and nothing else.

THREE ADDITIONS, ONE RULING.

``language_variant_state.flagged`` (Task 3(c), FAIL-AND-FLAG). Measured
2026-08-25 against the live translation prompt: Qwen appended a correction in
ALL FOUR target languages, because scene 5 of the reference project's narration
contains a real arithmetic error (it teaches 10x3=30, 10x2=20 => "320" and then
says it was written as 230). A translator that silently corrects the source
produces a divergence that exists only in languages the team cannot read. The
ruled contract is: translate faithfully, never correct, and emit a
machine-readable marker line instead. The consuming path strips the marker from
the deliverable and puts the variant HERE rather than at ``complete``.

``flagged`` IS NOT ``failed``. A flagged translation is a usable deliverable
that a human must look at; a failed one is an absence. Collapsing them would
either hide a real deliverable behind an error badge or hide a real doubt
behind a green one, and this series of packages exists to stop exactly that.

``language_variants.translation`` (JSONB). The deliverable, per scene, with the
provenance of the run that produced it. NULL means "never translated", which is
the state all 16 rows are in.

``language_variants.translation_flags`` (JSONB). The markers, captured
verbatim, WITH the scene they came from. A separate column rather than a key
inside ``translation`` so that "which variants did the model doubt?" is one
indexable predicate and cannot be answered by digging through a blob.

DOWNGRADE. The two columns drop cleanly. The enum label does NOT: PostgreSQL
cannot remove a value from an enum in place, and rebuilding the type would mean
destroying every row already carrying it. Left behind, unused. Same treatment
as 0027 and 0033, and stated here rather than left for the next reader to
discover from a failed downgrade.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the value is not
    # USED in the same transaction. It is not: the translation service writes
    # it in a later, separate session.
    op.execute(
        "ALTER TYPE language_variant_state ADD VALUE IF NOT EXISTS 'flagged'"
    )
    op.add_column(
        "language_variants",
        sa.Column(
            "translation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "WP-61. The produced translation and the provenance of the run "
                "that produced it. NULL = never translated. The text here is "
                "the DELIVERABLE: any IVGS-TRANSLATION-FLAG marker the model "
                "emitted has already been stripped out of it."
            ),
        ),
    )
    op.add_column(
        "language_variants",
        sa.Column(
            "translation_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "WP-61. Markers the translator emitted, verbatim, with the "
                "scene each came from. Non-empty implies state='flagged'."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("language_variants", "translation_flags")
    op.drop_column("language_variants", "translation")
    # The enum label stays. See the module docstring: removing it means
    # rebuilding the type and destroying any row that carries it.
