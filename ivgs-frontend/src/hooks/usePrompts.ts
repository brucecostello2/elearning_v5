import { useCallback, useMemo } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type {
  PromptRecord,
  PromptTier,
  PromptType,
  PromptVersion,
  PromptCreatePayload,
  PromptLibraryEntry,
  PlaygroundRequest,
  PlaygroundResponse,
  PlaygroundSavePayload,
} from "@/types/prompts";

/**
 * §9 Prompt Management System — Data Hook
 *
 * Custom hook providing complete prompt management across all three tiers:
 *
 * Tier hierarchy (§9.1):
 *   GLOBAL → PROJECT → SCENE (resolution: first match wins from bottom up)
 *
 * Operations:
 * - Fetch prompts by tier (GET /api/v1/prompts?tier=X)
 * - Fetch prompts by project (GET /api/v1/projects/{id}/prompts)
 * - Fetch prompts by scene (GET /api/v1/projects/{id}/scenes/{sid}/prompts)
 * - Create prompt (POST /api/v1/prompts)
 * - Update prompt (PUT /api/v1/prompts/{id})
 * - Delete prompt (DELETE /api/v1/prompts/{id})
 * - Get version history (GET /api/v1/prompts/{id}/versions)
 * - Rollback to version (POST /api/v1/prompts/{id}/rollback)
 * - Resolve effective prompt (GET /api/v1/prompts/resolve?type=X&project=Y&scene=Z)
 * - Execute playground (POST /api/v1/playground/execute)
 * - Save playground result (POST /api/v1/playground/save)
 * - Fetch library (GET /api/v1/prompts/library)
 * - Remove from library (DELETE /api/v1/prompts/library/{id})
 *
 * SWR configuration:
 * - Revalidation on focus: enabled
 * - Dedup interval: 10 seconds (prompts change less frequently)
 * - Retry on error: 3 times
 *
 * @param options - Hook configuration options
 * @returns Hook return object with prompt data and mutation functions
 */

/** Hook options for configuring which prompts to fetch */
interface UsePromptsOptions {
  /** Tier to fetch prompts for */
  tier?: PromptTier;
  /** Project ID for project/scene tier prompts */
  projectId?: string;
  /** Scene ID for scene-tier prompts */
  sceneId?: string;
}

/** SWR fetcher — backend returns bare array, not wrapped object */
async function fetchPrompts(url: string): Promise<PromptRecord[]> {
  const response = await api.get<PromptRecord[]>(url);
  return response.data;
}

/** Build cache key based on options */
function getPromptsKey(options: UsePromptsOptions): string | null {
  if (options.sceneId && options.projectId) {
    return `/api/v1/projects/${options.projectId}/scenes/${options.sceneId}/prompts`;
  }
  if (options.projectId) {
    return `/api/v1/projects/${options.projectId}/prompts`;
  }
  if (options.tier) {
    return `/api/v1/prompts?prompt_type=${encodeURIComponent(options.tier)}`;
  }
  return null;
}

interface UsePromptsReturn {
  /** Array of prompt records */
  prompts: PromptRecord[] | undefined;
  /** Whether data is loading */
  isLoading: boolean;
  /** Error object */
  error: Error | undefined;
  /** SWR mutate for manual revalidation */
  mutate: () => void;
  /** Create a new prompt */
  createPrompt: (payload: PromptCreatePayload) => Promise<PromptRecord>;
  /** Update an existing prompt (creates new version per §9.3) */
  updatePrompt: (
    promptId: string,
    promptText: string,
    changeNote?: string
  ) => Promise<PromptRecord>;
  /** Delete a prompt */
  deletePrompt: (promptId: string) => Promise<void>;
  /** Get version history for a prompt */
  getVersionHistory: (promptId: string) => Promise<PromptVersion[]>;
  /** Rollback a prompt to a specific version */
  rollbackPrompt: (promptId: string, versionId: string) => Promise<void>;
  /** Resolve the effective prompt for a type/project/scene */
  resolvePrompt: (
    promptType: PromptType,
    projectId?: string,
    sceneId?: string
  ) => Promise<PromptRecord>;
  /** Execute a prompt in the playground */
  executePlayground: (
    request: PlaygroundRequest
  ) => Promise<PlaygroundResponse>;
  /** Save a playground result as a prompt version */
  savePlaygroundResult: (
    payload: PlaygroundSavePayload
  ) => Promise<void>;
  /** Library entries */
  libraryEntries: PromptLibraryEntry[] | undefined;
  /** Whether library is loading */
  isLibraryLoading: boolean;
  /** Library error */
  libraryError: string | null;
  /** Fetch library entries */
  fetchLibrary: () => Promise<void>;
  /** Remove from library */
  removeFromLibrary: (entryId: string) => Promise<void>;
}

export function usePrompts(options: UsePromptsOptions): UsePromptsReturn {
  // ── SWR Data Fetching ─────────────────────────────────────────────
  const cacheKey = getPromptsKey(options);
  const {
    data: prompts,
    error,
    isLoading,
    mutate,
  } = useSWR<PromptRecord[], Error>(cacheKey, fetchPrompts, {
    revalidateOnFocus: true,
    dedupingInterval: 10000,
    errorRetryCount: 3,
    errorRetryInterval: 2000,
  });

  // ── Library SWR ───────────────────────────────────────────────────
  const {
    data: libraryEntries,
    error: libError,
    isLoading: isLibraryLoading,
    mutate: mutateLibrary,
  } = useSWR<PromptLibraryEntry[], Error>(
    "/api/v1/prompts/library",
    async (url: string): Promise<PromptLibraryEntry[]> => {
      const response = await api.get<PromptLibraryEntry[]>(url);
      return response.data;
    },
    {
      revalidateOnFocus: false,
      dedupingInterval: 30000,
      // Don't auto-fetch; triggered manually via fetchLibrary
      revalidateOnMount: false,
    }
  );

  /**
   * Create a new prompt.
   * POST /api/v1/prompts
   *
   * Creates a new prompt record at the specified tier with version 1.
   */
  const createPrompt = useCallback(
    async (payload: PromptCreatePayload): Promise<PromptRecord> => {
      const response = await api.post<PromptRecord>(
        "/api/v1/prompts",
        payload
      );
      await mutate(); // Revalidate cache
      return response.data;
    },
    [mutate]
  );

  /**
   * Update an existing prompt.
   * PUT /api/v1/prompts/{promptId}
   *
   * Per §9.3, every edit creates a new version record.
   * The previous version is retained and the new version
   * becomes active (is_active = true).
   */
  const updatePrompt = useCallback(
    async (
      promptId: string,
      promptText: string,
      changeNote?: string
    ): Promise<PromptRecord> => {
      const response = await api.put<PromptRecord>(
        `/api/v1/prompts/${promptId}`,
        {
          prompt_text: promptText,
          change_note: changeNote,
        }
      );
      await mutate(); // Revalidate cache
      return response.data;
    },
    [mutate]
  );

  /**
   * Delete a prompt.
   * DELETE /api/v1/prompts/{promptId}
   *
   * Removes the prompt override at the current tier.
   * The system will fall back to the parent tier's prompt.
   */
  const deletePrompt = useCallback(
    async (promptId: string): Promise<void> => {
      await api.delete(`/api/v1/prompts/${promptId}`);
      await mutate(); // Revalidate cache
    },
    [mutate]
  );

  /**
   * Get full version history for a prompt.
   * GET /api/v1/prompts/{promptId}/versions
   *
   * Returns all versions ordered by version_number descending.
   * Per §9.3, previous versions are retained and never deleted.
   */
  const getVersionHistory = useCallback(
    async (promptId: string): Promise<PromptVersion[]> => {
      const response = await api.get<PromptVersion[]>(
        `/api/v1/prompts/${promptId}/versions`
      );
      return response.data;
    },
    []
  );

  /**
   * Rollback a prompt to a specific version.
   * POST /api/v1/prompts/{promptId}/rollback
   *
   * Creates a new version with the content from the specified version.
   * The old active version becomes inactive.
   * The new version (copy of target) becomes is_active = true.
   */
  const rollbackPrompt = useCallback(
    async (promptId: string, versionId: string): Promise<void> => {
      await api.post(`/api/v1/prompts/${promptId}/rollback`, {
        target_version_id: versionId,
      });
      await mutate(); // Revalidate cache
    },
    [mutate]
  );

  /**
   * Resolve the effective prompt for a given type, project, and scene.
   * GET /api/v1/prompts/resolve
   *
   * Implements the resolution order from §9.1:
   * Scene override → Project override → Global default
   */
  const resolvePrompt = useCallback(
    async (
      promptType: PromptType,
      projectId?: string,
      sceneId?: string
    ): Promise<PromptRecord> => {
      const params = new URLSearchParams({
        prompt_type: promptType,
      });
      if (projectId) params.set("project_id", projectId);
      if (sceneId) params.set("scene_id", sceneId);

      const response = await api.get<PromptRecord>(
        `/api/v1/prompts/resolve?${params.toString()}`
      );
      return response.data;
    },
    []
  );

  /**
   * Execute a prompt in the Playground.
   * POST /api/v1/playground/execute
   *
   * Sends the prompt to the specified self-hosted model (vLLM or Ollama)
   * and returns the response per §8.1.6.
   */
  const executePlayground = useCallback(
    async (request: PlaygroundRequest): Promise<PlaygroundResponse> => {
      const response = await api.post<PlaygroundResponse>(
        "/api/v1/playground/execute",
        request
      );
      return response.data;
    },
    []
  );

  /**
   * Save a playground result as a new prompt version.
   * POST /api/v1/playground/save
   *
   * Results can be saved as new prompt versions directly from the
   * Playground per §8.1.6.
   */
  const savePlaygroundResult = useCallback(
    async (payload: PlaygroundSavePayload): Promise<void> => {
      await api.post("/api/v1/playground/save", payload);
      await mutate(); // Revalidate prompt cache
    },
    [mutate]
  );

  /**
   * Fetch library entries.
   * GET /api/v1/prompts/library
   */
  const fetchLibrary = useCallback(async (): Promise<void> => {
    await mutateLibrary();
  }, [mutateLibrary]);

  /**
   * Remove a template from the library.
   * DELETE /api/v1/prompts/library/{entryId}
   *
   * The underlying prompt version is not deleted — only the library
   * designation is removed per §9.5.
   */
  const removeFromLibrary = useCallback(
    async (entryId: string): Promise<void> => {
      await api.delete(`/api/v1/prompts/library/${entryId}`);
      await mutateLibrary(); // Revalidate library cache
    },
    [mutateLibrary]
  );

  return {
    prompts,
    isLoading,
    error,
    mutate: () => mutate(),
    createPrompt,
    updatePrompt,
    deletePrompt,
    getVersionHistory,
    rollbackPrompt,
    resolvePrompt,
    executePlayground,
    savePlaygroundResult,
    libraryEntries,
    isLibraryLoading,
    libraryError: libError?.message ?? null,
    fetchLibrary,
    removeFromLibrary,
  };
}
