"use client";

import React, { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useAssets } from "@/hooks/useAssets";
import { useAuth } from "@/hooks/useAuth";
import AssetBrowser from "@/components/AssetBrowser";
import AssetUploader from "@/components/AssetUploader";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { Asset } from "@/types/api";
import { assetMediaKind, assetSearchText, type MediaKind } from "@/lib/media";
import { useSceneIndexMap } from "@/hooks/useAssetMedia";

/**
 * §8.1.3 Table 8-2 — Media Assets Tab
 *
 * Features:
 *   - Grid of generated images/clips/animations per scene
 *   - Quality score badge per asset
 *   - Generation prompt display with edit button
 *   - Regenerate button per asset
 *   - Drag-drop file upload for manual assets
 *   - Preview modal for full-resolution view
 *
 * RBAC per Table 8-3:
 *   - admin/operator: upload, edit, regenerate
 *   - viewer: read-only browse and preview
 */

type ViewMode = "grid" | "list";
/**
 * WP-40 Task 1: filter on the DERIVED media kind, not on `asset_type`.
 *
 * `asset_type` is a pipeline role, and the live project holds seven of them
 * -- image, audio, video, final_render, talking_head, document,
 * reference_clip. The old tabs offered image / video / animation, so the
 * eighteen audio assets and the finished 720p draft were unreachable by any
 * filter, and "animation" matched nothing at all.
 */
type AssetFilter = "all" | MediaKind;

const ASSET_FILTERS: { id: AssetFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "image", label: "Images" },
  { id: "video", label: "Video" },
  { id: "audio", label: "Audio" },
  { id: "other", label: "Other" },
];

export default function AssetsPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const {
    assets,
    isLoading,
    error,
    uploadAsset,
    regenerateAsset,
    mutate,
  } = useAssets(projectId);

  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [filter, setFilter] = useState<AssetFilter>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [showUploader, setShowUploader] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  const canEdit = user?.role === "admin" || user?.role === "operator";

  /* Scene indices, so cards whose SeaweedFS paths collide are still
     tellable apart. Shares its SWR key with the storyboard page. */
  const sceneIndexById = useSceneIndexMap(projectId);

  /**
   * Filter assets by type and search query.
   */
  const filteredAssets = React.useMemo<Asset[]>(() => {
    if (!assets) return [];
    let result = [...assets];

    if (filter !== "all") {
      result = result.filter((a: Asset) => assetMediaKind(a) === filter);
    }

    if (searchQuery.trim()) {
      // The old haystack was filename / scene_label / generation_prompt --
      // three fields the API does not send, so typing anything emptied the
      // grid. `assetSearchText` searches what actually arrives.
      const q = searchQuery.toLowerCase();
      result = result.filter((a: Asset) => assetSearchText(a).includes(q));
    }

    return result.sort((a, b) => {
      const ai = a.scene_id ? sceneIndexById.get(a.scene_id) ?? 1e9 : 1e9;
      const bi = b.scene_id ? sceneIndexById.get(b.scene_id) ?? 1e9 : 1e9;
      if (ai !== bi) return ai - bi;
      return a.created_at < b.created_at ? -1 : 1;
    });
  }, [assets, filter, searchQuery, sceneIndexById]);

  /**
   * Handle manual file upload via drag-drop or file picker.
   */
  const handleUpload = useCallback(
    async (files: FileList | File[]): Promise<void> => {
      if (!canEdit) return;
      setIsUploading(true);
      try {
        for (const file of Array.from(files)) {
          const formData = new FormData();
          formData.append("file", file);
          formData.append("project_id", projectId);
          await uploadAsset(formData);
        }
        setToastMessage(
          `${files.length} asset${files.length > 1 ? "s" : ""} uploaded.`
        );
        setToastType("success");
        setShowToast(true);
        setShowUploader(false);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Upload failed.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setIsUploading(false);
      }
    },
    [canEdit, projectId, uploadAsset, mutate]
  );

  /**
   * Trigger regeneration of a specific asset via the pipeline.
   */
  const handleRegenerate = useCallback(
    async (assetId: string): Promise<void> => {
      if (!canEdit) return;
      try {
        await regenerateAsset(assetId);
        setToastMessage("Asset regeneration queued.");
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Regeneration failed.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      }
    },
    [canEdit, regenerateAsset, mutate]
  );

  // ── Loading ─────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading assets…" />
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400">
          Failed to load assets: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Media Assets</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            {filteredAssets.length} asset
            {filteredAssets.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3 mt-4 sm:mt-0">
          {canEdit && (
            <button
              onClick={() => setShowUploader(!showUploader)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
            >
              + Upload Asset
            </button>
          )}
        </div>
      </div>

      {/* ── Upload Area ────────────────────────────────────────────── */}
      {showUploader && canEdit && (
        <div className="mb-6 p-6 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 border-dashed rounded-xl">
          <AssetUploader
            accept="image/*,video/*"
            multiple
            onFileSelect={(files) => {
              if (files) handleUpload(files);
            }}
            isUploading={isUploading}
          />
        </div>
      )}

      {/* ── Filter Bar ─────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search assets…"
            className="w-full pl-9 pr-4 py-2 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 dark:text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        <div className="flex items-center gap-2">
          {ASSET_FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                filter === f.id
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:text-white border border-gray-300 dark:border-gray-600"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 ml-auto">
          <button
            onClick={() => setViewMode("grid")}
            className={`p-2 rounded ${
              viewMode === "grid"
                ? "text-blue-600 dark:text-blue-400 bg-gray-100 dark:bg-gray-800"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
            title="Grid view"
          >
            <svg
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>
          <button
            onClick={() => setViewMode("list")}
            className={`p-2 rounded ${
              viewMode === "list"
                ? "text-blue-600 dark:text-blue-400 bg-gray-100 dark:bg-gray-800"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
            title="List view"
          >
            <svg
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Asset Grid / List ──────────────────────────────────────── */}
      {filteredAssets.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          {assets && assets.length > 0
            ? "No assets match your filters."
            : "No assets generated yet for this project."}
        </div>
      ) : (
        <AssetBrowser
          assets={filteredAssets}
          viewMode={viewMode}
          canEdit={canEdit}
          onRegenerate={handleRegenerate}
          sceneIndexById={sceneIndexById}
        />
      )}

      {/* Toast */}
      {showToast && (
        <Toast
          message={toastMessage}
          type={toastType}
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
}
