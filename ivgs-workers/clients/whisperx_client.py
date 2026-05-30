"""
IVGS v5 — WhisperX Client
===========================

Implements §7.1.6: WhisperX large-v3 on node-04.
Word-level timestamp generation, SRT/VTT output.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from shared.providers import STTProvider

logger = logging.getLogger("ivgs.workers.whisperx")


class WhisperXClient(STTProvider):
    """HTTP client for WhisperX large-v3 on node-04. Implements STTProvider ABC."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        self.base_url = (base_url or os.environ["WHISPERX_URL"]).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    async def transcribe(
        self,
        audio_asset_id: str,
        language: str = "en",
        output_formats: Optional[list[str]] = None,
    ) -> dict:
        """
        Transcribe audio with word-level timestamps.

        Returns dict with:
          - segments: list of {start, end, text, words: [{word, start, end}]}
          - srt: SRT formatted string
          - vtt: VTT formatted string
          - caption_asset_ids: list of created caption asset IDs
        """
        client = await self._get_client()

        if output_formats is None:
            output_formats = ["srt", "vtt"]

        payload = {
            "audio_asset_id": audio_asset_id,
            "language": language,
            "model": "large-v3",
            "output_formats": output_formats,
            "word_timestamps": True,
        }

        response = await client.post(
            f"{self.base_url}/transcribe",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def align(
        self,
        audio_asset_id: str,
        transcript_text: str,
        language: str = "en",
    ) -> dict:
        """
        Forc
e-align WhisperX output with provided transcript."""
        client = await self._get_client()

        payload = {
            "audio_asset_id": audio_asset_id,
            "transcript": transcript_text,
            "language": language,
        }

        response = await client.post(
            f"{self.base_url}/align",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
