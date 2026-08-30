"""0053 — the assessment-authoring prompt gets its OWN lineage

WP-IVGS-12h, TASK 4. design-contract-7 splits the design across two engine
calls, and the second one — which authors every outcome's independent attempt
from the plan and a code-built practice summary, and never sees the practice
wording — needs a SYSTEM prompt of its own.

⛔ ITS OWN LINEAGE NAME AND NOT A SECOND VERSION OF `storyboard_generation_system`.
The two prompts are asked different questions, will move at different rates, and
must be rollable back independently: a bad v9 of the design prompt must not force
a rollback of the assessment prompt that was fine, and the reverse. WP-IVGS-12's
own Task 3 argument — *"a prompt that is not versioned is a prompt nobody can
roll back"* — applies to the identity of the lineage as much as to the row.

    assessment_authoring_system

Nothing else changes. The row itself is published by
`app/scripts/wpivgs12_publish_design_prompts.py`, through the same
preserve-inactive / insert-active path the other two use, so a rollback is one
UPDATE.

⛔ AND THE ENUM MEMBER MUST BE ADDED TO `shared/models/enums.py` IN THE SAME
COMMIT. Migration 0047 added two members here and WP-IVGS-12 did not add them
there; the INSERT succeeded, the rows were published, and the next SELECT that
touched one raised `LookupError: 'storyboard_generation_system' is not among the
defined enum values`. WP-IVGS-12b found it a package later. The list is
load-bearing ON READ, and `PromptType.ASSESSMENT_AUTHORING_SYSTEM` is added
alongside this file.

⚠ THERE IS NO OTHER STORAGE SURFACE IN CONTRACT-7. The second call's output is
`assessment_scenes` — full scene objects, of exactly the shape contract-6 already
stored, merged into the same sequence by the same function and written to the
same columns. 0048's provenance XOR and 0052's `designed_rationale` carry them
unchanged. This migration exists for the prompt lineage and for nothing else,
which is proved by a round trip rather than asserted.

Revision ID: 0053
Revises: 0052
"""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

NEW_VALUES = ("assessment_authoring_system",)

#: The members as they stood at 0052, in declaration order. ⛔ Rebuilt from THIS
#: list on downgrade and never from a live introspection — a downgrade that reads
#: the current type would happily preserve a member some later migration added
#: and call it a rollback. The discipline is 0047's and the list is 0047's plus
#: the two members 0047 itself added.
VALUES_BEFORE = (
    "master",
    "transcript_refinement",
    "storyboard_generation",
    "image_generation",
    "video_generation",
    "animation_generation",
    "tts_voice",
    "talking_head",
    "composition",
    "translation",
    "scene_media_adaptation",
    "transcript_refinement_system",
    "storyboard_generation_system",
)


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the value is not
    # USED in the same transaction. It is not: nothing here writes a row.
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE prompt_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """A REAL downgrade, on 0047's pattern.

    Postgres cannot drop a value from an enum, so the type is rebuilt: rows
    carrying a removed value are deleted FIRST and loudly, because leaving them
    would make the ``USING`` cast fail with a message that names neither the row
    nor the reason.

    ⚠ AND DELETING THIS PARTICULAR ROW IS NOT THE BENIGN THING 0047's DELETE IS.
    0047 could say "the stage falls back to its .j2 file", and that is true of
    the design prompt. There is NO file fallback for the assessment prompt and
    that is deliberate (`design_core.assessment_call._fetch_prompt` refuses
    rather than reaching for a baked-in default, so the package's central claim
    cannot be made by an unversioned string). So a downgrade past 0053 makes
    every design-contract-7 storyboard FAIL, loudly, at call 2 — which is the
    correct behaviour for a database that no longer holds the prompt the running
    code requires, and is stated here so nobody meets it as a surprise.
    """
    bind = op.get_bind()
    removed = ", ".join(f"'{v}'" for v in NEW_VALUES)

    doomed = bind.execute(
        sa.text(f"SELECT count(*) FROM prompts WHERE prompt_type::text IN ({removed})")
    ).scalar_one()
    if doomed:
        op.execute(f"DELETE FROM prompts WHERE prompt_type::text IN ({removed})")

    members = ", ".join(f"'{v}'" for v in VALUES_BEFORE)
    op.execute(f"CREATE TYPE prompt_type_0052 AS ENUM ({members})")
    op.execute(
        "ALTER TABLE prompts ALTER COLUMN prompt_type TYPE prompt_type_0052 "
        "USING prompt_type::text::prompt_type_0052"
    )
    op.execute("DROP TYPE prompt_type")
    op.execute("ALTER TYPE prompt_type_0052 RENAME TO prompt_type")
