"use client";

import React, { useState } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import { useModelSelections } from "@/hooks/useModelSelections";
import ModelPicker from "@/components/models/ModelPicker";
import type { ModelTier, SelectionCandidate, StageBinding } from "@/types/models";

/**
 * WP-66 Task 3 — every stage this project will run, and what it is bound to.
 *
 * The stage list is NOT typed out here. It comes from `ModelStage` server-side
 * (`selection_panel._stage_list`), so a stage added to the enum appears here
 * without an edit, and one removed cannot linger as a dead row.
 *
 * TIER IS PRESENTED, NOT HIDDEN. Selections are keyed by (stage, tier), and a
 * user choosing a final-tier model should know that is what they chose.
 */

const TIERS: ModelTier[] = ["production", "prototype"];

export default function ProjectModelsPanel({
  projectId,
}: {
  projectId: string;
}): React.ReactElement {
  const [tier, setTier] = useState<ModelTier>("production");
  const { panel, isLoading, error, select } = useModelSelections(projectId, tier);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const doSelect = async (
    binding: StageBinding,
    candidate: SelectionCandidate,
    rationale: string,
  ): Promise<void> => {
    setNotice(null);
    setFailure(null);
    try {
      setBusy(binding.stage);
      await select({
        stage: binding.stage,
        tier: binding.tier,
        modelId: candidate.id,
        rationale: rationale.trim() || "operator selection",
      });
      setNotice(
        `${binding.stage} is now bound to ${candidate.display_name}. ` +
          `A held draft approval for this project has been re-opened; the ` +
          `storyboard approval is unaffected.`,
      );
    } catch (e) {
      // The API answers 422 with {error:{code,message}} for a refusal -- a
      // message the user can act on, not a generic validation error.
      const detail = (e as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail as
        | { error?: { code?: string; message?: string } }
        | string
        | undefined;
      const message =
        typeof detail === "string"
          ? detail
          : (detail?.error?.message ?? (e as Error).message);
      setFailure(message);
    } finally {
      setBusy(null);
    }
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) {
    return (
      <div className="rounded border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-800 dark:text-red-300">
        Could not load model selections: {error.message}
      </div>
    );
  }
  if (!panel) return <div className="text-sm text-gray-500">No data.</div>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Models
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Which model runs each stage of this project, and where that choice
            came from. A scene can override any of these individually from the
            storyboard editor.
          </p>
        </div>
        <label className="text-sm text-gray-700 dark:text-gray-300">
          Tier{" "}
          <select
            value={tier}
            onChange={(e) => setTier(e.target.value as ModelTier)}
            className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-sm"
            title="Selections are keyed by (stage, tier). Prototype drives the draft; production drives the final render."
          >
            {TIERS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      {notice && (
        <div className="rounded border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 px-3 py-2 text-sm text-green-800 dark:text-green-300">
          {notice}
        </div>
      )}
      {failure && (
        <div className="rounded border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-800 dark:text-red-300">
          {failure}
        </div>
      )}

      <div className="space-y-2">
        {panel.bindings.map((b) => (
          <ModelPicker
            key={`${b.stage}-${b.tier}`}
            binding={b}
            busy={busy === b.stage}
            title={b.stage}
            onSelect={(c, r) => doSelect(b, c, r)}
          />
        ))}
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400">
        Changing a model re-opens a held <strong>draft</strong> approval,
        because the draft is what the models produced. It does{" "}
        <strong>not</strong> re-open the storyboard approval: a model choice does
        not alter narration, visual descriptions or media types, and invalidating
        it would refuse the very regeneration you are choosing a model for.
      </p>
    </div>
  );
}
