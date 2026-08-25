"use client";

import React, { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import StateBadge from "@/components/StateBadge";
import type { Project } from "@/types/api";

/**
 * §8.1.1 Video Gallery — Project Modal
 *
 * Clicking a gallery card opens this modal showing:
 *   - Full description
 *   - Runtime
 *   - Link to Project Detail
 *   - Link to Video Player
 *   - Language variant selector
 */

interface ProjectModalProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
}

export default function ProjectModal({
  project,
  isOpen,
  onClose,
}: ProjectModalProps): React.ReactElement | null {
  const router = useRouter();
  const [selectedLanguage, setSelectedLanguage] = useState<string>("en");

  /** Close on Escape key */
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "";
    };
  }, [isOpen, onClose]);

  const handleNavigateDetail = useCallback((): void => {
    onClose();
    router.push(`/projects/${project.id}`);
  }, [onClose, router, project.id]);

  const handleNavigatePlayer = useCallback((): void => {
    onClose();
    router.push(`/player/${project.id}?lang=${selectedLanguage}`);
  }, [onClose, router, project.id, selectedLanguage]);

  /* WP-43: `max_runtime_seconds` is `Optional[int]` on the API and the
     interface now says so. An absent runtime formats as "—" rather than
     "NaN:NaN". */
  const formatRuntime = (seconds: number | null | undefined): string => {
    if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Hero Image */}
        <div className="relative aspect-video bg-gray-50 dark:bg-gray-950">
          {project.hero_image_url ? (
            <img
              src={project.hero_image_url}
              alt={project.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <svg
                className="w-16 h-16 text-gray-700 dark:text-gray-300"
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
          <div className="absolute top-3 left-3">
            <StateBadge state={project.state} />
          </div>
          <div className="absolute bottom-3 right-3 px-2 py-1 bg-black/70 rounded text-sm text-gray-900 dark:text-white font-mono">
            {formatRuntime(project.max_runtime_seconds)}
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">{project.name}</h2>
          {project.description && (
            <p className="text-gray-500 dark:text-gray-400 text-sm mb-4 leading-relaxed">
              {project.description}
            </p>
          )}

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-3 text-sm mb-4">
            <div>
              <span className="text-gray-500 dark:text-gray-400 text-xs">Created</span>
              <p className="text-gray-700 dark:text-gray-300">
                {new Date(project.created_at).toLocaleDateString()}
              </p>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400 text-xs">Runtime</span>
              <p className="text-gray-700 dark:text-gray-300">
                {formatRuntime(project.max_runtime_seconds)}
              </p>
            </div>
          </div>

          {/* Language Selector */}
          {project.target_languages && project.target_languages.length > 0 && (
            <div className="mb-5">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Language Variant
              </label>
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                className="w-full px-3 py-2 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {project.target_languages.map((lang: string) => (
                  <option key={lang} value={lang}>
                    {lang.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleNavigateDetail}
              className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              View Details
            </button>
            {project.state === "COMPLETE" && (
              <button
                onClick={handleNavigatePlayer}
                className="flex-1 px-4 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
              >
                ▶ Watch
              </button>
            )}
          </div>
        </div>

        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full bg-black/50 text-gray-900 dark:text-white hover:bg-black/70 transition-colors"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
