"use client";

import React, { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useProjects } from "@/hooks/useProjects";
import AssetUploader from "@/components/AssetUploader";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { ProjectCreatePayload } from "@/types/api";

/**
 * §8.1.2 New Project / Input Form
 *
 * Table 8-1 New Project Form Fields:
 *   - Video Name: text, required, max 255 chars
 *   - Description: textarea, optional, max 1000 chars
 *   - Maximum Runtime: number (minutes:seconds), required, 1–120 min
 *   - Talking Head Clip: file upload (MP4/MOV), required, max 500 MB
 *   - Voice Transcripts: multi-file upload (PDF/DOCX/TXT), required, >= 1
 *   - Transcript Order: drag-and-drop reorder list
 *   - Existing Storyboard: file upload (PDF/DOCX), optional
 *   - Target Languages: multi-select dropdown, optional at creation
 */

/** Available target languages per §17 Localization */
const TARGET_LANGUAGES: { code: string; label: string }[] = [
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

/** Maximum talking head file size: 500 MB per Table 8-1 */
const MAX_TALKING_HEAD_SIZE = 500 * 1024 * 1024;

/** Accepted talking head MIME types */
const TALKING_HEAD_ACCEPT = ".mp4,.mov";

/** Accepted transcript MIME types */
const TRANSCRIPT_ACCEPT = ".pdf,.docx,.txt";

/** Accepted storyboard MIME types */
const STORYBOARD_ACCEPT = ".pdf,.docx";

interface TranscriptFile {
  file: File;
  id: string;
  order: number;
}

interface FormErrors {
  name?: string;
  runtime?: string;
  talkingHead?: string;
  transcripts?: string;
  general?: string;
}

export default function NewProjectPage(): React.ReactElement {
  const router = useRouter();
  const { user } = useAuth();
  const { createProject } = useProjects();

  // ── Form Fields ─────────────────────────────────────────────────────
  const [name, setName] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [runtimeMinutes, setRuntimeMinutes] = useState<number>(5);
  const [runtimeSeconds, setRuntimeSeconds] = useState<number>(0);
  const [talkingHeadFile, setTalkingHeadFile] = useState<File | null>(null);
  const [transcriptFiles, setTranscriptFiles] = useState<TranscriptFile[]>([]);
  const [storyboardFile, setStoryboardFile] = useState<File | null>(null);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);

  // ── UI State ────────────────────────────────────────────────────────
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  // ── Drag & Drop Reorder ─────────────────────────────────────────────
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const transcriptInputRef = useRef<HTMLInputElement>(null);

  /**
   * Validate all form fields per Table 8-1 constraints.
   * Returns true if valid, sets error state if not.
   */
  const validateForm = useCallback((): boolean => {
    const newErrors: FormErrors = {};

    // Video Name: required, max 255
    if (!name.trim()) {
      newErrors.name = "Video name is required.";
    } else if (name.trim().length > 255) {
      newErrors.name = "Video name must be 255 characters or fewer.";
    }

    // Maximum Runtime: 1–120 minutes
    const totalMinutes = runtimeMinutes + runtimeSeconds / 60;
    if (totalMinutes < 1 || totalMinutes > 120) {
      newErrors.runtime = "Runtime must be between 1 and 120 minutes.";
    }

    // Talking Head Clip: required, max 500 MB
    if (!talkingHeadFile) {
      newErrors.talkingHead = "Talking head clip is required.";
    } else if (talkingHeadFile.size > MAX_TALKING_HEAD_SIZE) {
      newErrors.talkingHead = "Talking head clip must be 500 MB or smaller.";
    }

    // Voice Transcripts: at least one
    if (transcriptFiles.length === 0) {
      newErrors.transcripts = "At least one voice transcript file is required.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [name, runtimeMinutes, runtimeSeconds, talkingHeadFile, transcriptFiles]);

  /**
   * Handle transcript file selection — add to list with unique IDs.
   */
  const handleTranscriptSelect = useCallback(
    (files: FileList | null): void => {
      if (!files) return;
      const newFiles: TranscriptFile[] = Array.from(files).map(
        (file, idx) => ({
          file,
          id: `${Date.now()}-${idx}-${file.name}`,
          order: transcriptFiles.length + idx,
        })
      );
      setTranscriptFiles((prev) => [...prev, ...newFiles]);
    },
    [transcriptFiles.length]
  );

  /**
   * Remove a transcript from the list.
   */
  const handleRemoveTranscript = useCallback((id: string): void => {
    setTranscriptFiles((prev) =>
      prev
        .filter((t) => t.id !== id)
        .map((t, idx) => ({ ...t, order: idx }))
    );
  }, []);

  /**
   * Drag-and-drop reorder for transcript order per Table 8-1.
   */
  const handleDragStart = useCallback(
    (e: React.DragEvent<HTMLDivElement>, index: number): void => {
      setDragIndex(index);
      e.dataTransfer.effectAllowed = "move";
    },
    []
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>): void => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    },
    []
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>, dropIndex: number): void => {
      e.preventDefault();
      if (dragIndex === null || dragIndex === dropIndex) return;

      setTranscriptFiles((prev) => {
        const updated = [...prev];
        const [moved] = updated.splice(dragIndex, 1);
        updated.splice(dropIndex, 0, moved);
        return updated.map((t, idx) => ({ ...t, order: idx }));
      });
      setDragIndex(null);
    },
    [dragIndex]
  );

  /**
   * Toggle a language in/out of the selected set.
   */
  const handleLanguageToggle = useCallback((code: string): void => {
    setSelectedLanguages((prev) =>
      prev.includes(code)
        ? prev.filter((c) => c !== code)
        : [...prev, code]
    );
  }, []);

  /**
   * Submit the form: build FormData, POST to /api/v1/projects.
   */
  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
      e.preventDefault();
      if (!validateForm()) return;

      setIsSubmitting(true);
      setErrors({});

      try {
        const formData = new FormData();
        formData.append("name", name.trim());
        formData.append("description", description.trim());
        formData.append(
          "max_runtime_seconds",
          String(runtimeMinutes * 60 + runtimeSeconds)
        );

        if (talkingHeadFile) {
          formData.append("talking_head_clip", talkingHeadFile);
        }

        transcriptFiles.forEach((tf, idx) => {
          formData.append("transcripts", tf.file);
          formData.append("transcript_order", String(idx));
        });

        if (storyboardFile) {
          formData.append("existing_storyboard", storyboardFile);
        }

        if (selectedLanguages.length > 0) {
          formData.append("target_languages", JSON.stringify(selectedLanguages));
        }

        const project = await createProject(formData);

        setToastMessage("Project created successfully!");
        setToastType("success");
        setShowToast(true);

        // Navigate to the new project detail page
        setTimeout(() => {
          router.push(`/projects/${project.id}`);
        }, 1000);
      } catch (err: unknown) {
        const message =
          err instanceof Error
            ? err.message
            : "Failed to create project. Please try again.";
        setErrors({ general: message });
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      } finally {
        setIsSubmitting(false);
      }
    },
    [
      validateForm,
      name,
      description,
      runtimeMinutes,
      runtimeSeconds,
      talkingHeadFile,
      transcriptFiles,
      storyboardFile,
      selectedLanguages,
      createProject,
      router,
    ]
  );

  // ── Access Gate: admin and operator only ─────────────────────────────
  if (user?.role === "viewer") {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <h2 className="text-2xl font-bold text-white mb-4">Access Denied</h2>
        <p className="text-gray-400">
          Viewers cannot create new projects. Contact an administrator for access.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-white mb-2">New Project</h1>
      <p className="text-gray-400 mb-8">
        Create a new video project. All fields marked with * are required.
      </p>

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* ── General Error ────────────────────────────────────────── */}
        {errors.general && (
          <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
            {errors.general}
          </div>
        )}

        {/* ── Video Name * ─────────────────────────────────────────── */}
        <div>
          <label
            htmlFor="project-name"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Video Name *
          </label>
          <input
            id="project-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            required
            placeholder="Enter video project name"
            className={`w-full px-4 py-2.5 bg-gray-800 border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.name ? "border-red-500" : "border-gray-600"
            }`}
          />
          <div className="flex justify-between mt-1">
            {errors.name && (
              <span className="text-red-400 text-xs">{errors.name}</span>
            )}
            <span className="text-gray-500 text-xs ml-auto">
              {name.length}/255
            </span>
          </div>
        </div>

        {/* ── Description ──────────────────────────────────────────── */}
        <div>
          <label
            htmlFor="project-description"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Description
          </label>
          <textarea
            id="project-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={1000}
            rows={4}
            placeholder="Optional project description"
            className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
          <span className="text-gray-500 text-xs">{description.length}/1000</span>
        </div>

        {/* ── Maximum Runtime * ─────────────────────────────────────── */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Maximum Runtime * (1–120 minutes)
          </label>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={0}
                max={120}
                value={runtimeMinutes}
                onChange={(e) =>
                  setRuntimeMinutes(
                    Math.max(0, Math.min(120, parseInt(e.target.value) || 0))
                  )
                }
                className={`w-20 px-3 py-2.5 bg-gray-800 border rounded-lg text-white text-center focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  errors.runtime ? "border-red-500" : "border-gray-600"
                }`}
              />
              <span className="text-gray-400 text-sm">min</span>
            </div>
            <span className="text-gray-500">:</span>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={0}
                max={59}
                value={runtimeSeconds}
                onChange={(e) =>
                  setRuntimeSeconds(
                    Math.max(0, Math.min(59, parseInt(e.target.value) || 0))
                  )
                }
                className={`w-20 px-3 py-2.5 bg-gray-800 border rounded-lg text-white text-center focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  errors.runtime ? "border-red-500" : "border-gray-600"
                }`}
              />
              <span className="text-gray-400 text-sm">sec</span>
            </div>
          </div>
          {errors.runtime && (
            <span className="text-red-400 text-xs mt-1 block">
              {errors.runtime}
            </span>
          )}
        </div>

        {/* ── Talking Head Clip * ───────────────────────────────────── */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Talking Head Clip * (MP4/MOV, max 500 MB)
          </label>
          <AssetUploader
            accept={TALKING_HEAD_ACCEPT}
            maxSize={MAX_TALKING_HEAD_SIZE}
            onFileSelect={(files) => {
              if (files && files.length > 0) setTalkingHeadFile(files[0]);
            }}
            selectedFile={talkingHeadFile}
            onRemove={() => setTalkingHeadFile(null)}
            error={errors.talkingHead}
          />
        </div>

        {/* ── Voice Transcripts * ──────────────────────────────────── */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Voice Transcripts * (PDF/DOCX/TXT, at least one)
          </label>
          <div className="mb-3">
            <input
              ref={transcriptInputRef}
              type="file"
              accept={TRANSCRIPT_ACCEPT}
              multiple
              onChange={(e) => handleTranscriptSelect(e.target.files)}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => transcriptInputRef.current?.click()}
              className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
            >
              + Add Transcript Files
            </button>
          </div>

          {/* Transcript Order — Drag-and-Drop Reorder List */}
          {transcriptFiles.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-500">
                Drag and drop to set transcript processing order:
              </p>
              {transcriptFiles.map((tf, index) => (
                <div
                  key={tf.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, index)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, index)}
                  className={`flex items-center gap-3 px-4 py-2.5 bg-gray-800 border rounded-lg cursor-grab active:cursor-grabbing transition-colors ${
                    dragIndex === index
                      ? "border-blue-500 bg-gray-700"
                      : "border-gray-600"
                  }`}
                >
                  <span className="text-gray-500 text-sm font-mono w-6">
                    {index + 1}.
                  </span>
                  <svg
                    className="w-4 h-4 text-gray-500 flex-shrink-0"
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
                  <span className="text-white text-sm truncate flex-1">
                    {tf.file.name}
                  </span>
                  <span className="text-gray-500 text-xs">
                    {(tf.file.size / 1024).toFixed(1)} KB
                  </span>
                  <button
                    type="button"
                    onClick={() => handleRemoveTranscript(tf.id)}
                    className="text-gray-500 hover:text-red-400 transition-colors"
                    title="Remove transcript"
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
              ))}
            </div>
          )}
          {errors.transcripts && (
            <span className="text-red-400 text-xs mt-1 block">
              {errors.transcripts}
            </span>
          )}
        </div>

        {/* ── Existing Storyboard (optional) ───────────────────────── */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Existing Storyboard (PDF/DOCX, optional)
          </label>
          <AssetUploader
            accept={STORYBOARD_ACCEPT}
            onFileSelect={(files) => {
              if (files && files.length > 0) setStoryboardFile(files[0]);
            }}
            selectedFile={storyboardFile}
            onRemove={() => setStoryboardFile(null)}
          />
        </div>

        {/* ── Target Languages ─────────────────────────────────────── */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Target Languages (optional at creation)
          </label>
          <div className="flex flex-wrap gap-2">
            {TARGET_LANGUAGES.map((lang) => {
              const isSelected = selectedLanguages.includes(lang.code);
              return (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => handleLanguageToggle(lang.code)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors border ${
                    isSelected
                      ? "bg-blue-600 border-blue-500 text-white"
                      : "bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-500 hover:text-gray-300"
                  }`}
                >
                  {lang.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Submit ───────────────────────────────────────────────── */}
        <div className="flex items-center gap-4 pt-4 border-t border-gray-700">
          <button
            type="submit"
            disabled={isSubmitting}
            className="px-8 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <LoadingSpinner size="sm" />
                Creating…
              </span>
            ) : (
              "Create Project"
            )}
          </button>
          <button
            type="button"
            onClick={() => router.push("/gallery")}
            className="px-6 py-3 text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>

      {/* ── Toast ──────────────────────────────────────────────────── */}
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
