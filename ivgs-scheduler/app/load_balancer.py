"""Dynamic GPU load balancer for Phase 2.

Replaces Phase 1 round-robin with weighted-random selection
based on real-time GPU utilization metrics stored in PostgreSQL.

Weight formula:
    w(gpu) = (1 - util_pct) * (1 - mem_pct) * queue_slack_factor
    where queue_slack_factor = max(0, (max_queue - current_queue) / max_queue)

Normalization: weights are normalized to sum=1 before sampling.
If all GPUs have zero weight (all saturated), raises NoCapacityError.
"""

import logging
import random
import statistics
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

MAX_QUEUE_DEPTH = 4     # Max pending jobs per GPU
METRICS_WINDOW_MINUTES = 5
IMBALANCE_ALERT_STDDEV = 0.30


class NoCapacityError(Exception):
    """Raised when no GPU has capacity for a task."""
    pass


class LoadBalancer:
    """Weighted GPU selection based on real-time utilization."""

    def __init__(self, db: Session, redis_client=None):
        self.db = db
        self.redis = redis_client

    def select_optimal_gpu(
        self,
        task_type: str,
        vram_requirement_mb: int,
        exclude_nodes: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Select best GPU using weighted-random algorithm.

        Returns dict: {node_id, gpu_index, node_hostname, available_vram_mb}
        Raises NoCapacityError if no GPU available.
        """
        candidates = self._get_candidate_gpus(
            vram_requirement_mb, exclude_nodes or []
        )
        if not candidates:
            raise NoCapacityError(
                f"No GPU available with {vram_requirement_mb}MB VRAM "
                f"for task type '{task_type}'"
            )

        weights = []
        for gpu in candidates:
            w = self._compute_weight(gpu)
            weights.append(w)
            logger.debug(
                "GPU %s:%d weight=%.4f (util=%.1f%%, mem=%.1f%%, q=%d)",
                gpu['hostname'], gpu['gpu_index'], w,
                gpu['util_pct'], gpu['mem_util_pct'], gpu['queue_depth']
            )

        total_weight = sum(weights)
        if total_weight == 0:
            raise NoCapacityError(
                "All GPUs at capacity — retry later"
            )

        # Weighted random selection
        r = random.uniform(0, total_weight)
        cumulative = 0
        selected = candidates[0]
        for gpu, w in zip(candidates, weights):
            cumulative += w
            if r <= cumulative:
                selected = gpu
                break

        logger.info(
            "LoadBalancer: selected GPU %s:%d for task '%s' "
            "(weight=%.4f, vram_avail=%dMB)",
            selected['hostname'], selected['gpu_index'],
            task_type, self._compute_weight(selected),
            selected['available_vram_mb']
        )
        return selected

    def record_metrics(
        self, node_id: int, metrics: Dict[str, Any]
    ) -> None:
        """Record GPU metrics snapshot for load balancing decisions."""
        try:
            from sqlalchemy import text
            self.db.execute(text("""
                INSERT INTO gpu_metrics_history
                    (gpu_node_id, gpu_util_pct, mem_util_pct,
                     temperature_c, power_draw_w, active_job_count,
                     queue_depth)
                VALUES
                    (:node_id, :gpu_util, :mem_util,
                     :temp, :power, :active_jobs, :queue_depth)
            """), {
                "node_id": node_id,
                "gpu_util": metrics.get('gpu_util_pct', 0),
                "mem_util": metrics.get('mem_util_pct', 0),
                "temp": metrics.get('temperature_c'),
                "power": metrics.get('power_draw_w'),
                "active_jobs": metrics.get('active_job_count', 0),
                "queue_depth": metrics.get('queue_depth', 0),
            })
            self.db.commit()
        except Exception as e:
            logger.error("Failed to record GPU metrics: %s", e)

    def get_utilization_report(self) -> Dict[str, Any]:
        """Return per-GPU and fleet-wide utilization statistics."""
        from sqlalchemy import text
        cutoff = datetime.utcnow() - timedelta(minutes=METRICS_WINDOW_MINUTES)
        rows = self.db.execute(text("""
            SELECT
                n.node_hostname,
                n.gpu_index,
                n.gpu_model,
                AVG(m.gpu_util_pct) AS avg_util,
                AVG(m.mem_util_pct) AS avg_mem,
                AVG(m.queue_depth)  AS avg_queue,
                MAX(m.recorded_at)  AS last_seen
            FROM gpu_nodes n
            LEFT JOIN gpu_metrics_history m
                   ON m.gpu_node_id = n.id
                  AND m.recorded_at >= :cutoff
            WHERE n.status = 'online'
            GROUP BY n.id, n.node_hostname, n.gpu_index, n.gpu_model
            ORDER BY avg_util DESC NULLS LAST
        """), {"cutoff": cutoff}).fetchall()

        gpu_stats = []
        util_values = []
        for row in rows:
            avg_util = float(row.avg_util or 0)
            util_values.append(avg_util)
            gpu_stats.append({
                "hostname": row.node_hostname,
                "gpu_index": row.gpu_index,
                "model": row.gpu_model,
                "avg_util_pct": round(avg_util, 1),
                "avg_mem_pct": round(float(row.avg_mem or 0), 1),
                "avg_queue": round(float(row.avg_queue or 0), 1),
                "last_seen": str(row.last_seen or ''),
            })

        fleet_avg = statistics.mean(util_values) if util_values else 0
        fleet_stddev = (statistics.stdev(util_values)
                        if len(util_values) > 1 else 0)

        imbalanced = fleet_stddev > IMBALANCE_ALERT_STDDEV
        if imbalanced:
            logger.warning(
                "GPU fleet utilization imbalanced: stddev=%.2f "
                "(threshold=%.2f)", fleet_stddev, IMBALANCE_ALERT_STDDEV
            )

        return {
            "gpu_count": len(gpu_stats),
            "fleet_avg_util_pct": round(fleet_avg, 1),
            "fleet_stddev": round(fleet_stddev, 3),
            "imbalanced": imbalanced,
            "gpus": gpu_stats,
        }

    def detect_imbalance(self) -> bool:
        """Return True if utilization stddev exceeds threshold."""
        report = self.get_utilization_report()
        return report.get('imbalanced', False)

    # ──────────────────────────────────────────────

    def _get_candidate_gpus(
        self, vram_requirement_mb: int, exclude: List[int]
    ) -> List[Dict[str, Any]]:
        """Query GPU nodes with sufficient available VRAM."""
        from sqlalchemy import text
        cutoff = datetime.utcnow() - timedelta(minutes=METRICS_WINDOW_MINUTES)
        rows = self.db.execute(text("""
            SELECT
                n.id AS node_id,
                n.node_hostname AS hostname,
                n.gpu_index,
                n.total_vram_mb,
                COALESCE(SUM(r.reserved_vram_mb), 0) AS reserved_mb,
                n.total_vram_mb - COALESCE(SUM(r.reserved_vram_mb), 0)
                    AS available_vram_mb,
                COALESCE(m.avg_util, 0.0) AS util_pct,
                COALESCE(m.avg_mem, 0.0) AS mem_util_pct,
                COALESCE(m.avg_q, 0) AS queue_depth
            FROM gpu_nodes n
            LEFT JOIN gpu_reservations r
                   ON r.gpu_node_id = n.id
                  AND r.status IN ('reserved', 'active')
            LEFT JOIN (
                SELECT gpu_node_id,
                       AVG(gpu_util_pct)  AS avg_util,
                       AVG(mem_util_pct)  AS avg_mem,
                       AVG(queue_depth)   AS avg_q
                FROM gpu_metrics_history
                WHERE recorded_at >= :cutoff
                GROUP BY gpu_node_id
            ) m ON m.gpu_node_id = n.id
            WHERE n.status = 'online'
              AND n.id NOT IN :exclude
            GROUP BY n.id, n.node_hostname, n.gpu_index, n.total_vram_mb,
                     m.avg_util, m.avg_mem, m.avg_q
            HAVING
                (n.total_vram_mb - COALESCE(SUM(r.reserved_vram_mb), 0))
                    >= :vram
        """), {
            "cutoff": cutoff,
            "vram": vram_requirement_mb,
            "exclude": tuple(exclude) if exclude else (0,),
        }).fetchall()

        return [dict(row._mapping) for row in rows]

    def _compute_weight(self, gpu: Dict[str, Any]) -> float:
        """Compute scheduling weight for a GPU candidate."""
        util = min(1.0, float(gpu.get('util_pct', 0)) / 100.0)
        mem  = min(1.0, float(gpu.get('mem_util_pct', 0)) / 100.0)
        q    = float(gpu.get('queue_depth', 0))
        q_slack = max(0.0, (MAX_QUEUE_DEPTH - q) / MAX_QUEUE_DEPTH)
        return max(0.0, (1.0 - util) * (1.0 - mem) * q_slack)
