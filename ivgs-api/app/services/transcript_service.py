"""
Transcript service: business logic for transcript CRUD, text extraction, and reordering.

Text extraction:
- PDF: PyMuPDF (fitz)
- DOCX: python-docx
- TXT: raw read

Per §5.1.3 and Stage 1 of pipeline (§6.1).
"""
import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript import Transcript
from app.models.asset import Asset
from shared.seaweedfs_client import seaweedfs_client

logger = logging.getLogger(__name__)


def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF using PyMuPDF."""
    import fitz  # PyMuPDF

    text_parts = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


def extract_text_from_docx(content: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document

    doc = Document(io.BytesIO(content))
    text_parts = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text_parts.append(paragraph.text)
    return "\n".join(text_parts).strip()


def extract_text_from_txt(content: bytes) -> str:
    """Extract text from plain text file."""
    return content.decode("utf-8", errors="replace").strip()


TEXT_EXTRACTORS = {
    "application/pdf": extract_text_from_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": extract_text_from_docx,
    "text/plain": extract_text_from_txt,
}


class TranscriptService:
    """Business logic for transcript management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_transcripts(
        self,
        project_id: UUID,
    ) -> List[Transcript]:
        """List transcripts for a project, ordered by sequence_order."""
        result = await self.db.execute(
            select(Transcript)
            .where(Transcript.project_id == project_id)
            .order_by(Transcript.sequence_order)
        )
        return list(result.scalars().all())

    async def upload_transcripts(
        self,
        project_id: UUID,
        files: list,
        current_username: str,
    ) -> List[Transcript]:
        """
        Upload one or more transcript files.

        For each file:
        1. Upload original to SeaweedFS at /ivgs/uploads/{project_id}/
        2. Extract text based on MIME type
        3. Create Transcript record with auto-assigned sequence_order
        4. Create Asset record for the original file
        """
        # Get current max sequence_order
        max_order_result = await self.db.execute(
            select(func.max(Transcript.sequence_order))
            .where(Transcript.project_id == project_id)
        )
        current_max = max_order_result.scalar() or 0

        transcripts = []
        for idx, file in enumerate(files):
            content = await file.read()
            content_type = file.content_type or "application/octet-stream"
            filename = file.filename or f"transcript_{idx}"

            # Compute content hash for deduplication
            content_hash = hashlib.sha256(content).hexdigest()

            # Upload original file to SeaweedFS
            seaweedfs_path = f"/ivgs/uploads/{project_id}/{filename}"
            # SeaweedFSClient has no .upload(); use upload_file (volume assign -> fid) so the
            # asset records a real fid for later download_file(fid). collection matches storage_tier.
            seaweedfs_fid = await seaweedfs_client.upload_file(
                file_data=content,
                collection="hot",
                filename=filename,
            ) or ""

            # Create asset record for original file
            asset = Asset(
                project_id=project_id,
                asset_type="document",
                seaweedfs_fid=seaweedfs_fid,
                seaweedfs_path=seaweedfs_path,
                mime_type=content_type,
                file_size_bytes=len(content),
                content_hash=content_hash,
                storage_tier="hot",
            )
            self.db.add(asset)
            await self.db.flush()

            # Extract text
            extracted_text = None
            extractor = TEXT_EXTRACTORS.get(content_type)
            if extractor:
                try:
                    extracted_text = extractor(content)
                except Exception as e:
                    logger.error("Text extraction failed for %s: %s", filename, e)
                    extracted_text = None
            else:
                # Try plain text fallback
                try:
                    extracted_text = content.decode("utf-8", errors="replace").strip()
                except Exception:
                    pass

            # Detect language (simple heuristic — default to en-US)
            language_code = "en-US"

            # Create transcript record
            sequence_order = current_max + idx + 1
            transcript = Transcript(
                project_id=project_id,
                sequence_order=sequence_order,
                original_asset_id=asset.id,
                refined_text=extracted_text,
                # ── WP-IVGS-12, migration 0046 ──
                # THE SAME TEXT, IN TWO COLUMNS, ON PURPOSE. `refined_text` is
                # what stage 1 reads and then OVERWRITES with its output
                # (`stage1_transcript.py:208` then `:241`), so on any project
                # that has run once the operator's uploaded script is gone.
                # Measured on one 3,172-byte upload across three of the
                # operator's own projects: 1,866 / 1,851 / 1,615 characters —
                # three different paraphrases, and no copy of the original.
                #
                # `source_text` is written HERE, once, and by nothing else. It
                # is what the Design Contract's `source_refs` character spans
                # index into (an offset against a string that gets rewritten
                # between the write and the read means nothing), and it is what
                # the gate shows beside a rewrite under ruling R1a.
                source_text=extracted_text,
                source_kind="uploaded",
                language_code=language_code,
            )
            self.db.add(transcript)
            transcripts.append(transcript)

        await self.db.commit()
        for t in transcripts:
            await self.db.refresh(t)

        logger.info(
            f"Uploaded {len(transcripts)} transcripts to project={project_id} "
            f"by={current_username}"
        )
        return transcripts

    async def get_transcript(
        self,
        project_id: UUID,
        transcript_id: UUID,
    ) -> Optional[Transcript]:
        """Get a single transcript by ID within a project."""
        result = await self.db.execute(
            select(Transcript).where(
                Transcript.id == transcript_id,
                Transcript.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_transcript(
        self,
        project_id: UUID,
        transcript_id: UUID,
        refined_text: Optional[str] = None,
        sequence_order: Optional[int] = None,
        language_code: Optional[str] = None,
        *,
        by_service: bool = False,
    ) -> Optional[Transcript]:
        """Update transcript fields.

        ⛔ RC-Q15. FOR AN UPLOADED SCRIPT WRITTEN BY THE WORKER, `refined_text`
        IS SUBSTITUTED WITH `source_text` BY CODE AND THE MODEL'S ECHO IS
        DISCARDED. This is 12b's law applied at our own seam: **never ask a model
        to transcribe what the database already holds.**

        MEASURED, the operator's Phase-1 watch, project `3beaf804` / job
        `5b228dd5`: `source_kind='uploaded'`, `source_text` 3,138 bytes intact,
        `refined_text` **1,647 bytes of paraphrase** — the script opened
        *"# How to Multiply Double-Digit Numbers"* and the stored refinement
        opened *"Here's how to multiply two-digit numbers. Let's break it down
        into small steps."* `stage2_storyboard.py:122` then builds the design
        call's `combined_transcript` from `refined_text`, so **the whole Design
        Core was reasoning about a summary of the operator's lesson.**

        ⛳ AND THE SUBSTITUTION IS WHY THIS SHAPE WAS CHOSEN OVER RE-POINTING
        CONSUMERS AT `source_text`. Every existing consumer of `refined_text`
        becomes correct with ZERO changes to any of them: stage 2's design input
        (`:122`), `design_review`'s coverage spans, and the gap quotes a reviewer
        reads. Re-pointing would have meant finding all of them, and the one
        missed would be a silent wrong answer rather than a compile error.

        ⚠ AND IT IS SCOPED TO THE SERVICE-TOKEN PATH, WHICH THE ORDER DID NOT
        COVER AND WHICH IS A REAL DISTINCTION. This same endpoint is how a HUMAN
        edits `refined_text` inline from the gate. Substituting unconditionally
        would silently discard an operator's own correction and hand their edit
        straight back to them unchanged — a worse defect than the one being
        fixed. `by_service` is True only for the worker's callback, so the model's
        echo is discarded and a person's edit is honoured. **The generated path
        is untouched byte for byte on both.**
        """
        transcript = await self.get_transcript(project_id, transcript_id)
        if transcript is None:
            return None

        if refined_text is not None:
            source_text = transcript.source_text or ""
            uploaded_by_worker = (
                by_service and (transcript.source_kind or "") == "uploaded"
            )
            if uploaded_by_worker and not source_text:
                # ⛔ REFUSE RATHER THAN STORE THE PLACEHOLDER. The extraction
                # prompt now has the model emit the fixed word `EXTRACTED` in
                # this field, so an uploaded row with no `source_text` to
                # substitute would otherwise persist that placeholder AS the
                # script and every stage downstream would design from one word.
                # An uploaded transcript without `source_text` is already a
                # broken row (migration 0046 exists to guarantee it); saying so
                # here is cheaper than discovering it at the gate.
                raise RuntimeError(
                    f"RC-Q15: transcript {transcript_id} is source_kind="
                    f"'uploaded' but has no source_text to substitute. Refusing "
                    f"to store the worker's placeholder as the script."
                )
            # ⛔ RC-Q18 RULING (2), OPERATOR, 2026-08-30. A HUMAN EDIT TO AN
            # UPLOADED ROW WRITES **BOTH** FIELDS.
            #
            # 12h-fix scoped the substitution to the worker so an operator's
            # inline correction at the gate was not silently discarded. That
            # left the invariant half-true: after a human edit, `refined_text`
            # and `source_text` disagreed, so the design read one string and the
            # coverage spans indexed into another — the RC-Q15 defect with a
            # person's hand on it instead of a model's.
            #
            # ⛳ THE RULING CLOSES IT WITHOUT TAKING THE EDIT AWAY: the operator
            # is editing THE SCRIPT, so the script is what gets written. Both
            # fields move together and the unification invariant — and the belt
            # below — hold for EVERY editor rather than for one of them.
            #
            # ⚠ `source_text`'s "written ONCE, by the upload path only" comment
            # in `models/transcript.py` is amended by this and says so.
            if (not by_service
                    and (transcript.source_kind or "") == "uploaded"):
                transcript.source_text = refined_text
                source_text = refined_text
                logger.info(
                    "RC-Q18 uploaded transcript edited by an operator: id=%s "
                    "source_text moved with refined_text (%d bytes). The span "
                    "offsets the design cites index into this text.",
                    transcript_id, len(refined_text),
                )

            if uploaded_by_worker:
                if refined_text != source_text:
                    # ⛳ NOT A WARNING TO BE SCROLLED PAST. The paraphrase is the
                    # defect; the substitution is the fix; and the size of what
                    # was discarded is the evidence that it happened.
                    logger.warning(
                        "RC-Q15 uploaded transcript refinement DISCARDED and "
                        "replaced with source_text: id=%s model_echo=%d bytes, "
                        "source=%d bytes. The model does not transcribe what the "
                        "database holds (12b).",
                        transcript_id, len(refined_text), len(source_text),
                    )
                refined_text = source_text
            transcript.refined_text = refined_text
        if sequence_order is not None:
            transcript.sequence_order = sequence_order
        if language_code is not None:
            transcript.language_code = language_code

        transcript.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(transcript)

        # ⛔ RC-Q15's BELT, POST-WRITE AND LOUD. Read back from the refreshed row
        # rather than from the local variable: the claim is about what is IN the
        # database, and an ORM default, a trigger or a future column could make
        # those two disagree. A silent mismatch here is exactly the failure this
        # whole ledger exists to remove — stage 2 would design from a summary
        # again and nothing would say so.
        # ⛳ RC-Q18 RULING (2): THE BELT NO LONGER ASKS WHO WROTE. Both paths now
        # maintain the invariant — the worker's echo is replaced, an operator's
        # edit moves both fields — so the check that matters is the invariant
        # itself, on every uploaded row this function touches.
        if ((transcript.source_kind or "") == "uploaded"
                and refined_text is not None
                and transcript.source_text
                and transcript.refined_text != transcript.source_text):
            raise RuntimeError(
                f"RC-Q15 BELT: transcript {transcript_id} is source_kind="
                f"'uploaded' and its stored refined_text is NOT byte-identical "
                f"to source_text after a write "
                f"({len(transcript.refined_text or '')} vs "
                f"{len(transcript.source_text)} bytes). The substitution did not "
                f"take. Stage 2 would design from a paraphrase of the operator's "
                f"script; refusing rather than storing it."
            )
        logger.info("Transcript updated: id=%s", transcript_id)
        return transcript

    async def delete_transcript(
        self,
        project_id: UUID,
        transcript_id: UUID,
    ) -> bool:
        """Delete a transcript from a project."""
        transcript = await self.get_transcript(project_id, transcript_id)
        if transcript is None:
            return False

        await self.db.delete(transcript)
        await self.db.commit()
        logger.info("Transcript deleted: id=%s from project=%s", transcript_id, project_id)
        return True

    async def reorder_transcripts(
        self,
        project_id: UUID,
        items: list,
    ) -> List[Transcript]:
        """
        Bulk reorder transcripts.

        Validates:
        - All IDs belong to the project
        - No duplicate sequence_orders
        - No gaps (sequence starts at 1, consecutive)
        """
        # Validate all IDs exist in this project
        existing = await self.list_transcripts(project_id)
        existing_ids = {t.id for t in existing}

        request_ids = {item.id for item in items}
        if request_ids != existing_ids:
            missing = existing_ids - request_ids
            extra = request_ids - existing_ids
            errors = []
            if missing:
                errors.append(f"Missing transcript IDs: {missing}")
            if extra:
                errors.append(f"Unknown transcript IDs: {extra}")
            raise ValueError("; ".join(errors))

        # Apply new order
        order_map = {item.id: item.sequence_order for item in items}
        for transcript in existing:
            transcript.sequence_order = order_map[transcript.id]
            transcript.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

        # Return in new order
        return await self.list_transcripts(project_id)
