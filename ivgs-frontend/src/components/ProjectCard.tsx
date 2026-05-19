"use client";

import React from "react";
import StateBadge from "@/components/StateBadge";
import type { Project } from "@/types/api";

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
  const formatRuntime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div
      onClick={() => onClick(project)}
      className="group bg-gray-800 border border-gray-700 rounded-xl overflow-hidden cursor-pointer hover:border-gray-600 hover:shadow-lg hover:shadow-blue-900/10 transition-all duration-200"
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
      <div className="relative aspect-video bg-gray-900 overflow-hidden">
        {project.hero_image_url ? (
          <img
            src={project.hero_image_url}
            alt={`${project.name} hero image`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg
              className="w-12 h-12 text-gray-700"
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
        )}

        {/* Runtime Badge */}
        <div className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 rounded text-xs text-white font-mono">
          {formatRuntime(project.max_runtime_seconds)}
        </div>

        {/* State Badge (top-left) */}
        <div className="absolute top-2 left-2">
          <StateBadge state={project.state} />
        </div>
      </div>

      {/* Card Body */}
      <div className="px-4 py-3">
        <h3 className="text-sm font-semibold text-white truncate group-hover:text-blue-300 transition-colors">
          {project.name}
        </h3>
        {project.description && (
          <p className="text-xs text-gray-400 mt-1 line-clamp-2">
            {project.description}
          </p>
        )}

        {/* Language Chips */}
        {project.target_languages && project.target_languages.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {project.target_languages.slice(0, 5).map((lang: string) => (
              <span
                key={lang}
                className="px-1.5 py-0.5 bg-gray-700 text-gray-400 text-[10px] rounded font-mono uppercase"
              >
                {lang}
              </span>
            ))}
            {project.target_languages.length > 5 && (
              <span className="px-1.5 py-0.5 text-gray-500 text-[10px]">
                +{project.target_languages.length - 5}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
