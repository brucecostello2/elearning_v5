# Deployment Instructions — Prompt Management Fix

## PR #44: `fix/prompt-management-complete`
**Target branch:** `feature/admin-monitoring-implementation`

---

## Quick Deploy to node-01

### 1. Pull the branch
```bash
cd /path/to/elearning_v5
git fetch origin
git checkout fix/prompt-management-complete
git pull origin fix/prompt-management-complete
```

### 2. Targeted container restart
**IMPORTANT:** Use targeted restart, NOT `docker-compose down`.  
This avoids disrupting `ivgs-postgres` and other services.

```bash
# Restart API container (picks up backend changes)
docker-compose -f ivgs-infra/docker-compose.node01.yml \
  up -d --no-deps --force-recreate ivgs-fastapi

# Restart frontend container (picks up TypeScript/component changes)
docker-compose -f ivgs-infra/docker-compose.node01.yml \
  up -d --no-deps --force-recreate ivgs-nextjs
```

### 3. Verify
```bash
# Check containers are running
docker ps --filter "name=ivgs-fastapi" --filter "name=ivgs-nextjs"

# Check API health (port 8001)
curl -s http://localhost:8001/api/v1/health | jq .

# Check new endpoints exist
curl -s http://localhost:8001/openapi.json | jq '.paths | keys[]' | grep prompt
```

---

## Container Names (hyphens, not underscores)
| Service   | Container Name |
|-----------|---------------|
| API       | `ivgs-fastapi` |
| Frontend  | `ivgs-nextjs`  |
| Database  | `ivgs-postgres` |

---

## New API Endpoints Added

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/prompts/resolve` | Resolve effective prompt (SCENE→PROJECT→GLOBAL) |
| PUT | `/api/v1/prompts/{id}` | Update prompt text |
| DELETE | `/api/v1/prompts/{id}` | Soft-delete prompt |
| GET | `/api/v1/prompts/{id}/versions` | Version history |
| POST | `/api/v1/prompts/{id}/rollback` | Rollback to previous version |
| GET | `/api/v1/prompts/library` | List library prompts |
| DELETE | `/api/v1/prompts/library/{id}` | Remove from library |
| POST | `/api/v1/playground/execute` | Execute prompt in playground |
| POST | `/api/v1/playground/save` | Save playground result |

---

## No Database Migrations Required
All changes use existing database columns. No Alembic migrations needed.
