"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Sidebar } from "@/components/Sidebar";
import LoadingSpinner from "@/components/LoadingSpinner";

/**
 * Monitoring Layout — wraps all /monitoring/* routes with the monitoring Sidebar.
 *
 * RBAC: Minimum role = operator (per §8.3 Table 8-3).
 * - Admin: full access to all monitoring views
 * - Operator: access to pipeline, GPU, quality (read-only)
 * - Viewer: redirected to dashboard
 *
 * Layout hierarchy:
 *   Root Layout (Header + Footer)
 *     → Monitoring Layout (Sidebar + Content area)
 *       → Individual monitoring page
 */
export default function MonitoringLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
      return;
    }
    /* Viewers have no access to monitoring pages (§8.3 Table 8-3) */
    if (!isLoading && user && user.role === "viewer") {
      router.replace("/");
    }
  }, [isLoading, isAuthenticated, user, router]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading monitoring..." />
      </div>
    );
  }

  if (user.role === "viewer") {
    return null; /* Will redirect in useEffect */
  }

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)]">
      <Sidebar context="monitoring" />
      <div className="flex-1 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}
