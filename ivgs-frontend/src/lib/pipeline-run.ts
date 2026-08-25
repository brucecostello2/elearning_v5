/**
 * Which job the Overview's Pipeline Progress strip describes (WP-43 Task 5).
 *
 * WHY THIS EXISTS. WP-40 §2.6 rewired the strip to read real checkpoints,
 * and that half is correct -- `mergeCheckpoints` maps the worker's
 * lowercase `stage_name` onto the eight display stages and normalises
 * `complete`/`failed` to the page's vocabulary. It still rendered all-grey,
 * and it was NOT a caching artifact.
 *
 * The cause is job SELECTION. `PipelineTracker` took `jobs[0]` -- the newest
 * row of `GET /projects/{id}/jobs`, which is ordered newest-first. On the
 * reference project c12fa967 that is `d3842fdf`, a `storyboard_generation`
 * job created 2026-08-25T00:40:35Z that is still `pending` and has written
 * ZERO checkpoints. Measured live 2026-08-25, all ten jobs:
 *
 *   d3842fdf storyboard_generation pending 2026-08-25  0 checkpoints
 *   c4249f92 storyboard_generation pending 2026-08-25  0
 *   7d6a44b2 storyboard_generation pending 2026-08-23  0
 *   4646aeba storyboard_generation pending 2026-08-23  0
 *   c57ec7b7 storyboard_generation pending 2026-08-23  0
 *   9fdea8ae storyboard_generation pending 2026-08-23  0
 *   6a16e1a6 storyboard_generation pending 2026-08-23  0
 *   bd99fe37 transcript_refinement success 2026-08-23  7 checkpoints, 6 complete
 *   e408515a transcript_refinement failed  2026-08-23  2 checkpoints, 1 failed
 *   768c4b59 transcript_refinement failed  2026-08-23  2, both unmappable probes
 *
 * So the run that actually produced this project's draft is `bd99fe37`, the
 * EIGHTH row. Seven checkpoint-less rows stood in front of it and the strip
 * faithfully reported the emptiness of the newest one.
 *
 * The fix is to pick the newest job that has checkpoints the display can
 * map, and to name it, so "grey" always means "this run did not reach that
 * stage" and never "the strip is looking at a different row".
 *
 * Deliberately NOT done: merging checkpoints across all ten jobs. `e408515a`
 * holds a FAILED `storyboard_generation` from a superseded 15:24 attempt
 * that `bd99fe37` then completed at 16:03. A cross-job merge is pessimistic
 * (any failure wins), so it would paint Storyboard Generation red over a
 * stage that demonstrably succeeded. One run, named, is the honest unit.
 */

/** The checkpoint fields this module needs, after `mergeCheckpoints`. */
export interface RunCheckpoint {
  stage: string;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  fallback_level?: string;
  retry_count?: number;
}

/** One candidate job with its already-merged checkpoints. */
export interface RunCandidate {
  id: string;
  created_at?: string | null;
  job_type?: string | null;
  status?: string | null;
  checkpoints: readonly RunCheckpoint[];
}

/** What the strip renders. */
export interface SelectedRun {
  /** The job whose checkpoints are shown, or null when none has any. */
  jobId: string | null;
  jobType: string | null;
  jobStatus: string | null;
  createdAt: string | null;
  checkpoints: RunCheckpoint[];
  /** How many jobs were examined. */
  examined: number;
  /** Newer jobs that had no mappable checkpoint -- the reason for the bug. */
  newerWithoutCheckpoints: number;
}

function timeOf(value: unknown): number {
  if (typeof value !== "string" || value.length === 0) return 0;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : 0;
}

/**
 * Choose the run to display.
 *
 * Newest-first by `created_at`, falling back to the order given when the
 * timestamps tie or are missing -- the route already returns newest-first,
 * so that fallback preserves its ordering rather than inventing one.
 */
export function selectPipelineRun(
  candidates: readonly RunCandidate[] | null | undefined,
): SelectedRun {
  const list = Array.isArray(candidates) ? candidates.filter(Boolean) : [];

  const ordered = list
    .map((c, i) => ({ c, i }))
    .sort((a, b) => {
      const d = timeOf(b.c.created_at) - timeOf(a.c.created_at);
      return d !== 0 ? d : a.i - b.i;
    })
    .map((x) => x.c);

  let newerWithoutCheckpoints = 0;
  for (const cand of ordered) {
    const cps = Array.isArray(cand.checkpoints) ? cand.checkpoints : [];
    if (cps.length === 0) {
      newerWithoutCheckpoints += 1;
      continue;
    }
    return {
      jobId: cand.id,
      jobType: cand.job_type ?? null,
      jobStatus: cand.status ?? null,
      createdAt: cand.created_at ?? null,
      checkpoints: [...cps],
      examined: ordered.length,
      newerWithoutCheckpoints,
    };
  }

  return {
    jobId: null,
    jobType: null,
    jobStatus: null,
    createdAt: null,
    checkpoints: [],
    examined: ordered.length,
    newerWithoutCheckpoints,
  };
}

/** The eight display stages, in pipeline order. Shared with the strip. */
export const PIPELINE_STAGE_IDS = [
  "TRANSCRIPT_REFINEMENT",
  "STORYBOARD_GENERATION",
  "MEDIA_GENERATION",
  "MANIFEST_GENERATION",
  "AUDIO_GENERATION",
  "TALKING_HEAD_RENDER",
  "PROTOTYPE_DRAFT",
  "FINAL_RENDER",
] as const;

export type StageDisplayStatus =
  | "pending"
  | "running"
  | "complete"
  | "failed";

/**
 * Fold a run's checkpoints onto the eight stages.
 *
 * A stage with no checkpoint stays "pending" -- which now means "this run
 * did not reach it", because the run is a real one by construction.
 */
export function stageStatuses(
  checkpoints: readonly RunCheckpoint[] | null | undefined,
): Record<string, StageDisplayStatus> {
  const out: Record<string, StageDisplayStatus> = {};
  for (const id of PIPELINE_STAGE_IDS) out[id] = "pending";

  if (!Array.isArray(checkpoints)) return out;
  for (const cp of checkpoints) {
    const stage = typeof cp?.stage === "string" ? cp.stage : null;
    if (!stage || !(stage in out)) continue;
    const s = typeof cp?.status === "string" ? cp.status.toUpperCase() : "";
    out[stage] =
      s === "COMPLETE"
        ? "complete"
        : s === "FAILED"
        ? "failed"
        : s === "RUNNING"
        ? "running"
        : "pending";
  }
  return out;
}
