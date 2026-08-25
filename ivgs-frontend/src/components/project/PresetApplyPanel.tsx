"use client";

import React, { useState } from "react";
import { applyPresetToProject, usePresets } from "@/hooks/useLibrary";
import type { PresetApplyResult } from "@/types/library";

/**
 * Apply a preset to an existing project — AD-09.5 / AD-09.15 criterion 1.
 *
 * WHY THE RESULT IS RENDERED IN TWO LISTS. `applied` and `recorded_not_applied`
 * come back separately from the API and both are shown, because a preset apply
 * that reports plain success while silently skipping half the bundle is exactly
 * the AD-09.3 stub family — eight endpoints in this system return 202 and do
 * nothing. Branding lands in the second list today: it is stored and readable,
 * and no render path consumes it (WP-56 Task 3 stopped on the presenter/logo
 * chain). Collapsing the two lists into one "Applied" toast would tell the
 * operator their logo was applied when nothing renders it.
 */
export default function PresetApplyPanel({
  projectId,
  canApply,
}: {
  projectId: string;
  canApply: boolean;
}): React.ReactElement | null {
  const { presets, isLoading } = usePresets(true);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PresetApplyResult | null>(null);
  const [error, setError] = useState("");

  if (!canApply) return null;

  async function apply() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await applyPresetToProject(projectId, selected));
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "The apply failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
        Apply a Preset
      </h2>
      <div className="rounded-lg border border-gray-300 bg-gray-100 p-4 dark:border-gray-700 dark:bg-gray-800">
        <p className="mb-3 text-sm text-gray-600 dark:text-gray-400">
          Writes the preset&rsquo;s actor, model selections and media defaults
          into this project. Presets are defaults, not constraints — editing the
          preset afterwards will not change this project, and editing this
          project will not change the preset.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="rounded-md border border-gray-400 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={isLoading}
            aria-label="Preset to apply"
          >
            <option value="">
              {isLoading ? "Loading presets…" : "— choose a preset —"}
            </option>
            {(presets ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} (v{p.version})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            onClick={apply}
            disabled={busy || !selected}
          >
            {busy ? "Applying…" : "Apply"}
          </button>
        </div>

        {error && (
          <p className="mt-3 text-sm text-red-500" role="alert">
            {error}
          </p>
        )}

        {result && (
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <p className="font-medium text-green-600 dark:text-green-400">
                Applied (version {result.preset_version})
              </p>
              {result.applied.length === 0 ? (
                <p className="text-gray-500">
                  Nothing was written — this preset carries no values that this
                  project can consume.
                </p>
              ) : (
                <ul className="list-inside list-disc text-gray-700 dark:text-gray-300">
                  {result.applied.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              )}
            </div>
            {result.recorded_not_applied.length > 0 && (
              <div className="rounded-md border border-amber-500/60 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/40">
                <p className="font-medium text-amber-700 dark:text-amber-300">
                  Recorded, but nothing renders it yet
                </p>
                <ul className="list-inside list-disc text-amber-800 dark:text-amber-200">
                  {result.recorded_not_applied.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
