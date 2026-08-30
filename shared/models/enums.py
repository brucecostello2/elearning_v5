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

    # ⛔ WP-IVGS-12b, AND THIS IS WP-68's DEFECT REPEATING — MEASURED, NOT
    # THEORISED. Migration 0047 added these two members to the PostgreSQL type
    # and WP-IVGS-12 did not add them HERE. The INSERT succeeded, the rows were
    # published, and the very next SELECT that touched one raised
    #     LookupError: 'storyboard_generation_system' is not among the defined
    #     enum values. Enum name: prompt_type.
    # exactly as `MediaType`'s docstring in `storyboard_scene.py` says it will:
    # "the row was written and could not be read back". The list is load-bearing
    # ON READ.
    #
    # ⚠ It went unnoticed for one package because nothing read those rows back
    # through the ORM until 12b's publisher looked for a version to supersede.
    # The orchestrator reaches them through the API's own filtered query, which
    # is why the WP-IVGS-12 acceptance run still worked.
    TRANSCRIPT_REFINEMENT_SYSTEM = "transcript_refinement_system"
    STORYBOARD_GENERATION_SYSTEM = "storyboard_generation_system"

    # ⛳ WP-IVGS-12h, ADDED IN THE SAME COMMIT AS MIGRATION 0053 — which is the
    # whole point of the paragraph above. design-contract-7's SECOND engine call
    # authors every outcome's independent attempt from the plan and a code-built
    # practice summary, never seeing the practice wording, and it gets its own
    # lineage so it can be rolled back without touching the design prompt.
    ASSESSMENT_AUTHORING_SYSTEM = "assessment_authoring_system"


#: ONE list, the way MEDIA_TYPES is one list. `Prompt.prompt_type` typed its
#: members out by hand and WP-IVGS-12 added two to the database without adding
#: them here — the exact WP-68 shape, and the column's own comment predicted it.
PROMPT_TYPES: tuple[str, ...] = tuple(p.value for p in PromptType)


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

#: ⛔ WP-IVGS-12g. THE EVENTS `scenes[]` MAY DECLARE UNDER design-contract-6 —
#: the nine minus the two that assess. In arc order, because the tuple closes a
#: per-request JSON-Schema enum and the model reads it in the order given.
#:
#: This is the vocabulary split the whole 12c-12f lineage argued its way to.
#: Contract-4 offered ONE array in which sourced and designed material competed
#: for the same slots, and 12f measured that anything excerptable wins: 0
#: designed scenes in 83, and immediate invention on a script with nothing to
#: excerpt. Contract-5 removed the competition for `assess` by putting that one
#: kind in its own required object — and RC-Q9f then measured the SAME defect
#: surviving in the one kind the grammar had left in `scenes[]`: six generations,
#: six `PLAN_ENTRY_UNREALIZED` refusals, all on a promised `practice` never
#: built. It also measured the mirror defect, RC-Q9f limb 2 — with `assess`
#: forced elsewhere the model started writing EXTRA assess scenes into
#: `scenes[]`, and the merge placed the mandated one next to its near-identical
#: twin, posing the same problem twice back to back.
#:
#: ⛳ ONE SPLIT KILLS BOTH. `scenes[]` becomes the EXPOSITORY arc and cannot
#: declare evidence at all; evidence is authored only in the per-outcome
#: evidence sections, where the grammar guarantees existence for BOTH kinds.
#: There is no slot for an unbuilt promise and no slot for a duplicate.
#:
#: ⚠ `feedback` STAYS HERE and that is deliberate. It is an APPLICATION event
#: (6-8) but not an ASSESSING one: it confirms or corrects an attempt rather
#: than being the attempt, so it belongs to the arc the script can supply.
#: Removing it would also make `MERRILL_NO_APPLICATION` unreachable for the
#: wrong reason.
EXPOSITORY_EVENTS: tuple[str, ...] = tuple(
    e for e in INSTRUCTIONAL_EVENTS if e not in ASSESSING_EVENTS
)


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
