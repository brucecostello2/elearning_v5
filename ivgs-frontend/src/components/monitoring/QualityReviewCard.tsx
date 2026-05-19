"use client";

import React, { useState, useCallback } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { FlaggedAsset, QualityMetricType } from "@/types/monitoring";

/**
 * §8.2.4 Quality Review Queue — Flagged Asset Card
 *
 * Displays a single flagged asset requiring human review:
 * - Thumbnail/preview: image src for images, video poster for video,
 *   waveform icon for audio
 * - Composite quality score: 0–100 with color coding
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
  metricLabels: Record<QualityMetricType, string>;
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
 * Quality score color thresholds:
 * - Green: ≥80 (good quality)
 * - Amber: 60–79 (marginal, flagged for review)
 * - Red: <60 (poor quality, likely rejection candidate)
 */
const getScoreColor = (score: number): string => {
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-amber-600";
  return "text-red-600";
};

const getScoreBgColor = (score: number): string => {
  if (score >= 80) return "bg-green-100";
  if (score >= 60) return "bg-amber-100";
  return "bg-red-100";
};

/**
 * Per-metric pass/fail determination.
 * Based on thresholds defined in the spec.
 */
const getMetricStatus = (
  metricType: QualityMetricType,
  value: number
): "pass" | "warning" | "fail" => {
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
      return "pass";
  }
};

const METRIC_STATUS_COLORS: Record<string, string> = {
  pass: "text-green-600",
  warning: "text-amber-600",
  fail: "text-red-600",
};

const METRIC_STATUS_BG: Record<string, string> = {
  pass: "bg-green-50",
  warning: "bg-amber-50",
  fail: "bg-red-50",
};

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
   * Handle rejection with reason.
   */
  const handleReject = useCallback(() => {
    onReject(rejectReason || undefined);
    setShowRejectForm(false);
    setRejectReason("");
  }, [onReject, rejectReason]);

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
      {/* ── Asset Preview ──────────────────────────────────────────── */}
      <div className="relative h-40 bg-gray-100 flex items-center justify-center">
        {asset.thumbnail_url ? (
          <img
            src={asset.thumbnail_url}
            alt={`Asset ${asset.asset_id.slice(0, 8)}`}
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-4xl">
            {ASSET_TYPE_ICONS[asset.asset_type] || "📄"}
          </span>
        )}
        {/* Type badge overlay */}
        <span className="absolute top-2 left-2 px-2 py-0.5 bg-black/60 text-white text-xs rounded">
          {asset.asset_type}
        </span>
        {/* Score badge overlay */}
        <div
          className={`absolute top-2 right-2 px-2 py-0.5 rounded text-sm
            font-bold ${getScoreBgColor(asset.quality_score)} ${getScoreColor(
            asset.quality_score
          )}`}
        >
          {asset.quality_score}
        </div>
      </div>

      {/* ── Card Body ──────────────────────────────────────────────── */}
      <div className="p-4 space-y-3">
        {/* Context */}
        <div>
          <p className="text-sm font-medium text-gray-900 truncate">
            {asset.project_name}
          </p>
          <p className="text-xs text-gray-500">
            Scene {asset.scene_index} • Asset {asset.asset_id.slice(0, 8)}…
          </p>
        </div>

        {/* Scores summary */}
        <div className="grid grid-cols-2 gap-2">
          <div className="text-center p-2 bg-gray-50 rounded">
            <p className="text-xs text-gray-500">Quality</p>
            <p className={`text-lg font-bold ${getScoreColor(asset.quality_score)}`}>
              {asset.quality_score}
            </p>
          </div>
          <div className="text-center p-2 bg-gray-50 rounded">
            <p className="text-xs text-gray-500">Safety</p>
            <p
              className={`text-lg font-bold ${getScoreColor(
                (asset.safety_score ?? 1) * 100
              )}`}
            >
              {((asset.safety_score ?? 1) * 100).toFixed(0)}
            </p>
          </div>
        </div>

        {/* Per-metric breakdown */}
        {asset.metrics && asset.metrics.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-600">Metric Breakdown</p>
            {asset.metrics.map((metric) => {
              const status = getMetricStatus(metric.type, metric.value);
              return (
                <div
                  key={metric.type}
                  className={`flex items-center justify-between px-2 py-1
                    rounded text-xs ${METRIC_STATUS_BG[status]}`}
                >
                  <span className="text-gray-700">
                    {metricLabels[metric.type] || metric.type}
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
          <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
            <button
              type="button"
              onClick={onApprove}
              disabled={isProcessing}
              className="flex-1 inline-flex items-center justify-center gap-1
                px-3 py-2 text-sm font-medium text-green-700 bg-green-50
                border border-green-200 rounded-md hover:bg-green-100
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
                px-3 py-2 text-sm font-medium text-red-700 bg-red-50
                border border-red-200 rounded-md hover:bg-red-100
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
          <div className="pt-2 border-t border-gray-100 space-y-2">
            <input
              type="text"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Rejection reason (optional)…"
              className="w-full rounded-md border-gray-300 text-xs shadow-sm
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
                className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-900"
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
