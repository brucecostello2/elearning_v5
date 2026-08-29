"""0050 — the XOR must treat jsonb 'null' as absent, like SQL NULL

WP-IVGS-12b. The SECOND defect in this one constraint, and a different one from
the first.

0048's first draft ACCEPTED the row it exists to refuse, because
`FALSE OR FALSE OR NULL` is NULL and a CHECK passes on NULL. Fixed before it
shipped.

This is the mirror: the constraint REFUSES a row it should accept. SQLAlchemy's
JSON/JSONB default is `none_as_null=False`, so a Python `None` is written as the
JSON value `null` rather than as SQL NULL. `source_refs IS NULL` is FALSE for
jsonb 'null', so a scene that is legitimately `designed` with no refs could not
satisfy the `designed` branch and PostgreSQL refused it — with a DETAIL line
printing `null` for the column, which reads as perfectly legal.

MEASURED on the 12b acceptance run: every regeneration's design-brief ingest
returned HTTP 500 on

    new row for relation "storyboard_scenes" violates check constraint
    "ck_storyboard_scenes_source_xor_designed"

for a row reading `..., null, designed, null, null)`. Reproduced directly: SQL
NULL accepted, `'null'::jsonb` refused, same row otherwise.

⛳ WHY BOTH HALVES ARE FIXED AND NOT JUST ONE. The ORM now sets
`none_as_null=True` on the four design JSONB columns, so the writer produces one
representation. This migration makes the CONSTRAINT agree, because rows written
before that change may already carry jsonb 'null', and a constraint that
distinguishes two spellings of "nothing" is a trap for the next writer whoever
it is. The invariant is "no usable refs", not "one particular spelling of empty".

Revision ID: 0050
Revises: 0049
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

CK = "ck_storyboard_scenes_source_xor_designed"

#: "This column carries no usable source refs." True for SQL NULL, for jsonb
#: 'null', and for an empty array — three spellings, one meaning.
_ABSENT = (
    "(source_refs IS NULL "
    " OR jsonb_typeof(source_refs) = 'null' "
    " OR (jsonb_typeof(source_refs) = 'array' "
    "     AND jsonb_array_length(source_refs) = 0))"
)

#: And its complement, spelled out rather than negated, so the NULL-propagation
#: trap that broke 0048's first draft cannot come back through the back door.
_PRESENT = (
    "(source_refs IS NOT NULL "
    " AND jsonb_typeof(source_refs) = 'array' "
    " AND jsonb_array_length(source_refs) > 0)"
)

_NEW = (
    f"scene_origin IS NULL "
    f"OR (scene_origin = 'designed' AND {_ABSENT}) "
    f"OR (scene_origin = 'sourced' AND {_PRESENT})"
)

_OLD = (
    "scene_origin IS NULL "
    "OR (scene_origin = 'designed' AND source_refs IS NULL) "
    "OR (scene_origin = 'sourced' AND source_refs IS NOT NULL "
    "    AND jsonb_typeof(source_refs) = 'array' "
    "    AND jsonb_array_length(source_refs) > 0)"
)


def upgrade() -> None:
    op.drop_constraint(CK, "storyboard_scenes", type_="check")
    op.create_check_constraint(CK, "storyboard_scenes", _NEW)


def downgrade() -> None:
    """Restores 0048's constraint.

    ⚠ GENUINELY LOSSY IN ONE DIRECTION and it says so rather than pretending:
    any row written with jsonb 'null' in `source_refs` while 0050 was in force
    will make this ALTER fail, because the older constraint cannot represent it.
    Normalise first if that happens:

        UPDATE storyboard_scenes SET source_refs = NULL
         WHERE jsonb_typeof(source_refs) = 'null';
    """
    op.drop_constraint(CK, "storyboard_scenes", type_="check")
    op.create_check_constraint(CK, "storyboard_scenes", _OLD)
