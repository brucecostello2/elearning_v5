# IVGS v5 — FastAPI Backend (ivgs-api)
# Python 3.12 slim base, non-root execution, health check
FROM python:3.14.5-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY shared/requirements.txt /build/shared-requirements.txt
COPY ivgs-api/requirements.txt /build/api-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r /build/shared-requirements.txt \
    -r /build/api-requirements.txt

# --- Runtime stage ---
FROM python:3.14.5-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r ivgs && useradd -r -g ivgs -m ivgs

COPY --from=builder /install /usr/local

WORKDIR /app

# Copy shared library
COPY shared/ /app/shared/

# Copy API application
COPY ivgs-api/ /app/

# Set ownership
RUN chown -R ivgs:ivgs /app

USER ivgs

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${UVICORN_PORT:-8001}", "--workers", "4"]
