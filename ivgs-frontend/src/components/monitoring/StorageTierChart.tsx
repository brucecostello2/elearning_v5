"use client";

import React, { useMemo } from "react";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from "chart.js";
import { Doughnut } from "react-chartjs-2";
import type { StorageTierData, StorageTier } from "@/types/monitoring";

/**
 * §8.2.6 Storage Analytics — Tier Usage Charts
 *
 * Doughnut charts showing used vs free capacity for each storage tier.
 * Per §8.2.6: "Tier usage breakdown (hot/warm/cold/archive):
 * used vs. allocated capacity per tier."
 *
 * Each tier gets its own doughnut chart with:
 * - Used space (colored segment)
 * - Free space (gray segment)
 * - Center label showing usage percentage
 * - Below chart: asset count and total size
 *
 * Plus an overall storage summary chart.
 */

ChartJS.register(ArcElement, Tooltip, Legend);

interface StorageTierChartProps {
  /** Tier definitions with labels and colors */
  tiers: { id: StorageTier; label: string; color: string; description: string }[];
  /** Per-tier usage data */
  tierData: StorageTierData[];
  /** Byte formatter function */
  formatBytes: (bytes: number) => string;
}

export default function StorageTierChart({
  tiers,
  tierData,
  formatBytes,
}: StorageTierChartProps): React.ReactElement {
  /**
   * Build chart data for each tier.
   */
  const tierCharts = useMemo(() => {
    return tiers.map((tier) => {
      const data = tierData.find((t) => t.tier === tier.id);
      const used = data?.used ?? 0;
      const allocated = data?.allocated ?? 1;
      const free = Math.max(allocated - used, 0);
      const percent = allocated > 0 ? Math.round((used / allocated) * 100) : 0;

      const chartData: ChartData<"doughnut"> = {
        labels: ["Used", "Free"],
        datasets: [
          {
            data: [used, free],
            backgroundColor: [tier.color, "#E5E7EB"],
            borderColor: ["white", "white"],
            borderWidth: 2,
            // @ts-expect-error — cutout is valid for doughnut but not in dataset-level types
            cutout: "70%",
          },
        ],
      };

      const options: ChartOptions<"doughnut"> = {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => {
                const value = context.parsed;
                return `${context.label}: ${formatBytes(value)}`;
              },
            },
          },
        },
      };

      return {
        tier,
        data: chartData,
        options,
        used,
        allocated,
        free,
        percent,
        assetCount: data?.asset_count ?? 0,
      };
    });
  }, [tiers, tierData, formatBytes]);

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
      {tierCharts.map(({ tier, data, options, used, allocated, percent, assetCount }) => (
        <div
          key={tier.id}
          className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4"
        >
          <div className="flex items-center gap-2 mb-3">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: tier.color }}
            />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {tier.label}
            </h3>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{tier.description}</p>

          {/* Doughnut Chart */}
          <div className="relative mx-auto" style={{ maxWidth: 150 }}>
            <Doughnut data={data} options={options} />
            {/* Center percentage label */}
            <div className="absolute inset-0 flex items-center justify-center">
              <span
                className={`text-lg font-bold ${
                  percent > 90
                    ? "text-red-600 dark:text-red-400"
                    : percent > 75
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-gray-900 dark:text-gray-100"
                }`}
              >
                {percent}%
              </span>
            </div>
          </div>

          {/* Stats below chart */}
          <div className="mt-3 space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500 dark:text-gray-400">Used</span>
              <span className="font-mono text-gray-900 dark:text-gray-100">
                {formatBytes(used)}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500 dark:text-gray-400">Allocated</span>
              <span className="font-mono text-gray-600 dark:text-gray-400">
                {formatBytes(allocated)}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500 dark:text-gray-400">Assets</span>
              <span className="font-mono text-gray-600 dark:text-gray-400">
                {assetCount.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
