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
    """13-state finite-state machine for project lifecycle (§6.1 Fig 6-1)."""
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
    """10 prompt types covering every pipeline stage (§9.1)."""
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
