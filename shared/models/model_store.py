# ruff: noqa: UP042  — (str, enum.Enum) is the house enum style (shared/models/enums.py)
"""
AD-01.5 Model Store — ORM (ARCH-1 Tarball 1).

Five tables on the shared declarative Base (shared.database.Base), mirroring
migration ``0026_ad01_model_store`` exactly:

    models, model_capability_tags, model_node_availability,
    model_approvals, project_model_selections

Lifecycle (AD-01.5.1): CANDIDATE -> APPROVED (attestation-gated, AD-01.7.2)
-> DEPRECATED -> RETIRED. Only APPROVED models are *planner-selectable*;
DEPRECATED models remain servable for selections that already exist.

DB-level invariants live in the migration (partial unique indexes are
PostgreSQL-only); the service layer re-enforces them so SQLite test runs
behave identically:
  * at most one ``is_default`` model per (stage, tier)
  * at most one ``selected_by='auto'`` selection per
    (project_id, stage, tier, scene_id-or-NULL) scope
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite test runs).
JSONVariant = JSONB().with_variant(  # type: ignore[no-untyped-call]
    __import__("sqlalchemy").JSON(), "sqlite"
)


# ---------------------------------------------------------------------------
# Enums (values match the PG ENUM types created in migration 0026)
# ---------------------------------------------------------------------------

class ModelState(str, enum.Enum):
    """AD-01.5.1 lifecycle states."""

    CANDIDATE = "candidate"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ModelTier(str, enum.Enum):
    """AD-01.3 tier — prototype drives Stage 7, production drives Stage 8."""

    PROTOTYPE = "prototype"
    PRODUCTION = "production"
    BOTH = "both"


class ModelStage(str, enum.Enum):
    """Pipeline stage a model serves (AD-01.5.2 ``models.stage``)."""

    TRANSCRIPT_REFINEMENT = "transcript_refinement"
    STORYBOARD_GENERATION = "storyboard_generation"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    ANIMATION_GENERATION = "animation_generation"
    VOICEOVER_TTS = "voiceover_tts"
    TALKING_HEAD = "talking_head"
    COMPOSITION = "composition"
    TRANSLATION = "translation"


class ModelEngine(str, enum.Enum):
    """Serving engine (AD-01.5.2 ``models.engine``)."""

    VLLM = "vllm"
    OLLAMA = "ollama"
    COMFYUI = "comfyui"
    COQUI = "coqui"
    KOKORO = "kokoro"
    COGVIDEOX = "cogvideox"
    WAN21 = "wan21"
    ANIMATEDIFF = "animatediff"
    LATENTSYNC = "latentsync"
    SADTALKER = "sadtalker"
    REMOTION = "remotion"
    FFMPEG = "ffmpeg"


class CapabilityDimension(str, enum.Enum):
    """AD-01.5.2 ``model_capability_tags.dimension``."""

    VISUAL_STYLE = "visual_style"
    SUBJECT_AFFINITY = "subject_affinity"
    MOTION_PROFILE = "motion_profile"
    VOICE_PROFILE = "voice_profile"
    LANGUAGE = "language"
    QUALITY_BIAS = "quality_bias"


class NodeAvailabilityStatus(str, enum.Enum):
    """AD-01.5.2 ``model_node_availability.status``."""

    AVAILABLE = "available"
    LOADING = "loading"
    UNAVAILABLE = "unavailable"


class SelectionSource(str, enum.Enum):
    """AD-01.5.2 ``project_model_selections.selected_by``."""

    AUTO = "auto"
    MANUAL = "manual"


def _sa_enum(py_enum: type[enum.Enum], name: str) -> SAEnum:
    """String-valued SA Enum bound to the pre-created PG type of ``name``.

    ``create_type=False`` on PG (migration 0026 owns the type); on SQLite this
    renders as VARCHAR+CHECK, keeping the test schema portable.
    """
    return SAEnum(
        py_enum,
        name=name,
        create_type=False,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

class Model(Base):
    """AD-01.5.2 ``models`` — the curated registry row."""

    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[ModelStage] = mapped_column(
        _sa_enum(ModelStage, "model_stage"), nullable=False,
    )
    engine: Mapped[ModelEngine] = mapped_column(
        _sa_enum(ModelEngine, "model_engine"), nullable=False,
    )
    tier: Mapped[ModelTier] = mapped_column(
        _sa_enum(ModelTier, "model_tier"), nullable=False,
        server_default=ModelTier.BOTH.value,
    )
    state: Mapped[ModelState] = mapped_column(
        _sa_enum(ModelState, "model_state"), nullable=False,
        server_default=ModelState.CANDIDATE.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    weaknesses: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    weights_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    weights_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    license: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vram_gb: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    dynamically_loadable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    default_params: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"), onupdate=datetime.utcnow,
    )

    capability_tags: Mapped[list[ModelCapabilityTag]] = relationship(
        back_populates="model", cascade="all, delete-orphan", lazy="selectin",
    )
    node_availability: Mapped[list[ModelNodeAvailability]] = relationship(
        back_populates="model", cascade="all, delete-orphan", lazy="selectin",
    )
    approvals: Mapped[list[ModelApproval]] = relationship(
        back_populates="model", cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_models_stage_tier_state", "stage", "tier", "state"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<Model id={self.id} name={self.name!r} stage={self.stage.value} "
            f"engine={self.engine.value} state={self.state.value}>"
        )


# ---------------------------------------------------------------------------
# model_capability_tags
# ---------------------------------------------------------------------------

class ModelCapabilityTag(Base):
    """AD-01.5.2 ``model_capability_tags`` — selector inputs."""

    __tablename__ = "model_capability_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
        default=uuid.uuid4,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
    )
    dimension: Mapped[CapabilityDimension] = mapped_column(
        _sa_enum(CapabilityDimension, "capability_dimension"), nullable=False,
    )
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    model: Mapped[Model] = relationship(back_populates="capability_tags")

    __table_args__ = (
        UniqueConstraint(
            "model_id", "dimension", "value", name="uq_capability_model_dim_value",
        ),
        Index("ix_capability_dimension_value", "dimension", "value"),
    )


# ---------------------------------------------------------------------------
# model_node_availability
# ---------------------------------------------------------------------------

class ModelNodeAvailability(Base):
    """AD-01.5.2 ``model_node_availability`` — poller-maintained residency."""

    __tablename__ = "model_node_availability"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
        default=uuid.uuid4,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[NodeAvailabilityStatus] = mapped_column(
        _sa_enum(NodeAvailabilityStatus, "node_availability_status"),
        nullable=False,
        server_default=NodeAvailabilityStatus.UNAVAILABLE.value,
    )
    served: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    model: Mapped[Model] = relationship(back_populates="node_availability")

    __table_args__ = (
        UniqueConstraint("model_id", "node_id", name="uq_availability_model_node"),
        Index("ix_availability_node", "node_id"),
    )


# ---------------------------------------------------------------------------
# model_approvals
# ---------------------------------------------------------------------------

class ModelApproval(Base):
    """AD-01.5.2 / AD-01.7.2 ``model_approvals`` — the attestation trail."""

    __tablename__ = "model_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
        default=uuid.uuid4,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
    )
    attested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    vetting_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    checklist: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    attested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    model: Mapped[Model] = relationship(back_populates="approvals")


# ---------------------------------------------------------------------------
# project_model_selections
# ---------------------------------------------------------------------------

class ProjectModelSelection(Base):
    """AD-01.5.2 ``project_model_selections`` — the planning-time binding."""

    __tablename__ = "project_model_selections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storyboard_scenes.id", ondelete="CASCADE"),
        nullable=True,
    )
    stage: Mapped[ModelStage] = mapped_column(
        _sa_enum(ModelStage, "model_stage"), nullable=False,
    )
    tier: Mapped[ModelTier] = mapped_column(
        _sa_enum(ModelTier, "model_tier"), nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    selected_by: Mapped[SelectionSource] = mapped_column(
        _sa_enum(SelectionSource, "selection_source"), nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    model: Mapped[Model] = relationship(lazy="joined")

    __table_args__ = (
        Index(
            "ix_selections_scope",
            "project_id", "stage", "tier", "scene_id",
        ),
    )
