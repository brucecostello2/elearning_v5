"use client";

import React, { useMemo } from "react";
import { useProjectPipelineRun } from "@/hooks/useMonitoring";
import LoadingSpinner from "@/components/LoadingSpinner";
import {
  PIPELINE_STAGE_IDS,
  stageStatuses,
  type StageDisplayStatus,
} from "@/lib/pipeline-run";

/**
 * §8.2.1 Pipeline Progress Tracker
 *
 * WP-40 Task 2 replaced this strip's invented seven-name stage vocabulary
 * and its read of `latestJob.stage_statuses` (a field `JobResponse` does not
 * send) with the eight spec stages fed from `pipeline_checkpoints`. That
 * half is correct and is unchanged.
 *
 * WP-43 Task 5. It still rendered all-grey for the reference project, and
 * the operator's screenshot was accurate rather than stale. The remaining
 * fault was JOB SELECTION: this component took `jobs[0]`, and
 * `GET /projects/{id}/jobs` is newest-first. On c12fa967 the newest seven
 * rows are `storyboard_generation` jobs, still `pending`, with zero
 * checkpoints between them; the run that produced the project's 720p draft
 * is the eighth row (`bd99fe37` — transcript refinement through prototype
 * draft, six of seven stages complete). The strip was faithfully drawing an
 * empty job.
 *
 * `useProjectPipelineRun` now picks the newest job that actually has
 * checkpoints, and the strip NAMES it. That matters: once the run is
 * identified, a grey node means "this run did not reach that stage" and can
 * no longer mean "the strip is looking somewhere else".
 */

interface PipelineStage {
  id: string;
  label: string;
  number: number;
}

const STAGE_LABELS: Record<string, string> = {
  TRANSCRIPT_REFINEMENT: "Transcript Refinement",
  STORYBOARD_GENERATION: "Storyboard Generation",
  MEDIA_GENERATION: "Media Generation",
  MANIFEST_GENERATION: "Manifest",
  AUDIO_GENERATION: "Audio Generation",
  TALKING_HEAD_RENDER: "Talking-Head Sync",
  PROTOTYPE_DRAFT: "Prototype Draft",
  FINAL_RENDER: "Final Render",
};

const PIPELINE_STAGES: PipelineStage[] = PIPELINE_STAGE_IDS.map((id, i) => ({
  id,
  label: STAGE_LABELS[id] ?? id,
  number: i + 1,
}));

interface PipelineTrackerProps {
  projectId: string;
}

function statusColors(status: StageDisplayStatus): {
  bg: string;
  text: string;
  ring: string;
} {
  switch (status) {
    case "complete":
      return { bg: "bg-green-600", text: "text-white", ring: "ring-green-600/30" };
    case "running":
      return { bg: "bg-blue-600", text: "text-white", ring: "ring-blue-600/30" };
    case "failed":
      return { bg: "bg-red-600", text: "text-white", ring: "ring-red-600/30" };
    default:
      return {
        bg: "bg-gray-200 dark:bg-gray-700",
        text: "text-gray-500 dark:text-gray-400",
        ring: "ring-gray-300/30 dark:ring-gray-700/30",
      };
  }
}

export default function PipelineTracker({
  projectId,
}: PipelineTrackerProps): React.ReactElement {
  const { run, isLoading, truncated } = useProjectPipelineRun(projectId);

  const statuses = useMemo(
    () => stageStatuses(run?.checkpoints ?? []),
    [run],
  );

  if (isLoading && !run) {
    return <LoadingSpinner size="sm" label="Loading pipeline…" />;
  }

  /* No job of this project has produced a single mappable checkpoint. Say
     that, rather than drawing eight grey circles that look like a pipeline
     which has not started when it may simply never have checkpointed. */
  if (!run || run.jobId === null) {
    return (
      <div className="rounded-xl border border-gray-300 bg-gray-100 p-6 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
        {run && run.examined > 0 ? (
          <>
            No pipeline checkpoints have been recorded for this project.{" "}
            {run.examined} job{run.examined === 1 ? "" : "s"} exist
            {run.examined === 1 ? "s" : ""} but none has written a stage
            checkpoint, so there is no run to show progress for. The Jobs tab
            lists them.
          </>
        ) : (
          <>This project has no pipeline jobs yet.</>
        )}
      </div>
    );
  }

  const completed = Object.values(statuses).filter(
    (s) => s === "complete",
  ).length;

  return (
    <div className="rounded-xl border border-gray-300 bg-gray-100 p-6 dark:border-gray-700 dark:bg-gray-800">
      {/* WP-60 Task 5 — MIXED PROVENANCE, PRESENTED AS ONE FACT.
          This line read e.g. "Run 1e65b11d · final render · started 8:39:32"
          above a strip showing Transcript Refinement and Storyboard Generation
          as the stages that ran. Both halves are true of that run and they
          come from different places:

            "final render"        = render_jobs.job_type — WHAT WAS REQUESTED
                                    when the run was triggered.
            the completed stages  = pipeline_checkpoints for that job_id —
                                    WHAT ACTUALLY EXECUTED.

          Verified on the live row: job 1e65b11d-edec-48cf-afaf-9ddf4e448d0b
          is job_type `final_render`, status success, and holds exactly two
          checkpoints, `transcript_refinement` (stage 1) and
          `storyboard_generation` (stage 2), both `complete`.

          The trigger label is authoritative for INTENT; the checkpoints are
          authoritative for EXECUTION. Neither is wrong and neither can stand
          in for the other, so each is now named for what it measures. */}
      <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <span>
          Run{" "}
          <span className="font-mono text-gray-700 dark:text-gray-300">
            {run.jobId.slice(0, 8)}
          </span>
          {run.jobType
            ? ` · requested as ${run.jobType.replace(/_/g, " ")}`
            : ""}
          {run.createdAt
            ? ` · started ${new Date(run.createdAt).toLocaleString()}`
            : ""}
        </span>
        <span
          title="Counted from this run's own pipeline_checkpoints rows - what executed, not what was requested."
        >
          {completed} of {PIPELINE_STAGES.length} stages recorded complete for
          this run
        </span>
        {/* The stepper below highlights the stage AFTER the last complete one.
            "2 complete" and "the strip sits on stage 3" are the same fact read
            two ways, and saying so is cheaper than making a reader work it
            out. */}
        {completed < PIPELINE_STAGES.length && (
          <span title="The next stage this run would reach. It is not a stage that has run.">
            next: stage {completed + 1} ·{" "}
            {PIPELINE_STAGES[completed]?.label ?? "—"}
          </span>
        )}
        {run.newerWithoutCheckpoints > 0 && (
          <span>
            ({run.newerWithoutCheckpoints} newer job
            {run.newerWithoutCheckpoints === 1 ? "" : "s"} recorded no
            checkpoints)
          </span>
        )}
        {truncated > 0 && (
          <span>({truncated} older jobs not examined)</span>
        )}
      </div>

      <div className="flex items-center justify-between gap-1 overflow-x-auto pb-2">
        {PIPELINE_STAGES.map((stage, idx) => {
          const status = statuses[stage.id] ?? "pending";
          const colors = statusColors(status);

          return (
            <React.Fragment key={stage.id}>
              <div className="flex min-w-[80px] flex-col items-center">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold ${colors.bg} ${colors.text} ring-4 ${colors.ring} transition-all`}
                  title={`${stage.label}: ${status}`}
                >
                  {status === "complete" ? (
                    "✓"
                  ) : status === "running" ? (
                    <span className="animate-pulse">{stage.number}</span>
                  ) : status === "failed" ? (
                    "✕"
                  ) : (
                    stage.number
                  )}
                </div>
                <span className="mt-1.5 text-center text-[10px] leading-tight text-gray-500 dark:text-gray-400">
                  {stage.label}
                </span>
              </div>

              {idx < PIPELINE_STAGES.length - 1 && (
                <div
                  className={`h-0.5 min-w-[20px] flex-1 transition-all ${
                    status === "complete"
                      ? "bg-green-600"
                      : "bg-gray-200 dark:bg-gray-700"
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
