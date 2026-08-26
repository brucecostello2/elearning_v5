"""
IVGS v5 — Retention Tier Migration Service
========================================

RetentionService per §10.3. Runs daily via Celery Beat.

Storage tiers: hot → warm → cold → archive → delete

Configuration source: retention_policies table (Table 20)
  name, hot_days, warm_days, cold_days, archive_days,
  delete_after_days, applies_to, is_default

Tier transition logic:
1. Scan assets table for records exceeding current tier duration
2. Look up applicable retention_policy for the asset type
3. Call transition_tier(asset_id, new_tier) to move data
4. Update storage_tier and tier_transition_at columns
5. Skip assets with preserve_flag = true

SeaweedFS tier mapping per §10.3:
- hot:     SSD-backed volumes (fast random I/O)
- warm:    HDD-backed volumes (sequential reads)
- cold:    Compressed HDD (infrequent access)
- archive: NAS archival (glacial retrieval times)
- delete:  Permanent removal from all storage
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StorageTier(str, Enum):
    """Storage tier levels per §10.3.

    THE VALUES ARE THE POSTGRES ENUM LABELS, NOT THE ENGLISH WORDS. The live
    ``storage_tier`` type is ``hot, warm, cold, archived, deleted`` -- both
    terminal labels are PAST PARTICIPLES. This class said ``archive`` and
    ``delete``, so every write of either would have failed with

        invalid input value for enum storage_tier: "archive"

    WP-57 §3.1 found the ``archive`` half (D-1). The ``delete`` half is the
    same defect one hop further down the chain and was not named there; both
    are corrected here. Nothing had ever reached either, because the scan that
    feeds them could not run at all -- see ``_process_tier_transitions``.
    """

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVE = "archived"
    DELETE = "deleted"


# Tier progression order (hot is most accessible, delete is terminal)
TIER_ORDER: list[StorageTier] = [
    StorageTier.HOT,
    StorageTier.WARM,
    StorageTier.COLD,
    StorageTier.ARCHIVE,
    StorageTier.DELETE,
]


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class RetentionPolicy(BaseModel):
    """Retention policy from Table 20 (retention_policies).

    ``archive_days`` and ``delete_after_days`` ARE NULLABLE, and correcting
    that is a WP-59 Task 7 finding of its own.

    The live `retention_policies` table holds three rows -- `standard`,
    `long-term`, `compliance` -- and in every one of them BOTH columns are
    NULL. This model declared them as required ints, so constructing a policy
    from any of those rows raised ValidationError, `load_policies`' bare
    `except Exception` caught it, and the service silently fell back to the
    hardcoded DEFAULT_RETENTION_POLICIES below. **The operator's configured
    retention policy has therefore never governed anything.** Same shape as
    WP-58's four `BACKUP_RETENTION_*` variables and WP-57's rate limits: a
    setting that looks live and is decorative, and is invisible until someone
    tries to change a value.

    NULL means "this policy does not progress past the previous tier" -- not
    zero, and not infinity. `get_tier_duration_days` returns None for it and
    the scan skips the hop, recording it, rather than treating an unset
    duration as "eligible immediately", which would archive or DELETE the
    fleet's assets on the first run.
    """

    name: str
    hot_days: int = Field(..., description="Days in hot tier")
    warm_days: int = Field(..., description="Days in warm tier")
    cold_days: int = Field(..., description="Days in cold tier")
    archive_days: int | None = Field(
        default=None,
        description="Days in archive tier; NULL = never progress past cold",
    )
    delete_after_days: int | None = Field(
        default=None,
        description="Days before permanent deletion; NULL = never delete",
    )
    applies_to: str = Field(
        ...,
        description="Asset type this policy applies to",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the default policy",
    )

    def get_tier_duration_days(self, tier: StorageTier) -> int | None:
        """
        Get the duration in days for a specific tier.

        Returns None when this policy does not configure a duration for the
        tier, which the caller must treat as "do not progress", NOT as zero.
        The old signature returned 0 for a missing value via
        ``mapping.get(tier, 0)``, and 0 compares as "time_in_tier >= duration"
        for every asset ever created -- so an unconfigured archive_days would
        have archived the entire fleet on the first run that reached it.
        """
        mapping: dict[StorageTier, int | None] = {
            StorageTier.HOT: self.hot_days,
            StorageTier.WARM: self.warm_days,
            StorageTier.COLD: self.cold_days,
            StorageTier.ARCHIVE: self.archive_days,
            StorageTier.DELETE: 0,
        }
        return mapping.get(tier)


class TierTransitionRecord(BaseModel):
    """Record of a single tier transition."""

    asset_id: str
    from_tier: StorageTier
    to_tier: StorageTier
    transitioned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    policy_name: str = ""
    storage_path: str = ""


class MigrationReport(BaseModel):
    """Summary report of a retention migration run."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    completed_at: datetime | None = None
    assets_scanned: int = 0
    transitions_performed: int = 0
    assets_deleted: int = 0
    assets_preserved: int = 0
    transitions: list[TierTransitionRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    # --- WP-59 Task 7 ---
    dry_run: bool = True
    status: str = Field(
        default="ok",
        description=(
            "'ok' or 'failed'. A tier pass that raises now sets this and the "
            "task raises on it. It used to be swallowed per tier and the run "
            "reported success having scanned nothing."
        ),
    )
    capped: bool = Field(
        default=False,
        description="True when max_transitions stopped the run short.",
    )
    policy_source: str = Field(
        default="unknown",
        description=(
            "'database' or 'hardcoded_defaults'. The three rows in the live "
            "retention_policies table could not be loaded at all until WP-59 "
            "(both terminal columns are NULL and the model required them), so "
            "the service silently used the hardcoded defaults. Which set "
            "governed is now reported rather than assumed."
        ),
    )
    policy_load_error: str | None = Field(
        default=None,
        description="Why the database policies could not be used, if they could not.",
    )
    policy_gaps: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Per tier hop, how many assets were skipped because the governing "
            "policy configures no duration for that tier."
        ),
    )
    would_move: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "Per tier hop ('hot->warm'), {'assets': n, 'bytes': n}. Populated "
            "in BOTH modes: in dry-run it is the whole output, in a live run it "
            "is what was attempted."
        ),
    )


# ---------------------------------------------------------------------------
# Default Retention Policies
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_POLICIES: list[RetentionPolicy] = [
    RetentionPolicy(
        name="default_images",
        hot_days=30,
        warm_days=60,
        cold_days=90,
        archive_days=365,
        delete_after_days=730,
        applies_to="image",
        is_default=True,
    ),
    RetentionPolicy(
        name="default_videos",
        hot_days=14,
        warm_days=30,
        cold_days=60,
        archive_days=180,
        delete_after_days=365,
        applies_to="video",
        is_default=True,
    ),
    RetentionPolicy(
        name="default_audio",
        hot_days=30,
        warm_days=60,
        cold_days=90,
        archive_days=365,
        delete_after_days=730,
        applies_to="audio",
        is_default=True,
    ),
    RetentionPolicy(
        name="default_renders",
        hot_days=60,
        warm_days=90,
        cold_days=180,
        archive_days=365,
        delete_after_days=1095,
        applies_to="render",
        is_default=True,
    ),
]


# ---------------------------------------------------------------------------
# Retention Service
# ---------------------------------------------------------------------------

class RetentionService:
    """
    Retention tier migration service per §10.3.

    Runs daily via Celery Beat. Manages the lifecycle of assets across
    storage tiers based on configurable retention policies.

    Tier progression: hot → warm → cold → archive → delete

    The service:
    1. Loads retention policies from the database (Table 20)
    2. Scans assets for tier transition eligibility
    3. Moves files between SeaweedFS tier-specific volumes
    4. Updates database records (storage_tier, tier_transition_at)
    5. Skips assets with preserve_flag = true
    6. Logs all transitions to audit_log (Table 9)

    SeaweedFS integration:
    - Uses SeaweedFS volume server rack/data center assignments
      to move data between tier-specific storage backends
    - hot = SSD volumes, warm = HDD volumes, cold = compressed HDD,
      archive = NAS volumes
    """

    def __init__(
        self,
        db_session_factory: Any,
        seaweedfs_filer_url: str = "http://node-01:8888",
        *,
        dry_run: bool = True,
        max_transitions: int | None = None,
        allow_delete: bool = False,
    ) -> None:
        """
        Initialize retention service.

        Args:
            db_session_factory: Async SQLAlchemy session factory.
            seaweedfs_filer_url: SeaweedFS filer URL for file operations.
            dry_run: WP-59 Task 7. DEFAULTS TO TRUE, deliberately. This service
                has never moved an asset in its life -- the first real run
                touches 158 live assets and must be an attended event, not a
                cron surprise at 04:00. A dry run performs the whole scan and
                the whole eligibility decision and writes NOTHING: no UPDATE,
                no SeaweedFS call, no audit row. Its report is the answer to
                "what would move, how many, how many bytes, per tier".
            max_transitions: Hard ceiling on transitions performed in one run.
                The operator's first live pass is a CAPPED pass; leaving the
                cap at None is the unbounded run and should follow a capped one
                that behaved.
            allow_delete: WP-61 Task 6. DEFAULTS TO FALSE, and the nightly
                schedule does not set it.

                The `archived -> deleted` hop is the only one that destroys
                bytes, and today it is unreachable for a *configuration*
                reason: all three rows in `retention_policies` have NULL
                `delete_after_days` (read live 2026-08-26), and NULL means "do
                not progress past this tier". That is true, and it is a
                property of DATA. One `UPDATE retention_policies SET
                delete_after_days = 365` and the nightly job starts deleting,
                with no code change, no review and nothing in the diff.

                This flag makes the property structural instead. The scheduled
                path cannot delete, whatever the policy table says, and turning
                that off is an explicit kwarg someone has to type -- which is
                the same shape of protection `dry_run` gives the whole run and
                `quarantine_only` gives the orphan sweep.
        """
        self._dry_run = dry_run
        self._max_transitions = max_transitions
        self._allow_delete = bool(allow_delete)
        self._db_session_factory = db_session_factory
        self._seaweedfs_filer_url = seaweedfs_filer_url
        self._policies_cache: dict[str, RetentionPolicy] = {}
        self._default_policy: RetentionPolicy | None = None
        self._policy_source: str = "unknown"
        self._policy_load_error: str | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._log = logger.bind(service="retention_service")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for SeaweedFS operations."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def load_policies(self) -> None:
        """
        Load retention policies from the database (Table 20).

        Falls back to DEFAULT_RETENTION_POLICIES if database is empty.
        Caches policies for the duration of the migration run.
        """
        try:
            async with self._db_session_factory() as session:
                from sqlalchemy import text

                result = await session.execute(
                    text("SELECT * FROM retention_policies ORDER BY name")
                )
                rows = result.fetchall()

                if rows:
                    for row in rows:
                        policy = RetentionPolicy(
                            name=row.name,
                            hot_days=row.hot_days,
                            warm_days=row.warm_days,
                            cold_days=row.cold_days,
                            archive_days=row.archive_days,
                            delete_after_days=row.delete_after_days,
                            applies_to=row.applies_to,
                            is_default=row.is_default,
                        )
                        self._policies_cache[row.applies_to] = policy
                        if row.is_default and self._default_policy is None:
                            self._default_policy = policy

                    self._policy_source = "database"
                    self._log.info(
                        "retention_policies_loaded_from_db",
                        count=len(self._policies_cache),
                        policies=sorted(self._policies_cache),
                    )
                    return

        except Exception as exc:
            # NOT a warning-and-carry-on any more. Falling back to hardcoded
            # defaults means the operator's configured retention policy is
            # being ignored, and until WP-59 that happened on EVERY run and was
            # invisible: the three rows in retention_policies have NULL in both
            # terminal columns, which the old required-int model rejected.
            self._policy_load_error = f"{type(exc).__name__}: {exc}"
            self._log.error(
                "retention_policies_db_load_failed",
                error=str(exc),
                consequence=(
                    "the configured retention_policies rows are NOT governing; "
                    "hardcoded DEFAULT_RETENTION_POLICIES are being used instead"
                ),
            )

        # Fall back to defaults
        for policy in DEFAULT_RETENTION_POLICIES:
            self._policies_cache[policy.applies_to] = policy
            if policy.is_default and self._default_policy is None:
                self._default_policy = policy

        self._policy_source = "hardcoded_defaults"
        self._log.info(
            "retention_policies_loaded_defaults",
            count=len(self._policies_cache),
            reason=self._policy_load_error or "retention_policies table is empty",
        )

    def get_policy_for_asset_type(self, asset_type: str) -> RetentionPolicy:
        """
        Get retention policy for an asset type.

        Args:
            asset_type: Asset type string (image, video, audio, render).

        Returns:
            Matching or default retention policy.
        """
        if asset_type in self._policies_cache:
            return self._policies_cache[asset_type]

        if self._default_policy is not None:
            return self._default_policy

        # Ultimate fallback
        return DEFAULT_RETENTION_POLICIES[0]

    async def run_migration(self) -> MigrationReport:
        """
        Execute a full retention tier migration cycle.

        Scans all assets, checks tier transition eligibility against
        retention policies, and performs transitions for eligible assets.

        Returns:
            MigrationReport: Summary of the migration run.
        """
        report = MigrationReport(dry_run=self._dry_run)

        self._log.info(
            "retention_migration_started",
            run_id=report.run_id,
            dry_run=self._dry_run,
            max_transitions=self._max_transitions,
        )

        # Load/refresh policies
        await self.load_policies()
        report.policy_source = self._policy_source
        report.policy_load_error = self._policy_load_error

        now = datetime.now(timezone.utc)

        # Process each tier (hot → warm → cold → archive → delete)
        for tier_index, current_tier in enumerate(TIER_ORDER[:-1]):
            next_tier = TIER_ORDER[tier_index + 1]

            try:
                count = await self._process_tier_transitions(
                    current_tier=current_tier,
                    next_tier=next_tier,
                    now=now,
                    report=report,
                )
                report.transitions_performed += count
            except Exception as exc:
                # WP-59 Task 7: FIX THE SWALLOW.
                #
                # This except used to append a string to `report.errors` and
                # carry on, and NOTHING read `report.errors`. The task returned
                # `{'status': 'ok'}` and Celery recorded SUCCESS, so a scan that
                # raised UndefinedColumn on every tier of every run reported a
                # migration that had scanned nothing and moved nothing. Same
                # class as the four in the swallowed-failures register
                # (WP-00-SWALLOWED-FAILURES), and the seventh instance of the
                # inert-mechanism pattern.
                #
                # The per-tier catch is KEPT -- one tier failing should not stop
                # the other three from being assessed, which is genuine value --
                # but `status` now goes to 'failed', and the calling task raises
                # on it. A failed tier pass records failure.
                report.status = "failed"
                report.errors.append(
                    f"Tier {current_tier.value}->{next_tier.value}: "
                    f"{type(exc).__name__}: {exc}"
                )
                self._log.error(
                    "tier_transition_error",
                    current_tier=current_tier.value,
                    next_tier=next_tier.value,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    consequence="this tier moved nothing; the run is reported failed",
                )

        report.completed_at = datetime.now(timezone.utc)
        report.duration_seconds = (
            report.completed_at - report.started_at
        ).total_seconds()

        self._log.info(
            "retention_migration_completed",
            run_id=report.run_id,
            dry_run=report.dry_run,
            status=report.status,
            policy_source=report.policy_source,
            policy_gaps=report.policy_gaps,
            scanned=report.assets_scanned,
            transitions=report.transitions_performed,
            deleted=report.assets_deleted,
            preserved=report.assets_preserved,
            capped=report.capped,
            would_move=report.would_move,
            errors=len(report.errors),
            duration_seconds=report.duration_seconds,
        )

        return report

    async def _process_tier_transitions(
        self,
        *,
        current_tier: StorageTier,
        next_tier: StorageTier,
        now: datetime,
        report: MigrationReport,
    ) -> int:
        """
        Process tier transitions for all assets in the given tier.

        Queries assets in current_tier, checks if they've exceeded
        the tier duration per their retention policy, and transitions
        eligible assets to next_tier.

        Args:
            current_tier: Source storage tier.
            next_tier: Destination storage tier.
            now: Current timestamp.
            report: Running migration report.

        Returns:
            Count of transitions performed.
        """
        transition_count = 0
        unconfigured = 0
        blocked = 0

        async with self._db_session_factory() as session:
            from sqlalchemy import text

            # `assets` has `seaweedfs_path` and `seaweedfs_fid`. There is no
            # `storage_path` column and there never has been -- WP-57 §3.1
            # (D-1), verified again here against the live schema on 2026-08-26:
            #
            #     ERROR:  column "storage_path" does not exist
            #
            # `seaweedfs_fid` is selected alongside it because the fid is the
            # handle that actually addresses the bytes on this fleet: the filer
            # namespace is EMPTY (measured -- GET /ivgs/ returns 404 and the
            # filer root lists no entries), so every object is a volume object
            # reached by fid, and `seaweedfs_path` is a label rather than a
            # location. Any future physical move has to work on the fid.
            result = await session.execute(
                text(
                    "SELECT id, asset_type::text, seaweedfs_path, "
                    "storage_tier::text, tier_transition_at, preserve_flag, "
                    "created_at, coalesce(seaweedfs_fid, ''), "
                    "coalesce(file_size_bytes, 0) "
                    "FROM assets "
                    "WHERE storage_tier = CAST(:tier AS storage_tier) "
                    "AND (preserve_flag IS NULL OR preserve_flag = false) "
                    "ORDER BY tier_transition_at ASC NULLS FIRST "
                    "LIMIT 5000"
                ),
                {"tier": current_tier.value},
            )
            rows = result.fetchall()
            report.assets_scanned += len(rows)

        for row in rows:
            asset_id = str(row[0])
            asset_type = str(row[1])
            storage_path = str(row[2]) if row[2] else ""
            tier_transition_at = row[4] or row[6]  # fallback to created_at
            seaweedfs_fid = str(row[7] or "")
            file_size_bytes = int(row[8] or 0)

            policy = self.get_policy_for_asset_type(asset_type)
            tier_duration_days = policy.get_tier_duration_days(current_tier)


            # Check if asset has exceeded tier duration
            if tier_transition_at is None:
                continue

            if tier_duration_days is None:
                # This policy does not configure a duration for this tier, so
                # it does not progress past it. Recorded once per tier rather
                # than per asset -- see the counter below.
                unconfigured += 1
                continue

            time_in_tier = (now - tier_transition_at).days

            if time_in_tier < tier_duration_days:
                continue

            # WP-61 Task 6. THE DELETE HOP IS REFUSED STRUCTURALLY, not because
            # the policy happens to leave `delete_after_days` NULL.
            #
            # Placed HERE, after eligibility and before `would_move`, on
            # purpose. After eligibility, so the count means "N assets were due
            # for deletion and were not deleted" rather than "N assets are
            # sitting in the archived tier" -- the first is the number an
            # operator needs before ever setting allow_delete, the second is
            # noise. Before `would_move`, because that mapping is a PREDICTION
            # of what a live pass moves, and a live pass will not move these.
            if next_tier == StorageTier.DELETE and not self._allow_delete:
                blocked += 1
                continue

            # This asset IS eligible. Record it in `would_move` before doing
            # anything, so a dry run and a live run count the same population
            # and the operator's dry-run output is a prediction of the live
            # pass rather than a separate calculation.
            hop = f"{current_tier.value}->{next_tier.value}"
            bucket = report.would_move.setdefault(hop, {"assets": 0, "bytes": 0})
            bucket["assets"] += 1
            bucket["bytes"] += file_size_bytes

            if self._dry_run:
                # WP-59 Task 7. Nothing is written in dry-run mode: not the
                # tier column, not the audit row, not a SeaweedFS call. The
                # eligibility decision above has already been made in full,
                # which is the part worth rehearsing.
                transition_count += 1
                continue

            if (
                self._max_transitions is not None
                and transition_count >= self._max_transitions
            ):
                report.capped = True
                self._log.warning(
                    "retention_migration_capped",
                    cap=self._max_transitions,
                    tier=current_tier.value,
                    consequence="remaining eligible assets were not transitioned",
                )
                break

            # Perform transition
            try:
                if next_tier == StorageTier.DELETE:
                    await self._delete_asset(
                        asset_id, storage_path, report
                    )
                    report.assets_deleted += 1
                else:
                    await self._transition_tier(
                        asset_id=asset_id,
                        storage_path=storage_path,
                        seaweedfs_fid=seaweedfs_fid,
                        from_tier=current_tier,
                        to_tier=next_tier,
                        policy_name=policy.name,
                        report=report,
                    )

                transition_count += 1

            except Exception as exc:
                # Per-asset, and it does NOT stop the tier -- one bad row should
                # not strand the rest. But it marks the run failed, because a
                # run that could not do what it was asked is not a successful
                # run however many other rows it managed.
                report.status = "failed"
                report.errors.append(
                    f"Transition failed for {asset_id}: {type(exc).__name__}: {exc}"
                )
                self._log.error(
                    "asset_transition_failed",
                    asset_id=asset_id,
                    from_tier=current_tier.value,
                    to_tier=next_tier.value,
                    error=str(exc),
                )

        if blocked:
            self._log.warning(
                "tier_hop_refused_delete_not_allowed",
                from_tier=current_tier.value,
                to_tier=next_tier.value,
                assets=blocked,
                consequence=(
                    "these assets are past their configured delete_after_days "
                    "and were NOT deleted: this run was not given "
                    "allow_delete=True. Nothing on the nightly schedule sets "
                    "it. Deleting them is a deliberate, attended pass."
                ),
            )
            report.policy_gaps[
                f"{current_tier.value}->{next_tier.value} (refused: allow_delete=False)"
            ] = blocked

        if unconfigured:
            self._log.info(
                "tier_hop_not_configured",
                from_tier=current_tier.value,
                to_tier=next_tier.value,
                assets=unconfigured,
                consequence=(
                    "the governing retention policy sets no duration for this "
                    "tier, so nothing progresses past it"
                ),
            )
            report.policy_gaps[f"{current_tier.value}->{next_tier.value}"] = unconfigured

        return transition_count

    async def _transition_tier(
        self,
        *,
        asset_id: str,
        storage_path: str,
        seaweedfs_fid: str,
        from_tier: StorageTier,
        to_tier: StorageTier,
        policy_name: str,
        report: MigrationReport,
    ) -> None:
        """
        Transition an asset from one tier to another.

        WHAT THIS ACTUALLY DOES, STATED HONESTLY (WP-59 Task 7).

        It moves the asset's TIER, which is a database fact, and it does not
        move any bytes. The old body POSTed to the filer path with
        ``X-Seaweedfs-Replication`` and ``X-Seaweedfs-Collection`` headers and
        called that a move. It is not one, twice over:

        * The filer namespace on this fleet is EMPTY. Measured 2026-08-26:
          ``GET /ivgs/`` on the filer answers 404 and the filer root lists no
          entries at all, while the volume servers hold 7 volumes and ~100
          files. Every asset is a VOLUME object addressed by fid;
          ``seaweedfs_path`` is a label the uploader writes into the row and
          never writes to the filer. So the POST addressed nothing.
        * SeaweedFS assigns a volume's COLLECTION and replication at
          ``/dir/assign`` time, when the object is first written. There is no
          filer header that relocates an existing object between collections.
          Genuinely moving the bytes means re-uploading them into a volume of
          the target collection and rewriting the fid -- which is a real
          feature, is not what this service was written to do, and is not being
          smuggled in under a header.

        So the physical placement is recorded as NOT PERFORMED rather than
        implied to have happened. A tier column that says ``cold`` over bytes
        that are still on the hot volume is a smaller lie than a log line that
        says the bytes moved, and it is the one the operator can see.
        """
        # Update database
        now = datetime.now(timezone.utc)
        try:
            async with self._db_session_factory() as session:
                async with session.begin():
                    from sqlalchemy import text

                    # NO `updated_at`. The `assets` table does not have one --
                    # verified against the live schema; its mutable-timestamp
                    # column is `tier_transition_at`, which is set here. The old
                    # statement named `updated_at` and would have failed with
                    # UndefinedColumn the moment the scan above was repaired.
                    await session.execute(
                        text(
                            "UPDATE assets SET "
                            "storage_tier = CAST(:tier AS storage_tier), "
                            "tier_transition_at = :now "
                            "WHERE id = CAST(:asset_id AS uuid)"
                        ),
                        {
                            "tier": to_tier.value,
                            "now": now,
                            "asset_id": asset_id,
                        },
                    )

            self._log.info(
                "tier_placement_not_performed",
                asset_id=asset_id,
                seaweedfs_fid=seaweedfs_fid,
                to_tier=to_tier.value,
                reason=(
                    "SeaweedFS assigns collection at write time; relocating an "
                    "existing fid between collections is not implemented"
                ),
            )

            record = TierTransitionRecord(
                asset_id=asset_id,
                from_tier=from_tier,
                to_tier=to_tier,
                policy_name=policy_name,
                storage_path=storage_path,
            )
            report.transitions.append(record)

            self._log.info(
                "tier_transition_completed",
                asset_id=asset_id,
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                policy_name=policy_name,
                physical_move="not_performed",
            )

        except Exception as exc:
            raise RuntimeError(
                f"Tier transition failed for {asset_id}: {exc}"
            ) from exc

    async def _delete_asset(
        self,
        asset_id: str,
        storage_path: str,
        report: MigrationReport,
    ) -> None:
        """
        Permanently delete an asset that has exceeded delete_after_days.

        1. Delete file from SeaweedFS
        2. Delete or mark database record
        3. Log to audit_log

        Args:
            asset_id: Asset UUID.
            storage_path: SeaweedFS file path.
            report: Running migration report.
        """
        # THREE DEFECTS IN THE OLD BODY, all of which would have fired on the
        # first row that ever reached this method (WP-59 Task 7):
        #
        #   status = 'deleted'      -- `assets` has NO `status` column.
        #   storage_tier = 'delete' -- the enum label is `deleted`.
        #   updated_at = NOW()      -- `assets` has no `updated_at` column.
        #
        # All three verified against the live schema on 2026-08-26. None had
        # ever been reached because the scan feeding this method could not run.
        #
        # The tombstone is `storage_tier = 'deleted'`, which is what the rest of
        # the system already reads as "not a live asset": `find_by_hash` and the
        # upload dedup both exclude it (asset_service.py:161, :302), so a
        # deleted-tier row is correctly invisible to dedup. The ROW is kept, not
        # dropped -- a tombstone that says which asset went is worth more than a
        # missing row, and dropping it would take the quality scores with it.
        try:
            async with self._db_session_factory() as session:
                async with session.begin():
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            "UPDATE assets SET "
                            "storage_tier = CAST('deleted' AS storage_tier), "
                            "tier_transition_at = now() "
                            "WHERE id = CAST(:asset_id AS uuid)"
                        ),
                        {"asset_id": asset_id},
                    )

            # The bytes are NOT removed here, deliberately. Retention-driven
            # byte deletion on this fleet has to go through the fid, and it has
            # to answer the same question project deletion answers -- is any
            # other live row pointing at this object? -- because a library
            # asset and a deduplicated asset can both share bytes with a row
            # that is not expiring. That guard lives in
            # `ProjectDeletionService.binary_manifest` (WP-59 Task 4) and this
            # service does not have it. Tombstoning the row makes the object an
            # orphan by construction, which is the shape `orphan_cleanup` exists
            # to sweep -- once it, too, is repaired (WP-59 report, Task 2).
            self._log.info(
                "asset_tombstoned",
                asset_id=asset_id,
                storage_path=storage_path,
                bytes_removed=False,
                reason=(
                    "byte removal needs the shared-object guard this service "
                    "does not have; the object becomes an orphan for the sweep"
                ),
            )

        except Exception as exc:
            raise RuntimeError(
                f"Asset deletion failed for {asset_id}: {exc}"
            ) from exc
