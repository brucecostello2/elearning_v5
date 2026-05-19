"use client";

import React, { useMemo } from "react";
import { useJobs } from "@/hooks/useJobs";
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
 * Pipeline stages per §6 (7 stages):
 *   1. Script Refinement
 *   2. Storyboard Generation
 *   3. Visual Asset Creation
 *   4. Audio Production
 *   5. Talking-Head Lip Sync
 *   6. Composition & Rendering
 *   7. Quality Assurance
 */

interface PipelineStage {
  id: string;
  label: string;
  number: number;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { id: "script_refinement", label: "Script Refinement", number: 1 },
  { id: "storyboard_generation", label: "Storyboard Generation", number: 2 },
  { id: "visual_asset_creation", label: "Visual Assets", number: 3 },
  { id: "audio_production", label: "Audio Production", number: 4 },
  { id: "talking_head_lipsync", label: "Talking-Head Sync", number: 5 },
  { id: "composition_rendering", label: "Composition", number: 6 },
  { id: "quality_assurance", label: "Quality Assurance", number: 7 },
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

  /**
   * Derive stage statuses from the most recent job.
   */
  const stageStatuses = useMemo<Map<string, StageStatus>>(() => {
    const statusMap = new Map<string, StageStatus>();

    // Initialize all stages as pending
    for (const stage of PIPELINE_STAGES) {
      statusMap.set(stage.id, {
        stage_id: stage.id,
        status: "pending",
        progress_percent: 0,
      });
    }

    if (!jobs || jobs.length === 0) return statusMap;

    // Use the most recent job's stage data
    const latestJob = jobs[0];
    if (latestJob.stage_statuses) {
      for (const ss of latestJob.stage_statuses) {
        statusMap.set(ss.stage_id, ss);
      }
    }

    return statusMap;
  }, [jobs]);

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

  if (isLoading) {
    return <LoadingSpinner size="sm" label="Loading pipeline…" />;
  }

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
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
                <span className="text-[10px] text-gray-400 mt-1.5 text-center leading-tight">
                  {stage.label}
                </span>
                {status === "running" && ss?.progress_percent !== undefined && (
                  <div className="w-14 h-1 bg-gray-700 rounded-full mt-1 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${ss.progress_percent}%` }}
                    />
                  </div>
                )}
                {ss?.fallback_level && (
                  <span className="text-[9px] text-yellow-400 mt-0.5">
                    {ss.fallback_level}
                  </span>
                )}
                {status === "running" && ss?.eta_seconds && (
                  <span className="text-[9px] text-gray-500">
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
