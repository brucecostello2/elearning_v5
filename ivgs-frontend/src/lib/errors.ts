/**
 * Server error-message extraction (WP-43).
 *
 * WHY THIS EXISTS. Four separate operator-visible failures in this package
 * all showed the same useless string -- "Request failed with status 422" --
 * over a response body that named the exact problem in plain English.
 *
 * `api-client.request` already flattened the three ENVELOPE shapes this API
 * uses for deliberate errors:
 *
 *   {"detail": "..."}                              (plain HTTPException)
 *   {"detail": {"error": {"message": "..."}}}      (the coded 409/404 shape)
 *   {"error": {...}}
 *
 * What it did not handle is the shape FastAPI itself produces when request
 * VALIDATION fails, which is the one a 422 always has: `detail` is an ARRAY
 * of per-field error objects. The old reducer explicitly skipped arrays
 * (`!Array.isArray(v)`), returned null, and fell through to the bare status.
 *
 * The four bodies below are real, captured live against
 * `ivgs-api:v5.6.5-reviewgate` on 2026-08-25:
 *
 *   PATCH /projects/{id}/scenes/{sid}   {"detail":[{"type":"value_error",
 *     "loc":["body","media_type"],"msg":"Value error, media_type must be one
 *     of: image, video_clip, animation","input":"VIDEO"}]}
 *
 *   POST /projects/{id}/languages       {"detail":[{"type":"value_error",
 *     "loc":["body","language_code"],"msg":"Value error, Unsupported language
 *     code 'es'. Supported: ar-SA, de-DE, en-GB, en-US, es-ES, fr-FR, ja-JP,
 *     zh-CN","input":"es"}]}
 *
 *   POST /auth/refresh                  {"detail":[{"type":"missing",
 *     "loc":["body"],"msg":"Field required","input":null}]}
 *
 *   POST /projects/{id}/languages/{lid}/retry
 *     {"detail":[{"type":"uuid_parsing","loc":["path","variant_id"],
 *      "msg":"Input should be a valid UUID, ...","input":"en-US"}]}
 *
 * Every one of those sentences is more useful than the status code, and the
 * operator saw none of them.
 *
 * The `msg` text is passed through VERBATIM, Pydantic's "Value error, "
 * prefix included. Rewriting it would mean this module deciding what the
 * server meant, which is the habit that produced the bare status in the
 * first place.
 */

/** One entry of FastAPI's `detail` array on a 422. */
export interface ValidationErrorItem {
  loc?: unknown;
  msg?: unknown;
  type?: unknown;
  input?: unknown;
  [key: string]: unknown;
}

/**
 * The field a validation item is about, as the operator would name it.
 *
 * `loc` is `["body", "media_type"]` / `["path", "variant_id"]` /
 * `["body"]`. The first element is the request PART, not a field, so it is
 * dropped -- unless it is all there is, which is what a wholly missing body
 * looks like.
 */
export function validationFieldName(loc: unknown): string | null {
  if (!Array.isArray(loc) || loc.length === 0) return null;
  const parts = loc
    .map((p) => (typeof p === "string" || typeof p === "number" ? String(p) : null))
    .filter((p): p is string => p !== null && p.length > 0);
  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0]!;
  return parts.slice(1).join(".");
}

/**
 * Flatten a FastAPI 422 `detail` array into "field: message" lines.
 *
 * Returns an empty array for anything that is not that shape, so callers
 * can fall through to the envelope reducer below.
 */
export function validationMessages(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [];
  const out: string[] = [];
  for (const raw of detail) {
    if (!raw || typeof raw !== "object") continue;
    const item = raw as ValidationErrorItem;
    if (typeof item.msg !== "string" || item.msg.length === 0) continue;
    const field = validationFieldName(item.loc);
    out.push(field ? `${field}: ${item.msg}` : item.msg);
  }
  return out;
}

/**
 * Reduce any deliberate-error envelope this API uses to a single string.
 *
 * Kept separate from the validation path so the precedence is explicit:
 * a 422's array is read FIRST, because `pickMessage` would otherwise walk
 * past it and reach for a nested `error`/`message` that a 422 never has.
 */
export function envelopeMessage(body: unknown): string | null {
  if (typeof body === "string") return body.length > 0 ? body : null;
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const o = body as Record<string, unknown>;
  return (
    envelopeMessage(o["message"]) ??
    envelopeMessage(o["detail"]) ??
    envelopeMessage(o["error"]) ??
    null
  );
}

/**
 * The message to show for a failed response.
 *
 * `status` is used only for the last-resort fallback, which now means
 * exactly what it says: the server sent nothing readable at all.
 */
export function apiErrorMessage(body: unknown, status: number): string {
  const detail =
    body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>)["detail"]
      : undefined;

  const validation = validationMessages(detail);
  if (validation.length > 0) return validation.join("; ");

  /* A body that IS the array (some proxies unwrap `detail`). */
  const bare = validationMessages(body);
  if (bare.length > 0) return bare.join("; ");

  return envelopeMessage(body) ?? `Request failed with status ${status}`;
}

/**
 * Per-field validation errors, for forms that can point at the input.
 *
 * The Model Store approve dialog needs this: its checklist textarea used to
 * fail with no message anywhere the operator could see it.
 */
export function fieldErrors(body: unknown): Record<string, string> {
  const detail =
    body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>)["detail"]
      : body;
  const out: Record<string, string> = {};
  if (!Array.isArray(detail)) return out;
  for (const raw of detail) {
    if (!raw || typeof raw !== "object") continue;
    const item = raw as ValidationErrorItem;
    if (typeof item.msg !== "string") continue;
    const field = validationFieldName(item.loc);
    if (field && !(field in out)) out[field] = item.msg;
  }
  return out;
}
