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

export default function StorageAnalyticsPage(): React.ReactElement {
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
    totalUsed,
    totalAllocated,
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
   * Usage percentage for total storage.
   */
  const totalUsagePercent = useMemo(() => {
    if (!totalAllocated || totalAllocated === 0) return 0;
    return Math.round(((totalUsed || 0) / totalAllocated) * 100);
  }, [totalUsed, totalAllocated]);

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600">
            Storage Analytics Error
          </h3>
          <p className="mt-2 text-sm text-gray-600">
            An error occurred loading storage analytics. Please refresh.
          </p>
        </div>
      }
    >
      <div className="min-h-screen bg-gray-50">
        {/* ── Page Header ─────────────────────────────────────────── */}
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                Storage Analytics
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                §8.2.6 — Tier usage, deduplication, quotas, migrations, orphan
                report
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">
                Total:{" "}
                <strong className="text-gray-900">
                  {formatBytes(totalUsed || 0)}
                </strong>{" "}
                / {formatBytes(totalAllocated || 0)}
              </span>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full
                  text-xs font-medium ${
                    totalUsagePercent > 90
                      ? "bg-red-100 text-red-800"
                      : totalUsagePercent > 75
                      ? "bg-amber-100 text-amber-800"
                      : "bg-green-100 text-green-800"
                  }`}
              >
                {totalUsagePercent}%
              </span>
            </div>
          </div>
        </header>

        {/* ── Tab Navigation ──────────────────────────────────────── */}
        <div className="bg-white border-b border-gray-200 px-6">
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
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
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
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <p className="text-sm text-red-700">
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
                  <div className="mt-6 bg-white rounded-lg border border-gray-200 p-6">
                    <h2 className="text-sm font-semibold text-gray-700 mb-3">
                      Deduplication Savings
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div className="text-center">
                        <p className="text-xs text-gray-500 uppercase tracking-wide">
                          Estimated Savings
                        </p>
                        <p className="mt-1 text-3xl font-bold text-green-600">
                          {dedupSavings?.percent ?? 0}%
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500 uppercase tracking-wide">
                          Space Saved
                        </p>
                        <p className="mt-1 text-3xl font-bold text-gray-900">
                          {formatBytes(dedupSavings?.bytes_saved ?? 0)}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500 uppercase tracking-wide">
                          Duplicate Assets
                        </p>
                        <p className="mt-1 text-3xl font-bold text-gray-900">
                          {dedupSavings?.duplicate_count ?? 0}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Per-Tier Detail Table */}
                  <div className="mt-6 bg-white rounded-lg border border-gray-200 overflow-hidden">
                    <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                      <h2 className="text-sm font-semibold text-gray-700">
                        Tier Breakdown
                      </h2>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                              Tier
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                              Used
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                              Allocated
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                              Usage %
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                              Assets
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {STORAGE_TIERS.map((tier) => {
                            const data = tierData?.find(
                              (t: StorageTierData) => t.tier === tier.id
                            );
                            const usagePercent =
                              data && data.allocated > 0
                                ? Math.round(
                                    (data.used / data.allocated) * 100
                                  )
                                : 0;

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
                                      <p className="text-sm font-medium text-gray-900">
                                        {tier.label}
                                      </p>
                                      <p className="text-xs text-gray-500">
                                        {tier.description}
                                      </p>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-900 font-mono">
                                  {formatBytes(data?.used ?? 0)}
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-600 font-mono">
                                  {formatBytes(data?.allocated ?? 0)}
                                </td>
                                <td className="px-4 py-2">
                                  <div className="flex items-center gap-2">
                                    <div className="w-24 bg-gray-200 rounded-full h-2">
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
                                    <span className="text-xs text-gray-600 font-mono">
                                      {usagePercent}%
                                    </span>
                                  </div>
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-600">
                                  {(data?.asset_count ?? 0).toLocaleString()}
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
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h2 className="text-sm font-semibold text-gray-700">
                  Quota Utilization — Top Consumers
                </h2>
              </div>
              {quotasLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : quotas && quotas.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          User
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Used
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Quota
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Usage
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Status
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {quotas.map((q: QuotaEntry) => {
                        const percent =
                          q.quota_bytes > 0
                            ? Math.round(
                                (q.used_bytes / q.quota_bytes) * 100
                              )
                            : 0;

                        return (
                          <tr key={q.user_id}>
                            <td className="px-4 py-2 text-sm font-medium text-gray-900">
                              {q.username}
                            </td>
                            <td className="px-4 py-2 text-sm text-gray-600 font-mono">
                              {formatBytes(q.used_bytes)}
                            </td>
                            <td className="px-4 py-2 text-sm text-gray-600 font-mono">
                              {formatBytes(q.quota_bytes)}
                            </td>
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-2">
                                <div className="w-24 bg-gray-200 rounded-full h-2">
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
                                <span className="text-xs text-gray-600 font-mono">
                                  {percent}%
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-2">
                              <span
                                className={`inline-flex items-center px-2 py-0.5
                                  rounded-full text-xs font-medium ${
                                    percent > 90
                                      ? "bg-red-100 text-red-800"
                                      : percent > 80
                                      ? "bg-amber-100 text-amber-800"
                                      : "bg-green-100 text-green-800"
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
                <p className="p-6 text-sm text-gray-500 text-center">
                  No quota data available.
                </p>
              )}
            </div>
          )}

          {/* ── Migrations Tab (Admin Only) ────────────────────────── */}
          {activeTab === "migrations" && user?.role === "admin" && (
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h2 className="text-sm font-semibold text-gray-700">
                  Upcoming Tier Migrations — Next 7 Days
                </h2>
              </div>
              {retentionLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : migrations && migrations.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Asset
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Project
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Current Tier
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Target Tier
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Size
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Scheduled
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {migrations.map((m: TierMigration) => (
                        <tr key={m.asset_id}>
                          <td className="px-4 py-2 text-sm text-gray-900 font-mono">
                            {m.asset_id.slice(0, 12)}…
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600">
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
                          <td className="px-4 py-2 text-sm text-gray-600 font-mono">
                            {formatBytes(m.size_bytes)}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {new Date(m.scheduled_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-6 text-sm text-gray-500 text-center">
                  No upcoming tier migrations.
                </p>
              )}
            </div>
          )}

          {/* ── Orphan Assets Tab (Admin Only) ─────────────────────── */}
          {activeTab === "orphans" && user?.role === "admin" && (
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h2 className="text-sm font-semibold text-gray-700">
                  Orphan Asset Report — Unreferenced SeaweedFS Files
                </h2>
              </div>
              {retentionLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : orphans && orphans.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          SeaweedFS FID
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Path
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Size
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Last Modified
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Reason
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {orphans.map((o: OrphanAsset) => (
                        <tr key={o.seaweedfs_fid}>
                          <td className="px-4 py-2 text-sm text-gray-900 font-mono">
                            {o.seaweedfs_fid}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600 font-mono truncate max-w-[200px]">
                            {o.path}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-600 font-mono">
                            {formatBytes(o.size_bytes)}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {new Date(o.last_modified).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {o.reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-6 text-sm text-gray-500 text-center">
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
