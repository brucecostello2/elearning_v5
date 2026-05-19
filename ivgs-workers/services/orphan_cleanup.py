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
        seaweedfs_base_url: str = "http://node-01:9333",
        seaweedfs_filer_url: str = "http://node-01:8888",
    ) -> None:
        """
        Initialize orphan cleanup service.

        Args:
            db_session_factory: Async SQLAlchemy session factory.
            seaweedfs_base_url: SeaweedFS master server URL.
            seaweedfs_filer_url: SeaweedFS filer URL for file operations.
        """
        self._db_session_factory = db_session_factory
        self._seaweedfs_base_url = seaweedfs_base_url
        self._seaweedfs_filer_url = seaweedfs_filer_url
        self._http_client: httpx.AsyncClient | None = None
        self._log = logger.bind(service="orphan_cleanup")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for SeaweedFS operations."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
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
        report = CleanupReport()

        self._log.info("orphan_cleanup_started", run_id=report.run_id)

        try:
            # Scan Type 1: SeaweedFS objects without DB records
            type1_count = await self._scan_type1_seaweedfs_without_db(report)
            report.type1_seaweedfs_without_db = type1_count

            # Scan Type 2: DB records without SeaweedFS files
            type2_count = await self._scan_type2_db_without_seaweedfs(report)
            report.type2_db_without_seaweedfs = type2_count

            # Scan Type 3: Zero-reference count assets
            type3_count = await self._scan_type3_zero_reference(report)
            report.type3_zero_reference_count = type3_count

            # Process quarantine expirations
            deleted_count = await self._process_quarantine_expirations(report)
            report.permanently_deleted = deleted_count

        except Exception as exc:
            report.errors.append(f"Cleanup run error: {exc}")
            self._log.error(
                "orphan_cleanup_error",
                run_id=report.run_id,
                error=str(exc),
            )

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
        """
        Scan for SeaweedFS objects without corresponding database records.

        Lists all objects in each scan directory via SeaweedFS filer API
        and cross-references against the assets table storage_path column.

        Args:
            report: Running cleanup report to append errors to.

        Returns:
            Count of orphans found.
        """
        orphan_count = 0
        client = await self._get_client()

        for directory in SEAWEEDFS_SCAN_DIRECTORIES:
            try:
                # List directory contents via SeaweedFS filer
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

                data = response.json()
                entries = data.get("Entries", []) or []

                for entry in entries:
                    full_path = f"{directory}{entry.get('FullPath', {}).get('Name', entry.get('name', ''))}"

                    # Check if path exists in assets table
                    exists_in_db = await self._check_path_in_db(full_path)

                    if not exists_in_db:
                        orphan_count += 1
                        await self._quarantine_seaweedfs_object(
                            full_path, report
                        )

            except Exception as exc:
                error_msg = (
                    f"Type 1 scan error for {directory}: {exc}"
                )
                report.errors.append(error_msg)
                self._log.error(
                    "type1_scan_error",
                    directory=directory,
                    error=str(exc),
                )

        return orphan_count

    # ------------------------------------------------------------------
    # Scan Type 2: DB without SeaweedFS
    # ------------------------------------------------------------------

    async def _scan_type2_db_without_seaweedfs(
        self,
        report: CleanupReport,
    ) -> int:
        """
        Scan for database records referencing non-existent SeaweedFS files.

        Queries all assets with a storage_path and verifies file existence
        via HEAD requests to the SeaweedFS filer.

        Args:
            report: Running cleanup report.

        Returns:
            Count of orphans found.
        """
        orphan_count = 0

        async with self._db_session_factory() as session:
            from sqlalchemy import select, text

            result = await session.execute(
                text(
                    "SELECT id, storage_path FROM assets "
                    "WHERE storage_path IS NOT NULL "
                    "AND storage_path != '' "
                    "ORDER BY created_at ASC "
                    "LIMIT 10000"
                )
            )
            rows = result.fetchall()

        client = await self._get_client()

        for row in rows:
            asset_id = str(row[0])
            storage_path = str(row[1])

            try:
                response = await client.head(
                    f"{self._seaweedfs_filer_url}{storage_path}"
                )

                if response.status_code == 404:
                    orphan_count += 1
                    await self._mark_db_record_orphaned(
                        asset_id, storage_path, report
                    )

            except Exception as exc:
                error_msg = (
                    f"Type 2 scan error for asset {asset_id}: {exc}"
                )
                report.errors.append(error_msg)
                self._log.error(
                    "type2_scan_error",
                    asset_id=asset_id,
                    storage_path=storage_path,
                    error=str(exc),
                )

        return orphan_count

    # ------------------------------------------------------------------
    # Scan Type 3: Zero-reference count
    # ------------------------------------------------------------------

    async def _scan_type3_zero_reference(
        self,
        report: CleanupReport,
    ) -> int:
        """
        Scan for assets with reference_count = 0 for > 7 days per §10.6.

        Assets whose reference_count has been 0 for longer than
        ZERO_REF_THRESHOLD_DAYS are quarantined.

        Args:
            report: Running cleanup report.

        Returns:
            Count of orphans found.
        """
        orphan_count = 0
        threshold_date = datetime.now(timezone.utc) - timedelta(
            days=ZERO_REF_THRESHOLD_DAYS
        )

        async with self._db_session_factory() as session:
            from sqlalchemy import text

            result = await session.execute(
                text(
                    "SELECT id, storage_path FROM assets "
                    "WHERE reference_count = 0 "
                    "AND updated_at < :threshold "
                    "AND storage_path IS NOT NULL "
                    "ORDER BY updated_at ASC "
                    "LIMIT 5000"
                ),
                {"threshold": threshold_date},
            )
            rows = result.fetchall()

        for row in rows:
            asset_id = str(row[0])
            storage_path = str(row[1])

            try:
                await self._quarantine_asset(
                    asset_id, storage_path, "zero_reference", report
                )
                orphan_count += 1
            except Exception as exc:
                error_msg = (
                    f"Type 3 quarantine error for asset {asset_id}: {exc}"
                )
                report.errors.append(error_msg)
                self._log.error(
                    "type3_quarantine_error",
                    asset_id=asset_id,
                    error=str(exc),
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
        async with self._db_session_factory() as session:
            async with session.begin():
                from sqlalchemy import text

                await session.execute(
                    text(
                        "UPDATE assets SET status = 'orphaned', "
                        "updated_at = NOW() "
                        "WHERE id = :asset_id"
                    ),
                    {"asset_id": asset_id},
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
        storage_path: str,
        reason: str,
        report: CleanupReport,
    ) -> None:
        """
        Quarantine an asset (move file + update DB status).

        Args:
            asset_id: Database asset UUID.
            storage_path: SeaweedFS file path.
            reason: Reason for quarantine.
            report: Running cleanup report.
        """
        # Move file to quarantine
        await self._quarantine_seaweedfs_object(storage_path, report)

        # Update DB record
        async with self._db_session_factory() as session:
            async with session.begin():
                from sqlalchemy import text

                await session.execute(
                    text(
                        "UPDATE assets SET status = 'quarantined', "
                        "updated_at = NOW() "
                        "WHERE id = :asset_id"
                    ),
                    {"asset_id": asset_id},
                )

        await self._log_audit(
            action_type="QUARANTINE",
            resource_type="asset",
            resource_id=asset_id,
            details={
                "scan_type": "type3_zero_reference",
                "storage_path": storage_path,
                "reason": reason,
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

            result = await session.execute(
                text(
                    "SELECT 1 FROM assets "
                    "WHERE storage_path = :path LIMIT 1"
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
                            "after_payload": str(details),
                        },
                    )
        except Exception as exc:
            self._log.error(
                "audit_log_write_failed",
                action_type=action_type,
                resource_id=resource_id,
                error=str(exc),
            )
