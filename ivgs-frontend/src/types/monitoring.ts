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
  last_login: string | null;
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

export interface DLQMessage {
  id: string;
  task_name: string;
  error_message: string;
  category: DLQCategory;
  retry_count: number;
  entered_dlq_at: string;
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

export interface FlaggedAsset {
  asset_id: string;
  project_name: string;
  scene_index: number;
  asset_type: string;
  thumbnail_url: string;
  quality_score: number;
  safety_score: number;
  metrics: any;
  project_owner_id?: string;
  score_id?: string;
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

export type StorageTier = "hot" | "warm" | "cold" | "archive" | "HOT" | "WARM" | "COLD" | "ARCHIVE";

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
}

export interface TierMigration {
  asset_id: string;
  project_name: string;
  current_tier: StorageTier;
  target_tier: StorageTier;
  size_bytes: number;
  scheduled_at: string;
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

export interface RetentionPolicy {
  id: string;
  name: string;
  source_tier: StorageTier;
  target_tier: StorageTier | "delete";
  threshold_days: number;
  auto_execute: boolean;
  last_run_at: string | null;
  assets_affected: number;
}

export interface RetentionPolicyUpdate {
  threshold_days?: number;
  auto_execute?: boolean;
}
