"use client";

import React, { useState, useCallback } from "react";
import type { Asset } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Media Assets Grid
 *
 * Grid of generated images/clips/animations per scene:
 *   - Thumbnail preview
 *   - Quality score badge
 *   - Generation prompt with edit button
 *   - Regenerate button
 *   - Click for full-resolution preview modal
 */

interface AssetBrowserProps {
  assets: Asset[];
  viewMode: "grid" | "list";
  canEdit: boolean;
  onRegenerate: (assetId: string) => Promise<void>;
}

export default function AssetBrowser({
  assets,
  viewMode,
  canEdit,
  onRegenerate,
}: AssetBrowserProps): React.ReactElement {
  const [previewAsset, setPreviewAsset] = useState<Asset | null>(null);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  const handleRegenerate = useCallback(
    async (assetId: string): Promise<void> => {
      setRegeneratingId(assetId);
      try {
        await onRegenerate(assetId);
      } finally {
        setRegeneratingId(null);
      }
    },
    [onRegenerate]
  );

  /** Quality score badge color */
  const getQualityColor = (score: number | undefined | null): string => {
    if (score === undefined || score === null) return "bg-gray-700 text-gray-400";
    if (score >= 0.8) return "bg-green-900/40 text-green-400";
    if (score >= 0.5) return "bg-yellow-900/40 text-yellow-400";
    return "bg-red-900/40 text-red-400";
  };

  const getQualityLabel = (score: number | undefined | null): string => {
    if (score === undefined || score === null) return "N/A";
    return `${(score * 100).toFixed(0)}%`;
  };

  /** Determine thumbnail display by asset type */
  const renderThumbnail = (asset: Asset): React.ReactElement => {
    if (asset.asset_type === "image" || asset.asset_type === "animation") {
      return (
        <img
          src={asset.thumbnail_url || asset.url}
          alt={asset.filename}
          className="w-full h-full object-cover"
          loading="lazy"
        />
      );
    }
    if (asset.asset_type === "video") {
      return (
        <div className="w-full h-full flex items-center justify-center bg-white dark:bg-gray-900">
          <svg
            className="w-10 h-10 text-gray-600 dark:text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
      );
    }
    return (
      <div className="w-full h-full flex items-center justify-center bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-400">
        <span className="text-xs">Asset</span>
      </div>
    );
  };

  // ── Grid View ───────────────────────────────────────────────────────
  if (viewMode === "grid") {
    return (
      <>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {assets.map((asset: Asset) => (
            <div
              key={asset.id}
              className="group bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
            >
              {/* Thumbnail */}
              <div
                className="relative aspect-square cursor-pointer overflow-hidden"
                onClick={() => setPreviewAsset(asset)}
              >
                {renderThumbnail(asset)}
                {/* Quality Badge */}
                <div
                  className={`absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-bold ${getQualityColor(
                    asset.quality_score
                  )}`}
                >
                  {getQualityLabel(asset.quality_score)}
                </div>
              </div>

              {/* Info */}
              <div className="px-3 py-2">
                <p className="text-xs text-gray-900 dark:text-white truncate font-medium">
                  {asset.scene_label || asset.filename}
                </p>
                {asset.generation_prompt && (
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 truncate mt-0.5">
                    {asset.generation_prompt}
                  </p>
                )}
                {canEdit && (
                  <button
                    onClick={() => handleRegenerate(asset.id)}
                    disabled={regeneratingId === asset.id}
                    className="mt-1.5 text-[10px] text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                  >
                    {regeneratingId === asset.id ? "Regenerating…" : "↻ Regenerate"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Preview Modal */}
        {previewAsset && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
            onClick={() => setPreviewAsset(null)}
          >
            <div
              className="relative max-w-4xl max-h-[90vh] w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              {previewAsset.asset_type === "video" ? (
                <video
                  src={previewAsset.url}
                  controls
                  autoPlay
                  className="w-full rounded-xl"
                />
              ) : (
                <img
                  src={previewAsset.url}
                  alt={previewAsset.filename}
                  className="w-full rounded-xl object-contain max-h-[85vh]"
                />
              )}
              <div className="mt-3 px-2 flex items-center justify-between">
                <div>
                  <p className="text-gray-900 dark:text-white font-medium text-sm">
                    {previewAsset.scene_label || previewAsset.filename}
                  </p>
                  {previewAsset.generation_prompt && (
                    <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">
                      {previewAsset.generation_prompt}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setPreviewAsset(null)}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-600 transition-colors text-sm"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  // ── List View ───────────────────────────────────────────────────────
  return (
    <>
      <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-300 dark:border-gray-700 text-left">
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-16">
                  Preview
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Name
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Quality
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Prompt
                </th>
                {canEdit && (
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-300 dark:divide-gray-700">
              {assets.map((asset: Asset) => (
                <tr
                  key={asset.id}
                  className="hover:bg-gray-750 transition-colors"
                >
                  <td className="px-4 py-2">
                    <div
                      className="w-12 h-12 rounded overflow-hidden cursor-pointer"
                      onClick={() => setPreviewAsset(asset)}
                    >
                      {renderThumbnail(asset)}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-gray-900 dark:text-white font-medium">
                    {asset.scene_label || asset.filename}
                  </td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400 capitalize">
                    {asset.asset_type}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${getQualityColor(
                        asset.quality_score
                      )}`}
                    >
                      {getQualityLabel(asset.quality_score)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400 text-xs max-w-[200px] truncate">
                    {asset.generation_prompt || "—"}
                  </td>
                  {canEdit && (
                    <td className="px-4 py-2">
                      <button
                        onClick={() => handleRegenerate(asset.id)}
                        disabled={regeneratingId === asset.id}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                      >
                        {regeneratingId === asset.id
                          ? "Regenerating…"
                          : "Regenerate"}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Preview Modal (same as grid) */}
      {previewAsset && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={() => setPreviewAsset(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            {previewAsset.asset_type === "video" ? (
              <video
                src={previewAsset.url}
                controls
                autoPlay
                className="w-full rounded-xl"
              />
            ) : (
              <img
                src={previewAsset.url}
                alt={previewAsset.filename}
                className="w-full rounded-xl object-contain max-h-[85vh]"
              />
            )}
            <button
              onClick={() => setPreviewAsset(null)}
              className="absolute top-3 right-3 w-8 h-8 bg-black/60 rounded-full text-gray-900 dark:text-white flex items-center justify-center hover:bg-black/80"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  );
}
