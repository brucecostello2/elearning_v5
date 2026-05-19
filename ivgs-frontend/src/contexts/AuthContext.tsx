/*
 * IVGS v5 — Auth Context Provider
 *
 * Per §16.1: JWT-based authentication with auto-refresh.
 * - Access tokens: 1-hour expiration
 * - Refresh tokens: 7-day expiration, stored in Redis
 *
 * Context provides:
 * - user: Current authenticated user (id, username, role)
 * - isAuthenticated: Boolean auth state
 * - isLoading: Initial auth check in progress
 * - login(username, password): Authenticate and store tokens
 * - logout(): Clear tokens and redirect
 *
 * Token refresh: Background timer checks token expiration every 60s.
 * On approaching expiration (< 5 min), auto-refreshes silently.
 */

"use client";

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  getUserFromToken,
  isTokenExpired,
  parseJWT,
  setTokens,
} from "@/lib/auth";
import type { UserRole } from "@/types/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AuthUser {
  id: string;
  username: string;
  role: UserRole;
}

interface LoginResult {
  success: boolean;
  error?: string;
  remainingAttempts?: number;
}

export interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  /* ------------------------------------------------------------------ */
  /* Initialize auth state from stored tokens                            */
  /* ------------------------------------------------------------------ */

  useEffect(() => {
    const token = getAccessToken();

    if (token && !isTokenExpired(token)) {
      const userData = getUserFromToken(token);
      if (userData) {
        setUser(userData);
      }
    } else if (token && isTokenExpired(token)) {
      /* Token expired — attempt refresh */
      void refreshToken();
    }

    setIsLoading(false);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ------------------------------------------------------------------ */
  /* Auto-refresh timer                                                  */
  /* ------------------------------------------------------------------ */

  useEffect(() => {
    const interval = setInterval(() => {
      const token = getAccessToken();
      if (!token) return;

      const payload = parseJWT(token);
      if (!payload) return;

      /* Refresh if < 5 minutes until expiration */
      const timeToExpiry = payload.exp * 1000 - Date.now();
      if (timeToExpiry < 300_000 && timeToExpiry > 0) {
        void refreshToken();
      }
    }, 60_000); /* Check every 60 seconds */

    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ------------------------------------------------------------------ */
  /* Token Refresh                                                       */
  /* ------------------------------------------------------------------ */

  const refreshToken = useCallback(async (): Promise<boolean> => {
    const refresh = getRefreshToken();
    if (!refresh) {
      setUser(null);
      return false;
    }

    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${refresh}`,
        },
      });

      if (!response.ok) {
        clearTokens();
        setUser(null);
        return false;
      }

      const data = (await response.json()) as {
        access_token: string;
        token_type: string;
        expires_in: number;
      };

      setTokens(data.access_token, refresh);
      const userData = getUserFromToken(data.access_token);
      if (userData) {
        setUser(userData);
      }
      return true;
    } catch {
      clearTokens();
      setUser(null);
      return false;
    }
  }, []);

  /* ------------------------------------------------------------------ */
  /* Login                                                               */
  /* ------------------------------------------------------------------ */

  const login = useCallback(
    async (username: string, password: string): Promise<LoginResult> => {
      try {
        const response = await fetch("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });

        if (!response.ok) {
          const errorData = (await response.json().catch(() => ({}))) as Record<
            string,
            unknown
          >;

          return {
            success: false,
            error:
              (errorData["message"] as string) ??
              (errorData["detail"] as string) ??
              "Authentication failed",
            remainingAttempts: errorData["remaining_attempts"] as
              | number
              | undefined,
          };
        }

        const data = (await response.json()) as {
          access_token: string;
          refresh_token: string;
          token_type: string;
          expires_in: number;
        };

        setTokens(data.access_token, data.refresh_token);
        const userData = getUserFromToken(data.access_token);
        if (userData) {
          setUser(userData);
        }

        return { success: true };
      } catch (err) {
        return {
          success: false,
          error:
            err instanceof Error
              ? err.message
              : "Network error. Please try again.",
        };
      }
    },
    [],
  );

  /* ------------------------------------------------------------------ */
  /* Logout                                                              */
  /* ------------------------------------------------------------------ */

  const logout = useCallback(async (): Promise<void> => {
    try {
      const token = getAccessToken();
      if (token) {
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => {
          /* Logout API failure is non-critical */
        });
      }
    } finally {
      clearTokens();
      setUser(null);
      router.push("/login");
    }
  }, [router]);

  /* ------------------------------------------------------------------ */
  /* Context Value                                                       */
  /* ------------------------------------------------------------------ */

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: user !== null,
      isLoading,
      login,
      logout,
    }),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
