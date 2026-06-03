"""
IVGS v5 - Coqui XTTS v2 TTS model server (sync; the PRIMARY TTS - Kokoro is its fallback).

Wire contract (from clients/coqui_client.py):
  GET  /health        -> 200 when the model is loaded (+ VRAM), else 503
  POST /tts_to_audio  -> raw WAV bytes
    JSON body: {text, language, speaker_wav, speed, temperature, length_penalty,
                repetition_penalty, top_k, top_p}

speaker_wav is a PATH the client sends. XTTS-v2 clones from a reference clip; if the
path is empty or not readable on THIS server, we fall back to a built-in XTTS speaker so
synthesis always succeeds. (For real cloning in production, mount the volume that holds
the reference clips into this container so the path resolves.)

Output: WAV at XTTS-v2's native rate; the client reads the rate from the WAV header.
Built on servers/common. Build context = ivgs-workers/servers.
"""
from __future__ import annotations

import os
import tempfile

from fastapi import HTTPException, Response
from pydantic import BaseModel

from common.base import create_app, env_int, get_model, run, setup_logging

log = setup_logging("coqui-tts")

XTTS_MODEL = os.environ.get("XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
DEFAULT_SPEAKER = os.environ.get("XTTS_DEFAULT_SPEAKER", "Claribel Dervla")
DEVICE = os.environ.get("DEVICE", "cuda")


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    speaker_wav: str = ""
    speed: float = 1.0
    # XTTS-specific tuning the client also sends; accepted (XTTS defaults match these):
    temperature: float = 0.75
    length_penalty: float = 1.0
    repetition_penalty: float = 5.0
    top_k: int = 50
    top_p: float = 0.85


def load():
    from TTS.api import TTS

    tts = TTS(XTTS_MODEL)
    tts.to(DEVICE)
    log.info("XTTS loaded: %s on %s", XTTS_MODEL, DEVICE)
    return tts


app = create_app("coqui-tts", load_fn=load)


def _lang(language: str) -> str:
    return language.split("-")[0].lower() if language else "en"


@app.post("/tts_to_audio")
async def tts_to_audio(req: TTSRequest) -> Response:
    tts = get_model(app)
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text is empty")

    kwargs = {"text": req.text, "language": _lang(req.language), "speed": req.speed}
    if req.speaker_wav and os.path.isfile(req.speaker_wav):
        kwargs["speaker_wav"] = req.speaker_wav
    else:
        if req.speaker_wav:
            log.warning(
                "speaker_wav %r not readable on this server; using built-in speaker %r",
                req.speaker_wav,
                DEFAULT_SPEAKER,
            )
        kwargs["speaker"] = DEFAULT_SPEAKER

    fd, out_path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
    os.close(fd)
    try:
        tts.tts_to_file(file_path=out_path, **kwargs)
        with open(out_path, "rb") as fh:
            wav = fh.read()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"xtts synthesis failed: {exc}")
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)
    return Response(content=wav, media_type="audio/wav")


if __name__ == "__main__":
    run(app, port=env_int("PORT", 5002))
