"use client";

import React, { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useProjects } from "@/hooks/useProjects";
import { useAuth } from "@/hooks/useAuth";
import StateBadge from "@/components/StateBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { LanguageVariant } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Languages Tab
 *
 * Features:
 *   - Language variant table with status badges
 *   - Add Language button
 *   - Retry button for failed variants
 */

const ALL_LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "pt", label: "Portuguese" },
  { code: "ja", label: "Japanese" },
  { code: "zh", label: "Chinese (Mandarin)" },
  { code: "ko", label: "Korean" },
  { code: "ar", label: "Arabic" },
  { code: "hi", label: "Hindi" },
];

export default function LanguagesPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const { project, isLoading, error, addLanguage, retryLanguage, mutate } =
    useProjects(projectId);

  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [selectedNewLang, setSelectedNewLang] = useState<string>("");
  const [isAdding, setIsAdding] = useState<boolean>(false);
  const [retryingLang, setRetryingLang] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  const canEdit = user?.role === "admin" || user?.role === "operator";

  /** Languages already added to this project */
  const existingLanguages = React.useMemo<string[]>(
    () =>
      (project?.language_variants || []).map(
        (v: LanguageVariant) => v.language_code
      ),
    [project]
  );

  /** Languages available to add */
  const availableLanguages = React.useMemo(
    () => ALL_LANGUAGES.filter((l) => !existingLanguages.includes(l.code)),
    [existingLanguages]
  );

  /**
   * Add a new language variant to the project.
   */
  const handleAddLanguage = useCallback(async (): Promise<void> => {
    if (!selectedNewLang || !canEdit) return;
    setIsAdding(true);
    try {
      await addLanguage(selectedNewLang);
      setToastMessage(`Language "${selectedNewLang.toUpperCase()}" added.`);
      setToastType("success");
      setShowToast(true);
      setShowAddForm(false);
      setSelectedNewLang("");
      mutate();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to add language.";
      setToastMessage(message);
      setToastType("error");
      setShowToast(true);
    } finally {
      setIsAdding(false);
    }
  }, [selectedNewLang, canEdit, addLanguage, mutate]);

  /**
   * Retry a failed language variant.
   */
  const handleRetry = useCallback(
    async (languageCode: string): Promise<void> => {
      if (!canEdit) return;
      setRetryingLang(languageCode);
      try {
        await retryLanguage(languageCode);
        setToastMessage(
          `Retry queued for "${languageCode.toUpperCase()}" variant.`
        );
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Retry failed.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setRetryingLang(null);
      }
    },
    [canEdit, retryLanguage, mutate]
  );

  const getLangLabel = (code: string): string =>
    ALL_LANGUAGES.find((l) => l.code === code)?.label || code.toUpperCase();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading languages…" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          {error?.message || "Project not found."}
        </div>
      </div>
    );
  }

  const variants: LanguageVariant[] = project.language_variants || [];

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Languages</h2>
          <p className="text-gray-400 text-sm mt-1">
            {variants.length} language variant
            {variants.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {canEdit && availableLanguages.length > 0 && (
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
            >
              + Add Language
            </button>
          )}
          <a
            href={`/projects/${projectId}`}
            className="text-sm text-gray-400 hover:text-white transition-colors"
          >
            ← Back
          </a>
        </div>
      </div>

      {/* Add Language Form */}
      {showAddForm && (
        <div className="mb-6 p-4 bg-gray-800 border border-gray-700 rounded-xl flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Select Language
            </label>
            <select
              value={selectedNewLang}
              onChange={(e) => setSelectedNewLang(e.target.value)}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Choose a language…</option>
              {availableLanguages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleAddLanguage}
            disabled={!selectedNewLang || isAdding}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors text-sm"
          >
            {isAdding ? "Adding…" : "Add"}
          </button>
          <button
            onClick={() => {
              setShowAddForm(false);
              setSelectedNewLang("");
            }}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors text-sm"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Language Variant Table */}
      {variants.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          No language variants configured for this project.
        </div>
      ) : (
        <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-left">
                  <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Language
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Code
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Status
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Progress
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Last Updated
                  </th>
                  <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {variants.map((variant: LanguageVariant) => (
                  <tr
                    key={variant.language_code}
                    className="hover:bg-gray-750 transition-colors"
                  >
                    <td className="px-5 py-3 text-white font-medium">
                      {getLangLabel(variant.language_code)}
                    </td>
                    <td className="px-5 py-3 text-gray-400 font-mono">
                      {variant.language_code.toUpperCase()}
                    </td>
                    <td className="px-5 py-3">
                      <StateBadge state={variant.status} />
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden max-w-[120px]">
                          <div
                            className="h-full bg-blue-500 rounded-full transition-all"
                            style={{
                              width: `${variant.progress_percent || 0}%`,
                            }}
                          />
                        </div>
                        <span className="text-xs text-gray-400">
                          {variant.progress_percent || 0}%
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs">
                      {variant.updated_at
                        ? new Date(variant.updated_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-5 py-3">
                      {canEdit &&
                        (variant.status === "FAILED" ||
                          variant.status === "ERROR") && (
                          <button
                            onClick={() =>
                              handleRetry(variant.language_code)
                            }
                            disabled={
                              retryingLang === variant.language_code
                            }
                            className="px-3 py-1 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50 transition-colors"
                          >
                            {retryingLang === variant.language_code
                              ? "Retrying…"
                              : "Retry"}
                          </button>
                        )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
