"""
IVGS v5 — Kokoro TTS Fallback Client
======================================

Implements §7.1.5 fallback: Kokoro TTS (English-only, lower VRAM, faster).
Inherits from TTSProvider ABC interface per §19.1.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from ivgs.shared.providers import TTSProvider, TTSParams, AudioResult

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
        base_url: str = "http://10.10.0.4:5003",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        if language not in KOKORO_SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Kokoro TTS does not support {language}. "
                f"Supported: {KOKORO_SUPPORTED_LANGUAGES}"
            )

        client = await self._get_client()

        payload = {
            "text": text,
            "language": language,
            "speed": params.speed or 1.0,
            "speaker_id": "default",
        }

        response = await client.post(
            f"{self.base_url}/synthesize",
            json=payload,
        )
        response.raise_for_status()

        return AudioResult(
            audio_bytes=response.content,
            sample_rate=48000,
            bit_depth=24,
            channels=1,
            format="wav",
            duration_seconds=None,
            language=language,
        )

    def supported_languages(self) -> list[str]:
        """Kokoro TTS supports English only."""
        return KOKORO_SUPPORTED_LANGUAGES.copy()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
