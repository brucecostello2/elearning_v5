import React from "react";

/**
 * Universal color-coded state badge component.
 *
 * State colors per §8.1.1:
 *   - DRAFT:       gray
 *   - IN_PROGRESS: blue
 *   - REVIEW:      yellow
 *   - COMPLETE:    green
 *   - ERROR/FAILED: red
 *   - PENDING:     gray (dim)
 *   - RUNNING:     blue (pulse)
 */

interface StateBadgeProps {
  state: string;
  size?: "sm" | "md";
}

const STATE_STYLES: Record<string, string> = {
  DRAFT: "bg-gray-700 text-gray-300",
  IN_PROGRESS: "bg-blue-900/40 text-blue-400",
  RUNNING: "bg-blue-900/40 text-blue-400",
  REVIEW: "bg-yellow-900/40 text-yellow-400",
  COMPLETE: "bg-green-900/40 text-green-400",
  COMPLETED: "bg-green-900/40 text-green-400",
  ERROR: "bg-red-900/40 text-red-400",
  FAILED: "bg-red-900/40 text-red-400",
  PENDING: "bg-gray-800 text-gray-500",
  QUEUED: "bg-purple-900/40 text-purple-400",
  CANCELLED: "bg-gray-800 text-gray-500",
};

export default function StateBadge({
  state,
  size = "sm",
}: StateBadgeProps): React.ReactElement {
  const style =
    STATE_STYLES[state.toUpperCase()] || "bg-gray-700 text-gray-400";

  const sizeClass =
    size === "sm"
      ? "px-2 py-0.5 text-[10px]"
      : "px-2.5 py-1 text-xs";

  const isAnimated =
    state.toUpperCase() === "IN_PROGRESS" ||
    state.toUpperCase() === "RUNNING";

  return (
    <span
      className={`inline-flex items-center gap-1 font-semibold rounded-full uppercase tracking-wide ${style} ${sizeClass}`}
    >
      {isAnimated && (
        <span className="w-1.5 h-1.5 bg-current rounded-full animate-pulse" />
      )}
      {state.replace(/_/g, " ")}
    </span>
  );
}
