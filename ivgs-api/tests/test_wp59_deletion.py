"""
WP-59 — project deletion.

WHAT THESE TESTS PIN, and why each one exists:

* The CATEGORY MAP is complete against the live foreign keys. A category
  missing from the map is a category silently left behind, and the map is the
  single source of both the dialog and the destruction — so it is the one thing
  worth pinning hardest.
* Deletion REFUSES while any job is non-terminal, and the refusal names the
  jobs (Task 3).
* Deletion refuses without the exact project name (Task 6).
* THE LIBRARY ASSET AND THE SHARED BYTES SURVIVE (Task 4). This is the
  acceptance test the package asks for: a project referencing a library asset,
  two projects pointing at the same object, delete one, and prove both the
  library asset and the object are intact with the surviving reference working.
* The audit record exists BEFORE destruction and survives it (Task 2).
* Deletion is idempotent and converges (Task 2).

The acceptance criterion is deliberately NOT "the call returned 200". WP-45
Task 3 found eight surfaces returning 202 while doing nothing; a status-code
test would have passed against that defect for as long as it existed. Every
test below asserts what is left in the database.
"""
import uuid

import pytest
from sqlalchemy import text

from app.services.project_deletion import (
    AlreadyDeletedError,
    CATEGORY_KEYS,
    ConfirmationMismatchError,
    NonTerminalJobsError,
    PROJECT_CATEGORIES,
    ProjectDeletionError,
    ProjectDeletionService,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — rows are inserted directly rather than through the API, because
# what is under test is what deletion REACHES, not how the rows got there.
# ---------------------------------------------------------------------------

async def _make_user(db_session, username, role="admin"):
    from app.services.user_service import create_user
    return await create_user(db_session, username, "Str0ngP@ss1", role)


async def _make_project(db_session, user, name):
    pid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO projects (id, name, state, created_by) "
            "VALUES (:id, :name, 'DRAFT', :uid)"
        ),
        {"id": pid, "name": name, "uid": user.id},
    )
    await db_session.commit()
    return pid


async def _make_asset(db_session, project_id, *, fid, path, library_asset_id=None,
                      asset_type="image", size=1234):
    aid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO assets (id, project_id, asset_type, seaweedfs_fid, "
            "  seaweedfs_path, file_size_bytes, library_asset_id, storage_tier) "
            "VALUES (:id, :pid, CAST(:t AS asset_type), :fid, :path, :size, "
            "        :lib, 'hot')"
        ),
        {"id": aid, "pid": project_id, "t": asset_type, "fid": fid,
         "path": path, "size": size, "lib": library_asset_id},
    )
    await db_session.commit()
    return aid


async def _make_library_asset(db_session, user, *, fid, path, kind="logo"):
    lid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO library_assets (id, kind, name, seaweedfs_fid, "
            "  seaweedfs_path, owner_scope, created_by) "
            "VALUES (:id, CAST(:k AS library_asset_kind), :n, :fid, :path, "
            "        CAST('user' AS library_owner_scope), :uid)"
        ),
        {"id": lid, "k": kind, "n": "Test logo", "fid": fid, "path": path,
         "uid": user.id},
    )
    await db_session.commit()
    return lid


async def _make_job(db_session, project_id, status="running",
                    job_type="image_generation"):
    jid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO render_jobs (id, project_id, job_type, status) "
            "VALUES (:id, :pid, CAST(:t AS job_type), CAST(:s AS job_status))"
        ),
        {"id": jid, "pid": project_id, "t": job_type, "s": status},
    )
    await db_session.commit()
    return jid


@pytest.fixture
def no_scheduler_registry(monkeypatch):
    """Answer "no reservations held" without a scheduler.

    The scheduler's registry lives in a Redis database this suite has no
    address for. Where the registry is not what is under test, it is stubbed to
    the answer a healthy empty registry gives -- and the UNREADABLE case has its
    own test below, which does exercise the real code path.
    """
    async def _none(self, job_ids):
        return []
    monkeypatch.setattr(ProjectDeletionService, "gpu_reservations_for_jobs", _none)


@pytest.fixture
def redis_scan_empty(monkeypatch):
    """Answer the scratch-key scan with "no keys", without a Redis.

    `conftest.mock_redis` replaces the RedisClient's own methods but not
    `redis_client.client`, which is a real aioredis handle. `scan_iter` is
    reached through it. Where the Redis outcome is not what a test is about,
    it is stubbed to what a healthy empty keyspace returns -- and the
    UNREACHABLE case has its own test below, which does not use this fixture.
    """
    from shared.redis_client import redis_client

    async def _scan_iter(match=None, count=None):
        return
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(redis_client.client, "scan_iter", _scan_iter)


@pytest.fixture
def record_purges(monkeypatch):
    """Record every object the purge step actually deletes."""
    from shared.seaweedfs_client import seaweedfs_client

    deleted_fids: list[str] = []

    async def _delete_file(fid):
        deleted_fids.append(fid)
        return True

    class _NoFiler:
        async def delete(self, url):
            raise RuntimeError("filer not reachable in this suite")

    async def _get_client():
        return _NoFiler()

    monkeypatch.setattr(seaweedfs_client, "delete_file", _delete_file)
    monkeypatch.setattr(seaweedfs_client, "_get_client", _get_client)
    return deleted_fids


# ---------------------------------------------------------------------------
# Task 1 — the map
# ---------------------------------------------------------------------------

class TestCategoryMap:
    async def test_every_project_fk_table_is_in_the_map(self, db_session):
        """The map must name every table a cascade from `projects` reaches.

        This is the test that stops the map going stale. It reads
        `pg_constraint` from the LIVE test schema and walks the cascade closure
        outward from `projects`, then asserts every table it finds appears in
        `PROJECT_CATEGORIES`. Add a table with a cascading FK to projects,
        render_jobs, assets or storyboard_scenes and forget the dialog, and this
        fails by name.
        """
        rows = (await db_session.execute(text("""
            SELECT con.conrelid::regclass::text AS child,
                   con.confrelid::regclass::text AS parent
            FROM pg_constraint con
            WHERE con.contype = 'f' AND con.confdeltype = 'c'
        """))).fetchall()

        edges: dict[str, list[str]] = {}
        for child, parent in rows:
            edges.setdefault(parent, []).append(child)

        reachable: set[str] = set()
        frontier = ["projects"]
        while frontier:
            node = frontier.pop()
            for child in edges.get(node, []):
                if child not in reachable:
                    reachable.add(child)
                    frontier.append(child)

        mapped = set(CATEGORY_KEYS)
        # `users` cascades INTO projects, not out of it; the closure above walks
        # outward only, so it cannot appear. Partitioned gpu_metrics_history
        # children hang off gpu_nodes, not projects.
        missing = {t for t in reachable if t not in mapped}
        assert not missing, (
            f"tables reachable by ON DELETE CASCADE from projects that no "
            f"deletion category names: {sorted(missing)}. Each one is material "
            f"a deletion destroys without telling anybody."
        )

    async def test_orphan_categories_carry_an_explicit_delete(self):
        """Anything no FK reaches must be deleted by hand, in the transaction."""
        for cat in PROJECT_CATEGORIES:
            if cat.cascade == "orphan":
                assert cat.delete_sql, (
                    f"{cat.key} is marked 'orphan' -- nothing cascades to it -- "
                    f"so it needs an explicit DELETE or it survives the project."
                )
            if cat.cascade == "cascade":
                assert cat.delete_sql is None, (
                    f"{cat.key} cascades; issuing a redundant DELETE would be a "
                    f"second, divergent statement of the schema."
                )

    async def test_dlq_and_quotas_are_marked_orphan(self):
        """Pin the two the live schema says nothing reaches.

        `dead_letter_messages` has no foreign key to anything at all, and
        `storage_quotas.entity_id` is polymorphic over `entity_type` so it
        cannot carry one. Both verified against the live schema 2026-08-26.
        """
        by_key = {c.key: c for c in PROJECT_CATEGORIES}
        assert by_key["dead_letter_messages"].cascade == "orphan"
        assert by_key["storage_quotas"].cascade == "orphan"


# ---------------------------------------------------------------------------
# Task 3 — running work
# ---------------------------------------------------------------------------

class TestNonTerminalJobs:
    @pytest.mark.parametrize("status", ["pending", "running"])
    async def test_refuses_while_a_job_is_not_terminal(
        self, db_session, no_scheduler_registry, status
    ):
        user = await _make_user(db_session, f"wp59_block_{status}")
        pid = await _make_project(db_session, user, f"Blocked {status}")
        jid = await _make_job(db_session, pid, status=status)

        svc = ProjectDeletionService(db_session)
        try:
            with pytest.raises(NonTerminalJobsError) as exc:
                await svc.delete(
                    pid, confirmation_name=f"Blocked {status}",
                    actor_id=user.id, actor_name=user.username,
                )
        finally:
            await svc.close()

        assert str(jid) in {j["id"] for j in exc.value.jobs}

        # AND THE PROJECT IS STILL THERE. A refusal that deleted anyway would
        # pass an exception-type-only test.
        still = await db_session.execute(
            text("SELECT count(*) FROM projects WHERE id = :p"), {"p": pid})
        assert still.scalar() == 1

    @pytest.mark.parametrize("status", ["success", "failed"])
    async def test_terminal_jobs_do_not_block(
        self, db_session, no_scheduler_registry, record_purges, status
    ):
        """`failed` is terminal, and that is how Cancel unblocks deletion.

        `job_status` is a four-value enum with no 'cancelled' member;
        `JobService.cancel_job` writes `failed` with error_message "Cancelled by
        user" (job_service.py:182). So cancelling a job is exactly what moves it
        into the terminal set this test pins.
        """
        user = await _make_user(db_session, f"wp59_term_{status}")
        pid = await _make_project(db_session, user, f"Terminal {status}")
        await _make_job(db_session, pid, status=status)

        svc = ProjectDeletionService(db_session)
        try:
            result = await svc.delete(
                pid, confirmation_name=f"Terminal {status}",
                actor_id=user.id, actor_name=user.username,
            )
        finally:
            await svc.close()

        assert result.rows_deleted["render_jobs"] == 1
        gone = await db_session.execute(
            text("SELECT count(*) FROM projects WHERE id = :p"), {"p": pid})
        assert gone.scalar() == 0

    async def test_unreadable_scheduler_registry_refuses(self, db_session):
        """"I could not check" is not "there is nothing".

        No stub here: the real `gpu_reservations_for_jobs` runs against a
        scheduler Redis this suite cannot reach, and the deletion must refuse
        on the unknown rather than assume the reservation is released.
        """
        user = await _make_user(db_session, "wp59_registry_down")
        pid = await _make_project(db_session, user, "Registry Down")
        await _make_job(db_session, pid, status="success")

        svc = ProjectDeletionService(db_session)
        try:
            preview = await svc.preview(pid)
            assert preview.scheduler_registry_error is not None
            assert preview.deletable is False
            with pytest.raises(ProjectDeletionError) as exc:
                await svc.delete(
                    pid, confirmation_name="Registry Down",
                    actor_id=user.id, actor_name=user.username,
                )
        finally:
            await svc.close()
        assert "registry" in str(exc.value).lower()

        still = await db_session.execute(
            text("SELECT count(*) FROM projects WHERE id = :p"), {"p": pid})
        assert still.scalar() == 1


# ---------------------------------------------------------------------------
# Task 6 — confirmation
# ---------------------------------------------------------------------------

class TestConfirmation:
    @pytest.mark.parametrize(
        "wrong", ["", "wrong", "confirm me", "Confirm Me ", " Confirm Me"]
    )
    async def test_wrong_name_refuses(
        self, db_session, no_scheduler_registry, wrong
    ):
        user = await _make_user(db_session, "wp59_confirm")
        pid = await _make_project(db_session, user, "Confirm Me")

        svc = ProjectDeletionService(db_session)
        try:
            with pytest.raises(ConfirmationMismatchError):
                await svc.delete(pid, confirmation_name=wrong,
                                 actor_id=user.id, actor_name=user.username)
        finally:
            await svc.close()

        still = await db_session.execute(
            text("SELECT count(*) FROM projects WHERE id = :p"), {"p": pid})
        assert still.scalar() == 1


# ---------------------------------------------------------------------------
# Task 4 — the library and the shared bytes SURVIVE
# ---------------------------------------------------------------------------

class TestSharedBytesSurvive:
    async def test_library_asset_and_shared_object_survive_a_deletion(
        self, db_session, no_scheduler_registry, record_purges
    ):
        """The Task 4 acceptance test, both conditions in one deletion.

        Constructed:
          * `victim` and `survivor`, two projects.
          * ONE library asset, referenced into BOTH -- which is what
            `LibraryService.reference_into_project` does: it copies the
            library row's fid and path onto a new `assets` row
            (library_service.py:370-371), so two rows point at one object.
          * A second object shared by an `assets` row in each project, with no
            library row behind it -- the shape a cross-project reference takes
            if one is ever created outside the library path.
          * One object owned by `victim` alone, which SHOULD be purged, so the
            test proves the guard is selective rather than simply inert.
        """
        user = await _make_user(db_session, "wp59_share")
        victim = await _make_project(db_session, user, "Victim")
        survivor = await _make_project(db_session, user, "Survivor")

        lib_id = await _make_library_asset(
            db_session, user, fid="fid-library", path="/ivgs/library/logo.png")

        # (a) library reference in both projects
        await _make_asset(db_session, victim, fid="fid-library",
                          path="/ivgs/library/logo.png", library_asset_id=lib_id)
        survivor_lib_ref = await _make_asset(
            db_session, survivor, fid="fid-library",
            path="/ivgs/library/logo.png", library_asset_id=lib_id)

        # (b) a plain shared object, no library row
        await _make_asset(db_session, victim, fid="fid-shared",
                          path="/ivgs/images/shared.png")
        survivor_shared = await _make_asset(
            db_session, survivor, fid="fid-shared",
            path="/ivgs/images/shared.png")

        # (c) victim's own object -- must be purged
        await _make_asset(db_session, victim, fid="fid-victim-only",
                          path="/ivgs/images/victim.png")

        svc = ProjectDeletionService(db_session)
        try:
            result = await svc.delete(
                victim, confirmation_name="Victim",
                actor_id=user.id, actor_name=user.username,
            )
        finally:
            await svc.close()

        # --- The guard was selective, not blanket ---
        assert record_purges == ["fid-victim-only"], (
            f"purge deleted {record_purges}; it must delete ONLY the object no "
            f"surviving row and no library row points at."
        )
        assert result.files_deleted == 1
        assert result.files_preserved == 2
        reasons = {r["fid"]: r["reason"] for r in result.preserved_reasons}
        assert reasons["fid-library"] == "library_asset"
        assert reasons["fid-shared"] == "referenced_by_another_project"

        # --- The library row itself is untouched. WP-59 Task 4(a): this package
        # never writes to library_assets at all.
        lib_rows = await db_session.execute(
            text("SELECT count(*) FROM library_assets WHERE id = :l"),
            {"l": lib_id})
        assert lib_rows.scalar() == 1

        # --- The surviving references still resolve to the same object ---
        surviving = (await db_session.execute(
            text("SELECT id::text, seaweedfs_fid, seaweedfs_path, "
                 "       library_asset_id::text "
                 "FROM assets WHERE project_id = :p ORDER BY seaweedfs_fid"),
            {"p": survivor})).fetchall()
        by_id = {r[0]: r for r in surviving}
        assert by_id[str(survivor_lib_ref)][1] == "fid-library"
        assert by_id[str(survivor_lib_ref)][3] == str(lib_id)
        assert by_id[str(survivor_shared)][1] == "fid-shared"

        # --- And the victim's rows are gone ---
        left = await db_session.execute(
            text("SELECT count(*) FROM assets WHERE project_id = :p"),
            {"p": victim})
        assert left.scalar() == 0

    async def test_dedup_within_a_project_is_one_row_not_two(self, db_session):
        """The sharing mechanism, pinned as it actually is.

        Content-hash dedup is PROJECT-SCOPED at both ends: the worker probe
        passes `project_id` (media_converter.py, all four call sites) and the
        upload's dedup query filters `Asset.project_id == project_id`
        (asset_service.py:298-303). So a dedup hit increments
        `reference_count` on ONE row inside ONE project -- it never creates a
        row in another project.

        This test pins that reading of the code, because Task 4(b)'s whole
        argument rests on it: if dedup were global, deleting a project could
        remove a row another project's scene still pointed at, and the guard
        would need to be somewhere else entirely.
        """
        from app.services.asset_service import AssetService
        import inspect

        source = inspect.getsource(AssetService.upload_asset)
        assert "Asset.project_id == project_id" in source, (
            "upload_asset's dedup query is no longer project-scoped. WP-59 "
            "Task 4(b)'s guard assumes it is; re-derive the sharing mechanism "
            "before trusting the purge."
        )


# ---------------------------------------------------------------------------
# Task 2 — the audit record, and convergence
# ---------------------------------------------------------------------------

class TestAuditAndIdempotency:
    async def test_audit_row_is_written_before_destruction_and_survives(
        self, db_session, no_scheduler_registry, record_purges, redis_scan_empty
    ):
        user = await _make_user(db_session, "wp59_audit")
        pid = await _make_project(db_session, user, "Audited")
        await _make_asset(db_session, pid, fid="fid-a", path="/ivgs/images/a.png")
        await _make_job(db_session, pid, status="success")

        svc = ProjectDeletionService(db_session)
        try:
            result = await svc.delete(
                pid, confirmation_name="Audited",
                actor_id=user.id, actor_name=user.username,
            )
        finally:
            await svc.close()

        row = (await db_session.execute(
            text("SELECT action_type, resource_id::text, before_payload, "
                 "       after_payload FROM audit_log WHERE id = :i"),
            {"i": uuid.UUID(result.audit_id)})).fetchone()

        assert row is not None, "the audit row did not survive the deletion"
        assert row[0] == "PROJECT_DELETE_COMPLETED"
        assert row[1] == str(pid)

        before = row[2]
        assert before["project_name"] == "Audited"
        assert before["requested_by"] == user.username
        # The per-category counts the operator was shown, kept verbatim.
        assert set(before["categories"]) == set(CATEGORY_KEYS)
        assert before["categories"]["assets"] == 1
        assert before["categories"]["render_jobs"] == 1
        # The resume manifest, which is what makes step 6 restartable.
        assert before["binary_manifest"][0]["fid"] == "fid-a"

        after = row[3]
        assert after["purge_state"] == "complete"
        assert after["files_deleted"] == 1

    async def test_unreachable_redis_is_recorded_not_silent(
        self, db_session, no_scheduler_registry, record_purges
    ):
        """A scratch-key purge that could not run says so in the audit row.

        No `redis_scan_empty` here: this test wants the real failure. The
        deletion must still COMPLETE -- the rows are already gone and raising
        would leave the audit row saying "pending" forever -- but it must not
        report a clean purge it did not perform. `purge_state` carries the
        difference, which is the whole WP-00 swallowed-failures rule applied to
        a step that genuinely should not abort.
        """
        user = await _make_user(db_session, "wp59_redis_down")
        pid = await _make_project(db_session, user, "Redis Down")
        await _make_job(db_session, pid, status="success")

        svc = ProjectDeletionService(db_session)
        try:
            result = await svc.delete(
                pid, confirmation_name="Redis Down",
                actor_id=user.id, actor_name=user.username)
        finally:
            await svc.close()

        after = (await db_session.execute(
            text("SELECT after_payload FROM audit_log WHERE id = :i"),
            {"i": uuid.UUID(result.audit_id)})).scalar()
        assert after["purge_state"] == "redis_incomplete"
        assert after["redis_purge_error"]

        # The deletion itself still happened. A recorded partial failure in a
        # post-destruction step must not be read as "nothing was deleted".
        gone = await db_session.execute(
            text("SELECT count(*) FROM projects WHERE id = :p"), {"p": pid})
        assert gone.scalar() == 0

    async def test_deleting_twice_converges(
        self, db_session, no_scheduler_registry, record_purges
    ):
        """Task 2: running delete twice reaches the same end state.

        The second call finds no project and no unfinished purge, and says so
        as ALREADY DELETED with the audit id -- which is different from "no such
        project", because the system does in fact remember destroying it.
        """
        user = await _make_user(db_session, "wp59_twice")
        pid = await _make_project(db_session, user, "Twice")

        svc = ProjectDeletionService(db_session)
        try:
            first = await svc.delete(
                pid, confirmation_name="Twice",
                actor_id=user.id, actor_name=user.username)
            with pytest.raises(AlreadyDeletedError) as exc:
                await svc.delete(
                    pid, confirmation_name="Twice",
                    actor_id=user.id, actor_name=user.username)
        finally:
            await svc.close()

        assert exc.value.audit_id == first.audit_id

    async def test_interrupted_purge_is_resumed_from_the_audit_row(
        self, db_session, no_scheduler_registry, record_purges
    ):
        """The crash case the ordering was designed for.

        Simulated by writing the audit row and deleting the project rows, then
        stopping -- which is exactly the state a process killed between step 5
        and step 6 leaves. The project row is gone, so nothing in the database
        can say what objects it owned except the audit row's manifest.
        """
        user = await _make_user(db_session, "wp59_resume")
        pid = await _make_project(db_session, user, "Interrupted")
        audit_id = uuid.uuid4()

        import json
        await db_session.execute(
            text(
                "INSERT INTO audit_log (id, user_id, action_type, resource_type, "
                "  resource_id, before_payload, timestamp) "
                "VALUES (:i, :u, 'PROJECT_DELETE_STARTED', 'project', :r, "
                "        CAST(:p AS jsonb), now())"
            ),
            {"i": audit_id, "u": user.id, "r": pid, "p": json.dumps({
                "project_name": "Interrupted",
                "job_ids": [],
                "binary_manifest": [
                    {"fid": "fid-stranded", "path": "/ivgs/images/s.png",
                     "size_bytes": 10, "keep_reason": ""},
                ],
                "purge_state": "pending",
            })},
        )
        await db_session.execute(
            text("DELETE FROM projects WHERE id = :p"), {"p": pid})
        await db_session.commit()

        svc = ProjectDeletionService(db_session)
        try:
            result = await svc.delete(
                pid, confirmation_name="Interrupted",
                actor_id=user.id, actor_name=user.username)
        finally:
            await svc.close()

        assert result.resumed is True
        assert record_purges == ["fid-stranded"], (
            "the stranded object was not purged from the audit manifest; a "
            "crash between the row deletion and the purge would leave it "
            "orphaned forever."
        )
        state = (await db_session.execute(
            text("SELECT action_type, after_payload->>'purge_state' "
                 "FROM audit_log WHERE id = :i"), {"i": audit_id})).fetchone()
        assert state[0] == "PROJECT_DELETE_COMPLETED"
        assert state[1] == "complete"


# ---------------------------------------------------------------------------
# Task 2 — DELETING is terminal
# ---------------------------------------------------------------------------

class TestDeletingState:
    async def test_deleting_is_in_no_transition_set(self):
        """Nothing may transition into or out of DELETING.

        It is not a lifecycle state; it is a marker meaning destruction has
        begun. If it ever appears in a value set, a half-deleted project could
        be nursed back into a pipeline.
        """
        from shared.models.enums import PROJECT_STATE_TRANSITIONS, ProjectState

        assert ProjectState.DELETING not in PROJECT_STATE_TRANSITIONS, (
            "DELETING has been given outgoing transitions"
        )
        for source, targets in PROJECT_STATE_TRANSITIONS.items():
            assert ProjectState.DELETING not in targets, (
                f"{source.value} can transition into DELETING through the state "
                f"machine; only the deletion service may write it."
            )

    async def test_the_enum_label_exists_in_the_database(self, db_session):
        """Migration 0033 is applied to whatever database this suite points at."""
        labels = (await db_session.execute(
            text("SELECT unnest(enum_range(NULL::project_state))::text")
        )).scalars().all()
        assert "DELETING" in labels, (
            "project_state has no DELETING label -- run `alembic upgrade head` "
            "against the test database (migration 0033)."
        )
