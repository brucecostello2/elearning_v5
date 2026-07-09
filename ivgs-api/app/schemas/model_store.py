"""AD-01 Model Store + selection-planner API schemas (ARCH-1 Tarball 1)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.models.model_store import (
    CapabilityDimension,
    ModelEngine,
    ModelStage,
    ModelState,
    ModelTier,
    NodeAvailabilityStatus,
    SelectionSource,
)

# --- capability tags -------------------------------------------------------

class CapabilityTagIn(BaseModel):
    dimension: CapabilityDimension
    value: str = Field(min_length=1, max_length=64)
    weight: float | None = Field(default=None, ge=0.0, le=1.0)


class CapabilityTagOut(CapabilityTagIn):
    model_config = ConfigDict(from_attributes=True)


# --- AD-04 seam 1: certification-export receiver ---------------------------

class ProvenanceIn(BaseModel):
    """Measurement environment behind a certification (MBCP Amendment B)."""

    provenance_id: UUID | None = None
    engine_image_digest: str | None = None
    gpu_driver_version: str | None = None
    cuda_version: str | None = None
    weight_bundle_ref: str | None = None
    hardware_profile_id: UUID | None = None


class ExportBundleIn(BaseModel):
    """MBCP -> IVGS certified-model export (mirrors mbcp_core.schemas.export).

    Ingested as a CANDIDATE registration + AD-01.7.2 attestation. Lean, opaque
    and checksum-anchored, exactly as MBCP sends it. Fields the IVGS Model
    needs but MBCP does not carry (engine *type*, measured VRAM) are derived /
    left for the operator at the approval gate — a recorded MBCP-side gap.
    """

    model_config = ConfigDict(extra="ignore")

    certification_id: UUID
    model_id: UUID | None = None  # MBCP's model id (provenance only)
    model_name: str = Field(min_length=1, max_length=128)
    ivgs_stage: str = Field(min_length=1, max_length=64)
    weight_tier: str = Field(default="certified", max_length=32)
    bundle_digest: str = Field(min_length=1, max_length=128)
    bundle_manifest_url: str = Field(min_length=1, max_length=1024)
    engine_version: str | None = Field(default=None, max_length=256)
    # SSOT §12.5 / ADR-4 "full AD-01 receiving contract" fields. Optional
    # because the current MBCP ExportBundle code omits them (deployment-package
    # generalization is tracked-remaining MBCP work); consumed when supplied,
    # else engine is derived from stage and VRAM stays null.
    engine: ModelEngine | None = None
    measured_vram_gb: float | None = Field(default=None, ge=0)
    license: str | None = Field(default=None, max_length=128)
    quantization: str | None = Field(default=None, max_length=64)
    provenance: ProvenanceIn | None = None
    quality_summary: dict = Field(default_factory=dict)
    certified_at: datetime | None = None
    certified_by: str = Field(default="mbcp", min_length=1, max_length=128)


class ExportReceiptOut(BaseModel):
    """Ack returned to MBCP. MBCP reads ``ad01_id`` (and accepts ``ack_id``)."""

    model_config = ConfigDict(from_attributes=True)

    ad01_id: str  # AD-01's id for the accepted model (the model UUID)
    accepted: bool = True
    created: bool = True  # True = new registration; False = re-cert / replay
    state: ModelState


# --- models ----------------------------------------------------------------

class ModelRegisterIn(BaseModel):
    """POST /models — registers a CANDIDATE (AD-01.5.1)."""

    name: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    stage: ModelStage
    engine: ModelEngine
    tier: ModelTier = ModelTier.BOTH
    description: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    source_url: str | None = Field(default=None, max_length=512)
    weights_ref: str | None = Field(default=None, max_length=512)
    weights_checksum: str | None = Field(default=None, max_length=128)
    license: str | None = Field(default=None, max_length=128)
    vram_gb: float | None = Field(default=None, ge=0)
    dynamically_loadable: bool = True
    default_params: dict | None = None
    capability_tags: list[CapabilityTagIn] = Field(default_factory=list)


class ModelUpdateIn(BaseModel):
    """PATCH /models/{id} — metadata / switches (no lifecycle here)."""

    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    source_url: str | None = Field(default=None, max_length=512)
    vram_gb: float | None = Field(default=None, ge=0)
    default_params: dict | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class ApproveIn(BaseModel):
    """POST /models/{id}/approve — AD-01.7.2 attestation (all required)."""

    attested_by: str = Field(min_length=1, max_length=128)
    vetting_reference: str = Field(min_length=1, max_length=512)
    checklist: dict


class AvailabilityIn(BaseModel):
    """PUT /models/{id}/availability/{node_id} — poller/ops upsert."""

    status: NodeAvailabilityStatus
    served: bool = False


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    attested_by: str
    vetting_reference: str
    checklist: dict
    attested_at: datetime


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    node_id: str
    status: NodeAvailabilityStatus
    served: bool
    last_health_check: datetime | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    stage: ModelStage
    engine: ModelEngine
    tier: ModelTier
    state: ModelState
    description: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    source_url: str | None = None
    weights_ref: str | None = None
    weights_checksum: str | None = None
    license: str | None = None
    vram_gb: float | None = None
    dynamically_loadable: bool
    default_params: dict | None = None
    is_default: bool
    enabled: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    capability_tags: list[CapabilityTagOut] = Field(default_factory=list)
    node_availability: list[AvailabilityOut] = Field(default_factory=list)
    approvals: list[ApprovalOut] = Field(default_factory=list)


# --- planner ---------------------------------------------------------------

class PlanRequest(BaseModel):
    """POST /projects/{project_id}/model-selections/plan (AD-01.6)."""

    stages: list[ModelStage] = Field(min_length=1)
    tier: ModelTier
    capability_profile: dict[CapabilityDimension, str] = Field(
        default_factory=dict,
        description="Job capability profile: dimension -> requested value",
    )


class ManualSelectionIn(BaseModel):
    """PUT manual override (AD-01.8.4)."""

    stage: ModelStage
    tier: ModelTier
    model_id: UUID
    scene_id: UUID | None = None
    rationale: str = Field(min_length=1)


class SelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    scene_id: UUID | None = None
    stage: ModelStage
    tier: ModelTier
    model_id: UUID
    selected_by: SelectionSource
    rationale: str
    created_at: datetime


class PlanResponse(BaseModel):
    selections: list[SelectionOut]
