"use client";

import React, { useState, useCallback, useRef, useMemo, useEffect } from "react";
import type { Scene, SceneStatus } from "@/types/storyboard";
import {
  mediaTypeLabel,
  sceneBadge,
  sceneTitle,
} from "@/lib/scenes";

/**
 * §8.2.5 Composition Timeline Editor (applied to Storyboard context)
 *
 * Horizontal timeline displaying all scenes proportional to their duration.
 * Color-coded by status:
 *   - PENDING: gray
 *   - GENERATING: blue (pulsing)
 *   - COMPLETE: green
 *   - ERROR: red
 *   - REGENERATING: yellow (pulsing)
 *
 * Features:
 * - Proportional width based on duration_seconds
 * - Zoom slider (50% – 400%)
 * - Pan via horizontal scroll
 * - Click to edit scene
 * - Hover tooltip with scene details
 * - Total duration display
 * - Current playhead position indicator
 *
 * @param projectId - Current project ID
 * @param scenes - Array of scenes (already filtered)
 * @param canEdit - Whether user can edit
 * @param onEditScene - Callback to open scene edit modal
 * @param onRegenerateScene - Callback to regenerate a scene
 * @param totalDuration - Total duration of all scenes in seconds
 */

interface SceneTimelineProps {
  /** Current project ID */
  projectId: string;
  /** Array of scenes to display */
  scenes: Scene[];
  /** Whether user can edit */
  canEdit: boolean;
  /** Open edit modal for a scene */
  onEditScene: (scene: Scene) => void;
  /** Trigger regeneration for a scene */
  onRegenerateScene: (sceneId: string) => Promise<void>;
  /** Total duration of all scenes */
  totalDuration: number;
}

/** Status-based color mapping for timeline segments */
const TIMELINE_COLORS: Record<SceneStatus, string> = {
  PENDING: "bg-gray-600",
  GENERATING: "bg-blue-500 animate-pulse",
  COMPLETE: "bg-green-600",
  ERROR: "bg-red-600",
  REGENERATING: "bg-yellow-500 animate-pulse",
};

/** Status-based border color for hover state */
const TIMELINE_HOVER_COLORS: Record<SceneStatus, string> = {
  PENDING: "hover:bg-gray-500",
  GENERATING: "hover:bg-blue-400",
  COMPLETE: "hover:bg-green-500",
  ERROR: "hover:bg-red-500",
  REGENERATING: "hover:bg-yellow-400",
};

/**
 * Format seconds to MM:SS string.
 */
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

/**
 * Generate tick marks for the timeline ruler.
 * @param totalSeconds - Total duration in seconds
 * @param zoom - Current zoom level (1 = 100%)
 * @returns Array of tick positions with labels
 */
function generateTicks(
  totalSeconds: number,
  zoom: number
): { position: number; label: string }[] {
  if (totalSeconds <= 0) return [];

  // Determine tick interval based on zoom level
  let interval: number;
  if (zoom >= 3) {
    interval = 1; // Every second at high zoom
  } else if (zoom >= 2) {
    interval = 2;
  } else if (zoom >= 1) {
    interval = 5;
  } else {
    interval = 10;
  }

  const ticks: { position: number; label: string }[] = [];
  for (let t = 0; t <= totalSeconds; t += interval) {
    ticks.push({
      position: (t / totalSeconds) * 100,
      label: formatTime(t),
    });
  }
  return ticks;
}

export default function SceneTimeline({
  projectId,
  scenes,
  canEdit,
  onEditScene,
  onRegenerateScene,
  totalDuration,
}: SceneTimelineProps): React.ReactElement {
  // ── State ────────────────────────────────────────────────────────────
  const [zoom, setZoom] = useState<number>(1);
  const [hoveredSceneId, setHoveredSceneId] = useState<string | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);

  // ── Refs ─────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null);

  /** Compute cumulative start time for each scene */
  const sceneTimings = useMemo<
    { scene: Scene; startTime: number; endTime: number; widthPercent: number }[]
  >(() => {
    let cumulativeTime = 0;
    return scenes.map((scene) => {
      /* WP-60 Task 7. `?? 0` is CORRECT here and wrong three lines below.
         This is GEOMETRY: a scene with no recorded duration occupies no width
         on the strip and advances the cumulative clock by nothing, which is the
         only coherent layout for an unknown length. It becomes a fabrication
         only when the same substituted 0 is FORMATTED AND SHOWN as "0:00" —
         a measured, zero-length scene. The display sites below say "no
         duration" instead. All 58 live scenes carry one, so this is a latent
         defect rather than a visible one, and it is ledgered as such. */
      const duration = scene.duration_seconds ?? 0;
      const startTime = cumulativeTime;
      cumulativeTime += duration;
      return {
        scene,
        startTime,
        endTime: startTime + duration,
        widthPercent:
          totalDuration > 0 ? (duration / totalDuration) * 100 : 0,
      };
    });
  }, [scenes, totalDuration]);

  /** Ruler ticks */
  const ticks = useMemo(
    () => generateTicks(totalDuration, zoom),
    [totalDuration, zoom]
  );

  /** Handle mouse hover for tooltip */
  const handleMouseMove = useCallback(
    (e: React.MouseEvent, sceneId: string): void => {
      setHoveredSceneId(sceneId);
      setTooltipPosition({ x: e.clientX, y: e.clientY });
    },
    []
  );

  /** Handle mouse leave */
  const handleMouseLeave = useCallback((): void => {
    setHoveredSceneId(null);
    setTooltipPosition(null);
  }, []);

  /** Get hovered scene data */
  const hoveredTiming = useMemo(() => {
    if (!hoveredSceneId) return null;
    return sceneTimings.find((t) => t.scene.id === hoveredSceneId) ?? null;
  }, [hoveredSceneId, sceneTimings]);

  // ── Empty State ─────────────────────────────────────────────────────
  if (scenes.length === 0 || totalDuration <= 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          No scenes to display in timeline view.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Controls ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {scenes.length} scene{scenes.length !== 1 ? "s" : ""} ·{" "}
            {formatTime(totalDuration)}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-500 dark:text-gray-400">Zoom:</label>
          <input
            type="range"
            min={0.5}
            max={4}
            step={0.1}
            value={zoom}
            onChange={(e) => setZoom(parseFloat(e.target.value))}
            className="w-32 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
          />
          <span className="text-xs text-gray-500 dark:text-gray-400 w-12 text-right">
            {Math.round(zoom * 100)}%
          </span>
        </div>
      </div>

      {/* ── Timeline Container ────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="overflow-x-auto bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700"
      >
        <div
          style={{ width: `${zoom * 100}%`, minWidth: "100%" }}
          className="relative"
        >
          {/* ── Ruler ──────────────────────────────────────────── */}
          <div className="relative h-8 border-b border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900/50">
            {ticks.map((tick, i) => (
              <div
                key={i}
                className="absolute top-0 h-full flex flex-col items-center"
                style={{ left: `${tick.position}%` }}
              >
                <div className="w-px h-3 bg-gray-600" />
                <span className="text-[9px] text-gray-500 dark:text-gray-400 mt-0.5 select-none">
                  {tick.label}
                </span>
              </div>
            ))}
          </div>

          {/* ── Scene Segments ────────────────────────────────── */}
          <div className="relative h-24 flex">
            {sceneTimings.map(({ scene, startTime, endTime, widthPercent }) => (
              <div
                key={scene.id}
                className={`relative h-full border-r border-gray-900 flex items-center justify-center overflow-hidden transition-colors duration-150 ${
                  TIMELINE_COLORS[scene.status]
                } ${
                  canEdit ? TIMELINE_HOVER_COLORS[scene.status] : ""
                } ${canEdit ? "cursor-pointer" : "cursor-default"}`}
                style={{ width: `${widthPercent}%` }}
                onClick={() => canEdit && onEditScene(scene)}
                onMouseMove={(e) => handleMouseMove(e, scene.id)}
                onMouseLeave={handleMouseLeave}
                role="button"
                aria-label={`Scene ${sceneTitle(scene.scene_index)}: ${
                  typeof scene.duration_seconds === "number"
                    ? formatTime(scene.duration_seconds)
                    : "duration not recorded"
                }`}
              >
                {/* Scene number & duration label */}
                <div className="flex flex-col items-center gap-0.5 px-1">
                  <span
                    title={sceneTitle(scene.scene_index)}
                    className="text-xs font-bold text-gray-900 dark:text-white drop-shadow"
                  >
                    {sceneBadge(scene.scene_index)}
                  </span>
                  {widthPercent > 3 && (
                    <span className="text-[9px] text-gray-900 dark:text-white truncate max-w-full px-1">
                      {typeof scene.duration_seconds === "number"
                        ? formatTime(scene.duration_seconds)
                        : "--:--"}
                    </span>
                  )}
                  {widthPercent > 8 && (
                    <span className="text-[8px] text-gray-900 dark:text-white truncate max-w-full px-1 text-center">
                      {scene.narration_text.slice(0, 30)}
                      {scene.narration_text.length > 30 ? "…" : ""}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* ── Scene Labels Row ──────────────────────────────── */}
          <div className="relative h-6 flex border-t border-gray-300 dark:border-gray-700">
            {sceneTimings.map(({ scene, widthPercent }) => (
              <div
                key={scene.id}
                className="h-full flex items-center justify-center overflow-hidden border-r border-gray-200 dark:border-gray-800"
                style={{ width: `${widthPercent}%` }}
              >
                {widthPercent > 5 && (
                  <span className="text-[9px] text-gray-500 dark:text-gray-400 truncate px-1">
                    {mediaTypeLabel(scene.media_type)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Tooltip ───────────────────────────────────────────────── */}
      {hoveredTiming && tooltipPosition && (
        <div
          className="fixed z-50 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg shadow-xl px-4 py-3 pointer-events-none"
          style={{
            left: tooltipPosition.x + 12,
            top: tooltipPosition.y - 80,
          }}
        >
          <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">
            Scene {sceneBadge(hoveredTiming.scene.scene_index)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
            <div>
              Duration:{" "}
              {typeof hoveredTiming.scene.duration_seconds === "number"
                ? formatTime(hoveredTiming.scene.duration_seconds)
                : "not recorded"}
            </div>
            <div>
              Start: {formatTime(hoveredTiming.startTime)} — End:{" "}
              {formatTime(hoveredTiming.endTime)}
            </div>
            <div>Type: {mediaTypeLabel(hoveredTiming.scene.media_type)}</div>
            <div>Status: {hoveredTiming.scene.status}</div>
            <div className="mt-1 text-gray-500 dark:text-gray-400 max-w-xs truncate">
              {hoveredTiming.scene.narration_text.slice(0, 80)}
              {hoveredTiming.scene.narration_text.length > 80 ? "…" : ""}
            </div>
          </div>
        </div>
      )}

      {/* ── Legend ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
        <span className="font-medium text-gray-500 dark:text-gray-400">Status:</span>
        {(
          [
            { status: "PENDING", color: "bg-gray-600", label: "Pending" },
            { status: "GENERATING", color: "bg-blue-500", label: "Generating" },
            { status: "COMPLETE", color: "bg-green-600", label: "Complete" },
            { status: "ERROR", color: "bg-red-600", label: "Error" },
            {
              status: "REGENERATING",
              color: "bg-yellow-500",
              label: "Regenerating",
            },
          ] as const
        ).map((item) => (
          <span key={item.status} className="flex items-center gap-1.5">
            <span className={`w-3 h-3 rounded ${item.color}`} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
