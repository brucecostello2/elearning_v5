# IVGS v5 — Celery Workers (ivgs-workers)
# Python 3.12 slim, GPU-ready base layer, non-root execution
FROM python:3.14.6-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY shared/requirements.txt /build/shared-requirements.txt
COPY ivgs-workers/requirements.txt /build/worker-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r /build/shared-requirements.txt \
    -r /build/worker-requirements.txt

# --- Runtime stage ---
FROM python:3.14.6-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r ivgs && useradd -r -g ivgs -m ivgs

COPY --from=builder /install /usr/local

WORKDIR /app

COPY shared/ /app/shared/
COPY ivgs-workers/ /app/

RUN chown -R ivgs:ivgs /app

USER ivgs

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD celery -A celery_app inspect ping --timeout=5 || exit 1

CMD ["celery", "-A", "worker", "worker", \
     "--loglevel=info", \
     "--concurrency=1", \
     "--prefetch-multiplier=1", \
     "-Ofair"]
