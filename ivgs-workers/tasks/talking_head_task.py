"""
IVGS v5 — Stage 6: Talking Head Rendering Task
===================================================

Pipeline Stage 6 per §6.1:
- Input: User-uploaded talking head reference clip + per-scene narration audio (segment-based)
- Primary: the AD-01-selected talking_head model, resolved per (project, tier)
  through the ARCH-1 provider factory. Default today is LatentSync on node-04
  (its alignment_score is a constant, not a measurement - see ledger P1.4e).
  Swapping the production head is a GUI
  action in /admin/models — never a code change (AD-01.1).
- Fallback: SadTalker on node-04, still engine-direct. The shared SadTalker
  provider requires a per-scene still image, which this whole-project stage
  does not have, so the fallback is NOT yet selection-driven. See
  WP-02-ORCH6 F2.
- Output: Full lip-synced talking head video at /ivgs/talking-heads/{project_id}/{language_code}.mp4
- Timeout: 3600 seconds (wraps the per-segment render loop)
- Retry: 2 retries with 30s→90s backoff

Processing:
    1. Resolve the AD-01 binding and build the provider (fails the task loudly
       if no model is selected or default for (talking_head, tier))
    2. Download user-uploaded reference clip from SeaweedFS
    3. Concatenate all scene audio files into a single audio track
    4. Acquire GPU reservation for the selected model (VRAM from its binding)
    5. Render one lip-synced segment per scene via the provider, then concat
       (bounded memory — a whole-scene render OOM'd the engine)
    6. Record quality signals. NOTE: no metric here measures lip-sync
       articulation - the engine's alignment_score is a constant and the
       validator's score is A/V duration agreement. The one real signal
       is av_drift_seconds. Ledger P1.4e.
    7. On render failure: fallback to SadTalker (8GB VRAM). NOT triggered
       by a low score - that gate was non-functional and is disabled.
    8. Run corruption detection (§11.2)
    9. Upload to SeaweedFS
    10. Update project talking_head_asset_id
    11. Save checkpoint and dispatch stage completion
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog
from pydantic import BaseModel, Field

from uuid import UUID

from celery_app import IVGSBaseTask, celery_app
from clients.ffmpeg_client import FFmpegClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from providers import ensure_registered  # registers engine builders (ARCH-1)
from shared.providers import (
    ModelBinding,
    TalkingHeadParams,
    TalkingHeadProvider,
    TalkingHeadResult,
    build_provider,
    get_binding,
)
from utils.error_handler import save_checkpoint, update_job_status
from utils.gpu_utils import acquire_gpu_reservation, release_gpu_reservation
from utils.media_converter import compute_asset_sha256
from validators.lipsync_validator import LipsyncValidator
from validators.corruption_detector import CorruptionDetector

logger = structlog.get_logger("ivgs.stage6.talking_head")

# Segment-based render config (spec 6.1): render in per-scene segments, splitting any
# scene longer than MAX_SEGMENT_SECONDS into equal sub-renders so no single render
# loads more than ~one segment of frames at once (a whole long-scene render OOM'd the
# engine). Total length scales by segment count, not per-render RAM.
MAX_SEGMENT_RETRIES = 2
MAX_SEGMENT_SECONDS = 30.0

# Render modes the talking-head engines accept. Mirrors the engine-side enum;
# kept as plain strings here so this task carries no engine import (ARCH-1).
# An unrecognised mode falls back to full_frame, preserving the pre-ARCH-1
# behaviour of this task rather than letting the provider raise.
VALID_RENDER_MODES = ("full_frame", "pip", "chroma_key")
DEFAULT_RENDER_MODE = "full_frame"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SceneAudioRef(BaseModel):
    """Reference to a scene audio asset for concatenation."""
    scene_id: str
    scene_index: int
    audio_asset_id: str
    duration_seconds: float


class Stage6Input(BaseModel):
    """Input for Stage 6: Talking Head Rendering."""
    job_id: str
    project_id: str
    project_name: str = ""
    language_code: str = "en-US"
    # AD-01 selection tier. Stage 6 renders ONCE and the single asset it
    # produces is consumed by both Stage 7 (draft) and Stage 8 (final), so
    # there is no per-tier render today and this is a constant in practice.
    # AD-01.13 criterion 5 ("prototype and production models applied to draft
    # and final respectively") therefore remains open — see WP-02-ORCH6 F3.
    tier: str = "prototype"
    reference_clip_asset_id: Optional[str] = None
    scene_audio_refs: List[SceneAudioRef] = Field(default_factory=list)
    output_width: int = 1920
    output_height: int = 1080
    output_fps: int = 30
    alignment_threshold: float = 0.85
    latentsync_mode: str = "full_frame"
    pip_position: str = "bottom_right"
    pip_scale: float = 0.25
    enable_face_enhance: bool = True
    lip_sync_strength: float = 1.0


class Stage6Output(BaseModel):
    """Output from Stage 6: Talking Head Rendering."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.TALKING_HEAD_RENDER.value
    status: StageStatus = StageStatus.SUCCESS
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    # NOTE ON alignment_score: this is NOT a lip-sync measurement.
    # It is lipsync_validator's A/V duration agreement (1 - drift/audio_len),
    # whose base term saturates at 1.0. Ledger P1.4e. The two fields below
    # exist so a reader cannot mistake it for a quality signal.
    alignment_score: float = 0.0
    # False whenever the engine reported "scored": False - i.e. its
    # alignment_score is the DEFAULT_ALIGNMENT constant, not a measurement.
    alignment_scored: bool = False
    # The one genuinely measured quality signal at this stage: absolute
    # video-minus-audio duration drift. Gated by av_drift_seconds in
    # quality_thresholds.yaml. Lower is better.
    av_drift_seconds: float = 0.0
    model_used: str = ""
    render_mode: str = ""
    generation_time_seconds: float = 0.0
    corruption_check_passed: bool = False
    fallback_used: bool = False
    errors: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _download_asset(asset_id: str, config: WorkerConfig) -> bytes:
    """Download asset data from SeaweedFS via Pipeline API."""
    async with httpx.AsyncClient(
        timeout=120.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.get(
            f"{config.pipeline_api.full_base_url}/assets/{asset_id}/download",
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Asset download failed (ID={asset_id}): HTTP {resp.status_code}")
        return resp.content


async def _upload_asset(
    project_id: str,
    language_code: str,
    data: bytes,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Upload talking head video to SeaweedFS."""
    async with httpx.AsyncClient(
        timeout=180.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets/upload",
            files={
                "file": (
                    f"talking_head_{language_code}.mp4",
                    data,
                    "video/mp4",
                ),
            },
            data={
                "asset_type": "talking_head",
                "language_code": language_code,
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Asset upload failed: HTTP {resp.status_code}")
        return resp.json()


async def _concatenate_scene_audio(
    scene_audio_refs: List[SceneAudioRef],
    config: WorkerConfig,
    temp_dir: str,
) -> str:
    """Download all scene audio files and concatenate into a single track."""
    ffmpeg = FFmpegClient(temp_dir=temp_dir)
    audio_paths: List[str] = []

    for ref in sorted(scene_audio_refs, key=lambda r: r.scene_index):
        audio_data = await _download_asset(ref.audio_asset_id, config)
        audio_path = os.path.join(temp_dir, f"scene_{ref.scene_index:04d}.wav")
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        audio_paths.append(audio_path)

    # Concatenate all audio into a single WAV
    concat_path = os.path.join(temp_dir, "full_audio.wav")
    ffmpeg.concat_audio(audio_paths, concat_path)

    return concat_path


# IVGS-5: engine-side face detection raises a bare RuntimeError("Face not
# detected"). Matched on message because a typed exception would require
# server.py, whose image digest is pinned by MBCP certificate provenance
# (deferred with IVGS-3/4). Deliberately narrow - a broad match would
# suppress retries for genuinely transient errors.
_FACE_FAILURE_MARKERS = ("face not detected", "no face detected", "face detection failed")


def _is_face_detection_failure(err: BaseException) -> bool:
    """True if this error means the reference clip has no usable face."""
    text = str(err).lower()
    return any(marker in text for marker in _FACE_FAILURE_MARKERS)


def _resolve_render_mode(requested: str) -> str:
    """Normalise the requested render mode, defaulting to full_frame."""
    return requested if requested in VALID_RENDER_MODES else DEFAULT_RENDER_MODE


async def _render_segment(
    provider: TalkingHeadProvider,
    reference_clip_data: bytes,
    audio_data: bytes,
    task_input: Stage6Input,
) -> TalkingHeadResult:
    """Render one lip-synced segment through the AD-01-selected provider.

    ARCH-1: no engine identity here. The provider was built from the binding
    resolved once per job; this function only maps task parameters onto the
    shared TalkingHeadParams contract.

    Note there is no ``scene_image_data``: Stage 6 renders the presenter from
    the reference clip against narration audio, and Stage 7/8 composite the
    result as a single continuous timeline overlay (AD-03 Pillar 2). Providers
    that require a per-scene still cannot serve this stage — see WP-02-ORCH6 F2.
    """
    params = TalkingHeadParams(
        voiceover_audio_data=audio_data,
        reference_clip_data=reference_clip_data,
        mode=_resolve_render_mode(task_input.latentsync_mode),
        output_width=task_input.output_width,
        output_height=task_input.output_height,
        output_fps=task_input.output_fps,
        face_enhance=task_input.enable_face_enhance,
        lip_sync_strength=task_input.lip_sync_strength,
        pip_position=task_input.pip_position,
        pip_scale=task_input.pip_scale,
        alignment_threshold=task_input.alignment_threshold,
    )
    return await provider.render(params)


async def _render_with_sadtalker(
    reference_clip_path: str,
    audio_path: str,
    task_input: Stage6Input,
    config: WorkerConfig,
    temp_dir: str,
) -> bytes:
    """Render lip-synced video using SadTalker (fallback)."""
    sadtalker_config = config.get_model_config("sadtalker")
    base_url = sadtalker_config.get("api_url", "http://node-04:8301")

    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(reference_clip_path, "rb") as ref_f, open(audio_path, "rb") as audio_f:
            resp = await client.post(
                f"{base_url}/generate",
                files={
                    "reference_video": ("reference.mp4", ref_f, "video/mp4"),
                    "audio": ("audio.wav", audio_f, "audio/wav"),
                },
                data={
                    "width": str(task_input.output_width),
                    "height": str(task_input.output_height),
                    "fps": str(task_input.output_fps),
                },
                timeout=300.0,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"SadTalker render failed: HTTP {resp.status_code}")

        return resp.content


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.talking_head_task.render_talking_head",
    queue="gpu_talking_head",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=3600,
    time_limit=3900,
    acks_late=True,
    reject_on_worker_lost=True,
)
def render_talking_head(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task: render full talking head video.

    1. Download reference clip and concatenate audio
    2. Render with the AD-01-selected provider (primary)
    3. Validate alignment score
    4. Fallback to SadTalker if needed
    5. Run corruption detection
    6. Upload result
    """
    config = WorkerConfig()

    try:
        task_input = Stage6Input(**task_input_dict)
    except Exception as e:
        logger.error("stage6_input_error", error=str(e))
        raise ValueError(f"Invalid Stage 6 input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    log = logger.bind(job_id=job_id, project_id=project_id)
    log.info("stage6_talking_head_starting")

    update_job_status(job_id, "running", stage=PipelineStage.TALKING_HEAD_RENDER.value)

    output = Stage6Output(job_id=job_id, project_id=project_id)

    # Stage 6 is optional: skip cleanly when no presenter/reference clip was uploaded.
    # Absent a talking-head source there is nothing to lip-sync, so advance to prototype_draft.
    if not task_input.reference_clip_asset_id:
        log.info("stage6_skipped_no_reference_clip")
        output.status = StageStatus.SUCCESS
        output.model_used = "skipped"
        output.completed_at = datetime.now(timezone.utc)
        skip_dict = output.model_dump(mode="json")
        celery_app.send_task(
            "tasks.pipeline_orchestrator_v2.handle_stage_completion",
            kwargs={"stage_output_dict": skip_dict},
            queue="default",
        )
        return skip_dict

    # ARCH-1 / AD-01: resolve the model selection for this (project, tier) and
    # build the provider. No engine identity is hard-coded in this task, so a
    # head-model swap is a GUI action (/admin/models set-default), not a code
    # change — which is the guarantee AD-01.1 exists to provide.
    #
    # Deliberately OUTSIDE the try/finally below: a SelectionError must
    # propagate and fail the Celery task, not be converted into a returned
    # {'status': 'failed'} that Celery records as SUCCESS (WP-00 register
    # instance 6). Resolving here also means nothing is allocated yet, so a
    # selection failure cannot leak the temp directory.
    ensure_registered()
    binding_loop = asyncio.new_event_loop()
    try:
        binding: ModelBinding = binding_loop.run_until_complete(
            get_binding(
                "talking_head",
                project_id=UUID(project_id),
                tier=task_input.tier,
            )
        )
    finally:
        binding_loop.close()

    log = log.bind(
        model=binding.name,
        engine=binding.engine,
        endpoint=binding.endpoint,
        tier=binding.tier,
    )
    log.info("stage6_model_bound", binding=binding.describe())

    provider: TalkingHeadProvider = build_provider(
        binding,
        timeout=config.timeouts.latentsync_timeout,
        alignment_threshold=task_input.alignment_threshold,
    )

    temp_dir = tempfile.mkdtemp(prefix="ivgs_stage6_")
    reservation = None

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Download reference clip
        reference_data = loop.run_until_complete(
            _download_asset(task_input.reference_clip_asset_id, config)
        )
        reference_path = os.path.join(temp_dir, "reference.mp4")
        with open(reference_path, "wb") as f:
            f.write(reference_data)

        # 2. Concatenate all scene audio
        audio_path = loop.run_until_complete(
            _concatenate_scene_audio(
                task_input.scene_audio_refs, config, temp_dir,
            )
        )

        # 3. Acquire GPU reservation for the SELECTED model (binding-driven).
        # vram_requirement_mb comes from the binding, falling back to the
        # engine default in providers/talking_head.py — 16384 for latentsync,
        # i.e. unchanged from the previous hardcoded value.
        try:
            reservation = acquire_gpu_reservation(
                job_id=job_id,
                model_name=binding.name,
                vram_requirement_mb=provider.vram_requirement_mb(),
            )
        except Exception as e:
            log.warning("gpu_reservation_failed", error=str(e))

        start_time = time.monotonic()
        video_data: Optional[bytes] = None
        alignment_score = 0.0
        model_used = ""
        fallback_used = False

        # 4. Render with the AD-01-selected provider (primary)
        try:
            # Segment-based render (spec 6.1): render in per-scene segments, splitting any
            # scene longer than MAX_SEGMENT_SECONDS into equal sub-renders. Each render
            # stays bounded (~one segment of frames) rather than the whole narration,
            # which OOM'd node-04. Length scales by segment count, not per-render RAM.
            sorted_refs = sorted(
                task_input.scene_audio_refs, key=lambda r: r.scene_index
            )
            if not sorted_refs:
                raise RuntimeError("No scene audio refs to render")

            # Build the ordered render-piece list. A scene whose audio exceeds
            # MAX_SEGMENT_SECONDS is sliced into ceil(dur/MAX) equal pieces at offsets we
            # control (no SceneRef ambiguity); the last piece runs to EOF so they tile.
            ffmpeg_seg = FFmpegClient(temp_dir=temp_dir)
            render_pieces: List[Dict[str, Any]] = []
            for ref in sorted_refs:
                scene_audio = os.path.join(
                    temp_dir, f"scene_{ref.scene_index:04d}.wav"
                )
                try:
                    scene_dur = float(
                        ffmpeg_seg.probe(scene_audio).get("format", {}).get("duration", 0.0)
                    )
                except Exception:
                    scene_dur = 0.0
                if scene_dur <= MAX_SEGMENT_SECONDS or scene_dur <= 0.0:
                    render_pieces.append(
                        {"audio": scene_audio, "scene_index": ref.scene_index, "part": 0}
                    )
                else:
                    n_parts = math.ceil(scene_dur / MAX_SEGMENT_SECONDS)
                    piece_dur = scene_dur / n_parts
                    for p in range(n_parts):
                        part_audio = os.path.join(
                            temp_dir, f"scene_{ref.scene_index:04d}_part{p:02d}.wav"
                        )
                        slice_cmd = [
                            ffmpeg_seg._ffmpeg, "-y",
                            "-ss", f"{p * piece_dur:.3f}", "-i", scene_audio,
                        ]
                        if p < n_parts - 1:
                            slice_cmd += ["-t", f"{piece_dur:.3f}"]
                        slice_cmd += ["-c:a", "pcm_s16le", part_audio]
                        ffmpeg_seg._run_ffmpeg(slice_cmd, timeout=120.0)
                        render_pieces.append(
                            {"audio": part_audio, "scene_index": ref.scene_index, "part": p}
                        )
                    log.info(
                        "scene_split",
                        scene_index=ref.scene_index,
                        duration_s=round(scene_dur, 1),
                        parts=n_parts,
                    )

            log.info(
                "render_plan",
                scenes=len(sorted_refs),
                pieces=len(render_pieces),
                max_segment_s=MAX_SEGMENT_SECONDS,
            )

            seg_clip_paths: List[str] = []
            seg_checksums: Dict[str, str] = {}
            seg_alignments: List[float] = []

            # The reference clip is identical for every segment; read it once
            # rather than re-reading the file per segment per attempt.
            with open(reference_path, "rb") as _ref_f:
                reference_clip_bytes = _ref_f.read()

            for seg_idx, piece in enumerate(render_pieces):
                seg_audio_path = piece["audio"]
                with open(seg_audio_path, "rb") as _seg_af:
                    seg_audio_bytes = _seg_af.read()
                seg_result = None
                last_seg_err = None
                for attempt in range(MAX_SEGMENT_RETRIES + 1):
                    try:
                        seg_result = loop.run_until_complete(
                            _render_segment(
                                provider, reference_clip_bytes,
                                seg_audio_bytes, task_input,
                            )
                        )
                        break
                    except Exception as seg_err:
                        # IVGS-5: face detection failure is DETERMINISTIC - the
                        # same reference clip fails identically every time, so
                        # retrying it is pure waste. Without this, a clip with
                        # no detectable face burns 3 attempts x N segments and
                        # then falls back to SadTalker, which cannot serve this
                        # stage at all (it requires a per-scene still Stage 6
                        # never has - ledger P1.0a). Abort immediately instead,
                        # with a message naming the cause and the remedy.
                        #
                        # Detected by message rather than by exception type
                        # because the engine raises a bare RuntimeError; a
                        # typed error needs server.py, which is deferred with
                        # IVGS-3/4 (image digest is pinned by MBCP provenance).
                        if _is_face_detection_failure(seg_err):
                            log.error(
                                "reference_clip_no_face_detected",
                                segment_index=seg_idx,
                                scene_index=piece["scene_index"],
                                attempt=attempt,
                                error=str(seg_err),
                                remedy=(
                                    "re-upload a reference clip with a clear, "
                                    "front-facing face visible throughout"
                                ),
                            )
                            raise RuntimeError(
                                "Stage 6 aborted: no face detected in the "
                                "uploaded reference clip "
                                f"(asset {task_input.reference_clip_asset_id}). "
                                "Re-upload a clip with a clear, front-facing "
                                "face visible throughout. This is an input "
                                "problem, not a render failure - retrying will "
                                "not help."
                            ) from seg_err
                        last_seg_err = seg_err
                        log.warning(
                            "segment_render_attempt_failed",
                            segment_index=seg_idx,
                            scene_index=piece["scene_index"],
                            part=piece["part"],
                            attempt=attempt,
                            error=str(seg_err),
                        )
                if seg_result is None:
                    raise RuntimeError(
                        f"Segment {seg_idx} (scene {piece['scene_index']} "
                        f"part {piece['part']}) failed after "
                        f"{MAX_SEGMENT_RETRIES + 1} attempts: {last_seg_err}"
                    )

                seg_clip_path = os.path.join(
                    temp_dir, f"segment_{seg_idx:04d}.mp4"
                )
                with open(seg_clip_path, "wb") as _seg_f:
                    _seg_f.write(seg_result.video_data)
                seg_checksums[seg_clip_path] = compute_asset_sha256(
                    seg_result.video_data
                )
                seg_clip_paths.append(seg_clip_path)
                seg_alignments.append(seg_result.alignment_score)

                # Render geometry is uniform across segments; capture once.
                if seg_idx == 0:
                    output.width = seg_result.width
                    output.height = seg_result.height
                    output.fps = seg_result.fps

                log.info(
                    "segment_render_complete",
                    segment_index=seg_idx,
                    scene_index=piece["scene_index"],
                    part=piece["part"],
                    alignment_score=seg_result.alignment_score,
                    segments_total=len(render_pieces),
                )

            # Assemble per-scene clips via checksum-verified concat demuxer.
            ffmpeg_concat = FFmpegClient(temp_dir=temp_dir)
            concat_output_path = os.path.join(
                temp_dir, "talking_head_concat.mp4"
            )
            concat_result = ffmpeg_concat.concat_segments(
                segment_paths=seg_clip_paths,
                output_path=concat_output_path,
                verify_checksums=seg_checksums,
                timeout=600.0,
            )
            with open(concat_output_path, "rb") as _concat_f:
                video_data = _concat_f.read()

            output.duration_seconds = concat_result.duration_seconds
            alignment_score = (
                round(sum(seg_alignments) / len(seg_alignments), 4)
                if seg_alignments else 0.0
            )
            # AD-01: attribute the render to the SELECTED model, not to a
            # hard-coded engine name. Event names below are deliberately
            # unchanged — they are the operator's existing evidence surface
            # for the segment/OOM strategy, and every line already carries
            # model/engine/endpoint/tier from the bound logger.
            model_used = binding.name

            log.info(
                "latentsync_segmented_render_complete",
                segments=len(seg_clip_paths),
                alignment_score=alignment_score,
                duration=output.duration_seconds,
            )

            # 5. Alignment gate - NON-FUNCTIONAL, deliberately not gating.
            #
            # This compared the engine's alignment_score against 0.85. That
            # score is a CONSTANT: servers/latentsync/server.py:39 sets
            # DEFAULT_ALIGNMENT = 0.90 and :123 emits it with "scored": False.
            # 0.90 >= 0.85 always, so this branch could never fire and the
            # fallback it guarded could never trigger. It read as a quality
            # gate and was not one. Ledger P1.4e.
            #
            # It is NOT re-enabled with a different threshold, because there is
            # nothing real to threshold - no metric in IVGS or MBCP measures
            # lip-sync articulation, the defect that made LatentSync non-viable
            # on 2026-06-08. Inventing a number here would restore false
            # assurance rather than remove it.
            #
            # The value is still recorded and surfaced as unscored, so the
            # output states plainly what it is.
            log.info(
                "alignment_gate_non_functional",
                engine_alignment_score=alignment_score,
                threshold=task_input.alignment_threshold,
                scored=False,
                note="engine score is a constant; gate disabled, see P1.4e",
            )

        except Exception as e:
            # Was `except (LatentSyncError, Exception)`; Exception already
            # subsumed LatentSyncError, and the engine-specific class is no
            # longer imported here (ARCH-1).
            log.warning("latentsync_render_failed", error=str(e))
            video_data = None

        # 6. Fallback to SadTalker
        if video_data is None:
            log.info("falling_back_to_sadtalker")
            fallback_used = True

            # Release the selected model's reservation, acquire SadTalker's
            if reservation:
                release_gpu_reservation(reservation, config)
            try:
                reservation = acquire_gpu_reservation(
                    job_id=job_id,
                    model_name="sadtalker",
                    vram_requirement_mb=8192,
                )
            except Exception:
                pass

            try:
                video_data = loop.run_until_complete(
                    _render_with_sadtalker(
                        reference_path, audio_path, task_input, config, temp_dir,
                    )
                )
                model_used = "sadtalker"

                # Probe output for metadata
                ffmpeg = FFmpegClient(temp_dir=temp_dir)
                sadtalker_path = os.path.join(temp_dir, "sadtalker_output.mp4")
                with open(sadtalker_path, "wb") as f:
                    f.write(video_data)
                probe = ffmpeg.probe(sadtalker_path)
                for stream in probe.get("streams", []):
                    if stream.get("codec_type") == "video":
                        output.width = int(stream.get("width", 0))
                        output.height = int(stream.get("height", 0))
                        fps_str = stream.get("r_frame_rate", "30/1")
                        if "/" in fps_str:
                            num, den = fps_str.split("/")
                            output.fps = int(int(num) / max(int(den), 1))
                        else:
                            output.fps = int(float(fps_str))
                output.duration_seconds = float(
                    probe.get("format", {}).get("duration", 0)
                )
                alignment_score = 0.80  # SadTalker doesn't report alignment

                log.info("sadtalker_render_complete", duration=output.duration_seconds)

            except Exception as e:
                log.error("sadtalker_render_failed", error=str(e))
                output.status = StageStatus.FAILED
                output.errors.append(
                    f"Both {binding.name} and the SadTalker fallback failed: {e}"
                )
                output.generation_time_seconds = round(time.monotonic() - start_time, 2)
                output.completed_at = datetime.now(timezone.utc)

                update_job_status(
                    job_id, "failed",
                    error_message="Stage 6: All talking head renderers failed",
                )

                output_dict = output.model_dump(mode="json")
                celery_app.send_task(
                    "tasks.pipeline_orchestrator_v2.handle_stage_completion",
                    kwargs={"stage_output_dict": output_dict},
                    queue="default",
                )
                return output_dict

        # 7. Corruption detection
        corruption_detector = CorruptionDetector()
        video_path = os.path.join(temp_dir, "talking_head_final.mp4")
        with open(video_path, "wb") as f:
            f.write(video_data)

        corruption_result = corruption_detector.validate_video(
            file_path=video_path,
            expected_codec="h264",
            expected_width=output.width,
            expected_height=output.height,
            expected_duration=output.duration_seconds,
            duration_tolerance=0.10,
        )
        output.corruption_check_passed = corruption_result.is_valid

        if not corruption_result.is_valid:
            log.warning(
                "corruption_detected",
                errors=corruption_result.errors,
            )

        # 8. Lipsync validation
        lipsync_validator = LipsyncValidator()
        lipsync_result = lipsync_validator.validate(
            video_path=video_path,
            audio_path=audio_path,
            threshold=task_input.alignment_threshold,
        )
        output.alignment_score = lipsync_result.alignment_score
        # The engine's own score is a constant emitted with "scored": False,
        # and this task never passes it to the validator, so nothing in this
        # output is a scored lip-sync measurement. Say so explicitly rather
        # than letting a 0.99 read as quality. Ledger P1.4e.
        output.alignment_scored = False
        output.av_drift_seconds = round(
            getattr(lipsync_result, "duration_mismatch_seconds", 0.0), 4
        )
        log.info(
            "talking_head_quality_summary",
            av_drift_seconds=output.av_drift_seconds,
            av_duration_agreement=output.alignment_score,
            alignment_scored=False,
            note="no metric here measures lip-sync articulation; see P1.4e",
        )

        # 9. Compute SHA-256 and upload
        sha256 = compute_asset_sha256(video_data)
        output.sha256_hash = sha256
        output.file_size_bytes = len(video_data)
        output.model_used = model_used
        output.render_mode = task_input.latentsync_mode
        output.fallback_used = fallback_used

        upload_result = loop.run_until_complete(
            _upload_asset(
                project_id=project_id,
                language_code=task_input.language_code,
                data=video_data,
                sha256_hash=sha256,
                metadata={
                    "model": model_used,
                    "alignment_score": alignment_score,
                    "width": output.width,
                    "height": output.height,
                    "fps": output.fps,
                    "duration": output.duration_seconds,
                    "fallback_used": fallback_used,
                    "corruption_check_passed": corruption_result.is_valid,
                },
                config=config,
            )
        )

        output.asset_id = upload_result.get("id", "")
        output.seaweedfs_path = upload_result.get("seaweedfs_path", "")
        output.generation_time_seconds = round(time.monotonic() - start_time, 2)
        output.completed_at = datetime.now(timezone.utc)

        loop.close()

        # Save checkpoint
        save_checkpoint(
            job_id=job_id,
            stage_name=PipelineStage.TALKING_HEAD_RENDER.value,
            stage_index=5,
            status=output.status.value,
            checkpoint_data={
                "asset_id": output.asset_id,
                "alignment_score": output.alignment_score,
                "model_used": model_used,
            },
        )

        log.info(
            "stage6_talking_head_complete",
            model=model_used,
            alignment_score=output.alignment_score,
            elapsed=output.generation_time_seconds,
        )

    except Exception as e:
        log.error("stage6_unexpected_error", error=str(e))
        output.status = StageStatus.FAILED
        output.errors.append(str(e))
        output.completed_at = datetime.now(timezone.utc)
        update_job_status(job_id, "failed", error_message=f"Stage 6 error: {e}")

    finally:
        # Release the provider's HTTP client. Uses its own short-lived loop:
        # the main loop is closed at the end of the try block, and this must
        # also run when we arrive here from the except branch.
        provider_close = getattr(provider, "close", None)
        if provider_close is not None:
            close_loop = asyncio.new_event_loop()
            try:
                close_loop.run_until_complete(provider_close())
            except Exception as close_err:
                log.warning("provider_close_failed", error=str(close_err))
            finally:
                close_loop.close()
        if reservation:
            release_gpu_reservation(reservation, config)
        # Cleanup temp files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Dispatch stage completion
    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )

    return output_dict
