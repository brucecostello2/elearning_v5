# IVGS v5 — GPU Scheduler Microservice (ivgs-scheduler)
# Standalone FastAPI service on node-01:8001
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY shared/requirements.txt /build/shared-requirements.txt
COPY ivgs-scheduler/requirements.txt /build/scheduler-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r /build/shared-requirements.txt \
    -r /build/scheduler-requirements.txt

# --- Runtime stage ---
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r ivgs && useradd -r -g ivgs -m ivgs

COPY --from=builder /install /usr/local

WORKDIR /app

COPY shared/ /app/shared/
COPY ivgs-scheduler/ /app/

RUN chown -R ivgs:ivgs /app

USER ivgs

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
