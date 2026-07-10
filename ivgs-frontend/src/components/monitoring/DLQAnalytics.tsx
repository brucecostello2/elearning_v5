"use client";

import React, { useMemo } from "react";
import {
  Chart as ChartJS,
  ArcElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from "chart.js";
import { Pie, Line, Bar } from "react-chartjs-2";
import type { DLQAnalyticsData } from "@/types/monitoring";

/**
 * §8.2.3 Dead Letter Queue Dashboard — Failure Analytics Charts
 *
 * Three visualization panels per §8.2.3:
 * 1. Failure count by category — Pie chart
 *    Categories: TRANSIENT, CONFIG, EXTERNAL, RESOURCE
 * 2. Failure rate trend — Line graph over time
 *    Shows DLQ entry rate over the last 7 days
 * 3. Top failing tasks — Horizontal bar chart
 *    Shows the 10 most frequently failing task names
 *
 * Chart.js registration for tree-shaking.
 */

ChartJS.register(
  ArcElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

interface DLQAnalyticsProps {
  /** Analytics data from GET /api/v1/dlq/analytics */
  data: DLQAnalyticsData;
}

/** Category colors for the pie chart */
const CATEGORY_COLORS: Record<string, string> = {
  TRANSIENT: "#3B82F6",
  CONFIG: "#8B5CF6",
  EXTERNAL: "#F59E0B",
  RESOURCE: "#EF4444",
};

export default function DLQAnalytics({
  data,
}: DLQAnalyticsProps): React.ReactElement {
  // ── Pie Chart: Failures by Category ─────────────────────────────────
  const categoryChartData = useMemo((): ChartData<"pie"> => {
    if (!data.category_counts) return { labels: [], datasets: [] };

    const categories = Object.keys(data.category_counts);
    const counts = Object.values(data.category_counts);
    const colors = categories.map(
      (c) => CATEGORY_COLORS[c] || "#6B7280"
    );

    return {
      labels: categories,
      datasets: [
        {
          data: counts,
          backgroundColor: colors,
          borderColor: colors.map(() => "white"),
          borderWidth: 2,
        },
      ],
    };
  }, [data.category_counts]);

  const pieOptions = useMemo(
    (): ChartOptions<"pie"> => ({
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            usePointStyle: true,
            padding: 12,
            font: { size: 11 },
          },
        },
        title: {
          display: true,
          text: "Failures by Category",
          font: { size: 13, weight: "bold" },
          color: "#374151",
        },
        tooltip: {
          callbacks: {
            label: (context) => {
              const total = (context.dataset.data as number[]).reduce(
                (a, b) => a + b,
                0
              );
              const value = context.parsed;
              const percent = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
              return `${context.label}: ${value} (${percent}%)`;
            },
          },
        },
      },
    }),
    []
  );

  // ── Line Chart: Failure Rate Trend ──────────────────────────────────
  const trendChartData = useMemo((): ChartData<"line"> => {
    if (!data.trend_data || data.trend_data.length === 0) {
      return { labels: [], datasets: [] };
    }

    const labels = data.trend_data.map((p) => {
      try {
        return new Date(p.date).toLocaleDateString([], {
          month: "short",
          day: "numeric",
        });
      } catch {
        return p.date;
      }
    });

    return {
      labels,
      datasets: [
        {
          label: "DLQ Entries",
          data: data.trend_data.map((p) => p.count),
          borderColor: "#EF4444",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
        },
      ],
    };
  }, [data.trend_data]);

  const lineOptions = useMemo(
    (): ChartOptions<"line"> => ({
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: "Failure Rate Trend (7 Days)",
          font: { size: 13, weight: "bold" },
          color: "#374151",
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: "#9CA3AF" },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(0, 0, 0, 0.05)" },
          ticks: {
            font: { size: 10 },
            color: "#9CA3AF",
            stepSize: 1,
          },
        },
      },
    }),
    []
  );

  // ── Bar Chart: Top Failing Tasks ────────────────────────────────────
  const topTasksChartData = useMemo((): ChartData<"bar"> => {
    if (!data.top_tasks || data.top_tasks.length === 0) {
      return { labels: [], datasets: [] };
    }

    /** Sort by count descending and take top 10 */
    const sorted = [...data.top_tasks]
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);

    return {
      labels: sorted.map((t) => t.task_name),
      datasets: [
        {
          label: "Failures",
          data: sorted.map((t) => t.count),
          backgroundColor: "#F87171",
          borderColor: "#EF4444",
          borderWidth: 1,
          borderRadius: 4,
        },
      ],
    };
  }, [data.top_tasks]);

  const barOptions = useMemo(
    (): ChartOptions<"bar"> => ({
      responsive: true,
      maintainAspectRatio: true,
      indexAxis: "y" as const,
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: "Top Failing Tasks",
          font: { size: 13, weight: "bold" },
          color: "#374151",
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: "rgba(0, 0, 0, 0.05)" },
          ticks: { font: { size: 10 }, color: "#9CA3AF" },
        },
        y: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: "#374151" },
        },
      },
    }),
    []
  );

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Category Pie Chart */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
        {data.category_counts &&
        Object.keys(data.category_counts).length > 0 ? (
          <Pie data={categoryChartData} options={pieOptions} />
        ) : (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            No category data
          </div>
        )}
      </div>

      {/* Trend Line Chart */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
        {data.trend_data && data.trend_data.length > 0 ? (
          <Line data={trendChartData} options={lineOptions} />
        ) : (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            No trend data
          </div>
        )}
      </div>

      {/* Top Tasks Bar Chart */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
        {data.top_tasks && data.top_tasks.length > 0 ? (
          <Bar data={topTasksChartData} options={barOptions} />
        ) : (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            No task data
          </div>
        )}
      </div>
    </div>
  );
}
