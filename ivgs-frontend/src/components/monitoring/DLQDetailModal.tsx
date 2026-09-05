"use client";

import React, { useState, useCallback, useEffect } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { DLQMessageDetail, DLQResolutionEntry } from "@/types/monitoring";

/**
 * §8.2.3 Dead Letter Queue Dashboard — Detail Modal
 *
 * Full-screen modal displaying complete DLQ message details:
 * - Full stack trace / traceback (syntax-highlighted)
 * - Task arguments (JSON pretty-printed)
 * - Task metadata: name, queue, routing key, exchange
 * - Resolution history: list of past replay/discard actions
 * - Action buttons: Replay (re-enqueue), Discard (with reason input)
 *
 * Fetches from GET /api/v1/dlq/messages/{id} for full detail.
 */

/**
 * WP-70 fix D-8. The API records one resolution per message
 * (`resolution`, `reviewed_by`, `reviewed_at`); the "history" tab renders it
 * as a one-entry list so the list rendering below is unchanged.
 */
const resolutionHistory = (detail: DLQMessageDetail): DLQResolutionEntry[] =>
  detail.resolution
    ? [
        {
          action: detail.resolution.toUpperCase(),
          reason: "",
          performed_by: detail.reviewed_by ?? "unknown",
          performed_at: detail.reviewed_at ?? detail.created_at,
          result: "",
        },
      ]
    : [];

/** The arguments tab: positional and keyword arguments, as the API sends them. */
const taskArguments = (detail: DLQMessageDetail): Record<string, unknown> | null =>
  detail.task_args != null || detail.task_kwargs != null
    ? { args: detail.task_args ?? [], kwargs: detail.task_kwargs ?? {} }
    : null;

interface DLQDetailModalProps {
  /** ID of the DLQ message to display */
  messageId: string;
  /** Whether the user is admin (for action buttons) */
  isAdmin: boolean;
  /** Close modal callback */
  onClose: () => void;
  /** Replay message callback */
  onReplay: (messageId: string) => void;
  /** Discard message callback with reason */
  onDiscard: (messageId: string, reason: string) => void;
  /** ID of message with action in progress */
  actionInProgress: string | null;
}

export default function DLQDetailModal({
  messageId,
  isAdmin,
  onClose,
  onReplay,
  onDiscard,
  actionInProgress,
}: DLQDetailModalProps): React.ReactElement {
  // ── State ───────────────────────────────────────────────────────────
  const [detail, setDetail] = useState<DLQMessageDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [discardReason, setDiscardReason] = useState<string>("");
  const [showDiscardForm, setShowDiscardForm] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<
    "traceback" | "arguments" | "history"
  >("traceback");

  // ── Fetch Detail ────────────────────────────────────────────────────
  useEffect(() => {
    const fetchDetail = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(`/api/v1/dlq/messages/${messageId}`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch: ${response.status}`);
        }

        const data = await response.json();
        setDetail(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load message detail"
        );
      } finally {
        setIsLoading(false);
      }
    };

    fetchDetail();
  }, [messageId]);

  /**
   * handleDiscard — Submit discard with reason.
   */
  const handleDiscardSubmit = useCallback(() => {
    if (!discardReason.trim()) {
      return;
    }
    onDiscard(messageId, discardReason.trim());
  }, [messageId, discardReason, onDiscard]);

  /**
   * Format ISO date to localized display.
   */
  const formatDate = useCallback((dateStr: string): string => {
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  }, []);

  // ── Close on Escape key ─────────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col">
        {/* ── Modal Header ───────────────────────────────────────── */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              DLQ Message Detail
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5">
              ID: {messageId}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-400 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ── Modal Body ─────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          ) : error ? (
            <div className="p-6">
              <div className="bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4">
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            </div>
          ) : detail ? (
            <div className="p-6 space-y-4">
              {/* ── Message Metadata ──────────────────────────────── */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Task Name</p>
                  <p className="text-sm font-mono font-medium text-gray-900 dark:text-gray-100 mt-0.5">
                    {detail.task_name}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Category</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-0.5">
                    {detail.failure_category ?? "unknown"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Retry Count</p>
                  <p className="text-sm font-mono font-medium text-gray-900 dark:text-gray-100 mt-0.5">
                    {detail.retry_count_exhausted ?? 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Entered DLQ</p>
                  <p className="text-sm text-gray-900 dark:text-gray-100 mt-0.5">
                    {formatDate(detail.created_at)}
                  </p>
                </div>
              </div>

              {/* ── Tab Navigation ────────────────────────────────── */}
              <div className="border-b border-gray-200 dark:border-gray-800">
                <nav className="flex gap-6">
                  {(
                    [
                      { id: "traceback" as const, label: "Stack Trace" },
                      { id: "arguments" as const, label: "Task Arguments" },
                      { id: "history" as const, label: "Resolution History" },
                    ] as const
                  ).map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={`py-2 text-sm font-medium border-b-2 transition-colors ${
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

              {/* ── Tab Content ───────────────────────────────────── */}
              {activeTab === "traceback" && (
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 overflow-x-auto">
                  <pre className="text-xs text-green-600 dark:text-green-400 font-mono whitespace-pre-wrap max-h-96 overflow-y-auto">
                    {detail.traceback || "No traceback available."}
                  </pre>
                </div>
              )}

              {activeTab === "arguments" && (
                <div className="bg-gray-50 dark:bg-gray-950 rounded-lg p-4 overflow-x-auto">
                  <pre className="text-xs text-gray-800 dark:text-gray-200 font-mono whitespace-pre-wrap max-h-96 overflow-y-auto">
                    {taskArguments(detail)
                      ? JSON.stringify(taskArguments(detail), null, 2)
                      : "No task arguments available."}
                  </pre>
                </div>
              )}

              {activeTab === "history" && (
                <div className="space-y-3">
                  {resolutionHistory(detail).length > 0 ? (
                    resolutionHistory(detail).map(
                      (entry: DLQResolutionEntry, index: number) => (
                        <div
                          key={index}
                          className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-950 rounded-lg"
                        >
                          <div
                            className={`mt-0.5 h-2.5 w-2.5 rounded-full flex-shrink-0 ${
                              entry.action.startsWith("REPLAY")
                                ? "bg-blue-500"
                                : "bg-red-500"
                            }`}
                          />
                          <div>
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                              {entry.action} by {entry.performed_by}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                              {formatDate(entry.performed_at)}
                            </p>
                            {entry.reason && (
                              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                                Reason: {entry.reason}
                              </p>
                            )}
                            {entry.result && (
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                Result: {entry.result}
                              </p>
                            )}
                          </div>
                        </div>
                      )
                    )
                  ) : (
                    <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                      No resolution history for this message.
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* ── Modal Footer (Actions) ─────────────────────────────── */}
        {isAdmin && detail && (
          <div className="px-6 py-4 bg-gray-50 dark:bg-gray-950 border-t border-gray-200 dark:border-gray-800 flex-shrink-0">
            {showDiscardForm ? (
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label
                    htmlFor="discard-reason"
                    className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                  >
                    Discard Reason
                  </label>
                  <input
                    id="discard-reason"
                    type="text"
                    value={discardReason}
                    onChange={(e) => setDiscardReason(e.target.value)}
                    placeholder="Enter reason for discarding…"
                    className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                      focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleDiscardSubmit}
                  disabled={
                    !discardReason.trim() || actionInProgress === messageId
                  }
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600
                    hover:bg-red-700 rounded-md shadow-sm disabled:opacity-50
                    disabled:cursor-not-allowed transition-colors"
                >
                  Confirm Discard
                </button>
                <button
                  type="button"
                  onClick={() => setShowDiscardForm(false)}
                  className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => onReplay(messageId)}
                  disabled={actionInProgress === messageId}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-sm
                    font-medium text-white bg-blue-600 hover:bg-blue-700
                    rounded-md shadow-sm disabled:opacity-50
                    disabled:cursor-not-allowed transition-colors"
                >
                  {actionInProgress === messageId ? (
                    <LoadingSpinner size="sm" />
                  ) : (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                    </svg>
                  )}
                  Replay
                </button>
                <button
                  type="button"
                  onClick={() => setShowDiscardForm(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-sm
                    font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800
                    rounded-md hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                  </svg>
                  Discard
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
