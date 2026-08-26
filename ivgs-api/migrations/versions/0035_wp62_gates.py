"""0035 — WP-62: the two human review gates, and one flag that was a lie.

Revision ID: 0035
Revises: 0034

TWO CHANGES, AND THEY ARE UNRELATED EXCEPT IN DATE. They ship in one revision
because the alternative is two revisions the operator applies in the same
minute, and a revision that does one small correct thing is worth less than a
revision whose docstring explains both.

-----------------------------------------------------------------------------
1. `project_gate_decisions` — WP-62 Task 2
-----------------------------------------------------------------------------

MEASURED 2026-08-26, BEFORE ANYTHING WAS WRITTEN. The "Approve storyboard"
button already existed and had existed since P1.5. It posts
`POST /projects/{id}/scenes/approve`, which sets `projects.state` to
MEDIA_GENERATION and dispatches `dispatch_media_generation`. It wrote no row.
Nothing recorded that an approval happened, nothing could ask whether one had,
and therefore nothing refused for want of one — spec v5.1 §6.1 requires both
gates to BLOCK and neither did.

The table is APPEND-ONLY. A rejection after an approval is a new row: "approved
then rejected" is a different fact from "never approved", and the sequence is
the review history.

`artifact_version` is NOT NULL and it is the mechanism, not a convenience. A
decision names the exact artifact it was taken against, and currency is
recomputed on read by comparing that fingerprint with the artifact as it stands
now. An upstream re-run changes the artifact and the approval goes stale by
arithmetic — there is no invalidation write to forget and no window in which a
crashed invalidator leaves a stale approval standing. `upstream_version` does
the same one level up, so re-running the STORYBOARD invalidates the DRAFT
approval immediately, before any new draft exists.

`decided_by` is SET NULL on user deletion (it must be, or deleting a user would
be blocked by the review history), which is exactly why `decided_by_name` is
denormalised beside it. A gate record that cannot say who decided, once the
reviewer has left, is not a record.

-----------------------------------------------------------------------------
2. `models.dynamically_loadable = false` for every vLLM entry — WP-62 Task 7
-----------------------------------------------------------------------------

WP-61 D-3, RULED: correct the flag now, move the routing at certification.

AD-02 is explicit that a vLLM node's model is fixed at container start by
`--model` and cannot be swapped at runtime. Two rows contradicted it, on a live
surface, measured 2026-08-26:

    Llama-3.3-70B-Instruct  translation            approved   dynamically_loadable = true
    test-model-1            storyboard_generation  retired    dynamically_loadable = true

The other two vLLM rows (`llama-3.3-70b-transcript`, `llama-3.3-70b-storyboard`)
were already false, which is what makes the two above a drift rather than a
convention. `model_selection.py:69` reads this flag; leaving it true on a live
approved row means a selection path could decide to "load" a model onto a node
whose engine cannot load one.

The UPDATE is scoped `WHERE engine = 'vllm'` rather than by name, because the
property belongs to the ENGINE and not to any particular model: a new vLLM row
added later must inherit the truth, and a by-name list would go stale the first
time one is.

NOTHING ELSE IN `models` IS TOUCHED. In particular the translation entry still
points at its certified Llama record and is NOT repointed at Qwen — the Qwen
bundle is provenance-exceptional (running, hashed, uncertified) until MBCP
certifies it under work orders 5 and 7. Its `description` is annotated with
that status and the manifest path, which is the honest statement of where it
stands; claiming a certification that does not exist would be worse than the
flag this revision corrects.

`downgrade()` restores the two rows to `true` by name — deliberately by name
and not by engine, because setting every vLLM row true on downgrade would
"restore" a value two of them never held.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


# The two rows measured true on 2026-08-26. Named so downgrade cannot invent a
# state that never existed.
_FLAG_WAS_TRUE = ("Llama-3.3-70B-Instruct", "test-model-1")

_TRANSLATION_ANNOTATION = (
    "PROVENANCE EXCEPTION, WP-62 Task 7 (WP-61 D-3, RULED). This is the "
    "CERTIFIED record and it is what an AD-01 translation binding resolves. "
    "The translation EXECUTION path does not use it: WP-61 routes translation "
    "to Qwen3.8-27B-FP8 on node-05 by dialling the stage-scoped endpoint "
    "directly. That Qwen bundle is provenance-exceptional - running, hashed, "
    "UNCERTIFIED - pending MBCP work orders 5 and 7. Its 74 file hashes over "
    "66 shards are banked at "
    "/mnt/ivgs-shared/qwen-weights-manifest-2026-08-26.txt. This entry is NOT "
    "repointed at Qwen until that certification lands; registering an "
    "uncertified bundle as approved would be a worse lie than the "
    "dynamically_loadable flag this revision corrected. Storyboard and "
    "transcript refinement stay on Llama until after M3.3 regardless, so the "
    "AD-05 conformance diff is not moved by a model change."
)


def upgrade() -> None:
    op.create_table(
        "project_gate_decisions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("gate", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("artifact_version", sa.String(128), nullable=False),
        sa.Column("upstream_version", sa.String(128), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "decided_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("decided_by_name", sa.String(128), nullable=True),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_project_gate_decisions_project_gate",
        "project_gate_decisions",
        ["project_id", "gate", "decided_at"],
    )

    # --- Task 7. The flag, corrected on the engine rather than on a name list.
    op.execute(
        "UPDATE models SET dynamically_loadable = false, updated_at = now() "
        "WHERE engine = 'vllm' AND dynamically_loadable = true"
    )
    op.execute(
        sa.text(
            "UPDATE models SET description = :note, updated_at = now() "
            "WHERE stage = 'translation' AND engine = 'vllm' "
            "AND (description IS NULL OR description = '')"
        ).bindparams(note=_TRANSLATION_ANNOTATION)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE models SET dynamically_loadable = true, updated_at = now() "
            "WHERE name IN :names"
        ).bindparams(sa.bindparam("names", value=_FLAG_WAS_TRUE, expanding=True))
    )
    op.execute(
        sa.text(
            "UPDATE models SET description = NULL, updated_at = now() "
            "WHERE stage = 'translation' AND engine = 'vllm' "
            "AND description = :note"
        ).bindparams(note=_TRANSLATION_ANNOTATION)
    )
    op.drop_index(
        "ix_project_gate_decisions_project_gate",
        table_name="project_gate_decisions",
    )
    op.drop_table("project_gate_decisions")
