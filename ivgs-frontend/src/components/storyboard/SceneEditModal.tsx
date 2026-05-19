"use client";

import React, { useState, useCallback, useEffect, useRef, useMemo } from "react";
import type {
  Scene,
  SceneStatus,
  MediaType,
  CameraAngle,
  TransitionType,
  SceneEffect,
  SceneUpdatePayload,
} from "@/types/storyboard";

/**
 * §8.1.3 Storyboard Tab — Scene Detail Modal
 *
 * Full editing modal for a single scene. All scene properties are editable:
 * - narration_text: Full narration text for this scene
 * - visual_description: Description for image/video generation
 * - media_type: IMAGE / VIDEO / ANIMATION / TALKING_HEAD / STOCK
 * - duration_seconds: Scene duration (0.5 – 120 seconds)
 * - camera_angle: Camera angle/shot type for visual generation
 * - transition_type: Transition to next scene (CUT / FADE / DISSOLVE / etc.)
 * - effects: Array of visual effects applied to this scene
 * - timing_offset_ms: Timing offset from start of video in milliseconds
 * - generation_params: JSON object for AI generation parameters
 *
 * The modal also displays read-only metadata:
 * - Scene index, status, creation/update timestamps
 * - Thumbnail preview
 * - Generation prompt ID (for traceability per §9.3)
 *
 * Actions:
 * - Save: PATCHes scene via API
 * - Regenerate: Triggers scene regeneration via API
 * - Cancel: Closes modal without saving
 *
 * Keyboard accessibility:
 * - Escape closes the modal
 * - Tab cycles through form fields
 * - Enter in non-textarea fields submits the form
 */

/** Available camera angles for the dropdown */
const CAMERA_ANGLES: CameraAngle[] = [
  "WIDE",
  "MEDIUM",
  "CLOSE_UP",
  "EXTREME_CLOSE_UP",
  "BIRD_EYE",
  "LOW_ANGLE",
  "HIGH_ANGLE",
  "DUTCH_ANGLE",
  "OVER_THE_SHOULDER",
  "POV",
];

/** Available transition types for the dropdown */
const TRANSITION_TYPES: TransitionType[] = [
  "CUT",
  "FADE_IN",
  "FADE_OUT",
  "CROSS_DISSOLVE",
  "WIPE_LEFT",
  "WIPE_RIGHT",
  "ZOOM_IN",
  "ZOOM_OUT",
  "SLIDE_LEFT",
  "SLIDE_RIGHT",
  "NONE",
];

/** Available visual effects (multi-select checkboxes) */
const AVAILABLE_EFFECTS: SceneEffect[] = [
  "KEN_BURNS",
  "PAN_LEFT",
  "PAN_RIGHT",
  "ZOOM_SLOW",
  "ZOOM_FAST",
  "PARALLAX",
  "VIGNETTE",
  "COLOR_GRADE_WARM",
  "COLOR_GRADE_COOL",
  "BLUR_BACKGROUND",
  "DEPTH_OF_FIELD",
  "LETTERBOX",
];

/** Available media types per Table 9-2 */
const MEDIA_TYPES: { value: MediaType; label: string; description: string }[] = [
  {
    value: "IMAGE",
    label: "Image",
    description: "Static image generated via FLUX.1/SDXL (§7.1.3)",
  },
  {
    value: "VIDEO",
    label: "Video Clip",
    description: "Short video via CogVideoX/Wan2.1 (§7.1.4)",
  },
  {
    value: "ANIMATION",
    label: "Animation",
    description: "Motion graphics via Remotion/AnimateDiff (§7.1.8)",
  },
  {
    value: "TALKING_HEAD",
    label: "Talking Head",
    description: "Lip-synced presenter via LatentSync/SadTalker (§7.1.7)",
  },
  {
    value: "STOCK",
    label: "Stock",
    description: "User-uploaded stock footage or image",
  },
];

interface SceneEditModalProps {
  /** Scene to edit */
  scene: Scene;
  /** Whether the user can edit (false = view-only) */
  canEdit: boolean;
  /** Save callback: receives scene ID and update payload */
  onSave: (sceneId: string, updates: Partial<Scene>) => Promise<void>;
  /** Close modal callback */
  onClose: () => void;
  /** Regenerate scene callback */
  onRegenerate: (sceneId: string) => Promise<void>;
}

export default function SceneEditModal({
  scene,
  canEdit,
  onSave,
  onClose,
  onRegenerate,
}: SceneEditModalProps): React.ReactElement {
  // ── Form State ────────────────────────────────────────────────────────
  const [narrationText, setNarrationText] = useState<string>(
    scene.narration_text
  );
  const [visualDescription, setVisualDescription] = useState<string>(
    scene.visual_description ?? ""
  );
  const [mediaType, setMediaType] = useState<MediaType>(scene.media_type);
  const [durationSeconds, setDurationSeconds] = useState<number>(
    scene.duration_seconds ?? 5
  );
  const [cameraAngle, setCameraAngle] = useState<CameraAngle | "">(
    scene.camera_angle ?? ""
  );
  const [transitionType, setTransitionType] = useState<TransitionType>(
    scene.transition_type ?? "CUT"
  );
  const [effects, setEffects] = useState<SceneEffect[]>(
    scene.effects ?? []
  );
  const [timingOffsetMs, setTimingOffsetMs] = useState<number>(
    scene.timing_offset_ms ?? 0
  );
  const [generationParams, setGenerationParams] = useState<string>(
    scene.generation_params
      ? JSON.stringify(scene.generation_params, null, 2)
      : "{}"
  );

  // ── UI State ──────────────────────────────────────────────────────────
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"content" | "visual" | "timing" | "advanced">(
    "content"
  );

  // ── Refs ──────────────────────────────────────────────────────────────
  const modalRef = useRef<HTMLDivElement>(null);
  const narrationRef = useRef<HTMLTextAreaElement>(null);

  /** Focus narration field on mount */
  useEffect(() => {
    narrationRef.current?.focus();
  }, []);

  /** Handle escape key to close modal */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  /** Handle click outside modal to close */
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): void => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose]
  );

  /** Validate generation params JSON */
  const validateJson = useCallback((value: string): boolean => {
    try {
      JSON.parse(value);
      setJsonError(null);
      return true;
    } catch {
      setJsonError("Invalid JSON syntax");
      return false;
    }
  }, []);

  /** Handle generation params change with validation */
  const handleGenerationParamsChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>): void => {
      const value = e.target.value;
      setGenerationParams(value);
      validateJson(value);
    },
    [validateJson]
  );

  /** Toggle a visual effect in the effects array */
  const handleToggleEffect = useCallback(
    (effect: SceneEffect): void => {
      setEffects((prev) => {
        if (prev.includes(effect)) {
          return prev.filter((e) => e !== effect);
        }
        return [...prev, effect];
      });
    },
    []
  );

  /**
   * Check if form has unsaved changes.
   */
  const hasChanges = useMemo<boolean>(() => {
    return (
      narrationText !== scene.narration_text ||
      visualDescription !== (scene.visual_description ?? "") ||
      mediaType !== scene.media_type ||
      durationSeconds !== (scene.duration_seconds ?? 5) ||
      cameraAngle !== (scene.camera_angle ?? "") ||
      transitionType !== (scene.transition_type ?? "CUT") ||
      JSON.stringify(effects) !== JSON.stringify(scene.effects ?? []) ||
      timingOffsetMs !== (scene.timing_offset_ms ?? 0) ||
      generationParams !==
        (scene.generation_params
          ? JSON.stringify(scene.generation_params, null, 2)
          : "{}")
    );
  }, [
    narrationText,
    visualDescription,
    mediaType,
    durationSeconds,
    cameraAngle,
    transitionType,
    effects,
    timingOffsetMs,
    generationParams,
    scene,
  ]);

  /**
   * Save form data to API.
   */
  const handleSave = useCallback(async (): Promise<void> => {
    if (!canEdit || isSaving) return;
    if (!validateJson(generationParams)) return;

    setSaveError(null);
    setIsSaving(true);

    try {
      const updates: SceneUpdatePayload = {
        narration_text: narrationText.trim(),
        visual_description: visualDescription.trim() || null,
        media_type: mediaType,
        duration_seconds: durationSeconds,
        camera_angle: cameraAngle || null,
        transition_type: transitionType,
        effects: effects.length > 0 ? effects : null,
        timing_offset_ms: timingOffsetMs,
        generation_params: JSON.parse(generationParams),
      };

      await onSave(scene.id, updates as Partial<Scene>);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to save scene";
      setSaveError(message);
    } finally {
      setIsSaving(false);
    }
  }, [
    canEdit,
    isSaving,
    generationParams,
    narrationText,
    visualDescription,
    mediaType,
    durationSeconds,
    cameraAngle,
    transitionType,
    effects,
    timingOffsetMs,
    onSave,
    scene.id,
    validateJson,
  ]);

  /**
   * Trigger scene regeneration.
   * POST /api/v1/projects/{id}/scenes/{sid}/regenerate
   */
  const handleRegenerate = useCallback(async (): Promise<void> => {
    if (!canEdit || isRegenerating) return;
    const confirmed = window.confirm(
      "Regenerate this scene? Existing generated assets will be replaced."
    );
    if (!confirmed) return;

    setIsRegenerating(true);
    try {
      await onRegenerate(scene.id);
      onClose();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Regeneration failed";
      setSaveError(message);
    } finally {
      setIsRegenerating(false);
    }
  }, [canEdit, isRegenerating, onRegenerate, scene.id, onClose]);

  /**
   * Format a timestamp to a human-readable string.
   */
  const formatTimestamp = (ts: string | null | undefined): string => {
    if (!ts) return "—";
    return new Date(ts).toLocaleString();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="scene-edit-title"
    >
      <div
        ref={modalRef}
        className="bg-gray-800 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden border border-gray-700"
      >
        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-sm font-bold text-white">
              {scene.scene_index + 1}
            </span>
            <h2
              id="scene-edit-title"
              className="text-lg font-semibold text-white"
            >
              {canEdit ? "Edit Scene" : "View Scene"}
            </h2>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                scene.status === "COMPLETE"
                  ? "bg-green-500/20 text-green-400"
                  : scene.status === "ERROR"
                  ? "bg-red-500/20 text-red-400"
                  : scene.status === "GENERATING" || scene.status === "REGENERATING"
                  ? "bg-blue-500/20 text-blue-400"
                  : "bg-gray-500/20 text-gray-400"
              }`}
            >
              {scene.status}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
            aria-label="Close modal"
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
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* ── Tab Navigation ─────────────────────────────────────── */}
        <div className="flex border-b border-gray-700 px-6">
          {(
            [
              { key: "content", label: "Content" },
              { key: "visual", label: "Visual" },
              { key: "timing", label: "Timing" },
              { key: "advanced", label: "Advanced" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Scrollable Body ────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* ── Content Tab ───────────────────────────────────── */}
          {activeTab === "content" && (
            <>
              {/* Narration Text */}
              <div>
                <label
                  htmlFor="narration-text"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Narration Text
                  <span className="text-red-400 ml-1">*</span>
                </label>
                <textarea
                  id="narration-text"
                  ref={narrationRef}
                  value={narrationText}
                  onChange={(e) => setNarrationText(e.target.value)}
                  rows={5}
                  disabled={!canEdit}
                  placeholder="Enter the narration text for this scene…"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed resize-y"
                />
                <p className="mt-1 text-xs text-gray-500">
                  {narrationText.length} characters
                </p>
              </div>

              {/* Visual Description */}
              <div>
                <label
                  htmlFor="visual-description"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Visual Description
                </label>
                <textarea
                  id="visual-description"
                  value={visualDescription}
                  onChange={(e) => setVisualDescription(e.target.value)}
                  rows={3}
                  disabled={!canEdit}
                  placeholder="Describe the visual content for AI generation…"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed resize-y"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Used as the image/video generation prompt input.
                </p>
              </div>

              {/* Media Type */}
              <div>
                <label
                  htmlFor="media-type"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Media Type
                </label>
                <select
                  id="media-type"
                  value={mediaType}
                  onChange={(e) =>
                    setMediaType(e.target.value as MediaType)
                  }
                  disabled={!canEdit}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  {MEDIA_TYPES.map((mt) => (
                    <option key={mt.value} value={mt.value}>
                      {mt.label} — {mt.description}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}

          {/* ── Visual Tab ────────────────────────────────────── */}
          {activeTab === "visual" && (
            <>
              {/* Camera Angle */}
              <div>
                <label
                  htmlFor="camera-angle"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Camera Angle
                </label>
                <select
                  id="camera-angle"
                  value={cameraAngle}
                  onChange={(e) =>
                    setCameraAngle(e.target.value as CameraAngle | "")
                  }
                  disabled={!canEdit}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  <option value="">None (default)</option>
                  {CAMERA_ANGLES.map((angle) => (
                    <option key={angle} value={angle}>
                      {angle.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>

              {/* Transition Type */}
              <div>
                <label
                  htmlFor="transition-type"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Transition to Next Scene
                </label>
                <select
                  id="transition-type"
                  value={transitionType}
                  onChange={(e) =>
                    setTransitionType(e.target.value as TransitionType)
                  }
                  disabled={!canEdit}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  {TRANSITION_TYPES.map((tt) => (
                    <option key={tt} value={tt}>
                      {tt.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>

              {/* Visual Effects (multi-select checkboxes) */}
              <div>
                <span className="block text-sm font-medium text-gray-300 mb-2">
                  Visual Effects
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {AVAILABLE_EFFECTS.map((effect) => (
                    <label
                      key={effect}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors ${
                        effects.includes(effect)
                          ? "border-blue-500 bg-blue-900/20 text-blue-300"
                          : "border-gray-700 bg-gray-900 text-gray-400 hover:border-gray-600"
                      } ${!canEdit ? "opacity-50 cursor-not-allowed" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={effects.includes(effect)}
                        onChange={() => handleToggleEffect(effect)}
                        disabled={!canEdit}
                        className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-blue-500"
                      />
                      <span className="text-xs">
                        {effect.replace(/_/g, " ")}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Thumbnail Preview */}
              {scene.thumbnail_url && (
                <div>
                  <span className="block text-sm font-medium text-gray-300 mb-2">
                    Current Thumbnail
                  </span>
                  <div className="w-full max-w-sm aspect-video bg-gray-900 rounded-lg overflow-hidden">
                    <img
                      src={scene.thumbnail_url}
                      alt={`Scene ${scene.scene_index + 1} thumbnail`}
                      className="w-full h-full object-cover"
                    />
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── Timing Tab ────────────────────────────────────── */}
          {activeTab === "timing" && (
            <>
              {/* Duration */}
              <div>
                <label
                  htmlFor="duration-seconds"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Duration (seconds)
                </label>
                <div className="flex items-center gap-3">
                  <input
                    id="duration-seconds"
                    type="number"
                    min={0.5}
                    max={120}
                    step={0.5}
                    value={durationSeconds}
                    onChange={(e) =>
                      setDurationSeconds(
                        Math.max(0.5, Math.min(120, parseFloat(e.target.value) || 0))
                      )
                    }
                    disabled={!canEdit}
                    className="w-32 px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                  />
                  <input
                    type="range"
                    min={0.5}
                    max={60}
                    step={0.5}
                    value={durationSeconds}
                    onChange={(e) =>
                      setDurationSeconds(parseFloat(e.target.value))
                    }
                    disabled={!canEdit}
                    className="flex-1 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Min 0.5s, max 120s. Current:{" "}
                  {Math.floor(durationSeconds / 60)}:
                  {String(Math.round(durationSeconds % 60)).padStart(2, "0")}
                </p>
              </div>

              {/* Timing Offset */}
              <div>
                <label
                  htmlFor="timing-offset"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Timing Offset (ms)
                </label>
                <input
                  id="timing-offset"
                  type="number"
                  min={0}
                  step={100}
                  value={timingOffsetMs}
                  onChange={(e) =>
                    setTimingOffsetMs(
                      Math.max(0, parseInt(e.target.value, 10) || 0)
                    )
                  }
                  disabled={!canEdit}
                  className="w-48 px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Offset from the start of the video. Automatically computed
                  from scene order if left at 0.
                </p>
              </div>

              {/* Read-only metadata */}
              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-700">
                <div>
                  <span className="block text-xs text-gray-500 mb-1">
                    Created
                  </span>
                  <span className="text-sm text-gray-300">
                    {formatTimestamp(scene.created_at)}
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-gray-500 mb-1">
                    Last Updated
                  </span>
                  <span className="text-sm text-gray-300">
                    {formatTimestamp(scene.updated_at)}
                  </span>
                </div>
              </div>
            </>
          )}

          {/* ── Advanced Tab ──────────────────────────────────── */}
          {activeTab === "advanced" && (
            <>
              {/* Generation Parameters (JSON) */}
              <div>
                <label
                  htmlFor="generation-params"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Generation Parameters (JSON)
                </label>
                <textarea
                  id="generation-params"
                  value={generationParams}
                  onChange={handleGenerationParamsChange}
                  rows={8}
                  disabled={!canEdit}
                  placeholder='{"steps": 50, "cfg_scale": 7.5}'
                  className={`w-full px-3 py-2 bg-gray-900 border rounded-lg text-white text-sm font-mono placeholder-gray-500 focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed resize-y ${
                    jsonError
                      ? "border-red-500 focus:ring-red-500"
                      : "border-gray-700 focus:ring-blue-500"
                  }`}
                />
                {jsonError && (
                  <p className="mt-1 text-xs text-red-400">{jsonError}</p>
                )}
                <p className="mt-1 text-xs text-gray-500">
                  Custom parameters passed to the AI model during generation.
                  Must be valid JSON.
                </p>
              </div>

              {/* Read-only: Generation Prompt ID */}
              {scene.generation_prompt_id && (
                <div>
                  <span className="block text-sm font-medium text-gray-300 mb-1">
                    Generation Prompt ID
                  </span>
                  <div className="px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg">
                    <code className="text-xs text-gray-400 font-mono break-all">
                      {scene.generation_prompt_id}
                    </code>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    Reference to the prompt version used for generation per §9.3
                    (full reproducibility).
                  </p>
                </div>
              )}

              {/* Scene ID */}
              <div>
                <span className="block text-sm font-medium text-gray-300 mb-1">
                  Scene ID
                </span>
                <div className="px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg">
                  <code className="text-xs text-gray-400 font-mono break-all">
                    {scene.id}
                  </code>
                </div>
              </div>
            </>
          )}
        </div>

        {/* ── Footer ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-700 bg-gray-800/50">
          {/* Error display */}
          {saveError && (
            <p className="text-sm text-red-400 mr-4 flex-1">{saveError}</p>
          )}
          {!saveError && <div className="flex-1" />}

          <div className="flex items-center gap-3">
            {canEdit && (
              <button
                onClick={handleRegenerate}
                disabled={
                  isRegenerating ||
                  scene.status === "GENERATING" ||
                  scene.status === "REGENERATING"
                }
                className="px-4 py-2 text-sm font-medium text-yellow-400 bg-yellow-900/20 border border-yellow-700 rounded-lg hover:bg-yellow-900/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isRegenerating ? "Regenerating…" : "Regenerate"}
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
            >
              {canEdit ? "Cancel" : "Close"}
            </button>
            {canEdit && (
              <button
                onClick={handleSave}
                disabled={isSaving || !hasChanges || !!jsonError}
                className="px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? "Saving…" : "Save Changes"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
