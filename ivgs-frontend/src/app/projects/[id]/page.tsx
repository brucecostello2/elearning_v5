"use client";

import React, { useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { useProjects } from "@/hooks/useProjects";
import { useAuth } from "@/hooks/useAuth";
import StateBadge from "@/components/StateBadge";
import PipelineTracker from "@/components/PipelineTracker";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { Project, ProjectState } from "@/types/api";

/**
 * §8.1.3 Project Detail Page (Tabbed Navigation)
 *
 * Table 8-2 defines the following tabs:
 *   - Overview: metadata, state timeline, runtime, pipeline progress
 *   - Transcripts: /projects/[id]/transcript
 *   - Storyboard: (Phase 12)
 *   - Media Assets: /projects/[id]/assets
 *   - Audio: /projects/[id]/audio
 *   - Talking Head: /projects/[id]/talking-head
 *   - Draft Preview: /projects/[id]/draft
 *   - Final Renders: /projects/[id]/renders
 *   - Prompts: (Phase 12)
 *   - Jobs: /projects/[id]/jobs
 *   - Languages: /projects/[id]/languages
 *
 * This page renders the Overview tab inline. Other tabs are linked via
 * Next.js routing to their own page components.
 */

interface TabDefinition {
  id: string;
  label: string;
  href: string;
  inline: boolean;
  minRole?: "admin" | "operator" | "viewer";
  phase?: number;
}

export default function ProjectDetailPage(): React.ReactElement {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const projectId = params.id as string;
  const { project, isLoading, error } = useProjects(projectId);

  const [activeTab, setActiveTab] = useState<string>("overview");

  /**
   * Tab definitions per Table 8-2.
   * Tabs with phase > 11 are placeholders that show "Coming soon".
   */
  const tabs = useMemo<TabDefinition[]>(
    () => [
      {
        id: "overview",
        label: "Overview",
        href: `/projects/${projectId}`,
        inline: true,
      },
      {
        id: "transcripts",
        label: "Transcripts",
        href: `/projects/${projectId}/transcript`,
        inline: false,
      },
      {
        id: "storyboard",
        label: "Storyboard",
        href: `/projects/${projectId}/storyboard`,
        inline: false,
        phase: 12,
      },
      {
        id: "assets",
        label: "Media Assets",
        href: `/projects/${projectId}/assets`,
        inline: false,
      },
      {
        id: "audio",
        label: "Audio",
        href: `/projects/${projectId}/audio`,
        inline: false,
      },
      {
        id: "talking-head",
        label: "Talking Head",
        href: `/projects/${projectId}/talking-head`,
        inline: false,
      },
      {
        id: "draft",
        label: "Draft Preview",
        href: `/projects/${projectId}/draft`,
        inline: false,
      },
      {
        id: "renders",
        label: "Final Renders",
        href: `/projects/${projectId}/renders`,
        inline: false,
      },
      {
        id: "prompts",
        label: "Prompts",
        href: `/projects/${projectId}/prompts`,
        inline: false,
        phase: 12,
      },
      {
        id: "jobs",
        label: "Jobs",
        href: `/projects/${projectId}/jobs`,
        inline: false,
      },
      {
        id: "languages",
        label: "Languages",
        href: `/projects/${projectId}/languages`,
        inline: false,
      },
    ],
    [projectId]
  );

  /** Navigate to a tab — inline tabs stay here, others route to sub-page */
  const handleTabClick = useCallback(
    (tab: TabDefinition): void => {
      if (tab.inline) {
        setActiveTab(tab.id);
      } else {
        router.push(tab.href);
      }
    },
    [router]
  );

  /**
   * Format runtime from seconds to MM:SS display.
   */
  const formatRuntime = useCallback((seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }, []);

  /**
   * Pipeline state timeline: ordered list of state transitions.
   */
  const stateTimeline: { state: ProjectState; label: string; order: number }[] =
    [
      { state: "DRAFT", label: "Draft", order: 1 },
      { state: "IN_PROGRESS", label: "In Progress", order: 2 },
      { state: "REVIEW", label: "Review", order: 3 },
      { state: "COMPLETE", label: "Complete", order: 4 },
    ];

  // ── Loading ─────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" label="Loading project…" />
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────
  if (error || !project) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="text-red-500 dark:text-red-400 text-lg font-semibold">
          {error?.message || "Project not found"}
        </div>
        <button
          onClick={() => router.push("/gallery")}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-600 transition-colors"
        >
          Back to Gallery
        </button>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ── Project Header ───────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between mb-6">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
                {project.name}
              </h1>
              <StateBadge state={project.state} />
            </div>
            {project.description && (
              <p className="text-gray-500 dark:text-gray-400 text-sm max-w-2xl">
                {project.description}
              </p>
            )}
            <div className="flex items-center gap-6 mt-3 text-sm text-gray-500 dark:text-gray-400">
              <span>
                Runtime: {formatRuntime(project.max_runtime_seconds)}
              </span>
              <span>
                Created:{" "}
                {new Date(project.created_at).toLocaleDateString()}
              </span>
              {project.target_languages &&
                project.target_languages.length > 0 && (
                  <span>
                    Languages: {project.target_languages.join(", ").toUpperCase()}
                  </span>
                )}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4 sm:mt-0">
            {project.state === "COMPLETE" && (
              <a
                href={`/player/${project.id}`}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
              >
                ▶ Watch
              </a>
            )}
            <button
              onClick={() => router.push("/gallery")}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-600 hover:text-gray-900 dark:hover:text-white transition-colors text-sm"
            >
              ← Gallery
            </button>
          </div>
        </div>

        {/* ── Tab Navigation per Table 8-2 ─────────────────────────── */}
        <div className="border-b border-gray-300 dark:border-gray-700 mb-8">
          <nav className="flex gap-1 overflow-x-auto pb-px -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab)}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-blue-500 text-blue-600 dark:text-blue-400"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600"
                }`}
              >
                {tab.label}
                {tab.phase && tab.phase > 11 && (
                  <span className="ml-1 text-xs text-gray-600 dark:text-gray-400">(soon)</span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* ── Overview Tab Content ─────────────────────────────────── */}
        {activeTab === "overview" && (
          <div className="space-y-8">
            {/* State Timeline */}
            <section>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Project Timeline
              </h2>
              <div className="flex items-center gap-2">
                {stateTimeline.map((step, idx) => {
                  const currentOrder =
                    project.state === "ERROR"
                      ? -1
                      : stateTimeline.findIndex(
                          (s) => s.state === project.state
                        );
                  const isCompleted = idx <= currentOrder;
                  const isCurrent = idx === currentOrder;

                  return (
                    <React.Fragment key={step.state}>
                      <div className="flex flex-col items-center">
                        <div
                          className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold ${
                            isCompleted
                              ? isCurrent
                                ? "bg-blue-600 text-white ring-4 ring-blue-600/30"
                                : "bg-green-600 text-white"
                              : "bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
                          }`}
                        >
                          {isCompleted && !isCurrent ? "✓" : step.order}
                        </div>
                        <span
                          className={`text-xs mt-1 ${
                            isCompleted ? "text-gray-700 dark:text-gray-300" : "text-gray-600 dark:text-gray-400"
                          }`}
                        >
                          {step.label}
                        </span>
                      </div>
                      {idx < stateTimeline.length - 1 && (
                        <div
                          className={`flex-1 h-0.5 ${
                            idx < currentOrder
                              ? "bg-green-600"
                              : "bg-gray-200 dark:bg-gray-700"
                          }`}
                        />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
              {project.state === "ERROR" && (
                <div className="mt-4 p-3 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400 text-sm">
                  Pipeline encountered an error. Check the Jobs tab for details.
                </div>
              )}
            </section>

            {/* Pipeline Progress Tracker per §8.2.1 */}
            <section>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Pipeline Progress
              </h2>
              <PipelineTracker projectId={projectId} />
            </section>

            {/* Project Metadata */}
            <section>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Project Details
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <MetadataCard
                  label="Video Name"
                  value={project.name}
                />
                <MetadataCard
                  label="Maximum Runtime"
                  value={formatRuntime(project.max_runtime_seconds)}
                />
                <MetadataCard
                  label="Created"
                  value={new Date(project.created_at).toLocaleString()}
                />
                <MetadataCard
                  label="Last Updated"
                  value={new Date(project.updated_at).toLocaleString()}
                />
                <MetadataCard
                  label="Created By"
                  value={project.created_by_name || project.created_by}
                />
                <MetadataCard
                  label="Target Languages"
                  value={
                    project.target_languages?.length
                      ? project.target_languages
                          .map((l: string) => l.toUpperCase())
                          .join(", ")
                      : "None specified"
                  }
                />
              </div>
            </section>

            {/* Quick Links to tabs */}
            <section>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Quick Access
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {tabs
                  .filter((t) => !t.inline && (!t.phase || t.phase <= 11))
                  .map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => handleTabClick(tab)}
                      className="p-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg text-left hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-750 transition-colors"
                    >
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {tab.label}
                      </span>
                    </button>
                  ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}

/**
 * Simple metadata display card for the Overview tab.
 */
function MetadataCard({
  label,
  value,
}: {
  label: string;
  value: string;
}): React.ReactElement {
  return (
    <div className="p-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg">
      <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-gray-900 dark:text-white">{value}</dd>
    </div>
  );
}
