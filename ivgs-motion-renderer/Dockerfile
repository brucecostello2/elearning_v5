# IVGS v5 — motion-graphics renderer (ivgs-motion-renderer)
#
# WP-IVGS-09 Task 1, executing RC-I1. CPU-ONLY BY CONSTRUCTION: no CUDA base,
# no torch, no model weights. The placement ruling (node-01) rests on that, and
# so does the Model Store's `weightless` row — an image that could load a model
# would make both statements false.
FROM python:3.12.8-slim-bookworm AS builder

WORKDIR /build

COPY ivgs-motion-renderer/requirements.txt /build/renderer-requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /build/renderer-requirements.txt

# --- Runtime stage ---
FROM python:3.12.8-slim-bookworm

# The image carries its own identity. Same mechanism WP-IVGS-08 Task 3(a) gave
# the other four images after measuring four different wrong answers to "which
# build is this" — and `dev/CLAUDE.md` §6 records that the env-injected
# `IVGS_*_TAG` is a known liar. `/healthz` reports these, not a tag variable.
ARG IVGS_BUILD_REF=unknown
ARG IVGS_BUILD_SHA=unknown
ENV IVGS_BUILD_REF=${IVGS_BUILD_REF} \
    IVGS_BUILD_SHA=${IVGS_BUILD_SHA}
LABEL org.opencontainers.image.version="${IVGS_BUILD_REF}" \
      org.opencontainers.image.revision="${IVGS_BUILD_SHA}"

# ffmpeg encodes the frames Pillow draws. curl is for the healthcheck.
#
# ⚠ NO FONT PACKAGE IS ASKED FOR -- AND ONE ARRIVES ANYWAY. Measured inside
# this image, 2026-08-28: `ffmpeg` pulls `fontconfig-config`, which pulls
# `fonts-dejavu-core`, so `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`
# exists here whether or not anyone wanted it.
#
# It is the same typeface and NOT the same bytes as the vendored copy:
# `0d977336...` (Debian bookworm) against `5c1247ac...` (Ubuntu noble, the copy
# WP-68's determinism assertions were measured against). Two builds of one face
# can differ in hinting, and hinting is pixels.
#
# THIS IS THE ARGUMENT FOR VENDORING, NOT AGAINST IT. `raster.FONT_PATH` names
# the in-repo file by absolute path, so the transitive copy is never reached
# while the vendored one is present, and `/healthz` hashes BOTH candidates so a
# substitution is visible rather than silent. Removing the transitive package
# would break ffmpeg's own text rendering and is not the fix.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r ivgs && useradd -r -g ivgs -m ivgs

COPY --from=builder /install /usr/local

WORKDIR /app

# `shared/motion/` only — not all of `shared/`. This service has no database,
# no Redis, no SeaweedFS and no provider registry, and copying them in would
# invite it to grow one. `shared/__init__.py` is needed for the package path.
COPY shared/__init__.py /app/shared/__init__.py
COPY shared/motion/ /app/shared/motion/
COPY ivgs-motion-renderer/main.py /app/main.py

RUN chown -R ivgs:ivgs /app

USER ivgs

EXPOSE 8500

# `/healthz` answers 503 when the pinned font or ffmpeg is missing, so this
# healthcheck fails for the two reasons that would otherwise leave a green
# container that cannot render.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8500/healthz || exit 1

# One worker. Rendering is CPU-bound and short; four uvicorn workers on a
# 16 GB node that also runs Postgres, Redis, SeaweedFS, the API and three
# Celery workers would compete for the cores that matter more.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8500", "--workers", "1"]
