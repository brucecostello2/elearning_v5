"use client";

import React, { useState, useCallback, useMemo, useEffect } from "react";
import { usePrompts } from "@/hooks/usePrompts";
import type { PromptRecord, PromptVersion } from "@/types/prompts";

/**
 * §9.3 Prompt Versioning — Version History & Rollback
 *
 * Every edit creates a new version record. Previous versions are retained
 * and never deleted. Users can view the full version history and roll back
 * with a single click. The is_active = true flag marks the active version;
 * only one version may be active per prompt_type per scope at any time.
 *
 * Features:
 * - Chronological list of all versions (newest first)
 * - Active version highlighted
 * - Version metadata: number, timestamp, author, description
 * - Unified diff view between any two versions
 * - One-click rollback to any previous version
 * - Full template content view per version
 *
 * @param prompt - The prompt record to show history for
 * @param canRollback - Whether user can perform rollback
 * @param onRollback - Rollback callback (versionId)
 * @param onBack - Navigation callback
 */

interface PromptHistoryProps {
  /** Prompt record to show history for */
  prompt: PromptRecord;
  /** Whether user can rollback */
  canRollback: boolean;
  /** Rollback callback */
  onRollback: (versionId: string) => Promise<void>;
  /** Back navigation callback */
  onBack: () => void;
}

/**
 * Simple unified diff implementation for text comparison.
 * Produces a line-by-line diff with + / - / (space) markers.
 */
function computeUnifiedDiff(
  oldText: string,
  newText: string
): { type: "add" | "remove" | "same"; content: string }[] {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const diff: { type: "add" | "remove" | "same"; content: string }[] = [];

  // Simple LCS-based diff
  const maxLen = Math.max(oldLines.length, newLines.length);
  let oldIdx = 0;
  let newIdx = 0;

  // Build a simple diff using longest common subsequence approach
  // For readability we use a simplified two-pointer approach
  const lcs = new Map<string, number[]>();

  // Index old lines by content for O(n) matching
  oldLines.forEach((line, idx) => {
    if (!lcs.has(line)) {
      lcs.set(line, []);
    }
    lcs.get(line)!.push(idx);
  });

  // Walk through new lines and match against old
  const matched = new Set<number>();
  const newMatched = new Map<number, number>();

  newLines.forEach((line, newI) => {
    const oldIndices = lcs.get(line);
    if (oldIndices) {
      for (const oldI of oldIndices) {
        if (!matched.has(oldI)) {
          matched.add(oldI);
          newMatched.set(newI, oldI);
          break;
        }
      }
    }
  });

  // Generate diff output
  oldIdx = 0;
  newIdx = 0;

  while (oldIdx < oldLines.length || newIdx < newLines.length) {
    if (newIdx < newLines.length && newMatched.has(newIdx)) {
      const matchedOldIdx = newMatched.get(newIdx)!;

      // Output removed lines before the match
      while (oldIdx < matchedOldIdx) {
        diff.push({ type: "remove", content: oldLines[oldIdx] });
        oldIdx++;
      }

      // Output the matched line
      diff.push({ type: "same", content: newLines[newIdx] });
      oldIdx = matchedOldIdx + 1;
      newIdx++;
    } else if (newIdx < newLines.length) {
      diff.push({ type: "add", content: newLines[newIdx] });
      newIdx++;
    } else if (oldIdx < oldLines.length) {
      diff.push({ type: "remove", content: oldLines[oldIdx] });
      oldIdx++;
    }
  }

  return diff;
}

export default function PromptHistory({
  prompt,
  canRollback,
  onRollback,
  onBack,
}: PromptHistoryProps): React.ReactElement {
  // ── Hooks ────────────────────────────────────────────────────────────
  const { getVersionHistory } = usePrompts({});

  // ── State ────────────────────────────────────────────────────────────
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    null
  );
  const [compareVersionId, setCompareVersionId] = useState<string | null>(
    null
  );
  const [isRollingBack, setIsRollingBack] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "diff" | "content">(
    "list"
  );

  /** Fetch version history on mount */
  useEffect(() => {
    let cancelled = false;

    async function fetchHistory(): Promise<void> {
      setIsLoading(true);
      setError(null);
      try {
        const history = await getVersionHistory(prompt.id);
        if (!cancelled) {
          setVersions(history);
          // Auto-select the active version
          const activeVersion = history.find((v) => v.is_active);
          if (activeVersion) {
            setSelectedVersionId(activeVersion.id);
          }
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const message =
            err instanceof Error
              ? err.message
              : "Failed to load version history";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchHistory();
    return () => {
      cancelled = true;
    };
  }, [prompt.id, getVersionHistory]);

  /** Get currently selected version */
  const selectedVersion = useMemo<PromptVersion | null>(
    () => versions.find((v) => v.id === selectedVersionId) ?? null,
    [versions, selectedVersionId]
  );

  /** Get comparison version */
  const compareVersion = useMemo<PromptVersion | null>(
    () => versions.find((v) => v.id === compareVersionId) ?? null,
    [versions, compareVersionId]
  );

  /** Compute diff between selected and compare versions */
  const diff = useMemo(() => {
    if (!selectedVersion || !compareVersion) return null;
    return computeUnifiedDiff(
      compareVersion.template_content,
      selectedVersion.template_content
    );
  }, [selectedVersion, compareVersion]);

  /**
   * Handle rollback action.
   */
  const handleRollback = useCallback(
    async (versionId: string): Promise<void> => {
      if (!canRollback || isRollingBack) return;
      const version = versions.find((v) => v.id === versionId);
      if (!version) return;

      const confirmed = window.confirm(
        `Roll back to version ${version.version_number}? ` +
          `This will create a new version with the content from v${version.version_number}.`
      );
      if (!confirmed) return;

      setIsRollingBack(versionId);
      try {
        await onRollback(versionId);
      } catch (err: unknown) {
        console.error("[PromptHistory] Rollback failed:", err);
      } finally {
        setIsRollingBack(null);
      }
    },
    [canRollback, isRollingBack, versions, onRollback]
  );

  /**
   * Select a version to compare against.
   */
  const handleCompare = useCallback(
    (versionId: string): void => {
      setCompareVersionId(versionId);
      setViewMode("diff");
    },
    []
  );

  /**
   * View full content of a version.
   */
  const handleViewContent = useCallback((versionId: string): void => {
    setSelectedVersionId(versionId);
    setViewMode("content");
  }, []);

  /** Format timestamp */
  const formatTimestamp = (ts: string): string => {
    return new Date(ts).toLocaleString();
  };

  // ── Loading State ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="flex items-center gap-2 text-gray-400">
          <svg
            className="w-5 h-5 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="text-sm">Loading version history…</span>
        </div>
      </div>
    );
  }

  // ── Error State ──────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="p-4 bg-red-900/20 border border-red-700 rounded-lg">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Prompt Info ──────────────────────────────────────────── */}
      <div className="p-4 bg-gray-800 rounded-xl border border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-white">
              {prompt.prompt_type}
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Tier: {prompt.tier} · {versions.length} version
              {versions.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setViewMode("list")}
              className={`px-3 py-1.5 text-xs rounded ${
                viewMode === "list"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 text-gray-300"
              }`}
            >
              List
            </button>
            {selectedVersion && compareVersion && (
              <button
                onClick={() => setViewMode("diff")}
                className={`px-3 py-1.5 text-xs rounded ${
                  viewMode === "diff"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-700 text-gray-300"
                }`}
              >
                Diff
              </button>
            )}
            {selectedVersion && (
              <button
                onClick={() => setViewMode("content")}
                className={`px-3 py-1.5 text-xs rounded ${
                  viewMode === "content"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-700 text-gray-300"
                }`}
              >
                Content
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── List View ───────────────────────────────────────────── */}
      {viewMode === "list" && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <div className="divide-y divide-gray-700">
            {versions.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500 text-sm">
                No versions found for this prompt.
              </div>
            ) : (
              versions.map((version) => (
                <div
                  key={version.id}
                  className={`px-4 py-3 hover:bg-gray-750 transition-colors ${
                    version.is_active
                      ? "border-l-2 border-l-green-500 bg-green-900/5"
                      : ""
                  } ${
                    selectedVersionId === version.id
                      ? "bg-blue-900/10"
                      : ""
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">
                        v{version.version_number}
                      </span>
                      {version.is_active && (
                        <span className="px-1.5 py-0.5 bg-green-900/30 text-green-400 text-[10px] rounded-full font-medium">
                          Active
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-500">
                      {formatTimestamp(version.created_at)}
                    </span>
                  </div>

                  {version.change_description && (
                    <p className="text-xs text-gray-400 mb-2">
                      {version.change_description}
                    </p>
                  )}

                  {version.created_by_name && (
                    <p className="text-[10px] text-gray-500 mb-2">
                      by {version.created_by_name}
                    </p>
                  )}

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleViewContent(version.id)}
                      className="px-2 py-1 text-[10px] text-blue-400 bg-blue-900/20 rounded hover:bg-blue-900/40 transition-colors"
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleCompare(version.id)}
                      disabled={!selectedVersionId || selectedVersionId === version.id}
                      className="px-2 py-1 text-[10px] text-gray-300 bg-gray-700 rounded hover:bg-gray-600 transition-colors disabled:opacity-30"
                    >
                      Compare
                    </button>
                    {canRollback && !version.is_active && (
                      <button
                        onClick={() => handleRollback(version.id)}
                        disabled={isRollingBack === version.id}
                        className="px-2 py-1 text-[10px] text-yellow-400 bg-yellow-900/20 rounded hover:bg-yellow-900/40 transition-colors disabled:opacity-50"
                      >
                        {isRollingBack === version.id
                          ? "Rolling back…"
                          : "Rollback"}
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── Diff View ───────────────────────────────────────────── */}
      {viewMode === "diff" && diff && selectedVersion && compareVersion && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 bg-gray-900/50 border-b border-gray-700">
            <div className="flex items-center gap-3 text-xs">
              <span className="text-red-400">
                − v{compareVersion.version_number}
              </span>
              <span className="text-gray-500">→</span>
              <span className="text-green-400">
                + v{selectedVersion.version_number}
              </span>
            </div>
          </div>
          <div className="p-4 max-h-96 overflow-y-auto">
            <pre className="text-xs font-mono leading-relaxed">
              {diff.map((line, i) => (
                <div
                  key={i}
                  className={`px-2 py-0.5 ${
                    line.type === "add"
                      ? "bg-green-900/20 text-green-300"
                      : line.type === "remove"
                      ? "bg-red-900/20 text-red-300"
                      : "text-gray-400"
                  }`}
                >
                  <span className="inline-block w-4 text-gray-600">
                    {line.type === "add"
                      ? "+"
                      : line.type === "remove"
                      ? "−"
                      : " "}
                  </span>
                  {line.content}
                </div>
              ))}
            </pre>
          </div>
        </div>
      )}

      {/* ── Content View ────────────────────────────────────────── */}
      {viewMode === "content" && selectedVersion && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 bg-gray-900/50 border-b border-gray-700">
            <span className="text-xs text-gray-400">
              v{selectedVersion.version_number} — Full Content
            </span>
            <span className="text-xs text-gray-500">
              {selectedVersion.template_content.length} chars ·{" "}
              {selectedVersion.template_content.split("\n").length} lines
            </span>
          </div>
          <div className="p-4 max-h-96 overflow-y-auto">
            <pre className="text-sm text-gray-200 font-mono whitespace-pre-wrap leading-relaxed">
              {selectedVersion.template_content}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
