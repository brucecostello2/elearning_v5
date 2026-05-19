"use client";

import React, { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useTranscripts } from "@/hooks/useTranscripts";
import { useAuth } from "@/hooks/useAuth";
import TranscriptEditor from "@/components/TranscriptEditor";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { Transcript } from "@/types/api";

/**
 * §8.1.3 Table 8-2 — Transcripts Tab
 *
 * Features:
 *   - Original uploads + refined transcript side-by-side diff
 *   - Inline edit of refined text
 *   - Reorder uploads (drag-and-drop)
 *   - Save changes back to API
 *
 * RBAC per Table 8-3:
 *   - admin/operator: full edit access
 *   - viewer: read-only
 */

export default function TranscriptPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const {
    transcripts,
    isLoading,
    error,
    updateTranscript,
    reorderTranscripts,
    mutate,
  } = useTranscripts(projectId);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const canEdit = user?.role === "admin" || user?.role === "operator";

  /**
   * Start inline editing of a transcript's refined text.
   */
  const handleStartEdit = useCallback(
    (transcript: Transcript): void => {
      if (!canEdit) return;
      setEditingId(transcript.id);
      setEditText(transcript.refined_text || transcript.original_text);
    },
    [canEdit]
  );

  /**
   * Cancel editing without saving.
   */
  const handleCancelEdit = useCallback((): void => {
    setEditingId(null);
    setEditText("");
  }, []);

  /**
   * Save the edited refined text back to the API.
   */
  const handleSaveEdit = useCallback(
    async (transcriptId: string): Promise<void> => {
      setIsSaving(true);
      try {
        await updateTranscript(transcriptId, { refined_text: editText });
        setEditingId(null);
        setEditText("");
        setToastMessage("Transcript saved successfully.");
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to save transcript.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setIsSaving(false);
      }
    },
    [editText, updateTranscript, mutate]
  );

  /**
   * Drag-and-drop reorder handlers.
   */
  const handleDragStart = useCallback(
    (_e: React.DragEvent<HTMLDivElement>, index: number): void => {
      setDragIndex(index);
    },
    []
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>): void => {
      e.preventDefault();
    },
    []
  );

  const handleDrop = useCallback(
    async (
      e: React.DragEvent<HTMLDivElement>,
      dropIndex: number
    ): Promise<void> => {
      e.preventDefault();
      if (dragIndex === null || dragIndex === dropIndex || !canEdit) return;

      try {
        const reordered = [...(transcripts || [])];
        const [moved] = reordered.splice(dragIndex, 1);
        reordered.splice(dropIndex, 0, moved);

        const orderMap = reordered.map((t, idx) => ({
          id: t.id,
          order: idx,
        }));

        await reorderTranscripts(orderMap);
        setToastMessage("Transcript order updated.");
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to reorder.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setDragIndex(null);
      }
    },
    [dragIndex, transcripts, canEdit, reorderTranscripts, mutate]
  );

  // ── Loading ─────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading transcripts…" />
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          Failed to load transcripts: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Transcripts</h2>
          <p className="text-gray-400 text-sm mt-1">
            {transcripts?.length || 0} transcript
            {(transcripts?.length || 0) !== 1 ? "s" : ""} — drag to reorder
          </p>
        </div>
        <a
          href={`/projects/${projectId}`}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          ← Back to Overview
        </a>
      </div>

      {/* ── Transcript List ────────────────────────────────────────── */}
      {!transcripts || transcripts.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          No transcripts uploaded for this project.
        </div>
      ) : (
        <div className="space-y-6">
          {transcripts.map((transcript: Transcript, index: number) => (
            <div
              key={transcript.id}
              draggable={canEdit}
              onDragStart={(e) => handleDragStart(e, index)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, index)}
              className={`bg-gray-800 border rounded-xl overflow-hidden transition-colors ${
                dragIndex === index
                  ? "border-blue-500"
                  : "border-gray-700"
              }`}
            >
              {/* Transcript Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
                <div className="flex items-center gap-3">
                  {canEdit && (
                    <svg
                      className="w-4 h-4 text-gray-500 cursor-grab"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 8h16M4 16h16"
                      />
                    </svg>
                  )}
                  <span className="text-sm font-mono text-gray-500">
                    #{index + 1}
                  </span>
                  <span className="text-white font-medium">
                    {transcript.filename}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {transcript.refined_text && (
                    <span className="px-2 py-0.5 bg-green-900/30 text-green-400 text-xs rounded-full">
                      Refined
                    </span>
                  )}
                  {canEdit && editingId !== transcript.id && (
                    <button
                      onClick={() => handleStartEdit(transcript)}
                      className="px-3 py-1 text-sm text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>

              {/* Side-by-side diff / Editor */}
              {editingId === transcript.id ? (
                <div className="p-6">
                  <TranscriptEditor
                    originalText={transcript.original_text}
                    refinedText={editText}
                    onChange={setEditText}
                    readOnly={false}
                  />
                  <div className="flex items-center gap-3 mt-4">
                    <button
                      onClick={() => handleSaveEdit(transcript.id)}
                      disabled={isSaving}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm"
                    >
                      {isSaving ? "Saving…" : "Save Changes"}
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      className="px-4 py-2 text-gray-400 hover:text-white transition-colors text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="p-6">
                  <TranscriptEditor
                    originalText={transcript.original_text}
                    refinedText={
                      transcript.refined_text || transcript.original_text
                    }
                    readOnly={true}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Toast */}
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
