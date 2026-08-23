/**
 * §8.1.3 Storyboard Tab — Type Definitions
 *
 * All TypeScript interfaces and types for the storyboard editor,
 * scene cards, scene editing modal, timeline view, and drag-drop
 * operations. These types map to the backend API response shapes
 * and form payloads.
 */

// ─── Enums & Literal Types ──────────────────────────────────────────────

/**
 * Scene status values.
 * Matches the backend scene.status column enum.
 */
export type SceneStatus =
  | "PENDING"
  | "GENERATING"
  | "COMPLETE"
  | "ERROR"
  | "REGENERATING";

/**
 * Media type for a scene per Table 9-2.
 * Determines which AI pipeline stage generates the visual asset.
 */
export type MediaType =
  | "IMAGE"       // Static image via FLUX.1/SDXL (§7.1.3)
  | "VIDEO"       // Short video clip via CogVideoX/Wan2.1 (§7.1.4)
  | "ANIMATION"   // Motion graphics via Remotion/AnimateDiff (§7.1.8)
  | "TALKING_HEAD" // Lip-synced presenter via LatentSync/SadTalker (§7.1.7)
  | "STOCK";      // User-uploaded stock footage or image

/**
 * Camera angle/shot type for visual generation.
 * Used in the scene edit modal and passed to image/video generation prompts.
 */
export type CameraAngle =
  | "WIDE"
  | "MEDIUM"
  | "CLOSE_UP"
  | "EXTREME_CLOSE_UP"
  | "BIRD_EYE"
  | "LOW_ANGLE"
  | "HIGH_ANGLE"
  | "DUTCH_ANGLE"
  | "OVER_THE_SHOULDER"
  | "POV";

/**
 * Transition type between scenes.
 * Applied during the composition stage (Stages 7–8).
 */
export type TransitionType =
  | "CUT"
  | "FADE_IN"
  | "FADE_OUT"
  | "CROSS_DISSOLVE"
  | "WIPE_LEFT"
  | "WIPE_RIGHT"
  | "ZOOM_IN"
  | "ZOOM_OUT"
  | "SLIDE_LEFT"
  | "SLIDE_RIGHT"
  | "NONE";

/**
 * Visual effect applied to a scene.
 * Ken Burns and pan/zoom effects are used as L2/L3 fallbacks (§7.1.8).
 */
export type SceneEffect =
  | "KEN_BURNS"
  | "PAN_LEFT"
  | "PAN_RIGHT"
  | "ZOOM_SLOW"
  | "ZOOM_FAST"
  | "PARALLAX"
  | "VIGNETTE"
  | "COLOR_GRADE_WARM"
  | "COLOR_GRADE_COOL"
  | "BLUR_BACKGROUND"
  | "DEPTH_OF_FIELD"
  | "LETTERBOX";

/**
 * View mode for the storyboard page.
 * Grid shows scene cards, timeline shows horizontal duration bars.
 */
export type StoryboardViewMode = "grid" | "timeline";

// ─── Scene Interface ────────────────────────────────────────────────────

/**
 * Complete scene record from the API.
 * Maps to the scenes database table.
 */
export interface Scene {
  /** Unique scene identifier (UUID) */
  id: string;

  /** Parent project ID */
  project_id: string;

  /** Zero-based scene index determining display and composition order */
  scene_index: number;

  /** Full narration text for this scene (TTS input) */
  narration_text: string;

  /** Visual description for image/video generation prompt */
  visual_description: string | null;

  /** Media type determining which generation pipeline to use */
  media_type: MediaType;

  /** Scene duration in seconds (0.5 – 120) */
  duration_seconds: number | null;

  /** Current generation/processing status */
  status: SceneStatus;

  /** Camera angle for visual generation */
  camera_angle: CameraAngle | null;

  /** Transition type to the next scene */
  transition_type: TransitionType | null;

  /** Array of visual effects applied to this scene */
  effects: SceneEffect[] | null;

  /** Timing offset from video start in milliseconds */
  timing_offset_ms: number | null;

  /** Custom generation parameters (JSON object) */
  generation_params: Record<string, unknown> | null;

  /** URL to the scene thumbnail image */
  /*
   * WP-40 addendum: `thumbnail_url` used to be declared here and is gone.
   * The identifier exists nowhere in ivgs-api and the live scenes payload has
   * exactly nine keys. A scene's picture is its image ASSET, linked by
   * `assets.scene_id` -- see `SceneThumbnail`.
   */

  /** Reference to the prompt version used for generation (§9.3) */
  generation_prompt_id: string | null;

  /** Error message if status is ERROR */
  error_message: string | null;

  /** ISO 8601 creation timestamp */
  created_at: string;

  /** ISO 8601 last update timestamp */
  updated_at: string;
}

// ─── API Payloads ───────────────────────────────────────────────────────

/**
 * Payload for updating a scene.
 * Sent as PATCH /api/v1/projects/{id}/scenes/{sid}
 */
export interface SceneUpdatePayload {
  narration_text?: string;
  visual_description?: string | null;
  media_type?: MediaType;
  duration_seconds?: number;
  camera_angle?: CameraAngle | null;
  transition_type?: TransitionType | null;
  effects?: SceneEffect[] | null;
  timing_offset_ms?: number;
  generation_params?: Record<string, unknown>;
}

/**
 * Payload for reordering scenes.
 * Sent as PUT /api/v1/projects/{id}/scenes/reorder
 */
export interface SceneReorderPayload {
  /** Ordered array of scene IDs in their new positions */
  scene_ids: string[];
}

/**
 * Payload for batch operations on scenes.
 * Used by batch-delete and batch-regenerate endpoints.
 */
export interface SceneBatchPayload {
  /** Array of scene IDs to operate on */
  scene_ids: string[];
}

// ─── API Responses ──────────────────────────────────────────────────────

/**
 * Response shape from GET /api/v1/projects/{id}/scenes
 */
export interface StoryboardResponse {
  /** Array of scene records */
  scenes: Scene[];
  /** Total scene count */
  total: number;
  /** Project ID */
  project_id: string;
}

// ─── Timeline Types ─────────────────────────────────────────────────────

/**
 * Computed timing data for a scene in the timeline view.
 */
export interface SceneTiming {
  /** Scene record */
  scene: Scene;
  /** Start time in seconds from video beginning */
  startTime: number;
  /** End time in seconds from video beginning */
  endTime: number;
  /** Width percentage relative to total duration */
  widthPercent: number;
}

/**
 * Timeline tick mark for the ruler.
 */
export interface TimelineTick {
  /** Position as percentage of total width */
  position: number;
  /** Human-readable time label (e.g., "1:30") */
  label: string;
}

/**
 * Timeline zoom configuration.
 */
export interface TimelineZoomConfig {
  /** Current zoom level (0.5 = 50%, 1 = 100%, 4 = 400%) */
  level: number;
  /** Minimum allowed zoom */
  min: number;
  /** Maximum allowed zoom */
  max: number;
  /** Zoom step size */
  step: number;
}
