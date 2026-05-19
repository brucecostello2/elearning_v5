from __future__ import annotations

import logging
from typing import Optional

import httpx

from ivgs.shared.providers import TTSProvider, TTSParams, AudioResult

logger = logging.getLogger("ivgs.workers.coqui")


COQUI_SUPPORTED_LANGUAGES = [
    "en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "zh-CN", "ja-JP", "ar-SA"
]


class CoquiClient(TTSProvider):
    """
    Coqui XTTS v2 implementation of TTSProvider interface (§19.1).

    Node: node-04. VRAM: 16 GB.
    Supports 8 languages with voice cloning.
    Audio output: WAV 48 kHz 24-bit mono.
    """

    def __init__(
        self,
        base_url: str = "http://10.10.0.4:5002",
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
        """Synthesize speech audio via Coqui XTTS v2."""
        client = await self._get_client()

        lang_code = language.split("-")[0] if "-" in language else language

        payload = {
            "text": text,
            "language": lang_code,
            "speaker_wav": params.speaker_reference_path or "",
            "temperature": params.temperature or 0.75,
            "length_penalty": params.length_penalty or 1.0,
            "repetition_penalty": params.repetition_penalty or 5.0,
            "top_k": params.top_k or 50,
            "top_p": params.top_p or 0.85,
            "speed": params.speed or 1.0,
        }

        response = await client.post(
            f"{self.base_url}/tts_to_audio",
            json=payload,
        )
        response.raise_for_status()

        return AudioResult(
            audio_bytes=response.content,
            sample_rate=48000,
            bit_depth=24,
            channels=1,
            format="wav",
            duration_seconds=None,  # Calculated post-generation
            language=language,
        )

    def supported_languages(self) -> list[str]:
        """Return list of supported BCP-47 language codes."""
        return COQUI_SUPPORTED_LANGUAGES.copy()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
