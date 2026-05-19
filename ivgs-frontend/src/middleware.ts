/*
 * IVGS v5 — Next.js Middleware
 *
 * Auth redirect middleware per §16.1.
 * Runs on every navigation request (not API calls).
 *
 * Protected routes: all except /login, /register, /api/*, /_next/*
 * Unauthenticated users → redirect to /login
 *
 * Note: This is a lightweight check for token presence only.
 * Full JWT validation happens server-side in the API.
 * Client-side AuthContext handles token refresh and validation.
 */

import { NextResponse, type NextRequest } from "next/server";

/* Routes that do not require authentication */
const PUBLIC_PATHS = new Set(["/login", "/register"]);

/* Path prefixes that should not be intercepted */
const SKIP_PREFIXES = ["/_next", "/api", "/favicon.ico"];

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  /* Skip static assets, API routes, and Next.js internals */
  if (SKIP_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  /* Allow public paths */
  if (PUBLIC_PATHS.has(pathname)) {
    return NextResponse.next();
  }

  /*
   * Check for auth token.
   *
   * In production with httpOnly cookies, check the cookie:
   *   const token = request.cookies.get("ivgs_access_token")?.value;
   *
   * For localStorage-based auth (development), the middleware cannot
   * check localStorage (server-side). Instead, rely on client-side
   * AuthContext and ProtectedRoute for enforcement.
   *
   * This middleware serves as a first-pass gate — the client-side
   * auth context provides the authoritative redirect.
   */
  const token = request.cookies.get("ivgs_access_token")?.value;

  /*
   * If no cookie token found, we still allow the request through
   * because the client-side AuthContext (useAuth hook) will handle
   * the redirect for localStorage-based auth flows.
   *
   * In production with httpOnly cookies, uncomment the redirect:
   */
  if (token === undefined && process.env.NODE_ENV === "production") {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
