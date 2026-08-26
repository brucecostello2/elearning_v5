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
 * One doughnut per tier.
 *
 * WP-60 Task 1. THIS COMPONENT FABRICATED A DENOMINATOR.
 *
 * It read `const allocated = data?.allocated ?? 1`. No allocation figure exists
 * anywhere in this system — `useMonitoring.ts` sets `allocated: undefined` for
 * every tier and says why — so `?? 1` turned "not modelled" into "one byte" on
 * every card. The Hot donut then rendered 570 MB against 1 B as a ten-digit
 * percentage, with "Allocated 1 B" printed underneath it. A substituted 1 is
 * worse than a substituted 0 here: 0 would at least have divided to nothing,
 * while 1 produced a large, confident, entirely invented number.
 *
 * The tier TABLE on this same page has been correct since WP-57 — null usage,
 * the word "not modelled" — because WP-57 swept PAGES and this is a COMPONENT.
 * The two now say the same thing in the same words.
 *
 * The rule: where a denominator exists, show the percentage. Where it does not,
 * say so — and draw a ring that represents only what was measured.
 */

ChartJS.register(ArcElement, Tooltip, Legend);

/** The words the tier table uses. Kept identical on purpose. */
const NO_ALLOCATION_LABEL = "not modelled";

interface StorageTierChartProps {
  /** Tier definitions with labels and colors */
  tiers: { id: StorageTier; label: string; color: string; description: string }[];
  /** Per-tier usage data */
  tierData: StorageTierData[];
  /** Byte formatter function */
  formatBytes: (bytes: number) => string;
  /**
   * Why no allocation figure exists, for the tooltip. Comes from
   * `useStorageAnalytics().allocationReason` so the chart and the table quote
   * one sentence rather than two.
   */
  allocationReason?: string;
}

export default function StorageTierChart({
  tiers,
  tierData,
  formatBytes,
  allocationReason,
}: StorageTierChartProps): React.ReactElement {
  const tierCharts = useMemo(() => {
    return tiers.map((tier) => {
      const data = tierData.find((t) => t.tier === tier.id);

      /* A tier absent from the response was never reported on. That is not the
         same fact as a tier that reported zero bytes, and the card must not
         collapse them. */
      const observed = data !== undefined;
      const used = observed ? data!.used ?? 0 : null;

      /* The ONLY condition under which a percentage may be drawn. `allocated`
         is `undefined` for every tier today; if a capacity model is ever added
         this branch starts working with no further change here. */
      const allocated =
        typeof data?.allocated === "number" && Number.isFinite(data.allocated)
          ? data.allocated
          : null;
      const hasTarget = allocated !== null && allocated > 0;

      const free = hasTarget ? Math.max(allocated! - (used ?? 0), 0) : 0;
      const percent = hasTarget
        ? Math.round(((used ?? 0) / allocated!) * 100)
        : null;

      /* With a capacity target: used vs free, as before.
         Without one: a single complete ring standing for what was measured.
         The ring is not a proportion of anything and the card says so. */
      const chartData: ChartData<"doughnut"> = hasTarget
        ? {
            labels: ["Used", "Free"],
            datasets: [
              {
                data: [used ?? 0, free],
                backgroundColor: [tier.color, "#E5E7EB"],
                borderColor: ["white", "white"],
                borderWidth: 2,
                // @ts-expect-error — cutout is valid for doughnut but not in dataset-level types
                cutout: "70%",
              },
            ],
          }
        : {
            labels: [observed ? "Stored" : "Not reported"],
            datasets: [
              {
                data: [1],
                backgroundColor: [observed ? tier.color : "#E5E7EB"],
                borderColor: ["white"],
                borderWidth: 2,
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
              /* Without a target the single arc has no byte value of its own,
                 so the tooltip states the measured total rather than letting
                 chart.js print the placeholder 1. */
              label: (context) =>
                hasTarget
                  ? `${context.label}: ${formatBytes(context.parsed)}`
                  : observed
                  ? `Stored: ${formatBytes(used ?? 0)} — no capacity target`
                  : "This tier was not reported on",
            },
          },
        },
      };

      return {
        tier,
        data: chartData,
        options,
        observed,
        used,
        hasTarget,
        allocated,
        percent,
        assetCount: observed ? data!.asset_count ?? 0 : null,
      };
    });
  }, [tiers, tierData, formatBytes]);

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
      {tierCharts.map(
        ({
          tier,
          data,
          options,
          observed,
          used,
          hasTarget,
          allocated,
          percent,
          assetCount,
        }) => (
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
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {tier.description}
            </p>

            {/* Doughnut */}
            <div className="relative mx-auto" style={{ maxWidth: 150 }}>
              <Doughnut data={data} options={options} />
              <div className="absolute inset-0 flex flex-col items-center justify-center px-4 text-center">
                {hasTarget ? (
                  <span
                    className={`text-lg font-bold ${
                      percent! > 90
                        ? "text-red-600 dark:text-red-400"
                        : percent! > 75
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-gray-900 dark:text-gray-100"
                    }`}
                  >
                    {percent}%
                  </span>
                ) : (
                  /* No percentage, because there is no denominator. The header
                     pill on this page prints nothing at all in the same
                     situation; a card has room to say why. */
                  <span
                    className="text-[10px] leading-tight text-gray-500 dark:text-gray-400"
                    title={allocationReason}
                  >
                    {observed ? "no capacity target" : "not reported"}
                  </span>
                )}
              </div>
            </div>

            {/* Stats below chart */}
            <div className="mt-3 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Used</span>
                <span className="font-mono text-gray-900 dark:text-gray-100">
                  {observed ? (
                    formatBytes(used ?? 0)
                  ) : (
                    <span className="font-sans text-gray-400 dark:text-gray-500">
                      no assets
                    </span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">
                  Allocated
                </span>
                <span
                  className="font-mono text-gray-600 dark:text-gray-400"
                  title={allocationReason}
                >
                  {hasTarget ? (
                    formatBytes(allocated!)
                  ) : (
                    /* Never "1 B", and never "0 B" either: no capacity is
                       modelled at all. Same words as the table above. */
                    <span className="font-sans text-gray-400 dark:text-gray-500">
                      {NO_ALLOCATION_LABEL}
                    </span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Assets</span>
                <span className="font-mono text-gray-600 dark:text-gray-400">
                  {assetCount !== null ? (
                    assetCount.toLocaleString()
                  ) : (
                    <span className="font-sans text-gray-400 dark:text-gray-500">
                      —
                    </span>
                  )}
                </span>
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}
