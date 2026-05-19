/*
 * IVGS v5 — Dashboard Home Page
 *
 * Per §8.1.1: Video Gallery is the dashboard home.
 * This page serves as the entry point — content components
 * are implemented in Phase 11.
 *
 * Authentication redirect handled by middleware.ts.
 */

import { redirect } from "next/navigation";

export default function HomePage() {
  /*
   * In Phase 11, this becomes the Video Gallery per §8.1.1:
   * Responsive grid of hero image cards, one per project.
   *
   * For Phase 10 (foundation), display a placeholder that
   * confirms auth is working.
   */
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white">
          Dashboard
        </h1>
        <p className="mt-2 text-sm text-gray-400">
          IVGS v5 — Intelligent Video Generation System
        </p>
      </div>

      {/* Phase 11: VideoGallery component replaces this placeholder */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-12 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-ivgs-900/50">
          <svg
            className="h-8 w-8 text-ivgs-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth="1.5"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"
            />
          </svg>
        </div>
        <h2 className="mt-4 text-lg font-semibold text-white">
          Video Gallery
        </h2>
        <p className="mt-2 text-sm text-gray-400">
          Your projects will appear here. Create a new project to get started.
        </p>
      </div>
    </div>
  );
}
