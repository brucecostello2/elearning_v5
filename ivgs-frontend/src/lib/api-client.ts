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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
  code?: string;
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

  constructor(error: ApiError) {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = error.status;
    this.detail = error.detail;
    this.code = error.code;
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

      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${refreshToken}`,
        },
      });

      if (!response.ok) {
        clearTokens();
        return false;
      }

      const data = (await response.json()) as {
        access_token: string;
        token_type: string;
        expires_in: number;
      };

      setTokens(data.access_token, refreshToken);
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

    throw new ApiRequestError({
      status: response.status,
      message:
        (errorBody["message"] as string) ??
        (errorBody["detail"] as string) ??
        `Request failed with status ${response.status}`,
      detail: errorBody["detail"] as string | undefined,
      code: errorBody["code"] as string | undefined,
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
};
