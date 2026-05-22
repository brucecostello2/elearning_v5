import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type { Asset } from "@/types/api";

/**
 * Assets data fetching, upload, and regeneration hook.
 * Fetches all assets for a given project.
 */

interface UseAssetsReturn {
  assets: Asset[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<Asset[]>;
  uploadAsset: (formData: FormData) => Promise<Asset>;
  regenerateAsset: (assetId: string) => Promise<void>;
}

const assetsFetcher = async (url: string): Promise<Asset[]> => {
  const response = await apiClient.get<Asset[]>(url);
  return response.data;
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
  const uploadAsset = async (formData: FormData): Promise<Asset> => {
    const response = await apiClient.upload<Asset>(
      `/api/v1/projects/${projectId}/assets`,
      formData
    );
    mutate();
    return response.data;
  };

  /**
   * Trigger regeneration of a specific asset via the pipeline.
   */
  const regenerateAsset = async (assetId: string): Promise<void> => {
    await apiClient.post(
      `/api/v1/projects/${projectId}/assets/${assetId}/regenerate`
    );
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
