"""
API v1 router aggregation.

All v1 sub-routers are included here with appropriate prefixes and tags.
Per §5.1: Every endpoint is registered under /api/v1/.
"""
from fastapi import APIRouter

# --- Core routers (previously registered) ---
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.health import router as health_router

# --- Domain routers ---
from app.api.v1.projects import router as projects_router
from app.api.v1.assets import project_router as project_assets_router
from app.api.v1.assets import asset_router as assets_router
from app.api.v1.transcripts import router as transcripts_router
from app.api.v1.storyboard import router as storyboard_router
from app.api.v1.languages import router as languages_router
from app.api.v1.jobs import project_job_router, job_router

# --- Prompt routers (§9) ---
from app.api.v1.prompts import (
    global_router as prompts_global_router,
    library_router as prompts_library_router,
    playground_router as prompts_playground_router,
    project_prompt_router,
    scene_prompt_router,
)

# --- Quality & Pipeline routers ---
from app.api.v1.quality import job_quality_router, quality_router
from app.api.v1.checkpoints import router as checkpoints_router
from app.api.v1.manifests import router as manifests_router

# --- Infrastructure routers ---
from app.api.v1.nodes import router as nodes_router
from app.api.v1.gpus import router as gpus_router
from app.api.v1.dlq import router as dlq_router
from app.api.v1.alerts import router as alerts_router

# --- Operations routers ---
from app.api.v1.retention import router as retention_router
from app.api.v1.quotas import router as quotas_router
from app.api.v1.backup import router as backup_router
from app.api.v1.rollback import router as rollback_router

# --- WebSocket ---
from app.api.v1.ws_logs import router as ws_logs_router


api_v1_router = APIRouter()

# Health (no prefix — mounted at /api/v1/health by convention)
api_v1_router.include_router(health_router, tags=["Health"])

# Authentication & Users
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])

# Projects
api_v1_router.include_router(projects_router, prefix="/projects", tags=["Projects"])

# Project sub-resources
api_v1_router.include_router(project_assets_router)  # prefix built into router
api_v1_router.include_router(transcripts_router)      # prefix built into router
api_v1_router.include_router(storyboard_router)       # prefix built into router
api_v1_router.include_router(languages_router)         # prefix built into router
api_v1_router.include_router(project_job_router)       # prefix built into router

# Standalone assets & jobs
api_v1_router.include_router(assets_router)            # prefix built into router
api_v1_router.include_router(job_router)               # prefix built into router

# Prompts (§9)
api_v1_router.include_router(prompts_library_router)    # /prompts/library  (MUST be before /prompts)
api_v1_router.include_router(prompts_global_router)     # /prompts
api_v1_router.include_router(prompts_playground_router)  # /playground
api_v1_router.include_router(project_prompt_router)     # /projects/{id}/prompts
api_v1_router.include_router(scene_prompt_router)       # /projects/{id}/scenes/{sid}/prompts

# Quality
api_v1_router.include_router(job_quality_router)       # prefix built into router
api_v1_router.include_router(quality_router)           # prefix built into router
api_v1_router.include_router(checkpoints_router)       # prefix built into router
api_v1_router.include_router(manifests_router, prefix="/manifests", tags=["Manifests"])

# Infrastructure
api_v1_router.include_router(nodes_router)             # prefix built into router
api_v1_router.include_router(gpus_router)              # prefix built into router
api_v1_router.include_router(dlq_router)               # prefix built into router
api_v1_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])

# Operations
api_v1_router.include_router(retention_router)         # prefix built into router
api_v1_router.include_router(quotas_router, prefix="/quotas", tags=["Quotas"])
api_v1_router.include_router(backup_router, prefix="/backup", tags=["Backup"])
api_v1_router.include_router(rollback_router)          # prefix built into router

# WebSocket
api_v1_router.include_router(ws_logs_router)
