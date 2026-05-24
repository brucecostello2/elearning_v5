import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type { GpuNodeResponse } from "@/types/api";

/** Legacy alias — components reference NodeStatus but backend uses GpuNodeResponse */
type NodeStatus = GpuNodeResponse;

/**
 * §8.1.5 Node Monitor — Node status polling hook.
 * Polls /api/v1/nodes every 10 seconds.
 */

interface UseNodesReturn {
  nodes: NodeStatus[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
}

const nodesFetcher = async (url: string): Promise<any> => {
  const response = await apiClient.get<{ data: NodeStatus[] }>(url);
  return response.data;
};

export function useNodes(): UseNodesReturn {
  const { data, error, isLoading } = useSWR<NodeStatus[]>(
    "/api/v1/nodes",
    nodesFetcher,
    {
      refreshInterval: 10000,
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
      dedupingInterval: 5000,
    }
  );

  return {
    nodes: data,
    isLoading,
    error,
  };
}
