"use client";

import React, { useMemo } from "react";
import type {
  PipelineStage,
  PipelineStageStatus,
  CheckpointData,
  FallbackLevel,
} from "@/types/monitoring";

/**
 * §8.2.1 Pipeline Progress Tracker — Stage DAG Visualization
 *
 * Renders the seven-stage content creation pipeline (§6.1) plus Final Render
 * as connected nodes in a directed acyclic graph.
 *
 * Each node displays:
 * - Stage name (abbreviated for compact display)
 * - Status color: pending (gray), running (blue animated), complete (green),
 *   failed (red), skipped (yellow)
 * - Checkpoint indicator: checkmark if checkpoint saved
 * - Fallback level badge (L1–L4 or DLQ) when applicable
 *
 * Connections between stages show directional flow with animated progress
 * for the currently active transition.
 *
 * Props:
 * - stages: ordered array of pipeline stage identifiers
 * - stageLabels: human-readable labels for each stage
 * - checkpoints: checkpoint data from GET /api/v1/jobs/{id}/checkpoints
 * - currentStage: the stage currently being executed
 * - jobStatus: overall job status string
 * - fallbackLevel: current fallback level for the active stage
 */

interface PipelineDAGProps {
  /** Ordered list of pipeline stage identifiers */
  stages: PipelineStage[];
  /** Human-readable labels for each stage */
  stageLabels: Record<PipelineStage, string>;
  /** Checkpoint data for each stage (from job detail) */
  checkpoints: CheckpointData[] | null;
  /** Currently executing pipeline stage */
  currentStage: PipelineStage | null;
  /** Overall job status (RUNNING, COMPLETE, ERROR, etc.) */
  jobStatus: string;
  /** Current fallback level for the active stage */
  fallbackLevel: FallbackLevel | null;
}

/** SVG dimensions and layout constants */
const SVG_WIDTH = 900;
const SVG_HEIGHT = 140;
const NODE_WIDTH = 90;
const NODE_HEIGHT = 44;
const NODE_SPACING = 14;
const NODE_Y = 48;
const CONNECTOR_Y = NODE_Y + NODE_HEIGHT / 2;

/** Status fill colors for DAG nodes */
const NODE_FILL: Record<PipelineStageStatus, string> = {
  PENDING: "#F3F4F6",
  RUNNING: "#DBEAFE",
  COMPLETE: "#D1FAE5",
  FAILED: "#FEE2E2",
  SKIPPED: "#FEF3C7",
};

/** Status stroke colors for DAG nodes */
const NODE_STROKE: Record<PipelineStageStatus, string> = {
  PENDING: "#D1D5DB",
  RUNNING: "#3B82F6",
  COMPLETE: "#10B981",
  FAILED: "#EF4444",
  SKIPPED: "#F59E0B",
};

/** Fallback level colors */
const FALLBACK_COLORS: Record<FallbackLevel, string> = {
  L1: "#10B981",
  L2: "#F59E0B",
  L3: "#F97316",
  L4: "#EF4444",
  DLQ: "#991B1B",
};

/**
 * Abbreviated stage names for compact node display.
 * Full names shown in tooltip.
 */
const SHORT_LABELS: Record<PipelineStage, string> = {
  TRANSCRIPT_REFINEMENT: "Transcript",
  STORYBOARD_GENERATION: "Storyboard",
  MEDIA_GENERATION: "Media Gen",
  MANIFEST_GENERATION: "Manifest",
  AUDIO_GENERATION: "Audio",
  TALKING_HEAD_RENDER: "Talk Head",
  PROTOTYPE_DRAFT: "Prototype",
  FINAL_RENDER: "Final",
};

export default function PipelineDAG({
  stages,
  stageLabels,
  checkpoints,
  currentStage,
  jobStatus,
  fallbackLevel,
}: PipelineDAGProps): React.ReactElement {
  /**
   * Compute node positions along the horizontal axis.
   * Nodes are evenly spaced across the SVG width.
   */
  const nodePositions = useMemo(() => {
    const totalNodeWidth = stages.length * NODE_WIDTH;
    const totalSpacing = (stages.length - 1) * NODE_SPACING;
    const startX = (SVG_WIDTH - totalNodeWidth - totalSpacing) / 2;

    return stages.map((stage, index) => ({
      stage,
      x: startX + index * (NODE_WIDTH + NODE_SPACING),
      y: NODE_Y,
    }));
  }, [stages]);

  /**
   * Get the status for a given stage from checkpoint data.
   * Falls back to PENDING if no checkpoint exists.
   */
  const getStageStatus = (stage: PipelineStage): PipelineStageStatus => {
    if (!checkpoints) return "PENDING";
    const cp = checkpoints.find((c) => c.stage === stage);
    if (!cp) return "PENDING";
    return cp.status;
  };

  /**
   * Check if a stage has a saved checkpoint.
   */
  const hasCheckpoint = (stage: PipelineStage): boolean => {
    if (!checkpoints) return false;
    return checkpoints.some(
      (c) => c.stage === stage && (c.status === "COMPLETE" || c.status === "RUNNING")
    );
  };

  return (
    <div className="w-full overflow-x-auto">
      <svg
        width={SVG_WIDTH}
        height={SVG_HEIGHT}
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className="mx-auto"
      >
        {/* ── Title ─────────────────────────────────────────────────── */}
        <text
          x={SVG_WIDTH / 2}
          y={20}
          textAnchor="middle"
          className="text-xs fill-gray-400 font-medium"
        >
          §6.1 Seven-Stage Pipeline + Final Render
        </text>

        {/* ── Connectors between nodes ─────────────────────────────── */}
        {nodePositions.slice(0, -1).map((pos, index) => {
          const nextPos = nodePositions[index + 1];
          const fromX = pos.x + NODE_WIDTH;
          const toX = nextPos.x;
          const fromStatus = getStageStatus(pos.stage);
          const toStatus = getStageStatus(nextPos.stage);

          /** Connector is active (animated) when transitioning between stages */
          const isActive =
            (fromStatus === "COMPLETE" || fromStatus === "RUNNING") &&
            toStatus === "RUNNING";

          return (
            <g key={`connector-${pos.stage}-${nextPos.stage}`}>
              {/* Background connector line */}
              <line
                x1={fromX}
                y1={CONNECTOR_Y}
                x2={toX}
                y2={CONNECTOR_Y}
                stroke={
                  fromStatus === "COMPLETE" && toStatus !== "PENDING"
                    ? "#10B981"
                    : "#E5E7EB"
                }
                strokeWidth={2}
                strokeDasharray={toStatus === "PENDING" ? "4 4" : "none"}
              />
              {/* Arrow head */}
              <polygon
                points={`${toX - 6},${CONNECTOR_Y - 4} ${toX},${CONNECTOR_Y} ${toX - 6},${CONNECTOR_Y + 4}`}
                fill={
                  fromStatus === "COMPLETE" && toStatus !== "PENDING"
                    ? "#10B981"
                    : "#E5E7EB"
                }
              />
              {/* Animated pulse on active transition */}
              {isActive && (
                <circle r={3} fill="#3B82F6">
                  <animateMotion
                    dur="1.5s"
                    repeatCount="indefinite"
                    path={`M${fromX},${CONNECTOR_Y} L${toX},${CONNECTOR_Y}`}
                  />
                </circle>
              )}
            </g>
          );
        })}

        {/* ── Stage Nodes ──────────────────────────────────────────── */}
        {nodePositions.map((pos) => {
          const status = getStageStatus(pos.stage);
          const isCurrent = currentStage === pos.stage;
          const hasCp = hasCheckpoint(pos.stage);

          /** Get checkpoint data for this stage */
          const cp = checkpoints?.find((c) => c.stage === pos.stage);

          return (
            <g key={pos.stage}>
              {/* Node background rectangle */}
              <rect
                x={pos.x}
                y={pos.y}
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={6}
                ry={6}
                fill={NODE_FILL[status]}
                stroke={NODE_STROKE[status]}
                strokeWidth={isCurrent ? 2.5 : 1.5}
                className={
                  status === "RUNNING"
                    ? "animate-pulse"
                    : "transition-all duration-300"
                }
              />

              {/* Stage label */}
              <text
                x={pos.x + NODE_WIDTH / 2}
                y={pos.y + 18}
                textAnchor="middle"
                className="text-[10px] fill-gray-800 font-medium"
                style={{ pointerEvents: "none" }}
              >
                {SHORT_LABELS[pos.stage]}
              </text>

              {/* Status text */}
              <text
                x={pos.x + NODE_WIDTH / 2}
                y={pos.y + 32}
                textAnchor="middle"
                className="text-[8px] fill-gray-500"
                style={{ pointerEvents: "none" }}
              >
                {status}
              </text>

              {/* Checkpoint indicator (small checkmark) */}
              {hasCp && (
                <circle
                  cx={pos.x + NODE_WIDTH - 8}
                  cy={pos.y + 8}
                  r={5}
                  fill="#10B981"
                  stroke="white"
                  strokeWidth={1}
                />
              )}
              {hasCp && (
                <text
                  x={pos.x + NODE_WIDTH - 8}
                  y={pos.y + 11}
                  textAnchor="middle"
                  className="text-[7px] fill-white font-bold"
                  style={{ pointerEvents: "none" }}
                >
                  ✓
                </text>
              )}

              {/* Fallback level badge — shown on current stage if applicable */}
              {isCurrent && fallbackLevel && fallbackLevel !== "L1" && (
                <g>
                  <rect
                    x={pos.x + NODE_WIDTH / 2 - 12}
                    y={pos.y + NODE_HEIGHT + 4}
                    width={24}
                    height={14}
                    rx={3}
                    fill={FALLBACK_COLORS[fallbackLevel]}
                  />
                  <text
                    x={pos.x + NODE_WIDTH / 2}
                    y={pos.y + NODE_HEIGHT + 14}
                    textAnchor="middle"
                    className="text-[8px] fill-white font-bold"
                    style={{ pointerEvents: "none" }}
                  >
                    {fallbackLevel}
                  </text>
                </g>
              )}

              {/* Retry count badge — shown if retries > 0 */}
              {cp && cp.retry_count > 0 && (
                <g>
                  <circle
                    cx={pos.x + 8}
                    cy={pos.y + 8}
                    r={7}
                    fill="#F59E0B"
                    stroke="white"
                    strokeWidth={1}
                  />
                  <text
                    x={pos.x + 8}
                    y={pos.y + 11}
                    textAnchor="middle"
                    className="text-[7px] fill-white font-bold"
                    style={{ pointerEvents: "none" }}
                  >
                    {cp.retry_count}
                  </text>
                </g>
              )}

              {/* Tooltip title element for hover */}
              <title>
                {stageLabels[pos.stage]} — {status}
                {cp?.started_at ? `\nStarted: ${cp.started_at}` : ""}
                {cp?.completed_at ? `\nCompleted: ${cp.completed_at}` : ""}
                {cp?.retry_count ? `\nRetries: ${cp.retry_count}` : ""}
                {cp?.node_id ? `\nNode: ${cp.node_id}` : ""}
              </title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
