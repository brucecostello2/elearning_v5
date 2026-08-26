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


class TestTaskWiring:
    def test_the_scheduled_entry_is_live_names_the_real_task_and_is_a_dry_run(self):
        """UPDATED BY WP-60 Task 8, AND STRICTLY STRONGER THAN BEFORE.

        WP-59 shipped this entry commented out and this test asserted it stayed
        that way, because moving 158 live assets for the first time is an
        attended operator event. Both of WP-59 §7.6's preconditions have since
        been met by the operator: a dry run scanning 161 with would_move 44 and
        zero errors, then a capped live pass moving exactly 5 with all 5 fids
        still serving HTTP 200. Step 3 -- enable the schedule -- was ruled, and
        WP-60 Task 8 executes it.

        So the assertion INVERTS, and this is not a relaxation. What the
        previous version really protected was "no unattended tier migration",
        and that property is now guaranteed by something better than a comment:
        `run_retention_migration` defaults `dry_run` to the service default
        (True), and this entry passes NO kwargs. The nightly job REPORTS; it
        does not move an asset.

        The test therefore pins the property rather than the comment, and the
        third assertion below is the one that matters -- an entry that acquires
        `"kwargs": {"dry_run": False}` turns a nightly report into a nightly
        migration, and that must never happen by accident.
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
            "ruled and its preconditions were met; the nightly DRY RUN is the "
            "visibility that stops this mechanism going quiet again."
        )

        block = "\n".join(live[entry_idx:entry_idx + 5])
        assert "ivgs_workers.tasks.periodic_tasks.run_retention_migration" in block, (
            "the entry must name the REAL task. It used to name "
            "tasks.pipeline_orchestrator.run_retention_migration, which is a "
            "stub that returns ok and does nothing."
        )

        # THE SAFETY PROPERTY. No kwargs at all -> the task's own default
        # (dry_run=True) governs. Turning live migration on is a separate,
        # deliberate edit and a future ruling.
        assert "dry_run" not in block, (
            "the scheduled entry passes a dry_run kwarg. The nightly job must "
            "inherit the task default (True). Turning off dry-run on a "
            "schedule is a FUTURE ruling, not this one."
        )
        assert "kwargs" not in block, (
            "the scheduled entry passes kwargs. It must pass none, so the "
            "dry-run default cannot be overridden here by accident."
        )

    def test_the_orphan_schedule_is_off_and_not_merely_pointed_at_a_stub(self):
        """WP-60 Task 10 (WP-59 D-2). "Off" must mean nothing runs.

        The orphan-cleanup entry was not off: it dispatched
        `tasks.pipeline_orchestrator.run_orphan_cleanup` nightly at 03:00, a
        Phase-5 stub that logs one line and returns {'status': 'ok'} --
        recorded in celery_taskmeta under SUCCESS as recently as
        2026-08-26 03:00:00. A schedule running a stub that reports health it
        does not have is the defect, not the safeguard.
        """
        src = (Path(__file__).resolve().parents[1] / "celery_app.py").read_text()
        live = [
            line for line in src.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert not any('"orphan-cleanup"' in line for line in live), (
            "the orphan-cleanup schedule is enabled. The ruling is that it "
            "stays off until a future one turns it on - and it must not be "
            "left pointing at the stub either, which is what 'off' used to mean"
        )
        assert not any(
            "tasks.pipeline_orchestrator.run_orphan_cleanup" in line
            for line in live
        ), "the stub is still on a live schedule"

        # And the STUB must not be on the live schedule either.
        assert not any(
            "tasks.pipeline_orchestrator.run_retention_migration" in line
            for line in live
        ), "beat is still dispatching the Phase-5 retention stub"

    def test_the_task_defaults_to_dry_run(self):
        """Uncommenting the schedule alone gives a nightly REPORT.

        Turning off dry-run is a second, separate, deliberate edit -- so the
        operator cannot start migrating live assets by restoring one line.
        """
        src = (Path(__file__).resolve().parents[1] / "tasks" / "periodic_tasks.py").read_text()
        assert "dry_run=True if dry_run is None else bool(dry_run)" in src
