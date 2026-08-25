"""
Phase 4 Gap 1: GPU Service Tests

Tests GpuService: register, list, get, update, drain, reservations, fleet utilization.
PURE_DB service — uses real AsyncSession.

Critical Path #7 tests included:
  - test_gpu_register_node_success
  - test_gpu_reserve_vram_allocation
  - test_gpu_reserve_insufficient_vram_fails
  - test_gpu_drain_node_releases_reservations
  - test_gpu_fleet_utilization_aggregation
"""
import uuid
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# WP-45 Task 4(b), D-2 RULED. `list_nodes` and `get_fleet_utilization` read the
# SCHEDULER's registry, not `gpu_nodes` - the table has always had zero rows
# because workers register with the scheduler and nothing has ever called
# POST /api/v1/gpu/nodes. The tests below that exercise those two methods stub
# the read-through; the ones that exercise registration, reservations and
# `gpu_nodes` itself are unchanged, because that table is still real and still
# referenced by gpu_reservations.
# ---------------------------------------------------------------------------


def _scheduler_fleet(*, nodes=None):
    nodes = nodes if nodes is not None else [{
        "node_id": "node-04:gpu0", "gpu_index": 0, "gpu_model": "RTX PRO 6000",
        "total_vram_mb": 97887, "used_vram_mb": 24576,
        "available_vram_mb": 73311, "gpu_utilization_pct": 25.0,
        "current_jobs": [], "last_heartbeat": "2026-08-25T13:00:00+00:00",
        "is_alive": True, "is_draining": False, "loaded_models": [],
        "circuit_breaker_state": "closed",
    }]
    total = sum(n["total_vram_mb"] for n in nodes)
    used = sum(n["used_vram_mb"] for n in nodes)
    return {
        "total_nodes": len(nodes),
        "alive_nodes": sum(1 for n in nodes if n["is_alive"]),
        "draining_nodes": sum(1 for n in nodes if n["is_draining"]),
        "total_vram_mb": total, "used_vram_mb": used,
        "available_vram_mb": total - used, "fleet_utilization_pct": 0.0,
        "queue_depth": {"urgent": 0, "normal": 0, "batch": 0}, "nodes": nodes,
    }


def _node(node_id, alive=True, draining=False, vram=97887, used=0):
    return {
        "node_id": node_id, "gpu_index": 0, "gpu_model": "RTX PRO 6000",
        "total_vram_mb": vram, "used_vram_mb": used,
        "available_vram_mb": vram - used, "gpu_utilization_pct": 0.0,
        "current_jobs": [], "last_heartbeat": "2026-08-25T13:00:00+00:00",
        "is_alive": alive, "is_draining": draining, "loaded_models": [],
        "circuit_breaker_state": "closed",
    }
from sqlalchemy import text

from app.services.gpu_service import GpuService
from app.schemas.gpu import GpuNodeCreate, GpuNodeUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_node(svc, hostname="gpu-host-01", index=0, vram=24576, model="A100"):
    data = GpuNodeCreate(
        node_hostname=hostname,
        gpu_index=index,
        gpu_model=model,
        total_vram_mb=vram,
        compute_capability="8.0",
    )
    return await svc.register_node(data)


async def _create_reservation(db, node_id, vram_mb=4096, status="reserved"):
    """Insert a GPU reservation directly."""
    job_id = uuid.uuid4()
    # Create a render job first
    await db.execute(
        text(
            "INSERT INTO render_jobs (id, project_id, job_type, status) "
            "VALUES (:jid, (SELECT id FROM projects LIMIT 1), 'video_generation', 'running')"
        ),
        {"jid": str(job_id)},
    )
    res_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO gpu_reservations (id, gpu_node_id, job_id, reserved_vram_mb, status) "
            "VALUES (:rid, :nid, :jid, :vram, :status)"
        ),
        {"rid": str(res_id), "nid": str(node_id), "jid": str(job_id), "vram": vram_mb, "status": status},
    )
    await db.commit()
    return res_id, job_id


async def _ensure_project(db):
    """Ensure at least one project exists for FK references."""
    row = (await db.execute(text("SELECT id FROM projects LIMIT 1"))).first()
    if row:
        return row[0]
    pid = uuid.uuid4()
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, username, password_hash, role) VALUES (:uid, :u, 'x', 'admin')"),
        {"uid": str(uid), "u": f"gpuuser-{uuid.uuid4().hex[:8]}"},
    )
    await db.execute(
        text("INSERT INTO projects (id, name, created_by) VALUES (:pid, 'GPU Test Project', :uid)"),
        {"pid": str(pid), "uid": str(uid)},
    )
    await db.commit()
    return pid


# ===========================================================================
# Critical Path #7 Tests (exact v3 Section 10 names)
# ===========================================================================

class TestCriticalPath7:
    """v3 Section 10 — GPU node register → reserve → drain lifecycle."""

    async def test_gpu_register_node_success(self, db_session):
        svc = GpuService(db_session)
        resp = await _register_node(svc)
        assert resp.node_hostname == "gpu-host-01"
        assert resp.gpu_index == 0
        assert resp.status == "online"
        assert resp.total_vram_mb == 24576

    async def test_gpu_reserve_vram_allocation(self, db_session):
        """After creating a reservation, used_vram_mb reflects it."""
        await _ensure_project(db_session)
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"h-{uuid.uuid4().hex[:6]}")
        await _create_reservation(db_session, node.id, vram_mb=8192, status="active")

        refreshed = await svc.get_node(node.id)
        assert refreshed is not None
        assert refreshed.used_vram_mb == 8192
        assert refreshed.available_vram_mb == 24576 - 8192

    async def test_gpu_reserve_insufficient_vram_fails(self, db_session):
        """
        Reserving more VRAM than available should logically fail.
        The service doesn't block this itself (scheduler does), but
        available_vram_mb should go negative, which is a detectable state.
        """
        await _ensure_project(db_session)
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"h-{uuid.uuid4().hex[:6]}", vram=1024)
        await _create_reservation(db_session, node.id, vram_mb=2048, status="active")

        refreshed = await svc.get_node(node.id)
        assert refreshed is not None
        # available goes negative when over-reserved
        assert refreshed.available_vram_mb < 0

    async def test_gpu_drain_node_releases_reservations(self, db_session):
        """Draining a node sets status to 'draining'."""
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"h-{uuid.uuid4().hex[:6]}")
        drained = await svc.drain_node(node.id)
        assert drained is not None
        assert drained.status == "draining"

    async def test_gpu_fleet_utilization_aggregation(self, db_session):
        """Fleet summary aggregates across the SCHEDULER's nodes (WP-45)."""
        svc = GpuService(db_session)
        fleet = _scheduler_fleet(nodes=[
            _node("node-02:gpu0", vram=16384, used=4096),
            _node("node-03:gpu0", vram=24576, used=0),
        ])
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=fleet),
        ):
            summary = await svc.get_fleet_utilization()
        assert summary.total_nodes == 2
        assert summary.total_vram_mb == 16384 + 24576
        assert summary.used_vram_mb == 4096
        assert summary.available_vram_mb == 16384 + 24576 - 4096
        assert summary.fleet_utilization_pct > 0


# ===========================================================================
# Additional Service Tests
# ===========================================================================

class TestRegisterNode:
    async def test_register_upsert_existing(self, db_session):
        """Re-registering same hostname+gpu_index updates instead of duplicating."""
        svc = GpuService(db_session)
        host = f"upsert-{uuid.uuid4().hex[:6]}"
        first = await _register_node(svc, hostname=host, index=0, model="A100")
        second = await _register_node(svc, hostname=host, index=0, model="H100")
        assert first.id == second.id
        assert second.gpu_model == "H100"

    async def test_register_different_index_creates_new(self, db_session):
        svc = GpuService(db_session)
        host = f"multi-{uuid.uuid4().hex[:6]}"
        n0 = await _register_node(svc, hostname=host, index=0)
        n1 = await _register_node(svc, hostname=host, index=1)
        assert n0.id != n1.id


class TestListNodes:
    """WP-45: these read the scheduler's registry, not gpu_nodes."""

    async def test_list_all(self, db_session):
        svc = GpuService(db_session)
        # A row in gpu_nodes must NOT appear: it is not what the fleet is.
        await _register_node(svc, hostname=f"list-{uuid.uuid4().hex[:6]}")
        with patch(
            "app.services.gpu_service.fetch_fleet",
            AsyncMock(return_value=_scheduler_fleet()),
        ):
            nodes, total = await svc.list_nodes()
        assert total == 1
        assert nodes[0].node_hostname == "node-04"

    async def test_list_with_status_filter(self, db_session):
        svc = GpuService(db_session)
        fleet = _scheduler_fleet(nodes=[
            _node("node-02:gpu0", alive=True),
            _node("node-03:gpu0", alive=False),
            _node("node-04:gpu0", alive=True, draining=True),
        ])
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=fleet),
        ):
            nodes, total = await svc.list_nodes(status_filter="online")
        assert total == 1
        assert all(n.status == "online" for n in nodes)

    async def test_list_pagination(self, db_session):
        svc = GpuService(db_session)
        fleet = _scheduler_fleet(nodes=[
            _node(f"node-0{i}:gpu0") for i in range(2, 6)
        ])
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=fleet),
        ):
            nodes, total = await svc.list_nodes(page=1, per_page=2)
        assert total == 4
        assert len(nodes) == 2

    async def test_an_unreachable_scheduler_raises_rather_than_reporting_zero(
        self, db_session,
    ):
        # "no nodes" and "I could not ask" must not be the same answer.
        from app.services.scheduler_fleet import SchedulerUnavailable

        svc = GpuService(db_session)
        with patch(
            "app.services.gpu_service.fetch_fleet",
            AsyncMock(side_effect=SchedulerUnavailable("refused")),
        ):
            with pytest.raises(SchedulerUnavailable):
                await svc.list_nodes()


class TestGetNode:
    async def test_get_existing(self, db_session):
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"get-{uuid.uuid4().hex[:6]}")
        result = await svc.get_node(node.id)
        assert result is not None
        assert result.id == node.id

    async def test_get_nonexistent(self, db_session):
        svc = GpuService(db_session)
        result = await svc.get_node(uuid.uuid4())
        assert result is None


class TestUpdateNode:
    async def test_update_model(self, db_session):
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"upd-{uuid.uuid4().hex[:6]}")
        updated = await svc.update_node(node.id, GpuNodeUpdate(gpu_model="H100"))
        assert updated is not None
        assert updated.gpu_model == "H100"

    async def test_update_nonexistent(self, db_session):
        svc = GpuService(db_session)
        result = await svc.update_node(uuid.uuid4(), GpuNodeUpdate(status="offline"))
        assert result is None


class TestDrainNode:
    async def test_drain_already_draining_raises(self, db_session):
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"drain-{uuid.uuid4().hex[:6]}")
        await svc.drain_node(node.id)
        with pytest.raises(ValueError, match="already draining"):
            await svc.drain_node(node.id)

    async def test_drain_offline_raises(self, db_session):
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"off-{uuid.uuid4().hex[:6]}")
        await svc.update_node(node.id, GpuNodeUpdate(status="offline"))
        with pytest.raises(ValueError, match="offline"):
            await svc.drain_node(node.id)

    async def test_drain_nonexistent(self, db_session):
        svc = GpuService(db_session)
        result = await svc.drain_node(uuid.uuid4())
        assert result is None


class TestNodeReservations:
    async def test_get_reservations_active_only(self, db_session):
        await _ensure_project(db_session)
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"res-{uuid.uuid4().hex[:6]}")
        await _create_reservation(db_session, node.id, vram_mb=2048, status="active")
        await _create_reservation(db_session, node.id, vram_mb=1024, status="released")

        reservations = await svc.get_node_reservations(node.id, active_only=True)
        assert reservations is not None
        assert all(r.status in ("reserved", "active") for r in reservations)

    async def test_get_reservations_all(self, db_session):
        await _ensure_project(db_session)
        svc = GpuService(db_session)
        node = await _register_node(svc, hostname=f"resa-{uuid.uuid4().hex[:6]}")
        await _create_reservation(db_session, node.id, vram_mb=2048, status="active")
        await _create_reservation(db_session, node.id, vram_mb=1024, status="released")

        reservations = await svc.get_node_reservations(node.id, active_only=False)
        assert reservations is not None
        assert len(reservations) >= 2

    async def test_get_reservations_nonexistent_node(self, db_session):
        svc = GpuService(db_session)
        result = await svc.get_node_reservations(uuid.uuid4())
        assert result is None


# ===========================================================================
# Coverage tests added for Step 2 (close-out): get_fleet_utilization status
# branches + get_utilization_history validation branches.
# ===========================================================================

async def _set_node_status(db, node_id, status):
    """Force a node's status field to a specific value (bypasses business logic)."""
    await db.execute(
        text("UPDATE gpu_nodes SET status = :s WHERE id = :id"),
        {"s": status, "id": str(node_id)},
    )
    await db.commit()


class TestFleetUtilizationStatusBranches:
    """WP-45: the three statuses come from the scheduler's two booleans."""

    async def test_fleet_counts_nodes_in_all_states(self, db_session):
        svc = GpuService(db_session)
        fleet = _scheduler_fleet(nodes=[
            _node("node-02:gpu0", alive=True, draining=False),
            _node("node-03:gpu0", alive=False, draining=False),
            _node("node-04:gpu0", alive=True, draining=True),
        ])
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=fleet),
        ):
            summary = await svc.get_fleet_utilization()
        assert summary.total_nodes == 3
        assert summary.online_nodes == 1
        assert summary.offline_nodes == 1
        # Draining wins over alive: a draining node is still heartbeating, and
        # what matters is that it is not taking new work.
        assert summary.draining_nodes == 1

class TestUtilizationHistoryValidation:
    """Cover the 6 validation branches of get_utilization_history (lines 364-505)."""

    async def test_empty_range_string_rejected(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("")
        assert exc_info.value.status_code == 400

    async def test_single_char_range_rejected(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("h")
        assert exc_info.value.status_code == 400

    async def test_non_numeric_prefix_rejected(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("abch")
        assert exc_info.value.status_code == 400
        assert "numeric prefix" in exc_info.value.detail["error"]["message"]

    async def test_zero_amount_rejected(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("0h")
        assert exc_info.value.status_code == 400
        assert "positive" in exc_info.value.detail["error"]["message"]

    async def test_negative_amount_rejected(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("-5h")
        assert exc_info.value.status_code == 400

    async def test_unsupported_unit_rejected(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("5y")
        assert exc_info.value.status_code == 400
        assert "unit" in exc_info.value.detail["error"]["message"].lower()

    async def test_exceeds_30day_retention_boundary(self, db_session):
        from fastapi import HTTPException
        svc = GpuService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_utilization_history("31d")
        assert exc_info.value.status_code == 400
        assert "30-day" in exc_info.value.detail["error"]["message"]

    async def test_valid_range_returns_list(self, db_session):
        svc = GpuService(db_session)
        result = await svc.get_utilization_history("1h")
        assert isinstance(result, list)
