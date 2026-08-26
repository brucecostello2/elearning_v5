"use client";

import React, { useState, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useRetentionPolicies, useRetentionReport } from "@/hooks/useRetention";
import { api } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import { formatBytes } from "@/lib/media";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  RetentionPolicy,
  RetentionPolicyUpdate,
  StorageTier,
} from "@/types/monitoring";

/**
 * §10.4 Retention Policy Management
 *
 * Admin-only page for managing storage tier lifecycle policies with:
 * - Policy table (source tier, target tier, threshold days, auto-execute)
 * - Tier transition lifecycle diagram
 * - Upcoming migrations list (assets moving tiers in next 7 days)
 * - Orphan cleanup status and manual trigger
 *
 * Data sources:
 *   - GET  /api/v1/retention/policies        — All retention policies
 *   - PUT  /api/v1/retention/policies/{id}    — Update policy thresholds
 *   - POST /api/v1/retention/run              — Trigger manual cleanup
 *   - GET  /api/v1/retention/report           — Tier stats + migrations
 *
 * RBAC: Admin only (per §8.3 Table 8-3)
 */

const TIER_LABELS: Partial<Record<StorageTier | "delete", string>> = {
  hot: "Hot (SSD)",
  warm: "Warm (HDD)",
  cold: "Cold (NAS)",
  archived: "Archive (Compressed)",
  delete: "Delete",
};

const TIER_COLORS: Partial<Record<StorageTier | "delete", string>> = {
  hot: "text-red-400 bg-red-900/20",
  warm: "text-orange-400 bg-orange-900/20",
  cold: "text-blue-400 bg-blue-900/20",
  archived: "text-purple-400 bg-purple-900/20",
  delete: "text-gray-400 bg-gray-800",
};

const TIER_THRESHOLDS: { tier: StorageTier; days: string; description: string }[] = [
  { tier: "hot", days: "0–30 days", description: "Fast SSD storage for active projects" },
  { tier: "warm", days: "31–90 days", description: "Standard HDD for recent projects" },
  { tier: "cold", days: "91–365 days", description: "Network attached storage for archival" },
  { tier: "archived", days: "366+ days", description: "Compressed NAS for long-term retention" },
];

export default function RetentionPage(): React.ReactElement {
  const { user } = useAuth();

  /* ── Data fetching ────────────────────────────────────────────────── */
  const { policies, isLoading: policiesLoading, error: policiesError, mutate } = useRetentionPolicies();
  const { migrations, orphans, isLoading: reportLoading } = useRetentionReport(user?.role === "admin");

  /* ── Edit modal state ─────────────────────────────────────────────── */
  const [editingPolicy, setEditingPolicy] = useState<RetentionPolicy | null>(null);
  /* WP-57 Task 5. Was `editThreshold` / `editAutoExecute`, PUT as
     {threshold_days, auto_execute} to an endpoint whose update schema declares
     NEITHER - so FastAPI dropped both and the form reported success having
     saved nothing. These are the fields the API actually accepts. */
  const [editHotDays, setEditHotDays] = useState<string>("");
  const [editWarmDays, setEditWarmDays] = useState<string>("");
  const [editColdDays, setEditColdDays] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [runningCleanup, setRunningCleanup] = useState(false);

  /* ── Feedback state ───────────────────────────────────────────────── */
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  /* ── Actions ──────────────────────────────────────────────────────── */
  const openEdit = useCallback((policy: RetentionPolicy) => {
    setEditingPolicy(policy);
    setEditHotDays(policy.hot_days != null ? String(policy.hot_days) : "");
    setEditWarmDays(policy.warm_days != null ? String(policy.warm_days) : "");
    setEditColdDays(policy.cold_days != null ? String(policy.cold_days) : "");
    setActionMessage(null);
  }, []);

  const handleSavePolicy = useCallback(async () => {
    if (!editingPolicy) return;
    setSaving(true);
    setActionMessage(null);
    try {
      /* Only send what the operator actually filled in: the API validates
         each field's range, and sending an empty string would be a 422. */
      const payload: RetentionPolicyUpdate = {};
      if (editHotDays.trim()) payload.hot_days = Number(editHotDays);
      if (editWarmDays.trim()) payload.warm_days = Number(editWarmDays);
      if (editColdDays.trim()) payload.cold_days = Number(editColdDays);
      await api.put(`/api/v1/retention/policies/${editingPolicy.id}`, payload);
      setActionMessage({ type: "success", text: `Policy "${editingPolicy.name}" updated successfully.` });
      setEditingPolicy(null);
      mutate();
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err?.response?.data?.detail || err?.message || "Failed to update policy.",
      });
    } finally {
      setSaving(false);
    }
  }, [editingPolicy, editHotDays, editWarmDays, editColdDays, mutate]);

  const handleRunCleanup = useCallback(async () => {
    setRunningCleanup(true);
    setActionMessage(null);
    try {
      await api.post("/api/v1/retention/run");
      setActionMessage({ type: "success", text: "Orphan cleanup initiated successfully." });
      mutate();
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err?.response?.data?.detail || err?.message || "Failed to trigger cleanup.",
      });
    } finally {
      setRunningCleanup(false);
    }
  }, [mutate]);

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Page header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Retention Policies</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            §10.4 — Storage tier lifecycle rules and asset retention management
          </p>
        </div>

        {/* Action feedback */}
        {actionMessage && (
          <div
            className={`mb-4 rounded-lg px-4 py-3 text-sm ${
              actionMessage.type === "success"
                ? "border border-green-200 dark:border-green-800 bg-green-100 dark:bg-green-900/20 text-green-600 dark:text-green-400"
                : "border border-red-200 dark:border-red-800 bg-red-100 dark:bg-red-900/20 text-red-600 dark:text-red-400"
            }`}
          >
            {actionMessage.text}
            <button onClick={() => setActionMessage(null)} className="ml-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">✕</button>
          </div>
        )}

        {/* Tier Lifecycle Diagram */}
        <div className="mb-6 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Storage Tier Lifecycle
          </h2>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {TIER_THRESHOLDS.map((item, idx) => (
              <React.Fragment key={item.tier}>
                <div className={`rounded-lg px-4 py-3 text-center ${TIER_COLORS[item.tier]}`}>
                  <p className="text-sm font-semibold">{TIER_LABELS[item.tier]}</p>
                  <p className="text-xs opacity-75">{item.days}</p>
                </div>
                {idx < TIER_THRESHOLDS.length - 1 && (
                  <svg className="h-5 w-5 text-gray-600 dark:text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                  </svg>
                )}
              </React.Fragment>
            ))}
            <svg className="h-5 w-5 text-gray-600 dark:text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
            </svg>
            <div className={`rounded-lg px-4 py-3 text-center ${TIER_COLORS.delete}`}>
              <p className="text-sm font-semibold">Delete</p>
              <p className="text-xs opacity-75">Per policy</p>
            </div>
          </div>
        </div>

        {/* Policy Table */}
        <div className="mb-8">
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Active Policies</h2>
          {policiesLoading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner size="lg" label="Loading retention policies..." />
            </div>
          ) : policiesError ? (
            <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-100 dark:bg-red-900/20 p-6 text-center text-red-600 dark:text-red-400">
              <p>Failed to load retention policies</p>
              <button onClick={() => mutate()} className="mt-2 rounded bg-gray-100 dark:bg-gray-800 px-3 py-1 text-sm hover:bg-gray-200 dark:hover:bg-gray-700">
                Retry
              </button>
            </div>
          ) : !policies || policies.length === 0 ? (
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-8 text-center">
              <p className="text-gray-500 dark:text-gray-400">No retention policies configured.</p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Policies will appear here once configured via the API.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/50 text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  <tr>
                    {/* WP-57 Task 5. Every column but the first used to read a
                        field the API has never sent - source_tier, target_tier,
                        threshold_days, auto_execute, last_run_at,
                        assets_affected. A retention policy on this API is a set
                        of PER-TIER DURATIONS, so that is what is shown. */}
                    <th className="px-4 py-3">Policy Name</th>
                    <th className="px-4 py-3">Applies To</th>
                    <th className="px-4 py-3">Hot</th>
                    <th className="px-4 py-3">Warm</th>
                    <th className="px-4 py-3">Cold</th>
                    <th className="px-4 py-3">Archive</th>
                    <th className="px-4 py-3">Delete After</th>
                    <th className="px-4 py-3">Default</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {policies.map((policy: RetentionPolicy) => (
                    <tr key={policy.id} className="hover:bg-gray-100 dark:hover:bg-gray-800/50">
                      <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-800 dark:text-gray-200">
                        {policy.name}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-500 dark:text-gray-400">
                        {policy.applies_to}
                      </td>
                      {/* WP-57 Task 5: null is "this policy does not define
                          that stage", which is different from 0 days. */}
                      {([
                        policy.hot_days,
                        policy.warm_days,
                        policy.cold_days,
                        policy.archive_days,
                        policy.delete_after_days,
                      ] as (number | null)[]).map((days, i) => (
                        <td
                          key={i}
                          className="whitespace-nowrap px-4 py-3 text-gray-700 dark:text-gray-300"
                        >
                          {typeof days === "number" ? `${days} days` : "not set"}
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          policy.is_default
                            ? "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400"
                            : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                        }`}>
                          {policy.is_default ? "Default" : "—"}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <button
                          onClick={() => openEdit(policy)}
                          className="rounded px-2 py-1 text-xs font-medium text-ivgs-600 dark:text-ivgs-400 transition-colors hover:bg-ivgs-600/20 hover:text-ivgs-800 dark:hover:text-ivgs-300"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Upcoming Migrations */}
        <div className="mb-8">
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Upcoming Migrations (7 days)</h2>
          {reportLoading ? (
            <LoadingSpinner label="Loading migrations..." />
          ) : !migrations || migrations.length === 0 ? (
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-gray-500 dark:text-gray-400">
              No upcoming tier migrations scheduled.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/50 text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  <tr>
                    <th className="px-4 py-3">Asset ID</th>
                    {/* WP-57 Task 3: dropped — the API has never sent a
                        project name on this row, so it rendered blank. */}
                    <th className="px-4 py-3">Current Tier</th>
                    <th className="px-4 py-3">Next Tier</th>
                    <th className="px-4 py-3">Size</th>
                    <th className="px-4 py-3">Due</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {migrations.slice(0, 10).map((m) => (
                    <tr key={m.asset_id} className="hover:bg-gray-100 dark:hover:bg-gray-800/50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700 dark:text-gray-300">
                        {m.asset_id.substring(0, 12)}…
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TIER_COLORS[m.current_tier]}`}>
                          {m.current_tier}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TIER_COLORS[m.next_tier]}`}>
                          {m.next_tier}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {formatBytes(m.file_size_bytes)}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {m.days_until_migration <= 0
                          ? "overdue"
                          : `in ${m.days_until_migration} day${m.days_until_migration === 1 ? "" : "s"}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Orphan Cleanup */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Orphan Cleanup</h2>
            <button
              onClick={handleRunCleanup}
              disabled={runningCleanup}
              className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              {runningCleanup ? "Running..." : "Run Cleanup Now"}
            </button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {reportLoading ? "..." : orphans?.length ?? 0}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Quarantined Orphans</p>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                {reportLoading
                  ? "..."
                  : orphans
                    ? `${(orphans.reduce((acc, o) => acc + o.size_bytes, 0) / (1024 * 1024)).toFixed(1)} MB`
                    : "0 MB"}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Reclaimable Space</p>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-gray-500 dark:text-gray-400">§10.6</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">OrphanCleanupService</p>
            </div>
          </div>
        </div>

        {/* Edit Policy Modal */}
        {editingPolicy && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="mx-4 w-full max-w-md rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Edit Policy: {editingPolicy.name}
              </h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Applies to {editingPolicy.applies_to}. Days are how long an asset
                stays in each tier before moving on.
              </p>

              {/* WP-57 Task 5. This modal used to offer a single "Threshold
                  (days)" and an "Auto-execute transitions" checkbox. Neither
                  exists on this API: the PUT dropped both silently and reported
                  success. These three are the fields RetentionPolicyUpdate
                  declares and validates. Blank means "leave unchanged". */}
              {([
                ["hot", "Hot (days)", editHotDays, setEditHotDays] as const,
                ["warm", "Warm (days)", editWarmDays, setEditWarmDays] as const,
                ["cold", "Cold (days)", editColdDays, setEditColdDays] as const,
              ]).map(([key, label, value, setter]) => (
                <div className="mt-4" key={key}>
                  <label
                    htmlFor={`policy-${key}`}
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    {label}
                  </label>
                  <input
                    id={`policy-${key}`}
                    type="number"
                    min={1}
                    max={3650}
                    value={value}
                    placeholder="leave blank to keep"
                    onChange={(e) => setter(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-800 dark:text-gray-200 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500"
                  />
                </div>
              ))}

              <p className="mt-4 rounded-md border border-amber-500/60 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                Saving updates the policy record. It does not move any asset:
                nothing has ever migrated a tier on this system (WP-57 D-1).
              </p>

              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setEditingPolicy(null)}
                  className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSavePolicy}
                  disabled={saving}
                  className="rounded-lg bg-ivgs-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ivgs-500 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
