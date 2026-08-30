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


def _first_set(*keys: str, default: str) -> str:
    """First environment variable in ``keys`` with a non-blank value.

    ``_env`` returns "" for a variable that is set-but-empty, which for a node
    identity is worse than unset: it would register the node under an empty
    hostname. This treats blank as absent.
    """
    for key in keys:
        val = os.getenv(key, "")
        if val and val.strip():
            return val.strip()
    return default


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
    # WP-37. Stage 2 emits a whole storyboard as one JSON document, so its output
    # budget is a property of THAT STAGE, not of the fleet-wide LLM default -
    # which is why it gets its own knob rather than inheriting max_tokens above.
    #
    # It has to be its own variable, not a bigger default: node-02's .env.node02
    # pins IVGS_VLLM_MAX_TOKENS=2048, so raising the shared default would have
    # changed nothing on the node where stage 2 actually runs. That 2048 is what
    # truncated job e408515a four times (~8 KB of JSON each attempt).
    #
    # 8192 was sized from measurement, not habit:
    #   input  ~2,000 tokens  (stage2 templates 5,066 chars ~1,266; the refined
    #                          transcript 2,241 chars ~560; project context ~100)
    #   output  8,192 tokens
    #   total  ~10,200 against node-02's 32,768 serving context
    #          (vllm --max-model-len 32768) - roughly 22K of headroom, enough for
    #          a transcript several times longer than this one.
    # 2048 demonstrably could not hold a 5-minute storyboard; 8192 is 4x that
    # with the context to spare.
    #
    # ⛔ WP-IVGS-12g RAISED THE FLOOR TO 12,288, AND THE INPUT FIGURE ABOVE IS
    # NOW STALE BY A FACTOR OF SEVEN. Both halves are measured, on the pinned
    # engine, against the operator's own 3,008-byte script.
    #
    # WHAT TRUNCATED. The first acceptance generation under design-contract-6
    # hit this ceiling exactly — `finish_reason=length`, 8,192 completion
    # tokens, 28,977 characters of JSON and no parseable document. One
    # generation in three. ⚠ AND IT IS NOT RC-Q12's WHITESPACE CORRIDOR: the
    # emission was 10.6% whitespace, the ordinary ratio for indented JSON, and
    # the probes for both new array shapes were run against that corridor before
    # the contract shipped and did not enter it. This was a plain overrun.
    #
    # WHY THE EMISSION GREW, and it is contract-6's own doing:
    #   the evidence layer went from ~2,040 characters (contract-5's three
    #   assessments) to ~3,950-4,400 (three assessments AND three practice
    #   scenes, each a full scene object) — it roughly DOUBLED, by construction;
    #   and with `practice`/`assess` removed from `scenes[]` the expository arc
    #   itself lengthened, 31 and 37 scenes where contract-5 emitted 10 to 14.
    #
    # ⚠ THE INPUT SIDE IS THE PART NOBODY WAS WATCHING. Measured prompt_tokens
    # on every generation above: **14,861** — not the ~2,000 this comment has
    # claimed since WP-37. The stage-2 SYSTEM prompt alone has gone 7,788 ->
    # 19,217 characters across v1..v7 and the input estimate here was never
    # revisited. So the real arithmetic against node-02's 32,768 is:
    #
    #     input  14,861   output 12,288   total 27,149   headroom 5,619
    #
    # ⛔ THAT HEADROOM, NOT THIS KNOB, IS THE BINDING CONSTRAINT NOW, and it is
    # why the floor is 12,288 and NOT the 16,384 cap. Maxing the floor would fit
    # today (14,861 + 16,384 = 31,245, 1,523 spare), leave `storyboard_max_
    # tokens_for` nothing left to widen for a genuinely large storyboard, and
    # put the next longer script straight into the context wall instead of into
    # a budget that can still grow. 12,288 covers the largest emission measured
    # (7,693 completion tokens) with 60% to spare and keeps the scaling path.
    storyboard_max_tokens: int = _env(
        "IVGS_VLLM_STORYBOARD_MAX_TOKENS", 12288, int
    )
    # WP-58 Task 5. The FLOOR above is a fixed number, and a fixed number is the
    # same latent defect one course-size larger: WP-37's truncation happened
    # because 2048 was adequate until a storyboard was not. These two scale the
    # budget with what is actually being asked for.
    #
    # 400 tokens/scene is ~2.6x the MEASURED density. Real data, read from the
    # live database rather than estimated: the largest successful storyboard
    # payload is 10,831 characters for 18 scenes (job bd99fe37), i.e. ~600
    # chars ~ 150 tokens per scene.
    #
    # The cap exists because node-02 serves --max-model-len 32768 and the budget
    # is OUTPUT only. Measured input is ~2,000 tokens; at 5x transcript length
    # that is ~10,000, so 10,000 + 16,384 = 26,384 still fits. Asking for more
    # output than the context can hold is refused by the server, which would
    # turn a large course into a hard failure instead of a long one.
    storyboard_tokens_per_scene: int = _env(
        "IVGS_VLLM_STORYBOARD_TOKENS_PER_SCENE", 400, int
    )
    storyboard_max_tokens_cap: int = _env(
        "IVGS_VLLM_STORYBOARD_MAX_TOKENS_CAP", 16384, int
    )
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

    # WP-45 Task 4(a) / WP-40 D-2.
    #
    # This is the name the GPU scheduler keys the node by: its registry id is
    # `{node_hostname}:gpu{index}`. The default is the CONTAINER's hostname - a
    # 12-character hex id that changes on every recreate - so the registry filled
    # with entries like `61c7c02b3a8a:gpu0`, one per container the node has ever
    # run, and nothing on the fleet could say which physical node any of them
    # was. Measured 2026-08-25: 21 registered "nodes", 3 alive, on a fleet of
    # three GPUs.
    #
    # IVGS_NODE_NAME is the stable per-node name (node-02 ... node-06) and is
    # read FIRST. IVGS_NODE_HOSTNAME is kept as a fallback so a node that has
    # not been given the new variable behaves exactly as it did before rather
    # than changing identity on upgrade.
    node_hostname: str = _first_set(
        "IVGS_NODE_NAME", "IVGS_NODE_HOSTNAME",
        default=os.getenv("HOSTNAME", "worker-unknown"),
    )
    node_id: str = _first_set(
        "IVGS_NODE_ID", "IVGS_NODE_NAME",
        default=os.getenv("HOSTNAME", "worker-unknown"),
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

    def storyboard_max_tokens_for(self, scene_count: Optional[int] = None) -> int:
        """Output budget for one storyboard, scaled to the scene count.

        WP-58 Task 5. ``scene_count`` is ``target_scene_count`` from the stage
        input and is frequently ``None`` - the operator does not have to state
        it. When it is None the fixed floor applies, which is the pre-WP-58
        behaviour and is already comfortable for the largest storyboard this
        system has produced (18 scenes, ~2,700 output tokens measured).

        Never returns less than ``storyboard_max_tokens``: this may only widen
        the budget, never narrow it. A scene count that is wrong-low must not be
        able to reintroduce the truncation it exists to prevent.
        """
        floor = self.vllm.storyboard_max_tokens
        if not scene_count or scene_count < 1:
            return floor
        scaled = 2048 + (scene_count * self.vllm.storyboard_tokens_per_scene)
        return max(floor, min(scaled, self.vllm.storyboard_max_tokens_cap))

    #: Seconds of headroom between the LLM client giving up and Celery's soft
    #: limit firing. The client must lose the race: a VLLMTimeoutError is a
    #: named, retryable, logged failure, while SoftTimeLimitExceeded kills the
    #: task mid-write and leaves the job row stranded `running` (RC-P16, which
    #: then blocks both /resume and WP-59 deletion). 30s covers the checkpoint
    #: write, the scene POSTs and the completion dispatch that follow the call.
    STORYBOARD_CLIENT_TIMEOUT_HEADROOM_S = 30

    def _storyboard_client_timeout(self) -> float:
        """The stage-2 LLM client timeout, DERIVED from the declared policy.

        Falls back to the shared knob only if the policy module cannot be read,
        and says so rather than silently reverting to 120s -- which is the
        value that produced `vLLM timeout: All vLLM endpoints timed out` four
        times in a row on the first v8 run.
        """
        try:
            # Imported lazily: `config` is loaded by modules that must not gain
            # a hard dependency on the Temporal shadow package.
            from temporal_pipeline.policies import ALL_POLICIES

            soft = next(
                p.celery_soft_time_limit_s for p in ALL_POLICIES
                if p.celery_task_name
                == "tasks.stage2_storyboard.generate_storyboard_task"
            )
        except Exception:                                        # noqa: BLE001
            import logging

            logging.getLogger("ivgs.config").warning(
                "storyboard_client_timeout_policy_unreadable: falling back to "
                "the shared vllm_timeout of %ss. A v8 Design Contract measured "
                "169.3s on 2026-08-29, so this WILL time out.",
                self.timeouts.vllm_timeout,
            )
            return float(self.timeouts.vllm_timeout)
        return float(max(soft - self.STORYBOARD_CLIENT_TIMEOUT_HEADROOM_S,
                         self.timeouts.vllm_timeout))

    def get_vllm_config_for_stage(self, stage: str) -> Dict[str, Any]:
        """Get vLLM configuration appropriate for a pipeline stage."""
        if stage == "storyboard_generation":
            # WP-37: split out of the shared branch below so the storyboard's
            # output budget is not capped by the generic IVGS_VLLM_MAX_TOKENS.
            # Same endpoint and model as transcript_refinement; only the output
            # budget differs. Stage 1 is left on the shared knob deliberately -
            # it completed inside 2048 on this material.
            return _AttrDict({
                "base_url": self.vllm.primary_base_url,
                "model": self.vllm.primary_model,
                # ⛔ WP-IVGS-12. THE SHARED 120s KNOB IS SHORTER THAN THIS
                # STAGE'S OWN DECLARED POLICY, AND IT KILLED THE FIRST
                # ACCEPTANCE RUN.
                #
                # `self.timeouts.vllm_timeout` is 120s for every stage. Stage 2
                # has declared soft 270 / hard 300 since WP-41, and WP-IVGS-10's
                # addendum made the CELERY limits actually apply -- but the
                # CLIENT timeout inside them was never reconciled with either.
                # It did not matter while a v7 storyboard took 55s. It matters
                # now: a v8 Design Contract is emitted under grammar-constrained
                # decoding, and MEASURED 2026-08-29 on the operator's own script
                # against the pinned engine it takes **169.3s** (11,914 prompt
                # tokens, 3,238 completion tokens, finish_reason=stop, 9 scenes).
                # Comfortably inside the policy. Nowhere near inside 120s.
                #
                # This is RC-P17's shape one layer down, so it is fixed the same
                # way: DERIVED FROM THE DECLARED POLICY, not transcribed from it.
                # A transcription is "an accurate mirror with no authority" and
                # goes stale the first time the policy moves.
                "timeout": self._storyboard_client_timeout(),
                "max_tokens": self.vllm.storyboard_max_tokens,
                "temperature": self.vllm.temperature,
                "top_p": self.vllm.top_p,
                "fallback_base_url": self.vllm.secondary_base_url,
                "fallback_model": self.vllm.secondary_model,
            })
        if stage in ("transcript_refinement",):
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
