"use client";

import React, { useCallback, useMemo } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { GPUNode } from "@/types/monitoring";

/**
 * §8.2.2 GPU Fleet Status — Per-GPU Node Card
 *
 * Displays comprehensive GPU metrics for a single node:
 * - GPU model name and compute capability
 * - VRAM usage: total/used (progress bar, color-coded by utilization)
 *   - Green: <70%, Amber: 70–90%, Red: >90%
 * - Temperature gauge per §8.1.5:
 *   - Green: <70°C, Amber: 70–85°C, Red: >85°C
 * - GPU utilization percentage with visual indicator
 * - Power draw vs TDP (Thermal Design Power)
 * - Active job: job ID, pipeline stage, progress
 * - CPU and RAM mini-bars for system resource context
 * - Node status badge: ONLINE / OFFLINE / DRAINING
 * - Drain toggle button (admin only per §5.2.1)
 *
 * Data sourced from:
 * - GET /api/v1/gpu/nodes — node status and metrics
 * - nvidia-gpu-exporter metrics (§13.1 Table 13-1):
 *   ivgs_gpu_utilization_pct, ivgs_gpu_vram_used_mb
 * - node-exporter metrics: CPU, RAM
 */

interface GPUNodeCardProps {
  /** GPU node data from the fleet status API */
  node: GPUNode;
  /** Human-readable GPU label (e.g., "NVIDIA A6000 (48 GB)") */
  gpuLabel: string;
  /** Whether the current user is admin (for drain toggle) */
  isAdmin: boolean;
  /** Whether a drain toggle is in progress for this node */
  isDraining: boolean;
  /** Callback to toggle drain mode on this node */
  onDrainToggle: (nodeId: string) => void;
}

/**
 * Temperature color thresholds per §8.1.5 Node Monitor Page:
 * - green <70°C
 * - amber 70–85°C
 * - red >85°C
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
 * - Green: <70%
 * - Amber: 70–90%
 * - Red: >90% (per Table 13-3 GPUVRAMHigh alert)
 */
const getVRAMColor = (percent: number): string => {
  if (percent >= 90) return "bg-red-500";
  if (percent >= 70) return "bg-amber-500";
  return "bg-blue-500";
};

/**
 * Node status badge colors
 */
const STATUS_BADGE_STYLES: Record<string, string> = {
  ONLINE: "bg-green-100 text-green-800",
  OFFLINE: "bg-red-100 text-red-800",
  DRAINING: "bg-amber-100 text-amber-800",
};

export default function GPUNodeCard({
  node,
  gpuLabel,
  isAdmin,
  isDraining,
  onDrainToggle,
}: GPUNodeCardProps): React.ReactElement {
  // ── Computed Metrics ────────────────────────────────────────────────

  /** VRAM utilization percentage */
  const vramPercent = useMemo((): number => {
    if (!node.total_vram_mb || node.total_vram_mb === 0) return 0;
    return Math.round(((node.used_vram_mb || 0) / node.total_vram_mb) * 100);
  }, [node.total_vram_mb, node.used_vram_mb]);

  /** Power draw percentage vs TDP */
  const powerPercent = useMemo((): number => {
    if (!node.tdp_watts || node.tdp_watts === 0) return 0;
    return Math.round(((node.power_draw_watts || 0) / node.tdp_watts) * 100);
  }, [node.power_draw_watts, node.tdp_watts]);

  /** Temperature with safe default */
  const temperature = node.temperature_c ?? 0;

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
          node.status === "OFFLINE"
            ? "border-red-200 opacity-75"
            : node.status === "DRAINING"
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
              node.status === "ONLINE"
                ? "bg-green-500"
                : node.status === "DRAINING"
                ? "bg-amber-500 animate-pulse"
                : "bg-red-500"
            }`}
          />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              {node.node_id}
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
            {node.status}
          </span>
          {/* Drain toggle — admin only */}
          {isAdmin && node.total_vram_mb > 0 && (
            <button
              type="button"
              onClick={() => onDrainToggle(node.node_id)}
              disabled={isDraining}
              className={`px-2 py-1 text-xs font-medium rounded transition-colors
                ${
                  node.status === "DRAINING"
                    ? "bg-green-50 text-green-700 border border-green-200 hover:bg-green-100"
                    : "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100"
                }
                disabled:opacity-50 disabled:cursor-not-allowed`}
              title={
                node.status === "DRAINING"
                  ? "Click to undrain (resume scheduling)"
                  : "Click to drain (stop scheduling new jobs)"
              }
            >
              {isDraining ? (
                <LoadingSpinner size="sm" />
              ) : node.status === "DRAINING" ? (
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
        {node.total_vram_mb > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-600">VRAM</span>
              <span className="text-xs text-gray-500">
                {formatVRAM(node.used_vram_mb || 0)} /{" "}
                {formatVRAM(node.total_vram_mb)}
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
        {node.total_vram_mb > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">
              GPU Utilization
            </span>
            <div className="flex items-center gap-2">
              <div className="w-20 bg-gray-200 rounded-full h-1.5">
                <div
                  className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(node.utilization_pct || 0, 100)}%`,
                  }}
                />
              </div>
              <span className="text-xs font-mono text-gray-700 w-10 text-right">
                {node.utilization_pct ?? 0}%
              </span>
            </div>
          </div>
        )}

        {/* Temperature */}
        {node.total_vram_mb > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">
              Temperature
            </span>
            <div className="flex items-center gap-2">
              <div className="w-20 bg-gray-200 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all duration-300 ${getTemperatureBarColor(
                    temperature
                  )}`}
                  style={{
                    width: `${Math.min((temperature / 100) * 100, 100)}%`,
                  }}
                />
              </div>
              <span
                className={`text-xs font-mono w-12 text-right font-medium ${getTemperatureColor(
                  temperature
                )}`}
              >
                {temperature}°C
              </span>
            </div>
          </div>
        )}

        {/* Power Draw */}
        {node.power_draw_watts !== undefined && node.tdp_watts && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">
              Power
            </span>
            <span className="text-xs text-gray-500">
              {node.power_draw_watts}W / {node.tdp_watts}W TDP ({powerPercent}%)
            </span>
          </div>
        )}

        {/* CPU / RAM Mini-bars */}
        <div className="grid grid-cols-2 gap-3 pt-1 border-t border-gray-100">
          <div>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[10px] text-gray-500">CPU</span>
              <span className="text-[10px] text-gray-500">
                {node.cpu_percent ?? 0}%
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1">
              <div
                className={`h-1 rounded-full ${
                  (node.cpu_percent ?? 0) > 85
                    ? "bg-red-500"
                    : "bg-blue-400"
                }`}
                style={{
                  width: `${Math.min(node.cpu_percent ?? 0, 100)}%`,
                }}
              />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[10px] text-gray-500">RAM</span>
              <span className="text-[10px] text-gray-500">
                {node.ram_percent ?? 0}%
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1">
              <div
                className={`h-1 rounded-full ${
                  (node.ram_percent ?? 0) > 90
                    ? "bg-red-500"
                    : "bg-purple-400"
                }`}
                style={{
                  width: `${Math.min(node.ram_percent ?? 0, 100)}%`,
                }}
              />
            </div>
          </div>
        </div>

        {/* Active Job */}
        {node.active_job && (
          <div className="pt-2 border-t border-gray-100">
            <p className="text-xs font-medium text-gray-600 mb-1">
              Active Job
            </p>
            <div className="bg-gray-50 rounded p-2">
              <p className="text-xs text-gray-900 font-mono">
                {(node.active_job as import('@/types/monitoring').GPUActiveJob).job_id.slice(0, 12)}…
              </p>
              <p className="text-[10px] text-gray-500 mt-0.5">
                Stage: {(node.active_job as import('@/types/monitoring').GPUActiveJob).stage} •{" "}
                {(node.active_job as import('@/types/monitoring').GPUActiveJob).model_name}
              </p>
              {(node.active_job as import('@/types/monitoring').GPUActiveJob).progress !== undefined && (
                <div className="mt-1 w-full bg-gray-200 rounded-full h-1">
                  <div
                    className="bg-blue-500 h-1 rounded-full"
                    style={{
                      width: `${Math.min((node.active_job as import('@/types/monitoring').GPUActiveJob).progress ?? 0, 100)}%`,
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Queue Depth */}
        {(node.queued_jobs ?? 0) > 0 && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Queued Jobs</span>
            <span className="font-medium text-amber-600">
              {node.queued_jobs}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
