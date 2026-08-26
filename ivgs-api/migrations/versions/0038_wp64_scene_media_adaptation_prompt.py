"""0038 — WP-64: a prompt_type for the editor's medium adaptation.

Revision ID: 0038
Revises: 0037

ONE ENUM LABEL: ``prompt_type.scene_media_adaptation``.

WHY IT IS IN ``prompts`` AND NOT SOMEWHERE ELSE.

WP-64 Task 3 gives the Edit Scene modal an explicit "Adapt description for
video / animation / image" action. It sends the scene's narration, its current
description and the target medium to the STORYBOARD binding (Llama; the model
does not move — `docs/reference-run-2026-08-23-correctness-annotation.md` §2
holds storyboard and transcript there until M3.3) and returns the rewrite to
the operator to read, edit and save.

The text it renders is a prompt: it is authored, it will be wrong the first
time, it will be amended, and when a rewrite reads badly the first question is
"under which version?". That is precisely what the `prompts` table answers —
one active row per type, previous versions preserved inactive, a change note on
the row, and a rollback that is one UPDATE of `is_active`. Storing this prompt
anywhere else would mean a second publish path, a second history, and a second
place to look.

IT IS NOT A PIPELINE STAGE, and nothing here pretends otherwise. No orchestrator
names it, `STAGE_TASK_MAP` does not resolve it, and it registers no Celery task.
`PromptType` now holds ten stage prompts and one editor prompt, and its
docstring says so.

DOWNGRADE IS A DELIBERATE NO-OP. PostgreSQL cannot remove a value from an enum
in place; the alternative is rebuilding the type, which would require destroying
any row already carrying the label. Same treatment as 0027, 0033 and 0034, and
the same reason.
"""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the new value is
    # not USED in the same transaction. It is not: the publisher script writes
    # the row in a later, separate session.
    op.execute(
        "ALTER TYPE prompt_type ADD VALUE IF NOT EXISTS 'scene_media_adaptation'"
    )


def downgrade() -> None:
    # See the module docstring. Left in place, unused.
    pass
