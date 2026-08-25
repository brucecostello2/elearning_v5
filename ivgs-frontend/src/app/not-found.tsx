import Link from "next/link";

/**
 * WP-43 Task 4 — an honest 404 inside the app's own chrome.
 *
 * This app had no `not-found.tsx`, so any unrouted path fell through to
 * Next's built-in error page. That page styles nothing but its own `<h1>`
 * and inherits everything else from `body` -- which, until this package,
 * painted near-black text on a near-black background in dark mode (see
 * `src/app/layout.tsx`). The result was the black page the operator
 * reported: header visible, content invisible.
 *
 * The specific route that produced it was `/projects/{id}/prompts`, which
 * the Prompts tab linked to and which had no page component. That page now
 * exists. This file is the backstop for the next one: a missing route says
 * so, in readable text, with a way out.
 */
export default function NotFound(): React.ReactElement {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center gap-4 px-6 py-16 text-center">
      <p className="text-sm font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        404
      </p>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        This page does not exist
      </h1>
      <p className="max-w-md text-sm text-gray-600 dark:text-gray-400">
        The address you followed has no page behind it. If you reached this
        from a link inside the dashboard, that link is pointing at a route
        that was never built — worth reporting, because a tab should never
        lead here.
      </p>
      <div className="mt-2 flex items-center gap-3">
        <Link
          href="/gallery"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          Go to Gallery
        </Link>
        <Link
          href="/"
          className="rounded-lg bg-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
        >
          Dashboard
        </Link>
      </div>
    </div>
  );
}
