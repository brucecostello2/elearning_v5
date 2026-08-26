"use client";

import React, { useRef } from "react";
import StateBadge from "@/components/StateBadge";
import type { Project } from "@/types/api";
import { useAssetObjectUrl, useInView } from "@/hooks/useAssetMedia";

/**
 * §8.1.1 Video Gallery — Project Card
 *
 * Each card displays:
 *   - Hero image / thumbnail
 *   - Video title
 *   - Short description
 *   - Runtime estimate
 *   - State badge (DRAFT / IN_PROGRESS / REVIEW / COMPLETE / ERROR)
 *   - Language variant chips
 */

interface ProjectCardProps {
  project: Project;
  onClick: (project: Project) => void;
}

export default function ProjectCard({
  project,
  onClick,
}: ProjectCardProps): React.ReactElement {
  /**
   * Format runtime seconds to MM:SS display.
   */
  /* WP-43: `max_runtime_seconds` is `Optional[int]` on the API and the
     interface now says so. An absent runtime formats as "—" rather than
     "NaN:NaN". */
  const formatRuntime = (seconds: number | null | undefined): string => {
    if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  /* WP-57 Task 1. THE BADGE WAS NOT A DURATION.
     It rendered `max_runtime_seconds`, which is the CEILING the operator typed
     at project creation, not the length of anything. Both populated cards read
     "5:00" because both projects carry the default 300 - a configured target
     presented in the position and format of a measured runtime.
     `total_duration_estimate_seconds` is the honest number and the API already
     sends it: the sum of the storyboard's scene durations. It is an ESTIMATE,
     so the badge says "est" rather than letting it pass for a measurement, and
     a project with no storyboard yet has no estimate to show. */
  const estimate = project.total_duration_estimate_seconds;
  const hasEstimate = typeof estimate === "number" && Number.isFinite(estimate);

  /* Fetch only once the card is on screen: 17 cards must not fire 17 requests
     for thumbnails nobody has scrolled to. */
  const cardRef = useRef<HTMLDivElement>(null);
  const inView = useInView(cardRef);
  const { url: thumbUrl, error: thumbError } = useAssetObjectUrl(
    project.thumbnail_asset_id,
    inView && Boolean(project.thumbnail_asset_id),
    320,
  );

  return (
    <div
      ref={cardRef}
      onClick={() => onClick(project)}
      className="group bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden cursor-pointer hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-lg hover:shadow-blue-900/10 transition-all duration-200"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(project);
        }
      }}
    >
      {/* Hero Image */}
      <div className="relative aspect-video bg-white dark:bg-gray-900 overflow-hidden">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt={`${project.name} preview`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
          />
        ) : (
          /* WP-57 Task 1. THREE DISTINCT STATES, because they were one icon.
             Every card showed the same film-strip glyph whether the project had
             no assets, had one that failed to load, or was still fetching - and
             an icon that means all three means none of them. */
          <div className="w-full h-full flex flex-col items-center justify-center gap-1 px-3 text-center">
            {/* WP-60 Task 4. FOUR STATES, because "Preview failed to load"
                was covering two unrelated facts.
                Two cards showed it permanently — not because the loader
                failed but because their only visual output is an mp4 and
                `/assets/{id}/thumbnail` answers 415 for anything that is not
                an image. That is a property of the project, not a transport
                error, and the reader has no way to act on it while the card
                blames the loader. The API now says which it is. */}
            {thumbError ? (
              <span className="text-[11px] leading-tight text-amber-600 dark:text-amber-400">
                Preview failed to load
              </span>
            ) : project.thumbnail_asset_id ? (
              <span className="text-[11px] leading-tight text-gray-500 dark:text-gray-400">
                Loading preview…
              </span>
            ) : (
              <span
                className="text-[11px] leading-tight text-gray-500 dark:text-gray-400"
                title={project.thumbnail_unavailable_reason ?? undefined}
              >
                {project.thumbnail_unavailable_reason ?? "No render yet"}
              </span>
            )}
          </div>
        )}

        {/* Runtime Badge */}
        <div
          className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 rounded text-xs text-white font-mono"
          title={
            hasEstimate
              ? "Estimated runtime — the sum of this storyboard's scene durations"
              : "No storyboard yet, so there is no runtime to estimate"
          }
        >
          {hasEstimate ? `est ${formatRuntime(estimate)}` : "no estimate"}
        </div>

        {/* State Badge (top-left) */}
        <div className="absolute top-2 left-2">
          <StateBadge state={project.state} />
        </div>
      </div>

      {/* Card Body */}
      <div className="px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate group-hover:text-blue-800 dark:group-hover:text-blue-300 transition-colors">
          {project.name}
        </h3>
        {project.description && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
            {project.description}
          </p>
        )}

        {/* Language Chips */}
        {project.target_languages && project.target_languages.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {project.target_languages.slice(0, 5).map((lang: string) => (
              <span
                key={lang}
                className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-[10px] rounded font-mono uppercase"
              >
                {lang}
              </span>
            ))}
            {project.target_languages.length > 5 && (
              <span className="px-1.5 py-0.5 text-gray-500 dark:text-gray-400 text-[10px]">
                +{project.target_languages.length - 5}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
