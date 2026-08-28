# IVGS v5 — FastAPI Backend (ivgs-api)
# Python 3.12 slim base, non-root execution, health check
FROM python:3.14.7-slim-bookworm AS builder

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
FROM python:3.14.7-slim-bookworm

# WP-IVGS-08 Task 3(a). THE IMAGE NOW CARRIES ITS OWN IDENTITY.
#
# Measured 2026-08-27 (WP-IVGS-03 S2.4): the running image was v5.27.0-motion
# while /health said 5.0.0, openapi said 5.1.0 and IVGS_API_TAG said
# v5.1.14-stream-b -- four answers, none of them right, and nothing inside the
# image knew which build it was. dev/CLAUDE.md S6 already documents that the
# env-injected tag is a known liar; this is the fix for the other half.
ARG IVGS_BUILD_REF=unknown
ARG IVGS_BUILD_SHA=unknown
ENV IVGS_BUILD_REF=${IVGS_BUILD_REF} \
    IVGS_BUILD_SHA=${IVGS_BUILD_SHA}
LABEL org.opencontainers.image.version="${IVGS_BUILD_REF}" \
      org.opencontainers.image.revision="${IVGS_BUILD_SHA}"

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
