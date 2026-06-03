"""
IVGS v5 - WhisperX large-v3 STT / alignment model server (sync; port 9000).

Wire contract (the STTProvider contract in shared/providers + Build Plan 3.6):
  GET  /health      -> 200 when the model is loaded (+ VRAM), else 503   (from common.base)
  POST /transcribe  -> JSON STTResult {text, segments[], language, duration_seconds}
       body: {audio_path, language, model_size, word_timestamps, output_format}
  POST /align       -> JSON STTResult {text, segments[], language, duration_seconds}
       body: {audio_path, transcript, language}

audio_path is a path the client sends. In the cluster the audio lives on the shared NFS
(/mnt/ivgs-shared, mounted into this container), so the calling worker writes/locates the
audio there and passes the path; this server reads it via ffmpeg (whisperx.load_audio).

Each segment carries word-level timing: {start, end, text, words:[{word,start,end,score}]}.
The four STTResult fields are the contract; the response also includes "srt" and "vtt"
strings (rendered from the aligned segments) because spec 7.1.6 lists SRT/VTT as WhisperX
outputs - they are extra, not part of STTResult. Per 19.1, turning captions into stored
assets stays in the orchestration layer, not here.

Built on servers/common. Build context = ivgs-workers/servers.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from common.base import create_app, env_int, get_model, run, setup_logging

log = setup_logging("whisperx")

DEVICE = os.environ.get("DEVICE", "cuda")
DEFAULT_MODEL = os.environ.get("WHISPERX_MODEL", "large-v3")
# CTranslate2 compute type for the ASR pass. "float16" needs a GPU build of CTranslate2;
# override to int8 / int8_float16 / float32 if the installed build lacks kernels for this card.
COMPUTE_TYPE = os.environ.get("WHISPERX_COMPUTE_TYPE", "float16")
BATCH_SIZE = env_int("WHISPERX_BATCH_SIZE", 16)
SAMPLE_RATE = 16000  # whisperx.load_audio always resamples to 16 kHz mono


class TranscribeRequest(BaseModel):
    audio_path: str
    language: Optional[str] = None
    model_size: str = DEFAULT_MODEL
    word_timestamps: bool = True
    output_format: str = "srt"


class AlignRequest(BaseModel):
    audio_path: str
    transcript: str
    language: str = "en"


def load():
    """Load the WhisperX ASR model once at startup. Alignment models differ by language and
    are loaded lazily (and cached) on first use, so the holder carries an 'align' cache dict."""
    import whisperx

    model = whisperx.load_model(DEFAULT_MODEL, DEVICE, compute_type=COMPUTE_TYPE)
    log.info("WhisperX ASR loaded: %s on %s (compute_type=%s)", DEFAULT_MODEL, DEVICE, COMPUTE_TYPE)
    return {"asr": model, "align": {}}


app = create_app("whisperx", load_fn=load)


def _require_audio(path: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=422, detail="audio_path is empty")
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail=f"audio_path not found on server: {path}")


def _get_align_model(state: dict, language: str):
    """Load + cache the wav2vec2 alignment model for a language code."""
    import whisperx

    cache = state["align"]
    if language not in cache:
        model_a, metadata = whisperx.load_align_model(language_code=language, device=DEVICE)
        cache[language] = (model_a, metadata)
        log.info("loaded alignment model for language=%s", language)
    return cache[language]


def _full_text(segments: list) -> str:
    return " ".join(s.get("text", "").strip() for s in segments).strip()


def _fmt_ts(seconds: float, sep: str) -> str:
    # sep="," -> SRT (HH:MM:SS,mmm); sep="." -> VTT (HH:MM:SS.mmm)
    ms = int(round(max(seconds, 0.0) * 1000.0))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _to_srt(segments: list) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        start = _fmt_ts(float(seg.get("start", 0.0)), ",")
        end = _fmt_ts(float(seg.get("end", 0.0)), ",")
        blocks.append(f"{i}\n{start} --> {end}\n{seg.get('text', '').strip()}\n")
    return "\n".join(blocks).strip() + ("\n" if blocks else "")


def _to_vtt(segments: list) -> str:
    out = ["WEBVTT", ""]
    for seg in segments:
        start = _fmt_ts(float(seg.get("start", 0.0)), ".")
        end = _fmt_ts(float(seg.get("end", 0.0)), ".")
        out.append(f"{start} --> {end}")
        out.append(seg.get("text", "").strip())
        out.append("")
    return "\n".join(out).strip() + "\n"


def _result(segments: list, language: str, duration: float) -> dict:
    return {
        "text": _full_text(segments),
        "segments": segments,
        "language": language,
        "duration_seconds": round(float(duration), 3),
        "srt": _to_srt(segments),
        "vtt": _to_vtt(segments),
    }


@app.post("/transcribe")
async def transcribe(req: TranscribeRequest) -> dict:
    import whisperx

    _require_audio(req.audio_path)
    state = get_model(app)
    asr = state["asr"]

    t0 = time.time()
    audio = whisperx.load_audio(req.audio_path)
    duration = float(len(audio)) / SAMPLE_RATE
    try:
        asr_kwargs = {"batch_size": BATCH_SIZE}
        if req.language:
            asr_kwargs["language"] = req.language
        result = asr.transcribe(audio, **asr_kwargs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"whisperx transcribe failed: {exc}")

    language = result.get("language") or (req.language or "en")
    segments = result.get("segments", [])

    if req.word_timestamps and segments:
        try:
            model_a, metadata = _get_align_model(state, language)
            aligned = whisperx.align(
                segments, model_a, metadata, audio, DEVICE, return_char_alignments=False
            )
            segments = aligned.get("segments", segments)
        except Exception as exc:
            log.warning("alignment failed (language=%s); returning unaligned segments: %s", language, exc)

    log.info("transcribe ok: %d segs, language=%s, %.2fs wall", len(segments), language, time.time() - t0)
    return _result(segments, language, duration)


@app.post("/align")
async def align(req: AlignRequest) -> dict:
    import whisperx

    _require_audio(req.audio_path)
    if not req.transcript or not req.transcript.strip():
        raise HTTPException(status_code=422, detail="transcript is empty")
    state = get_model(app)

    audio = whisperx.load_audio(req.audio_path)
    duration = float(len(audio)) / SAMPLE_RATE
    # Force-align the supplied transcript: present it as one segment spanning the clip and let
    # whisperx.align split it into word-level timings.
    segments_in = [{"text": req.transcript.strip(), "start": 0.0, "end": duration}]
    try:
        model_a, metadata = _get_align_model(state, req.language)
        aligned = whisperx.align(
            segments_in, model_a, metadata, audio, DEVICE, return_char_alignments=False
        )
        segments = aligned.get("segments", segments_in)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"whisperx align failed: {exc}")

    log.info("align ok: %d segs, language=%s", len(segments), req.language)
    return _result(segments, req.language, duration)


if __name__ == "__main__":
    run(app, port=env_int("PORT", 9000))
