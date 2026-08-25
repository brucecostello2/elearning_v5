"use client";

import React, { useCallback, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";

import { api } from "@/lib/api";
import { unwrapList } from "@/lib/unwrap";
import { useAuth } from "@/hooks/useAuth";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";

/**
 * §9 Prompt Management — the project tier, per project.
 *
 * WP-43 Tasks 2 and 4. This page did not exist. The Prompts tab was labelled
 * "(soon)" and pointed at `/projects/{id}/prompts` anyway, so clicking it
 * navigated to a route with no page component: HTTP 404, Next's built-in
 * error page, whose body text inherits `body`'s colour — which the root
 * layout was painting near-black on near-black. That is the "completely
 * black page, nav bar only" the operator reported.
 *
 * The tab was never "soon". `GET /api/v1/projects/{id}/prompts` has shipped
 * since IVGS-0.4 and works: verified live 2026-08-25 for c12fa967, HTTP 200,
 * ten effective prompts, every one resolving to source GLOBAL.
 *
 * WIRE SHAPE — `EffectivePrompt`, a BARE ARRAY of exactly six keys:
 *
 *   {prompt_type, prompt_id, prompt_text, version, source, scene_id}
 *
 * This is NOT `PromptResponse`. There is no `id`, no `scope`, no
 * `is_active`, no `created_at`, no `created_by`, no `change_note`. The
 * global prompts page's `PromptRecord` declares all of those, so reusing it
 * here would have been the WP-40 §0 defect again, on a page built to fix an
 * instance of it. The interface below is the wire and nothing more.
 *
 * `source` is the resolution result from §9.1 — SCENE beats PROJECT beats
 * GLOBAL — so it says, per prompt type, which tier this project is actually
 * running on.
 */

/** One row of `GET /api/v1/projects/{id}/prompts`. Six keys, all of them. */
interface EffectivePrompt {
  prompt_type: string;
  prompt_id: string | null;
  prompt_text: string | null;
  version: number | null;
  /** "SCENE" | "PROJECT" | "GLOBAL" — which tier won resolution. */
  source: string | null;
  scene_id: string | null;
}

const SOURCE_STYLES: Record<string, string> = {
  GLOBAL: "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
  PROJECT: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  SCENE: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
};

function prettyType(value: string): string {
  return value
    .split("_")
    .map((w) => (w.length > 0 ? w[0]!.toUpperCase() + w.slice(1) : w))
    .join(" ");
}

async function fetchEffectivePrompts(url: string): Promise<EffectivePrompt[]> {
  /* Bare array on the wire. `unwrapList` accepts either that or an envelope,
     so this cannot break the way WP-38's scenes fetch did if the route ever
     gains one. */
  const response = await api.get<unknown>(url);
  return unwrapList<EffectivePrompt>(response.data);
}

export default function ProjectPromptsPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();

  const key = projectId ? `/api/v1/projects/${projectId}/prompts` : null;
  const { data, error, isLoading, mutate } = useSWR<EffectivePrompt[]>(
    key,
    fetchEffectivePrompts,
    { revalidateOnFocus: true, dedupingInterval: 5000 },
  );

  const [expanded, setExpanded] = useState<string | null>(null);
  const [editingType, setEditingType] = useState<string | null>(null);
  const [draftText, setDraftText] = useState<string>("");
  const [changeNote, setChangeNote] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [toast, setToast] = useState<string>("");

  /* `POST /projects/{id}/prompts` is behind require_operator_or_admin. */
  const canEdit = user?.role === "admin" || user?.role === "operator";

  const prompts = useMemo<EffectivePrompt[]>(
    () => (Array.isArray(data) ? data : []),
    [data],
  );

  const overrideCount = prompts.filter(
    (p) => (p.source ?? "").toUpperCase() !== "GLOBAL",
  ).length;

  const startEdit = useCallback((p: EffectivePrompt): void => {
    setEditingType(p.prompt_type);
    setDraftText(p.prompt_text ?? "");
    setChangeNote("");
    setSaveError(null);
    setNoteError(null);
  }, []);

  const cancelEdit = useCallback((): void => {
    setEditingType(null);
    setDraftText("");
    setChangeNote("");
    setSaveError(null);
    setNoteError(null);
  }, []);

  const saveOverride = useCallback(async (): Promise<void> => {
    if (!editingType || !canEdit) return;

    /* `PromptCreate.change_note` is `min_length=1` and REQUIRED. Saying so
       here beats letting the server say it in a 422 the operator has to
       decode -- and if one arrives anyway, it is rendered verbatim below. */
    if (changeNote.trim().length === 0) {
      setNoteError("A change note is required — the API rejects an empty one.");
      return;
    }
    if (draftText.trim().length === 0) {
      setSaveError("Prompt text cannot be empty.");
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    setNoteError(null);
    try {
      await api.post(`/api/v1/projects/${projectId}/prompts`, {
        prompt_type: editingType,
        prompt_text: draftText,
        change_note: changeNote.trim(),
      });
      setToast(`Project override saved for ${prettyType(editingType)}.`);
      cancelEdit();
      await mutate();
    } catch (err: unknown) {
      setSaveError(
        err instanceof Error && err.message
          ? err.message
          : "Failed to save the project override.",
      );
    } finally {
      setIsSaving(false);
    }
  }, [editingType, canEdit, changeNote, draftText, projectId, cancelEdit, mutate]);

  if (isLoading && !data) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading prompts…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-100 p-4 text-red-600 dark:border-red-700 dark:bg-red-900/30 dark:text-red-400">
        Failed to load prompts: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Prompts
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {prompts.length} prompt type{prompts.length === 1 ? "" : "s"} ·{" "}
            {overrideCount === 0
              ? "all resolving to the global template"
              : `${overrideCount} overridden for this project`}
          </p>
        </div>
        <Link
          href="/prompts"
          className="shrink-0 rounded-lg bg-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
        >
          Global prompt library →
        </Link>
      </div>

      <p className="rounded-lg border border-gray-300 bg-gray-100 px-4 py-3 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
        These are the <strong>effective</strong> prompts for this project —
        what the pipeline will actually use. Resolution is scene → project →
        global (§9.1); the badge on each row says which tier won. Saving here
        creates a <strong>project-tier override</strong>, which takes
        precedence over the global template for this project only.
      </p>

      {prompts.length === 0 ? (
        <div className="py-16 text-center text-gray-500 dark:text-gray-400">
          No prompts resolved for this project.
        </div>
      ) : (
        <div className="space-y-3">
          {prompts.map((p) => {
            const source = (p.source ?? "UNKNOWN").toUpperCase();
            const isOpen = expanded === p.prompt_type;
            const isEditing = editingType === p.prompt_type;

            return (
              <div
                key={p.prompt_type}
                className="overflow-hidden rounded-xl border border-gray-300 bg-gray-100 dark:border-gray-700 dark:bg-gray-800"
              >
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                  <div className="flex min-w-0 flex-wrap items-center gap-3">
                    <span className="font-medium text-gray-900 dark:text-white">
                      {prettyType(p.prompt_type)}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                        SOURCE_STYLES[source] ??
                        "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
                      }`}
                    >
                      {source}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      v{p.version ?? "—"} ·{" "}
                      {(p.prompt_text ?? "").length} chars
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded(isOpen ? null : p.prompt_type)
                      }
                      className="rounded-lg bg-gray-200 px-3 py-1.5 text-xs text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                    >
                      {isOpen ? "Hide" : "View"}
                    </button>
                    {canEdit && !isEditing && (
                      <button
                        type="button"
                        onClick={() => {
                          setExpanded(p.prompt_type);
                          startEdit(p);
                        }}
                        className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs text-white transition-colors hover:bg-blue-700"
                      >
                        {source === "PROJECT"
                          ? "Edit override"
                          : "Override for this project"}
                      </button>
                    )}
                  </div>
                </div>

                {isOpen && (
                  <div className="border-t border-gray-300 px-5 py-4 dark:border-gray-700">
                    {isEditing ? (
                      <div className="space-y-3">
                        <div>
                          <label
                            htmlFor={`text-${p.prompt_type}`}
                            className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
                          >
                            Prompt text (Jinja2)
                          </label>
                          <textarea
                            id={`text-${p.prompt_type}`}
                            value={draftText}
                            onChange={(e) => {
                              setDraftText(e.target.value);
                              setSaveError(null);
                            }}
                            rows={14}
                            className="w-full resize-y rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-xs text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                          />
                        </div>
                        <div>
                          <label
                            htmlFor={`note-${p.prompt_type}`}
                            className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
                          >
                            Change note (required)
                          </label>
                          <input
                            id={`note-${p.prompt_type}`}
                            value={changeNote}
                            onChange={(e) => {
                              setChangeNote(e.target.value);
                              setNoteError(null);
                            }}
                            aria-invalid={noteError ? true : undefined}
                            placeholder="Why this override exists"
                            className={`w-full rounded-lg border bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white ${
                              noteError
                                ? "border-red-500"
                                : "border-gray-300 dark:border-gray-700"
                            }`}
                          />
                          {noteError && (
                            <p
                              role="alert"
                              className="mt-1 text-xs text-red-600 dark:text-red-400"
                            >
                              {noteError}
                            </p>
                          )}
                        </div>
                        {saveError && (
                          <p
                            role="alert"
                            className="rounded-md border border-red-200 bg-red-100 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300"
                          >
                            {saveError}
                          </p>
                        )}
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void saveOverride()}
                            disabled={isSaving}
                            className="rounded-lg bg-green-600 px-4 py-2 text-sm text-white transition-colors hover:bg-green-700 disabled:opacity-50"
                          >
                            {isSaving ? "Saving…" : "Save project override"}
                          </button>
                          <button
                            type="button"
                            onClick={cancelEdit}
                            className="px-3 py-2 text-sm text-gray-500 transition-colors hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 font-mono text-xs text-gray-800 dark:bg-gray-900 dark:text-gray-200">
                          {p.prompt_text ?? "(this prompt has no text)"}
                        </pre>
                        {p.prompt_id && (
                          <p className="mt-2 font-mono text-[10px] text-gray-500 dark:text-gray-400">
                            prompt_id {p.prompt_id}
                            {p.scene_id ? ` · scene ${p.scene_id}` : ""}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {toast && (
        <Toast message={toast} type="success" onClose={() => setToast("")} />
      )}
    </div>
  );
}
