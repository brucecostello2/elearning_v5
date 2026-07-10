"use client";

import React, { useState, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useBackupRecords } from "@/hooks/useBackups";
import { api } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  BackupRecord,
  BackupType,
  BackupStatus,
} from "@/types/monitoring";

/**
 * §14 Backup and Disaster Recovery Management
 *
 * Admin-only page for managing automated backups with:
 * - Backup records table (type, timestamp, status, size, verification)
 * - Manual backup trigger (POST /api/v1/backup/trigger)
 * - Backup verification (POST /api/v1/backup/{id}/verify)
 * - RTO/RPO information panel
 *
 * Data sources:
 *   - GET  /api/v1/backup/records        — Backup record listing
 *   - POST /api/v1/backup/trigger         — Trigger manual backup
 *   - POST /api/v1/backup/{id}/verify     — Verify backup integrity
 *
 * RBAC: Admin only (per §8.3 Table 8-3)
 */

const BACKUP_TYPE_OPTIONS: { value: BackupType | "ALL"; label: string }[] = [
  { value: "ALL", label: "All Types" },
  { value: "full_database", label: "Full Database" },
  { value: "wal_archive", label: "WAL Archive" },
  { value: "asset_backup", label: "Asset Backup" },
  { value: "config_backup", label: "Config Backup" },
  { value: "vm_snapshot", label: "VM Snapshot" },
];

const STATUS_BADGES: Record<BackupStatus, { bg: string; text: string }> = {
  running: { bg: "bg-blue-900/30", text: "text-blue-400" },
  completed: { bg: "bg-green-900/30", text: "text-green-400" },
  failed: { bg: "bg-red-900/30", text: "text-red-400" },
  verified: { bg: "bg-emerald-900/30", text: "text-emerald-400" },
};

/** Format byte sizes to human-readable */
function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/** Format seconds to human-readable duration */
function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

/** Format ISO timestamp to locale-friendly string */
function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function BackupsPage(): React.ReactElement {
  const { user } = useAuth();

  /* ── Filter & pagination state ────────────────────────────────────── */
  const [typeFilter, setTypeFilter] = useState<BackupType | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const pageSize = 15;

  /* ── Modal state ──────────────────────────────────────────────────── */
  const [showTriggerModal, setShowTriggerModal] = useState(false);
  const [triggerType, setTriggerType] = useState<BackupType>("full_database");
  const [triggering, setTriggering] = useState(false);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  /* ── Feedback state ───────────────────────────────────────────────── */
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  /* ── Data fetching ────────────────────────────────────────────────── */
  const { records, totalCount, isLoading, error, mutate } = useBackupRecords({
    backup_type: typeFilter === "ALL" ? undefined : typeFilter,
    page,
    pageSize,
  });

  const totalPages = totalCount ? Math.ceil(totalCount / pageSize) : 1;

  /* ── Actions ──────────────────────────────────────────────────────── */
  const handleTriggerBackup = useCallback(async () => {
    setTriggering(true);
    setActionMessage(null);
    try {
      await api.post("/api/v1/backup/trigger", { backup_type: triggerType });
      setActionMessage({ type: "success", text: `${triggerType} backup triggered successfully.` });
      setShowTriggerModal(false);
      mutate();
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err?.response?.data?.detail || err?.message || "Failed to trigger backup.",
      });
    } finally {
      setTriggering(false);
    }
  }, [triggerType, mutate]);

  const handleVerify = useCallback(async (backupId: string) => {
    setVerifyingId(backupId);
    setActionMessage(null);
    try {
      await api.post(`/api/v1/backup/${backupId}/verify`);
      setActionMessage({ type: "success", text: "Backup verification initiated." });
      mutate();
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err?.response?.data?.detail || err?.message || "Verification failed.",
      });
    } finally {
      setVerifyingId(null);
    }
  }, [mutate]);

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Page header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Backup Management</h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              §14 — Automated backup records, verification, and recovery
            </p>
          </div>
          <button
            onClick={() => setShowTriggerModal(true)}
            className="rounded-lg bg-ivgs-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ivgs-500"
          >
            Trigger Backup
          </button>
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
            <button
              onClick={() => setActionMessage(null)}
              className="ml-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            >
              ✕
            </button>
          </div>
        )}

        {/* RTO/RPO Info Panel */}
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">RTO</p>
            <p className="mt-1 text-xl font-bold text-gray-900 dark:text-white">4 hours</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">Recovery Time Objective</p>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">RPO</p>
            <p className="mt-1 text-xl font-bold text-gray-900 dark:text-white">24 hours</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">Recovery Point Objective</p>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Records</p>
            <p className="mt-1 text-xl font-bold text-gray-900 dark:text-white">
              {isLoading ? "..." : totalCount ?? 0}
            </p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">Total Backup Records</p>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Schedule</p>
            <p className="mt-1 text-xl font-bold text-gray-900 dark:text-white">Daily</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">Full DB at 02:00 UTC</p>
          </div>
        </div>

        {/* Filters */}
        <div className="mb-4 flex items-center gap-4">
          <div>
            <label htmlFor="type-filter" className="sr-only">Filter by type</label>
            <select
              id="type-filter"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value as BackupType | "ALL");
                setPage(1);
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-800 dark:text-gray-200 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500"
            >
              {BACKUP_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() => mutate()}
            className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            Refresh
          </button>
        </div>

        {/* Backup records table */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner size="lg" label="Loading backup records..." />
          </div>
        ) : error ? (
          <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-100 dark:bg-red-900/20 p-6 text-center text-red-600 dark:text-red-400">
            <p className="text-lg font-semibold">Failed to load backup records</p>
            <p className="mt-1 text-sm">{error.message}</p>
            <button
              onClick={() => mutate()}
              className="mt-3 rounded-lg bg-gray-100 dark:bg-gray-800 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
            >
              Retry
            </button>
          </div>
        ) : !records || records.length === 0 ? (
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-12 text-center">
            <svg className="mx-auto h-12 w-12 text-gray-600 dark:text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375" />
            </svg>
            <p className="mt-4 text-lg font-medium text-gray-500 dark:text-gray-400">No backup records found</p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Trigger a manual backup or wait for the scheduled backup to create records.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/50 text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Started</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Duration</th>
                  <th className="px-4 py-3">Verified</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                {records.map((record: BackupRecord) => {
                  const statusBadge = STATUS_BADGES[record.status] ?? STATUS_BADGES.running;
                  // Derive duration client-side: completed_at - started_at
                  const durationSecs: number | null =
                    record.completed_at
                      ? Math.max(0, Math.floor(
                          (new Date(record.completed_at).getTime()
                            - new Date(record.started_at).getTime()) / 1000))
                      : null;

                  return (
                    <tr key={record.id} className="hover:bg-gray-100 dark:hover:bg-gray-800/50">
                      <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-800 dark:text-gray-200">
                        {record.backup_type.replace(/_/g, " ").toUpperCase()}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-500 dark:text-gray-400">
                        {formatTimestamp(record.started_at)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge.bg} ${statusBadge.text}`}>
                          {record.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-500 dark:text-gray-400">
                        {formatBytes(record.size_bytes ?? 0)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-500 dark:text-gray-400">
                        {formatDuration(durationSecs)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        {record.status === "verified" ? (
                          <span className="inline-flex rounded-full bg-emerald-100 dark:bg-emerald-900/30 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                            verified
                          </span>
                        ) : record.status === "failed" ? (
                          <span className="inline-flex rounded-full bg-red-100 dark:bg-red-900/30 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400">
                            failed
                          </span>
                        ) : (
                          <span className="inline-flex rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs font-medium text-gray-500 dark:text-gray-400">
                            unverified
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <button
                          onClick={() => handleVerify(record.id)}
                          disabled={verifyingId === record.id || !["completed", "verified"].includes(record.status)}
                          className="rounded px-2 py-1 text-xs font-medium text-ivgs-600 dark:text-ivgs-400 transition-colors hover:bg-ivgs-600/20 hover:text-ivgs-800 dark:hover:text-ivgs-300 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {verifyingId === record.id ? "Verifying..." : "Verify"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Page {page} of {totalPages} ({totalCount} total records)
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Trigger Backup Modal */}
        {showTriggerModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="mx-4 w-full max-w-md rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Trigger Manual Backup</h2>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Select the backup type and confirm. This will initiate an immediate backup job.
              </p>
              <div className="mt-4">
                <label htmlFor="backup-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Backup Type
                </label>
                <select
                  id="backup-type"
                  value={triggerType}
                  onChange={(e) => setTriggerType(e.target.value as BackupType)}
                  className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-800 dark:text-gray-200 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500"
                >
                  <option value="full_database">Full Database</option>
                  <option value="wal_archive">WAL Archive</option>
                  <option value="asset_backup">Asset Backup</option>
                  <option value="config_backup">Config Backup</option>
                </select>
              </div>
              <div className="mt-4 rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-100 dark:bg-yellow-900/10 p-3 text-xs text-yellow-600 dark:text-yellow-400">
                ⚠ Manual backups may impact system performance during execution. Prefer scheduling
                backups during off-peak hours.
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setShowTriggerModal(false)}
                  className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleTriggerBackup}
                  disabled={triggering}
                  className="rounded-lg bg-ivgs-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ivgs-500 disabled:opacity-50"
                >
                  {triggering ? "Triggering..." : "Trigger Backup"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
