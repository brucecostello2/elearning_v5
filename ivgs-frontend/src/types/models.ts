/**
 * Model Store types — mirror ivgs-api/app/schemas/model_store.py (AD-01.5.2).
 */

export type ModelStage =
  | "transcript_refinement"
  | "storyboard_generation"
  | "image_generation"
  | "video_generation"
  | "animation_generation"
  | "voiceover_tts"
  | "talking_head"
  | "composition"
  | "translation";

export type ModelEngine =
  | "vllm"
  | "ollama"
  | "comfyui"
  | "coqui"
  | "kokoro"
  | "cogvideox"
  | "wan21"
  | "animatediff"
  | "latentsync"
  | "sadtalker"
  | "remotion"
  | "ffmpeg";

export type ModelTier = "prototype" | "production" | "both";

export type ModelState = "candidate" | "approved" | "deprecated" | "retired";

export type CapabilityDimension =
  | "visual_style"
  | "subject_affinity"
  | "motion_profile"
  | "voice_profile"
  | "language"
  | "quality_bias";

export type NodeAvailabilityStatus = "available" | "loading" | "unavailable";

export interface CapabilityTag {
  dimension: CapabilityDimension;
  value: string;
  weight: number;
}

export interface ModelAvailability {
  node_id: string;
  status: NodeAvailabilityStatus;
  served: boolean;
  last_health_check: string | null;
}

export type WeightPlacementStatus =
  | "fetching"
  | "verified"
  | "failed"
  | "removed";

export interface WeightPlacement {
  id: string;
  node_id: string;
  status: WeightPlacementStatus;
  dest_dir: string | null;
  engine_container: string | null;
  bundle_digest: string | null;
  file_count: number | null;
  bytes_on_disk: number | null;
  checksum_verified: boolean;
  signature_verified: boolean;
  last_error_reason: string | null;
  last_error: string | null;
  fetched_at: string | null;
  fetched_by: string | null;
}

/**
 * WP-65. The states an admin has to tell apart, because each needs a different
 * action. Before WP-65 the Nodes column rendered all of them as the word
 * "none".
 *
 *  available          verified bytes on a node that hosts the engine
 *  not_fetched        a real bundle exists at MBCP; nobody has fetched it
 *  engine_only        MBCP certified the ENGINE IMAGE; no weights exist
 *  no_host            nothing on this fleet serves the engine
 *  no_reference       the row was never ingested from MBCP
 *  unknown_reference  the weights_ref is in a form IVGS cannot speak
 *  fetching / failed  a fetch is in flight, or the last one failed
 */
export type WeightState =
  | "available"
  | "not_fetched"
  | "engine_only"
  | "no_host"
  | "no_reference"
  | "unknown_reference"
  | "fetching"
  | "failed";

export interface WeightStatus {
  state: WeightState;
  label: string;
  detail: string | null;
  verified_nodes: string[];
  /** null means NOT MEASURED. It is never 0-for-unknown. */
  bytes_on_disk: number | null;
  can_fetch: boolean;
  target_node: string | null;
  target_dir: string | null;
  target_container: string | null;
  /** Presence of the MBCP serving token on the API host. Never the value. */
  credentials_present: boolean;
}

export interface FetchWeightsResult {
  accepted: boolean;
  state: WeightState;
  reason: string | null;
  message: string;
  placement: WeightPlacement | null;
  status: WeightStatus;
}

export interface ModelApproval {
  id: string;
  attested_by: string;
  vetting_reference: string;
  checklist: Record<string, unknown>;
  created_at: string;
}

export interface StoreModel {
  id: string;
  name: string;
  display_name: string;
  stage: ModelStage;
  engine: ModelEngine;
  tier: ModelTier;
  state: ModelState;
  description: string | null;
  strengths: string[] | null;
  weaknesses: string[] | null;
  source_url: string | null;
  weights_ref: string | null;
  weights_checksum: string | null;
  license: string | null;
  vram_gb: number | null;
  dynamically_loadable: boolean;
  default_params: Record<string, unknown> | null;
  is_default: boolean;
  enabled: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  capability_tags: CapabilityTag[];
  node_availability: ModelAvailability[];
  /** WP-65: bytes on a node's disk. Distinct from node_availability, which
   *  reports the GPU scheduler's LRU of models a job once loaded. */
  weight_placements: WeightPlacement[];
  /** WP-65: the computed answer to "what should an admin do about this
   *  model's weights". Null only on an API older than v5.24.0-weights. */
  weight_status: WeightStatus | null;
  approvals: ModelApproval[];
}

export interface ModelRegisterPayload {
  name: string;
  display_name: string;
  stage: ModelStage;
  engine: ModelEngine;
  tier: ModelTier;
  description?: string | null;
  source_url?: string | null;
  weights_ref?: string | null;
  weights_checksum?: string | null;
  license?: string | null;
  vram_gb?: number | null;
  dynamically_loadable?: boolean;
  default_params?: Record<string, unknown> | null;
  capability_tags?: CapabilityTag[];
}

export interface ModelUpdatePayload {
  display_name?: string;
  description?: string | null;
  source_url?: string | null;
  vram_gb?: number | null;
  default_params?: Record<string, unknown> | null;
  enabled?: boolean;
  is_default?: boolean;
}

export interface ModelApprovePayload {
  attested_by: string;
  vetting_reference: string;
  checklist: Record<string, unknown>;
}

export const MODEL_STAGES: ModelStage[] = [
  "transcript_refinement",
  "storyboard_generation",
  "image_generation",
  "video_generation",
  "animation_generation",
  "voiceover_tts",
  "talking_head",
  "composition",
  "translation",
];

export const MODEL_ENGINES: ModelEngine[] = [
  "vllm",
  "ollama",
  "comfyui",
  "coqui",
  "kokoro",
  "cogvideox",
  "wan21",
  "animatediff",
  "latentsync",
  "sadtalker",
  "remotion",
  "ffmpeg",
];

export const MODEL_TIERS: ModelTier[] = ["prototype", "production", "both"];

export const CAPABILITY_DIMENSIONS: CapabilityDimension[] = [
  "visual_style",
  "subject_affinity",
  "motion_profile",
  "voice_profile",
  "language",
  "quality_bias",
];

// ===========================================================================
// WP-66 — model selection, per project and per scene
// ===========================================================================

export type SelectionSource = "auto" | "manual" | "preset";

export interface ModelSelection {
  id: string;
  project_id: string;
  /** Non-null on a SCENE-scoped override; null on the project binding. */
  scene_id: string | null;
  stage: ModelStage;
  tier: ModelTier;
  model_id: string;
  selected_by: SelectionSource;
  rationale: string;
  created_at: string;
  /** WP-66: carried so a picker does not have to fetch the whole registry. */
  model_name: string | null;
  model_display_name: string | null;
  model_engine: ModelEngine | null;
  model_state: ModelState | null;
}

/**
 * WHERE a binding came from. Not decoration: WP-60 Task 5 established that a
 * surface presenting mixed provenance as one fact is this codebase's recurring
 * defect, and a resolved model binding has five possible origins that look
 * identical once resolved.
 *
 *  scene      overridden for this scene
 *  selection  chosen for this project by hand
 *  preset     written by applying a library preset
 *  auto       chosen by the planner (POST /plan PERSISTS; it is not a preview)
 *  default    no row anywhere; the stage's is_default model
 *  none       no model bound and no default exists
 */
export type SelectionProvenance =
  | "scene"
  | "selection"
  | "preset"
  | "auto"
  | "default"
  | "none";

export interface SelectionCandidate {
  id: string;
  name: string;
  display_name: string;
  stage: ModelStage;
  engine: ModelEngine;
  tier: ModelTier;
  state: ModelState;
  is_default: boolean;
  vram_gb: number | null;
  /** Whether PUT /selections would accept it. Computed by the same function
   *  the write uses, so the picker cannot offer what the write refuses. */
  selectable: boolean;
  refusal_reason: string | null;
  refusal_message: string | null;
  weight_state: WeightState | null;
  weight_label: string | null;
}

export interface StageBinding {
  stage: ModelStage;
  tier: ModelTier;
  provenance: SelectionProvenance;
  provenance_label: string;
  selection: ModelSelection | null;
  model_id: string | null;
  model_name: string | null;
  model_display_name: string | null;
  /** A binding that resolved but is no longer valid. Surfaced, never silently
   *  rewritten: the user chose this model. */
  warning: string | null;
  candidates: SelectionCandidate[];
}

export interface ProjectSelections {
  project_id: string;
  tier: ModelTier;
  bindings: StageBinding[];
}

export interface ClearSelectionResult {
  cleared: number;
  message: string;
}
