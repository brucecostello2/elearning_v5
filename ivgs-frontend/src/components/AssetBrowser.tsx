"use client";

import React, { useCallback, useRef, useState } from "react";
import type { Asset } from "@/types/api";
import {
  assetFilename,
  assetLabel,
  assetMediaKind,
  assetTypeLabel,
  formatBytes,
  type MediaKind,
} from "@/lib/media";
import {
  useAssetDownload,
  useAssetObjectUrl,
  useInView,
} from "@/hooks/useAssetMedia";

/**
 * §8.1.3 Table 8-2 — Media Assets Grid
 *
 * WP-40 Task 1. Every card here used to render blank, and devtools recorded
 * ZERO image requests over 40 real assets. The cause was not a failed load:
 * the thumbnail was `<img src={asset.thumbnail_url || asset.url}>` and the
 * API sends neither field, so React emitted an `<img>` with no `src` and the
 * browser had nothing to request. See `@/lib/media` for the full wire shape.
 *
 * What a card can show is derived from what the API does send
 * (`mime_type`, `seaweedfs_path`, `file_size_bytes`, `asset_type`), and the
 * bytes come from the existing authenticated proxy
 * `GET /api/v1/assets/{id}/download`.
 *
 * Deliberate choices, because they are visible to the operator:
 *   - There is no thumbnail route on this API. An image card therefore shows
 *     the FULL-SIZE original, and only once it scrolls into view.
 *   - Video and audio are never fetched for a card -- a 6 MB draft render is
 *     not a thumbnail. They show a typed placeholder and load on demand in
 *     the preview.
 *   - Quality scores are not on this payload (they live in
 *     `asset_quality_scores` behind /api/v1/quality). The card shows size and
 *     type, which are real, instead of a badge reading "N/A" on every asset.
 */

interface AssetBrowserProps {
  assets: Asset[];
  viewMode: "grid" | "list";
  canEdit: boolean;
  onRegenerate: (assetId: string) => Promise<void>;
  /**
   * `scene_id` -> `scene_index`, so a card can say which scene it belongs to.
   *
   * WP-40 addendum, correcting a weakness in the first pass: `assetFilename`
   * is a real field but not a distinguishing one. All 16 image assets of
   * project c12fa967 share the SeaweedFS path `/ivgs/images/{pid}/image.png`
   * and all 18 audio assets share `/ivgs/audio/{pid}/en-US.wav`, so the grid
   * showed sixteen cards reading "image.png". `scene_id` is populated on all
   * 36 scene-scoped assets and is what makes them tellable apart.
   */
  sceneIndexById?: Map<string, number>;
}

/* ── Placeholders ──────────────────────────────────────────────────────── */

function PlayIcon({ className }: { className: string }): React.ReactElement {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
  );
}

function AudioIcon({ className }: { className: string }): React.ReactElement {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M9 19V6l12-3v13M9 19a3 3 0 11-6 0 3 3 0 016 0zm12-3a3 3 0 11-6 0 3 3 0 016 0z"
      />
    </svg>
  );
}

function DocIcon({ className }: { className: string }): React.ReactElement {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  );
}

/**
 * A non-image card face: a typed icon plus the asset's real type label.
 * Also the fallback when an image genuinely fails to load.
 */
function Placeholder({
  kind,
  label,
  note,
  iconSize,
}: {
  kind: MediaKind;
  label: string;
  note?: string;
  iconSize: string;
}): React.ReactElement {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-1 bg-gray-200 dark:bg-gray-900 text-gray-600 dark:text-gray-400 px-2 text-center">
      {kind === "video" ? (
        <PlayIcon className={iconSize} />
      ) : kind === "audio" ? (
        <AudioIcon className={iconSize} />
      ) : (
        <DocIcon className={iconSize} />
      )}
      <span className="text-[10px] leading-tight truncate max-w-full">{label}</span>
      {note && <span className="text-[9px] text-red-500 dark:text-red-400">{note}</span>}
    </div>
  );
}

/* ── Thumbnail ─────────────────────────────────────────────────────────── */

/**
 * The card face.
 *
 * Images fetch their bytes through the authenticated proxy once the card is
 * near the viewport; everything else renders a typed placeholder and costs
 * no bandwidth at all.
 */
function AssetThumbnail({
  asset,
  iconSize,
}: {
  asset: Asset;
  iconSize: string;
}): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const inView = useInView(containerRef);
  const kind = assetMediaKind(asset);
  const isImage = kind === "image";
  const { url, isLoading, error } = useAssetObjectUrl(asset.id, isImage && inView);

  return (
    <div ref={containerRef} className="w-full h-full">
      {!isImage ? (
        <Placeholder kind={kind} label={assetTypeLabel(asset)} iconSize={iconSize} />
      ) : error ? (
        <Placeholder
          kind="other"
          label={assetTypeLabel(asset)}
          note="unavailable"
          iconSize={iconSize}
        />
      ) : url ? (
        <img
          src={url}
          alt={assetFilename(asset)}
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-gray-200 dark:bg-gray-900">
          <span className="text-[10px] text-gray-500 dark:text-gray-400">
            {isLoading ? "Loading…" : ""}
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Preview modal ─────────────────────────────────────────────────────── */

/**
 * Full-resolution preview. The bytes are fetched here on open -- this is the
 * only place a video or audio asset is ever downloaded by the grid.
 */
function AssetPreview({
  asset,
  onClose,
  onDownload,
  isDownloading,
}: {
  asset: Asset;
  onClose: () => void;
  onDownload: (asset: Asset) => void;
  isDownloading: boolean;
}): React.ReactElement {
  const kind = assetMediaKind(asset);
  const { url, isLoading, error } = useAssetObjectUrl(asset.id, true);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      <div
        className="relative max-w-4xl max-h-[90vh] w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-gray-100 dark:bg-gray-900 rounded-xl p-4">
          {isLoading ? (
            <div className="py-16 text-center text-sm text-gray-500 dark:text-gray-400">
              Loading media…
            </div>
          ) : error ? (
            <div className="py-16 text-center text-sm text-red-500 dark:text-red-400">
              Could not load this asset: {error}
            </div>
          ) : url && kind === "video" ? (
            <video src={url} controls autoPlay className="w-full rounded-lg max-h-[70vh]" />
          ) : url && kind === "audio" ? (
            <div className="py-12 px-4">
              <audio src={url} controls className="w-full" />
            </div>
          ) : url && kind === "image" ? (
            <img
              src={url}
              alt={assetFilename(asset)}
              className="w-full rounded-lg object-contain max-h-[70vh]"
            />
          ) : (
            <div className="py-16 text-center text-sm text-gray-500 dark:text-gray-400">
              {assetTypeLabel(asset)} — no inline preview for this type. Use
              Download.
            </div>
          )}
        </div>

        <div className="mt-3 px-2 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-white font-medium text-sm truncate">
              {assetFilename(asset)}
            </p>
            <p className="text-gray-400 text-xs mt-0.5">
              {assetTypeLabel(asset)} · {asset.mime_type || "unknown type"} ·{" "}
              {formatBytes(asset.file_size_bytes)}
              {asset.language_code ? ` · ${asset.language_code}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => onDownload(asset)}
              disabled={isDownloading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm"
            >
              {isDownloading ? "Downloading…" : "↓ Download"}
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-600 transition-colors text-sm"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Browser ───────────────────────────────────────────────────────────── */

export default function AssetBrowser({
  assets,
  viewMode,
  canEdit,
  onRegenerate,
  sceneIndexById,
}: AssetBrowserProps): React.ReactElement {
  const labelOf = useCallback(
    (asset: Asset): string =>
      assetLabel(
        asset,
        asset.scene_id ? sceneIndexById?.get(asset.scene_id) ?? null : null,
      ),
    [sceneIndexById],
  );

  const [previewAsset, setPreviewAsset] = useState<Asset | null>(null);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const { download, downloadingId, error: downloadError } = useAssetDownload();

  const handleRegenerate = useCallback(
    async (assetId: string): Promise<void> => {
      setRegeneratingId(assetId);
      try {
        await onRegenerate(assetId);
      } finally {
        setRegeneratingId(null);
      }
    },
    [onRegenerate],
  );

  const modal = previewAsset ? (
    <AssetPreview
      asset={previewAsset}
      onClose={() => setPreviewAsset(null)}
      onDownload={download}
      isDownloading={downloadingId === previewAsset.id}
    />
  ) : null;

  const downloadBanner = downloadError ? (
    <div className="mb-4 p-3 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400 text-sm">
      Download failed: {downloadError}
    </div>
  ) : null;

  // ── Grid View ───────────────────────────────────────────────────────
  if (viewMode === "grid") {
    return (
      <>
        {downloadBanner}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {assets.map((asset: Asset) => {
            const kind = assetMediaKind(asset);
            return (
              <div
                key={asset.id}
                className="group bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
              >
                {/* Face — click to preview */}
                <div
                  className="relative aspect-square cursor-pointer overflow-hidden"
                  onClick={() => setPreviewAsset(asset)}
                  title={`Preview ${assetFilename(asset)}`}
                >
                  <AssetThumbnail asset={asset} iconSize="w-10 h-10" />
                  {(kind === "video" || kind === "audio") && (
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
                      <span className="text-white text-xs font-medium">
                        ▶ Play
                      </span>
                    </div>
                  )}
                  <div className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-black/60 text-white">
                    {formatBytes(asset.file_size_bytes)}
                  </div>
                </div>

                {/* Info */}
                <div className="px-3 py-2">
                  <p
                    className="text-xs text-gray-900 dark:text-white truncate font-medium"
                    title={labelOf(asset)}
                  >
                    {labelOf(asset)}
                  </p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 truncate mt-0.5">
                    {assetTypeLabel(asset)}
                    {asset.language_code ? ` · ${asset.language_code}` : ""}
                  </p>
                  <div className="mt-1.5 flex items-center gap-3">
                    <button
                      onClick={() => download(asset)}
                      disabled={downloadingId === asset.id}
                      className="text-[10px] text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                    >
                      {downloadingId === asset.id ? "Downloading…" : "↓ Download"}
                    </button>
                    {canEdit && (
                      <button
                        onClick={() => handleRegenerate(asset.id)}
                        disabled={regeneratingId === asset.id}
                        className="text-[10px] text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                      >
                        {regeneratingId === asset.id ? "Regenerating…" : "↻ Regenerate"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {modal}
      </>
    );
  }

  // ── List View ───────────────────────────────────────────────────────
  return (
    <>
      {downloadBanner}
      <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-300 dark:border-gray-700 text-left">
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-16">
                  Preview
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  File
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Size
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Created
                </th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-300 dark:divide-gray-700">
              {assets.map((asset: Asset) => (
                <tr key={asset.id} className="hover:bg-gray-750 transition-colors">
                  <td className="px-4 py-2">
                    <div
                      className="w-12 h-12 rounded overflow-hidden cursor-pointer"
                      onClick={() => setPreviewAsset(asset)}
                    >
                      <AssetThumbnail asset={asset} iconSize="w-5 h-5" />
                    </div>
                  </td>
                  <td className="px-4 py-2 text-gray-900 dark:text-white font-medium">
                    <span className="block max-w-[280px] truncate" title={labelOf(asset)}>
                      {labelOf(asset)}
                    </span>
                    <span className="block text-xs text-gray-500 dark:text-gray-400">
                      {asset.mime_type || "unknown type"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400">
                    {assetTypeLabel(asset)}
                  </td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400">
                    {formatBytes(asset.file_size_bytes)}
                  </td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400 text-xs">
                    {asset.created_at
                      ? new Date(asset.created_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => download(asset)}
                        disabled={downloadingId === asset.id}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                      >
                        {downloadingId === asset.id ? "Downloading…" : "Download"}
                      </button>
                      {canEdit && (
                        <button
                          onClick={() => handleRegenerate(asset.id)}
                          disabled={regeneratingId === asset.id}
                          className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                        >
                          {regeneratingId === asset.id ? "Regenerating…" : "Regenerate"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {modal}
    </>
  );
}
