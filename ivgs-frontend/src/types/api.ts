/*
 * IVGS v5 — API Type Definitions
 *
 * TypeScript interfaces for all API response schemas.
 * Aligned with database tables (§4), API spec (§5), and Appendix C.
 *
 * Naming convention: <Entity>Response for API responses,
 *                    <Entity>Request for API request bodies.
 */

// ---------------------------------------------------------------------------
// Common Types
// ---------------------------------------------------------------------------

export type UserRole = "admin" | "operator" | "viewer";

export type ProjectState =
  | "DRAFT"
  | "TRANSCRIPT_REFINEMENT"
  | "STORYBOARD_GENERATION"
  | "MEDIA_GENERATION"
  | "MANIFEST_GENERATION"
  | "AUDIO_GENERATION"
  | "TALKING_HEAD_RENDER"
  | "PROTOTYPE_DRAFT"
  | "USER_REVIEW"
  | "FINAL_RENDER"
  | "COMPLETE"
  | "LOCALISATION"
  | "ERROR"
  | "IN_PROGRESS"
  | "REVIEW";

export type JobStatus = "pending" | "running" | "success" | "failed" | "PENDING" | "RUNNING" | "IN_PROGRESS" | "QUEUED" | "SUCCESS" | "FAILED" | "ERROR";

export type AssetType =
  | "image"
  | "video"
  | "audio"
  | "animation"
  | "talking_head"
  | "draft"
  | "render"
  | "caption"
  | "thumbnail";

export type QualityDecision = "approved" | "flagged" | "rejected";

export type FailureCategory = "transient" | "config" | "external" | "resource";

export type DLQResolution = "replayed" | "discarded" | "escalated";

export type StorageTier = "hot" | "warm" | "cold" | "archive";

export type FallbackStrategy =
  | "ai_video"
  | "animated_still"
  | "zoom_pan"
  | "static_image";

export type GpuNodeStatus = "online" | "offline" | "draining" | "unknown" | "ONLINE" | "OFFLINE" | "DRAINING" | "UNKNOWN";

/** How a node's status was established. WP-24. */
export type NodeStatusBasis = "self" | "node-exporter-scrape" | "probe-unavailable";

/** Why a node's GPU numbers are, or are not, there. WP-24. */
export interface NodeTelemetry {
  available: boolean;
  source: string;
  reason: string;
  as_of: string;
}

/** Legacy alias used by some components */
/**
 * NodeStatus - response from GET /api/v1/nodes (Phase 3 stub per spec section 5.1.7).
 *
 * NOT the same shape as GpuNodeResponse. The /api/v1/nodes endpoint serves
 * declared topology from NODE_TOPOLOGY in ivgs-api/app/api/v1/nodes.py, joined
 * with live reachability and GPU telemetry from app/core/node_health.py.
 *
 * WP-24 (2026-08-23) ended the Phase-3 stub. Two contract changes matter:
 *
 *   1. `status` can be "unknown" - the probe could not run. It is NOT a synonym
 *      for offline and must not be rendered as one.
 *   2. The GPU metric fields are NULLABLE. null means NOT MEASURED. Rendering
 *      null as 0 recreates the exact defect WP-24 removed: six cards reporting
 *      "VRAM 0.0 / Util 0% / Temp 0 C" for hardware nothing had ever read.
 *      Use `telemetry.available` to decide whether to draw a value at all.
 *
 * Key differences from GpuNodeResponse:
 *   - node_id is a string ("node-01"), not a UUID
 *   - hostname is the field name (not node_hostname)
 *   - power_draw_w / last_heartbeat_at only present on the single-node detail endpoint
 *   - services array is present (not on GpuNodeResponse)
 *   - active_jobs is present but always empty (job wiring is M4)
 */
export interface NodeStatus {
  node_id: string;
  hostname: string;
  status: GpuNodeStatus;
  /** How `status` was established. WP-24. */
  status_basis?: NodeStatusBasis;
  /** Plain-English justification for `status`. WP-24. */
  status_reason?: string;
  role: string;
  gpu_model: string | null;
  /**
   * WP-57 Task 4. Whether this node has a GPU, and whether it runs a Celery
   * pipeline worker (i.e. whether it is in the SCHEDULER's fleet).
   *
   * They exist because two dashboards counted nodes from this same payload and
   * neither could say what it counted. Operational Monitoring labelled a count
   * of ALL six nodes "GPU Nodes Online", silently promoting node-01 — CPU-only
   * infrastructure — into the GPU fleet. The scheduler's "3/3" counts something
   * different again: node-06 has a GPU and runs the CLIP scorer but no Celery
   * worker; node-05 (WP-61) has a GPU serving Qwen and no Celery worker
   * either. Three defensible numbers, none of them labelled. A surface cannot
   * say what it counts unless the payload says what each node is.
   */
  has_gpu: boolean;
  runs_pipeline_worker: boolean;
  /** DECLARED capacity from the topology table - not a reading. */
  total_vram_mb: number;
  /** Whether the declared hardware above has been verified on the box. */
  topology_verified?: boolean;
  /** OBSERVED. null = not measured. Never render null as 0. */
  used_vram_mb: number | null;
  /** OBSERVED. null = not measured. */
  gpu_utilization_pct: number | null;
  /** OBSERVED. null = not measured. */
  temperature_c: number | null;
  /** Why the observations above are present or absent. */
  telemetry?: NodeTelemetry;
  /** OBSERVED. null = not measured.
   *  WP-48: served by BOTH /nodes and /nodes/{id}. It used to be detail-only,
   *  which is why every card's Power cell read "no data" while Prometheus held
   *  a live reading. */
  power_draw_w: number | null;
  services: string[];
  active_jobs: unknown[];
  // Optional field - only present on /api/v1/nodes/{node_id} detail endpoint
  last_heartbeat_at?: string | null;
}

/** One container on a node, from GET /api/v1/nodes/{id}/containers. WP-48. */
export interface NodeContainer {
  name: string;
  image: string | null;
  state: string | null;
  status: string | null;
}

export interface NodeContainersResponse {
  available: boolean;
  source: string | null;
  /** Why the list is unavailable. Non-null exactly when available is false. */
  reason: string | null;
  containers: NodeContainer[];
}

/** One log line. `level` is INFERRED from the text; null means the line
 *  does not say, and must not be shown as "info". */
export interface NodeLogLine {
  timestamp: string | null;
  level: "critical" | "error" | "warning" | "info" | "debug" | null;
  message: string;
}

export interface NodeLogsResponse {
  available: boolean;
  source: string | null;
  container: string;
  reason: string | null;
  as_of?: string;
  lines: NodeLogLine[];
}

export type WorkerHeartbeatStatus =
  | "alive"
  | "suspected_dead"
  | "confirmed_dead";

export type ManifestStatus = "draft" | "locked" | "rendered" | "invalid";

export type CheckpointStatus = "pending" | "complete" | "failed" | "skipped";

// ---------------------------------------------------------------------------
// Auth Types (§5.1.1, §16.1)
// ---------------------------------------------------------------------------

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  password: string;
  role: UserRole;
}

// ---------------------------------------------------------------------------
// Project Types (§5.1.2, Table 1)
// ---------------------------------------------------------------------------

/**
 * `GET /api/v1/projects/{id}` — `ProjectResponse`
 * (`ivgs-api/app/schemas/project.py:79`).
 *
 * WP-43. Three fields declared here as REQUIRED were never sent by the API:
 * `asset_count`, `target_languages` and `current_job_id`. The live payload
 * for c12fa967, captured 2026-08-25, has exactly thirteen keys:
 *
 *   id, name, description, max_runtime_seconds, state, hero_image_url,
 *   scene_count, total_duration_estimate_seconds, created_at, updated_at,
 *   language_variants, active_job, created_by
 *
 * `target_languages` is the one that showed: the Overview header rendered
 * "Languages: …" from it, so the row was permanently absent, and the
 * metadata card said "None specified" for a project with two variants. The
 * language list is `language_variants` — the field that IS sent.
 *
 * Same family as WP-40 T1/T5 and WP-38: a type asserting a shape the wire
 * does not have. Optional fields below are optional because the schema
 * declares them `Optional[...]`, not as a hedge.
 */
export interface ProjectResponse {
  id: string;
  name: string;
  description?: string | null;
  state: ProjectState;
  max_runtime_seconds?: number | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  scene_count: number;
  total_duration_estimate_seconds?: number | null;
  hero_image_url?: string | null;
  /**
   * WP-57 Task 1. The asset whose thumbnail represents this project — a
   * final render if one exists, else the newest generated image.
   *
   * An ID rather than a URL, because `/assets/{id}/thumbnail` is token-guarded
   * and a browser will not attach a Bearer header to an `<img src>`; the card
   * fetches it through `apiClient.blob()`. NULL is a real answer meaning "this
   * project has no renderable asset yet", and the card must say that in words
   * rather than show an icon indistinguishable from a broken image.
   */
  thumbnail_asset_id?: string | null;
  /**
   * WP-60 Task 4. Why there is no thumbnail. Set only when
   * `thumbnail_asset_id` is null, and rendered verbatim by the card so a
   * video-only project stops being reported as a loader failure.
   */
  thumbnail_unavailable_reason?: string | null;
  /** `LanguageVariantSummary` — {language_code, state} and nothing else. */
  language_variants?: LanguageVariantSummary[];
  active_job?: ActiveJobInfo | null;
  /**
   * @deprecated Not sent by this API. Kept optional only so existing callers
   * compile while they migrate to `language_variants`.
   */
  target_languages?: string[];
}

/** `ActiveJobInfo` (`schemas/project.py:59`) — embedded in the project. */
export interface ActiveJobInfo {
  id: string;
  job_type: string;
  status: string;
  started_at: string | null;
}

/**
 * `LanguageVariantSummary` (`schemas/project.py:70`).
 *
 * Two keys. Not the full variant: no `id`, so the Languages tab cannot
 * retry from this payload — it reads `GET /projects/{id}/languages`, which
 * carries the variant UUID the retry route needs.
 */
export interface LanguageVariantSummary {
  language_code: string;
  state: string;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  max_runtime_seconds: number;
  target_languages?: string[];
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  max_runtime_seconds?: number;
}

// ---------------------------------------------------------------------------
// Scene Types (§5.1.3, Table 3)
// ---------------------------------------------------------------------------

export interface SceneResponse {
  id: string;
  project_id: string;
  scene_index: number;
  narration_text: string;
  visual_description: string;
  media_type: "image" | "video_clip" | "animation";
  duration_seconds: number;
  status: string;
  assets: AssetSummary[];
}

/**
 * @deprecated Every field below except `id` and `asset_type` is absent from
 * the API. Nothing reads this type any more; use `AssetResponse` plus
 * `@/lib/media`. WP-40 addendum.
 */
export interface AssetSummary {
  id: string;
  asset_type: AssetType;
  storage_path?: string;
  quality_score?: number | null;
  quality_decision?: QualityDecision | null;
  thumbnail_url?: string | null;
}

// ---------------------------------------------------------------------------
// Asset Types (§5.1.4, Table 6)
// ---------------------------------------------------------------------------

/**
 * WP-40 Task 1 — this now matches the wire.
 *
 * `AssetResponse` (ivgs-api/app/schemas/asset.py:27) sends exactly the
 * fields below. It does NOT send `url`, `thumbnail_url`, `filename`,
 * `scene_label`, `generation_prompt`, `storage_path`, `metadata`,
 * `quality_score` or `quality_decision`. This interface previously declared
 * all nine -- four of them as REQUIRED -- so `asset.thumbnail_url ||
 * asset.url` type-checked and evaluated to `undefined`, and
 * `<img src={undefined}>` renders with no `src`: zero image requests over
 * 40 real assets.
 *
 * The nine phantom fields are kept below as `never`-adjacent optionals ONLY
 * where a sibling tab still reads them (see the deprecation note); nothing
 * new should use them. Use `@/lib/media` to derive a filename, media kind
 * and download path from what the API really sends.
 *
 * Quality scores are a separate table (`asset_quality_scores`) behind
 * `/api/v1/quality/...`; they were never part of this payload.
 */
export interface AssetResponse {
  id: string;
  project_id: string;
  scene_id: string | null;
  asset_type: AssetType;
  seaweedfs_fid: string | null;
  seaweedfs_path: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  language_code: string | null;
  generation_prompt_id: string | null;
  storage_tier: StorageTier;
  preserve_flag: boolean;
  content_hash: string | null;
  reference_count: number;
  created_at: string;

  /*
   * WP-40 addendum: `url`, `filename`, `scene_label`, `generation_prompt`,
   * `thumbnail_url`, `quality_score`, `quality_decision`, `metadata` and
   * `storage_path` USED TO BE DECLARED HERE and are DELIBERATELY GONE.
   *
   * The first pass kept them as deprecated optionals so the audio,
   * talking-head, draft and renders tabs -- which had the same defect and
   * were out of that scope -- would still compile. All four are fixed now,
   * so the declarations are removed outright: reading `asset.url` is a
   * COMPILE ERROR again, which is the only thing that reliably stops this
   * family of bug coming back. Use @/lib/media to derive what a card needs.
   */
}

// ---------------------------------------------------------------------------
// Job Types (§5.2.1, Table 7)
// ---------------------------------------------------------------------------

export interface JobResponse {
  id: string;
  project_id: string;
  celery_task_id: string;
  job_type: string;
  node_id: string | null;
  status: JobStatus;
  /**
   * WP-45 Task 5 / WP-40 D-4, ruled. These were dead columns: NULL on all 23
   * rows on the fleet, and nothing in ivgs-api, ivgs-workers or shared/ ever
   * wrote them. They are stamped now, on the status callback every worker
   * already makes. Still nullable -- a job that has not started has no start.
   */
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  failure_category: FailureCategory | null;
  /** WP-45: the stage the worker last reported. Null until one does. */
  resume_from_stage?: string | null;
  /** WP-45 Task 6(c): the language variant this job rendered; null = source. */
  language_code?: string | null;
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Transcript Types (§5.1.3, Table 2)
// ---------------------------------------------------------------------------

/**
 * WP-40 Task 5 — this now matches the wire.
 *
 * `TranscriptResponse` (ivgs-api/app/schemas/transcript.py:13) sends id,
 * project_id, sequence_order, original_asset_id, refined_text,
 * language_code, created_at, updated_at. There is no `original_text` field
 * and no `original_text` COLUMN on the `transcripts` table -- the uploaded
 * source document is an asset referenced by `original_asset_id`.
 *
 * Declaring `original_text: string` here is what let the transcript page
 * pass `undefined` into `TranscriptEditor`, where `original.split("\n")`
 * threw "Cannot read properties of undefined (reading 'split')" -- ledger
 * P1.4r.
 */
export interface TranscriptResponse {
  id: string;
  project_id: string;
  sequence_order: number;
  original_asset_id: string | null;
  refined_text: string | null;
  language_code: string | null;
  created_at: string;
  updated_at: string;

  /*
   * WP-40 addendum: `original_text`, `original_filename` and `status` used to
   * be declared here and are DELIBERATELY GONE. `original_text` in particular
   * was declared REQUIRED, which is what let the page hand `undefined` to
   * `TranscriptEditor` and produce the P1.4r `.split` crash. Reading any of
   * them is a compile error again.
   */
}

// ---------------------------------------------------------------------------
// Prompt Types (§5.1.5, Table 5)
// ---------------------------------------------------------------------------

export interface PromptResponse {
  id: string;
  prompt_type: string;
  scope: "global" | "project" | "scene";
  project_id: string | null;
  scene_id: string | null;
  template_text: string;
  version: number;
  is_active: boolean;
  created_by: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// DLQ Types (§5.2.4, Table 15)
// ---------------------------------------------------------------------------

export interface DLQMessageResponse {
  id: string;
  original_queue: string;
  task_name: string;
  task_args: unknown[];
  task_kwargs: Record<string, unknown>;
  exception_type: string;
  exception_message: string;
  traceback: string;
  failure_category: FailureCategory;
  retry_count_exhausted: number;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  resolution: DLQResolution | null;
}

// ---------------------------------------------------------------------------
// GPU Node Types (§5.2.2, Table 11)
// ---------------------------------------------------------------------------

/**
 * GpuNodeResponse - matches backend ivgs-api app/schemas/gpu.py:GpuNodeResponse exactly.
 *
 * Per IVGS v5 Functional Specification Appendix C.4 and GPU Fleet Monitoring
 * Spec v1.1 section 6.0 (defect #7 resolution).
 *
 * No optional/aliased fields. Components access these exact names.
 * The three previous competing naming conventions (backend-matching,
 * frontend-aliased, per-component-invented) are eliminated.
 */
export interface GpuNodeResponse {
  id: string;
  node_hostname: string;
  gpu_index: number;
  gpu_model: string | null;
  total_vram_mb: number | null;
  /**
   * WP-60 Task 2(b): reservation accounting, not a device reading.
   * `reserved_vram_mb` is the same number under its true name; render that.
   */
  used_vram_mb: number;
  reserved_vram_mb: number;
  available_vram_mb: number;
  /**
   * WP-60 Task 2(a). NULLABLE, and narrowing them to `number` was what let the
   * card print "0 C" / "0 W" / "0%" for readings nothing had taken. The API
   * schema now sends null when the scheduler registry holds no reading; typing
   * them as `number` here would put the fabrication straight back.
   */
  gpu_utilization_pct: number | null;
  temperature_c: number | null;
  power_draw_w: number | null;
  /**
   * WP-61 Task 8, RULED. WHERE the three readings above came from.
   *
   * They are Prometheus device telemetry (`prometheus:nvidia-gpu-exporter`),
   * the same series Node Monitor reads — not scheduler-registry fields. The
   * registry could never carry them: the heartbeat sender shells out to
   * `nvidia-smi` inside the worker container and the workers image has no such
   * binary (proven 2026-08-26). "Not reported" was true and permanent.
   *
   * `telemetry_source` is null when nothing was measured, and
   * `telemetry_reason` says why in words. A card must render the reason, not a
   * zero. Note that `used_vram_mb` / `reserved_vram_mb` are NOT covered by
   * this label — they are reservation accounting and legitimately differ from
   * the device.
   */
  telemetry_source: string | null;
  telemetry_reason: string | null;
  /**
   * WP-62 Task 1, RULED. THE PAGE SHOWS EVERY GPU-BEARING MACHINE.
   *
   * `GET /gpu/nodes` now returns node-02, 03, 04, 05 and 06 — every machine
   * with a card — not just the three that registered a Celery worker with the
   * scheduler. node-05 (vLLM/Qwen) and node-06 (CLIP scorer) run no Celery
   * worker by design and could never enter that registry, which is why
   * relabelling the count twice (WP-57 T4, WP-60 T2) left the page still
   * missing two GPUs.
   *
   *   in_scheduler   — false for a GPU node the scheduler does not place work
   *                    on. Such a node has NO reservation figure and NO Drain.
   *   role           — what the node is for. The only thing a non-scheduler
   *                    node has to say about itself; without it "no active
   *                    jobs" reads as idle.
   *   supports_drain — false means the control must not be rendered. The
   *                    server answers 409 DRAIN_NOT_APPLICABLE if called.
   *   device_*       — PHYSICAL VRAM from Prometheus. A DIFFERENT NUMBER from
   *                    `reserved_vram_mb`, which is scheduler accounting: on
   *                    2026-08-26 node-02 held 88494 MiB on the device with 0
   *                    reserved. Both are on the payload so a card can label
   *                    each rather than presenting one as "VRAM usage".
   */
  in_scheduler: boolean;
  role: string | null;
  supports_drain: boolean;
  device_used_vram_mb: number | null;
  device_total_vram_mb: number | null;
  power_tdp_w: number | null;
  compute_capability: string | null;
  status: GpuNodeStatus;
  registered_at: string;
  last_heartbeat_at: string | null;
  active_jobs: ActiveJobSummary[];
  reservations: GpuReservationResponse[];
}

/**
 * ActiveJobSummary - matches backend ActiveJobSummary in schemas/gpu.py.
 * Was previously a string | null (current_job) on the frontend type;
 * backend has always provided a structured list.
 */
export interface ActiveJobSummary {
  job_id: string;
  project_name: string | null;
  stage: string | null;
  started_at: string | null;
}

/**
 * GpuReservationResponse - matches backend GpuReservationResponse in schemas/gpu.py.
 */
export interface GpuReservationResponse {
  id: string;
  gpu_node_id: string;
  job_id: string;
  reserved_vram_mb: number;
  model_name: string | null;
  status: string;
  reserved_at: string;
  expires_at: string;
}

// ---------------------------------------------------------------------------
// Quality Types (§11.1, Table 17)
// ---------------------------------------------------------------------------

export interface QualityScoreResponse {
  asset_id: string;
  quality_score: number;
  safety_score: number;
  scoring_details: Record<string, unknown>;
  decision: QualityDecision;
}

// ---------------------------------------------------------------------------
// Composition Types (§6.4, Table 16)
// ---------------------------------------------------------------------------

export interface CompositionManifestResponse {
  id: string;
  job_id: string;
  manifest_version: string;
  total_duration_ms: number;
  resolution_width: number;
  resolution_height: number;
  framerate: number;
  status: ManifestStatus;
  locked_at: string | null;
  rendered_at: string | null;
  checksum: string;
}

// ---------------------------------------------------------------------------
// Language Variant Types (§17.1, Table 8)
// ---------------------------------------------------------------------------

/**
 * `GET /api/v1/projects/{id}/languages` — `LanguageVariantResponse`
 * (`ivgs-api/app/schemas/language_variant.py:35`).
 *
 * WP-43 Task 3b. This interface used to declare TEN fields the API has
 * never sent, and the two that mattered were the ones the variants table
 * read: `progress_percent` and `status`. `variant.progress_percent || 0`
 * over an absent field is what rendered EN-US as a confident **0%** beside
 * a **PENDING** badge, for a language that has a finished 720p draft on
 * disk. It was never a measurement — nothing in ivgs-api, ivgs-workers or
 * shared/ writes a per-language progress figure at all.
 *
 * The live payload, captured 2026-08-25, is exactly seven keys, and the two
 * render ids are IDs, not URLs — `final_render_1080p_url` was wrong twice.
 */
export interface LanguageVariantResponse {
  id: string;
  project_id: string;
  language_code: string;
  /** LOWERCASE on the wire, e.g. "pending". */
  state: string;
  final_render_1080p_id: string | null;
  final_render_4k_id: string | null;
  /**
   * WP-45 Task 6(c) / WP-43 D-1, ruled derive-never-store. Computed by the API
   * on every request from this variant's own pipeline checkpoints.
   *
   * `null` -- never 0 -- when there is nothing to measure. WP-43 found this
   * field being read as `progress_percent || 0` when it did not exist at all,
   * so an absent measurement rendered as a confident 0% beside a language with
   * a finished 720p draft on disk.
   */
  progress_percent?: number | null;
  completed_stages?: number | null;
  total_stages?: number | null;
  /** Where the figure came from, in words. Shown as the column's tooltip. */
  progress_source?: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Pipeline Checkpoint Types (§6.2, Table 10)
// ---------------------------------------------------------------------------

export interface CheckpointResponse {
  id: string;
  job_id: string;
  stage_name: string;
  stage_index: number;
  status: CheckpointStatus;
  started_at: string | null;
  completed_at: string | null;
}

// ---------------------------------------------------------------------------
// Health Check
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  version: string;
  uptime_seconds: number;
  services: Record<string, "up" | "down">;
}

// ---------------------------------------------------------------------------
// Pagination Wrapper
// ---------------------------------------------------------------------------

/**
 * The paginated envelope this API ACTUALLY sends (Appendix C.1):
 * `{ data, total, page, per_page, pages, has_more }`.
 *
 * WP-56 Task 5 CORRECTED THIS TYPE. It previously declared
 * `{ items, total, page, per_page, total_pages }` — and the API has never sent
 * `items` or `total_pages` from any route. It was a PHANTOM TYPE of the WP-40/43
 * family: nothing read it yet, so nothing was visibly broken, but the first
 * component to trust it would have read `undefined` and rendered an empty list
 * for a populated response. `src/lib/unwrap.ts` has documented the real shape
 * as `PaginatedEnvelope` since WP-35; the two disagreed and the wrong one had
 * the more inviting name.
 *
 * Reaching for `.items` is now a compile error, which is the point.
 */
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  has_more: boolean;
}

// ---------------------------------------------------------------------------
// Convenience Type Aliases
// ---------------------------------------------------------------------------
// Components import these short names; they map to the *Response interfaces.

/**
 * WP-40 addendum: `render_variants` and `draft_video_url` were removed. The
 * API sends neither, so the Final Renders tab could never show a render and
 * the Draft Preview tab could never show a draft -- both rendered their empty
 * state unconditionally on every project. Both tabs now read the ASSET list,
 * where the renders actually live.
 */
export type Project = ProjectResponse & {
  /**
   * @deprecated Not sent. The payload carries `created_by` (a UUID) only.
   */
  created_by_name?: string;
};

export type Asset = AssetResponse;

/**
 * WP-45 Task 6(f). Six of the seven "computed fields added by the API" were
 * never added by the API. `current_stage`, `has_checkpoint`, `checkpoint_data`,
 * `assigned_node`, `assigned_gpu` and `duration_seconds` are not sent by
 * `JobResponse` and never were, so the Jobs tab rendered "-" for stage,
 * "Unassigned" for node and "N/A" for GPU on every row -- every job looked
 * identical and none of them was identified.
 *
 * They are deleted rather than made optional-and-guarded, which is the fix
 * WP-40's addendum A6 established: a declared field that nothing sends will be
 * read by the next person who writes a component.
 *
 * `duration_seconds` is the one that had a real source: it is derived
 * client-side from started_at/completed_at (now populated -- WP-45 Task 5) and
 * falls back to the checkpoint span, which is what the tracker already does.
 *
 * `stage_statuses` was removed by WP-40 for the same reason. Stage state comes
 * from GET /jobs/{id}/checkpoints.
 */
export type RenderJob = JobResponse;

/**
 * WP-40 addendum: the `filename` alias was removed. It was not sent by the
 * API and the transcript list rendered it as its row title, so every row
 * header was blank. Use `sequence_order` / `language_code`.
 */
export type Transcript = TranscriptResponse;

export type LanguageVariant = LanguageVariantResponse;

export type RenderVariant = LanguageVariantResponse;

export interface VideoQuality {
  label: string;
  src: string;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string;
  max_runtime_seconds?: number;
  target_languages?: string[];
}
