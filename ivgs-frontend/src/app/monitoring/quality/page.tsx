"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useQualityReviewQueue } from "@/hooks/useMonitoring";
import QualityReviewCard from "@/components/monitoring/QualityReviewCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  FlaggedAsset,
  QualityDecision,
  QualityMetricType,
} from "@/types/monitoring";

/**
 * §8.2.4 Quality Review Queue
 *
 * Grid of assets flagged by the quality assurance pipeline (§11).
 * Each card displays:
 * - Asset thumbnail or preview (image/video/audio waveform)
 * - Quality score (0–100 composite)
 * - Safety score (content safety check)
 * - Per-metric breakdown: CLIP score, SNR (audio), frame consistency (video)
 * - Project name and scene context
 *
 * Actions (admin full / operator own projects):
 * - Approve: POST /api/v1/quality/{score_id}/approve
 *   Sets decision = approved, pipeline continues
 * - Reject: POST /api/v1/quality/{score_id}/reject
 *   Sets decision = rejected, triggers asset regeneration
 *
 * All decisions logged in audit_log table per §8.2.4.
 *
 * Data sources:
 *   - GET /api/v1/quality/flagged — paginated flagged assets (§5.2.3)
 *   - POST /api/v1/quality/{score_id}/approve — approve flagged asset
 *   - POST /api/v1/quality/{score_id}/reject — reject flagged asset
 *
 * RBAC per Table 8-3:
 *   - admin: full access + approve/reject all projects
 *   - operator: view + approve/reject own projects only
 *   - viewer: no access (redirected)
 */

/** Quality metric type labels for display */
const METRIC_LABELS: Partial<Record<QualityMetricType, string>> = {
  CLIP_SCORE: "CLIP Score",
  SNR: "Signal-to-Noise",
  FRAME_CONSISTENCY: "Frame Consistency",
  LIP_SYNC_SCORE: "Lip-Sync Alignment",
  RESOLUTION_CHECK: "Resolution",
  DURATION_CHECK: "Duration",
  SAFETY_SCORE: "Content Safety",
};

/** Sort options for the quality queue */
const SORT_OPTIONS = [
  { value: "quality_asc", label: "Quality Score (Low → High)" },
  { value: "quality_desc", label: "Quality Score (High → Low)" },
  { value: "date_desc", label: "Newest First" },
  { value: "date_asc", label: "Oldest First" },
  { value: "project", label: "By Project" },
] as const;

/** Asset type filter options */
const ASSET_TYPE_FILTERS = [
  { value: "ALL", label: "All Types" },
  { value: "IMAGE", label: "Images" },
  { value: "VIDEO", label: "Videos" },
  { value: "AUDIO", label: "Audio" },
  { value: "ANIMATION", label: "Animations" },
  { value: "TALKING_HEAD", label: "Talking Heads" },
] as const;

export default function QualityReviewPage(): React.ReactElement | null {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role === "viewer") {
      router.push("/");
    }
  }, [user, router]);

  // ── State ───────────────────────────────────────────────────────────
  const [sortBy, setSortBy] = useState<string>("quality_asc");
  const [assetTypeFilter, setAssetTypeFilter] = useState<string>("ALL");
  const [page, setPage] = useState<number>(1);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // ── Data Fetching ───────────────────────────────────────────────────
  /**
   * useQualityReviewQueue fetches from GET /api/v1/quality/flagged
   * with sorting and filtering. Polling interval: 30 seconds.
   */
  const {
    assets,
    totalCount,
    isLoading,
    error,
    mutate: mutateAssets,
  } = useQualityReviewQueue({
    sort: sortBy,
    assetType: assetTypeFilter !== "ALL" ? assetTypeFilter : undefined,
    page,
    pageSize: 12,
  });

  // ── Handlers ────────────────────────────────────────────────────────

  /**
   * handleApprove — POST /api/v1/quality/{score_id}/approve
   *
   * Approves a flagged asset, allowing the pipeline to continue.
   * Decision is recorded in audit_log per §8.2.4.
   */
  const handleApprove = useCallback(
    async (scoreId: string) => {
      setActionInProgress(scoreId);
      setActionError(null);
      setActionSuccess(null);

      try {
        const response = await fetch(
          `/api/v1/quality/${scoreId}/approve`,
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
            errorData?.detail || `Approve failed: ${response.status}`
          );
        }

        setActionSuccess(`Asset approved successfully.`);
        await mutateAssets();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to approve asset";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [mutateAssets]
  );

  /**
   * handleReject — POST /api/v1/quality/{score_id}/reject
   *
   * Rejects a flagged asset, triggering regeneration of the asset.
   * Decision is recorded in audit_log per §8.2.4.
   */
  const handleReject = useCallback(
    async (scoreId: string, reason?: string) => {
      setActionInProgress(scoreId);
      setActionError(null);
      setActionSuccess(null);

      try {
        const response = await fetch(
          `/api/v1/quality/${scoreId}/reject`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
            },
            body: JSON.stringify({ reason: reason || "Quality below threshold" }),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Reject failed: ${response.status}`
          );
        }

        setActionSuccess(`Asset rejected — regeneration queued.`);
        await mutateAssets();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to reject asset";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [mutateAssets]
  );

  /**
   * canActOnAsset — who may approve/reject.
   *
   * WP-40 addendum. This read `asset.project_owner_id`, which the API does
   * not send (`FlaggedAssetResponse`, schemas/quality.py:32), so the operator
   * branch compared `undefined === user.id` and was always false.
   *
   * It is corrected to admin-only rather than to some ownership rule, because
   * that is what the SERVER enforces: both `POST /quality/{id}/approve` and
   * `POST /quality/{id}/reject` are `Depends(require_admin)`
   * (quality.py:97, :137). An operator pressing these would be refused 403
   * whatever this function said. Mirroring the real guard is not a
   * loosening -- it is the UI stopping offering a control that cannot work.
   */
  const canActOnAsset = useCallback(
    (_asset: FlaggedAsset): boolean => user?.role === "admin",
    [user]
  );

  /** Total pages for pagination */
  const totalPages = useMemo(
    () => Math.ceil((totalCount || 0) / 12),
    [totalCount]
  );

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600 dark:text-red-400">
            Quality Review Error
          </h3>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            An error occurred loading the quality review queue. Please refresh.
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
                Quality Review Queue
              </h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                §8.2.4 — Flagged assets requiring human review per §11 Quality
                Assurance Pipeline
              </p>
            </div>
            <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-300">
              {totalCount ?? 0} flagged
            </span>
          </div>
        </header>

        <div className="px-6 py-6">
          {/* ── Filters & Sort ─────────────────────────────────────── */}
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 mb-6">
            <div className="flex flex-wrap items-end gap-4">
              <div className="min-w-[180px]">
                <label
                  htmlFor="asset-type"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Asset Type
                </label>
                <select
                  id="asset-type"
                  value={assetTypeFilter}
                  onChange={(e) => {
                    setAssetTypeFilter(e.target.value);
                    setPage(1);
                  }}
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                >
                  {ASSET_TYPE_FILTERS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="min-w-[220px]">
                <label
                  htmlFor="sort-by"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Sort By
                </label>
                <select
                  id="sort-by"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                >
                  {SORT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* ── Success/Error Alerts ───────────────────────────────── */}
          {actionSuccess && (
            <div className="bg-green-50 dark:bg-green-900/40 border border-green-200 dark:border-green-800 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-green-700 dark:text-green-300">{actionSuccess}</p>
                <button
                  type="button"
                  onClick={() => setActionSuccess(null)}
                  className="text-green-500 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {actionError && (
            <div className="bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-red-700 dark:text-red-300">{actionError}</p>
                <button
                  type="button"
                  onClick={() => setActionError(null)}
                  className="text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* ── Loading ──────────────────────────────────────────── */}
          {isLoading && (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          )}

          {/* ── Error ────────────────────────────────────────────── */}
          {error && !isLoading && (
            <div className="bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <p className="text-sm text-red-700 dark:text-red-300">
                Failed to load flagged assets. Please try again.
              </p>
            </div>
          )}

          {/* ── Asset Grid ───────────────────────────────────────── */}
          {!isLoading && !error && assets && (
            <>
              {assets.length === 0 ? (
                <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-12 text-center">
                  <svg
                    className="mx-auto h-12 w-12 text-green-600 dark:text-green-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                    />
                  </svg>
                  <h3 className="mt-4 text-sm font-medium text-gray-900 dark:text-gray-100">
                    All Clear
                  </h3>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    No assets currently flagged for review.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                  {assets.map((asset: FlaggedAsset) => (
                    <QualityReviewCard
                      /* WP-40 addendum: the score's primary key is `id` on
                         the wire (schemas/quality.py:35), not `score_id` --
                         which was undefined, so approve/reject POSTed to
                         /api/v1/quality/undefined/{approve,reject}. */
                      key={asset.id}
                      asset={asset}
                      metricLabels={METRIC_LABELS}
                      canAct={canActOnAsset(asset)}
                      isProcessing={actionInProgress === asset.id}
                      onApprove={() => handleApprove(asset.id)}
                      onReject={(reason) =>
                        handleReject(asset.id, reason)
                      }
                    />
                  ))}
                </div>
              )}

              {/* ── Pagination ──────────────────────────────────── */}
              {totalPages > 1 && (
                <div className="mt-6 flex items-center justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1.5 text-sm font-medium rounded-md border
                      border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-950
                      disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setPage((p) => Math.min(totalPages, p + 1))
                    }
                    disabled={page === totalPages}
                    className="px-3 py-1.5 text-sm font-medium rounded-md border
                      border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-950
                      disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}
