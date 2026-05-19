/*
 * IVGS v5 — Sidebar Navigation
 *
 * Per §8.0: Sidebar in expanded views: content sections and
 * operational sections based on user role.
 *
 * Context-aware: shows different sections depending on the
 * current page context (project detail, admin, monitoring).
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/types/api";

interface SidebarSection {
  title: string;
  items: SidebarItem[];
  minRole: UserRole;
}

interface SidebarItem {
  label: string;
  href: string;
  badge?: string;
  minRole: UserRole;
}

/* Project detail sidebar — per §8.1.3 Table 8-2 */
const PROJECT_SECTIONS: SidebarSection[] = [
  {
    title: "Content",
    minRole: "viewer",
    items: [
      { label: "Overview", href: "overview", minRole: "viewer" },
      { label: "Transcripts", href: "transcripts", minRole: "viewer" },
      { label: "Storyboard", href: "storyboard", minRole: "viewer" },
      { label: "Media Assets", href: "media", minRole: "viewer" },
      { label: "Audio", href: "audio", minRole: "viewer" },
      { label: "Talking Head", href: "talking-head", minRole: "viewer" },
      { label: "Draft Preview", href: "draft", minRole: "viewer" },
      { label: "Final Renders", href: "renders", minRole: "viewer" },
    ],
  },
  {
    title: "Management",
    minRole: "operator",
    items: [
      { label: "Prompts", href: "prompts", minRole: "operator" },
      { label: "Jobs", href: "jobs", minRole: "operator" },
      { label: "Languages", href: "languages", minRole: "operator" },
    ],
  },
];

/* Admin sidebar — per §8.2 and §8.3 */
const ADMIN_SECTIONS: SidebarSection[] = [
  {
    title: "Monitoring",
    minRole: "operator",
    items: [
      { label: "Pipeline Tracker", href: "/admin/pipeline", minRole: "operator" },
      { label: "GPU Fleet", href: "/admin/gpu", minRole: "operator" },
      { label: "Dead Letter Queue", href: "/admin/dlq", minRole: "admin" },
      { label: "Quality Review", href: "/admin/quality", minRole: "operator" },
    ],
  },
  {
    title: "Operations",
    minRole: "admin",
    items: [
      { label: "Storage Analytics", href: "/admin/storage", minRole: "admin" },
      { label: "User Management", href: "/admin/users", minRole: "admin" },
      { label: "Backup Management", href: "/admin/backups", minRole: "admin" },
      { label: "Retention Policies", href: "/admin/retention", minRole: "admin" },
    ],
  },
];

const ROLE_LEVEL: Record<UserRole, number> = {
  admin: 3,
  operator: 2,
  viewer: 1,
};

function hasAccess(userRole: UserRole, minRole: UserRole): boolean {
  return ROLE_LEVEL[userRole] >= ROLE_LEVEL[minRole];
}

interface SidebarProps {
  context: "project" | "admin";
  projectId?: string;
}

export function Sidebar({ context, projectId }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();

  if (!user) return null;

  const sections =
    context === "project" ? PROJECT_SECTIONS : ADMIN_SECTIONS;

  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 bg-gray-950 py-4">
      {sections
        .filter((section) => hasAccess(user.role, section.minRole))
        .map((section) => (
          <div key={section.title} className="mb-6 px-3">
            <h3 className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
              {section.title}
            </h3>
            <ul className="space-y-0.5">
              {section.items
                .filter((item) => hasAccess(user.role, item.minRole))
                .map((item) => {
                  const fullHref =
                    context === "project" && projectId
                      ? `/projects/${projectId}/${item.href}`
                      : item.href;

                  const isActive = pathname === fullHref ||
                    pathname.startsWith(`${fullHref}/`);

                  return (
                    <li key={item.href}>
                      <Link
                        href={fullHref}
                        className={clsx(
                          "flex items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors",
                          isActive
                            ? "bg-ivgs-600/20 font-medium text-ivgs-300"
                            : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200",
                        )}
                      >
                        <span>{item.label}</span>
                        {item.badge && (
                          <span className="rounded-full bg-ivgs-600/30 px-1.5 py-0.5 text-[10px] font-medium text-ivgs-300">
                            {item.badge}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
            </ul>
          </div>
        ))}
    </aside>
  );
}
