import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type { Project, LanguageVariant } from "@/types/api";

/**
 * Projects data fetching and mutations hook.
 *
 * When called without an ID, fetches the full project list for the gallery.
 * When called with an ID, fetches a single project with full details.
 */

interface UseProjectsReturn {
  projects: Project[] | undefined;
  project: Project | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<Project[] | Project>;
  createProject: (formData: FormData) => Promise<Project>;
  addLanguage: (languageCode: string) => Promise<LanguageVariant>;
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
   * Create a new project via multipart form upload.
   */
  const createProject = async (formData: FormData): Promise<Project> => {
    const response = await apiClient.post<{ data: Project }>(
      "/api/v1/projects",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    listMutate();
    return response.data;
  };

  /**
   * Add a language variant to the current project.
   */
  const addLanguage = async (
    languageCode: string
  ): Promise<LanguageVariant> => {
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
    addLanguage,
    retryLanguage,
  };
}
