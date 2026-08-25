"use client";

import React, { useCallback, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";

import { api } from "@/lib/api";
import { unwrapList } from "@/lib/unwrap";
import { useProjects } from "@/hooks/useProjects";
import { useAuth } from "@/hooks/useAuth";
import StateBadge from "@/components/StateBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import {
  addableLanguages,
  isRetryableVariant,
  languageLabel,
  variantHasRender,
  variantProgressPercent,
  variantState,
} from "@/lib/languages";
import type { LanguageVariant } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Languages Tab
 *
 * WP-43 Task 3, two defects, both about telling the truth.
 *
 * (a) **Adding a language always failed with a bare status.** The picker
 *     offered ten bare ISO-639-1 codes (en, es, fr, de, pt, ja, zh, ko, ar,
 *     hi). `LanguageVariantCreate` accepts eight BCP-47 codes and rejects
 *     everything else, so not one of the ten could ever succeed — and three
 *     of them (pt, ko, hi) have no accepted form at all. The 422's body
 *     names the problem in full; the client threw it away. The picker now
 *     offers exactly the accepted set, and any server refusal is rendered
 *     verbatim, at the field, in the PipelineGateButton manner.
 *
 * (b) **"PENDING 0%" over a language that has a finished draft.** The 0% was
 *     WP-45 Task 6(c) CLOSED this: the API derives progress from each
 *     variant's own pipeline checkpoints and sends it. The original defect:
 *     `variant.progress_percent || 0` over a field that did not exist:
 *     `LanguageVariantResponse` sends id, project_id, language_code, state,
 *     final_render_1080p_id, final_render_4k_id, created_at — and nothing
 *     else. No per-language progress figure is written anywhere in
 *     ivgs-api, ivgs-workers or shared/, so there is nothing to read. The
 *     column now says "not tracked yet" and the report records the gap.
 *
 * The rows are read from `GET /projects/{id}/languages` rather than from
 * `project.language_variants`, because only the former carries the variant
 * UUID — and the retry route's path parameter is a UUID, which is why Retry
 * used to 422 too.
 */

async function fetchVariants(url: string): Promise<LanguageVariant[]> {
  const response = await api.get<unknown>(url);
  return unwrapList<LanguageVariant>(response.data);
}

export default function LanguagesPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const { addLanguage, retryLanguage } = useProjects(projectId);

  const variantsKey = projectId
    ? `/api/v1/projects/${projectId}/languages`
    : null;
  const {
    data: variants,
    error,
    isLoading,
    mutate,
  } = useSWR<LanguageVariant[]>(variantsKey, fetchVariants, {
    revalidateOnFocus: true,
    dedupingInterval: 5000,
  });

  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [selectedNewLang, setSelectedNewLang] = useState<string>("");
  const [isAdding, setIsAdding] = useState<boolean>(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  const canEdit = user?.role === "admin" || user?.role === "operator";

  const rows = useMemo<LanguageVariant[]>(
    () => (Array.isArray(variants) ? variants : []),
    [variants],
  );

  const available = useMemo(
    () => addableLanguages(rows.map((v) => v.language_code)),
    [rows],
  );

  const handleAddLanguage = useCallback(async (): Promise<void> => {
    if (!selectedNewLang || !canEdit) return;
    setIsAdding(true);
    setAddError(null);
    try {
      await addLanguage(selectedNewLang);
      setToastMessage(`Language "${selectedNewLang}" added.`);
      setToastType("success");
      setShowToast(true);
      setShowAddForm(false);
      setSelectedNewLang("");
      await mutate();
    } catch (err: unknown) {
      /* The server's own sentence, not a status code and not a rewrite of
         it. On a 422 that reads e.g. "language_code: Value error,
         Unsupported language code 'es'. Supported: ar-SA, de-DE, ...". */
      setAddError(
        err instanceof Error && err.message
          ? err.message
          : "Failed to add language.",
      );
    } finally {
      setIsAdding(false);
    }
  }, [selectedNewLang, canEdit, addLanguage, mutate]);

  const handleRetry = useCallback(
    async (variant: LanguageVariant): Promise<void> => {
      if (!canEdit || !variant.id) return;
      setRetryingId(variant.id);
      setRowError(null);
      try {
        await retryLanguage(variant.id);
        setToastMessage(
          `Retry queued for the ${variant.language_code} variant.`,
        );
        setToastType("success");
        setShowToast(true);
        await mutate();
      } catch (err: unknown) {
        setRowError(
          err instanceof Error && err.message ? err.message : "Retry failed.",
        );
      } finally {
        setRetryingId(null);
      }
    },
    [canEdit, retryLanguage, mutate],
  );

  if (isLoading && !variants) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading languages…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-100 p-4 text-red-600 dark:border-red-700 dark:bg-red-900/30 dark:text-red-400">
        Failed to load language variants: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Languages
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {rows.length} language variant{rows.length !== 1 ? "s" : ""}
          </p>
        </div>
        {canEdit && available.length > 0 && (
          <button
            type="button"
            onClick={() => {
              setShowAddForm((v) => !v);
              setAddError(null);
            }}
            className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white transition-colors hover:bg-blue-700"
          >
            + Add Language
          </button>
        )}
      </div>

      {/* ── Add form ─────────────────────────────────────────────────── */}
      {showAddForm && (
        <div className="rounded-xl border border-gray-300 bg-gray-100 p-4 dark:border-gray-700 dark:bg-gray-800">
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-[16rem] flex-1">
              <label
                htmlFor="new-language"
                className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
              >
                Language
              </label>
              <select
                id="new-language"
                value={selectedNewLang}
                onChange={(e) => {
                  setSelectedNewLang(e.target.value);
                  setAddError(null);
                }}
                aria-invalid={addError ? true : undefined}
                className={`w-full rounded-lg border bg-gray-200 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white ${
                  addError
                    ? "border-red-500 dark:border-red-500"
                    : "border-gray-300 dark:border-gray-600"
                }`}
              >
                <option value="">Choose a language…</option>
                {available.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.label} — {lang.code}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                These are the eight BCP-47 codes the API accepts
                (<code className="font-mono">SUPPORTED_LANGUAGES</code>). A code
                outside this set is refused before the request reaches the
                database.
              </p>
              {addError && (
                <p
                  role="alert"
                  className="mt-2 rounded-md border border-red-200 bg-red-100 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300"
                >
                  {addError}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void handleAddLanguage()}
              disabled={!selectedNewLang || isAdding}
              className="rounded-lg bg-green-600 px-4 py-2 text-sm text-white transition-colors hover:bg-green-700 disabled:opacity-50"
            >
              {isAdding ? "Adding…" : "Add"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowAddForm(false);
                setSelectedNewLang("");
                setAddError(null);
              }}
              className="px-4 py-2 text-sm text-gray-500 transition-colors hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {rowError && (
        <p
          role="alert"
          className="rounded-md border border-red-200 bg-red-100 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300"
        >
          {rowError}
        </p>
      )}

      {/* ── Variant table ────────────────────────────────────────────── */}
      {rows.length === 0 ? (
        <div className="py-16 text-center text-gray-500 dark:text-gray-400">
          No language variants configured for this project.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-300 bg-gray-100 dark:border-gray-700 dark:bg-gray-800">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-300 text-left dark:border-gray-700">
                  <Th>Language</Th>
                  <Th>Code</Th>
                  <Th>State</Th>
                  <Th>Progress</Th>
                  <Th>Final render</Th>
                  <Th>Created</Th>
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-300 dark:divide-gray-700">
                {rows.map((variant) => {
                  const percent = variantProgressPercent(variant);
                  return (
                    <tr key={variant.id ?? variant.language_code}>
                      <td className="px-5 py-3 font-medium text-gray-900 dark:text-white">
                        {languageLabel(variant.language_code)}
                      </td>
                      <td className="px-5 py-3 font-mono text-gray-500 dark:text-gray-400">
                        {variant.language_code}
                      </td>
                      <td className="px-5 py-3">
                        <StateBadge state={variantState(variant)} />
                      </td>
                      <td className="px-5 py-3">
                        {percent === null ? (
                          /* The honest replacement for a fabricated 0%. */
                          <span
                            className="text-xs italic text-gray-500 dark:text-gray-400"
                            title={
                              variant.progress_source ??
                              "No render job has been attributed to this language yet."
                            }
                          >
                            not started
                          </span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <div className="h-2 max-w-[120px] flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                              <div
                                className="h-full rounded-full bg-blue-500 transition-all"
                                style={{ width: `${percent}%` }}
                              />
                            </div>
                            <span
                              className="text-xs text-gray-500 dark:text-gray-400"
                              title={variant.progress_source ?? undefined}
                            >
                              {percent}%
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-3 text-xs text-gray-500 dark:text-gray-400">
                        {variantHasRender(variant) ? "Available" : "None yet"}
                      </td>
                      <td className="px-5 py-3 text-xs text-gray-500 dark:text-gray-400">
                        {variant.created_at
                          ? new Date(variant.created_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-5 py-3">
                        {canEdit && isRetryableVariant(variant) && (
                          <button
                            type="button"
                            onClick={() => void handleRetry(variant)}
                            disabled={retryingId === variant.id}
                            className="rounded bg-yellow-600 px-3 py-1 text-xs text-white transition-colors hover:bg-yellow-700 disabled:opacity-50"
                          >
                            {retryingId === variant.id ? "Retrying…" : "Retry"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        <strong>Progress is not measured per language.</strong>{" "}
        <code className="font-mono">LanguageVariantResponse</code> carries
        only a state and the two final-render ids; no component of IVGS writes
        a per-language completion figure. This column will show a real
        percentage the day one exists, and says nothing until then.
      </p>

      {showToast && (
        <Toast
          message={toastMessage}
          type={toastType}
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <th className="px-5 py-3 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
      {children}
    </th>
  );
}
