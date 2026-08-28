"""
Base Pydantic v2 schemas used across all endpoints.

- PaginatedResponse: Standard pagination envelope per Appendix C.1
- ErrorDetail / ErrorResponse: Standard error format per Appendix C.2
- HealthResponse: Health check response format per §5.1.1
"""
from typing import Generic, List, Optional, TypeVar

import os

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard pagination envelope per Appendix C.1.

    {
        "data": [...],
        "total": 142,
        "page": 1,
        "per_page": 50,
        "pages": 3,
        "has_more": true
    }
    """

    data: List[T]
    total: int = Field(ge=0, description="Total count across all pages")
    page: int = Field(ge=1, description="Current page (1-indexed)")
    per_page: int = Field(ge=1, le=100, description="Items per page")
    pages: int = Field(ge=0, description="Total page count")
    has_more: bool = Field(description="Whether additional pages exist")


class ErrorDetailItem(BaseModel):
    """Individual field-level error detail."""

    field: str
    issue: str


class ErrorBody(BaseModel):
    """Error body matching Appendix C.2 format."""

    code: str = Field(description="Machine-readable error code from C.5")
    message: str = Field(description="Human-readable error message")
    details: Optional[List[ErrorDetailItem]] = Field(
        default=None, description="Optional field-level error list"
    )
    request_id: Optional[str] = Field(
        default=None, description="UUID for log correlation"
    )


class ErrorResponse(BaseModel):
    """Top-level error response wrapper."""

    error: ErrorBody


class ServiceStatus(BaseModel):
    """Individual service health status."""

    status: str  # "connected" | "disconnected" | "degraded"
    latency_ms: Optional[float] = None


class HealthResponse(BaseModel):
    """
    Health check response per §5.1.1.

    Returns status of database, Redis, and SeaweedFS.
    """

    status: str = Field(description="Overall status: healthy | degraded | unhealthy")
    # WP-IVGS-08 Task 3(a). Was `default="5.0.0"` -- the third place this API
    # asserted a version it had no way of knowing (with `/health` and
    # `openapi.json`, which disagreed with it and with each other). It now
    # defaults to the build baked into the image, or "unknown".
    version: str = Field(
        default_factory=lambda: os.environ.get("IVGS_BUILD_REF", "unknown")
    )
    database: ServiceStatus
    redis: ServiceStatus
    seaweedfs: ServiceStatus

    model_config = ConfigDict(from_attributes=True)
