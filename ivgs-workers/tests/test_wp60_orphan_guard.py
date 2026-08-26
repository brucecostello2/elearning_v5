"""
WP-60 Task 10 — OrphanCleanupService: repaired, guarded, and PROVEN.

WP-59 D-2 ruled: repair it, and it MUST inherit the deletion service's
shared-object guard before it can quarantine or delete anything.

WHY THE GUARD IS THE WHOLE TASK. `LibraryService.reference_into_project`
(library_service.py:370-371) copies the library row's fid and path onto the
project row VERBATIM -- reference, not copy. So a library object shared into
three projects is FOUR ROWS OVER ONE SET OF BYTES. Decrement the project rows
and `reference_count` reaches 0 on some of them while the bytes are in active
use by the library and by every other project. The Type-3 scan quarantines
zero-reference assets and then permanently deletes them after seven days.
Switching it on as it stood would have deleted library bytes out from under
every referencing project, on a nightly schedule, silently.

THESE ARE CONSTRUCTED PROOFS AGAINST REAL ROWS in the reconciliation test
database, mirroring WP-59 Task 4's acceptance rather than asserting against a
mock that agrees with the code. Every row created here is removed in teardown.

The four the brief requires:
  1. a library reference SURVIVES the sweep
  2. a cross-project shared object SURVIVES the sweep
  3. a genuine orphan IS quarantined
  4. and it is quarantined WITH AN AUDIT TRAIL, not silently purged
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.orphan_cleanup import (
    OrphanCleanupService,
    SharedObjectGuard,
    ZERO_REF_THRESHOLD_DAYS,
)

pytestmark = pytest.mark.asyncio

DSN = os.environ.get("TEST_DATABASE_URL")
requires_db = pytest.mark.skipif(
    not DSN,
    reason="TEST_DATABASE_URL is not set; see TEST-BASELINE §1 for the block",
)

# Old enough that the zero-reference scan considers it.
STALE = datetime.now(timezone.utc) - timedelta(days=ZERO_REF_THRESHOLD_DAYS + 5)


@pytest_asyncio.fixture
async def factory():
    """A fresh engine per test.

    NullPool because each test runs on its own event loop: a pooled connection
    created on one loop and finalised on another raises "attached to a
    different loop" during teardown, which is noise about the fixture rather
    than about the service.
    """
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(DSN, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


class Fixtures:
    """Rows created for one test, and the teardown that removes them."""

    def __init__(self) -> None:
        self.tag = uuid.uuid4().hex[:12]
        self.project_ids: list[uuid.UUID] = []
        self.library_ids: list[uuid.UUID] = []
        self.asset_ids: list[uuid.UUID] = []

    async def project(self, session, name: str) -> uuid.UUID:
        pid = uuid.uuid4()
        await session.execute(
            text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
            {"id": pid, "name": f"wp60-{self.tag}-{name}"},
        )
        self.project_ids.append(pid)
        return pid

    async def library_asset(self, session, fid: str, path: str) -> uuid.UUID:
        lid = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO library_assets "
                "  (id, kind, name, seaweedfs_fid, seaweedfs_path) "
                "VALUES (:id, 'reference_image', :name, :fid, :path)"
            ),
            {"id": lid, "name": f"wp60-lib-{self.tag}", "fid": fid, "path": path},
        )
        self.library_ids.append(lid)
        return lid

    async def asset(
        self, session, *, project_id, fid, path,
        reference_count=1, library_asset_id=None, last_accessed_at=STALE,
    ) -> uuid.UUID:
        aid = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO assets "
                "  (id, project_id, asset_type, seaweedfs_fid, seaweedfs_path, "
                "   reference_count, library_asset_id, last_accessed_at, created_at) "
                "VALUES (:id, :pid, 'image', :fid, :path, :rc, :lib, :acc, :acc)"
            ),
            {
                "id": aid, "pid": project_id, "fid": fid, "path": path,
                "rc": reference_count, "lib": library_asset_id,
                "acc": last_accessed_at,
            },
        )
        self.asset_ids.append(aid)
        return aid

    async def cleanup(self, session) -> None:
        if self.asset_ids:
            await session.execute(
                text("DELETE FROM assets WHERE id = ANY(:ids)"),
                {"ids": self.asset_ids},
            )
        if self.library_ids:
            await session.execute(
                text("DELETE FROM library_assets WHERE id = ANY(:ids)"),
                {"ids": self.library_ids},
            )
        if self.project_ids:
            await session.execute(
                text("DELETE FROM projects WHERE id = ANY(:ids)"),
                {"ids": self.project_ids},
            )
        await session.execute(
            text("DELETE FROM audit_log WHERE after_payload::text LIKE :tag"),
            {"tag": f"%wp60-{self.tag}%"},
        )


@pytest_asyncio.fixture
async def fx(factory):
    f = Fixtures()
    yield f
    async with factory() as session:
        async with session.begin():
            await f.cleanup(session)


async def _run_sweep(factory, dry_run: bool = True):
    """The real service, on the real rows. Dry run: it decides everything and
    changes nothing, which is what makes the guard's verdict observable."""
    service = OrphanCleanupService(
        db_session_factory=factory,
        seaweedfs_base_url="http://127.0.0.1:1",   # unreachable on purpose:
        seaweedfs_filer_url="http://127.0.0.1:1",  # storage is not what is
        dry_run=dry_run,                           # under test here.
    )
    try:
        return await service.run_cleanup()
    finally:
        await service.close()


# ---------------------------------------------------------------------------
# PROOF 1 — a library reference survives
# ---------------------------------------------------------------------------

@requires_db
async def test_proof_1_a_library_reference_survives_the_sweep(factory, fx):
    fid, path = f"9,wp60lib{fx.tag}", f"/ivgs/library/wp60-{fx.tag}.png"

    async with factory() as session:
        async with session.begin():
            lib_id = await fx.library_asset(session, fid, path)
            project = await fx.project(session, "consumer")
            # reference_into_project's shape: SAME fid, SAME path, and the row
            # has fallen to zero references.
            asset_id = await fx.asset(
                session, project_id=project, fid=fid, path=path,
                reference_count=0, library_asset_id=lib_id,
            )

    report = await _run_sweep(factory)

    assert report.preserved.get("library_asset", 0) >= 1, (
        f"the library reference was NOT held back. preserved={report.preserved}"
    )

    guard = SharedObjectGuard(factory)
    assert await guard.keep_reason(fid, path, str(asset_id)) == "library_asset"

    # And it is still there, with its library link intact.
    async with factory() as session:
        row = (await session.execute(
            text("SELECT library_asset_id FROM assets WHERE id = :id"),
            {"id": asset_id},
        )).fetchone()
    assert row is not None and row[0] is not None


# ---------------------------------------------------------------------------
# PROOF 2 — a cross-project shared object survives
# ---------------------------------------------------------------------------

@requires_db
async def test_proof_2_a_cross_project_shared_object_survives(factory, fx):
    """Dedup: two projects, two rows, ONE set of bytes. One row falls to zero
    references; the other is in active use. Deleting the bytes because the
    first row looks unreferenced destroys the second project's asset."""
    fid = f"9,wp60shared{fx.tag}"
    path = f"/ivgs/images/wp60-shared-{fx.tag}.png"

    async with factory() as session:
        async with session.begin():
            p_a = await fx.project(session, "a")
            p_b = await fx.project(session, "b")
            unreferenced = await fx.asset(
                session, project_id=p_a, fid=fid, path=path, reference_count=0,
            )
            still_used = await fx.asset(
                session, project_id=p_b, fid=fid, path=path, reference_count=3,
            )

    report = await _run_sweep(factory)

    assert report.preserved.get("referenced_by_another_asset", 0) >= 1, (
        f"the shared object was NOT held back. preserved={report.preserved}"
    )

    guard = SharedObjectGuard(factory)
    reason = await guard.keep_reason(fid, path, str(unreferenced))
    assert reason == "referenced_by_another_asset"

    async with factory() as session:
        count = (await session.execute(
            text("SELECT count(*) FROM assets WHERE seaweedfs_fid = :fid"),
            {"fid": fid},
        )).scalar()
    assert count == 2, "a row over the shared object was destroyed"
    assert still_used  # referenced, for clarity


# ---------------------------------------------------------------------------
# PROOF 3 — a genuine orphan IS quarantined
# ---------------------------------------------------------------------------

@requires_db
async def test_proof_3_a_genuine_orphan_is_quarantined(factory, fx):
    """Nothing else names these bytes: no library row, no second asset row, no
    preserve_flag. The guard must NOT hold this one back, or the mechanism is
    safe by being useless."""
    fid = f"9,wp60orphan{fx.tag}"
    path = f"/ivgs/images/wp60-orphan-{fx.tag}.png"

    async with factory() as session:
        async with session.begin():
            project = await fx.project(session, "orphanhome")
            orphan = await fx.asset(
                session, project_id=project, fid=fid, path=path,
                reference_count=0,
            )

    guard = SharedObjectGuard(factory)
    assert await guard.keep_reason(fid, path, str(orphan)) == "", (
        "the guard held back an object nothing references - the sweep would "
        "never quarantine anything"
    )

    report = await _run_sweep(factory)

    assert report.type3_zero_reference_count >= 1, (
        f"the genuine orphan was not detected. coverage={report.coverage}"
    )
    assert report.newly_quarantined >= 1
    # Dry run: detected and reported, nothing moved.
    assert report.dry_run is True

    async with factory() as session:
        still_there = (await session.execute(
            text("SELECT count(*) FROM assets WHERE id = :id"), {"id": orphan},
        )).scalar()
    assert still_there == 1, "a DRY RUN deleted a row"


# ---------------------------------------------------------------------------
# PROOF 4 — with an audit trail, not silently purged
# ---------------------------------------------------------------------------

@requires_db
async def test_proof_4_the_quarantine_leaves_an_audit_trail(factory, fx):
    fid = f"9,wp60audit{fx.tag}"
    path = f"/ivgs/images/wp60-audit-{fx.tag}.png"

    async with factory() as session:
        async with session.begin():
            project = await fx.project(session, "auditable")
            await fx.asset(
                session, project_id=project, fid=fid, path=path,
                reference_count=0,
            )

    await _run_sweep(factory)

    async with factory() as session:
        rows = (await session.execute(
            text(
                "SELECT action_type, resource_type, after_payload "
                "FROM audit_log "
                "WHERE after_payload::text LIKE :needle "
                "ORDER BY timestamp DESC"
            ),
            {"needle": f"%{path}%"},
        )).fetchall()

    assert rows, "an object was quarantined with NO audit row"
    action, resource_type, payload = rows[0]
    assert action in ("QUARANTINE", "QUARANTINE_DRY_RUN")
    assert resource_type == "asset"
    # The trail has to carry enough to reverse the decision.
    assert payload.get("seaweedfs_fid") == fid
    assert payload.get("seaweedfs_path") == path
    assert payload.get("reason") == "zero_reference"
    assert payload.get("dry_run") is True
    assert "guard" in payload, "the audit row does not record that the guard ran"


# ---------------------------------------------------------------------------
# The guard fails CLOSED
# ---------------------------------------------------------------------------

async def test_the_guard_treats_an_unreachable_database_as_keep():
    """An unverifiable object must never be quarantined. The cost of a wrong
    keep is a wasted object; the cost of a wrong delete is unrecoverable."""
    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("database unreachable")

        async def __aexit__(self, *a):
            return False

    guard = SharedObjectGuard(lambda: _Boom())
    assert await guard.keep_reason("9,abc", "/ivgs/x.png", None) == "guard_unavailable"


def test_storage_urls_come_from_the_environment_not_from_node_01(monkeypatch):
    """WP-60 Task 10 — a repaired scan that still probes the wrong host.

    The defaults were `http://node-01:9333` / `:8888`. Inside a compose
    container `node-01` resolves to **127.0.1.1** first (verified with
    `getent hosts node-01` in ivgs-celery-default) and nothing listens there,
    so every probe hung until its connect timeout — roughly half an hour across
    161 assets, with nothing in the log to say why.

    The correct values were in the environment the whole time.
    """
    monkeypatch.setenv("SEAWEEDFS_MASTER_URL", "http://seaweedfs-master:9333")
    monkeypatch.setenv("SEAWEEDFS_FILER_URL", "http://seaweedfs-filer:8888")

    svc = OrphanCleanupService(db_session_factory=lambda: None)
    assert "node-01" not in svc._seaweedfs_base_url
    assert "node-01" not in svc._seaweedfs_filer_url
    assert svc._seaweedfs_base_url == "http://seaweedfs-master:9333"
    assert svc._seaweedfs_filer_url == "http://seaweedfs-filer:8888"


def test_an_explicit_url_still_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("SEAWEEDFS_FILER_URL", "http://from-env:8888")
    svc = OrphanCleanupService(
        db_session_factory=lambda: None,
        seaweedfs_filer_url="http://explicit:8888",
    )
    assert svc._seaweedfs_filer_url == "http://explicit:8888"


def test_the_service_defaults_to_dry_run():
    """It QUARANTINES and then PERMANENTLY DELETES. A caller that forgets an
    argument must get a report, not a purge."""
    assert OrphanCleanupService(db_session_factory=lambda: None)._dry_run is True


async def test_the_guard_refuses_an_object_it_cannot_identify():
    guard = SharedObjectGuard(lambda: None)
    assert await guard.keep_reason("", "", None) == "no_handle"
