"""
IVGS v5 — Kokoro TTS Fallback Client
======================================

Implements §7.1.5 fallback: Kokoro TTS (English-only, lower VRAM, faster).
Inherits from TTSProvider ABC interface per §19.1.
"""

from __future__ import annotations

import io
import logging
import os
import wave
from typing import Optional

import httpx

from shared.providers import TTSProvider, TTSParams, AudioResult

logger = logging.getLogger("ivgs.workers.kokoro")

KOKORO_SUPPORTED_LANGUAGES = ["en-US", "en-GB"]


class KokoroClient(TTSProvider):
    """
    Kokoro TTS implementation of TTSProvider interface (§19.1).

    English-only fallback for Coqui XTTS v2.
    Node: node-04. Lower VRAM footprint, faster inference.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.environ["KOKORO_TTS_URL"]).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def synthesize(
        self, text: str, language: str, params: TTSParams
    ) -> AudioResult:
        """Synthesize speech audio via Kokoro TTS."""
        # WP-42: stage 5 hands the engine the ALREADY-MAPPED code ("en"), not
        # the BCP-47 tag, so the old `language not in ["en-US","en-GB"]` test
        # rejected every real call. Accept either spelling.
        if language.split("-")[0].lower() != "en":
            raise ValueError(
                f"Kokoro TTS does not support {language}. "
                f"Supported: {KOKORO_SUPPORTED_LANGUAGES}"
            )

        client = await self._get_client()

        # WP-42: Kokoro serves the SAME wire contract as Coqui —
        # POST /tts_to_audio with a TTSRequest body (verified against the live
        # OpenAPI on node-04:5003). The old client posted `/synthesize` with a
        # `speaker_id` field; that route does not exist and returned 404.
        payload = {
            "text": text,
            "language": language.split("-")[0].lower(),
            "speaker_wav": params.speaker_wav or "",
            "speed": params.speed or 1.0,
        }

        response = await client.post(
            f"{self.base_url}/tts_to_audio",
            json=payload,
        )
        response.raise_for_status()

        # WP-42: this constructed AudioResult with kwargs the dataclass does
        # not define (`audio_bytes`, `bit_depth`, `channels`, `language`) and a
        # None duration, so every Kokoro synthesis raised TypeError before the
        # audio was ever looked at. The engine has never actually served this
        # pipeline. Rate and duration now come from the returned WAV header,
        # as they do on the Coqui path, rather than being asserted.
        audio_data = response.content
        sample_rate, duration = 48000, 0.0
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as w:
                sample_rate = w.getframerate()
                duration = w.getnframes() / sample_rate if sample_rate else 0.0
        except Exception:
            logger.warning("could not parse Kokoro WAV header; using defaults")

        return AudioResult(
            audio_data=audio_data,
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    def supported_languages(self) -> list[str]:
        """Kokoro TTS supports English only."""
        return KOKORO_SUPPORTED_LANGUAGES.copy()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
