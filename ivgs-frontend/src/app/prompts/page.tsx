"use client";

import React, { useState, useMemo, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import { usePrompts } from "@/hooks/usePrompts";
import PromptManager from "@/components/prompts/PromptManager";
import PromptEditor from "@/components/prompts/PromptEditor";
import PromptPlayground from "@/components/prompts/PromptPlayground";
import PromptHistory from "@/components/prompts/PromptHistory";
import PromptLibrary from "@/components/prompts/PromptLibrary";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  PromptType,
  PromptTier,
  PromptRecord,
  PromptVersion,
} from "@/types/prompts";

/**
 * §9 Prompt Management System — Global Prompt Management Page
 *
 * This page provides the top-level interface for managing prompts across
 * the entire system. It implements the 3-tier Jinja2 hierarchy described
 * in §9.1 (Table 9-1):
 *
 *   Tier 1 — Global: All projects and scenes, admin only
 *   Tier 2 — Project: All scenes within a project, admin + operator (own)
 *   Tier 3 — Scene: Single scene, admin + operator (own)
 *
 * Resolution order: Scene → Project → Global (first match used).
 *
 * This page shows the GLOBAL tier. Project and scene tiers are accessible
 * from their respective project detail pages.
 *
 * Features:
 * - List all prompt types per Table 9-2
 * - Create / edit global prompt templates
 * - Jinja2 editor with syntax highlighting (Monaco)
 * - Template variable autocomplete per §9.4
 * - Version history with rollback per §9.3
 * - Prompt Library browser per §9.5
 * - Link to Prompt Playground per §8.1.6
 *
 * RBAC per Table 8-3:
 *   - admin: full CRUD on global prompts
 *   - operator: read-only (can view but not edit global prompts)
 *   - viewer: no access
 */

/** All prompt types per Table 9-2 */
const PROMPT_TYPES: { value: PromptType; label: string; stage: string }[] = [
  {
    value: "master",
    label: "Master",
    stage: "All stages",
  },
  {
    value: "transcript_refinement",
    label: "Transcript Refinement",
    stage: "Stage 1",
  },
  {
    value: "storyboard_generation",
    label: "Storyboard Generation",
    stage: "Stage 2",
  },
  {
    value: "image_generation",
    label: "Image Generation",
    stage: "Stage 3",
  },
  {
    value: "video_generation",
    label: "Video Generation",
    stage: "Stage 3",
  },
  {
    value: "animation_generation",
    label: "Animation Generation",
    stage: "Stage 3",
  },
  {
    value: "tts_voice",
    label: "TTS Voice",
    stage: "Stage 5",
  },
  {
    value: "talking_head",
    label: "Talking Head",
    stage: "Stage 6",
  },
  {
    value: "composition",
    label: "Composition",
    stage: "Stages 7–8",
  },
  {
    value: "translation",
    label: "Translation",
    stage: "Localization",
  },
];

/** View modes for the page layout */
type PageView = "manager" | "editor" | "playground" | "history" | "library";

export default function PromptsPage(): React.ReactElement {
  // ── Auth ─────────────────────────────────────────────────────────────
  const { user } = useAuth();

  // ── Data ─────────────────────────────────────────────────────────────
  const {
    prompts,
    isLoading,
    error,
    mutate,
    createPrompt,
    updatePrompt,
    deletePrompt,
    rollbackPrompt,
    getVersionHistory,
  } = usePrompts({ tier: "GLOBAL" });

  // ── View State ──────────────────────────────────────────────────────
  const [currentView, setCurrentView] = useState<PageView>("manager");
  const [selectedPromptType, setSelectedPromptType] =
    useState<PromptType | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptRecord | null>(
    null
  );
  const [selectedVersion, setSelectedVersion] =
    useState<PromptVersion | null>(null);

  /** Whether current user is admin (can edit global prompts) */
  const isAdmin = user?.role === "admin";

  /**
   * Handle prompt type selection from the manager.
   * Opens the editor for the selected prompt type.
   */
  const handleSelectPromptType = useCallback(
    (promptType: PromptType, prompt: PromptRecord | null): void => {
      setSelectedPromptType(promptType);
      setSelectedPrompt(prompt);
      setCurrentView("editor");
    },
    []
  );

  /**
   * Handle prompt save from the editor.
   * Creates or updates the prompt via API.
   */
  const handleSavePrompt = useCallback(
    async (
      promptType: PromptType,
      templateContent: string,
      metadata?: Record<string, unknown>
    ): Promise<void> => {
      if (selectedPrompt) {
        await updatePrompt(selectedPrompt.id, templateContent, metadata);
      } else {
        await createPrompt({
          prompt_type: promptType,
          tier: "GLOBAL" as PromptTier,
          prompt_text: templateContent,
          metadata,
        });
      }
      setCurrentView("manager");
      setSelectedPrompt(null);
      setSelectedPromptType(null);
    },
    [selectedPrompt, updatePrompt, createPrompt]
  );

  /**
   * Handle viewing version history for a prompt.
   */
  const handleViewHistory = useCallback(
    (prompt: PromptRecord): void => {
      setSelectedPrompt(prompt);
      setCurrentView("history");
    },
    []
  );

  /**
   * Handle rollback to a specific version.
   */
  const handleRollback = useCallback(
    async (versionId: string): Promise<void> => {
      if (!selectedPrompt) return;
      await rollbackPrompt(selectedPrompt.id, versionId);
      setCurrentView("manager");
    },
    [selectedPrompt, rollbackPrompt]
  );

  /**
   * Navigate back to the manager view.
   */
  const handleBack = useCallback((): void => {
    setCurrentView("manager");
    setSelectedPrompt(null);
    setSelectedPromptType(null);
    setSelectedVersion(null);
  }, []);

  /**
   * Open playground view.
   */
  const handleOpenPlayground = useCallback((): void => {
    setCurrentView("playground");
  }, []);

  /**
   * Open library view.
   */
  const handleOpenLibrary = useCallback((): void => {
    setCurrentView("library");
  }, []);

  /**
   * Apply a library template to the editor.
   */
  const handleApplyTemplate = useCallback(
    (templateContent: string, promptType: PromptType): void => {
      setSelectedPromptType(promptType);
      setSelectedPrompt(null);
      setCurrentView("editor");
    },
    []
  );

  // ── Access Control ───────────────────────────────────────────────────
  if (user?.role === "viewer") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="text-yellow-500 text-lg font-semibold">
          Access Denied
        </div>
        <p className="text-gray-400 text-sm max-w-md text-center">
          Prompt management is not available for viewer accounts.
          Contact your administrator for access.
        </p>
      </div>
    );
  }

  // ── Loading State ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" label="Loading prompts…" />
      </div>
    );
  }

  // ── Error State ──────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="text-red-500 text-lg font-semibold">
          Failed to load prompts
        </div>
        <p className="text-gray-400 text-sm max-w-md text-center">
          {error.message ||
            "An unexpected error occurred while fetching prompt data."}
        </p>
        <button
          onClick={() => mutate()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ── Page Header ──────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <div className="flex items-center gap-3">
              {currentView !== "manager" && (
                <button
                  onClick={handleBack}
                  className="p-1.5 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
                  aria-label="Back to prompt manager"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 19l-7-7 7-7"
                    />
                  </svg>
                </button>
              )}
              <h1 className="text-3xl font-bold text-white">
                {currentView === "manager" && "Prompt Management"}
                {currentView === "editor" && "Prompt Editor"}
                {currentView === "playground" && "Prompt Playground"}
                {currentView === "history" && "Version History"}
                {currentView === "library" && "Prompt Library"}
              </h1>
            </div>
            <p className="mt-1 text-gray-400">
              {currentView === "manager" &&
                "Manage global prompt templates across all prompt types (§9)"}
              {currentView === "editor" &&
                selectedPromptType &&
                `Editing ${
                  PROMPT_TYPES.find((pt) => pt.value === selectedPromptType)
                    ?.label ?? selectedPromptType
                } prompt template`}
              {currentView === "playground" &&
                "Test prompts against self-hosted models (§8.1.6)"}
              {currentView === "history" &&
                selectedPrompt &&
                `Version history for ${selectedPrompt.prompt_type} prompt`}
              {currentView === "library" &&
                "Browse and apply reusable prompt templates (§9.5)"}
            </p>
          </div>

          {/* Action Buttons */}
          {currentView === "manager" && (
            <div className="mt-4 sm:mt-0 flex items-center gap-3">
              <button
                onClick={handleOpenLibrary}
                className="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
              >
                📚 Library
              </button>
              <button
                onClick={handleOpenPlayground}
                className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition-colors"
              >
                🧪 Playground
              </button>
            </div>
          )}
        </div>

        {/* ── Tier Indicator ───────────────────────────────────────── */}
        {currentView === "manager" && (
          <div className="mb-6 p-3 bg-gray-800 rounded-lg border border-gray-700">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-blue-500" />
                <span className="text-sm font-medium text-white">
                  Global Tier
                </span>
              </div>
              <span className="text-xs text-gray-400">
                §9.1 — Base defaults used when no project or scene override
                exists. Admin only.
              </span>
              {!isAdmin && (
                <span className="ml-auto px-2 py-0.5 bg-yellow-900/30 text-yellow-400 text-xs rounded">
                  Read-only
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── View Content ─────────────────────────────────────────── */}
        {currentView === "manager" && (
          <PromptManager
            prompts={prompts ?? []}
            promptTypes={PROMPT_TYPES}
            tier="GLOBAL"
            canEdit={isAdmin}
            onSelectPromptType={handleSelectPromptType}
            onViewHistory={handleViewHistory}
            onDeletePrompt={isAdmin ? deletePrompt : undefined}
          />
        )}

        {currentView === "editor" && selectedPromptType && (
          <PromptEditor
            promptType={selectedPromptType}
            tier="GLOBAL"
            existingPrompt={selectedPrompt}
            canEdit={isAdmin}
            onSave={handleSavePrompt}
            onCancel={handleBack}
          />
        )}

        {currentView === "playground" && (
          <PromptPlayground onBack={handleBack} />
        )}

        {currentView === "history" && selectedPrompt && (
          <PromptHistory
            prompt={selectedPrompt}
            canRollback={isAdmin}
            onRollback={handleRollback}
            onBack={handleBack}
          />
        )}

        {currentView === "library" && (
          <PromptLibrary
            canEdit={isAdmin}
            onApplyTemplate={handleApplyTemplate}
            onBack={handleBack}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}
