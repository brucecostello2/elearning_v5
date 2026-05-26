"use client";

import React, { useCallback, useMemo } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { GPUNode } from "@/types/monitoring";

/**
 * GPU Fleet Status - Per-GPU Node Card (spec section 8.2.2)
 *
 * Displays GPU metrics for a single node:
 * - GPU model name and compute capability
 * - VRAM usage: total/used (progress bar, color-coded by utilization)
 *   - Green: <70%, Amber: 70-90%, Red: >90%
 * - Temperature gauge per spec section 8.1.5:
 *   - Green: <70 C, Amber: 70-85 C, Red: >85 C
 * - GPU utilization percentage with visual indicator
 * - Power draw vs TDP (when TDP known)
 * - Active job: job ID, project name, pipeline stage
 * - Node status badge: online / offline / draining
 * - Drain toggle button (admin only per spec 5.2.1)
 *
 * Field naming matches backend GpuNodeResponse exactly per
 * IVGS v5 Functional Specification Appendix C.4 and GPU Fleet Monitoring
 * Spec v1.1 section 6.0 (defect #6/#7 resolution).
 *
 * CPU, RAM, and queue-depth metrics are not surfaced because the backend
 * does not collect them per spec 4.2 Table 19.
 *
 * active_job fields not on backend ActiveJobSummary (model_name, progress)
 * are not surfaced. Per-job progress lives on RenderJob, not on the GPU
 * snapshot - separate change request to add to ActiveJobSummary if needed.
 *
 * Data sourced from:
 * - GET /api/v1/gpu/nodes (snapshot, this card)
 * - GET /api/v1/gpu/utilization/history (time-series, sibling chart)
 */

interface GPUNodeCardProps {
  /** GPU node data from the fleet status API */
  node: GPUNode;
  /** Human-readable GPU label (e.g., "NVIDIA RTX 5000 Pro Blackwell (48 GB)") */
  gpuLabel: string;
  /** Whether the current user is admin (for drain toggle) */
  isAdmin: boolean;
  /** Whether a drain toggle is in progress for this node */
  isDraining: boolean;
  /**
   * Callback to toggle drain mode on this node.
   * Receives node.id (UUID) - backend drain endpoint takes UUID.
   */
  onDrainToggle: (nodeId: string) => void;
}

/**
 * Temperature color thresholds per spec section 8.1.5:
 * green <70 C, amber 70-85 C, red >85 C
 */
const getTemperatureColor = (tempC: number): string => {
  if (tempC >= 85) return "text-red-600";
  if (tempC >= 70) return "text-amber-500";
  return "text-green-600";
};

const getTemperatureBarColor = (tempC: number): string => {
  if (tempC >= 85) return "bg-red-500";
  if (tempC >= 70) return "bg-amber-500";
  return "bg-green-500";
};

/**
 * VRAM utilization color thresholds:
 * Green <70%, Amber 70-90%, Red >90% (per Table 13-3 GPUVRAMHigh)
 */
const getVRAMColor = (percent: number): string => {
  if (percent >= 90) return "bg-red-500";
  if (percent >= 70) return "bg-amber-500";
  return "bg-blue-500";
};

/**
 * Node status badge colors. Keys are lowercase per backend convention.
 */
const STATUS_BADGE_STYLES: Record<string, string> = {
  online: "bg-green-100 text-green-800",
  offline: "bg-red-100 text-red-800",
  draining: "bg-amber-100 text-amber-800",
};

export default function GPUNodeCard({
  node,
  gpuLabel,
  isAdmin,
  isDraining,
  onDrainToggle,
}: GPUNodeCardProps): React.ReactElement {
  // ── Computed Metrics ────────────────────────────────────────────────

  /** VRAM utilization percentage (null-safe for unknown total) */
  const vramPercent = useMemo((): number => {
    if (!node.total_vram_mb || node.total_vram_mb === 0) return 0;
    return Math.round((node.used_vram_mb / node.total_vram_mb) * 100);
  }, [node.total_vram_mb, node.used_vram_mb]);

  /** Power draw percentage vs TDP (null-safe; 0 when TDP unknown) */
  const powerPercent = useMemo((): number => {
    if (!node.power_tdp_w || node.power_tdp_w === 0) return 0;
    return Math.round((node.power_draw_w / node.power_tdp_w) * 100);
  }, [node.power_draw_w, node.power_tdp_w]);

  const statusLabel =
    node.status.charAt(0).toUpperCase() + node.status.slice(1);

  /** First active job (UI displays one at a time per spec section 8.2.2) */
  const activeJob =
    node.active_jobs && node.active_jobs.length > 0
      ? node.active_jobs[0]
      : null;

  /**
   * Format VRAM values to GB with one decimal place.
   */
  const formatVRAM = useCallback((mb: number): string => {
    return `${(mb / 1024).toFixed(1)} GB`;
  }, []);

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div
      className={`bg-white rounded-lg border overflow-hidden transition-shadow
        hover:shadow-md ${
          node.status === "offline"
            ? "border-red-200 opacity-75"
            : node.status === "draining"
            ? "border-amber-200"
            : "border-gray-200"
        }`}
    >
      {/* ── Card Header ──────────────────────────────────────────── */}
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Status dot */}
          <div
            className={`h-2.5 w-2.5 rounded-full ${
              node.status === "online"
                ? "bg-green-500"
                : node.status === "draining"
                ? "bg-amber-500 animate-pulse"
                : "bg-red-500"
            }`}
          />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              {node.node_hostname}
            </h3>
            <p className="text-xs text-gray-500">{gpuLabel}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Status badge */}
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs
              font-medium ${
                STATUS_BADGE_STYLES[node.status] || "bg-gray-100 text-gray-600"
              }`}
          >
            {statusLabel}
          </span>
          {/* Drain toggle - admin only, only meaningful for nodes with a GPU */}
          {isAdmin && (node.total_vram_mb ?? 0) > 0 && (
            <button
              type="button"
              onClick={() => onDrainToggle(node.id)}
              disabled={isDraining}
              className={`px-2 py-1 text-xs font-medium rounded transition-colors
                ${
                  node.status === "draining"
                    ? "bg-green-50 text-green-700 border border-green-200 hover:bg-green-100"
                    : "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100"
                }
                disabled:opacity-50 disabled:cursor-not-allowed`}
              title={
                node.status === "draining"
                  ? "Click to undrain (resume scheduling)"
                  : "Click to drain (stop scheduling new jobs)"
              }
            >
              {isDraining ? (
                <LoadingSpinner size="sm" />
              ) : node.status === "draining" ? (
                "Undrain"
              ) : (
                "Drain"
              )}
            </button>
          )}
        </div>
      </div>

      {/* ── Card Body ────────────────────────────────────────────── */}
      <div className="p-4 space-y-3">
        {/* VRAM Usage */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-600">VRAM</span>
              <span className="text-xs text-gray-500">
                {formatVRAM(node.used_vram_mb)} /{" "}
                {formatVRAM(node.total_vram_mb!)}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${getVRAMColor(
                  vramPercent
                )}`}
                style={{ width: `${Math.min(vramPercent, 100)}%` }}
              />
            </div>
            <p className="mt-0.5 text-right text-xs text-gray-400">
              {vramPercent}%
            </p>
          </div>
        )}

        {/* GPU Utilization */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">
              GPU Utilization
            </span>
            <div className="flex items-center gap-2">
              <div className="w-20 bg-gray-200 rounded-full h-1.5">
                <div
                  className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(node.gpu_utilization_pct, 100)}%`,
                  }}
                />
              </div>
              <span className="text-xs font-mono text-gray-700 w-10 text-right">
                {node.gpu_utilization_pct.toFixed(0)}%
              </span>
            </div>
          </div>
        )}

        {/* Temperature */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">
              Temperature
            </span>
            <div className="flex items-center gap-2">
              <div className="w-20 bg-gray-200 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all duration-300 ${getTemperatureBarColor(
                    node.temperature_c
                  )}`}
                  style={{
                    width: `${Math.min((node.temperature_c / 100) * 100, 100)}%`,
                  }}
                />
              </div>
              <span
                className={`text-xs font-mono w-12 text-right font-medium ${getTemperatureColor(
                  node.temperature_c
                )}`}
              >
                {node.temperature_c.toFixed(0)} C
              </span>
            </div>
          </div>
        )}

        {/* Power Draw - shows draw alone if TDP not known */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">Power</span>
            <span className="text-xs text-gray-500">
              {node.power_tdp_w
                ? `${node.power_draw_w.toFixed(0)}W / ${node.power_tdp_w}W TDP (${powerPercent}%)`
                : `${node.power_draw_w.toFixed(0)}W`}
            </span>
          </div>
        )}

        {/* Active Job */}
        {activeJob && (
          <div className="pt-2 border-t border-gray-100">
            <p className="text-xs font-medium text-gray-600 mb-1">
              Active Job
            </p>
            <div className="bg-gray-50 rounded p-2">
              <p className="text-xs text-gray-900 font-mono">
                {activeJob.job_id.slice(0, 12)}…
              </p>
              <p className="text-[10px] text-gray-500 mt-0.5">
                {activeJob.project_name ?? "—"}
                {activeJob.stage && ` • ${activeJob.stage}`}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
