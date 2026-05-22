import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type { RenderJob } from "@/types/api";

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

const jobsFetcher = async (url: string): Promise<RenderJob[]> => {
  const response = await apiClient.get<RenderJob[]>(url);
  return response.data;
};

export function useJobs(projectId: string): UseJobsReturn {
  const url = `/api/v1/projects/${projectId}/jobs`;

  const { data, error, isLoading, mutate } = useSWR<RenderJob[]>(
    url,
    jobsFetcher,
    {
      refreshInterval: (latestData) => {
        // Poll frequently when jobs are active
        const hasActive = latestData?.some(
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
   */
  const resumeJob = async (jobId: string): Promise<void> => {
    await apiClient.post(
      `/api/v1/projects/${projectId}/jobs/${jobId}/resume`
    );
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
