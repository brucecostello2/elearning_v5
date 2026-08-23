"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import {
  useStorageAnalytics,
  useStorageQuotas,
  useRetentionReport,
} from "@/hooks/useMonitoring";
import StorageTierChart from "@/components/monitoring/StorageTierChart";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  StorageTier,
  StorageTierData,
  QuotaEntry,
  TierMigration,
  OrphanAsset,
} from "@/types/monitoring";

/**
 * §8.2.6 Storage Analytics
 *
 * Comprehensive storage monitoring page with:
 * - Tier usage breakdown: hot/warm/cold/archive
 *   - Used vs allocated capacity per tier
 *   - Asset count and total size per tier
 * - Deduplication savings (estimated %)
 * - Quota utilization per user (top 10 consumers) — admin only
 * - Upcoming tier migrations: assets due to transition in next 7 days
 * - Orphan asset report: unreferenced SeaweedFS files
 *
 * Data sources:
 *   - GET /api/v1/retention/report — tier distribution, migrations, orphans
 *   - GET /api/v1/quotas/{entity_type}/{entity_id} — quota usage
 *   - PUT /api/v1/retention/policies/{id} — update retention policy (admin)
 *
 * RBAC per Table 8-3:
 *   - admin: full access (all tiers, all users, orphan report)
 *   - operator: own quota only
 *   - viewer: no access (redirected)
 */

/** Storage tier definitions per §10 Digital Asset Management */
const STORAGE_TIERS: { id: StorageTier; label: string; color: string; description: string }[] = [
  {
    id: "HOT",
    label: "Hot",
    color: "#EF4444",
    description: "Active projects — fast SSD access",
  },
  {
    id: "WARM",
    label: "Warm",
    color: "#F59E0B",
    description: "Recent projects — HDD, 30–90 days old",
  },
  {
    id: "COLD",
    label: "Cold",
    color: "#3B82F6",
    description: "Archived — NAS, 90–365 days old",
  },
  {
    id: "ARCHIVE",
    label: "Archive",
    color: "#6B7280",
    description: "Long-term — compressed NAS, 365+ days",
  },
];

export default function StorageAnalyticsPage(): React.ReactElement | null {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role === "viewer") {
      router.push("/");
    }
  }, [user, router]);

  // ── State ───────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<
    "overview" | "quotas" | "migrations" | "orphans"
  >("overview");

  // ── Data Fetching ───────────────────────────────────────────────────
  /**
   * useStorageAnalytics fetches tier breakdown and dedup savings.
   * Polling interval: 60 seconds.
   */
  const {
    tierData,
    dedupSavings,
    dedupAvailable,
    dedupReason,
    totalUsed,
    totalAllocated,
    allocationAvailable,
    allocationReason,
    totalAssets,
    isLoading: storageLoading,
    error: storageError,
  } = useStorageAnalytics();

  /**
   * useStorageQuotas fetches per-user quota utilization.
   * Admin-only data. Polling interval: 120 seconds.
   */
  const {
    quotas,
    isLoading: quotasLoading,
    noQuotaData,
  } = useStorageQuotas(user?.role === "admin");

  /**
   * useRetentionReport fetches upcoming tier migrations and orphan assets.
   * Polling interval: 120 seconds.
   */
  const {
    migrations,
    orphans,
    isLoading: retentionLoading,
  } = useRetentionReport(user?.role === "admin");

  // ── Computed Values ─────────────────────────────────────────────────

  /**
   * Format bytes to human-readable string.
   */
  const formatBytes = useCallback((bytes: number): string => {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
  }, []);

  /**
   * Usage percentage for total storage, or null when there is no denominator.
   *
   * WP-23: this returned 0 when totalAllocated was missing, and the header
   * rendered "0%" in a green "healthy" pill. There is no allocation figure
   * anywhere in the system, so 0% was not a low number - it was no number at
   * all, dressed as a reassuring one.
   */
  const totalUsagePercent = useMemo((): number | null => {
    if (!allocationAvailable) return null;
    if (!totalAllocated || totalAllocated === 0) return null;
    return Math.round(((totalUsed || 0) / totalAllocated) * 100);
  }, [totalUsed, totalAllocated, allocationAvailable]);

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600 dark:text-red-400">
            Storage Analytics Error
          </h3>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            An error occurred loading storage analytics. Please refresh.
          </p>
        </div>
      }
    >
      {/* WP-23: was `min-h-screen` (100vh). The monitoring layout already
          reserves the 3.5rem sticky global header via
          `flex min-h-[calc(100vh-3.5rem)]`, so a 100vh child overflowed its
          scroll container by exactly the header height and pushed this page's
          own <h1> under it. min-h-full fills the container instead of
          re-adding the header's height. */}
      <div className="min-h-full bg-gray-50 dark:bg-gray-950">
        {/* ── Page Header ─────────────────────────────────────────── */}
        <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Storage Analytics
              </h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                §8.2.6 — Tier usage, deduplication, quotas, migrations, orphan
                report
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Total:{" "}
                <strong className="text-gray-900 dark:text-gray-100">
                  {typeof totalUsed === "number" ? formatBytes(totalUsed) : "—"}
                </strong>
                {typeof totalAssets === "number" && (
                  <> across {totalAssets.toLocaleString()} assets</>
                )}
              </span>
              {/* The Used/Allocated pill is rendered only when an allocation
                  figure exists. It never has: see allocationReason. Showing
                  "0%" in a green pill asserted headroom nobody had measured. */}
              {totalUsagePercent !== null ? (
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded-full
                    text-xs font-medium ${
                      totalUsagePercent > 90
                        ? "bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-300"
                        : totalUsagePercent > 75
                        ? "bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-300"
                        : "bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-300"
                    }`}
                >
                  {totalUsagePercent}%
                </span>
              ) : (
                <span
                  title={allocationReason}
                  className="inline-flex items-center px-2 py-0.5 rounded-full text-xs
                    font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                >
                  no capacity target
                </span>
              )}
            </div>
          </div>
        </header>

        {/* ── Tab Navigation ──────────────────────────────────────── */}
        <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6">
          <nav className="flex gap-6" aria-label="Storage tabs">
            {[
              { id: "overview" as const, label: "Overview" },
              ...(user?.role === "admin"
                ? [
                    { id: "quotas" as const, label: "Quotas" },
                    { id: "migrations" as const, label: "Migrations" },
                    { id: "orphans" as const, label: "Orphan Assets" },
                  ]
                : []),
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-blue-600 text-blue-600 dark:text-blue-400"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="px-6 py-6">
          {/* ── Overview Tab ──────────────────────────────────────── */}
          {activeTab === "overview" && (
            <>
              {storageLoading ? (
                <div className="flex justify-center py-12">
                  <LoadingSpinner size="lg" />
                </div>
              ) : storageError ? (
                <div className="bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4">
                  <p className="text-sm text-red-700 dark:text-red-300">
                    Failed to load storage data.
                  </p>
                </div>
              ) : (
                <>
                  {/* Tier Pie Charts */}
                  {tierData && (
                    <StorageTierChart
                      tiers={STORAGE_TIERS}
                      tierData={tierData}
                      formatBytes={formatBytes}
                    />
                  )}

                  {/* Dedup Savings */}
                  <div className="mt-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                      Deduplication Savings
                    </h2>
                    {/* WP-23: these three tiles read `?? 0` and so displayed
                        "0% saved / 0 B / 0 duplicates" for a subsystem that has
                        never run. The database says otherwise -- 45 assets carry
                        43 distinct content_hash values -- so "0 duplicates" was
                        not merely unmeasured, it was wrong. Until something
                        computes it (P2.4), the honest answer is that there is no
                        figure. */}
                    {dedupAvailable && dedupSavings ? (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="text-center">
                          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            Estimated Savings
                          </p>
                          <p className="mt-1 text-3xl font-bold text-green-600 dark:text-green-400">
                            {dedupSavings.percent}%
                          </p>
                        </div>
                        <div className="text-center">
                          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            Space Saved
                          </p>
                          <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {formatBytes(dedupSavings.bytes_saved)}
                          </p>
                        </div>
                        <div className="text-center">
                          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            Duplicate Assets
                          </p>
                          <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {dedupSavings.duplicate_count}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed border-gray-300
                        dark:border-gray-700 px-4 py-6 text-center">
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                          Not available
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 max-w-2xl mx-auto">
                          {dedupReason}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Per-Tier Detail Table */}
                  <div className="mt-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
                    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800">
                      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Tier Breakdown
                      </h2>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                        <thead className="bg-gray-50 dark:bg-gray-950">
                          <tr>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                              Tier
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                              Used
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                              Allocated
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                              Usage %
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                              Assets
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                          {STORAGE_TIERS.map((tier) => {
                            const data = tierData?.find(
                              (t: StorageTierData) => t.tier === tier.id
                            );
                            // WP-23: a tier with no allocation figure has no
                            // usage percentage. This used to fall through to 0,
                            // so an unmeasured tier and a genuinely empty one
                            // were indistinguishable. null keeps them apart.
                            const usagePercent: number | null =
                              data && (data.allocated ?? 0) > 0
                                ? Math.round(
                                    (data.used! / data.allocated!) * 100
                                  )
                                : null;
                            // A tier absent from the API response was never
                            // reported on, which is not the same as "0 bytes".
                            const tierObserved = data !== undefined;

                            return (
                              <tr key={tier.id}>
                                <td className="px-4 py-2">
                                  <div className="flex items-center gap-2">
                                    <div
                                      className="w-3 h-3 rounded-sm"
                                      style={{
                                        backgroundColor: tier.color,
                                      }}
                                    />
                                    <div>
                                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                        {tier.label}
                                      </p>
                                      <p className="text-xs text-gray-500 dark:text-gray-400">
                                        {tier.description}
                                      </p>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-100 font-mono">
                                  {tierObserved ? (
                                    formatBytes(data!.used ?? 0)
                                  ) : (
                                    <span className="text-gray-400 dark:text-gray-500">
                                      no assets
                                    </span>
                                  )}
                                </td>
                                <td
                                  className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 font-mono"
                                  title={allocationReason}
                                >
                                  {/* Never 0 B: no capacity is modelled at all. */}
                                  <span className="text-gray-400 dark:text-gray-500 font-sans">
                                    not modelled
                                  </span>
                                </td>
                                <td className="px-4 py-2">
                                  {usagePercent !== null ? (
                                    <div className="flex items-center gap-2">
                                      <div className="w-24 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                        <div
                                          className={`h-2 rounded-full ${
                                            usagePercent > 90
                                              ? "bg-red-500"
                                              : usagePercent > 75
                                              ? "bg-amber-500"
                                              : "bg-green-500"
                                          }`}
                                          style={{
                                            width: `${Math.min(usagePercent, 100)}%`,
                                          }}
                                        />
                                      </div>
                                      <span className="text-xs text-gray-600 dark:text-gray-400 font-mono">
                                        {usagePercent}%
                                      </span>
                                    </div>
                                  ) : (
                                    /* A 0%-full green bar reads as "plenty of
                                       room". There is no denominator, so there
                                       is no bar. */
                                    <span
                                      className="text-xs text-gray-400 dark:text-gray-500"
                                      title={allocationReason}
                                    >
                                      —
                                    </span>
                                  )}
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">
                                  {tierObserved
                                    ? (data!.asset_count ?? 0).toLocaleString()
                                    : "0"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </>
          )}

          {/* ── Quotas Tab (Admin Only) ────────────────────────────── */}
          {activeTab === "quotas" && user?.role === "admin" && (
            <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                  Quota Utilization — Top Consumers
                </h2>
              </div>
              {quotasLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : noQuotaData ? (
                /* WP-40 Task 4: `storage_quotas` is empty, so every lookup
                   404s. Saying so beats a table of 0 B / 0 B rows, which
                   reads as a real zero-byte quota per user. */
                <div className="p-6 text-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    No quota data.
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    No storage quota is recorded for any user. Quotas are set
                    per entity via <code>PUT /api/v1/quotas/user/&#123;id&#125;</code>;
                    nothing in the pipeline creates them automatically.
                  </p>
                </div>
              ) : quotas && quotas.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                    <thead className="bg-gray-50 dark:bg-gray-950">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          User
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Used
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Quota
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Usage
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Status
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {quotas.map((q: QuotaEntry) => {
                        const percent =
                          q.quota_bytes > 0
                            ? Math.round(
                                (q.used_bytes / q.quota_bytes) * 100
                              )
                            : 0;

                        if (!q.has_quota) {
                          return (
                            <tr key={q.user_id}>
                              <td className="px-4 py-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                                {q.username}
                              </td>
                              <td
                                className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 italic"
                                colSpan={4}
                              >
                                no quota data
                              </td>
                            </tr>
                          );
                        }

                        return (
                          <tr key={q.user_id}>
                            <td className="px-4 py-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                              {q.username}
                            </td>
                            <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 font-mono">
                              {formatBytes(q.used_bytes)}
                            </td>
                            <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 font-mono">
                              {formatBytes(q.quota_bytes)}
                            </td>
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-2">
                                <div className="w-24 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                  <div
                                    className={`h-2 rounded-full ${
                                      percent > 90
                                        ? "bg-red-500"
                                        : percent > 80
                                        ? "bg-amber-500"
                                        : "bg-green-500"
                                    }`}
                                    style={{
                                      width: `${Math.min(percent, 100)}%`,
                                    }}
                                  />
                                </div>
                                <span className="text-xs text-gray-600 dark:text-gray-400 font-mono">
                                  {percent}%
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-2">
                              <span
                                className={`inline-flex items-center px-2 py-0.5
                                  rounded-full text-xs font-medium ${
                                    percent > 90
                                      ? "bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-300"
                                      : percent > 80
                                      ? "bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-300"
                                      : "bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-300"
                                  }`}
                              >
                                {percent > 90
                                  ? "Critical"
                                  : percent > 80
                                  ? "Warning"
                                  : "OK"}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-6 text-sm text-gray-500 dark:text-gray-400 text-center">
                  No quota data available.
                </p>
              )}
            </div>
          )}

          {/* ── Migrations Tab (Admin Only) ────────────────────────── */}
          {activeTab === "migrations" && user?.role === "admin" && (
            <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                  Upcoming Tier Migrations — Next 7 Days
                </h2>
              </div>
              {retentionLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : migrations && migrations.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                    <thead className="bg-gray-50 dark:bg-gray-950">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Asset
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Project
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Current Tier
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Target Tier
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Size
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Scheduled
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {migrations.map((m: TierMigration) => (
                        <tr key={m.asset_id}>
                          <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-100 font-mono">
                            {m.asset_id.slice(0, 12)}…
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">
                            {m.project_name}
                          </td>
                          <td className="px-4 py-2">
                            <span
                              className="inline-flex items-center px-2 py-0.5
                                rounded text-xs font-medium"
                              style={{
                                backgroundColor:
                                  STORAGE_TIERS.find(
                                    (t) => t.id === m.current_tier
                                  )?.color + "20",
                                color:
                                  STORAGE_TIERS.find(
                                    (t) => t.id === m.current_tier
                                  )?.color,
                              }}
                            >
                              {m.current_tier}
                            </span>
                          </td>
                          <td className="px-4 py-2">
                            <span
                              className="inline-flex items-center px-2 py-0.5
                                rounded text-xs font-medium"
                              style={{
                                backgroundColor:
                                  STORAGE_TIERS.find(
                                    (t) => t.id === m.target_tier
                                  )?.color + "20",
                                color:
                                  STORAGE_TIERS.find(
                                    (t) => t.id === m.target_tier
                                  )?.color,
                              }}
                            >
                              {m.target_tier}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 font-mono">
                            {formatBytes(m.size_bytes)}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {new Date(m.scheduled_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-6 text-sm text-gray-500 dark:text-gray-400 text-center">
                  No upcoming tier migrations.
                </p>
              )}
            </div>
          )}

          {/* ── Orphan Assets Tab (Admin Only) ─────────────────────── */}
          {activeTab === "orphans" && user?.role === "admin" && (
            <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                  Orphan Asset Report — Unreferenced SeaweedFS Files
                </h2>
              </div>
              {retentionLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : orphans && orphans.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                    <thead className="bg-gray-50 dark:bg-gray-950">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          SeaweedFS FID
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Path
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Size
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Last Modified
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Reason
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {orphans.map((o: OrphanAsset) => (
                        <tr key={o.seaweedfs_fid}>
                          <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-100 font-mono">
                            {o.seaweedfs_fid}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 font-mono truncate max-w-[200px]">
                            {o.path}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 font-mono">
                            {formatBytes(o.size_bytes)}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {new Date(o.last_modified).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {o.reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-6 text-sm text-gray-500 dark:text-gray-400 text-center">
                  No orphan assets detected. Storage is clean.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}
