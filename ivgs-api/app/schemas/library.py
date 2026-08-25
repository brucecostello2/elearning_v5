"""
Pydantic schemas for the AD-09 production content libraries: library assets,
actors and presets.

WP-40/WP-43 LESSON APPLIED, and it is the reason several fields you might
expect are absent. That defect family — a type declaring a field the API never
sends, so a component reads `undefined` and renders a blank where a value
belongs — reached thirteen instances. The rule taken from it: a field exists in
the type only if the API demonstrably populates it. Anything AD-09 specifies
but WP-56 does not implement is NOT declared here, so reaching for it is a
compile error in the frontend rather than a blank box in the operator's face.

Specifically NOT declared, and each for a stated reason:
  * `preset_drift` — AD-09.14 open question 8 is UNRULED; nothing computes it.
  * presenter/logo scene fields — WP-56 Task 3 stopped; see the report.
  * `intro_outro_templates`, `courses` — AD-09 sequencing items 5 and 7, out of
    scope for this package.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Mirrors the `library_asset_kind` PostgreSQL ENUM (migration 0030). Declared
# as a plain tuple rather than a Python enum so the API's accepted values and
# the database's are one edit apart and visibly the same list.
LIBRARY_ASSET_KINDS = (
    "logo", "video_clip", "audio_clip", "music_bed",
    "reference_clip", "reference_image", "font", "document",
)
OWNER_SCOPES = ("global", "user")
PRESENTER_ORIENTATIONS = ("landscape", "portrait")


# ---------------------------------------------------------------------------
# Library assets — AD-09.4.2
# ---------------------------------------------------------------------------

class LibraryAssetResponse(BaseModel):
    """A library asset as the GUI receives it."""

    id: UUID
    kind: str
    name: str
    description: Optional[str] = None
    seaweedfs_fid: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    content_hash: Optional[str] = None
    tags: Optional[List[str]] = None
    owner_scope: str
    created_by: Optional[UUID] = None
    superseded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LibraryAssetUploadResponse(LibraryAssetResponse):
    """Upload result.

    ``was_deduplicated`` is here for the same reason WP-45 added it to
    ``AssetUploadResponse``: without it a dedup hit and a fresh upload are
    byte-identical replies, and the operator cannot tell whether the library
    just grew or they re-selected something already in it. That ambiguity is
    the B3 duplicate-asset accumulation ledger item in miniature.
    """

    was_deduplicated: bool = False


class LibraryAssetUpdate(BaseModel):
    """Metadata-only edit. Bytes are immutable; supersede instead."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class LibraryAssetReferenceRequest(BaseModel):
    """Reference a library asset into a project — AD-09.4.2 reference-don't-copy.

    Creates an ``assets`` row that points at the SAME SeaweedFS object and
    records ``library_asset_id``. No bytes move. This is what makes swapping a
    logo across a course a reference change instead of a re-upload.
    """

    library_asset_id: UUID
    asset_type: str = Field(
        description="The project-side `assets.asset_type` ENUM value to file it under",
    )
    scene_id: Optional[UUID] = None
    language_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Actors — AD-09.4.3
# ---------------------------------------------------------------------------

class ActorBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    reference_clip_id: Optional[UUID] = None
    reference_image_id: Optional[UUID] = None
    voice_profile: Optional[Dict[str, Any]] = None
    # ⚠ AD-09.14 OPEN QUESTION 1 — AWAITING THE OPERATOR.
    # The MagiHuman parameter set that reproduces an identity is operator
    # knowledge recorded nowhere in this repository. The field is an opaque
    # per-engine map and is INTENTIONALLY unvalidated: a schema invented here
    # would be indistinguishable from a recorded fact in six months.
    # Shape: {"<engine_name>": {...}, ...}
    engine_bindings: Optional[Dict[str, Any]] = None
    default_orientation: str = "landscape"
    certified_model_id: Optional[UUID] = None


class ActorCreate(ActorBase):
    owner_scope: str = "user"


class ActorUpdate(BaseModel):
    """Every field optional — PATCH semantics.

    ``certified_model_id`` is editable and changing it is an IDENTITY CHANGE
    (AD-09.4.3): an actor is only reproducible on the engine it was established
    against. The API records the change; the GUI is required to warn before
    sending it.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    reference_clip_id: Optional[UUID] = None
    reference_image_id: Optional[UUID] = None
    voice_profile: Optional[Dict[str, Any]] = None
    engine_bindings: Optional[Dict[str, Any]] = None
    default_orientation: Optional[str] = None
    certified_model_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class ActorResponse(ActorBase):
    id: UUID
    owner_scope: str
    is_active: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Presets — AD-09.5
# ---------------------------------------------------------------------------

class PresetModelSelection(BaseModel):
    """One (stage, tier) → model binding carried by a preset.

    ``stage`` and ``tier`` are the AD-01 ``model_stage`` / ``model_tier`` ENUM
    values. They are validated at APPLY time by ``model_selection.manual_override``,
    which already checks that the model exists, is servable, and serves the named
    stage — three checks this schema deliberately does not duplicate. A preset
    created while a model was approved and applied after it was retired must fail
    at apply time with the real reason, not at create time with a stale one.
    """

    stage: str
    tier: str
    model_id: UUID


class PresetMediaDefaults(BaseModel):
    """Scene-creation defaults. Applied to scenes the project creates LATER."""

    media_type: Optional[str] = None
    resolution_tier: Optional[str] = None
    framerate: Optional[int] = None


class PresetBranding(BaseModel):
    """Branding block — RECORDED, NOT RENDERED.

    ⚠ Every field here is stored on the preset and returned to the GUI, and
    NOTHING IN THE RENDER PATH READS ANY OF IT. WP-56 Task 3 stopped on the
    finding that the per-scene presenter and logo overlay chain is broken at
    three of its four links (see the WP-56 report §Task 3), so a logo recorded
    here does not appear in a rendered course.

    It is carried anyway because a preset that cannot hold branding is not the
    preset AD-09.5 specifies, and because the operator needs somewhere to put
    these decisions before the render path is repaired. The GUI labels the block
    accordingly. Do not remove that label until the render path lands.
    """

    logo_library_asset_id: Optional[UUID] = None
    logo_policy: Optional[str] = Field(
        default=None,
        description="always | never | per_scene (AD-09.10). Recorded, not rendered.",
    )
    brand_colours: Optional[Dict[str, str]] = None
    typography: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "AD-09.10 token set: heading / body / lower_third / title_card. "
            "Font files live in the library as kind=font. Provisioning those "
            "fonts to the compositor node is AD-09.14 open question 6 and is "
            "OUT OF SCOPE for WP-56 — see the report for what the code requires."
        ),
    )


class PresetPayload(BaseModel):
    """The bundle a preset carries (AD-09.5).

    Validated on the way IN so a malformed preset is a 422 at creation rather
    than a surprise at apply time, and stored as JSONB so adding a block later
    is not a migration.
    """

    actor_id: Optional[UUID] = None
    model_selections: List[PresetModelSelection] = Field(default_factory=list)
    media_defaults: Optional[PresetMediaDefaults] = None
    branding: Optional[PresetBranding] = None
    max_runtime_seconds: Optional[int] = Field(default=None, ge=1)
    target_audience: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    payload: PresetPayload
    owner_scope: str = "user"


class PresetRevise(BaseModel):
    """Create the NEXT version of an existing preset.

    There is no PresetUpdate and there will not be one. Presets are versioned
    rather than mutated (AD-09.5) so a project can record which VERSION produced
    it; an in-place edit would rewrite the provenance of every project already
    created from it.
    """

    description: Optional[str] = None
    payload: PresetPayload


class PresetResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    version: int
    payload: Dict[str, Any]
    is_active: bool
    owner_scope: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PresetApplyRequest(BaseModel):
    """Apply a preset to an existing project."""

    preset_id: UUID


class PresetApplyResult(BaseModel):
    """What applying actually did — itemised, because a preset apply that
    reports plain success is indistinguishable from one that silently skipped
    half the bundle. That shape is the AD-09.3 stub family and this package does
    not add to it.
    """

    project_id: UUID
    preset_id: UUID
    preset_version: int
    applied: List[str] = Field(
        default_factory=list,
        description="Human-readable list of what was written into the project",
    )
    recorded_not_applied: List[str] = Field(
        default_factory=list,
        description=(
            "Bundle entries stored on the project's preset provenance but with "
            "NO consuming code path — branding, chiefly. Named individually so "
            "the operator is never told a logo was applied when nothing renders it."
        ),
    )
