"""
IVGS v5 — ORM Model Registry

Importing this package ensures every model class is registered with
SQLAlchemy's Base.metadata, which is required for:
  - Alembic autogenerate
  - Base.metadata.create_all() in tests
  - Relationship back-population

All 23 models correspond to tables created by migrations 0001–0014.
"""
# Core domain models (0001_initial_core)
from app.models.user import User  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.asset import Asset  # noqa: F401
from app.models.transcript import Transcript  # noqa: F401
from app.models.storyboard_scene import StoryboardScene  # noqa: F401
from app.models.prompt import Prompt  # noqa: F401
from app.models.prompt_tag import PromptTag, prompt_tag_associations  # noqa: F401
from app.models.render_job import RenderJob  # noqa: F401
from app.models.language_variant import LanguageVariant  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401

# Pipeline & orchestration (0002–0005)
from app.models.checkpoint import PipelineCheckpoint  # noqa: F401
from app.models.gpu_node import GpuNode, GpuReservation  # noqa: F401
from app.models.task_retry import TaskRetry  # noqa: F401
from app.models.worker_heartbeat import WorkerHeartbeat  # noqa: F401

# Quality & DLQ (0006–0008)
from app.models.dead_letter_queue import DeadLetterMessage  # noqa: F401
from app.models.composition_manifest import CompositionManifest  # noqa: F401
from app.models.quality_score import AssetQualityScore  # noqa: F401

# Rendering (0009)
from app.models.render_segment import RenderSegment  # noqa: F401

# Monitoring & storage (0010–0012)
from app.models.gpu_metrics_history import GpuMetricsHistory  # noqa: F401
from app.models.retention_policy import RetentionPolicy  # noqa: F401
from app.models.storage_quota import StorageQuota  # noqa: F401

# Backup & fallback (0013–0014)
from app.models.backup_record import BackupRecord  # noqa: F401
from app.models.fallback_policy import FallbackPolicy  # noqa: F401

__all__ = [
    # Core domain
    "User",
    "Project",
    "Asset",
    "Transcript",
    "StoryboardScene",
    "Prompt",
    "PromptTag",
    "prompt_tag_associations",
    "RenderJob",
    "LanguageVariant",
    "AuditLog",
    # Pipeline & orchestration
    "PipelineCheckpoint",
    "GpuNode",
    "GpuReservation",
    "TaskRetry",
    "WorkerHeartbeat",
    # Quality & DLQ
    "DeadLetterMessage",
    "CompositionManifest",
    "AssetQualityScore",
    # Rendering
    "RenderSegment",
    # Monitoring & storage
    "GpuMetricsHistory",
    "RetentionPolicy",
    "StorageQuota",
    # Backup & fallback
    "BackupRecord",
    "FallbackPolicy",
]
