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
  camera_angle?: string | null;
  transition_type?: string | null;
  effects?: string[] | null;
  timing_offset_ms?: number | null;
  generation_params?: Record<string, unknown> | null;
}

/** Exactly the keys `SceneUpdate` declares. */
export interface SceneUpdateWire {
  narration_text?: string;
  visual_description?: string | null;
  media_type?: MediaType;
  duration_seconds?: number;
  camera_angle?: string | null;
  transition_type?: string | null;
  effects?: string[] | null;
  timing_offset_ms?: number | null;
  generation_params?: Record<string, unknown> | null;
}

/**
 * `SceneUpdate.timing_offset_ms: int = Field(ge=-60000, le=60000)`.
 *
 * A timing offset is a nudge against the narration; a change larger than a
 * minute is a duration edit or a reorder, and both have their own controls.
 */
export const TIMING_OFFSET_MIN_MS = -60000;
export const TIMING_OFFSET_MAX_MS = 60000;
/** `SceneUpdate` bounds on the effects list. */
export const EFFECTS_MAX = 32;

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
 * 2. All NINE declared keys survive, as of WP-45.
 *
 *    `camera_angle`, `transition_type`, `effects`, `timing_offset_ms` and
 *    `generation_params` used to be sent and dropped: Pydantic ignores keys a
 *    model does not declare, so there was no error on either side and the modal
 *    presented them as saved settings. WP-43 could only label them "Not saved
 *    to the server"; WP-45 gave them columns (migration 0028) and a schema, so
 *    they are sent for real and the notices are gone.
 *
 *    They are emitted only when the draft actually carries them, because the
 *    route reads `model_dump(exclude_unset=True)`: an omitted key leaves the
 *    stored value alone, and an explicit `null` clears it. Sending `null` for a
 *    field the operator never touched would wipe it on every save.
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

  // WP-45 / WP-43 D-2. `undefined` means "not part of this edit" and is left
  // off the wire entirely; `null` means "clear it" and is sent.
  if (draft.camera_angle !== undefined) {
    out.camera_angle = emptyToNull(draft.camera_angle);
  }
  if (draft.transition_type !== undefined) {
    out.transition_type = emptyToNull(draft.transition_type);
  }
  if (draft.effects !== undefined) {
    out.effects = Array.isArray(draft.effects)
      ? draft.effects
          .filter((e): e is string => typeof e === "string" && e.trim().length > 0)
          .slice(0, EFFECTS_MAX)
      : null;
  }
  if (draft.timing_offset_ms !== undefined) {
    out.timing_offset_ms =
      typeof draft.timing_offset_ms === "number" &&
      Number.isFinite(draft.timing_offset_ms)
        ? Math.round(draft.timing_offset_ms)
        : null;
  }
  if (draft.generation_params !== undefined) {
    // Only a plain object reaches the wire. The route refuses anything else,
    // and a 422 on generation params would fail the whole save including the
    // narration edit the operator actually came for.
    out.generation_params =
      draft.generation_params &&
      typeof draft.generation_params === "object" &&
      !Array.isArray(draft.generation_params)
        ? draft.generation_params
        : null;
  }

  return out;
}

/** "" and whitespace mean "cleared"; the API stores null, not an empty string. */
function emptyToNull(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * Client-side timing-offset check, worded as the server words its own refusal.
 *
 * Returns null when the value is acceptable.
 */
export function timingOffsetError(ms: unknown): string | null {
  if (ms === null || ms === undefined) return null;
  if (typeof ms !== "number" || !Number.isFinite(ms)) {
    return "Timing offset must be a whole number of milliseconds.";
  }
  if (ms < TIMING_OFFSET_MIN_MS || ms > TIMING_OFFSET_MAX_MS) {
    return `Timing offset must be between ${TIMING_OFFSET_MIN_MS} and ${TIMING_OFFSET_MAX_MS} ms.`;
  }
  return null;
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

/* ---------------------------------------------------------------------------
 * Scene numbering — WP-63 Task 5
 * -------------------------------------------------------------------------*/

/**
 * WHAT AN OPERATOR SEES ON A CARD, AND WHAT EVERYTHING ELSE CALLS THE SAME SCENE.
 *
 * The storyboard cards, the timeline and the edit modal all rendered
 * `scene_index + 1` — scenes 1 to 9. Every other surface in the system speaks
 * `scene_index`, zero-based: the storyboard rows, the checkpoint data, the
 * worker logs, the translation flags, and the rejection this package started
 * from ("scene indexes 0, 2 and 7"). So an operator told that scene 0 failed
 * had to do arithmetic, in their head, in the wrong direction, to find the
 * card — and the two conventions collide in the middle of the range, where
 * "scene 5" names two different scenes depending on who said it.
 *
 * That is not hypothetical. The incident report for this package says *"scene 5
 * teaches 92 + 230 = 322 and its visual is a hand holding a pencil"*. In the
 * database that is `scene_index = 4`; `scene_index = 5` is "Let's try another
 * one: 32 times 21", a different scene entirely.
 *
 * BOTH ARE SHOWN, and the zero-based one leads, because it is the one that
 * appears in every message an operator has to act on. `sceneBadge` is what
 * goes in the small round badge; `sceneTitle` is the tooltip and accessible
 * name that spells the pairing out.
 */

/** The badge text: the index the rest of the system speaks. */
export function sceneBadge(sceneIndex: number): string {
  return `#${sceneIndex}`;
}

/** The long form, for `title` and `aria-label`: both numbers, once. */
export function sceneTitle(sceneIndex: number): string {
  return `scene_index ${sceneIndex} (the ${ordinal(sceneIndex + 1)} scene)`;
}

function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}
