"use client";

import React, { useState, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useRetentionPolicies, useRetentionReport } from "@/hooks/useRetention";
import { api } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { RetentionPolicy, StorageTier } from "@/types/monitoring";

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

const TIER_LABELS: Record<StorageTier | "delete", string> = {
  hot: "Hot (SSD)",
  warm: "Warm (HDD)",
  cold: "Cold (NAS)",
  archive: "Archive (Compressed)",
  delete: "Delete",
};

const TIER_COLORS: Record<StorageTier | "delete", string> = {
  hot: "text-red-400 bg-red-900/20",
  warm: "text-orange-400 bg-orange-900/20",
  cold: "text-blue-400 bg-blue-900/20",
  archive: "text-purple-400 bg-purple-900/20",
  delete: "text-gray-400 bg-gray-800",
};

const TIER_THRESHOLDS: { tier: StorageTier; days: string; description: string }[] = [
  { tier: "hot", days: "0–30 days", description: "Fast SSD storage for active projects" },
  { tier: "warm", days: "31–90 days", description: "Standard HDD for recent projects" },
  { tier: "cold", days: "91–365 days", description: "Network attached storage for archival" },
  { tier: "archive", days: "366+ days", description: "Compressed NAS for long-term retention" },
];

export default function RetentionPage(): React.ReactElement {
  const { user } = useAuth();

  /* ── Data fetching ────────────────────────────────────────────────── */
  const { policies, isLoading: policiesLoading, error: policiesError, mutate } = useRetentionPolicies();
  const { migrations, orphans, isLoading: reportLoading } = useRetentionReport(user?.role === "admin");

  /* ── Edit modal state ─────────────────────────────────────────────── */
  const [editingPolicy, setEditingPolicy] = useState<RetentionPolicy | null>(null);
  const [editThreshold, setEditThreshold] = useState(0);
  const [editAutoExecute, setEditAutoExecute] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningCleanup, setRunningCleanup] = useState(false);

  /* ── Feedback state ───────────────────────────────────────────────── */
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  /* ── Actions ──────────────────────────────────────────────────────── */
  const openEdit = useCallback((policy: RetentionPolicy) => {
    setEditingPolicy(policy);
    setEditThreshold(policy.threshold_days);
    setEditAutoExecute(policy.auto_execute);
    setActionMessage(null);
  }, []);

  const handleSavePolicy = useCallback(async () => {
    if (!editingPolicy) return;
    setSaving(true);
    setActionMessage(null);
    try {
      await api.put(`/api/v1/retention/policies/${editingPolicy.id}`, {
        threshold_days: editThreshold,
        auto_execute: editAutoExecute,
      });
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
  }, [editingPolicy, editThreshold, editAutoExecute, mutate]);

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
          <h1 className="text-2xl font-bold text-white">Retention Policies</h1>
          <p className="mt-1 text-sm text-gray-400">
            §10.4 — Storage tier lifecycle rules and asset retention management
          </p>
        </div>

        {/* Action feedback */}
        {actionMessage && (
          <div
            className={`mb-4 rounded-lg px-4 py-3 text-sm ${
              actionMessage.type === "success"
                ? "border border-green-800 bg-green-900/20 text-green-400"
                : "border border-red-800 bg-red-900/20 text-red-400"
            }`}
          >
            {actionMessage.text}
            <button onClick={() => setActionMessage(null)} className="ml-2 text-gray-500 hover:text-gray-300">✕</button>
          </div>
        )}

        {/* Tier Lifecycle Diagram */}
        <div className="mb-6 rounded-lg border border-gray-800 bg-gray-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-400">
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
                  <svg className="h-5 w-5 text-gray-600" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                  </svg>
                )}
              </React.Fragment>
            ))}
            <svg className="h-5 w-5 text-gray-600" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
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
          <h2 className="mb-4 text-lg font-semibold text-white">Active Policies</h2>
          {policiesLoading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner size="lg" label="Loading retention policies..." />
            </div>
          ) : policiesError ? (
            <div className="rounded-lg border border-red-800 bg-red-900/20 p-6 text-center text-red-400">
              <p>Failed to load retention policies</p>
              <button onClick={() => mutate()} className="mt-2 rounded bg-gray-800 px-3 py-1 text-sm hover:bg-gray-700">
                Retry
              </button>
            </div>
          ) : !policies || policies.length === 0 ? (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-8 text-center">
              <p className="text-gray-400">No retention policies configured.</p>
              <p className="mt-1 text-sm text-gray-500">
                Policies will appear here once configured via the API.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-800 bg-gray-900/50 text-xs uppercase tracking-wider text-gray-400">
                  <tr>
                    <th className="px-4 py-3">Policy Name</th>
                    <th className="px-4 py-3">Source Tier</th>
                    <th className="px-4 py-3">Target Tier</th>
                    <th className="px-4 py-3">Threshold</th>
                    <th className="px-4 py-3">Auto-Execute</th>
                    <th className="px-4 py-3">Last Run</th>
                    <th className="px-4 py-3">Assets</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {policies.map((policy: RetentionPolicy) => (
                    <tr key={policy.id} className="hover:bg-gray-800/50">
                      <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-200">
                        {policy.name}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TIER_COLORS[policy.source_tier]}`}>
                          {TIER_LABELS[policy.source_tier]}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TIER_COLORS[policy.target_tier]}`}>
                          {TIER_LABELS[policy.target_tier]}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-300">
                        {policy.threshold_days} days
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          policy.auto_execute
                            ? "bg-green-900/30 text-green-400"
                            : "bg-gray-800 text-gray-400"
                        }`}>
                          {policy.auto_execute ? "Enabled" : "Disabled"}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-400">
                        {policy.last_run_at
                          ? new Date(policy.last_run_at).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "Never"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-400">
                        {policy.assets_affected}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <button
                          onClick={() => openEdit(policy)}
                          className="rounded px-2 py-1 text-xs font-medium text-ivgs-400 transition-colors hover:bg-ivgs-600/20 hover:text-ivgs-300"
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
          <h2 className="mb-4 text-lg font-semibold text-white">Upcoming Migrations (7 days)</h2>
          {reportLoading ? (
            <LoadingSpinner label="Loading migrations..." />
          ) : !migrations || migrations.length === 0 ? (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-gray-400">
              No upcoming tier migrations scheduled.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-800 bg-gray-900/50 text-xs uppercase tracking-wider text-gray-400">
                  <tr>
                    <th className="px-4 py-3">Asset ID</th>
                    <th className="px-4 py-3">Project</th>
                    <th className="px-4 py-3">Current Tier</th>
                    <th className="px-4 py-3">Target Tier</th>
                    <th className="px-4 py-3">Size</th>
                    <th className="px-4 py-3">Scheduled</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {migrations.slice(0, 10).map((m) => (
                    <tr key={m.asset_id} className="hover:bg-gray-800/50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-300">
                        {m.asset_id.substring(0, 12)}…
                      </td>
                      <td className="px-4 py-3 text-gray-300">{m.project_name}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TIER_COLORS[m.current_tier]}`}>
                          {m.current_tier}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TIER_COLORS[m.target_tier]}`}>
                          {m.target_tier}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {(m.size_bytes / (1024 * 1024)).toFixed(1)} MB
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {new Date(m.scheduled_at).toLocaleDateString()}
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
            <h2 className="text-lg font-semibold text-white">Orphan Cleanup</h2>
            <button
              onClick={handleRunCleanup}
              disabled={runningCleanup}
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 transition-colors hover:bg-gray-700 disabled:opacity-50"
            >
              {runningCleanup ? "Running..." : "Run Cleanup Now"}
            </button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <p className="text-2xl font-bold text-white">
                {reportLoading ? "..." : orphans?.length ?? 0}
              </p>
              <p className="text-xs text-gray-400">Quarantined Orphans</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <p className="text-2xl font-bold text-yellow-400">
                {reportLoading
                  ? "..."
                  : orphans
                    ? `${(orphans.reduce((acc, o) => acc + o.size_bytes, 0) / (1024 * 1024)).toFixed(1)} MB`
                    : "0 MB"}
              </p>
              <p className="text-xs text-gray-400">Reclaimable Space</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <p className="text-2xl font-bold text-gray-400">§10.6</p>
              <p className="text-xs text-gray-400">OrphanCleanupService</p>
            </div>
          </div>
        </div>

        {/* Edit Policy Modal */}
        {editingPolicy && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="mx-4 w-full max-w-md rounded-lg border border-gray-700 bg-gray-900 p-6">
              <h2 className="text-lg font-semibold text-white">
                Edit Policy: {editingPolicy.name}
              </h2>
              <p className="mt-1 text-sm text-gray-400">
                {TIER_LABELS[editingPolicy.source_tier]} → {TIER_LABELS[editingPolicy.target_tier]}
              </p>

              <div className="mt-4">
                <label htmlFor="threshold" className="block text-sm font-medium text-gray-300">
                  Threshold (days)
                </label>
                <input
                  id="threshold"
                  type="number"
                  min={1}
                  max={3650}
                  value={editThreshold}
                  onChange={(e) => setEditThreshold(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500"
                />
              </div>

              <div className="mt-4 flex items-center gap-3">
                <input
                  id="auto-execute"
                  type="checkbox"
                  checked={editAutoExecute}
                  onChange={(e) => setEditAutoExecute(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-700 bg-gray-800 text-ivgs-600 focus:ring-ivgs-500"
                />
                <label htmlFor="auto-execute" className="text-sm text-gray-300">
                  Auto-execute transitions
                </label>
              </div>

              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setEditingPolicy(null)}
                  className="rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
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
