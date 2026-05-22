"use client";

import React, { useState, useMemo } from "react";
import { useParams } from "next/navigation";
import { useProjects } from "@/hooks/useProjects";
import VideoPlayer from "@/components/VideoPlayer";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { RenderVariant, VideoQuality } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Final Renders Tab
 *
 * Features:
 *   - Download links for 1080p and 4K MP4
 *   - SRT/VTT captions download
 *   - Language variant selector
 *   - Embedded player for selected variant/quality
 */

export default function RendersPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { project, isLoading, error } = useProjects(projectId);

  const [selectedLanguage, setSelectedLanguage] = useState<string>("en");
  const [selectedQuality, setSelectedQuality] = useState<"1080p" | "4K">(
    "1080p"
  );

  /** Available render variants for this project */
  const variants = useMemo<RenderVariant[]>(
    () => project?.render_variants || [],
    [project]
  );

  /** Get the currently selected variant */
  const activeVariant = useMemo<RenderVariant | undefined>(
    () => variants.find((v) => v.language === selectedLanguage),
    [variants, selectedLanguage]
  );

  /** Available languages from variants */
  const availableLanguages = useMemo<string[]>(
    () => variants.map((v) => v.language ?? v.language_code).filter((l): l is string => !!l),
    [variants]
  );

  /** Video qualities for the player */
  const qualities = useMemo<VideoQuality[]>(() => {
    if (!activeVariant) return [];
    const q: VideoQuality[] = [];
    if (activeVariant.url_1080p) {
      q.push({ label: "1080p", src: activeVariant.url_1080p });
    }
    if (activeVariant.url_4k) {
      q.push({ label: "4K", src: activeVariant.url_4k });
    }
    return q;
  }, [activeVariant]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading renders…" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          {error?.message || "Project not found."}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Final Renders</h2>
          <p className="text-gray-400 text-sm mt-1">
            Download 1080p and 4K renders with captions
          </p>
        </div>
        <a
          href={`/projects/${projectId}`}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          ← Back
        </a>
      </div>

      {variants.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          No final renders available yet. The pipeline must complete before
          renders are generated.
        </div>
      ) : (
        <div className="space-y-6">
          {/* Language & Quality Selectors */}
          <div className="flex flex-col sm:flex-row gap-4 p-4 bg-gray-800 rounded-xl">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Language
              </label>
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {availableLanguages.map((lang) => (
                  <option key={lang} value={lang}>
                    {lang.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Quality
              </label>
              <div className="flex gap-2">
                {(["1080p", "4K"] as const).map((q) => (
                  <button
                    key={q}
                    onClick={() => setSelectedQuality(q)}
                    className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      selectedQuality === q
                        ? "bg-blue-600 text-white"
                        : "bg-gray-700 text-gray-400 hover:text-white"
                    }`}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Video Player */}
          {activeVariant && qualities.length > 0 && (
            <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
              <VideoPlayer
                src={
                  selectedQuality === "4K" && activeVariant.url_4k
                    ? activeVariant.url_4k
                    : activeVariant.url_1080p || ""
                }
                qualities={qualities}
                subtitleUrl={activeVariant.subtitle_vtt_url}
                showLanguageSelector={false}
                showSubtitleToggle={!!activeVariant.subtitle_vtt_url}
                showChapterNav={true}
                showDownload={true}
              />
            </div>
          )}

          {/* Download Links */}
          {activeVariant && (
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-white mb-4">
                Downloads — {selectedLanguage.toUpperCase()}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {activeVariant.url_1080p && (
                  <DownloadLink
                    label="MP4 1080p"
                    url={activeVariant.url_1080p}
                    icon="🎬"
                  />
                )}
                {activeVariant.url_4k && (
                  <DownloadLink
                    label="MP4 4K"
                    url={activeVariant.url_4k}
                    icon="🎬"
                  />
                )}
                {activeVariant.subtitle_srt_url && (
                  <DownloadLink
                    label="SRT Captions"
                    url={activeVariant.subtitle_srt_url}
                    icon="📝"
                  />
                )}
                {activeVariant.subtitle_vtt_url && (
                  <DownloadLink
                    label="VTT Captions"
                    url={activeVariant.subtitle_vtt_url}
                    icon="📝"
                  />
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DownloadLink({
  label,
  url,
  icon,
}: {
  label: string;
  url: string;
  icon: string;
}): React.ReactElement {
  return (
    <a
      href={url}
      download
      className="flex items-center gap-3 p-3 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors group"
    >
      <span className="text-xl">{icon}</span>
      <div className="flex-1 min-w-0">
        <span className="text-sm text-white font-medium group-hover:text-blue-300 transition-colors">
          {label}
        </span>
      </div>
      <svg
        className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors"
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
    </a>
  );
}
