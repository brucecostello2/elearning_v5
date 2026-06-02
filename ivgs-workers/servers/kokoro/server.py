"""
IVGS v5 - Kokoro TTS model server (sync; English-only fallback for Coqui).

Wire contract (from clients/coqui_client.py - Kokoro is its fallback_url, same contract):
  GET  /health        -> 200 when the pipeline is loaded (+ VRAM), else 503
  POST /tts_to_audio  -> raw WAV bytes
    JSON body: {text, language, speaker_wav, speed, temperature, length_penalty,
                repetition_penalty, top_k, top_p}
    Kokoro uses only text / language / speed; the XTTS-specific fields and speaker_wav
    are accepted and ignored (Kokoro uses preset voices, not voice cloning).

Output: WAV PCM_16 mono @ 24 kHz (Kokoro native). The Coqui client reads the rate from
the WAV header, so the 24 kHz vs 48 kHz difference is handled client-side.

Built on servers/common (create_app + get_model). Build context = ivgs-workers/servers.
"""
from __future__ import annotations

import io
import os

import numpy as np
import soundfile as sf
from fastapi import HTTPException, Response
from pydantic import BaseModel

from common.base import create_app, env_int, get_model, run, setup_logging

log = setup_logging("kokoro-tts")

KOKORO_LANG_CODE = os.environ.get("KOKORO_LANG_CODE", "a")  # 'a' = American English
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
SAMPLE_RATE = 24000  # Kokoro native; changing this would require resampling
_ENGLISH = {"en", "en-us", "en-gb"}


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    speaker_wav: str = ""  # path or "" - ignored (Kokoro uses preset voices)
    speed: float = 1.0
    # XTTS-specific fields the Coqui client also sends; accepted and ignored:
    temperature: float = 0.75
    length_penalty: float = 1.0
    repetition_penalty: float = 5.0
    top_k: int = 50
    top_p: float = 0.85


def load():
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code=KOKORO_LANG_CODE)
    log.info("KPipeline loaded (lang_code=%s, default voice=%s)", KOKORO_LANG_CODE, KOKORO_VOICE)
    return pipeline


app = create_app("kokoro-tts", load_fn=load)


def _synthesize(pipeline, text: str, speed: float) -> bytes:
    """Run Kokoro over (possibly multi-chunk) text and return one WAV blob."""
    chunks = []
    for item in pipeline(text, voice=KOKORO_VOICE, speed=speed, split_pattern=r"\n+"):
        # Tolerate both the (graphemes, phonemes, audio) tuple and a Result-style object.
        audio = getattr(item, "audio", None)
        if audio is None:
            audio = item[-1]
        arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        chunks.append(np.asarray(arr, dtype=np.float32).reshape(-1))
    if not chunks:
        raise RuntimeError("kokoro produced no audio for the given text")
    wav = np.concatenate(chunks)
    buf = io.BytesIO()
    sf.write(buf, wav, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@app.post("/tts_to_audio")
async def tts_to_audio(req: TTSRequest) -> Response:
    pipeline = get_model(app)
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text is empty")
    if req.language and req.language.lower() not in _ENGLISH:
        log.warning(
            "kokoro is the English-only fallback; language=%s will be read as English",
            req.language,
        )
    wav = _synthesize(pipeline, req.text, req.speed)
    return Response(content=wav, media_type="audio/wav")


if __name__ == "__main__":
    run(app, port=env_int("PORT", 5003))
