"use client";

import React, { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAssets } from "@/hooks/useAssets";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { Asset } from "@/types/api";
import {
  assetFilename,
  assetRenderKind,
  assetRenderProfile,
  formatBytes,
} from "@/lib/media";
import { useAssetDownload, useAssetObjectUrl } from "@/hooks/useAssetMedia";

/**
 * §8.1.3 Table 8-2 — Draft Preview Tab
 *
 * Embedded player for the 720p prototype draft — the low-resolution preview
 * generated before final rendering.
 *
 * WP-40 addendum. This page read `project.draft_video_url`. `ProjectResponse`
 * does not have that field — the live payload's keys are id, name,
 * description, max_runtime_seconds, state, hero_image_url, scene_count,
 * total_duration_estimate_seconds, created_at, updated_at, language_variants,
 * active_job, created_by. It was `undefined` on every project, so this tab
 * showed "No draft preview available yet" **even though the draft exists**:
 * project c12fa967 has `draft_720p_en-US.mp4`, 5.7 MB, sitting in the asset
 * list since 19:24.
 *
 * The draft is an ASSET, so this page now reads the asset list. Note that
 * drafts and final renders share `asset_type: "final_render"` — verified in
 * the workers, `stage7_prototype_draft.py:191` uploads `draft_720p_{lang}.mp4`
 * and `stage8_final_render.py:205` uploads `final_{profile}_{lang}.mp4`, both
 * as `final_render`. The filename prefix is the only discriminator, which is
 * what `assetRenderKind` encodes.
 */

export default function DraftPreviewPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { assets, isLoading, error } = useAssets(projectId);

  const [selectedId, setSelectedId] = useState<string | null>(null);

  /** Every prototype draft this project has, newest first. */
  const drafts = useMemo<Asset[]>(
    () =>
      (assets || [])
        .filter((a: Asset) => assetRenderKind(a) === "draft")
        .sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [assets],
  );

  const active = useMemo<Asset | null>(
    () => drafts.find((d) => d.id === selectedId) ?? drafts[0] ?? null,
    [drafts, selectedId],
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading draft…" />
      </div>
    );
  }

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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Draft Preview
          </h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            720p prototype draft — review before final rendering
          </p>
        </div>
      </div>

      {!active ? (
        <div className="text-center py-16">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gray-100 dark:bg-gray-800 mb-4">
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
                d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
          </div>
          <p className="text-gray-500 dark:text-gray-400 text-lg font-medium">
            No draft preview available yet
          </p>
          <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
            The draft will be generated after the pipeline completes the
            composition stage.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {drafts.length > 1 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Language
              </span>
              {drafts.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedId(d.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                    active.id === d.id
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-gray-300 dark:border-gray-600"
                  }`}
                >
                  {d.language_code || assetFilename(d)}
                </button>
              ))}
            </div>
          )}

          <DraftPlayer asset={active} />
        </div>
      )}
    </div>
  );
}

/**
 * The player itself.
 *
 * `VideoPlayer` takes a `src` string, and the only source available is the
 * authenticated proxy — which a `<video src>` cannot reach, because a browser
 * will not attach the Bearer header. So the bytes are fetched here and passed
 * in as an object URL, and its own download button is switched off in favour
 * of one that saves under the asset's real filename rather than a blob id.
 */
function DraftPlayer({ asset }: { asset: Asset }): React.ReactElement {
  const { url, isLoading, error } = useAssetObjectUrl(asset.id, true);
  const { download, downloadingId, error: downloadError } = useAssetDownload();

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
          <p className="text-sm text-gray-400 px-4 text-center">
            {error
              ? `Could not load the draft: ${error}`
              : isLoading
              ? "Loading draft…"
              : ""}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-t border-gray-300 dark:border-gray-700">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {assetFilename(asset)}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {assetRenderProfile(asset) ?? "draft"} ·{" "}
            {formatBytes(asset.file_size_bytes)}
            {asset.language_code ? ` · ${asset.language_code}` : ""} ·{" "}
            {new Date(asset.created_at).toLocaleString()}
          </p>
        </div>
        <button
          onClick={() => download(asset)}
          disabled={downloadingId === asset.id}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
        >
          {downloadingId === asset.id ? "Downloading…" : "↓ Download"}
        </button>
      </div>

      {downloadError && (
        <p className="px-5 pb-4 text-sm text-red-600 dark:text-red-400">
          Download failed: {downloadError}
        </p>
      )}

      <div className="px-5 py-3 border-t border-gray-300 dark:border-gray-700 text-sm text-gray-500 dark:text-gray-400">
        This is a 720p draft preview. Final renders in 1080p and 4K will be
        available on the Final Renders tab after processing completes.
      </div>
    </div>
  );
}
