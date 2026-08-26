"""
IVGS v5 — Orphan Cleanup Service
========================================

OrphanCleanupService per §10.6. Runs daily via Celery Beat.

Three scan types:
1. SeaweedFS objects without corresponding database records
2. Database asset records referencing non-existent SeaweedFS files
3. Assets with reference_count = 0 for more than 7 days

Orphan lifecycle:
- Identified → quarantined (moved to /ivgs/quarantine/)
- Quarantined for 7 days → permanently deleted
- All actions logged to audit_log table (Table 9)

SeaweedFS directories scanned per §10.2:
- /ivgs/images/
- /ivgs/videos/
- /ivgs/audio/
- /ivgs/talking-heads/
- /ivgs/animations/
- /ivgs/drafts/
- /ivgs/final/
- /ivgs/thumbnails/
- /ivgs/captions/
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUARANTINE_DAYS: int = 7
ZERO_REF_THRESHOLD_DAYS: int = 7
QUARANTINE_PATH: str = "/ivgs/quarantine"

SEAWEEDFS_SCAN_DIRECTORIES: list[str] = [
    "/ivgs/images/",
    "/ivgs/videos/",
    "/ivgs/audio/",
    "/ivgs/talking-heads/",
    "/ivgs/animations/",
    "/ivgs/drafts/",
    "/ivgs/final/",
    "/ivgs/thumbnails/",
    "/ivgs/captions/",
]


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class OrphanRecord(BaseModel):
    """Record of an identified orphan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scan_type: str = Field(
        ...,
        description="Type 1 (no DB), Type 2 (no file), Type 3 (zero ref)",
    )
    storage_path: str = Field(default="", description="SeaweedFS path")
    asset_id: str = Field(default="", description="Database asset UUID")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    quarantined_at: datetime | None = None
    deleted_at: datetime | None = None
    status: str = Field(default="detected")  # detected / quarantined / deleted


class CleanupReport(BaseModel):
    """Summary report of an orphan cleanup run."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    completed_at: datetime | None = None
    type1_seaweedfs_without_db: int = 0
    type2_db_without_seaweedfs: int = 0
    type3_zero_reference_count: int = 0
    newly_quarantined: int = 0
    permanently_deleted: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

    # WP-60 Task 10. Swallow-register entry 29: `errors` was appended to and
    # NOTHING READ IT -- the task returned the report as a success either way.
    # `status` is derived from errors and is what the task raises on.
    status: str = "ok"

    # Did this run actually change anything? Defaults TRUE, like the retention
    # service, so an accidental dispatch reports instead of acting.
    dry_run: bool = True

    # Objects the guard held back, by reason. This is the number that proves
    # the guard is doing something, and a run where it is empty on a fleet with
    # a populated library is a run to distrust.
    preserved: dict[str, int] = Field(default_factory=dict)

    # WP-60 Task 10: what this run could NOT see. Type 1 scans the filer
    # namespace, which on this fleet is EMPTY -- every object is stored by fid
    # through the master. A scan with zero coverage that reports zero orphans
    # is indistinguishable from a clean fleet, which is the whole family of
    # defect this package exists to close.
    coverage: dict[str, str] = Field(default_factory=dict)




# ---------------------------------------------------------------------------
# The shared-object guard  —  WP-60 Task 10 (WP-59 D-2)
# ---------------------------------------------------------------------------

class SharedObjectGuard:
    """Is anything still pointing at this object?

    THIS CLASS IS THE PRECONDITION FOR THE SERVICE EXISTING AT ALL.

    ``OrphanCleanupService`` QUARANTINES and then PERMANENTLY DELETES binaries.
    Before WP-60 it had no concept of a library reference or of a deduped
    object shared between projects, and WP-59 D-2 ruled that it must inherit
    ``ProjectDeletionService.binary_manifest``'s guard rather than grow a
    second copy — because two copies of a safety rule drift, and the one that
    drifts is the one that deletes library bytes out from under every
    referencing project.

    The rules are the same two, in the same order, checked against the same two
    handles, and they are ported here verbatim in intent:

    * ``library_asset_id IS NOT NULL`` on any row naming this object.
      ``LibraryService.reference_into_project`` copies the library row's fid and
      path onto the project row verbatim (library_service.py:370-371), so the
      project asset and the library asset are the SAME BYTES. Deleting it
      because one project's copy looks unreferenced destroys the library entry
      and every other project's reference with it.
    * any live row outside the candidate naming the same fid **or** the same
      path — another ``assets`` row, or a ``library_assets`` row.

    Checked against fid AND path because the two are independent handles on
    this fleet: ``upload_asset`` stores bytes by fid via the master
    (asset_service.py:341) and records a filer-style path the filer namespace
    does not actually contain, while library and referenced rows carry both.

    ``preserve_flag`` is a third rule this guard adds and the deletion service
    does not need: deletion is a deliberate operator act on one named project,
    while this sweep runs unattended over everything. An operator who set
    preserve_flag has said "not this one", and an automatic sweep is exactly
    the thing that flag exists to stop.

    A guard that cannot reach the database returns "unknown", and an unknown is
    treated as KEEP by every caller. Failing closed is the only safe direction:
    the cost of a wrong keep is a wasted object, the cost of a wrong delete is
    unrecoverable.
    """

    def __init__(self, db_session_factory: Any) -> None:
        self._db_session_factory = db_session_factory

    async def keep_reason(
        self,
        fid: str,
        path: str,
        exclude_asset_id: str | None = None,
    ) -> str:
        """Why this object must be kept, or "" if nothing references it.

        Args:
            fid: SeaweedFS file id, may be empty.
            path: SeaweedFS path, may be empty.
            exclude_asset_id: The candidate's own row, excluded so that an
                asset is not held back by itself.

        Returns:
            A reason string, or "" when the object is genuinely unreferenced.
            Never raises: an unreachable database yields
            ``guard_unavailable``, which callers must treat as keep.
        """
        from sqlalchemy import text

        if not fid and not path:
            # Nothing to check against. An object we cannot identify is an
            # object we must not delete.
            return "no_handle"

        params = {
            "fid": fid or "\x00-no-fid",
            "path": path or "\x00-no-path",
            "exclude": exclude_asset_id,
        }

        try:
            async with self._db_session_factory() as session:
                # Rule 1 — the library. Checked first and separately because a
                # library-backed row is shared even when it is the ONLY row.
                library_backed = await session.execute(
                    text(
                        "SELECT count(*) FROM assets "
                        "WHERE (seaweedfs_fid = :fid OR seaweedfs_path = :path) "
                        "AND library_asset_id IS NOT NULL"
                    ),
                    {"fid": params["fid"], "path": params["path"]},
                )
                if (library_backed.scalar() or 0) > 0:
                    return "library_asset"

                in_library = await session.execute(
                    text(
                        "SELECT count(*) FROM library_assets "
                        "WHERE seaweedfs_fid = :fid OR seaweedfs_path = :path"
                    ),
                    {"fid": params["fid"], "path": params["path"]},
                )
                if (in_library.scalar() or 0) > 0:
                    return "library_asset"

                # Rule 2 — any other live row, in any project.
                if exclude_asset_id:
                    other = await session.execute(
                        text(
                            "SELECT count(*) FROM assets "
                            "WHERE (seaweedfs_fid = :fid OR seaweedfs_path = :path) "
                            "AND id <> CAST(:exclude AS uuid)"
                        ),
                        params,
                    )
                else:
                    other = await session.execute(
                        text(
                            "SELECT count(*) FROM assets "
                            "WHERE seaweedfs_fid = :fid OR seaweedfs_path = :path"
                        ),
                        {"fid": params["fid"], "path": params["path"]},
                    )
                if (other.scalar() or 0) > 0:
                    return "referenced_by_another_asset"

                # Rule 3 — the operator's own veto.
                if exclude_asset_id:
                    preserved = await session.execute(
                        text(
                            "SELECT count(*) FROM assets "
                            "WHERE id = CAST(:exclude AS uuid) "
                            "AND preserve_flag IS TRUE"
                        ),
                        {"exclude": exclude_asset_id},
                    )
                    if (preserved.scalar() or 0) > 0:
                        return "preserve_flag"

        except Exception as exc:  # noqa: BLE001 - deliberate, see docstring
            logger.error(
                "shared_object_guard_unavailable",
                fid=fid,
                path=path,
                error=str(exc),
                detail=(
                    "the guard could not reach the database. Treated as KEEP: "
                    "an unverifiable object must never be quarantined or "
                    "deleted."
                ),
            )
            return "guard_unavailable"

        return ""


# ---------------------------------------------------------------------------
# Orphan Cleanup Service
# ---------------------------------------------------------------------------

class OrphanCleanupService:
    """
    Orphan cleanup service per §10.6.

    Runs daily via Celery Beat. Performs three types of orphan scans
    and manages the quarantine-then-delete lifecycle.

    Scan Type 1: SeaweedFS objects without corresponding database records
    - Lists all objects in scan directories via SeaweedFS API
    - Cross-references against assets table storage_path column
    - Objects with no matching DB record → quarantine

    Scan Type 2: Database records without SeaweedFS files
    - Queries assets table for all records with storage_path set
    - HEAD request to SeaweedFS for each path
    - Records where file doesn't exist → mark as orphaned

    Scan Type 3: Zero-reference assets
    - Queries assets where reference_count = 0
    - Checks if reference_count has been 0 for > 7 days
    - Eligible assets → quarantine

    Quarantine lifecycle:
    - Move to /ivgs/quarantine/{original_path}
    - After 7 days in quarantine → permanent deletion
    - All actions logged to audit_log (Table 9)
    """

    def __init__(
        self,
        db_session_factory: Any,
        seaweedfs_base_url: str | None = None,
        seaweedfs_filer_url: str | None = None,
        dry_run: bool = True,
    ) -> None:
        """
        Initialize orphan cleanup service.

        Args:
            db_session_factory: Async SQLAlchemy session factory.
            seaweedfs_base_url: SeaweedFS master server URL.
            seaweedfs_filer_url: SeaweedFS filer URL for file operations.
            dry_run: DEFAULTS TO TRUE. When true every decision is made and
                reported and nothing is moved, marked or deleted. Passing False
                is deliberately explicit: there is no way to destroy an object
                by omitting an argument.
        """
        self._db_session_factory = db_session_factory
        # WP-60 Task 10 — THE DEFAULTS POINTED AT THE CONTAINER'S OWN LOOPBACK.
        #
        # These were hardcoded `http://node-01:9333` and `http://node-01:8888`.
        # Inside a compose container `node-01` resolves to **127.0.1.1** before
        # it resolves to 192.168.1.90 -- verified with `getent hosts node-01`
        # in ivgs-celery-default -- and nothing listens on those ports there.
        # So every storage probe hung until its connect timeout: on 161 assets
        # that is roughly half an hour of the sweep doing nothing, which is how
        # a repaired scan still looks broken.
        #
        # The right values have been in the environment the whole time
        # (SEAWEEDFS_MASTER_URL / SEAWEEDFS_FILER_URL, set by compose to the
        # service names), and this service ignored them. It reads them now, and
        # an explicit argument still wins so tests can point it anywhere.
        self._seaweedfs_base_url = (
            seaweedfs_base_url
            or os.getenv("SEAWEEDFS_MASTER_URL")
            or "http://seaweedfs-master:9333"
        ).rstrip("/")
        self._seaweedfs_filer_url = (
            seaweedfs_filer_url
            or os.getenv("SEAWEEDFS_FILER_URL")
            or "http://seaweedfs-filer:8888"
        ).rstrip("/")
        self._http_client: httpx.AsyncClient | None = None
        self._log = logger.bind(service="orphan_cleanup")
        # WP-60 Task 10 (WP-59 D-2). The guard is not optional and is not a
        # parameter: there is no configuration in which this service may
        # quarantine or delete without consulting it.
        self._guard = SharedObjectGuard(db_session_factory)
        # DEFAULTS TO DRY RUN. This service has never executed; its first real
        # pass is an attended operator event, and the SCHEDULE STAYS OFF until
        # a future ruling. `dry_run` is what makes the mechanism exercisable —
        # and provable — without it acting.
        self._dry_run = bool(dry_run)

    async def _may_act_on(
        self,
        report: CleanupReport,
        *,
        fid: str,
        path: str,
        asset_id: str | None,
        scan_type: str,
    ) -> bool:
        """The single gate every destructive path goes through.

        WP-60 Task 10. There is exactly one of these on purpose: a second place
        that decides "is this safe to delete" is a second place that can be
        wrong, and the two will not be wrong in the same way.
        """
        reason = await self._guard.keep_reason(
            fid=fid, path=path, exclude_asset_id=asset_id,
        )
        if not reason:
            return True

        report.preserved[reason] = report.preserved.get(reason, 0) + 1
        self._log.info(
            "orphan_candidate_preserved",
            scan_type=scan_type,
            asset_id=asset_id,
            fid=fid,
            path=path,
            keep_reason=reason,
        )
        return False

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for SeaweedFS operations."""
        if self._http_client is None or self._http_client.is_closed:
            # WP-60 Task 10: a per-asset probe, not a download. 30s/10s meant
            # one unreachable endpoint turned a sweep into a half-hour stall
            # with nothing in the log to say why. Short, and bounded.
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=2.0),
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def run_cleanup(self) -> CleanupReport:
        """
        Execute a full orphan cleanup cycle.

        Runs all three scan types, quarantines new orphans, and
        permanently deletes orphans that have been quarantined
        for > QUARANTINE_DAYS.

        Returns:
            CleanupReport: Summary of the cleanup run.
        """
        report = CleanupReport(dry_run=self._dry_run)

        self._log.info(
            "orphan_cleanup_started",
            run_id=report.run_id,
            dry_run=self._dry_run,
        )

        # WP-60 Task 10 — EACH SCAN IN ITS OWN try.
        #
        # These four used to sit inside ONE try. The `SELECT` in
        # `_scan_type2_db_without_seaweedfs` was outside any local handler, so
        # its `UndefinedColumn` on `assets.storage_path` aborted `run_cleanup`
        # at scan 2 and scans 2, 3 AND the quarantine expiry never ran at all.
        # One broken query silently removed three quarters of the mechanism,
        # and the task still returned the report as a success.
        scans = (
            ("type1", self._scan_type1_seaweedfs_without_db),
            ("type2", self._scan_type2_db_without_seaweedfs),
            ("type3", self._scan_type3_zero_reference),
        )
        results: dict[str, int] = {}
        for name, scan in scans:
            try:
                results[name] = await scan(report)
            except Exception as exc:
                results[name] = 0
                report.errors.append(f"{name} scan failed: {exc}")
                report.coverage[name] = f"scan failed: {exc}"
                self._log.error(
                    "orphan_scan_failed",
                    run_id=report.run_id,
                    scan=name,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        report.type1_seaweedfs_without_db = results.get("type1", 0)
        report.type2_db_without_seaweedfs = results.get("type2", 0)
        report.type3_zero_reference_count = results.get("type3", 0)

        try:
            report.permanently_deleted = (
                await self._process_quarantine_expirations(report)
            )
        except Exception as exc:
            report.errors.append(f"quarantine expiry failed: {exc}")
            self._log.error(
                "quarantine_expiry_failed",
                run_id=report.run_id,
                error=str(exc),
            )

        # Swallow-register entry 29 CLOSED: errors now reach a field the caller
        # acts on, instead of an unread list beneath a returned success.
        if report.errors:
            report.status = "error"

        now = datetime.now(timezone.utc)
        report.completed_at = now
        report.duration_seconds = (now - report.started_at).total_seconds()

        self._log.info(
            "orphan_cleanup_completed",
            run_id=report.run_id,
            type1=report.type1_seaweedfs_without_db,
            type2=report.type2_db_without_seaweedfs,
            type3=report.type3_zero_reference_count,
            quarantined=report.newly_quarantined,
            deleted=report.permanently_deleted,
            preserved=report.preserved,
            coverage=report.coverage,
            status=report.status,
            dry_run=report.dry_run,
            errors=len(report.errors),
            duration_seconds=report.duration_seconds,
        )

        return report

    # ------------------------------------------------------------------
    # Scan Type 1: SeaweedFS without DB
    # ------------------------------------------------------------------

    async def _scan_type1_seaweedfs_without_db(
        self,
        report: CleanupReport,
    ) -> int:
        """Objects in storage that no database row claims.

        WP-60 Task 10 — THIS SCAN HAS ZERO COVERAGE ON THIS FLEET, AND NOW
        SAYS SO INSTEAD OF REPORTING ZERO ORPHANS.

        It lists the filer namespace and cross-references each entry against
        `assets`. The filer namespace is EMPTY -- measured directly:

            GET http://<filer>:8888/?limit=20
            {"Path":"","Entries":null,"EmptyFolder":true}

        because `AssetService.upload_asset` stores bytes BY FID through the
        master (asset_service.py:341) and records a filer-style path the filer
        does not actually contain. So this scan walks nine directories that do
        not exist, finds nothing, and reports zero orphans -- which reads
        exactly like a clean fleet.

        Enumerating the fid namespace instead is not possible with the HTTP
        APIs available: SeaweedFS volume servers expose counts, not a needle
        listing, and `weed shell`'s `volume.list` would mean running a sibling
        binary from inside this worker. That is a design decision, not a line
        of code, so the honest thing here is to state the coverage rather than
        to invent a number. Type 2 and Type 3 -- the scans that can actually
        find something on this fleet -- are unaffected and do run.

        Returns:
            Count of orphans found. Zero, with `report.coverage["type1"]`
            explaining why zero means "did not look" rather than "found none".
        """
        orphan_count = 0
        client = await self._get_client()
        namespace_populated = False

        for directory in SEAWEEDFS_SCAN_DIRECTORIES:
            try:
                response = await client.get(
                    f"{self._seaweedfs_filer_url}{directory}",
                    params={"limit": 10000},
                    headers={"Accept": "application/json"},
                )
                if response.status_code != 200:
                    self._log.warning(
                        "seaweedfs_directory_list_failed",
                        directory=directory,
                        status=response.status_code,
                    )
                    continue

                entries = (response.json() or {}).get("Entries") or []
                if entries:
                    namespace_populated = True

                for entry in entries:
                    name = (
                        entry.get("FullPath", {}).get("Name")
                        if isinstance(entry.get("FullPath"), dict)
                        else None
                    ) or entry.get("name", "")
                    full_path = f"{directory}{name}"

                    if await self._check_path_in_db(full_path):
                        continue

                    # THE GUARD, before anything is touched. A filer object
                    # with no `assets` row may still be a library object, and
                    # the library row carries the same path.
                    if not await self._may_act_on(
                        report, fid="", path=full_path,
                        asset_id=None, scan_type="type1",
                    ):
                        continue

                    orphan_count += 1
                    await self._quarantine_seaweedfs_object(full_path, report)

            except Exception as exc:
                report.errors.append(f"Type 1 scan error for {directory}: {exc}")
                self._log.error(
                    "type1_scan_error", directory=directory, error=str(exc),
                )

        if not namespace_populated:
            report.coverage["type1"] = (
                "ZERO COVERAGE: the SeaweedFS filer namespace is empty, so "
                "this scan examined nothing. Assets on this fleet are stored "
                "by fid through the master, not through the filer, and the fid "
                "namespace is not enumerable over HTTP. A zero here means 'did "
                "not look', NOT 'no orphans exist'."
            )
            self._log.warning(
                "type1_scan_no_coverage",
                directories=len(SEAWEEDFS_SCAN_DIRECTORIES),
                detail=report.coverage["type1"],
            )
        else:
            report.coverage["type1"] = "filer namespace listed"

        return orphan_count

    # ------------------------------------------------------------------
    # Scan Type 2: DB without SeaweedFS
    # ------------------------------------------------------------------

    async def _scan_type2_db_without_seaweedfs(
        self,
        report: CleanupReport,
    ) -> int:
        """Database rows whose stored object is gone.

        WP-60 Task 10. THE QUERY NAMED A COLUMN THAT DOES NOT EXIST.

            SELECT id, storage_path FROM assets ...
            ERROR:  column "storage_path" does not exist

        `assets` has `seaweedfs_path` and `seaweedfs_fid`. Verified against the
        live schema 2026-08-26. Worse than the wrong name: this `SELECT` sat
        OUTSIDE any local try, so the `UndefinedColumn` propagated out of the
        scan and aborted `run_cleanup` -- scans 2, 3 and the quarantine expiry
        never ran on any night this task was dispatched.

        The existence check now uses the FID through the volume master, which
        is how these objects are actually stored, and falls back to the filer
        path only when a row has a path and no fid.

        This scan does not quarantine or delete: a missing object with a live
        row is a DATABASE problem, not a storage one, and the row is the only
        remaining record that the object ever existed. It is recorded.
        """
        orphan_count = 0

        async with self._db_session_factory() as session:
            from sqlalchemy import text

            result = await session.execute(
                text(
                    "SELECT id, coalesce(seaweedfs_fid, ''), "
                    "       coalesce(seaweedfs_path, '') "
                    "FROM assets "
                    "WHERE (seaweedfs_fid IS NOT NULL AND seaweedfs_fid <> '') "
                    "   OR (seaweedfs_path IS NOT NULL AND seaweedfs_path <> '') "
                    "ORDER BY created_at ASC "
                    "LIMIT 10000"
                )
            )
            rows = result.fetchall()

        report.coverage["type2"] = f"{len(rows)} asset rows checked"
        client = await self._get_client()

        for row in rows:
            asset_id = str(row[0])
            fid = str(row[1] or "")
            path = str(row[2] or "")

            try:
                missing = await self._object_is_missing(client, fid, path)
                if not missing:
                    continue

                orphan_count += 1
                await self._mark_db_record_orphaned(
                    asset_id, fid or path, report,
                )

            except Exception as exc:
                report.errors.append(
                    f"Type 2 scan error for asset {asset_id}: {exc}"
                )
                self._log.error(
                    "type2_scan_error",
                    asset_id=asset_id, fid=fid, path=path, error=str(exc),
                )

        return orphan_count

    async def _object_is_missing(
        self, client: httpx.AsyncClient, fid: str, path: str,
    ) -> bool:
        """True only when storage positively says the object is not there.

        A network error, a timeout or a 5xx is NOT an answer. Treating one as
        "missing" would let a transient volume-server hiccup mark every asset
        on the fleet as an orphan in a single nightly pass, so anything other
        than a definite 404 means "present as far as we can tell".
        """
        if fid:
            try:
                response = await client.get(
                    f"{self._seaweedfs_base_url}/dir/lookup",
                    params={"volumeId": fid.split(",", 1)[0]},
                )
                if response.status_code == 404:
                    return True
                if response.status_code != 200:
                    return False
                locations = (response.json() or {}).get("locations") or []
                if not locations:
                    return True
                url = locations[0].get("publicUrl") or locations[0].get("url")
                if not url:
                    return False
                head = await client.head(f"http://{url}/{fid}")
                return head.status_code == 404
            except Exception:
                # Unreachable storage is not evidence of absence.
                return False

        try:
            head = await client.head(f"{self._seaweedfs_filer_url}{path}")
            return head.status_code == 404
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Scan Type 3: Zero-reference count
    # ------------------------------------------------------------------

    async def _scan_type3_zero_reference(
        self,
        report: CleanupReport,
    ) -> int:
        """Assets nothing has referenced for longer than the threshold.

        WP-60 Task 10. THIS IS THE SCAN THAT CAN DESTROY THE LIBRARY, and it
        is why WP-59 D-2 ruled the guard a precondition rather than a
        follow-up.

        Two column defects, both verified against the live schema:
          * `storage_path` does not exist -> `seaweedfs_path` / `seaweedfs_fid`
          * `updated_at` does not exist on `assets` at all. The age of a
            zero-reference row is taken from `last_accessed_at`, falling back
            to `created_at` -- which is the conservative direction, because a
            row that has never been accessed is aged from creation and a
            recently-touched one is protected.

        AND THE REAL DANGER: `LibraryService.reference_into_project` copies the
        library row's fid and path onto the project row VERBATIM, so a library
        object shared into three projects is four rows over ONE set of bytes.
        Decrement the project rows and `reference_count` on some of them
        reaches 0 while the bytes are still in active use by the library and by
        every other project. Before the guard, this scan would have quarantined
        and then permanently deleted them.

        Every candidate goes through `_may_act_on` first. No exceptions, no
        configuration that skips it.
        """
        orphan_count = 0
        threshold_date = datetime.now(timezone.utc) - timedelta(
            days=ZERO_REF_THRESHOLD_DAYS
        )

        async with self._db_session_factory() as session:
            from sqlalchemy import text

            result = await session.execute(
                text(
                    "SELECT id, coalesce(seaweedfs_fid, ''), "
                    "       coalesce(seaweedfs_path, '') "
                    "FROM assets "
                    "WHERE reference_count <= 0 "
                    "AND coalesce(last_accessed_at, created_at) < :threshold "
                    "AND ((seaweedfs_fid IS NOT NULL AND seaweedfs_fid <> '') "
                    "  OR (seaweedfs_path IS NOT NULL AND seaweedfs_path <> '')) "
                    "ORDER BY coalesce(last_accessed_at, created_at) ASC "
                    "LIMIT 5000"
                ),
                {"threshold": threshold_date},
            )
            rows = result.fetchall()

        report.coverage["type3"] = (
            f"{len(rows)} zero-reference rows older than "
            f"{ZERO_REF_THRESHOLD_DAYS}d considered"
        )

        for row in rows:
            asset_id = str(row[0])
            fid = str(row[1] or "")
            path = str(row[2] or "")

            try:
                if not await self._may_act_on(
                    report, fid=fid, path=path,
                    asset_id=asset_id, scan_type="type3",
                ):
                    continue

                await self._quarantine_asset(
                    asset_id, fid, path, "zero_reference", report,
                )
                orphan_count += 1
            except Exception as exc:
                report.errors.append(
                    f"Type 3 quarantine error for asset {asset_id}: {exc}"
                )
                self._log.error(
                    "type3_quarantine_error", asset_id=asset_id, error=str(exc),
                )

        return orphan_count

    # ------------------------------------------------------------------
    # Quarantine Operations
    # ------------------------------------------------------------------

    async def _quarantine_seaweedfs_object(
        self,
        storage_path: str,
        report: CleanupReport,
    ) -> None:
        """
        Move a SeaweedFS object to the quarantine directory.

        Copies the file to /ivgs/quarantine/ and deletes the original.
        Records the quarantine action in audit_log.

        Args:
            storage_path: Original SeaweedFS file path.
            report: Running cleanup report.
        """
        quarantine_dest = f"{QUARANTINE_PATH}{storage_path}"

        if self._dry_run:
            report.newly_quarantined += 1
            self._log.info(
                "orphan_would_be_quarantined",
                dry_run=True,
                original_path=storage_path,
                quarantine_path=quarantine_dest,
            )
            await self._log_audit(
                action_type="QUARANTINE_DRY_RUN",
                resource_type="seaweedfs_object",
                resource_id=storage_path,
                details={
                    "dry_run": True,
                    "original_path": storage_path,
                    "quarantine_path": quarantine_dest,
                },
            )
            return

        client = await self._get_client()

        try:
            # Copy to quarantine
            copy_response = await client.post(
                f"{self._seaweedfs_filer_url}{quarantine_dest}",
                headers={
                    "X-Seaweedfs-Copy-Source": storage_path,
                },
            )

            if copy_response.status_code in (200, 201):
                # Delete original
                delete_response = await client.delete(
                    f"{self._seaweedfs_filer_url}{storage_path}"
                )

                if delete_response.status_code in (200, 202, 204):
                    report.newly_quarantined += 1
                    await self._log_audit(
                        action_type="QUARANTINE",
                        resource_type="seaweedfs_object",
                        resource_id=storage_path,
                        details={
                            "scan_type": "type1_seaweedfs_without_db",
                            "original_path": storage_path,
                            "quarantine_path": quarantine_dest,
                        },
                    )

                    self._log.info(
                        "orphan_quarantined",
                        scan_type="type1",
                        original_path=storage_path,
                        quarantine_path=quarantine_dest,
                    )

        except Exception as exc:
            report.errors.append(
                f"Quarantine failed for {storage_path}: {exc}"
            )
            self._log.error(
                "quarantine_failed",
                storage_path=storage_path,
                error=str(exc),
            )

    async def _mark_db_record_orphaned(
        self,
        asset_id: str,
        storage_path: str,
        report: CleanupReport,
    ) -> None:
        """
        Mark a database asset record as orphaned (file missing in SeaweedFS).

        Sets the asset status to 'orphaned' and logs to audit_log.

        Args:
            asset_id: Database asset UUID.
            storage_path: The missing SeaweedFS path.
            report: Running cleanup report.
        """
        # WP-60 Task 10. `assets` HAS NO `status` COLUMN, AND NO `updated_at`.
        # Verified against the live schema 2026-08-26. This UPDATE could never
        # have run; it would have raised UndefinedColumn on the first row --
        # except that the SELECT feeding it raised first, so this line has
        # never executed at all.
        #
        # The finding is recorded in `generation_metadata` (jsonb, exists) so
        # it is queryable, and in `audit_log` so it is attributable. Neither is
        # destructive: a row whose object is missing is the ONLY remaining
        # record that the object existed, and marking is not deleting.
        if not self._dry_run:
            async with self._db_session_factory() as session:
                async with session.begin():
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            "UPDATE assets SET generation_metadata = "
                            "  coalesce(generation_metadata, '{}'::jsonb) "
                            "  || jsonb_build_object("
                            "       'orphan_state', 'object_missing', "
                            "       'orphan_detected_at', :detected_at, "
                            "       'orphan_handle', :handle) "
                            "WHERE id = CAST(:asset_id AS uuid)"
                        ),
                        {
                            "asset_id": asset_id,
                            "handle": storage_path,
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )

        report.newly_quarantined += 1

        await self._log_audit(
            action_type="MARK_ORPHANED",
            resource_type="asset",
            resource_id=asset_id,
            details={
                "scan_type": "type2_db_without_seaweedfs",
                "storage_path": storage_path,
                "reason": "SeaweedFS file not found",
            },
        )

        self._log.info(
            "db_record_orphaned",
            asset_id=asset_id,
            storage_path=storage_path,
        )

    async def _quarantine_asset(
        self,
        asset_id: str,
        fid: str,
        path: str,
        reason: str,
        report: CleanupReport,
    ) -> None:
        """Quarantine an asset: move the bytes, mark the row, leave a trail.

        THE CALLER HAS ALREADY PASSED `_may_act_on`. This function does not
        re-check, and it must never be called from a path that has not.

        `assets` has no `status` column (verified 2026-08-26), so the mark goes
        into `generation_metadata` and the attribution into `audit_log`.
        Quarantine is reversible for QUARANTINE_DAYS by design; the audit row
        is what makes reversing it possible, which is why it is written whether
        or not the byte move succeeds.
        """
        handle = path or fid

        await self._log_audit(
            action_type="QUARANTINE_DRY_RUN" if self._dry_run else "QUARANTINE",
            resource_type="asset",
            resource_id=asset_id,
            details={
                "scan_type": "type3_zero_reference",
                "dry_run": self._dry_run,
                "seaweedfs_fid": fid,
                "seaweedfs_path": path,
                "quarantine_path": f"{QUARANTINE_PATH}{handle}",
                "reason": reason,
                "guard": "passed - no library row, no other asset row, no preserve_flag",
            },
        )

        if self._dry_run:
            report.newly_quarantined += 1
            self._log.info(
                "asset_would_be_quarantined",
                dry_run=True, asset_id=asset_id, fid=fid, path=path,
                reason=reason,
            )
            return

        if path:
            await self._quarantine_seaweedfs_object(path, report)
        else:
            report.newly_quarantined += 1

        async with self._db_session_factory() as session:
            async with session.begin():
                from sqlalchemy import text

                await session.execute(
                    text(
                        "UPDATE assets SET generation_metadata = "
                        "  coalesce(generation_metadata, '{}'::jsonb) "
                        "  || jsonb_build_object("
                        "       'orphan_state', 'quarantined', "
                        "       'orphan_reason', :reason, "
                        "       'orphan_detected_at', :detected_at) "
                        "WHERE id = CAST(:asset_id AS uuid)"
                    ),
                    {
                        "asset_id": asset_id,
                        "reason": reason,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

    async def _process_quarantine_expirations(
        self,
        report: CleanupReport,
    ) -> int:
        """
        Permanently delete assets that have been quarantined for > 7 days.

        Scans the quarantine directory for objects older than
        QUARANTINE_DAYS and permanently deletes them.

        Args:
            report: Running cleanup report.

        Returns:
            Count of permanently deleted items.
        """
        deleted_count = 0
        client = await self._get_client()
        expiration_threshold = datetime.now(timezone.utc) - timedelta(
            days=QUARANTINE_DAYS
        )

        try:
            # List quarantine directory
            response = await client.get(
                f"{self._seaweedfs_filer_url}{QUARANTINE_PATH}/",
                params={"limit": 10000},
                headers={"Accept": "application/json"},
            )

            if response.status_code != 200:
                return 0

            data = response.json()
            entries = data.get("Entries", []) or []

            for entry in entries:
                # Check modification time
                mtime = entry.get("Mtime", "")
                if not mtime:
                    continue

                try:
                    entry_time = datetime.fromisoformat(
                        mtime.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    continue

                if entry_time < expiration_threshold:
                    entry_name = entry.get("FullPath", {}).get(
                        "Name", entry.get("name", "")
                    )
                    full_path = f"{QUARANTINE_PATH}/{entry_name}"

                    # WP-60 Task 10 — THE LAST GATE, AND THE ONLY IRREVERSIBLE
                    # STEP IN THE SERVICE.
                    #
                    # The guard is applied AGAIN here, against the object's
                    # ORIGINAL path, and not because the quarantine-time check
                    # was insufficient. Quarantine lasts QUARANTINE_DAYS, and
                    # in that week a library reference or a cross-project
                    # dedup CAN come into existence over the same handle. A
                    # decision taken seven days ago is not evidence about
                    # today, and this is the step with no way back.
                    original_path = full_path[len(QUARANTINE_PATH):] or full_path
                    if not await self._may_act_on(
                        report, fid="", path=original_path,
                        asset_id=None, scan_type="quarantine_expiry",
                    ):
                        continue

                    if self._dry_run:
                        deleted_count += 1
                        self._log.info(
                            "quarantined_object_would_be_deleted",
                            dry_run=True, path=full_path, quarantined_at=mtime,
                        )
                        continue

                    try:
                        delete_response = await client.delete(
                            f"{self._seaweedfs_filer_url}{full_path}"
                        )

                        if delete_response.status_code in (
                            200, 202, 204
                        ):
                            deleted_count += 1
                            await self._log_audit(
                                action_type="PERMANENT_DELETE",
                                resource_type="quarantined_object",
                                resource_id=full_path,
                                details={
                                    "quarantined_at": mtime,
                                    "deleted_after_days": QUARANTINE_DAYS,
                                },
                            )

                            self._log.info(
                                "quarantined_object_deleted",
                                path=full_path,
                                quarantined_at=mtime,
                            )

                    except Exception as exc:
                        report.errors.append(
                            f"Delete failed for {full_path}: {exc}"
                        )

        except Exception as exc:
            report.errors.append(
                f"Quarantine expiration scan error: {exc}"
            )
            self._log.error(
                "quarantine_expiration_error",
                error=str(exc),
            )

        return deleted_count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _check_path_in_db(self, storage_path: str) -> bool:
        """
        Check if a storage path exists in the assets table.

        Args:
            storage_path: SeaweedFS file path to check.

        Returns:
            True if a matching asset record exists.
        """
        async with self._db_session_factory() as session:
            from sqlalchemy import text

            # WP-60 Task 10: `storage_path` does not exist. The real column is
            # `seaweedfs_path`, and `library_assets` carries the same handle --
            # a filer object claimed only by a library row is NOT an orphan.
            result = await session.execute(
                text(
                    "SELECT 1 FROM assets WHERE seaweedfs_path = :path "
                    "UNION ALL "
                    "SELECT 1 FROM library_assets WHERE seaweedfs_path = :path "
                    "LIMIT 1"
                ),
                {"path": storage_path},
            )
            return result.fetchone() is not None

    async def _log_audit(
        self,
        *,
        action_type: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any],
    ) -> None:
        """
        Log an action to the audit_log table (Table 9).

        All orphan cleanup actions are recorded for compliance
        and post-mortem analysis.

        Args:
            action_type: Type of action (QUARANTINE, PERMANENT_DELETE, etc.).
            resource_type: Type of resource affected.
            resource_id: ID or path of the affected resource.
            details: Additional context as JSONB.
        """
        try:
            async with self._db_session_factory() as session:
                async with session.begin():
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            "INSERT INTO audit_log "
                            "(id, user_id, action_type, resource_type, "
                            "resource_id, after_payload, timestamp) "
                            "VALUES (:id, :user_id, :action_type, "
                            ":resource_type, :resource_id, "
                            ":after_payload, NOW())"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "user_id": None,
                            "action_type": action_type,
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            # WP-60 Task 10. THIS WAS `str(details)`.
                            #
                            # `audit_log.after_payload` is JSONB and
                            # `str(dict)` is a Python repr -- single quotes,
                            # `True` not `true` -- which asqlpg rejects with
                            # InvalidTextRepresentation. So EVERY audit row
                            # this service tried to write failed, and failed
                            # into the `except` below, which logs and returns.
                            # The audit trail that makes a quarantine
                            # reversible has never been written once.
                            #
                            # It was invisible because the scans raised before
                            # reaching here: three defects deep, each hidden by
                            # the one in front of it.
                            "after_payload": json.dumps(details, default=str),
                        },
                    )
        except Exception as exc:
            # Deliberately not re-raised: losing the audit row must not abort a
            # sweep mid-way. But it is an ERROR, not a warning, and it names
            # the consequence -- a quarantine without its audit row cannot be
            # reversed, which is the only thing that makes quarantine safer
            # than deletion.
            self._log.error(
                "audit_log_write_failed",
                action_type=action_type,
                resource_id=resource_id,
                error=str(exc),
                detail=(
                    "the action proceeded but is NOT recorded. A quarantine "
                    "with no audit row cannot be reversed."
                ),
            )
