"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import {
  useGPUFleetStatus,
  useGPUUtilizationHistory,
} from "@/hooks/useMonitoring";
import GPUNodeCard from "@/components/monitoring/GPUNodeCard";
import GPUFleetChart from "@/components/monitoring/GPUFleetChart";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  GPUNode,
  GPUUtilizationPoint,
  ModelResidencyEntry,
} from "@/types/monitoring";

/**
 * §8.2.2 GPU Fleet Status
 *
 * Operational monitoring page for the GPU fleet with:
 * - Per-GPU cards: model, VRAM total/used (progress bar), temperature gauge,
 *   active job with stage, status badge, drain toggle (admin only per §5.2.1)
 * - Fleet utilization chart: line graph over last 30 minutes
 * - Queue depth per GPU node
 * - Model residency heatmap: which AI models are currently loaded on which GPUs
 *
 * Data sources:
 *   - GET /api/v1/gpu/nodes — all registered GPU nodes with status/VRAM
 *   - GET /api/v1/gpu/utilization — fleet-wide utilization summary
 *   - GET /api/v1/gpu/nodes/{id}/reservations — active VRAM reservations
 *   - POST /api/v1/gpu/nodes/{id}/drain — toggle drain mode (§5.2.1)
 *
 * Prometheus metrics consumed (§12.4 Table 12-3):
 *   - ivgs_gpu_vram_used_mb — reserved VRAM per GPU
 *   - ivgs_gpu_utilization_pct — GPU utilization % per node
 *   - ivgs_scheduler_queue_depth — queue depth per GPU node
 *
 * Polling: every 10 seconds per §8.1.5 Node Monitor specification.
 *
 * RBAC per Table 8-3:
 *   - admin: full detail + drain toggle
 *   - operator: read-only status
 *   - viewer: no access (redirected)
 */

/** Node IDs for the 6-node Proxmox cluster per §2.2 */
const NODE_IDS = [
  "node-01",
  "node-02",
  "node-03",
  "node-04",
  "node-05",
  "node-06",
] as const;

/** GPU capability labels per §3.2 */
const GPU_LABELS: Record<string, string> = {
  "node-01": "Management (No GPU)",
  "node-02": "NVIDIA A6000 (48 GB)",
  "node-03": "NVIDIA A6000 (48 GB)",
  "node-04": "NVIDIA RTX 4090 (24 GB)",
  "node-05": "NVIDIA RTX 4090 (24 GB)",
  "node-06": "Intel Arc A770 (16 GB)",
};

/** View mode for the page */
type GPUViewMode = "cards" | "heatmap";

export default function GPUFleetStatusPage(): React.ReactElement {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role === "viewer") {
      router.push("/");
    }
  }, [user, router]);

  // ── State ───────────────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState<GPUViewMode>("cards");
  const [drainingNodeId, setDrainingNodeId] = useState<string | null>(null);
  const [drainError, setDrainError] = useState<string | null>(null);

  // ── Data Fetching ───────────────────────────────────────────────────
  /**
   * useGPUFleetStatus fetches from GET /api/v1/gpu/nodes with fleet summary.
   * Polling interval: 10 seconds per §8.1.5 (Node Monitor polls every 10s).
   */
  const {
    nodes,
    fleetSummary,
    modelResidency,
    isLoading: nodesLoading,
    error: nodesError,
    mutate: mutateNodes,
  } = useGPUFleetStatus();

  /**
   * useGPUUtilizationHistory fetches fleet utilization over the last 30 minutes.
   * Used for the fleet utilization line chart per §8.2.2.
   */
  const {
    history,
    isLoading: historyLoading,
  } = useGPUUtilizationHistory();

  // ── Handlers ────────────────────────────────────────────────────────

  /**
   * handleDrainToggle — POST /api/v1/gpu/nodes/{id}/drain
   *
   * Toggles drain mode on a GPU node per §5.2.1.
   * When drained, no new jobs are scheduled to the node.
   * Existing jobs continue to completion.
   * Admin only per Table 8-3.
   */
  const handleDrainToggle = useCallback(
    async (nodeId: string) => {
      if (user?.role !== "admin") {
        setDrainError("Only administrators can toggle drain mode.");
        return;
      }

      setDrainingNodeId(nodeId);
      setDrainError(null);

      try {
        const response = await fetch(`/api/v1/gpu/nodes/${nodeId}/drain`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail ||
              `Drain toggle failed with status ${response.status}`
          );
        }

        await mutateNodes();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to toggle drain mode";
        setDrainError(message);
        console.error("[GPUFleetStatus] Drain toggle error:", message);
      } finally {
        setDrainingNodeId(null);
      }
    },
    [user, mutateNodes]
  );

  // ── Computed Values ─────────────────────────────────────────────────

  /**
   * Compute fleet-level aggregates for the summary bar.
   */
  const fleetStats = useMemo(() => {
    if (!nodes || nodes.length === 0) {
      return {
        totalNodes: 0,
        onlineNodes: 0,
        offlineNodes: 0,
        drainingNodes: 0,
        avgUtilization: 0,
        totalVRAM: 0,
        usedVRAM: 0,
        activeJobs: 0,
        queuedJobs: 0,
      };
    }

    const onlineNodes = nodes.filter(
      (n: GPUNode) => n.status === "ONLINE"
    ).length;
    const offlineNodes = nodes.filter(
      (n: GPUNode) => n.status === "OFFLINE"
    ).length;
    const drainingNodes = nodes.filter(
      (n: GPUNode) => n.status === "DRAINING"
    ).length;

    const gpuNodes = nodes.filter(
      (n: GPUNode) => n.total_vram_mb > 0
    );

    const avgUtilization =
      gpuNodes.length > 0
        ? gpuNodes.reduce(
            (sum: number, n: GPUNode) => sum + (n.utilization_pct || 0),
            0
          ) / gpuNodes.length
        : 0;

    const totalVRAM = gpuNodes.reduce(
      (sum: number, n: GPUNode) => sum + n.total_vram_mb,
      0
    );
    const usedVRAM = gpuNodes.reduce(
      (sum: number, n: GPUNode) => sum + (n.used_vram_mb || 0),
      0
    );
    const activeJobs = nodes.reduce(
      (sum: number, n: GPUNode) => sum + (n.active_jobs || 0),
      0
    );
    const queuedJobs = nodes.reduce(
      (sum: number, n: GPUNode) => sum + (n.queued_jobs || 0),
      0
    );

    return {
      totalNodes: nodes.length,
      onlineNodes,
      offlineNodes,
      drainingNodes,
      avgUtilization: Math.round(avgUtilization),
      totalVRAM,
      usedVRAM,
      activeJobs,
      queuedJobs,
    };
  }, [nodes]);

  /**
   * Build model residency heatmap data.
   * Maps each GPU node to the list of models currently loaded.
   * Used for the heatmap visualization per §8.2.2.
   */
  const heatmapData = useMemo(() => {
    if (!modelResidency) return [];
    return modelResidency as ModelResidencyEntry[];
  }, [modelResidency]);

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600">
            GPU Fleet Status Error
          </h3>
          <p className="mt-2 text-sm text-gray-600">
            An error occurred loading GPU fleet data. Please refresh.
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
                GPU Fleet Status
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                §8.2.2 — Per-GPU cards, fleet utilization, queue depth, model
                residency heatmap
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* View mode toggle */}
              <div className="inline-flex rounded-md shadow-sm">
                <button
                  type="button"
                  onClick={() => setViewMode("cards")}
                  className={`px-3 py-1.5 text-sm font-medium rounded-l-md border
                    ${
                      viewMode === "cards"
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                    }`}
                >
                  Cards
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("heatmap")}
                  className={`px-3 py-1.5 text-sm font-medium rounded-r-md border-t
                    border-b border-r
                    ${
                      viewMode === "heatmap"
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                    }`}
                >
                  Heatmap
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* ── Fleet Summary Bar ───────────────────────────────────── */}
        <div className="bg-white border-b border-gray-200 px-6 py-3">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Nodes Online
              </p>
              <p className="mt-1 text-2xl font-bold text-green-600">
                {fleetStats.onlineNodes}
                <span className="text-sm text-gray-400 font-normal">
                  /{fleetStats.totalNodes}
                </span>
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Avg GPU Utilization
              </p>
              <p
                className={`mt-1 text-2xl font-bold ${
                  fleetStats.avgUtilization > 85
                    ? "text-red-600"
                    : fleetStats.avgUtilization > 60
                    ? "text-amber-600"
                    : "text-green-600"
                }`}
              >
                {fleetStats.avgUtilization}%
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                VRAM Usage
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {(fleetStats.usedVRAM / 1024).toFixed(1)}
                <span className="text-sm text-gray-400 font-normal">
                  /{(fleetStats.totalVRAM / 1024).toFixed(0)} GB
                </span>
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Active Jobs
              </p>
              <p className="mt-1 text-2xl font-bold text-blue-600">
                {fleetStats.activeJobs}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Queued Jobs
              </p>
              <p className="mt-1 text-2xl font-bold text-amber-600">
                {fleetStats.queuedJobs}
              </p>
            </div>
          </div>
        </div>

        <div className="px-6 py-6">
          {/* ── Drain Error ──────────────────────────────────────── */}
          {drainError && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-amber-700">{drainError}</p>
                <button
                  type="button"
                  onClick={() => setDrainError(null)}
                  className="text-amber-500 hover:text-amber-700"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* ── Loading ──────────────────────────────────────────── */}
          {nodesLoading && (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          )}

          {/* ── Error ────────────────────────────────────────────── */}
          {nodesError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <p className="text-sm text-red-700">
                Failed to load GPU fleet status. Please try again.
              </p>
            </div>
          )}

          {/* ── GPU Node Cards View ──────────────────────────────── */}
          {!nodesLoading && !nodesError && nodes && viewMode === "cards" && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 mb-8">
                {nodes.map((node: GPUNode) => (
                  <GPUNodeCard
                    key={node.node_id}
                    node={node}
                    gpuLabel={GPU_LABELS[node.node_id] || node.node_id}
                    isAdmin={user?.role === "admin"}
                    isDraining={drainingNodeId === node.node_id}
                    onDrainToggle={handleDrainToggle}
                  />
                ))}
              </div>

              {/* Fleet Utilization Chart — last 30 minutes */}
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h2 className="text-sm font-semibold text-gray-700 mb-4">
                  Fleet Utilization — Last 30 Minutes
                </h2>
                {historyLoading ? (
                  <div className="flex justify-center py-8">
                    <LoadingSpinner size="md" />
                  </div>
                ) : history ? (
                  <GPUFleetChart
                    data={history}
                    nodes={nodes}
                  />
                ) : (
                  <p className="text-sm text-gray-500 text-center py-8">
                    No utilization history available.
                  </p>
                )}
              </div>
            </>
          )}

          {/* ── Model Residency Heatmap View ─────────────────────── */}
          {!nodesLoading && !nodesError && nodes && viewMode === "heatmap" && (
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">
                Model Residency Heatmap — §8.2.2
              </h2>
              <p className="text-xs text-gray-500 mb-4">
                Shows which AI models are currently loaded on which GPU nodes.
                Darker cells indicate higher VRAM reservation.
              </p>

              {heatmapData.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-8">
                  No model residency data available.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                          Model
                        </th>
                        {NODE_IDS.filter((id) => id !== "node-01").map(
                          (nodeId) => (
                            <th
                              key={nodeId}
                              className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase"
                            >
                              {nodeId}
                            </th>
                          )
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {heatmapData.map((entry: ModelResidencyEntry) => (
                        <tr key={entry.model_name}>
                          <td className="px-3 py-2 text-sm font-medium text-gray-900 whitespace-nowrap">
                            {entry.model_name}
                          </td>
                          {NODE_IDS.filter((id) => id !== "node-01").map(
                            (nodeId) => {
                              const allocation = entry.allocations?.find(
                                (a) => a.node_id === nodeId
                              );
                              const intensity = allocation
                                ? Math.min(
                                    allocation.vram_mb /
                                      (nodes.find(
                                        (n: GPUNode) => n.node_id === nodeId
                                      )?.total_vram_mb || 1),
                                    1
                                  )
                                : 0;

                              return (
                                <td
                                  key={nodeId}
                                  className="px-3 py-2 text-center"
                                >
                                  {allocation ? (
                                    <div
                                      className="inline-flex items-center justify-center
                                        w-16 h-8 rounded text-xs font-mono font-medium"
                                      style={{
                                        backgroundColor: `rgba(59, 130, 246, ${
                                          0.1 + intensity * 0.8
                                        })`,
                                        color:
                                          intensity > 0.5
                                            ? "white"
                                            : "rgb(59, 130, 246)",
                                      }}
                                    >
                                      {(allocation.vram_mb / 1024).toFixed(1)}G
                                    </div>
                                  ) : (
                                    <span className="text-xs text-gray-300">
                                      —
                                    </span>
                                  )}
                                </td>
                              );
                            }
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}
