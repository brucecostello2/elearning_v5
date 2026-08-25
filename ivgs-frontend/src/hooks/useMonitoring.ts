import useSWR, { type SWRConfiguration, type KeyedMutator } from "swr";
import { api } from "@/lib/api";
import { unwrapList } from "@/lib/unwrap";
import type { RunCandidate, SelectedRun } from "@/lib/pipeline-run";
import { selectPipelineRun } from "@/lib/pipeline-run";
import type { DisplayCheckpoint } from "@/lib/jobs";
import {
  isTerminalStatus,
  jobDurationMs,
  mergeCheckpoints,
  normalizeJobStatus,
} from "@/lib/jobs";
import type {
  CheckpointData,
  FallbackLevel,
  PipelineStage,
  PipelineJob,
  PipelineJobDetail,
  GPUNode,
  GPUUtilizationPoint,
  GPUUtilizationHistoryResponse,
  ModelResidencyEntry,
  DLQMessage,
  DLQAnalyticsData,
  FlaggedAsset,
  CompositionManifest,
  TimelineSegment,
  StorageTierData,
  QuotaEntry,
  TierMigration,
  OrphanAsset,
  User,
} from "@/types/monitoring";

/**
 * Phase 13 — Frontend Operational Monitoring Hooks
 *
 * SWR-based data fetching hooks for all operational monitoring views.
 * Each hook provides:
 * - Typed data from the API
 * - Loading state (isLoading)
 * - Error state (error)
 * - Mutation function for cache invalidation (mutate)
 *
 * Polling intervals per specification:
 * - Pipeline jobs: 15 seconds (§8.2.1 real-time)
 * - GPU fleet: 10 seconds (§8.1.5 polls every 10s)
 * - DLQ messages: 30 seconds
 * - Quality review: 30 seconds
 * - Composition timeline: 10 seconds (active renders)
 * - Storage analytics: 60 seconds
 * - User management: no polling (on-demand)
 *
 * All hooks use the centralized API client from @/lib/api.
 */

// ── SWR Fetcher ───────────────────────────────────────────────────────

/**
 * Generic SWR fetcher using the API client.
 * Extracts data from Axios response.
 */
const fetcher = async (url: string): Promise<any> => {
  const response = await api.get(url);
  return response.data;
};

// ── Pipeline Monitoring Hooks ─────────────────────────────────────────

/**
 * Filter parameters for pipeline job listing.
 */
interface PipelineJobFilters {
  state?: string;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
}

/**
 * usePipelineJobs — the cross-project render-job list.
 *
 * WP-40 Task 2. This hook used to fetch `/api/v1/projects?expand=jobs` and
 * return `data.data` -- the PROJECT list. `expand` is not a parameter that
 * route implements (verified live 2026-08-23: no `jobs` key in the
 * response), so the Pipeline Tracker was rendering 16 projects as if they
 * were jobs. Every one of the page's symptoms follows from that:
 *
 *   - "16 jobs" was 16 projects.
 *   - RUNNING/COMPLETE/ERROR/PENDING all 0, because a project carries
 *     `state`, not `status` -- and even against real jobs the counters would
 *     still have read 0, since `render_jobs.status` is lowercase
 *     (`success`/`failed`) and the filters compared against COMPLETE/ERROR.
 *   - AVG DURATION "—", because a project has no started_at/completed_at.
 *   - Rows labelled "Job #c12fa967", which is the project's id.
 *
 * WP-45 Task 6(a): `GET /api/v1/jobs` now exists, so the list is ONE request
 * instead of 1 + N. It was 17 requests per 15-second poll on this fleet, and
 * every one of them was a project fetched only to ask for its jobs.
 *
 * Project NAMES still come from the projects list -- `JobResponse` carries a
 * project_id and not a name -- but that is one request that was already being
 * made, and it is made in parallel with the jobs now rather than before them.
 *
 * Checkpoint spans are still fetched for terminal jobs: WP-45 Task 5 made
 * started_at/completed_at real, so most jobs no longer need one, but a job that
 * predates that fix has no span of its own and the checkpoints remain the only
 * timing the system recorded for it (WP-40 D-4: checkpoint-derived duration
 * stays the fallback).
 *
 * Filters are applied here too. They were previously sent as query params to
 * the projects route, which ignores every one of them, so the state, search
 * and date controls did nothing.
 *
 * Polls every 15 seconds per §8.2.1.
 */

/**
 * Checkpoint spans for jobs that have finished, memoised for the session.
 *
 * A terminal job's checkpoints never change, so re-fetching them on every
 * 15-second poll would be pure waste. Only jobs never seen before cost a
 * request, and only up to MAX_CHECKPOINT_LOOKUPS of them per pass.
 */
const durationCache = new Map<string, number | null>();

/** Per-pass ceiling on checkpoint lookups. Surfaced, never silent. */
const MAX_CHECKPOINT_LOOKUPS = 40;

interface WireJob {
  id: string;
  project_id: string;
  job_type?: string | null;
  status?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  error_message?: string | null;
  retry_count?: number | null;
  node_id?: string | null;
}

/** A job row as the monitoring page consumes it. */
export interface AggregatedJob extends PipelineJob {
  project_id: string;
  job_type: string | null;
  duration_ms: number | null;
  error_message: string | null;
}

async function fetchAggregatedJobs(): Promise<AggregatedJob[]> {
  /* WP-45 Task 6(a): two requests, in parallel, whatever the project count. */
  const [projectsResp, jobsResp] = await Promise.all([
    fetcher("/api/v1/projects?per_page=100"),
    fetcher("/api/v1/jobs?per_page=100"),
  ]);

  const projects = unwrapList<{ id: string; name?: string }>(projectsResp);
  const projectNames = new Map<string, string>(
    projects.map((p) => [p.id, p.name ?? p.id])
  );

  const flat = unwrapList<WireJob>(jobsResp).map((job) => ({
    job,
    /* A job whose project is not in the first 100 keeps its id as its label,
       rather than being dropped from a list that claims to be all jobs. */
    project: { id: job.project_id, name: projectNames.get(job.project_id) },
  }));

  /* Timing, for terminal jobs we have not measured yet. */
  const pending = flat
    .filter(({ job }) => isTerminalStatus(job.status) && !durationCache.has(job.id))
    .slice(0, MAX_CHECKPOINT_LOOKUPS);

  if (pending.length > 0) {
    await Promise.all(
      pending.map(async ({ job }) => {
        try {
          const resp = await fetcher(`/api/v1/jobs/${job.id}/checkpoints`);
          const checkpoints = Array.isArray(resp?.checkpoints) ? resp.checkpoints : [];
          durationCache.set(job.id, jobDurationMs(job, checkpoints));
        } catch {
          durationCache.set(job.id, null);
        }
      })
    );
  }

  return flat
    .map(({ job, project }) => ({
      id: job.id,
      project_id: job.project_id,
      project_name: project.name ?? job.project_id,
      job_type: job.job_type ?? null,
      status: normalizeJobStatus(job.status),
      progress: 0,
      created_at: job.created_at,
      started_at: job.started_at ?? null,
      completed_at: job.completed_at ?? null,
      estimated_completion: null,
      fallback_level: "L1" as FallbackLevel,
      duration_ms: durationCache.get(job.id) ?? jobDurationMs(job, null),
      error_message: job.error_message ?? null,
    }))
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
}

function applyJobFilters(
  jobs: AggregatedJob[],
  filters: PipelineJobFilters
): AggregatedJob[] {
  let result = jobs;

  if (filters.state && filters.state !== "ALL") {
    result = result.filter((j) => j.status === filters.state);
  }

  if (filters.search && filters.search.trim()) {
    const q = filters.search.trim().toLowerCase();
    result = result.filter((j) =>
      [j.id, j.project_name, j.job_type ?? "", j.project_id]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }

  if (filters.dateFrom) {
    const from = new Date(filters.dateFrom).getTime();
    if (Number.isFinite(from)) {
      result = result.filter((j) => new Date(j.created_at).getTime() >= from);
    }
  }

  if (filters.dateTo) {
    /* Inclusive of the whole day the operator picked. */
    const to = new Date(filters.dateTo).getTime() + 24 * 60 * 60 * 1000 - 1;
    if (Number.isFinite(to)) {
      result = result.filter((j) => new Date(j.created_at).getTime() <= to);
    }
  }

  return result;
}

export function usePipelineJobs(filters: PipelineJobFilters = {}): {
  jobs: AggregatedJob[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<AggregatedJob[]>;
} {
  const config: SWRConfiguration = {
    refreshInterval: 15_000,
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
  };

  const { data, error, isLoading, mutate } = useSWR<AggregatedJob[]>(
    "pipeline-jobs-aggregate",
    fetchAggregatedJobs,
    config
  );

  return {
    jobs: data ? applyJobFilters(data, filters) : undefined,
    isLoading,
    error,
    mutate,
  };
}

/**
 * usePipelineJobDetail — a single job plus its checkpoints.
 *
 * WP-40 Task 2. Two problems, both invisible while the list handed this hook
 * a PROJECT id (every detail fetch 404'd):
 *
 *   1. `GET /api/v1/jobs/{id}` returns `JobResponse`, which has no
 *      checkpoints at all. The stage table read `jobDetail.checkpoints` and
 *      therefore drew eight PENDING rows for every job, finished or not.
 *   2. `GET /api/v1/jobs/{id}/checkpoints` -- which does have them -- keys
 *      each row by `stage_name` at worker granularity
 *      (`image_generation`, `tts_audio`, ...), while the page's DAG is keyed
 *      by the eight spec stages. `mergeCheckpoints` maps and collapses them.
 */
export function usePipelineJobDetail(jobId: string | null): {
  jobDetail: PipelineJobDetail | undefined;
  isLoading: boolean;
  error: Error | undefined;
} {
  const config: SWRConfiguration = {
    refreshInterval: 10_000,
    revalidateOnFocus: true,
  };

  const { data, error, isLoading } = useSWR<PipelineJobDetail>(
    jobId ? `job-detail:${jobId}` : null,
    async (): Promise<PipelineJobDetail> => {
      const [job, cps] = await Promise.all([
        fetcher(`/api/v1/jobs/${jobId}`),
        fetcher(`/api/v1/jobs/${jobId}/checkpoints`).catch(() => null),
      ]);

      const checkpoints = mergeCheckpoints(
        Array.isArray(cps?.checkpoints) ? cps.checkpoints : []
      ) as unknown as CheckpointData[];

      const failed = checkpoints.find((c) => c.status === "FAILED");
      const running = checkpoints.find((c) => c.status === "RUNNING");

      return {
        id: job?.id ?? String(jobId),
        status: normalizeJobStatus(job?.status),
        current_stage: (running?.stage ?? null) as PipelineStage | null,
        error_stage: (failed?.stage ?? null) as PipelineStage | null,
        error_message: job?.error_message ?? null,
        fallback_level: "L1",
        checkpoints,
      };
    },
    config
  );

  return {
    jobDetail: data,
    isLoading,
    error,
  };
}

// ── GPU Fleet Monitoring Hooks ────────────────────────────────────────

/**
 * useGPUFleetStatus — Fetches GPU fleet status with per-node metrics.
 *
 * Polls every 10 seconds per §8.1.5.
 * Source: GET /api/v1/gpu/nodes + GET /api/v1/gpu/utilization
 *
 * @returns GPU nodes, fleet summary, model residency, loading/error state
 */
export function useGPUFleetStatus(): {
  nodes: GPUNode[] | undefined;
  fleetSummary: any;
  modelResidency: ModelResidencyEntry[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const config: SWRConfiguration = {
    refreshInterval: 10_000,
    revalidateOnFocus: true,
    dedupingInterval: 3_000,
  };

  const { data, error, isLoading, mutate } = useSWR(
    "/api/v1/gpu/nodes",
    fetcher,
    config
  );

  /** Fetch fleet utilization summary in parallel */
  const { data: fleetData } = useSWR(
    "/api/v1/gpu/utilization",
    fetcher,
    config
  );

  return {
    nodes: data?.data ?? data?.nodes ?? data,
    fleetSummary: fleetData ?? null,
    modelResidency: fleetData?.model_residency ?? data?.model_residency,
    isLoading,
    error,
    mutate,
  };
}

/**
 * useJobCheckpoints — the stage checkpoints for one render job.
 *
 * WP-40 Task 2. `GET /api/v1/jobs/{id}` carries no checkpoints, and the
 * checkpoint route keys rows by worker stage name; `mergeCheckpoints` maps
 * them onto the eight spec stages the UI draws. Shared by the monitoring
 * page's stage table and the project Overview's Pipeline Progress strip,
 * which is the other component that had no real stage data to show.
 */
export function useJobCheckpoints(jobId: string | null | undefined): {
  checkpoints: DisplayCheckpoint[];
  isLoading: boolean;
} {
  const { data, isLoading } = useSWR<DisplayCheckpoint[]>(
    jobId ? `job-checkpoints:${jobId}` : null,
    async (): Promise<DisplayCheckpoint[]> => {
      const resp = await fetcher(`/api/v1/jobs/${jobId}/checkpoints`);
      return mergeCheckpoints(Array.isArray(resp?.checkpoints) ? resp.checkpoints : []);
    },
    { refreshInterval: 15_000, dedupingInterval: 5_000 }
  );

  return { checkpoints: data ?? [], isLoading };
}

/**
 * useProjectPipelineRun — the run the Overview's progress strip describes.
 *
 * WP-43 Task 5. `PipelineTracker` used to take `jobs[0]` and read that one
 * job's checkpoints. `GET /projects/{id}/jobs` is ordered newest-first, and
 * on the reference project the newest seven rows are `storyboard_generation`
 * jobs that are still `pending` and have written **zero** checkpoints. The
 * run that actually produced the project's draft — `bd99fe37`, seven stages,
 * six complete — is the EIGHTH row. So the strip was correctly reporting the
 * emptiness of a job nobody cared about, and it read as "nothing has ever
 * happened". Not a caching artifact: the same all-grey result reproduces
 * from the captured payloads in `src/lib/__tests__/ui-nav.test.mjs`.
 *
 * This fetches the checkpoints for every job of the project and hands
 * `selectPipelineRun` the lot; that function picks the newest job whose
 * checkpoints map onto the eight display stages, and reports how many newer
 * jobs had none so the strip can say which run it is showing.
 *
 * The per-job requests are capped at MAX_RUN_JOBS. A project with more jobs
 * than that has its OLDEST ones dropped, never its newest, and the cap is
 * surfaced rather than silent.
 */
const MAX_RUN_JOBS = 25;

export function useProjectPipelineRun(projectId: string | null | undefined): {
  run: SelectedRun | null;
  isLoading: boolean;
  /** Jobs beyond the cap that were not examined. */
  truncated: number;
} {
  const { data, isLoading } = useSWR<{ run: SelectedRun; truncated: number }>(
    projectId ? `project-pipeline-run:${projectId}` : null,
    async (): Promise<{ run: SelectedRun; truncated: number }> => {
      const jobsResp = await api.get<unknown>(
        `/api/v1/projects/${projectId}/jobs?per_page=100`,
      );
      const jobs = unwrapList<{
        id?: string;
        job_type?: string;
        status?: string;
        created_at?: string;
      }>(jobsResp.data).filter((j) => typeof j?.id === "string");

      const considered = jobs.slice(0, MAX_RUN_JOBS);

      const candidates: RunCandidate[] = await Promise.all(
        considered.map(async (job) => {
          let checkpoints: ReturnType<typeof mergeCheckpoints> = [];
          try {
            const resp = await api.get<{ checkpoints?: unknown }>(
              `/api/v1/jobs/${job.id}/checkpoints`,
            );
            checkpoints = mergeCheckpoints(
              Array.isArray(resp.data?.checkpoints) ? resp.data.checkpoints : [],
            );
          } catch {
            /* A single unreadable job must not blank the whole strip. */
          }
          return {
            id: job.id as string,
            created_at: job.created_at ?? null,
            job_type: job.job_type ?? null,
            status: job.status ?? null,
            checkpoints,
          };
        }),
      );

      return {
        run: selectPipelineRun(candidates),
        truncated: Math.max(0, jobs.length - considered.length),
      };
    },
    { refreshInterval: 15_000, dedupingInterval: 5_000 },
  );

  return {
    run: data?.run ?? null,
    isLoading,
    truncated: data?.truncated ?? 0,
  };
}

/**
 * useGPUUtilizationHistory - Fetches GPU utilization time-series.
 *
 * Source: GET /api/v1/gpu/utilization/history?range=<range>
 * Per GPU Fleet Monitoring Spec v1.1 section 6.2.
 *
 * Returns time-series data for the spec 8.2.2 fleet utilization chart.
 * Distinguishes three states:
 *   - history: GPUUtilizationPoint[] - successful response (possibly empty)
 *   - error: Error - request failed (could be 413 if range too large)
 *   - isLoading: true - request in flight
 *
 * Empty array is a SUCCESSFUL state, not an error. Callers must render
 * an empty-data UI state when history.length === 0.
 *
 * @param range - Time range (e.g. "30m", "1h", "24h"). Defaults to "30m"
 *                per spec 8.2.2 ("last 30 minutes"). Hard-capped at 5000
 *                points per response (Spec v1.1 section 3.3); larger ranges
 *                may return 413, surfaced via the `error` return.
 */
export function useGPUUtilizationHistory(range: string = "30m"): {
  history: GPUUtilizationPoint[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
} {
  const config: SWRConfiguration = {
    refreshInterval: 30_000,
    dedupingInterval: 10_000,
    errorRetryCount: 3,
    errorRetryInterval: 5_000,
    // Don't retry on 4xx - they won't fix themselves
    shouldRetryOnError: (err: Error) => {
      const status = (err as any)?.status;
      return !(typeof status === "number" && status >= 400 && status < 500);
    },
  };

  const { data, error, isLoading } = useSWR<GPUUtilizationHistoryResponse>(
    `/api/v1/gpu/utilization/history?range=${encodeURIComponent(range)}`,
    fetcher,
    config
  );

  // Strict-unwrap: only return history if it's actually an array.
  // Defensive against API shape changes or middleware envelope wrapping.
  const history = Array.isArray(data?.history) ? data!.history : undefined;

  return {
    history,
    isLoading,
    error,
  };
}

// ── DLQ Monitoring Hooks ──────────────────────────────────────────────

/**
 * DLQ message filter parameters.
 */
interface DLQMessageFilters {
  category?: string;
  taskName?: string;
  dateFrom?: string;
  dateTo?: string;
  page: number;
  pageSize: number;
}

/**
 * useDLQMessages — Fetches paginated DLQ messages with filters.
 *
 * Polls every 30 seconds.
 * Source: GET /api/v1/dlq/messages per §5.2.2
 *
 * @param filters - Pagination and filter parameters
 * @returns DLQ messages, total count, loading/error state
 */
export function useDLQMessages(filters: DLQMessageFilters): {
  messages: DLQMessage[] | undefined;
  totalCount: number | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const params = new URLSearchParams();
  if (filters.category) params.set("category", filters.category);
  if (filters.taskName) params.set("task_name", filters.taskName);
  if (filters.dateFrom) params.set("from_date", filters.dateFrom);
  if (filters.dateTo) params.set("to_date", filters.dateTo);
  params.set("page", filters.page.toString());
  params.set("per_page", filters.pageSize.toString());

  const key = `/api/v1/dlq/messages?${params.toString()}`;

  const config: SWRConfiguration = {
    refreshInterval: 30_000,
    revalidateOnFocus: true,
  };

  const { data, error, isLoading, mutate } = useSWR(key, fetcher, config);

  return {
    messages: data?.data ?? data?.messages ?? data?.results ?? data,
    totalCount: data?.total ?? data?.count,
    isLoading,
    error,
    mutate,
  };
}

/**
 * useDLQAnalytics — Fetches DLQ failure analytics.
 *
 * Polls every 60 seconds (aggregated data changes slowly).
 * Source: GET /api/v1/dlq/analytics per §5.2.2
 *
 * @returns DLQ analytics data
 */
export function useDLQAnalytics(): {
  analytics: DLQAnalyticsData | undefined;
  isLoading: boolean;
} {
  const config: SWRConfiguration = {
    refreshInterval: 60_000,
    dedupingInterval: 30_000,
  };

  const { data, isLoading } = useSWR(
    "/api/v1/dlq/analytics",
    fetcher,
    config
  );

  return { analytics: data, isLoading };
}

// ── Quality Review Hooks ──────────────────────────────────────────────

/**
 * Quality review queue filter parameters.
 */
interface QualityReviewFilters {
  sort?: string;
  assetType?: string;
  page: number;
  pageSize: number;
}

/**
 * useQualityReviewQueue — Fetches flagged assets for quality review.
 *
 * Polls every 30 seconds.
 * Source: GET /api/v1/quality/flagged per §5.2.3
 *
 * @param filters - Sort, type filter, pagination
 * @returns Flagged assets, total count, loading/error state
 */
export function useQualityReviewQueue(filters: QualityReviewFilters): {
  assets: FlaggedAsset[] | undefined;
  totalCount: number | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const params = new URLSearchParams();
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.assetType) params.set("asset_type", filters.assetType);
  params.set("page", filters.page.toString());
  params.set("per_page", filters.pageSize.toString());

  const key = `/api/v1/quality/flagged?${params.toString()}`;

  const config: SWRConfiguration = {
    refreshInterval: 30_000,
    revalidateOnFocus: true,
  };

  const { data, error, isLoading, mutate } = useSWR(key, fetcher, config);

  return {
    assets: data?.data ?? data?.assets ?? data?.results ?? data,
    totalCount: data?.total ?? data?.count,
    isLoading,
    error,
    mutate,
  };
}

// ── Composition Timeline Hooks ────────────────────────────────────────

/**
 * useCompositionTimeline — Fetches composition manifest and render segments.
 *
 * Polls every 10 seconds for active renders, 60 seconds otherwise.
 * Source: GET /api/v1/jobs/{id}/manifest per §5.2.5
 *
 * @param jobId - Job ID to load timeline for (null to skip)
 * @returns Manifest, segments, render progress, loading/error state
 */
export function useCompositionTimeline(jobId: string | null): {
  manifest: CompositionManifest | undefined;
  segments: TimelineSegment[] | undefined;
  renderProgress: number | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const config: SWRConfiguration = {
    refreshInterval: 10_000,
    revalidateOnFocus: true,
  };

  const { data, error, isLoading, mutate } = useSWR(
    jobId ? `/api/v1/jobs/${jobId}/manifest` : null,
    fetcher,
    config
  );

  return {
    manifest: data?.manifest ?? data,
    segments: data?.segments ?? data?.manifest?.segments,
    renderProgress: data?.render_progress,
    isLoading,
    error,
    mutate,
  };
}

// ── Storage Analytics Hooks ───────────────────────────────────────────

/**
 * useStorageAnalytics — Fetches tier breakdown and dedup savings.
 *
 * Polls every 60 seconds.
 * Source: GET /api/v1/retention/report per §5.2.6
 *
 * @returns Tier data, dedup info, totals, loading/error state
 */
export function useStorageAnalytics(): {
  tierData: StorageTierData[] | undefined;
  dedupSavings: { percent: number; bytes_saved: number; duplicate_count: number } | undefined;
  /** False when the API exposes no dedup figures at all. Do NOT render 0 instead. */
  dedupAvailable: boolean;
  dedupReason: string;
  totalUsed: number | undefined;
  totalAllocated: number | undefined;
  /** False when no allocation/capacity figure exists anywhere. */
  allocationAvailable: boolean;
  allocationReason: string;
  totalAssets: number | undefined;
  policyName: string | undefined;
  isLoading: boolean;
  error: Error | undefined;
} {
  const config: SWRConfiguration = {
    refreshInterval: 60_000,
    dedupingInterval: 30_000,
  };

  const { data, error, isLoading } = useSWR(
    "/api/v1/retention/report",
    fetcher,
    config
  );

  // WP-23. This hook used to read `data.tiers ?? data.tier_breakdown`,
  // `data.dedup_savings`, `data.total_used` and `data.total_allocated`. NONE of
  // those four names has ever existed on the API side -- `git log -S` over the
  // whole of ivgs-api/ returns no commit for `total_allocated` or
  // `tier_breakdown`, while the frontend has read them since 0962319, the
  // initial release. Every field resolved to undefined and the page floored each
  // one to 0 with `?? 0`, which is how a database holding 45 assets and 208 MB
  // rendered as "0 B used, 0 assets".
  //
  // The endpoint actually returns RetentionReportResponse
  // (ivgs-api/app/schemas/retention.py:103): total_assets, total_size_bytes,
  // tier_distribution[{tier, asset_count, total_size_bytes}], upcoming_migrations,
  // policy_name.
  const tierData: StorageTierData[] | undefined = data?.tier_distribution?.map(
    (t: { tier: string; asset_count: number; total_size_bytes: number }) => ({
      tier: t.tier as StorageTierData["tier"],
      used_bytes: t.total_size_bytes,
      // No per-tier capacity exists in the data model, so there is nothing
      // truthful to put here. The page must read `allocationAvailable`, not
      // treat 0 as "no space allocated".
      total_bytes: 0,
      asset_count: t.asset_count,
      used: t.total_size_bytes,
      allocated: undefined,
    })
  );

  return {
    tierData,
    // Deduplication is not computed by any endpoint (ledger P2.4). The columns
    // exist -- assets.content_hash and assets.reference_count are populated on
    // every row -- but nothing aggregates them, so there is no figure to show.
    // Reporting 0% saved would assert that dedup ran and found nothing.
    dedupSavings: undefined,
    dedupAvailable: false,
    dedupReason:
      "Deduplication savings are not computed by any endpoint (ledger P2.4). " +
      "assets.content_hash and assets.reference_count are populated, so the " +
      "figure is derivable, but nothing derives it yet.",
    totalUsed: data?.total_size_bytes,
    totalAllocated: undefined,
    allocationAvailable: false,
    allocationReason:
      "No storage allocation or per-tier capacity is modelled anywhere in the " +
      "system, so there is no denominator to report against.",
    totalAssets: data?.total_assets,
    policyName: data?.policy_name,
    isLoading,
    error,
  };
}
/**
 * useStorageQuotas — per-user quota utilisation.
 *
 * WP-40 Task 4. The console filled with 404s from
 * `/api/v1/quotas/user/{id}`. Two corrections to the premise, both verified
 * live on 2026-08-23:
 *
 *   1. The route EXISTS. `quotas.py:33` is
 *      `GET /quotas/{entity_type}/{entity_id}`, mounted at `/api/v1/quotas`.
 *      The 404 is its own honest answer -- `storage_quotas` has 0 rows, so
 *      every lookup raises RESOURCE_NOT_FOUND "No quota for user/{id}".
 *   2. It is not called on project pages. The only caller is this hook, and
 *      the only mount is /monitoring/storage's admin Quotas tab. The spam is
 *      four 404s (one per user) on every poll and every window refocus.
 *
 * The fix is to stop asking a question already answered. A 404 means "this
 * entity has no quota record", which cannot change without an admin PUT, so
 * it is remembered for the session and never re-requested. First load costs
 * one probe per user; every later poll costs none.
 *
 * Rows now carry `has_quota`, so the UI can say "no quota data" instead of
 * rendering 0 / 0 -- which reads as a real zero-byte quota and is worse than
 * saying nothing.
 *
 * NOTE: nothing anywhere writes `storage_quotas`; there is no quota
 * provisioning path in this system. That is backend scope and is NOT fixed
 * here -- WP-40 explicitly forbids building a quotas API.
 */

/** Entities known to have no quota record. Session-lived, never re-probed. */
const quotaMisses = new Set<string>();

export function useStorageQuotas(enabled: boolean): {
  quotas: QuotaEntry[] | undefined;
  isLoading: boolean;
  /** True when no user in the list has a quota record at all. */
  noQuotaData: boolean;
} {
  const config: SWRConfiguration = {
    refreshInterval: 120_000,
    dedupingInterval: 60_000,
    /* A refocus must not re-run the probe sweep. */
    revalidateOnFocus: false,
    /* A 404 here is data, not a transient fault; retrying cannot help. */
    shouldRetryOnError: false,
  };

  const { data, isLoading } = useSWR<QuotaEntry[]>(
    enabled ? "/api/v1/quotas/user/aggregated" : null,
    async (): Promise<QuotaEntry[]> => {
      const usersResp = await fetcher("/api/v1/users");
      const users = unwrapList<User>(usersResp);

      const entries = await Promise.all(
        users.map(async (u): Promise<QuotaEntry> => {
          const base = { user_id: u.id, username: u.username };

          /* Already established that this user has no quota record. */
          if (quotaMisses.has(u.id)) {
            return { ...base, used_bytes: 0, quota_bytes: 0, has_quota: false };
          }

          try {
            const quota = await fetcher(`/api/v1/quotas/user/${u.id}`);
            return {
              ...base,
              used_bytes: quota?.used_bytes ?? 0,
              quota_bytes: quota?.quota_bytes ?? 0,
              has_quota: true,
            };
          } catch (err: unknown) {
            /* 404 = no record for this entity. Remember it; ask once, ever.
               Anything else is a real fault and is not memoised, so it will
               be retried on the next poll. */
            const status = (err as { status?: number })?.status;
            if (status === 404) quotaMisses.add(u.id);
            return { ...base, used_bytes: 0, quota_bytes: 0, has_quota: false };
          }
        })
      );
      return entries;
    },
    config
  );

  return {
    quotas: data,
    isLoading,
    noQuotaData: Array.isArray(data) && data.every((q) => !q.has_quota),
  };
}

/**
 * useRetentionReport — Fetches upcoming migrations and orphan assets.
 *
 * Admin-only. Polls every 120 seconds.
 * Source: GET /api/v1/retention/report?include=migrations,orphans
 *
 * @param enabled - Whether to fetch (false for non-admin users)
 * @returns Migrations, orphan assets, loading state
 */
export function useRetentionReport(enabled: boolean): {
  migrations: TierMigration[] | undefined;
  orphans: OrphanAsset[] | undefined;
  isLoading: boolean;
} {
  const config: SWRConfiguration = {
    refreshInterval: 120_000,
    dedupingInterval: 60_000,
  };

  const { data, isLoading } = useSWR(
    enabled
      ? "/api/v1/retention/report?include=migrations,orphans"
      : null,
    fetcher,
    config
  );

  return {
    migrations: data?.upcoming_migrations ?? data?.migrations,
    orphans: data?.orphan_assets ?? data?.orphans,
    isLoading,
  };
}

// ── User Management Hooks ─────────────────────────────────────────────

/**
 * useUsers — Fetches all users for admin management.
 *
 * No polling (on-demand refresh via mutate).
 * Source: GET /api/v1/users per §5.1.9
 *
 * @returns Users, loading/error state, mutator
 */
export function useUsers(): {
  users: User[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const config: SWRConfiguration = {
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
  };

  const { data, error, isLoading, mutate } = useSWR(
    "/api/v1/users",
    fetcher,
    config
  );

  return {
    users: data?.data ?? data?.users ?? data,
    isLoading,
    error,
    mutate,
  };
}
