"use client";

import React from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

import { useProjects } from "@/hooks/useProjects";
import StateBadge from "@/components/StateBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import { PROJECT_TABS, activeTabId, tabHref } from "@/lib/project-tabs";
import { projectStateProgress } from "@/lib/project-state";
import {
  useProjectProgress,
  stepBarClasses,
  stepDotClasses,
  tabDotClasses,
} from "@/hooks/useProjectProgress";

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
  /* WP-62 Task 3, RULED. THE STEPPER IS THE PROGRESS DISPLAY, and it is
     computed ONCE on the server. It used to be derived here from
     `project.state` alone, which is why it was frozen fleet-wide: that column
     stopped advancing the moment a stale job's failure callback reset a
     project to DRAFT mid-run, and every later stage hop was refused as an
     illegal transition out of DRAFT. The same payload feeds the tab
     indicators below, so the two cannot disagree. */
  const { progress } = useProjectProgress(projectId);
  const steps = progress?.steps ?? [];
  const stateInfo = projectStateProgress(project?.state);

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

        {/* ── The progress display: ONE stepper, dynamic and coloured ──
            WP-62 Task 3, RULED. The 11-step stepper IS the progress display.

            complete green · active blue · failed red · gated amber · pending
            grey. Amber is the one that had nowhere to appear before this
            package: the two human review gates had no record, so no surface
            could say "this is waiting on you" and the pipeline simply looked
            stopped. */}
        {project && steps.length > 0 && (
          <div className="mb-5 overflow-x-auto rounded-xl border border-gray-300 bg-gray-100 px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
            <div className="flex min-w-max items-center gap-1">
              {steps.map((step, idx) => (
                <React.Fragment key={step.key}>
                  <div className="flex min-w-[64px] flex-col items-center">
                    <div
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${stepDotClasses(
                        step.status
                      )}`}
                      title={
                        step.gate && step.status === "gated"
                          ? `Waiting on you: ${
                              progress?.gates?.[step.gate]?.reason ??
                              "this review gate is open"
                            }`
                          : `${step.label} — ${step.status}`
                      }
                    >
                      {step.status === "complete"
                        ? "✓"
                        : step.status === "failed"
                        ? "!"
                        : step.status === "gated"
                        ? "?"
                        : step.index}
                    </div>
                    <span className="mt-1 whitespace-nowrap text-[10px] leading-tight text-gray-500 dark:text-gray-400">
                      {step.label}
                    </span>
                  </div>
                  {idx < steps.length - 1 && (
                    <div
                      className={`h-0.5 w-4 ${stepBarClasses(step.status)}`}
                    />
                  )}
                </React.Fragment>
              ))}
            </div>

            {/* An open gate is named in words under the strip. An amber circle
                tells the operator something is waiting; it does not tell them
                what to do about it, and this is the one place every tab can
                see. */}
            {steps
              .filter((s) => s.status === "gated" && s.gate)
              .map((s) => (
                <p
                  key={s.gate}
                  className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-400"
                >
                  {s.label} gate is open —{" "}
                  {progress?.gates?.[s.gate as string]?.reason ??
                    "awaiting a decision"}
                  .
                </p>
              ))}

            {/* WP-62 Task 3. THE STORED COLUMN AND THE DERIVED POSITION, when
                they disagree — shown, not silently corrected.

                Every project that ran before this package has a stale
                `projects.state`: the P1.4q reset walked it back to DRAFT
                mid-run and the stage hops that followed were refused. This
                package fixes the writer and recomputes the stepper on read; it
                deliberately hand-edits no stored state. So the gap persists on
                old rows, and an operator reading "DRAFT" on the badge above a
                green Final Render needs to be told why rather than left to
                wonder which is lying. */}
            {progress && !progress.stored_state_matches && (
              <p className="mt-2 text-[11px] leading-tight text-gray-500 dark:text-gray-400">
                The stepper above is computed from the pipeline checkpoints this
                project actually wrote. The stored state column says{" "}
                <span className="font-mono">{progress.stored_state}</span>,
                which is behind the work recorded (
                <span className="font-mono">{progress.derived_state}</span>).
                Runs before 2026-08-26 were reset to DRAFT mid-flight by a
                stale-job callback; nothing here has been edited to hide it.
              </p>
            )}

            {stateInfo.index === -1 && (
              <p
                className={`mt-2 text-xs ${
                  stateInfo.isError
                    ? "text-red-600 dark:text-red-400"
                    : "text-gray-500 dark:text-gray-400"
                }`}
              >
                {stateInfo.isError
                  ? "This project is in ERROR. It left the pipeline at whichever stage failed — see the Jobs tab."
                  : stateInfo.isOffSequence
                  ? `State ${stateInfo.state} sits outside the linear pipeline path.`
                  : `State ${stateInfo.state} is not one this strip knows how to place.`}
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
                  {/* WP-62 Task 3. The tab indicator comes from the SAME
                      computation as the stepper. Tabs that are not a pipeline
                      stage (Overview, Prompts, Jobs, Languages) are absent
                      from `tabs` and get no dot — a grey dot on Jobs would
                      read as "no jobs". */}
                  {(() => {
                    const dot = tabDotClasses(progress?.tabs?.[tab.id]);
                    return dot ? (
                      <span
                        className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle ${dot}`}
                        aria-hidden="true"
                      />
                    ) : null;
                  })()}
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
