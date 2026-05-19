"use client";

import React, { useState, useMemo, useCallback } from "react";
import { useProjects } from "@/hooks/useProjects";
import { useAuth } from "@/hooks/useAuth";
import ProjectCard from "@/components/ProjectCard";
import ProjectModal from "@/components/ProjectModal";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { Project, ProjectState } from "@/types/api";

/**
 * §8.1.1 Video Gallery (Dashboard Home)
 *
 * Responsive grid of hero image cards, one per project. Each card displays:
 * hero image/thumbnail, video title, short description, runtime estimate,
 * state badge (DRAFT / IN_PROGRESS / REVIEW / COMPLETE / ERROR), and
 * language variant chips. Clicking a card opens the Project Modal.
 *
 * Filtering: by state, by language, and free-text search across name and
 * description. Results are paginated client-side with infinite scroll.
 *
 * RBAC per Table 8-3:
 *   - admin: all projects
 *   - operator: own projects
 *   - viewer: read-only access to all visible projects
 */

/** All possible project states for filter dropdown */
const PROJECT_STATES: ProjectState[] = [
  "DRAFT",
  "IN_PROGRESS",
  "REVIEW",
  "COMPLETE",
  "ERROR",
];

/** Available target languages (ISO 639-1) for filter */
const LANGUAGE_OPTIONS: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "pt", label: "Portuguese" },
  { code: "ja", label: "Japanese" },
  { code: "zh", label: "Chinese" },
  { code: "ko", label: "Korean" },
  { code: "ar", label: "Arabic" },
  { code: "hi", label: "Hindi" },
];

/** Number of projects to show per page (infinite scroll batch) */
const PAGE_SIZE = 24;

export default function GalleryPage(): React.ReactElement {
  // ── Auth & Data ─────────────────────────────────────────────────────
  const { user } = useAuth();
  const { projects, isLoading, error, mutate } = useProjects();

  // ── Filter State ────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [stateFilter, setStateFilter] = useState<ProjectState | "ALL">("ALL");
  const [languageFilter, setLanguageFilter] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "name">("newest");

  // ── Modal State ─────────────────────────────────────────────────────
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  // ── Pagination ──────────────────────────────────────────────────────
  const [visibleCount, setVisibleCount] = useState<number>(PAGE_SIZE);

  /**
   * Filter and sort projects based on current filter state.
   * Admin sees all projects; operator sees only their own per Table 8-3.
   */
  const filteredProjects = useMemo<Project[]>(() => {
    if (!projects) return [];

    let result = [...projects];

    // RBAC filtering: operator sees only own projects
    if (user?.role === "operator") {
      result = result.filter(
        (p: Project) => p.created_by === user.id
      );
    }

    // State filter
    if (stateFilter !== "ALL") {
      result = result.filter(
        (p: Project) => p.state === stateFilter
      );
    }

    // Language filter
    if (languageFilter !== "ALL") {
      result = result.filter((p: Project) =>
        p.target_languages?.includes(languageFilter)
      );
    }

    // Free-text search across name and description
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (p: Project) =>
          p.name.toLowerCase().includes(query) ||
          (p.description?.toLowerCase().includes(query) ?? false)
      );
    }

    // Sort
    switch (sortBy) {
      case "newest":
        result.sort(
          (a, b) =>
            new Date(b.created_at).getTime() -
            new Date(a.created_at).getTime()
        );
        break;
      case "oldest":
        result.sort(
          (a, b) =>
            new Date(a.created_at).getTime() -
            new Date(b.created_at).getTime()
        );
        break;
      case "name":
        result.sort((a, b) => a.name.localeCompare(b.name));
        break;
    }

    return result;
  }, [projects, user, stateFilter, languageFilter, searchQuery, sortBy]);

  /** Visible slice for infinite scroll */
  const visibleProjects = useMemo<Project[]>(
    () => filteredProjects.slice(0, visibleCount),
    [filteredProjects, visibleCount]
  );

  /** Load more projects for infinite scroll */
  const handleLoadMore = useCallback((): void => {
    setVisibleCount((prev) => Math.min(prev + PAGE_SIZE, filteredProjects.length));
  }, [filteredProjects.length]);

  /** Open project modal on card click */
  const handleCardClick = useCallback((project: Project): void => {
    setSelectedProject(project);
    setIsModalOpen(true);
  }, []);

  /** Close project modal */
  const handleCloseModal = useCallback((): void => {
    setIsModalOpen(false);
    setSelectedProject(null);
  }, []);

  /** Reset all filters */
  const handleResetFilters = useCallback((): void => {
    setSearchQuery("");
    setStateFilter("ALL");
    setLanguageFilter("ALL");
    setSortBy("newest");
    setVisibleCount(PAGE_SIZE);
  }, []);

  // ── Loading State ───────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" label="Loading projects…" />
      </div>
    );
  }

  // ── Error State ─────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="text-red-500 text-lg font-semibold">
          Failed to load projects
        </div>
        <p className="text-gray-400 text-sm max-w-md text-center">
          {error.message || "An unexpected error occurred while fetching projects."}
        </p>
        <button
          onClick={() => mutate()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ── Page Header ──────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white">Video Gallery</h1>
            <p className="mt-1 text-gray-400">
              {filteredProjects.length} project
              {filteredProjects.length !== 1 ? "s" : ""}
              {stateFilter !== "ALL" || languageFilter !== "ALL" || searchQuery
                ? " (filtered)"
                : ""}
            </p>
          </div>
          {(user?.role === "admin" || user?.role === "operator") && (
            <a
              href="/projects/new"
              className="mt-4 sm:mt-0 inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              New Project
            </a>
          )}
        </div>

        {/* ── Filter Bar ───────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8 p-4 bg-gray-800 rounded-xl">
          {/* Search */}
          <div className="lg:col-span-2">
            <label
              htmlFor="gallery-search"
              className="block text-xs font-medium text-gray-400 mb-1"
            >
              Search
            </label>
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                id="gallery-search"
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setVisibleCount(PAGE_SIZE);
                }}
                placeholder="Search by name or description…"
                className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* State filter */}
          <div>
            <label
              htmlFor="state-filter"
              className="block text-xs font-medium text-gray-400 mb-1"
            >
              State
            </label>
            <select
              id="state-filter"
              value={stateFilter}
              onChange={(e) => {
                setStateFilter(e.target.value as ProjectState | "ALL");
                setVisibleCount(PAGE_SIZE);
              }}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">All States</option>
              {PROJECT_STATES.map((state) => (
                <option key={state} value={state}>
                  {state.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>

          {/* Language filter */}
          <div>
            <label
              htmlFor="language-filter"
              className="block text-xs font-medium text-gray-400 mb-1"
            >
              Language
            </label>
            <select
              id="language-filter"
              value={languageFilter}
              onChange={(e) => {
                setLanguageFilter(e.target.value);
                setVisibleCount(PAGE_SIZE);
              }}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">All Languages</option>
              {LANGUAGE_OPTIONS.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>

          {/* Sort */}
          <div>
            <label
              htmlFor="sort-select"
              className="block text-xs font-medium text-gray-400 mb-1"
            >
              Sort By
            </label>
            <div className="flex gap-2">
              <select
                id="sort-select"
                value={sortBy}
                onChange={(e) =>
                  setSortBy(e.target.value as "newest" | "oldest" | "name")
                }
                className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="name">Name (A-Z)</option>
              </select>
              <button
                onClick={handleResetFilters}
                title="Reset all filters"
                className="px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-400 hover:text-white hover:border-gray-500 transition-colors"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* ── Project Grid ─────────────────────────────────────────── */}
        {filteredProjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <svg
              className="w-16 h-16 text-gray-600 mb-4"
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
            <p className="text-gray-400 text-lg font-medium">
              No projects found
            </p>
            <p className="text-gray-500 text-sm mt-1">
              {searchQuery || stateFilter !== "ALL" || languageFilter !== "ALL"
                ? "Try adjusting your filters"
                : "Create your first project to get started"}
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {visibleProjects.map((project: Project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onClick={handleCardClick}
                />
              ))}
            </div>

            {/* Load More */}
            {visibleCount < filteredProjects.length && (
              <div className="flex justify-center mt-10">
                <button
                  onClick={handleLoadMore}
                  className="px-8 py-3 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white transition-colors border border-gray-700"
                >
                  Load More ({filteredProjects.length - visibleCount} remaining)
                </button>
              </div>
            )}
          </>
        )}

        {/* ── Project Modal ────────────────────────────────────────── */}
        {isModalOpen && selectedProject && (
          <ProjectModal
            project={selectedProject}
            isOpen={isModalOpen}
            onClose={handleCloseModal}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}
