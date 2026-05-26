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

export type GpuNodeStatus = "online" | "offline" | "draining" | "ONLINE" | "OFFLINE" | "DRAINING";

/** Legacy alias used by some components */
/**
 * NodeStatus - response from GET /api/v1/nodes (Phase 3 stub per spec section 5.1.7).
 *
 * NOT the same shape as GpuNodeResponse. The /api/v1/nodes endpoint serves
 * static topology from a hardcoded NODE_TOPOLOGY dict in ivgs-api/app/api/v1/nodes.py.
 * Phase 8 GPU scheduler will replace the stub with real metrics; until then this
 * shape is what the wire actually emits.
 *
 * Key differences from GpuNodeResponse:
 *   - node_id is a string ("node-01"), not a UUID
 *   - hostname is the field name (not node_hostname)
 *   - status is currently always "online" (stub)
 *   - power_draw_w / last_heartbeat_at only present on the single-node detail endpoint
 *   - services array is present (not on GpuNodeResponse)
 *   - active_jobs is present but always empty in current stub
 */
export interface NodeStatus {
  node_id: string;
  hostname: string;
  status: GpuNodeStatus;
  role: string;
  gpu_model: string | null;
  total_vram_mb: number;
  used_vram_mb: number;
  gpu_utilization_pct: number;
  temperature_c: number;
  services: string[];
  active_jobs: unknown[];
  // Optional fields - only present on /api/v1/nodes/{node_id} detail endpoint
  power_draw_w?: number;
  last_heartbeat_at?: string | null;
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

export interface ProjectResponse {
  id: string;
  name: string;
  description: string;
  state: ProjectState;
  max_runtime_seconds: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  scene_count: number;
  asset_count: number;
  target_languages: string[];
  hero_image_url: string | null;
  current_job_id: string | null;
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

export interface AssetSummary {
  id: string;
  asset_type: AssetType;
  storage_path: string;
  quality_score: number | null;
  quality_decision: QualityDecision | null;
  thumbnail_url: string | null;
}

// ---------------------------------------------------------------------------
// Asset Types (§5.1.4, Table 6)
// ---------------------------------------------------------------------------

export interface AssetResponse {
  id: string;
  project_id: string;
  scene_id: string | null;
  asset_type: AssetType;
  storage_path: string;
  file_size_bytes: number;
  content_hash: string | null;
  reference_count: number;
  storage_tier: StorageTier;
  metadata: Record<string, unknown>;
  quality_score: number | null;
  quality_decision: QualityDecision | null;
  created_at: string;
  url?: string;
  filename?: string;
  scene_label?: string;
  generation_prompt?: string;
  thumbnail_url?: string;
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
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  failure_category: FailureCategory | null;
}

// ---------------------------------------------------------------------------
// Transcript Types (§5.1.3, Table 2)
// ---------------------------------------------------------------------------

export interface TranscriptResponse {
  id: string;
  project_id: string;
  original_filename: string;
  original_text: string;
  refined_text: string;
  language_code: string;
  sequence_order: number;
  status: string;
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
  used_vram_mb: number;
  available_vram_mb: number;
  gpu_utilization_pct: number;
  temperature_c: number;
  power_draw_w: number;
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

export interface LanguageVariantResponse {
  id: string;
  project_id: string;
  language_code: string;
  state: string;
  final_render_1080p_url: string | null;
  final_render_4k_url: string | null;
  language?: string;
  status?: string;
  progress_percent?: number;
  updated_at?: string;
  url_1080p?: string;
  url_4k?: string;
  subtitle_vtt_url?: string;
  subtitle_srt_url?: string;
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

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// ---------------------------------------------------------------------------
// Convenience Type Aliases
// ---------------------------------------------------------------------------
// Components import these short names; they map to the *Response interfaces.

export type Project = ProjectResponse & {
  /** Populated by joined query — display name of creator */
  created_by_name?: string;
  language_variants?: LanguageVariantResponse[];
  render_variants?: LanguageVariantResponse[];
  draft_video_url?: string;
};

export type Asset = AssetResponse;

export type RenderJob = JobResponse & {
  /** Computed fields added by the API for pipeline views */
  current_stage?: string;
  has_checkpoint?: boolean;
  checkpoint_data?: Record<string, unknown>;
  assigned_node?: string;
  assigned_gpu?: string;
  duration_seconds?: number;
  stage_statuses?: Record<string, unknown>;
};

export type Transcript = TranscriptResponse & {
  /** Alias used in hooks */
  filename?: string;
};

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
