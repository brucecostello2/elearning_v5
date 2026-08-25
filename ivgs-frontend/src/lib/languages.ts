/**
 * Language-variant vocabulary and progress honesty (WP-43 Task 3).
 *
 * WHY THIS EXISTS.
 *
 * (a) Adding a language always failed. The form offered bare ISO-639-1 codes
 *     -- en, es, fr, de, pt, ja, zh, ko, ar, hi -- and the API's
 *     `LanguageVariantCreate` validator
 *     (`ivgs-api/app/schemas/language_variant.py:24`) accepts exactly eight
 *     BCP-47 codes and rejects everything else. Not one of the ten offered
 *     was among them. Reproduced live 2026-08-25:
 *
 *       POST /projects/{id}/languages {"language_code":"es"} -> 422
 *       {"detail":[{"loc":["body","language_code"],
 *         "msg":"Value error, Unsupported language code 'es'. Supported:
 *                ar-SA, de-DE, en-GB, en-US, es-ES, fr-FR, ja-JP, zh-CN",
 *         "input":"es"}]}
 *
 *     `pt`, `ko` and `hi` had no accepted form at all, so three of the ten
 *     entries were pure invention.
 *
 * (b) The variants table showed "PENDING 0%" for EN-US although an EN-US
 *     draft exists (`draft_720p_en-US.mp4`, 6,005,929 bytes, asset
 *     72964509-…). The 0% was not a measurement. `LanguageVariantResponse`
 *     (`schemas/language_variant.py:35`) sends exactly:
 *
 *       id, project_id, language_code, state, final_render_1080p_id,
 *       final_render_4k_id, created_at
 *
 *     There is no `progress_percent`, no `status` and no `updated_at`, and
 *     `language_variants` on the project detail payload is thinner still --
 *     `{language_code, state}` and nothing else, verified live. The table
 *     read `variant.progress_percent || 0`, so an absent field rendered as a
 *     confident zero. Nothing anywhere in ivgs-api, ivgs-workers or shared/
 *     writes a per-language progress figure; the field does not exist to be
 *     read. See the report's backend-gap note.
 */

/** Exactly `SUPPORTED_LANGUAGES` in `schemas/language_variant.py:11`. */
export const SUPPORTED_LANGUAGES: { code: string; label: string }[] = [
  { code: "en-US", label: "English (United States)" },
  { code: "en-GB", label: "English (United Kingdom)" },
  { code: "es-ES", label: "Spanish (Spain)" },
  { code: "fr-FR", label: "French (France)" },
  { code: "de-DE", label: "German (Germany)" },
  { code: "zh-CN", label: "Chinese (Simplified, China)" },
  { code: "ja-JP", label: "Japanese (Japan)" },
  { code: "ar-SA", label: "Arabic (Saudi Arabia)" },
];

const LABEL_BY_CODE = new Map(
  SUPPORTED_LANGUAGES.map((l) => [l.code.toLowerCase(), l.label]),
);

/** Whether the API will accept this code without a 422. */
export function isSupportedLanguage(code: unknown): boolean {
  return (
    typeof code === "string" && LABEL_BY_CODE.has(code.trim().toLowerCase())
  );
}

/**
 * Display name for a variant.
 *
 * An unsupported code is shown as itself rather than mapped to a guess --
 * a project could already hold a row this list does not cover.
 */
export function languageLabel(code: unknown): string {
  if (typeof code !== "string" || code.trim().length === 0) return "Unknown";
  return LABEL_BY_CODE.get(code.trim().toLowerCase()) ?? code;
}

/** The subset of `SUPPORTED_LANGUAGES` not already on the project. */
export function addableLanguages(
  existing: readonly unknown[] | null | undefined,
): { code: string; label: string }[] {
  const taken = new Set(
    (Array.isArray(existing) ? existing : [])
      .map((c) => (typeof c === "string" ? c.trim().toLowerCase() : null))
      .filter((c): c is string => c !== null),
  );
  return SUPPORTED_LANGUAGES.filter((l) => !taken.has(l.code.toLowerCase()));
}

/** The fields a variant row can actually carry. */
export interface LanguageVariantLike {
  id?: string | null;
  language_code?: string | null;
  state?: string | null;
  final_render_1080p_id?: string | null;
  final_render_4k_id?: string | null;
  created_at?: string | null;
  /**
   * Neither of these is sent by this API. They are declared so that the two
   * readers below can look for them WITHOUT an index signature -- an index
   * signature would make every real response type structurally incompatible
   * with this one, and would also let any typo compile.
   */
  progress_percent?: number | null;
  status?: string | null;
}

/**
 * Per-language completion, or null when it is not measured.
 *
 * Returns a number ONLY if a future payload actually carries one. Today it
 * returns null for every row on this API, which is what makes the table say
 * "not tracked yet" instead of "0%".
 */
export function variantProgressPercent(
  variant: LanguageVariantLike | null | undefined,
): number | null {
  const raw = variant?.progress_percent;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  if (raw < 0 || raw > 100) return null;
  return raw;
}

/**
 * What a variant's `state` means, uppercased for the badge.
 *
 * The wire value is LOWERCASE ("pending"); the badge vocabulary is upper.
 * `status` is read first only so that a payload which one day gains it is
 * handled, and it is not asserted to exist.
 */
export function variantState(
  variant: LanguageVariantLike | null | undefined,
): string {
  const raw = variant?.status ?? variant?.state;
  if (typeof raw !== "string" || raw.trim().length === 0) return "UNKNOWN";
  return raw.trim().toUpperCase();
}

/** A variant whose localisation run can be retried. */
export function isRetryableVariant(
  variant: LanguageVariantLike | null | undefined,
): boolean {
  const s = variantState(variant);
  return s === "FAILED" || s === "ERROR";
}

/**
 * Whether a rendered output exists for this variant.
 *
 * The only completion signal the payload genuinely carries: a final render
 * id at either resolution. Used to caption the row rather than to invent a
 * percentage from it.
 */
export function variantHasRender(
  variant: LanguageVariantLike | null | undefined,
): boolean {
  return Boolean(variant?.final_render_1080p_id || variant?.final_render_4k_id);
}
