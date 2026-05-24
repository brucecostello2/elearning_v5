import useSWR, { type SWRConfiguration, type KeyedMutator } from "swr";
import { api } from "@/lib/api";
import type { PipelineJob, PipelineJobDetail } from "@/types/monitoring";

/**
 * §8.2.1 Pipeline Monitoring Hooks
 *
 * Real-time pipeline monitoring hooks with SWR polling.
 * These hooks provide convenient wrappers around the pipeline
 * endpoints for use in monitoring views.
 *
 * Note: The primary pipeline hooks (usePipelineJobs, usePipelineJobDetail)
 * are in useMonitoring.ts. This file provides additional convenience hooks
 * for real-time pipeline status tracking with WebSocket integration hints.
 *
 * Polling intervals per specification:
 * - Pipeline jobs listing: 15 seconds (§8.2.1)
 * - Individual job detail: 10 seconds (active), 60 seconds (inactive)
 */

// ── SWR Fetcher ───────────────────────────────────────────────────────

const fetcher = async (url: string): Promise<any> => {
  const response = await api.get(url);
  return response.data;
};

// ── Pipeline Summary Hook ─────────────────────────────────────────────

interface PipelineSummary {
  total: number;
  running: number;
  pending: number;
  completed: number;
  failed: number;
}

/**
 * usePipelineSummary — Fetches pipeline job summary statistics.
 *
 * Derives aggregate counts from the jobs listing for dashboard display.
 * Polls every 15 seconds per §8.2.1.
 *
 * @returns Summary statistics, loading state
 */
export function usePipelineSummary(): {
  summary: PipelineSummary;
  jobs: PipelineJob[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const config: SWRConfiguration = {
    refreshInterval: 15_000,
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
  };

  const { data, error, isLoading, mutate } = useSWR(
    "/api/v1/projects?expand=jobs",
    fetcher,
    config
  );

  const jobs: PipelineJob[] | undefined =
    data?.data ?? data?.jobs ?? data?.results?.flatMap((p: any) => p.jobs) ?? (Array.isArray(data) ? data : []);

  const summary: PipelineSummary = {
    total: jobs?.length ?? 0,
    running: jobs?.filter((j) => j.status === "running").length ?? 0,
    pending: jobs?.filter((j) => j.status === "pending").length ?? 0,
    completed: jobs?.filter((j) => j.status === "complete" || j.status === "success").length ?? 0,
    failed: jobs?.filter((j) => j.status === "failed").length ?? 0,
  };

  return {
    summary,
    jobs,
    isLoading,
    error,
    mutate,
  };
}

// ── Pipeline Job Actions ──────────────────────────────────────────────

/**
 * resumePipelineJob — Resumes a failed pipeline job from its last checkpoint.
 *
 * Admin-only action per §8.3 Table 8-3.
 * Source: POST /api/v1/jobs/{id}/resume
 *
 * @param jobId - Job ID to resume
 * @returns Promise resolving to API response
 */
export async function resumePipelineJob(jobId: string): Promise<any> {
  const response = await api.post(`/api/v1/jobs/${jobId}/resume`);
  return response.data;
}
