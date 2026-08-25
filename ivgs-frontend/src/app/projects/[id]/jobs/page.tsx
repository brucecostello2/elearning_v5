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

/**
 * The blank a field gets when the system does not record it.
 *
 * WP-45 Task 6(f). "—" and "Unassigned" and "N/A" all read as measurements:
 * "no stage", "no node", "no GPU". They were none of those - they were six
 * field names the API has never sent. Where a value is genuinely unrecorded the
 * tab says so, in words, once.
 */
const notRecorded = (
  <span className="text-xs italic text-gray-400 dark:text-gray-500">
    not recorded
  </span>
);

/** `job_type` is a lowercase enum on the wire; this is its display form. */
function jobTypeLabel(jobType: string | null | undefined): string {
  if (!jobType) return "unknown";
  return jobType.replace(/_/g, " ");
}

/**
 * Job duration in seconds, from the columns that now carry it.
 *
 * WP-45 Task 5 / WP-40 D-4: `started_at` and `completed_at` were dead columns -
 * NULL on every row on the fleet, written by nothing - and the tab read a
 * `duration_seconds` field the API has never sent, so the column was blank on
 * every job. They are stamped now. Returns null, not 0, when the span cannot be
 * measured: `formatDuration(0)` renders "—", which would make "instant"
 * indistinguishable from "unrecorded", the two worst things to conflate on a
 * duration display (WP-40 §2.4).
 */
function jobDurationSeconds(job: RenderJob): number | null {
  if (!job.started_at) return null;
  const started = new Date(job.started_at).getTime();
  const ended = job.completed_at ? new Date(job.completed_at).getTime() : Date.now();
  if (!Number.isFinite(started) || !Number.isFinite(ended)) return null;
  const seconds = Math.round((ended - started) / 1000);
  return seconds >= 0 ? seconds : null;
}


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
    if (seconds === null || seconds === undefined) return "not recorded";
    if (seconds === 0) return "under 1s";
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
                    Job
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Type
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Created
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
                      {/* WP-45 Task 6(f): the row identifies the job. It used
                          to draw job.current_stage and job.assigned_node, two
                          field names the API has never sent, so every row read
                          "—" and "Unassigned" and none of them said which job
                          it was. */}
                      <td className="px-5 py-3 text-gray-900 dark:text-white font-mono text-xs">
                        {job.id.slice(0, 8)}
                      </td>
                      <td className="px-5 py-3 text-gray-700 dark:text-gray-300">
                        {jobTypeLabel(job.job_type)}
                        {job.language_code && (
                          <span className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 font-mono text-[10px] text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                            {job.language_code}
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                        {job.created_at
                          ? new Date(job.created_at).toLocaleString()
                          : notRecorded}
                      </td>
                      <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                        {job.started_at
                          ? new Date(job.started_at).toLocaleString()
                          : notRecorded}
                      </td>
                      <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                        {formatDuration(jobDurationSeconds(job))}
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
                        {/* WP-45: `job.has_checkpoint` was never sent by the
                            API, so the Resume button could not appear on any
                            row, ever. The server decides whether a resume is
                            possible -- it answers 409 with the reason when the
                            job has no completed checkpoint -- so the button is
                            offered on terminal-failed jobs and the refusal is
                            surfaced as a toast rather than guessed at here. */}
                        {canResume &&
                          (job.status === "FAILED" ||
                            job.status === "ERROR" ||
                            job.status === "failed") && (
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
                        <td colSpan={8} className="px-5 py-4 bg-gray-850">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                Job ID
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 font-mono text-xs mt-0.5">
                                {job.id}
                              </p>
                            </div>
                            {/* WP-45 Task 6(f): honest blanks. `assigned_gpu`
                                was a field the API has never sent, rendered as
                                "N/A" -- which reads as "this job used no GPU"
                                rather than "nobody records this". The fields
                                below are the ones the API populates. */}
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                Node
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 mt-0.5">
                                {job.node_id || notRecorded}
                              </p>
                            </div>
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                Last stage reported
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 mt-0.5">
                                {job.resume_from_stage
                                  ? jobTypeLabel(job.resume_from_stage)
                                  : notRecorded}
                              </p>
                            </div>
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                Celery task
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 font-mono text-xs mt-0.5 break-all">
                                {job.celery_task_id || notRecorded}
                              </p>
                            </div>
                            <div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">
                                Completed
                              </span>
                              <p className="text-gray-700 dark:text-gray-300 mt-0.5">
                                {job.completed_at
                                  ? new Date(job.completed_at).toLocaleString()
                                  : notRecorded}
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
