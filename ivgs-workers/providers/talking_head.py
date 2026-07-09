"""ARCH-1 talking-head engine builders (Stage-6 exemplar).

Wraps the existing engine clients behind the shared ``TalkingHeadProvider``
ABC and registers them with the selection-aware factory. The binding — not
task code — decides the endpoint, model identity, and VRAM ask.

Engine specifics:
  * ``latentsync`` — byte-based HTTP client. Cross-engine fallback is
    DISABLED here (``fallback_url=None``): under ARCH-1 the fallback model
    is an AD-01 selection concern, not a hidden client behaviour.
  * ``sadtalker`` — the client already implements the shared ABC but
    consumes file paths; the provider spills the byte inputs to a temp
    directory per render and cleans up afterwards.
"""
from __future__ import annotations

import os
import tempfile

from clients.latentsync_client import (
    LatentSyncClient,
    LatentSyncMode,
    LatentSyncParams,
)
from clients.sadtalker_client import SadTalkerClient

from shared.providers import (
    ModelBinding,
    TalkingHeadParams,
    TalkingHeadProvider,
    TalkingHeadResult,
    register_engine_builder,
)

_ENGINE_DEFAULT_VRAM_MB = {"latentsync": 16384, "sadtalker": 8192}


def _vram_mb(binding: ModelBinding) -> int:
    if binding.vram_requirement_mb:
        return binding.vram_requirement_mb
    return _ENGINE_DEFAULT_VRAM_MB.get(binding.engine, 16384)


class LatentSyncProvider(TalkingHeadProvider):
    """Shared-ABC provider over the byte-based LatentSync client."""

    def __init__(
        self,
        binding: ModelBinding,
        *,
        timeout: float = 600.0,
        alignment_threshold: float = 0.85,
    ) -> None:
        self._binding = binding
        self._client = LatentSyncClient(
            base_url=binding.endpoint,
            fallback_url=None,  # ARCH-1: fallback is a selection, not a client trick
            timeout=timeout,
            alignment_threshold=alignment_threshold,
        )

    async def render(self, params: TalkingHeadParams) -> TalkingHeadResult:
        if params.voiceover_audio_data is None or params.reference_clip_data is None:
            raise ValueError(
                "latentsync provider requires voiceover_audio_data and "
                "reference_clip_data byte inputs"
            )
        ls_params = LatentSyncParams(
            audio_data=params.voiceover_audio_data,
            reference_video_data=params.reference_clip_data,
            scene_image_data=params.scene_image_data,
            mode=LatentSyncMode(params.mode),
            output_width=params.output_width,
            output_height=params.output_height,
            output_fps=params.output_fps,
            lip_sync_strength=params.lip_sync_strength,
            face_enhance=params.face_enhance,
            pip_scale=params.pip_scale,
            pip_position=params.pip_position,
        )
        result = await self._client.render(ls_params)
        return TalkingHeadResult(
            video_data=result.video_data,
            width=result.width,
            height=result.height,
            fps=result.fps,
            duration_seconds=result.duration_seconds,
            alignment_score=result.alignment_score,
            model=self._binding.name,
            generation_time_seconds=result.generation_time_seconds,
        )

    async def check_health(self) -> bool:
        return await self._client.check_health()

    def vram_requirement_mb(self) -> int:
        return _vram_mb(self._binding)

    def provider_name(self) -> str:
        return self._binding.name

    async def close(self) -> None:
        await self._client.close()


class SadTalkerProvider(TalkingHeadProvider):
    """Shared-ABC provider over the path-based SadTalker client."""

    def __init__(
        self,
        binding: ModelBinding,
        *,
        timeout: float = 900.0,
        alignment_threshold: float = 0.85,
    ) -> None:
        self._binding = binding
        self._alignment_threshold = alignment_threshold
        self._client = SadTalkerClient(
            base_url=binding.endpoint,
            timeout=timeout,
        )

    @staticmethod
    def _spill(tmp: str, name: str, data: bytes | None, existing: str) -> str:
        """Write ``data`` to ``tmp/name`` unless a path was already given."""
        if existing:
            return existing
        if data is None:
            return ""
        path = os.path.join(tmp, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    async def render(self, params: TalkingHeadParams) -> TalkingHeadResult:
        with tempfile.TemporaryDirectory(prefix="sadtalker_") as tmp:
            image = self._spill(
                tmp, "scene.png", params.scene_image_data, params.scene_image_path,
            )
            audio = self._spill(
                tmp, "voice.wav", params.voiceover_audio_data,
                params.voiceover_audio_path,
            )
            reference = self._spill(
                tmp, "reference.mp4", params.reference_clip_data,
                params.reference_clip_path,
            )
            if not image or not audio:
                raise ValueError(
                    "sadtalker provider requires scene image and voiceover "
                    "audio (bytes or path)"
                )
            engine_params = TalkingHeadParams(
                scene_image_path=image,
                voiceover_audio_path=audio,
                reference_clip_path=reference,
                output_width=params.output_width,
                output_height=params.output_height,
                output_fps=params.output_fps,
                alignment_threshold=self._alignment_threshold,
                timeout_seconds=params.timeout_seconds,
            )
            result = await self._client.render(engine_params)
        result.model = self._binding.name
        return result

    async def check_health(self) -> bool:
        return await self._client.check_health()

    def vram_requirement_mb(self) -> int:
        return _vram_mb(self._binding)

    def provider_name(self) -> str:
        return self._binding.name

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()


def register() -> None:
    register_engine_builder("latentsync", LatentSyncProvider)
    register_engine_builder("sadtalker", SadTalkerProvider)
