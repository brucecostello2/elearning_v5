"use client";

import React, { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useJobs } from "@/hooks/useJobs";
import { useAuth } from "@/hooks/useAuth";
import StateBadge from "@/components/StateBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { RenderJob } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Jobs Tab
 *
 * Features:
 *   - Pipeline job history table
 *   - Columns: status, node, stage, timing, error details, retry count
 *   - Checkpoint resume button for failed jobs
 *   - Real-time polling for active jobs
 */

export default function JobsPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const { jobs, isLoading, error, resumeJob, mutate } = useJobs(projectId);

  const [resumingJobId, setResumingJobId] = useState<string | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  const canResume = user?.role === "admin" || user?.role === "operator";

  /**
   * Resume a failed job from its last checkpoint.
   */
  const handleResume = useCallback(
    async (jobId: string): Promise<void> => {
      if (!canResume) return;
      setResumingJobId(jobId);
      try {
        await resumeJob(jobId);
        setToastMessage("Job resumed from checkpoint.");
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to resume job.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setResumingJobId(null);
      }
    },
    [canResume, resumeJob, mutate]
  );

  /**
   * Format duration from seconds to human readable.
   */
  const formatDuration = (seconds: number | null | undefined): string => {
    if (!seconds) return "—";
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading jobs…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400">
          Failed to load jobs: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Pipeline Jobs</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            {jobs?.length || 0} job{(jobs?.length || 0) !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {!jobs || jobs.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          No pipeline jobs have been created for this project yet.
        </div>
      ) : (
        <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-300 dark:border-gray-700 text-left">
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Status
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Stage
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Node
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Started
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Duration
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Retries
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-300 dark:divide-gray-700">
                {jobs.map((job: RenderJob) => (
                  <React.Fragment key={job.id}>
                    <tr
                      className="hover:bg-gray-750 cursor-pointer transition-colors"
                      onClick={() =>
                        setExpandedJobId(
                          expandedJobId === job.id ? null : job.id
                        )
                      }
                    >
                      <td className="px-5 py-3">
                        <StateBadge state={job.status} />
                      </td>
                      <td className="px-5 py-3 text-gray-900 dark:text-white font-medium">
                        {job.current_stage || "—"}
                      </td>
                      <td className="px-5 py-3 text-gray-700 dark:text-gray-300">
                        {job.assigned_node || "Unassigned"}
                      </td>
                      <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                        {job.started_at
                          ? new Date(job.started_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                        {formatDuration(job.duration_seconds)}
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`font-mono ${
                            (job.retry_count || 0) > 0
                              ? "text-yellow-600 dark:text-yellow-400"
                              : "text-gray-500 dark:text-gray-400"
                          }`}
                        >
                          {job.retry_count || 0}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        {canResume &&
                          (job.status === "FAILED" ||
                            job.status === "ERROR") &&
                          job.has_checkpoint && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleResume(job.id);
                              }}
                              disabled={resumingJobId === job.id}
                              className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
                            >
                              {resumingJobId === job.id
                                ? "Resuming…"
                                : "Resume"}
                            </button>
                          )}
                      </td>
                    </tr>

                    {/* Expanded Detail Row */}
                    {expandedJobId === job.id && (
                      <tr>
                        <td colSpan={7} className="px-5 py-4 bg-gray-850">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                Job ID
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 font-mono text-xs mt-0.5">
                                {job.id}
                              </p>
                            </div>
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                GPU
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 mt-0.5">
                                {job.assigned_gpu || "N/A"}
                              </p>
                            </div>
                            {job.error_message && (
                              <div className="sm:col-span-2">
                                <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                  Error Details
                                </span>
                                <pre className="mt-1 p-3 bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400 text-xs overflow-x-auto whitespace-pre-wrap">
                                  {job.error_message}
                                </pre>
                              </div>
                            )}
                            {job.checkpoint_data && (
                              <div className="sm:col-span-2">
                                <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                  Last Checkpoint
                                </span>
                                <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">
                                  Stage: {String(job.checkpoint_data.stage)} | Progress:{" "}
                                  {String(job.checkpoint_data.progress)}% | Saved:{" "}
                                  {new Date(
                                    String(job.checkpoint_data.saved_at)
                                  ).toLocaleString()}
                                </p>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showToast && (
        <Toast
          message={toastMessage}
          type={toastType}
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
}
