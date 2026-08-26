"use client";

import React from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { usePipelineJobs, useGPUFleetStatus, useDLQMessages, useStorageAnalytics } from "@/hooks/useMonitoring";
import ErrorBoundary from "@/components/ErrorBoundary";
import LoadingSpinner from "@/components/LoadingSpinner";
import { formatBytes } from "@/lib/media";

/**
 * Monitoring Dashboard — Landing page for /monitoring
 *
 * Shows overview stats cards for all monitoring areas with quick links:
 * - Pipeline: active/failed job counts
 * - GPU Fleet: online nodes, avg utilization
 * - DLQ: pending message count
 * - Quality: flagged assets count
 * - Storage: total usage
 * - Timeline: active renders
 *
 * RBAC: operator+ (per §8.3 Table 8-3)
 */

interface MonitoringCard {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  stat?: string | number;
  statLabel?: string;
  color: string;
}

export default function MonitoringPage(): React.ReactElement {
  const { user } = useAuth();
  const { jobs, isLoading: jobsLoading } = usePipelineJobs();
  const { nodes, isLoading: nodesLoading } = useGPUFleetStatus();
  const { messages: dlqMessages, isLoading: dlqLoading } = useDLQMessages({ page: 1, pageSize: 1 });
  const { totalUsed, isLoading: storageLoading } = useStorageAnalytics();

  /**
   * WP-40 Task 2: these read 0 for the same reason the Pipeline Tracker's
   * counters did -- `usePipelineJobs` returned PROJECTS, and the comparison
   * used lowercase wire values against a list that carried neither. The hook
   * now yields real jobs with normalised uppercase statuses.
   */
  const activeJobs = jobs?.filter((j) => j.status === "RUNNING").length ?? 0;
  const failedJobs = jobs?.filter((j) => j.status === "ERROR").length ?? 0;
  /* WP-57 Task 4. THE NUMBER IS RIGHT; THE LABEL WAS WRONG.
     This tile reads `useGPUFleetStatus()` — the SCHEDULER's fleet — while the
     Node Monitor reads GET /api/v1/nodes, the six-machine topology. Two
     surfaces, two sources, two different true numbers, and neither said which
     it meant, so they read as a contradiction.
     What this counts is GPU workers REGISTERED WITH THE SCHEDULER: node-02, 03
     and 04. It is not the GPU fleet — node-06 has an RTX 5080 and runs the CLIP
     scorer but no Celery worker, so it is correctly absent — and it is not the
     machine count, which is six. Relabelled rather than recomputed: a number
     that splits the difference would be true of nothing. */
  const onlineNodes = nodes?.filter((n) => n.status === "online").length ?? 0;
  const totalNodes = nodes?.length ?? 0;

  const cards: MonitoringCard[] = [
    {
      title: "Pipeline Tracker",
      description: "Real-time pipeline job monitoring with stage progress, checkpoints, and fallback indicators.",
      href: "/monitoring/pipeline",
      color: "text-blue-400",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z" />
        </svg>
      ),
      stat: jobsLoading ? "..." : `${activeJobs} active / ${failedJobs} failed`,
      statLabel: "Pipeline Jobs",
    },
    {
      title: "GPU Fleet",
      description: "GPU node status, utilization metrics, VRAM usage, temperature, and model residency.",
      href: "/monitoring/gpu",
      color: "text-green-400",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75A2.25 2.25 0 0 0 4.5 6.75v10.5a2.25 2.25 0 0 0 2.25 2.25Z" />
        </svg>
      ),
      /* WP-57 Task 4: same source, same labelling rule as the tile above. */
      stat: nodesLoading
        ? "..."
        : `${onlineNodes}/${totalNodes} scheduler workers`,
      statLabel: "GPU Nodes",
    },
    {
      title: "Dead Letter Queue",
      description: "Failed task management with replay, discard, and bulk operations. Error categorization.",
      href: "/monitoring/dlq",
      color: "text-red-400",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m0-10.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.75c0 5.592 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.57-.598-3.75h-.152c-3.196 0-6.1-1.25-8.25-3.286Zm0 13.036h.008v.008H12v-.008Z" />
        </svg>
      ),
      stat: dlqLoading ? "..." : "View Queue",
      statLabel: "DLQ Messages",
    },
    {
      title: "Quality Review",
      description: "Flagged asset review queue with quality scores, safety metrics, and approve/reject workflows.",
      href: "/monitoring/quality",
      color: "text-yellow-400",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
        </svg>
      ),
      stat: "View Queue",
      statLabel: "Quality Flagged",
    },
    {
      title: "Storage Analytics",
      description: "Storage tier breakdown, deduplication savings, quota utilization, and orphan asset tracking.",
      href: "/monitoring/storage",
      color: "text-purple-400",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375" />
        </svg>
      ),
      /* WP-57 Task 2: shared formatter. See the tile below. */
      stat: storageLoading
        ? "..."
        : typeof totalUsed === "number"
        ? formatBytes(totalUsed)
        : "View Stats",
      statLabel: "Total Used",
    },
    {
      title: "Composition Timeline",
      description: "Composition manifest viewer with timeline segments, render progress, and layer visualization.",
      href: "/monitoring/timeline",
      color: "text-cyan-400",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5h1.5C5.496 19.5 6 18.996 6 18.375m-2.625 0V4.125c0-.621.504-1.125 1.125-1.125h11.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125m-16.5 0h1.5m14.25 0h1.5m-1.5 0c.621 0 1.125-.504 1.125-1.125v-11.25c0-.621-.504-1.125-1.125-1.125m0 15.75h1.5A1.125 1.125 0 0 0 21 18.375m0 0V4.125c0-.621-.504-1.125-1.125-1.125H5.625c-.621 0-1.125.504-1.125 1.125v1.5" />
        </svg>
      ),
      stat: "View Timeline",
      statLabel: "Active Renders",
    },
  ];

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Operational Monitoring</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Real-time system health, pipeline progress, and resource utilization.
          </p>
        </div>

        {/* Quick stats */}
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {jobsLoading ? "..." : activeJobs}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">Active Pipelines</p>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">
              {nodesLoading ? "..." : `${onlineNodes}/${totalNodes}`}
            </p>
            {/* WP-57 Task 4: the label now states its source. Not "GPU Nodes
                Online", which implied the GPU fleet and so implied node-05 and
                node-06 were missing. */}
            <p
              className="text-xs text-gray-500 dark:text-gray-400"
              title="GPU workers registered with the scheduler (node-02/03/04). node-06 has a GPU but runs no Celery worker; node-05 is out of service. See Node Monitor for all six machines."
            >
              Scheduler GPU workers
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-2xl font-bold text-red-600 dark:text-red-400">
              {jobsLoading ? "..." : failedJobs}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">Failed Jobs</p>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
            <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
              {/* WP-57 Task 2. THE TWO SURFACES NEVER DISAGREED.
                  This tile and Storage Analytics read the SAME total_size_bytes
                  from the same endpoint. This one hardcoded GB to one decimal,
                  so 347 MB rendered as "0.3 GB" while the other page said
                  "347.0 MB" - one fact, two units, and the coarse rounding here
                  made it look like a contradiction. Using the shared formatter
                  means both pick the unit the number deserves and always agree.
                  Also note `totalUsed ?` was falsy for a genuine 0 and fell to
                  "—"; an empty store is a measurement, not a missing one. */}
              {storageLoading
                ? "..."
                : typeof totalUsed === "number"
                ? formatBytes(totalUsed)
                : "—"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">Storage Used</p>
          </div>
        </div>

        {/* Monitoring area cards */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((card) => (
            <Link
              key={card.href}
              href={card.href}
              className="group rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 transition-all hover:border-ivgs-600/50 hover:bg-gray-100 dark:hover:bg-gray-800/50"
            >
              <div className="flex items-start justify-between">
                <div className={`${card.color} transition-colors group-hover:opacity-80`}>
                  {card.icon}
                </div>
                {card.stat && (
                  <div className="text-right">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{card.stat}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400">{card.statLabel}</p>
                  </div>
                )}
              </div>
              <h3 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white group-hover:text-ivgs-800 dark:group-hover:text-ivgs-300">
                {card.title}
              </h3>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{card.description}</p>
              <div className="mt-4 flex items-center text-sm text-ivgs-600 dark:text-ivgs-400 group-hover:text-ivgs-800 dark:group-hover:text-ivgs-300">
                <span>Open</span>
                <svg className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                </svg>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </ErrorBoundary>
  );
}
