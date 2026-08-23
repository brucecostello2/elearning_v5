"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import {
  useDLQMessages,
  useDLQAnalytics,
} from "@/hooks/useMonitoring";
import DLQTable from "@/components/monitoring/DLQTable";
import DLQDetailModal from "@/components/monitoring/DLQDetailModal";
import DLQAnalytics from "@/components/monitoring/DLQAnalytics";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  DLQMessage,
  DLQCategory,
  DLQAnalyticsData,
} from "@/types/monitoring";

/**
 * §8.2.3 Dead Letter Queue Dashboard
 *
 * Full DLQ management page with:
 * - Message table: task name, failure category, error message (truncated),
 *   retry count, entered DLQ timestamp
 * - Filters: category (transient/config/external/resource), date range, task name
 * - Detail modal: full stack trace, task arguments, resolution history
 * - Actions: Replay (re-enqueue), Discard (mark resolved with reason)
 * - Failure analytics: category pie, trend line, top tasks bar chart
 * - Bulk operations: replay all transient, discard older than N days
 *
 * Data sources:
 *   - GET /api/v1/dlq/messages — paginated list with filters (§5.2.2)
 *   - GET /api/v1/dlq/messages/{id} — detail with traceback and args
 *   - POST /api/v1/dlq/messages/{id}/replay — re-enqueue task
 *   - POST /api/v1/dlq/messages/{id}/discard — mark as discarded
 *   - GET /api/v1/dlq/analytics — failure analytics data
 *   - POST /api/v1/dlq/bulk-replay — bulk replay by filter
 *
 * RBAC per Table 8-3:
 *   - admin: full access + replay/discard + bulk operations
 *   - operator: read-only view
 *   - viewer: no access (redirected)
 */

/** DLQ failure categories per §6.2 retry policies */
const DLQ_CATEGORIES: { value: DLQCategory | "ALL"; label: string }[] = [
  { value: "ALL", label: "All Categories" },
  { value: "TRANSIENT", label: "Transient" },
  { value: "CONFIG", label: "Configuration" },
  { value: "EXTERNAL", label: "External" },
  { value: "RESOURCE", label: "Resource" },
];

/** Page size options for pagination */
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;

export default function DLQDashboardPage(): React.ReactElement | null {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role === "viewer") {
      router.push("/");
    }
  }, [user, router]);

  // ── State ───────────────────────────────────────────────────────────
  const [categoryFilter, setCategoryFilter] = useState<DLQCategory | "ALL">(
    "ALL"
  );
  const [taskNameFilter, setTaskNameFilter] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(25);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(
    null
  );
  const [showAnalytics, setShowAnalytics] = useState<boolean>(true);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [bulkActionInProgress, setBulkActionInProgress] =
    useState<boolean>(false);
  const [discardDaysThreshold, setDiscardDaysThreshold] = useState<number>(30);

  // ── Data Fetching ───────────────────────────────────────────────────
  /**
   * useDLQMessages fetches from GET /api/v1/dlq/messages with pagination
   * and filters. Polling interval: 30 seconds.
   */
  const {
    messages,
    totalCount,
    isLoading: messagesLoading,
    error: messagesError,
    mutate: mutateMessages,
  } = useDLQMessages({
    category: categoryFilter !== "ALL" ? categoryFilter : undefined,
    taskName: taskNameFilter || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    page,
    pageSize,
  });

  /**
   * useDLQAnalytics fetches from GET /api/v1/dlq/analytics.
   * Polling interval: 60 seconds (less frequent — analytics are aggregated).
   */
  const {
    analytics,
    isLoading: analyticsLoading,
  } = useDLQAnalytics();

  // ── Handlers ────────────────────────────────────────────────────────

  /**
   * handleReplay — POST /api/v1/dlq/messages/{id}/replay
   *
   * Re-enqueues the original Celery task for retry.
   * Admin only per Table 8-3.
   */
  const handleReplay = useCallback(
    async (messageId: string) => {
      if (user?.role !== "admin") {
        setActionError("Only administrators can replay DLQ messages.");
        return;
      }

      setActionInProgress(messageId);
      setActionError(null);

      try {
        const response = await fetch(
          `/api/v1/dlq/messages/${messageId}/replay`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
            },
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Replay failed: ${response.status}`
          );
        }

        await mutateMessages();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to replay message";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [user, mutateMessages]
  );

  /**
   * handleDiscard — POST /api/v1/dlq/messages/{id}/discard
   *
   * Marks the DLQ message as discarded with a reason.
   * Admin only per Table 8-3.
   */
  const handleDiscard = useCallback(
    async (messageId: string, reason: string) => {
      if (user?.role !== "admin") {
        setActionError("Only administrators can discard DLQ messages.");
        return;
      }

      setActionInProgress(messageId);
      setActionError(null);

      try {
        const response = await fetch(
          `/api/v1/dlq/messages/${messageId}/discard`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
            },
            body: JSON.stringify({ reason }),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Discard failed: ${response.status}`
          );
        }

        await mutateMessages();
        setSelectedMessageId(null);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to discard message";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [user, mutateMessages]
  );

  /**
   * handleBulkReplayTransient — POST /api/v1/dlq/bulk-replay
   *
   * Bulk replays all transient failures. Admin only.
   */
  const handleBulkReplayTransient = useCallback(async () => {
    if (user?.role !== "admin") {
      setActionError("Only administrators can perform bulk operations.");
      return;
    }

    if (
      !window.confirm(
        "Replay all transient DLQ messages? This will re-enqueue all messages with category TRANSIENT."
      )
    ) {
      return;
    }

    setBulkActionInProgress(true);
    setActionError(null);

    try {
      const response = await fetch("/api/v1/dlq/bulk-replay", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
        },
        body: JSON.stringify({ category: "TRANSIENT" }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `Bulk replay failed: ${response.status}`
        );
      }

      const result = await response.json();
      window.alert(`Successfully replayed ${result.count || 0} messages.`);
      await mutateMessages();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Bulk replay failed";
      setActionError(message);
    } finally {
      setBulkActionInProgress(false);
    }
  }, [user, mutateMessages]);

  /**
   * handleBulkDiscardOld — POST /api/v1/dlq/bulk-replay with discard action
   *
   * Discards all DLQ messages older than N days. Admin only.
   */
  const handleBulkDiscardOld = useCallback(async () => {
    if (user?.role !== "admin") {
      setActionError("Only administrators can perform bulk operations.");
      return;
    }

    if (
      !window.confirm(
        `Discard all DLQ messages older than ${discardDaysThreshold} days? This cannot be undone.`
      )
    ) {
      return;
    }

    setBulkActionInProgress(true);
    setActionError(null);

    try {
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - discardDaysThreshold);

      const response = await fetch("/api/v1/dlq/bulk-replay", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
        },
        body: JSON.stringify({
          action: "discard",
          before_date: cutoffDate.toISOString(),
          reason: `Bulk discard: older than ${discardDaysThreshold} days`,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `Bulk discard failed: ${response.status}`
        );
      }

      const result = await response.json();
      window.alert(`Successfully discarded ${result.count || 0} messages.`);
      await mutateMessages();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Bulk discard failed";
      setActionError(message);
    } finally {
      setBulkActionInProgress(false);
    }
  }, [user, mutateMessages, discardDaysThreshold]);

  /**
   * handleClearFilters — Reset all filter state.
   */
  const handleClearFilters = useCallback(() => {
    setCategoryFilter("ALL");
    setTaskNameFilter("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }, []);

  /** Total pages for pagination */
  const totalPages = useMemo(
    () => Math.ceil((totalCount || 0) / pageSize),
    [totalCount, pageSize]
  );

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600 dark:text-red-400">
            DLQ Dashboard Error
          </h3>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            An error occurred loading the DLQ dashboard. Please refresh.
          </p>
        </div>
      }
    >
      {/* WP-23 / operator ruling 2026-08-23 item 7. Was `min-h-screen` (100vh).
          The monitoring layout already reserves the 3.5rem sticky global header
          via `flex min-h-[calc(100vh-3.5rem)]`, so a 100vh child overflowed its
          scroll container by exactly the header height and pushed this page's
          own <h1> under it. min-h-full fills the container instead of re-adding
          the header's height. */}
      <div className="min-h-full bg-gray-50 dark:bg-gray-950">
        {/* ── Page Header ─────────────────────────────────────────── */}
        <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Dead Letter Queue
              </h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                §8.2.3 — Failed task management with replay, discard, and
                analytics
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* Total count badge */}
              <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-300">
                {totalCount ?? 0} messages
              </span>
              {/* Analytics toggle */}
              <button
                type="button"
                onClick={() => setShowAnalytics(!showAnalytics)}
                className={`px-3 py-1.5 text-sm font-medium rounded-md border
                  ${
                    showAnalytics
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-950"
                  }`}
              >
                Analytics
              </button>
            </div>
          </div>
        </header>

        <div className="px-6 py-6">
          {/* ── Analytics Section ─────────────────────────────────── */}
          {showAnalytics && (
            <div className="mb-6">
              {analyticsLoading ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : analytics ? (
                <DLQAnalytics data={analytics} />
              ) : null}
            </div>
          )}

          {/* ── Filters ─────────────────────────────────────────── */}
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 mb-6">
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex-1 min-w-[150px]">
                <label
                  htmlFor="category-filter"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Category
                </label>
                <select
                  id="category-filter"
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(
                      e.target.value as DLQCategory | "ALL"
                    );
                    setPage(1);
                  }}
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                >
                  {DLQ_CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex-1 min-w-[180px]">
                <label
                  htmlFor="task-filter"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Task Name
                </label>
                <input
                  id="task-filter"
                  type="text"
                  value={taskNameFilter}
                  onChange={(e) => {
                    setTaskNameFilter(e.target.value);
                    setPage(1);
                  }}
                  placeholder="e.g., generate_media"
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>

              <div className="min-w-[130px]">
                <label
                  htmlFor="dlq-date-from"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  From
                </label>
                <input
                  id="dlq-date-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => {
                    setDateFrom(e.target.value);
                    setPage(1);
                  }}
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>

              <div className="min-w-[130px]">
                <label
                  htmlFor="dlq-date-to"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  To
                </label>
                <input
                  id="dlq-date-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => {
                    setDateTo(e.target.value);
                    setPage(1);
                  }}
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>

              <button
                type="button"
                onClick={handleClearFilters}
                className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100
                  hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"
              >
                Clear
              </button>
            </div>

            {/* ── Bulk Actions (Admin Only) ─────────────────────── */}
            {user?.role === "admin" && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-800 flex flex-wrap items-center gap-3">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Bulk Actions:
                </span>
                <button
                  type="button"
                  onClick={handleBulkReplayTransient}
                  disabled={bulkActionInProgress}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-xs
                    font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/40 border border-blue-200 dark:border-blue-800
                    rounded-md hover:bg-blue-100 dark:hover:bg-blue-900/50 disabled:opacity-50
                    disabled:cursor-not-allowed transition-colors"
                >
                  Replay All Transient
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleBulkDiscardOld}
                    disabled={bulkActionInProgress}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs
                      font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800
                      rounded-md hover:bg-red-100 dark:hover:bg-red-900/50 disabled:opacity-50
                      disabled:cursor-not-allowed transition-colors"
                  >
                    Discard Older Than
                  </button>
                  <input
                    type="number"
                    min={1}
                    max={365}
                    value={discardDaysThreshold}
                    onChange={(e) =>
                      setDiscardDaysThreshold(
                        Math.max(1, parseInt(e.target.value) || 30)
                      )
                    }
                    className="w-16 rounded-md border-gray-300 dark:border-gray-700 text-xs shadow-sm
                      focus:border-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-xs text-gray-500 dark:text-gray-400">days</span>
                </div>
                {bulkActionInProgress && <LoadingSpinner size="sm" />}
              </div>
            )}
          </div>

          {/* ── Action Error ─────────────────────────────────────── */}
          {actionError && (
            <div className="bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-amber-700 dark:text-amber-300">{actionError}</p>
                <button
                  type="button"
                  onClick={() => setActionError(null)}
                  className="text-amber-500 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* ── DLQ Message Table ─────────────────────────────────── */}
          {messagesLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          ) : messagesError ? (
            <div className="bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <p className="text-sm text-red-700 dark:text-red-300">
                Failed to load DLQ messages. Please try again.
              </p>
            </div>
          ) : (
            <DLQTable
              messages={messages || []}
              isAdmin={user?.role === "admin"}
              actionInProgress={actionInProgress}
              onReplay={handleReplay}
              onViewDetail={(id) => setSelectedMessageId(id)}
              page={page}
              pageSize={pageSize}
              totalPages={totalPages}
              totalCount={totalCount || 0}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
              pageSizeOptions={PAGE_SIZE_OPTIONS as unknown as number[]}
            />
          )}
        </div>

        {/* ── Detail Modal ────────────────────────────────────────── */}
        {selectedMessageId && (
          <DLQDetailModal
            messageId={selectedMessageId}
            isAdmin={user?.role === "admin"}
            onClose={() => setSelectedMessageId(null)}
            onReplay={handleReplay}
            onDiscard={handleDiscard}
            actionInProgress={actionInProgress}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}
