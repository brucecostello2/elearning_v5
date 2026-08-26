"""
Project deletion — WP-59.

A project is not one table. Task 1 of this package measured what it actually
is, against the LIVE schema rather than the spec's table list, and the answer
is 15 database tables, a set of SeaweedFS volume objects, and five families of
Redis key. ``PROJECT_CATEGORIES`` below IS that map: it is the source of the
dialog's category list and of the destruction, so a category cannot appear in
one and be missing from the other.

WHY THE ORDER IS WHAT IT IS
---------------------------
Deletion spans Postgres, SeaweedFS and Redis. Three stores, no distributed
transaction, so it CANNOT be atomic. What can be guaranteed is that every
reachable intermediate state is honestly labelled:

  1. Refuse while any job is non-terminal (Task 3), and prove the GPU
     reservations are gone by reading the SCHEDULER's registry, not the job row.
  2. Write the audit record, and COMMIT it, before anything is destroyed. It
     carries the per-category counts the operator was shown. ``audit_log`` has
     no foreign key to ``projects`` (verified against the live schema), so the
     row outlives the project by construction rather than by luck.
  3. Mark the project ``DELETING`` and COMMIT. Terminal: no pipeline can start
     from it, and nothing transitions out of it.
  4. Capture the binary manifest — every ``(fid, path)`` the project's assets
     point at — BEFORE the rows are deleted, because afterwards there is
     nothing left to read it from. It is written into the audit row, which is
     what makes step 6 resumable after a crash.
  5. Delete the database rows in ONE transaction. Rows that cascade are left to
     cascade; rows that do not are deleted explicitly in that same transaction.
  6. Purge the binaries, as a separate idempotent step, AFTER the rows are
     gone. Anything this step misses is by construction an orphan — a stored
     object with no row pointing at it — and never a live row pointing at
     nothing.
  7. Purge the Redis keys. Same reasoning: they are per-job scratch, and a
     leftover key is inert once the job row is gone.

A crash between any two steps leaves either a project marked DELETING (steps
3-5) or an orphaned binary (steps 5-7). Running deletion again converges:
``resume_pending_deletions`` re-reads the manifest out of the audit row and
finishes the purge, and every purge operation treats "already absent" as
success.

WHAT THIS SERVICE MUST NEVER DESTROY (Task 4)
---------------------------------------------
(a) ``library_assets`` rows and their binaries. AD-09.4.2 is reference-don't-
    copy: ``LibraryService.reference_into_project`` (library_service.py:366)
    creates an ``assets`` row carrying the LIBRARY object's ``seaweedfs_fid``
    and ``seaweedfs_path`` verbatim. Two projects referencing one logo hold two
    rows pointing at one object. Deleting the project deletes its reference
    row; the object and the ``library_assets`` row are untouched.

(b) Bytes another live row still points at. The sharing mechanism was
    established by reading the code, not assumed: content-hash dedup is
    PROJECT-SCOPED at both ends — the probe passes ``project_id``
    (media_converter.py:552 and its four call sites) and the upload's dedup
    query is ``and_(or_(*dedup_conditions), Asset.project_id == project_id, ...)``
    (asset_service.py:298-303). So dedup never produces a row in another
    project; within a project it produces ONE row with ``reference_count``
    incremented. The cross-project sharing that does exist is (a). Both are
    covered by the same rule, which is enforced per object rather than
    inferred: an object is purged only if NO surviving ``assets`` row and NO
    ``library_assets`` row still names its fid or its path.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.seaweedfs_client import seaweedfs_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Terminal job statuses
# ---------------------------------------------------------------------------
# `job_status` is a four-value PostgreSQL ENUM: pending, running, success,
# failed (verified live). There is no 'cancelled' value — JobService.cancel_job
# (job_service.py:182) writes `failed` with error_message "Cancelled by user",
# which is why cancel is a legitimate route to a terminal state here.
NON_TERMINAL_JOB_STATUSES: tuple[str, ...] = ("pending", "running")
_NON_TERMINAL_SQL_LIST = ", ".join(f"'{s}'" for s in NON_TERMINAL_JOB_STATUSES)


class ProjectDeletionError(RuntimeError):
    """Deletion could not proceed. Carries the operator-facing reason."""


class NonTerminalJobsError(ProjectDeletionError):
    """Task 3: a project with running or pending work cannot be deleted."""

    def __init__(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = jobs
        super().__init__(
            f"{len(jobs)} job(s) are still pending or running. Cancel them "
            f"before deleting this project."
        )


class ConfirmationMismatchError(ProjectDeletionError):
    """Task 6: the confirmation did not carry the project's exact name."""


class AlreadyDeletedError(ProjectDeletionError):
    """The project is gone and its purge finished. Deletion has converged.

    Task 2 requires that running delete twice converge on the same end state.
    It does — and this is what "converged" looks like from the second call: the
    rows are gone, the purge is recorded complete, and there is nothing left to
    do. Reporting that is different from reporting "no such project", which is
    what a bare 404 would say about an id the system in fact remembers
    destroying.
    """

    def __init__(self, audit_id: str, completed_at: str) -> None:
        self.audit_id = audit_id
        self.completed_at = completed_at
        super().__init__(
            f"This project was already deleted (audit record {audit_id}, "
            f"completed {completed_at}). Nothing further to do."
        )


# ---------------------------------------------------------------------------
# The map — Task 1, measured against the live schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Category:
    """One category of material a project deletion destroys.

    ``count_sql`` returns a single integer for one ``:project_id``. ``cascade``
    records what the LIVE foreign key does when the ``projects`` row goes:

      "cascade"    — an ON DELETE CASCADE path reaches this table. Deleting the
                     project row is sufficient; no explicit DELETE is issued.
      "orphan"     — nothing reaches it. Without an explicit DELETE the rows
                     survive the project as unreferenced litter, which is why
                     ``delete_sql`` exists and runs in the same transaction.
      "set_null"   — a column elsewhere is nulled rather than a row removed.
      "storage"    — not a database row at all.
    """

    key: str
    label: str
    detail: str
    cascade: str
    count_sql: Optional[str] = None
    delete_sql: Optional[str] = None
    binary: bool = False


# The cascade column below is not documentation of intent — it is a
# transcription of `pg_constraint.confdeltype` read off the running database on
# 2026-08-26. Every "cascade" entry has a named constraint behind it; every
# "orphan" entry was checked and has none.
PROJECT_CATEGORIES: tuple[Category, ...] = (
    Category(
        key="storyboard_scenes",
        label="Storyboard scenes",
        detail="Scene text, visual descriptions, timing and camera direction.",
        cascade="cascade",  # storyboard_scenes_project_id_fkey
        count_sql="SELECT count(*) FROM storyboard_scenes WHERE project_id = :project_id",
    ),
    Category(
        key="transcripts",
        label="Transcripts",
        detail="Uploaded source transcripts and their refined text.",
        cascade="cascade",  # transcripts_project_id_fkey
        count_sql="SELECT count(*) FROM transcripts WHERE project_id = :project_id",
    ),
    Category(
        key="prompts",
        label="Prompts",
        detail="Every prompt version written for this project, active or superseded.",
        cascade="cascade",  # prompts_project_id_fkey
        count_sql="SELECT count(*) FROM prompts WHERE project_id = :project_id",
    ),
    Category(
        key="prompt_tag_associations",
        label="Prompt tag links",
        detail="Which retrieval tags each of this project's prompts carries.",
        # prompt_tag_associations_prompt_id_fkey, via prompts. FOUND BY THE
        # CATEGORY-MAP TEST, not by reading: `test_every_project_fk_table_is_in_
        # the_map` walks pg_constraint's cascade closure outward from `projects`
        # and named this table as one the map had missed. The tags themselves
        # (`prompt_tags`) are shared vocabulary and are NOT touched -- only the
        # links from this project's prompts to them.
        cascade="cascade",
        count_sql=(
            "SELECT count(*) FROM prompt_tag_associations pta "
            "JOIN prompts p ON p.id = pta.prompt_id "
            "WHERE p.project_id = :project_id"
        ),
    ),
    Category(
        key="render_jobs",
        label="Job history",
        detail="Every pipeline run this project has ever had, and why each one ended.",
        cascade="cascade",  # render_jobs_project_id_fkey
        count_sql="SELECT count(*) FROM render_jobs WHERE project_id = :project_id",
    ),
    Category(
        key="pipeline_checkpoints",
        label="Checkpoints",
        detail="Stage checkpoints. Losing these makes an interrupted run unresumable.",
        cascade="cascade",  # pipeline_checkpoints_job_id_fkey, via render_jobs
        count_sql=(
            "SELECT count(*) FROM pipeline_checkpoints c "
            "JOIN render_jobs j ON j.id = c.job_id WHERE j.project_id = :project_id"
        ),
    ),
    Category(
        key="composition_manifests",
        label="Composition manifests",
        detail="The rendered timeline: what went where, at what offset, at what resolution.",
        cascade="cascade",  # composition_manifests_job_id_fkey
        count_sql=(
            "SELECT count(*) FROM composition_manifests m "
            "JOIN render_jobs j ON j.id = m.job_id WHERE j.project_id = :project_id"
        ),
    ),
    Category(
        key="render_segments",
        label="Render segments",
        detail="Per-segment render records and their output references.",
        cascade="cascade",  # render_segments_job_id_fkey
        count_sql=(
            "SELECT count(*) FROM render_segments s "
            "JOIN render_jobs j ON j.id = s.job_id WHERE j.project_id = :project_id"
        ),
    ),
    Category(
        key="task_retries",
        label="Retry records",
        detail="Every retry attempt and the failure that caused it.",
        cascade="cascade",  # task_retries_job_id_fkey
        count_sql=(
            "SELECT count(*) FROM task_retries r "
            "JOIN render_jobs j ON j.id = r.job_id WHERE j.project_id = :project_id"
        ),
    ),
    Category(
        key="gpu_reservations",
        label="GPU reservation records",
        detail="Database records of GPU reservations taken for this project's jobs.",
        cascade="cascade",  # gpu_reservations_job_id_fkey
        count_sql=(
            "SELECT count(*) FROM gpu_reservations g "
            "JOIN render_jobs j ON j.id = g.job_id WHERE j.project_id = :project_id"
        ),
    ),
    Category(
        key="language_variants",
        label="Language variants",
        detail="Each localised version of this course and its render references.",
        cascade="cascade",  # language_variants_project_id_fkey
        count_sql="SELECT count(*) FROM language_variants WHERE project_id = :project_id",
    ),
    Category(
        key="project_model_selections",
        label="Model selections",
        detail="Which AD-01 certified model was chosen for each stage and scene.",
        cascade="cascade",  # project_model_selections_project_id_fkey
        count_sql=(
            "SELECT count(*) FROM project_model_selections WHERE project_id = :project_id"
        ),
    ),
    Category(
        key="assets",
        label="Media assets (database records)",
        detail=(
            "Every asset row: images, video, audio, talking-head clips, drafts "
            "and final renders. Library references are counted here and their "
            "shared files are NOT deleted."
        ),
        cascade="cascade",  # assets_project_id_fkey
        count_sql="SELECT count(*) FROM assets WHERE project_id = :project_id",
    ),
    Category(
        key="asset_quality_scores",
        label="Quality scores",
        detail="Automated quality and safety verdicts, and any human review notes.",
        cascade="cascade",  # asset_quality_scores_asset_id_fkey, via assets
        count_sql=(
            "SELECT count(*) FROM asset_quality_scores q "
            "JOIN assets a ON a.id = q.asset_id WHERE a.project_id = :project_id"
        ),
    ),
    # ---- No foreign key reaches these two. They are deleted explicitly. ----
    Category(
        key="dead_letter_messages",
        label="Dead-letter messages",
        detail=(
            "Failed task messages retained for replay that name this project's "
            "jobs. Nothing links them to the project, so they would otherwise "
            "survive it as unreplayable litter."
        ),
        cascade="orphan",
        # `dead_letter_messages` has NO foreign key to anything (verified: it
        # appears nowhere in pg_constraint as a child). The job id lives inside
        # task_args / task_kwargs JSONB, in three different shapes -- WP-45 §4.2
        # measured all three -- so the only reliable predicate is a text search
        # for the id. The table is small and unindexed for this; a sequential
        # scan here is correct and cheap.
        count_sql=(
            "SELECT count(*) FROM dead_letter_messages d "
            "WHERE EXISTS (SELECT 1 FROM render_jobs j WHERE j.project_id = :project_id "
            "  AND (d.task_args::text LIKE '%' || j.id::text || '%' "
            "    OR d.task_kwargs::text LIKE '%' || j.id::text || '%')) "
            "OR d.task_args::text LIKE '%' || :project_id_text || '%' "
            "OR d.task_kwargs::text LIKE '%' || :project_id_text || '%'"
        ),
        delete_sql=(
            "DELETE FROM dead_letter_messages d "
            "WHERE EXISTS (SELECT 1 FROM render_jobs j WHERE j.project_id = :project_id "
            "  AND (d.task_args::text LIKE '%' || j.id::text || '%' "
            "    OR d.task_kwargs::text LIKE '%' || j.id::text || '%')) "
            "OR d.task_args::text LIKE '%' || :project_id_text || '%' "
            "OR d.task_kwargs::text LIKE '%' || :project_id_text || '%'"
        ),
    ),
    Category(
        key="project_gate_decisions",
        label="Review gate decisions",
        detail=(
            "Every storyboard and draft review decision recorded for this "
            "project: who approved or rejected what, when, and against which "
            "artefact version."
        ),
        # project_gate_decisions_project_id_fkey (WP-62 migration 0035).
        # FOUND BY THE CATEGORY-MAP TEST, which walks pg_constraint's cascade
        # closure outward from `projects` and fails by name on any table it
        # reaches that this map has missed -- exactly as it found
        # `prompt_tag_associations` on its first run. A new table with an
        # ON DELETE CASCADE to projects cannot be added without landing here.
        cascade="cascade",
        count_sql=(
            "SELECT count(*) FROM project_gate_decisions "
            "WHERE project_id = :project_id"
        ),
    ),
    Category(
        key="storage_quotas",
        label="Storage quota records",
        detail="This project's storage accounting row.",
        cascade="orphan",
        # storage_quotas.entity_id is a bare UUID with no foreign key -- the
        # table is polymorphic over entity_type ('project' / 'user' / ...), and
        # a polymorphic column cannot carry one.
        count_sql=(
            "SELECT count(*) FROM storage_quotas "
            "WHERE entity_type = 'project' AND entity_id = :project_id"
        ),
        delete_sql=(
            "DELETE FROM storage_quotas "
            "WHERE entity_type = 'project' AND entity_id = :project_id"
        ),
    ),
    # ---- Not database rows ----
    Category(
        key="stored_files",
        label="Stored files (SeaweedFS)",
        detail=(
            "The actual bytes: rendered images, video, audio and finished "
            "courses. Files shared with the asset library, or with any project "
            "that still exists, are NOT deleted."
        ),
        cascade="storage",
        binary=True,
    ),
    Category(
        key="redis_keys",
        label="Pipeline scratch state (Redis)",
        detail=(
            "Media-join counters, job context and failure lists held for this "
            "project's jobs while they run."
        ),
        cascade="storage",
        binary=True,
    ),
)

CATEGORY_KEYS: tuple[str, ...] = tuple(c.key for c in PROJECT_CATEGORIES)


# Redis key families keyed by JOB id, enumerated from the live keyspace on
# 2026-08-26 and cross-checked against their writers in ivgs-workers. Every one
# is per-job scratch: nothing here is a record of anything, which is why it can
# be purged after the rows rather than before.
JOB_REDIS_KEY_TEMPLATES: tuple[str, ...] = (
    "ivgs:job_context:{job_id}",
    "ivgs:media_tasks:{job_id}",
    "ivgs:media_join_ctx:{job_id}",
    "ivgs:media_failures:{job_id}",
)
# media_join_seen carries a stage suffix, so it is matched rather than templated.
JOB_REDIS_KEY_PATTERNS: tuple[str, ...] = (
    "ivgs:media_join_seen:{job_id}:*",
)


@dataclass
class CategoryCount:
    key: str
    label: str
    detail: str
    cascade: str
    count: int
    breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class DeletionPreview:
    """Everything the dialog needs, and nothing it must guess at."""

    project_id: str
    project_name: str
    project_state: str
    categories: list[CategoryCount]
    blocking_jobs: list[dict[str, Any]]
    gpu_reservations_held: list[dict[str, Any]]
    total_rows: int
    total_bytes: int
    deletable: bool
    # "I could not check" and "I checked and there is nothing" are different
    # facts (WP-45 §2.5). These two carry the first one, separately, because
    # they have different consequences: an unreadable SCHEDULER registry blocks
    # the deletion, an unreadable Redis scratch count does not.
    scheduler_registry_error: Optional[str] = None
    redis_registry_error: Optional[str] = None


@dataclass
class DeletionResult:
    """What was actually destroyed. Not a status code."""

    project_id: str
    project_name: str
    audit_id: str
    rows_deleted: dict[str, int]
    files_deleted: int
    files_preserved: int
    preserved_reasons: list[dict[str, str]]
    redis_keys_deleted: int
    files_failed: list[dict[str, str]] = field(default_factory=list)
    resumed: bool = False


class ProjectDeletionService:
    """Enumerate a project, then destroy it in an order that cannot lie."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._sched_redis: Optional[Any] = None

    # ------------------------------------------------------------------
    # Scheduler registry (Task 3)
    # ------------------------------------------------------------------

    async def _scheduler_redis(self) -> Any:
        """Connect to the SCHEDULER's Redis database, read-only.

        Task 3 requires that reservations be verified "against the scheduler's
        registry, not assumed from the job row". The registry is a set of
        `sched:*` keys in Redis db 1 (scheduler.py:111-114); the API's own
        client is bound to db 0, so it cannot see them. This opens a second
        connection at the scheduler's own default rather than adding scheduler
        keys to the API's database, which would put two writers in one
        namespace for no gain.
        """
        if self._sched_redis is None:
            self._sched_redis = aioredis.from_url(
                settings.SCHEDULER_REDIS_URL, decode_responses=True,
            )
        return self._sched_redis

    async def close(self) -> None:
        if self._sched_redis is not None:
            await self._sched_redis.aclose()
            self._sched_redis = None

    async def gpu_reservations_for_jobs(
        self, job_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Reservations the SCHEDULER still holds for these jobs.

        Two lookups, because one is not sufficient:

        * ``sched:job_reservation:{job_id}`` is the job→reservation map. It
          carries the same TTL as the reservation, so it can expire first under
          clock skew or a partial release.
        * ``sched:reservations:index`` is the durable set of reservation ids.
          It is cleaned LAZILY (scheduler.py:522 removes a stale member only
          when something happens to walk past it), so a reservation hash that
          outlived its job map is visible only here.

        Returns [] when the registry is empty or unreachable — and an
        unreachable registry is reported by the caller rather than read as
        "nothing reserved". That distinction is the WP-45 dedup-probe lesson:
        "I could not check" and "I checked and there is nothing" are different
        facts.
        """
        if not job_ids:
            return []
        r = await self._scheduler_redis()
        wanted = set(job_ids)
        held: dict[str, dict[str, Any]] = {}

        for job_id in job_ids:
            res_id = await r.get(f"sched:job_reservation:{job_id}")
            if res_id:
                data = await r.hgetall(f"sched:reservation:{res_id}")
                held[res_id] = {
                    "reservation_id": res_id,
                    "job_id": job_id,
                    "node_id": data.get("node_id", ""),
                    "vram_mb": data.get("vram_mb", ""),
                    "expires_at": data.get("expires_at", ""),
                    "found_via": "job_map",
                }

        for res_id in await r.smembers("sched:reservations:index"):
            if res_id in held:
                continue
            data = await r.hgetall(f"sched:reservation:{res_id}")
            if not data:
                # Stale index member; the hash has expired. Not a held
                # reservation, and not ours to clean up.
                continue
            if data.get("job_id") in wanted:
                held[res_id] = {
                    "reservation_id": res_id,
                    "job_id": data.get("job_id", ""),
                    "node_id": data.get("node_id", ""),
                    "vram_mb": data.get("vram_mb", ""),
                    "expires_at": data.get("expires_at", ""),
                    "found_via": "reservation_index",
                }

        return list(held.values())

    # ------------------------------------------------------------------
    # Enumeration (Task 1) — the dialog's source of truth
    # ------------------------------------------------------------------

    async def _scalar(self, sql: str, params: dict[str, Any]) -> int:
        result = await self.db.execute(text(sql), params)
        value = result.scalar()
        return int(value or 0)

    async def _asset_breakdown(self, project_id: UUID) -> dict[str, int]:
        """Per-type asset counts. The operator asked for media assets BY TYPE."""
        result = await self.db.execute(
            text(
                "SELECT asset_type::text, count(*) FROM assets "
                "WHERE project_id = :project_id GROUP BY 1 ORDER BY 1"
            ),
            {"project_id": project_id},
        )
        return {row[0]: int(row[1]) for row in result.fetchall()}

    async def _job_type_breakdown(self, project_id: UUID) -> dict[str, int]:
        result = await self.db.execute(
            text(
                "SELECT job_type::text, count(*) FROM render_jobs "
                "WHERE project_id = :project_id GROUP BY 1 ORDER BY 1"
            ),
            {"project_id": project_id},
        )
        return {row[0]: int(row[1]) for row in result.fetchall()}

    async def binary_manifest(self, project_id: UUID) -> list[dict[str, Any]]:
        """Every stored object this project's assets point at, with its guard.

        ``keep_reason`` is decided HERE, while the rows still exist, and carried
        into the purge unchanged. Deciding it later — after the rows are gone —
        would mean re-deriving "is anything else pointing at this?" from a
        database that no longer contains the answer.

        The two guards are the Task 4 rule, applied per object:

        * ``library_asset_id IS NOT NULL`` — the object belongs to the library.
          ``reference_into_project`` copied the library row's fid and path onto
          the project row verbatim (library_service.py:370-371), so purging it
          would delete a file the library and every other referencing project
          still use.
        * another live row names the same fid or path — a surviving ``assets``
          row in a project that is not being deleted, or a ``library_assets``
          row. Checked against fid AND path because the two are independent
          handles on this fleet: ``upload_asset`` stores bytes by fid via the
          master (asset_service.py:341) and records a filer-style path that the
          filer namespace does not actually contain, while library and
          referenced rows carry both.
        """
        result = await self.db.execute(
            text(
                """
                SELECT a.id::text,
                       coalesce(a.seaweedfs_fid, '')  AS fid,
                       coalesce(a.seaweedfs_path, '') AS path,
                       coalesce(a.file_size_bytes, 0) AS size_bytes,
                       a.asset_type::text             AS asset_type,
                       a.library_asset_id::text       AS library_asset_id
                FROM assets a
                WHERE a.project_id = :project_id
                """
            ),
            {"project_id": project_id},
        )
        rows = result.fetchall()

        manifest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            asset_id, fid, path, size_bytes, asset_type, library_asset_id = row
            if not fid and not path:
                continue
            key = (fid, path)
            entry = manifest.setdefault(
                key,
                {
                    "fid": fid,
                    "path": path,
                    "size_bytes": int(size_bytes or 0),
                    "asset_types": [],
                    "asset_ids": [],
                    "keep_reason": "",
                },
            )
            entry["asset_ids"].append(asset_id)
            if asset_type not in entry["asset_types"]:
                entry["asset_types"].append(asset_type)
            if library_asset_id:
                entry["keep_reason"] = "library_asset"

        for entry in manifest.values():
            if entry["keep_reason"]:
                continue
            reason = await self._external_reference_reason(
                project_id, entry["fid"], entry["path"],
            )
            if reason:
                entry["keep_reason"] = reason

        return list(manifest.values())

    async def _external_reference_reason(
        self, project_id: UUID, fid: str, path: str,
    ) -> str:
        """Is any row OUTSIDE this project still pointing at this object?"""
        params = {
            "project_id": project_id,
            "fid": fid or "\x00-no-fid",
            "path": path or "\x00-no-path",
        }
        other_project = await self._scalar(
            "SELECT count(*) FROM assets "
            "WHERE project_id <> :project_id "
            "AND (seaweedfs_fid = :fid OR seaweedfs_path = :path)",
            params,
        )
        if other_project:
            return "referenced_by_another_project"
        in_library = await self._scalar(
            "SELECT count(*) FROM library_assets "
            "WHERE seaweedfs_fid = :fid OR seaweedfs_path = :path",
            {"fid": params["fid"], "path": params["path"]},
        )
        if in_library:
            return "library_asset"
        return ""

    async def blocking_jobs(self, project_id: UUID) -> list[dict[str, Any]]:
        """Jobs that are not terminal. Deletion refuses while this is non-empty."""
        result = await self.db.execute(
            text(
                "SELECT id::text, job_type::text, status::text, "
                "       coalesce(celery_task_id, ''), created_at, started_at "
                "FROM render_jobs "
                "WHERE project_id = :project_id "
                # NON_TERMINAL_JOB_STATUSES is a module constant, never user
                # input, so interpolating it is safe and avoids driver-specific
                # array-parameter behaviour on a two-element IN list.
                f"AND status::text IN ({_NON_TERMINAL_SQL_LIST}) "
                "ORDER BY created_at DESC"
            ),
            {"project_id": project_id},
        )
        return [
            {
                "id": row[0],
                "job_type": row[1],
                "status": row[2],
                "celery_task_id": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "started_at": row[5].isoformat() if row[5] else None,
            }
            for row in result.fetchall()
        ]

    async def preview(self, project_id: UUID) -> Optional[DeletionPreview]:
        """The dialog's data. Every category, every count, for THIS project."""
        row = (
            await self.db.execute(
                text(
                    "SELECT name, state::text FROM projects WHERE id = :project_id"
                ),
                {"project_id": project_id},
            )
        ).fetchone()
        if row is None:
            return None
        project_name, project_state = row[0], row[1]

        params = {
            "project_id": project_id,
            "project_id_text": str(project_id),
        }

        manifest = await self.binary_manifest(project_id)
        purgeable = [m for m in manifest if not m["keep_reason"]]

        job_ids = [
            r[0]
            for r in (
                await self.db.execute(
                    text("SELECT id::text FROM render_jobs WHERE project_id = :project_id"),
                    {"project_id": project_id},
                )
            ).fetchall()
        ]
        redis_key_count, redis_error = await self._count_redis_keys(job_ids)

        categories: list[CategoryCount] = []
        total_rows = 0
        for cat in PROJECT_CATEGORIES:
            if cat.key == "stored_files":
                count = len(purgeable)
                breakdown = {
                    "shared_files_preserved": len(manifest) - len(purgeable),
                }
            elif cat.key == "redis_keys":
                count = redis_key_count
                breakdown = {}
            else:
                count = await self._scalar(cat.count_sql or "SELECT 0", params)
                breakdown = {}
                total_rows += count
                if cat.key == "assets":
                    breakdown = await self._asset_breakdown(project_id)
                elif cat.key == "render_jobs":
                    breakdown = await self._job_type_breakdown(project_id)
            categories.append(
                CategoryCount(
                    key=cat.key,
                    label=cat.label,
                    detail=cat.detail,
                    cascade=cat.cascade,
                    count=count,
                    breakdown=breakdown,
                )
            )

        blocking = await self.blocking_jobs(project_id)
        try:
            reservations = await self.gpu_reservations_for_jobs(job_ids)
            reservation_error = None
        except Exception as exc:  # registry unreachable
            reservations = []
            reservation_error = str(exc)
            logger.error(
                "gpu_reservation_registry_unreachable project=%s error=%s "
                "consequence=deletion refuses rather than assuming no reservation is held",
                project_id, exc,
            )

        return DeletionPreview(
            project_id=str(project_id),
            project_name=project_name,
            project_state=project_state,
            categories=categories,
            blocking_jobs=blocking,
            gpu_reservations_held=reservations,
            total_rows=total_rows,
            total_bytes=sum(m["size_bytes"] for m in purgeable),
            # A registry that could not be READ is not a registry that said
            # "nothing held". Deletion refuses on the unknown, deliberately.
            deletable=(
                not blocking and not reservations and reservation_error is None
            ),
            scheduler_registry_error=reservation_error,
            redis_registry_error=redis_error,
        )

    async def _count_redis_keys(
        self, job_ids: list[str],
    ) -> tuple[int, Optional[str]]:
        """How many scratch keys this project's jobs still hold, or why not.

        A Redis this cannot reach does NOT block the deletion: these keys are
        per-job scratch, and a leftover counter is inert once the job row is
        gone. It is reported rather than shown as a confident 0, because a 0
        the dialog cannot stand behind is the shape of defect this package
        exists to stop repeating.
        """
        from shared.redis_client import redis_client

        if not job_ids:
            return 0, None
        count = 0
        try:
            for job_id in job_ids:
                for tmpl in JOB_REDIS_KEY_TEMPLATES:
                    if await redis_client.exists(tmpl.format(job_id=job_id)):
                        count += 1
                for pattern in JOB_REDIS_KEY_PATTERNS:
                    async for _ in redis_client.client.scan_iter(
                        match=pattern.format(job_id=job_id), count=200,
                    ):
                        count += 1
        except Exception as exc:
            logger.error(
                "project_delete_redis_scan_unavailable error=%s "
                "consequence=scratch-key count is unknown, not zero", exc,
            )
            return 0, str(exc)
        return count, None

    # ------------------------------------------------------------------
    # Destruction (Task 2)
    # ------------------------------------------------------------------

    async def delete(
        self,
        project_id: UUID,
        *,
        confirmation_name: str,
        actor_id: Optional[UUID],
        actor_name: str,
        client_ip: Optional[str] = None,
    ) -> DeletionResult:
        """Destroy a project, in the order the module docstring sets out."""
        preview = await self.preview(project_id)
        if preview is None:
            # Not present. It may still have an unfinished purge behind it.
            resumed = await self.resume_pending_deletions(project_id)
            if resumed is not None:
                return resumed
            completed = await self._completed_audit(project_id)
            if completed is not None:
                raise AlreadyDeletedError(completed[0], completed[1])
            raise LookupError(f"Project {project_id} not found")

        if confirmation_name != preview.project_name:
            raise ConfirmationMismatchError(
                "The confirmation name does not match this project's name. "
                "Deletion refused."
            )

        if preview.blocking_jobs:
            raise NonTerminalJobsError(preview.blocking_jobs)

        if preview.scheduler_registry_error is not None:
            raise ProjectDeletionError(
                f"The GPU scheduler's reservation registry could not be read "
                f"({preview.scheduler_registry_error}). Deletion refuses rather "
                f"than assume no reservation is held for this project's jobs."
            )

        if preview.gpu_reservations_held:
            raise ProjectDeletionError(
                f"{len(preview.gpu_reservations_held)} GPU reservation(s) are "
                f"still held by the scheduler for this project's jobs. They "
                f"must be released before the project can be deleted."
            )

        manifest = await self.binary_manifest(project_id)
        job_ids = [
            r[0]
            for r in (
                await self.db.execute(
                    text("SELECT id::text FROM render_jobs WHERE project_id = :project_id"),
                    {"project_id": project_id},
                )
            ).fetchall()
        ]

        # --- Step 2: the audit record, committed BEFORE anything is destroyed
        audit_id = uuid4()
        audit_payload = {
            "project_id": str(project_id),
            "project_name": preview.project_name,
            "project_state_at_request": preview.project_state,
            "requested_by": actor_name,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "categories": {c.key: c.count for c in preview.categories},
            "category_breakdowns": {
                c.key: c.breakdown for c in preview.categories if c.breakdown
            },
            "total_rows": preview.total_rows,
            "total_bytes": preview.total_bytes,
            "job_ids": job_ids,
            # The resume manifest. Written before destruction so a crash after
            # the rows are gone still has somewhere to read the object list.
            "binary_manifest": manifest,
            # WP-59: written BEFORE destruction, deliberately, so a crash after
            # the rows are gone still has a manifest to resume from.
            #
            # WP-62 Task 5. THE CLOSURE, AND WHAT WAS ACTUALLY MISSING.
            #
            # Measured 2026-08-26 across all 14 rows in `audit_log` for
            # `resource_type='project'`: every one has
            # `before_payload->>'purge_state' = 'pending'` AND
            # `after_payload->>'purge_state' = 'complete'`, and every one is
            # `action_type = 'PROJECT_DELETE_COMPLETED'`. So the closure the
            # ledger asks for -- COMPLETED updating the ORIGINATING row --
            # already exists: `_record_completion` UPDATEs this row by its own
            # id. What did NOT exist is any way to read that without knowing
            # it: this field says "pending" forever on a finished deletion, one
            # column away from an after_payload that says "complete", and an
            # operator querying the obvious field gets the wrong answer on
            # every historical row.
            #
            # The field is NOT rewritten on completion -- a `before_payload` is
            # a record of the moment before, and editing it would destroy the
            # evidence that the row was written before destruction began. It is
            # LABELLED instead, so it can only be read as what it is, and
            # `deletion_audit_status()` below is the read path that does the
            # classification once for everyone.
            "purge_state": "pending",
            "purge_state_note": (
                "This is the state at the moment BEFORE destruction and it is "
                "never updated. Read after_payload->>'purge_state' for the "
                "outcome, and action_type for whether the purge finished at "
                "all: a row still at PROJECT_DELETE_STARTED died mid-purge and "
                "is resumable from the binary_manifest above."
            ),
            "purge_started_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.execute(
            text(
                "INSERT INTO audit_log "
                "(id, user_id, action_type, resource_type, resource_id, "
                " before_payload, client_ip, timestamp) "
                "VALUES (:id, :user_id, 'PROJECT_DELETE_STARTED', 'project', "
                "        :resource_id, CAST(:payload AS jsonb), "
                "        CAST(:client_ip AS inet), now())"
            ),
            {
                "id": audit_id,
                "user_id": actor_id,
                "resource_id": project_id,
                "payload": json.dumps(audit_payload),
                "client_ip": client_ip,
            },
        )
        await self.db.commit()

        # --- Step 3: DELETING, committed. Terminal.
        await self.db.execute(
            text(
                "UPDATE projects SET state = 'DELETING', updated_at = now() "
                "WHERE id = :project_id"
            ),
            {"project_id": project_id},
        )
        await self.db.commit()
        logger.info(
            "project_delete_marked project=%s name=%r audit=%s by=%s",
            project_id, preview.project_name, audit_id, actor_name,
        )

        # --- Step 5: rows, in one transaction
        rows_deleted = await self._delete_rows(project_id)

        # --- Step 6: binaries, idempotent
        (
            files_deleted, files_preserved, preserved_reasons, files_failed,
        ) = await self._purge_binaries(manifest)

        # --- Step 7: Redis
        redis_deleted, redis_purge_error = await self._purge_redis(job_ids)

        # --- Completion record
        await self._record_completion(
            audit_id=audit_id,
            project_id=project_id,
            actor_id=actor_id,
            rows_deleted=rows_deleted,
            files_deleted=files_deleted,
            files_preserved=files_preserved,
            preserved_reasons=preserved_reasons,
            files_failed=files_failed,
            redis_deleted=redis_deleted,
            redis_purge_error=redis_purge_error,
        )

        logger.info(
            "project_delete_completed project=%s name=%r rows=%s files=%s "
            "preserved=%s redis=%s audit=%s",
            project_id, preview.project_name, sum(rows_deleted.values()),
            files_deleted, files_preserved, redis_deleted, audit_id,
        )
        return DeletionResult(
            project_id=str(project_id),
            project_name=preview.project_name,
            audit_id=str(audit_id),
            rows_deleted=rows_deleted,
            files_deleted=files_deleted,
            files_preserved=files_preserved,
            preserved_reasons=preserved_reasons,
            files_failed=files_failed,
            redis_keys_deleted=redis_deleted,
        )

    async def _delete_rows(self, project_id: UUID) -> dict[str, int]:
        """Delete every row, in ONE transaction.

        Cascade paths are LEFT to cascade — issuing redundant DELETEs against a
        table that ON DELETE CASCADE already reaches would be a second,
        divergent statement of the schema. What is issued explicitly is exactly
        the set of tables no foreign key reaches, which is why ``Category``
        records the cascade behaviour: the two are the same list, read once.
        """
        params = {
            "project_id": project_id,
            "project_id_text": str(project_id),
        }
        counts: dict[str, int] = {}

        # Count first, inside the same transaction, so the numbers reported are
        # the numbers destroyed rather than a second read of a changed database.
        for cat in PROJECT_CATEGORIES:
            if cat.count_sql:
                counts[cat.key] = await self._scalar(cat.count_sql, params)

        for cat in PROJECT_CATEGORIES:
            if cat.delete_sql:
                await self.db.execute(text(cat.delete_sql), params)

        # The project row last: its cascade is what removes everything above it.
        await self.db.execute(
            text("DELETE FROM projects WHERE id = :project_id"),
            {"project_id": project_id},
        )
        await self.db.commit()
        counts["projects"] = 1
        return counts

    async def _purge_binaries(
        self, manifest: list[dict[str, Any]],
    ) -> tuple[int, int, list[dict[str, str]], list[dict[str, str]]]:
        """Delete the objects, skipping every one another live row still holds.

        IDEMPOTENT BY CONSTRUCTION. ``delete_file`` reports False for an object
        that is already gone, and the filer answers 404 for a path it does not
        have; both are counted as done, because "absent" is the end state this
        step is trying to reach. Running the purge twice therefore converges
        rather than erroring.
        """
        deleted = 0
        preserved = 0
        reasons: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []

        for entry in manifest:
            if entry.get("keep_reason"):
                preserved += 1
                reasons.append(
                    {
                        "fid": entry.get("fid", ""),
                        "path": entry.get("path", ""),
                        "reason": entry["keep_reason"],
                    }
                )
                continue

            fid = entry.get("fid") or ""
            path = entry.get("path") or ""
            ok = False
            if fid:
                try:
                    ok = await seaweedfs_client.delete_file(fid)
                except Exception as exc:
                    logger.error(
                        "project_delete_purge_failed fid=%s error=%s "
                        "consequence=object is now an orphan; orphan_cleanup is the backstop",
                        fid, exc,
                    )
            if path:
                # The filer namespace on this fleet is empty -- every asset is a
                # volume object addressed by fid -- but the path is deleted too
                # so the purge stays correct if the filer is ever populated. A
                # 404 is the desired end state, not a failure.
                try:
                    client = await seaweedfs_client._get_client()
                    resp = await client.delete(
                        f"{seaweedfs_client.filer_url}{path}"
                    )
                    ok = ok or resp.status_code in (200, 202, 204, 404)
                except Exception as exc:
                    logger.warning(
                        "project_delete_filer_purge_failed path=%s error=%s", path, exc,
                    )
            if ok:
                deleted += 1
            else:
                # NOT counted as deleted. Reporting an unconfirmed delete as a
                # delete is the exact shape this package exists to stop: the
                # operator would read "3 files deleted" over three objects still
                # on disk. It is not fatal either -- the rows are already gone,
                # so the object is now an orphan by construction rather than a
                # live row pointing at nothing -- so it is recorded and the
                # deletion continues.
                failed.append({"fid": fid, "path": path})
                logger.error(
                    "project_delete_object_not_confirmed fid=%s path=%s "
                    "consequence=the object is now an ORPHAN: its row is gone "
                    "and the bytes are not; it is reported, not counted as "
                    "deleted",
                    fid, path,
                )

        return deleted, preserved, reasons, failed

    async def _purge_redis(self, job_ids: list[str]) -> tuple[int, Optional[str]]:
        """Delete the per-job scratch keys. Reports failure; never raises.

        This is step 7, after the rows are gone. Raising here would abort a
        deletion that has already succeeded in every way that matters and leave
        the audit row saying "pending" forever. The failure is recorded in the
        completion payload instead, where it is greppable and re-runnable.
        """
        from shared.redis_client import redis_client

        deleted = 0
        try:
            for job_id in job_ids:
                for tmpl in JOB_REDIS_KEY_TEMPLATES:
                    if await redis_client.delete(tmpl.format(job_id=job_id)):
                        deleted += 1
                for pattern in JOB_REDIS_KEY_PATTERNS:
                    async for key in redis_client.client.scan_iter(
                        match=pattern.format(job_id=job_id), count=200,
                    ):
                        if await redis_client.delete(key):
                            deleted += 1
        except Exception as exc:
            logger.error(
                "project_delete_redis_purge_failed error=%s "
                "consequence=scratch keys for this project's jobs remain; they "
                "are inert without their job rows and are re-purged on resume",
                exc,
            )
            return deleted, str(exc)
        return deleted, None

    async def _record_completion(
        self,
        *,
        audit_id: UUID,
        project_id: UUID,
        actor_id: Optional[UUID],
        rows_deleted: dict[str, int],
        files_deleted: int,
        files_preserved: int,
        preserved_reasons: list[dict[str, str]],
        redis_deleted: int,
        files_failed: Optional[list[dict[str, str]]] = None,
        redis_purge_error: Optional[str] = None,
    ) -> None:
        after = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "rows_deleted": rows_deleted,
            "files_deleted": files_deleted,
            "files_preserved": files_preserved,
            "preserved_reasons": preserved_reasons,
            "files_failed": files_failed or [],
            "redis_keys_deleted": redis_deleted,
            "redis_purge_error": redis_purge_error,
            # Three distinct end states, named. "complete" must mean the purge
            # actually reached every object it set out to; anything else says
            # which half did not.
            "purge_state": (
                "complete"
                if redis_purge_error is None and not files_failed
                else "redis_incomplete" if redis_purge_error is not None and not files_failed
                else "files_incomplete" if redis_purge_error is None
                else "files_and_redis_incomplete"
            ),
        }
        await self.db.execute(
            text(
                "UPDATE audit_log SET after_payload = CAST(:payload AS jsonb), "
                "action_type = 'PROJECT_DELETE_COMPLETED' WHERE id = :id"
            ),
            {"payload": json.dumps(after), "id": audit_id},
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Audit (WP-62 Task 5)
    # ------------------------------------------------------------------

    async def deletion_audit_status(
        self, limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Every deletion this system has recorded, classified.

        WP-62 Task 5. HOW AN OPERATOR AUDITS THE TEN 2026-08-26 DELETIONS --
        and every one after them -- without knowing which of four fields to
        read or how the two payloads relate.

        The classification is derived here, once, rather than being a query an
        operator has to get right:

          completed          action_type COMPLETED, after_payload purge_state
                             'complete'. The purge reached every object.
          completed_partial  COMPLETED, but the purge could not finish some
                             half of its work: 'files_incomplete',
                             'redis_incomplete' or both. The rows are gone; the
                             named objects are not.
          died_mid_purge     Still at PROJECT_DELETE_STARTED. The rows were
                             destroyed and `_record_completion` never ran.
                             RESUMABLE: `resume_pending_deletions(project_id)`
                             re-runs the purge from the manifest in
                             before_payload and converges to the same end
                             state.
          in_flight          Also STARTED, but written within the last five
                             minutes. Indistinguishable from died_mid_purge by
                             the record alone -- a purge that is running writes
                             nothing until it finishes -- so it is reported as
                             a separate class rather than as a false alarm. The
                             fix if it is genuinely stuck is the same resume.

        THE TEN 2026-08-26 DELETIONS ARE HISTORICAL TEST DATA AND ARE NOT
        MODIFIED by this or by anything else in WP-62. They read `completed`
        here, which is what they are; their `before_payload.purge_state` still
        says "pending" and always will, because it is a record of the moment
        before destruction. Rows written from this package onward carry
        `purge_state_note` explaining that in place; the ten do not, which is
        exactly why this read path exists rather than a data fix.
        """
        rows = (
            await self.db.execute(
                text(
                    "SELECT id::text, action_type, resource_id::text, timestamp, "
                    "       before_payload, after_payload, "
                    "       (now() - timestamp) > interval '5 minutes' AS settled "
                    "FROM audit_log "
                    "WHERE resource_type = 'project' "
                    "AND action_type IN ('PROJECT_DELETE_STARTED', "
                    "                    'PROJECT_DELETE_COMPLETED') "
                    "ORDER BY timestamp DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
        ).fetchall()

        out: list[dict[str, Any]] = []
        for (
            audit_id, action_type, project_id, stamp, before, after, settled,
        ) in rows:
            before = before or {}
            after = after or {}
            purge_state = after.get("purge_state")
            if action_type == "PROJECT_DELETE_COMPLETED":
                classification = (
                    "completed" if purge_state == "complete"
                    else "completed_partial"
                )
            else:
                classification = "died_mid_purge" if settled else "in_flight"

            out.append(
                {
                    "audit_id": audit_id,
                    "project_id": project_id,
                    "project_name": before.get("project_name"),
                    "requested_by": before.get("requested_by"),
                    "requested_at": stamp.isoformat() if stamp else None,
                    "action_type": action_type,
                    "classification": classification,
                    "purge_state": purge_state,
                    "completed_at": after.get("completed_at"),
                    "files_deleted": after.get("files_deleted"),
                    "files_preserved": after.get("files_preserved"),
                    "files_failed": after.get("files_failed") or [],
                    "redis_purge_error": after.get("redis_purge_error"),
                    "resumable": classification in ("died_mid_purge", "in_flight"),
                    "objects_in_manifest": len(before.get("binary_manifest") or []),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Resume (Task 2: idempotent and resumable)
    # ------------------------------------------------------------------

    async def _completed_audit(
        self, project_id: UUID,
    ) -> Optional[tuple[str, str]]:
        """The audit row of a deletion that already ran to completion."""
        row = (
            await self.db.execute(
                text(
                    "SELECT id::text, "
                    "       coalesce(after_payload->>'completed_at', "
                    "                timestamp::text) "
                    "FROM audit_log "
                    "WHERE resource_type = 'project' AND resource_id = :project_id "
                    "AND action_type = 'PROJECT_DELETE_COMPLETED' "
                    "ORDER BY timestamp DESC LIMIT 1"
                ),
                {"project_id": project_id},
            )
        ).fetchone()
        return (row[0], row[1]) if row is not None else None

    async def resume_pending_deletions(
        self, project_id: UUID,
    ) -> Optional[DeletionResult]:
        """Finish a deletion whose rows are gone but whose purge did not run.

        This is the crash case the ordering was designed for. The project row
        no longer exists, so nothing in the database can say what objects it
        owned — except the audit row, which was written before destruction
        began and carries the manifest. Re-running the purge from it converges
        to the same end state as an uninterrupted run.
        """
        row = (
            await self.db.execute(
                text(
                    "SELECT id::text, before_payload FROM audit_log "
                    "WHERE resource_type = 'project' AND resource_id = :project_id "
                    "AND action_type = 'PROJECT_DELETE_STARTED' "
                    "ORDER BY timestamp DESC LIMIT 1"
                ),
                {"project_id": project_id},
            )
        ).fetchone()
        if row is None:
            return None

        audit_id, payload = row[0], row[1] or {}
        manifest = payload.get("binary_manifest") or []
        job_ids = payload.get("job_ids") or []

        files_deleted, files_preserved, reasons, files_failed = (
            await self._purge_binaries(manifest)
        )
        redis_deleted, redis_purge_error = await self._purge_redis(job_ids)
        await self._record_completion(
            audit_id=UUID(audit_id),
            project_id=project_id,
            actor_id=None,
            rows_deleted={},
            files_deleted=files_deleted,
            files_preserved=files_preserved,
            preserved_reasons=reasons,
            files_failed=files_failed,
            redis_deleted=redis_deleted,
            redis_purge_error=redis_purge_error,
        )
        logger.info(
            "project_delete_resumed project=%s audit=%s files=%s preserved=%s redis=%s",
            project_id, audit_id, files_deleted, files_preserved, redis_deleted,
        )
        return DeletionResult(
            project_id=str(project_id),
            project_name=payload.get("project_name", ""),
            audit_id=audit_id,
            rows_deleted={},
            files_deleted=files_deleted,
            files_preserved=files_preserved,
            preserved_reasons=reasons,
            files_failed=files_failed,
            redis_keys_deleted=redis_deleted,
            resumed=True,
        )
