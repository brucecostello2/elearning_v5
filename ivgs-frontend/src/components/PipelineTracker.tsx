"use client";

import React, { useMemo } from "react";
import { useJobs } from "@/hooks/useJobs";
import { useJobCheckpoints } from "@/hooks/useMonitoring";
import LoadingSpinner from "@/components/LoadingSpinner";

/**
 * §8.2.1 Pipeline Progress Tracker
 *
 * Visual stage DAG showing all pipeline stages with status indicators:
 *   - pending / running / complete / failed
 *   - Checkpoint data for each stage
 *   - Estimated completion time
 *   - Fallback level indicator (L1–L4 or DLQ)
 *
 * Pipeline stages per §6.1, the same eight the /monitoring DAG draws.
 */

interface PipelineStage {
  id: string;
  label: string;
  number: number;
}

/**
 * WP-40 Task 2 — the stage ids now match the rest of the app.
 *
 * This strip had its own seven-name vocabulary
 * (`script_refinement`, `visual_asset_creation`, `quality_assurance`, ...)
 * that nothing on the wire ever produced, and it read stage data from
 * `latestJob.stage_statuses` -- a field `JobResponse`
 * (schemas/render_job.py) does not send. So every node rendered grey
 * "pending" no matter what the run had done, including after a complete
 * end-to-end run.
 *
 * These are the same eight spec stages the /monitoring DAG draws, fed from
 * the same source: `pipeline_checkpoints` via
 * GET /api/v1/jobs/{id}/checkpoints, mapped by `mergeCheckpoints`.
 */
const PIPELINE_STAGES: PipelineStage[] = [
  { id: "TRANSCRIPT_REFINEMENT", label: "Transcript Refinement", number: 1 },
  { id: "STORYBOARD_GENERATION", label: "Storyboard Generation", number: 2 },
  { id: "MEDIA_GENERATION", label: "Media Generation", number: 3 },
  { id: "MANIFEST_GENERATION", label: "Manifest", number: 4 },
  { id: "AUDIO_GENERATION", label: "Audio Generation", number: 5 },
  { id: "TALKING_HEAD_RENDER", label: "Talking-Head Sync", number: 6 },
  { id: "PROTOTYPE_DRAFT", label: "Prototype Draft", number: 7 },
  { id: "FINAL_RENDER", label: "Final Render", number: 8 },
];

interface StageStatus {
  stage_id: string;
  status: "pending" | "running" | "complete" | "failed" | "skipped";
  progress_percent: number;
  fallback_level?: string;
  eta_seconds?: number;
}

interface PipelineTrackerProps {
  projectId: string;
}

export default function PipelineTracker({
  projectId,
}: PipelineTrackerProps): React.ReactElement {
  const { jobs, isLoading } = useJobs(projectId);

  /* The project's most recent render job -- the run this strip describes.
     WP-35: `Array.isArray` is the guard that actually holds; a paginated
     envelope is truthy and its `.length` is undefined. */
  const latestJobId =
    Array.isArray(jobs) && jobs.length > 0 ? (jobs[0] as { id?: string })?.id ?? null : null;

  const { checkpoints, isLoading: checkpointsLoading } =
    useJobCheckpoints(latestJobId);

  /**
   * Derive stage statuses from that job's checkpoints.
   */
  const stageStatuses = useMemo<Map<string, StageStatus>>(() => {
    const statusMap = new Map<string, StageStatus>();

    for (const stage of PIPELINE_STAGES) {
      statusMap.set(stage.id, {
        stage_id: stage.id,
        status: "pending",
        progress_percent: 0,
      });
    }

    for (const cp of checkpoints) {
      if (!statusMap.has(cp.stage)) continue;
      const status: StageStatus["status"] =
        cp.status === "COMPLETE"
          ? "complete"
          : cp.status === "FAILED"
          ? "failed"
          : cp.status === "RUNNING"
          ? "running"
          : "pending";
      statusMap.set(cp.stage, {
        stage_id: cp.stage,
        status,
        progress_percent: status === "complete" ? 100 : status === "running" ? 50 : 0,
      });
    }

    return statusMap;
  }, [checkpoints]);

  const getStatusColor = (
    status: string
  ): { bg: string; text: string; ring: string } => {
    switch (status) {
      case "complete":
        return {
          bg: "bg-green-600",
          text: "text-white",
          ring: "ring-green-600/30",
        };
      case "running":
        return {
          bg: "bg-blue-600",
          text: "text-white",
          ring: "ring-blue-600/30",
        };
      case "failed":
        return {
          bg: "bg-red-600",
          text: "text-white",
          ring: "ring-red-600/30",
        };
      default:
        return {
          bg: "bg-gray-700",
          text: "text-gray-400",
          ring: "ring-gray-700/30",
        };
    }
  };

  const getConnectorColor = (status: string): string => {
    switch (status) {
      case "complete":
        return "bg-green-600";
      case "running":
        return "bg-blue-600";
      case "failed":
        return "bg-red-600";
      default:
        return "bg-gray-700";
    }
  };

  const formatEta = (seconds: number | undefined): string => {
    if (!seconds) return "";
    if (seconds < 60) return `~${seconds}s`;
    const mins = Math.floor(seconds / 60);
    return `~${mins}m`;
  };

  if (isLoading || checkpointsLoading) {
    return <LoadingSpinner size="sm" label="Loading pipeline…" />;
  }

  return (
    <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl p-6">
      {/* Horizontal Stage Visualization */}
      <div className="flex items-center justify-between gap-1 overflow-x-auto pb-2">
        {PIPELINE_STAGES.map((stage, idx) => {
          const ss = stageStatuses.get(stage.id);
          const status = ss?.status || "pending";
          const colors = getStatusColor(status);

          return (
            <React.Fragment key={stage.id}>
              {/* Stage Node */}
              <div className="flex flex-col items-center min-w-[80px]">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm ${colors.bg} ${colors.text} ring-4 ${colors.ring} transition-all`}
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
                <span className="text-[10px] text-gray-500 dark:text-gray-400 mt-1.5 text-center leading-tight">
                  {stage.label}
                </span>
                {status === "running" && ss?.progress_percent !== undefined && (
                  <div className="w-14 h-1 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${ss.progress_percent}%` }}
                    />
                  </div>
                )}
                {ss?.fallback_level && (
                  <span className="text-[9px] text-yellow-600 dark:text-yellow-400 mt-0.5">
                    {ss.fallback_level}
                  </span>
                )}
                {status === "running" && ss?.eta_seconds && (
                  <span className="text-[9px] text-gray-500 dark:text-gray-400">
                    {formatEta(ss.eta_seconds)}
                  </span>
                )}
              </div>

              {/* Connector Line */}
              {idx < PIPELINE_STAGES.length - 1 && (
                <div
                  className={`flex-1 h-0.5 min-w-[20px] ${getConnectorColor(
                    status === "complete" ? "complete" : "pending"
                  )} transition-all`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
