"""
IVGS v5 — Localization Pipeline Worker Tasks
=============================================

Implements §17.2 Table 17-2 localization stages:
  1. Transcript Translation (vLLM)
  2. TTS Audio Generation (Coqui XTTS v2 in target language)
  3. Talking Head Re-rendering (LatentSync with new audio)
  4. Caption Generation (WhisperX for new audio)
  5. Final Composition (FFmpeg with new assets)

Triggered when project state transitions to LOCALISATION via
POST /api/v1/projects/{id}/languages.
"""

from __future__ import annotations

import logging
from typing import Any


from shared.providers import LLMParams, TTSParams
from ivgs_workers.celery_app import app
from ivgs_workers.config import WorkerConfig
from ivgs_workers.utils.provider_factory import (
    get_llm_provider,
    get_tts_provider,
)

logger = logging.getLogger("ivgs.workers.localization")
config = WorkerConfig()


@app.task(
    name="ivgs.localization.translate_transcripts",
    bind=True,
    queue="gpu_llm",
    acks_late=True,
    max_retries=4,
    default_retry_delay=5,
)
def translate_transcripts(
    self,
    project_id: str,
    language_code: str,
    language_variant_id: str,
) -> dict[str, Any]:
    """
    Stage 1: Translate all refined transcripts to target language via vLLM.

    Uses 'translation' prompt type. Stores new transcript records
    with target language_code.
    """
    import asyncio

    async def _translate():
        from sqlalchemy import text as sa_text
        from shared.database import get_async_session

        provider = get_llm_provider(config)

        async with get_async_session() as db:
            # Fetch all English transcripts for this project
            rows = (
                await db.execute(
                    sa_text(
                        "SELECT id, refined_text, sequence_order "
                        "FROM transcripts "
                        "WHERE project_id = :pid AND language_code = 'en-US' "
                        "ORDER BY sequence_order"
                    ),
                    {"pid": project_id},
                )
            ).fetchall()

            translated_ids = []
            for row in rows:
                system_prompt = (
                    f"You are a professional translator. Translate the following "
                    f"instructional content to {language_code}. Maintain the "
                    f"educational tone, technical accuracy, and learning objectives. "
                    f"Do not add explanations — output only the translation."
                )
                params = LLMParams(
                    system_prompt=system_prompt,
                    temperature=0.3,
                    max_tokens=4096,
                )
                _result = await provider.generate(row.refined_text, params)  # noqa: F841

                # Insert translated transcript
                import uuid
                tid = str(uuid.uuid4())
                await db.execute(
                    sa_text(
                        "INSERT INTO transcripts "
                        "(id, project_id, refined_text, sequence_order, language_code) "
                        "VALUES (:id, :pid, :text, :seq, :lang)"
                    ),
                    {
                        "id": tid,
                        "pid": project_id,
                        "text": result.text,
                        "seq": row.sequence_order,
                        "lang": language_code,
                    },
                )
                translated_ids.append(tid)

            await db.commit()

        await provider.close()
        return {"translated_transcript_ids": translated_ids}

    return asyncio.get_event_loop().run_until_complete(_translate())


@app.task(
    name="ivgs.localization.generate_tts",
    bind=True,
    queue="gpu_tts",
    acks_late=True,
    max_retries=3,
    default_retry_delay=10,
)
def generate_localized_tts(
    self,
    project_id: str,
    language_code: str,
    language_variant_id: str,
    translated_transcript_ids: list[str],
) -> dict[str, Any]:
    """
    Stage 2: Generate TTS audio in target language via Coqui XTTS v2.
    """
    import asyncio

    async def _generate_tts():
        from sqlalchemy import text as sa_text
        from shared.database import get_async_session
        from shared.seaweedfs_client import SeaweedFSClient

        tts_provider = get_tts_provider(config)
        seaweedfs = SeaweedFSClient(config.SEAWEEDFS_FILER_URL)

        async with get_async_session() as db:
            audio_asset_ids = []
            for tid in translated_transcript_ids:
                row = (
                    await db.execute(
                        sa_text("SELECT refined_text, sequence_order FROM transcripts WHERE id = :id"),
                        {"id": tid},
                    )
                ).fetchone()

                if not row:
                    continue

                params = TTSParams(speed=1.0)
                audio_result = await tts_provider.synthesize(
                    text=row.refined_text,
                    language=language_code,
                    params=params,
                )

                # Upload to SeaweedFS
                fid = await seaweedfs.upload(
                    audio_result.audio_bytes,
                    path=f"/ivgs/audio/{project_id}/{language_code}/scene_{row.sequence_order}.wav",
                )

                # Create asset record
                import uuid, hashlib
                asset_id = str(uuid.uuid4())
                sha256 = hashlib.sha256(audio_result.audio_bytes).hexdigest()

                await db.execute(
                    sa_text(
                        "INSERT INTO assets "
                        "(id, project_id, asset_type, seaweedfs_fid, seaweedfs_path, "
                        "sha256_hash, language_code, file_size_bytes) "
                        "VALUES (:id, :pid, 'tts_audio', :fid, :path, :sha, :lang, :size)"
                    ),
                    {
                        "id": asset_id,
                        "pid": project_id,
                        "fid": fid,
                        "path": f"/ivgs/audio/{project_id}/{language_code}/scene_{row.sequence_order}.wav",
                        "sha": sha256,
                        "lang": language_code,
                        "size": len(audio_result.audio_bytes),
                    },
                )
                audio_asset_ids.append(asset_id)

            await db.commit()

        await tts_provider.close()
        return {"audio_asset_ids": audio_asset_ids}

    return asyncio.get_event_loop().run_until_complete(_generate_tts())


@app.task(
    name="ivgs.localization.render_talking_head",
    bind=True,
    queue="gpu_talking_head",
    acks_late=True,
    max_retries=2,
    default_retry_delay=30,
)
def render_localized_talking_head(
    self,
    project_id: str,
    language_code: str,
    language_variant_id: str,
    audio_asset_ids: list[str],
) -> dict[str, Any]:
    """
    Stage 3: Re-render talking head with LatentSync against new audio track.
    """
    import asyncio

    async def _render():
        from sqlalchemy import text as sa_text
        from shared.database import get_async_session
        from ivgs_workers.clients.latentsync_client import LatentSyncClient

        latentsync = LatentSyncClient(base_url=config.LATENTSYNC_URL)

        async with get_async_session() as db:
            # Concatenate audio files for full talking head
            # Get original talking head clip
            original_th = (
                await db.execute(
                    sa_text(
                        "SELECT seaweedfs_path FROM assets "
                        "WHERE project_id = :pid AND asset_type = 'talking_head' "
                        "AND language_code = 'en-US' LIMIT 1"
                    ),
                    {"pid": project_id},
                )
            ).fetchone()

            if not original_th:
                raise RuntimeError(f"No original talking head found for project {project_id}")

            # Render lip-sync with new audio
            result = await latentsync.render(  # noqa: F841
                video_path=original_th.seaweedfs_path,
                audio_asset_ids=audio_asset_ids,
                output_path=f"/ivgs/talking-heads/{project_id}/{language_code}.mp4",
            )

            # Store new talking head asset
            import uuid
            asset_id = str(uuid.uuid4())
            await db.execute(
                sa_text(
                    "INSERT INTO assets "
                    "(id, project_id, asset_type, seaweedfs_path, language_code) "
                    "VALUES (:id, :pid, 'talking_head', :path, :lang)"
                ),
                {
                    "id": asset_id,
                    "pid": project_id,
                    "path": f"/ivgs/talking-heads/{project_id}/{language_code}.mp4",
                    "lang": language_code,
                },
            )
            await db.commit()

        return {"talking_head_asset_id": asset_id}

    return asyncio.get_event_loop().run_until_complete(_render())


@app.task(
    name="ivgs.localization.generate_captions",
    bind=True,
    queue="gpu_tts",
    acks_late=True,
    max_retries=3,
    default_retry_delay=10,
)
def generate_localized_captions(
    self,
    project_id: str,
    language_code: str,
    language_variant_id: str,
    audio_asset_ids: list[str],
) -> dict[str, Any]:
    """
    Stage 4: Generate word-level captions via WhisperX for new audio.
    """
    import asyncio

    async def _captions():
        from ivgs_workers.clients.whisperx_client import WhisperXClient

        whisperx = WhisperXClient(base_url=config.WHISPERX_URL)
        caption_ids = []

        for audio_id in audio_asset_ids:
            result = await whisperx.transcribe(
                audio_asset_id=audio_id,
                language=language_code,
                output_formats=["srt", "vtt"],
            )
            caption_ids.extend(result.get("caption_asset_ids", []))

        return {"caption_asset_ids": caption_ids}

    return asyncio.get_event_loop().run_until_complete(_captions())


@app.task(
    name="ivgs.localization.final_composition",
    bind=True,
    queue="composition",
    acks_late=True,
    max_retries=2,
    default_retry_delay=30,
)
def localized_final_composition(
    self,
    project_id: str,
    language_code: str,
    language_variant_id: str,
    talking_head_asset_id: str,
    audio_asset_ids: list[str],
    caption_asset_ids: list[str],
) -> dict[str, Any]:
    """
    Stage 5: FFmpeg composites new audio, lip-sync, captions with existing scene media.
    Produces new 1080p + 4K MP4 for this language variant.
    """
    import asyncio

    async def _compose():
        from sqlalchemy import text as sa_text
        from shared.database import get_async_session
        from ivgs_workers.clients.ffmpeg_client import FFmpegClient

        ffmpeg = FFmpegClient()

        async with get_async_session() as db:
            # Build composition from manifest + new localized assets
            result = await ffmpeg.compose_localized(
                project_id=project_id,
                language_code=language_code,
                talking_head_asset_id=talking_head_asset_id,
                audio_asset_ids=audio_asset_ids,
                caption_asset_ids=caption_asset_ids,
            )

            # Update language variant status
            await db.execute(
                sa_text(
                    "UPDATE language_variants SET state = 'COMPLETE' "
                    "WHERE id = :lvid"
                ),
                {"lvid": language_variant_id},
            )
            await db.commit()

        return {
            "output_1080p": result["path_1080p"],
            "output_4k": result["path_4k"],
            "language_code": language_code,
        }

    return asyncio.get_event_loop().run_until_complete(_compose())


# ---------------------------------------------------------------------------
# Orchestrator: chain localization stages via event-driven dispatch
# ---------------------------------------------------------------------------

@app.task(
    name="ivgs.localization.orchestrate",
    bind=True,
    queue="default",
    acks_late=True,
)
def orchestrate_localization(
    self,
    project_id: str,
    language_code: str,
    language_variant_id: str,
) -> None:
    """
    Entry point: dispatches localization pipeline for a target language.
    Called when project state transitions to LOCALISATION.
    """
    translate_transcripts.apply_async(
        kwargs={
            "project_id": project_id,
            "language_code": language_code,
            "language_variant_id": language_variant_id,
        },
        link=generate_localized_tts.s(
            project_id=project_id,
            language_code=language_code,
            language_variant_id=language_variant_id,
        ),
    )
