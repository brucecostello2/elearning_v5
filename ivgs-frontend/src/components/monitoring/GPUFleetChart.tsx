"use client";

import React, { useMemo } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ChartOptions,
  type ChartData,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { GPUNode, GPUUtilizationPoint } from "@/types/monitoring";

/**
 * §8.2.2 GPU Fleet Status — Fleet Utilization Chart
 *
 * Line chart showing GPU utilization percentage for each node
 * over the last 30 minutes. Per §8.2.2: "Fleet utilization chart
 * (line graph, last 30 minutes)."
 *
 * Features:
 * - One line per GPU node (node-02 through node-06)
 * - Queue depth shown as secondary axis bar overlay
 * - Threshold line at 85% (GPUOvertemperature alert level)
 * - Responsive layout with proper legend
 * - Tooltip with node ID, utilization %, and timestamp
 *
 * Chart.js registration for tree-shaking.
 */

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface GPUFleetChartProps {
  /** Historical utilization data points indexed by timestamp */
  data: GPUUtilizationPoint[];
  /** Current node list (for colors and labels) */
  nodes: GPUNode[];
}

/** Color palette for GPU node lines */
const NODE_COLORS: Record<string, { line: string; fill: string }> = {
  "node-02": { line: "#3B82F6", fill: "rgba(59, 130, 246, 0.1)" },
  "node-03": { line: "#8B5CF6", fill: "rgba(139, 92, 246, 0.1)" },
  "node-04": { line: "#10B981", fill: "rgba(16, 185, 129, 0.1)" },
  "node-05": { line: "#F59E0B", fill: "rgba(245, 158, 11, 0.1)" },
  "node-06": { line: "#EF4444", fill: "rgba(239, 68, 68, 0.1)" },
};

export default function GPUFleetChart({
  data,
  nodes,
}: GPUFleetChartProps): React.ReactElement {
  /**
   * Transform raw utilization data into Chart.js datasets.
   * Each GPU node becomes a separate line dataset.
   */
  const chartData = useMemo((): ChartData<"line"> => {
    // Hardened guard (Spec v1.1 sec 6.3): explicitly verify array shape.
    // Previous guard (!data || data.length === 0) failed when data was an
    // object instead of array, causing TypeError downstream.
    if (!Array.isArray(data) || data.length === 0) {
      return { labels: [], datasets: [] };
    }

    // Extract unique timestamps. Field name: recorded_at per
    // gpu_metrics_history storage model (Spec v1.1 sec 3.4).
    const timestamps = Array.from(
      new Set(data.map((p) => p.recorded_at))
    ).sort();

    // Format timestamps to HH:MM:SS for display
    const labels = timestamps.map((ts) => {
      try {
        return new Date(ts).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      } catch {
        return ts;
      }
    });

    // Build one dataset per GPU node. Filter to nodes with GPU capacity
    // (total_vram_mb > 0). Node-01 has no GPU per spec sec 3.1; filtered.
    const gpuNodes = nodes.filter((n) => (n.total_vram_mb ?? 0) > 0);

    const datasets = gpuNodes.map((node) => {
      // JOIN history points to snapshot nodes by node_hostname (stable
      // display identifier present on both sides). Per Spec v1.1 sec 6.3.
      const nodeData = timestamps.map((ts) => {
        const point = data.find(
          (p) =>
            p.recorded_at === ts &&
            p.node_hostname === node.node_hostname
        );
        return point?.gpu_util_pct ?? null;
      });

      // NODE_COLORS is keyed by hostname ("node-02" etc.)
      const colors = NODE_COLORS[node.node_hostname] || {
        line: "#6B7280",
        fill: "rgba(107, 114, 128, 0.1)",
      };

      return {
        label: node.node_hostname,
        data: nodeData,
        borderColor: colors.line,
        backgroundColor: colors.fill,
        fill: true,
        tension: 0.3,
        pointRadius: 1,
        pointHoverRadius: 4,
        borderWidth: 2,
        // Dashed line for nodes with no data in the window - visual
        // distinction from solid line of nulls.
        ...(nodeData.every((v) => v === null) && {
          borderDash: [4, 4],
          fill: false,
        }),
      };
    });

    return { labels, datasets };
  }, [data, nodes]);

  /**
   * Chart.js options configuration.
   * Responsive with fixed aspect ratio, clean styling.
   */
  const options = useMemo(
    (): ChartOptions<"line"> => ({
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 3,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "top",
          labels: {
            usePointStyle: true,
            pointStyle: "circle",
            padding: 16,
            font: { size: 11 },
          },
        },
        title: {
          display: false,
        },
        tooltip: {
          backgroundColor: "rgba(0, 0, 0, 0.8)",
          titleFont: { size: 11 },
          bodyFont: { size: 11 },
          padding: 8,
          callbacks: {
            label: (context) => {
              const value = context.parsed.y;
              return value !== null
                ? `${context.dataset.label}: ${value.toFixed(1)}%`
                : `${context.dataset.label}: N/A`;
            },
          },
        },
      },
      scales: {
        x: {
          display: true,
          grid: {
            display: false,
          },
          ticks: {
            maxTicksLimit: 10,
            font: { size: 10 },
            color: "#9CA3AF",
          },
        },
        y: {
          display: true,
          min: 0,
          max: 100,
          grid: {
            color: "rgba(0, 0, 0, 0.05)",
          },
          ticks: {
            stepSize: 25,
            font: { size: 10 },
            color: "#9CA3AF",
            callback: (value) => `${value}%`,
          },
        },
      },
    }),
    []
  );

  // ── Render ──────────────────────────────────────────────────────────

  if (!data || data.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
        No utilization history data available for the last 30 minutes.
      </div>
    );
  }

  return (
    <div className="relative">
      <Line data={chartData} options={options} />
      {/* Legend annotation for alert thresholds */}
      <div className="mt-2 flex items-center justify-end gap-4 text-xs text-gray-500 dark:text-gray-400">
        <span>
          🔴 &gt;85°C alert threshold (Table 13-3 GPUOvertemperature)
        </span>
        <span>
          🟡 &lt;30% utilization warning (Table 13-3 GPUUtilizationLow)
        </span>
      </div>
    </div>
  );
}
