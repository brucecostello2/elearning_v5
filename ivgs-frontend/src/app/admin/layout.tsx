"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Sidebar } from "@/components/Sidebar";
import LoadingSpinner from "@/components/LoadingSpinner";

/**
 * Admin Layout — wraps all /admin/* routes with the admin Sidebar.
 *
 * RBAC: Minimum role = admin (per §8.3 Table 8-3).
 * Operators and viewers are redirected to the dashboard.
 *
 * Layout hierarchy:
 *   Root Layout (Header + Footer)
 *     → Admin Layout (Sidebar + Content area)
 *       → Individual admin page (users, backups, retention)
 */
export default function AdminLayout({
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
    /* Only admin role can access admin pages (§8.3 Table 8-3) */
    if (!isLoading && user && user.role !== "admin") {
      router.replace("/");
    }
  }, [isLoading, isAuthenticated, user, router]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading admin..." />
      </div>
    );
  }

  if (user.role !== "admin") {
    return null; /* Will redirect in useEffect */
  }

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)]">
      <Sidebar context="admin" />
      <div className="flex-1 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}
