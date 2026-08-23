/**
 * Pipeline-job normalisation (WP-40 Task 2).
 *
 * WHY THIS EXISTS. `/monitoring` Pipeline Tracker listed "16 jobs" while
 * RUNNING/COMPLETE/ERROR/PENDING all read 0, AVG DURATION read "—" and every
 * row was labelled "Job #c12fa967" -- a PROJECT id.
 *
 * All four symptoms are one cause: `usePipelineJobs` fetched
 * `/api/v1/projects?expand=jobs` and returned `data.data`. That route is the
 * PROJECT list. `expand` is not a parameter it implements (verified live
 * 2026-08-23: the response has no `jobs` key), so the page was rendering 16
 * projects as if they were jobs. A project has `state`, not `status`, so
 * every `j.status === "RUNNING"` filter matched nothing; a project has no
 * `started_at`/`completed_at`, so the average was 0 and formatted as "—";
 * and `job.id.slice(0,8)` printed the project's id.
 *
 * There is no cross-project job list route on this API -- jobs.py exposes
 * only `GET /projects/{id}/jobs` (project-scoped) and `GET /jobs/{id}`
 * (single). So the aggregate is assembled client-side, which is why the
 * mapping below lives in a plain module: it is testable without a browser.
 *
 * Wire facts, all verified live on 2026-08-23:
 *   - `render_jobs.status` is LOWERCASE: pending | running | success | failed
 *     (the page's constants, filters and badges are all UPPERCASE).
 *   - `render_jobs.started_at` and `.completed_at` are NULL on all 20 rows,
 *     and nothing in ivgs-api, ivgs-workers or shared/ ever writes them --
 *     they are read-only fields. So job-level timing cannot be the duration
 *     source, and `pipeline_checkpoints` (11 rows, started_at on all 11,
 *     completed_at on 8) is.
 */

/** The uppercase vocabulary the monitoring page's filters and badges use. */
export type DisplayJobStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETE"
  | "ERROR"
  | "CANCELLED"
  | "UNKNOWN";

const STATUS_MAP: Record<string, DisplayJobStatus> = {
  pending: "PENDING",
  queued: "PENDING",
  running: "RUNNING",
  in_progress: "RUNNING",
  started: "RUNNING",
  success: "COMPLETE",
  succeeded: "COMPLETE",
  complete: "COMPLETE",
  completed: "COMPLETE",
  failed: "ERROR",
  failure: "ERROR",
  error: "ERROR",
  cancelled: "CANCELLED",
  canceled: "CANCELLED",
  revoked: "CANCELLED",
};

/**
 * Map a wire status to the page's vocabulary.
 *
 * `success` -> COMPLETE and `failed` -> ERROR are the two that mattered:
 * the counters looked for COMPLETE/ERROR and the database holds
 * success/failed, so even with the right data source they would have
 * counted zero.
 */
export function normalizeJobStatus(status: unknown): DisplayJobStatus {
  if (typeof status !== "string" || status.length === 0) return "UNKNOWN";
  const mapped = STATUS_MAP[status.toLowerCase()];
  return mapped ?? "UNKNOWN";
}

/** A job (or checkpoint) whose status is one that will not change again. */
export function isTerminalStatus(status: unknown): boolean {
  const s = normalizeJobStatus(status);
  return s === "COMPLETE" || s === "ERROR" || s === "CANCELLED";
}

/**
 * Worker stage names -> the eight stages the monitoring page draws.
 *
 * The workers checkpoint at a finer grain than the page's DAG: a single
 * MEDIA_GENERATION box covers `image_generation` and `video_generation`, and
 * AUDIO_GENERATION covers `tts_audio`. Unmapped names return null and are
 * dropped rather than rendered as a mystery row.
 */
const STAGE_MAP: Record<string, string> = {
  transcript_refinement: "TRANSCRIPT_REFINEMENT",
  script_refinement: "TRANSCRIPT_REFINEMENT",
  storyboard_generation: "STORYBOARD_GENERATION",
  image_generation: "MEDIA_GENERATION",
  video_generation: "MEDIA_GENERATION",
  media_generation: "MEDIA_GENERATION",
  visual_asset_creation: "MEDIA_GENERATION",
  manifest_generation: "MANIFEST_GENERATION",
  composition_manifest: "MANIFEST_GENERATION",
  tts_audio: "AUDIO_GENERATION",
  audio_generation: "AUDIO_GENERATION",
  audio_production: "AUDIO_GENERATION",
  talking_head_render: "TALKING_HEAD_RENDER",
  talking_head_lipsync: "TALKING_HEAD_RENDER",
  prototype_draft: "PROTOTYPE_DRAFT",
  final_render: "FINAL_RENDER",
  composition_rendering: "FINAL_RENDER",
};

export function checkpointStage(stageName: unknown): string | null {
  if (typeof stageName !== "string" || stageName.length === 0) return null;
  return STAGE_MAP[stageName.toLowerCase()] ?? null;
}

/** One row of `GET /api/v1/jobs/{id}/checkpoints`.checkpoints. */
export interface WireCheckpoint {
  stage_name?: string | null;
  status?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  retry_count?: number | null;
  [key: string]: unknown;
}

/** The shape `PipelineDAG` and the stage table on the page consume. */
export interface DisplayCheckpoint {
  stage: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  fallback_level: string;
  retry_count?: number;
}

function msOf(value: unknown): number | null {
  if (typeof value !== "string" || value.length === 0) return null;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : null;
}

/**
 * Collapse wire checkpoints onto the page's eight display stages.
 *
 * Two checkpoints can land on one box (image_generation + video_generation).
 * The merge is deliberately pessimistic so the DAG cannot claim more
 * progress than the run actually made: any failure makes the box FAILED,
 * otherwise any not-yet-complete member makes it RUNNING, and only an
 * all-complete set is COMPLETE. The span is min(started) -> max(completed),
 * and completed is null while any member is still open.
 */
export function mergeCheckpoints(
  checkpoints: readonly WireCheckpoint[] | null | undefined,
): DisplayCheckpoint[] {
  if (!Array.isArray(checkpoints)) return [];

  const byStage = new Map<string, WireCheckpoint[]>();
  for (const cp of checkpoints) {
    const stage = checkpointStage(cp?.stage_name);
    if (!stage) continue;
    const bucket = byStage.get(stage);
    if (bucket) bucket.push(cp);
    else byStage.set(stage, [cp]);
  }

  const out: DisplayCheckpoint[] = [];
  byStage.forEach((members, stage) => {
    const statuses = members.map((m) => normalizeJobStatus(m?.status));
    const status = statuses.includes("ERROR")
      ? "FAILED"
      : statuses.every((s) => s === "COMPLETE")
      ? "COMPLETE"
      : statuses.every((s) => s === "PENDING")
      ? "PENDING"
      : "RUNNING";

    const starts = members.map((m) => msOf(m?.started_at)).filter((n): n is number => n !== null);
    const endsRaw = members.map((m) => msOf(m?.completed_at));
    const allClosed = endsRaw.every((n) => n !== null);
    const ends = endsRaw.filter((n): n is number => n !== null);

    const retries = members
      .map((m) => (typeof m?.retry_count === "number" ? m.retry_count : 0))
      .reduce((a, b) => a + b, 0);

    out.push({
      stage,
      status,
      started_at: starts.length ? new Date(Math.min(...starts)).toISOString() : null,
      completed_at: allClosed && ends.length ? new Date(Math.max(...ends)).toISOString() : null,
      fallback_level: "L1",
      retry_count: retries,
    });
  });

  return out;
}

/**
 * How long a job took, in milliseconds, or null when it cannot be known.
 *
 * Prefers the job's own timestamps -- correct the day something starts
 * writing them -- and falls back to the span of its checkpoints, which is
 * the only timing this system actually records today.
 */
export function jobDurationMs(
  job: { started_at?: string | null; completed_at?: string | null } | null | undefined,
  checkpoints?: readonly WireCheckpoint[] | null,
): number | null {
  const jobStart = msOf(job?.started_at);
  const jobEnd = msOf(job?.completed_at);
  if (jobStart !== null && jobEnd !== null && jobEnd >= jobStart) {
    return jobEnd - jobStart;
  }

  if (!Array.isArray(checkpoints) || checkpoints.length === 0) return null;
  const starts = checkpoints.map((c) => msOf(c?.started_at)).filter((n): n is number => n !== null);
  const ends = checkpoints.map((c) => msOf(c?.completed_at)).filter((n): n is number => n !== null);
  if (starts.length === 0 || ends.length === 0) return null;

  const span = Math.max(...ends) - Math.min(...starts);
  return span >= 0 ? span : null;
}

/**
 * Mean of the durations that are actually known.
 *
 * Returns null -- not 0 -- when nothing is measurable, so the page can say
 * "no timing data" instead of formatting a fabricated zero as "—" and
 * leaving the operator unable to tell "instant" from "unrecorded".
 */
export function averageDurationMs(durations: readonly (number | null)[]): number | null {
  const known = durations.filter((d): d is number => typeof d === "number" && d >= 0);
  if (known.length === 0) return null;
  return known.reduce((a, b) => a + b, 0) / known.length;
}
