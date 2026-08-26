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

/**
 * WP-62 Task 1. `NODE_IDS` and `GPU_LABELS` are GONE from this file.
 *
 * They were a hardcoded second statement of the fleet's hardware, and they
 * were wrong twice: WP-53 found every one of the five GPU rows naming a card
 * that is not in this fleet (A6000s, a 4090, an Intel Arc A770), under a
 * comment citing "§3.2"; the corrected list then still carried node-04 at
 * 96 GB against the API's own 48 GB and left the contradiction visible as
 * WP-53 D-2.
 *
 * The API now sends `gpu_model` and `total_vram_mb` per node from the fleet
 * topology - the same dictionary Node Monitor renders - so the label is
 * DERIVED from the payload. A card the page cannot name is a card the topology
 * does not declare, which is a fact worth seeing rather than a gap for a
 * literal to fill. One source; a hardware correction lands in one place and
 * reaches both pages.
 */
function gpuLabelFor(node: GPUNode): string {
  const model = node.gpu_model?.trim();
  const vramGb =
    typeof node.total_vram_mb === "number" && node.total_vram_mb > 0
      ? `${Math.round(node.total_vram_mb / 1024)} GB`
      : null;
  if (model && vramGb) return `${model} (${vramGb})`;
  if (model) return model;
  if (vramGb) return `GPU, ${vramGb} — model not declared`;
  return "GPU model not declared by the fleet topology";
}

/** View mode for the page */
type GPUViewMode = "cards" | "heatmap";

export default function GPUFleetStatusPage(): React.ReactElement | null {
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
    error: historyError,
  } = useGPUUtilizationHistory("30m");

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
            Authorization: `Bearer ${localStorage.getItem("ivgs_access_token")}`,
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
        gpuCount: 0,
        schedulerCount: 0,
        schedulerOnline: 0,
        deviceUsedVRAM: 0,
        deviceReportingVRAM: 0,
        deviceReportingCount: 0,
        totalNodes: 0,
        onlineNodes: 0,
        offlineNodes: 0,
        drainingNodes: 0,
        avgUtilization: null as number | null,
        utilizationReportingCount: 0,
        totalVRAM: 0,
        usedVRAM: 0,
        activeJobs: 0,
      };
    }

    const onlineNodes = nodes.filter(
      (n: GPUNode) => n.status === "online"
    ).length;
    const offlineNodes = nodes.filter(
      (n: GPUNode) => n.status === "offline"
    ).length;
    const drainingNodes = nodes.filter(
      (n: GPUNode) => n.status === "draining"
    ).length;

    const gpuNodes = nodes.filter(
      (n: GPUNode) => (n.total_vram_mb ?? 0) > 0
    );
    /* WP-62 Task 1, RULED. THE HEADER COUNTS GPUs, WITH THE SCHEDULER SUBSET
       NAMED AS A SUBSET. "5 GPUs - 3 scheduler workers".

       Three defensible numbers have been on three surfaces for three packages:
       6 machines, 5 GPUs, 3 scheduler workers. WP-57 T4 and WP-60 T2 each made
       one tile say which of the three it was. That was necessary and it was
       not the requirement: the page was still DRAWING only the narrow one, so
       two GPUs did not appear at all. Now the page draws all five and this
       header states the relationship between the two counts in one line, so a
       reader never has to reconcile two tiles. */
    const schedulerNodes = gpuNodes.filter((n: GPUNode) => n.in_scheduler);

    /* WP-60 Task 2(a). AVERAGING OVER UNREPORTED NODES INVENTED A FLEET
       FIGURE. Summing `gpu_utilization_pct` across every GPU node treated a
       node that reported nothing as a node reporting 0%, so one silent worker
       dragged the fleet average down by a third and the tile still read as a
       measurement. The average is now taken over the nodes that actually
       reported, and is null when none did. */
    const reporting = gpuNodes.filter(
      (n: GPUNode) => typeof n.gpu_utilization_pct === "number"
    );
    const avgUtilization: number | null =
      reporting.length > 0
        ? reporting.reduce(
            (sum: number, n: GPUNode) => sum + (n.gpu_utilization_pct as number),
            0
          ) / reporting.length
        : null;
    const utilizationReportingCount = reporting.length;

    const totalVRAM = gpuNodes.reduce(
      (sum: number, n: GPUNode) => sum + (n.total_vram_mb ?? 0),
      0
    );
    const usedVRAM = gpuNodes.reduce(
      (sum: number, n: GPUNode) => sum + n.used_vram_mb,
      0
    );
    const activeJobs = nodes.reduce(
      (sum: number, n: GPUNode) => sum + n.active_jobs.length,
      0
    );
    /* Device VRAM, summed over the nodes that REPORTED one. Summing across
       non-reporting nodes as zero is the WP-60 Task 2(a) defect in the other
       column: it would make a fleet look emptier than it is. */
    const deviceReporting = gpuNodes.filter(
      (n: GPUNode) => typeof n.device_used_vram_mb === "number"
    );
    const deviceUsedVRAM = deviceReporting.reduce(
      (sum: number, n: GPUNode) => sum + (n.device_used_vram_mb as number),
      0
    );
    const deviceReportingVRAM = deviceReporting.reduce(
      (sum: number, n: GPUNode) => sum + (n.total_vram_mb ?? 0),
      0
    );

    return {
      gpuCount: gpuNodes.length,
      schedulerCount: schedulerNodes.length,
      schedulerOnline: schedulerNodes.filter(
        (n: GPUNode) => n.status === "online"
      ).length,
      deviceUsedVRAM,
      deviceReportingVRAM,
      deviceReportingCount: deviceReporting.length,
      totalNodes: nodes.length,
      onlineNodes,
      offlineNodes,
      drainingNodes,
      avgUtilization:
        avgUtilization === null ? null : Math.round(avgUtilization),
      utilizationReportingCount,
      totalVRAM,
      usedVRAM,
      activeJobs,
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

  /* WP-62 Task 1. The heatmap's columns are the GPU nodes the API actually
     returned, not a literal list. The old `NODE_IDS.filter(id => id !==
     "node-01")` was a hand-maintained sixth statement of the topology; it also
     silently disagreed with the cards above it whenever the two lists drifted. */
  const gpuHostnames = useMemo(
    () =>
      (nodes ?? [])
        .filter((n: GPUNode) => (n.total_vram_mb ?? 0) > 0)
        .map((n: GPUNode) => n.node_hostname),
    [nodes]
  );

  // ── Render ──────────────────────────────────────────────────────────

  if (user && user.role === "viewer") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600 dark:text-red-400">
            GPU Fleet Status Error
          </h3>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            An error occurred loading GPU fleet data. Please refresh.
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
                GPU Fleet Status
              </h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
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
                        : "bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-950"
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
                        : "bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-950"
                    }`}
                >
                  Heatmap
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* ── Fleet Summary Bar ───────────────────────────────────── */}
        <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-3">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {/* WP-62 Task 1, RULED, and the third operator report of the
                    same defect. The two previous "fixes" (WP-57 T4, WP-60 T2)
                    relabelled this tile. The tile was not the problem: the
                    PAGE drew only the scheduler's registry, so node-05 and
                    node-06 - each with a card, each serving a model - were
                    absent from a page titled GPU Fleet Status.

                    The page now draws every GPU-bearing machine and this tile
                    counts GPUs, naming the scheduler subset as a subset in the
                    same line. Both numbers come from ONE payload
                    (`GET /gpu/nodes`, `in_scheduler` per row), so they cannot
                    drift apart the way two tiles reading two endpoints did. */}
                GPUs in the fleet
              </p>
              <p
                className="mt-1 text-2xl font-bold text-green-600 dark:text-green-400"
                title="Every GPU-bearing machine in the fleet (nodes 02-06). The scheduler subset are the ones running a Celery worker registered with the GPU scheduler; node-05 (vLLM/Qwen) and node-06 (CLIP scorer) run none by design and take no pipeline work. node-01 is CPU-only and is not counted here at all."
              >
                {fleetStats.gpuCount}
                <span className="text-sm text-gray-500 dark:text-gray-400 font-normal">
                  {" "}
                  GPUs — {fleetStats.schedulerCount} scheduler worker
                  {fleetStats.schedulerCount === 1 ? "" : "s"}
                </span>
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Avg GPU Utilization
              </p>
              {fleetStats.avgUtilization !== null ? (
                <p
                  className={`mt-1 text-2xl font-bold ${
                    fleetStats.avgUtilization > 85
                      ? "text-red-600 dark:text-red-400"
                      : fleetStats.avgUtilization > 60
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-green-600 dark:text-green-400"
                  }`}
                  title={`Averaged over the ${fleetStats.utilizationReportingCount} node(s) that reported a utilisation reading.`}
                >
                  {fleetStats.avgUtilization}%
                </p>
              ) : (
                /* WP-60 Task 2(a): no node reported a reading. A green "0%"
                   here asserted an idle fleet on no evidence. */
                <p
                  className="mt-1 text-sm text-gray-400 dark:text-gray-500 py-2"
                  title="No node reported a GPU utilisation reading. WP-61 Task 8: this figure is Prometheus device telemetry (nvidia-gpu-exporter), not a scheduler-registry field - the registry could never carry it, because the heartbeat sender reads it with nvidia-smi and the workers image has no such binary. If this says 'not reported', check the exporter and the scrape, not the workers."
                >
                  not reported
                </p>
              )}
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                VRAM on the devices
              </p>
              {/* WP-62 Task 1. This tile summed the SCHEDULER'S RESERVATION
                  across the fleet and called it "VRAM Usage", which is why it
                  read 0.0 GB while three cards physically held ~120 GB. It is
                  now the device figure from Prometheus, over the nodes that
                  reported one - and it says how many that was, because a fleet
                  total that silently treats a non-reporting card as empty is
                  the WP-60 Task 2(a) defect in the other direction. */}
              {fleetStats.deviceReportingCount > 0 ? (
                <p
                  className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100"
                  title={`Physical VRAM in use, summed over the ${fleetStats.deviceReportingCount} of ${fleetStats.gpuCount} GPU node(s) reporting a device reading. Scheduler reservation is a separate figure and is shown per card.`}
                >
                  {(fleetStats.deviceUsedVRAM / 1024).toFixed(1)}
                  <span className="text-sm text-gray-500 dark:text-gray-400 font-normal">
                    /{(fleetStats.deviceReportingVRAM / 1024).toFixed(0)} GB
                    {fleetStats.deviceReportingCount < fleetStats.gpuCount &&
                      ` (${fleetStats.deviceReportingCount}/${fleetStats.gpuCount} reporting)`}
                  </span>
                </p>
              ) : (
                <p
                  className="mt-1 text-sm text-gray-400 dark:text-gray-500 py-2"
                  title="No GPU node reported a device VRAM reading. Check the nvidia-gpu-exporter scrape targets in Prometheus."
                >
                  not reported
                </p>
              )}
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Active Jobs
              </p>
              <p className="mt-1 text-2xl font-bold text-blue-600 dark:text-blue-400">
                {fleetStats.activeJobs}
              </p>
            </div>
          </div>
        </div>

        <div className="px-6 py-6">
          {/* ── Drain Error ──────────────────────────────────────── */}
          {drainError && (
            <div className="bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-amber-700 dark:text-amber-300">{drainError}</p>
                <button
                  type="button"
                  onClick={() => setDrainError(null)}
                  className="text-amber-500 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
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
            <div className="bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
              <p className="text-sm text-red-700 dark:text-red-300">
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
                    key={node.id}
                    node={node}
                    gpuLabel={gpuLabelFor(node)}
                    isAdmin={user?.role === "admin"}
                    isDraining={drainingNodeId === node.id}
                    onDrainToggle={handleDrainToggle}
                  />
                ))}
              </div>

              {/* Fleet Utilization Chart — last 30 minutes */}
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                  Fleet Utilization — Last 30 Minutes
                </h2>
                {historyLoading ? (
                  <div className="flex justify-center py-8">
                    <LoadingSpinner size="md" />
                  </div>
                ) : historyError ? (
                  <div className="bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded p-4 text-sm text-amber-800 dark:text-amber-300">
                    Utilization history unavailable: {historyError.message}.
                    The fleet snapshot above is unaffected.
                  </div>
                ) : history && history.length > 0 ? (
                  <GPUFleetChart
                    data={history}
                    nodes={nodes}
                  />
                ) : (
                  <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                    No utilization history available for the selected range.
                  </p>
                )}
              </div>
            </>
          )}

          {/* ── Model Residency Heatmap View ─────────────────────── */}
          {!nodesLoading && !nodesError && nodes && viewMode === "heatmap" && (
            <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                Model Residency Heatmap — §8.2.2
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                Shows which AI models are currently loaded on which GPU nodes.
                Darker cells indicate higher VRAM reservation.
              </p>

              {heatmapData.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                  No model residency data available.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Model
                        </th>
                        {gpuHostnames.map((nodeId) => (
                          <th
                            key={nodeId}
                            className="px-3 py-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase"
                          >
                            {nodeId}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {heatmapData.map((entry: ModelResidencyEntry) => (
                        <tr key={entry.model_name}>
                          <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-100 whitespace-nowrap">
                            {entry.model_name}
                          </td>
                          {gpuHostnames.map((nodeId) => {
                              const allocation = entry.allocations?.find(
                                (a) => a.node_id === nodeId
                              );
                              const intensity = allocation
                                ? Math.min(
                                    allocation.vram_mb /
                                      (nodes.find(
                                        (n: GPUNode) => n.node_hostname === nodeId
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
                                    <span className="text-xs text-gray-700 dark:text-gray-300">
                                      —
                                    </span>
                                  )}
                                </td>
                              );
                          })}
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
