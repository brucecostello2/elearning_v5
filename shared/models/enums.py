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
    #: WP-68 (migration 0041). A numeric or structural transformation the
    #: viewer must see happen, rendered from a template and its parameters
    #: rather than generated from a description.
    MOTION_GRAPHICS = "motion_graphics"


#: THE one list of media_type values, in PostgreSQL enum order.
#:
#: It exists because WP-68 added a fourth value in the migration and in two
#: validators, and MISSED the ORM column's own literal list -- so an INSERT
#: succeeded against the PostgreSQL type while every SELECT afterwards raised
#: `LookupError: 'motion_graphics' is not among the defined enum values`. The
#: row was written and could not be read back. One list, read by the model and
#: by the API schema, is the fix that makes that impossible rather than
#: unlikely.
MEDIA_TYPES: tuple[str, ...] = tuple(m.value for m in MediaType)


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


# ── WP-IVGS-12: the Design Core vocabularies ─────────────────────────
#
# Migrations 0046 and 0048 create CHECK constraints from these exact tuples,
# the ORM types them, the API schemas validate against them, the worker's
# Design Contract JSON Schema closes its enums with them, and the published
# stage-2 prompt lists them to the model. ONE list, six readers.
#
# ⛔ THE PRECEDENT IS WP-68's, AND IT COST AN ACCEPTANCE RUN. `motion_graphics`
# was added to the PostgreSQL type and not to the Python list, so the INSERT
# succeeded and every subsequent SELECT raised. A vocabulary that lives in two
# places is a vocabulary that will disagree with itself. These are NOT enum
# classes: they map onto VARCHAR + CHECK, not onto PostgreSQL ENUM types,
# because a CHECK is alterable in an ordinary migration and a PG enum is not,
# and these vocabularies are young.


class InstructionalEvent(str, enum.Enum):
    """Gagné's Nine Events of Instruction — the scene-sequence skeleton.

    Instructional Design Foundation §3. Declaration order IS arc order and is
    load-bearing: the Merrill cross-check asks whether a design ever leaves the
    first five (a storyboard that never reaches `practice`/`assess` is a
    lecture, not a lesson), and that question is answered by INDEX.
    """

    HOOK = "hook"                    # 1 gain attention
    OBJECTIVE = "objective"          # 2 inform objectives
    RECALL_PRIOR = "recall_prior"    # 3 stimulate recall of prior learning
    PRESENT = "present"              # 4 present content
    GUIDE = "guide"                  # 5 provide guidance
    PRACTICE = "practice"            # 6 elicit practice
    FEEDBACK = "feedback"            # 7 provide feedback
    ASSESS = "assess"                # 8 assess
    TRANSFER = "transfer"            # 9 enhance retention and transfer


INSTRUCTIONAL_EVENTS: tuple[str, ...] = tuple(
    e.value for e in InstructionalEvent
)

#: Events 1-5. A design whose scenes are drawn entirely from this set has
#: demonstrated without ever applying — Merrill's application principle
#: unmet. Foundation §3. Held as a frozenset so the validator's question is a
#: set operation and not a slice nobody re-checks after the enum grows.
DEMONSTRATION_EVENTS: frozenset[str] = frozenset(INSTRUCTIONAL_EVENTS[:5])

#: Events 6-8. At least one of these must appear, and at least one must be
#: reachable from every outcome, or the outcome has no evidence.
APPLICATION_EVENTS: frozenset[str] = frozenset(INSTRUCTIONAL_EVENTS[5:8])

#: The subset that ASSESSES. Serving an outcome is not evidence for it;
#: Foundation §1 stage 2 ("determine acceptable evidence") is the whole point
#: of separating these two questions, and the gate asks them separately.
ASSESSING_EVENTS: frozenset[str] = frozenset({"practice", "assess"})


class BloomLevel(str, enum.Enum):
    """Bloom's taxonomy as revised (Anderson & Krathwohl). Foundation §2.

    Ascending. The level is set by the outcome's BEHAVIOR VERB and it dictates
    both the instruction and the evidence — `apply` is the level that activates
    the worked-example effect (worked → faded → independent), which is what the
    multiplication script already embodies.
    """

    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


BLOOM_LEVELS: tuple[str, ...] = tuple(b.value for b in BloomLevel)


class SceneOrigin(str, enum.Enum):
    """Foundation §6's ``source_refs[] XOR origin:"designed"``.

    SOURCED   the scene works from named character spans of the uploaded
              script — verbatim, or reworded under R1a with `rewrite_of`
              naming the span it reworded.
    DESIGNED  material the integrated intent required and the script lacked.
              Legitimate and expected; it is silence that is the defect class,
              not invention.
    """

    SOURCED = "sourced"
    DESIGNED = "designed"


SCENE_ORIGINS: tuple[str, ...] = tuple(o.value for o in SceneOrigin)


class TranscriptSourceKind(str, enum.Enum):
    """Where a transcript row's text came from. Migration 0046.

    Task 2's mode switch reads this and nothing else: an UPLOADED script is
    EXTRACTED (beats, spans, events — extraction, not rewriting), a GENERATED
    transcript keeps the pre-existing refine-for-readability behaviour.

    UNKNOWN is a real answer and is used honestly: rows whose
    ``original_asset_id`` was cleared by ``ON DELETE SET NULL`` have no evidence
    left, and guessing would put the wrong stage-1 mode on the operator's own
    history.
    """

    UPLOADED = "uploaded"
    GENERATED = "generated"
    UNKNOWN = "unknown"


TRANSCRIPT_SOURCE_KINDS: tuple[str, ...] = tuple(
    k.value for k in TranscriptSourceKind
)
