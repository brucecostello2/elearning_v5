"""
Activity input/output shapes, mirroring the live stage models field for field.

Why mirrors and not the models themselves
-----------------------------------------

The live models are pydantic v2 and live inside the stage task modules, which
import ``celery_app``, ``WorkerConfig``, ``httpx`` and the engine clients.
Importing them into a workflow worker would drag the Celery coordination layer
into the thing that replaces it, and Temporal's default data converter does not
round-trip pydantic v2 without a custom converter. So these are plain
dataclasses — which the default converter handles natively — carrying the same
field names, the same defaults, and the same nesting.

The mirror is not maintained by good intentions. Every class below declares
``_MIRRORS`` (``module:ClassName``) and ``_EXTRA`` (fields this shape adds on
purpose). ``tests/temporal/test_payload_shapes.py`` imports each named model
and asserts the field sets match exactly once ``_EXTRA`` is removed — so a field
added to ``SceneImageResult`` next month fails a test here rather than silently
diverging.

One reshape, and it is deliberate
---------------------------------

Stage 3 is batch-shaped in Celery: ``Stage3Input`` carries ``scenes:
List[SceneImageInput]`` and one task renders all of them. AD-05 §5.2 makes the
fan-out per-SCENE, so the activity takes one scene and returns one result —
Appendix C's ``render_scene_image(Stage3Input, scene_index) -> SceneMedia``.
The mirror target for the per-scene activities is therefore the *element* model
(``SceneImageInput`` / ``SceneImageResult``), not the batch wrapper.

That reshape is itself the end of a defect class. WP-39's join counted one
report per dispatched STAGE — three reports for eighteen scenes — which is why
a single mislabelled report could strand the whole job. Eighteen scenes now
mean eighteen activity completions, each matched by the server to the
scheduled event that started it.

Image and animation deliberately share these payload types, because they share
one Celery task and one engine and always did. What they no longer share is
their identity: ``ActivityContext.label`` is set from the DagNode, never
defaulted from the task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, FrozenSet, List, Optional


# ---------------------------------------------------------------------------
# The binding every activity carries
# ---------------------------------------------------------------------------

@dataclass
class ActivityContext:
    """
    Who this execution is, in terms the idempotency store can key on.

    ``label`` and ``idempotency_key`` are set by the workflow from the DagNode
    and are never derived inside the activity. That is the WP-39 rule as a type:
    an activity cannot get its own stage identity wrong, because it is not
    asked what it is.
    """

    job_id: str
    project_id: str
    label: str                       # PipelineStage value
    idempotency_key: str             # IdempotencyKey.render()
    queue: str = "default"
    scene_index: Optional[int] = None
    segment_index: Optional[int] = None
    # Set by the activity body from activity.info().attempt, so a result read
    # back from event history says which delivery produced it.
    attempt: int = 0


# ---------------------------------------------------------------------------
# Shared nested shapes
# ---------------------------------------------------------------------------

@dataclass
class JobContext:
    """Mirrors ``PipelineJobContext`` — the context that travels with a dispatch."""

    _MIRRORS: ClassVar[str] = "models.task_result:PipelineJobContext"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    job_id: str = ""
    project_id: str = ""
    project_name: str = ""
    project_description: str = ""
    target_audience: str = ""
    max_runtime_seconds: int = 600
    language_code: str = "en-US"
    priority: str = "normal"
    tier: str = "prototype"
    current_stage: str = ""
    resume_from_stage: Optional[str] = None


@dataclass
class TranscriptRecord:
    _MIRRORS: ClassVar[str] = "models.task_result:TranscriptRecord"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    id: str = ""
    project_id: str = ""
    sequence_order: int = 0
    original_text: str = ""
    refined_text: Optional[str] = None
    language_code: str = "en-US"


@dataclass
class RefinedTranscript:
    _MIRRORS: ClassVar[str] = "models.task_result:RefinedTranscript"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    transcript_id: str = ""
    sequence_order: int = 0
    original_text: str = ""
    refined_text: str = ""
    language_code: str = "en-US"
    refinement_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoryboardScene:
    _MIRRORS: ClassVar[str] = "models.task_result:StoryboardScene"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    scene_index: int = 0
    narration_text: str = ""
    visual_description: str = ""
    media_type: str = "image"
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None
    transition: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Stage 1 — refine_transcript (gpu_llm)
# ---------------------------------------------------------------------------

@dataclass
class RefineTranscriptInput:
    _MIRRORS: ClassVar[str] = "models.task_result:TranscriptRefinementInput"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"ctx"})

    ctx: ActivityContext
    job_context: JobContext = field(default_factory=JobContext)
    transcripts: List[TranscriptRecord] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt_template: str = ""


@dataclass
class RefineTranscriptOutput:
    _MIRRORS: ClassVar[str] = "models.task_result:TranscriptRefinementOutput"
    # `stage` is a property on the pydantic model, not a field; it is a real
    # field here because the workflow sets it from the DagNode label.
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"stage", "idempotency_key", "attempt"})

    job_id: str = ""
    project_id: str = ""
    stage: str = ""
    status: str = "success"
    refined_transcripts: List[RefinedTranscript] = field(default_factory=list)
    total_transcripts: int = 0
    successful_count: int = 0
    failed_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    processing_time_seconds: float = 0.0
    model_used: str = ""
    idempotency_hash: str = ""
    errors: List[Dict[str, Any]] = field(default_factory=list)
    completed_at: Optional[str] = None
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stage 2 — generate_storyboard (gpu_llm)
# ---------------------------------------------------------------------------

@dataclass
class GenerateStoryboardInput:
    _MIRRORS: ClassVar[str] = "models.task_result:StoryboardGenerationInput"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"ctx"})

    ctx: ActivityContext
    job_context: JobContext = field(default_factory=JobContext)
    refined_transcripts: List[RefinedTranscript] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt_template: str = ""
    target_scene_count: int = 0


@dataclass
class GenerateStoryboardOutput:
    _MIRRORS: ClassVar[str] = "models.task_result:StoryboardGenerationOutput"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"stage", "idempotency_key", "attempt"})

    job_id: str = ""
    project_id: str = ""
    stage: str = ""
    status: str = "success"
    scenes: List[StoryboardScene] = field(default_factory=list)
    total_scenes: int = 0
    total_duration_seconds: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    processing_time_seconds: float = 0.0
    model_used: str = ""
    idempotency_hash: str = ""
    scene_ids: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    completed_at: Optional[str] = None
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stage 3 — image / animation branches (gpu_image)
# ---------------------------------------------------------------------------

@dataclass
class RenderSceneImageInput:
    """
    One scene of the image OR animation branch.

    Mirrors ``SceneImageInput``; the batch-level settings a scene needs
    (``visual_style``, ``flux_model``, target size, the two enable flags) come
    across from ``Stage3Input`` as ``_EXTRA`` because a per-scene activity has
    no batch to read them from.
    """

    _MIRRORS: ClassVar[str] = "tasks.stage3_images:SceneImageInput"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset(
        {
            "ctx",
            "project_name",
            "project_description",
            "target_audience",
            "visual_style",
            "flux_model",
            "tier",
            "target_width",
            "target_height",
            "enable_clip_scoring",
            "enable_dedup",
        }
    )

    ctx: ActivityContext
    scene_id: str = ""
    scene_index: int = 0
    visual_description: str = ""
    media_type: str = "image"
    narration_text: str = ""
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None

    # carried down from Stage3Input
    project_name: str = ""
    project_description: str = ""
    target_audience: str = "general"
    visual_style: str = "professional, clean, modern"
    flux_model: str = "flux1-schnell-fp8.safetensors"
    tier: str = "prototype"
    target_width: int = 1920
    target_height: int = 1080
    enable_clip_scoring: bool = True
    enable_dedup: bool = True


@dataclass
class RenderSceneImageOutput:
    _MIRRORS: ClassVar[str] = "tasks.stage3_images:SceneImageResult"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"stage", "idempotency_key", "attempt"})

    scene_id: str = ""
    scene_index: int = 0
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    quality_score: float = 0.0
    quality_decision: str = ""
    clip_score: Optional[float] = None
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    errors: List[str] = field(default_factory=list)
    status: str = "success"

    # The label this scene was rendered UNDER -- image_generation or
    # animation_generation. Never defaulted; set from the DagNode.
    stage: str = ""
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stage 3 — video branch (gpu_video)
# ---------------------------------------------------------------------------

@dataclass
class RenderSceneVideoInput:
    _MIRRORS: ClassVar[str] = "tasks.video_generation_task:SceneVideoInput"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset(
        {"ctx", "project_name", "target_audience", "language_code", "enable_dedup"}
    )

    ctx: ActivityContext
    scene_id: str = ""
    scene_index: int = 0
    visual_description: str = ""
    narration_text: str = ""
    duration_seconds: float = 5.0
    scene_title: Optional[str] = None
    scene_type: str = "broll"
    preferred_model: str = "auto"

    # carried down from VideoGenerationInput
    project_name: str = ""
    target_audience: str = "general"
    language_code: str = "en-US"
    enable_dedup: bool = True


@dataclass
class RenderSceneVideoOutput:
    _MIRRORS: ClassVar[str] = "tasks.video_generation_task:SceneVideoResult"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"stage", "idempotency_key", "attempt"})

    scene_id: str = ""
    scene_index: int = 0
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    quality_score: float = 0.0
    quality_decision: str = ""
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    fallback_level: int = 0
    errors: List[str] = field(default_factory=list)
    status: str = "success"

    stage: str = ""
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stage 4 — build_composition_manifest (default)
# ---------------------------------------------------------------------------
#
# Stage 4 has no pydantic pair at HEAD: tasks/stage4_manifest.py takes a raw
# dict and returns a raw dict (:105, :121-129). These two shapes are the keys
# that dict actually carries, so _MIRRORS is empty and the shape test skips
# them -- stated rather than papered over.

@dataclass
class BuildManifestInput:
    _MIRRORS: ClassVar[str] = ""
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    ctx: ActivityContext
    job_id: str = ""
    project_id: str = ""


@dataclass
class BuildManifestOutput:
    _MIRRORS: ClassVar[str] = ""
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    job_id: str = ""
    project_id: str = ""
    manifest_id: str = ""
    status: str = "locked"
    total_duration_ms: int = 0
    scene_count: int = 0
    stage: str = ""
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stage 5 — generate_voiceover (gpu_tts)
# ---------------------------------------------------------------------------

@dataclass
class SceneVoiceover:
    _MIRRORS: ClassVar[str] = "tasks.stage5_voiceover:SceneVoiceoverInput"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    scene_id: str = ""
    scene_index: int = 0
    narration_text: str = ""
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None
    language_code: str = "en-US"


@dataclass
class SceneVoiceoverResult:
    _MIRRORS: ClassVar[str] = "tasks.stage5_voiceover:SceneVoiceoverResult"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    scene_id: str = ""
    scene_index: int = 0
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 0
    bit_depth: int = 0
    file_size_bytes: int = 0
    quality_score: float = 0.0
    quality_decision: str = ""
    snr_db: Optional[float] = None
    clipping_pct: Optional[float] = None
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    language_code: str = "en-US"
    # WP-42: the text the engine actually spoke, and its provenance. The
    # 2026-08-23 run persisted neither, so a draft whose narration had been
    # silently rewritten could not be traced back to its input.
    synthesized_text: str = ""
    text_source: str = "storyboard"
    narration_estimate_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    status: str = "success"


@dataclass
class GenerateVoiceoverInput:
    # `Stage4Input` in stage5_voiceover.py -- the file is stage 5, the class is
    # named 4, and the Celery task registers as tasks.stage4_voiceover.*. All
    # three disagree and all three are load-bearing today.
    _MIRRORS: ClassVar[str] = "tasks.stage5_voiceover:Stage4Input"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"ctx"})

    ctx: ActivityContext
    job_id: str = ""
    project_id: str = ""
    project_name: str = ""
    target_audience: str = "general"
    language_code: str = "en-US"
    scenes: List[SceneVoiceover] = field(default_factory=list)
    speaker_wav_path: Optional[str] = None
    # `speaker_wav_data: Optional[bytes]` on the live model. Raw bytes do not
    # belong in an event history -- Temporal stores every activity input
    # verbatim and forever. The reference is carried; the audio is not.
    speaker_wav_data: Optional[str] = None
    optimize_text: bool = True
    enable_dedup: bool = True
    tts_temperature: float = 0.75
    tts_speed: float = 1.0
    tier: str = "prototype"


@dataclass
class GenerateVoiceoverOutput:
    _MIRRORS: ClassVar[str] = "tasks.stage5_voiceover:Stage4Output"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"idempotency_key", "attempt"})

    job_id: str = ""
    project_id: str = ""
    stage: str = ""
    status: str = "success"
    scene_results: List[SceneVoiceoverResult] = field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    total_generation_time_seconds: float = 0.0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    completed_at: Optional[str] = None
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stage 6 — render_talking_head (gpu_talking_head)
# ---------------------------------------------------------------------------

@dataclass
class SceneAudioRef:
    _MIRRORS: ClassVar[str] = "tasks.talking_head_task:SceneAudioRef"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    scene_id: str = ""
    scene_index: int = 0
    audio_asset_id: str = ""
    duration_seconds: float = 0.0


@dataclass
class RenderTalkingHeadInput:
    _MIRRORS: ClassVar[str] = "tasks.talking_head_task:Stage6Input"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"ctx"})

    ctx: ActivityContext
    job_id: str = ""
    project_id: str = ""
    project_name: str = ""
    language_code: str = "en-US"
    tier: str = "prototype"
    reference_clip_asset_id: Optional[str] = None
    scene_audio_refs: List[SceneAudioRef] = field(default_factory=list)
    output_width: int = 1920
    output_height: int = 1080
    output_fps: int = 30
    alignment_threshold: float = 0.85
    latentsync_mode: str = "full_frame"
    pip_position: str = "bottom_right"
    pip_scale: float = 0.25
    enable_face_enhance: bool = True
    lip_sync_strength: float = 1.0


@dataclass
class RenderTalkingHeadOutput:
    _MIRRORS: ClassVar[str] = "tasks.talking_head_task:Stage6Output"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"idempotency_key", "attempt"})

    job_id: str = ""
    project_id: str = ""
    stage: str = ""
    status: str = "success"
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    # Not a lip-sync measurement -- ledger P1.4e. Carried with its two
    # companions so the mirror cannot be read as one either.
    alignment_score: float = 0.0
    alignment_scored: bool = False
    av_drift_seconds: float = 0.0
    model_used: str = ""
    render_mode: str = ""
    generation_time_seconds: float = 0.0
    corruption_check_passed: bool = False
    fallback_used: bool = False
    errors: List[str] = field(default_factory=list)
    completed_at: Optional[str] = None
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# Stages 7 and 8 — composition
# ---------------------------------------------------------------------------

@dataclass
class ManifestSceneAsset:
    _MIRRORS: ClassVar[str] = "tasks.stage7_prototype_draft:ManifestSceneAsset"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    asset_id: str = ""
    asset_type: str = ""
    seaweedfs_path: str = ""
    duration_seconds: float = 0.0
    content_hash: str = ""


@dataclass
class ManifestScene:
    _MIRRORS: ClassVar[str] = "tasks.stage7_prototype_draft:ManifestScene"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    scene_id: str = ""
    scene_index: int = 0
    scene_title: str = ""
    narration_text: str = ""
    duration_seconds: float = 10.0
    media_type: str = "image"
    background_asset: Optional[ManifestSceneAsset] = None
    audio_asset: Optional[ManifestSceneAsset] = None
    talking_head_position: str = "bottom_right"
    talking_head_scale: float = 0.25
    show_lower_third: bool = True
    caption_timestamps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AssembleDraftInput:
    _MIRRORS: ClassVar[str] = "tasks.stage7_prototype_draft:Stage7Input"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"ctx"})

    ctx: ActivityContext
    job_id: str = ""
    project_id: str = ""
    project_name: str = ""
    language_code: str = "en-US"
    manifest_id: str = ""
    talking_head_asset_id: Optional[str] = None
    scenes: List[ManifestScene] = field(default_factory=list)
    enable_lower_thirds: bool = True
    enable_captions: bool = True
    enable_talking_head: bool = True


@dataclass
class AssembleDraftOutput:
    _MIRRORS: ClassVar[str] = "tasks.stage7_prototype_draft:Stage7Output"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"idempotency_key", "attempt"})

    job_id: str = ""
    project_id: str = ""
    stage: str = ""
    status: str = "success"
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 30
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    scene_count: int = 0
    scenes_composed: int = 0
    scenes_failed: int = 0
    render_time_seconds: float = 0.0
    corruption_check_passed: bool = False
    errors: List[str] = field(default_factory=list)
    completed_at: Optional[str] = None
    idempotency_key: str = ""
    attempt: int = 0


@dataclass
class FinalRenderAsset:
    _MIRRORS: ClassVar[str] = "tasks.stage8_final_render:FinalRenderAsset"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    asset_id: str = ""
    asset_type: str = ""
    seaweedfs_path: str = ""
    content_hash: str = ""


@dataclass
class FinalRenderScene:
    _MIRRORS: ClassVar[str] = "tasks.stage8_final_render:FinalRenderScene"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    scene_id: str = ""
    scene_index: int = 0
    scene_title: str = ""
    narration_text: str = ""
    duration_seconds: float = 10.0
    media_type: str = "image"
    background_asset: Optional[FinalRenderAsset] = None
    audio_asset: Optional[FinalRenderAsset] = None
    talking_head_position: str = "bottom_right"
    talking_head_scale: float = 0.25
    show_lower_third: bool = True
    caption_timestamps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SegmentRenderResult:
    _MIRRORS: ClassVar[str] = "tasks.stage8_final_render:SegmentRenderResult"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    segment_id: str = ""
    segment_index: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    output_path: str = ""
    sha256_hash: str = ""
    file_size_bytes: int = 0
    render_time_seconds: float = 0.0
    status: str = "pending"
    retry_count: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class ProfileRenderResult:
    _MIRRORS: ClassVar[str] = "tasks.stage8_final_render:ProfileRenderResult"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    profile: str = ""
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 30
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    render_time_seconds: float = 0.0
    segment_count: int = 0
    segments_succeeded: int = 0
    segments_failed: int = 0
    corruption_check_passed: bool = False
    status: str = "success"


@dataclass
class RenderFinalInput:
    _MIRRORS: ClassVar[str] = "tasks.stage8_final_render:Stage8Input"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"ctx"})

    ctx: ActivityContext
    job_id: str = ""
    project_id: str = ""
    project_name: str = ""
    language_code: str = "en-US"
    manifest_id: str = ""
    talking_head_asset_id: Optional[str] = None
    scenes: List[FinalRenderScene] = field(default_factory=list)
    render_profiles: List[str] = field(default_factory=lambda: ["1080p", "4k"])
    enable_lower_thirds: bool = True
    enable_captions: bool = True
    enable_talking_head: bool = True
    max_segment_duration: float = 30.0
    min_segment_duration: float = 10.0
    max_segment_retries: int = 2


@dataclass
class RenderFinalOutput:
    _MIRRORS: ClassVar[str] = "tasks.stage8_final_render:Stage8Output"
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset({"idempotency_key", "attempt"})

    job_id: str = ""
    project_id: str = ""
    stage: str = ""
    status: str = "success"
    profile_results: List[ProfileRenderResult] = field(default_factory=list)
    total_render_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    completed_at: Optional[str] = None
    idempotency_key: str = ""
    attempt: int = 0


# ---------------------------------------------------------------------------
# GPU reservation (AD-05 §6)
# ---------------------------------------------------------------------------

@dataclass
class ReservationRequest:
    _MIRRORS: ClassVar[str] = ""
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    ctx: ActivityContext
    stage_label: str = ""
    queue: str = "default"
    vram_mb: int = 0


@dataclass
class Reservation:
    _MIRRORS: ClassVar[str] = ""
    _EXTRA: ClassVar[FrozenSet[str]] = frozenset()

    reservation_id: str = ""
    node_id: str = ""
    granted: bool = False
    # D4's fail-open, made explicit and reportable instead of silent. Set when
    # ivgs-scheduler could not grant and the stage proceeded unreserved.
    fail_open: bool = False
    detail: str = ""


# Every mirrored shape, for the drift test to iterate.
MIRRORED_PAYLOADS = (
    JobContext,
    TranscriptRecord,
    RefinedTranscript,
    StoryboardScene,
    RefineTranscriptInput,
    RefineTranscriptOutput,
    GenerateStoryboardInput,
    GenerateStoryboardOutput,
    RenderSceneImageInput,
    RenderSceneImageOutput,
    RenderSceneVideoInput,
    RenderSceneVideoOutput,
    BuildManifestInput,
    BuildManifestOutput,
    SceneVoiceover,
    SceneVoiceoverResult,
    GenerateVoiceoverInput,
    GenerateVoiceoverOutput,
    SceneAudioRef,
    RenderTalkingHeadInput,
    RenderTalkingHeadOutput,
    ManifestSceneAsset,
    ManifestScene,
    AssembleDraftInput,
    AssembleDraftOutput,
    FinalRenderAsset,
    FinalRenderScene,
    SegmentRenderResult,
    ProfileRenderResult,
    RenderFinalInput,
    RenderFinalOutput,
    ReservationRequest,
    Reservation,
)
