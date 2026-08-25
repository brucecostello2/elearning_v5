import React from "react";
import ProjectShell from "@/components/project/ProjectShell";

/**
 * WP-43 Task 1 — the shared shell for every `/projects/{id}/*` route.
 *
 * A Next.js segment layout is the mechanism that makes "on every tab"
 * structural rather than a convention each page has to remember: the header,
 * the lifecycle strip and the tab bar are rendered here once, and a page
 * added under this segment inherits them whether or not its author thought
 * about navigation.
 */
export default function ProjectLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return <ProjectShell>{children}</ProjectShell>;
}
