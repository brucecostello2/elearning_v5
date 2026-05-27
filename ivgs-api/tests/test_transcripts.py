"""
Transcript endpoint tests: upload, CRUD, reorder.
"""
import io
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestTranscriptUpload:
    """Test transcript file upload and text extraction."""

    async def test_upload_txt_file(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test uploading a plain text transcript."""
        content = b"This is a test transcript for the instructional video."
        response = await client.post(
            f"/api/v1/projects/{project_id}/transcripts/upload",
            files=[("files", ("test.txt", io.BytesIO(content), "text/plain"))],
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        assert data[0]["refined_text"] is not None
        assert data[0]["sequence_order"] == 1

    async def test_upload_multiple_files(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test uploading multiple transcript files."""
        files = [
            ("files", ("part1.txt", io.BytesIO(b"Part 1 content"), "text/plain")),
            ("files", ("part2.txt", io.BytesIO(b"Part 2 content"), "text/plain")),
        ]
        response = await client.post(
            f"/api/v1/projects/{project_id}/transcripts/upload",
            files=files,
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data) == 2
        assert data[0]["sequence_order"] < data[1]["sequence_order"]


@pytest.mark.asyncio
class TestTranscriptCRUD:
    """Test transcript CRUD operations."""

    async def test_list_transcripts(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test listing transcripts for a project."""
        response = await client.get(
            f"/api/v1/projects/{project_id}/transcripts",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_update_transcript(self, client: AsyncClient, operator_token: str, transcript_fixture: dict):
        """Test updating transcript refined_text."""
        project_id = transcript_fixture["project_id"]
        transcript_id = transcript_fixture["id"]
        response = await client.patch(
            f"/api/v1/projects/{project_id}/transcripts/{transcript_id}",
            json={"refined_text": "Updated refined text content"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["refined_text"] == "Updated refined text content"

    async def test_delete_transcript(self, client: AsyncClient, operator_token: str, transcript_fixture: dict):
        """Test deleting a transcript."""
        project_id = transcript_fixture["project_id"]
        transcript_id = transcript_fixture["id"]
        response = await client.delete(
            f"/api/v1/projects/{project_id}/transcripts/{transcript_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 204


@pytest.mark.asyncio
class TestTranscriptReorder:
    """Test transcript reordering."""

    async def test_reorder_transcripts(self, client: AsyncClient, operator_token: str, project_with_transcripts: dict):
        """Test bulk reordering transcripts."""
        project_id = project_with_transcripts["project_id"]
        transcripts = project_with_transcripts["transcripts"]

        # Reverse the order
        items = [
            {"id": str(transcripts[1]["id"]), "sequence_order": 1},
            {"id": str(transcripts[0]["id"]), "sequence_order": 2},
        ]
        response = await client.post(
            f"/api/v1/projects/{project_id}/transcripts/reorder",
            json={"items": items},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data[0]["sequence_order"] == 1
        assert data[1]["sequence_order"] == 2
