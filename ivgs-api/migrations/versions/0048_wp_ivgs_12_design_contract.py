"""0048 — the Design Contract: a scene declares what it teaches and where it came from

WP-IVGS-12 Task 1, Phase 1 of the recovery plan. Normative source:
``dev/design/Instructional_Design_Foundation_for_IVGS_2026-08-29.md`` §6.

WHY THE STORAGE IS SPLIT THE WAY IT IS - ARGUED FROM HOW THE GATE READS IT

The gate (Foundation §7) renders one page containing six things. Three of them
are properties of a SCENE and are read while iterating scenes:

    the Gagné event, so the arc can be drawn in scene order
    the outcomes this scene serves, so the matrix can be filled
    the provenance - the span it reworked, or its designed origin

and three of them are properties of the DESIGN AS A WHOLE, read once:

    the outcomes list, with any ABCD refinement awaiting approval
    the beats consciously dropped, with reasons
    the evidence map, outcome -> the scene ids that ASSESS it

Per-scene facts go on ``storyboard_scenes`` because the gate already SELECTs
those rows and renders a panel per scene - ``media_rationale`` and
``text_carried_by`` (0045) set that precedent, and a join per scene to fetch an
event name would buy nothing. Whole-design facts go in ONE ROW of a new table,
because they are a document: they have no scene to hang on, they are what the
reviewer approves, and a project that regenerates its storyboard produces a NEW
design that must not silently overwrite the one the reviewer was reading.
That last point is not hypothetical - recovery-plan RC-E records the Regenerate
button discarding a storyboard with no confirmation and no record. A brief per
generation means the previous design is still there to diff against.

⛔ WHAT IS DELIBERATELY *NOT* ADDED, AND THE FOUNDATION IS FLAGGED FOR IT

Foundation §6 lists ``modality_rationale (one line, §4 table row)`` as a new
per-scene field. **It already exists.** v7's RULE 9 asked for exactly that - one
line on why THIS medium for THIS scene - and 0045 gave it the column
``media_rationale``. Adding ``modality_rationale`` beside it would create two
columns for one fact, which is the drift class this repository has been bitten
by repeatedly (the WP-64 delimiter, the four sources of truth in RC-C).

**Ruling taken here and flagged in the report rather than made silently:
Foundation §6's ``modality_rationale`` IS ``storyboard_scenes.media_rationale``,
and the Design Contract uses the existing name on the wire.** One name, one
column, one meaning. The Foundation is normative on WHAT must be declared, not
on what the column is called when the declaration already has one.

THE FIVE ORIGINAL FIELDS ARE UNTOUCHED. ``scene_index``, ``narration_text``,
``visual_description``, ``media_type`` and ``duration_seconds`` keep their exact
types, nullability and semantics; downstream branches on them and this migration
does not go near them.

NOTHING IS BACKFILLED AND NOTHING IS NOT NULL. Every column added here is
nullable with no default, so a scene created by any existing path - the v7
storyboard, the gate's manual add, the adaptation service - keeps working
unchanged and reads correctly as "authored before the Design Core, declared
nothing". The gate is what requires a declaration, and only for storyboards that
carry a brief.

Revision ID: 0048
Revises: 0047
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

#: Gagné's Nine Events, Foundation §3, in arc order. The order is meaningful -
#: the Merrill check in the validator asks whether a design ever leaves the
#: first five - so this is a tuple, not a set.
INSTRUCTIONAL_EVENTS = (
    "hook",
    "objective",
    "recall_prior",
    "present",
    "guide",
    "practice",
    "feedback",
    "assess",
    "transfer",
)

#: Bloom as revised (Anderson & Krathwohl), Foundation §2, ascending.
BLOOM_LEVELS = (
    "remember",
    "understand",
    "apply",
    "analyze",
    "evaluate",
    "create",
)

#: Foundation §6: ``source_refs[] XOR origin:"designed"``. Stored as one column
#: rather than as the presence/absence of another, so the XOR is a CHECK a
#: database can enforce instead of a rule an application has to remember.
SCENE_ORIGINS = ("sourced", "designed")

CK_EVENT = "ck_storyboard_scenes_instructional_event"
CK_BLOOM = "ck_storyboard_scenes_bloom_level"
CK_ORIGIN = "ck_storyboard_scenes_scene_origin"
CK_XOR = "ck_storyboard_scenes_source_xor_designed"
IX_BRIEF_ACTIVE = "ux_storyboard_design_briefs_active_per_project"


def _members(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # ── per-scene: the design declarations ────────────────────────────────
    op.add_column(
        "storyboard_scenes",
        sa.Column("serves_outcomes", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("instructional_event", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("bloom_level", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("source_refs", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("scene_origin", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("rewrite_of", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "storyboard_scenes",
        sa.Column("signal_spec", postgresql.JSONB(), nullable=True),
    )

    op.create_check_constraint(
        CK_EVENT,
        "storyboard_scenes",
        f"instructional_event IS NULL OR instructional_event IN "
        f"({_members(INSTRUCTIONAL_EVENTS)})",
    )
    op.create_check_constraint(
        CK_BLOOM,
        "storyboard_scenes",
        f"bloom_level IS NULL OR bloom_level IN ({_members(BLOOM_LEVELS)})",
    )
    op.create_check_constraint(
        CK_ORIGIN,
        "storyboard_scenes",
        f"scene_origin IS NULL OR scene_origin IN ({_members(SCENE_ORIGINS)})",
    )
    # The XOR, enforced by the database rather than by whoever remembers.
    # A scene that declares nothing (every pre-Design-Core row) is allowed
    # through; a scene that declares BOTH, or declares 'sourced' with no refs,
    # is not.
    #
    # ⛔ `source_refs IS NOT NULL` IS NOT REDUNDANT AND WAS ADDED AFTER THE
    # CHECK WAS MEASURED LETTING A BAD ROW IN. Without it, a row with
    # scene_origin='sourced' and source_refs NULL evaluates the third branch to
    # NULL (jsonb_typeof(NULL) is NULL), the disjunction becomes
    # FALSE OR FALSE OR NULL = NULL, and **a CHECK constraint PASSES on NULL**.
    # Three-valued logic turns the strictest branch into the weakest one. The
    # first draft of this constraint accepted exactly the row it exists to
    # refuse; `tests/test_wpivgs12_design_contract.py` pins all six cases.
    op.create_check_constraint(
        CK_XOR,
        "storyboard_scenes",
        "scene_origin IS NULL "
        "OR (scene_origin = 'designed' AND source_refs IS NULL) "
        "OR (scene_origin = 'sourced' AND source_refs IS NOT NULL "
        "    AND jsonb_typeof(source_refs) = 'array' "
        "    AND jsonb_array_length(source_refs) > 0)",
    )

    # ── whole-design: the brief the reviewer approves ─────────────────────
    op.create_table(
        "storyboard_design_briefs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Nullable and NOT a foreign key on purpose: a brief must survive its
        # job row being pruned by retention, and it is evidence of what was
        # designed rather than a child of the run that designed it.
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        # outcomes[]: each {id, text, bloom_level, abcd:{...},
        #                   proposed_refinement|null, measurable:bool}
        # NEVER silently substituted - Foundation §2. The operator's own words
        # stay in `text`; a refinement is a PROPOSAL alongside it.
        sa.Column("outcomes", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        # dropped_beats[]: each {span:{transcript_id,start,end}, summary, reason}
        sa.Column("dropped_beats", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        # evidence_map: {outcome_id: [scene_index, ...]} - the ASSESSING scenes
        # only. Serving is not evidence; Foundation §1 stage 2 is the whole point.
        sa.Column("evidence_map", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        # The extraction artifact stage 1 produced and the design consumed.
        # Kept so the gate can diff a rewrite against the beat it came from
        # without re-reading the transcript, and so a drop can be shown in
        # context.
        sa.Column("intent", postgresql.JSONB(), nullable=True),
        # The model's emission, verbatim and unvalidated. This is the evidence
        # limb: everything above is parsed FROM it, and a reader who suspects
        # the parse can check it. RC-P1 happened because nobody could.
        sa.Column("raw_contract", postgresql.JSONB(), nullable=True),
        # The PARSED per-scene declarations, [{scene_index, serves_outcomes,
        # instructional_event, bloom_level, source_refs, scene_origin,
        # rewrite_of, signal_spec}, ...].
        #
        # ⛳ DERIVED, AND STORED ANYWAY, FOR ONE REASON: the contract is
        # captured BEFORE the scene rows exist, so `create_scene` has to look up
        # each scene's declarations as it lands. Re-deriving them there would put
        # a second copy of the parse in the API tree, and the worker's copy would
        # be the one that gets maintained. One parse, in `design_core.contract`,
        # and its OUTPUT travels.
        sa.Column("scene_designs", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("contract_version", sa.String(length=16), nullable=True),
        sa.Column("prompt_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # One ACTIVE brief per project; superseded ones stay readable. Same shape
    # as the prompts lineage, and for the same reason.
    op.create_index(
        IX_BRIEF_ACTIVE,
        "storyboard_design_briefs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_storyboard_design_briefs_project_created",
        "storyboard_design_briefs",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_storyboard_design_briefs_project_created",
        table_name="storyboard_design_briefs",
    )
    op.drop_index(IX_BRIEF_ACTIVE, table_name="storyboard_design_briefs")
    op.drop_table("storyboard_design_briefs")

    for ck in (CK_XOR, CK_ORIGIN, CK_BLOOM, CK_EVENT):
        op.drop_constraint(ck, "storyboard_scenes", type_="check")
    for col in (
        "signal_spec",
        "rewrite_of",
        "scene_origin",
        "source_refs",
        "bloom_level",
        "instructional_event",
        "serves_outcomes",
    ):
        op.drop_column("storyboard_scenes", col)
