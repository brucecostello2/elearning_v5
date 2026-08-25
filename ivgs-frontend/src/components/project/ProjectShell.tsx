"use client";

import React from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

import { useProjects } from "@/hooks/useProjects";
import StateBadge from "@/components/StateBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import { PROJECT_TABS, activeTabId, tabHref } from "@/lib/project-tabs";
import {
  PROJECT_STATE_SEQUENCE,
  projectStateProgress,
  stateStepStatuses,
} from "@/lib/project-state";

/**
 * WP-43 Task 1 — the project header and tab bar, on every project tab.
 *
 * Before this, the tab bar was JSX inside the Overview page component, so it
 * existed on exactly one of the eleven tabs. Every sub-page replaced it with
 * a bare "← Back" link, which made Overview a compulsory waypoint between
 * any two tabs and left the operator with no indication, on ten of eleven
 * pages, of which tab they were on.
 *
 * This shell is rendered from `src/app/projects/[id]/layout.tsx`, so it
 * wraps `/projects/{id}` and every `/projects/{id}/*` route by construction
 * -- a new tab cannot be added without it. The per-page back links are gone;
 * "← Gallery" survives here, once, at the top level.
 *
 * The project is read through the same `useProjects(projectId)` SWR key the
 * pages use, so this adds no extra request.
 */
export default function ProjectShell({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const params = useParams();
  const pathname = usePathname();
  const projectId = (params?.id as string) ?? "";
  const { project, isLoading, error } = useProjects(projectId);

  const active = activeTabId(pathname);
  const progress = projectStateProgress(project?.state);
  const steps = stateStepStatuses(project?.state);

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* ── Project header ─────────────────────────────────────────── */}
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-3">
              <h1 className="truncate text-2xl font-bold text-gray-900 dark:text-white">
                {project?.name ??
                  (isLoading ? "Loading project…" : "Project")}
              </h1>
              {project && <StateBadge state={project.state} size="md" />}
            </div>
            {project?.description && (
              <p className="max-w-2xl truncate text-sm text-gray-500 dark:text-gray-400">
                {project.description}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Link
              href="/gallery"
              className="rounded-lg bg-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-300 hover:text-gray-900 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 dark:hover:text-white"
            >
              ← Gallery
            </Link>
          </div>
        </div>

        {/* ── Lifecycle strip ────────────────────────────────────────── */}
        {project && (
          <div className="mb-5 overflow-x-auto rounded-xl border border-gray-300 bg-gray-100 px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
            <div className="flex min-w-max items-center gap-1">
              {PROJECT_STATE_SEQUENCE.map((step, idx) => {
                const status = steps[idx] ?? "unknown";
                const dot =
                  status === "done"
                    ? "bg-green-600 text-white"
                    : status === "current"
                    ? "bg-blue-600 text-white ring-4 ring-blue-600/30"
                    : "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400";
                return (
                  <React.Fragment key={step.state}>
                    <div className="flex min-w-[64px] flex-col items-center">
                      <div
                        className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${dot}`}
                      >
                        {status === "done" ? "✓" : idx + 1}
                      </div>
                      <span className="mt-1 whitespace-nowrap text-[10px] leading-tight text-gray-500 dark:text-gray-400">
                        {step.label}
                      </span>
                    </div>
                    {idx < PROJECT_STATE_SEQUENCE.length - 1 && (
                      <div
                        className={`h-0.5 w-4 ${
                          steps[idx] === "done"
                            ? "bg-green-600"
                            : "bg-gray-200 dark:bg-gray-700"
                        }`}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
            {/*
              An honest caption for the two cases the old four-step strip
              could not express: ERROR and LOCALISATION are real states with
              no position on the linear path, and anything else unrecognised
              is said to be unrecognised rather than drawn as "not started".
            */}
            {progress.index === -1 && (
              <p
                className={`mt-2 text-xs ${
                  progress.isError
                    ? "text-red-600 dark:text-red-400"
                    : "text-gray-500 dark:text-gray-400"
                }`}
              >
                {progress.isError
                  ? "This project is in ERROR. It left the pipeline at whichever stage failed — see the Jobs tab."
                  : progress.isOffSequence
                  ? `State ${progress.state} sits outside the linear pipeline path.`
                  : `State ${progress.state} is not one this strip knows how to place.`}
              </p>
            )}
          </div>
        )}

        {/* ── Tab bar ────────────────────────────────────────────────── */}
        <div className="mb-8 border-b border-gray-300 dark:border-gray-700">
          <nav className="-mb-px flex gap-1 overflow-x-auto pb-px">
            {PROJECT_TABS.map((tab) => {
              const isActive = active === tab.id;
              return (
                <Link
                  key={tab.id}
                  href={tabHref(projectId, tab)}
                  aria-current={isActive ? "page" : undefined}
                  className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                    isActive
                      ? "border-blue-500 text-blue-600 dark:text-blue-400"
                      : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-800 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-200"
                  }`}
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* ── Tab content ────────────────────────────────────────────── */}
        {error && !project ? (
          <div className="rounded-lg border border-red-200 bg-red-100 p-4 text-red-600 dark:border-red-700 dark:bg-red-900/30 dark:text-red-400">
            {error.message || "Project not found."}
          </div>
        ) : isLoading && !project ? (
          <div className="flex min-h-[40vh] items-center justify-center">
            <LoadingSpinner size="lg" label="Loading project…" />
          </div>
        ) : (
          children
        )}
      </div>
    </ErrorBoundary>
  );
}
