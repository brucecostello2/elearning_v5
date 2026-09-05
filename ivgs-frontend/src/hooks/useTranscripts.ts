import useSWR, { type KeyedMutator } from "swr";
import { apiClient } from "@/lib/api-client";
import type { Transcript } from "@/types/api";

/**
 * Transcripts data fetching, update, and reorder hook.
 * Fetches all transcripts for a given project, sorted by order.
 */

interface UseTranscriptsReturn {
  transcripts: Transcript[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<Transcript[]>;
  updateTranscript: (
    transcriptId: string,
    payload: { refined_text: string }
  ) => Promise<any>;
  reorderTranscripts: (
    orderMap: { id: string; order: number }[]
  ) => Promise<void>;
}

const transcriptsFetcher = async (url: string): Promise<any> => {
  const response = await apiClient.get<{ data: Transcript[] }>(url);
  return response.data;
};

export function useTranscripts(projectId: string): UseTranscriptsReturn {
  const url = `/api/v1/projects/${projectId}/transcripts`;

  const { data, error, isLoading, mutate } = useSWR<Transcript[]>(
    url,
    transcriptsFetcher,
    {
      revalidateOnFocus: true,
      dedupingInterval: 5000,
    }
  );

  /**
   * Update the refined text of a transcript.
   */
  const updateTranscript = async (
    transcriptId: string,
    payload: { refined_text: string }
  ): Promise<any> => {
    const response = await apiClient.patch<{ data: Transcript }>(
      `/api/v1/projects/${projectId}/transcripts/${transcriptId}`,
      payload
    );
    mutate();
    return response.data;
  };

  /**
   * Reorder transcripts by providing a new order mapping.
   *
   * WP-70 fix S7: the route is `POST /transcripts/reorder` (transcripts.py);
   * this used PUT and answered 405. Latent — no component calls it yet.
   */
  const reorderTranscripts = async (
    orderMap: { id: string; order: number }[]
  ): Promise<void> => {
    await apiClient.post(
      `/api/v1/projects/${projectId}/transcripts/reorder`,
      { order: orderMap }
    );
    mutate();
  };

  return {
    transcripts: data,
    isLoading,
    error,
    mutate,
    updateTranscript,
    reorderTranscripts,
  };
}
