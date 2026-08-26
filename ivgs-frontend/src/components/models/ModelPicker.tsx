"use client";

import React, { useState } from "react";
import type { SelectionCandidate, StageBinding } from "@/types/models";

/**
 * WP-66 — one model picker, used at both scopes.
 *
 * WHY UNAVAILABLE MODELS ARE SHOWN AND DISABLED RATHER THAN FILTERED OUT.
 * A user who cannot see the model they expected has no way to learn why, and
 * reports "the picker is broken" instead of "the weights are not fetched". The
 * three absences WP-65 made distinct in the Model Store need to stay distinct
 * here, because each needs a different person to do a different thing.
 *
 * `selectable` is computed SERVER-side by the same function `PUT /selections`
 * uses, so this component never decides eligibility itself. A picker that
 * offers what the write refuses -- or greys out what it would accept -- is
 * worse than no picker.
 */

const PROVENANCE_STYLE: Record<string, string> = {
  scene: "bg-purple-900/50 text-purple-300 border border-purple-800",
  selection: "bg-blue-900/50 text-blue-300 border border-blue-800",
  preset: "bg-teal-900/50 text-teal-300 border border-teal-800",
  auto: "bg-indigo-900/50 text-indigo-300 border border-indigo-800",
  default: "bg-gray-700/50 text-gray-300 border border-gray-600",
  none: "bg-red-900/50 text-red-300 border border-red-800",
};

export function ProvenanceBadge({
  provenance,
  label,
}: {
  provenance: string;
  label: string;
}): React.ReactElement {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        PROVENANCE_STYLE[provenance] ?? PROVENANCE_STYLE.default
      }`}
      title={`Provenance: ${provenance}`}
    >
      {label}
    </span>
  );
}

export interface ModelPickerProps {
  binding: StageBinding;
  busy?: boolean;
  /** Rendered above the list, e.g. "Model for this scene". */
  title?: string;
  /** When set, an explicit "use the project default" choice is offered. */
  onUseDefault?: () => void | Promise<void>;
  /** The inherited binding's model name, shown beside "use the project
   *  default" so the user knows what they would fall back TO. */
  inheritedName?: string | null;
  onSelect: (candidate: SelectionCandidate, rationale: string) => Promise<void>;
}

export default function ModelPicker({
  binding,
  busy = false,
  title,
  onUseDefault,
  inheritedName,
  onSelect,
}: ModelPickerProps): React.ReactElement {
  // Defaulted to something honest rather than forcing prose -- the column is
  // mandatory (`project_model_selections.rationale`), and demanding an essay
  // for a routine choice trains people to type "x".
  const [rationale, setRationale] = useState<string>("operator selection");
  const [expanded, setExpanded] = useState<boolean>(false);

  const current = binding.model_id;
  const usable = binding.candidates.filter((c) => c.selectable).length;

  return (
    <div className="rounded-md border border-gray-200 dark:border-gray-700 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-gray-900 dark:text-white">
            {title ?? binding.stage}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-700 dark:text-gray-300">
              {binding.model_display_name ?? binding.model_name ?? "no model bound"}
            </span>
            <ProvenanceBadge
              provenance={binding.provenance}
              label={binding.provenance_label}
            />
            <span
              className="text-xs text-gray-500 dark:text-gray-400"
              title="Selections are keyed by (stage, tier). A production-tier model is what a finished render uses."
            >
              tier: {binding.tier}
            </span>
          </div>
        </div>
        <button
          type="button"
          className="rounded border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Close" : "Change model"}
        </button>
      </div>

      {/* A binding that resolved but is no longer valid. Surfaced, never
          silently rewritten -- the user chose this model. */}
      {binding.warning && (
        <div className="mt-2 rounded border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-2 py-1 text-xs text-amber-800 dark:text-amber-300">
          {binding.warning}
        </div>
      )}

      {expanded && (
        <div className="mt-3 space-y-2">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {usable} of {binding.candidates.length} model
            {binding.candidates.length === 1 ? "" : "s"} can be selected for this
            stage. The rest are listed with the reason they cannot.
          </div>

          {binding.candidates.length === 0 && (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              No model in the store serves this stage and tier.
            </div>
          )}

          {binding.candidates.map((c) => {
            const isCurrent = c.id === current;
            return (
              <div
                key={c.id}
                className={`flex flex-wrap items-center justify-between gap-2 rounded border px-2 py-1.5 ${
                  isCurrent
                    ? "border-blue-400 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20"
                    : "border-gray-200 dark:border-gray-700"
                } ${c.selectable ? "" : "opacity-60"}`}
              >
                <div className="min-w-0">
                  <div className="text-sm text-gray-900 dark:text-white">
                    {c.display_name}
                    {c.is_default && (
                      <span className="ml-1 rounded bg-gray-200 dark:bg-gray-700 px-1 py-0.5 text-[10px] text-gray-700 dark:text-gray-300">
                        stage default
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {c.engine} · {c.state}
                    {c.weight_label ? ` · ${c.weight_label}` : ""}
                  </div>
                  {!c.selectable && c.refusal_message && (
                    <div className="mt-0.5 text-xs text-red-600 dark:text-red-400">
                      {c.refusal_message}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  disabled={busy || !c.selectable || isCurrent}
                  className="rounded border border-blue-300 dark:border-blue-700 px-2 py-1 text-xs text-blue-800 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30 disabled:opacity-50"
                  onClick={() => void onSelect(c, rationale)}
                  title={
                    c.selectable
                      ? undefined
                      : (c.refusal_message ?? "not selectable")
                  }
                >
                  {isCurrent ? "current" : "Use this model"}
                </button>
              </div>
            );
          })}

          {onUseDefault && (
            <div className="flex items-center justify-between gap-2 rounded border border-dashed border-gray-300 dark:border-gray-600 px-2 py-1.5">
              <div className="text-xs text-gray-600 dark:text-gray-300">
                Use the project default
                {inheritedName ? ` (${inheritedName})` : ""}
                <div className="text-gray-500 dark:text-gray-400">
                  Removes this scene&apos;s override so it follows the project
                  again — including when the project default later changes.
                </div>
              </div>
              <button
                type="button"
                disabled={busy || binding.provenance !== "scene"}
                className="rounded border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
                onClick={() => void onUseDefault()}
                title={
                  binding.provenance === "scene"
                    ? "Delete this scene's model override"
                    : "This scene has no override to clear"
                }
              >
                Clear override
              </button>
            </div>
          )}

          <label className="block">
            <span className="text-xs text-gray-600 dark:text-gray-300">
              Rationale (recorded with the selection)
            </span>
            <input
              type="text"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-sm text-gray-900 dark:text-gray-100"
              placeholder="operator selection"
            />
          </label>
        </div>
      )}
    </div>
  );
}
