# servers/common - shared wrapper skeleton (Build Plan section 6, D-wrapper-reuse)

Factored out of the proven `servers/cogvideox/server.py`. The node-04 media wrappers
share one app factory + lifespan + `/health`(+VRAM) + error handling (`base.py`), and the
async ones share the job lifecycle + `/status` `/download` `/metrics` (`jobs.py`).

`cogvideox` itself is left untouched (proven and deployed on node-02/03); it can be
retrofitted onto this base later.

## Build-context convention (IMPORTANT - differs from cogvideox)

These wrappers build with **context = `ivgs-workers/servers`** (the parent of `common/`
and each service dir) so the Dockerfile can pull in the shared package:

    # docker build -f servers/<svc>/Dockerfile  <context = ivgs-workers/servers>
    WORKDIR /app
    COPY common ./common
    COPY <svc>/server.py ./server.py
    COPY <svc>/requirements.txt ./requirements.txt
    # -> /app/common/*  and  /app/server.py ;  `import common.base` resolves

(`cogvideox` keeps context = its own service dir; it has no `common` dependency.)

## Sync service (Coqui, Kokoro, WhisperX)

    from common.base import create_app, get_model, run

    def load():
        ...
        return model

    app = create_app("kokoro-tts", load_fn=load)

    @app.post("/tts_to_audio")
    async def tts_to_audio(req: TTSParams):
        model = get_model(app)             # raises 503 until loaded
        wav = synth(model, req)
        return Response(content=wav, media_type="audio/wav")

    if __name__ == "__main__":
        run(app)                           # host 0.0.0.0, port from $PORT

## Async service (LatentSync, SadTalker)

    from common.base import create_app, run
    from common.jobs import JobStore, register_job_routes

    store = JobStore(ttl_seconds=3600)

    def runner(job, params, image_path):   # SYNC; runs in a worker thread
        out = render(...)
        job.output_path = out
        job.duration = seconds
        job.metrics = {"alignment_score": score, "duration_seconds": seconds}

    app = create_app("latentsync", load_fn=load)
    register_job_routes(app, store, download_media_type="video/mp4", with_metrics=True)

    @app.post("/")
    async def submit(...multipart...):
        job = store.submit(runner, params, image_path)
        return {"job_id": job.job_id}

    if __name__ == "__main__":
        run(app)

## Notes

- `load_fn` is sync and blocking; it runs once during startup (before the app accepts
  connections), so blocking the loop there is fine. On load failure the model is `None`
  and `/health` reports 503 (the container HEALTHCHECK `start-period` must cover the load).
- `vram_stats()` is safe without torch/CUDA (returns `{"cuda": false}`), so `/health`
  never 500s on a stats hiccup.
- Pin `fastapi==0.115.0` / `uvicorn[standard]==0.30.6` / `pydantic==2.9.2` to match the
  fleet (lifespan is supported there).
