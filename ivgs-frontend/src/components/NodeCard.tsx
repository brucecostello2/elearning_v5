"use client";

import React from "react";
import type { NodeStatus } from "@/types/api";

/**
 * Node Monitor - Node Card (spec section 8.1.5)
 *
 * Consumed by /nodes page. Backed by GET /api/v1/nodes, which joins declared
 * topology with live reachability and GPU telemetry (ivgs-api/app/core/
 * node_health.py). The shape is NOT GpuNodeResponse - see NodeStatus in
 * types/api.ts.
 *
 * WP-24 (2026-08-23). This card used to draw a VRAM bar and a "0 C" temperature
 * for every node, because the endpoint hardcoded those fields to 0 and the card
 * rendered them unconditionally. Two rules now hold, and both matter:
 *
 *   1. A metric is drawn ONLY when a real reading exists. null means not
 *      measured, and shows as "no data" with the reason - never as 0.
 *   2. The VRAM bar is gated on an actual reading, not on total_vram_mb > 0.
 *      total_vram_mb is DECLARED capacity; gating on it drew a 0%-full bar for
 *      hardware nothing had read.
 *
 * Field naming follows the endpoint's contract (hostname, node_id-as-string),
 * not GpuNodeResponse.
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

  const hasGpu = node.gpu_model !== null;
  /** A reading exists only if the endpoint sent a number. null = not measured. */
  const vramRead = typeof node.used_vram_mb === "number";
  const utilRead = typeof node.gpu_utilization_pct === "number";
  const tempRead = typeof node.temperature_c === "number";
  const powerRead = typeof node.power_draw_w === "number";
  const anyRead = vramRead || utilRead || tempRead || powerRead;

  /** VRAM usage percentage - computed only against a real reading. */
  const vramPercent =
    vramRead && node.total_vram_mb > 0
      ? ((node.used_vram_mb as number) / node.total_vram_mb) * 100
      : 0;

  /** VRAM bar color */
  const vramColor =
    vramPercent > 90
      ? "bg-red-500"
      : vramPercent > 70
      ? "bg-yellow-500"
      : "bg-blue-500";

  /** Shown in place of a number when nothing measured it. */
  const noData = (
    <span className="text-sm font-medium text-gray-400 dark:text-gray-500">
      no data
    </span>
  );

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
      : statusKey === "unknown"
      ? {
          // Grey, not red. "We could not tell" must not look like "it is down" -
          // colouring unknown as offline is the same class of lie WP-24 removed,
          // just rendered in CSS instead of JSON.
          dot: "bg-gray-400",
          badge: "bg-gray-500/20 text-gray-500 dark:text-gray-400",
        }
      : {
          dot: "bg-red-500",
          badge: "bg-red-900/30 text-red-400",
        };

  const statusLabel =
    statusKey.charAt(0).toUpperCase() + statusKey.slice(1);

  return (
    <div
      className={`bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl p-5 transition-all ${
        onClick
          ? "cursor-pointer hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-lg hover:shadow-blue-900/10"
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
          <h3 className="text-sm font-bold text-gray-900 dark:text-white">
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
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {node.gpu_model ?? (
          <span className="italic text-gray-600 dark:text-gray-400">No GPU ({node.role})</span>
        )}
      </p>

      {/* VRAM: capacity is always declarable; the BAR needs a real reading. */}
      {hasGpu && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>VRAM</span>
            {vramRead ? (
              <span>
                {((node.used_vram_mb as number) / 1024).toFixed(1)} /{" "}
                {(node.total_vram_mb / 1024).toFixed(1)} GB
              </span>
            ) : (
              <span className="text-gray-400 dark:text-gray-500">
                no data / {(node.total_vram_mb / 1024).toFixed(1)} GB installed
              </span>
            )}
          </div>
          {vramRead ? (
            <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${vramColor}`}
                style={{ width: `${Math.min(vramPercent, 100)}%` }}
              />
            </div>
          ) : (
            /* Deliberately NOT a 0%-full bar: an empty bar reads as "measured
               and idle". A dashed rail reads as "nothing measured". */
            <div className="w-full h-2 rounded-full border border-dashed border-gray-300 dark:border-gray-600" />
          )}
        </div>
      )}

      {/* GPU stats - each cell independently shows its reading or "no data" */}
      {hasGpu && (
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div className="text-center">
            <span className="text-xs text-gray-500 dark:text-gray-400 block">Util</span>
            {utilRead ? (
              <span className="text-sm font-bold text-gray-900 dark:text-white">
                {(node.gpu_utilization_pct as number).toFixed(0)}%
              </span>
            ) : (
              noData
            )}
          </div>

          <div className="text-center">
            <span className="text-xs text-gray-500 dark:text-gray-400 block">Temp</span>
            {tempRead ? (
              <span
                className={`text-sm font-bold ${getTempColor(node.temperature_c as number)}`}
              >
                {(node.temperature_c as number).toFixed(0)} C
              </span>
            ) : (
              noData
            )}
          </div>

          <div className="text-center">
            <span className="text-xs text-gray-500 dark:text-gray-400 block">Power</span>
            {powerRead ? (
              <span className="text-sm font-bold text-gray-900 dark:text-white">
                {(node.power_draw_w as number).toFixed(0)}W
              </span>
            ) : (
              noData
            )}
          </div>
        </div>
      )}

      {/* Why there is no telemetry. Without this the card just looks broken. */}
      {hasGpu && !anyRead && node.telemetry?.reason && (
        <p className="text-[10px] leading-snug text-gray-500 dark:text-gray-400 mb-2">
          {node.telemetry.reason}
        </p>
      )}

      {/* How the status was decided - "unknown" especially must explain itself. */}
      {node.status_reason && (
        <p className="text-[10px] leading-snug text-gray-500 dark:text-gray-400 mb-1">
          Status: {node.status_reason}
        </p>
      )}

      {/* Declared-but-unverified hardware must not read as measured fact. */}
      {node.topology_verified === false && (
        <p className="text-[10px] leading-snug text-amber-600 dark:text-amber-400 mb-1">
          Hardware below is declared in the topology table, not verified on the box.
        </p>
      )}

      {/* Detail Hint for Admin */}
      {showDetailHint && (
        <p className="text-[10px] text-gray-600 dark:text-gray-400 mt-2 text-center">
          Click for logs and details
        </p>
      )}
    </div>
  );
}
