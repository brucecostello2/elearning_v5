import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  Project,
  LanguageVariant,
  ProjectCreatePayload,
} from "@/types/api";

/**
 * Projects data fetching and mutations hook.
 *
 * When called without an ID, fetches the full project list for the gallery.
 * When called with an ID, fetches a single project with full details.
 */

/** Asset types the New Project form uploads against a project. */
export type ProjectAssetType = "reference_clip" | "document";

interface UseProjectsReturn {
  projects: Project[] | undefined;
  project: Project | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<Project[] | Project>;
  createProject: (payload: ProjectCreatePayload) => Promise<Project>;
  uploadProjectAsset: (
    projectId: string,
    file: File,
    assetType: ProjectAssetType
  ) => Promise<{ id: string }>;
  uploadTranscripts: (projectId: string, files: File[]) => Promise<unknown>;
  addLanguage: (languageCode: string) => Promise<any>;
  retryLanguage: (languageCode: string) => Promise<void>;
}

const projectsFetcher = async (url: string): Promise<Project[]> => {
  const response = await apiClient.get<{ data: Project[]; total: number; page: number; per_page: number; pages: number; has_more: boolean }>(url);
  // API returns { data: [...], total, page, ... } — unwrap the array.
  return response.data.data;
};

const projectFetcher = async (url: string): Promise<Project> => {
  const response = await apiClient.get<{ data: Project }>(url);
  // API returns { data: { ...project } } — unwrap.
  return response.data.data;
};

export function useProjects(projectId?: string): UseProjectsReturn {
  // List mode (no ID) or detail mode (with ID)
  const isDetail = !!projectId;
  const url = isDetail
    ? `/api/v1/projects/${projectId}`
    : "/api/v1/projects";

  const {
    data: listData,
    error: listError,
    isLoading: listLoading,
    mutate: listMutate,
  } = useSWR<Project[]>(
    !isDetail ? url : null,
    projectsFetcher,
    {
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
      dedupingInterval: 5000,
    }
  );

  const {
    data: detailData,
    error: detailError,
    isLoading: detailLoading,
    mutate: detailMutate,
  } = useSWR<Project>(
    isDetail ? url : null,
    projectFetcher,
    {
      revalidateOnFocus: true,
      refreshInterval: 10000,
    }
  );

  /**
   * Create a new project.
   *
   * IVGS-0.5: this used to POST multipart/form-data to a JSON Pydantic
   * endpoint, through an apiClient.post that JSON.stringify's whatever it is
   * given — so the body arrived as "{}" and the request could never succeed.
   * POST /api/v1/projects takes ProjectCreate: name, description,
   * max_runtime_seconds, target_languages. Files are separate uploads.
   */
  const createProject = async (
    payload: ProjectCreatePayload
  ): Promise<Project> => {
    const response = await apiClient.post<Project>(
      "/api/v1/projects",
      payload
    );
    listMutate();
    return response.data;
  };

  /**
   * Upload one file against a project through the existing assets route.
   *
   * IVGS-0.5: the talking-head clip goes up as `reference_clip`, which is what
   * the orchestrator looks for when it builds the Stage 6 input
   * (_fetch_reference_clip_id queries asset_type=reference_clip).
   */
  const uploadProjectAsset = async (
    projectId: string,
    file: File,
    assetType: ProjectAssetType
  ): Promise<{ id: string }> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("asset_type", assetType);
    const response = await apiClient.upload<{ id: string }>(
      `/api/v1/projects/${projectId}/assets/upload`,
      formData
    );
    return response.data;
  };

  /**
   * Upload transcript files. The pipeline refuses to start without at least
   * one ("Cannot trigger pipeline: no transcripts uploaded").
   */
  const uploadTranscripts = async (
    projectId: string,
    files: File[]
  ): Promise<unknown> => {
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    const response = await apiClient.upload<unknown>(
      `/api/v1/projects/${projectId}/transcripts/upload`,
      formData
    );
    return response.data;
  };

  /**
   * Add a language variant to the current project.
   */
  const addLanguage = async (
    languageCode: string
  ): Promise<any> => {
    if (!projectId) throw new Error("Project ID required");
    const response = await apiClient.post<{ data: LanguageVariant }>(
      `/api/v1/projects/${projectId}/languages`,
      { language_code: languageCode }
    );
    detailMutate();
    return response.data;
  };

  /**
   * Retry a failed language variant.
   */
  const retryLanguage = async (languageCode: string): Promise<void> => {
    if (!projectId) throw new Error("Project ID required");
    await apiClient.post(
      `/api/v1/projects/${projectId}/languages/${languageCode}/retry`
    );
    detailMutate();
  };

  return {
    projects: listData,
    project: detailData,
    isLoading: isDetail ? detailLoading : listLoading,
    error: isDetail ? detailError : listError,
    mutate: (isDetail ? detailMutate : listMutate) as KeyedMutator<
      Project[] | Project
    >,
    createProject,
    uploadProjectAsset,
    uploadTranscripts,
    addLanguage,
    retryLanguage,
  };
}
