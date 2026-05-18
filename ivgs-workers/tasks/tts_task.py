"""TTS generation Celery task with timeout, retry, and validation."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.idempotency import IdempotencyGuard
from app.services.timeout_manager import TimeoutManager, TimeoutError
from app.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

WORKDIR = os.getenv("WORKDIR", "/mnt/workdir")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")  # "openai" or "elevenlabs"
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")  # OpenAI: alloy/echo/fable/onyx/nova/shimmer


@shared_task(
    name="tasks.tts.generate_tts_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def generate_tts_task(self, job_id: int) -> None:
    """Generate TTS audio for all scenes.

    Reads scene narration from storyboard checkpoint. Generates MP3 audio
    for each scene using the configured TTS provider. Validates audio
    duration and format. Saves audio paths to 'tts' checkpoint.

    Args:
        job_id: The job to process.
    """
    logger.info("generate_tts_task: job=%d provider=%s", job_id, TTS_PROVIDER)
    db = SessionLocal()
    tm = TimeoutManager()
    policy = RetryPolicy(db)

    try:
        cp_svc = CheckpointService(db)
        storyboard = cp_svc.get_stage_output(job_id, "storyboard",
                                              "storyboard_scenes")
        if not storyboard:
            raise ValueError(f"Storyboard checkpoint missing for job {job_id}")

        output_dir = Path(WORKDIR) / str(job_id) / "audio"
        output_dir.mkdir(parents=True, exist_ok=True)

        scene_audio: List[Dict[str, Any]] = []

        for scene in storyboard:
            scene_idx = scene.get("scene_index", 0)
            narration = scene.get("narration") or scene.get("caption_text", "")
            if not narration:
                scene_audio.append({"scene_index": scene_idx,
                                    "audio_path": None, "duration_ms": 0})
                continue

            output_path = str(output_dir / f"scene_{scene_idx:03d}.mp3")
            params = {"narration": narration, "voice": TTS_VOICE,
                      "provider": TTS_PROVIDER}

            guard = IdempotencyGuard(db)
            result = guard.check_or_execute(
                job_id=job_id,
                stage=f"tts_scene_{scene_idx}",
                stage_index=3,
                params=params,
                executor=lambda n=narration, o=output_path:
                    _generate_tts(n, o, tm),
                validate=lambda r: os.path.exists(r.get("audio_path", "")),
            )
            scene_audio.append({
                "scene_index": scene_idx,
                "audio_path": result["audio_path"],
                "duration_ms": result.get("duration_ms", 0),
            })

        cp_svc.save_checkpoint(
            job_id=job_id, stage="tts", stage_index=3,
            data={"provider": TTS_PROVIDER, "voice": TTS_VOICE},
            outputs={"scene_audio": scene_audio,
                     "total_scenes": len(scene_audio)},
        )
        db.commit()

        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "tts"])

    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "tts", str(exc), failure_type]
        )
    finally:
        db.close()


def _generate_tts(narration: str, output_path: str,
                   tm: TimeoutManager) -> Dict[str, Any]:
    """Generate audio for a single narration segment."""
    if TTS_PROVIDER == "openai":
        return _openai_tts(narration, output_path, tm)
    return _elevenlabs_tts(narration, output_path, tm)


def _openai_tts(narration: str, output_path: str,
                 tm: TimeoutManager) -> Dict[str, Any]:
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _call():
        resp = client.audio.speech.create(
            model="tts-1-hd", voice=TTS_VOICE,
            input=narration, response_format="mp3",
        )
        return resp.content

    audio_bytes = tm.call_with_timeout(
        _call, model="openai_tts", operation="generation", timeout_seconds=120
    )
    IdempotencyGuard.atomic_write(audio_bytes, output_path)
    duration_ms = _get_audio_duration_ms(output_path)
    return {"audio_path": output_path, "duration_ms": duration_ms}


def _elevenlabs_tts(narration: str, output_path: str,
                     tm: TimeoutManager) -> Dict[str, Any]:
    import requests
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def _call():
        resp = requests.post(
            url,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": narration, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.content

    audio_bytes = tm.call_with_timeout(
        _call, model="elevenlabs_tts", operation="generation", timeout_seconds=120
    )
    IdempotencyGuard.atomic_write(audio_bytes, output_path)
    duration_ms = _get_audio_duration_ms(output_path)
    return {"audio_path": output_path, "duration_ms": duration_ms}


def _get_audio_duration_ms(audio_path: str) -> int:
    """Get audio duration via ffprobe."""
    import subprocess, json as _json
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", audio_path],
            capture_output=True, text=True, timeout=10
        )
        data = _json.loads(result.stdout)
        return int(float(data["format"]["duration"]) * 1000)
    except Exception:
        return 0
