/**
 * WP-66 — the middle that was missing.
 *
 * Models are certified in MBCP, made available by the IVGS admin, and then
 * selected by the user scene by scene. Both ends were complete: the schema
 * carries a nullable `scene_id` so per-scene binding was designed in, and
 * dispatch honours it scene-first then project. The frontend called none of
 * the three endpoints that join them.
 */
"use client";

import { useCallback } from "react";
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  ClearSelectionResult,
  ModelSelection,
  ModelStage,
  ModelTier,
  ProjectSelections,
  StageBinding,
} from "@/types/models";

const base = (projectId: string): string =>
  `/api/v1/projects/${projectId}/model-selections`;

export interface UseModelSelectionsResult {
  panel: ProjectSelections | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ProjectSelections | undefined>;
  /** Bind a model. `sceneId` null = the project binding. */
  select: (args: {
    stage: ModelStage;
    tier: ModelTier;
    modelId: string;
    rationale: string;
    sceneId?: string | null;
  }) => Promise<ModelSelection>;
  /** "Use the project default" — DELETES the scene row. Never writes a copy of
   *  the project one; see the route's docstring for why that distinction is
   *  load-bearing rather than stylistic. */
  clearScene: (args: {
    stage: ModelStage;
    tier: ModelTier;
    sceneId: string;
  }) => Promise<ClearSelectionResult>;
}

export function useModelSelections(
  projectId: string,
  tier: ModelTier = "production",
): UseModelSelectionsResult {
  const url = `${base(projectId)}/panel?tier=${tier}`;
  const { data, error, isLoading, mutate } = useSWR<ProjectSelections>(
    projectId ? url : null,
    async (u: string) => (await apiClient.get<ProjectSelections>(u)).data,
    { revalidateOnFocus: true },
  );

  const select = useCallback(
    async (args: {
      stage: ModelStage;
      tier: ModelTier;
      modelId: string;
      rationale: string;
      sceneId?: string | null;
    }): Promise<ModelSelection> => {
      const res = await apiClient.put<ModelSelection>(base(projectId), {
        stage: args.stage,
        tier: args.tier,
        model_id: args.modelId,
        scene_id: args.sceneId ?? null,
        rationale: args.rationale,
      });
      await mutate();
      return res.data;
    },
    [projectId, mutate],
  );

  const clearScene = useCallback(
    async (args: {
      stage: ModelStage;
      tier: ModelTier;
      sceneId: string;
    }): Promise<ClearSelectionResult> => {
      const res = await apiClient.post<ClearSelectionResult>(
        `${base(projectId)}/clear`,
        { stage: args.stage, tier: args.tier, scene_id: args.sceneId },
      );
      await mutate();
      return res.data;
    },
    [projectId, mutate],
  );

  return {
    panel: data,
    isLoading,
    error: error as Error | undefined,
    refresh: () => mutate(),
    select,
    clearScene,
  };
}

/**
 * One scene's binding, for the stage its OWN media type dispatches to.
 *
 * Keyed on `mediaType` so changing Media Type in the editor re-fetches and the
 * candidate list changes with it — an animation scene offers animation models.
 * The mapping lives server-side (`selection_panel.MEDIA_TYPE_STAGE`) so the two
 * cannot drift.
 */
export function useSceneSelection(
  projectId: string,
  sceneId: string | null,
  mediaType: string,
  tier: ModelTier = "production",
): {
  binding: StageBinding | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<StageBinding | undefined>;
} {
  const url =
    projectId && sceneId
      ? `${base(projectId)}/scene/${sceneId}?media_type=${encodeURIComponent(
          mediaType || "image",
        )}&tier=${tier}`
      : null;
  const { data, error, isLoading, mutate } = useSWR<StageBinding>(
    url,
    async (u: string) => (await apiClient.get<StageBinding>(u)).data,
    { revalidateOnFocus: false },
  );
  return {
    binding: data,
    isLoading,
    error: error as Error | undefined,
    refresh: () => mutate(),
  };
}
