"use client";

import React from "react";
import type { NodeStatus } from "@/types/api";

/**
 * Node Monitor — Node Card (spec section 8.1.5)
 *
 * Each card shows:
 *   - Node hostname, status (online/offline/draining)
 *   - GPU model
 *   - VRAM total/used (progress bar)
 *   - GPU utilization %
 *   - GPU temperature: green <70 C / amber 70-85 C / red >85 C
 *   - GPU power draw vs TDP (when TDP known)
 *   - Current active job (first of active_jobs[])
 *
 * Field naming matches backend GpuNodeResponse exactly per
 * IVGS v5 Functional Specification Appendix C.4 and GPU Fleet Monitoring
 * Spec v1.1 section 6.0. No optional aliased fields.
 *
 * CPU and RAM utilization are not surfaced because the backend
 * does not collect them per spec section 4.2 Table 19.
 *
 * Renders backend values directly. Status badge reflects node.status;
 * live metrics render what backend returns regardless of state. When
 * Phase 8 GPU Scheduler populates real-time values, this component
 * displays them with no code change.
 */

interface NodeCardProps {
  node: NodeStatus;
  onClick?: (node: NodeStatus) => void;
  showDetailHint?: boolean;
}

export default function NodeCard({
  node,
  onClick,
  showDetailHint = false,
}: NodeCardProps): React.ReactElement {
  const getTempColor = (temp: number): string => {
    if (temp < 70) return "text-green-400";
    if (temp <= 85) return "text-yellow-400";
    return "text-red-400";
  };

  /** VRAM usage percentage (null-safe; 0 when total unknown) */
  const vramPercent =
    node.total_vram_mb && node.total_vram_mb > 0
      ? (node.used_vram_mb / node.total_vram_mb) * 100
      : 0;

  /** VRAM bar color */
  const vramColor =
    vramPercent > 90
      ? "bg-red-500"
      : vramPercent > 70
      ? "bg-yellow-500"
      : "bg-blue-500";

  /** Status badge color triple (dot, badge bg, badge text) */
  const statusStyles =
    node.status === "online"
      ? {
          dot: "bg-green-400 animate-pulse",
          badge: "bg-green-900/30 text-green-400",
        }
      : node.status === "draining"
      ? {
          dot: "bg-yellow-400",
          badge: "bg-yellow-900/30 text-yellow-400",
        }
      : {
          dot: "bg-red-500",
          badge: "bg-red-900/30 text-red-400",
        };

  const statusLabel =
    node.status.charAt(0).toUpperCase() + node.status.slice(1);

  const activeJob =
    node.active_jobs && node.active_jobs.length > 0
      ? node.active_jobs[0]
      : null;

  return (
    <div
      className={`bg-gray-800 border border-gray-700 rounded-xl p-5 transition-all ${
        onClick
          ? "cursor-pointer hover:border-gray-600 hover:shadow-lg hover:shadow-blue-900/10"
          : ""
      }`}
      onClick={onClick ? () => onClick(node) : undefined}
    >
      {/* Header: Node hostname + status */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${statusStyles.dot}`}
          />
          <h3 className="text-sm font-bold text-white">
            {node.node_hostname}
          </h3>
        </div>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusStyles.badge}`}
        >
          {statusLabel}
        </span>
      </div>

      {/* GPU Model */}
      <p className="text-xs text-gray-400 mb-3">
        {node.gpu_model ?? (
          <span className="italic text-gray-600">Unknown GPU</span>
        )}
      </p>

      {/* VRAM Bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span>VRAM</span>
          <span>
            {node.total_vram_mb
              ? `${(node.used_vram_mb / 1024).toFixed(1)} / ${(
                  node.total_vram_mb / 1024
                ).toFixed(1)} GB`
              : "Unknown"}
          </span>
        </div>
        <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${vramColor}`}
            style={{ width: `${Math.min(vramPercent, 100)}%` }}
          />
        </div>
      </div>

      {/* GPU Stats Grid */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        {/* GPU Utilization */}
        <div className="text-center">
          <span className="text-xs text-gray-500 block">Util</span>
          <span className="text-sm font-bold text-white">
            {node.gpu_utilization_pct.toFixed(0)}%
          </span>
        </div>

        {/* Temperature */}
        <div className="text-center">
          <span className="text-xs text-gray-500 block">Temp</span>
          <span
            className={`text-sm font-bold ${getTempColor(node.temperature_c)}`}
          >
            {node.temperature_c.toFixed(0)} C
          </span>
        </div>

        {/* Power */}
        <div className="text-center">
          <span className="text-xs text-gray-500 block">Power</span>
          <span className="text-sm font-bold text-white">
            {node.power_tdp_w
              ? `${node.power_draw_w.toFixed(0)}/${node.power_tdp_w}W`
              : `${node.power_draw_w.toFixed(0)}W`}
          </span>
        </div>
      </div>

      {/* Active Job */}
      <div className="border-t border-gray-700 pt-3">
        {activeJob ? (
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            <span className="text-xs text-gray-300 truncate flex-1">
              {activeJob.project_name ?? "—"} — {activeJob.stage ?? "—"}
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-600 italic">No active job</span>
        )}
      </div>

      {/* Detail Hint for Admin */}
      {showDetailHint && (
        <p className="text-[10px] text-gray-600 mt-2 text-center">
          Click for logs and details
        </p>
      )}
    </div>
  );
}
