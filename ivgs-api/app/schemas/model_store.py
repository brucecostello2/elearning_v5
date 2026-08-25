"""AD-01 Model Store + selection-planner API schemas (ARCH-1 Tarball 1)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    # WP-53. Was `extra="ignore"`.
    #
    # `extra="ignore"` on a SEAM schema is the swallow pattern in schema form:
    # the sender amends the contract, the receiver returns 201, and the
    # amendment goes in the bin without a line anywhere saying so. That is
    # exactly what happened to `request_constraints` between 2026-08-21 and
    # this change.
    #
    # WHY NOT `extra="forbid"`. It was the other option on the table and it is
    # the wrong one HERE, for a reason specific to this seam. AD-04 seam 1 is an
    # MBCP-initiated PUSH and IVGS is a receiver (dev/CLAUDE.md 11.1) -- MBCP
    # amends the bundle unilaterally and has done so at least twice. Under
    # `forbid`, the next unilateral amendment would 422 every certification
    # export until someone on this side shipped a schema change: a silent drop
    # traded for a total ingest outage, with the sender unable to fix it. For a
    # receiver that does not control the contract, availability of the seam
    # beats strictness about its edges.
    #
    # `allow` + a validator that RECORDS is what "must produce a record, not
    # silence" actually asks for. The record is durable, not just a log line
    # that rotates: `receive_certified_model` writes the field names onto the
    # store row. So an unknown field costs one warning and one stored name, and
    # the bundle still lands.
    model_config = ConfigDict(extra="allow")

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
    # WP-53. MBCP has sent this since 2026-08-21 (WP-E32-R, its Appendix G) and
    # IVGS dropped it silently until now: the DECLARED geometry and sampler
    # rules a request must obey, from the adapter serving that cert's stage.
    #
    # NOT the same thing as `quality_summary.performance.resolution`, and the
    # distinction is the whole point. That is what was MEASURED under test -- a
    # real 1920x1080 for Wan2.2-T2V. A consumer that builds a request from the
    # measurement reproduces a 135/134 sampler failure while holding MBCP's
    # certificate, which is WP-47's scenario, named by the sender in its own
    # code comment before it happened here.
    #
    # NULLABLE, and that is not a detail. Mirrors
    # `mbcp_core/schemas/export.py:82` -- `request_constraints: dict | None =
    # None` -- read off origin/main at 156ddb4.
    #
    # MBCP sends an explicit `null` for most models: `request_constraints()`
    # returns None for anything with no declared rule, and its own tests pin
    # that for FLUX.1-dev and for unregistered names. A `dict` field with a
    # `default_factory` would have 422'd every one of those bundles -- turning a
    # silently-dropped field into a rejected export, which is worse than the
    # defect being fixed.
    #
    # `None` and `{}` MUST stay distinct, in MBCP's words: "An empty block would
    # be the claim 'we checked'; a missing one is the truth 'we have declared
    # nothing'." IVGS therefore stores NULL for a null and never substitutes an
    # empty object.
    #
    # Typed `dict`, not a model: carried, stored, surfaced, NOT interpreted --
    # WP-53's scope. The real block is self-describing anyway, and leads with an
    # honesty label: `kind: "declared"`, `declared_by`, `declared_on`, then
    # optional `geometry`, `frame_count_rule`, `value_rules` and a NESTED
    # `default_params` of legal defaults. That nested key is one more reason
    # this does not belong inside `models.default_params` -- they would collide.
    request_constraints: dict | None = None
    certified_at: datetime | None = None
    certified_by: str = Field(default="mbcp", min_length=1, max_length=128)

    @property
    def unknown_fields(self) -> list[str]:
        """Names MBCP sent that this schema does not declare, sorted.

        Empty for a bundle that matches the contract. Non-empty means the seam
        has drifted and IVGS is behind -- which is a fact worth storing next to
        the row it arrived with, not a reason to reject the row.
        """
        return sorted(self.__pydantic_extra__ or {})


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


# WP-45 Task 6(e). 512 characters is not an attestation, it is a note.
#
# WP-46 §A8's vetting reference is 1,912 characters, and it is a SHORT one: it
# names the MBCP certification, the run, the result, the hardware profile, the
# measured VRAM and generation time, the engine image digest, the graph SHA, the
# nine weight bundles, and the IVGS report that verified all of it. Every clause
# is the kind of thing an auditor asks for, and the old cap forced whoever pasted
# it to choose which provenance to delete. Truncating a provenance record to fit
# a column is the one thing an attestation may not do.
#
# TEXT in the database (migration 0028); a generous but stated cap here, so an
# accidental paste of an entire report is still refused with a message rather
# than silently accepted into a column with no bound.
MAX_VETTING_REFERENCE = 8192
MAX_ATTESTED_BY = 256


class ApproveIn(BaseModel):
    """POST /models/{id}/approve — AD-01.7.2 attestation (all required)."""

    attested_by: str = Field(min_length=1, max_length=MAX_ATTESTED_BY)
    vetting_reference: str = Field(
        min_length=1,
        max_length=MAX_VETTING_REFERENCE,
        description=(
            "Free-text evidence: certification ids, measured figures, the "
            "report that verified them. Stored in full."
        ),
    )
    checklist: dict

    @field_validator("vetting_reference")
    @classmethod
    def validate_vetting_reference(cls, v: str) -> str:
        """Inline refusal, worded the way the rest of the API words its own."""
        text = v.strip()
        if not text:
            raise ValueError(
                "vetting_reference cannot be blank. An approval without "
                "evidence is not an attestation."
            )
        if len(text) > MAX_VETTING_REFERENCE:
            raise ValueError(
                f"vetting_reference is {len(text)} characters; the maximum is "
                f"{MAX_VETTING_REFERENCE}. Cite the evidence document rather "
                "than pasting it."
            )
        return text


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
