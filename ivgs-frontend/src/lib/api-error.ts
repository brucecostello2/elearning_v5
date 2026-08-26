/**
 * The server's own words, out of an axios error — WP-63 Task 7.
 *
 * WHY THIS EXISTS. The per-scene Regen button was reported as doing nothing.
 * It was not doing nothing. Measured on node-01, 2026-08-26:
 *
 *   15:15:40.605Z  PATCH  /projects/14f71729/scenes/bc4b52ef        200 OK
 *   15:15:59.961Z  POST   /projects/14f71729/scenes/bc4b52ef/regenerate
 *                                                              409 Conflict
 *
 * The 409 was CORRECT, and it carried the reason: editing the scene moved the
 * storyboard fingerprint, so the approval recorded at 13:41:29 no longer named
 * the storyboard on screen, and WP-62's gate refused the media work. The
 * refusal even says what to do about it. The operator saw none of it, because
 * every regeneration path in the storyboard UI awaited a promise inside a
 * `try/finally` with no `catch`, and SWR's `rollbackOnError` quietly reverted
 * the optimistic "Regenerating…" state.
 *
 * A refusal nobody is shown is indistinguishable from a button that is not
 * wired up. That is the whole of the "regeneration is decorative" finding on
 * the per-scene half.
 *
 * The four shapes below are the four this API actually produces: the
 * structured `{detail: {error: {code, message}}}` envelope every guarded route
 * uses, a bare string detail, FastAPI's own 422 list, and a transport error
 * with no response at all.
 */

export interface ApiErrorInfo {
  message: string;
  /** e.g. "GATE_BLOCKED", "PIPELINE_ALREADY_RUNNING". Absent on 422s. */
  code?: string;
  status?: number;
}

type MaybeAxiosError = {
  response?: {
    status?: number;
    data?: {
      detail?:
        | string
        | { error?: { code?: string; message?: string } }
        | Array<{ msg?: string }>;
    };
  };
  message?: string;
};

export function apiError(err: unknown): ApiErrorInfo {
  const e = err as MaybeAxiosError;
  const status = e?.response?.status;
  const detail = e?.response?.data?.detail;

  if (typeof detail === "string") {
    return { message: detail, status };
  }
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => d?.msg).filter(Boolean);
    if (msgs.length > 0) return { message: msgs.join("; "), status };
  }
  if (detail && typeof detail === "object" && "error" in detail) {
    const inner = (detail as { error?: { code?: string; message?: string } }).error;
    if (inner?.message) {
      return { message: inner.message, code: inner.code, status };
    }
  }
  if (err instanceof Error && err.message) {
    return { message: err.message, status };
  }
  return { message: "The request was refused and gave no reason.", status };
}

/** Just the sentence, for a banner. */
export function apiErrorMessage(err: unknown): string {
  return apiError(err).message;
}
