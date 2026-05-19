"use client";

import React from "react";
import type { NodeStatus } from "@/types/api";

/**
 * §8.1.5 Node Monitor — Node Card
 *
 * Each card shows:
 *   - Node name, online/offline status
 *   - GPU model
 *   - VRAM total/used (progress bar)
 *   - GPU utilization %
 *   - GPU temperature: green <70°C / amber 70–85°C / red >85°C
 *   - GPU power draw vs TDP
 *   - CPU/RAM mini-bars
 *   - Current active job
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
  /**
   * GPU temperature color coding per §8.1.5:
   *   green  < 70°C
   *   amber  70–85°C
   *   red    > 85°C
   */
  const getTempColor = (temp: number): string => {
    if (temp < 70) return "text-green-400";
    if (temp <= 85) return "text-yellow-400";
    return "text-red-400";
  };

  const getTempBgColor = (temp: number): string => {
    if (temp < 70) return "bg-green-500";
    if (temp <= 85) return "bg-yellow-500";
    return "bg-red-500";
  };

  /** VRAM usage percentage */
  const vramPercent =
    node.vram_total_mb > 0
      ? (node.vram_used_mb / node.vram_total_mb) * 100
      : 0;

  /** VRAM bar color */
  const vramColor =
    vramPercent > 90
      ? "bg-red-500"
      : vramPercent > 70
      ? "bg-yellow-500"
      : "bg-blue-500";

  return (
    <div
      className={`bg-gray-800 border border-gray-700 rounded-xl p-5 transition-all ${
        onClick
          ? "cursor-pointer hover:border-gray-600 hover:shadow-lg hover:shadow-blue-900/10"
          : ""
      }`}
      onClick={onClick ? () => onClick(node) : undefined}
    >
      {/* Header: Node name + status */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              node.is_online
                ? "bg-green-400 animate-pulse"
                : "bg-red-500"
            }`}
          />
          <h3 className="text-sm font-bold text-white">{node.node_name}</h3>
        </div>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            node.is_online
              ? "bg-green-900/30 text-green-400"
              : "bg-red-900/30 text-red-400"
          }`}
        >
          {node.is_online ? "Online" : "Offline"}
        </span>
      </div>

      {/* GPU Model */}
      <p className="text-xs text-gray-400 mb-3">{node.gpu_model}</p>

      {/* VRAM Bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span>VRAM</span>
          <span>
            {(node.vram_used_mb / 1024).toFixed(1)} /{" "}
            {(node.vram_total_mb / 1024).toFixed(1)} GB
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
            {node.gpu_utilization_percent}%
          </span>
        </div>

        {/* Temperature */}
        <div className="text-center">
          <span className="text-xs text-gray-500 block">Temp</span>
          <span
            className={`text-sm font-bold ${getTempColor(
              node.gpu_temperature_c
            )}`}
          >
            {node.gpu_temperature_c}°C
          </span>
        </div>

        {/* Power */}
        <div className="text-center">
          <span className="text-xs text-gray-500 block">Power</span>
          <span className="text-sm font-bold text-white">
            {node.gpu_power_draw_w}/{node.gpu_tdp_w}W
          </span>
        </div>
      </div>

      {/* CPU / RAM Mini-Bars */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div>
          <div className="flex items-center justify-between text-[10px] text-gray-500 mb-0.5">
            <span>CPU</span>
            <span>{node.cpu_utilization_percent}%</span>
          </div>
          <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-cyan-500 rounded-full transition-all"
              style={{
                width: `${Math.min(node.cpu_utilization_percent, 100)}%`,
              }}
            />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between text-[10px] text-gray-500 mb-0.5">
            <span>RAM</span>
            <span>{node.ram_utilization_percent}%</span>
          </div>
          <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 rounded-full transition-all"
              style={{
                width: `${Math.min(node.ram_utilization_percent, 100)}%`,
              }}
            />
          </div>
        </div>
      </div>

      {/* Active Job */}
      <div className="border-t border-gray-700 pt-3">
        {node.active_job ? (
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            <span className="text-xs text-gray-300 truncate flex-1">
              {node.active_job.project_name} — {node.active_job.stage}
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
