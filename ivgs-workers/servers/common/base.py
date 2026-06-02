"""
IVGS v5 - Shared FastAPI base for media-server wrappers (Build Plan section 6, D-wrapper-reuse).

Factored out of the proven servers/cogvideox/server.py so the five node-04 wrappers
(Coqui, Kokoro, WhisperX = sync; LatentSync, SadTalker = async) share one app factory,
lifespan model load/unload, /health with VRAM, and consistent error handling.

A SYNC service builds its app like:

    from common.base import create_app, get_model, run

    def load():
        ...
        return model_object          # heavy, blocking; runs once at startup

    app = create_app("kokoro-tts", load_fn=load)

    @app.post("/tts_to_audio")
    async def tts_to_audio(req: TTSParams):
        model = get_model(app)       # 503 until loaded
        ...
        return Response(content=wav_bytes, media_type="audio/wav")

    if __name__ == "__main__":
        run(app)

ASYNC (job-based) services additionally use common.jobs.

Build note: these wrappers build with context = ivgs-workers/servers (NOT the service
dir), so the Dockerfile can `COPY common ./common` alongside `COPY <svc>/server.py .`.
torch is optional at import time - vram_stats() degrades gracefully if it is absent.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def setup_logging(name: str) -> logging.Logger:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger(name)


def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def vram_stats() -> dict:
    """VRAM usage for the active CUDA device. Safe when torch/CUDA are unavailable."""
    try:
        import torch
    except Exception:
        return {"cuda": False}
    if not torch.cuda.is_available():
        return {"cuda": False}
    try:
        dev = torch.cuda.current_device()
        free, total = torch.cuda.mem_get_info(dev)
        return {
            "cuda": True,
            "device": dev,
            "name": torch.cuda.get_device_name(dev),
            "total_mb": round(total / 1048576),
            "free_mb": round(free / 1048576),
            "allocated_mb": round(torch.cuda.memory_allocated(dev) / 1048576),
            "reserved_mb": round(torch.cuda.memory_reserved(dev) / 1048576),
        }
    except Exception as exc:  # defensive - never let /health 500 on a stats hiccup
        return {"cuda": True, "error": str(exc)}


# load_fn is a SYNC callable: the heavy, blocking load runs once during startup
# (before the app accepts connections), so blocking the loop there is fine.
LoadFn = Callable[[], Any]
UnloadFn = Callable[[Any], None]


def create_app(
    service: str,
    *,
    load_fn: LoadFn,
    unload_fn: Optional[UnloadFn] = None,
    title: Optional[str] = None,
) -> FastAPI:
    """
    Build a FastAPI app with:
      - a lifespan that runs load_fn() at startup, stores the result on
        app.state.model, and runs unload_fn(model) at shutdown;
      - GET /health -> 200 {"status":"healthy","service","vram"} when the model is
        loaded, else 503 {"status":"model_not_loaded", ...};
      - a catch-all handler that turns genuinely-unhandled errors into a consistent
        JSON 500 (HTTPExceptions keep their own status via Starlette's inner handler).
    """
    log = setup_logging(service)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model = None
        log.info("loading model for service=%s", service)
        try:
            model = load_fn()
        except Exception:
            log.exception("model load failed for service=%s", service)
            model = None
        app.state.model = model
        if model is None:
            log.error("service=%s started WITHOUT a model (health will report 503)", service)
        else:
            log.info("service=%s model loaded; vram=%s", service, vram_stats())
        try:
            yield
        finally:
            if unload_fn is not None and app.state.model is not None:
                try:
                    unload_fn(app.state.model)
                except Exception:
                    log.exception("unload_fn failed for service=%s", service)
            app.state.model = None

    app = FastAPI(title=title or f"IVGS {service} model server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> JSONResponse:
        ok = getattr(app.state, "model", None) is not None
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "status": "healthy" if ok else "model_not_loaded",
                "service": service,
                "vram": vram_stats(),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    app.state.log = log
    return app


def get_model(app: FastAPI) -> Any:
    """Return the loaded model, or raise 503 if it is not ready."""
    model = getattr(app.state, "model", None)
    if model is None:
        raise HTTPException(status_code=503, detail="model_not_loaded")
    return model


def run(app: FastAPI, port: Optional[int] = None) -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port or env_int("PORT", 8000))
