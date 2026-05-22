"""
Configuration management using Pydantic v2 BaseSettings.

All environment variables from Appendix A.2 of the v5 specification.
Loaded from .env file or environment at import time.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Database (PostgreSQL 17 + TimescaleDB) ---
    DATABASE_URL: str = "postgresql+asyncpg://ivgs:ivgs@localhost:5432/ivgs"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30

    # --- Redis 7 ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50

    # --- SeaweedFS ---
    SEAWEEDFS_MASTER_URL: str = "http://localhost:9333"
    SEAWEEDFS_FILER_URL: str = "http://localhost:8888"
    SEAWEEDFS_MOUNT_PATH: str = "/ivgs"

    # --- GPU Scheduler ---
    GPU_SCHEDULER_URL: str = "http://localhost:8001"

    # --- vLLM Endpoints ---
    VLLM_PRIMARY_URL: str = "http://10.10.0.2:8000/v1"
    VLLM_SECONDARY_URL: str = "http://10.10.0.3:8000/v1"
    VLLM_MIDSIZE_URL: str = "http://10.10.0.4:8000/v1"
    OLLAMA_URL: str = "http://10.10.0.5:11434"

    # --- ComfyUI Endpoints ---
    COMFYUI_PRIMARY_URL: str = "http://10.10.0.4:8188"
    COMFYUI_FALLBACK_URL: str = "http://10.10.0.5:8188"

    # --- TTS / Talking Head ---
    COQUI_TTS_URL: str = "http://10.10.0.4:5002"
    KOKORO_TTS_URL: str = "http://10.10.0.4:5003"
    LATENTSYNC_URL: str = "http://10.10.0.4:7860"
    SADTALKER_URL: str = "http://10.10.0.4:7861"

    # --- Composition ---
    REMOTION_URL: str = "http://10.10.0.6:3002"

    # --- Authentication (§16.1) ---
    JWT_SECRET_KEY: str = "CHANGE_ME_STRONG_RANDOM_SECRET_64_CHARS_MINIMUM"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Backup (§14.1) ---
    BACKUP_NAS_PATH: str = "/mnt/backup/ivgs"
    BACKUP_GPG_KEY_ID: str = ""

    # --- NFS Shared Volume ---
    SHARED_VOLUME_PATH: str = "/mnt/ivgs-shared"

    # --- Logging (§13.4) ---
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    NODE_HOSTNAME: str = "node-01"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }

    @property
    def sync_database_url(self) -> str:
        """Return synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")


settings = Settings()
