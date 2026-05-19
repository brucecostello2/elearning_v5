import { useCallback, useMemo } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { api } from "@/lib/api";
import type {
  Scene,
  SceneUpdatePayload,
  SceneReorderPayload,
  StoryboardResponse,
} from "@/types/storyboard";

/**
 * §8.1.3 Storyboard Tab — Data Hook
 *
 * Custom hook providing complete storyboard data management:
 *
 * - Fetch scenes for a project (GET /api/v1/projects/{id}/scenes)
 * - Update scene properties (PATCH /api/v1/projects/{id}/scenes/{sid})
 * - Delete scene (DELETE /api/v1/projects/{id}/scenes/{sid})
 * - Batch delete scenes (POST /api/v1/projects/{id}/scenes/batch-delete)
 * - Reorder scenes (PUT /api/v1/projects/{id}/scenes/reorder)
 * - Regenerate scene (POST /api/v1/projects/{id}/scenes/{sid}/regenerate)
 * - Batch regenerate (POST /api/v1/projects/{id}/scenes/batch-regenerate)
 *
 * SWR configuration:
 * - Revalidation on focus: enabled
 * - Revalidation on reconnect: enabled
 * - Dedup interval: 5 seconds
 * - Retry on error: 3 times with exponential backoff
 *
 * Optimistic updates:
 * - Scene reorder applies locally before API confirmation
 * - Scene delete removes from local cache immediately
 * - Scene update patches local cache immediately
 * - On error, SWR revalidation restores correct state
 *
 * @param projectId - Project ID to fetch scenes for
 * @returns Hook return object with scenes data and mutation functions
 */

/** SWR fetcher using the API client */
async function fetchScenes(url: string): Promise<Scene[]> {
  const response = await api.get<StoryboardResponse>(url);
  return response.data.scenes;
}

/** SWR cache key generator */
function getScenesKey(projectId: string | undefined): string | null {
  if (!projectId) return null;
  return `/api/v1/projects/${projectId}/scenes`;
}

interface UseStoryboardReturn {
  /** Array of scenes sorted by scene_index */
  scenes: Scene[] | undefined;
  /** Whether data is currently loading */
  isLoading: boolean;
  /** Error object if fetch failed */
  error: Error | undefined;
  /** SWR mutate function for manual revalidation */
  mutate: () => void;
  /** Update a single scene's properties */
  updateScene: (sceneId: string, updates: Partial<Scene>) => Promise<void>;
  /** Delete a single scene */
  deleteScene: (sceneId: string) => Promise<void>;
  /** Delete multiple scenes */
  deleteScenes: (sceneIds: string[]) => Promise<void>;
  /** Reorder scenes after drag-drop */
  reorderScenes: (
    sourceIndex: number,
    destinationIndex: number
  ) => Promise<void>;
  /** Regenerate a single scene */
  regenerateScene: (sceneId: string) => Promise<void>;
  /** Regenerate multiple scenes */
  regenerateScenes: (sceneIds: string[]) => Promise<void>;
}

export function useStoryboard(
  projectId: string | undefined
): UseStoryboardReturn {
  // ── SWR Data Fetching ─────────────────────────────────────────────
  const cacheKey = getScenesKey(projectId);
  const {
    data: scenes,
    error,
    isLoading,
    mutate,
  } = useSWR<Scene[], Error>(cacheKey, fetchScenes, {
    revalidateOnFocus: true,
    revalidateOnReconnect: true,
    dedupingInterval: 5000,
    errorRetryCount: 3,
    errorRetryInterval: 1000,
  });

  /** Sorted scenes by scene_index */
  const sortedScenes = useMemo<Scene[] | undefined>(() => {
    if (!scenes) return undefined;
    return [...scenes].sort(
      (a: Scene, b: Scene) => a.scene_index - b.scene_index
    );
  }, [scenes]);

  /**
   * Update a single scene.
   * Optimistically patches local cache before API call.
   * PATCH /api/v1/projects/{projectId}/scenes/{sceneId}
   */
  const updateScene = useCallback(
    async (sceneId: string, updates: Partial<Scene>): Promise<void> => {
      if (!projectId || !cacheKey) {
        throw new Error("Project ID is required");
      }

      // Optimistic update
      const optimisticData = scenes?.map((s: Scene) =>
        s.id === sceneId
          ? { ...s, ...updates, updated_at: new Date().toISOString() }
          : s
      );

      await mutate(
        async (): Promise<Scene[]> => {
          await api.patch(
            `/api/v1/projects/${projectId}/scenes/${sceneId}`,
            updates
          );
          // Refetch to get server-confirmed data
          const response = await api.get<StoryboardResponse>(cacheKey);
          return response.data.scenes;
        },
        {
          optimisticData,
          rollbackOnError: true,
          revalidate: false,
        }
      );
    },
    [projectId, cacheKey, scenes, mutate]
  );

  /**
   * Delete a single scene.
   * Optimistically removes from local cache.
   * DELETE /api/v1/projects/{projectId}/scenes/{sceneId}
   */
  const deleteScene = useCallback(
    async (sceneId: string): Promise<void> => {
      if (!projectId || !cacheKey) {
        throw new Error("Project ID is required");
      }

      // Optimistic removal
      const optimisticData = scenes?.filter(
        (s: Scene) => s.id !== sceneId
      );

      await mutate(
        async (): Promise<Scene[]> => {
          await api.delete(
            `/api/v1/projects/${projectId}/scenes/${sceneId}`
          );
          const response = await api.get<StoryboardResponse>(cacheKey);
          return response.data.scenes;
        },
        {
          optimisticData,
          rollbackOnError: true,
          revalidate: false,
        }
      );
    },
    [projectId, cacheKey, scenes, mutate]
  );

  /**
   * Delete multiple scenes in a batch.
   * POST /api/v1/projects/{projectId}/scenes/batch-delete
   */
  const deleteScenes = useCallback(
    async (sceneIds: string[]): Promise<void> => {
      if (!projectId || !cacheKey) {
        throw new Error("Project ID is required");
      }

      const sceneIdSet = new Set(sceneIds);

      // Optimistic removal
      const optimisticData = scenes?.filter(
        (s: Scene) => !sceneIdSet.has(s.id)
      );

      await mutate(
        async (): Promise<Scene[]> => {
          await api.post(
            `/api/v1/projects/${projectId}/scenes/batch-delete`,
            { scene_ids: sceneIds }
          );
          const response = await api.get<StoryboardResponse>(cacheKey);
          return response.data.scenes;
        },
        {
          optimisticData,
          rollbackOnError: true,
          revalidate: false,
        }
      );
    },
    [projectId, cacheKey, scenes, mutate]
  );

  /**
   * Reorder scenes after drag-drop.
   * Optimistically reorders local cache using splice logic.
   * PUT /api/v1/projects/{projectId}/scenes/reorder
   *
   * The API expects a payload with the new scene order:
   * { scene_ids: [id1, id2, id3, ...] }
   */
  const reorderScenes = useCallback(
    async (
      sourceIndex: number,
      destinationIndex: number
    ): Promise<void> => {
      if (!projectId || !cacheKey || !sortedScenes) {
        throw new Error("Project ID and scenes are required");
      }

      // Compute new order locally
      const newOrder = [...sortedScenes];
      const [movedScene] = newOrder.splice(sourceIndex, 1);
      newOrder.splice(destinationIndex, 0, movedScene);

      // Update scene_index values
      const reorderedScenes = newOrder.map(
        (s: Scene, idx: number) => ({
          ...s,
          scene_index: idx,
        })
      );

      // Build API payload
      const payload: SceneReorderPayload = {
        scene_ids: reorderedScenes.map((s: Scene) => s.id),
      };

      await mutate(
        async (): Promise<Scene[]> => {
          await api.put(
            `/api/v1/projects/${projectId}/scenes/reorder`,
            payload
          );
          const response = await api.get<StoryboardResponse>(cacheKey);
          return response.data.scenes;
        },
        {
          optimisticData: reorderedScenes,
          rollbackOnError: true,
          revalidate: false,
        }
      );
    },
    [projectId, cacheKey, sortedScenes, mutate]
  );

  /**
   * Regenerate a single scene.
   * POST /api/v1/projects/{projectId}/scenes/{sceneId}/regenerate
   *
   * Sets scene status to REGENERATING optimistically.
   */
  const regenerateScene = useCallback(
    async (sceneId: string): Promise<void> => {
      if (!projectId || !cacheKey) {
        throw new Error("Project ID is required");
      }

      // Optimistic status update
      const optimisticData = scenes?.map((s: Scene) =>
        s.id === sceneId
          ? { ...s, status: "REGENERATING" as const }
          : s
      );

      await mutate(
        async (): Promise<Scene[]> => {
          await api.post(
            `/api/v1/projects/${projectId}/scenes/${sceneId}/regenerate`
          );
          const response = await api.get<StoryboardResponse>(cacheKey);
          return response.data.scenes;
        },
        {
          optimisticData,
          rollbackOnError: true,
          revalidate: true, // Revalidate to poll for completion
        }
      );
    },
    [projectId, cacheKey, scenes, mutate]
  );

  /**
   * Regenerate multiple scenes in a batch.
   * POST /api/v1/projects/{projectId}/scenes/batch-regenerate
   */
  const regenerateScenes = useCallback(
    async (sceneIds: string[]): Promise<void> => {
      if (!projectId || !cacheKey) {
        throw new Error("Project ID is required");
      }

      const sceneIdSet = new Set(sceneIds);

      // Optimistic status update for all selected scenes
      const optimisticData = scenes?.map((s: Scene) =>
        sceneIdSet.has(s.id)
          ? { ...s, status: "REGENERATING" as const }
          : s
      );

      await mutate(
        async (): Promise<Scene[]> => {
          await api.post(
            `/api/v1/projects/${projectId}/scenes/batch-regenerate`,
            { scene_ids: sceneIds }
          );
          const response = await api.get<StoryboardResponse>(cacheKey);
          return response.data.scenes;
        },
        {
          optimisticData,
          rollbackOnError: true,
          revalidate: true,
        }
      );
    },
    [projectId, cacheKey, scenes, mutate]
  );

  return {
    scenes: sortedScenes,
    isLoading,
    error,
    mutate: () => mutate(),
    updateScene,
    deleteScene,
    deleteScenes,
    reorderScenes,
    regenerateScene,
    regenerateScenes,
  };
}
