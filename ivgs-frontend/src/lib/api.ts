/**
 * IVGS v5 — Centralized API client re-export.
 *
 * Several hooks (useMonitoring, usePrompts, useStoryboard) import
 * `{ api } from "@/lib/api"`.  The underlying implementation lives
 * in `@/lib/api-client` (fetch-based, with automatic JWT refresh).
 *
 * This file re-exports `apiClient` under the name `api` so that
 * both import paths resolve to the same singleton.
 *
 * Usage:
 *   import { api } from "@/lib/api";
 *   const res = await api.get<MyType>("/api/v1/foo");
 *   console.log(res.data);  // typed as MyType
 */
export { apiClient as api } from "./api-client";
export type { ApiResponse, ApiError, PaginatedResponse, ApiRequestError } from "./api-client";
