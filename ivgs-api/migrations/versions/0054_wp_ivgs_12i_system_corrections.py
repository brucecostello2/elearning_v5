"""0054 — the design brief carries what CODE corrected, and what it could not

WP-IVGS-12i, RC-R4. The operator's ruling of 2026-08-30 splits a gate refusal
into MECHANICAL (a deterministic default fix exists) and JUDGMENT (a human must
decide), and says mechanical refusals are repaired by code before the gate —
**declared, never silently.**

This column is the "never silently" half, and it is the half that makes the rule
safe. A pass that flips a scene's medium and authors a template from its own
narration is doing real work on the artefact the reviewer is about to approve;
if the only trace of it were a log line on node-01, the gate would show a clean
storyboard and nobody at the gate could tell an authored scene from a designed
one.

⛔ IT ALSO CARRIES THE FAILURES, and that is not an afterthought. When authoring
refuses, the original refusal STANDS and the scene is put back — so the reviewer
sees a scene that is still refused, and is owed the fact that code tried and what
it was told. `storyboard_repair.Correction` writes a row either way.

WHY ON THE BRIEF AND NOT ON `projects` OR ON THE SCENE

One design per generation is the shape `storyboard_design_briefs` already has,
and a repair belongs to the generation it repaired. A regenerate supersedes the
brief (`is_active=false`) and the corrections go with it, which is exactly right:
the previous design's repairs describe scenes that no longer exist. A column on
`projects` would be overwritten by the next run and a reader could not tell which
design it described.

Nullable with no default, deliberately: **NULL means the pass never ran** (a
pre-12i brief, or a storyboard from before this package), and `{}`-shaped JSON
with `repaired: 0` means it ran and changed nothing. Those are different facts
and a `server_default` would have destroyed the distinction on every old row.

Revision ID: 0054
Revises: 0053
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "storyboard_design_briefs",
        sa.Column(
            "system_corrections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "WP-IVGS-12i RC-R4. One auto-repair pass, declared: "
                "{ran_at, scenes, refusals_before, refusals_after, "
                "mechanical_before, judgment_before, repaired, repair_refused, "
                "corrections:[{scene_index, refusal_code, refusal_reason, "
                "media_type_was, media_type_is, applied, template, params, "
                "original_visual_description, repair_error}]}. "
                "NULL means the pass never ran; a row with repaired=0 means it "
                "ran and found nothing mechanical."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("storyboard_design_briefs", "system_corrections")
