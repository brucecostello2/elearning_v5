"use client";

import React, { useState, useCallback, useMemo, useRef } from "react";
import { useAssetObjectUrl, useInView } from "@/hooks/useAssetMedia";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { FlaggedAsset, QualityMetricType } from "@/types/monitoring";

/**
 * §8.2.4 Quality Review Queue — Flagged Asset Card
 *
 * Displays a single flagged asset requiring human review:
 * - Thumbnail/preview: image src for images, video poster for video,
 *   waveform icon for audio
 * - Composite quality score: 0.0–1.0 on the wire (schemas/quality.py:71),
 *   shown as a percentage
 * - Safety score: content safety check result
 * - Per-metric breakdown table:
 *   - CLIP score (image similarity to prompt)
 *   - SNR (audio signal-to-noise ratio, threshold >20dB per §6.1 Stage 5)
 *   - Frame consistency (video temporal coherence)
 *   - Lip-sync alignment (talking head, threshold >0.85 per §7.1.7)
 *   - Resolution check (meets target dimensions)
 *   - Duration check (within expected range)
 * - Project name and scene index for context
 * - Approve / Reject buttons (with optional rejection reason)
 *
 * Approve: POST /api/v1/quality/{score_id}/approve
 * Reject: POST /api/v1/quality/{score_id}/reject
 * Both decisions logged in audit_log.
 */

interface QualityReviewCardProps {
  /** Flagged asset data */
  asset: FlaggedAsset;
  /** Human-readable metric labels */
  metricLabels: Partial<Record<QualityMetricType, string>>;
  /** Whether the user can act on this asset (RBAC check done by parent) */
  canAct: boolean;
  /** Whether an action is in progress for this card */
  isProcessing: boolean;
  /** Approve callback */
  onApprove: () => void;
  /** Reject callback with optional reason */
  onReject: (reason?: string) => void;
}

/**
 * Quality score color thresholds.
 *
 * WP-60 Task 6/7. THE SCALE WAS WRONG, AND IT COLOURED EVERY SCORE RED.
 *
 * `schemas/quality.py:71` pins both scores as `Field(ge=0.0, le=1.0)` — a
 * FRACTION. These thresholds were 80/60, i.e. a 0–100 scale, taken from this
 * file's own header comment ("composite quality score: 0–100"). So the live
 * row's `quality_score` of 0.7222 — a decent 72% — was compared against 60,
 * fell through to `text-red-600`, and was printed verbatim as "0.7222".
 * A confident wrong colour on a review queue sends the reviewer to reject
 * something the scorer passed.
 *
 * The thresholds are now expressed in the wire's own units and the value is
 * rendered as a percentage. `null` never reaches here: see `scorePercent`.
 */
const GOOD_SCORE = 0.8;
const MARGINAL_SCORE = 0.6;

const getScoreColor = (score: number): string => {
  if (score >= GOOD_SCORE) return "text-green-700 dark:text-green-400";
  if (score >= MARGINAL_SCORE) return "text-amber-700 dark:text-amber-400";
  return "text-red-700 dark:text-red-400";
};

const getScoreBgColor = (score: number): string => {
  if (score >= GOOD_SCORE) return "bg-green-100 dark:bg-green-900/50";
  if (score >= MARGINAL_SCORE) return "bg-amber-100 dark:bg-amber-900/50";
  return "bg-red-100 dark:bg-red-900/50";
};

/** A 0–1 score as a whole-number percentage, or null when absent. */
const scorePercent = (score: number | null | undefined): number | null =>
  typeof score === "number" && Number.isFinite(score)
    ? Math.round(score * 100)
    : null;

/** The one styling class pair used when a score is absent. Never a colour. */
const ABSENT_SCORE_CLASS = "text-gray-400 dark:text-gray-500";

/**
 * Per-metric pass/fail determination.
 * Based on thresholds defined in the spec.
 */
const getMetricStatus = (
  metricType: QualityMetricType,
  value: number
): "pass" | "warning" | "fail" | "unscored" => {
  switch (metricType) {
    case "CLIP_SCORE":
      return value >= 0.25 ? "pass" : value >= 0.15 ? "warning" : "fail";
    case "SNR":
      /** §6.1 Stage 5: SNR > 20 dB quality gate */
      return value >= 20 ? "pass" : value >= 15 ? "warning" : "fail";
    case "FRAME_CONSISTENCY":
      return value >= 0.9 ? "pass" : value >= 0.8 ? "warning" : "fail";
    case "LIP_SYNC_SCORE":
      /** §7.1.7: lip-sync score threshold > 0.85 */
      return value >= 0.85 ? "pass" : value >= 0.7 ? "warning" : "fail";
    case "RESOLUTION_CHECK":
      return value >= 1 ? "pass" : "fail";
    case "DURATION_CHECK":
      return value >= 1 ? "pass" : "fail";
    case "SAFETY_SCORE":
      return value >= 0.9 ? "pass" : value >= 0.7 ? "warning" : "fail";
    default:
      /* WP-60 Task 6(b)/7. This used to `return "pass"`, painting a green
         row for any key it did not recognise. On the live flagged row EVERY
         numeric key is unrecognised — `scoring_details` carries
         `actual_fps`, `frame_count`, `actual_width`, `actual_height`,
         `check_coverage`, `actual_duration_seconds` — so the whole breakdown
         rendered green "pass" while two of the recorded checks had in fact
         FAILED (`resolution_ok: false`, `duration_ok: false`).
         There is no threshold for these keys, so there is no verdict to give:
         they are shown as measurements, in neutral grey. */
      return "unscored";
  }
};

/**
 * WP-60 Task 6(b). THE METRIC ROWS WERE UNREADABLE IN DARK MODE.
 *
 * The row background was a hardcoded light tint (`bg-green-50`) with NO dark
 * variant, while the label beside it carried `dark:text-gray-300` and the
 * value `text-green-600`. In dark mode that is pale grey on pale green and
 * mid-green on pale green: both "ghosted", which is what the screenshot shows.
 * The background never switched because it was never told to.
 *
 * Every row colour now has a dark counterpart, and the label uses a token that
 * has contrast against BOTH tints rather than against the page.
 */
const METRIC_STATUS_COLORS: Record<string, string> = {
  pass: "text-green-800 dark:text-green-300",
  warning: "text-amber-800 dark:text-amber-300",
  fail: "text-red-800 dark:text-red-300",
  unscored: "text-gray-700 dark:text-gray-300",
};

const METRIC_STATUS_BG: Record<string, string> = {
  pass: "bg-green-50 dark:bg-green-950/60",
  warning: "bg-amber-50 dark:bg-amber-950/60",
  fail: "bg-red-50 dark:bg-red-950/60",
  unscored: "bg-gray-50 dark:bg-gray-800/60",
};

const METRIC_LABEL_CLASS = "text-gray-800 dark:text-gray-200";

/** Asset type icons */
const ASSET_TYPE_ICONS: Record<string, string> = {
  IMAGE: "🖼️",
  VIDEO: "🎬",
  AUDIO: "🔊",
  ANIMATION: "✨",
  TALKING_HEAD: "🗣️",
};

export default function QualityReviewCard({
  asset,
  metricLabels,
  canAct,
  isProcessing,
  onApprove,
  onReject,
}: QualityReviewCardProps): React.ReactElement {
  const [showRejectForm, setShowRejectForm] = useState<boolean>(false);
  const [rejectReason, setRejectReason] = useState<string>("");

  /**
   * Numeric metrics out of `scoring_details`.
   *
   * The wire type is `Optional[Dict[str, Any]]`, so the values are not
   * guaranteed to be numbers; non-numeric entries are dropped rather than
   * fed to a threshold comparison that would silently read as "fail".
   */
  const scoringMetrics = useMemo<{ type: string; value: number }[]>(() => {
    const details = asset.scoring_details;
    if (!details || typeof details !== "object" || Array.isArray(details)) return [];
    return Object.entries(details)
      .filter(([, v]) => typeof v === "number" && Number.isFinite(v))
      .map(([type, value]) => ({ type, value: value as number }));
  }, [asset.scoring_details]);

  /**
   * WP-60 Task 6(c) — ORIENTATION, DERIVED FROM THE DIMENSIONS THAT ARE THERE.
   *
   * The live flagged row records `actual_width: 768, actual_height: 1408` on a
   * landscape project, and a warning that reads "Resolution mismatch: expected
   * 1920×1080, got 768×1408". Those numbers are NOT wrong and must not be
   * "corrected": 768×1408 is Wan2.2-Animate's native 9:16 output (MBCP work
   * order 1), and the mismatch is the finding.
   *
   * What the card was missing is that a reviewer had to do the arithmetic
   * themselves to see it. Orientation is derived here — never invented: if the
   * scorer did not record both dimensions, the badge is absent rather than
   * guessing "landscape" from a project that happens to be one.
   */
  const orientation = useMemo<{
    label: "portrait" | "landscape" | "square";
    width: number;
    height: number;
  } | null>(() => {
    const d = asset.scoring_details;
    if (!d || typeof d !== "object" || Array.isArray(d)) return null;
    const w = (d as Record<string, unknown>).actual_width;
    const h = (d as Record<string, unknown>).actual_height;
    if (
      typeof w !== "number" || !Number.isFinite(w) || w <= 0 ||
      typeof h !== "number" || !Number.isFinite(h) || h <= 0
    ) {
      return null;
    }
    return {
      label: h > w ? "portrait" : w > h ? "landscape" : "square",
      width: w,
      height: h,
    };
  }, [asset.scoring_details]);

  /* Both scores are 0–1 on the wire. `null` is a real answer — the live row has
     `safety_score: null` — and it is NOT 1.0. See the render below. */
  const qualityPct = scorePercent(asset.quality_score);
  const safetyPct = scorePercent(asset.safety_score);

  /**
   * Handle rejection with reason.
   */
  const handleReject = useCallback(() => {
    onReject(rejectReason || undefined);
    setShowRejectForm(false);
    setRejectReason("");
  }, [onReject, rejectReason]);

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden hover:shadow-md transition-shadow">
      {/* ── Asset Preview ──────────────────────────────────────────── */}
      <div className="relative h-40 bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
        {/* WP-40 addendum: `thumbnail_url` exists nowhere in ivgs-api, so this
            <img> never had a src. `asset_id` does exist, and the download
            proxy serves the real bytes. */}
        <FlaggedAssetPreview
          assetId={asset.asset_id}
          assetType={asset.asset_type}
          fallbackIcon={
            (asset.asset_type && ASSET_TYPE_ICONS[asset.asset_type.toUpperCase()]) ||
            "📄"
          }
        />
        {/* Type badge overlay */}
        <span className="absolute top-2 left-2 px-2 py-0.5 bg-black/60 text-white text-xs rounded">
          {asset.asset_type ?? "asset"}
        </span>
        {/* Orientation badge — WP-60 Task 6(c). Absent when the scorer did not
            record both dimensions; never guessed. */}
        {orientation && (
          <span
            className={`absolute bottom-2 left-2 px-2 py-0.5 rounded text-[11px]
              font-medium bg-black/70 text-white`}
            title={`Recorded output ${orientation.width}×${orientation.height} — ${orientation.label}. This is the asset's real size, not a target.`}
          >
            {orientation.label} {orientation.width}×{orientation.height}
          </span>
        )}
        {/* Score badge overlay */}
        <div
          className={`absolute top-2 right-2 px-2 py-0.5 rounded text-sm font-bold ${
            qualityPct !== null
              ? `${getScoreBgColor(asset.quality_score!)} ${getScoreColor(
                  asset.quality_score!
                )}`
              : `bg-gray-100 dark:bg-gray-800 ${ABSENT_SCORE_CLASS}`
          }`}
          title={
            qualityPct !== null
              ? "Composite quality score (0–100%)"
              : "No composite quality score was recorded for this asset"
          }
        >
          {qualityPct !== null ? `${qualityPct}%` : "not scored"}
        </div>
      </div>

      {/* ── Card Body ──────────────────────────────────────────────── */}
      <div className="p-4 space-y-3">
        {/* Context */}
        <div>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {asset.project_name ?? "Unknown project"}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {/* `scene_index` is not on this payload; the asset id is. */}
            Asset {asset.asset_id.slice(0, 8)}… • {asset.decision}
          </p>
        </div>

        {/* Scores summary */}
        {/* WP-60 Task 7. THE SAFETY TILE INVENTED A PERFECT SCORE.
            It read `((asset.safety_score ?? 1) * 100).toFixed(0)`, so an
            absent safety score rendered as a green "100" — the single most
            reassuring number this card can display, asserted on no evidence.
            `safety_score` is null on the live flagged row and on every row the
            CLIP scorer has not reached. Absent is now said in words. */}
        <div className="grid grid-cols-2 gap-2">
          <div className="text-center p-2 bg-gray-50 dark:bg-gray-950 rounded">
            <p className="text-xs text-gray-500 dark:text-gray-400">Quality</p>
            {qualityPct !== null ? (
              <p className={`text-lg font-bold ${getScoreColor(asset.quality_score!)}`}>
                {qualityPct}%
              </p>
            ) : (
              <p className={`text-xs leading-tight py-1 ${ABSENT_SCORE_CLASS}`}>
                not scored
              </p>
            )}
          </div>
          <div className="text-center p-2 bg-gray-50 dark:bg-gray-950 rounded">
            <p className="text-xs text-gray-500 dark:text-gray-400">Safety</p>
            {safetyPct !== null ? (
              <p className={`text-lg font-bold ${getScoreColor(asset.safety_score!)}`}>
                {safetyPct}%
              </p>
            ) : (
              <p
                className={`text-xs leading-tight py-1 ${ABSENT_SCORE_CLASS}`}
                title="No safety score was recorded for this asset. This is not the same as a safe result."
              >
                not scored
              </p>
            )}
          </div>
        </div>

        {/* Per-metric breakdown */}
        {/* The per-metric breakdown is `scoring_details` on the wire
            (schemas/quality.py:40); this read `metrics`, which is not a field
            the API sends, so no breakdown ever rendered. */}
        {scoringMetrics.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400">Metric Breakdown</p>
            {scoringMetrics.map((metric: { type: string; value: any }) => {
              const status = getMetricStatus(
                metric.type as QualityMetricType,
                metric.value
              );
              return (
                <div
                  key={metric.type}
                  className={`flex items-center justify-between px-2 py-1
                    rounded text-xs ${METRIC_STATUS_BG[status]}`}
                >
                  <span className={METRIC_LABEL_CLASS}>
                    {(metricLabels as Record<string, string>)[metric.type] || metric.type}
                  </span>
                  <span className={`font-mono font-medium ${METRIC_STATUS_COLORS[status]}`}>
                    {typeof metric.value === "number"
                      ? metric.value.toFixed(3)
                      : metric.value}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Actions ──────────────────────────────────────────────── */}
        {canAct && !showRejectForm && (
          <div className="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
            <button
              type="button"
              onClick={onApprove}
              disabled={isProcessing}
              className="flex-1 inline-flex items-center justify-center gap-1
                px-3 py-2 text-sm font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/40
                border border-green-200 dark:border-green-800 rounded-md hover:bg-green-100 dark:hover:bg-green-900/50
                disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isProcessing ? (
                <LoadingSpinner size="sm" />
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
              )}
              Approve
            </button>
            <button
              type="button"
              onClick={() => setShowRejectForm(true)}
              disabled={isProcessing}
              className="flex-1 inline-flex items-center justify-center gap-1
                px-3 py-2 text-sm font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/40
                border border-red-200 dark:border-red-800 rounded-md hover:bg-red-100 dark:hover:bg-red-900/50
                disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
              Reject
            </button>
          </div>
        )}

        {/* Reject form */}
        {canAct && showRejectForm && (
          <div className="pt-2 border-t border-gray-100 dark:border-gray-800 space-y-2">
            <input
              type="text"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Rejection reason (optional)…"
              className="w-full rounded-md border-gray-300 dark:border-gray-700 text-xs shadow-sm
                focus:border-blue-500 focus:ring-blue-500"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleReject}
                disabled={isProcessing}
                className="flex-1 px-3 py-1.5 text-xs font-medium text-white
                  bg-red-600 rounded hover:bg-red-700 disabled:opacity-50
                  transition-colors"
              >
                Confirm Reject
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowRejectForm(false);
                  setRejectReason("");
                }}
                className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Preview for a flagged asset.
 *
 * WP-60 Task 6(a) — WHY THE IMAGE WAS BROKEN, WHICH IS NOT WHAT WAS ASSUMED.
 *
 * The brief expected WP-57's gallery fix (a token-guarded route an `<img src>`
 * cannot reach) to be missing here. It is not: this card has used
 * `useAssetObjectUrl` — the same one mechanism — since WP-40, and the fetch
 * succeeds. Measured on the live queue instead:
 *
 *     GET /api/v1/quality/flagged  ->  asset_type: "video", mime video/mp4
 *
 * The card fetched 6 MB of h264 and handed the blob to an `<img>`. An `<img>`
 * cannot decode video, so the browser drew its broken-image glyph — and
 * because the FETCH succeeded, `error` stayed null and the honest fallback
 * never ran. A success path rendering a failure.
 *
 * This file's own docstring already said "Only images are shown inline: a
 * flagged video would download in full to render one frame". The sentence was
 * true of the intent and false of the code — nothing ever checked
 * `asset_type`. It does now, and the check comes BEFORE the fetch, so a
 * flagged video no longer pulls megabytes to fail with.
 *
 * Non-image assets show their type icon and say what they are. That is the
 * whole honest answer available here: the API image has no video decoder
 * (`/assets/{id}/thumbnail` answers 415 saying exactly that), so there is no
 * frame to show and inventing one is not an option.
 */
const INLINE_PREVIEW_TYPES = new Set(["image"]);

function FlaggedAssetPreview({
  assetId,
  assetType,
  fallbackIcon,
}: {
  assetId: string;
  assetType: string | null;
  fallbackIcon: React.ReactNode;
}): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const inView = useInView(containerRef);

  /* Decided before the request is made, not after it comes back. */
  const canRenderInline =
    typeof assetType === "string" &&
    INLINE_PREVIEW_TYPES.has(assetType.toLowerCase());

  const { url, error, isLoading } = useAssetObjectUrl(
    assetId,
    inView && canRenderInline,
  );

  return (
    <div
      ref={containerRef}
      className="w-full h-full flex flex-col items-center justify-center gap-1 px-2 text-center"
    >
      {canRenderInline && url && !error ? (
        <img
          src={url}
          alt={`Asset ${assetId.slice(0, 8)}`}
          className="w-full h-full object-cover"
        />
      ) : (
        <>
          <span className="text-4xl">{fallbackIcon}</span>
          {/* Three distinct states in words, the WP-57 gallery rule applied
              one level down: cannot be previewed / failed to load / loading. */}
          {!canRenderInline ? (
            <span className="text-[10px] leading-tight text-gray-500 dark:text-gray-400">
              no inline preview for {assetType ?? "this asset type"}
            </span>
          ) : error ? (
            <span className="text-[10px] leading-tight text-amber-600 dark:text-amber-400">
              preview failed to load
            </span>
          ) : isLoading ? (
            <span className="text-[10px] leading-tight text-gray-500 dark:text-gray-400">
              loading preview…
            </span>
          ) : null}
        </>
      )}
    </div>
  );
}
