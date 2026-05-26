"use client";

import React from "react";
import type { NodeStatus } from "@/types/api";

/**
 * Node Monitor - Node Card (spec section 8.1.5)
 *
 * Consumed by /nodes page. Backed by the Phase 3 stub endpoint
 * GET /api/v1/nodes which serves a hardcoded NODE_TOPOLOGY (ivgs-api/
 * app/api/v1/nodes.py). The shape is NOT GpuNodeResponse - see
 * NodeStatus interface in types/api.ts for details.
 *
 * Phase 8 (GPU scheduler) will replace the stub with live metrics.
 * Until then:
 *   - status is always "online" (stub default)
 *   - gpu_utilization_pct, temperature_c, used_vram_mb are always 0
 *   - power_draw_w is undefined on the list endpoint
 *   - active_jobs is always []
 *
 * Field naming follows the stub's contract (hostname, node_id-as-string),
 * not GpuNodeResponse. Diverging type-design accepted because the stub
 * endpoint is owned separately and will be replaced wholesale in Phase 8.
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

  /** VRAM usage percentage. Phase 3 stub always sets used_vram_mb=0. */
  const vramPercent =
    node.total_vram_mb > 0
      ? (node.used_vram_mb / node.total_vram_mb) * 100
      : 0;

  /** VRAM bar color */
  const vramColor =
    vramPercent > 90
      ? "bg-red-500"
      : vramPercent > 70
      ? "bg-yellow-500"
      : "bg-blue-500";

  /** Status badge color triple. Phase 3 stub returns lowercase. */
  const statusKey = node.status.toLowerCase();
  const statusStyles =
    statusKey === "online"
      ? {
          dot: "bg-green-400 animate-pulse",
          badge: "bg-green-900/30 text-green-400",
        }
      : statusKey === "draining"
      ? {
          dot: "bg-yellow-400",
          badge: "bg-yellow-900/30 text-yellow-400",
        }
      : {
          dot: "bg-red-500",
          badge: "bg-red-900/30 text-red-400",
        };

  const statusLabel =
    statusKey.charAt(0).toUpperCase() + statusKey.slice(1);

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
            {node.hostname}
          </h3>
        </div>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusStyles.badge}`}
        >
          {statusLabel}
        </span>
      </div>

      {/* GPU Model (null for infrastructure node-01) */}
      <p className="text-xs text-gray-400 mb-3">
        {node.gpu_model ?? (
          <span className="italic text-gray-600">No GPU ({node.role})</span>
        )}
      </p>

      {/* VRAM Bar - rendered only for nodes with a GPU */}
      {node.total_vram_mb > 0 && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span>VRAM</span>
            <span>
              {(node.used_vram_mb / 1024).toFixed(1)} /{" "}
              {(node.total_vram_mb / 1024).toFixed(1)} GB
            </span>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${vramColor}`}
              style={{ width: `${Math.min(vramPercent, 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* GPU Stats Grid - rendered only for nodes with a GPU */}
      {node.total_vram_mb > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div className="text-center">
            <span className="text-xs text-gray-500 block">Util</span>
            <span className="text-sm font-bold text-white">
              {node.gpu_utilization_pct.toFixed(0)}%
            </span>
          </div>

          <div className="text-center">
            <span className="text-xs text-gray-500 block">Temp</span>
            <span
              className={`text-sm font-bold ${getTempColor(node.temperature_c)}`}
            >
              {node.temperature_c.toFixed(0)} C
            </span>
          </div>

          <div className="text-center">
            <span className="text-xs text-gray-500 block">Power</span>
            <span className="text-sm font-bold text-white">
              {node.power_draw_w !== undefined
                ? `${node.power_draw_w.toFixed(0)}W`
                : "—"}
            </span>
          </div>
        </div>
      )}

      {/* Detail Hint for Admin */}
      {showDetailHint && (
        <p className="text-[10px] text-gray-600 mt-2 text-center">
          Click for logs and details
        </p>
      )}
    </div>
  );
}
