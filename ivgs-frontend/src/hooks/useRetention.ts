import useSWR, { type SWRConfiguration, type KeyedMutator } from "swr";
import { api } from "@/lib/api";
import type {
  RetentionPolicy,
  TierMigration,
  OrphanAsset,
} from "@/types/monitoring";

/**
 * §10.4 Retention Policy Hooks
 *
 * SWR-based data fetching hooks for retention policy management.
 * Provides:
 * - Retention policy listing
 * - Migration and orphan data
 * - Loading and error states
 * - Cache invalidation via mutate
 *
 * Source: GET /api/v1/retention/policies per §5.2.6
 */

// ── SWR Fetcher ───────────────────────────────────────────────────────

const fetcher = async (url: string): Promise<any> => {
  const response = await api.get(url);
  return response.data;
};

// ── Retention Policies Hook ───────────────────────────────────────────

/**
 * useRetentionPolicies — Fetches retention policies.
 *
 * Admin-only. No polling (on-demand via mutate).
 * Source: GET /api/v1/retention/policies per §10.4
 *
 * @returns Retention policies, loading/error state, mutator
 */
export function useRetentionPolicies(): {
  policies: RetentionPolicy[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: KeyedMutator<any>;
} {
  const config: SWRConfiguration = {
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
  };

  const { data, error, isLoading, mutate } = useSWR(
    "/api/v1/retention/policies",
    fetcher,
    config
  );

  return {
    policies: data?.policies ?? data?.items ?? data,
    isLoading,
    error,
    mutate,
  };
}

// ── Retention Report Hook ─────────────────────────────────────────────

/**
 * useRetentionReport — Fetches upcoming migrations and orphan assets.
 *
 * Admin-only. Polls every 120 seconds.
 * Source: GET /api/v1/retention/report?include=migrations,orphans
 *
 * @param enabled - Whether to fetch (false for non-admin users)
 * @returns Migrations, orphan assets, loading state
 */
export function useRetentionReport(enabled: boolean): {
  migrations: TierMigration[] | undefined;
  orphans: OrphanAsset[] | undefined;
  isLoading: boolean;
} {
  const config: SWRConfiguration = {
    refreshInterval: 120_000,
    dedupingInterval: 60_000,
  };

  const { data, isLoading } = useSWR(
    enabled
      ? "/api/v1/retention/report?include=migrations,orphans"
      : null,
    fetcher,
    config
  );

  return {
    migrations: data?.upcoming_migrations ?? data?.migrations,
    orphans: data?.orphan_assets ?? data?.orphans,
    isLoading,
  };
}
