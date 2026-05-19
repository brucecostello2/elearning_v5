/*
 * IVGS v5 — Type Re-exports and Utility Types
 *
 * Central export point for all TypeScript type definitions.
 * Import from "@/types" instead of "@/types/api" for convenience.
 */

export * from "./api";

// ---------------------------------------------------------------------------
// Utility Types
// ---------------------------------------------------------------------------

/** Make specific properties optional */
export type PartialBy<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/** Make specific properties required */
export type RequiredBy<T, K extends keyof T> = Omit<T, K> &
  Required<Pick<T, K>>;

/** Extract non-nullable type */
export type NonNullableFields<T> = {
  [K in keyof T]: NonNullable<T[K]>;
};

/** State badge color mapping helper type */
export type StateBadgeVariant =
  | "draft"
  | "progress"
  | "review"
  | "complete"
  | "error";

/** Map ProjectState to StateBadgeVariant */
export function getStateBadgeVariant(
  state: import("./api").ProjectState,
): StateBadgeVariant {
  switch (state) {
    case "DRAFT":
      return "draft";
    case "COMPLETE":
      return "complete";
    case "USER_REVIEW":
      return "review";
    case "ERROR":
      return "error";
    default:
      return "progress";
  }
}

/** Format file size for display */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = bytes / Math.pow(1024, i);
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Format duration in seconds to human-readable */
export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}
