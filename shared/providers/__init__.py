"""
Provider abstraction interfaces for all AI services (§19.1).

All pipeline task code calls provider interfaces ONLY. The concrete
implementation behind each interface may be swapped (e.g. new model)
by updating the provider class — no task code changes required.

This is the primary technical lesson from the v4 failure (§1.3.3).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# Shared parameter / result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LLMParams:
    """Parameters for LLM inference."""
    model: str = "llama-3.3-70b"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9
    stop: Optional[list[str]] = None
    timeout_seconds: int = 120


@dataclass
class LLMResponse:
    """Result from an LLM inference call."""
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"


@dataclass
class ImageParams:
    """Parameters for image generation."""
    width: int = 1024
    height: int = 1024
    steps: int = 50
    cfg_scale: float = 7.5
    seed: Optional[int] = None
    model: str = "flux1-dev"
    timeout_seconds: int = 300


@dataclass
class ImageResult:
    """Result from an image generation call."""
    image_data: bytes
    width: int
    height: int
    seed: int = 0
    model: str = ""


@dataclass
class TTSParams:
    """Parameters for text-to-speech synthesis."""
    speaker_wav: Optional[str] = None  # Path to reference voice clip
    speed: float = 1.0
    sample_rate: int = 48000
    timeout_seconds: int = 120


@dataclass
class AudioResult:
    """Result from a TTS synthesis call."""
    audio_data: bytes
    sample_rate: int = 48000
    duration_seconds: float = 0.0
    format: str = "wav"


@dataclass
class VideoParams:
    """Parameters for video generation."""
    width: int = 480
    height: int = 480
    fps: int = 24
    num_frames: int = 48
    seed: Optional[int] = None
    model: str = "cogvideox-5b"
    timeout_seconds: int = 1800


@dataclass
class VideoResult:
    """Result from a video generation call."""
    video_data: bytes
    width: int
    height: int
    fps: int = 24
    duration_seconds: float = 0.0
    model: str = ""


# ---------------------------------------------------------------------------
# Abstract provider interfaces
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract interface for Large Language Model providers."""

    @abstractmethod
    async def generate(self, prompt: str, params: LLMParams) -> LLMResponse:
        """Generate text from a prompt."""
        ...

    @abstractmethod
    async def stream(self, prompt: str, params: LLMParams) -> Iterator[str]:
        """Stream generated text tokens."""
        ...


class ImageProvider(ABC):
    """Abstract interface for image generation providers."""

    @abstractmethod
    async def generate(self, prompt: str, params: ImageParams) -> ImageResult:
        """Generate an image from a text prompt."""
        ...


class TTSProvider(ABC):
    """Abstract interface for text-to-speech providers."""

    @abstractmethod
    async def synthesize(
        self, text: str, language: str, params: TTSParams
    ) -> AudioResult:
        """Synthesize speech audio from text."""
        ...

    @abstractmethod
    def supported_languages(self) -> list[str]:
        """Return list of supported BCP-47 language codes."""
        ...


class VideoProvider(ABC):
    """Abstract interface for video generation providers."""

    @abstractmethod
    async def generate(
        self, prompt: str, params: VideoParams
    ) -> VideoResult:
        """Generate a video clip from a text prompt."""
        ...

    @abstractmethod
    def max_clip_duration_seconds(self) -> float:
        """Return maximum supported clip duration in seconds."""
        ...


@dataclass
class STTParams:
    """Parameters for speech-to-text transcription."""
    language: Optional[str] = None
    model_size: str = "large-v3"
    word_timestamps: bool = True
    output_format: str = "srt"
    timeout_seconds: int = 300


@dataclass
class STTResult:
    """Result from a speech-to-text transcription."""
    text: str
    segments: list = field(default_factory=list)
    language: str = ""
    duration_seconds: float = 0.0


class STTProvider(ABC):
    """Abstract interface for speech-to-text providers."""

    @abstractmethod
    async def transcribe(
        self, audio_path: str, params: STTParams
    ) -> STTResult:
        """Transcribe audio to text with timestamps."""
        ...

    @abstractmethod
    async def align(
        self, audio_path: str, transcript: str, language: str
    ) -> STTResult:
        """Force-align a transcript to audio for word-level timestamps."""
        ...
