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
    ) -> Optional[Transcript]:
        """Update transcript fields."""
        transcript = await self.get_transcript(project_id, transcript_id)
        if transcript is None:
            return None

        if refined_text is not None:
            transcript.refined_text = refined_text
        if sequence_order is not None:
            transcript.sequence_order = sequence_order
        if language_code is not None:
            transcript.language_code = language_code

        transcript.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(transcript)
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
