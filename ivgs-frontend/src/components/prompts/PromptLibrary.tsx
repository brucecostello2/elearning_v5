"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { usePrompts } from "@/hooks/usePrompts";
import type {
  PromptType,
  PromptLibraryEntry,
  PromptLibraryCategory,
} from "@/types/prompts";

/**
 * §9.5 Prompt Library
 *
 * Administrators can designate frequently used prompt patterns as library
 * templates. Library templates are tagged (e.g., "healthcare",
 * "technical-training", "compliance") and can be applied as the starting
 * point for new global or project prompts.
 *
 * Library entries are stored as inactive prompt versions with a library
 * tag and are not included in the resolution chain until explicitly
 * promoted to active.
 *
 * Features:
 * - Browse library templates by category
 * - Search across template name and content
 * - Preview template content
 * - Apply template as starting point for new prompt
 * - Admin: Add/remove templates from library
 * - Admin: Tag management
 *
 * @param canEdit - Whether user can add/remove library entries
 * @param onApplyTemplate - Apply a template to the editor
 * @param onBack - Navigation callback
 */

/** Predefined library categories per §9.5 */
const LIBRARY_CATEGORIES: PromptLibraryCategory[] = [
  {
    id: "healthcare",
    label: "Healthcare",
    description: "Medical and healthcare training content",
    icon: "🏥",
    color: "bg-red-500/20 text-red-400 border-red-700",
  },
  {
    id: "technical-training",
    label: "Technical Training",
    description: "Software, engineering, and technical skills",
    icon: "⚙️",
    color: "bg-blue-500/20 text-blue-400 border-blue-700",
  },
  {
    id: "compliance",
    label: "Compliance",
    description: "Regulatory, legal, and compliance training",
    icon: "📋",
    color: "bg-yellow-500/20 text-yellow-400 border-yellow-700",
  },
  {
    id: "onboarding",
    label: "Onboarding",
    description: "Employee onboarding and orientation",
    icon: "🎓",
    color: "bg-green-500/20 text-green-400 border-green-700",
  },
  {
    id: "product-demo",
    label: "Product Demo",
    description: "Product demonstrations and walkthroughs",
    icon: "🎬",
    color: "bg-purple-500/20 text-purple-400 border-purple-700",
  },
  {
    id: "safety",
    label: "Safety",
    description: "Workplace and operational safety",
    icon: "⚠️",
    color: "bg-orange-500/20 text-orange-400 border-orange-700",
  },
  {
    id: "general",
    label: "General",
    description: "General-purpose instructional content",
    icon: "📚",
    color: "bg-gray-500/20 text-gray-400 border-gray-700",
  },
];

interface PromptLibraryProps {
  /** Whether user can add/remove library entries */
  canEdit: boolean;
  /** Apply template to editor */
  onApplyTemplate: (templateContent: string, promptType: PromptType) => void;
  /** Back navigation callback */
  onBack: () => void;
}

export default function PromptLibrary({
  canEdit,
  onApplyTemplate,
  onBack,
}: PromptLibraryProps): React.ReactElement {
  // ── Hooks ────────────────────────────────────────────────────────────
  const {
    libraryEntries,
    isLibraryLoading,
    libraryError,
    fetchLibrary,
    removeFromLibrary,
  } = usePrompts({});

  // ── State ────────────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [selectedEntry, setSelectedEntry] =
    useState<PromptLibraryEntry | null>(null);
  const [isRemoving, setIsRemoving] = useState<string | null>(null);

  /** Fetch library on mount */
  useEffect(() => {
    fetchLibrary();
  }, [fetchLibrary]);

  /**
   * Filter library entries by search and category.
   */
  const filteredEntries = useMemo<PromptLibraryEntry[]>(() => {
    if (!Array.isArray(libraryEntries)) return [];

    let result = [...libraryEntries];

    // Category filter — match on prompt_type
    if (selectedCategory !== "ALL") {
      result = result.filter((entry) =>
        entry.prompt_type === selectedCategory
      );
    }

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (entry) =>
          entry.prompt_type.toLowerCase().includes(query) ||
          entry.change_note?.toLowerCase().includes(query) ||
          entry.prompt_text.toLowerCase().includes(query)
      );
    }

    return result;
  }, [libraryEntries, selectedCategory, searchQuery]);

  /**
   * Category counts for badges.
   */
  const categoryCounts = useMemo<Record<string, number>>(() => {
    const counts: Record<string, number> = { ALL: Array.isArray(libraryEntries) ? libraryEntries.length : 0 };
    LIBRARY_CATEGORIES.forEach((cat) => {
      counts[cat.id] =
        (Array.isArray(libraryEntries) ? libraryEntries : []).filter((entry) => entry.prompt_type === cat.id)
          .length ?? 0;
    });
    return counts;
  }, [libraryEntries]);

  /**
   * Handle applying a template.
   */
  const handleApply = useCallback(
    (entry: PromptLibraryEntry): void => {
      onApplyTemplate(entry.prompt_text, entry.prompt_type);
    },
    [onApplyTemplate]
  );

  /**
   * Handle removing from library.
   */
  const handleRemove = useCallback(
    async (entryId: string): Promise<void> => {
      if (!canEdit) return;
      const confirmed = window.confirm(
        "Remove this template from the library? The underlying prompt version will not be deleted."
      );
      if (!confirmed) return;

      setIsRemoving(entryId);
      try {
        await removeFromLibrary(entryId);
        if (selectedEntry?.id === entryId) {
          setSelectedEntry(null);
        }
      } finally {
        setIsRemoving(null);
      }
    },
    [canEdit, removeFromLibrary, selectedEntry]
  );

  // ── Loading ──────────────────────────────────────────────────────────
  if (isLibraryLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500 dark:text-gray-400">
        <span className="text-sm">Loading prompt library…</span>
      </div>
    );
  }

  // ── Error ────────────────────────────────────────────────────────────
  if (libraryError) {
    return (
      <div className="p-4 bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg">
        <p className="text-sm text-red-600 dark:text-red-400">{libraryError}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Category Filter ──────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedCategory("ALL")}
          className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
            selectedCategory === "ALL"
              ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-white border-white/30"
              : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-300 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
          }`}
        >
          All ({categoryCounts.ALL})
        </button>
        {LIBRARY_CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setSelectedCategory(cat.id)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
              selectedCategory === cat.id
                ? cat.color
                : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-300 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
            }`}
          >
            {cat.icon} {cat.label} ({categoryCounts[cat.id] ?? 0})
          </button>
        ))}
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search library templates…"
        className="w-full px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      {/* ── Template Grid ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredEntries.length === 0 ? (
          <div className="col-span-full py-12 text-center text-gray-500 dark:text-gray-400 text-sm">
            No library templates match the current filters.
          </div>
        ) : (
          filteredEntries.map((entry) => (
            <div
              key={entry.id}
              className={`bg-gray-100 dark:bg-gray-800 rounded-xl border p-4 cursor-pointer transition-all ${
                selectedEntry?.id === entry.id
                  ? "border-blue-500 ring-2 ring-blue-500/20"
                  : "border-gray-300 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
              }`}
              onClick={() => setSelectedEntry(entry)}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-2">
                <h4 className="text-sm font-medium text-gray-900 dark:text-white">
                  {entry.prompt_type.replace(/_/g, " ")}
                </h4>
                <span className="text-xs text-gray-500 dark:text-gray-400 font-mono ml-2 whitespace-nowrap">
                  v{entry.version} · {entry.scope}
                </span>
              </div>

              {/* Change note */}
              {entry.change_note && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 line-clamp-2">
                  {entry.change_note}
                </p>
              )}

              {/* Preview snippet */}
              <div className="p-2 bg-white dark:bg-gray-900 rounded text-[10px] text-gray-500 dark:text-gray-400 font-mono max-h-16 overflow-hidden">
                {entry.prompt_text.slice(0, 150)}
                {entry.prompt_text.length > 150 ? "…" : ""}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 mt-3">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleApply(entry);
                  }}
                  className="flex-1 px-2 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/20 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                >
                  Apply
                </button>
                {canEdit && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemove(entry.id);
                    }}
                    disabled={isRemoving === entry.id}
                    className="px-2 py-1.5 text-xs text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/20 rounded hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors disabled:opacity-50"
                  >
                    {isRemoving === entry.id ? "…" : "Remove"}
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Selected Entry Detail ──────────────────────────────── */}
      {selectedEntry && (
        <div className="bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-900/50 border-b border-gray-300 dark:border-gray-700">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white">
              {selectedEntry.prompt_type.replace(/_/g, " ")}
            </h3>
            <button
              onClick={() => setSelectedEntry(null)}
              className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
          <div className="p-4">
            <pre className="text-sm text-gray-800 dark:text-gray-200 font-mono whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
              {selectedEntry.prompt_text}
            </pre>
          </div>
          <div className="px-4 py-3 border-t border-gray-300 dark:border-gray-700 flex items-center justify-end gap-2">
            <button
              onClick={() => handleApply(selectedEntry)}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Apply as Template
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
