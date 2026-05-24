"use client";

import React, { useState, useMemo, useCallback, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";


import { useAuth } from "@/hooks/useAuth";
import { useCompositionTimeline } from "@/hooks/useMonitoring";
import TimelineEditor from "@/components/monitoring/TimelineEditor";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  CompositionManifest,
  TimelineSegment,
  TimelineLayer,
  ManifestLockStatus,
  RenderSegmentStatus,
} from "@/types/monitoring";

/**
 * §8.2.5 Composition Timeline Editor
 *
 * Horizontal timeline editor for composition manifests with:
 * - Scene-by-scene horizontal timeline with duration visualization
 * - Layer tracks: background, talking head, lower-third, captions, audio
 * - Color coding by segment status (pending/rendering/complete/failed)
 * - Zoom and pan controls for navigating long compositions
 * - Manifest lock status indicator (draft/locked per §6.1 Stage 4)
 * - Failed segment retry button (POST /api/v1/jobs/{id}/resume)
 * - Per-segment progress bars for active renders
 * - Overall render progress percentage with ETA
 *
 * Data sources:
 *   - GET /api/v1/jobs/{id}/manifest — composition manifest with timeline JSON
 *   - POST /api/v1/jobs/{id}/manifest/lock — freeze timeline (§5.2.5)
 *   - POST /api/v1/jobs/{id}/manifest/validate — validate asset checksums
 *   - GET /api/v1/jobs/{id}/checkpoints — render segment status
 *
 * Layer stack per Table 6-3:
 *   - Background: scene image / video clip / animation
 *   - Talking Head: lip-synced presenter (chroma-key or PiP)
 *   - Lower Third: scene title / key term overlay (Remotion-rendered)
 *   - Captions: burned-in subtitles from WhisperX timestamps
 *   - Audio: TTS voice track
 *
 * RBAC per Table 8-3:
 *   - admin: full access (lock, validate, retry)
 *   - operator: read-only timeline view
 *   - viewer: no access (redirected)
 */

/** Layer definitions matching Table 6-3 Video Composition Layer Stack */
const TIMELINE_LAYERS: { id: TimelineLayer; label: string; color: string }[] = [
  { id: "BACKGROUND", label: "Background", color: "#3B82F6" },
  { id: "TALKING_HEAD", label: "Talking Head", color: "#8B5CF6" },
  { id: "LOWER_THIRD", label: "Lower Third", color: "#10B981" },
  { id: "CAPTIONS", label: "Captions", color: "#F59E0B" },
  { id: "AUDIO", label: "Audio", color: "#EF4444" },
];

/** Segment status colors matching §8.2.5 */
const SEGMENT_STATUS_COLORS: Partial<Record<RenderSegmentStatus, string>> = {
  PENDING: "#D1D5DB",
  RENDERING: "#60A5FA",
  COMPLETE: "#34D399",
  FAILED: "#F87171",
};

function CompositionTimelinePageInner(): React.ReactElement | null {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  /** Job ID from query parameter: /monitoring/timeline?jobId=xxx */
  const jobId = searchParams.get("jobId");

  useEffect(() => {
    if (user && user.role === "viewer") {
      router.push("/");
    }
  }, [user, router]);

  // ── State ───────────────────────────────────────────────────────────
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [panOffset, setPanOffset] = useState<number>(0);
  const [jobIdInput, setJobIdInput] = useState<string>(jobId || "");
  const [activeJobId, setActiveJobId] = useState<string | null>(jobId);
  const [lockInProgress, setLockInProgress] = useState<boolean>(false);
  const [validateInProgress, setValidateInProgress] = useState<boolean>(false);
  const [retrySegmentId, setRetrySegmentId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // ── Data Fetching ───────────────────────────────────────────────────
  /**
   * useCompositionTimeline fetches from GET /api/v1/jobs/{id}/manifest.
   * Polling interval: 10 seconds for active renders, 60 seconds otherwise.
   */
  const {
    manifest,
    segments,
    renderProgress,
    isLoading,
    error,
    mutate: mutateManifest,
  } = useCompositionTimeline(activeJobId);

  // ── Handlers ────────────────────────────────────────────────────────

  /**
   * handleLoadJob — Set the active job ID to load its composition manifest.
   */
  const handleLoadJob = useCallback(() => {
    if (jobIdInput.trim()) {
      setActiveJobId(jobIdInput.trim());
      setActionError(null);
      setActionSuccess(null);
    }
  }, [jobIdInput]);

  /**
   * handleLockManifest — POST /api/v1/jobs/{id}/manifest/lock
   *
   * Freezes the composition manifest per §6.1 Stage 4.
   * After locking, no modifications are allowed; regeneration requires
   * a new manifest. Admin only per Table 8-3.
   */
  const handleLockManifest = useCallback(async () => {
    if (!activeJobId || user?.role !== "admin") return;

    if (
      !window.confirm(
        "Lock this composition manifest? After locking, no modifications are allowed."
      )
    ) {
      return;
    }

    setLockInProgress(true);
    setActionError(null);

    try {
      const response = await fetch(
        `/api/v1/jobs/${activeJobId}/manifest/lock`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `Lock failed: ${response.status}`
        );
      }

      setActionSuccess("Manifest locked successfully.");
      await mutateManifest();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to lock manifest";
      setActionError(message);
    } finally {
      setLockInProgress(false);
    }
  }, [activeJobId, user, mutateManifest]);

  /**
   * handleValidateManifest — POST /api/v1/jobs/{id}/manifest/validate
   *
   * Validates all referenced assets exist and checksums match per §5.2.5.
   * Admin only.
   */
  const handleValidateManifest = useCallback(async () => {
    if (!activeJobId || user?.role !== "admin") return;

    setValidateInProgress(true);
    setActionError(null);

    try {
      const response = await fetch(
        `/api/v1/jobs/${activeJobId}/manifest/validate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `Validation failed: ${response.status}`
        );
      }

      const result = await response.json();
      if (result.valid) {
        setActionSuccess("All assets validated — checksums match.");
      } else {
        setActionError(
          `Validation failed: ${result.errors?.length || 0} asset(s) with mismatched checksums.`
        );
      }
      await mutateManifest();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Validation request failed";
      setActionError(message);
    } finally {
      setValidateInProgress(false);
    }
  }, [activeJobId, user, mutateManifest]);

  /**
   * handleRetrySegment — Retry a failed render segment.
   * Uses POST /api/v1/jobs/{id}/resume with segment targeting.
   */
  const handleRetrySegment = useCallback(
    async (segmentId: string) => {
      if (!activeJobId || user?.role !== "admin") return;

      setRetrySegmentId(segmentId);
      setActionError(null);

      try {
        const response = await fetch(
          `/api/v1/jobs/${activeJobId}/resume`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${localStorage.getItem("access_token")}`,
            },
            body: JSON.stringify({ segment_id: segmentId }),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Retry failed: ${response.status}`
          );
        }

        setActionSuccess(`Segment ${segmentId.slice(0, 8)} retry queued.`);
        await mutateManifest();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Segment retry failed";
        setActionError(message);
      } finally {
        setRetrySegmentId(null);
      }
    },
    [activeJobId, user, mutateManifest]
  );

  // ── Computed Values ─────────────────────────────────────────────────

  /**
   * Calculate overall render progress from segment statuses.
   * Matches §8.2.5: "Overall render progress (%) with ETA."
   */
  const overallProgress = useMemo(() => {
    if (!segments || segments.length === 0) return { percent: 0, eta: null };

    const complete = segments.filter(
      (s: TimelineSegment) => s.status === "COMPLETE"
    ).length;
    const percent = Math.round((complete / segments.length) * 100);

    /** Estimate ETA from average segment render time */
    const completedSegments = segments.filter(
      (s: TimelineSegment) =>
        s.status === "COMPLETE" && s.render_started_at && s.render_completed_at
    );

    let eta: string | null = null;
    if (completedSegments.length > 0) {
      const avgTime =
        completedSegments.reduce((sum: number, s: TimelineSegment) => {
          const start = new Date(s.render_started_at!).getTime();
          const end = new Date(s.render_completed_at!).getTime();
          return sum + (end - start);
        }, 0) / completedSegments.length;

      const remaining = segments.filter(
        (s: TimelineSegment) => s.status !== "COMPLETE"
      ).length;

      if (remaining > 0) {
        const etaMs = remaining * avgTime;
        const etaDate = new Date(Date.now() + etaMs);
        eta = etaDate.toLocaleTimeString();
      }
    }

    return { percent, eta };
  }, [segments]);

  /** Lock status display */
  const lockStatus = useMemo((): ManifestLockStatus => {
    if (!manifest) return "UNKNOWN";
    return manifest.status === "locked" ? "LOCKED" : "DRAFT";
  }, [manifest]);

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600">
            Timeline Editor Error
          </h3>
          <p className="mt-2 text-sm text-gray-600">
            An error occurred loading the timeline editor. Please refresh.
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
                Composition Timeline
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                §8.2.5 — Horizontal timeline with layer visualization,
                segment progress, and lock management
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* Lock status indicator */}
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full
                  text-sm font-medium ${
                    lockStatus === "LOCKED"
                      ? "bg-green-100 text-green-800"
                      : lockStatus === "DRAFT"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-gray-100 text-gray-600"
                  }`}
              >
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                >
                  {lockStatus === "LOCKED" ? (
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
                    />
                  ) : (
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M13.5 10.5V6.75a4.5 4.5 0 1 1 9 0v3.75M3.75 21.75h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H3.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
                    />
                  )}
                </svg>
                {lockStatus === "LOCKED" ? "Manifest Locked" : lockStatus === "DRAFT" ? "Draft" : "—"}
              </span>
              {/* Render progress */}
              {manifest && (
                <span className="text-sm font-medium text-gray-700">
                  {overallProgress.percent}%
                  {overallProgress.eta && (
                    <span className="text-xs text-gray-500 ml-1">
                      ETA: {overallProgress.eta}
                    </span>
                  )}
                </span>
              )}
            </div>
          </div>
        </header>

        <div className="px-6 py-6">
          {/* ── Job Selector ──────────────────────────────────────── */}
          {!activeJobId && (
            <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">
                Load Composition Timeline
              </h2>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label
                    htmlFor="job-id-input"
                    className="block text-xs font-medium text-gray-700 mb-1"
                  >
                    Job ID
                  </label>
                  <input
                    id="job-id-input"
                    type="text"
                    value={jobIdInput}
                    onChange={(e) => setJobIdInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleLoadJob()}
                    placeholder="Enter render job ID…"
                    className="w-full rounded-md border-gray-300 text-sm shadow-sm
                      focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleLoadJob}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600
                    hover:bg-blue-700 rounded-md shadow-sm transition-colors"
                >
                  Load Timeline
                </button>
              </div>
            </div>
          )}

          {/* ── Alerts ────────────────────────────────────────────── */}
          {actionSuccess && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-green-700">{actionSuccess}</p>
                <button
                  type="button"
                  onClick={() => setActionSuccess(null)}
                  className="text-green-500 hover:text-green-700"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {actionError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-red-700">{actionError}</p>
                <button
                  type="button"
                  onClick={() => setActionError(null)}
                  className="text-red-500 hover:text-red-700"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* ── Loading ──────────────────────────────────────────── */}
          {activeJobId && isLoading && (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          )}

          {/* ── Error ────────────────────────────────────────────── */}
          {activeJobId && error && !isLoading && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <p className="text-sm text-red-700">
                Failed to load composition manifest. Please check the Job ID.
              </p>
            </div>
          )}

          {/* ── Timeline Editor ───────────────────────────────────── */}
          {activeJobId && !isLoading && !error && manifest && (
            <>
              {/* ── Toolbar ───────────────────────────────────────── */}
              <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    {/* Zoom controls */}
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-gray-500">
                        Zoom:
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setZoomLevel((z) => Math.max(0.25, z - 0.25))
                        }
                        className="p-1 rounded hover:bg-gray-100"
                      >
                        <svg className="h-4 w-4 text-gray-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14" />
                        </svg>
                      </button>
                      <span className="text-xs text-gray-600 font-mono w-10 text-center">
                        {(zoomLevel * 100).toFixed(0)}%
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setZoomLevel((z) => Math.min(4, z + 0.25))
                        }
                        className="p-1 rounded hover:bg-gray-100"
                      >
                        <svg className="h-4 w-4 text-gray-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setZoomLevel(1);
                          setPanOffset(0);
                        }}
                        className="px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100 rounded"
                      >
                        Fit
                      </button>
                    </div>

                    {/* Layer legend */}
                    <div className="flex items-center gap-3 ml-4">
                      {TIMELINE_LAYERS.map((layer) => (
                        <div
                          key={layer.id}
                          className="flex items-center gap-1"
                        >
                          <div
                            className="w-3 h-3 rounded-sm"
                            style={{ backgroundColor: layer.color }}
                          />
                          <span className="text-xs text-gray-600">
                            {layer.label}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Admin actions */}
                  {user?.role === "admin" && (
                    <div className="flex items-center gap-2">
                      {lockStatus === "DRAFT" && (
                        <button
                          type="button"
                          onClick={handleLockManifest}
                          disabled={lockInProgress}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5
                            text-xs font-medium text-amber-700 bg-amber-50
                            border border-amber-200 rounded-md hover:bg-amber-100
                            disabled:opacity-50 transition-colors"
                        >
                          {lockInProgress ? (
                            <LoadingSpinner size="sm" />
                          ) : (
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                            </svg>
                          )}
                          Lock Manifest
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={handleValidateManifest}
                        disabled={validateInProgress}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5
                          text-xs font-medium text-blue-700 bg-blue-50
                          border border-blue-200 rounded-md hover:bg-blue-100
                          disabled:opacity-50 transition-colors"
                      >
                        {validateInProgress ? (
                          <LoadingSpinner size="sm" />
                        ) : (
                          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                          </svg>
                        )}
                        Validate
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* ── Timeline Canvas ────────────────────────────────── */}
              <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                <TimelineEditor
                  manifest={manifest}
                  segments={segments || []}
                  layers={TIMELINE_LAYERS}
                  segmentStatusColors={SEGMENT_STATUS_COLORS}
                  zoomLevel={zoomLevel}
                  panOffset={panOffset}
                  onPanChange={setPanOffset}
                  isAdmin={user?.role === "admin"}
                  retrySegmentId={retrySegmentId}
                  onRetrySegment={handleRetrySegment}
                />
              </div>

              {/* ── Render Progress Bar ────────────────────────────── */}
              <div className="mt-4 bg-white rounded-lg border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">
                    Overall Render Progress
                  </span>
                  <span className="text-sm font-bold text-gray-900">
                    {overallProgress.percent}%
                    {overallProgress.eta && (
                      <span className="text-xs text-gray-500 font-normal ml-2">
                        ETA: {overallProgress.eta}
                      </span>
                    )}
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all duration-500 ${
                      overallProgress.percent === 100
                        ? "bg-green-500"
                        : "bg-blue-600"
                    }`}
                    style={{ width: `${overallProgress.percent}%` }}
                  />
                </div>
                {segments && (
                  <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
                    <span>
                      {segments.filter((s: TimelineSegment) => s.status === "COMPLETE").length}{" "}
                      complete
                    </span>
                    <span>
                      {segments.filter((s: TimelineSegment) => s.status === "RENDERING").length}{" "}
                      rendering
                    </span>
                    <span>
                      {segments.filter((s: TimelineSegment) => s.status === "PENDING").length}{" "}
                      pending
                    </span>
                    <span className="text-red-500">
                      {segments.filter((s: TimelineSegment) => s.status === "FAILED").length}{" "}
                      failed
                    </span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}

export default function CompositionTimelinePage(): React.ReactElement {
  return (
    <Suspense fallback={<LoadingSpinner size="lg" label="Loading timeline..." />}>
      <CompositionTimelinePageInner />
    </Suspense>
  );
}
