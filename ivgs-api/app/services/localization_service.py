"""Multi-language localization service.
Translates transcript, re-voices TTS, aligns captions, recomposes video."""
import json
import logging
import os
from typing import Optional, List, Dict
from app.models.localization import LocalizationConfig, LocalizedAsset
from app.services.manifest_service import ManifestService
from app.middleware.checkpoint import CheckpointService
from app.core.database import get_db_context
import openai

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "es": {"name": "Spanish",   "tts_voice": "nova",   "openai_code": "es"},
    "fr": {"name": "French",    "tts_voice": "alloy",  "openai_code": "fr"},
    "de": {"name": "German",    "tts_voice": "echo",   "openai_code": "de"},
    "ja": {"name": "Japanese",  "tts_voice": "shimmer","openai_code": "ja"},
    "zh": {"name": "Chinese",   "tts_voice": "onyx",   "openai_code": "zh"},
    "pt": {"name": "Portuguese","tts_voice": "fable",  "openai_code": "pt"},
    "ko": {"name": "Korean",    "tts_voice": "nova",   "openai_code": "ko"},
    "ar": {"name": "Arabic",    "tts_voice": "alloy",  "openai_code": "ar"},
}


class LocalizationService:
    def __init__(
        self,
        manifest_service: ManifestService,
        checkpoint_service: CheckpointService,
        workdir: str = "/mnt/workdir",
    ):
        self.manifest_service = manifest_service
        self.checkpoint_service = checkpoint_service
        self.workdir = workdir

    def get_supported_languages(self) -> List[Dict]:
        return [
            {"code": code, **info}
            for code, info in SUPPORTED_LANGUAGES.items()
        ]

    # ------------------------------------------------------------------
    # Step 1: Translate transcript
    # ------------------------------------------------------------------
    def translate_transcript(
        self,
        job_id: str,
        source_language: str,
        target_language: str,
        original_transcript: Dict,
    ) -> Dict:
        """Use GPT-4 to translate transcript preserving scene structure."""
        lang_info = SUPPORTED_LANGUAGES.get(target_language)
        if lang_info is None:
            raise ValueError(f"Unsupported target language: {target_language}")

        system_prompt = (
            f"You are a professional video script translator. "
            f"Translate the following JSON transcript from {source_language} "
            f"to {lang_info['name']} ({target_language}). "
            "IMPORTANT: preserve all JSON structure, scene IDs, timing "
            "markers (e.g. [PAUSE:500ms]), and formatting. Only translate "
            "the 'narration', 'caption_text', and 'visual_description' "
            "string fields. Return valid JSON."
        )

        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": json.dumps(original_transcript,
                                                          ensure_ascii=False)},
            ],
            temperature=0.3,
            max_tokens=8192,
        )
        translated_text = response.choices[0].message.content
        try:
            translated = json.loads(translated_text)
        except json.JSONDecodeError:
            # Strip markdown fences if GPT-4 wrapped in ```json...```
            cleaned = translated_text.strip().lstrip("```json").rstrip("```")
            translated = json.loads(cleaned)

        logger.info("Translated transcript to %s (%d chars)",
                    target_language, len(translated_text))
        return translated

    # ------------------------------------------------------------------
    # Step 2: Generate localized TTS
    # ------------------------------------------------------------------
    def generate_localized_tts(
        self,
        job_id: str,
        scene_id: str,
        narration_text: str,
        target_language: str,
        voice_override: Optional[str] = None,
    ) -> str:
        """Generate TTS audio for translated narration."""
        lang_info = SUPPORTED_LANGUAGES.get(target_language, {})
        voice = voice_override or lang_info.get("tts_voice", "alloy")

        output_dir = os.path.join(self.workdir, job_id,
                                  "localized", target_language)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{scene_id}_tts.mp3")

        client = openai.OpenAI()
        response = client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=narration_text,
        )
        response.stream_to_file(output_path)
        logger.info("Generated localized TTS: %s (%s)", output_path,
                    target_language)
        return output_path

    # ------------------------------------------------------------------
    # Step 3: Generate localized captions
    # ------------------------------------------------------------------
    def generate_localized_captions(
        self,
        job_id: str,
        scene_id: str,
        translated_text: str,
        tts_audio_path: str,
        target_language: str,
    ) -> Dict[str, str]:
        """Generate SRT + VTT from translated text + localized audio."""
        from app.services.caption_reconciliation import CaptionReconciliation
        reconciler = CaptionReconciliation(workdir=self.workdir)
        srt_path, vtt_path = reconciler.align_captions(
            job_id=job_id,
            scene_id=f"{scene_id}_{target_language}",
            audio_path=tts_audio_path,
            original_text=translated_text,
            language_code=target_language,
        )
        return {"srt": srt_path, "vtt": vtt_path}

    # ------------------------------------------------------------------
    # Step 4: Recompose video with localized assets
    # ------------------------------------------------------------------
    def create_localized_video(
        self,
        job_id: str,
        target_language: str,
        localized_tts_paths: Dict[str, str],  # scene_id → audio path
        localized_caption_paths: Dict[str, str],  # scene_id → srt path
    ) -> Optional[str]:
        """Recompose the full video with localized audio + captions."""
        output_dir = os.path.join(self.workdir, job_id,
                                  "localized", target_language)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "composed.mp4")

        # Get base manifest and substitute localized audio + captions
        manifest = self.manifest_service.get_manifest(job_id)
        if manifest is None:
            logger.error("No manifest for job %s", job_id)
            return None

        # Build FFmpeg command from manifest with localized audio tracks
        timeline = manifest.get_timeline()
        # ... (FFmpeg complex-filter substitution logic)
        # Simplified representative command:
        import subprocess
        audio_inputs = []
        audio_map = []
        for idx, (scene_id, audio_path) in enumerate(
                localized_tts_paths.items()):
            audio_inputs.extend(["-i", audio_path])
            audio_map.extend(["-map", f"{idx + 1}:a"])

        cmd = [
            "ffmpeg", "-y",
            "-i", manifest.get_base_video_path(),
            *audio_inputs,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            *audio_map,
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=1800)
        if result.returncode != 0:
            logger.error("FFmpeg recompose failed: %s",
                         result.stderr.decode()[:500])
            return None

        logger.info("Localized video created: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Main orchestration method
    # ------------------------------------------------------------------
    def run_full_localization(
        self,
        job_id: str,
        target_language: str,
        config_id: int,
    ) -> bool:
        """Run complete localization pipeline for one target language."""
        with get_db_context() as db:
            config = db.query(LocalizationConfig).filter_by(
                id=config_id).first()
            if config is None:
                return False
            config.status = "translating"
            db.commit()

        try:
            # Get original transcript from checkpoint
            cp = self.checkpoint_service.get_last_checkpoint(
                job_id, "transcript")
            original_transcript = cp.get_checkpoint_data()

            # Step 1: Translate
            translated = self.translate_transcript(
                job_id, config.source_language, target_language,
                original_transcript)

            with get_db_context() as db:
                config = db.query(LocalizationConfig).filter_by(
                    id=config_id).first()
                config.status = "tts_generating"
                db.commit()

            # Step 2: TTS per scene
            tts_paths: Dict[str, str] = {}
            for scene in translated.get("scenes", []):
                scene_id = scene["id"]
                narration = scene.get("narration", "")
                if narration:
                    tts_path = self.generate_localized_tts(
                        job_id, scene_id, narration,
                        target_language, config.tts_voice_id)
                    tts_paths[scene_id] = tts_path
                    self._save_asset(db, config_id, job_id, scene_id,
                                     "tts_audio", tts_path)

            with get_db_context() as db:
                config = db.query(LocalizationConfig).filter_by(
                    id=config_id).first()
                config.status = "captions_generating"
                db.commit()

            # Step 3: Captions per scene
            caption_paths: Dict[str, str] = {}
            for scene_id, tts_path in tts_paths.items():
                scene = next(s for s in translated["scenes"]
                             if s["id"] == scene_id)
                result = self.generate_localized_captions(
                    job_id, scene_id, scene.get("caption_text", ""),
                    tts_path, target_language)
                caption_paths[scene_id] = result["srt"]
                self._save_asset(db, config_id, job_id, scene_id,
                                 "caption_srt", result["srt"])

            with get_db_context() as db:
                config = db.query(LocalizationConfig).filter_by(
                    id=config_id).first()
                config.status = "composing"
                db.commit()

            # Step 4: Recompose
            video_path = self.create_localized_video(
                job_id, target_language, tts_paths, caption_paths)
            if video_path is None:
                raise RuntimeError("Recomposition failed")

            self._save_asset(db, config_id, job_id, None,
                             "composed_video", video_path)

            with get_db_context() as db:
                config = db.query(LocalizationConfig).filter_by(
                    id=config_id).first()
                config.status = "complete"
                db.commit()
            return True

        except Exception as exc:
            logger.error("Localization failed for %s → %s: %s",
                         job_id, target_language, exc)
            with get_db_context() as db:
                config = db.query(LocalizationConfig).filter_by(
                    id=config_id).first()
                config.status = "failed"
                config.error_message = str(exc)[:1000]
                db.commit()
            return False

    def _save_asset(self, db, config_id, job_id, scene_id,
                    asset_type, asset_path):
        asset = LocalizedAsset(
            localization_config_id=config_id,
            job_id=job_id,
            scene_id=scene_id,
            asset_type=asset_type,
            asset_path=asset_path,
            status="complete",
        )
        with get_db_context() as db:
            db.add(asset)
            db.commit()
