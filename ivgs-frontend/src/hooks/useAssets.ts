import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type { Asset } from "@/types/api";
import { unwrapList } from "@/lib/unwrap";

/**
 * Assets data fetching, upload, and regeneration hook.
 * Fetches all assets for a given project.
 */

interface UseAssetsReturn {
  assets: Asset[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<Asset[]>;
  uploadAsset: (formData: FormData) => Promise<any>;
  regenerateAsset: (assetId: string) => Promise<void>;
}

/**
 * WP-35. Same defect as useJobs: GET /api/v1/projects/{id}/assets is
 * `response_model=PaginatedResponse[AssetResponse]` (assets.py:38), so
 * `response.data` is the envelope. Consumers of `assets` call `.map`/`.filter`
 * on it -- the assets, talking-head and audio tabs all would have thrown
 * `assets.map is not a function`. Fixed here rather than left as a known
 * duplicate of a crash being fixed one file away.
 */
const assetsFetcher = async (url: string): Promise<Asset[]> => {
  const response = await apiClient.get<unknown>(url);
  return unwrapList<Asset>(response.data);
};

export function useAssets(projectId: string): UseAssetsReturn {
  const url = `/api/v1/projects/${projectId}/assets`;

  const { data, error, isLoading, mutate } = useSWR<Asset[]>(
    url,
    assetsFetcher,
    {
      revalidateOnFocus: true,
      dedupingInterval: 5000,
    }
  );

  /**
   * Upload a new asset (manual upload).
   */
  const uploadAsset = async (formData: FormData): Promise<any> => {
    const response = await apiClient.post<{ data: Asset }>(
      `/api/v1/projects/${projectId}/assets`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    mutate();
    return response.data;
  };

  /**
   * Trigger regeneration of a specific asset via the pipeline.
   */
  /**
   * WP-40 Task 1: the path was wrong and always 404'd.
   *
   * The asset-scoped router is mounted at `/assets` (assets.py:33); only the
   * LIST and UPLOAD routes are project-scoped. The regenerate route is
   * `POST /api/v1/assets/{id}/regenerate` (assets.py:154), not
   * `/api/v1/projects/{pid}/assets/{id}/regenerate`. Every press of the
   * card's Regenerate button raised a 404 toast.
   */
  const regenerateAsset = async (assetId: string): Promise<void> => {
    await apiClient.post(`/api/v1/assets/${assetId}/regenerate`);
    mutate();
  };

  return {
    assets: data,
    isLoading,
    error,
    mutate,
    uploadAsset,
    regenerateAsset,
  };
}
