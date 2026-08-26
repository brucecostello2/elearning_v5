"""
IVGS v5 — Shared Enumerations (§4.1, §6.1)

Every enum here mirrors a PostgreSQL ENUM type created in the Alembic
migrations (0001–0014).  Import these in service/API code instead of
hard-coding string literals.
"""
from __future__ import annotations

import enum


# ── §4.1 Table 1: project_state ──────────────────────────────────────

class ProjectState(str, enum.Enum):
    """14-state finite-state machine for project lifecycle (§6.1 Fig 6-1).

    Thirteen lifecycle states plus ``DELETING`` (WP-59 Task 2, migration 0033),
    which is not a lifecycle state at all: it is a TERMINAL marker meaning
    "destruction has begun and this project is not coming back". It is
    deliberately absent from ``PROJECT_STATE_TRANSITIONS`` in BOTH directions —
    nothing may transition into it through the state machine (the deletion
    service writes the column directly, because reaching it is not a lifecycle
    event) and nothing may transition out of it, so a half-deleted project can
    never be nursed back into a pipeline.
    """
    DRAFT = "DRAFT"
    TRANSCRIPT_REFINEMENT = "TRANSCRIPT_REFINEMENT"
    STORYBOARD_GENERATION = "STORYBOARD_GENERATION"
    MEDIA_GENERATION = "MEDIA_GENERATION"
    MANIFEST_GENERATION = "MANIFEST_GENERATION"
    AUDIO_GENERATION = "AUDIO_GENERATION"
    TALKING_HEAD_RENDER = "TALKING_HEAD_RENDER"
    PROTOTYPE_DRAFT = "PROTOTYPE_DRAFT"
    USER_REVIEW = "USER_REVIEW"
    FINAL_RENDER = "FINAL_RENDER"
    COMPLETE = "COMPLETE"
    LOCALISATION = "LOCALISATION"
    ERROR = "ERROR"
    # WP-59 Task 2. Written directly by ProjectDeletionService before the first
    # row is destroyed, and committed, so a crash mid-delete leaves a project
    # that is VISIBLY mid-delete rather than one that looks alive with missing
    # organs. See PROJECT_STATE_TRANSITIONS below: it appears in no value set.
    DELETING = "DELETING"


# Valid transitions per §6.1 Table 6-1.
# Key = current state, Value = set of allowed next states.
PROJECT_STATE_TRANSITIONS: dict[ProjectState, set[ProjectState]] = {
    ProjectState.DRAFT: {
        ProjectState.TRANSCRIPT_REFINEMENT,
        ProjectState.ERROR,
    },
    ProjectState.TRANSCRIPT_REFINEMENT: {
        ProjectState.STORYBOARD_GENERATION,
        ProjectState.ERROR,
    },
    ProjectState.STORYBOARD_GENERATION: {
        ProjectState.MEDIA_GENERATION,
        ProjectState.ERROR,
    },
    ProjectState.MEDIA_GENERATION: {
        ProjectState.MANIFEST_GENERATION,
        ProjectState.ERROR,
    },
    ProjectState.MANIFEST_GENERATION: {
        ProjectState.AUDIO_GENERATION,
        ProjectState.ERROR,
    },
    ProjectState.AUDIO_GENERATION: {
        ProjectState.TALKING_HEAD_RENDER,
        ProjectState.ERROR,
    },
    ProjectState.TALKING_HEAD_RENDER: {
        ProjectState.PROTOTYPE_DRAFT,
        ProjectState.ERROR,
    },
    ProjectState.PROTOTYPE_DRAFT: {
        ProjectState.USER_REVIEW,
        ProjectState.ERROR,
    },
    ProjectState.USER_REVIEW: {
        ProjectState.FINAL_RENDER,
        ProjectState.STORYBOARD_GENERATION,  # revision loop
        ProjectState.ERROR,
    },
    ProjectState.FINAL_RENDER: {
        ProjectState.COMPLETE,
        ProjectState.LOCALISATION,
        ProjectState.ERROR,
    },
    ProjectState.COMPLETE: {
        ProjectState.LOCALISATION,
    },
    ProjectState.LOCALISATION: {
        ProjectState.COMPLETE,
        ProjectState.ERROR,
    },
    ProjectState.ERROR: {
        # Can return to the state that failed (operator retry).
        ProjectState.DRAFT,
        ProjectState.TRANSCRIPT_REFINEMENT,
        ProjectState.STORYBOARD_GENERATION,
        ProjectState.MEDIA_GENERATION,
        ProjectState.MANIFEST_GENERATION,
        ProjectState.AUDIO_GENERATION,
        ProjectState.TALKING_HEAD_RENDER,
        ProjectState.PROTOTYPE_DRAFT,
        ProjectState.USER_REVIEW,
        ProjectState.FINAL_RENDER,
    },
}


# ── §4.1 Table 6: user_role ──────────────────────────────────────────

class UserRole(str, enum.Enum):
    """RBAC roles per §16.2."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# ── §4.1 Table 5: prompt_type ────────────────────────────────────────

class PromptType(str, enum.Enum):
    """11 prompt types: the ten pipeline stages (§9.1), plus one editor prompt.

    WP-64 Task 3 added ``SCENE_MEDIA_ADAPTATION``, and it is deliberately in
    this enum rather than in a table of its own. It is not a pipeline stage --
    nothing dispatches it, no orchestrator names it -- but it is a versioned,
    published, rollback-able prompt that an operator action renders against a
    model, which is exactly what this table exists to hold. Giving it a second
    home would mean a second publish path, a second history and a second place
    to look when a rewrite reads wrong.
    """
    MASTER = "master"
    TRANSCRIPT_REFINEMENT = "transcript_refinement"
    STORYBOARD_GENERATION = "storyboard_generation"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    ANIMATION_GENERATION = "animation_generation"
    TTS_VOICE = "tts_voice"
    TALKING_HEAD = "talking_head"
    COMPOSITION = "composition"
    TRANSLATION = "translation"
    #: WP-64 Task 3. The Edit Scene modal's "Adapt description for this medium"
    #: action. Not a stage: it is rendered synchronously by the API against the
    #: STORYBOARD binding (Llama), and its output is returned to the operator to
    #: read and edit, never written to the scene by the endpoint itself.
    SCENE_MEDIA_ADAPTATION = "scene_media_adaptation"


# ── §4.1 Table 4: asset_type ─────────────────────────────────────────

class AssetType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    TALKING_HEAD = "talking_head"
    FINAL_RENDER = "final_render"


# ── §4.1 Table 4: storage_tier ───────────────────────────────────────

class StorageTier(str, enum.Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVED = "archived"
    DELETED = "deleted"


# ── §4.1 Table 3: media_type ─────────────────────────────────────────

class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO_CLIP = "video_clip"
    ANIMATION = "animation"


# ── §4.1 Table 7: job_status ─────────────────────────────────────────

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# ── §4.1 Table 7: job_type ───────────────────────────────────────────

class JobType(str, enum.Enum):
    TRANSCRIPT_REFINEMENT = "transcript_refinement"
    STORYBOARD_GENERATION = "storyboard_generation"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    ANIMATION_GENERATION = "animation_generation"
    TTS_AUDIO = "tts_audio"
    TALKING_HEAD_RENDER = "talking_head_render"
    PROTOTYPE_DRAFT = "prototype_draft"
    FINAL_RENDER = "final_render"
    LOCALISATION = "localisation"


# ── §4.1 Table 7: failure_category ───────────────────────────────────

class FailureCategory(str, enum.Enum):
    TRANSIENT = "transient"
    CONFIG = "config"
    EXTERNAL = "external"
    RESOURCE = "resource"
