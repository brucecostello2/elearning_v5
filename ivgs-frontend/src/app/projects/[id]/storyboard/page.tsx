"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useStoryboard } from "@/hooks/useStoryboard";
import { useProjects } from "@/hooks/useProjects";
import StoryboardEditor from "@/components/storyboard/StoryboardEditor";
import SceneEditModal from "@/components/storyboard/SceneEditModal";
import SceneTimeline from "@/components/storyboard/SceneTimeline";
import GateReviewPanel from "@/components/project/GateReviewPanel";
import { useProjectProgress } from "@/hooks/useProjectProgress";
import LoadingSpinner from "@/components/LoadingSpinner";
import { apiError } from "@/lib/api-error";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { Scene, SceneStatus, StoryboardViewMode } from "@/types/storyboard";
import type { MediaType } from "@/lib/scenes";
import {
  MEDIA_TYPES as MEDIA_TYPE_VALUES,
  mediaTypeLabel,
  normalizeMediaType,
} from "@/lib/scenes";

/**
 * §8.1.3 Storyboard Tab — Project Detail Page
 *
 * Full storyboard editor with:
 * - Drag-drop scene reordering (react-beautiful-dnd)
 * - Scene cards with thumbnails, narration snippets, media type badges
 * - Scene detail editing modal (all properties)
 * - Scene regeneration triggers
 * - Bulk operations (select multiple, delete, regenerate)
 * - Grid / Timeline view toggle
 * - Filtering by status, media type, and search
 *
 * RBAC per Table 8-3:
 *   - admin: full edit on all projects
 *   - operator: full edit on own projects
 *   - viewer: read-only (no edit, no reorder, no regenerate)
 */

/** Possible scene statuses for filter dropdown */
const SCENE_STATUSES: SceneStatus[] = [
  "PENDING",
  "GENERATING",
  "COMPLETE",
  "ERROR",
  "REGENERATING",
];

/*
 * WP-43 Task 7. This filter offered the same five UPPERCASE names the edit
 * modal did, and compared them with `s.media_type === mediaTypeFilter`
 * against a wire value of "image". Every option therefore emptied the grid,
 * and two of the five named pipelines the API cannot select. The options are
 * now the three values the API uses, so the comparison can match.
 */
const MEDIA_TYPES: readonly MediaType[] = MEDIA_TYPE_VALUES;

export default function StoryboardPage(): React.ReactElement {
  // ── Route Params ──────────────────────────────────────────────────────
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  // ── Auth & Data ───────────────────────────────────────────────────────
  const { user } = useAuth();
  const { project, isLoading: projectLoading } = useProjects(projectId);
  const {
    scenes,
    isLoading: scenesLoading,
    error,
    mutate,
    adaptSceneDescription,
    reorderScenes,
    deleteScene,
    deleteScenes,
    regenerateScene,
    regenerateScenes,
    updateScene,
  } = useStoryboard(projectId);

  // ── View Mode ─────────────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState<StoryboardViewMode>("grid");

  // ── Filter State ──────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<SceneStatus | "ALL">("ALL");
  const [mediaTypeFilter, setMediaTypeFilter] = useState<MediaType | "ALL">(
    "ALL"
  );

  // ── Selection State (for bulk operations) ─────────────────────────────
  const [selectedSceneIds, setSelectedSceneIds] = useState<Set<string>>(
    new Set()
  );

  // ── Modal State ───────────────────────────────────────────────────────
  const [editingScene, setEditingScene] = useState<Scene | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);

  // ── Bulk Action Loading ───────────────────────────────────────────────
  const [isBulkActionLoading, setIsBulkActionLoading] =
    useState<boolean>(false);

  /* ── The server's refusals, shown ────────────────────────────────────
     WP-63 Task 7. Every regeneration path here awaited a promise and caught
     nothing, so a 409 from the gate or the in-flight guard arrived, was
     rolled back by SWR, and vanished. Measured: the operator's Regen press at
     15:15:59Z on 2026-08-26 answered 409 Conflict with a message naming the
     stale approval and what to do about it, and the screen did not change. */
  const [actionError, setActionError] = useState<
    { message: string; code?: string } | null
  >(null);

  /**
   * Determine if the current user can edit this project.
   * Admin can edit all projects. Operator can edit own projects only.
   * Viewer cannot edit. Per Table 8-3.
   */
  const canEdit = useMemo<boolean>(() => {
    if (!user || !project) return false;
    if (user.role === "admin") return true;
    if (user.role === "operator" && project.created_by === user.id) return true;
    return false;
  }, [user, project]);

  /**
   * WP-40 Task 3a — who may approve.
   *
   * WP-62 Task 2(d). THE "WHEN" HALF IS GONE FROM HERE, and that is the
   * point. It was a hand-maintained list of eight `ProjectState` values kept
   * in step with `project_service.py` by hand — a second copy of the gate's
   * rule, in a browser, over a column this fleet has been demonstrably wrong
   * about (WP-62 Task 3: `projects.state` was frozen at DRAFT on projects that
   * had rendered). Whether the gate is open is now ONE server computation, the
   * same one the stepper reads, anchored to the storyboard artefact rather
   * than to a position.
   *
   * What is left here is RBAC, which is genuinely a client-side concern: the
   * route is behind `require_operator_or_admin`, and a viewer must not be
   * offered a control they would be refused.
   */
  const canDecideGate = useMemo<boolean>(
    () => user?.role === "admin" || user?.role === "operator",
    [user],
  );

  /* The same computation the top stepper reads. One answer to "is this gate
     open", on every surface that asks. */
  const { progress, mutate: mutateProgress } = useProjectProgress(projectId);
  const storyboardGate = progress?.gates?.storyboard;
  const gateIsOpen =
    (progress?.steps ?? []).some(
      (st) => st.gate === "storyboard" && st.status === "gated",
    ) && storyboardGate !== undefined;

  /**
   * Filter scenes based on current filter state.
   * Scenes are filtered by status, media type, and free-text search
   * across narration_text and visual_description.
   */
  const filteredScenes = useMemo<Scene[]>(() => {
    if (!scenes) return [];

    let result = [...scenes];

    // Status filter
    if (statusFilter !== "ALL") {
      result = result.filter(
        (s: Scene) => s.status === statusFilter
      );
    }

    // Media type filter
    if (mediaTypeFilter !== "ALL") {
      /* Compare NORMALISED values so a row written under an older
         vocabulary still matches its own filter entry. */
      result = result.filter(
        (s: Scene) => normalizeMediaType(s.media_type) === mediaTypeFilter
      );
    }

    // Free-text search across narration and visual description
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (s: Scene) =>
          s.narration_text.toLowerCase().includes(query) ||
          (s.visual_description?.toLowerCase().includes(query) ?? false) ||
          `scene ${s.scene_index + 1}`.includes(query)
      );
    }

    return result;
  }, [scenes, statusFilter, mediaTypeFilter, searchQuery]);

  /**
   * Total duration of all scenes in seconds.
   * Used for the timeline header summary.
   */
  const totalDuration = useMemo<number>(() => {
    if (!scenes) return 0;
    return scenes.reduce(
      (sum: number, s: Scene) => sum + (s.duration_seconds ?? 0),
      0
    );
  }, [scenes]);

  /**
   * Count of scenes by status for the filter bar badges.
   */
  const statusCounts = useMemo<Record<SceneStatus | "ALL", number>>(() => {
    const counts: Record<string, number> = { ALL: scenes?.length ?? 0 };
    SCENE_STATUSES.forEach((status) => {
      counts[status] =
        scenes?.filter((s: Scene) => s.status === status).length ?? 0;
    });
    return counts as Record<SceneStatus | "ALL", number>;
  }, [scenes]);

  /** Toggle selection of a single scene */
  const handleToggleSelect = useCallback((sceneId: string): void => {
    setSelectedSceneIds((prev) => {
      const next = new Set(prev);
      if (next.has(sceneId)) {
        next.delete(sceneId);
      } else {
        next.add(sceneId);
      }
      return next;
    });
  }, []);

  /** Select all visible (filtered) scenes */
  const handleSelectAll = useCallback((): void => {
    const allIds = new Set(filteredScenes.map((s: Scene) => s.id));
    setSelectedSceneIds(allIds);
  }, [filteredScenes]);

  /** Clear all selections */
  const handleClearSelection = useCallback((): void => {
    setSelectedSceneIds(new Set());
  }, []);

  /** Open scene edit modal */
  const handleEditScene = useCallback((scene: Scene): void => {
    setEditingScene(scene);
    setIsEditModalOpen(true);
  }, []);

  /** Close scene edit modal */
  const handleCloseEditModal = useCallback((): void => {
    setIsEditModalOpen(false);
    setEditingScene(null);
  }, []);

  /**
   * Save scene edits from the modal.
   * Calls updateScene from useStoryboard hook which PATCHes via API.
   */
  const handleSaveScene = useCallback(
    async (sceneId: string, updates: Partial<Scene>): Promise<void> => {
      await updateScene(sceneId, updates);
      setIsEditModalOpen(false);
      setEditingScene(null);
    },
    [updateScene]
  );

  /**
   * Handle drag-drop reorder completion.
   * Updates scene_index values via API call.
   */
  const handleReorder = useCallback(
    async (sourceIndex: number, destinationIndex: number): Promise<void> => {
      if (!canEdit) return;
      await reorderScenes(sourceIndex, destinationIndex);
    },
    [canEdit, reorderScenes]
  );

  /**
   * Regenerate a single scene.
   * Triggers POST /api/v1/projects/{id}/scenes/{sid}/regenerate
   */
  const handleRegenerateScene = useCallback(
    async (sceneId: string): Promise<void> => {
      if (!canEdit) {
        /* Also a silent no-op before this package: an operator who does not own
           the project got the button, pressed it, and no request was made. */
        setActionError({
          message:
            "You can regenerate scenes on projects you own. Ask an " +
            "administrator, or the project's owner, to run this one.",
        });
        return;
      }
      setActionError(null);
      try {
        await regenerateScene(sceneId);
      } catch (err) {
        setActionError(apiError(err));
      }
    },
    [canEdit, regenerateScene]
  );

  /**
   * Delete a single scene with confirmation.
   */
  const handleDeleteScene = useCallback(
    async (sceneId: string): Promise<void> => {
      if (!canEdit) return;
      const confirmed = window.confirm(
        "Are you sure you want to delete this scene? This action cannot be undone."
      );
      if (!confirmed) return;
      await deleteScene(sceneId);
      setSelectedSceneIds((prev) => {
        const next = new Set(prev);
        next.delete(sceneId);
        return next;
      });
    },
    [canEdit, deleteScene]
  );

  /**
   * Bulk delete selected scenes.
   */
  const handleBulkDelete = useCallback(async (): Promise<void> => {
    if (!canEdit || selectedSceneIds.size === 0) return;
    const confirmed = window.confirm(
      `Are you sure you want to delete ${selectedSceneIds.size} scene(s)? This action cannot be undone.`
    );
    if (!confirmed) return;

    setIsBulkActionLoading(true);
    try {
      await deleteScenes(Array.from(selectedSceneIds));
      setSelectedSceneIds(new Set());
    } finally {
      setIsBulkActionLoading(false);
    }
  }, [canEdit, selectedSceneIds, deleteScenes]);

  /**
   * Bulk regenerate selected scenes.
   */
  const handleBulkRegenerate = useCallback(async (): Promise<void> => {
    if (!canEdit || selectedSceneIds.size === 0) return;
    const confirmed = window.confirm(
      `Regenerate ${selectedSceneIds.size} scene(s)? Existing assets will be replaced.`
    );
    if (!confirmed) return;

    setActionError(null);
    setIsBulkActionLoading(true);
    try {
      await regenerateScenes(Array.from(selectedSceneIds));
      setSelectedSceneIds(new Set());
    } catch (err) {
      setActionError(apiError(err));
    } finally {
      setIsBulkActionLoading(false);
    }
  }, [canEdit, selectedSceneIds, regenerateScenes]);

  /** Reset all filters */
  const handleResetFilters = useCallback((): void => {
    setSearchQuery("");
    setStatusFilter("ALL");
    setMediaTypeFilter("ALL");
  }, []);

  // ── Loading State ────────────────────────────────────────────────────
  if (projectLoading || scenesLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" label="Loading storyboard…" />
      </div>
    );
  }

  // ── Error State ──────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="text-red-500 dark:text-red-400 text-lg font-semibold">
          Failed to load storyboard
        </div>
        <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md text-center">
          {error.message ||
            "An unexpected error occurred while fetching storyboard data."}
        </p>
        <button
          onClick={() => mutate()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  // ── Empty State ──────────────────────────────────────────────────────
  if (!scenes || scenes.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
          <svg
            className="w-16 h-16 text-gray-500 dark:text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            />
          </svg>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            No scenes yet
          </h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md text-center">
            This project does not have a storyboard yet. Generate one by
            processing the transcript through the pipeline, or upload an
            existing storyboard from the project settings.
          </p>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        {/* ── The open review gate, as the primary action ─────────────
            WP-62 Task 2(d). On this tab the preview IS the page, so the panel
            sits directly above the storyboard it is asking about. */}
        {gateIsOpen && storyboardGate && (
          <GateReviewPanel
            projectId={projectId}
            gate="storyboard"
            state={storyboardGate}
            canDecide={canDecideGate}
            onDecided={() => {
              void mutateProgress();
              void mutate();
            }}
          />
        )}

        {/* ── A refusal, in the server's own words ────────────────────
            WP-63 Task 7. Not a generic "Regeneration failed": the API says
            WHICH gate, over WHICH artefact version, and what to do next, and
            no component here could reconstruct any of that. */}
        {actionError && (
          <div
            role="alert"
            className="flex items-start justify-between gap-4 rounded-xl border-2 border-red-400 bg-red-50 p-4 dark:border-red-700 dark:bg-red-950/40"
          >
            <div className="min-w-0">
              <p className="text-sm font-semibold text-red-900 dark:text-red-200">
                The request was refused
                {actionError.code ? ` — ${actionError.code}` : ""}
              </p>
              <p className="mt-1 text-sm text-red-900/90 dark:text-red-200/90">
                {actionError.message}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setActionError(null)}
              aria-label="Dismiss"
              className="shrink-0 rounded px-2 py-1 text-sm text-red-800 hover:bg-red-100 dark:text-red-300 dark:hover:bg-red-900/40"
            >
              ✕
            </button>
          </div>
        )}

        {/* ── Page Header ──────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Storyboard Editor
            </h1>
            <p className="mt-1 text-gray-500 dark:text-gray-400">
              {scenes.length} scene{scenes.length !== 1 ? "s" : ""} ·{" "}
              {Math.floor(totalDuration / 60)}:
              {String(Math.round(totalDuration % 60)).padStart(2, "0")}{" "}
              total duration
              {!canEdit && (
                <span className="ml-2 text-yellow-500 dark:text-yellow-400 text-xs font-medium">
                  (read-only)
                </span>
              )}
            </p>
          </div>

          {/* View Mode Toggle + review gate */}
          <div className="mt-4 sm:mt-0 flex items-center gap-2">
            {/* WP-62 Task 2(d). THE APPROVE BUTTON HAS MOVED OFF THIS ROW.
                It sat here, between the read-only badge and the Grid/Timeline
                toggle, at the weight of a view toggle — a blocking review gate
                rendered as a corner control. It is now the amber gate panel
                above this header, which states what is being asked, shows the
                decision's consequence, offers reject and regenerate as well as
                approve (§6.4 requires all three; only approve existed), and
                takes a note that lands in audit_log.

                Leaving a second Approve control here as well would be the
                same-screen duplication WP-62 Task 4 removes on Overview. */}
            <button
              onClick={() => setViewMode("grid")}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                viewMode === "grid"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-600"
              }`}
              aria-label="Grid view"
            >
              <svg
                className="w-4 h-4 inline-block mr-1"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
                />
              </svg>
              Grid
            </button>
            <button
              onClick={() => setViewMode("timeline")}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                viewMode === "timeline"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-600"
              }`}
              aria-label="Timeline view"
            >
              <svg
                className="w-4 h-4 inline-block mr-1"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
              Timeline
            </button>
          </div>
        </div>

        {/* ── Filter Bar ───────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 p-4 bg-gray-100 dark:bg-gray-800 rounded-xl">
          {/* Search */}
          <div>
            <label
              htmlFor="storyboard-search"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              Search
            </label>
            <input
              id="storyboard-search"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search narration, visuals…"
              className="w-full px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Status Filter */}
          <div>
            <label
              htmlFor="status-filter"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              Status
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as SceneStatus | "ALL")
              }
              className="w-full px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">All Statuses ({statusCounts.ALL})</option>
              {SCENE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status} ({statusCounts[status]})
                </option>
              ))}
            </select>
          </div>

          {/* Media Type Filter */}
          <div>
            <label
              htmlFor="media-type-filter"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              Media Type
            </label>
            <select
              id="media-type-filter"
              value={mediaTypeFilter}
              onChange={(e) =>
                setMediaTypeFilter(e.target.value as MediaType | "ALL")
              }
              className="w-full px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">All Types</option>
              {MEDIA_TYPES.map((type) => (
                <option key={type} value={type}>
                  {mediaTypeLabel(type)}
                </option>
              ))}
            </select>
          </div>

          {/* Reset Filters */}
          <div className="flex items-end">
            <button
              onClick={handleResetFilters}
              className="w-full px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-600 transition-colors"
            >
              Reset Filters
            </button>
          </div>
        </div>

        {/* ── Bulk Actions Bar ─────────────────────────────────────── */}
        {canEdit && selectedSceneIds.size > 0 && (
          <div className="flex items-center gap-3 mb-4 p-3 bg-blue-100 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-lg">
            <span className="text-sm text-blue-800 dark:text-blue-300">
              {selectedSceneIds.size} scene
              {selectedSceneIds.size !== 1 ? "s" : ""} selected
            </span>
            <div className="flex-1" />
            <button
              onClick={handleSelectAll}
              className="px-3 py-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-600 transition-colors"
            >
              Select All ({filteredScenes.length})
            </button>
            <button
              onClick={handleClearSelection}
              className="px-3 py-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-600 transition-colors"
            >
              Clear
            </button>
            <button
              onClick={handleBulkRegenerate}
              disabled={isBulkActionLoading}
              className="px-3 py-1.5 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700 transition-colors disabled:opacity-50"
            >
              {isBulkActionLoading ? "Processing…" : "Regenerate Selected"}
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={isBulkActionLoading}
              className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700 transition-colors disabled:opacity-50"
            >
              {isBulkActionLoading ? "Processing…" : "Delete Selected"}
            </button>
          </div>
        )}

        {/* ── Main Content Area ────────────────────────────────────── */}
        {viewMode === "grid" ? (
          <StoryboardEditor
            projectId={projectId}
            scenes={filteredScenes}
            canEdit={canEdit}
            selectedSceneIds={selectedSceneIds}
            onToggleSelect={handleToggleSelect}
            onEditScene={handleEditScene}
            onRegenerateScene={handleRegenerateScene}
            onDeleteScene={handleDeleteScene}
            onReorder={handleReorder}
          />
        ) : (
          <SceneTimeline
            projectId={projectId}
            scenes={filteredScenes}
            canEdit={canEdit}
            onEditScene={handleEditScene}
            onRegenerateScene={handleRegenerateScene}
            totalDuration={totalDuration}
          />
        )}

        {/* ── Scene Edit Modal ─────────────────────────────────────── */}
        {isEditModalOpen && editingScene && (
          <SceneEditModal
            scene={editingScene}
            canEdit={canEdit}
            onSave={handleSaveScene}
            /* WP-64 Task 3. Passed straight through: it returns a proposal and
               writes nothing, so there is no page-level state to keep and no
               cache to invalidate. The modal holds the proposal until the
               operator accepts it, at which point it becomes an ordinary
               unsaved edit that `handleSaveScene` persists. */
            onAdaptDescription={adaptSceneDescription}
            onClose={handleCloseEditModal}
            onRegenerate={handleRegenerateScene}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}
