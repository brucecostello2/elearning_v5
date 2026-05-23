import useSWR, { type SWRConfiguration, type KeyedMutator } from "swr";
import { api } from "@/lib/api";
import type {
  PipelineJob,
  PipelineJobDetail,
  GPUNode,
  GPUUtilizationPoint,
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
const fetcher = async (url: string) => {
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
 * useGPUUtilizationHistory — Fetches GPU utilization history (last 30 min).
 *
 * Source: GET /api/v1/gpu/utilization?history=30m
 * Returns time-series data for the fleet utilization chart.
 *
 * @returns Utilization history data points
 */
export function useGPUUtilizationHistory(): {
  history: GPUUtilizationPoint[] | undefined;
  isLoading: boolean;
} {
  const config: SWRConfiguration = {
    refreshInterval: 30_000,
    dedupingInterval: 10_000,
  };

  const { data, isLoading } = useSWR(
    "/api/v1/gpu/utilization?history=30m",
    fetcher,
    config
  );

  return {
    history: data?.history ?? data,
    isLoading,
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
  totalUsed: number | undefined;
  totalAllocated: number | undefined;
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

  return {
    tierData: data?.tiers ?? data?.tier_breakdown,
    dedupSavings: data?.dedup_savings,
    totalUsed: data?.total_used,
    totalAllocated: data?.total_allocated,
    isLoading,
    error,
  };
}

/**
 * useStorageQuotas — Fetches per-user quota utilization.
 *
 * Admin-only. Polls every 120 seconds.
 * Source: GET /api/v1/quotas/user/all (admin endpoint)
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

  const { data, isLoading } = useSWR(
    enabled ? "/api/v1/quotas/user/all" : null,
    fetcher,
    config
  );

  return {
    quotas: data?.quotas ?? data,
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
