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
  addLanguage: (languageCode: string) => Promise<LanguageVariant>;
  /** Takes the variant UUID -- the retry route's path param is a UUID. */
  retryLanguage: (variantId: string) => Promise<void>;
  triggerPipeline: (tier?: RenderTier) => Promise<Project>;
}

/** AD-01 model-selection tier for a run (IVGS-0.3). */
export type RenderTier = "prototype" | "production";

/**
 * States from which `POST /projects/{id}/trigger` is legal.
 *
 * `ProjectService.trigger_pipeline` (project_service.py:266) accepts exactly
 * DRAFT (-> TRANSCRIPT_REFINEMENT) and USER_REVIEW (-> FINAL_RENDER) and
 * raises ValueError otherwise, which the route turns into a 409. Mirrored
 * here so the button is simply absent rather than offered and then refused.
 */
export const TRIGGERABLE_STATES = ["DRAFT", "USER_REVIEW"] as const;

export function canTriggerPipeline(state: string | null | undefined): boolean {
  return (
    typeof state === "string" &&
    (TRIGGERABLE_STATES as readonly string[]).includes(state)
  );
}

const projectsFetcher = async (url: string): Promise<Project[]> => {
  const response = await apiClient.get<{ data: Project[]; total: number; page: number; per_page: number; pages: number; has_more: boolean }>(url);
  // API returns { data: [...], total, page, ... } — unwrap the array.
  return response.data.data;
};

const projectFetcher = async (url: string): Promise<Project> => {
  // WP-IVGS-0 F9: GET /api/v1/projects/{id} has response_model=ProjectResponse
  // and returns the project UNWRAPPED. This used to read response.data.data, so
  // the project detail page — the page the New Project form navigates to after
  // a successful create — received undefined.
  //
  // The list route above is different and genuinely does wrap: it returns
  // PaginatedResponse { data: [...], total, page, ... }. Only the single-project
  // route is flat. Do not "fix" projectsFetcher to match this one.
  const response = await apiClient.get<Project>(url);
  return response.data;
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
   *
   * WP-43 Task 3a. The route is `POST /projects/{id}/languages` with body
   * `{language_code}` and it accepts exactly eight BCP-47 codes
   * (`SUPPORTED_LANGUAGES`, `schemas/language_variant.py:11`). The form used
   * to offer bare ISO-639-1 codes, none of which is in that set, so the
   * response was always a 422 whose `detail` array the old client reduced to
   * "Request failed with status 422". The picker now offers only accepted
   * codes and the error, if one still arrives, arrives as the server's own
   * sentence.
   */
  const addLanguage = async (
    languageCode: string
  ): Promise<LanguageVariant> => {
    if (!projectId) throw new Error("Project ID required");
    const response = await apiClient.post<LanguageVariant>(
      `/api/v1/projects/${projectId}/languages`,
      { language_code: languageCode }
    );
    detailMutate();
    return response.data;
  };

  /**
   * Retry a failed language variant.
   *
   * WP-43 Task 3a. This took a language CODE and put it in the path, but the
   * route is `POST /projects/{id}/languages/{variant_id}/retry` and
   * `variant_id` is a `UUID` path parameter. Reproduced live 2026-08-25:
   *
   *   POST .../languages/en-US/retry -> 422
   *   {"detail":[{"type":"uuid_parsing","loc":["path","variant_id"],
   *     "msg":"Input should be a valid UUID, ...","input":"en-US"}]}
   *
   * The variant id is not on the project detail payload -- its
   * `language_variants` entries are `{language_code, state}` and nothing
   * else -- which is why the caller now reads `GET /projects/{id}/languages`
   * for the rows it renders.
   */
  const retryLanguage = async (variantId: string): Promise<void> => {
    if (!projectId) throw new Error("Project ID required");
    if (!variantId) throw new Error("Language variant id required");
    await apiClient.post(
      `/api/v1/projects/${projectId}/languages/${encodeURIComponent(variantId)}/retry`
    );
    detailMutate();
  };

  /**
   * Trigger pipeline execution from the project's current state.
   *
   * WP-40 Task 3b (ledger M6). `POST /api/v1/projects/{id}/trigger?tier=...`
   * (projects.py:146) exists and works; nothing in the GUI called it, so
   * starting a run meant a curl block.
   *
   * A 409 arrives as an ApiRequestError carrying the server's own reason --
   * "Cannot trigger pipeline from state 'X'. Triggerable states: [...]" or
   * "Cannot trigger pipeline: no transcripts uploaded". Callers show that
   * text; there is nothing this side can add to it that would be truer.
   */
  const triggerPipeline = async (
    tier: RenderTier = "prototype"
  ): Promise<Project> => {
    if (!projectId) throw new Error("Project ID required");
    const response = await apiClient.post<Project>(
      `/api/v1/projects/${projectId}/trigger?tier=${encodeURIComponent(tier)}`
    );
    detailMutate();
    return response.data;
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
    triggerPipeline,
  };
}
