# IVGS v5 Node-01 — Comprehensive Root Cause Analysis

**Date:** 2026-05-22  
**Node:** node-01 (192.168.1.90)  
**Repository:** `brucecostello2/elearning_v5`  
**Branch:** `fix/add-worker-models-task-result`  
**Compose file:** `ivgs-infra/docker-compose.node01.yml` (503 lines, 15 services)

---

## 1. System Architecture — Service Dependency Map

```
                          ┌──────────────────┐
                          │    nginx (:443)   │
                          │   reverse proxy   │
                          └───────┬──────┬────┘
                     depends_on   │      │   depends_on
                    (healthy)     │      │   (healthy)
                   ┌──────────────┘      └────────────────┐
                   ▼                                      ▼
          ┌─────────────────┐                   ┌──────────────────┐
          │ fastapi-backend  │                   │ nextjs-frontend  │
          │   (:8001)        │                   │   (:3001)        │
          │ GHCR image       │                   │  GHCR image      │
          └──┬────┬────┬─────┘                   └──────────────────┘
             │    │    │                              (no deps)
             │    │    │ depends_on (healthy)
             ▼    ▼    ▼
    ┌──────────┐ ┌───────┐ ┌──────────────┐
    │ postgres │ │ redis │ │seaweedfs-filer│
    │ (:5432)  │ │(:6379)│ │  (:8888)     │
    └──────────┘ └───────┘ └──────┬───────┘
                                  │ depends_on (healthy)
                           ┌──────┴──────┐
                           │seaweedfs-   │
                           │  master     │
                           │  (:9333)    │
                           └──────┬──────┘
                                  │ depends_on (healthy)
                           ┌──────┴──────┐
                           │seaweedfs-   │
                           │  volume     │
                           │  (:8080)    │
                           └─────────────┘

  ┌────────────────────┐     ┌──────────────┐
  │ celery-worker-     │     │ celery-beat  │
  │   default          │     │              │
  │ (ivgs-workers img) │     │(ivgs-workers)│
  └──┬────┬────────────┘     └──┬────┬──────┘
     │    │ depends_on          │    │ depends_on
     ▼    ▼ (healthy)           ▼    ▼ (healthy)
  postgres  redis            postgres  redis

  ┌────────────────────┐
  │ ivgs-scheduler     │
  │   (:8001→:8002)    │
  │  GHCR image        │
  └──┬────┬────────────┘
     │    │ depends_on (healthy)
     ▼    ▼
  postgres  redis

  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  ┌─────────────────────┐
  │  prometheus  │  │ grafana  │  │ node-exporter │  │ github-actions-     │
  │  (:9090)     │  │ (:3000)  │  │  (:9100)      │  │   runner            │
  └──────────────┘  └────┬─────┘  └───────────────┘  └─────────────────────┘
                         │ depends_on (healthy)
                    prometheus
```

### Dependency chains (longest to shortest):

| Chain | Depth | Implication |
|-------|-------|-------------|
| nginx → fastapi → postgres + redis + seaweedfs-filer → seaweedfs-master | 4 | Nginx won't start until entire backend chain is healthy |
| nginx → nextjs-frontend | 2 | Independent; only needs healthy frontend |
| grafana → prometheus | 2 | Monitoring chain |
| celery-worker → postgres + redis | 2 | Workers blocked if DB/Redis unhealthy |
| celery-beat → postgres + redis | 2 | Beat blocked if DB/Redis unhealthy |
| seaweedfs-filer → seaweedfs-master | 2 | Filer blocked if master unhealthy |
| seaweedfs-volume → seaweedfs-master | 2 | Volume blocked if master unhealthy |

---

## 2. Complete Service Inventory

| # | Service | Container Name | Image Source | Port (host:container) | Has Healthcheck | Depends On |
|---|---------|---------------|-------------|----------------------|-----------------|------------|
| 1 | postgres | ivgs-postgres | `postgres:17.2@sha256:3d9e...` | 127.0.0.1:5432:5432 | ✅ pg_isready | — |
| 2 | redis | ivgs-redis | `redis:7.4@sha256:e422...` | 127.0.0.1:6379:6379 | ✅ redis-cli ping | — |
| 3 | seaweedfs-master | ivgs-seaweedfs-master | `chrislusf/seaweedfs:3.71@sha256:a1b2...` ⚠️ | 127.0.0.1:9333:9333 | ✅ wget localhost:9333 | — |
| 4 | seaweedfs-volume | ivgs-seaweedfs-volume | `chrislusf/seaweedfs:3.71@sha256:a1b2...` ⚠️ | 127.0.0.1:8080:8080 | ✅ wget localhost:8080 | seaweedfs-master (healthy) |
| 5 | seaweedfs-filer | ivgs-seaweedfs-filer | `chrislusf/seaweedfs:3.71@sha256:a1b2...` ⚠️ | 127.0.0.1:8888:8888 | ✅ wget localhost:8888 | seaweedfs-master (healthy) |
| 6 | fastapi-backend | ivgs-fastapi | `ghcr.io/.../ivgs-api:${IVGS_API_TAG}` 🔴 | 127.0.0.1:8001:8001 | ✅ curl localhost:8001 | postgres, redis, seaweedfs-filer |
| 7 | ivgs-scheduler | ivgs-scheduler | `ghcr.io/.../ivgs-scheduler:${IVGS_SCHEDULER_TAG}` 🔴 | 127.0.0.1:8002:8001 | ✅ curl localhost:8001 | postgres, redis |
| 8 | nextjs-frontend | ivgs-nextjs | `ghcr.io/.../ivgs-frontend:${IVGS_FRONTEND_TAG}` 🔴 | 127.0.0.1:3001:3001 | ✅ curl localhost:3001 | — |
| 9 | nginx | ivgs-nginx | `nginx:1.27@sha256:c2e7...` ⚠️ | 0.0.0.0:443:443, 80:80 | ✅ curl localhost:80 | fastapi-backend, nextjs-frontend |
| 10 | celery-worker-default | ivgs-celery-default | `ivgs-workers:${IVGS_WORKERS_TAG:-v5.1.0}` ✅ local | — | ✅ celery inspect ping | postgres, redis |
| 11 | celery-beat | ivgs-celery-beat | `ivgs-workers:${IVGS_WORKERS_TAG:-v5.1.0}` ✅ local | — | ❌ **NONE** | postgres, redis |
| 12 | prometheus | ivgs-prometheus | `prom/prometheus:v2.53.0@sha256:f5a7...` ⚠️ | 127.0.0.1:9090:9090 | ✅ wget localhost:9090 | — |
| 13 | grafana | ivgs-grafana | `grafana/grafana:11.1.0@sha256:b1c2...` ⚠️ | 127.0.0.1:3000:3000 | ✅ curl localhost:3000 | prometheus (healthy) |
| 14 | node-exporter | ivgs-node-exporter | `prom/node-exporter:v1.8.1@sha256:a1b2...` ⚠️ | 0.0.0.0:9100:9100 | ✅ wget localhost:9100 | — |
| 15 | github-actions-runner | ivgs-github-runner | `ghcr.io/actions/actions-runner:2.319.1@sha256:c1d2...` ⚠️ | — | ❌ **NONE** | — |

**Legend:**
- 🔴 = Critical issue (will fail to start)
- ⚠️ = Fake/invalid SHA256 digest (will fail `docker pull`)
- ✅ = Correct or already fixed

---

## 3. Root Cause Analysis — Every Issue Found

### Category A: Image Pull Failures (8 services affected)

#### A1. Fabricated SHA256 Digests — 7 public images 🔴

**Evidence:** The following SHA256 digests are fabricated placeholders with sequential hex patterns (`a1b2c3d4e5f6...`). Docker will fail to pull ANY of these images because the digest won't match any manifest in the registry.

| Image | Digest | Pattern |
|-------|--------|---------|
| `chrislusf/seaweedfs:3.71` | `sha256:a1b2c3d4e5f6a7b8...` | Sequential `a1b2c3d4` repeating |
| `nginx:1.27` | `sha256:c2e7e5e8e9b4f3a1...` | Sequential variant |
| `prom/prometheus:v2.53.0` | `sha256:f5a7b8c9d0e1f2a3...` | Sequential variant |
| `grafana/grafana:11.1.0` | `sha256:b1c2d3e4f5a6b7c8...` | Sequential variant |
| `prom/node-exporter:v1.8.1` | `sha256:a1b2c3d4e5f6a7b8...` | Same as seaweedfs |
| `ghcr.io/actions/actions-runner:2.319.1` | `sha256:c1d2e3f4a5b6c7d8...` | Sequential variant |

**Note:** `postgres:17.2` and `redis:7.4` digests *appear* more random but may also be fabricated — they should be verified with `docker pull --quiet` on node-01.

**Impact:** SeaweedFS (master, volume, filer), nginx, prometheus, grafana, node-exporter, and GitHub runner will all fail `docker compose pull`.

**Fix:** Either:
1. **Remove the `@sha256:...` suffix entirely** — Docker will pull by tag only (simpler, recommended for initial deployment)
2. **Replace with real digests** from `docker pull <image>:<tag>` then `docker inspect --format='{{index .RepoDigests 0}}' <image>:<tag>`

#### A2. GHCR Images Never Published — 3 application services 🔴

**Evidence:** `docker-compose.node01.yml` references these GHCR images:
```yaml
fastapi-backend:  ghcr.io/brucecostello2/ivgs-api:${IVGS_API_TAG}
ivgs-scheduler:   ghcr.io/brucecostello2/ivgs-scheduler:${IVGS_SCHEDULER_TAG}
nextjs-frontend:  ghcr.io/brucecostello2/ivgs-frontend:${IVGS_FRONTEND_TAG}
```

Unauthenticated API check returns HTTP 401 (packages likely don't exist or are private with no push history). There is no CI/CD pipeline in the repo to build and push these images.

**Impact:** FastAPI, scheduler, and frontend services cannot start — images don't exist in the registry.

**Fix:** Build locally on node-01 from the Dockerfiles:
```bash
# From repo root (/opt/ivgs)
docker build -f ivgs-api/Dockerfile -t ivgs-api:v5.1.0 .
docker build -f ivgs-scheduler/Dockerfile -t ivgs-scheduler:v5.1.0 .
docker build -f ivgs-frontend/Dockerfile -t ivgs-frontend:v5.1.0 .
```
Then update compose file to use local image names:
```yaml
fastapi-backend:  image: ivgs-api:${IVGS_API_TAG:-v5.1.0}
ivgs-scheduler:   image: ivgs-scheduler:${IVGS_SCHEDULER_TAG:-v5.1.0}
nextjs-frontend:  image: ivgs-frontend:${IVGS_FRONTEND_TAG:-v5.1.0}
```

---

### Category B: Health Check Failures (3 services affected)

#### B1. FastAPI Dockerfile — Health check targets wrong port 🔴

**Evidence (ivgs-api/Dockerfile line 45):**
```dockerfile
HEALTHCHECK ... CMD curl -f http://localhost:8000/api/v1/health || exit 1
```

But the app listens on port **8001** (both `EXPOSE 8001` and `main.py` defaults to 8001). The health check hits port 8000 which has nothing listening → always fails → container marked `unhealthy`.

**Impact:** `fastapi-backend` is perpetually unhealthy → nginx (which depends on it being healthy) never starts.

**Fix:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1
```

#### B2. FastAPI Dockerfile — CMD won't expand env var 🟡

**Evidence (ivgs-api/Dockerfile line 47):**
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${UVICORN_PORT:-8001}", "--workers", "4"]
```

JSON-array (exec form) `CMD` does **not** invoke a shell, so `${UVICORN_PORT:-8001}` is passed literally as the string `"${UVICORN_PORT:-8001}"` to uvicorn, which will crash with "invalid port". 

**Impact:** API service won't start at all unless this is fixed.

**Fix:** Either use shell form or hardcode:
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
```

#### B3. Celery Beat — No healthcheck defined 🟡

**Evidence:** The `celery-beat` service (lines 382-404) has no `healthcheck:` block. While it has `depends_on` with `service_healthy` conditions for postgres/redis, celery-beat itself has no health indicator.

**Impact:** No visibility into whether beat is actually running and scheduling tasks. If beat crashes silently, periodic tasks (DLQ processing, retention cleanup, heartbeat checks) stop with no alert.

**Fix:**
```yaml
healthcheck:
  <<: *common-healthcheck
  test: ["CMD-SHELL", "celery -A celery_app inspect ping --timeout=10 || exit 1"]
```
(Or check for PID file: `test -f /tmp/celerybeat.pid && kill -0 $(cat /tmp/celerybeat.pid)`)

#### B4. GitHub Actions Runner — No healthcheck defined 🟡

**Evidence:** `github-actions-runner` (lines 490-502) has no healthcheck. It also keeps restarting (per user context).

**Impact:** Runner restart loops go undetected by orchestration.

---

### Category C: Network / IP Address Issues (1 category, 10+ env vars affected)

#### C1. Hardcoded 10.10.0.x IPs — spec vs reality mismatch 🔴

**Evidence:** The compose file and `.env.template` reference `10.10.0.x` addresses for GPU nodes, but the actual network uses `192.168.1.x`.

| Variable | Current Value | Should Be |
|----------|--------------|-----------|
| `VLLM_PRIMARY_URL` | `http://10.10.0.2:8000/v1` | `http://192.168.1.72:8000/v1` (or actual IP) |
| `VLLM_SECONDARY_URL` | `http://10.10.0.3:8000/v1` | `http://192.168.1.73:8000/v1` |
| `VLLM_MIDSIZE_URL` | `http://10.10.0.4:8000/v1` | `http://192.168.1.74:8000/v1` |
| `OLLAMA_URL` | `http://10.10.0.5:11434` | `http://192.168.1.75:11434` |
| `COMFYUI_PRIMARY_URL` | `http://10.10.0.4:8188` | `http://192.168.1.74:8188` |
| `COMFYUI_FALLBACK_URL` | `http://10.10.0.5:8188` | `http://192.168.1.75:8188` |
| `COQUI_TTS_URL` | `http://10.10.0.4:5002` | `http://192.168.1.74:5002` |
| `LATENTSYNC_URL` | `http://10.10.0.4:7860` | `http://192.168.1.74:7860` |
| `REMOTION_URL` | `http://10.10.0.6:3002` | `http://192.168.1.76:3002` |

**Note:** `.env.template` also has `10.10.0.1` for DATABASE_URL, REDIS_URL, etc. — but in docker-compose.node01.yml these correctly use Docker service names (`postgres:5432`, `redis:6379`), so the env template is only wrong for external use.

**Impact:** FastAPI backend and worker tasks that reach out to GPU nodes will get connection timeouts/refusals on every pipeline operation. The system starts but every pipeline job fails.

**Fix:** These must be corrected in `.env.node01` (the actual env file, not the template). Since we don't have the env file in the repo, the user must update it on node-01 with the actual GPU node IPs.

---

### Category D: Nginx Configuration Issues

#### D1. Nginx upstreams use 127.0.0.1 instead of Docker service names 🔴

**Evidence (`configs/nginx/nginx.conf` lines 69-81):**
```nginx
upstream fastapi {
    server 127.0.0.1:8001;
}
upstream nextjs {
    server 127.0.0.1:3001;
}
upstream grafana {
    server 127.0.0.1:3000;
}
```

Inside a Docker container, `127.0.0.1` refers to the container's **own** loopback, not the host. Nginx cannot reach fastapi/nextjs/grafana via `127.0.0.1`.

**Impact:** Nginx starts (its health check is `/health` which returns a static 200) but ALL proxy traffic fails with 502 Bad Gateway.

**Fix:** Use Docker service names:
```nginx
upstream fastapi {
    server fastapi-backend:8001;
}
upstream nextjs {
    server nextjs-frontend:3001;
}
upstream grafana {
    server grafana:3000;
}
```

#### D2. SSL certificates don't exist 🔴

**Evidence:** `configs/nginx/ssl/` only contains `generate-certs.sh` — no actual `.crt` or `.key` files. Nginx config references:
```nginx
ssl_certificate /etc/nginx/ssl/ivgs.crt;
ssl_certificate_key /etc/nginx/ssl/ivgs.key;
```

**Impact:** Nginx will fail to start with "cannot load certificate" error on the HTTPS server block.

**Fix:** Run the certificate generation script before deployment:
```bash
cd configs/nginx/ssl && bash generate-certs.sh
```
Or create self-signed certs:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout configs/nginx/ssl/ivgs.key \
  -out configs/nginx/ssl/ivgs.crt \
  -subj "/CN=ivgs-node01/O=IVGS"
```

---

### Category E: Frontend Port Mismatch

#### E1. Frontend Dockerfile exposes 3000, compose expects 3001 🔴

**Evidence:**
- `ivgs-frontend/Dockerfile` line 28: `EXPOSE 3000`
- `ivgs-frontend/Dockerfile` line 33: `ENV PORT=3000`
- `ivgs-frontend/Dockerfile` line 31: healthcheck targets `localhost:3000`
- `docker-compose.node01.yml` line 303: `PORT: "3001"` (overrides)
- `docker-compose.node01.yml` line 305: `ports: "127.0.0.1:3001:3001"`
- `docker-compose.node01.yml` line 310: healthcheck targets `localhost:3001`

The compose file overrides `PORT=3001`, but the port mapping is `3001:3001` which means the container must listen on 3001 internally. Next.js standalone server respects the `PORT` env var, so it will listen on 3001. **However**, the Dockerfile's built-in healthcheck still checks port 3000.

**Impact:** If Docker uses the Dockerfile healthcheck (lower priority than compose healthcheck), it will fail. With the compose healthcheck override, it should work — but the Dockerfile EXPOSE is misleading.

**Severity:** Low if compose healthcheck wins (it does). But the Dockerfile should be fixed for consistency.

**Fix:** Update Dockerfile to match:
```dockerfile
EXPOSE 3001
ENV PORT=3001
HEALTHCHECK ... CMD wget -qO- http://localhost:3001/ || exit 1
```

---

### Category F: Missing Configuration Files

#### F1. No Prometheus config directory 🟡

**Evidence:** `configs/prometheus/` directory does not exist, but compose mounts:
```yaml
- ./configs/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
- ./configs/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro
```

**Impact:** Prometheus container will fail to start — Docker bind mount fails if source file doesn't exist.

**Fix:** Create `configs/prometheus/prometheus.yml` and `configs/prometheus/alert_rules.yml`.

#### F2. No Grafana provisioning directory 🟡

**Evidence:** `configs/grafana/` directory does not exist, but compose mounts:
```yaml
- ./configs/grafana/provisioning/datasources:/etc/grafana/provisioning/datasources:ro
- ./configs/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro
- ./configs/grafana/dashboards:/var/lib/grafana/dashboards:ro
```

**Impact:** Grafana container will fail to start.

**Fix:** Create the directory structure with minimal provisioning configs.

#### F3. WAL archive script dependency 🟡

**Evidence (docker-compose.node01.yml line 103):**
```yaml
-c archive_command='/scripts/wal_archive.sh %p %f'
```
The script exists at `./scripts/wal_archive.sh` in the repo, but is NOT mounted into the postgres container. The container has no `/scripts/` directory.

**Impact:** PostgreSQL will start but WAL archiving will fail silently (non-zero exit from archive_command logs a warning but doesn't prevent operation). Backups based on WAL shipping will be broken.

**Fix:** Add volume mount:
```yaml
volumes:
  - ./scripts:/scripts:ro
```

#### F4. Host mount paths may not exist 🟡

**Evidence:** Several services mount host paths:
- `/mnt/ivgs-shared` (fastapi, celery-worker, seaweedfs-volume)
- `/mnt/backup/ivgs/wal` (postgres)

**Impact:** If these directories don't exist on node-01, Docker will create them as root-owned empty dirs, which may cause permission issues.

**Fix:** Pre-create with correct ownership:
```bash
sudo mkdir -p /mnt/ivgs-shared /mnt/backup/ivgs/wal
sudo chown 999:999 /mnt/backup/ivgs/wal  # postgres UID
```

---

### Category G: Environment Variable Issues

#### G1. Missing `.env.node01` file 🔴

**Evidence:** The compose file references `env_file: - .env.node01` but this file is not in the repository (correctly `.gitignored`). The `.env.template` exists but must be copied and customized.

**Required variables (from compose `${VAR:?...}` patterns):**
- `POSTGRES_PASSWORD` — required by postgres, fastapi, scheduler, celery services
- `IVGS_API_TAG` — required by fastapi-backend
- `IVGS_SCHEDULER_TAG` — required by ivgs-scheduler
- `IVGS_FRONTEND_TAG` — required by nextjs-frontend
- `GRAFANA_ADMIN_PASSWORD` — required by grafana
- `GITHUB_REPO_URL` — required by github-actions-runner
- `GITHUB_RUNNER_TOKEN` — required by github-actions-runner

**Impact:** `docker compose up` will immediately fail with "variable is not set" errors.

#### G2. Celery Result Backend uses psycopg2 driver 🟡

**Evidence (docker-compose.node01.yml lines 352, 392):**
```
IVGS_CELERY_RESULT_BACKEND: db+postgresql+psycopg2://...
```

This requires `psycopg2-binary` in the workers image. Checking `ivgs-workers/requirements.txt`:
```
psycopg2-binary==2.9.10  ← present ✅
```

This is correct but note the API uses `postgresql+psycopg` (psycopg3) while Celery result backend uses `postgresql+psycopg2` (psycopg2). This is intentional — Celery's SQLAlchemy result backend only supports psycopg2.

#### G3. Worker config.py uses `IVGS_` prefix, compose must match 🟢

**Evidence:** `config.py` reads `IVGS_CELERY_BROKER_URL`, `IVGS_CELERY_RESULT_BACKEND`, `IVGS_VLLM_PRIMARY_URL`, etc.

The compose file correctly sets `IVGS_CELERY_BROKER_URL` and `IVGS_CELERY_RESULT_BACKEND` for celery services. ✅

But: `VLLM_PRIMARY_URL` in the fastapi-backend environment block doesn't use the `IVGS_` prefix. This is fine if the FastAPI app reads `VLLM_PRIMARY_URL` directly (not via WorkerConfig). ✅ Confirmed: FastAPI reads env vars directly, workers use config.py.

---

### Category H: Service-Specific Issues

#### H1. Scheduler port conflict 🟡

**Evidence:**
- Scheduler container listens internally on port 8001 (`SCHEDULER_PORT: "8001"`)
- FastAPI also listens internally on port 8001
- Compose maps scheduler to host port 8002: `127.0.0.1:8002:8001`
- FastAPI references scheduler at `GPU_SCHEDULER_URL: http://ivgs-scheduler:8001`

This is actually **correct** — inside the Docker network, each container has its own network namespace, so both can listen on 8001 internally. The `GPU_SCHEDULER_URL` correctly uses the container name and internal port.

**Status:** ✅ No issue (just potentially confusing)

#### H2. GitHub Actions Runner — perpetual restart loop 🟡

**Evidence:** The runner requires a valid `GITHUB_RUNNER_TOKEN` which is a one-time registration token. Once the runner registers, the token becomes invalid. If the container restarts after registration, the token in the env var is stale.

**Impact:** Runner container goes into a restart loop after initial setup.

**Fix:** The runner should be registered once, then its configuration persisted via a volume mount:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - runner-data:/home/runner  # ADD THIS
```

#### H3. SeaweedFS version mismatch 🟡

**Evidence:**
- `docker-compose.node01.yml`: `chrislusf/seaweedfs:3.71`
- `docker-compose.base.yml`: `chrislusf/seaweedfs:3.80`

Two different versions are specified for dev vs production. This could cause data format incompatibilities.

---

## 4. Issue Priority Matrix

| Priority | ID | Issue | Services Affected | Blocks Startup? |
|----------|-----|-------|------------------|-----------------|
| 🔴 P0 | A1 | Fake SHA256 digests | 7 services | YES — cannot pull images |
| 🔴 P0 | A2 | GHCR images not published | 3 services | YES — cannot pull images |
| 🔴 P0 | G1 | Missing .env.node01 | ALL services | YES — compose fails immediately |
| 🔴 P0 | B2 | API CMD env var not expanded | fastapi-backend | YES — uvicorn crashes |
| 🔴 P0 | B1 | API healthcheck wrong port | fastapi-backend → nginx | YES — perpetually unhealthy |
| 🔴 P0 | D1 | Nginx 127.0.0.1 upstreams | nginx | YES — 502 on all traffic |
| 🔴 P0 | D2 | SSL certs missing | nginx | YES — cannot start |
| 🔴 P0 | E1 | Frontend port mismatch (Dockerfile) | nextjs-frontend | Partial — compose overrides mitigate |
| 🔴 P0 | F1 | Prometheus config missing | prometheus → grafana | YES — both fail |
| 🔴 P0 | F2 | Grafana config missing | grafana | YES — cannot start |
| 🔴 P0 | C1 | Wrong GPU node IPs (10.10.0.x) | fastapi, workers | NO start block, but all GPU jobs fail |
| 🟡 P1 | B3 | Celery beat no healthcheck | celery-beat | No — but no monitoring |
| 🟡 P1 | B4 | Runner no healthcheck | github-runner | No — but restart loops hidden |
| 🟡 P1 | F3 | WAL archive script not mounted | postgres | No — but backup broken |
| 🟡 P1 | F4 | Host mount dirs may not exist | multiple | No — Docker auto-creates |
| 🟡 P1 | H2 | Runner token stale on restart | github-runner | Yes — restart loop |
| 🟡 P1 | H3 | SeaweedFS version mismatch | seaweedfs (all) | No — but risk |
| 🟢 P2 | G2 | psycopg2 vs psycopg3 dual drivers | workers | No — intentional |

---

## 5. Convergent Remediation Plan — Correct Execution Order

### Phase 0: Pre-flight (on node-01, before any Docker operations)

```bash
# 0.1 — Create .env.node01 from template
cd /opt/ivgs
cp .env.template .env.node01

# 0.2 — Edit .env.node01 with real values
cat >> .env.node01 << 'EOF'
# === REQUIRED: Fill these in ===
POSTGRES_PASSWORD=<generate-strong-password>
GRAFANA_ADMIN_PASSWORD=<generate-strong-password>
GITHUB_REPO_URL=https://github.com/brucecostello2/elearning_v5
GITHUB_RUNNER_TOKEN=<get-from-github-settings>

# === Image tags (local builds) ===
IVGS_API_TAG=v5.1.0
IVGS_SCHEDULER_TAG=v5.1.0
IVGS_FRONTEND_TAG=v5.1.0
IVGS_WORKERS_TAG=v5.1.0

# === Fix GPU node IPs ===
VLLM_PRIMARY_URL=http://192.168.1.72:8000/v1
VLLM_SECONDARY_URL=http://192.168.1.73:8000/v1
VLLM_MIDSIZE_URL=http://192.168.1.74:8000/v1
OLLAMA_URL=http://192.168.1.75:11434
COMFYUI_PRIMARY_URL=http://192.168.1.74:8188
COMFYUI_FALLBACK_URL=http://192.168.1.75:8188
COQUI_TTS_URL=http://192.168.1.74:5002
LATENTSYNC_URL=http://192.168.1.74:7860
REMOTION_URL=http://192.168.1.76:3002
EOF

# 0.3 — Create required host directories
sudo mkdir -p /mnt/ivgs-shared /mnt/backup/ivgs/wal

# 0.4 — Generate SSL certificates
cd /opt/ivgs/configs/nginx/ssl
bash generate-certs.sh   # or manual openssl command
```

**Validation:**
```bash
[ -f .env.node01 ] && echo "✅ .env.node01 exists" || echo "❌ missing"
[ -f configs/nginx/ssl/ivgs.crt ] && echo "✅ SSL cert" || echo "❌ missing"
[ -d /mnt/ivgs-shared ] && echo "✅ shared mount" || echo "❌ missing"
```

### Phase 1: Fix docker-compose.node01.yml — Image References

**1.1 Remove fake SHA256 digests from all public images:**
```yaml
# BEFORE:
image: chrislusf/seaweedfs:3.71@sha256:a1b2c3d4e5f6...
# AFTER:
image: chrislusf/seaweedfs:3.71

# Repeat for: nginx, prometheus, grafana, node-exporter, actions-runner
# Also verify: postgres, redis digests with docker pull
```

**1.2 Change GHCR references to local images:**
```yaml
# BEFORE:
image: ghcr.io/brucecostello2/ivgs-api:${IVGS_API_TAG:?...}
# AFTER:
image: ivgs-api:${IVGS_API_TAG:-v5.1.0}

# Same for ivgs-scheduler and ivgs-frontend
```

**Validation:**
```bash
grep -c "sha256:a1b2\|sha256:c2e7\|sha256:f5a7\|sha256:b1c2\|sha256:c1d2" docker-compose.node01.yml
# Should output: 0
grep -c "ghcr.io" docker-compose.node01.yml
# Should output: 0 (or just the runner if keeping it)
```

### Phase 2: Fix Dockerfiles

**2.1 Fix ivgs-api/Dockerfile — healthcheck port + CMD:**
```dockerfile
# Line 45: Fix healthcheck port
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1

# Line 47: Fix CMD to not use shell expansion in exec form
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
```

**2.2 Fix ivgs-frontend/Dockerfile — port consistency:**
```dockerfile
EXPOSE 3001
ENV PORT=3001
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -qO- http://localhost:3001/ || exit 1
```

**Validation:**
```bash
grep "8000" ivgs-api/Dockerfile
# Should output: nothing
grep "3000" ivgs-frontend/Dockerfile
# Should output: nothing
```

### Phase 3: Fix Nginx Configuration

**3.1 Update upstream definitions in `configs/nginx/nginx.conf`:**
```nginx
upstream fastapi {
    server fastapi-backend:8001;
    keepalive 32;
}
upstream nextjs {
    server nextjs-frontend:3001;
    keepalive 16;
}
upstream grafana {
    server grafana:3000;
    keepalive 8;
}
```

**Validation:**
```bash
grep "127.0.0.1" configs/nginx/nginx.conf
# Should output: nothing in upstream blocks
```

### Phase 4: Create Missing Config Files

**4.1 Prometheus config:**
```bash
mkdir -p configs/prometheus
cat > configs/prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - alert_rules.yml

scrape_configs:
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']
  - job_name: 'fastapi'
    static_configs:
      - targets: ['fastapi-backend:8001']
    metrics_path: /metrics
  - job_name: 'scheduler'
    static_configs:
      - targets: ['ivgs-scheduler:8001']
    metrics_path: /metrics
EOF

cat > configs/prometheus/alert_rules.yml << 'EOF'
groups:
  - name: ivgs_alerts
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 5m
        labels:
          severity: critical
EOF
```

**4.2 Grafana provisioning:**
```bash
mkdir -p configs/grafana/provisioning/datasources
mkdir -p configs/grafana/provisioning/dashboards
mkdir -p configs/grafana/dashboards

cat > configs/grafana/provisioning/datasources/prometheus.yml << 'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
    access: proxy
EOF

cat > configs/grafana/provisioning/dashboards/default.yml << 'EOF'
apiVersion: 1
providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    options:
      path: /var/lib/grafana/dashboards
EOF
```

**4.3 Mount WAL archive script into postgres:**

Add to postgres service volumes in compose:
```yaml
volumes:
  - postgres-data:/var/lib/postgresql/data
  - /mnt/backup/ivgs/wal:/mnt/wal-archive
  - ./scripts:/scripts:ro          # ADD THIS
```

### Phase 5: Fix GPU Node IPs in Compose File

Update the hardcoded IPs in `fastapi-backend` environment block:
```yaml
environment:
  # ... keep database/redis/seaweedfs as Docker service names ...
  VLLM_PRIMARY_URL: http://192.168.1.72:8000/v1
  VLLM_SECONDARY_URL: http://192.168.1.73:8000/v1
  VLLM_MIDSIZE_URL: http://192.168.1.74:8000/v1
  OLLAMA_URL: http://192.168.1.75:11434
  COMFYUI_PRIMARY_URL: http://192.168.1.74:8188
  COMFYUI_FALLBACK_URL: http://192.168.1.75:8188
  COQUI_TTS_URL: http://192.168.1.74:5002
  LATENTSYNC_URL: http://192.168.1.74:7860
  REMOTION_URL: http://192.168.1.76:3002
```

### Phase 6: Add Missing Healthchecks

**6.1 Celery beat healthcheck:**
```yaml
celery-beat:
  # ... existing config ...
  healthcheck:
    <<: *common-healthcheck
    test: ["CMD-SHELL", "test -f /tmp/celerybeat.pid && kill -0 $(cat /tmp/celerybeat.pid) || exit 1"]
```

**6.2 GitHub runner healthcheck (optional):**
```yaml
github-actions-runner:
  # ... existing config ...
  healthcheck:
    <<: *common-healthcheck
    test: ["CMD-SHELL", "pgrep -f 'Runner.Listener' || exit 1"]
```

### Phase 7: Build Images & Deploy

```bash
cd /opt/ivgs

# 7.1 — Pull public images (with fixed tags, no fake digests)
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 pull \
  postgres redis seaweedfs-master seaweedfs-volume seaweedfs-filer \
  nginx prometheus grafana node-exporter

# 7.2 — Build application images locally
docker build -f ivgs-api/Dockerfile -t ivgs-api:v5.1.0 .
docker build -f ivgs-scheduler/Dockerfile -t ivgs-scheduler:v5.1.0 .
docker build -f ivgs-frontend/Dockerfile -t ivgs-frontend:v5.1.0 .
docker build -f ivgs-workers/Dockerfile -t ivgs-workers:v5.1.0 .

# 7.3 — Start infrastructure tier first
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d postgres redis

# Wait for healthy
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  ps postgres redis
# Both should show "healthy"

# 7.4 — Start storage tier
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d seaweedfs-master
sleep 10
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d seaweedfs-volume seaweedfs-filer

# 7.5 — Start application tier
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d fastapi-backend ivgs-scheduler nextjs-frontend

# 7.6 — Start worker tier
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d celery-worker-default celery-beat

# 7.7 — Start nginx (depends on fastapi + nextjs being healthy)
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d nginx

# 7.8 — Start monitoring tier
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d prometheus node-exporter
sleep 10
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d grafana

# 7.9 — Start CI/CD (optional, fix runner token first)
docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01 \
  up -d github-actions-runner
```

### Phase 8: Validation Tests

```bash
COMPOSE="docker compose -f ivgs-infra/docker-compose.node01.yml --env-file .env.node01"

echo "=== Service Health ==="
$COMPOSE ps --format 'table {{.Name}}\t{{.Status}}'

echo "=== Test 1: PostgreSQL ==="
$COMPOSE exec postgres pg_isready -U ivgs -d ivgs && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 2: Redis ==="
$COMPOSE exec redis redis-cli ping | grep PONG && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 3: SeaweedFS Master ==="
curl -sf http://localhost:9333/cluster/status && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 4: SeaweedFS Volume ==="
curl -sf http://localhost:8080/status && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 5: SeaweedFS Filer ==="
curl -sf http://localhost:8888/ && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 6: FastAPI Health ==="
curl -sf http://localhost:8001/api/v1/health && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 7: Scheduler Health ==="
curl -sf http://localhost:8002/health && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 8: Frontend ==="
curl -sf http://localhost:3001/ > /dev/null && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 9: Nginx HTTPS ==="
curl -sf -k https://localhost/health && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 10: Nginx API Proxy ==="
curl -sf -k https://localhost/api/v1/health && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 11: Celery Worker ==="
$COMPOSE exec celery-worker-default celery -A celery_app inspect registered \
  | grep -c "stage" && echo "✅ PASS (tasks registered)" || echo "❌ FAIL"

echo "=== Test 12: Prometheus ==="
curl -sf http://localhost:9090/-/healthy && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 13: Grafana ==="
curl -sf http://localhost:3000/api/health && echo "✅ PASS" || echo "❌ FAIL"

echo "=== Test 14: Node Exporter ==="
curl -sf http://localhost:9100/metrics | head -1 && echo "✅ PASS" || echo "❌ FAIL"
```

---

## 6. Summary — Why Iterative Troubleshooting Wasn't Converging

The deployment has **12 independent P0 blocking issues** across 6 categories. Fixing one at a time leads to a whack-a-mole pattern because:

1. **Image pull failures** mask all other issues (you can't see healthcheck bugs if the container never starts)
2. **The dependency chain** means fixing a leaf service (e.g., fastapi) doesn't help if its dependencies (postgres, redis, seaweedfs) are also broken
3. **Two layers of configuration** (compose file + `.env.node01`) mean fixes in one layer can be undone by the other
4. **Nginx appears healthy** (static /health endpoint) while silently failing all proxy traffic — masking the real issue (wrong upstream addresses)
5. **The Dockerfile vs compose healthcheck precedence** causes confusion — compose healthcheck wins at runtime, but Dockerfile healthcheck matters when images are used elsewhere

The convergent fix is to address ALL issues in the correct order (env → images → config → build → deploy → validate) before starting any containers.

---

## Appendix A: Complete File Change Manifest

| File | Changes Needed |
|------|---------------|
| `.env.node01` | **CREATE** — copy from template, fill secrets, fix IPs |
| `ivgs-infra/docker-compose.node01.yml` | Remove fake SHA256 digests (7), change GHCR→local (3), fix GPU IPs (9), add celery-beat healthcheck, add postgres script mount |
| `ivgs-api/Dockerfile` | Fix healthcheck port 8000→8001, fix CMD env var expansion |
| `ivgs-frontend/Dockerfile` | Fix EXPOSE/PORT/healthcheck 3000→3001 |
| `configs/nginx/nginx.conf` | Change upstreams from 127.0.0.1 to Docker service names |
| `configs/nginx/ssl/ivgs.crt` | **CREATE** — generate self-signed cert |
| `configs/nginx/ssl/ivgs.key` | **CREATE** — generate private key |
| `configs/prometheus/prometheus.yml` | **CREATE** — scrape config |
| `configs/prometheus/alert_rules.yml` | **CREATE** — alert rules |
| `configs/grafana/provisioning/datasources/prometheus.yml` | **CREATE** — datasource config |
| `configs/grafana/provisioning/dashboards/default.yml` | **CREATE** — dashboard provider |

**Total: 11 files to create/modify before a single container can be started successfully.**
