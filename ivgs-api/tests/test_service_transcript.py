"""
Phase 4 Gap 1: Transcript Service Tests

Tests TranscriptService: list, upload, get, update, delete, reorder.
DB+EXTERNAL service — SeaweedFS is mocked by conftest.py autouse fixture.
Text extraction uses real functions where possible.
"""
import io
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from app.services.transcript_service import (
    TranscriptService,
    extract_text_from_txt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project_with_user(db):
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, username, password_hash, role) VALUES (:uid, :u, 'x', 'admin')"),
        {"uid": str(uid), "u": f"tuser-{uuid.uuid4().hex[:8]}"},
    )
    await db.execute(
        text("INSERT INTO projects (id, name, created_by) VALUES (:pid, :n, :uid)"),
        {"pid": str(pid), "n": f"Transcript-Proj-{uuid.uuid4().hex[:6]}", "uid": str(uid)},
    )
    await db.commit()
    return pid


def _make_file(content: bytes, filename: str, content_type: str):
    """Create a mock UploadFile-like object."""
    f = AsyncMock()
    f.read = AsyncMock(return_value=content)
    f.filename = filename
    f.content_type = content_type
    return f


async def _upload_one(svc, pid, text_content="Hello world", filename="test.txt"):
    """Upload a single plain-text transcript."""
    files = [_make_file(text_content.encode(), filename, "text/plain")]
    transcripts = await svc.upload_transcripts(pid, files, "admin")
    return transcripts[0]


# ===========================================================================
# Text Extraction Tests
# ===========================================================================

class TestTextExtraction:
    def test_extract_txt(self):
        result = extract_text_from_txt(b"Hello\nWorld")
        assert result == "Hello\nWorld"

    def test_extract_txt_unicode(self):
        result = extract_text_from_txt("Héllo wörld".encode("utf-8"))
        assert "Héllo" in result

    def test_extract_txt_empty(self):
        result = extract_text_from_txt(b"")
        assert result == ""


# ===========================================================================
# Upload Tests
# ===========================================================================

class TestUploadTranscripts:
    async def test_upload_single_txt(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t = await _upload_one(svc, pid, "My transcript text")

        assert t.project_id == pid
        assert t.refined_text == "My transcript text"
        assert t.sequence_order == 1
        assert t.language_code == "en-US"

    async def test_upload_multiple_files(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        files = [
            _make_file(b"First file", "f1.txt", "text/plain"),
            _make_file(b"Second file", "f2.txt", "text/plain"),
        ]
        transcripts = await svc.upload_transcripts(pid, files, "admin")
        assert len(transcripts) == 2
        assert transcripts[0].sequence_order == 1
        assert transcripts[1].sequence_order == 2

    async def test_upload_appends_sequence_order(self, db_session):
        """Uploading more files continues sequence numbering."""
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        await _upload_one(svc, pid, "First")
        t2 = await _upload_one(svc, pid, "Second", "second.txt")
        assert t2.sequence_order == 2

    async def test_upload_unknown_mimetype_fallback(self, db_session):
        """Unknown MIME type falls back to UTF-8 decode."""
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        files = [_make_file(b"plain data", "data.bin", "application/octet-stream")]
        transcripts = await svc.upload_transcripts(pid, files, "admin")
        assert transcripts[0].refined_text == "plain data"


# ===========================================================================
# List / Get Tests
# ===========================================================================

class TestListTranscripts:
    async def test_list_ordered(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        await _upload_one(svc, pid, "A")
        await _upload_one(svc, pid, "B", "b.txt")

        result = await svc.list_transcripts(pid)
        assert len(result) == 2
        assert result[0].sequence_order < result[1].sequence_order

    async def test_list_empty(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        result = await svc.list_transcripts(pid)
        assert result == []


class TestGetTranscript:
    async def test_get_existing(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t = await _upload_one(svc, pid)

        result = await svc.get_transcript(pid, t.id)
        assert result is not None
        assert result.id == t.id

    async def test_get_wrong_project(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t = await _upload_one(svc, pid)

        other_pid = await _create_project_with_user(db_session)
        result = await svc.get_transcript(other_pid, t.id)
        assert result is None

    async def test_get_nonexistent(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        result = await svc.get_transcript(pid, uuid.uuid4())
        assert result is None


# ===========================================================================
# Update Tests
# ===========================================================================

class TestUpdateTranscript:
    async def test_update_text(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t = await _upload_one(svc, pid, "Original")

        updated = await svc.update_transcript(pid, t.id, refined_text="Refined")
        assert updated.refined_text == "Refined"

    async def test_update_language(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t = await _upload_one(svc, pid)

        updated = await svc.update_transcript(pid, t.id, language_code="es-ES")
        assert updated.language_code == "es-ES"

    async def test_update_nonexistent(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        result = await svc.update_transcript(pid, uuid.uuid4(), refined_text="x")
        assert result is None


# ===========================================================================
# Delete Tests
# ===========================================================================

class TestDeleteTranscript:
    async def test_delete_success(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t = await _upload_one(svc, pid)

        deleted = await svc.delete_transcript(pid, t.id)
        assert deleted is True
        assert await svc.get_transcript(pid, t.id) is None

    async def test_delete_nonexistent(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        deleted = await svc.delete_transcript(pid, uuid.uuid4())
        assert deleted is False


# ===========================================================================
# Reorder Tests
# ===========================================================================

class TestReorderTranscripts:
    async def test_reorder_success(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t1 = await _upload_one(svc, pid, "A")
        t2 = await _upload_one(svc, pid, "B", "b.txt")

        # Swap order
        items = [
            MagicMock(id=t1.id, sequence_order=2),
            MagicMock(id=t2.id, sequence_order=1),
        ]
        result = await svc.reorder_transcripts(pid, items)
        assert result[0].refined_text == "B"  # B now first
        assert result[1].refined_text == "A"

    async def test_reorder_missing_id_raises(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t1 = await _upload_one(svc, pid, "A")

        items = [
            MagicMock(id=t1.id, sequence_order=1),
            MagicMock(id=uuid.uuid4(), sequence_order=2),  # doesn't exist
        ]
        with pytest.raises(ValueError, match="Unknown transcript IDs"):
            await svc.reorder_transcripts(pid, items)

    async def test_reorder_incomplete_list_raises(self, db_session):
        """Must include ALL transcripts in reorder request."""
        pid = await _create_project_with_user(db_session)
        svc = TranscriptService(db_session)
        t1 = await _upload_one(svc, pid, "A")
        await _upload_one(svc, pid, "B", "b.txt")

        # Only include one of two
        items = [MagicMock(id=t1.id, sequence_order=1)]
        with pytest.raises(ValueError, match="Missing transcript IDs"):
            await svc.reorder_transcripts(pid, items)
