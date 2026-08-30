"use client";

import React, { useState, useCallback, useMemo } from "react";
import useSWR from "swr";
import {
  DragDropContext,
  Droppable,
  Draggable,
  DropResult,
  DragStart,
  DragUpdate,
} from "react-beautiful-dnd";
import SceneCard from "@/components/storyboard/SceneCard";
import { apiClient } from "@/lib/api-client";
import type { Scene } from "@/types/storyboard";
import type { ModelSelection } from "@/types/models";
import type { SceneCompleteness } from "@/hooks/useProjectProgress";

/**
 * §8.1.3 Storyboard Editor — Drag-Drop Scene Grid
 *
 * Core editor component that wraps scene cards in a react-beautiful-dnd
 * context. Scenes are displayed in a responsive CSS grid and can be
 * reordered by dragging. The reorder callback triggers an API call to
 * update scene_index values on the backend.
 *
 * Features:
 * - Drag-and-drop reordering with visual feedback
 * - Optimistic local reorder before API confirmation
 * - Selection checkboxes for bulk operations
 * - Responsive grid layout (1 col mobile, 2 col tablet, 3 col desktop)
 * - Accessible drag handles with aria labels
 *
 * Props:
 * @param projectId - Current project ID
 * @param scenes - Array of scenes to render (already filtered)
 * @param canEdit - Whether the current user has edit permissions
 * @param selectedSceneIds - Set of currently selected scene IDs
 * @param onToggleSelect - Callback to toggle scene selection
 * @param onEditScene - Callback to open scene edit modal
 * @param onRegenerateScene - Callback to regenerate a scene
 * @param onDeleteScene - Callback to delete a scene
 * @param onReorder - Callback to handle reorder (sourceIndex, destIndex)
 */

interface StoryboardEditorProps {
  /** Current project ID */
  projectId: string;
  /** Array of scenes to render (already filtered by parent) */
  scenes: Scene[];
  /** Whether the current user can edit scenes */
  canEdit: boolean;
  /** Set of selected scene IDs for bulk operations */
  selectedSceneIds: Set<string>;
  /** Toggle selection of a single scene */
  onToggleSelect: (sceneId: string) => void;
  /** Open edit modal for a scene */
  onEditScene: (scene: Scene) => void;
  /** Trigger regeneration for a scene */
  onRegenerateScene: (sceneId: string) => Promise<void>;
  /** Delete a scene */
  onDeleteScene: (sceneId: string) => Promise<void>;
  /** Handle drag-drop reorder */
  onReorder: (sourceIndex: number, destinationIndex: number) => Promise<void>;
  /**
   * WP-IVGS-12i RC-R2. The gate's per-scene findings, keyed by `scene_index`.
   *
   * ⚠ BY `scene_index` AND NOT BY SCENE ID, because that is the key the gate
   * computes them under: `assess_storyboard` reads rows and reports indices,
   * and a scene id never enters the completeness check. Passed as a map rather
   * than a list so this component does not filter nineteen findings nineteen
   * times.
   */
  findingsByScene?: Map<number, SceneCompleteness[]>;
}

export default function StoryboardEditor({
  projectId,
  scenes,
  canEdit,
  selectedSceneIds,
  onToggleSelect,
  onEditScene,
  onRegenerateScene,
  onDeleteScene,
  onReorder,
  findingsByScene,
}: StoryboardEditorProps): React.ReactElement {
  /* WP-66 Task 4 — which scenes override the project's model binding.
     Rendered on the grid so the exceptions are visible without opening every
     card. Read-only and failure-tolerant: if this request fails the cards
     simply carry no badge, because a missing badge is a smaller wrong than a
     storyboard that will not render. */
  const { data: selections } = useSWR<ModelSelection[]>(
    projectId ? `/api/v1/projects/${projectId}/model-selections` : null,
    async (u: string) => (await apiClient.get<ModelSelection[]>(u)).data,
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const sceneOverrides = useMemo(() => {
    const map = new Map<string, string>();
    for (const sel of selections ?? []) {
      if (!sel.scene_id) continue;
      map.set(sel.scene_id, sel.model_display_name ?? sel.model_name ?? "custom");
    }
    return map;
  }, [selections]);

  // ── Drag State ──────────────────────────────────────────────────────
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragSourceId, setDragSourceId] = useState<string | null>(null);
  const [isReordering, setIsReordering] = useState<boolean>(false);

  /**
   * Handle drag start event.
   * Sets visual state for the dragged item.
   */
  const handleDragStart = useCallback((start: DragStart): void => {
    setIsDragging(true);
    setDragSourceId(start.draggableId);
  }, []);

  /**
   * Handle drag end event.
   * If the item was dropped in a valid location, trigger the reorder
   * callback. Otherwise, reset visual state.
   */
  const handleDragEnd = useCallback(
    async (result: DropResult): Promise<void> => {
      setIsDragging(false);
      setDragSourceId(null);

      // Dropped outside the list — no reorder
      if (!result.destination) return;

      // Dropped in the same position — no reorder
      if (result.source.index === result.destination.index) return;

      // Trigger reorder via parent callback
      setIsReordering(true);
      try {
        await onReorder(result.source.index, result.destination.index);
      } catch (err) {
        console.error("[StoryboardEditor] Reorder failed:", err);
      } finally {
        setIsReordering(false);
      }
    },
    [onReorder]
  );

  /**
   * Regenerate scene handler with loading guard.
   */
  const handleRegenerate = useCallback(
    async (sceneId: string): Promise<void> => {
      try {
        await onRegenerateScene(sceneId);
      } catch (err) {
        console.error("[StoryboardEditor] Regenerate failed:", err);
      }
    },
    [onRegenerateScene]
  );

  /**
   * Delete scene handler with loading guard.
   */
  const handleDelete = useCallback(
    async (sceneId: string): Promise<void> => {
      try {
        await onDeleteScene(sceneId);
      } catch (err) {
        console.error("[StoryboardEditor] Delete failed:", err);
      }
    },
    [onDeleteScene]
  );

  // ── Empty Filtered State ─────────────────────────────────────────────
  if (scenes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <svg
          className="w-12 h-12 text-gray-500 dark:text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          No scenes match the current filters.
        </p>
      </div>
    );
  }

  return (
    <DragDropContext
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <Droppable droppableId="storyboard-scenes" direction="horizontal">
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 transition-colors duration-200 ${
              snapshot.isDraggingOver
                ? "bg-blue-100 dark:bg-blue-900/10 rounded-xl p-2"
                : ""
            } ${isReordering ? "opacity-70 pointer-events-none" : ""}`}
          >
            {scenes.map((scene: Scene, index: number) => (
              <Draggable
                key={scene.id}
                draggableId={scene.id}
                index={index}
                isDragDisabled={!canEdit}
              >
                {(dragProvided, dragSnapshot) => (
                  <div
                    ref={dragProvided.innerRef}
                    {...dragProvided.draggableProps}
                    className={`transition-transform duration-150 ${
                      dragSnapshot.isDragging
                        ? "z-50 rotate-2 scale-105 shadow-2xl"
                        : ""
                    }`}
                  >
                    <SceneCard
                      scene={scene}
                      index={index}
                      canEdit={canEdit}
                      isSelected={selectedSceneIds.has(scene.id)}
                      isDragging={dragSnapshot.isDragging}
                      dragHandleProps={dragProvided.dragHandleProps}
                      onToggleSelect={() => onToggleSelect(scene.id)}
                      onEdit={() => onEditScene(scene)}
                      onRegenerate={() => handleRegenerate(scene.id)}
                      onDelete={() => handleDelete(scene.id)}
                      /* WP-66 Task 4. One request for the whole storyboard,
                         not one per card: `GET /model-selections` already
                         returns every row, scene-scoped included. */
                      modelOverrideName={sceneOverrides.get(scene.id) ?? null}
                      findings={findingsByScene?.get(scene.scene_index)}
                    />
                  </div>
                )}
              </Draggable>
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>

      {/* Reorder loading overlay */}
      {isReordering && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/20">
          <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-6 py-3 text-sm text-gray-900 dark:text-white shadow-xl">
            Updating scene order…
          </div>
        </div>
      )}
    </DragDropContext>
  );
}
