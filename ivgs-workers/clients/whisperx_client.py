"""
IVGS v5 - WhisperX Client
===========================

Implements 7.1.6: WhisperX large-v3 on node-04 (STT + word-level alignment).
HTTP client for the whisperx model server (servers/whisperx); implements the
STTProvider interface (shared/providers):

    transcribe(audio_path, params: STTParams) -> STTResult
    align(audio_path, transcript, language)   -> STTResult

Audio is passed by path. In the cluster the audio lives on the shared NFS, which is
mounted into the whisperx container, so the path the calling worker provides resolves
on the server side. SRT/VTT serialization and caption-asset creation are the caller's
job (per 19.1), built from STTResult.segments.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from shared.providers import STTParams, STTProvider, STTResult

logger = logging.getLogger("ivgs.workers.whisperx")


class WhisperXClient(STTProvider):
    """HTTP client for WhisperX large-v3 on node-04. Implements the STTProvider ABC."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 300.0) -> None:
        self.base_url = (base_url or os.environ["WHISPERX_URL"]).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0))
        return self._client

    @staticmethod
    def _to_result(data: dict) -> STTResult:
        return STTResult(
            text=data.get("text", ""),
            segments=data.get("segments", []),
            language=data.get("language", ""),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
        )

    async def transcribe(self, audio_path: str, params: STTParams) -> STTResult:
        """Transcribe audio to text with word-level timestamps."""
        client = await self._get_client()
        payload = {
            "audio_path": audio_path,
            "language": params.language,
            "model_size": params.model_size,
            "word_timestamps": params.word_timestamps,
            "output_format": params.output_format,
        }
        resp = await client.post(f"{self.base_url}/transcribe", json=payload)
        resp.raise_for_status()
        return self._to_result(resp.json())

    async def align(self, audio_path: str, transcript: str, language: str) -> STTResult:
        """Force-align a transcript to audio for word-level timestamps."""
        client = await self._get_client()
        payload = {"audio_path": audio_path, "transcript": transcript, "language": language}
        resp = await client.post(f"{self.base_url}/align", json=payload)
        resp.raise_for_status()
        return self._to_result(resp.json())

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
