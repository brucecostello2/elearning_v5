/*
 * IVGS v5 — API Client
 *
 * Per §5.3: All /api/v1/* endpoints require Bearer token.
 * Tokens are 1-hour JWTs (§16.1 Table 16-1).
 *
 * Features:
 * - Automatic Bearer token injection from auth store
 * - 401 interception → automatic token refresh → retry
 * - Standard error mapping per Table 5-3
 * - Typed response handling
 * - Request/response logging in development
 *
 * Error codes per §5.3 Table 5-3:
 * 400 Bad Request, 401 Unauthorized, 403 Forbidden,
 * 404 Not Found, 409 Conflict, 422 Unprocessable Entity,
 * 500 Internal Server Error
 */

import { getAccessToken, getRefreshToken, setTokens, clearTokens } from "./auth";
import { apiErrorMessage } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
  code?: string;
  /** The parsed error body, so a form can map per-field messages. */
  body?: unknown;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  ok: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// ---------------------------------------------------------------------------
// Error Class
// ---------------------------------------------------------------------------

export class ApiRequestError extends Error {
  status: number;
  detail?: string;
  code?: string;
  /** Parsed response body, kept so callers can call `fieldErrors` on it. */
  body?: unknown;

  constructor(error: ApiError) {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = error.status;
    this.detail = error.detail;
    this.code = error.code;
    this.body = error.body;
  }
}

// ---------------------------------------------------------------------------
// Token Refresh Lock
// ---------------------------------------------------------------------------

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  /* Prevent concurrent refresh requests */
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        return false;
      }

      /*
       * WP-43 Task 6. This used to send the refresh token as an
       * `Authorization` header with NO BODY. `POST /api/v1/auth/refresh`
       * (`ivgs-api/app/api/v1/auth.py:102`) takes `body: RefreshRequest`,
       * a JSON object with a required `refresh_token` field, and ignores
       * the header entirely. FastAPI therefore rejected every refresh
       * before the route ran. Reproduced live 2026-08-25:
       *
       *   POST /api/v1/auth/refresh   (header only, no body)  -> 422
       *   {"detail":[{"type":"missing","loc":["body"],
       *     "msg":"Field required","input":null}]}
       *
       * That is the recurring console 422. Its consequence is the one the
       * operator felt: a refresh never succeeded, so `refreshAccessToken`
       * returned false, `clearTokens()` ran, and the next write went out
       * unauthenticated -- reads that were already cached kept working
       * while writes failed. No API change is needed; the request was
       * simply the wrong shape.
       */
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        clearTokens();
        return false;
      }

      const data = (await response.json()) as {
        access_token: string;
        refresh_token?: string;
        token_type: string;
        expires_in: number;
      };

      /*
       * `TokenResponse` (schemas/auth.py:16) returns a NEW refresh_token and
       * the route's own docstring says "Old refresh token is invalidated
       * after exchange". Re-storing the old one would have made the first
       * refresh succeed and every later one fail -- so the rotation is
       * honoured, with the previous token kept only if the server omits it.
       */
      setTokens(data.access_token, data.refresh_token || refreshToken);
      return true;
    } catch {
      clearTokens();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ---------------------------------------------------------------------------
// Core Fetch Wrapper
// ---------------------------------------------------------------------------

/**
 * Perform an authenticated fetch, transparently refreshing the access token
 * once on a 401 and routing a token-less 403 to the login page.
 *
 * Extracted from `request` (WP-40) so that `blob()` -- which must not parse
 * the body as JSON -- shares exactly the same auth handling. Before this,
 * the Bearer token lived only inside the JSON path, which is why nothing in
 * the app could load a protected binary: `<img src>` cannot carry a header.
 */
async function authedFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const accessToken = getAccessToken();

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  let response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  if (response.status === 401 && accessToken) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      const newToken = getAccessToken();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      response = await fetch(path, {
        ...options,
        headers,
        credentials: "same-origin",
      });
    } else {
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new ApiRequestError({
        status: 401,
        message: "Session expired. Please sign in again.",
      });
    }
  }

  return response;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<ApiResponse<T>> {
  const accessToken = getAccessToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  /* Remove Content-Type for FormData (browser sets boundary) */
  if (options.body instanceof FormData) {
    delete headers["Content-Type"];
  }

  let response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  /* Auto-refresh on 401 */
  if (response.status === 401 && accessToken) {
    const refreshed = await refreshAccessToken();

    if (refreshed) {
      const newToken = getAccessToken();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }

      response = await fetch(path, {
        ...options,
        headers,
        credentials: "same-origin",
      });
    } else {
      /* Refresh failed — redirect to login */
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new ApiRequestError({
        status: 401,
        message: "Session expired. Please sign in again.",
      });
    }
  }

  /* No token at all and the API refused (FastAPI returns 403 for a missing
     bearer): a dead/expired session — send the user to login instead of
     stranding them on an error page. A 403 WITH a token is a real role
     denial and is surfaced normally. */
  if (response.status === 403 && !accessToken) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiRequestError({
      status: 403,
      message: "Not signed in. Please sign in.",
    });
  }

  /* Parse response */
  if (!response.ok) {
    let errorBody: Record<string, unknown> = {};
    try {
      errorBody = (await response.json()) as Record<string, unknown>;
    } catch {
      /* Non-JSON error response */
    }

    /* API errors arrive in several shapes ({"detail": "..."} |
       {"detail": {"error": {"message": "..."}}} | {"error": {...}} |
       FastAPI's own {"detail": [{loc, msg}, ...]} on a 422).
       Rendering a non-string as a React child crashes the page (React #31),
       so always reduce to a string.

       WP-43. The reducer that used to live here skipped ARRAYS, which is
       exactly the shape a 422 always has, so every validation failure in
       the app showed "Request failed with status 422" over a body that
       named the field and the reason. `apiErrorMessage` reads that array
       first and passes the server's `msg` through verbatim; `fieldErrors`
       (`lib/errors.ts`) exposes the same information per field so a form
       can point at the input that is wrong. */
    const message = apiErrorMessage(errorBody, response.status);

    throw new ApiRequestError({
      status: response.status,
      message,
      detail:
        typeof errorBody["detail"] === "string"
          ? (errorBody["detail"] as string)
          : undefined,
      code: errorBody["code"] as string | undefined,
      body: errorBody,
    });
  }

  /* Handle 204 No Content */
  if (response.status === 204) {
    return {
      data: undefined as T,
      status: response.status,
      ok: true,
    };
  }

  const data = (await response.json()) as T;

  return {
    data,
    status: response.status,
    ok: true,
  };
}

// ---------------------------------------------------------------------------
// HTTP Method Helpers
// ---------------------------------------------------------------------------

export const apiClient = {
  get: <T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> => {
    const url = params
      ? `${path}?${new URLSearchParams(params).toString()}`
      : path;
    return request<T>(url, { method: "GET" });
  },

  post: <T>(path: string, body?: unknown, _config?: Record<string, unknown>): Promise<ApiResponse<T>> => {
    return request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  patch: <T>(path: string, body?: unknown): Promise<ApiResponse<T>> => {
    return request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  put: <T>(path: string, body?: unknown): Promise<ApiResponse<T>> => {
    return request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  delete: <T>(path: string): Promise<ApiResponse<T>> => {
    return request<T>(path, { method: "DELETE" });
  },

  upload: <T>(path: string, formData: FormData): Promise<ApiResponse<T>> => {
    return request<T>(path, {
      method: "POST",
      body: formData,
    });
  },

  /**
   * GET a binary body with the Bearer token attached.
   *
   * WP-40 Task 1. Every media route on this API sits behind
   * `Depends(get_service_or_user)`, so the token must travel in a header --
   * and a header is exactly what a browser will not send for `<img src>`,
   * `<video src>` or an `<a download>`. Fetching the bytes here and handing
   * the caller an object URL is the only way a protected asset can be
   * displayed without a new unauthenticated API route.
   *
   * Returns the blob plus the server's own `Content-Type` and the filename
   * from `Content-Disposition`, both of which the download proxy sets.
   */
  blob: async (
    path: string,
  ): Promise<{ blob: Blob; mimeType: string; filename: string | null }> => {
    const response = await authedFetch(path, { method: "GET" });

    if (!response.ok) {
      /* WP-43: the same verbatim treatment as the JSON path. A protected
         media route refusing for a stated reason should say the reason. */
      let body: unknown = null;
      try {
        body = await response.clone().json();
      } catch {
        /* Binary route, non-JSON error body -- fall back to the status. */
      }
      throw new ApiRequestError({
        status: response.status,
        message: apiErrorMessage(body, response.status),
        body,
      });
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") ?? "";
    const match = /filename\*?=(?:UTF-8'')?"?([^\";]+)"?/i.exec(disposition);

    return {
      blob,
      mimeType: response.headers.get("content-type") || blob.type || "",
      filename: match && match[1] ? decodeURIComponent(match[1]) : null,
    };
  },
};
