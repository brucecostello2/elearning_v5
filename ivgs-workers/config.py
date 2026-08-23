"""
IVGS v5 — Worker Configuration
================================

All worker configuration is loaded from environment variables with sensible
defaults matching the functional specification.

Environment variable prefix: IVGS_

Sections:
- Celery broker/backend
- vLLM connection settings (§7.1.1)
- GPU scheduling API (§12)
- Pipeline API (checkpoint, DLQ)
- Timeouts per model (Table 6-5)
- Retry policies per stage (Table 6-4)
- Worker resource limits
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _env(key: str, default: Any = None, cast: type = str) -> Any:
    """Read an environment variable with type casting."""
    val = os.getenv(key, default)
    if val is None:
        return None
    if cast == bool:
        return str(val).lower() in ("1", "true", "yes", "on")
    return cast(val)


def _env_required(key: str, cast: type = str) -> Any:
    """Read a required environment variable; raise on missing."""
    val = os.getenv(key)
    if val is None:
        raise EnvironmentError(f"Required environment variable {key} is not set")
    if cast == bool:
        return str(val).lower() in ("1", "true", "yes", "on")
    return cast(val)


class _AttrDict(dict):
    """dict supporting both item access (d["x"]) and attribute access (d.x).

    Lets config helpers return one object usable both by call sites that index
    (vllm_config["model"]) and those that use attributes (cfg.model).
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


@dataclass(frozen=True)
class VLLMConfig:
    """
    vLLM server connection configuration per §7.1.1.
    vLLM serves OpenAI-compatible API at http://node-0X:8000/v1.
    Base URLs below are host:port only (no /v1); VLLMClient appends /v1/chat/completions.
    Tensor parallelism for 70B+ models uses NCCL over 10GbE VLAN.
    """

    primary_base_url: str = _env_required("VLLM_PRIMARY_URL")
    secondary_base_url: str = _env_required("VLLM_SECONDARY_URL")
    midsize_base_url: str = _env_required("VLLM_MIDSIZE_URL")

    primary_model: str = _env(
        "IVGS_VLLM_PRIMARY_MODEL", "meta-llama/Llama-3.3-70B-Instruct"
    )
    secondary_model: str = _env(
        "IVGS_VLLM_SECONDARY_MODEL", "Qwen/Qwen2.5-72B-Instruct"
    )
    midsize_model: str = _env(
        "IVGS_VLLM_MIDSIZE_MODEL", "mistralai/Mistral-Small-24B-Instruct-2501"
    )

    timeout_seconds: int = _env("IVGS_VLLM_TIMEOUT", 120, int)
    connect_timeout_seconds: int = _env("IVGS_VLLM_CONNECT_TIMEOUT", 10, int)
    max_retries: int = _env("IVGS_VLLM_MAX_RETRIES", 2, int)
    max_tokens: int = _env("IVGS_VLLM_MAX_TOKENS", 4096, int)
    temperature: float = _env("IVGS_VLLM_TEMPERATURE", 0.3, float)
    top_p: float = _env("IVGS_VLLM_TOP_P", 0.9, float)

    max_connections: int = _env("IVGS_VLLM_MAX_CONNECTIONS", 10, int)
    max_keepalive: int = _env("IVGS_VLLM_MAX_KEEPALIVE", 5, int)

    health_check_interval: int = _env(
        "IVGS_VLLM_HEALTH_CHECK_INTERVAL", 30, int
    )

    api_key: Optional[str] = _env("IVGS_VLLM_API_KEY", None)


@dataclass(frozen=True)
class GpuSchedulerConfig:
    """GPU scheduler API connection settings per §12."""

    base_url: str = _env(
        "IVGS_GPU_SCHEDULER_URL", "http://node-01:8001"
    )
    timeout_seconds: int = _env("IVGS_GPU_SCHEDULER_TIMEOUT", 15, int)
    reservation_ttl_seconds: int = _env(
        "IVGS_GPU_RESERVATION_TTL", 300, int
    )
    heartbeat_interval_seconds: int = _env(
        "IVGS_GPU_HEARTBEAT_INTERVAL", 10, int
    )


@dataclass(frozen=True)
class PipelineAPIConfig:
    """
    IVGS API connection settings for pipeline services.
    Workers call back into the API for checkpoint, DLQ, job status,
    prompt resolution, and transcript/storyboard CRUD.
    """

    base_url: str = _env("API_BASE_URL", "http://node-01:8001")
    api_prefix: str = _env("IVGS_API_PREFIX", "/api/v1")
    timeout_seconds: int = _env("IVGS_API_TIMEOUT", 30, int)
    service_token: str = _env("IVGS_SERVICE_TOKEN", "dev-service-token")

    @property
    def full_base_url(self) -> str:
        return f"{self.base_url}{self.api_prefix}"


@dataclass(frozen=True)
class TimeoutConfig:
    """Per-model timeout thresholds per §6.5 Table 6-5."""

    vllm_timeout: int = _env("IVGS_TIMEOUT_VLLM", 120, int)
    vllm_warnings: List[int] = field(default_factory=lambda: [60, 90, 120])

    comfyui_timeout: int = _env("IVGS_TIMEOUT_COMFYUI", 300, int)
    comfyui_warnings: List[int] = field(default_factory=lambda: [150, 225, 300])

    cogvideox_timeout: int = _env("IVGS_TIMEOUT_COGVIDEOX", 1800, int)
    cogvideox_warnings: List[int] = field(
        default_factory=lambda: [900, 1350, 1800]
    )

    wan21_timeout: int = _env("IVGS_TIMEOUT_WAN21", 30, int)
    wan21_warnings: List[int] = field(default_factory=lambda: [15, 22, 30])

    tts_timeout: int = _env("IVGS_TIMEOUT_TTS", 120, int)
    tts_warnings: List[int] = field(default_factory=lambda: [60, 90, 120])

    latentsync_timeout: int = _env("IVGS_TIMEOUT_LATENTSYNC", 600, int)
    latentsync_warnings: List[int] = field(
        default_factory=lambda: [300, 450, 600]
    )

    ffmpeg_timeout: int = _env("IVGS_TIMEOUT_FFMPEG", 900, int)
    ffmpeg_warnings: List[int] = field(default_factory=lambda: [450, 675, 900])


@dataclass(frozen=True)
class RetryConfig:
    """Retry policies per stage type per §6.4 Table 6-4."""

    llm_max_retries: int = _env("IVGS_RETRY_LLM_MAX", 4, int)
    llm_backoff_sequence: List[int] = field(
        default_factory=lambda: [5, 15, 45, 135]
    )

    image_max_retries: int = _env("IVGS_RETRY_IMAGE_MAX", 3, int)
    image_backoff_sequence: List[int] = field(
        default_factory=lambda: [10, 30, 90]
    )

    video_max_retries: int = _env("IVGS_RETRY_VIDEO_MAX", 2, int)
    video_backoff_sequence: List[int] = field(
        default_factory=lambda: [30, 90]
    )

    tts_max_retries: int = _env("IVGS_RETRY_TTS_MAX", 3, int)
    tts_backoff_sequence: List[int] = field(
        default_factory=lambda: [10, 30, 90]
    )

    talking_head_max_retries: int = _env("IVGS_RETRY_TALKHEAD_MAX", 2, int)
    talking_head_backoff_sequence: List[int] = field(
        default_factory=lambda: [30, 90]
    )

    composition_max_retries: int = _env("IVGS_RETRY_COMPOSITION_MAX", 2, int)
    composition_backoff_sequence: List[int] = field(
        default_factory=lambda: [30, 90]
    )


@dataclass(frozen=True)
class WorkerConfig:
    """Master worker configuration aggregating all sub-configs."""

    celery_broker_url: str = _env(
        "IVGS_CELERY_BROKER_URL", "redis://node-01:6379/0"
    )
    celery_result_backend: str = _env(
        "IVGS_CELERY_RESULT_BACKEND",
        "db+postgresql+psycopg2://ivgs:ivgs@node-01:5432/ivgs_results",
    )
    # INVARIANT (ledger P0.1, WP-05): this MUST exceed the longest hard `time_limit`
    # of any registered task, with margin. With task_acks_late = True
    # (celery_app.py:288) the ack lands only after the task body returns, and kombu's
    # Redis transport restores an unacked message to the queue once this many seconds
    # elapse. At the old 3600 against the 3900 s hard limit on talking_head
    # (talking_head_task.py:399) and video_generation (video_generation_task.py:445),
    # a still-running render had its message put back at t=3600 and re-claimed - on
    # gpu_video, which tracked config binds to BOTH node-02 and node-03, by a second
    # node concurrently.
    #
    # 7200 is the ledger's recommendation: 3900 + 3300 s of margin. The invariant is
    # not left to a comment - assert_visibility_timeout_covers_time_limits() in
    # celery_app.py aborts worker startup if it is ever violated again.
    broker_visibility_timeout: int = _env(
        "IVGS_BROKER_VISIBILITY_TIMEOUT", 7200, int
    )
    broker_use_ssl: bool = _env("IVGS_BROKER_USE_SSL", False, bool)
    broker_ssl_ca_certs: Optional[str] = _env("IVGS_BROKER_SSL_CA_CERTS", None)
    result_expires_seconds: int = _env("IVGS_RESULT_EXPIRES", 86400, int)

    worker_concurrency: int = _env("IVGS_WORKER_CONCURRENCY", 1, int)
    worker_max_tasks_per_child: int = _env(
        "IVGS_WORKER_MAX_TASKS_PER_CHILD", 100, int
    )
    worker_max_memory_per_child: int = _env(
        "IVGS_WORKER_MAX_MEMORY_MB", 8192, int
    )
    task_hard_time_limit: int = _env("IVGS_TASK_HARD_TIME_LIMIT", 3600, int)
    task_soft_time_limit: int = _env("IVGS_TASK_SOFT_TIME_LIMIT", 3300, int)

    node_hostname: str = _env(
        "IVGS_NODE_HOSTNAME", os.getenv("HOSTNAME", "worker-unknown")
    )
    node_id: str = _env(
        "IVGS_NODE_ID", os.getenv("HOSTNAME", "worker-unknown")
    )
    worker_id: str = _env(
        "IVGS_WORKER_ID",
        f"{os.getenv('HOSTNAME', 'worker-unknown')}-{os.getpid()}",
    )

    gpu_indices: List[int] = field(
        default_factory=lambda: [
            int(x)
            for x in _env("IVGS_GPU_INDICES", "0").split(",")
            if x.strip()
        ]
    )

    log_level: str = _env("IVGS_LOG_LEVEL", "INFO")
    log_format: str = _env("IVGS_LOG_FORMAT", "json")

    vllm: VLLMConfig = field(default_factory=VLLMConfig)
    gpu_scheduler: GpuSchedulerConfig = field(default_factory=GpuSchedulerConfig)
    pipeline_api: PipelineAPIConfig = field(default_factory=PipelineAPIConfig)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    retries: RetryConfig = field(default_factory=RetryConfig)

    prompt_template_dir: str = _env(
        "IVGS_PROMPT_TEMPLATE_DIR",
        os.path.join(os.path.dirname(__file__), "prompts"),
    )

    enable_gpu_reservation: bool = _env(
        "IVGS_ENABLE_GPU_RESERVATION", True, bool
    )
    enable_node_registration: bool = _env(
        "IVGS_ENABLE_NODE_REGISTRATION", True, bool
    )
    enable_availability_poller: bool = _env(
        "IVGS_ENABLE_AVAILABILITY_POLLER", True, bool
    )
    enable_idempotency_check: bool = _env(
        "IVGS_ENABLE_IDEMPOTENCY_CHECK", True, bool
    )
    enable_checkpoint_saving: bool = _env(
        "IVGS_ENABLE_CHECKPOINT_SAVING", True, bool
    )

    # GPU media-service URLs (H.0 WI-2). Env-overridable; defaults follow the
    # Build Plan wire contract + task call-site defaults + the fleet node map.
    # cogvideox port 8200 is settled (Stage-1 build); latentsync/sadtalker
    # ports (8300/8301 here vs Build Plan 7860/7861) are a tracked H.1/Stage-3
    # item, changeable via env without a code edit.
    cogvideox_url: str = _env("IVGS_COGVIDEOX_URL", "http://cogvideox-server:8200")
    cogvideox_fallback_url: str = _env("IVGS_COGVIDEOX_FALLBACK_URL", "http://node-03:8200")
    wan21_url: str = _env("IVGS_WAN21_URL", "http://node-02:8210")
    wan21_fallback_url: str = _env("IVGS_WAN21_FALLBACK_URL", "http://node-03:8210")
    latentsync_url: str = _env("IVGS_LATENTSYNC_URL", "http://node-04:8300")
    sadtalker_url: str = _env("IVGS_SADTALKER_URL", "http://node-04:8301")

    @property
    def redis_url(self) -> str:
        """Redis URL for app-level keys; aliases the Celery broker (same Redis)."""
        return self.celery_broker_url

    def get_vllm_config_for_stage(self, stage: str) -> Dict[str, Any]:
        """Get vLLM configuration appropriate for a pipeline stage."""
        if stage in ("transcript_refinement", "storyboard_generation"):
            return _AttrDict({
                "base_url": self.vllm.primary_base_url,
                "model": self.vllm.primary_model,
                "timeout": self.timeouts.vllm_timeout,
                "max_tokens": self.vllm.max_tokens,
                "temperature": self.vllm.temperature,
                "top_p": self.vllm.top_p,
                "fallback_base_url": self.vllm.secondary_base_url,
                "fallback_model": self.vllm.secondary_model,
            })
        elif stage in (
            "image_generation", "video_generation", "animation_generation"
        ):
            return _AttrDict({
                "base_url": self.vllm.midsize_base_url,
                "model": self.vllm.midsize_model,
                "timeout": self.timeouts.vllm_timeout,
                "max_tokens": 4096,
                "temperature": 0.7,
                "top_p": 0.95,
                "fallback_base_url": self.vllm.primary_base_url,
                "fallback_model": self.vllm.primary_model,
            })
        else:
            return _AttrDict({
                "base_url": self.vllm.primary_base_url,
                "model": self.vllm.primary_model,
                "timeout": self.timeouts.vllm_timeout,
                "max_tokens": self.vllm.max_tokens,
                "temperature": self.vllm.temperature,
                "top_p": self.vllm.top_p,
            })

    def get_model_config(self, name: str) -> "_AttrDict":
        """Resolve a GPU model-service config by logical name (H.0 WI-2).

        Returns an _AttrDict with at least 'api_url' and 'fallback_url'
        (fallback_url is None for single-instance services). URLs come from the
        env-overridable WorkerConfig fields above, never hard-coded literals.
        """
        registry = {
            "cogvideox_5b": (self.cogvideox_url, self.cogvideox_fallback_url),
            "wan21": (self.wan21_url, self.wan21_fallback_url),
            "latentsync": (self.latentsync_url, None),
            "sadtalker": (self.sadtalker_url, None),
        }
        if name not in registry:
            raise KeyError(f"Unknown model config '{name}'")
        primary, fallback = registry[name]
        return _AttrDict({"api_url": primary, "fallback_url": fallback})

    def get_retry_config_for_stage(self, stage: str) -> Dict[str, Any]:
        """Get retry configuration for a specific pipeline stage."""
        stage_map = {
            "transcript_refinement": {
                "max_retries": self.retries.llm_max_retries,
                "backoff_sequence": self.retries.llm_backoff_sequence,
            },
            "storyboard_generation": {
                "max_retries": self.retries.llm_max_retries,
                "backoff_sequence": self.retries.llm_backoff_sequence,
            },
            "image_generation": {
                "max_retries": self.retries.image_max_retries,
                "backoff_sequence": self.retries.image_backoff_sequence,
            },
            "video_generation": {
                "max_retries": self.retries.video_max_retries,
                "backoff_sequence": self.retries.video_backoff_sequence,
            },
            "tts_audio": {
                "max_retries": self.retries.tts_max_retries,
                "backoff_sequence": self.retries.tts_backoff_sequence,
            },
            "talking_head_render": {
                "max_retries": self.retries.talking_head_max_retries,
                "backoff_sequence": self.retries.talking_head_backoff_sequence,
            },
            "composition": {
                "max_retries": self.retries.composition_max_retries,
                "backoff_sequence": self.retries.composition_backoff_sequence,
            },
        }
        return stage_map.get(
            stage, {"max_retries": 3, "backoff_sequence": [10, 30, 90]}
        )
