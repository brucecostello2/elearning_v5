/**
 * Null-safe text helpers (WP-40 Task 5 / ledger P1.4r).
 *
 * WHY THIS EXISTS. The project-detail chunk threw
 * "Cannot read properties of undefined (reading 'split')". WP-38 §3 audited
 * the tree and produced a shortlist of unguarded `.split(` sites but could
 * not identify which one fired without a browser.
 *
 * It is `TranscriptEditor.tsx:33`, and the wire proves it without a browser:
 *
 *   GET /api/v1/projects/{id}/transcripts  ->  TranscriptResponse
 *   (schemas/transcript.py:13) sends id, project_id, sequence_order,
 *   original_asset_id, refined_text, language_code, created_at, updated_at.
 *
 * There is no `original_text` -- and there is no `original_text` COLUMN on
 * the `transcripts` table either; the source document lives in an asset
 * referenced by `original_asset_id`. The frontend's `TranscriptResponse`
 * nevertheless declared `original_text: string` (non-optional), the
 * transcript page passed `transcript.original_text` straight into
 * `TranscriptEditor`, and `computeLineDiff` called `original.split("\n")` on
 * `undefined`. Verified live 2026-08-23 on project c12fa967: the sole
 * transcript row has no `original_text` key.
 *
 * Same family again: a type asserting a field the wire does not have
 * (WP-35 envelope, WP-38 bare array, WP-40 asset URLs).
 *
 * These helpers are deliberately total -- they have no failure mode, because
 * a missing string should render as an empty pane, not take the page down.
 */

/** Coerce anything to a string; null/undefined/non-strings become "". */
export function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

/**
 * Split into lines, safely.
 *
 * `splitLines(undefined)` is `[]`, not a throw and not `[""]`: an absent
 * document has zero lines, and callers that render `.length` should show 0.
 */
export function splitLines(value: unknown): string[] {
  const text = asText(value);
  if (text.length === 0) return [];
  return text.split("\n");
}

/** Line count, safely. 0 for absent or empty text. */
export function lineCount(value: unknown): number {
  return splitLines(value).length;
}

/** Split on a separator, safely. Returns [] for absent input. */
export function splitOn(value: unknown, separator: string): string[] {
  const text = asText(value);
  if (text.length === 0) return [];
  return text.split(separator);
}

/** True when the value is a non-empty string. */
export function hasText(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}
