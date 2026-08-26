"""
Response schemas for project deletion — WP-59.

These carry the WHOLE inventory the dialog needs and the WHOLE record of what
destruction actually did. Nothing here is decorative: every field is read by
the dialog or by the acceptance evidence.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeletionCategory(BaseModel):
    """One category of material, with its real count for THIS project."""

    key: str = Field(description="Stable identifier; the dialog selects on this.")
    label: str = Field(description="Operator-facing name of the category.")
    detail: str = Field(
        description="What is inside it, in plain words, so the reader can "
                    "recognise something they wanted to keep."
    )
    cascade: str = Field(
        description=(
            "What the LIVE foreign key does when the projects row goes: "
            "'cascade' (a database ON DELETE CASCADE path reaches it), "
            "'orphan' (nothing reaches it -- deleted explicitly in the same "
            "transaction, or it would survive as litter), or 'storage' (not a "
            "database row at all). Transcribed from pg_constraint, not intent."
        )
    )
    count: int = Field(description="Rows, files or keys this category holds now.")
    breakdown: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Sub-counts where one category holds genuinely different things -- "
            "assets by asset_type, jobs by job_type. Empty where the single "
            "count is the whole truth."
        ),
    )


class DeletionPreviewResponse(BaseModel):
    """Everything the confirmation flow needs, measured, for one project."""

    project_id: str
    project_name: str
    project_state: str
    categories: list[DeletionCategory]
    blocking_jobs: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Jobs that are pending or running. While this is non-empty the "
            "deletion refuses (Task 3) and the dialog offers Cancel instead."
        ),
    )
    gpu_reservations_held: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Reservations the SCHEDULER still holds for this project's jobs, "
            "read from its own Redis registry rather than inferred from the "
            "job row."
        ),
    )
    total_rows: int
    total_bytes: int = Field(
        description="Bytes in stored objects that would actually be deleted -- "
                    "shared and library-referenced objects are excluded."
    )
    deletable: bool = Field(
        description="False while any job is non-terminal, any GPU reservation "
                    "is still held, or the scheduler's registry could not be "
                    "read at all."
    )
    scheduler_registry_error: str | None = Field(
        default=None,
        description=(
            "Set when the GPU scheduler's reservation registry could not be "
            "read. Deletion refuses on this rather than assuming nothing is "
            "held -- 'I could not check' is not 'there is nothing'."
        ),
    )
    redis_registry_error: str | None = Field(
        default=None,
        description=(
            "Set when the Redis scratch-key count could not be taken. Does NOT "
            "block deletion: those keys are per-job scratch and are inert once "
            "the job rows are gone. Reported so the count is not read as a "
            "confident zero."
        ),
    )


class DeletionResultResponse(BaseModel):
    """What was destroyed. WP-45's lesson: assert the destruction, not the code."""

    project_id: str
    project_name: str
    audit_id: str = Field(
        description="The audit_log row written BEFORE destruction began. It "
                    "survives the project and carries the per-category counts."
    )
    rows_deleted: dict[str, int]
    total_rows_deleted: int
    files_deleted: int
    files_preserved: int = Field(
        description="Stored objects deliberately NOT deleted because a library "
                    "asset or a surviving project still points at them."
    )
    preserved_reasons: list[dict[str, str]] = Field(default_factory=list)
    files_failed: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Objects the purge could NOT confirm deleted. They are not counted "
            "in files_deleted: reporting an unconfirmed delete as a delete is "
            "the shape of defect this package exists to stop. Each one is now "
            "an orphan by construction -- its row is gone and the bytes are "
            "not -- and is recorded in the audit row."
        ),
    )
    redis_keys_deleted: int
    resumed: bool = Field(
        default=False,
        description="True when this call finished a purge left behind by an "
                    "earlier interrupted deletion rather than running one.",
    )
