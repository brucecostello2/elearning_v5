/**
 * Model Store data hook — AD-01.5.2 registry.
 *
 * List via SWR (auto-refresh); mutations return the updated model and
 * revalidate the list. All mutations are admin-only server-side; the page
 * gates the UI accordingly.
 */
"use client";

import { useCallback } from "react";
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  FetchWeightsResult,
  ModelApprovePayload,
  ModelRegisterPayload,
  ModelUpdatePayload,
  StoreModel,
} from "@/types/models";

const LIST_URL = "/api/v1/models";

const fetcher = async (url: string): Promise<StoreModel[]> => {
  const res = await apiClient.get<StoreModel[]>(url);
  return res.data;
};

export interface UseModelsResult {
  models: StoreModel[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<StoreModel[] | undefined>;
  registerModel: (payload: ModelRegisterPayload) => Promise<StoreModel>;
  updateModel: (id: string, payload: ModelUpdatePayload) => Promise<StoreModel>;
  approveModel: (id: string, payload: ModelApprovePayload) => Promise<StoreModel>;
  deprecateModel: (id: string) => Promise<StoreModel>;
  retireModel: (id: string) => Promise<StoreModel>;
  /** WP-65. Admin-only, GUI-only. Resolves with the outcome even when the
   *  fetch was REFUSED — a refusal is an answer, not an exception, and the
   *  page renders which of the several refusals it was. */
  fetchWeights: (id: string) => Promise<FetchWeightsResult>;
}

export function useModels(): UseModelsResult {
  const { data, error, isLoading, mutate } = useSWR<StoreModel[]>(
    LIST_URL,
    fetcher,
    { refreshInterval: 30_000, revalidateOnFocus: true },
  );

  const fetchWeights = useCallback(
    async (id: string): Promise<FetchWeightsResult> => {
      // 202 in every case, including the refusals — see the route docstring.
      const res = await apiClient.post<FetchWeightsResult>(
        `${LIST_URL}/${id}/fetch-weights`,
      );
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const registerModel = useCallback(
    async (payload: ModelRegisterPayload): Promise<StoreModel> => {
      const res = await apiClient.post<StoreModel>(LIST_URL, payload);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const updateModel = useCallback(
    async (id: string, payload: ModelUpdatePayload): Promise<StoreModel> => {
      const res = await apiClient.patch<StoreModel>(`${LIST_URL}/${id}`, payload);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const approveModel = useCallback(
    async (id: string, payload: ModelApprovePayload): Promise<StoreModel> => {
      const res = await apiClient.post<StoreModel>(
        `${LIST_URL}/${id}/approve`,
        payload,
      );
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const deprecateModel = useCallback(
    async (id: string): Promise<StoreModel> => {
      const res = await apiClient.post<StoreModel>(`${LIST_URL}/${id}/deprecate`);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  const retireModel = useCallback(
    async (id: string): Promise<StoreModel> => {
      const res = await apiClient.post<StoreModel>(`${LIST_URL}/${id}/retire`);
      await mutate();
      return res.data;
    },
    [mutate],
  );

  return {
    models: data,
    isLoading,
    error: error as Error | undefined,
    refresh: () => mutate(),
    registerModel,
    updateModel,
    approveModel,
    deprecateModel,
    retireModel,
    fetchWeights,
  };
}
