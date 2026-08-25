"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import LoadingSpinner from "@/components/LoadingSpinner";

/**
 * Content Library layout — AD-09.4 / AD-09.5.
 *
 * NOT under /admin, deliberately. The admin layout gates on `role === "admin"`,
 * and the library is an OPERATOR surface: uploading brand media, creating
 * actors and applying presets are day-to-day production work, not
 * administration. Only two actions inside it are admin-gated, and both are
 * gated server-side as well — writing to the `global` scope, and promoting a
 * user asset into it.
 */
export default function LibraryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading library..." />
      </div>
    );
  }

  return <div className="flex-1 overflow-y-auto">{children}</div>;
}
