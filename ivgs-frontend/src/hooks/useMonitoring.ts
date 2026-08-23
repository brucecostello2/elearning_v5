import useSWR, { type SWRConfiguration, type KeyedMutator } from "swr";
import { api } from "@/lib/api";
import type {
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
 * usePipelineJobs — Fetches pipeline jobs with filtering.
 *
 * Polls every 15 seconds per §8.2.1.
 * Source: multiple endpoints aggregated server-side or via
 * GET /api/v1/projects with ?expand=jobs parameter.
 *
 * @param filters - Optional filter parameters
 * @returns Pipeline job data, loading state, error, and mutator
 */
export function usePipelineJobs(filters: PipelineJobFilters = {}): {
  jobs: PipelineJob[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<{ jobs: PipelineJob[] }>;
} {
  const params = new URLSearchParams();
  if (filters.state) params.set("state", filters.state);
  if (filters.search) params.set("search", filters.search);
  if (filters.dateFrom) params.set("from_date", filters.dateFrom);
  if (filters.dateTo) params.set("to_date", filters.dateTo);
  params.set("expand", "jobs");

  const queryString = params.toString();
  const key = `/api/v1/projects?${queryString}`;

  const config: SWRConfiguration = {
    refreshInterval: 15_000,
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
  };

  const { data, error, isLoading, mutate } = useSWR(key, fetcher, config);

  return {
    jobs: data?.data ?? data?.jobs ?? data?.results?.flatMap((p: any) => p.jobs) ?? (Array.isArray(data) ? data : []),
    isLoading,
    error,
    mutate,
  };
}

/**
 * usePipelineJobDetail — Fetches detailed info for a single pipeline job.
 *
 * Includes checkpoint data, retry history, and error details.
 * Source: GET /api/v1/jobs/{id} + GET /api/v1/jobs/{id}/checkpoints
 *
 * @param jobId - Job ID to fetch detail for (null to skip)
 * @returns Job detail data, loading state, error
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

  const { data, error, isLoading } = useSWR(
    jobId ? `/api/v1/jobs/${jobId}` : null,
    fetcher,
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
 * useStorageQuotas — Fetches per-user quota utilization.
 *
 * Admin-only. Polls every 120 seconds.
 *
 * Implementation note: the API does not expose a bulk
 * /api/v1/quotas/user/all endpoint. This hook fetches the user list
 * from /api/v1/users and then issues a parallel quota lookup per user
 * against /api/v1/quotas/user/{user_id}. Users with no quota record
 * (404 from the quota endpoint) are reported with used_bytes=0 and
 * quota_bytes=0 so the row still appears in the admin table.
 *
 * Trade-off: per-user fetch errors are swallowed and reported as
 * empty quota rows. If individual quota endpoints start returning
 * 500s, those failures will be silent. Phase F backlog item:
 * surface fetch errors per row in the admin UI.
 *
 * @param enabled - Whether to fetch (false for non-admin users)
 * @returns Quota entries, loading state
 */
export function useStorageQuotas(enabled: boolean): {
  quotas: QuotaEntry[] | undefined;
  isLoading: boolean;
} {
  const config: SWRConfiguration = {
    refreshInterval: 120_000,
    dedupingInterval: 60_000,
  };
  const { data, isLoading } = useSWR<QuotaEntry[]>(
    enabled ? "/api/v1/quotas/user/aggregated" : null,
    async (): Promise<QuotaEntry[]> => {
      const usersResp = await fetcher("/api/v1/users");
      const users: User[] = usersResp?.data ?? [];
      const entries = await Promise.all(
        users.map(async (u): Promise<QuotaEntry> => {
          try {
            const quota = await fetcher(`/api/v1/quotas/user/${u.id}`);
            return {
              user_id: u.id,
              username: u.username,
              used_bytes: quota?.used_bytes ?? 0,
              quota_bytes: quota?.quota_bytes ?? 0,
            };
          } catch {
            return {
              user_id: u.id,
              username: u.username,
              used_bytes: 0,
              quota_bytes: 0,
            };
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
