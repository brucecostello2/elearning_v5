/*
 * IVGS v5 — useAuth Hook
 *
 * Convenience hook wrapping AuthContext.
 * Provides: login, logout, user, role, isAuthenticated, isLoading
 *
 * Usage:
 *   const { user, login, logout, isAuthenticated } = useAuth();
 */

"use client";

import { useContext } from "react";
import { AuthContext, type AuthContextValue } from "@/contexts/AuthContext";

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      "useAuth must be used within an AuthProvider. " +
        "Ensure <AuthProvider> wraps your component tree in layout.tsx."
    );
  }

  return context;
}
