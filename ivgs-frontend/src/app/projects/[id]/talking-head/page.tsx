"use client";

import React, { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useAssets } from "@/hooks/useAssets";
import { useAuth } from "@/hooks/useAuth";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { Asset } from "@/types/api";
import { assetFilename, assetTypeLabel, formatBytes, formatDuration } from "@/lib/media";
import { useAssetDownload, useAssetObjectUrl } from "@/hooks/useAssetMedia";

/**
 * §8.1.3 Table 8-2 — Talking Head Tab
 *
 * Features:
 *   - Preview of rendered talking head video
 *   - Lip-sync alignment score display
 *   - Regenerate button for re-processing
 *
 * WP-40 addendum. `<video src={asset.url}>` against a field the API does not
 * send: no `src` attribute, no request, a black box. `asset.scene_label`,
 * `asset.filename`, `asset.quality_score` and `asset.metadata.duration` are
 * all phantom as well, so the label was empty and neither the lip-sync badge
 * nor the duration ever rendered.
 *
 * The clip now loads through the authenticated download proxy. Lip-sync
 * scoring lives in `asset_quality_scores` behind /api/v1/quality and is not
 * on this payload, so nothing here claims to know it.
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
        <div className="p-4 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400">
          Failed to load talking head: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Talking Head</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            Preview rendered talking head video with lip-sync alignment
          </p>
        </div>
      </div>

      {talkingHeadAssets.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          No talking head video rendered yet.
        </div>
      ) : (
        <div className="space-y-6">
          {talkingHeadAssets.map((asset: Asset) => (
            <TalkingHeadClip
              key={asset.id}
              asset={asset}
              canEdit={canEdit}
              isRegenerating={isRegenerating}
              onRegenerate={handleRegenerate}
            />
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

/**
 * One rendered talking-head clip.
 *
 * The bytes are fetched with the Bearer token and handed to `<video>` as an
 * object URL -- a `<video src>` pointed straight at the proxy would 403,
 * because a browser will not attach the header.
 */
function TalkingHeadClip({
  asset,
  canEdit,
  isRegenerating,
  onRegenerate,
}: {
  asset: Asset;
  canEdit: boolean;
  isRegenerating: boolean;
  onRegenerate: (assetId: string) => Promise<void>;
}): React.ReactElement {
  const { url, isLoading, error } = useAssetObjectUrl(asset.id, true);
  const { download, downloadingId } = useAssetDownload();

  return (
    <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden">
      <div className="relative aspect-video bg-black flex items-center justify-center">
        {url ? (
          <video
            src={url}
            controls
            className="w-full h-full object-contain"
            preload="metadata"
          >
            Your browser does not support video playback.
          </video>
        ) : (
          <p className="text-sm text-gray-400">
            {error ? `Could not load this clip: ${error}` : isLoading ? "Loading clip…" : ""}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between px-5 py-4 gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {assetFilename(asset)}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
            {assetTypeLabel(asset)} · {formatBytes(asset.file_size_bytes)}
            {asset.duration_seconds != null
              ? ` · ${formatDuration(asset.duration_seconds)}`
              : ""}
            {asset.language_code ? ` · ${asset.language_code}` : ""}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => download(asset)}
            disabled={downloadingId === asset.id}
            className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {downloadingId === asset.id ? "Downloading…" : "↓ Download"}
          </button>
          {canEdit && (
            <button
              onClick={() => onRegenerate(asset.id)}
              disabled={isRegenerating}
              className="px-4 py-1.5 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-600 hover:text-gray-900 dark:hover:text-white disabled:opacity-50 transition-colors"
            >
              {isRegenerating ? "Regenerating…" : "Regenerate"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
