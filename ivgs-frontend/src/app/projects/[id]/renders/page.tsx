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
 * §8.1.3 Table 8-2 — Final Renders Tab
 *
 * WP-40 addendum. This page read `project.render_variants`, and each variant's
 * `url_1080p`, `url_4k`, `subtitle_srt_url`, `subtitle_vtt_url` and
 * `language`. **None of those exist.** `ProjectResponse` has no
 * `render_variants` at all, and the `language_variants` it does send carry
 * exactly two keys — verified live on project c12fa967:
 *
 *     "language_variants": [{"language_code": "en-US", "state": "pending"},
 *                           {"language_code": "es-ES", "state": "pending"}]
 *
 * So `variants` was always `[]` and this tab said "No final renders available
 * yet" unconditionally — it could never have shown a render, finished or not.
 *
 * Renders are ASSETS. `stage8_final_render.py:205` uploads
 * `final_{profile}_{lang}.mp4` with `asset_type: "final_render"` and
 * `render_profiles = ["1080p", "4k"]` (stage8:103). Drafts use the same
 * asset_type with a `draft_` prefix, which `assetRenderKind` separates so a
 * 720p review draft cannot appear here as a finished render.
 *
 * **Captions are not separate assets.** `stage8_final_render.py:304` composes
 * captions as a `layer_type="caption"` INTO the video; nothing uploads an SRT
 * or VTT file. The two caption download links this page used to render had no
 * possible data source, so they are gone rather than left as dead controls.
 */

export default function RendersPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { assets, isLoading, error } = useAssets(projectId);

  const [selectedLanguage, setSelectedLanguage] = useState<string | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);

  /** Every finished render, newest first. */
  const renders = useMemo<Asset[]>(
    () =>
      (assets || [])
        .filter((a: Asset) => assetRenderKind(a) === "final")
        .sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [assets],
  );

  const languages = useMemo<string[]>(() => {
    const seen: string[] = [];
    for (const r of renders) {
      const lang = r.language_code || "—";
      if (!seen.includes(lang)) seen.push(lang);
    }
    return seen;
  }, [renders]);

  const activeLanguage = selectedLanguage ?? languages[0] ?? null;

  const forLanguage = useMemo<Asset[]>(
    () =>
      renders.filter((r) => (r.language_code || "—") === activeLanguage),
    [renders, activeLanguage],
  );

  const profiles = useMemo<string[]>(() => {
    const seen: string[] = [];
    for (const r of forLanguage) {
      const p = assetRenderProfile(r) ?? "source";
      if (!seen.includes(p)) seen.push(p);
    }
    return seen;
  }, [forLanguage]);

  const activeProfile =
    selectedProfile && profiles.includes(selectedProfile)
      ? selectedProfile
      : profiles[0] ?? null;

  const active = useMemo<Asset | null>(
    () =>
      forLanguage.find(
        (r) => (assetRenderProfile(r) ?? "source") === activeProfile,
      ) ?? null,
    [forLanguage, activeProfile],
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading renders…" />
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
            Final Renders
          </h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            Download finished renders per language and quality
          </p>
        </div>
      </div>

      {renders.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          <p>No final renders available yet.</p>
          <p className="text-sm mt-1">
            The pipeline must reach the final render stage. A 720p prototype
            draft, if one exists, is on the Draft Preview tab.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Language & Quality Selectors */}
          <div className="flex flex-col sm:flex-row gap-4 p-4 bg-gray-100 dark:bg-gray-800 rounded-xl">
            <div className="flex-1">
              <label
                htmlFor="render-language"
                className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
              >
                Language
              </label>
              <select
                id="render-language"
                value={activeLanguage ?? ""}
                onChange={(e) => {
                  setSelectedLanguage(e.target.value);
                  setSelectedProfile(null);
                }}
                className="w-full px-3 py-2 bg-gray-200 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {languages.map((lang) => (
                  <option key={lang} value={lang}>
                    {lang.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Quality
              </span>
              <div className="flex gap-2">
                {/* Only the profiles this project actually rendered. The old
                    tabs offered a fixed 1080p / 4K pair regardless. */}
                {profiles.map((p) => (
                  <button
                    key={p}
                    onClick={() => setSelectedProfile(p)}
                    className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      activeProfile === p
                        ? "bg-blue-600 text-white"
                        : "bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-white"
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {active && <RenderPlayer asset={active} />}

          {/* Downloads — every render for this language */}
          <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">
              Downloads — {(activeLanguage ?? "").toUpperCase()}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {forLanguage.map((r) => (
                <DownloadRow key={r.id} asset={r} />
              ))}
            </div>
            <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
              Captions are burned into the video by the composition stage; this
              pipeline does not produce separate SRT or VTT files.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Player for the selected render, loaded through the authenticated proxy. */
function RenderPlayer({ asset }: { asset: Asset }): React.ReactElement {
  const { url, isLoading, error } = useAssetObjectUrl(asset.id, true);

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
              ? `Could not load this render: ${error}`
              : isLoading
              ? "Loading render…"
              : ""}
          </p>
        )}
      </div>
      <div className="px-5 py-3 text-xs text-gray-500 dark:text-gray-400">
        {assetFilename(asset)} · {assetRenderProfile(asset) ?? "source"} ·{" "}
        {formatBytes(asset.file_size_bytes)} ·{" "}
        {new Date(asset.created_at).toLocaleString()}
      </div>
    </div>
  );
}

/**
 * One download row.
 *
 * Not an `<a download href>` — the proxy needs a Bearer header, so the bytes
 * are fetched and saved under the server's own Content-Disposition filename.
 */
function DownloadRow({ asset }: { asset: Asset }): React.ReactElement {
  const { download, downloadingId, error } = useAssetDownload();
  const busy = downloadingId === asset.id;

  return (
    <button
      onClick={() => download(asset)}
      disabled={busy}
      className="flex items-center gap-3 p-3 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-600 disabled:opacity-50 transition-colors group text-left"
    >
      <span className="text-xl">🎬</span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm text-gray-900 dark:text-white font-medium truncate group-hover:text-blue-800 dark:group-hover:text-blue-300 transition-colors">
          {busy ? "Downloading…" : `MP4 ${assetRenderProfile(asset) ?? "source"}`}
        </span>
        <span className="block text-xs text-gray-600 dark:text-gray-400 truncate">
          {error ? error : `${assetFilename(asset)} · ${formatBytes(asset.file_size_bytes)}`}
        </span>
      </span>
      <svg
        className="w-4 h-4 text-gray-500 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
        />
      </svg>
    </button>
  );
}
