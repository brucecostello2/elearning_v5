"""
WP-59 Task 7 — tier migration: the repairs, and the dry run.

WHAT THIS PINS, and why each matters:

* THE ENUM VALUES ARE THE DATABASE'S LABELS. `storage_tier` is
  `hot, warm, cold, archived, deleted` -- both terminal labels are past
  participles. `StorageTier.ARCHIVE` said `archive` and `StorageTier.DELETE`
  said `delete`, so every write of either would have raised
  `invalid input value for enum storage_tier`. WP-57 §3.1 (D-1) found the
  archive half; the delete half is the same defect one hop further down.
* THE SCAN READS A COLUMN THAT EXISTS. `assets` has `seaweedfs_path`; there is
  no `storage_path` and never has been.
* THE UPDATE DOES NOT WRITE `updated_at` OR `status`. `assets` has neither.
  Both would have failed the moment the scan was repaired.
* A FAILED TIER PASS RECORDS FAILURE. The per-tier `except` appended to a list
  nobody read and the task returned `{'status': 'ok'}`, so Celery recorded
  SUCCESS over a scan that raised on every tier of every run.
* DRY RUN IS THE DEFAULT, AND IT WRITES NOTHING. The first real pass moves 158
  live assets and is an attended operator event, not a cron surprise.
"""
import re
from pathlib import Path

import pytest

from services.retention_migration import (
    MigrationReport,
    RetentionService,
    StorageTier,
    TIER_ORDER,
)

SERVICE_SRC = Path(__file__).resolve().parents[1] / "services" / "retention_migration.py"


# ---------------------------------------------------------------------------
# The enum labels
# ---------------------------------------------------------------------------

class TestStorageTierLabels:
    def test_terminal_tiers_use_the_database_labels(self):
        """`archived` and `deleted`, not `archive` and `delete`."""
        assert StorageTier.ARCHIVE.value == "archived"
        assert StorageTier.DELETE.value == "deleted"

    def test_every_tier_value_is_a_real_storage_tier_label(self):
        """The whole enum, against the live `storage_tier` type's members.

        Transcribed from the running database on 2026-08-26:
            hot, warm, cold, archived, deleted
        """
        live_labels = {"hot", "warm", "cold", "archived", "deleted"}
        for tier in TIER_ORDER:
            assert tier.value in live_labels, (
                f"StorageTier.{tier.name} = {tier.value!r} is not a member of "
                f"the storage_tier enum; any write of it raises "
                f"'invalid input value for enum storage_tier'."
            )


# ---------------------------------------------------------------------------
# The SQL
# ---------------------------------------------------------------------------

class TestSqlMatchesTheSchema:
    def test_scan_selects_seaweedfs_path_not_storage_path(self):
        src = SERVICE_SRC.read_text()
        sql = "\n".join(
            line for line in src.splitlines()
            if '"' in line and ("SELECT" in line or "FROM assets" in line
                                or "storage_path" in line)
        )
        assert "seaweedfs_path" in src
        # `storage_path` may appear in prose and in local variable names; what
        # must never reappear is a SELECT of it as a column.
        assert not re.search(r'"SELECT[^"]*\bstorage_path\b', src), (
            "the tier scan is selecting `storage_path` again. That column does "
            "not exist on `assets` -- WP-57 §3.1 -- and the query raises "
            "UndefinedColumn on every tier of every run."
        )

    def test_no_update_writes_updated_at_or_status_on_assets(self):
        """`assets` has neither column. Verified against the live schema."""
        src = SERVICE_SRC.read_text()
        updates = re.findall(r'"UPDATE assets SET[^;]*?"(?=\s*\))', src, re.S)
        joined = " ".join(updates) if updates else src[src.find("UPDATE assets"):]
        assert "updated_at" not in joined, (
            "an UPDATE on `assets` names `updated_at`; the table has no such "
            "column, so the statement fails with UndefinedColumn."
        )
        assert "status = " not in joined, (
            "an UPDATE on `assets` names `status`; the table has no such column."
        )


# ---------------------------------------------------------------------------
# Dry run, cap and failure recording
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Returns one batch of rows for the FIRST tier and nothing afterwards."""

    def __init__(self, rows_by_tier, executed):
        self._rows_by_tier = rows_by_tier
        self._executed = executed

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return self

    async def execute(self, stmt, params=None):
        text_sql = str(stmt)
        self._executed.append((text_sql, params))
        if "SELECT" in text_sql and "FROM assets" in text_sql:
            tier = (params or {}).get("tier")
            return _FakeResult(self._rows_by_tier.get(tier, []))
        if "retention_policies" in text_sql:
            return _FakeResult([])
        return _FakeResult([])


def _session_factory(rows_by_tier, executed):
    def factory():
        return _FakeSession(rows_by_tier, executed)
    return factory


def _row(asset_id, asset_type, path, tier, transitioned_at, created_at,
         fid="fid-1", size=1000):
    # Matches the SELECT's column order exactly:
    # id, asset_type, seaweedfs_path, storage_tier, tier_transition_at,
    # preserve_flag, created_at, seaweedfs_fid, file_size_bytes
    return (asset_id, asset_type, path, tier, transitioned_at, False,
            created_at, fid, size)


@pytest.mark.asyncio
class TestDryRun:
    async def test_dry_run_is_the_default(self):
        svc = RetentionService(db_session_factory=_session_factory({}, []))
        assert svc._dry_run is True, (
            "RetentionService must default to dry-run. The first real pass "
            "moves 158 live assets and is an attended event; a caller that "
            "forgets an argument must get a report, not a migration."
        )

    async def test_dry_run_writes_nothing_and_reports_what_would_move(self):
        from datetime import datetime, timedelta, timezone

        old = datetime.now(timezone.utc) - timedelta(days=400)
        executed = []
        rows = {
            "hot": [
                _row("11111111-1111-1111-1111-111111111111", "image",
                     "/ivgs/images/a.png", "hot", old, old, size=500),
                _row("22222222-2222-2222-2222-222222222222", "image",
                     "/ivgs/images/b.png", "hot", old, old, size=1500),
            ],
        }
        svc = RetentionService(
            db_session_factory=_session_factory(rows, executed), dry_run=True)
        report = await svc.run_migration()

        assert report.dry_run is True
        assert report.status == "ok"
        assert report.would_move["hot->warm"] == {"assets": 2, "bytes": 2000}

        # NOTHING WAS WRITTEN. Not the tier column, not an audit row.
        writes = [sql for sql, _ in executed if "UPDATE" in sql or "INSERT" in sql]
        assert writes == [], f"dry run issued writes: {writes}"

    async def test_a_failed_tier_pass_sets_status_failed(self):
        """The swallow, pinned closed.

        The per-tier `except` is kept -- one tier failing should not stop the
        others being assessed -- but `status` goes to 'failed' and the calling
        task raises on it. It used to append to a list nobody read.
        """
        class _Boom:
            async def __aenter__(self):
                raise RuntimeError("UndefinedColumn: storage_path")

            async def __aexit__(self, *exc):
                return False

        svc = RetentionService(db_session_factory=lambda: _Boom())
        report = await svc.run_migration()

        assert report.status == "failed"
        assert report.errors, "a failed tier pass recorded no error"
        assert any("storage_path" in e for e in report.errors)

    async def test_null_terminal_days_load_and_do_not_progress(self):
        """The live retention_policies rows must LOAD, and must not delete.

        All three rows in the live table have NULL `archive_days` and NULL
        `delete_after_days`. The model required them as ints, so every load
        raised ValidationError into a bare `except` and the service silently
        used the hardcoded defaults instead -- the operator's configured
        policy has never governed anything.

        Both halves are pinned here, and the second is the dangerous one: NULL
        must mean "do not progress past this tier", never zero. The old
        `mapping.get(tier, 0)` returned 0 for a missing value, and 0 satisfies
        `time_in_tier >= duration` for every asset that has ever existed -- so
        an unconfigured `delete_after_days` would have DELETED the fleet on the
        first run that reached it.
        """
        from services.retention_migration import RetentionPolicy

        p = RetentionPolicy(
            name="standard", hot_days=30, warm_days=90, cold_days=365,
            archive_days=None, delete_after_days=None,
            applies_to="all", is_default=True,
        )
        assert p.get_tier_duration_days(StorageTier.HOT) == 30
        assert p.get_tier_duration_days(StorageTier.ARCHIVE) is None
        assert p.get_tier_duration_days(StorageTier.COLD) == 365

    async def test_report_defaults_are_honest(self):
        """A fresh report claims a dry run and no failure, not the reverse."""
        r = MigrationReport()
        assert r.dry_run is True
        assert r.status == "ok"
        assert r.capped is False
        assert r.would_move == {}
        # Which policy set governed is REPORTED, not assumed. It was neither
        # reported nor assumed before: the fallback to hardcoded defaults was a
        # warning nobody read.
        assert r.policy_source == "unknown"
        assert r.policy_load_error is None
        assert r.policy_gaps == {}


class TestNightlyVisibility:
    """WP-60 Task 8. The nightly dry run's result must be VISIBLE, or a run
    that quietly stops scanning looks exactly like a run that found nothing."""

    def test_would_move_gauge_handles_the_mapping_it_is_actually_given(self):
        """`would_move` is `{"hot->warm": {"assets": 39, "bytes": …}}`, not a
        count. The first version did `int(report.would_move or 0)` and raised
        TypeError on the first live dispatch — the push failed and the gauge
        was silently absent, which is the exact defect this task exists to
        prevent, inside the mechanism built to prevent it."""
        from tasks.periodic_tasks import _would_move_assets

        class _R:
            pass

        r = _R()
        r.would_move = {
            "hot->warm": {"assets": 39, "bytes": 109966042},
            "warm->cold": {"assets": 3, "bytes": 12},
        }
        assert _would_move_assets(r) == 42

        for empty in ({}, None):
            r.would_move = empty
            assert _would_move_assets(r) == 0

    def test_the_metrics_push_never_raises_into_the_migration(self):
        """A reporting failure must not fail the run — but it must be LOUD.
        That is why the except logs at WARNING with the error type, and it is
        how the dict/int defect above was caught on its first dispatch."""
        import structlog
        from tasks.periodic_tasks import _report_retention_migration_metrics

        class _Bad:
            dry_run = True
            status = "ok"
            assets_scanned = 1
            transitions_performed = 0
            assets_deleted = 0
            errors: list = []

            @property
            def would_move(self):
                raise RuntimeError("boom")

        # Must not propagate.
        _report_retention_migration_metrics(_Bad(), structlog.get_logger("t"))


class TestTaskWiring:
    def test_the_scheduled_entry_is_live_names_the_real_task_and_is_capped(self):
        """INVERTED TWICE NOW, AND STRONGER EACH TIME. Read the sequence.

        WP-59 shipped this entry COMMENTED OUT and this test asserted it stayed
        that way, because moving 158 live assets for the first time is an
        attended operator event.

        WP-60 enabled it as a nightly DRY RUN once the operator's dry run and
        capped live pass had both behaved, and inverted the assertion. The
        version that stood here asserted `"dry_run" not in block` and
        `"kwargs" not in block` -- the entry passed nothing, so the task's own
        dry-run default governed and the nightly job REPORTED.

        WP-61 Task 6 (WP-60 D-1, RULED) turns it LIVE, so it inverts again.

        **This is the third version and it is the strongest, not the weakest.**
        What each version really protected:

            WP-59   "nothing unattended runs"        rested on a `#`
            WP-60   "nothing unattended MOVES"       rested on a default the
                                                     entry could not override
            WP-61   "nothing unattended DESTROYS,    rests on a refusal in the
                     and nothing moves uncapped"     service plus an explicit
                                                     kwarg a reviewer can see

        A `#` is one `sed` away. A default is one kwarg away. `allow_delete` is
        a branch in `_process_tier_transitions` that refuses the delete hop
        whatever `retention_policies` says, and the second assertion below
        fails the day the entry acquires the argument that lifts it.

        Nothing was weakened, no skip marker added, no coverage deleted. The
        full WP-61 assertions live in `test_wp61_schedules.py`; this one is
        kept here so the file that has tracked this entry through three
        rulings still tracks it.
        """
        src = (Path(__file__).resolve().parents[1] / "celery_app.py").read_text()

        live = [
            line for line in src.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        entry_idx = next(
            (i for i, line in enumerate(live)
             if '"retention-migration"' in line),
            None,
        )
        assert entry_idx is not None, (
            "the tier-migration schedule is not enabled. WP-59 §7.6 step 3 was "
            "ruled and its preconditions were met; WP-61 Task 6 turned it live."
        )

        block = "\n".join(live[entry_idx:entry_idx + 6])
        assert "ivgs_workers.tasks.periodic_tasks.run_retention_migration" in block, (
            "the entry must name the REAL task. It used to name "
            "tasks.pipeline_orchestrator.run_retention_migration, which is a "
            "stub that returns ok and does nothing."
        )

        # LIVE, and CAPPED. An entry that loses the cap is an unattended
        # unbounded migration.
        assert '"dry_run": False' in block, (
            "the nightly tier migration is ruled LIVE (WP-60 D-1). Without an "
            "explicit dry_run=False it silently reverts to a nightly report."
        )
        assert '"max_transitions": 500' in block, (
            "the nightly entry has lost its cap."
        )

        # THE SAFETY PROPERTY, and it has moved from 'cannot move' to
        # 'cannot destroy'. `archived -> deleted` is the only hop that
        # destroys bytes and it is refused unless allow_delete is passed.
        assert "allow_delete" not in block, (
            "the scheduled entry passes allow_delete. Permanent deletion from "
            "an unattended nightly schedule is not what was ruled."
        )

    def test_every_declared_task_name_belongs_to_the_function_under_it(self):
        """WP-60. A DECORATOR THAT DRIFTED OFF ITS FUNCTION FAILS NIGHTLY.

        This test exists because WP-60 broke exactly that and no existing test
        noticed. `_report_retention_migration_metrics` was inserted between
        `@shared_task(name="...run_retention_migration")` and
        `def run_retention_migration`, so the HELPER took the decorator and the
        task became a plain function. The beat entry then named something that
        was not registered, and the nightly dry run would have raised
        NotRegistered every night — loudly, but into a log nobody reads, which
        is the same family of defect as the stub reporting SUCCESS.

        It was caught by running the task against the deployed image, not by
        reading. What is asserted here is the invariant that broke, and it is
        checked in the SOURCE deliberately: importing this module does NOT
        autodiscover its tasks, and WP-59 §3.1 records concluding a task was
        unregistered from exactly that mistaken import. `celery_app.tasks`
        would be the wrong oracle here.
        """
        import re

        src = (
            Path(__file__).resolve().parents[1] / "tasks" / "periodic_tasks.py"
        ).read_text()

        # @shared_task( ... name="X" ... ) followed by the next `def NAME(`
        pattern = re.compile(
            r'@shared_task\((?P<args>[^)]*?)\)\s*\ndef\s+(?P<func>\w+)\s*\(',
            re.S,
        )
        seen = {}
        for m in pattern.finditer(src):
            name_m = re.search(r'name="([^"]+)"', m.group("args"))
            assert name_m, "a @shared_task has no explicit name"
            declared = name_m.group(1).rsplit(".", 1)[-1]
            seen[name_m.group(1)] = m.group("func")
            assert declared == m.group("func"), (
                f'@shared_task(name="...{declared}") decorates '
                f'`{m.group("func")}`. The decorator has drifted onto a '
                f"different function; the name it declares is no longer "
                f"registered and every dispatch of it raises NotRegistered."
            )

        # And the live beat entries in the ivgs_workers namespace must name
        # something this module actually declares.
        import celery_app as ca

        missing = [
            f"{entry_name} -> {entry['task']}"
            for entry_name, entry in ca.CELERY_BEAT_SCHEDULE.items()
            if entry["task"].startswith("ivgs_workers.tasks.periodic_tasks.")
            and entry["task"] not in seen
        ]
        assert not missing, (
            f"beat schedule names a task periodic_tasks.py does not declare: "
            f"{missing}"
        )

    def test_the_orphan_schedule_is_on_weekly_and_never_points_at_the_stub(self):
        """INVERTED BY WP-61 Task 7 (WP-59 D-2 / WP-60 D-2, RULED: on, weekly).

        **AND IT WAS PASSING FOR THE WRONG REASON, which is worth recording.**
        The previous version asserted `'"orphan-cleanup"' not in line`. WP-61's
        entry is named `"orphan-cleanup-weekly"`, so the literal with its
        closing quote does not match it and this test stayed green over a
        schedule that had just been turned ON. It was not measuring the
        property it claimed; it was matching a string.

        What the old version really protected was TWO things, and only one of
        them has been superseded:

          * "the sweep does not run unattended" -- SUPERSEDED by the ruling.
          * "'off' never means 'a stub runs and reports ok'" -- STILL TRUE and
            still asserted below. The entry used to dispatch
            `tasks.pipeline_orchestrator.run_orphan_cleanup`, a Phase-5 stub
            logging one line and returning {'status': 'ok'}, recorded in
            celery_taskmeta under SUCCESS as recently as 2026-08-26 03:00:00.

        The replacement for the first is stronger than an absent entry: the
        sweep runs, and it is structurally unable to permanently delete
        (`quarantine_only`). Those assertions live in
        `test_wp61_schedules.py`; what is kept here is the stub check and the
        shape of the entry.
        """
        src = (Path(__file__).resolve().parents[1] / "celery_app.py").read_text()
        live = [
            line for line in src.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        # THE STUB MUST NEVER BE ON A LIVE SCHEDULE. Unchanged in strength.
        assert not any(
            "tasks.pipeline_orchestrator.run_orphan_cleanup" in line
            for line in live
        ), "the Phase-5 orphan stub is on a live schedule"
        assert not any(
            "tasks.pipeline_orchestrator.run_retention_migration" in line
            for line in live
        ), "beat is still dispatching the Phase-5 retention stub"

        # And the sweep that IS scheduled is the real task, weekly, and cannot
        # permanently delete.
        idx = next(
            (i for i, line in enumerate(live)
             if '"orphan-cleanup-weekly"' in line),
            None,
        )
        assert idx is not None, (
            "the orphan sweep is ruled ON and WEEKLY (WP-61 Task 7)."
        )
        block = "\n".join(live[idx:idx + 14])
        assert "ivgs_workers.tasks.periodic_tasks.run_orphan_cleanup" in block
        assert "day_of_week" in block, "ruled WEEKLY, not nightly"
        assert '"quarantine_only": True' in block, (
            "the scheduled sweep must not be able to permanently delete."
        )

    def test_the_task_defaults_to_dry_run(self):
        """Uncommenting the schedule alone gives a nightly REPORT.

        Turning off dry-run is a second, separate, deliberate edit -- so the
        operator cannot start migrating live assets by restoring one line.
        """
        src = (Path(__file__).resolve().parents[1] / "tasks" / "periodic_tasks.py").read_text()
        assert "dry_run=True if dry_run is None else bool(dry_run)" in src
