/**
 * Scene media-type vocabulary and update payload (WP-43 Task 7).
 *
 * WHY THIS EXISTS. The operator could not set a scene to video or animation:
 * choosing any Media Type other than the current one and pressing Save
 * Changes failed with "Request failed with status 422", so every storyboard
 * stayed all-static. That is a run-blocker, and it is one more instance of
 * the WP-40 §0 family -- a frontend type asserting a vocabulary the API has
 * never accepted.
 *
 * The API's `SceneUpdate.media_type` validator
 * (`ivgs-api/app/schemas/storyboard.py:39`) accepts exactly three LOWERCASE
 * values and rejects everything else:
 *
 *     image | video_clip | animation
 *
 * `src/types/storyboard.ts` declared five UPPERCASE ones -- IMAGE, VIDEO,
 * ANIMATION, TALKING_HEAD, STOCK. Not one of them is accepted, and two of
 * them (TALKING_HEAD, STOCK) name pipelines this route cannot select at all.
 * Reproduced live 2026-08-25 against `ivgs-api:v5.6.5-reviewgate`:
 *
 *   PATCH .../scenes/{sid}  {"media_type":"VIDEO"}  -> 422
 *   {"detail":[{"loc":["body","media_type"],
 *     "msg":"Value error, media_type must be one of: image, video_clip,
 *            animation","input":"VIDEO"}]}
 *
 * The same mismatch was visible without ever pressing Save: the live scenes
 * payload carries `"media_type":"image"`, so `MEDIA_TYPE_ICONS[scene.media_type]`
 * and `MEDIA_TYPE_LABELS[...]` (SceneCard, keyed by the uppercase names)
 * both resolved to `undefined`, and the storyboard's media-type filter
 * compared `"image" === "IMAGE"` and matched nothing at all.
 *
 * `src/types/api.ts:212` already had the union right. The two type files
 * disagreed with each other; the wire settles it.
 */

/** The three values `SceneUpdate` / `SceneCreate` accept, exactly as sent. */
export const MEDIA_TYPES = ["image", "video_clip", "animation"] as const;

export type MediaType = (typeof MEDIA_TYPES)[number];

const MEDIA_TYPE_LABEL: Record<MediaType, string> = {
  image: "Image",
  video_clip: "Video Clip",
  animation: "Animation",
};

const MEDIA_TYPE_ICON: Record<MediaType, string> = {
  image: "🖼️",
  video_clip: "🎬",
  animation: "✨",
};

/**
 * Legacy display names -> wire values.
 *
 * A scene row written before this package could hold anything; accept the
 * old vocabulary on the way IN so an existing storyboard still renders,
 * while only ever sending the three the API takes.
 */
const ALIASES: Record<string, MediaType> = {
  image: "image",
  images: "image",
  still: "image",
  video: "video_clip",
  video_clip: "video_clip",
  videoclip: "video_clip",
  clip: "video_clip",
  animation: "animation",
  animated: "animation",
  motion: "animation",
};

/**
 * Coerce whatever the wire holds to one of the three, or null.
 *
 * Null is deliberate: `media_type` is `Optional[str]` on the API and IS null
 * on scenes the pipeline has not typed yet. Defaulting a null to "image"
 * would silently assert a decision nobody made.
 */
export function normalizeMediaType(value: unknown): MediaType | null {
  if (typeof value !== "string") return null;
  const key = value.trim().toLowerCase();
  if (key.length === 0) return null;
  return ALIASES[key] ?? null;
}

/** Human label for a scene's media type, honest about the untyped case. */
export function mediaTypeLabel(value: unknown): string {
  const t = normalizeMediaType(value);
  if (t) return MEDIA_TYPE_LABEL[t];
  return typeof value === "string" && value.trim().length > 0
    ? value
    : "Not set";
}

/** Icon for a scene's media type; a generic frame when it is not set. */
export function mediaTypeIcon(value: unknown): string {
  const t = normalizeMediaType(value);
  return t ? MEDIA_TYPE_ICON[t] : "🎞️";
}

/** The fields the scene editor holds, before they are filtered for the wire. */
export interface SceneEditDraft {
  narration_text?: string | null;
  visual_description?: string | null;
  media_type?: unknown;
  duration_seconds?: number | null;
}

/** Exactly the keys `SceneUpdate` declares. */
export interface SceneUpdateWire {
  narration_text?: string;
  visual_description?: string | null;
  media_type?: MediaType;
  duration_seconds?: number;
}

/** The API's own bounds: `duration_seconds: float = Field(ge=0.1, le=600.0)`. */
export const DURATION_MIN_SECONDS = 0.1;
export const DURATION_MAX_SECONDS = 600;

/**
 * Build the PATCH body from an edit draft.
 *
 * Two jobs, both of which the old code got wrong:
 *
 * 1. `media_type` is emitted only when it normalises to one of the three.
 *    An unrecognised value is DROPPED rather than sent and rejected -- the
 *    edit to narration still lands instead of the whole save failing.
 *
 * 2. Only the four declared keys survive. The modal used to send
 *    `camera_angle`, `transition_type`, `effects`, `timing_offset_ms` and
 *    `generation_params` as well. Pydantic ignores unknown keys, so those
 *    were never an error -- but they were never STORED either, and the
 *    modal presented them as saved settings. They are now marked in the UI
 *    as local-only rather than silently discarded.
 */
export function sceneUpdatePayload(draft: SceneEditDraft): SceneUpdateWire {
  const out: SceneUpdateWire = {};

  if (typeof draft.narration_text === "string") {
    out.narration_text = draft.narration_text;
  }
  if (draft.visual_description !== undefined) {
    out.visual_description =
      typeof draft.visual_description === "string"
        ? draft.visual_description
        : null;
  }

  const media = normalizeMediaType(draft.media_type);
  if (media) out.media_type = media;

  if (typeof draft.duration_seconds === "number" && Number.isFinite(draft.duration_seconds)) {
    out.duration_seconds = draft.duration_seconds;
  }

  return out;
}

/**
 * Client-side duration check, worded as the server words its own refusal.
 *
 * Returns null when the value is acceptable.
 */
export function durationError(seconds: unknown): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) {
    return "Duration must be a number of seconds.";
  }
  if (seconds < DURATION_MIN_SECONDS || seconds > DURATION_MAX_SECONDS) {
    return `Duration must be between ${DURATION_MIN_SECONDS} and ${DURATION_MAX_SECONDS} seconds.`;
  }
  return null;
}
