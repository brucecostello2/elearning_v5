import useSWR, { type SWRConfiguration, type KeyedMutator } from "swr";
import { api } from "@/lib/api";
import type { BackupRecord } from "@/types/monitoring";

/**
 * §14 Backup Management Hooks
 *
 * SWR-based data fetching hooks for backup management views.
 * Provides:
 * - Typed backup records from the API
 * - Loading and error states
 * - Cache invalidation via mutate
 *
 * Polling: 60 seconds (backups change infrequently)
 * Source: GET /api/v1/backup/records per §5.2.8
 */

// ── SWR Fetcher ───────────────────────────────────────────────────────

const fetcher = async (url: string) => {
  const response = await api.get(url);
  return response.data;
};

// ── Backup Records Hook ───────────────────────────────────────────────

interface BackupRecordFilters {
  type?: string;
  status?: string;
  page: number;
  pageSize: number;
}

/**
 * useBackupRecords — Fetches backup records with filters.
 *
 * Admin-only. Polls every 60 seconds.
 * Source: GET /api/v1/backup/records per §14.1
 *
 * @param filters - Type, status filter, pagination
 * @returns Backup records, total count, loading/error state
 */
export function useBackupRecords(filters: BackupRecordFilters): {
  records: BackupRecord[] | undefined;
  totalCount: number | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const params = new URLSearchParams();
  if (filters.type) params.set("type", filters.type);
  if (filters.status) params.set("status", filters.status);
  params.set("page", filters.page.toString());
  params.set("per_page", filters.pageSize.toString());

  const key = `/api/v1/backup/records?${params.toString()}`;

  const config: SWRConfiguration = {
    refreshInterval: 60_000,
    revalidateOnFocus: true,
  };

  const { data, error, isLoading, mutate } = useSWR(key, fetcher, config);

  return {
    records: data?.data ?? data?.records ?? data?.results ?? data?.items ?? data,
    totalCount: data?.total ?? data?.count ?? data?.total_count,
    isLoading,
    error,
    mutate,
  };
}
