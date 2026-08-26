import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";

/**
 * Project deletion — WP-59.
 *
 * The dialog does NOT compose its own category list. It renders exactly what
 * `GET /projects/{id}/deletion-preview` returns, and the API builds that from
 * the same `PROJECT_CATEGORIES` map the deletion itself walks. A category the
 * dialog cannot show is therefore a category the deletion cannot destroy, and
 * vice versa: they cannot drift apart, because there is only one list.
 *
 * That is deliberate and it is the whole point of the friction. A dialog that
 * enumerated its own categories in TypeScript would be a second statement of
 * what someone believed a project was -- which is exactly the shape of defect
 * WP-57 found four times over on the dashboards.
 */

export interface DeletionCategory {
  key: string;
  label: string;
  detail: string;
  /** 'cascade' | 'orphan' | 'storage' — what the live FK does. */
  cascade: string;
  count: number;
  breakdown: Record<string, number>;
}

export interface BlockingJob {
  id: string;
  job_type: string;
  status: string;
  celery_task_id: string;
  created_at: string | null;
  started_at: string | null;
  note?: string;
}

export interface GpuReservation {
  reservation_id: string;
  job_id: string;
  node_id: string;
  vram_mb: string;
  expires_at: string;
  found_via: string;
}

export interface DeletionPreview {
  project_id: string;
  project_name: string;
  project_state: string;
  categories: DeletionCategory[];
  blocking_jobs: BlockingJob[];
  gpu_reservations_held: GpuReservation[];
  total_rows: number;
  total_bytes: number;
  deletable: boolean;
  scheduler_registry_error: string | null;
  redis_registry_error: string | null;
}

export interface DeletionResult {
  project_id: string;
  project_name: string;
  audit_id: string;
  rows_deleted: Record<string, number>;
  total_rows_deleted: number;
  files_deleted: number;
  files_preserved: number;
  preserved_reasons: { fid: string; path: string; reason: string }[];
  /** Objects the purge could not confirm deleted. NOT counted in files_deleted. */
  files_failed: { fid: string; path: string }[];
  redis_keys_deleted: number;
  resumed: boolean;
}

interface UseProjectDeletionReturn {
  preview: DeletionPreview | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: KeyedMutator<DeletionPreview>;
  /** POST the existing WP-45 cancel route. Not a reimplementation of revoke. */
  cancelJob: (jobId: string) => Promise<void>;
  deleteProject: (confirmName: string) => Promise<DeletionResult>;
}

const previewFetcher = async (url: string): Promise<DeletionPreview> => {
  const response = await apiClient.get<DeletionPreview>(url);
  return response.data;
};

export function useProjectDeletion(
  projectId: string,
  enabled: boolean,
): UseProjectDeletionReturn {
  /* Fetched only while the dialog is open. This is an admin-only inventory of
     an entire project and it walks fifteen tables; polling it behind a closed
     dialog would be work nobody asked for. Refreshed on a short interval WHILE
     open so a job that finishes (or is cancelled) unblocks the flow without a
     manual reload. */
  const { data, error, isLoading, mutate } = useSWR<DeletionPreview>(
    enabled ? `/api/v1/projects/${projectId}/deletion-preview` : null,
    previewFetcher,
    { refreshInterval: enabled ? 5000 : 0, revalidateOnFocus: false },
  );

  /**
   * WP-45 Task 3 site 3 made `POST /jobs/{id}/cancel` actually revoke, with
   * `terminate=True, signal="SIGTERM"` so `IVGSBaseTask.on_failure` runs and
   * the GPU reservation is released rather than leaked. This calls that route.
   * It does not revoke anything itself and must not: a second revoke path is a
   * second thing that can be wrong about whether the GPU stopped.
   */
  const cancelJob = async (jobId: string): Promise<void> => {
    await apiClient.post(`/api/v1/jobs/${jobId}/cancel`);
    await mutate();
  };

  const deleteProject = async (confirmName: string): Promise<DeletionResult> => {
    const response = await apiClient.delete<DeletionResult>(
      `/api/v1/projects/${projectId}?confirm_name=${encodeURIComponent(confirmName)}`,
    );
    return response.data;
  };

  return {
    preview: data,
    isLoading,
    error,
    refresh: mutate,
    cancelJob,
    deleteProject,
  };
}
