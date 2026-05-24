/**
 * §9 Prompt Management System — Type Definitions
 *
 * All TypeScript interfaces and types for the 3-tier prompt management
 * system, version history, Prompt Playground, and Prompt Library. These
 * types map to the backend API response shapes and form payloads.
 */

// ─── Enums & Literal Types ──────────────────────────────────────────────

/**
 * Prompt tier per §9.1 Table 9-1.
 * Defines the scope at which a prompt is applied.
 */
export type PromptTier =
  | "GLOBAL"   // Tier 1: All projects and scenes, admin only
  | "PROJECT"  // Tier 2: All scenes within a project
  | "SCENE";   // Tier 3: Single scene within a project

/**
 * Prompt type per §9.2 Table 9-2.
 * Each type corresponds to a pipeline stage.
 */
export type PromptType =
  | "master"                // All stages — system-wide instructions
  | "transcript_refinement" // Stage 1 — simplify transcript
  | "storyboard_generation" // Stage 2 — generate storyboard JSON
  | "image_generation"      // Stage 3 — photorealistic/illustrative
  | "video_generation"      // Stage 3 — short video clips
  | "animation_generation"  // Stage 3 — diagram animations
  | "tts_voice"             // Stage 5 — voice style, pace, emphasis
  | "talking_head"          // Stage 6 — lip-sync settings
  | "composition"           // Stages 7–8 — layout rules
  | "translation";          // Localization — translate content

/**
 * Template variable category for grouping in the variable panel.
 */
export type TemplateVariableCategory =
  | "project"
  | "scene"
  | "localization";

// ─── Prompt Record ──────────────────────────────────────────────────────

/**
 * Complete prompt record from the API.
 * Maps to the prompts database table.
 *
 * Per §9.3, every edit creates a new version. The is_active flag
 * determines which version is currently in use. Only one version
 * may be active per prompt_type per scope at any time.
 */
export interface PromptRecord {
  /** Unique prompt identifier (UUID) */
  id: string;

  /** Prompt type per Table 9-2 */
  prompt_type: PromptType;

  /** Scope at which this prompt is defined (maps to backend `scope`) */
  scope: PromptTier;

  /** Project ID (null for GLOBAL scope) */
  project_id: string | null;

  /** Scene ID (null for GLOBAL and PROJECT scopes) */
  scene_id: string | null;

  /** Jinja2 prompt content (maps to backend `prompt_text`) */
  prompt_text: string;

  /** Whether this is the active version */
  is_active: boolean;

  /** Version number (auto-incremented per prompt_type per scope) */
  version: number;

  /** User ID of the creator */
  created_by: string;

  /** ISO 8601 creation timestamp */
  created_at: string;

  /** Optional change note describing this version */
  change_note: string | null;
}

// ─── Prompt Version ─────────────────────────────────────────────────────

/**
 * Prompt version record for version history.
 * Returned by GET /api/v1/prompts/{id}/versions
 */
export interface PromptVersion {
  /** Unique version identifier (UUID) */
  id: string;

  /** Version number */
  version: number;

  /** Jinja2 prompt content for this version (for diff display) */
  prompt_text: string;

  /** Whether this version is currently active */
  is_active: boolean;

  /** User ID who created this version */
  created_by: string | null;

  /** ISO 8601 creation timestamp */
  created_at: string;

  /** Optional change note describing this version */
  change_note: string | null;
}

// ─── Template Variables ─────────────────────────────────────────────────

/**
 * Template variable definition per §9.4.
 * Used for autocomplete and preview in the editor.
 */
export interface TemplateVariable {
  /** Variable name (used in {{ name }} syntax) */
  name: string;

  /** Human-readable description */
  description: string;

  /** Sample value for preview rendering */
  sampleValue: string;

  /** Category for grouping in the variable panel */
  category: TemplateVariableCategory;
}

// ─── API Payloads ───────────────────────────────────────────────────────

/**
 * Payload for creating a new prompt.
 * POST /api/v1/prompts
 */
export interface PromptCreatePayload {
  /** Prompt type */
  prompt_type: PromptType;

  /** Jinja2 prompt content */
  prompt_text: string;

  /** Required description of changes */
  change_note: string;
}

/**
 * Payload for updating a prompt (creates new version per §9.3).
 * PUT /api/v1/prompts/{id}
 */
export interface PromptUpdatePayload {
  /** Updated Jinja2 prompt content */
  prompt_text: string;

  /** Required description of changes */
  change_note: string;
}

/**
 * Payload for rolling back to a specific version.
 * POST /api/v1/prompts/{id}/rollback
 */
export interface PromptRollbackPayload {
  /** Version ID to rollback to */
  target_version_id: string;
}

// ─── Playground Types ───────────────────────────────────────────────────

/**
 * Available model for the Playground per §7.1.1 and §7.1.2.
 * Only self-hosted models — no cloud options per §7.2.
 */
export interface PlaygroundModel {
  /** Model identifier */
  id: string;

  /** Human-readable model name */
  name: string;

  /** Provider: "vLLM" or "Ollama" (no cloud providers) */
  provider: "vLLM" | "Ollama";

  /** Node where the model runs */
  node: string;

  /** VRAM allocation */
  vram: string;

  /** Context window size */
  context: string;

  /** Description of the model's primary use case */
  description: string;
}

/**
 * Playground execution parameters per §8.1.6.
 * Tunable via sliders in the Playground UI.
 */
export interface PlaygroundParameters {
  /** Sampling temperature (0.0 – 2.0) */
  temperature: number;

  /** Maximum tokens to generate (64 – 8192) */
  max_tokens: number;

  /** Nucleus sampling threshold (0.0 – 1.0) */
  top_p: number;
}

/**
 * Playground execution request.
 * POST /api/v1/playground/execute
 */
export interface PlaygroundRequest {
  /** User prompt text */
  prompt: string;

  /** Optional system prompt */
  system_prompt?: string;

  /** Model ID to execute against */
  model_id: string;

  /** Generation parameters */
  parameters: PlaygroundParameters;
}

/**
 * Token usage information from model response.
 */
export interface TokenUsage {
  /** Number of tokens in the prompt */
  prompt_tokens: number;

  /** Number of tokens in the completion */
  completion_tokens: number;

  /** Total tokens (prompt + completion) */
  total_tokens: number;
}

/**
 * Playground execution response.
 */
export interface PlaygroundResponse {
  /** Generated text content */
  content: string;

  /** Model ID that generated the response */
  model_id: string;

  /** Token usage statistics */
  usage: TokenUsage | null;

  /** Response latency in milliseconds */
  latency_ms: number | null;

  /** Finish reason (e.g., "stop", "length") */
  finish_reason: string | null;
}

/**
 * Playground session history entry.
 * Stored client-side for the duration of the session.
 */
export interface PlaygroundHistoryEntry {
  /** Unique entry ID (client-generated UUID) */
  id: string;

  /** ISO 8601 timestamp */
  timestamp: string;

  /** User prompt text */
  prompt: string;

  /** Optional system prompt */
  system_prompt?: string;

  /** Model ID used */
  model_id: string;

  /** Human-readable model name */
  model_name: string;

  /** Parameters used */
  parameters: PlaygroundParameters;

  /** Model response */
  response: PlaygroundResponse;
}

/**
 * Payload for saving a playground result as a prompt version.
 * POST /api/v1/playground/save
 */
export interface PlaygroundSavePayload {
  /** Prompt text to save as template */
  prompt: string;

  /** Optional system prompt */
  system_prompt?: string;

  /** Model ID that generated the response */
  model_id: string;

  /** The response from the model */
  response: PlaygroundResponse;
}

// ─── Library Types ──────────────────────────────────────────────────────

/**
 * Prompt library entry per §9.5.
 * Library templates are stored as inactive prompt versions with a
 * library tag and are not included in the resolution chain until
 * explicitly promoted to active.
 */
export interface PromptLibraryEntry {
  /** Unique library entry ID (UUID) */
  id: string;

  /** Prompt type this template is designed for */
  prompt_type: PromptType;

  /** Scope (typically GLOBAL for library templates) */
  scope: PromptTier;

  /** Jinja2 prompt content */
  prompt_text: string;

  /** Version number */
  version: number;

  /** Whether this version is currently active */
  is_active: boolean;

  /** Project ID (null for GLOBAL) */
  project_id: string | null;

  /** Scene ID (null for GLOBAL/PROJECT) */
  scene_id: string | null;

  /** User who added this to the library */
  created_by: string;

  /** ISO 8601 creation timestamp */
  created_at: string;

  /** Optional change note */
  change_note: string | null;
}

/**
 * Library category definition for the category filter UI.
 */
export interface PromptLibraryCategory {
  /** Category identifier (matches tag values) */
  id: string;

  /** Human-readable label */
  label: string;

  /** Category description */
  description: string;

  /** Emoji icon */
  icon: string;

  /** Tailwind CSS classes for styling */
  color: string;
}

// ─── Resolution Types ───────────────────────────────────────────────────

/**
 * Prompt resolution result showing the effective prompt
 * and its source tier per §9.1 resolution order.
 */
export interface PromptResolution {
  /** The effective prompt record */
  prompt: PromptRecord;

  /** The tier from which this prompt was resolved */
  resolved_from: PromptTier;

  /** Whether this is an inherited value (no override at requested tier) */
  is_inherited: boolean;

  /** Chain of tiers checked during resolution */
  resolution_chain: {
    tier: PromptTier;
    found: boolean;
    prompt_id: string | null;
  }[];
}
