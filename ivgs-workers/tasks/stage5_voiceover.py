"""
IVGS v5 — Stage 4: Voiceover Synthesis Task
===============================================

Pipeline Stage 4 (Audio Generation) per §6.1:
- Trigger: Stage 3 (Image Generation) completed
- Input: Storyboard scenes with narration text
- Processing per scene:
    1. Optionally optimize narration text via vLLM (TTS-friendly)
    2. Synthesize audio via Coqui XTTS v2 (WAV 48kHz 24-bit mono)
    3. Normalize audio format via FFmpeg
    4. Validate: SNR >20dB, clipping <1%, duration, format
    5. SHA-256 dedup check before upload
    6. Store WAV to SeaweedFS: /ivgs/audio/{project_id}/{scene_id}/{language}.wav
    7. Update scene.audio_asset_id in database
    8. Save checkpoint per scene

- GPU: Coqui XTTS v2 requires 8GB VRAM (node-04:5002)
- Timeout: 120s per scene
- Retry: 3 retries with 10s→30s→90s backoff
- Fallback: Kokoro TTS (English-only)
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog
from jinja2 import BaseLoader, Environment, select_autoescape

from celery_app import IVGSBaseTask, celery_app
from clients.coqui_client import (
    CoquiClient,
    CoquiSynthesisParams,
    SUPPORTED_LANGUAGES,
)
from clients.vllm_client import VLLMClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from utils.audio_validator import AudioValidator
from utils.error_handler import save_checkpoint, update_job_status
from utils.gpu_utils import acquire_gpu_reservation
from utils.media_converter import (
    AudioConverter,
    check_duplicate_asset,
    compute_asset_sha256,
)

logger = structlog.get_logger("ivgs.stage4.voiceover")

jinja_env = Environment(loader=BaseLoader(), autoescape=select_autoescape(default_for_string=False, default=False))


# ---------------------------------------------------------------------------
# Pydantic models for Stage 4
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class SceneVoiceoverInput(BaseModel):
    """Input for a single scene voiceover synthesis."""
    scene_id: str
    scene_index: int
    narration_text: str
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None
    language_code: str = "en-US"


class Stage4Input(BaseModel):
    """Input for Stage 4: Voiceover Synthesis."""
    job_id: str
    project_id: str
    project_name: str = ""
    target_audience: str = "general"
    language_code: str = "en-US"
    scenes: List[SceneVoiceoverInput] = Field(min_length=1)
    speaker_wav_path: Optional[str] = None
    speaker_wav_data: Optional[bytes] = None
    optimize_text: bool = True
    enable_dedup: bool = True
    tts_temperature: float = 0.75
    tts_speed: float = 1.0


class SceneVoiceoverResult(BaseModel):
    """Result for a single scene voiceover synthesis."""
    scene_id: str
    scene_index: int
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
    errors: List[str] = Field(default_factory=list)
    status: str = "success"


class Stage4Output(BaseModel):
    """Output from Stage 4: Voiceover Synthesis."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.TTS_AUDIO.value
    status: StageStatus = StageStatus.SUCCESS
    scene_results: List[SceneVoiceoverResult] = Field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    total_generation_time_seconds: float = 0.0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load Stage 4 system prompt template."""
    config = WorkerConfig()
    path = os.path.join(config.prompt_template_dir, "stage4_system.j2")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Stage 4 system prompt not found: {path}")


async def _optimize_narration_text(
    narration_text: str,
    scene: SceneVoiceoverInput,
    project_context: Dict[str, Any],
    vllm_client: VLLMClient,
    config: WorkerConfig,
) -> str:
    """Optimize narration text for TTS using vLLM."""
    vllm_config = config.get_vllm_config_for_stage("image_generation")

    system_template = _load_system_prompt()
    system_prompt = jinja_env.from_string(system_template).render(
        project_title=project_context.get("project_name", ""),
        target_audience=project_context.get("target_audience", "general"),
        language_code=scene.language_code,
        scene_duration=scene.duration_seconds,
    )

    user_prompt = (
        f"Optimize this narration text for TTS synthesis:\n\n"
        f"{narration_text}\n\n"
        f"Scene: {scene.scene_title or f'Scene {scene.scene_index + 1}'}\n"
        f"Target duration: {scene.duration_seconds}s"
    )

    response = await vllm_client.chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=vllm_config["model"],
        base_url=vllm_config["base_url"],
        max_tokens=2048,
        temperature=0.3,
        timeout=60,
    )

    return response.content.strip()


async def _upload_audio_to_seaweedfs(
    audio_data: bytes,
    project_id: str,
    scene_id: str,
    language_code: str,
    config: WorkerConfig,
) -> Tuple[str, str]:
    """Upload audio to SeaweedFS."""
    seaweedfs_path = f"/ivgs/audio/{project_id}/{scene_id}/{language_code}.wav"

    async with httpx.AsyncClient(
        timeout=60.0,
        headers={
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/assets/upload",
            files={
                "file": (f"{language_code}.wav", audio_data, "audio/wav"),
            },
            data={
                "project_id": project_id,
                "asset_type": "audio",
                "storage_path": seaweedfs_path,
                "sha256": compute_asset_sha256(audio_data),
                "file_size": str(len(audio_data)),
            },
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Audio upload failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )

        data = resp.json()
        return data.get("asset_id", data.get("id", "")), seaweedfs_path


async def _update_scene_audio(
    project_id: str,
    scene_id: str,
    asset_id: str,
    config: WorkerConfig,
) -> None:
    """Update scene record with generated audio asset_id."""
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = await client.patch(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/scenes/{scene_id}",
            json={"audio_asset_id": asset_id},
        )
        if resp.status_code != 200:
            logger.warning(
                "scene_audio_update_failed",
                scene_id=scene_id,
                status_code=resp.status_code,
            )


# ---------------------------------------------------------------------------
# Per-scene processing
# ---------------------------------------------------------------------------

async def _process_single_voiceover(
    scene: SceneVoiceoverInput,
    task_input: Stage4Input,
    coqui_client: CoquiClient,
    vllm_client: Optional[VLLMClient],
    audio_validator: AudioValidator,
    audio_converter: AudioConverter,
    config: WorkerConfig,
) -> SceneVoiceoverResult:
    """Process a single scene voiceover: optimize → synthesize → validate → upload."""
    start_time = time.monotonic()

    log = logger.bind(
        scene_id=scene.scene_id,
        scene_index=scene.scene_index,
        language=scene.language_code,
    )

    try:
        narration_text = scene.narration_text

        # 1. Optionally optimize text for TTS
        if task_input.optimize_text and vllm_client:
            try:
                log.info("optimizing_narration_text")
                narration_text = await _optimize_narration_text(
                    narration_text=narration_text,
                    scene=scene,
                    project_context={
                        "project_name": task_input.project_name,
                        "target_audience": task_input.target_audience,
                    },
                    vllm_client=vllm_client,
                    config=config,
                )
            except Exception as opt_err:
                log.warning("text_optimization_failed", error=str(opt_err))
                # Continue with original text

        # 2. Map language code
        coqui_lang = SUPPORTED_LANGUAGES.get(
            scene.language_code,
            SUPPORTED_LANGUAGES.get(task_input.language_code, "en"),
        )

        # 3. Synthesize audio
        log.info("synthesizing_voiceover")
        synthesis_params = CoquiSynthesisParams(
            text=narration_text,
            language=coqui_lang,
            speaker_wav=task_input.speaker_wav_data,
            speaker_wav_path=task_input.speaker_wav_path,
            temperature=task_input.tts_temperature,
            speed=task_input.tts_speed,
        )

        synthesis_result = await coqui_client.synthesize(synthesis_params)
        audio_data = synthesis_result.audio_data

        # 4. Normalize audio to 48kHz 24-bit mono WAV
        try:
            log.info("normalizing_audio")
            normalized = audio_converter.normalize_wav(
                audio_data=audio_data,
                target_sample_rate=48000,
                target_bit_depth=24,
                target_channels=1,
            )
            audio_data = normalized.output_data
        except Exception as norm_err:
            log.warning("audio_normalization_failed", error=str(norm_err))
            # Continue with original audio

        # 5. Validate audio quality
        log.info("validating_audio")
        validation = audio_validator.validate(
            audio_data=audio_data,
            expected_duration=scene.duration_seconds,
        )

        if not validation.is_valid:
            log.warning(
                "audio_validation_failed",
                errors=validation.errors,
                snr_db=validation.snr_db,
                clipping_pct=validation.clipping_pct,
            )
            return SceneVoiceoverResult(
                scene_id=scene.scene_id,
                scene_index=scene.scene_index,
                duration_seconds=validation.actual_duration_seconds,
                quality_score=validation.quality_score,
                quality_decision=validation.decision.value,
                snr_db=validation.snr_db,
                clipping_pct=validation.clipping_pct,
                model_used=synthesis_result.model_used,
                generation_time_seconds=round(time.monotonic() - start_time, 3),
                language_code=scene.language_code,
                errors=validation.errors,
                status="failed",
            )

        # 6. SHA-256 dedup
        sha256_hash = compute_asset_sha256(audio_data)
        was_deduplicated = False

        if task_input.enable_dedup:
            existing = check_duplicate_asset(
                sha256_hash=sha256_hash,
                api_base_url=config.pipeline_api.full_base_url,
                service_token=config.pipeline_api.service_token,
            )
            if existing:
                log.info("audio_deduplicated", existing_asset_id=existing.get("id"))
                was_deduplicated = True
                asset_id = existing.get("id", "")
                seaweedfs_path = existing.get("storage_path", "")

                await _update_scene_audio(
                    task_input.project_id, scene.scene_id, asset_id, config
                )

                return SceneVoiceoverResult(
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    asset_id=asset_id,
                    seaweedfs_path=seaweedfs_path,
                    sha256_hash=sha256_hash,
                    duration_seconds=validation.actual_duration_seconds,
                    sample_rate=validation.actual_sample_rate,
                    bit_depth=validation.actual_bit_depth,
                    file_size_bytes=len(audio_data),
                    quality_score=validation.quality_score,
                    quality_decision=validation.decision.value,
                    snr_db=validation.snr_db,
                    clipping_pct=validation.clipping_pct,
                    model_used=synthesis_result.model_used,
                    generation_time_seconds=round(time.monotonic() - start_time, 3),
                    was_deduplicated=True,
                    language_code=scene.language_code,
                    status="success",
                )

        # 7. Upload to SeaweedFS
        log.info("uploading_audio")
        asset_id, seaweedfs_path = await _upload_audio_to_seaweedfs(
            audio_data=audio_data,
            project_id=task_input.project_id,
            scene_id=scene.scene_id,
            language_code=scene.language_code,
            config=config,
        )

        # 8. Update scene record
        await _update_scene_audio(
            task_input.project_id, scene.scene_id, asset_id, config
        )

        elapsed = round(time.monotonic() - start_time, 3)
        log.info(
            "voiceover_generated",
            asset_id=asset_id,
            duration=validation.actual_duration_seconds,
            snr_db=validation.snr_db,
            elapsed=elapsed,
        )

        return SceneVoiceoverResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            asset_id=asset_id,
            seaweedfs_path=seaweedfs_path,
            sha256_hash=sha256_hash,
            duration_seconds=validation.actual_duration_seconds,
            sample_rate=validation.actual_sample_rate,
            bit_depth=validation.actual_bit_depth,
            file_size_bytes=len(audio_data),
            quality_score=validation.quality_score,
            quality_decision=validation.decision.value,
            snr_db=validation.snr_db,
            clipping_pct=validation.clipping_pct,
            model_used=synthesis_result.model_used,
            generation_time_seconds=elapsed,
            was_deduplicated=was_deduplicated,
            language_code=scene.language_code,
            status="success",
        )

    except Exception as e:
        elapsed = round(time.monotonic() - start_time, 3)
        log.error("voiceover_generation_failed", error=str(e))
        return SceneVoiceoverResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            generation_time_seconds=elapsed,
            language_code=scene.language_code,
            errors=[str(e)],
            status="failed",
        )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.stage4_voiceover.generate_voiceover_task",
    max_retries=3,
    default_retry_delay=10,
    soft_time_limit=900,
    time_limit=1200,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_voiceover_task(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Stage 4 Celery task: Generate voiceover for all storyboard scenes.

    Dispatched after Stage 3 completion. Processes scenes sequentially
    with checkpoint saving after each scene.
    """
    start_time = time.monotonic()
    task_input = Stage4Input(**task_input_dict)
    config = WorkerConfig()

    log = self.structured_logger.bind(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        total_scenes=len(task_input.scenes),
        language=task_input.language_code,
    )
    log.info("stage4_starting")

    update_job_status(task_input.job_id, "running")

    # GPU reservation for Coqui XTTS v2 (8GB)
    reservation_id = None
    if config.enable_gpu_reservation:
        try:
            reservation = acquire_gpu_reservation(
                job_id=task_input.job_id,
                model_name="coqui-xtts-v2",
                vram_requirement_mb=8192,
                estimated_duration_s=len(task_input.scenes) * 30,
            )
            reservation_id = reservation.get("reservation_id")
            self._gpu_reservation_id = reservation_id
        except Exception as gpu_err:
            log.warning("gpu_reservation_failed", error=str(gpu_err))

    scene_results: List[SceneVoiceoverResult] = []
    successful = 0
    failed = 0
    deduplicated = 0

    loop = asyncio.new_event_loop()

    try:
        coqui_client = CoquiClient(
            base_url=os.getenv("IVGS_COQUI_URL", "http://node-04:5002"),
            fallback_url=os.getenv("IVGS_COQUI_FALLBACK_URL"),
            timeout=config.timeouts.tts_timeout,
        )
        audio_validator = AudioValidator()
        audio_converter = AudioConverter()

        vllm_client = None
        if task_input.optimize_text:
            vllm_client = VLLMClient(config.vllm)

        for scene in task_input.scenes:
            result = loop.run_until_complete(
                _process_single_voiceover(
                    scene=scene,
                    task_input=task_input,
                    coqui_client=coqui_client,
                    vllm_client=vllm_client,
                    audio_validator=audio_validator,
                    audio_converter=audio_converter,
                    config=config,
                )
            )

            scene_results.append(result)

            if result.status == "success":
                successful += 1
                if result.was_deduplicated:
                    deduplicated += 1
            else:
                failed += 1

            if config.enable_checkpoint_saving:
                save_checkpoint(
                    job_id=task_input.job_id,
                    stage_name=PipelineStage.TTS_AUDIO.value,
                    stage_index=4,
                    status="running",
                    checkpoint_data={
                        "completed_scenes": [
                            r.scene_id for r in scene_results if r.status == "success"
                        ],
                        "total_processed": len(scene_results),
                    },
                )

            log.info(
                "voiceover_processed",
                scene_id=scene.scene_id,
                status=result.status,
                progress=f"{len(scene_results)}/{len(task_input.scenes)}",
            )

        loop.run_until_complete(coqui_client.close())
        if vllm_client:
            loop.run_until_complete(vllm_client.close())

    except Exception as e:
        log.error("stage4_processing_error", error=str(e))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        raise
    finally:
        loop.close()

    total_time = round(time.monotonic() - start_time, 3)
    overall_status = StageStatus.SUCCESS if failed == 0 else StageStatus.FAILED

    output = Stage4Output(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        status=overall_status,
        scene_results=scene_results,
        total_scenes=len(task_input.scenes),
        successful_count=successful,
        failed_count=failed,
        deduplicated_count=deduplicated,
        total_generation_time_seconds=total_time,
        completed_at=datetime.now(timezone.utc),
    )

    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=task_input.job_id,
            stage_name=PipelineStage.TTS_AUDIO.value,
            stage_index=4,
            status=overall_status.value,
            checkpoint_data={
                "successful_count": successful,
                "failed_count": failed,
                "total_generation_time": total_time,
            },
        )

    log.info(
        "stage4_completed",
        status=overall_status.value,
        successful=successful,
        failed=failed,
        total_time=total_time,
    )

    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )
    return output_dict
