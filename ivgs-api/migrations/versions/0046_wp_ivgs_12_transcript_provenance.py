"""0046 — a transcript remembers what was uploaded, and where it came from

WP-IVGS-12 Task 0/Task 2, on an operator directive of 2026-08-29.

⛔ THE DEFECT THIS FIXES IS NOT "A MISSING MARKER". IT IS THAT THE OPERATOR'S
UPLOADED SCRIPT IS DESTROYED IN PLACE ON THE FIRST RUN.

There is exactly ONE path that creates a ``transcripts`` row -
``TranscriptService.upload_transcripts`` (``app/services/transcript_service.py:157``) -
and it writes the text extracted from the uploaded file into ``refined_text``.
Stage 1 then READS ``refined_text`` (``stage1_transcript.py:208``) and PATCHes
its paraphrase back into the SAME column (``:241``). There is no
``original_text`` column; the ``original_text`` field on the worker's
``TranscriptRecord`` is populated from ``refined_text`` and is therefore not the
original at all.

MEASURED 2026-08-29 on the operator's own projects, one 3,172-byte upload:

    project 4ca0d5c5 (live)      refined_text 1,866 chars   59% of the upload
    project 9c29b1d1 (archived)  refined_text 1,851 chars   58%
    project c12fa967             refined_text 1,615 chars   51%

Three different paraphrases of one script, and not one byte of the script
survives in the database. ⛳ THIS IS WHY NOBODY EVER COMPARED OUTPUT NARRATION
TO INPUT SCRIPT (recovery-plan §3 item 4): the comparison was not possible.
It also means a re-run refines a paraphrase of a paraphrase.

  ⚠ A fourth row shows the same column holding something that was never a
    transcript at all: project 0361c667 has ``refined_text`` =
    "Sure! Please provide the raw transcript you'd like me to refine." - 64
    characters where a 540-byte upload used to be. The model's chat pleasantry
    was written over the operator's file.

WHAT THE TWO COLUMNS ARE

``source_text``   The text as extracted at upload, IMMUTABLE. Written once by
                  the upload path and never by a stage. This is what the Design
                  Contract's ``source_refs`` character spans are measured
                  against, and what R1a's "original shown beside it at the gate"
                  displays. Without it, a span offset means nothing, because the
                  string it indexes into is rewritten between the two reads.

``source_kind``   ``uploaded`` | ``generated`` | ``unknown``. Task 2's mode
                  switch reads it: an UPLOADED script is EXTRACTED (beats, spans,
                  events), a GENERATED transcript keeps the existing
                  refine-for-readability behaviour. Constrained by CHECK rather
                  than by a PG enum on purpose - a CHECK is alterable in a
                  normal migration and an enum is not, and this vocabulary is
                  younger than the ones that earned enums.

THE BACKFILL, AND WHAT IT HONESTLY CANNOT DO

``source_kind`` IS backfilled, deterministically, from asset provenance: the
only creation path sets ``original_asset_id`` from a real uploaded file, so a
row that has one WAS uploaded. A row whose asset is NULL lost it to
``ON DELETE SET NULL`` and there is no evidence left - it is marked ``unknown``,
not guessed.

⛔ ``source_text`` IS DELIBERATELY NOT BACKFILLED, AND IT WOULD BE A LIE TO DO
IT. Copying today's ``refined_text`` into ``source_text`` would enshrine the
paraphrase AS the original and destroy the only evidence that the two differ -
which is the exact defect this column exists to expose. The upload survives
only as a blob in SeaweedFS behind ``original_asset_id``, and recovering it
needs network I/O that has no business inside a migration. The opt-in recovery
is ``app/scripts/wpivgs12_recover_transcript_source.py``, which re-extracts from
the asset and refuses to overwrite a non-NULL ``source_text``.

Revision ID: 0046
Revises: 0045
"""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

#: The closed vocabulary. Quoted verbatim into the CHECK below and imported by
#: the ORM, so the two cannot drift apart the way a delimiter once did.
SOURCE_KINDS = ("uploaded", "generated", "unknown")

CK_NAME = "ck_transcripts_source_kind"


def upgrade() -> None:
    op.add_column(
        "transcripts",
        sa.Column("source_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "transcripts",
        sa.Column("source_kind", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        CK_NAME,
        "transcripts",
        "source_kind IS NULL OR source_kind IN "
        "('uploaded', 'generated', 'unknown')",
    )

    # Backfill from asset provenance. Two statements, not one CASE, so the row
    # counts are separable in the migration log and a reader can see how many
    # rows had no evidence at all.
    op.execute(
        "UPDATE transcripts SET source_kind = 'uploaded' "
        "WHERE source_kind IS NULL AND original_asset_id IS NOT NULL"
    )
    op.execute(
        "UPDATE transcripts SET source_kind = 'unknown' "
        "WHERE source_kind IS NULL"
    )


def downgrade() -> None:
    """A real downgrade: the CHECK first, then both columns.

    Dropping the columns loses ``source_text``, which is the only place the
    uploaded script lives once this migration has been in service - so the
    downgrade is genuinely lossy and says so here rather than pretending
    otherwise. The blob behind ``original_asset_id`` is unaffected, so the
    recovery script can repopulate after a re-upgrade.
    """
    op.drop_constraint(CK_NAME, "transcripts", type_="check")
    op.drop_column("transcripts", "source_kind")
    op.drop_column("transcripts", "source_text")
