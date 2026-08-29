"""0045 — a scene records WHERE its written content lives, and WHY its medium

WP-IVGS-10 Task 2, executing the operator's ruling of 2026-08-28: *"the
storyboard's visual layer is authored as aesthetic staging, not content."*

WHAT THESE TWO COLUMNS ARE FOR, AND WHY THEY ARE COLUMNS

v7's RULE 1-EXTENDED says that content which is written text or numerals may
never be delegated to a diffusion medium. That rule has exactly two sanctioned
answers per scene, and BOTH have to be stated on the row or the rule is
unenforceable:

  * the scene is ``motion_graphics`` and carries ``generation_params`` — a
    template and its parameters, drawn in a real font by a renderer that cannot
    misspell them. That answer already has a column (0028) and needs nothing
    here.
  * the scene keeps a diffusion medium and DECLARES that the written content is
    carried by the narration, while the visual depicts the non-text situation.
    That is ``text_carried_by``.

⛔ IT IS A COLUMN AND NOT A PHRASE IN THE PROSE, and the reason is the whole
history of RULE 1 on this pipeline. Every previous attempt to state something
about a visual INSIDE the visual's own text has had to be recovered later by a
regular expression, and the checks that resulted are the ones this repository
has repeatedly measured being satisfied by accident: v4's RULE 1 examples were
all about text written ON a surface, so naming a number in prose read as
permitted, and five of thirteen descriptions did it. A declaration a machine
must infer is not a declaration. This one is a value or it is absent.

``media_rationale`` is v7 RULE 9: one line saying why THIS medium for THIS
scene. WP-64 made the media_type choice deliberate and WP-68 gave it a fourth
option; neither asked the model to say why, so a wrong choice and a right one
look identical on the row and a reviewer has nothing to read. It is deliberately
free text and deliberately NOT validated for content: a rationale is for a human
to weigh, and a machine that scored it would be answering the subjective
question this package is careful never to answer.

WHAT THIS MIGRATION DOES NOT DO

It does not backfill. Existing rows get NULL, which reads correctly as "this
storyboard was authored before v7 and declared nothing" rather than as a
declaration nobody made. WP-IVGS-10's Task 1 table is the record of what those
rows actually are, and inventing declarations for them would destroy the
evidence.

It adds no NOT NULL and no default. A scene created by any existing path keeps
working unchanged; the gate is what requires a declaration, and only for scenes
whose narration is written or numeric.

Revision ID: 0045
Revises: 0044
"""
import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

#: The only value `text_carried_by` may take. A one-value domain is deliberate:
#: this is a declaration that the written content is SPOKEN, not a free-text
#: field a future caller can fill with a sentence and satisfy a check. If a
#: second carrier is ever real -- burnt-in captions, say -- it is a migration
#: and a ruling, not a string somebody passes.
TEXT_CARRIERS = ("narration",)


def upgrade() -> None:
    op.add_column(
        "storyboard_scenes",
        sa.Column(
            "media_rationale",
            sa.Text(),
            nullable=True,
            comment=(
                "v7 RULE 9: one line saying why this media_type for this "
                "scene. Free text, read by humans at the storyboard gate."
            ),
        ),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column(
            "text_carried_by",
            sa.String(length=16),
            nullable=True,
            comment=(
                "v7 RULE 1-EXTENDED: when the narration's content is written "
                "or numeric and the scene keeps a diffusion medium, this "
                "declares that the written content is carried by the "
                "narration and the visual depicts the non-text situation. "
                "NULL means no declaration was made."
            ),
        ),
    )
    # A CHECK rather than an enum type. The domain has one value today and the
    # cost of being wrong about that later is an ALTER TABLE, not a
    # PostgreSQL enum that cannot have a value removed -- which is exactly the
    # trap 0027/0041/0042/0044 all had to write "downgrade is a no-op" about.
    op.create_check_constraint(
        "ck_storyboard_scenes_text_carried_by",
        "storyboard_scenes",
        "text_carried_by IS NULL OR text_carried_by IN ('narration')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_storyboard_scenes_text_carried_by",
        "storyboard_scenes",
        type_="check",
    )
    op.drop_column("storyboard_scenes", "text_carried_by")
    op.drop_column("storyboard_scenes", "media_rationale")
