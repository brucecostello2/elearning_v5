"""0041 — WP-68: `media_type.motion_graphics`.

Revision ID: 0041
Revises: 0040

ONE ENUM LABEL, and NO new column. The structured template parameters the
renderer needs — `{"template": "place_value_split", "number": 23}` — go in
`storyboard_scenes.generation_params`, a JSONB column that has existed since the
table was created. The brief asked where that structure could live "without a
schema fight"; the answer is that it already has somewhere.

WHY A FOURTH MEDIA TYPE AND NOT AN ANIMATION SUBTYPE. The two are told apart by
what they NEED, not by how they look: `animation_generation`'s existing family
(Wan2.2-Animate) requires a person in a reference still and a driving clip,
while a motion graphic requires structured scene data and no image at all
(WP-67's capability contracts state both). A subtype would have put two
incompatible input contracts behind one value that the orchestrator routes by,
and the routing is what decides which worker gets the scene.

WHAT THIS LABEL DOES **NOT** DO, and this is the point of the comment.

It does not make a motion-graphics scene renderable. No renderer is deployed on
this fleet, `animation_generation_task` is frozen under AD-05 §8 and would run
Wan's client against such a scene, and the Media Type dropdown deliberately does
NOT offer this value (WP-64 removed a dropdown option advertising a pathway that
did not exist; adding one back would be the same defect). What the label does is
let the storyboard prompt CHOOSE motion graphics and record the choice as
structured data, and let the orchestrator recognise that choice and hold it
visibly instead of silently turning it into an image — which is what an
unrecognised value does today (`pipeline_orchestrator_v2.py:620-621`).

DOWNGRADE IS A DELIBERATE NO-OP. PostgreSQL cannot remove a value from an enum
in place; rebuilding the type would require destroying any row carrying the
label. Same treatment, and the same reason, as 0027, 0033, 0034, 0038 and 0040.
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction provided the new value is
    # not USED in the same transaction. It is not: nothing here writes a row.
    op.execute("ALTER TYPE media_type ADD VALUE IF NOT EXISTS 'motion_graphics'")


def downgrade() -> None:
    # See the module docstring. Left in place, unused.
    pass
