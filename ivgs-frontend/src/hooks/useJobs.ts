import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type { RenderJob } from "@/types/api";
import { unwrapList } from "@/lib/unwrap";

/**
 * §8.1.3 Table 8-2 — Jobs Tab Data Hook
 *
 * Fetches pipeline job history for a project.
 * Polls every 5 seconds when there are active (non-terminal) jobs.
 * Provides resume mutation for checkpoint restart.
 */

interface UseJobsReturn {
  jobs: RenderJob[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<RenderJob[]>;
  resumeJob: (jobId: string) => Promise<void>;
}

/**
 * WP-35. GET /api/v1/projects/{id}/jobs has
 * `response_model=PaginatedResponse[JobResponse]` (ivgs-api/app/api/v1/jobs.py:31),
 * so `response.data` is the ENVELOPE `{data, total, page, ...}`, not the array.
 * This returned that envelope while `useSWR<RenderJob[]>` below asserted an
 * array -- a lie TypeScript accepted only because the fetcher was typed
 * `Promise<any>`. It crashed the project detail page with
 * `latestData?.some is not a function`.
 */
const jobsFetcher = async (url: string): Promise<RenderJob[]> => {
  const response = await apiClient.get<unknown>(url);
  return unwrapList<RenderJob>(response.data);
};

export function useJobs(projectId: string): UseJobsReturn {
  const url = `/api/v1/projects/${projectId}/jobs`;

  const { data, error, isLoading, mutate } = useSWR<RenderJob[]>(
    url,
    jobsFetcher,
    {
      refreshInterval: (latestData) => {
        // Poll frequently when jobs are active.
        // WP-35: Array.isArray, not `?.`. Optional chaining guards null/undefined
        // and does nothing about a value that is present but is an object -- which
        // is exactly what this used to receive.
        const hasActive = (Array.isArray(latestData) ? latestData : []).some(
          (job) =>
            job.status === "RUNNING" ||
            job.status === "IN_PROGRESS" ||
            job.status === "PENDING" ||
            job.status === "QUEUED"
        );
        return hasActive ? 5000 : 30000;
      },
      revalidateOnFocus: true,
      dedupingInterval: 3000,
    }
  );

  /**
   * Resume a failed job from its last checkpoint.
   *
   * WP-70 fix S8: the route is `POST /jobs/{job_id}/resume` (checkpoints.py),
   * not nested under the project; the old path answered 404. Latent — no
   * component calls it yet.
   */
  const resumeJob = async (jobId: string): Promise<void> => {
    await apiClient.post(`/api/v1/jobs/${jobId}/resume`);
    mutate();
  };

  return {
    jobs: data,
    isLoading,
    error,
    mutate,
    resumeJob,
  };
}
