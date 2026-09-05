/**
 * IVGS v5 — Monitoring & Admin Type Definitions
 *
 * Types consumed by monitoring dashboards, DLQ views, GPU fleet status,
 * pipeline visualizations, storage analytics, and admin user management.
 *
 * Spec references: §8.1–8.3, §10.1, §11.1, §13.1, §16.2
 */

// ────────────────────────────────────────────────────────────────────────────
// User & Admin (§16.2)
// ────────────────────────────────────────────────────────────────────────────

export type UserRole = "admin" | "operator" | "viewer";

export interface User {
  id: string;
  username: string;
  role: UserRole;
  created_at: string;
  /** WP-70 fix S12: `UserResponse.last_login_at` — the page rendered every user as "Never" under the old name `last_login`. */
  last_login_at: string | null;
}

export interface CreateUserPayload {
  username: string;
  password: string;
  role: UserRole;
}

// ────────────────────────────────────────────────────────────────────────────
// Pipeline (§8.2.1, §6.1)
// ────────────────────────────────────────────────────────────────────────────

export type PipelineStage =
  | "TRANSCRIPT_REFINEMENT"
  | "STORYBOARD_GENERATION"
  | "MEDIA_GENERATION"
  | "MANIFEST_GENERATION"
  | "AUDIO_GENERATION"
  | "TALKING_HEAD_RENDER"
  | "PROTOTYPE_DRAFT"
  | "FINAL_RENDER"
  | "LOCALISATION";

export type PipelineStageStatus =
  | "pending"
  | "running"
  | "complete"
  | "failed"
  | "skipped"
  | "PENDING"
  | "RUNNING"
  | "COMPLETE"
  | "FAILED"
  | "SKIPPED";

export type FallbackLevel = "none" | "provider" | "model" | "full" | "L1" | "L2" | "L3" | "L4" | "DLQ";

export interface CheckpointData {
  stage: PipelineStage;
  status: PipelineStageStatus;
  started_at: string | null;
  completed_at: string | null;
  fallback_level: FallbackLevel;
  error_message?: string;
  retry_count?: number;
  node_id?: string;
}

export interface PipelineJob {
  id: string;
  project_name: string;
  status: string;
  progress: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  estimated_completion: string | null;
  fallback_level: FallbackLevel;
}

export interface PipelineJobDetail {
  id: string;
  status: string;
  current_stage: PipelineStage | null;
  error_stage: PipelineStage | null;
  error_message: string | null;
  fallback_level: FallbackLevel;
  checkpoints: CheckpointData[];
}

// ────────────────────────────────────────────────────────────────────────────
// GPU Fleet (§8.2.2)
// ────────────────────────────────────────────────────────────────────────────

// GPUNode is a re-export of GpuNodeResponse from the canonical API types
// (rewritten per GPU Fleet Monitoring Spec v1.1 section 6.0 to match backend
// exactly). There is one node shape across the app per spec Appendix C.4.
// Previously this file defined a separate GPUNode with fields that did not
// exist on the backend response (cpu_percent, ram_percent, tdp_watts,
// queued_jobs, active_job singular). Aligned per Spec v1.1 section 6.1.
export type { GpuNodeResponse as GPUNode } from "@/types/api";
export type { ActiveJobSummary } from "@/types/api";

/**
 * Single time-series GPU utilization measurement.
 *
 * Field names mirror the backend gpu_metrics_history storage model
 * (per GPU Fleet Monitoring Spec v1.1 section 3.4). All metric fields
 * except gpu_node_id, node_hostname, and recorded_at are nullable.
 */
export interface GPUUtilizationPoint {
  gpu_node_id: string;
  node_hostname: string;
  recorded_at: string;
  gpu_util_pct: number | null;
  mem_util_pct: number | null;
  temperature_c: number | null;
  power_draw_w: number | null;
  active_job_count: number | null;
  queue_depth: number | null;
}

/**
 * Envelope returned by GET /api/v1/gpu/utilization/history.
 */
export interface GPUUtilizationHistoryResponse {
  history: GPUUtilizationPoint[];
  range: string;
  point_count: number;
}

export interface ModelResidencyEntry {
  node_id: string;
  model_name: string;
  loaded_at: string;
  vram_mb: number;
  allocations?: any[];
}

// ────────────────────────────────────────────────────────────────────────────
// Dead Letter Queue (§10.1)
// ────────────────────────────────────────────────────────────────────────────

export type DLQCategory =
  | "transient"
  | "config"
  | "external"
  | "resource"
  | "unknown"
  | "TRANSIENT"
  | "CONFIG"
  | "EXTERNAL"
  | "RESOURCE"
  | "UNKNOWN";

/**
 * WP-70 fix S11. The field names are `DLQMessageResponse`'s
 * (ivgs-api/app/schemas/dlq.py): this interface used to declare
 * `error_message`, `category` and `retry_count`, which the API never sent, so
 * the table rendered an empty badge and an empty error for every row.
 */
export interface DLQMessage {
  id: string;
  task_name: string;
  exception_message: string | null;
  failure_category: DLQCategory | null;
  retry_count_exhausted: number | null;
  /** WP-70 fix D-7: the arrival timestamp under the API's one name. */
  created_at: string;
}

export interface DLQResolutionEntry {
  action: string;
  reason: string;
  performed_by: string;
  performed_at: string;
  result: string;
}

export interface DLQMessageDetail {
  id: string;
  task_name: string;
  category: DLQCategory;
  retry_count: number;
  entered_dlq_at: string;
  traceback: string;
  task_arguments: Record<string, unknown>;
  resolution_history: DLQResolutionEntry[];
}

export interface DLQAnalyticsData {
  category_counts: Record<DLQCategory, number>;
  top_tasks: Array<{ task_name: string; count: number }>;
  trend_data: Array<{ date: string; count: number }>;
}

// ────────────────────────────────────────────────────────────────────────────
// Quality (§11.1)
// ────────────────────────────────────────────────────────────────────────────

export type QualityDecision = "approved" | "flagged" | "rejected";

export type QualityMetricType =
  | "aesthetic"
  | "safety"
  | "consistency"
  | "technical"
  | "CLIP_SCORE"
  | "SNR"
  | "FRAME_CONSISTENCY"
  | "LIP_SYNC_SCORE"
  | "RESOLUTION_CHECK"
  | "DURATION_CHECK"
  | "SAFETY_SCORE";

/**
 * WP-40 addendum — this now matches the wire.
 *
 * `FlaggedAssetResponse` (ivgs-api/app/schemas/quality.py:32) sends id,
 * asset_id, job_id, quality_score, safety_score, scoring_details, decision,
 * created_at, asset_type, project_id, project_name.
 *
 * It does NOT send `thumbnail_url` (which exists nowhere in ivgs-api),
 * `scene_index`, or `metrics` — the per-metric breakdown is
 * `scoring_details`. All three were declared here, two of them as required,
 * so the review card rendered an `<img>` with no `src`, a literal
 * "Scene undefined", and no metric breakdown at all.
 */
export interface FlaggedAsset {
  id: string;
  asset_id: string;
  job_id: string | null;
  project_id: string | null;
  project_name: string | null;
  asset_type: string | null;
  quality_score: number | null;
  safety_score: number | null;
  scoring_details: Record<string, unknown> | null;
  decision: string;
  created_at: string;

  /*
   * WP-40 addendum: `score_id`, `project_owner_id`, `thumbnail_url`,
   * `scene_index` and `metrics` used to be declared here and are gone.
   * `score_id` was the key the approve/reject buttons posted with, so they
   * hit /api/v1/quality/undefined/{approve,reject}.
   */
}

// ────────────────────────────────────────────────────────────────────────────
// Composition Timeline (§13.1)
// ────────────────────────────────────────────────────────────────────────────

export type ManifestLockStatus =
  | "draft"
  | "locked"
  | "rendered"
  | "invalid"
  | "DRAFT"
  | "LOCKED"
  | "RENDERED"
  | "INVALID"
  | "UNKNOWN";

export type RenderSegmentStatus =
  | "pending"
  | "rendering"
  | "complete"
  | "failed"
  | "PENDING"
  | "RENDERING"
  | "COMPLETE"
  | "FAILED";

export type TimelineLayer =
  | "video"
  | "audio"
  | "overlay"
  | "transition"
  | "subtitle"
  | "BACKGROUND"
  | "TALKING_HEAD"
  | "LOWER_THIRD"
  | "CAPTIONS"
  | "AUDIO";

export interface TimelineSegment {
  id: string;
  layer: TimelineLayer;
  start_seconds: number;
  duration_seconds: number;
  asset_id: string;
  status: RenderSegmentStatus;
  render_started_at?: string;
  render_completed_at?: string;
  progress?: number;
}

export interface CompositionManifest {
  id: string;
  project_id: string;
  status: ManifestLockStatus;
  scene_count: number;
  total_duration_seconds: number;
  segments: TimelineSegment[];
  scenes?: any[];
  locked_at: string | null;
  rendered_at: string | null;
}

// ────────────────────────────────────────────────────────────────────────────
// Storage Analytics (§14.1)
// ────────────────────────────────────────────────────────────────────────────

/**
 * The `storage_tier` PostgreSQL ENUM, exactly.
 *
 * WP-57 Task 2 NARROWED THIS, and the narrowing is the fix rather than a
 * tidy-up. It used to be the union of both cases —
 * `"hot" | ... | "HOT" | ...` — which is how the Storage Analytics page came to
 * key its four donuts on `"HOT"`, `"WARM"`, `"COLD"`, `"ARCHIVE"` while the API
 * sends `"hot"`. `tierData.find(t => t.tier === tier.id)` was comparing
 * `"hot" === "HOT"`, matching nothing, and every tier rendered 0% / "no assets"
 * / 0 B directly beneath a populated total on the same page.
 *
 * The uppercase half of that union existed only to make the mismatch compile.
 * A type widened to accommodate a bug stops being able to catch it — the same
 * disease as WP-56's phantom `PaginatedResponse<T>`.
 *
 * Note `"archived"`, not `"archive"`: the ENUM is
 * `hot | warm | cold | archived | deleted`, verified against pg_enum. The old
 * type said `"archive"`, so lowercasing alone would still have missed that tier.
 */
export type StorageTier = "hot" | "warm" | "cold" | "archived" | "deleted";

export interface StorageTierData {
  tier: StorageTier;
  used_bytes: number;
  total_bytes: number;
  asset_count: number;
  used?: number;
  allocated?: number;
}

export interface QuotaEntry {
  user_id: string;
  username: string;
  used_bytes: number;
  quota_bytes: number;
  /**
   * WP-40 Task 4: whether a `storage_quotas` row actually exists for this
   * entity. Without it, "no record" and "a genuine zero-byte quota" render
   * identically as 0 / 0, and the operator cannot tell which they are
   * looking at. The table is currently empty for every user.
   */
  has_quota: boolean;
}

/**
 * One row of `GET /api/v1/retention/report`'s `upcoming_migrations`.
 *
 * WP-57 Task 3 — the phantom-field family, instance 14. CAPTURED FROM THE LIVE
 * WIRE, not from what the table wanted to render. What the API actually sends is
 * exactly these five keys; the interface previously declared
 * `project_name`, `target_tier`, `size_bytes` and `scheduled_at`, none of which
 * has ever been on the wire. Only `asset_id` and `current_tier` matched, which
 * is precisely what the screenshot showed: two populated columns, two blanks,
 * `NaN undefined`, and `Invalid Date`.
 *
 * The phantoms are DELETED rather than null-guarded — the WP-40/43 fix. Reading
 * `m.size_bytes` is now a compile error, which is what stopped it silently
 * reaching a formatter as `undefined`.
 *
 * Two renames worth naming, because they are not cosmetic:
 *   `target_tier` -> `next_tier`         the API's own word, and clearer
 *   `size_bytes`  -> `file_size_bytes`   ditto
 *
 * `scheduled_at` has no replacement ON PURPOSE. The API sends
 * `days_until_migration`, which is what it can honestly compute; a timestamp
 * would have to be invented. See the page for why "0 days" is rendered as
 * "overdue" rather than "today".
 */
export interface TierMigration {
  asset_id: string;
  current_tier: StorageTier;
  next_tier: StorageTier;
  days_until_migration: number;
  file_size_bytes: number;
}

export interface OrphanAsset {
  seaweedfs_fid: string;
  path: string;
  size_bytes: number;
  last_modified: string;
  reason: string;
}

// ────────────────────────────────────────────────────────────────────────────
// Backup Management (§14)
// ────────────────────────────────────────────────────────────────────────────

// Stream B Phase 14: aligned with backend DB ENUM and API contract.
//   backend ENUM backup_type   = full_database, wal_archive, asset_backup,
//                                config_backup, vm_snapshot
//   backend ENUM backup_status = running, completed, failed, verified
// Verification is a status transition (completed -> verified) rather than
// a separate enum field.  duration is derived client-side from
// started_at / completed_at.
export type BackupType =
  | "full_database"
  | "wal_archive"
  | "asset_backup"
  | "config_backup"
  | "vm_snapshot";

export type BackupStatus = "running" | "completed" | "failed" | "verified";

export interface BackupRecord {
  id: string;
  backup_type: BackupType;
  started_at: string;
  completed_at: string | null;
  status: BackupStatus;
  size_bytes: number | null;
  backup_path: string | null;
  verification_checksum: string | null;
  verified_at: string | null;
  error_message: string | null;
}

export interface BackupTriggerPayload {
  backup_type: BackupType;
}

export interface RollbackPoint {
  id: string;
  version_tag: string;
  created_at: string;
  alembic_revision: string;
  docker_image_tags: Record<string, string>;
}

// ────────────────────────────────────────────────────────────────────────────
// Retention Policies (§10.4)
// ────────────────────────────────────────────────────────────────────────────

/**
 * `GET /api/v1/retention/policies` — CAPTURED FROM THE LIVE WIRE.
 *
 * WP-57 Task 5 found this by sweep, not from a screenshot, and it was the worst
 * of the set. The interface declared `source_tier`, `target_tier`,
 * `threshold_days`, `auto_execute`, `last_run_at` and `assets_affected` — SIX
 * fields, and the API sends NONE of them. The whole admin Retention Policies
 * table rendered undefined in every column but `name`.
 *
 * And it was not only a display defect. The editor PUT
 * `{threshold_days, auto_execute}` to an endpoint whose update schema
 * (`RetentionPolicyUpdate`, ivgs-api/app/schemas/retention.py:52) declares
 * neither, so FastAPI dropped both silently and the form returned 200 having
 * saved nothing — a green surface over an empty action, on an admin settings
 * form, which is the AD-09.3 family in the place it can do most harm.
 *
 * A retention policy is a set of PER-TIER DURATIONS, not a single threshold with
 * an on/off switch. That is what the table now shows.
 */
export interface RetentionPolicy {
  id: string;
  name: string;
  description: string | null;
  hot_days: number | null;
  warm_days: number | null;
  cold_days: number | null;
  archive_days: number | null;
  delete_after_days: number | null;
  applies_to: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

/** Mirrors `RetentionPolicyUpdate` on the API, field for field. */
export interface RetentionPolicyUpdate {
  name?: string;
  description?: string;
  hot_days?: number;
  warm_days?: number;
  cold_days?: number;
  archive_days?: number;
  delete_after_days?: number;
  applies_to?: string;
  is_default?: boolean;
}
