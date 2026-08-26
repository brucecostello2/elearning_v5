"use client";

import React, { useCallback, useEffect, useState } from "react";
import { mutate as globalMutate } from "swr";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/api-error";

/**
 * WP-64 Task 6(b) — the project's learning outcomes, shown and editable.
 *
 * WHY IT IS ON THE OVERVIEW AND NOT BURIED IN A SETTINGS DIALOG. This field is
 * an INPUT to storyboard generation, not metadata: RULE 0 of the storyboard
 * prompt makes it the test the scene mix and every visual are judged against.
 * An operator reading a storyboard that does not serve their course needs to be
 * able to see, in one place, what the model was told the course was for.
 *
 * THE NOTICE IS THE POINT OF THIS COMPONENT AS MUCH AS THE TEXTAREA IS.
 * Scenes are rows a completed run wrote. Editing this field afterwards changes
 * what the NEXT storyboard generation reads and reaches back into nothing. A
 * field that looked like it governed the storyboard on screen, and silently
 * did not, would be the same class of defect as the five scene fields WP-43
 * found being accepted with a 200 and dropped.
 */
export default function LearningOutcomesPanel({
  projectId,
  value,
  canEdit,
}: {
  projectId: string;
  value: string | null | undefined;
  canEdit: boolean;
}): React.ReactElement {
  const saved = value ?? "";
  const [draft, setDraft] = useState<string>(saved);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  /* Re-seed when the project reloads under us, but never while the operator is
     mid-edit: overwriting a half-typed outcome with a revalidation would throw
     away typing, which is the same sin as overwriting a description. */
  useEffect(() => {
    if (!isEditing) setDraft(saved);
  }, [saved, isEditing]);

  const handleSave = useCallback(async (): Promise<void> => {
    if (isSaving) return;
    setError(null);
    setIsSaving(true);
    try {
      await api.patch(`/api/v1/projects/${projectId}`, {
        /* An empty box means "there are none", which is a real answer and is
           sent as null so the column is cleared rather than set to "". */
        learning_outcomes: draft.trim() ? draft.trim() : null,
      });
      await globalMutate(`/api/v1/projects/${projectId}`);
      setIsEditing(false);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }, [projectId, draft, isSaving]);

  return (
    <section>
      <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-white">
        Learning Outcomes
      </h2>
      <div className="rounded-lg border border-gray-300 bg-gray-100 p-4 dark:border-gray-700 dark:bg-gray-800">
        <p className="mb-3 text-xs text-gray-600 dark:text-gray-400">
          What the viewer should be able to do afterwards. The storyboard model
          reads this when it plans the scenes: an outcome about following or
          performing something is one a still frame cannot serve, and the scene
          that teaches it becomes a video clip rather than an image.{" "}
          <strong className="font-medium">
            Editing this does not change scenes that already exist — it feeds
            the next storyboard generation.
          </strong>
        </p>

        {isEditing ? (
          <>
            <textarea
              id="learning-outcomes"
              aria-label="Learning outcomes"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={4000}
              rows={5}
              placeholder="One statement per line."
              className="w-full resize-y rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white"
            />
            {error && (
              <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">
                {error}
              </p>
            )}
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={handleSave}
                disabled={isSaving}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {isSaving ? "Saving…" : "Save outcomes"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(saved);
                  setError(null);
                  setIsEditing(false);
                }}
                className="rounded-lg bg-gray-200 px-3 py-1.5 text-xs font-medium text-gray-800 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            {saved ? (
              <p className="whitespace-pre-wrap text-sm text-gray-900 dark:text-gray-100">
                {saved}
              </p>
            ) : (
              /* A real answer, in words. Not an empty box that reads as a
                 loading failure. */
              <p className="text-sm text-gray-500 dark:text-gray-400">
                None stated. The storyboard will be planned from the transcript
                alone.
              </p>
            )}
            {canEdit && (
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="mt-3 rounded-lg bg-gray-200 px-3 py-1.5 text-xs font-medium text-gray-800 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
              >
                {saved ? "Edit outcomes" : "Add outcomes"}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}
