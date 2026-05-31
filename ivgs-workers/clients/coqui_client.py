from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import httpx

from shared.providers import TTSProvider, TTSParams, AudioResult

logger = logging.getLogger("ivgs.workers.coqui")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CoquiError(Exception):
    """Base exception for Coqui TTS errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, language: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.language = language


class CoquiConnectionError(CoquiError):
    """Coqui server unreachable."""
    pass


class CoquiTimeoutError(CoquiError):
    """Coqui TTS timed out."""
    pass


class CoquiSynthesisError(CoquiError):
    """Coqui synthesis failed."""
    pass


class CoquiUnsupportedLanguageError(CoquiError):
    """Requested language not supported."""
    pass


class CoquiVoiceCloneError(CoquiError):
    """Voice cloning failed."""
    pass


# ---------------------------------------------------------------------------
# Enums and config
# ---------------------------------------------------------------------------

class CoquiLanguage(str, Enum):
    """Supported languages per spec section 7.1.5."""
    EN_US = "en"
    EN_GB = "en"
    ES_ES = "es"
    FR_FR = "fr"
    DE_DE = "de"
    ZH_CN = "zh-cn"
    JA_JP = "ja"
    AR_SA = "ar"


SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en-US": "en",
    "en-GB": "en",
    "es-ES": "es",
    "fr-FR": "fr",
    "de-DE": "de",
    "zh-CN": "zh-cn",
    "ja-JP": "ja",
    "ar-SA": "ar",
}


@dataclass(frozen=True)
class CoquiSynthesisParams:
    """Parameters for TTS synthesis."""
    text: str
    language: str = "en"
    speaker_wav: Optional[bytes] = None
    speaker_wav_path: Optional[str] = None
    temperature: float = 0.75
    length_penalty: float = 1.0
    repetition_penalty: float = 5.0
    top_k: int = 50
    top_p: float = 0.85
    speed: float = 1.0
    enable_text_splitting: bool = True

    def compute_hash(self) -> str:
        """SHA-256 hash for idempotency."""
        data = {
            "text": self.text,
            "language": self.language,
            "temperature": self.temperature,
            "length_penalty": self.length_penalty,
            "repetition_penalty": self.repetition_penalty,
            "speed": self.speed,
        }
        if self.speaker_wav_path:
            data["speaker_wav_path"] = self.speaker_wav_path
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class CoquiSynthesisResult:
    """Result from Coqui TTS synthesis."""
    audio_data: bytes
    sample_rate: int
    bit_depth: int
    channels: int
    duration_seconds: float
    language: str
    model_used: str
    generation_time_seconds: float
    params_hash: str
    text_length: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Coqui XTTS v2 Client
# ---------------------------------------------------------------------------

class CoquiClient(TTSProvider):
    """
    Coqui XTTS v2 implementation of the TTSProvider interface (spec 19.1).

    Sync contract: POST /tts_to_audio returns raw WAV bytes (no polling).
    Output: WAV 48 kHz mono. fallback_url points at Kokoro (same contract).

    synthesize() is dual-dispatch:
      - synthesize(text, language, TTSParams) -> AudioResult        (provider interface)
      - synthesize(CoquiSynthesisParams) -> CoquiSynthesisResult     (task interface,
        used by tasks.stage5_voiceover)

    NOTE: live synthesis, the Kokoro failover, and WAV-header parsing are
    validated in Stage 3 (requires a running TTS server).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        fallback_url: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or os.environ["COQUI_TTS_URL"]).rstrip("/")
        self.fallback_url = fallback_url.rstrip("/") if fallback_url else None
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def _post(self, base_url: str, payload: Dict[str, Any]) -> bytes:
        """Single synchronous TTS POST. Returns raw audio bytes. Raises typed CoquiError."""
        client = await self._get_client()
        try:
            response = await client.post(f"{base_url}/tts_to_audio", json=payload)
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise CoquiConnectionError(f"cannot reach Coqui at {base_url}: {e}", language=payload.get("language")) from e
        except httpx.HTTPStatusError as e:
            raise CoquiSynthesisError(str(e), status_code=e.response.status_code, language=payload.get("language")) from e
        return response.content

    async def _post_with_failover(self, payload: Dict[str, Any]):
        """POST to primary, failing over to fallback_url (Kokoro) on connection error. Returns (bytes, elapsed)."""
        start = time.monotonic()
        try:
            content = await self._post(self.base_url, payload)
        except CoquiConnectionError:
            if self.fallback_url:
                logger.warning("Coqui primary %s unreachable; failing over to %s (Kokoro)", self.base_url, self.fallback_url)
                content = await self._post(self.fallback_url, payload)
            else:
                raise
        return content, time.monotonic() - start

    async def _synthesize(self, params: CoquiSynthesisParams) -> CoquiSynthesisResult:
        """Core synthesis: POST, then parse the returned WAV for metadata."""
        lang = params.language.split("-")[0] if "-" in params.language else params.language
        payload = {
            "text": params.text,
            "language": lang,
            "speaker_wav": params.speaker_wav_path or "",
            "temperature": params.temperature,
            "length_penalty": params.length_penalty,
            "repetition_penalty": params.repetition_penalty,
            "top_k": params.top_k,
            "top_p": params.top_p,
            "speed": params.speed,
        }
        audio_bytes, elapsed = await self._post_with_failover(payload)

        sample_rate, bit_depth, channels, duration = 48000, 24, 1, 0.0
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as w:
                sample_rate = w.getframerate()
                channels = w.getnchannels()
                bit_depth = w.getsampwidth() * 8
                duration = w.getnframes() / sample_rate if sample_rate else 0.0
        except Exception:
            logger.warning("could not parse WAV header; using default audio metadata")

        return CoquiSynthesisResult(
            audio_data=audio_bytes,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            duration_seconds=duration,
            language=params.language,
            model_used="xtts-v2",
            generation_time_seconds=elapsed,
            params_hash=params.compute_hash(),
            text_length=len(params.text),
        )

    async def synthesize(self, text_or_params, language: str = "en", params: Optional[TTSParams] = None):
        """
        Dual-dispatch (see class docstring):
          - synthesize(CoquiSynthesisParams) -> CoquiSynthesisResult   (task path)
          - synthesize(text, language, TTSParams) -> AudioResult        (provider path)
        """
        if isinstance(text_or_params, CoquiSynthesisParams):
            return await self._synthesize(text_or_params)
        tts = params or TTSParams()
        rich = CoquiSynthesisParams(
            text=text_or_params,
            language=language,
            speaker_wav_path=tts.speaker_wav,
            speed=tts.speed,
        )
        result = await self._synthesize(rich)
        return AudioResult(
            audio_data=result.audio_data,
            sample_rate=result.sample_rate,
            duration_seconds=result.duration_seconds,
            format="wav",
        )

    def supported_languages(self) -> list[str]:
        """Return list of supported BCP-47 language codes."""
        return list(SUPPORTED_LANGUAGES.keys())

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
