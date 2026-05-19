"use client";

import React, { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useAssets } from "@/hooks/useAssets";
import { useAuth } from "@/hooks/useAuth";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { Asset } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Talking Head Tab
 *
 * Features:
 *   - Preview of rendered talking head video
 *   - Lip-sync alignment score display
 *   - Regenerate button for re-processing
 */

export default function TalkingHeadPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const { assets, isLoading, error, regenerateAsset, mutate } =
    useAssets(projectId);

  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  const canEdit = user?.role === "admin" || user?.role === "operator";

  /** Filter to talking head assets */
  const talkingHeadAssets = React.useMemo<Asset[]>(
    () =>
      (assets || []).filter(
        (a: Asset) => a.asset_type === "talking_head"
      ),
    [assets]
  );

  const handleRegenerate = useCallback(
    async (assetId: string): Promise<void> => {
      if (!canEdit) return;
      setIsRegenerating(true);
      try {
        await regenerateAsset(assetId);
        setToastMessage("Talking head regeneration queued.");
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Regeneration failed.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setIsRegenerating(false);
      }
    },
    [canEdit, regenerateAsset, mutate]
  );

  /**
   * Lip-sync score color coding.
   * >= 0.85: green (excellent), >= 0.70: yellow (acceptable), < 0.70: red (poor)
   */
  const getScoreColor = (score: number | undefined | null): string => {
    if (score === undefined || score === null) return "text-gray-500";
    if (score >= 0.85) return "text-green-400 bg-green-900/30";
    if (score >= 0.7) return "text-yellow-400 bg-yellow-900/30";
    return "text-red-400 bg-red-900/30";
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading talking head…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          Failed to load talking head: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Talking Head</h2>
          <p className="text-gray-400 text-sm mt-1">
            Preview rendered talking head video with lip-sync alignment
          </p>
        </div>
        <a
          href={`/projects/${projectId}`}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          ← Back
        </a>
      </div>

      {talkingHeadAssets.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          No talking head video rendered yet.
        </div>
      ) : (
        <div className="space-y-6">
          {talkingHeadAssets.map((asset: Asset) => (
            <div
              key={asset.id}
              className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden"
            >
              {/* Video Player */}
              <div className="relative aspect-video bg-black">
                <video
                  src={asset.url}
                  controls
                  className="w-full h-full object-contain"
                  preload="metadata"
                >
                  Your browser does not support video playback.
                </video>
              </div>

              {/* Info Bar */}
              <div className="flex items-center justify-between px-5 py-4">
                <div className="flex items-center gap-4">
                  <span className="text-sm font-medium text-white">
                    {asset.scene_label || asset.filename}
                  </span>
                  {asset.quality_score !== undefined &&
                    asset.quality_score !== null && (
                      <span
                        className={`px-2.5 py-0.5 text-xs font-medium rounded-full ${getScoreColor(
                          asset.quality_score
                        )}`}
                      >
                        Lip-sync: {(asset.quality_score * 100).toFixed(1)}%
                      </span>
                    )}
                  {asset.metadata?.duration && (
                    <span className="text-xs text-gray-500">
                      Duration: {asset.metadata.duration}s
                    </span>
                  )}
                </div>
                {canEdit && (
                  <button
                    onClick={() => handleRegenerate(asset.id)}
                    disabled={isRegenerating}
                    className="px-4 py-1.5 text-sm bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 hover:text-white disabled:opacity-50 transition-colors"
                  >
                    {isRegenerating ? "Regenerating…" : "Regenerate"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

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
