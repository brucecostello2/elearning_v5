"use client";

import React from "react";
import { useParams } from "next/navigation";
import { useProjects } from "@/hooks/useProjects";
import VideoPlayer from "@/components/VideoPlayer";
import LoadingSpinner from "@/components/LoadingSpinner";

/**
 * §8.1.3 Table 8-2 — Draft Preview Tab
 *
 * Embedded video player for 720p prototype draft.
 * This is the low-resolution preview generated before final rendering.
 */

export default function DraftPreviewPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { project, isLoading, error } = useProjects(projectId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading draft…" />
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

  const draftUrl = project.draft_video_url;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Draft Preview</h2>
          <p className="text-gray-400 text-sm mt-1">
            720p prototype draft — review before final rendering
          </p>
        </div>
        <a
          href={`/projects/${projectId}`}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          ← Back
        </a>
      </div>

      {!draftUrl ? (
        <div className="text-center py-16">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gray-800 mb-4">
            <svg
              className="w-10 h-10 text-gray-600"
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
          <p className="text-gray-500 text-lg font-medium">
            No draft preview available yet
          </p>
          <p className="text-gray-600 text-sm mt-1">
            The draft will be generated after the pipeline completes the
            composition stage.
          </p>
        </div>
      ) : (
        <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
          <VideoPlayer
            src={draftUrl}
            qualities={[{ label: "720p", src: draftUrl }]}
            showLanguageSelector={false}
            showSubtitleToggle={false}
            showChapterNav={false}
            showDownload={false}
          />
          <div className="px-5 py-3 border-t border-gray-700 text-sm text-gray-400">
            This is a 720p draft preview. Final renders in 1080p and 4K will
            be available on the Final Renders tab after processing completes.
          </div>
        </div>
      )}
    </div>
  );
}
