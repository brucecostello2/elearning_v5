# ruff: noqa: UP042  — (str, enum.Enum) is the house enum style (shared/models/enums.py)
"""
AD-01.5 Model Store — ORM (ARCH-1 Tarball 1).

Five tables on the shared declarative Base (shared.database.Base), mirroring
migration ``0026_ad01_model_store`` exactly:

    models, model_capability_tags, model_node_availability,
    model_approvals, project_model_selections

plus ``model_weight_placements`` (WP-65, migration 0039) -- see that class for
why the byte record could not live in ``model_node_availability``.

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
    BigInteger,
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
    # WP-IVGS-03 — four MBCP runtimes this enum could not name. MBCP's
    # ``models.engine`` is free text (``mbcp_core/models/model.py:33``,
    # ``String(64)``, no CHECK), IVGS's is closed, and nothing keeps the two
    # domains in step; every value below was measured from where MBCP actually
    # writes that column, not from ``adapter_key`` (which is ``tts_coqui``,
    # ``ffmpeg_composition`` etc. and is NOT the engine value).
    #
    # ``tts`` is the runtime name, and deliberately not a model family: ONE
    # adapter (``mbcp_adapters/tts_server.py:56 TtsServerAdapter``, registered
    # under ``runtime_kind "tts"``) serves BOTH XTTS-v2 and Kokoro, exactly as
    # ``comfyui`` serves six families. This is WP-46's rule applied, not
    # relaxed: engine names the RUNTIME. It is the value four live MBCP
    # certificates were 422'd on.
    TTS = "tts"
    # The three remote engine_only talking-head runtimes. MBCP's convention for
    # these is ``engine == adapter_key`` (measured for ``latentsync`` and
    # ``wan22_s2v``, inferred for the other two — see the WP-IVGS-03 report
    # §1.3). Each is its own served engine, not a family on a shared runtime.
    MAGIHUMAN = "magihuman"
    HUMO = "humo"
    WAN22_S2V = "wan22_s2v"
    # WP-IVGS-09 (migration 0044). The runtime `ivgs-motion-renderer` serves.
    #
    # Declared by WP-68 in the endpoint table, the capability registry and the
    # weightless map -- but never in this enum, so the engine existed everywhere
    # except the one place a Model Store row has to name it. Nothing failed
    # because nothing had tried: an engine with no renderer had no row to insert.
    #
    # A RUNTIME, not a family, on the same reasoning as `tts` above: the family
    # is `maths_motion` (client_registry.py:439), and one renderer could later
    # serve a second family of templates without a second engine value.
    #
    # NOT folded into `ffmpeg`. `ffmpeg` is a local binary with no endpoint --
    # `resolve_endpoint("ffmpeg")` correctly refuses, measured 2026-08-28 -- and
    # this is an HTTP service with a URL, a health endpoint and a build ref.
    MOTION_GRAPHICS = "motion_graphics"


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
    """AD-01.5.2 ``project_model_selections.selected_by`` — the PROVENANCE.

    WP-66 added ``PRESET`` (migration 0040). Before it, a selection written by
    applying a library preset (``preset_service.py:246``) was recorded as
    ``MANUAL``, because it goes through ``manual_override`` — so the column that
    exists to say where a binding came from could not distinguish a preset from
    an operator's own choice, and the only trace was a free-text rationale.

    Nothing at dispatch switches on this value (``factory.py`` passes it through
    to the binding and never compares it), so it is purely a provenance record.
    That is the point: WP-60 Task 5 established that a surface presenting mixed
    provenance as one fact is this codebase's recurring defect.
    """

    AUTO = "auto"
    MANUAL = "manual"
    PRESET = "preset"


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

#: Engines that serve ONE model fixed at process start (WP-IVGS-08 Task 4).
#:
#: AD-01 §211: "vLLM serves a fixed model per process and cannot hot-swap
#: arbitrary large models at request time." ⛔ AD-01 §91 and §211 both put
#: **Ollama in the LOADABLE class**, so it is deliberately absent here.
#:
#: The TTS engines are here on MEASUREMENT rather than AD-01's prose:
#: `servers/coqui/server.py:52-56` builds `TTS(XTTS_MODEL)` inside `load()` at
#: container start and `servers/kokoro/server.py:50` does the same. One model
#: per process, fixed at init.
FIXED_AT_INIT_ENGINES: frozenset[ModelEngine] = frozenset({
    ModelEngine.VLLM,
    ModelEngine.COQUI,
    ModelEngine.KOKORO,
    ModelEngine.TTS,
})


def is_dynamically_loadable(engine: "ModelEngine | str | None") -> bool:
    """Whether ``engine`` can load/unload a model on demand (AD-01 §211)."""
    if engine is None:
        return True
    if not isinstance(engine, ModelEngine):
        try:
            engine = ModelEngine(str(getattr(engine, "value", engine)))
        except ValueError:
            return True
    return engine not in FIXED_AT_INIT_ENGINES


def _default_dynamically_loadable(context) -> bool:
    """Derive the flag from the row's own engine at INSERT time.

    WP-IVGS-08 Task 4. Migration 0043 removed the SERVER default, which was an
    unconditional `true` -- so vLLM models claimed to be hot-swappable and the
    planner could pick one the node was not serving.

    ⛔ THIS IS NOT THE OLD DEFAULT MOVED UP A LAYER. The server default answered
    `true` for every row regardless of engine; this computes the correct value
    from the engine the row is actually being written with. An explicit value
    passed by a caller always wins.

    It exists because the flag is a PROPERTY OF THE ENGINE, and two insert
    paths (`ad01_ingest` and the manual registration route) would otherwise each
    have to remember it -- exactly the kind of duplicated knowledge that drifts.
    """
    params = context.get_current_parameters()
    return is_dynamically_loadable(params.get("engine"))


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
        # No `server_default`: migration 0043 dropped it so the DATABASE never
        # invents this value. The Python-side default computes it from the
        # engine -- see `_default_dynamically_loadable`.
        Boolean, nullable=False, default=_default_dynamically_loadable,
    )
    default_params: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    # WP-53, migration 0029. AD-04 seam 1: the DECLARED geometry and sampler
    # rules a request must obey, as MBCP's export bundle has carried them since
    # 2026-08-21 (WP-E32-R). Deliberately NOT folded into `default_params`
    # above -- those are defaults a caller may override, these are constraints a
    # caller must satisfy, and the two are one careless read apart from the
    # sampler failure MBCP documented. Carried opaquely; IVGS does not interpret
    # it as of WP-53.
    request_constraints: Mapped[dict | None] = mapped_column(
        JSONVariant, nullable=True,
    )
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
    weight_placements: Mapped[list[ModelWeightPlacement]] = relationship(
        "ModelWeightPlacement",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin",
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
    attested_by: Mapped[str] = mapped_column(String(256), nullable=False)
    # WP-45 Task 6(e) / migration 0028: TEXT, not VARCHAR(512). A real AD-01
    # vetting reference names the certification, the run, the result, the
    # hardware profile, the measured figures and the report that verified them -
    # WP-46's is 1,912 characters and is a short one. The cap forced whoever
    # pasted it to choose which provenance to delete, which is the one thing an
    # attestation may not do. The schema states a generous bound inline
    # (ApproveIn.MAX_VETTING_REFERENCE) so the refusal is a message, not a
    # truncation.
    vetting_reference: Mapped[str] = mapped_column(Text, nullable=False)
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


# ---------------------------------------------------------------------------
# model_weight_placements  (WP-65, migration 0039)
# ---------------------------------------------------------------------------

class WeightPlacementStatus(str, enum.Enum):
    """Lifecycle of one model's bytes on one node."""

    #: A fetch is in flight. Bytes are in a staging tree, not yet loadable.
    FETCHING = "fetching"
    #: Every manifest file present under the engine's model root, each
    #: SHA-256 verified against the signed manifest.
    VERIFIED = "verified"
    #: A fetch was attempted and refused or failed. ``last_error`` says which.
    FAILED = "failed"
    #: Bytes were verified once and have since been removed or superseded.
    REMOVED = "removed"


class ModelWeightPlacement(Base):
    """WP-65 -- BYTES on a NODE. Fetch-owned, not poller-owned.

    WHY THIS IS A NEW TABLE AND NOT COLUMNS ON ``model_node_availability``
    ---------------------------------------------------------------------
    The two record different facts and have different owners, and merging them
    would make the fetch record self-erasing.

    ``model_node_availability`` is a projection of the GPU scheduler's Redis
    LRU set: ``ivgs-scheduler/scheduler.py:303`` records a model load when a
    JOB runs, ``get_loaded_models`` reads it back
    (``model_concurrency.py:307-320``), ``GET /fleet`` publishes it
    (``ivgs-scheduler/main.py:787``), and
    ``poll_model_node_availability`` reconciles it into PG
    (``ivgs-workers/tasks/periodic_tasks.py:1017``). That poller runs **every
    30 seconds** (``ivgs-workers/celery_app.py:380``) and its reconcile
    unconditionally flips every AVAILABLE row not backed by the current fleet
    snapshot to UNAVAILABLE (``periodic_tasks.py:996-1000``). A fetch result
    written into that table would therefore be erased within half a minute,
    because the poller has no idea bytes exist and would not put them in
    ``desired``.

    Their semantics differ too. Availability answers *"a job loaded this model
    name on this node at some point"* -- the LRU key carries no TTL (measured
    ``ttl=-1``, 2026-08-26) so it never expires, and stale container-hash node
    ids from long-dead workers are still in it. Placement answers *"these
    exact bytes are on this node's disk under the directory this engine loads
    from, and their hashes were checked"*. Both are worth having; only one of
    them is evidence.

    They also disagree about what a node IS. Availability stores the
    scheduler's GPU-scoped id (``node-04:gpu0``); weights live on a node's
    filesystem, not on a GPU, so this table stores ``node-03``.

    Measured on 2026-08-26, the two answers were different for the one model
    the store called available: ``model_node_availability`` said
    ``wan2.2-animate`` was on ``node-04:gpu0``, while the bytes were on
    **node-03** -- ``ivgs-wan-animate-server-node03`` enumerated
    ``Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors`` and
    node-04's ComfyUI mounts only ``checkpoints`` and could not have held it.
    """

    __tablename__ = "model_weight_placements"

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
    #: Fleet node name (``node-03``) -- NOT the scheduler's ``node-03:gpu0``.
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WeightPlacementStatus] = mapped_column(
        _sa_enum(WeightPlacementStatus, "weight_placement_status"),
        nullable=False,
        server_default=WeightPlacementStatus.FETCHING.value,
    )
    #: Host-side directory the bytes were placed in, so an operator can look.
    dest_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: The engine container that mounts ``dest_dir``. Recorded because one
    #: IVGS engine key can have two deployments with different model roots
    #: (``comfyui`` -> node-03's Wan pack and node-04's FLUX ComfyUI).
    engine_container: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: Bundle digest actually fetched and verified. NOT copied from
    #: ``models.weights_checksum``: that column holds whatever MBCP put in
    #: ``bundle_digest``, which for an engine-only certification is the ENGINE
    #: IMAGE digest -- five live rows share one value for that reason.
    bundle_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bytes_on_disk: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Every file's SHA-256 matched the signed manifest.
    checksum_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    #: The manifest HMAC verified. False means the signing key was not
    #: supplied, so the bundle is self-consistent but not proven to be MBCP's.
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    #: The ``reason`` slug of the refusal, when status is FAILED. The admin
    #: surface switches on this to say which of the several different absences
    #: this is.
    last_error_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    #: Who asked for the fetch. An admin username, or a task name.
    fetched_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    model: Mapped[Model] = relationship(back_populates="weight_placements")

    __table_args__ = (
        UniqueConstraint("model_id", "node_id", name="uq_placement_model_node"),
        Index("ix_placement_node", "node_id"),
        Index("ix_placement_status", "status"),
    )
