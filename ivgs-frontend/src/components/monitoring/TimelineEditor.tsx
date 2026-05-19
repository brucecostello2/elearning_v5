"use client";

import React, { useRef, useCallback, useMemo, useEffect, useState } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type {
  CompositionManifest,
  TimelineSegment,
  TimelineLayer,
  RenderSegmentStatus,
} from "@/types/monitoring";

/**
 * §8.2.5 Composition Timeline Editor
 *
 * Horizontal timeline visualization for composition manifests.
 * Uses HTML div-based rendering (not Canvas) for accessibility.
 *
 * Features:
 * - Layer tracks per Table 6-3:
 *   Background, Talking Head, Lower Third, Captions, Audio
 * - Segments color-coded by status: pending/rendering/complete/failed
 * - Per-segment progress bars for active renders
 * - Failed segment retry button (admin only)
 * - Zoom (0.25x–4x) and pan via horizontal scroll
 * - Scene boundary markers
 * - Total duration display
 *
 * Props:
 * - manifest: composition manifest with scene/layer data
 * - segments: render segments with status and progress
 * - layers: layer definitions with colors
 * - zoomLevel: current zoom (1 = 100%)
 * - panOffset: horizontal scroll position
 */

interface TimelineEditorProps {
  /** Composition manifest data */
  manifest: CompositionManifest;
  /** Render segments with status data */
  segments: TimelineSegment[];
  /** Layer definitions with IDs, labels, and colors */
  layers: { id: TimelineLayer; label: string; color: string }[];
  /** Color mapping for segment statuses */
  segmentStatusColors: Record<RenderSegmentStatus, string>;
  /** Current zoom level (1.0 = 100%) */
  zoomLevel: number;
  /** Pan offset in pixels */
  panOffset: number;
  /** Callback when pan position changes */
  onPanChange: (offset: number) => void;
  /** Whether the user is admin (for retry button) */
  isAdmin: boolean;
  /** Segment ID currently being retried */
  retrySegmentId: string | null;
  /** Callback to retry a failed segment */
  onRetrySegment: (segmentId: string) => void;
}

/** Track height in pixels */
const TRACK_HEIGHT = 40;
/** Track label width */
const LABEL_WIDTH = 100;
/** Pixels per second at zoom 1.0 */
const PIXELS_PER_SECOND = 10;
/** Gap between tracks */
const TRACK_GAP = 2;

export default function TimelineEditor({
  manifest,
  segments,
  layers,
  segmentStatusColors,
  zoomLevel,
  panOffset,
  onPanChange,
  isAdmin,
  retrySegmentId,
  onRetrySegment,
}: TimelineEditorProps): React.ReactElement {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null);

  /**
   * Calculate the total duration of the composition in seconds.
   */
  const totalDuration = useMemo((): number => {
    if (!manifest.scenes || manifest.scenes.length === 0) return 0;
    return manifest.scenes.reduce(
      (sum, scene) => sum + (scene.duration_seconds || 0),
      0
    );
  }, [manifest.scenes]);

  /**
   * Total timeline width based on duration and zoom.
   */
  const timelineWidth = useMemo(
    () => totalDuration * PIXELS_PER_SECOND * zoomLevel,
    [totalDuration, zoomLevel]
  );

  /**
   * Build segment rectangles for each layer.
   * Maps segments to their position and width on the timeline.
   */
  const segmentRects = useMemo(() => {
    if (!segments || segments.length === 0) return [];

    return segments.map((seg) => {
      const startPx = (seg.start_seconds || 0) * PIXELS_PER_SECOND * zoomLevel;
      const widthPx =
        (seg.duration_seconds || 1) * PIXELS_PER_SECOND * zoomLevel;
      const layerIndex = layers.findIndex((l) => l.id === seg.layer);
      const topPx = layerIndex >= 0 ? layerIndex * (TRACK_HEIGHT + TRACK_GAP) : 0;

      return {
        ...seg,
        x: startPx,
        width: Math.max(widthPx, 2),
        y: topPx,
        layerColor:
          layers.find((l) => l.id === seg.layer)?.color || "#6B7280",
      };
    });
  }, [segments, layers, zoomLevel]);

  /**
   * Build scene boundary markers.
   */
  const sceneBoundaries = useMemo(() => {
    if (!manifest.scenes) return [];
    let accumulatedTime = 0;
    return manifest.scenes.map((scene, index) => {
      const x = accumulatedTime * PIXELS_PER_SECOND * zoomLevel;
      accumulatedTime += scene.duration_seconds || 0;
      return {
        x,
        sceneIndex: index + 1,
        label: `S${index + 1}`,
      };
    });
  }, [manifest.scenes, zoomLevel]);

  /**
   * Handle scroll for panning.
   */
  const handleScroll = useCallback(() => {
    if (scrollContainerRef.current) {
      onPanChange(scrollContainerRef.current.scrollLeft);
    }
  }, [onPanChange]);

  /** Sync pan offset from parent */
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollLeft = panOffset;
    }
  }, [panOffset]);

  /**
   * Format seconds to MM:SS display.
   */
  const formatTime = useCallback((seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }, []);

  // ── Render ──────────────────────────────────────────────────────────

  const totalHeight = layers.length * (TRACK_HEIGHT + TRACK_GAP);

  return (
    <div className="flex">
      {/* ── Track Labels (fixed left column) ─────────────────────── */}
      <div className="flex-shrink-0 bg-gray-50 border-r border-gray-200" style={{ width: LABEL_WIDTH }}>
        {/* Time ruler label */}
        <div
          className="flex items-center justify-center text-[10px] text-gray-400 border-b border-gray-200"
          style={{ height: 24 }}
        >
          Time
        </div>
        {/* Layer labels */}
        {layers.map((layer) => (
          <div
            key={layer.id}
            className="flex items-center gap-1.5 px-2 border-b border-gray-100"
            style={{ height: TRACK_HEIGHT + TRACK_GAP }}
          >
            <div
              className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{ backgroundColor: layer.color }}
            />
            <span className="text-[10px] font-medium text-gray-700 truncate">
              {layer.label}
            </span>
          </div>
        ))}
      </div>

      {/* ── Scrollable Timeline Area ─────────────────────────────── */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-x-auto"
        onScroll={handleScroll}
      >
        <div style={{ width: Math.max(timelineWidth, 600), position: "relative" }}>
          {/* ── Time Ruler ────────────────────────────────────────── */}
          <div
            className="bg-gray-100 border-b border-gray-200 relative"
            style={{ height: 24 }}
          >
            {/* Time markers every 10 seconds (or adjusted by zoom) */}
            {Array.from(
              { length: Math.ceil(totalDuration / 10) + 1 },
              (_, i) => i * 10
            ).map((seconds) => {
              const x = seconds * PIXELS_PER_SECOND * zoomLevel;
              if (x > timelineWidth) return null;
              return (
                <div
                  key={seconds}
                  className="absolute top-0 text-[9px] text-gray-500 font-mono"
                  style={{ left: x, transform: "translateX(-50%)" }}
                >
                  <div className="h-3 border-l border-gray-300" />
                  <span className="mt-0.5 block">{formatTime(seconds)}</span>
                </div>
              );
            })}

            {/* Scene boundary markers */}
            {sceneBoundaries.map((boundary) => (
              <div
                key={boundary.sceneIndex}
                className="absolute top-0 h-full"
                style={{ left: boundary.x }}
              >
                <div className="h-full border-l-2 border-dashed border-blue-300" />
                <span
                  className="absolute -top-0.5 text-[8px] text-blue-600 font-bold bg-blue-50 px-1 rounded"
                  style={{ left: 2 }}
                >
                  {boundary.label}
                </span>
              </div>
            ))}
          </div>

          {/* ── Segment Tracks ────────────────────────────────────── */}
          <div className="relative" style={{ height: totalHeight }}>
            {/* Track background stripes */}
            {layers.map((layer, index) => (
              <div
                key={`bg-${layer.id}`}
                className={`absolute w-full border-b border-gray-100 ${
                  index % 2 === 0 ? "bg-white" : "bg-gray-50/50"
                }`}
                style={{
                  top: index * (TRACK_HEIGHT + TRACK_GAP),
                  height: TRACK_HEIGHT + TRACK_GAP,
                }}
              />
            ))}

            {/* Render segments */}
            {segmentRects.map((rect) => (
              <div
                key={rect.id}
                className="absolute rounded-sm cursor-pointer transition-opacity"
                style={{
                  left: rect.x,
                  top: rect.y + 2,
                  width: rect.width,
                  height: TRACK_HEIGHT - 4,
                  backgroundColor:
                    segmentStatusColors[rect.status] || "#D1D5DB",
                  opacity: hoveredSegment === rect.id ? 1 : 0.85,
                  border:
                    hoveredSegment === rect.id
                      ? "2px solid #1F2937"
                      : "1px solid rgba(0,0,0,0.1)",
                }}
                onMouseEnter={() => setHoveredSegment(rect.id)}
                onMouseLeave={() => setHoveredSegment(null)}
                title={`${rect.layer} — ${rect.status}${
                  rect.progress !== undefined
                    ? ` (${rect.progress}%)`
                    : ""
                }\nDuration: ${formatTime(rect.duration_seconds || 0)}`}
              >
                {/* Segment label (if wide enough) */}
                {rect.width > 30 && (
                  <span
                    className="absolute inset-0 flex items-center justify-center
                      text-[8px] font-medium text-white truncate px-1"
                    style={{ textShadow: "0 1px 2px rgba(0,0,0,0.3)" }}
                  >
                    {rect.status === "RENDERING" && rect.progress !== undefined
                      ? `${rect.progress}%`
                      : rect.status.charAt(0)}
                  </span>
                )}

                {/* Progress bar overlay for rendering segments */}
                {rect.status === "RENDERING" && rect.progress !== undefined && (
                  <div
                    className="absolute bottom-0 left-0 h-1 bg-white/40 rounded-b-sm"
                    style={{ width: `${rect.progress}%` }}
                  />
                )}

                {/* Retry button for failed segments (admin only) */}
                {rect.status === "FAILED" &&
                  isAdmin &&
                  hoveredSegment === rect.id && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRetrySegment(rect.id);
                      }}
                      disabled={retrySegmentId === rect.id}
                      className="absolute -top-6 left-1/2 -translate-x-1/2
                        px-2 py-0.5 text-[9px] font-medium text-white
                        bg-blue-600 rounded shadow-sm hover:bg-blue-700
                        disabled:opacity-50 whitespace-nowrap"
                    >
                      {retrySegmentId === rect.id ? "…" : "Retry"}
                    </button>
                  )}
              </div>
            ))}

            {/* Scene boundary vertical lines spanning all tracks */}
            {sceneBoundaries.map((boundary) => (
              <div
                key={`line-${boundary.sceneIndex}`}
                className="absolute top-0 h-full border-l border-dashed border-blue-200 pointer-events-none"
                style={{ left: boundary.x }}
              />
            ))}
          </div>

          {/* ── Duration Footer ────────────────────────────────────── */}
          <div className="bg-gray-50 border-t border-gray-200 px-3 py-1 flex items-center justify-between">
            <span className="text-[10px] text-gray-500">
              Total: {formatTime(totalDuration)} •{" "}
              {manifest.scenes?.length || 0} scenes •{" "}
              {segments.length} segments
            </span>
            <span className="text-[10px] text-gray-400">
              Zoom: {(zoomLevel * 100).toFixed(0)}% •{" "}
              {PIXELS_PER_SECOND * zoomLevel}px/s
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
