"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import {
  usePipelineJobs,
  usePipelineJobDetail,
} from "@/hooks/useMonitoring";
import { useWebSocket } from "@/hooks/useWebSocket";
import PipelineDAG from "@/components/monitoring/PipelineDAG";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  PipelineJob,
  PipelineStage,
  PipelineStageStatus,
  CheckpointData,
  FallbackLevel,
} from "@/types/monitoring";

/**
 * §8.2.1 Pipeline Progress Tracker
 *
 * Full pipeline monitoring page with:
 * - Visual stage DAG showing all 8 pipeline stages
 * - Real-time status updates via WebSocket (/api/v1/jobs/{id}/status)
 * - Checkpoint data display per stage
 * - ETA calculation based on average stage durations
 * - Fallback level indicators (L1 primary → L4 last resort → DLQ)
 * - Resume button for ERROR state projects (POST /api/v1/jobs/{id}/resume)
 * - Job filtering by state, project, date range
 * - Auto-refresh via SWR polling (15s) + WebSocket for instant updates
 *
 * RBAC per Table 8-3:
 *   - admin: full detail + resume + logs
 *   - operator: read-only status view
 *   - viewer: no access (redirected)
 *
 * Data sources:
 *   - GET /api/v1/projects/{id}/jobs — job listing
 *   - GET /api/v1/jobs/{id} — job detail with checkpoints
 *   - GET /api/v1/jobs/{id}/checkpoints — stage checkpoints
 *   - POST /api/v1/jobs/{id}/resume — resume from checkpoint
 *   - WS /api/v1/jobs/{id}/status — real-time job progress
 */

/** Pipeline stage names matching §6.1 Seven-Stage Pipeline + Final Render */
const PIPELINE_STAGES: PipelineStage[] = [
  "TRANSCRIPT_REFINEMENT",
  "STORYBOARD_GENERATION",
  "MEDIA_GENERATION",
  "MANIFEST_GENERATION",
  "AUDIO_GENERATION",
  "TALKING_HEAD_RENDER",
  "PROTOTYPE_DRAFT",
  "FINAL_RENDER",
];

/** Human-readable labels for each pipeline stage */
const STAGE_LABELS: Record<PipelineStage, string> = {
  TRANSCRIPT_REFINEMENT: "Transcript Refinement",
  STORYBOARD_GENERATION: "Storyboard Generation",
  MEDIA_GENERATION: "Media Generation",
  MANIFEST_GENERATION: "Manifest Generation",
  AUDIO_GENERATION: "Audio Generation",
  TALKING_HEAD_RENDER: "Talking Head Render",
  PROTOTYPE_DRAFT: "Prototype Draft",
  FINAL_RENDER: "Final Render",
};

/** Color mapping for pipeline stage statuses */
const STATUS_COLORS: Record<PipelineStageStatus, string> = {
  PENDING: "bg-gray-200 text-gray-700",
  RUNNING: "bg-blue-100 text-blue-800 animate-pulse",
  COMPLETE: "bg-green-100 text-green-800",
  FAILED: "bg-red-100 text-red-800",
  SKIPPED: "bg-yellow-100 text-yellow-700",
};

/** Job state filter options */
const JOB_STATE_FILTERS = [
  { value: "ALL", label: "All Jobs" },
  { value: "RUNNING", label: "Running" },
  { value: "COMPLETE", label: "Complete" },
  { value: "ERROR", label: "Error" },
  { value: "PENDING", label: "Pending" },
] as const;

export default function PipelineMonitoringPage(): React.ReactElement | null {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user } = useAuth();
  const router = useRouter();

  /**
   * RBAC enforcement per Table 8-3:
   * Viewer role has no access to operational monitoring views.
   * Redirect to dashboard home if unauthorized.
   */
  useEffect(() => {
    if (user && user.role === "viewer") {
      router.push("/");
    }
  }, [user, router]);

  // ── Filter State ────────────────────────────────────────────────────
  const [stateFilter, setStateFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [resumingJobId, setResumingJobId] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);

  // ── Data Fetching ───────────────────────────────────────────────────
  /**
   * usePipelineJobs fetches from GET /api/v1/projects (with jobs expanded)
   * Polling interval: 15 seconds per §8.2.1 real-time requirement.
   * SWR handles caching, deduplication, and background revalidation.
   */
  const {
    jobs,
    isLoading: jobsLoading,
    error: jobsError,
    mutate: mutateJobs,
  } = usePipelineJobs({
    state: stateFilter !== "ALL" ? stateFilter : undefined,
    search: searchQuery || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
  });

  /**
   * usePipelineJobDetail fetches detailed job info including checkpoints
   * from GET /api/v1/jobs/{id} when a job is selected.
   */
  const {
    jobDetail,
    isLoading: detailLoading,
    error: detailError,
  } = usePipelineJobDetail(selectedJobId);

  // ── WebSocket for Real-Time Updates ─────────────────────────────────
  /**
   * WebSocket connection for live job status per §8.2.1.
   * Connects to WS /api/v1/jobs/{id}/status when a job is selected.
   * Updates are merged into the SWR cache for seamless UI updates.
   */
  const { lastMessage, connectionState } = useWebSocket(
    selectedJobId ? `/api/v1/jobs/${selectedJobId}/status` : null
  );

  /**
   * Merge WebSocket updates into the job detail.
   * When a status message arrives, update the local cache without
   * waiting for the next SWR revalidation cycle.
   */
  useEffect(() => {
    if (lastMessage && selectedJobId) {
      try {
        const update = JSON.parse(lastMessage);
        mutateJobs();
      } catch {
        console.error("[PipelineMonitoring] Failed to parse WebSocket message");
      }
    }
  }, [lastMessage, selectedJobId, mutateJobs]);

  // ── Handlers ────────────────────────────────────────────────────────

  /**
   * handleResumeJob — POST /api/v1/jobs/{id}/resume
   *
   * Triggers pipeline resume from last successful checkpoint per §6.2
   * Operational Layer. Only available for jobs in ERROR state.
   * Admin only per Table 8-3.
   */
  const handleResumeJob = useCallback(
    async (jobId: string) => {
      if (user?.role !== "admin") {
        setResumeError("Only administrators can resume pipeline jobs.");
        return;
      }

      setResumingJobId(jobId);
      setResumeError(null);

      try {
        const response = await fetch(`/api/v1/jobs/${jobId}/resume`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail ||
              `Resume failed with status ${response.status}`
          );
        }

        /** Revalidate both the job list and detail after resume */
        await mutateJobs();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to resume pipeline job";
        setResumeError(message);
        console.error("[PipelineMonitoring] Resume error:", message);
      } finally {
        setResumingJobId(null);
      }
    },
    [user, mutateJobs]
  );

  /**
   * handleSelectJob — Select a job to view detailed checkpoint data.
   * Triggers the detail fetch and WebSocket connection.
   */
  const handleSelectJob = useCallback((jobId: string) => {
    setSelectedJobId((prev) => (prev === jobId ? null : jobId));
    setResumeError(null);
  }, []);

  /**
   * handleClearFilters — Reset all filter state to defaults.
   */
  const handleClearFilters = useCallback(() => {
    setStateFilter("ALL");
    setSearchQuery("");
    setDateFrom("");
    setDateTo("");
  }, []);

  // ── Computed Values ─────────────────────────────────────────────────

  /**
   * Compute summary statistics from the current job list.
   * Used for the status summary bar at the top of the page.
   */
  const summaryStats = useMemo(() => {
    if (!jobs || jobs.length === 0) {
      return {
        total: 0,
        running: 0,
        complete: 0,
        error: 0,
        pending: 0,
        avgDuration: 0,
      };
    }

    const running = jobs.filter(
      (j: PipelineJob) =>
        j.status === "RUNNING" ||
        j.status === "TRANSCRIPT_REFINEMENT" ||
        j.status === "STORYBOARD_GENERATION" ||
        j.status === "MEDIA_GENERATION" ||
        j.status === "MANIFEST_GENERATION" ||
        j.status === "AUDIO_GENERATION" ||
        j.status === "TALKING_HEAD_RENDER" ||
        j.status === "PROTOTYPE_DRAFT" ||
        j.status === "FINAL_RENDER"
    ).length;

    const complete = jobs.filter(
      (j: PipelineJob) => j.status === "COMPLETE"
    ).length;

    const error = jobs.filter(
      (j: PipelineJob) => j.status === "ERROR"
    ).length;

    const pending = jobs.filter(
      (j: PipelineJob) => j.status === "PENDING" || j.status === "DRAFT"
    ).length;

    /** Calculate average duration from completed jobs */
    const completedJobs = jobs.filter(
      (j: PipelineJob) =>
        j.status === "COMPLETE" && j.started_at && j.completed_at
    );

    const avgDuration =
      completedJobs.length > 0
        ? completedJobs.reduce((sum: number, j: PipelineJob) => {
            const start = new Date(j.started_at!).getTime();
            const end = new Date(j.completed_at!).getTime();
            return sum + (end - start);
          }, 0) / completedJobs.length
        : 0;

    return {
      total: jobs.length,
      running,
      complete,
      error,
      pending,
      avgDuration,
    };
  }, [jobs]);

  /**
   * Format milliseconds duration to human-readable string.
   * E.g., 125000 → "2m 5s"
   */
  const formatDuration = useCallback((ms: number): string => {
    if (ms <= 0) return "—";
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    }
    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    }
    return `${seconds}s`;
  }, []);

  /**
   * Format ISO date string to localized display format.
   */
  const formatDate = useCallback((dateStr: string | null): string => {
    if (!dateStr) return "—";
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  }, []);

  /**
   * Get the fallback level badge color based on the level.
   * L1 = primary (green), L2 = first fallback (yellow),
   * L3 = second fallback (orange), L4 = last resort (red), DLQ = critical.
   */
  const getFallbackBadgeColor = useCallback(
    (level: FallbackLevel): string => {
      switch (level) {
        case "L1":
          return "bg-green-100 text-green-800";
        case "L2":
          return "bg-yellow-100 text-yellow-800";
        case "L3":
          return "bg-orange-100 text-orange-800";
        case "L4":
          return "bg-red-100 text-red-700";
        case "DLQ":
          return "bg-red-200 text-red-900 font-bold";
        default:
          return "bg-gray-100 text-gray-600";
      }
    },
    []
  );

  // ── Render ──────────────────────────────────────────────────────────

  /** Redirect viewers — they have no access per Table 8-3 */
  if (user && user.role === "viewer") {
    return null;
  }

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600">
            Pipeline Monitoring Error
          </h3>
          <p className="mt-2 text-sm text-gray-600">
            An error occurred loading the pipeline monitor. Please refresh.
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
                Pipeline Progress Tracker
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                §8.2.1 — Real-time pipeline monitoring with stage DAG,
                checkpoints, and resume controls
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* WebSocket connection indicator */}
              <div className="flex items-center gap-1.5">
                <div
                  className={`h-2.5 w-2.5 rounded-full ${
                    connectionState === "CONNECTED"
                      ? "bg-green-500 animate-pulse"
                      : connectionState === "CONNECTING"
                      ? "bg-yellow-500 animate-pulse"
                      : "bg-gray-400"
                  }`}
                />
                <span className="text-xs text-gray-500">
                  {connectionState === "CONNECTED"
                    ? "Live"
                    : connectionState === "CONNECTING"
                    ? "Connecting…"
                    : "Polling"}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* ── Summary Statistics Bar ──────────────────────────────── */}
        <div className="bg-white border-b border-gray-200 px-6 py-3">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Total Jobs
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {summaryStats.total}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Running
              </p>
              <p className="mt-1 text-2xl font-bold text-blue-600">
                {summaryStats.running}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Complete
              </p>
              <p className="mt-1 text-2xl font-bold text-green-600">
                {summaryStats.complete}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Error
              </p>
              <p className="mt-1 text-2xl font-bold text-red-600">
                {summaryStats.error}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Pending
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-600">
                {summaryStats.pending}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Avg Duration
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {formatDuration(summaryStats.avgDuration)}
              </p>
            </div>
          </div>
        </div>

        <div className="px-6 py-6">
          {/* ── Filters ─────────────────────────────────────────── */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
            <div className="flex flex-wrap items-end gap-4">
              {/* State filter */}
              <div className="flex-1 min-w-[160px]">
                <label
                  htmlFor="state-filter"
                  className="block text-xs font-medium text-gray-700 mb-1"
                >
                  Job State
                </label>
                <select
                  id="state-filter"
                  value={stateFilter}
                  onChange={(e) => setStateFilter(e.target.value)}
                  className="w-full rounded-md border-gray-300 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                >
                  {JOB_STATE_FILTERS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Search */}
              <div className="flex-1 min-w-[200px]">
                <label
                  htmlFor="search-query"
                  className="block text-xs font-medium text-gray-700 mb-1"
                >
                  Search Projects
                </label>
                <input
                  id="search-query"
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Project name or job ID…"
                  className="w-full rounded-md border-gray-300 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>

              {/* Date range */}
              <div className="min-w-[140px]">
                <label
                  htmlFor="date-from"
                  className="block text-xs font-medium text-gray-700 mb-1"
                >
                  From
                </label>
                <input
                  id="date-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full rounded-md border-gray-300 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>
              <div className="min-w-[140px]">
                <label
                  htmlFor="date-to"
                  className="block text-xs font-medium text-gray-700 mb-1"
                >
                  To
                </label>
                <input
                  id="date-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-full rounded-md border-gray-300 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>

              {/* Clear filters */}
              <button
                type="button"
                onClick={handleClearFilters}
                className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900
                  hover:bg-gray-100 rounded-md transition-colors"
              >
                Clear Filters
              </button>
            </div>
          </div>

          {/* ── Loading State ───────────────────────────────────── */}
          {jobsLoading && (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          )}

          {/* ── Error State ─────────────────────────────────────── */}
          {jobsError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <div className="flex items-center gap-2">
                <svg
                  className="h-5 w-5 text-red-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
                  />
                </svg>
                <p className="text-sm text-red-700">
                  Failed to load pipeline jobs. Please try again.
                </p>
              </div>
            </div>
          )}

          {/* ── Resume Error Alert ──────────────────────────────── */}
          {resumeError && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <svg
                    className="h-5 w-5 text-amber-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126Z"
                    />
                  </svg>
                  <p className="text-sm text-amber-700">{resumeError}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setResumeError(null)}
                  className="text-amber-500 hover:text-amber-700"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* ── Job List & DAG ──────────────────────────────────── */}
          {!jobsLoading && !jobsError && jobs && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left panel: Job list */}
              <div className="lg:col-span-1">
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                    <h2 className="text-sm font-semibold text-gray-700">
                      Pipeline Jobs ({jobs.length})
                    </h2>
                  </div>
                  <div className="divide-y divide-gray-100 max-h-[calc(100vh-320px)] overflow-y-auto">
                    {jobs.length === 0 ? (
                      <div className="p-6 text-center text-sm text-gray-500">
                        No pipeline jobs match the current filters.
                      </div>
                    ) : (
                      jobs.map((job: PipelineJob) => (
                        <button
                          key={job.id}
                          type="button"
                          onClick={() => handleSelectJob(job.id)}
                          className={`w-full text-left px-4 py-3 hover:bg-gray-50
                            transition-colors ${
                              selectedJobId === job.id
                                ? "bg-blue-50 border-l-4 border-blue-500"
                                : ""
                            }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-gray-900 truncate">
                                {job.project_name}
                              </p>
                              <p className="text-xs text-gray-500 mt-0.5">
                                Job #{job.id.slice(0, 8)} •{" "}
                                {formatDate(job.created_at)}
                              </p>
                            </div>
                            <div className="ml-3 flex items-center gap-2">
                              {/* Status badge */}
                              <span
                                className={`inline-flex items-center px-2 py-0.5
                                  rounded-full text-xs font-medium ${
                                    job.status === "COMPLETE"
                                      ? "bg-green-100 text-green-800"
                                      : job.status === "ERROR"
                                      ? "bg-red-100 text-red-800"
                                      : job.status === "PENDING" ||
                                        job.status === "DRAFT"
                                      ? "bg-gray-100 text-gray-700"
                                      : "bg-blue-100 text-blue-800"
                                  }`}
                              >
                                {job.status}
                              </span>
                              {/* Fallback level badge per §6.3 */}
                              {job.fallback_level &&
                                job.fallback_level !== "L1" && (
                                  <span
                                    className={`inline-flex items-center px-1.5
                                      py-0.5 rounded text-xs font-medium
                                      ${getFallbackBadgeColor(
                                        job.fallback_level
                                      )}`}
                                  >
                                    {job.fallback_level}
                                  </span>
                                )}
                            </div>
                          </div>

                          {/* Progress bar for running jobs */}
                          {job.progress !== undefined && job.progress < 100 && (
                            <div className="mt-2 w-full bg-gray-200 rounded-full h-1.5">
                              <div
                                className="bg-blue-600 h-1.5 rounded-full transition-all
                                  duration-300"
                                style={{ width: `${job.progress}%` }}
                              />
                            </div>
                          )}

                          {/* ETA for running jobs */}
                          {job.estimated_completion && (
                            <p className="mt-1 text-xs text-gray-400">
                              ETA:{" "}
                              {formatDate(job.estimated_completion)}
                            </p>
                          )}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Right panel: DAG + Detail */}
              <div className="lg:col-span-2">
                {selectedJobId ? (
                  <div className="space-y-6">
                    {/* DAG Visualization */}
                    <div className="bg-white rounded-lg border border-gray-200 p-6">
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-semibold text-gray-700">
                          Stage DAG — Pipeline Execution Graph
                        </h2>
                        {/* Resume button — admin only, ERROR state only */}
                        {user?.role === "admin" &&
                          jobDetail?.status === "ERROR" && (
                            <button
                              type="button"
                              onClick={() =>
                                handleResumeJob(selectedJobId)
                              }
                              disabled={resumingJobId === selectedJobId}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5
                                text-sm font-medium text-white bg-blue-600
                                hover:bg-blue-700 rounded-md shadow-sm
                                disabled:opacity-50 disabled:cursor-not-allowed
                                transition-colors"
                            >
                              {resumingJobId === selectedJobId ? (
                                <>
                                  <LoadingSpinner size="sm" />
                                  Resuming…
                                </>
                              ) : (
                                <>
                                  <svg
                                    className="h-4 w-4"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    strokeWidth={2}
                                    stroke="currentColor"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z"
                                    />
                                  </svg>
                                  Resume from Checkpoint
                                </>
                              )}
                            </button>
                          )}
                      </div>

                      {detailLoading ? (
                        <div className="flex justify-center py-8">
                          <LoadingSpinner size="md" />
                        </div>
                      ) : detailError ? (
                        <p className="text-sm text-red-600 text-center py-8">
                          Failed to load job detail.
                        </p>
                      ) : jobDetail ? (
                        <PipelineDAG
                          stages={PIPELINE_STAGES}
                          stageLabels={STAGE_LABELS}
                          checkpoints={jobDetail.checkpoints}
                          currentStage={jobDetail.current_stage}
                          jobStatus={jobDetail.status}
                          fallbackLevel={jobDetail.fallback_level}
                        />
                      ) : null}
                    </div>

                    {/* Checkpoint Details Table */}
                    {jobDetail && jobDetail.checkpoints && (
                      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                          <h2 className="text-sm font-semibold text-gray-700">
                            Checkpoint Data — §6.2 Operational Layer
                          </h2>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Stage
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Status
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Started
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Completed
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Duration
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Retries
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Fallback
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                  Node
                                </th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {PIPELINE_STAGES.map((stage) => {
                                const cp = jobDetail.checkpoints?.find(
                                  (c: CheckpointData) => c.stage === stage
                                );
                                const duration =
                                  cp?.started_at && cp?.completed_at
                                    ? new Date(cp.completed_at).getTime() -
                                      new Date(cp.started_at).getTime()
                                    : 0;

                                return (
                                  <tr
                                    key={stage}
                                    className={
                                      cp?.status === "RUNNING"
                                        ? "bg-blue-50"
                                        : cp?.status === "FAILED"
                                        ? "bg-red-50"
                                        : ""
                                    }
                                  >
                                    <td className="px-4 py-2 text-sm font-medium text-gray-900">
                                      {STAGE_LABELS[stage]}
                                    </td>
                                    <td className="px-4 py-2">
                                      <span
                                        className={`inline-flex items-center px-2
                                          py-0.5 rounded-full text-xs font-medium
                                          ${
                                            cp
                                              ? STATUS_COLORS[cp.status]
                                              : "bg-gray-100 text-gray-500"
                                          }`}
                                      >
                                        {cp?.status || "PENDING"}
                                      </span>
                                    </td>
                                    <td className="px-4 py-2 text-xs text-gray-500">
                                      {formatDate(cp?.started_at || null)}
                                    </td>
                                    <td className="px-4 py-2 text-xs text-gray-500">
                                      {formatDate(cp?.completed_at || null)}
                                    </td>
                                    <td className="px-4 py-2 text-xs text-gray-600 font-mono">
                                      {formatDuration(duration)}
                                    </td>
                                    <td className="px-4 py-2 text-xs text-gray-600">
                                      {cp?.retry_count ?? "—"}
                                    </td>
                                    <td className="px-4 py-2">
                                      {cp?.fallback_level && (
                                        <span
                                          className={`inline-flex items-center
                                            px-1.5 py-0.5 rounded text-xs font-medium
                                            ${getFallbackBadgeColor(
                                              cp.fallback_level
                                            )}`}
                                        >
                                          {cp.fallback_level}
                                        </span>
                                      )}
                                    </td>
                                    <td className="px-4 py-2 text-xs text-gray-500">
                                      {cp?.node_id || "—"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Error Details — shown for ERROR jobs */}
                    {jobDetail && jobDetail.status === "ERROR" && (
                      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-red-800 mb-2">
                          Error Details
                        </h3>
                        <pre className="text-xs text-red-700 bg-red-100 rounded p-3 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                          {jobDetail.error_message || "No error details available."}
                        </pre>
                        {jobDetail.error_stage && (
                          <p className="mt-2 text-xs text-red-600">
                            Failed at stage:{" "}
                            <strong>
                              {STAGE_LABELS[jobDetail.error_stage as PipelineStage] ||
                                jobDetail.error_stage}
                            </strong>
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
                    <svg
                      className="mx-auto h-12 w-12 text-gray-400"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1}
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z"
                      />
                    </svg>
                    <h3 className="mt-4 text-sm font-medium text-gray-900">
                      Select a Pipeline Job
                    </h3>
                    <p className="mt-1 text-sm text-gray-500">
                      Click a job in the left panel to view its stage DAG
                      and checkpoint details.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}
