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
