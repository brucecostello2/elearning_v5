"use client";

import React, { useState, useCallback } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { DLQMessage, DLQCategory } from "@/types/monitoring";

/**
 * §8.2.3 Dead Letter Queue Dashboard — Message Table
 *
 * Paginated table displaying DLQ messages with:
 * - Columns: task name, failure category, error message (truncated),
 *   retry count, entered DLQ timestamp
 * - Category badges color-coded by type:
 *   TRANSIENT (blue), CONFIG (purple), EXTERNAL (amber), RESOURCE (red)
 * - Expandable rows showing full error message preview
 * - Action buttons: Replay (re-enqueue), View Detail (opens modal)
 * - Pagination with page size selector
 *
 * Data flows from parent DLQ page via props.
 */

interface DLQTableProps {
  /** Array of DLQ messages for the current page */
  messages: DLQMessage[];
  /** Whether the current user is admin (for action buttons) */
  isAdmin: boolean;
  /** ID of message with action in progress (shows spinner) */
  actionInProgress: string | null;
  /** Callback to replay a message */
  onReplay: (messageId: string) => void;
  /** Callback to open detail modal */
  onViewDetail: (messageId: string) => void;
  /** Current page number (1-based) */
  page: number;
  /** Items per page */
  pageSize: number;
  /** Total number of pages */
  totalPages: number;
  /** Total message count across all pages */
  totalCount: number;
  /** Callback to change page */
  onPageChange: (page: number) => void;
  /** Callback to change page size */
  onPageSizeChange: (size: number) => void;
  /** Available page size options */
  pageSizeOptions: number[];
}

/** Category badge colors per §6.2 failure categories */
const CATEGORY_STYLES: Record<DLQCategory, string> = {
  TRANSIENT: "bg-blue-100 text-blue-800",
  CONFIG: "bg-purple-100 text-purple-800",
  EXTERNAL: "bg-amber-100 text-amber-800",
  RESOURCE: "bg-red-100 text-red-800",
};

/** Maximum characters for truncated error message */
const ERROR_TRUNCATE_LENGTH = 80;

export default function DLQTable({
  messages,
  isAdmin,
  actionInProgress,
  onReplay,
  onViewDetail,
  page,
  pageSize,
  totalPages,
  totalCount,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions,
}: DLQTableProps): React.ReactElement {
  /** Track which rows are expanded to show full error */
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  /**
   * Toggle row expansion for error message preview.
   */
  const toggleExpand = useCallback((messageId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  }, []);

  /**
   * Truncate error message string.
   */
  const truncateError = useCallback(
    (error: string): { truncated: string; isTruncated: boolean } => {
      if (error.length <= ERROR_TRUNCATE_LENGTH) {
        return { truncated: error, isTruncated: false };
      }
      return {
        truncated: error.slice(0, ERROR_TRUNCATE_LENGTH) + "…",
        isTruncated: true,
      };
    },
    []
  );

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

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* ── Table ──────────────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase w-8">
                {/* Expand toggle column */}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Task Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Category
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Error Message
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                Retries
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Entered DLQ
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {messages.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-sm text-gray-500"
                >
                  No DLQ messages match the current filters.
                </td>
              </tr>
            ) : (
              messages.map((msg: DLQMessage) => {
                const { truncated, isTruncated } = truncateError(
                  msg.error_message
                );
                const isExpanded = expandedRows.has(msg.id);

                return (
                  <React.Fragment key={msg.id}>
                    <tr className="hover:bg-gray-50">
                      {/* Expand toggle */}
                      <td className="px-4 py-3">
                        {isTruncated && (
                          <button
                            type="button"
                            onClick={() => toggleExpand(msg.id)}
                            className="text-gray-400 hover:text-gray-600"
                          >
                            <svg
                              className={`h-4 w-4 transition-transform ${
                                isExpanded ? "rotate-90" : ""
                              }`}
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={2}
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="m8.25 4.5 7.5 7.5-7.5 7.5"
                              />
                            </svg>
                          </button>
                        )}
                      </td>
                      {/* Task Name */}
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 font-mono">
                        {msg.task_name}
                      </td>
                      {/* Category */}
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center px-2 py-0.5
                            rounded-full text-xs font-medium ${
                              CATEGORY_STYLES[msg.category] ||
                              "bg-gray-100 text-gray-700"
                            }`}
                        >
                          {msg.category}
                        </span>
                      </td>
                      {/* Error Message */}
                      <td className="px-4 py-3 text-sm text-gray-600 max-w-[300px]">
                        <span className="font-mono text-xs">
                          {isExpanded ? msg.error_message : truncated}
                        </span>
                      </td>
                      {/* Retry Count */}
                      <td className="px-4 py-3 text-center text-sm font-mono text-gray-700">
                        {msg.retry_count}
                      </td>
                      {/* Entered DLQ */}
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {formatDate(msg.entered_dlq_at)}
                      </td>
                      {/* Actions */}
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => onViewDetail(msg.id)}
                            className="text-xs text-blue-600 hover:text-blue-800"
                          >
                            Detail
                          </button>
                          {isAdmin && (
                            <button
                              type="button"
                              onClick={() => onReplay(msg.id)}
                              disabled={actionInProgress === msg.id}
                              className="inline-flex items-center gap-1 px-2 py-1
                                text-xs font-medium text-green-700 bg-green-50
                                border border-green-200 rounded hover:bg-green-100
                                disabled:opacity-50 disabled:cursor-not-allowed
                                transition-colors"
                            >
                              {actionInProgress === msg.id ? (
                                <LoadingSpinner size="sm" />
                              ) : (
                                "Replay"
                              )}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {/* Expanded error row */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} className="px-4 py-3 bg-gray-50">
                          <pre className="text-xs text-gray-700 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                            {msg.error_message}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ─────────────────────────────────────────────── */}
      <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">
            Showing {(page - 1) * pageSize + 1}–
            {Math.min(page * pageSize, totalCount)} of {totalCount}
          </span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(parseInt(e.target.value))}
            className="rounded-md border-gray-300 text-xs shadow-sm
              focus:border-blue-500 focus:ring-blue-500"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(1)}
            disabled={page === 1}
            className="px-2 py-1 text-xs rounded border border-gray-300 bg-white
              text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            First
          </button>
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className="px-2 py-1 text-xs rounded border border-gray-300 bg-white
              text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Prev
          </button>
          <span className="text-xs text-gray-600 px-2">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
            className="px-2 py-1 text-xs rounded border border-gray-300 bg-white
              text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
          <button
            type="button"
            onClick={() => onPageChange(totalPages)}
            disabled={page === totalPages}
            className="px-2 py-1 text-xs rounded border border-gray-300 bg-white
              text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Last
          </button>
        </div>
      </div>
    </div>
  );
}
