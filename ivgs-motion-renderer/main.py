"""IVGS v5 — motion-graphics renderer (``ivgs-motion-renderer``).

WP-IVGS-09 Task 1, executing ledger **RC-I1**: *"A-4 renderer: APPROVED.
Technology RULED = the Pillow reference service — ``shared/motion/raster.py``
promoted behind a small HTTP service."*

WHAT THIS FILE IS, AND WHAT IT DELIBERATELY IS NOT
--------------------------------------------------

It is **transport and refusal**. Every pixel on every frame is drawn by
``shared.motion.raster``, which WP-68 wrote and proved, and every op on every
frame comes from ``shared.motion.templates``. This module opens a socket in
front of them, converts frames to a container, and says something true when it
cannot.

**It contains no drawing code, and it must not acquire any.** The brief is
explicit — *"the Pillow reference implementation IS the renderer; do not
reimplement it"* — and the reason is the one WP-68 states: the rasteriser is the
definition of what a drawing op MEANS. A second implementation here would be a
second answer, free to drift, with the templates' tests still green.

THE WIRE, AND WHERE IT COMES FROM
---------------------------------

Measured before it was designed (Task 1(a)), not invented:

* **The request shape is the scene's own ``generation_params``.** WP-68 §5.1
  measured two ``motion_graphics`` scenes storing, one each::

      {"template": "place_value_split", "number": 23}
      {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 0}

  — a FLAT object per scene: ``template`` plus that template's parameters, and
  the column is a ``Dict`` on the wire (``SceneCreate.generation_params``,
  ``ivgs-api/app/schemas/storyboard.py:66``). ``POST /render`` takes exactly
  that, unwrapped, so the worker forwards what the storyboard wrote rather than
  translating it. A translation layer is a place for a parameter to be dropped
  silently.

* **The accepted parameter set is WP-67's capability contract**, not this file's
  opinion: ``client_registry.py:437-447`` declares ``maths_motion`` with
  ``accepts_params = {template, number, top, bottom, step, column, label}`` and
  ``produces = "video/mp4"``. Both are enforced below —
  ``_ACCEPTED_PARAMS`` and the response media type.

* **The artifact shape is what Stage 7 consumes.** Traced through
  ``manifests.py:430-435`` (``asset_type`` → layer: only ``image`` and ``video``
  become ``background``) and ``stage7_prototype_draft.py:258-262``
  (``scene.media_type == "image"`` → ``.png``, ELSE ``.mp4``). A
  ``motion_graphics`` scene therefore reaches the compositor as ``.mp4``, and its
  asset must be registered ``asset_type="video"`` to become the background layer
  at all. So this service produces **MP4**, H.264, at the templates' own
  1280x720/30fps. It does not produce a PNG sequence and call it a render.

* **Duration is not a parameter, and that is measured too.**
  ``ffmpeg_client.py:445`` pads a short background with
  ``tpad=stop_mode=clone:stop_duration=<scene duration>`` — it holds the final
  frame. For column arithmetic the final frame is the answer, so a template
  shorter than its narration ends on the answer and stays there. Accepting a
  duration would mean stretching or truncating an animation whose timing is the
  teaching.

DETERMINISM
-----------

The property that makes this worth deploying. Two identical requests give
byte-identical frames, and the response says so in ``X-IVGS-Frames-Digest``
(sha256 over the PNG bytes of every frame, from ``raster.render_digest``).

The MP4 is *additionally* made reproducible — ``-fflags +bitexact``,
``-flags:v +bitexact``, ``-map_metadata -1`` — so no encoder version string or
creation timestamp lands in the container. The digest header is nevertheless
over FRAMES, not over the file: the frames are the thing the templates define,
and hashing the container would make a future ffmpeg upgrade look like a
template change.

NO FABRICATED FRAME, EVER
-------------------------

Every failure path below returns a named error and no image:

* unknown template            → 400, listing the templates that exist
* parameter outside the WP-67 contract → 400, naming the parameter
* parameter the template rejects → 400, quoting the ``TypeError``
* the pinned font is absent   → 503, quoting the rasteriser's own refusal
* ffmpeg missing or failing   → 502, quoting its stderr

There is no branch that answers with a placeholder, a blank canvas, a
substituted font or a cached frame from another request. That is the
fabricated-absence rule (WP-57/60) applied to a renderer: an image that is not
the requested render is worse than no image, because the pipeline cannot tell.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import structlog
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

# `shared/` is copied to /app/shared in the image and is importable from the
# repo root in a dev checkout. Nothing else from `shared` is imported: this
# service has no database, no Redis and no SeaweedFS.
from shared.motion import raster
from shared.motion.templates import (
    FPS,
    HEIGHT,
    WIDTH,
    render,
    template_names,
    template_spec,
)

logger = structlog.get_logger(__name__)

#: WP-67's capability contract, `client_registry.py:437-447`. Enforced rather
#: than documented: a parameter outside this set is refused by name, so a
#: storyboard that invents one is told, instead of having it silently ignored
#: while a picture comes back that does not reflect it.
#
# WP-IVGS-10 Task 4 adds `phase`, executing RC-O10. It is a template parameter
# like any other and is refused for a template that does not declare it, by the
# `extra` check below -- this set is the OUTER gate (the capability contract),
# `template_spec` is the inner one (what this template takes).
_ACCEPTED_PARAMS = frozenset(
    {"template", "number", "top", "bottom", "step", "column", "label", "phase"}
)

#: Filled in at build time by the Dockerfile (see `ARG IVGS_BUILD_REF`), the
#: same mechanism WP-IVGS-08 Task 3(a) gave the other four images after
#: measuring four different wrong answers to "which build is this".
BUILD_REF = os.environ.get("IVGS_BUILD_REF", "unknown")
BUILD_SHA = os.environ.get("IVGS_BUILD_SHA", "unknown")

FFMPEG = os.environ.get("IVGS_FFMPEG_BINARY", "ffmpeg")

app = FastAPI(
    title="IVGS motion-graphics renderer",
    version=BUILD_REF,
    description=(
        "Renders the WP-68 maths-teaching motion templates to MP4. "
        "CPU-only. No weights, no GPU, no model."
    ),
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _font_status() -> Dict[str, Any]:
    """What the rasteriser will actually draw with, or why it will refuse.

    Reported by `/healthz` because a missing font is the one failure that turns
    this service from working to refusing with no other symptom, and an
    operator should be able to see it before a render does.
    """
    candidates: list[Dict[str, Any]] = []
    for path in (raster.FONT_PATH, raster.FONT_FALLBACK):
        present = Path(path).is_file()
        row: Dict[str, Any] = {"path": path, "present": present}
        # EVERY present candidate is hashed, not only the one in use. Measured
        # 2026-08-28 inside this image: the vendored `DejaVuSans-Bold.ttf` and
        # the system one at `/usr/share/fonts/...` are the SAME TYPEFACE and
        # DIFFERENT BYTES -- `5c1247ac...` (Ubuntu noble, the copy the WP-68
        # determinism assertions were measured against) versus `0d977336...`
        # (Debian bookworm, which arrives transitively as an ffmpeg dependency
        # via `fontconfig-config`). Two builds of one face can differ in
        # hinting, and hinting is pixels. Surfacing both hashes is what lets an
        # operator SEE a substitution rather than infer it from a changed digest
        # three stages downstream.
        if present:
            row["sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        candidates.append(row)
    usable = next((c["path"] for c in candidates if c["present"]), None)
    entry: Dict[str, Any] = {"candidates": candidates, "in_use": usable}
    if usable:
        entry["sha256"] = next(c["sha256"] for c in candidates if c["path"] == usable)
        entry["vendored"] = usable == raster.FONT_PATH
    return entry


def _ffmpeg_version() -> str | None:
    if shutil.which(FFMPEG) is None:
        return None
    try:
        out = subprocess.run(
            [FFMPEG, "-version"], capture_output=True, text=True, timeout=10,
        )
        return out.stdout.splitlines()[0] if out.stdout else None
    except (OSError, subprocess.SubprocessError):
        return None


def _split_request(body: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """The flat scene-parameter object → (template name, template kwargs).

    Refuses by name on every path. `body` is the scene's `generation_params`
    entry verbatim; see the module docstring for where that shape was measured.
    """
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail=(
                "request body must be a JSON object of the shape a "
                "motion_graphics scene stores in generation_params, e.g. "
                '{"template": "place_value_split", "number": 23}'
            ),
        )

    name = body.get("template")
    if not name:
        raise HTTPException(
            status_code=400,
            detail=(
                "no 'template' in the request. Known templates: "
                + ", ".join(template_names())
            ),
        )

    unknown = sorted(set(body) - _ACCEPTED_PARAMS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"parameter(s) {unknown} are not in the maths_motion capability "
                f"contract (WP-67, client_registry.py:437-447), which accepts "
                f"{sorted(_ACCEPTED_PARAMS)}. Refused rather than ignored: a "
                f"silently dropped parameter renders a picture that does not "
                f"show what was asked for."
            ),
        )

    try:
        spec = template_spec(str(name))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    params = {k: v for k, v in body.items() if k != "template"}
    declared = set(spec["params"])
    extra = sorted(set(params) - declared)
    if extra:
        raise HTTPException(
            status_code=400,
            detail=(
                f"template {name!r} does not take {extra}; it takes "
                f"{sorted(declared)}"
            ),
        )
    return str(name), params


def _render_or_refuse(name: str, params: Dict[str, Any]):
    """Call the reference implementation. Translate its refusals; invent none."""
    try:
        return render(name, **params)
    except TypeError as exc:
        # A parameter the template cannot accept (wrong type, wrong arity).
        raise HTTPException(
            status_code=400, detail=f"template {name!r} rejected its parameters: {exc}",
        ) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=400, detail=f"template {name!r} refused: {exc}",
        ) from exc


#: Where the encoder writes. NOT `/dev/stdout`, and the reason is measured:
#: piping an MP4 out of ffmpeg fails outright ---
#:
#:     [mp4 @ ...] muxer does not support non seekable output
#:     Could not write header for output file #0
#:
#: --- because the MP4 muxer rewrites its header after the last frame, and
#: `+faststart` then moves the `moov` atom to the front so a consumer can start
#: playing without reading the whole file. Both need to seek. Caught live on
#: 2026-08-28 by the first real encode, AFTER a unit suite that had only ever
#: exercised the "no ffmpeg" refusal path --- which is why
#: `test_the_encoder_never_writes_an_mp4_to_a_non_seekable_target` exists.
_MP4_MUXER_NEEDS_A_SEEKABLE_FILE = True


def encode_cmd(fps: int, out_path: str) -> list[str]:
    """The ffmpeg invocation, as data, so a test can inspect it.

    Split out of `_frames_to_mp4` on 2026-08-28 for exactly one reason: the
    defect above was a wrong ARGUMENT, and a test can only assert on an argument
    it can see. Grepping the module source could not distinguish the command
    from the comment explaining why the command is what it is.
    """
    return [
        FFMPEG, "-hide_banner", "-nostdin", "-y",
        "-fflags", "+bitexact",
        "-f", "image2pipe", "-vcodec", "png",
        "-framerate", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-flags:v", "+bitexact",
        "-map_metadata", "-1",
        "-movflags", "+faststart",
        "-f", "mp4",
        out_path,
    ]


def _frames_to_mp4(rendered) -> bytes:
    """PNG frames → an H.264 MP4, reproducibly.

    Frames are PIPED IN, so no frame sequence is ever written to disk. The MP4
    is written to a private temporary file and read back, because the muxer
    cannot write to a pipe (see the constant above). The file is created with
    `NamedTemporaryFile`, so it has a unique name and is removed on the way out
    whether or not the encode succeeded --- two concurrent requests cannot read
    each other's output and nothing is left behind.

    `-fflags/-flags +bitexact` and `-map_metadata -1` keep the encoder version
    string and the creation time out of the container, so the same request twice
    gives the same FILE as well as the same frames.
    """
    if shutil.which(FFMPEG) is None:
        raise HTTPException(
            status_code=502,
            detail=(
                f"ffmpeg binary {FFMPEG!r} is not present in this image. The "
                f"renderer will not emit a frame sequence and call it a video."
            ),
        )

    payload = io.BytesIO()
    for i in range(len(rendered.frames)):
        payload.write(raster.frame_bytes(rendered, i))

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
        out_path = handle.name
    try:
        cmd = encode_cmd(rendered.fps, out_path)
        proc = subprocess.run(
            cmd, input=payload.getvalue(), capture_output=True, timeout=300,
        )
        data = b""
        if os.path.exists(out_path):
            with open(out_path, "rb") as fh:
                data = fh.read()
        if proc.returncode != 0 or not data:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"ffmpeg failed (exit {proc.returncode}) encoding "
                    f"{len(rendered.frames)} frames: "
                    f"{proc.stderr.decode('utf-8', 'replace')[-600:]}"
                ),
            )
        return data
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _guard_font() -> None:
    """Turn the rasteriser's own FileNotFoundError into a 503 before any work.

    Checked up front so the refusal costs nothing and names the real cause,
    rather than surfacing part-way through frame 40 of 128.
    """
    try:
        raster._font(48)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> JSONResponse:
    """Build ref and template inventory, as the brief requires.

    `status` is `degraded`, not `ok`, when the pinned font or ffmpeg is absent.
    Reporting `ok` while the only two things that can stop a render are missing
    would be a green light for a service that cannot render — the false-green
    defect WP-IVGS-08 §3.1 proved gone on the ingress and which is not being
    reintroduced here.
    """
    font = _font_status()
    ff = _ffmpeg_version()
    ready = bool(font["in_use"]) and ff is not None
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ok" if ready else "degraded",
            "service": "ivgs-motion-renderer",
            "build_ref": BUILD_REF,
            "build_sha": BUILD_SHA,
            "python": sys.version.split()[0],
            "canvas": {"width": WIDTH, "height": HEIGHT, "fps": FPS},
            "templates": list(template_names()),
            "template_count": len(template_names()),
            "font": font,
            "ffmpeg": ff,
            "accepts_params": sorted(_ACCEPTED_PARAMS),
            "produces": "video/mp4",
        },
    )


@app.get("/templates")
def templates() -> Dict[str, Any]:
    """The full inventory: every template, its parameters and what it teaches.

    Served from `template_spec`, so this cannot describe a template the
    renderer does not have.
    """
    return {
        "templates": [
            {
                "name": n,
                "params": template_spec(n)["params"],
                "describes": template_spec(n)["describes"],
            }
            for n in template_names()
        ],
    }


@app.post("/render")
def render_mp4(body: Dict[str, Any]) -> Response:
    """A scene's `generation_params` → one MP4. `video/mp4`, per WP-67."""
    name, params = _split_request(body)
    _guard_font()
    started = time.monotonic()

    rendered = _render_or_refuse(name, params)
    digest = raster.render_digest(rendered)
    data = _frames_to_mp4(rendered)

    logger.info(
        "motion_render_complete",
        template=name,
        params=params,
        frames=len(rendered.frames),
        duration_seconds=round(rendered.duration_seconds, 3),
        frames_digest=digest,
        bytes=len(data),
        elapsed_s=round(time.monotonic() - started, 2),
    )
    return Response(
        content=data,
        media_type="video/mp4",
        headers={
            "X-IVGS-Template": name,
            "X-IVGS-Frames": str(len(rendered.frames)),
            "X-IVGS-Fps": str(rendered.fps),
            "X-IVGS-Duration-Seconds": f"{rendered.duration_seconds:.3f}",
            # sha256 over the PNG bytes of EVERY frame. The determinism claim,
            # in a form a caller can check without decoding the container.
            "X-IVGS-Frames-Digest": digest,
            "X-IVGS-Build-Ref": BUILD_REF,
        },
    )


@app.post("/frame")
def frame_png(body: Dict[str, Any], index: int = 0) -> Response:
    """One frame as a PNG.

    Exists for two jobs the MP4 cannot do: proving determinism against exact
    bytes without an encoder in the way, and extracting a frame as evidence for
    a report. `index` is bounds-checked against the render rather than clamped —
    a caller asking for frame 500 of a 128-frame template has a bug, and
    returning frame 127 would hide it.
    """
    name, params = _split_request(body)
    _guard_font()
    rendered = _render_or_refuse(name, params)

    n = len(rendered.frames)
    if not 0 <= index < n:
        raise HTTPException(
            status_code=400,
            detail=f"frame {index} is outside template {name!r}, which has {n} frames (0..{n - 1})",
        )
    data = raster.frame_bytes(rendered, index)
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "X-IVGS-Template": name,
            "X-IVGS-Frame-Index": str(index),
            "X-IVGS-Frames": str(n),
            "X-IVGS-Frame-Digest": hashlib.sha256(data).hexdigest(),
            "X-IVGS-Build-Ref": BUILD_REF,
        },
    )
