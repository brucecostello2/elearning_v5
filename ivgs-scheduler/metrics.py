"""
IVGS v5 — Scheduler Prometheus Metrics
==========================================

Prometheus metric definitions per §12.4 Table 12-3.

Metrics exposed:
- ivgs_scheduler_queue_depth           — Gauge: queue depth per GPU/priority
- ivgs_scheduler_wait_time_seconds     — Histogram: time from submission to decision
- ivgs_scheduler_rejection_total       — Counter: total rejections by reason
- ivgs_scheduler_circuit_breaker_state — Gauge: CB state per node (0=closed, 1=open)
- ivgs_gpu_vram_used_mb                — Gauge: reserved VRAM per GPU node
- ivgs_gpu_utilization_pct             — Gauge: GPU utilization % per node

All metrics are scraped by Prometheus at 15-second intervals per §13.1.
Endpoint: node-01:8001/metrics
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

import structlog

logger = structlog.get_logger(__name__)


class SchedulerMetrics:
    """
    Prometheus metrics for the GPU scheduler per §12.4 Table 12-3.

    All metrics follow the naming convention ivgs_scheduler_* or ivgs_gpu_*
    as specified in the functional specification.
    """

    def __init__(self) -> None:
        # --- ivgs_scheduler_queue_depth per §12.4 ---
        self.queue_depth = Gauge(
            "ivgs_scheduler_queue_depth",
            "Queue depth per GPU node and priority level",
            ["node_id", "priority"],
        )

        # --- ivgs_scheduler_wait_time_seconds per §12.4 ---
        self.wait_time = Histogram(
            "ivgs_scheduler_wait_time_seconds",
            "Time from job submission to scheduling decision",
            buckets=[
                0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
                1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
            ],
        )

        # --- ivgs_scheduler_rejection_total per §12.4 ---
        self.rejection_total = Counter(
            "ivgs_scheduler_rejection_total",
            "Total admission control rejections by reason",
            ["reason"],
        )

        # --- ivgs_scheduler_circuit_breaker_state per §12.4 ---
        self.circuit_breaker_state = Gauge(
            "ivgs_scheduler_circuit_breaker_state",
            "Circuit breaker state per GPU node (0=closed, 1=open)",
            ["node_id"],
        )

        # --- ivgs_gpu_vram_used_mb per §12.4 ---
        self.vram_used = Gauge(
            "ivgs_gpu_vram_used_mb",
            "Reserved VRAM per GPU node in megabytes",
            ["node_id", "gpu_index"],
        )

        # --- ivgs_gpu_utilization_pct per §12.4 ---
        self.gpu_utilization = Gauge(
            "ivgs_gpu_utilization_pct",
            "GPU utilization percentage per node (from heartbeat data)",
            ["node_id", "gpu_index"],
        )

        # --- Additional operational metrics ---
        self.reservations_active = Gauge(
            "ivgs_scheduler_reservations_active",
            "Number of active VRAM reservations",
        )

        self.scheduling_decisions_total = Counter(
            "ivgs_scheduler_decisions_total",
            "Total scheduling decisions made",
            ["result"],
        )

        self.nodes_registered = Gauge(
            "ivgs_scheduler_nodes_registered",
            "Number of registered GPU nodes",
        )

        self.nodes_alive = Gauge(
            "ivgs_scheduler_nodes_alive",
            "Number of alive GPU nodes",
        )

        self.heartbeats_total = Counter(
            "ivgs_scheduler_heartbeats_total",
            "Total heartbeat updates received",
        )

        self.model_evictions_total = Counter(
            "ivgs_scheduler_model_evictions_total",
            "Total LRU model evictions",
            ["node_id"],
        )

        self.priority_aging_total = Counter(
            "ivgs_scheduler_priority_aging_total",
            "Total priority aging bumps applied",
        )

        logger.info("prometheus_metrics_initialized")

    def set_queue_depth(
        self, node_id: str, priority: str, depth: int
    ) -> None:
        """Update queue depth gauge for a node and priority level."""
        self.queue_depth.labels(node_id=node_id, priority=priority).set(depth)

    def observe_wait_time(self, seconds: float) -> None:
        """Observe a scheduling wait time in the histogram."""
        self.wait_time.observe(seconds)

    def increment_rejection(self, reason: str) -> None:
        """Increment rejection counter for a specific reason."""
        self.rejection_total.labels(reason=reason).inc()

    def set_circuit_breaker_state(
        self, node_id: str, state: int
    ) -> None:
        """Set circuit breaker state for a node (0=closed, 1=open)."""
        self.circuit_breaker_state.labels(node_id=node_id).set(state)

    def set_vram_used(
        self, node_id: str, gpu_index: int, used_mb: int
    ) -> None:
        """Set VRAM usage for a GPU node."""
        self.vram_used.labels(
            node_id=node_id, gpu_index=str(gpu_index)
        ).set(used_mb)

    def set_gpu_utilization(
        self, node_id: str, gpu_index: int, utilization_pct: float
    ) -> None:
        """Set GPU utilization percentage for a node."""
        self.gpu_utilization.labels(
            node_id=node_id, gpu_index=str(gpu_index)
        ).set(utilization_pct)

    def increment_heartbeats(self) -> None:
        """Increment heartbeat counter."""
        self.heartbeats_total.inc()

    def increment_model_evictions(self, node_id: str) -> None:
        """Increment model eviction counter for a node."""
        self.model_evictions_total.labels(node_id=node_id).inc()

    def increment_aging(self) -> None:
        """Increment priority aging counter."""
        self.priority_aging_total.inc()

    def set_active_reservations(self, count: int) -> None:
        """Set active reservations count."""
        self.reservations_active.set(count)

    def increment_decisions(self, result: str) -> None:
        """Increment scheduling decisions counter."""
        self.scheduling_decisions_total.labels(result=result).inc()

    def set_registered_nodes(self, count: int) -> None:
        """Set registered nodes count."""
        self.nodes_registered.set(count)

    def set_alive_nodes(self, count: int) -> None:
        """Set alive nodes count."""
        self.nodes_alive.set(count)
