/**
 * The project tab bar (WP-43 Tasks 1, 2 and 4).
 *
 * WHY THIS EXISTS.
 *
 * Task 1. The tab bar lived inside the Overview PAGE, so it existed on
 * exactly one of the eleven tabs. Every sub-page replaced it with a bare
 * "← Back" link, which made Overview a mandatory waypoint: Transcripts to
 * Audio was three clicks, and no page but Overview ever showed which tab
 * you were on. The list now lives in one module, the shell renders it from
 * `src/app/projects/[id]/layout.tsx`, and it is therefore present on every
 * `/projects/{id}/*` route.
 *
 * Task 2. Two tabs were labelled "(soon)":
 *
 *   - **Storyboard** — labelled "(soon)" while
 *     `src/app/projects/[id]/storyboard/page.tsx` existed, worked, and was
 *     the page WP-38 fixed and WP-40 extended. The label was simply stale.
 *   - **Prompts** — labelled "(soon)" and pointing at
 *     `/projects/{id}/prompts`, which had **no page component at all**.
 *
 * Task 4. That missing Prompts page IS the blank page the operator saw, and
 * it took two defects to look black rather than like a 404:
 *
 *   1. `/projects/{id}/prompts` returns HTTP 404 -- confirmed live
 *      2026-08-25 -- and this app had no `not-found.tsx`, so Next's
 *      built-in error page rendered inside the root layout.
 *   2. That page's text inherits `body`'s colour, and the root layout's
 *      `<body>` className carried CONTRADICTORY dark utilities:
 *      `dark:bg-gray-950 ... dark:bg-gray-50 dark:bg-gray-950
 *      dark:text-gray-100 ... dark:text-gray-900 dark:text-gray-100`.
 *      Tailwind emits by ascending shade, so the LAST rule in the sheet
 *      wins regardless of attribute order. Measured in the deployed bundle
 *      (`/app/.next/static/css/23624bb2737bd75a.css`):
 *      `dark:text-gray-900` at byte 55113 beats `dark:text-gray-100` at
 *      54618, and `dark:bg-gray-950` at 52808 beats `dark:bg-gray-50` at
 *      51982. In dark mode the body therefore painted **rgb(17 24 39) text
 *      on rgb(3 7 18)** -- near-black on near-black.
 *
 *   Every other page sets its own text colours on inner elements, which is
 *   why only the one page that inherits from `body` was invisible.
 *
 * Both are fixed: the Prompts page now exists (the route it reads,
 * `GET /projects/{id}/prompts`, returns ten effective prompts for the
 * reference project), a real `not-found.tsx` renders inside the app chrome,
 * and the body classes no longer contradict themselves.
 *
 * The invariant this module exists to keep: **every tab points at a page
 * that ships.** There is no `phase` field and no "(soon)" any more, because
 * there is nothing left to defer.
 */

export interface ProjectTab {
  /** Stable id, and the URL segment for every tab but Overview. */
  id: string;
  label: string;
  /** Path segment appended to /projects/{id}; empty string = Overview. */
  segment: string;
}

/**
 * Table 8-2 order, with Storyboard and Prompts routed rather than deferred.
 */
export const PROJECT_TABS: readonly ProjectTab[] = [
  { id: "overview", label: "Overview", segment: "" },
  { id: "transcripts", label: "Transcripts", segment: "transcript" },
  { id: "storyboard", label: "Storyboard", segment: "storyboard" },
  /* WP-66. Where a user chooses which model runs each stage. The invariant
     above still holds: this points at a page that ships. */
  { id: "models", label: "Models", segment: "models" },
  { id: "assets", label: "Media Assets", segment: "assets" },
  { id: "audio", label: "Audio", segment: "audio" },
  { id: "talking-head", label: "Talking Head", segment: "talking-head" },
  { id: "draft", label: "Draft Preview", segment: "draft" },
  { id: "renders", label: "Final Renders", segment: "renders" },
  { id: "prompts", label: "Prompts", segment: "prompts" },
  { id: "jobs", label: "Jobs", segment: "jobs" },
  { id: "languages", label: "Languages", segment: "languages" },
];

/** Href for a tab on a given project. */
export function tabHref(projectId: string, tab: ProjectTab): string {
  return tab.segment
    ? `/projects/${projectId}/${tab.segment}`
    : `/projects/${projectId}`;
}

/**
 * Which tab a pathname is on.
 *
 * Matches the segment that follows the project id, so a deeper path such as
 * `/projects/{id}/storyboard/anything` still highlights Storyboard rather
 * than falling back to Overview and telling the operator they are somewhere
 * they are not.
 */
export function activeTabId(pathname: string | null | undefined): string {
  if (typeof pathname !== "string") return "overview";
  const parts = pathname.split("?")[0]!.split("/").filter(Boolean);
  /* ["projects", "<id>", "<segment>", ...] */
  const segment = parts[0] === "projects" ? parts[2] : undefined;
  if (!segment) return "overview";
  const hit = PROJECT_TABS.find((t) => t.segment === segment);
  return hit ? hit.id : "overview";
}
