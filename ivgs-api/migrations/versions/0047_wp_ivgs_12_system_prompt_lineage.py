"""0047 — the SYSTEM half of a stage prompt gets a version lineage too

WP-IVGS-12, on an operator directive of 2026-08-29: *"v8 must not ship
half-versioned. Either bring the SYSTEM prompt under the WP-63 lineage alongside
the user template, or ... assert the j2's content hash into version_fingerprint.
Argue which from the code; do not leave the split as found."*

⛳ THE CODE SAYS "BRING IT UNDER THE LINEAGE", AND NO FROZEN EDIT IS NEEDED.

``stage2_storyboard._resolve_prompts`` (``:86-111``) resolves in this order:

    system_prompt = task_input.system_prompt          <-- FIRST
    if not system_prompt: system_prompt = _load_template("stage2_system.j2")
    api_sys, api_user = _resolve_prompts_from_api(...)
    if api_sys:  system_prompt = api_sys              <-- never fires
    if api_user: user_template = api_user             <-- ALWAYS fires

``_resolve_prompts_from_api`` returns ``(None, text)`` by construction and says
so in its own docstring (``:151-153``): a ``prompts`` row carries exactly one
text, so the API can only ever supply the USER half. That is the split.

But ``StoryboardGenerationInput.system_prompt`` (``models/task_result.py:366``)
is populated by ``pipeline_orchestrator_v2._build_stage_input`` - which is NOT
one of the eight frozen bodies, and which currently sets neither prompt field.
So the orchestrator can resolve a versioned SYSTEM prompt from the database and
hand it in, and the frozen body already honours it AHEAD of the file. The
mirror-image trick does not work for the user half, because the API fetch
overwrites ``task_input.user_prompt_template`` unconditionally - which is
exactly why the system slot is the one to use.

⛳ AND IT IS THE SLOT THE LEARNING OUTCOMES NEEDED (R1b / P2.66). The outcomes
are the design's governing constraint, so they belong in the role prompt, not
appended to a description. Rendering the system prompt in the orchestrator makes
``learning_outcomes`` a first-class Jinja variable for the first time, and
retires ``_description_with_outcomes``'s delimited block. See the report §3.

WHAT THIS MIGRATION DOES

Two new ``prompt_type`` members, named so each sorts beside the partner it
governs:

    transcript_refinement_system
    storyboard_generation_system

Nothing else. The rows themselves are published by
``app/scripts/wpivgs12_publish_design_prompts.py`` through the same
preserve-inactive / insert-active lineage ``wp63_publish_storyboard_prompt.py``
uses, so a system prompt is now rolled back by one UPDATE like any other.

⚠ THE FILE FALLBACK SURVIVES AND MUST. If no active row exists the frozen body
still loads its ``.j2``, which is the correct behaviour for a worker whose API
is briefly unreachable. That path is now RECORDED rather than invisible: the
orchestrator writes which prompt it actually resolved - row id and version, or
the file's SHA-256 - into the job context, and it reaches
``pipeline_checkpoints.version_fingerprint``, a column that has existed since
0002 and that NOTHING has ever populated (grep over ``ivgs-workers``: no hits).
So the operator's second option is not discarded; it is what makes the first
one auditable.

Revision ID: 0047
Revises: 0046
"""
import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

NEW_VALUES = ("transcript_refinement_system", "storyboard_generation_system")

#: The members as they stood at 0046, in declaration order. The downgrade
#: rebuilds the type from THIS list rather than from a live introspection,
#: because a downgrade that reads the current type would happily preserve a
#: member some later migration added and call it a rollback.
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
)


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the value is not
    # USED in the same transaction. It is not: nothing here writes a row.
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE prompt_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """A REAL downgrade, unlike 0041's documented no-op.

    Postgres cannot drop a value from an enum, so the type is rebuilt: rows
    carrying a removed value are deleted FIRST and loudly, because leaving them
    would make the ``USING`` cast fail with a message that names neither the row
    nor the reason.

    Deleting a prompt row is safe in a way that deleting most rows is not: the
    stage falls back to its ``.j2`` file when no active row exists, so the
    system degrades to exactly the behaviour that preceded 0047.
    """
    bind = op.get_bind()
    removed = ", ".join(f"'{v}'" for v in NEW_VALUES)

    doomed = bind.execute(
        sa.text(f"SELECT count(*) FROM prompts WHERE prompt_type::text IN ({removed})")
    ).scalar_one()
    if doomed:
        op.execute(f"DELETE FROM prompts WHERE prompt_type::text IN ({removed})")

    members = ", ".join(f"'{v}'" for v in VALUES_BEFORE)
    op.execute(f"CREATE TYPE prompt_type_0046 AS ENUM ({members})")
    op.execute(
        "ALTER TABLE prompts ALTER COLUMN prompt_type TYPE prompt_type_0046 "
        "USING prompt_type::text::prompt_type_0046"
    )
    op.execute("DROP TYPE prompt_type")
    op.execute("ALTER TYPE prompt_type_0046 RENAME TO prompt_type")
