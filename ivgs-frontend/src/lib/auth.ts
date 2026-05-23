/*
 * IVGS v5 — Auth Utilities
 *
 * Per §16.1 Table 16-1:
 * - Access tokens: JWT, HS256, 1-hour expiration
 * - Refresh tokens: JWT, 7-day expiration, stored in Redis
 * - Session storage: Redis-backed
 *
 * Token storage strategy:
 * - Production: httpOnly cookies set by server (prevents XSS)
 * - Development: localStorage fallback (for dev convenience)
 *
 * All /api/v1/* endpoints except /health and /auth/login
 * require Bearer token per §5.3.
 */

import type { UserRole } from "@/types/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACCESS_TOKEN_KEY = "ivgs_access_token";
const REFRESH_TOKEN_KEY = "ivgs_refresh_token";
const COOKIE_MAX_AGE = 86400; // 24h — keep in sync with access-token JWT exp

/**
 * Mirror the access token to a cookie so the Next.js middleware (which runs
 * server-side and cannot read localStorage) can see that the user is
 * authenticated and skip the redirect-to-/login.
 */
function writeAccessCookie(value: string, maxAge: number): void {
  if (typeof document === "undefined") return;
  document.cookie = `${ACCESS_TOKEN_KEY}=${value}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

/* Role hierarchy per §16.2 Table 16-2 */
const ROLE_HIERARCHY: Record<UserRole, number> = {
  admin: 3,
  operator: 2,
  viewer: 1,
};

// ---------------------------------------------------------------------------
// Token Storage
// ---------------------------------------------------------------------------

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(
  accessToken: string,
  refreshToken: string,
): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  writeAccessCookie(accessToken, COOKIE_MAX_AGE);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  writeAccessCookie("", 0);
}

export function hasStoredTokens(): boolean {
  return getAccessToken() !== null;
}

// ---------------------------------------------------------------------------
// Token Parsing
// ---------------------------------------------------------------------------

interface JWTPayload {
  sub: string;
  username: string;
  role: UserRole;
  exp: number;
  iat: number;
}

export function parseJWT(token: string): JWTPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    const payload = parts[1];
    if (!payload) return null;

    const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decoded) as JWTPayload;
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = parseJWT(token);
  if (!payload) return true;

  /* 30-second buffer before actual expiration */
  const expiresAt = payload.exp * 1000;
  return Date.now() > expiresAt - 30_000;
}

export function getUserFromToken(token: string): {
  id: string;
  username: string;
  role: UserRole;
} | null {
  const payload = parseJWT(token);
  if (!payload) return null;

  return {
    id: payload.sub,
    username: payload.username,
    role: payload.role,
  };
}

// ---------------------------------------------------------------------------
// Role Checks
// ---------------------------------------------------------------------------

export function hasMinRole(
  userRole: UserRole,
  requiredRole: UserRole,
): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole];
}

export function isAdmin(role: UserRole): boolean {
  return role === "admin";
}

export function isOperator(role: UserRole): boolean {
  return role === "operator" || role === "admin";
}
