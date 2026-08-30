"""0052 — a designed scene reaches the table, and it must say why it exists

WP-IVGS-12f, closing the storage half of RC-Q9e.

WHY THIS COLUMN DID NOT EXIST UNTIL NOW

`scene_origin` has accepted `'designed'` since migration 0048, and until this
package **not one row ever carried it**: 83 scenes across six generations were
`sourced` without exception (RC-Q9e). `design_core.contract.parse_contract` has
parsed a `designed_rationale` off the contract's provenance branch the whole
time and `DesignBriefService.SCENE_DESIGN_FIELDS` has never written it, because
there was nothing to write and no column to write it to.

Contract-5 makes designed scenes MANDATORY — one invented unaided assessment per
learning outcome, pinned by the grammar — so the column is now load-bearing.

⛳ AND IT IS THE EVIDENCE LIMB, NOT DECORATION. The whole complaint this package
lineage answers is silent invention: material that is not in the script,
appearing in the lesson, with nothing saying where it came from. A row that says
`scene_origin = 'designed'` and cannot say WHY is that defect one layer down —
the reviewer at the gate sees an invented scene and has no account of it.
`_arc_row` renders this beside the origin so the two are read together.

ADDITIVE, NULLABLE, AND NON-DESTRUCTIVE. Every existing row gets NULL, which is
accurate: none of them was designed. No CHECK constraint is touched —
`ck_storyboard_scenes_source_xor_designed` governs `source_refs` against
`scene_origin` and this column is not in it.
"""
from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

TABLE = "storyboard_scenes"
COLUMN = "designed_rationale"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True))
    op.execute(
        f"COMMENT ON COLUMN {TABLE}.{COLUMN} IS "
        "'WP-IVGS-12f. Why an invented scene exists: what the outcome required "
        "that the uploaded script did not contain. NULL on every sourced scene, "
        "and NULL on every row written before contract-5, which is accurate - "
        "no scene was designed before it. Set from the contract''s designed "
        "provenance branch by DesignBriefService.apply_scene_design.'"
    )


def downgrade() -> None:
    """Drops the column.

    ⚠ LOSSY AND IT SAYS SO. The rationales themselves go. They stay recoverable
    from `storyboard_design_briefs.raw_contract`, which stores the model's
    emission verbatim precisely so a derived column can be dropped without
    losing what was said — the same argument 0051 makes for `assessment_plan`.
    """
    op.drop_column(TABLE, COLUMN)
