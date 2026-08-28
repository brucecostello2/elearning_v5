"""
WP-61 Tasks 6 and 7 — the two schedules that were ruled ON, and what stops
them going further than they were told to.

THE ASSERTIONS INVERT AGAIN, AND THEY GET STRONGER AGAIN.

WP-59 shipped both entries off and pinned that they stayed off. WP-60 enabled
the tier migration as a nightly DRY RUN and inverted that assertion, pinning
the property (`no kwargs` -> the task's dry-run default governs) rather than a
comment character. WP-61 turns the migration LIVE and the orphan sweep ON, so
both assertions invert once more.

**What must not happen is the assertions getting weaker each time.** The
protection each version really provided:

    WP-59  "nothing unattended runs"        a `#`
    WP-60  "nothing unattended MOVES"       a default the entry cannot override
    WP-61  "nothing unattended DESTROYS"    a code path that refuses, plus an
                                            explicit kwarg on the entry that a
                                            reviewer can see

Each is a stronger guarantee than the one before it, because each rests on
something harder to undo by accident. A `#` is one `sed` away. A default is one
kwarg away. `allow_delete` and `quarantine_only` are refusals in the service,
and the tests below fail if the schedule ever acquires the argument that lifts
them.

THE ONE THING THAT IS NOT ALLOWED TO CHANGE: neither task may become able to
delete by OMISSION. Both still default to the safe value; the schedules pass
their arguments explicitly so the choice is visible in the diff.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.orphan_cleanup import OrphanCleanupService
from services.retention_migration import (
    RetentionPolicy,
    RetentionService,
    StorageTier,
)

CELERY_APP_SRC = (Path(__file__).resolve().parents[1] / "celery_app.py")
PERIODIC_SRC = (
    Path(__file__).resolve().parents[1] / "tasks" / "periodic_tasks.py"
)


def _live_lines(path: Path) -> list[str]:
    """Source lines that are neither blank nor comments.

    A schedule that is "enabled" inside a comment block is the defect WP-60
    Task 10 found: the orphan entry was not off, it was pointing at a stub.
    """
    return [
        line for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """One batch of rows per tier, and a record of every statement issued.

    Restated here rather than imported from `test_wp59_retention`: pytest runs
    with `--import-mode=importlib`, which does not put a test file's directory
    on `sys.path`, and a cross-module test import is ledger P2.51 -- the cause
    of all 15 errors in `test_quality_gate.py`. Adding a sixteenth is not a
    trade worth making to save twenty lines.
    """

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
        sql = str(stmt)
        self._executed.append((sql, params))
        if "SELECT" in sql and "FROM assets" in sql:
            return _FakeResult(self._rows_by_tier.get((params or {}).get("tier"), []))
        return _FakeResult([])

    async def commit(self):
        return None


def _session_factory(rows_by_tier, executed):
    def factory():
        return _FakeSession(rows_by_tier, executed)
    return factory


def _entry_block(name: str, span: int = 10) -> str:
    live = _live_lines(CELERY_APP_SRC)
    idx = next((i for i, l in enumerate(live) if f'"{name}"' in l), None)
    assert idx is not None, f"beat entry {name!r} is not enabled"
    return "\n".join(live[idx:idx + span])


# ---------------------------------------------------------------------------
# TASK 6 — the nightly tier migration is LIVE
# ---------------------------------------------------------------------------

class TestTierMigrationScheduleIsLive:
    def test_the_entry_is_live_capped_and_names_the_real_task(self):
        """INVERTED FROM WP-60, AND STRICTLY STRONGER.

        WP-60's version asserted `"dry_run" not in block` and `"kwargs" not in
        block`, because the nightly job was a report. The ruling's
        preconditions were met -- a dry run reporting 44 would-move with zero
        errors, then a capped live pass moving exactly 5 with all 5 fids still
        serving HTTP 200 -- so the nightly job now migrates.

        The old assertion protected "no unattended MOVE". This one protects
        "no unattended UNCAPPED move and no unattended DELETE", which is a
        stronger property: an entry that drops `max_transitions` fails here,
        and an entry that acquires `allow_delete` fails here.
        """
        block = _entry_block("retention-migration")

        assert (
            "ivgs_workers.tasks.periodic_tasks.run_retention_migration" in block
        ), "the entry must name the REAL task, not the Phase-5 stub."
        assert '"dry_run": False' in block, (
            "the nightly tier migration is ruled LIVE. An entry without an "
            "explicit dry_run=False inherits the task default (True) and "
            "silently reverts to a nightly report."
        )
        assert '"max_transitions": 500' in block, (
            "the nightly entry has lost its cap. Nobody is watching this run. "
            "A migration that suddenly finds thousands eligible -- a policy "
            "edit, a clock skew, a backfill -- must move 500 and set "
            "capped=True in a report someone reads, not move everything and "
            "be discovered afterwards."
        )

    def test_the_entry_does_NOT_pass_allow_delete(self):
        """THE LOAD-BEARING OMISSION.

        `archived -> deleted` is the only hop that destroys bytes. This is the
        assertion that fails the day somebody adds the argument that would let
        a cron job do it.
        """
        block = _entry_block("retention-migration")
        assert "allow_delete" not in block, (
            "the nightly tier migration entry passes allow_delete. Permanent "
            "deletion from an unattended schedule is not what was ruled."
        )

    def test_the_task_still_defaults_to_dry_run(self):
        """Live-ness lives on the ENTRY, not in the task.

        An accidental bare dispatch -- an operator testing something in a
        shell -- must still report rather than migrate.
        """
        src = PERIODIC_SRC.read_text()
        assert "dry_run=True if dry_run is None else bool(dry_run)" in src
        assert re.search(r"def run_retention_migration\([^)]*allow_delete: bool = False", src, re.S), (
            "run_retention_migration must default allow_delete to False"
        )


@pytest.mark.asyncio
class TestDeletionIsRefusedStructurally:
    """archive/delete stay impossible, and NOT because the data says so today.

    All three rows in `retention_policies` have NULL `archive_days` and NULL
    `delete_after_days` (read live 2026-08-26), so nothing progresses past
    cold. That is TRUE and it is a property of DATA: one
    `UPDATE retention_policies SET delete_after_days = 365` turns the nightly
    job into a deleter, with no code change, no review, and nothing in any
    diff.

    These tests pin both halves: NULL means "do not progress" (never zero), AND
    a policy that DOES configure deletion still deletes nothing on the
    scheduled path.
    """

    def _policy(self, **over):
        kw = dict(
            name="standard", hot_days=30, warm_days=90, cold_days=365,
            archive_days=None, delete_after_days=None,
            applies_to="all", is_default=True,
        )
        kw.update(over)
        return RetentionPolicy(**kw)

    async def test_null_terminal_days_mean_do_not_progress_never_zero(self):
        """`mapping.get(tier, 0)` would have deleted the fleet on first reach.

        0 satisfies `time_in_tier >= duration` for every asset that has ever
        existed. NULL must be None, and None must be a stop.
        """
        p = self._policy()
        assert p.get_tier_duration_days(StorageTier.COLD) == 365
        assert p.get_tier_duration_days(StorageTier.ARCHIVE) is None

    async def test_a_policy_that_configures_deletion_still_deletes_NOTHING(self):
        """THE ONE THAT SURVIVES A FUTURE POLICY EDIT.

        The policy here sets `delete_after_days=1` and the asset is 400 days
        old, so it is unambiguously eligible. The scheduled path deletes it
        anyway -- zero deletions, and the refusal is REPORTED rather than
        silently counted as "nothing was due".
        """
        old = datetime.now(timezone.utc) - timedelta(days=400)
        executed: list = []
        rows = {
            "archived": [
                (
                    "33333333-3333-3333-3333-333333333333", "image",
                    "/ivgs/images/c.png", "archived", old, False, old,
                    "fid-c", 900,
                ),
            ],
        }
        svc = RetentionService(
            db_session_factory=_session_factory(rows, executed),
            dry_run=False,
        )
        # Force the policy rather than letting the fake session load one.
        svc._default_policy = self._policy(
            archive_days=30, delete_after_days=1,
        )
        svc._policy_source = "test"

        report = await svc.run_migration()

        assert report.assets_deleted == 0, (
            "the scheduled path deleted an asset. allow_delete defaults to "
            "False and the nightly entry does not set it; a policy edit alone "
            "must never be able to enable deletion through this path."
        )
        deletes = [
            sql for sql, _ in executed
            if "DELETE" in sql.upper() or "PERMANENT" in sql.upper()
        ]
        assert deletes == [], f"a delete reached the database: {deletes}"

        # AND IT SAID SO. A refusal that is invisible reads, one report later,
        # as "there was nothing to delete".
        refusals = [
            k for k in report.policy_gaps
            if "allow_delete=False" in k
        ]
        assert refusals, (
            f"the refusal was not reported. policy_gaps={report.policy_gaps}"
        )
        assert report.policy_gaps[refusals[0]] == 1

    async def test_allow_delete_true_DOES_reach_the_delete_path(self):
        """The negative. A guard that refuses unconditionally is not a guard.

        An attended pass with `allow_delete=True` must still be able to do the
        thing an operator asked for, or the flag is theatre and someone will
        route around it.
        """
        old = datetime.now(timezone.utc) - timedelta(days=400)
        executed: list = []
        rows = {
            "archived": [
                (
                    "44444444-4444-4444-4444-444444444444", "image",
                    "/ivgs/images/d.png", "archived", old, False, old,
                    "fid-d", 900,
                ),
            ],
        }
        svc = RetentionService(
            db_session_factory=_session_factory(rows, executed),
            dry_run=True,          # dry run: decide everything, write nothing
            allow_delete=True,
        )
        svc._default_policy = self._policy(archive_days=30, delete_after_days=1)
        svc._policy_source = "test"

        report = await svc.run_migration()

        assert report.would_move.get("archived->deleted", {}).get("assets") == 1, (
            "with allow_delete=True the asset must be recognised as eligible. "
            f"would_move={report.would_move}"
        )


# ---------------------------------------------------------------------------
# TASK 7 — the orphan sweep is ON, weekly, and cannot delete
# ---------------------------------------------------------------------------

class TestOrphanScheduleIsOnWeeklyAndCannotDelete:
    def test_the_entry_is_live_and_weekly(self):
        """INVERTED FROM WP-60, which pinned that it stayed off.

        WP-60's version also pinned that "off" did not mean "pointing at a
        stub" -- the entry used to dispatch
        `tasks.pipeline_orchestrator.run_orphan_cleanup`, a Phase-5 stub
        recording SUCCESS at 03:00 nightly. That half of the assertion is kept
        below and is unchanged in strength.
        """
        block = _entry_block("orphan-cleanup-weekly", span=14)
        assert (
            "ivgs_workers.tasks.periodic_tasks.run_orphan_cleanup" in block
        )
        assert "day_of_week" in block, (
            "the orphan sweep is ruled WEEKLY. A crontab() without "
            "day_of_week runs it every night."
        )

        live = _live_lines(CELERY_APP_SRC)
        assert not any(
            "tasks.pipeline_orchestrator.run_orphan_cleanup" in l for l in live
        ), "the Phase-5 stub is on a live schedule again"

    def test_all_three_ruled_kwargs_are_passed_EXPLICITLY(self):
        """A schedule that relies on a default is one refactor from meaning
        something else -- and this particular default governs whether binaries
        are destroyed."""
        block = _entry_block("orphan-cleanup-weekly", span=14)
        assert '"dry_run": False' in block, (
            "the weekly sweep is ruled to act. A dry run would report the same "
            "numbers forever and quarantine nothing."
        )
        assert '"quarantine_only": True' in block, (
            "THE SWEEP MUST NOT BE ABLE TO PERMANENTLY DELETE. Quarantine is "
            "reversible for QUARANTINE_DAYS and audited; permanent deletion is "
            "reversible by nothing. A schedule may do the first."
        )
        assert '"exclude_scans": ["type1"]' in block, (
            "Type 1 has ZERO COVERAGE on this fleet -- it lists the filer "
            "namespace, which is empty -- and returns 0 whether or not such "
            "orphans exist. Running it is false assurance."
        )

    def test_the_task_defaults_to_the_SAFE_value_for_all_three(self):
        """Nothing may become destructive by omitting an argument."""
        src = PERIODIC_SRC.read_text()
        assert "dry_run=True if dry_run is None else bool(dry_run)" in src
        assert re.search(
            r"def run_orphan_cleanup\([^)]*quarantine_only: bool = False", src, re.S
        )
        assert re.search(
            r"def run_orphan_cleanup\([^)]*exclude_scans: list\[str\] \| None = None",
            src, re.S,
        )

    def test_the_decorator_still_belongs_to_the_task_under_it(self):
        """WP-60 S21.2's protection, applied to the helper THIS package added.

        `_report_retention_migration_metrics` was once inserted between
        `@shared_task(name="...run_retention_migration")` and its `def`, so the
        HELPER took the decorator and the task became a plain function -- the
        beat entry then named something unregistered and the nightly job would
        have raised NotRegistered every night, loudly, into a log nobody reads.
        WP-61 adds `_report_orphan_cleanup_metrics` in the same neighbourhood,
        so the same check is asserted here against the entries this package
        turned on.
        """
        src = PERIODIC_SRC.read_text()
        pattern = re.compile(
            r'@shared_task\((?P<args>[^)]*?)\)\s*\ndef\s+(?P<func>\w+)\s*\(',
            re.S,
        )
        declared = {}
        for m in pattern.finditer(src):
            name_m = re.search(r'name="([^"]+)"', m.group("args"))
            assert name_m, "a @shared_task has no explicit name"
            assert name_m.group(1).rsplit(".", 1)[-1] == m.group("func"), (
                f'@shared_task(name="...{name_m.group(1)}") decorates '
                f'`{m.group("func")}`; the declared name is not registered.'
            )
            declared[name_m.group(1)] = m.group("func")

        import celery_app as ca

        for entry_name in ("orphan-cleanup-weekly", "retention-migration"):
            task = ca.CELERY_BEAT_SCHEDULE[entry_name]["task"]
            assert task in declared, (
                f"beat entry {entry_name} names {task}, which "
                f"periodic_tasks.py does not declare."
            )

    def test_get_beat_schedule_IS_GONE_not_merely_delegating(self):
        """WP-IVGS-08 Task 2(c). This used to assert that
        `periodic_tasks.get_beat_schedule()` returned the ONE real schedule
        rather than a second hand-written copy -- WP-61's repair of a function
        that had drifted into a competing statement of the truth.

        The function is now REMOVED. It had zero callers: only its own
        definition and that test. Deleting it is strictly stronger than the
        delegation it replaced, because a copy of the schedule cannot drift out
        of a function that does not exist. This test inverts to hold that line.
        """
        import tasks.periodic_tasks as pt
        assert not hasattr(pt, "get_beat_schedule"), (
            "re-introducing this function re-opens the second-schedule defect "
            "WP-61 closed; the schedule lives in celery_app.CELERY_BEAT_SCHEDULE"
        )
class TestQuarantineOnlyAndExclusionActuallyBite:
    """The kwargs are not decoration: the service must honour them."""

    class _NullSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *a, **k):
            class _R:
                def fetchall(self_inner):
                    return []

                def scalar_one_or_none(self_inner):
                    return None

                def first(self_inner):
                    return None

            return _R()

        async def commit(self):
            return None

    def _svc(self, **kw):
        return OrphanCleanupService(
            db_session_factory=lambda: self._NullSession(), **kw
        )

    async def test_quarantine_only_skips_the_expiry_pass_and_SAYS_SO(self):
        svc = self._svc(dry_run=False, quarantine_only=True)
        called = {"expiry": False}

        async def _boom(report):
            called["expiry"] = True
            return 99

        svc._process_quarantine_expirations = _boom
        report = await svc.run_cleanup()
        await svc.close()

        assert called["expiry"] is False, (
            "the quarantine-expiry pass ran on a quarantine_only sweep. That "
            "is the only path here that permanently destroys bytes."
        )
        assert report.permanently_deleted == 0
        assert "NOT RUN" in report.coverage["quarantine_expiry"], (
            "0 deletions with no reason reads as 'nothing was due'."
        )

    async def test_without_quarantine_only_the_expiry_pass_DOES_run(self):
        """The negative. An attended run must still be able to finish the job."""
        svc = self._svc(dry_run=False, quarantine_only=False)
        called = {"expiry": False}

        async def _ran(report):
            called["expiry"] = True
            return 3

        svc._process_quarantine_expirations = _ran
        report = await svc.run_cleanup()
        await svc.close()

        assert called["expiry"] is True
        assert report.permanently_deleted == 3

    async def test_excluding_type1_skips_it_and_records_WHY(self):
        svc = self._svc(dry_run=True, exclude_scans=["type1"])
        called = {"type1": False}

        async def _t1(report):
            called["type1"] = True
            return 7

        svc._scan_type1_seaweedfs_without_db = _t1
        report = await svc.run_cleanup()
        await svc.close()

        assert called["type1"] is False
        assert report.type1_seaweedfs_without_db == 0
        note = report.coverage["type1"]
        assert "EXCLUDED" in note
        # The ledgered debt has to be IN the report, not only in a commit
        # message. WP-60 S12.2: zero coverage, and a design decision owed.
        assert "fid" in note
        assert "design decision" in note

    async def test_the_guard_is_still_not_optional(self):
        """WP-60's invariant, re-asserted because this package turned the
        schedule on.

        There is no configuration in which this service may quarantine or
        delete without consulting `SharedObjectGuard` -- a library object
        shared into three projects is four rows over one set of bytes, and
        decrementing the project rows takes `reference_count` to 0 while the
        bytes are in active use.
        """
        import inspect

        from services import orphan_cleanup as oc

        init_src = inspect.getsource(oc.OrphanCleanupService.__init__)
        assert "self._guard = SharedObjectGuard(db_session_factory)" in init_src
        # And it takes no parameter that could switch it off.
        assert "guard" not in inspect.signature(
            oc.OrphanCleanupService.__init__
        ).parameters
