"""
WP-60 Task 3 — the acquire/release imbalance, constructed rather than waited for.

WHAT THIS PINS, AND WHY IT IS NOT A UNIT-TEST FORMALITY.

Measured on the live fleet at 2026-08-26 01:37 UTC::

    gpu:node:node-03:gpu0   used_vram_mb   = 16384
                            current_job_id = ""        (nothing running)
                            registered_at  = 2026-08-26T00:36
    sched:reservation:*     -- NO KEYS EXIST ANYWHERE IN db1 --

A registration one hour old, already carrying 16 GB of reservation that no job
and no reservation record could account for. ``AdmissionController.
_check_vram_availability`` computes headroom as ``total_vram_mb -
used_vram_mb``, so node-03 was silently a 16 GB smaller GPU than it is, and
would have stayed that way.

THE MECHANISM, which the brief asked to be established between two candidates:

  * "re-registration preserved a stale counter" — RULED OUT. ``register_node``
    wrote ``used_vram_mb: "0"`` unconditionally on every registration
    (``gpu_registry.py:147`` before this package). Registration could not
    preserve anything; it erased.

  * "an acquire after 00:36 lost its release" — CONFIRMED, and it is not a
    race. ``sched:reservation:{id}`` is written with ``EXPIRE ttl_s`` where
    ttl_s was the hardcoded 300 (§12.2), while ``used_vram_mb`` on the node
    hash is a plain counter with no TTL. The longest hard task time_limit in
    this system is 3900s. So EVERY reservation covering a long render outlives
    its own record by an hour, at which point ``release_reservation`` found
    nothing and raised ``ReservationNotFoundError`` — and the counter it had
    incremented stayed up. A one-way ratchet, not a rare interleaving.

    ``cleanup_expired_reservations`` was the only thing that noticed, and its
    own comment said why it could not help: *"We don't know the node_id
    anymore"*. It removed the index entries that recorded the debt and left the
    debt. The live counter finally cleared at 02:46 — by re-registration
    zeroing it, which is the defect erasing its own evidence, not a recovery.

The tests below construct exactly that condition: reserve, expire the record
the way Redis would, release, and assert the VRAM comes back.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from admission_control import AdmissionController
from gpu_registry import GpuRegistry
from model_concurrency import ModelConcurrencyManager, normalise_model_name
from scheduler import GpuScheduler
from test_scheduler import FakeRedis


NODE = "node-03:gpu0"
TOTAL_VRAM = 97_887
RESERVED = 16_384


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def registry(redis):
    return GpuRegistry(redis=redis)


@pytest.fixture
def concurrency(redis):
    return ModelConcurrencyManager(redis=redis)


@pytest.fixture
def admission(redis, registry, concurrency):
    return AdmissionController(
        registry=registry,
        circuit_breaker=AsyncMock(),
        concurrency=concurrency,
        redis=redis,
    )


@pytest.fixture
def scheduler(redis, registry, admission, concurrency):
    """A scheduler whose reservation TTL is 1s, so the expiry this test needs
    can be constructed instead of waited five minutes for."""
    return GpuScheduler(
        registry=registry,
        admission=admission,
        load_balancer=MagicMock(),
        concurrency=concurrency,
        priority_queue=MagicMock(),
        circuit_breaker=MagicMock(),
        redis=redis,
        metrics=None,
        reservation_ttl_s=1,
    )


async def _register(registry):
    return await registry.register_node(
        node_hostname="node-03",
        gpu_index=0,
        gpu_model="NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        total_vram_mb=TOTAL_VRAM,
        compute_capability="12.0",
    )


async def _expire_the_ttl_record(redis, reservation_id):
    """What Redis does at ttl_s, done deterministically.

    Only the TTL'd hash goes. The node counter, the index and the per-node set
    are untouched -- exactly the state the live fleet was found in.
    """
    await redis.delete(f"sched:reservation:{reservation_id}")


class TestTheLeakItself:
    async def test_a_release_after_the_ttl_returns_the_vram(self, redis, registry, admission, scheduler):
        """RED before WP-60: raised ReservationNotFoundError and left 16 GB
        counted against a node with nothing running on it."""
        await _register(registry)

        reservation = await scheduler._create_reservation(
            job_id="job-1",
            node_id=NODE,
            gpu_index=0,
            model_name="wan2.2-animate",
            vram_mb=RESERVED,
            estimated_duration_s=3900,
        )
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == RESERVED

        # The job runs for 3900s. Its reservation record lives for 300.
        await _expire_the_ttl_record(redis, reservation.reservation_id)

        result = await admission.release_reservation(reservation.reservation_id)

        assert result.vram_freed_mb == RESERVED
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == 0

    async def test_headroom_is_restored_so_admission_stops_undercounting(
        self, redis, registry, admission, scheduler
    ):
        """The consequence, asserted where it bites: admission control."""
        await _register(registry)
        reservation = await scheduler._create_reservation(
            job_id="job-1", node_id=NODE, gpu_index=0,
            model_name="wan2.2-animate", vram_mb=RESERVED,
            estimated_duration_s=3900,
        )
        await _expire_the_ttl_record(redis, reservation.reservation_id)
        await admission.release_reservation(reservation.reservation_id)

        nodes = await registry.get_alive_nodes()
        assert len(nodes) == 1
        assert nodes[0].available_vram_mb == TOTAL_VRAM

    async def test_the_expiry_sweep_releases_instead_of_only_tidying(
        self, redis, registry, admission, scheduler
    ):
        """`cleanup_expired_reservations` used to drop the index entry and
        leave the VRAM -- turning a visible leak into an invisible one."""
        await _register(registry)
        reservation = await scheduler._create_reservation(
            job_id="job-1", node_id=NODE, gpu_index=0,
            model_name="wan2.2-animate", vram_mb=RESERVED,
            estimated_duration_s=3900,
        )
        await _expire_the_ttl_record(redis, reservation.reservation_id)

        released = await admission.cleanup_expired_reservations()

        assert released == 1
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == 0

    async def test_a_live_reservation_is_not_swept(self, redis, registry, admission, scheduler):
        """The sweep must not free VRAM a running job still holds."""
        await _register(registry)
        await scheduler._create_reservation(
            job_id="job-1", node_id=NODE, gpu_index=0,
            model_name="wan2.2-animate", vram_mb=RESERVED,
            estimated_duration_s=3900,
        )
        assert await admission.cleanup_expired_reservations() == 0
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == RESERVED


class TestRegistrationReseedsOrReconciles:
    """The brief: make registration's behaviour explicit rather than accidental."""

    async def test_first_registration_seeds_zero(self, redis, registry):
        await _register(registry)
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == 0

    async def test_reregistration_does_not_erase_a_live_reservation(
        self, redis, registry, scheduler
    ):
        """The defect in the OTHER direction, which the blind reseed created.

        A worker that restarts mid-render re-registers while its own job still
        holds the GPU. The old unconditional `used_vram_mb: "0"` told admission
        control the whole card was free, so it would over-admit onto a busy
        GPU. Derived accounting keeps the live reservation.
        """
        await _register(registry)
        await scheduler._create_reservation(
            job_id="job-1", node_id=NODE, gpu_index=0,
            model_name="wan2.2-animate", vram_mb=RESERVED,
            estimated_duration_s=3900,
        )
        await _register(registry)  # worker restarts, re-registers
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == RESERVED

    async def test_reregistration_clears_a_counter_no_reservation_justifies(
        self, redis, registry
    ):
        """The live node-03 condition. Derived accounting corrects it, and --
        unlike the old blind zeroing -- says that it did."""
        await _register(registry)
        await redis.hset(f"gpu:node:{NODE}", mapping={"used_vram_mb": str(RESERVED)})

        await _register(registry)

        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == 0


class TestOperatorReconcilePath:
    async def test_reconcile_reports_the_drift_it_corrects(self, redis, registry, admission):
        await _register(registry)
        await redis.hset(f"gpu:node:{NODE}", mapping={"used_vram_mb": str(RESERVED)})

        result = await admission.reconcile_node_vram(NODE)

        assert result["previous_used_vram_mb"] == RESERVED
        assert result["used_vram_mb"] == 0
        assert result["drift_mb"] == RESERVED
        assert result["reconciled"] is True
        assert int(await redis.hget(f"gpu:node:{NODE}", "used_vram_mb")) == 0

    async def test_reconcile_is_a_no_op_when_the_books_balance(
        self, redis, registry, admission, scheduler
    ):
        await _register(registry)
        await scheduler._create_reservation(
            job_id="job-1", node_id=NODE, gpu_index=0,
            model_name="wan2.2-animate", vram_mb=RESERVED,
            estimated_duration_s=3900,
        )
        result = await admission.reconcile_node_vram(NODE)
        assert result["drift_mb"] == 0
        assert result["reconciled"] is False
        assert result["used_vram_mb"] == RESERVED


class TestModelNameIsNormalisedAtWrite:
    """WP-60 Task 3(a). db1 held gpu:model_fleet:wan2.2-animate ->
    {node-04:gpu0} AND gpu:model_fleet:Wan2.2-Animate -> {c326eab3def1:gpu0}.
    Both were written by this class, from callers that disagreed on case."""

    def test_normaliser_is_idempotent_and_case_folding(self):
        assert normalise_model_name("Wan2.2-Animate") == "wan2.2-animate"
        assert normalise_model_name("wan2.2-animate") == "wan2.2-animate"
        assert normalise_model_name("  Wan2.2-Animate  ") == "wan2.2-animate"
        once = normalise_model_name("Wan2.2-Animate")
        assert normalise_model_name(once) == once

    async def test_two_spellings_land_in_one_set_of_keys(self, redis, concurrency):
        await concurrency.record_model_load(
            node_id="node-04:gpu0", gpu_index=0,
            model_name="Wan2.2-Animate", job_id="job-1",
        )
        await concurrency.record_model_load(
            node_id="node-04:gpu0", gpu_index=0,
            model_name="wan2.2-animate", job_id="job-2",
        )

        assert await redis.smembers("gpu:model_fleet:Wan2.2-Animate") == set()
        assert await redis.smembers("gpu:model_fleet:wan2.2-animate") == {
            "node-04:gpu0"
        }
        assert await redis.smembers("gpu:models:node-04:gpu0") == {
            "wan2.2-animate"
        }

    async def test_a_load_under_one_spelling_is_visible_to_the_other(
        self, redis, concurrency
    ):
        """The consequence that mattered: the per-model concurrency limit was
        enforced per SPELLING, so two jobs of the same model could each see a
        count of zero and both be admitted onto a GPU sized for one."""
        await concurrency.record_model_load(
            node_id="node-04:gpu0", gpu_index=0,
            model_name="Wan2.2-Animate", job_id="job-1",
        )
        assert await concurrency.get_concurrent_count("wan2.2-animate") == 1
        assert await concurrency.get_concurrent_count("Wan2.2-Animate") == 1
