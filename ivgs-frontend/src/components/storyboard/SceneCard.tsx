"use client";

import React, { useState, useCallback } from "react";
import SceneThumbnail from "@/components/SceneThumbnail";
import type {
  Scene,
  SceneStatus,
  MediaType,
} from "@/types/storyboard";
import type { DraggableProvidedDragHandleProps } from "react-beautiful-dnd";

/**
 * §8.1.3 Storyboard Tab — Scene Card
 *
 * Individual scene card in the storyboard grid. Displays:
 * - Scene index number
 * - Thumbnail image (or placeholder if not yet generated)
 * - Narration text (first 120 chars with ellipsis)
 * - Visual description snippet
 * - Media type badge (IMAGE / VIDEO / ANIMATION / TALKING_HEAD / STOCK)
 * - Duration in seconds
 * - Status badge with color coding
 * - Drag handle for reordering
 * - Selection checkbox for bulk operations
 * - Action buttons: Edit, Regenerate, Delete
 *
 * Props:
 * @param scene - Scene data object
 * @param index - Position index in the filtered list
 * @param canEdit - Whether user has edit permissions
 * @param isSelected - Whether this card is selected for bulk ops
 * @param isDragging - Whether this card is currently being dragged
 * @param dragHandleProps - Props from react-beautiful-dnd for drag handle
 * @param onToggleSelect - Callback to toggle selection
 * @param onEdit - Callback to open edit modal
 * @param onRegenerate - Callback to regenerate this scene
 * @param onDelete - Callback to delete this scene
 */

interface SceneCardProps {
  /** Scene data */
  scene: Scene;
  /** Position index in the current list */
  index: number;
  /** Whether the user can edit */
  canEdit: boolean;
  /** Whether this card is currently selected */
  isSelected: boolean;
  /** Whether this card is being dragged */
  isDragging: boolean;
  /** Drag handle props from react-beautiful-dnd */
  dragHandleProps: DraggableProvidedDragHandleProps | null | undefined;
  /** Toggle selection callback */
  onToggleSelect: () => void;
  /** Open edit modal callback */
  onEdit: () => void;
  /** Regenerate scene callback */
  onRegenerate: () => void;
  /** Delete scene callback */
  onDelete: () => void;
}

/** Color mapping for scene status badges */
const STATUS_COLORS: Record<SceneStatus, string> = {
  PENDING: "bg-gray-500 text-gray-100",
  GENERATING: "bg-blue-500 text-blue-100",
  COMPLETE: "bg-green-500 text-green-100",
  ERROR: "bg-red-500 text-red-100",
  REGENERATING: "bg-yellow-500 text-yellow-100",
};

/** Human-readable labels for scene statuses */
const STATUS_LABELS: Record<SceneStatus, string> = {
  PENDING: "Pending",
  GENERATING: "Generating",
  COMPLETE: "Complete",
  ERROR: "Error",
  REGENERATING: "Regenerating",
};

/** Icon mapping for media types */
const MEDIA_TYPE_ICONS: Record<MediaType, string> = {
  IMAGE: "🖼️",
  VIDEO: "🎬",
  ANIMATION: "✨",
  TALKING_HEAD: "🗣️",
  STOCK: "📷",
};

/** Human-readable labels for media types */
const MEDIA_TYPE_LABELS: Record<MediaType, string> = {
  IMAGE: "Image",
  VIDEO: "Video",
  ANIMATION: "Animation",
  TALKING_HEAD: "Talking Head",
  STOCK: "Stock",
};

/**
 * Truncate text to a maximum length with ellipsis.
 * @param text - Input text
 * @param maxLength - Maximum character count
 * @returns Truncated text with ellipsis if needed
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trimEnd() + "…";
}

/**
 * Format duration in seconds to a human-readable string (e.g., "1:30").
 * @param seconds - Duration in seconds
 * @returns Formatted duration string
 */
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export default function SceneCard({
  scene,
  index,
  canEdit,
  isSelected,
  isDragging,
  dragHandleProps,
  onToggleSelect,
  onEdit,
  onRegenerate,
  onDelete,
}: SceneCardProps): React.ReactElement {
  // ── Local Loading States ──────────────────────────────────────────
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  /** Handle regenerate with loading state */
  const handleRegenerate = useCallback(
    async (e: React.MouseEvent): Promise<void> => {
      e.stopPropagation();
      if (isRegenerating) return;
      setIsRegenerating(true);
      try {
        await (onRegenerate as unknown as () => Promise<void>)();
      } finally {
        setIsRegenerating(false);
      }
    },
    [onRegenerate, isRegenerating]
  );

  /** Handle delete with loading state */
  const handleDelete = useCallback(
    async (e: React.MouseEvent): Promise<void> => {
      e.stopPropagation();
      if (isDeleting) return;
      setIsDeleting(true);
      try {
        await (onDelete as unknown as () => Promise<void>)();
      } finally {
        setIsDeleting(false);
      }
    },
    [onDelete, isDeleting]
  );

  /** Handle card click for edit */
  const handleCardClick = useCallback((): void => {
    if (canEdit) {
      onEdit();
    }
  }, [canEdit, onEdit]);


  return (
    <div
      className={`relative group bg-gray-100 dark:bg-gray-800 rounded-xl border transition-all duration-200 overflow-hidden ${
        isSelected
          ? "border-blue-500 ring-2 ring-blue-500/30"
          : isDragging
          ? "border-blue-400 shadow-2xl"
          : "border-gray-300 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
      } ${canEdit ? "cursor-pointer" : "cursor-default"}`}
      onClick={handleCardClick}
      role="article"
      aria-label={`Scene ${scene.scene_index + 1}: ${truncateText(
        scene.narration_text,
        50
      )}`}
    >
      {/* ── Selection Checkbox & Drag Handle ────────────────────── */}
      <div className="absolute top-2 left-2 z-10 flex items-center gap-2">
        {canEdit && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={(e) => {
              e.stopPropagation();
              onToggleSelect();
            }}
            className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-blue-500 dark:text-blue-400 focus:ring-blue-500 focus:ring-offset-gray-800"
            aria-label={`Select scene ${scene.scene_index + 1}`}
          />
        )}
        {canEdit && dragHandleProps && (
          <div
            {...dragHandleProps}
            className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-grab active:cursor-grabbing"
            aria-label={`Drag to reorder scene ${scene.scene_index + 1}`}
            onClick={(e) => e.stopPropagation()}
          >
            <svg
              className="w-4 h-4 text-gray-500 dark:text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 8h16M4 16h16"
              />
            </svg>
          </div>
        )}
      </div>

      {/* ── Scene Index Badge ────────────────────────────────────── */}
      <div className="absolute top-2 right-2 z-10">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-white dark:bg-gray-900/80 text-xs font-bold text-gray-900 dark:text-white">
          {scene.scene_index + 1}
        </span>
      </div>

      {/* ── Thumbnail ───────────────────────────────────────────── */}
      <div className="aspect-video bg-white dark:bg-gray-900 relative">
        {/* WP-40 addendum: `scene.thumbnail_url` does not exist on this API.
            The scene's generated image asset does, linked by `scene_id`. */}
        <SceneThumbnail
          projectId={scene.project_id}
          sceneId={scene.id}
          sceneIndex={scene.scene_index}
          fallback={
            <span className="text-4xl">
              {MEDIA_TYPE_ICONS[scene.media_type] ?? "🎞️"}
            </span>
          }
        />

        {/* Duration overlay */}
        {scene.duration_seconds != null && scene.duration_seconds > 0 && (
          <div className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 rounded text-xs font-mono text-gray-900 dark:text-white">
            {formatDuration(scene.duration_seconds)}
          </div>
        )}

        {/* Status overlay for non-complete scenes */}
        {scene.status !== "COMPLETE" && (
          <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
            {scene.status === "GENERATING" || scene.status === "REGENERATING" ? (
              <div className="flex items-center gap-2">
                <svg
                  className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {STATUS_LABELS[scene.status]}
                </span>
              </div>
            ) : scene.status === "ERROR" ? (
              <span className="text-sm font-medium text-red-600 dark:text-red-400">
                ⚠ Generation Failed
              </span>
            ) : null}
          </div>
        )}
      </div>

      {/* ── Card Body ───────────────────────────────────────────── */}
      <div className="p-4">
        {/* Media Type & Status Badges */}
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-200 dark:bg-gray-700 text-xs text-gray-700 dark:text-gray-300">
            {MEDIA_TYPE_ICONS[scene.media_type]}{" "}
            {MEDIA_TYPE_LABELS[scene.media_type]}
          </span>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
              STATUS_COLORS[scene.status]
            }`}
          >
            {STATUS_LABELS[scene.status]}
          </span>
        </div>

        {/* Narration Text */}
        <p className="text-sm text-gray-900 dark:text-white font-medium mb-1 line-clamp-2">
          {truncateText(scene.narration_text, 120)}
        </p>

        {/* Visual Description */}
        {scene.visual_description && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 line-clamp-2">
            {truncateText(scene.visual_description, 100)}
          </p>
        )}

        {/* Camera Angle & Transition (if set) */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {scene.camera_angle && (
            <span className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700/50 rounded text-[10px] text-gray-500 dark:text-gray-400">
              📐 {scene.camera_angle}
            </span>
          )}
          {scene.transition_type && (
            <span className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700/50 rounded text-[10px] text-gray-500 dark:text-gray-400">
              🔀 {scene.transition_type}
            </span>
          )}
          {scene.effects && scene.effects.length > 0 && (
            <span className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700/50 rounded text-[10px] text-gray-500 dark:text-gray-400">
              ✨ {scene.effects.length} effect
              {scene.effects.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* ── Action Buttons ──────────────────────────────────── */}
        {canEdit && (
          <div className="flex items-center gap-2 pt-2 border-t border-gray-300 dark:border-gray-700">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit();
              }}
              className="flex-1 px-2 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/20 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
              aria-label={`Edit scene ${scene.scene_index + 1}`}
            >
              Edit
            </button>
            <button
              onClick={handleRegenerate}
              disabled={
                isRegenerating ||
                scene.status === "GENERATING" ||
                scene.status === "REGENERATING"
              }
              className="flex-1 px-2 py-1.5 text-xs font-medium text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/20 rounded hover:bg-yellow-100 dark:hover:bg-yellow-900/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label={`Regenerate scene ${scene.scene_index + 1}`}
            >
              {isRegenerating ? "…" : "Regen"}
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="px-2 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/20 rounded hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label={`Delete scene ${scene.scene_index + 1}`}
            >
              {isDeleting ? "…" : "✕"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
