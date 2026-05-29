# =============================================================================
# IVGS v5 — Backup Worker (ivgs-backup-worker)
# =============================================================================
# Dedicated Celery worker container for Phase 14 backup operations.
#
# Why a separate image (not reusing ivgs-workers):
#   - Backup worker needs docker.sock access (verify_backup.sh spins up a temp
#     postgres container).  GPU workers should not have docker.sock access.
#   - Backup worker needs the GPG private key.  GPU workers should not.
#   - Backup worker needs psql + gpg + docker-cli.  GPU workers don't.
#   - Isolating the privileged container reduces blast radius if any GPU
#     worker is compromised (large attack surface from external models).
#
# Listens on Celery queue:  `backup`
# Tasks:  run_full_database_backup, run_asset_backup, run_config_backup,
#         run_verification
# =============================================================================

FROM python:3.12.8-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY shared/requirements.txt /build/shared-requirements.txt
COPY ivgs-backup-worker/requirements.txt /build/backup-worker-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r /build/shared-requirements.txt \
    -r /build/backup-worker-requirements.txt

# --- Runtime stage ---
FROM python:3.12.8-slim-bookworm

# Phase 14 backup tooling:
#   docker.io  — invoke docker run/exec for verify_backup.sh's temp postgres
#   gnupg      — gpg for encrypt/decrypt operations
#   postgresql-client-17 — psql for verify queries (matches server version)
#   rsync      — used by asset_backup.sh and config_backup.sh
#   gzip       — backup.sh compresses dumps
#   curl       — pushgateway metric pushes
#   ca-certificates — TLS for any HTTPS callouts
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 ca-certificates curl gnupg \
        docker.io \
        rsync gzip uuid-runtime \
    && rm -rf /var/lib/apt/lists/*

# postgresql-client-17 comes from postgresql.org repository (Debian's default
# is too old). Add the official Postgres apt repo, then install only the client.
RUN install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
       https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

# Create ivgs user matching the existing service convention (UID 999).
# We also need ivgs to be in the docker group so it can use docker.sock.
# The docker group GID inside the container should match the host's docker
# group GID, which is set via compose's `group_add: ["${DOCKER_GID}"]`.
RUN groupadd -r ivgs && useradd -r -g ivgs -m -d /home/ivgs ivgs

COPY --from=builder /install /usr/local

WORKDIR /app
COPY shared/ /app/shared/
COPY ivgs-backup-worker/ /app/

# /app/.gnupg will be mount target for GPG key.  Pre-create so permissions are
# already right when the bind mount lands here.
RUN mkdir -p /home/ivgs/.gnupg \
    && chown -R ivgs:ivgs /home/ivgs/.gnupg \
    && chmod 700 /home/ivgs/.gnupg

RUN chown -R ivgs:ivgs /app

USER ivgs
ENV GNUPGHOME=/home/ivgs/.gnupg

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD celery -A celery_app inspect ping --timeout=5 || exit 1

# Single worker process — backups are infrequent, no need for concurrency.
# --prefetch-multiplier=1 means each worker pulls one task at a time
# (no over-buffering, important for long-running tasks like full DB backup).
# -Ofair distributes tasks fairly when concurrency > 1.
CMD ["celery", "-A", "celery_app", "worker", \
     "--loglevel=info", \
     "--queues=backup", \
     "--concurrency=1", \
     "--prefetch-multiplier=1", \
     "-Ofair", \
     "-n", "backup-worker@node01"]
