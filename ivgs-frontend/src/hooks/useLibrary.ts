/**
 * AD-09 library data hooks — assets, actors, presets.
 *
 * One hook per entity, each SWR-backed with mutations that revalidate. The
 * paginated envelope is unwrapped here so pages never have to know whether a
 * route returns `{data, total, ...}` or a bare array — the two shapes have
 * caused contract drift in this codebase before (P2.58, `GET /fleet`).
 */
"use client";

import { useCallback } from "react";
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/lib/api-client";
import type {
  Actor,
  ActorCreatePayload,
  ActorUpdatePayload,
  LibraryAsset,
  LibraryAssetKind,
  LibraryAssetUploadResult,
  LibraryReferencePayload,
  OwnerScope,
  Preset,
  PresetApplyResult,
  PresetPayload,
} from "@/types/library";

const ASSETS_URL = "/api/v1/library/assets";
const ACTORS_URL = "/api/v1/actors";
const PRESETS_URL = "/api/v1/presets";

async function listFetcher<T>(url: string): Promise<T[]> {
  const res = await apiClient.get<PaginatedResponse<T>>(url);
  return res.data.data;
}

/* ---------------------------------------------------------------- assets */

export interface UseLibraryAssetsResult {
  assets: LibraryAsset[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<unknown>;
  uploadAsset: (input: {
    file: File;
    kind: LibraryAssetKind;
    name: string;
    description?: string;
    tags?: string[];
    ownerScope?: OwnerScope;
  }) => Promise<LibraryAssetUploadResult>;
  updateAsset: (
    id: string,
    patch: { name?: string; description?: string; tags?: string[] },
  ) => Promise<LibraryAsset>;
  supersedeAsset: (id: string, replacementId: string) => Promise<LibraryAsset>;
  promoteAsset: (id: string) => Promise<LibraryAsset>;
}

export function useLibraryAssets(kind?: string): UseLibraryAssetsResult {
  const url = kind ? `${ASSETS_URL}?kind=${encodeURIComponent(kind)}&per_page=100` : `${ASSETS_URL}?per_page=100`;
  const { data, error, isLoading, mutate } = useSWR<LibraryAsset[]>(
    url,
    listFetcher<LibraryAsset>,
    { revalidateOnFocus: true },
  );

  const uploadAsset = useCallback(
    async (input: {
      file: File;
      kind: LibraryAssetKind;
      name: string;
      description?: string;
      tags?: string[];
      ownerScope?: OwnerScope;
    }): Promise<LibraryAssetUploadResult> => {
      const form = new FormData();
      form.append("file", input.file);
      form.append("kind", input.kind);
      form.append("name", input.name);
      if (input.description) form.append("description", input.description);
      if (input.tags && input.tags.length > 0) {
        form.append("tags", JSON.stringify(input.tags));
      }
      form.append("owner_scope", input.ownerScope ?? "user");
      const res = await apiClient.upload<LibraryAssetUploadResult>(ASSETS_URL, form);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const updateAsset = useCallback(
    async (id: string, patch: { name?: string; description?: string; tags?: string[] }) => {
      const res = await apiClient.patch<LibraryAsset>(`${ASSETS_URL}/${id}`, patch);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const supersedeAsset = useCallback(
    async (id: string, replacementId: string) => {
      const res = await apiClient.post<LibraryAsset>(
        `${ASSETS_URL}/${id}/supersede?replacement_id=${encodeURIComponent(replacementId)}`,
      );
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const promoteAsset = useCallback(
    async (id: string) => {
      const res = await apiClient.post<LibraryAsset>(`${ASSETS_URL}/${id}/promote`);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  return {
    assets: data,
    isLoading,
    error: error as Error | undefined,
    refresh: mutate,
    uploadAsset,
    updateAsset,
    supersedeAsset,
    promoteAsset,
  };
}

/* ---------------------------------------------------------------- actors */

export interface UseActorsResult {
  actors: Actor[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<unknown>;
  createActor: (payload: ActorCreatePayload) => Promise<Actor>;
  updateActor: (id: string, payload: ActorUpdatePayload) => Promise<Actor>;
}

export function useActors(includeInactive = false): UseActorsResult {
  const url = `${ACTORS_URL}?per_page=100${includeInactive ? "&include_inactive=true" : ""}`;
  const { data, error, isLoading, mutate } = useSWR<Actor[]>(
    url,
    listFetcher<Actor>,
    { revalidateOnFocus: true },
  );

  const createActor = useCallback(
    async (payload: ActorCreatePayload) => {
      const res = await apiClient.post<Actor>(ACTORS_URL, payload);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const updateActor = useCallback(
    async (id: string, payload: ActorUpdatePayload) => {
      const res = await apiClient.patch<Actor>(`${ACTORS_URL}/${id}`, payload);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  return {
    actors: data,
    isLoading,
    error: error as Error | undefined,
    refresh: mutate,
    createActor,
    updateActor,
  };
}

/* --------------------------------------------------------------- presets */

export interface UsePresetsResult {
  presets: Preset[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<unknown>;
  createPreset: (input: {
    name: string;
    description?: string;
    payload: PresetPayload;
    ownerScope?: OwnerScope;
  }) => Promise<Preset>;
  revisePreset: (
    name: string,
    input: { description?: string; payload: PresetPayload },
  ) => Promise<Preset>;
  listVersions: (name: string) => Promise<Preset[]>;
}

export function usePresets(activeOnly = true): UsePresetsResult {
  const url = `${PRESETS_URL}?per_page=100&active_only=${activeOnly ? "true" : "false"}`;
  const { data, error, isLoading, mutate } = useSWR<Preset[]>(
    url,
    listFetcher<Preset>,
    { revalidateOnFocus: true },
  );

  const createPreset = useCallback(
    async (input: {
      name: string;
      description?: string;
      payload: PresetPayload;
      ownerScope?: OwnerScope;
    }) => {
      const res = await apiClient.post<Preset>(PRESETS_URL, {
        name: input.name,
        description: input.description ?? null,
        payload: input.payload,
        owner_scope: input.ownerScope ?? "user",
      });
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const revisePreset = useCallback(
    async (name: string, input: { description?: string; payload: PresetPayload }) => {
      const res = await apiClient.post<Preset>(
        `${PRESETS_URL}/by-name/${encodeURIComponent(name)}/revise`,
        { description: input.description ?? null, payload: input.payload },
      );
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const listVersions = useCallback(async (name: string) => {
    const res = await apiClient.get<Preset[]>(
      `${PRESETS_URL}/by-name/${encodeURIComponent(name)}/versions`,
    );
    return res.data;
  }, []);

  return {
    presets: data,
    isLoading,
    error: error as Error | undefined,
    refresh: mutate,
    createPreset,
    revisePreset,
    listVersions,
  };
}

/* --------------------------------------------------------- project seam */

/** Apply a preset to a project. Returns the ITEMISED result — `applied` and
 *  `recorded_not_applied` are separate lists and the caller must show both. */
export async function applyPresetToProject(
  projectId: string,
  presetId: string,
): Promise<PresetApplyResult> {
  const res = await apiClient.post<PresetApplyResult>(
    `/api/v1/projects/${projectId}/apply-preset`,
    { preset_id: presetId },
  );
  return res.data;
}

/** AD-09.4.2 reference-don't-copy. No bytes move. */
export async function referenceLibraryAsset(
  projectId: string,
  payload: LibraryReferencePayload,
): Promise<{ id: string; library_asset_id: string | null }> {
  const res = await apiClient.post<{ id: string; library_asset_id: string | null }>(
    `/api/v1/projects/${projectId}/library-reference`,
    payload,
  );
  return res.data;
}
