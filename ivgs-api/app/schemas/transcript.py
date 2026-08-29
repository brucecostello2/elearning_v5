"""
Transcript Pydantic schemas per §5.1.3.

Includes: TranscriptResponse, TranscriptUpdate, ReorderRequest.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TranscriptResponse(BaseModel):
    """Response schema for a single transcript."""

    id: UUID
    project_id: UUID
    sequence_order: int
    original_asset_id: Optional[UUID] = None
    refined_text: Optional[str] = None
    # ── WP-IVGS-12, migration 0046 ──
    # ⛔ `refined_text` IS NOT THE UPLOAD once a run has happened: stage 1
    # PATCHes its paraphrase over it. `source_text` is the extraction as
    # uploaded, written once and never by a stage, and it is what the Design
    # Contract's character spans index into.
    source_text: Optional[str] = None
    source_kind: Optional[str] = None
    language_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptUpdate(BaseModel):
    """Schema for PATCH /api/v1/projects/{id}/transcripts/{tid}."""

    refined_text: Optional[str] = Field(default=None, description="Updated refined text")
    sequence_order: Optional[int] = Field(default=None, ge=1, description="New sequence order")
    language_code: Optional[str] = Field(default=None, max_length=10)


class ReorderItem(BaseModel):
    """Single item in a reorder request."""

    id: UUID
    sequence_order: int = Field(ge=1)


class TranscriptReorderRequest(BaseModel):
    """
    Schema for POST /api/v1/projects/{id}/transcripts/reorder.

    Body: [{id, sequence_order}, ...]
    Validates no duplicate sequence_orders.
    """

    items: List[ReorderItem] = Field(min_length=1)

    @classmethod
    def validate_no_duplicates(cls, items: List[ReorderItem]) -> List[ReorderItem]:
        orders = [item.sequence_order for item in items]
        if len(orders) != len(set(orders)):
            raise ValueError("Duplicate sequence_order values are not allowed")
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate transcript IDs are not allowed")
        return items
