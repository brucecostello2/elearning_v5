"""GPU Scheduler service configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ivgs:ivgs@node-01:5432/ivgs"
    redis_url: str = "redis://node-01:6379/1"
    log_level: str = "info"
    port: int = 8001
    # VRAM headroom: leave this % free on each GPU before scheduling
    vram_headroom_pct: float = 0.10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
