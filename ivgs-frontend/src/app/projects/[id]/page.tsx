"use client";

import React, { useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { canTriggerPipeline, useProjects } from "@/hooks/useProjects";
import { useAuth } from "@/hooks/useAuth";
import PipelineTracker from "@/components/PipelineTracker";
import PipelineGateButton from "@/components/PipelineGateButton";
import PresetApplyPanel from "@/components/project/PresetApplyPanel";
import DeleteProjectDialog from "@/components/project/DeleteProjectDialog";
import { PROJECT_TABS, tabHref } from "@/lib/project-tabs";

/**
 * §8.1.3 Project Detail — the Overview tab.
 *
 * WP-43 Task 1. This file used to own the project header, the lifecycle
 * strip and the whole tab bar, which is why those three things existed on
 * this page and nowhere else. They now live in
 * `src/components/project/ProjectShell.tsx`, rendered by the segment layout
 * for every `/projects/{id}/*` route. What is left here is the Overview tab
 * itself: the actions, the pipeline progress strip and the metadata.
 *
 * The loading and error states also moved to the shell -- it holds the same
 * SWR key, so a project that fails to load fails once, in one place, rather
 * than in eleven pages with eleven wordings.
 */
export default function ProjectOverviewPage(): React.ReactElement | null {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const projectId = params.id as string;
  const { project, triggerPipeline } = useProjects(projectId);

  /**
   * WP-40 Task 3b. Operator or admin only -- `POST /projects/{id}/trigger`
   * is behind `require_operator_or_admin`, so a viewer must not see the
   * button at all rather than press it into a 403.
   */
  const canTrigger =
    (user?.role === "admin" || user?.role === "operator") &&
    canTriggerPipeline(project?.state);

  /* `POST /projects/{id}/apply-preset` is behind `require_operator_or_admin`,
     so a viewer must not see the control rather than press it into a 403 —
     the same WP-40 Task 3b rule as the trigger button above. Unlike
     `canTrigger` this does not depend on lifecycle state: a preset can be
     applied to a project at any point. */
  const canManage = user?.role === "admin" || user?.role === "operator";

  /* WP-59. `DELETE /projects/{id}` is behind `require_admin` -- an operator is
     not an admin here, deliberately, because this is the one action in the
     application that destroys work irreversibly. An operator must not see the
     button and then be refused by the server; the same WP-40 Task 3b rule as
     the trigger and preset controls above. */
  const canDelete = user?.role === "admin";

  /** Format runtime from seconds to MM:SS display. */
  const formatRuntime = useCallback((seconds: number | null | undefined): string => {
    if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }, []);

  const formatDate = useCallback((value: unknown): string => {
    if (typeof value !== "string" || value.length === 0) return "—";
    const d = new Date(value);
    return Number.isFinite(d.getTime()) ? d.toLocaleString() : "—";
  }, []);

  /* The shell renders loading and error; if it let us through without a
     project there is nothing to draw. */
  if (!project) return null;

  /* `target_languages` is NOT on the project detail payload -- verified live
     2026-08-25, which sends `language_variants: [{language_code, state}]`
     instead. Read the shape that exists rather than the one the interface
     used to claim. */
  const languageCodes: string[] = Array.isArray(project.language_variants)
    ? project.language_variants
        .map((v) => v?.language_code)
        .filter((c): c is string => typeof c === "string" && c.length > 0)
    : Array.isArray(project.target_languages)
    ? project.target_languages
    : [];

  return (
    <div className="space-y-8">
      {/* ── Actions ──────────────────────────────────────────────────── */}
      {(canTrigger || project.state === "COMPLETE" || canDelete) && (
        <div className="flex flex-wrap items-center gap-2">
          {/* WP-40 Task 3b (ledger M6). POST /projects/{id}/trigger accepts
              only DRAFT and USER_REVIEW (project_service.py:266), and is
              guarded by require_operator_or_admin -- so the button is shown
              for exactly those states and never to a viewer. A 409 (wrong
              state, or "no transcripts uploaded") is surfaced with the
              server's own wording. */}
          {canTrigger && (
            <PipelineGateButton
              label={
                project.state === "USER_REVIEW"
                  ? "Start final render"
                  : "Trigger pipeline"
              }
              confirmTitle={
                project.state === "USER_REVIEW"
                  ? "Start the final render?"
                  : "Trigger the pipeline?"
              }
              confirmBody={
                project.state === "USER_REVIEW"
                  ? "This accepts the draft and starts the full-resolution render. It consumes GPU time."
                  : "This starts transcript refinement and runs the pipeline forward. It requires at least one uploaded transcript and consumes GPU time."
              }
              confirmLabel={
                project.state === "USER_REVIEW" ? "Start render" : "Trigger"
              }
              successMessage="Pipeline triggered."
              onConfirm={(tier) => triggerPipeline(tier)}
            />
          )}
          {project.state === "COMPLETE" && (
            <button
              type="button"
              onClick={() => router.push(`/player/${project.id}`)}
              className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700"
            >
              ▶ Watch
            </button>
          )}
          {/* WP-59 spec item 1: a Delete button on the project page. Pushed to
              the right so it is never adjacent to the action an operator
              actually came here to press. */}
          {canDelete && (
            <div className="ml-auto">
              <DeleteProjectDialog
                projectId={projectId}
                projectName={project.name}
                canDelete={canDelete}
              />
            </div>
          )}
        </div>
      )}

      {/* ── Pipeline Progress per §8.2.1 ─────────────────────────────── */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          Pipeline Progress
        </h2>
        <PipelineTracker projectId={projectId} />
      </section>

      {/* ── Project metadata ─────────────────────────────────────────── */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          Project Details
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <MetadataCard label="Video Name" value={project.name} />
          <MetadataCard
            label="Maximum Runtime"
            value={formatRuntime(project.max_runtime_seconds)}
          />
          <MetadataCard label="Created" value={formatDate(project.created_at)} />
          {/* WP-60 Task 5. "LAST UPDATED" MEASURED THE ROW, NOT THE PROJECT.
              It renders `projects.updated_at`, which moves when the project
              RECORD is edited and does not move when a run starts, a stage
              completes or an asset lands. That is why the screenshot showed
              "Last updated 8:31:10 AM" above a run that started at 8:39:32 AM
              - not a clock problem and not a stale cache, just a column
              measuring something narrower than its label implied. Verified on
              the live row: projects.updated_at = 2026-08-25T15:31:10Z, and
              render_jobs 1e65b11d started 2026-08-25T15:39:32Z. */}
          <MetadataCard
            label="Project Record Edited"
            value={formatDate(project.updated_at)}
            title="When this project's own record was last changed (name, description, settings). Pipeline runs and generated assets do not move it - see Pipeline Progress above for run activity."
          />
          <MetadataCard
            label="Scenes"
            value={
              typeof project.scene_count === "number"
                ? String(project.scene_count)
                : "—"
            }
          />
          <MetadataCard
            label="Languages"
            value={
              languageCodes.length > 0 ? languageCodes.join(", ") : "None yet"
            }
          />
        </div>
      </section>

      {/* ── Preset application — AD-09.5 / AD-09.15 criterion 1 ──────── */}
      <PresetApplyPanel projectId={projectId} canApply={canManage} />

      {/* ── Quick access ─────────────────────────────────────────────── */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          Quick Access
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {PROJECT_TABS.filter((t) => t.segment).map((tab) => (
            <Link
              key={tab.id}
              href={tabHref(projectId, tab)}
              className="rounded-lg border border-gray-300 bg-gray-100 p-4 text-left transition-colors hover:border-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-gray-600"
            >
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {tab.label}
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

/** Simple metadata display card for the Overview tab. */
function MetadataCard({
  label,
  value,
  /** What this figure measures, when the label alone cannot carry it. */
  title,
}: {
  label: string;
  value: string;
  title?: string;
}): React.ReactElement {
  return (
    <div className="rounded-lg border border-gray-300 bg-gray-100 p-4 dark:border-gray-700 dark:bg-gray-800">
      <dt
        className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400"
        title={title}
      >
        {label}
      </dt>
      <dd className="mt-1 text-sm text-gray-900 dark:text-white">{value}</dd>
    </div>
  );
}
