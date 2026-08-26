"""
IVGS v5 — GPU Scheduler Microservice
========================================

Standalone FastAPI microservice for VRAM-aware GPU job scheduling per §12.
Deployed on node-01 at port 8001.

API Routes per §12.3:
- POST /schedule           — Schedule a job with VRAM bin-packing
- POST /register           — Register a GPU node
- PUT  /heartbeat          — Update worker heartbeat
- DELETE /reservations/{id} — Release a VRAM reservation
- GET  /fleet              — Fleet status overview
- POST /drain/{node_id}    — Mark node for draining
- GET  /health             — Health check
- GET  /metrics            — Prometheus metrics

Components per §12.1 Table 12-1:
- GpuScheduler: VRAM-aware bin-packing, first-fit allocation
- GpuRegistry: Node registration, heartbeat, dead detection
- AdmissionController: 4-check validation (§12.2)
- LoadBalancer: Weighted random selection
- ModelConcurrencyManager: Max 2 concurrent loads per model
- PriorityQueueManager: urgent/normal/batch with anti-starvation
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from pydantic import BaseModel, Field, field_validator

from admission_control import AdmissionController
from circuit_breaker import CircuitBreaker
from gpu_registry import GpuRegistry
from load_balancer import LoadBalancer
from metrics import SchedulerMetrics
from model_concurrency import ModelConcurrencyManager
from priority_queue import PriorityQueueManager
from scheduler import GpuScheduler

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SchedulerConfig(BaseModel):
    """Configuration for the GPU Scheduler microservice per §12."""

    redis_url: str = Field(
        default="redis://localhost:6379/3",
        description="Redis connection URL for scheduler state",
    )
    host: str = Field(default="0.0.0.0", description="Bind host")
    port: int = Field(default=8001, description="Bind port per §12")
    heartbeat_stale_threshold_s: int = Field(
        default=60,
        description="Seconds before a node is considered dead per §12.1",
    )
    reservation_ttl_s: int = Field(
        default=300,
        description="VRAM reservation TTL in seconds (5 min) per §12.2",
    )
    circuit_breaker_window_s: int = Field(
        default=600,
        description="Circuit breaker evaluation window (10 min) per §12.2",
    )
    circuit_breaker_error_threshold: float = Field(
        default=0.20,
        description="Error rate threshold for circuit breaker per §12.2",
    )
    max_concurrent_models_per_gpu: int = Field(
        default=2,
        description="Max concurrent model loads per GPU per §12.1",
    )
    priority_aging_interval_s: int = Field(
        default=1800,
        description="Anti-starvation aging interval (30 min) per §12.1",
    )
    dead_node_scan_interval_s: int = Field(
        default=15,
        description="Background scan interval for dead nodes",
    )
    reservation_cleanup_interval_s: int = Field(
        default=30,
        description="Background scan interval for expired reservations",
    )

    @classmethod
    def from_env(cls) -> SchedulerConfig:
        """Load configuration from environment variables."""
        return cls(
            redis_url=os.getenv("SCHEDULER_REDIS_URL", "redis://localhost:6379/3"),
            host=os.getenv("SCHEDULER_HOST", "0.0.0.0"),
            port=int(os.getenv("SCHEDULER_PORT", "8001")),
            heartbeat_stale_threshold_s=int(
                os.getenv("SCHEDULER_HEARTBEAT_STALE_S", "60")
            ),
            reservation_ttl_s=int(
                os.getenv("SCHEDULER_RESERVATION_TTL_S", "300")
            ),
            circuit_breaker_window_s=int(
                os.getenv("SCHEDULER_CB_WINDOW_S", "600")
            ),
            circuit_breaker_error_threshold=float(
                os.getenv("SCHEDULER_CB_ERROR_THRESHOLD", "0.20")
            ),
            max_concurrent_models_per_gpu=int(
                os.getenv("SCHEDULER_MAX_CONCURRENT_MODELS", "2")
            ),
            priority_aging_interval_s=int(
                os.getenv("SCHEDULER_AGING_INTERVAL_S", "1800")
            ),
            dead_node_scan_interval_s=int(
                os.getenv("SCHEDULER_DEAD_SCAN_S", "15")
            ),
            reservation_cleanup_interval_s=int(
                os.getenv("SCHEDULER_RES_CLEANUP_S", "30")
            ),
        )


# ---------------------------------------------------------------------------
# Request / Response Models per §12.3
# ---------------------------------------------------------------------------

class ScheduleRequest(BaseModel):
    """POST /schedule request body per §12.3."""

    job_id: str = Field(..., description="Unique job identifier")
    model_name: str = Field(..., description="Model name for scheduling")
    vram_requirement_mb: int = Field(
        ..., gt=0, description="VRAM requirement in megabytes"
    )
    estimated_duration_s: int = Field(
        ..., gt=0, description="Estimated job duration in seconds"
    )
    priority: str = Field(
        default="normal",
        description="Priority level: urgent, normal, batch per §12.1",
    )
    project_id: Optional[str] = Field(
        default=None, description="Project ID for phase gate validation"
    )
    stage: Optional[int] = Field(
        default=None, description="Pipeline stage number for phase gate"
    )

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        allowed = {"urgent", "normal", "batch"}
        if v not in allowed:
            raise ValueError(f"Priority must be one of {allowed}, got '{v}'")
        return v


class ScheduleResponse(BaseModel):
    """POST /schedule response body per §12.3."""

    node_id: str = Field(..., description="Assigned node hostname")
    gpu_index: int = Field(..., description="Assigned GPU index")
    reservation_id: str = Field(..., description="VRAM reservation identifier")
    estimated_wait_s: float = Field(
        default=0.0, description="Estimated wait time before execution"
    )


class RegisterRequest(BaseModel):
    """POST /register request body per §12.3."""

    node_hostname: str = Field(..., description="Node hostname (e.g., node-04)")
    gpu_index: int = Field(..., ge=0, description="GPU device index")
    gpu_model: str = Field(
        ..., description="GPU model name (e.g., RTX 5000 Pro)"
    )
    total_vram_mb: int = Field(
        ..., gt=0, description="Total VRAM in megabytes"
    )
    compute_capability: str = Field(
        ..., description="CUDA compute capability (e.g., 9.0)"
    )


class RegisterResponse(BaseModel):
    """POST /register response body."""

    node_id: str = Field(..., description="Registered node identifier")
    status: str = Field(default="registered", description="Registration status")


class HeartbeatRequest(BaseModel):
    """PUT /heartbeat request body per §12.3."""

    worker_id: str = Field(..., description="Worker process identifier")
    node_hostname: str = Field(..., description="Node hostname")
    gpu_index: int = Field(..., ge=0, description="GPU device index")
    current_job_id: Optional[str] = Field(
        default=None, description="Currently executing job ID"
    )
    heartbeat_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional heartbeat data (GPU util, temp, etc.)",
    )


class HeartbeatResponse(BaseModel):
    """PUT /heartbeat response body."""

    acknowledged: bool = Field(default=True, description="Heartbeat acknowledged")
    timestamp: str = Field(..., description="Server-side heartbeat timestamp")


class FleetNodeStatus(BaseModel):
    """Single node status in fleet response."""

    node_id: str
    gpu_index: int
    gpu_model: str
    total_vram_mb: int
    # WP-60 Task 2(b). THIS IS RESERVATION ACCOUNTING, NOT PHYSICAL VRAM.
    #
    # It is seeded to 0 at registration and moved only by the scheduler's own
    # acquire/release (`admission_control.py`). It has never at any point been
    # a reading off the card. The GPU Fleet page labelled it "VRAM" and showed
    # node-02 at "0.0 GB / 95.6 GB" while Node Monitor's Prometheus scrape --
    # which IS physical -- showed 86.4 GB on the same machine. Both true, one
    # of them mislabelled. The field keeps its name for wire compatibility;
    # the alias below is what a surface should render.
    used_vram_mb: int
    reserved_vram_mb: int = Field(
        default=0,
        description=(
            "Alias of used_vram_mb under its true name: VRAM RESERVED BY THE "
            "SCHEDULER, not measured on the device."
        ),
    )
    available_vram_mb: int
    # WP-60 Task 2(a): null means no heartbeat has carried a reading. Never 0.
    gpu_utilization_pct: Optional[float] = None
    gpu_temperature_c: Optional[float] = None
    gpu_power_draw_w: Optional[float] = None
    current_jobs: List[str]
    last_heartbeat: str
    is_alive: bool
    is_draining: bool
    loaded_models: List[str]
    circuit_breaker_state: str


class FleetResponse(BaseModel):
    """GET /fleet response body per §12.3."""

    total_nodes: int
    alive_nodes: int
    draining_nodes: int
    total_vram_mb: int
    used_vram_mb: int
    available_vram_mb: int
    fleet_utilization_pct: float
    queue_depth: Dict[str, int]
    nodes: List[FleetNodeStatus]


class DrainResponse(BaseModel):
    """POST /drain/{node_id} response body per §12.3."""

    node_id: str
    status: str
    active_jobs: int
    message: str


class ReservationReleaseResponse(BaseModel):
    """DELETE /reservations/{id} response body per §12.3."""

    reservation_id: str
    released: bool
    vram_freed_mb: int


# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------

class AppState:
    """Shared application state holding all scheduler components per §12.1."""

    def __init__(self) -> None:
        self.config: Optional[SchedulerConfig] = None
        self.redis: Optional[aioredis.Redis] = None
        self.registry: Optional[GpuRegistry] = None
        self.scheduler: Optional[GpuScheduler] = None
        self.admission: Optional[AdmissionController] = None
        self.load_balancer: Optional[LoadBalancer] = None
        self.concurrency: Optional[ModelConcurrencyManager] = None
        self.priority_queue: Optional[PriorityQueueManager] = None
        self.circuit_breaker: Optional[CircuitBreaker] = None
        self.metrics: Optional[SchedulerMetrics] = None
        self._background_tasks: List[asyncio.Task] = []

    async def initialize(self, config: SchedulerConfig) -> None:
        """Initialize all scheduler components."""
        self.config = config

        # --- Redis connection ---
        self.redis = aioredis.from_url(
            config.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        await self.redis.ping()
        logger.info(
            "redis_connected",
            url=config.redis_url,
        )

        # --- Prometheus metrics (§12.4) ---
        self.metrics = SchedulerMetrics()

        # --- GPU Registry (§12.1) ---
        self.registry = GpuRegistry(
            redis=self.redis,
            stale_threshold_s=config.heartbeat_stale_threshold_s,
            metrics=self.metrics,
        )

        # --- Circuit Breaker (§12.2) ---
        self.circuit_breaker = CircuitBreaker(
            redis=self.redis,
            window_s=config.circuit_breaker_window_s,
            error_threshold=config.circuit_breaker_error_threshold,
            metrics=self.metrics,
        )

        # --- Model Concurrency Manager (§12.1) ---
        self.concurrency = ModelConcurrencyManager(
            redis=self.redis,
            max_concurrent=config.max_concurrent_models_per_gpu,
            metrics=self.metrics,
        )

        # --- Priority Queue Manager (§12.1) ---
        self.priority_queue = PriorityQueueManager(
            redis=self.redis,
            aging_interval_s=config.priority_aging_interval_s,
            metrics=self.metrics,
        )

        # --- Load Balancer (§12.1) ---
        self.load_balancer = LoadBalancer(
            redis=self.redis,
            registry=self.registry,
            metrics=self.metrics,
        )

        # --- Admission Controller (§12.2) ---
        self.admission = AdmissionController(
            registry=self.registry,
            circuit_breaker=self.circuit_breaker,
            concurrency=self.concurrency,
            reservation_ttl_s=config.reservation_ttl_s,
            redis=self.redis,
            metrics=self.metrics,
        )

        # --- GPU Scheduler (§12.1) ---
        self.scheduler = GpuScheduler(
            registry=self.registry,
            admission=self.admission,
            load_balancer=self.load_balancer,
            concurrency=self.concurrency,
            priority_queue=self.priority_queue,
            circuit_breaker=self.circuit_breaker,
            redis=self.redis,
            metrics=self.metrics,
        )

        logger.info("scheduler_components_initialized")

    async def start_background_tasks(self) -> None:
        """Start background maintenance tasks."""
        config = self.config
        assert config is not None

        # Dead node scanner
        self._background_tasks.append(
            asyncio.create_task(
                self._periodic_dead_node_scan(config.dead_node_scan_interval_s)
            )
        )

        # Expired reservation cleanup
        self._background_tasks.append(
            asyncio.create_task(
                self._periodic_reservation_cleanup(
                    config.reservation_cleanup_interval_s
                )
            )
        )

        # Priority queue aging
        self._background_tasks.append(
            asyncio.create_task(
                self._periodic_priority_aging(config.priority_aging_interval_s)
            )
        )

        logger.info(
            "background_tasks_started",
            count=len(self._background_tasks),
        )

    async def shutdown(self) -> None:
        """Gracefully shut down all components."""
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        if self.redis:
            await self.redis.close()

        logger.info("scheduler_shutdown_complete")

    # --- Background task loops ---

    async def _periodic_dead_node_scan(self, interval_s: int) -> None:
        """Periodically scan for dead GPU nodes (60s stale threshold per §12.1)."""
        while True:
            try:
                await asyncio.sleep(interval_s)
                assert self.registry is not None
                dead_nodes = await self.registry.detect_dead_nodes()
                if dead_nodes:
                    logger.warning(
                        "dead_nodes_detected",
                        nodes=dead_nodes,
                        count=len(dead_nodes),
                    )
                    # Release reservations for dead nodes
                    assert self.admission is not None
                    for node_id in dead_nodes:
                        await self.admission.release_node_reservations(node_id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("dead_node_scan_error")

    async def _periodic_reservation_cleanup(self, interval_s: int) -> None:
        """Clean up expired VRAM reservations (5-min TTL per §12.2)."""
        while True:
            try:
                await asyncio.sleep(interval_s)
                assert self.admission is not None
                expired_count = await self.admission.cleanup_expired_reservations()
                if expired_count > 0:
                    logger.info(
                        "expired_reservations_cleaned",
                        count=expired_count,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("reservation_cleanup_error")

    async def _periodic_priority_aging(self, interval_s: int) -> None:
        """Apply anti-starvation aging to queued jobs per §12.1."""
        while True:
            try:
                await asyncio.sleep(interval_s)
                assert self.priority_queue is not None
                aged_count = await self.priority_queue.apply_aging()
                if aged_count > 0:
                    logger.info(
                        "priority_aging_applied",
                        aged_jobs=aged_count,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("priority_aging_error")


# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------

app_state = AppState()


# ---------------------------------------------------------------------------
# FastAPI Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing startup and shutdown of all components."""
    config = SchedulerConfig.from_env()
    logger.info(
        "scheduler_starting",
        host=config.host,
        port=config.port,
        redis_url=config.redis_url,
    )

    await app_state.initialize(config)
    await app_state.start_background_tasks()

    yield

    logger.info("scheduler_shutting_down")
    await app_state.shutdown()


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IVGS v5 GPU Scheduler",
    description="VRAM-aware GPU job scheduling microservice per §12",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware — Request ID injection
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    """Inject a unique request ID for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    structlog.contextvars.unbind_contextvars("request_id")
    return response


# ---------------------------------------------------------------------------
# Routes per §12.3
# ---------------------------------------------------------------------------

@app.post("/schedule", response_model=ScheduleResponse, status_code=200)
async def schedule_job(request: ScheduleRequest) -> ScheduleResponse:
    """
    Schedule a GPU job with VRAM bin-packing per §12.1.

    Performs full 4-check admission control per §12.2:
    1. Phase gate check
    2. VRAM availability check
    3. Concurrency limit check
    4. Circuit breaker check

    Returns the assigned node, GPU index, and reservation ID.
    """
    log = logger.bind(
        job_id=request.job_id,
        model_name=request.model_name,
        vram_mb=request.vram_requirement_mb,
        priority=request.priority,
    )
    log.info("schedule_request_received")

    start_time = time.monotonic()

    try:
        assert app_state.scheduler is not None
        assert app_state.metrics is not None

        result = await app_state.scheduler.schedule_job(
            job_id=request.job_id,
            model_name=request.model_name,
            vram_requirement_mb=request.vram_requirement_mb,
            estimated_duration_s=request.estimated_duration_s,
            priority=request.priority,
            project_id=request.project_id,
            stage=request.stage,
        )

        elapsed = time.monotonic() - start_time
        app_state.metrics.observe_wait_time(elapsed)

        log.info(
            "job_scheduled",
            node_id=result.node_id,
            gpu_index=result.gpu_index,
            reservation_id=result.reservation_id,
            elapsed_s=round(elapsed, 3),
        )

        return ScheduleResponse(
            node_id=result.node_id,
            gpu_index=result.gpu_index,
            reservation_id=result.reservation_id,
            estimated_wait_s=round(elapsed, 3),
        )

    except PhaseGateError as exc:
        log.warning("phase_gate_rejection", error=str(exc))
        app_state.metrics.increment_rejection("phase_gate")
        raise HTTPException(status_code=409, detail=str(exc))

    except NoCapacityError as exc:
        log.warning("no_capacity", error=str(exc))
        app_state.metrics.increment_rejection("no_capacity")
        raise HTTPException(status_code=503, detail=str(exc))

    except ConcurrencyLimitError as exc:
        log.warning("concurrency_limit", error=str(exc))
        app_state.metrics.increment_rejection("concurrency_limit")
        raise HTTPException(status_code=429, detail=str(exc))

    except CircuitBreakerOpenError as exc:
        log.warning("circuit_breaker_open", error=str(exc))
        app_state.metrics.increment_rejection("circuit_breaker")
        raise HTTPException(status_code=503, detail=str(exc))

    except Exception as exc:
        log.exception("schedule_error")
        app_state.metrics.increment_rejection("internal_error")
        raise HTTPException(status_code=500, detail=f"Scheduling error: {exc}")


@app.post("/register", response_model=RegisterResponse, status_code=201)
async def register_node(request: RegisterRequest) -> RegisterResponse:
    """
    Register a GPU node with the scheduler per §12.3.

    Creates or updates a node entry in the GPU registry.
    """
    log = logger.bind(
        node_hostname=request.node_hostname,
        gpu_index=request.gpu_index,
        gpu_model=request.gpu_model,
        total_vram_mb=request.total_vram_mb,
    )
    log.info("register_request_received")

    try:
        assert app_state.registry is not None
        node_id = await app_state.registry.register_node(
            node_hostname=request.node_hostname,
            gpu_index=request.gpu_index,
            gpu_model=request.gpu_model,
            total_vram_mb=request.total_vram_mb,
            compute_capability=request.compute_capability,
        )

        log.info("node_registered", node_id=node_id)

        return RegisterResponse(node_id=node_id, status="registered")

    except Exception as exc:
        log.exception("register_error")
        raise HTTPException(status_code=500, detail=f"Registration error: {exc}")


@app.put("/heartbeat", response_model=HeartbeatResponse, status_code=200)
async def update_heartbeat(request: HeartbeatRequest) -> HeartbeatResponse:
    """
    Update worker heartbeat per §12.3.

    Workers must call this within the 5-minute reservation TTL to keep
    VRAM reservations active per §12.2.
    """
    log = logger.bind(
        worker_id=request.worker_id,
        node_hostname=request.node_hostname,
        gpu_index=request.gpu_index,
    )

    try:
        assert app_state.registry is not None
        await app_state.registry.update_heartbeat(
            worker_id=request.worker_id,
            node_hostname=request.node_hostname,
            gpu_index=request.gpu_index,
            current_job_id=request.current_job_id,
            heartbeat_data=request.heartbeat_data,
        )

        ts = datetime.now(timezone.utc).isoformat()
        return HeartbeatResponse(acknowledged=True, timestamp=ts)

    except NodeNotFoundError as exc:
        log.warning("heartbeat_unknown_node", error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))

    except Exception as exc:
        log.exception("heartbeat_error")
        raise HTTPException(status_code=500, detail=f"Heartbeat error: {exc}")


@app.delete(
    "/reservations/{reservation_id}",
    response_model=ReservationReleaseResponse,
    status_code=200,
)
async def release_reservation(reservation_id: str) -> ReservationReleaseResponse:
    """
    Release a VRAM reservation on job completion per §12.3.

    Frees the reserved VRAM on the assigned GPU node and removes
    the reservation record.
    """
    log = logger.bind(reservation_id=reservation_id)
    log.info("release_reservation_request")

    try:
        assert app_state.admission is not None
        result = await app_state.admission.release_reservation(reservation_id)

        log.info(
            "reservation_released",
            vram_freed_mb=result.vram_freed_mb,
        )

        return ReservationReleaseResponse(
            reservation_id=reservation_id,
            released=True,
            vram_freed_mb=result.vram_freed_mb,
        )

    except ReservationNotFoundError as exc:
        log.warning("reservation_not_found", error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))

    except Exception as exc:
        log.exception("release_error")
        raise HTTPException(status_code=500, detail=f"Release error: {exc}")


@app.get("/fleet", response_model=FleetResponse, status_code=200)
async def get_fleet_status() -> FleetResponse:
    """
    Get fleet-wide GPU status per §12.3.

    Returns per-node breakdown including VRAM utilization,
    current jobs, circuit breaker state, and loaded models.
    """
    try:
        assert app_state.registry is not None
        assert app_state.circuit_breaker is not None
        assert app_state.concurrency is not None
        assert app_state.priority_queue is not None

        all_nodes = await app_state.registry.get_all_nodes()
        node_statuses: List[FleetNodeStatus] = []

        total_vram = 0
        used_vram = 0
        alive_count = 0
        draining_count = 0

        for node in all_nodes:
            cb_state = await app_state.circuit_breaker.get_state(node.node_id)
            loaded_models = await app_state.concurrency.get_loaded_models(
                node.node_id, node.gpu_index
            )
            current_jobs = await app_state.registry.get_node_jobs(node.node_id)

            total_vram += node.total_vram_mb
            used_vram += node.used_vram_mb

            if node.is_alive:
                alive_count += 1
            if node.is_draining:
                draining_count += 1

            node_statuses.append(
                FleetNodeStatus(
                    node_id=node.node_id,
                    gpu_index=node.gpu_index,
                    gpu_model=node.gpu_model,
                    total_vram_mb=node.total_vram_mb,
                    used_vram_mb=node.used_vram_mb,
                    reserved_vram_mb=node.used_vram_mb,
                    available_vram_mb=node.total_vram_mb - node.used_vram_mb,
                    gpu_utilization_pct=node.gpu_utilization_pct,
                    gpu_temperature_c=node.gpu_temperature_c,
                    gpu_power_draw_w=node.gpu_power_draw_w,
                    current_jobs=current_jobs,
                    last_heartbeat=node.last_heartbeat_iso,
                    is_alive=node.is_alive,
                    is_draining=node.is_draining,
                    loaded_models=loaded_models,
                    circuit_breaker_state=cb_state,
                )
            )

        queue_depth = await app_state.priority_queue.get_queue_depths()

        available_vram = total_vram - used_vram
        fleet_util = (used_vram / total_vram * 100) if total_vram > 0 else 0.0

        return FleetResponse(
            total_nodes=len(all_nodes),
            alive_nodes=alive_count,
            draining_nodes=draining_count,
            total_vram_mb=total_vram,
            used_vram_mb=used_vram,
            available_vram_mb=available_vram,
            fleet_utilization_pct=round(fleet_util, 1),
            queue_depth=queue_depth,
            nodes=node_statuses,
        )

    except Exception as exc:
        logger.exception("fleet_status_error")
        raise HTTPException(status_code=500, detail=f"Fleet status error: {exc}")


@app.post("/drain/{node_id}", response_model=DrainResponse, status_code=200)
async def drain_node(node_id: str) -> DrainResponse:
    """
    Mark a node for draining per §12.3.

    Draining nodes accept no new jobs but continue processing active ones.
    """
    log = logger.bind(node_id=node_id)
    log.info("drain_request_received")

    try:
        assert app_state.registry is not None
        active_jobs = await app_state.registry.drain_node(node_id)

        log.info("node_draining", active_jobs=active_jobs)

        return DrainResponse(
            node_id=node_id,
            status="draining",
            active_jobs=active_jobs,
            message=f"Node {node_id} marked for draining. {active_jobs} active jobs will complete.",
        )

    except NodeNotFoundError as exc:
        log.warning("drain_unknown_node", error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))

    except Exception as exc:
        log.exception("drain_error")
        raise HTTPException(status_code=500, detail=f"Drain error: {exc}")


@app.get("/health", status_code=200)
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    redis_ok = False
    try:
        if app_state.redis:
            await app_state.redis.ping()
            redis_ok = True
    except Exception:
        pass

    registry_count = 0
    if app_state.registry:
        try:
            nodes = await app_state.registry.get_all_nodes()
            registry_count = len(nodes)
        except Exception:
            pass

    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "ivgs-scheduler",
        "version": "5.0.0",
        "redis": "connected" if redis_ok else "disconnected",
        "registered_nodes": registry_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint per §12.4."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------------------------
# Custom Exceptions (imported by other modules)
# ---------------------------------------------------------------------------

class PhaseGateError(Exception):
    """Phase gate check failure per §12.2 Check #1."""


class NoCapacityError(Exception):
    """No GPU capacity available per §12.2 Check #2."""


class ConcurrencyLimitError(Exception):
    """Concurrency limit exceeded per §12.2 Check #3."""


class CircuitBreakerOpenError(Exception):
    """Circuit breaker is open per §12.2 Check #4."""


class NodeNotFoundError(Exception):
    """GPU node not found in registry."""


class ReservationNotFoundError(Exception):
    """VRAM reservation not found."""


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info",
    )
