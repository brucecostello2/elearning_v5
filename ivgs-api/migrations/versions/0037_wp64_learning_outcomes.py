"""0037 — WP-64: the project carries the course's learning outcomes.

Revision ID: 0037
Revises: 0036

ONE NULLABLE TEXT COLUMN: ``projects.learning_outcomes``.

WHAT WAS MISSING, AND WHY A PROMPT COULD NOT FIX IT.

WP-64 Tasks 2 and 6(d) ask the storyboard model to choose each scene's medium
against what the viewer must be able to DO afterwards. It could not: the only
things the project hands Stage 2 are its name, a short dashboard description,
a target audience, a runtime budget and the transcript
(``ivgs-workers/tasks/stage2_storyboard.py:615-628``). "What should the viewer
be able to do at the end" was nowhere in the system, so no wording of the
prompt could make the model reason from it. This column is the input half of
that fix; the prompt is the other half and is useless without it.

FREE TEXT, DELIBERATELY, AND NULLABLE. One outcome or six, prose or a list, is
the operator's call — an outcome statement is a sentence, not an enum, and a
schema that forced structure onto it would be this package guessing at a
pedagogy it has not been given. NULL means the project was authored before this
column existed or its author had nothing to add; every project on the fleet
today is in that case and NOTHING IS BACKFILLED. Inventing outcomes for seven
existing projects would put this package's guesses in a field the storyboard
model then reasons from.

IT IS NOT RETROACTIVE, and the GUI says so in as many words. Scenes are rows
that were written by a completed run; editing this field changes the NEXT
storyboard generation and does not reach back into scenes already authored.

DOWNGRADE DROPS THE COLUMN and is exercised. Unlike the enum migrations either
side of it, a column can be removed cleanly: the data it holds is
operator-authored text that exists nowhere else, so a downgrade loses it, which
is what a downgrade of an additive column means.
"""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("learning_outcomes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "learning_outcomes")
