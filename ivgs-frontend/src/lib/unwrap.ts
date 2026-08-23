/**
 * Response-envelope unwrapping (WP-35).
 *
 * WHY THIS EXISTS. This API returns list data in two different shapes and the
 * frontend has no generated client to keep them straight:
 *
 *   PaginatedResponse<T>   { data: T[], total, page, per_page, pages, has_more }
 *       GET /api/v1/projects/{id}/jobs      (jobs.py:31)
 *       GET /api/v1/projects/{id}/assets    (assets.py:38)
 *       GET /api/v1/projects
 *
 *   bare List<T>           T[]
 *       GET /api/v1/projects/{id}/transcripts   (transcripts.py:36)
 *
 *   bare object            T
 *       GET /api/v1/projects/{id}            (ProjectResponse)
 *
 * Getting it wrong is not a cosmetic bug. `useJobs`'s fetcher returned the
 * envelope where an array was expected, and because the fetcher was typed
 * `Promise<any>` the `useSWR<RenderJob[]>` annotation asserted "array" over an
 * object and TypeScript accepted it. The result crashed the project detail page
 * at runtime with `latestData?.some is not a function` -- optional chaining does
 * not help, because the value is present, it is just not an array.
 *
 * `unwrapList` accepts either shape and always returns an array, so a caller can
 * never be handed a non-array where it expects one. It is deliberately total: it
 * has no failure mode, because a list endpoint that returns something
 * unrecognisable should render as "nothing to show", not take the page down.
 */

/** The paginated envelope this API uses for list routes. */
export interface PaginatedEnvelope<T> {
  data: T[];
  total?: number;
  page?: number;
  per_page?: number;
  pages?: number;
  has_more?: boolean;
}

/**
 * Return `payload` as an array, whether it arrived bare or inside a
 * `PaginatedResponse` envelope.
 *
 * Never throws and never returns a non-array:
 *   [1,2,3]                  -> [1,2,3]
 *   {data:[1,2], total:2}    -> [1,2]
 *   {data:[]}                -> []
 *   undefined / null         -> []
 *   {} / 42 / "x"            -> []
 */
export function unwrapList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const inner = (payload as { data?: unknown }).data;
    if (Array.isArray(inner)) return inner as T[];
  }
  return [];
}

/**
 * Return `payload` as a single object, whether it arrived bare or wrapped in a
 * `{ data: ... }` envelope.
 *
 * The mirror of `unwrapList` for detail routes. `GET /projects/{id}` is bare
 * (ProjectResponse); reading `response.data.data` on it is what WP-IVGS-0 F9
 * fixed, and it is what made this page unreachable long enough for the jobs bug
 * to hide behind it.
 */
export function unwrapObject<T>(payload: unknown): T | undefined {
  if (payload === null || payload === undefined) return undefined;
  if (typeof payload !== "object") return payload as T;
  if (Array.isArray(payload)) return undefined;
  const inner = (payload as { data?: unknown }).data;
  // Only treat it as an envelope when `data` is itself a non-array object.
  if (inner && typeof inner === "object" && !Array.isArray(inner)) {
    return inner as T;
  }
  return payload as T;
}
