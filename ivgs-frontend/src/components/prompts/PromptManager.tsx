"use client";

import React, { useState, useMemo, useCallback } from "react";
import type {
  PromptType,
  PromptTier,
  PromptRecord,
} from "@/types/prompts";

/**
 * §9.1 Three-Tier Jinja2 Hierarchy — Prompt Manager
 *
 * Displays all prompt types (Table 9-2) with their current active prompts
 * at the specified tier. Provides navigation between tiers and shows
 * inheritance status:
 *
 * - "Defined" = prompt exists at this tier (green badge)
 * - "Inherited" = no override at this tier, inheriting from parent (gray badge)
 * - "Missing" = no prompt at any tier (red badge)
 *
 * Resolution visualization per §9.1:
 *   Scene override → Project override → Global default (first match used)
 *
 * Actions per row:
 * - Edit: Opens PromptEditor for this prompt type at the current tier
 * - History: Opens PromptHistory for this prompt's version history
 * - Delete: Removes the override at this tier (falls back to parent)
 *
 * @param prompts - Array of prompt records for the current tier
 * @param promptTypes - Metadata for all prompt types
 * @param tier - Current tier being displayed
 * @param canEdit - Whether user can create/edit/delete
 * @param onSelectPromptType - Open editor for a prompt type
 * @param onViewHistory - Open version history for a prompt
 * @param onDeletePrompt - Delete a prompt (optional if no edit permission)
 */

interface PromptManagerProps {
  /** All prompt records for the current tier */
  prompts: PromptRecord[];
  /** Prompt type metadata (from Table 9-2) */
  promptTypes: { value: PromptType; label: string; stage: string }[];
  /** Current tier */
  tier: PromptTier;
  /** Whether user can edit */
  canEdit: boolean;
  /** Open editor for a prompt type */
  onSelectPromptType: (
    promptType: PromptType,
    prompt: PromptRecord | null
  ) => void;
  /** Open version history */
  onViewHistory: (prompt: PromptRecord) => void;
  /** Delete a prompt (undefined if user cannot delete) */
  onDeletePrompt?: (promptId: string) => Promise<void>;
}

/** Tier display metadata */
const TIER_INFO: Record<
  PromptTier,
  { label: string; color: string; description: string }
> = {
  GLOBAL: {
    label: "Global",
    color: "bg-blue-500",
    description: "Base defaults for all projects and scenes",
  },
  PROJECT: {
    label: "Project",
    color: "bg-purple-500",
    description: "Overrides for all scenes within this project",
  },
  SCENE: {
    label: "Scene",
    color: "bg-orange-500",
    description: "Override for this specific scene only",
  },
};

export default function PromptManager({
  prompts,
  promptTypes,
  tier,
  canEdit,
  onSelectPromptType,
  onViewHistory,
  onDeletePrompt,
}: PromptManagerProps): React.ReactElement {
  // ── Search & Filter ──────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [stageFilter, setStageFilter] = useState<string>("ALL");
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  /** Get unique pipeline stages for filter dropdown */
  const stages = useMemo<string[]>(() => {
    const unique = new Set(promptTypes.map((pt) => pt.stage));
    return Array.from(unique);
  }, [promptTypes]);

  /**
   * Build a map of prompt_type -> active prompt record for quick lookup.
   */
  const promptMap = useMemo<Map<PromptType, PromptRecord>>(() => {
    const map = new Map<PromptType, PromptRecord>();
    prompts.forEach((p) => {
      if (p.is_active) {
        map.set(p.prompt_type, p);
      }
    });
    return map;
  }, [prompts]);

  /**
   * Filter prompt types by search and stage.
   */
  const filteredPromptTypes = useMemo(() => {
    let result = [...promptTypes];

    if (stageFilter !== "ALL") {
      result = result.filter((pt) => pt.stage === stageFilter);
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (pt) =>
          pt.label.toLowerCase().includes(query) ||
          pt.value.toLowerCase().includes(query) ||
          pt.stage.toLowerCase().includes(query)
      );
    }

    return result;
  }, [promptTypes, stageFilter, searchQuery]);

  /**
   * Handle prompt deletion with confirmation.
   */
  const handleDelete = useCallback(
    async (promptId: string, promptLabel: string): Promise<void> => {
      if (!onDeletePrompt) return;
      const confirmed = window.confirm(
        `Delete the ${tier.toLowerCase()}-tier "${promptLabel}" prompt? ` +
          `The system will fall back to the parent tier's prompt.`
      );
      if (!confirmed) return;

      setIsDeleting(promptId);
      try {
        await onDeletePrompt(promptId);
      } finally {
        setIsDeleting(null);
      }
    },
    [onDeletePrompt, tier]
  );

  /** Get status badge for a prompt type */
  const getStatusBadge = useCallback(
    (promptType: PromptType): React.ReactElement => {
      const prompt = promptMap.get(promptType);
      if (prompt) {
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-900/30 text-green-400 text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            Defined
          </span>
        );
      }
      if (tier !== "GLOBAL") {
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-700 text-gray-400 text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
            Inherited
          </span>
        );
      }
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-900/30 text-red-400 text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
          Missing
        </span>
      );
    },
    [promptMap, tier]
  );

  return (
    <div className="space-y-4">
      {/* ── Filter Bar ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search prompt types…"
          className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={stageFilter}
          onChange={(e) => setStageFilter(e.target.value)}
          className="px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="ALL">All Stages</option>
          {stages.map((stage) => (
            <option key={stage} value={stage}>
              {stage}
            </option>
          ))}
        </select>
      </div>

      {/* ── Prompt Type Table ───────────────────────────────────── */}
      <div className="overflow-hidden bg-gray-800 rounded-xl border border-gray-700">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-900/50">
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Prompt Type
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Pipeline Stage
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Version
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Updated
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {filteredPromptTypes.map((pt) => {
              const prompt = promptMap.get(pt.value) ?? null;
              return (
                <tr
                  key={pt.value}
                  className="hover:bg-gray-750 transition-colors"
                >
                  {/* Prompt Type */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-white">
                        {pt.label}
                      </span>
                      <span className="text-xs text-gray-500 font-mono">
                        {pt.value}
                      </span>
                    </div>
                  </td>

                  {/* Pipeline Stage */}
                  <td className="px-4 py-3">
                    <span className="text-sm text-gray-300">{pt.stage}</span>
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3">{getStatusBadge(pt.value)}</td>

                  {/* Version */}
                  <td className="px-4 py-3">
                    {prompt ? (
                      <span className="text-sm text-gray-300">
                        v{prompt.version}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-500">—</span>
                    )}
                  </td>

                  {/* Updated */}
                  <td className="px-4 py-3">
                    {prompt?.created_at ? (
                      <span className="text-sm text-gray-400">
                        {new Date(prompt.created_at).toLocaleDateString()}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-500">—</span>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => onSelectPromptType(pt.value, prompt)}
                        className="px-3 py-1 text-xs font-medium text-blue-400 bg-blue-900/20 rounded hover:bg-blue-900/40 transition-colors"
                      >
                        {canEdit
                          ? prompt
                            ? "Edit"
                            : "Create"
                          : "View"}
                      </button>
                      {prompt && (
                        <button
                          onClick={() => onViewHistory(prompt)}
                          className="px-3 py-1 text-xs font-medium text-gray-300 bg-gray-700 rounded hover:bg-gray-600 transition-colors"
                        >
                          History
                        </button>
                      )}
                      {canEdit && prompt && onDeletePrompt && (
                        <button
                          onClick={() => handleDelete(prompt.id, pt.label)}
                          disabled={isDeleting === prompt.id}
                          className="px-3 py-1 text-xs font-medium text-red-400 bg-red-900/20 rounded hover:bg-red-900/40 transition-colors disabled:opacity-50"
                        >
                          {isDeleting === prompt.id ? "…" : "Delete"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Empty filtered state */}
        {filteredPromptTypes.length === 0 && (
          <div className="px-4 py-8 text-center text-gray-500 text-sm">
            No prompt types match the current search or filter.
          </div>
        )}
      </div>

      {/* ── Inheritance Info ─────────────────────────────────────── */}
      <div className="p-4 bg-gray-800/50 rounded-lg border border-gray-700">
        <h3 className="text-sm font-medium text-gray-300 mb-2">
          §9.1 Resolution Order
        </h3>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-orange-500" />
            Scene Override
          </span>
          <svg
            className="w-4 h-4 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-purple-500" />
            Project Override
          </span>
          <svg
            className="w-4 h-4 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-blue-500" />
            Global Default
          </span>
          <span className="ml-2 text-gray-500">
            (first match used)
          </span>
        </div>
      </div>
    </div>
  );
}
