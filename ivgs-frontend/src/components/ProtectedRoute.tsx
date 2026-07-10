/*
 * IVGS v5 — Protected Route Component
 *
 * Per §8.3 Table 8-3: Role-based access control for pages.
 *
 * Roles per §16.2 Table 16-2:
 * - admin:    Full system access
 * - operator: Create/manage own projects, limited monitoring
 * - viewer:   Read-only access to gallery and video player
 *
 * Usage:
 *   <ProtectedRoute minRole="admin">
 *     <AdminPage />
 *   </ProtectedRoute>
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { UserRole } from "@/types/api";

const ROLE_LEVEL: Record<UserRole, number> = {
  admin: 3,
  operator: 2,
  viewer: 1,
};

interface ProtectedRouteProps {
  children: React.ReactNode;
  minRole?: UserRole;
  fallback?: React.ReactNode;
}

export function ProtectedRoute({
  children,
  minRole = "viewer",
  fallback,
}: ProtectedRouteProps) {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  /* Loading state */
  if (isLoading) {
    return (
      fallback ?? (
        <div className="flex min-h-[50vh] items-center justify-center">
          <LoadingSpinner size="lg" />
        </div>
      )
    );
  }

  /* Not authenticated — redirect handled by useEffect */
  if (!isAuthenticated || !user) {
    return null;
  }

  /* Insufficient role */
  if (ROLE_LEVEL[user.role] < ROLE_LEVEL[minRole]) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center px-4">
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20">
            <svg
              className="h-8 w-8 text-red-600 dark:text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M18.364 18.364A9 9 0 0 0 5.636 5.636m12.728 12.728A9 9 0 0 1 5.636 5.636m12.728 12.728L5.636 5.636"
              />
            </svg>
          </div>
          <h2 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">
            Access Denied
          </h2>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            This page requires {minRole} role or higher.
            Your current role is {user.role}.
          </p>
          <button
            onClick={() => router.push("/")}
            className="mt-4 rounded-lg bg-gray-100 dark:bg-gray-800 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
