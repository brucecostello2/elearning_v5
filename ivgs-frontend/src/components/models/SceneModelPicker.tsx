"use client";

import React, { useState } from "react";
import ModelPicker from "@/components/models/ModelPicker";
import { useModelSelections, useSceneSelection } from "@/hooks/useModelSelections";
import { mediaTypeLabel } from "@/lib/scenes";
import type { ModelTier, SelectionCandidate } from "@/types/models";

/**
 * WP-66 Task 4 — a model picker for ONE scene, beside its Media Type.
 *
 * The capability the operator asked for by name, and the schema has supported
 * it since the beginning: `project_model_selections.scene_id` is nullable
 * (`shared/models/model_store.py:365`) and dispatch reads scene-scoped first,
 * project-scoped as fallback (`shared/providers/factory.py:147-151`). Nothing
 * ever wrote a scene-scoped row.
 *
 * MEDIUM, DESCRIPTION AND MODEL ARE THE THREE THINGS A SCENE BINDS, and the
 * modal now makes all three legible together. Changing Media Type changes the
 * stage this picker asks about, so the candidate list changes with it -- an
 * animation scene offers animation models. The mapping is server-side
 * (`selection_panel.MEDIA_TYPE_STAGE`) so the two cannot drift.
 */
export default function SceneModelPicker({
  projectId,
  sceneId,
  mediaType,
  canEdit,
  tier = "production",
}: {
  projectId: string;
  sceneId: string;
  /** The medium currently selected in the modal, NOT the saved one -- the
   *  picker follows what the user is about to save. */
  mediaType: string;
  canEdit: boolean;
  tier?: ModelTier;
}): React.ReactElement {
  const { binding, isLoading, error, refresh } = useSceneSelection(
    projectId,
    sceneId,
    mediaType || "image",
    tier,
  );
  const { select, clearScene } = useModelSelections(projectId, tier);
  const [busy, setBusy] = useState<boolean>(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const doSelect = async (
    candidate: SelectionCandidate,
    rationale: string,
  ): Promise<void> => {
    if (!binding) return;
    setNotice(null);
    setFailure(null);
    try {
      setBusy(true);
      await select({
        stage: binding.stage,
        tier: binding.tier,
        modelId: candidate.id,
        rationale: rationale.trim() || "operator selection",
        sceneId,
      });
      await refresh();
      setNotice(
        `This scene now uses ${candidate.display_name}. Its siblings are ` +
          `unchanged and still follow the project binding.`,
      );
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail as
        | { error?: { code?: string; message?: string } }
        | string
        | undefined;
      setFailure(
        typeof detail === "string"
          ? detail
          : (detail?.error?.message ?? (e as Error).message),
      );
    } finally {
      setBusy(false);
    }
  };

  const doClear = async (): Promise<void> => {
    if (!binding) return;
    setNotice(null);
    setFailure(null);
    try {
      setBusy(true);
      const res = await clearScene({
        stage: binding.stage,
        tier: binding.tier,
        sceneId,
      });
      await refresh();
      setNotice(res.message);
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (isLoading) {
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Loading this scene&apos;s model binding…
      </p>
    );
  }
  if (error || !binding) {
    return (
      <p className="text-xs text-amber-700 dark:text-amber-400">
        Could not load this scene&apos;s model binding
        {error ? `: ${error.message}` : ""}. The scene will still render on the
        project binding.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {notice && (
        <div className="rounded border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 px-2 py-1 text-xs text-green-800 dark:text-green-300">
          {notice}
        </div>
      )}
      {failure && (
        <div className="rounded border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 px-2 py-1 text-xs text-red-800 dark:text-red-300">
          {failure}
        </div>
      )}
      <ModelPicker
        binding={binding}
        busy={busy || !canEdit}
        /* WP-IVGS-09b. THE TITLE NAMES THE MEDIUM FIRST, and this is not
           cosmetic: `binding.stage` alone is what the defect report quoted --
           "the picker keeps image generation". It said `image_generation` for a
           motion-graphics scene because the medium was unmapped server-side and
           fell back. With that fixed the stage reads `animation_generation`,
           which is CORRECT to AD-01 (motion graphics are an animation-stage
           family) and would read as still-wrong to an operator who just chose
           "Motion Graphics". Both facts are shown, medium first, because the
           medium is what they picked and the stage is what the selection is
           keyed by. */
        title={`Model for this scene · ${mediaTypeLabel(mediaType)} (${binding.stage})`}
        onSelect={doSelect}
        onUseDefault={doClear}
        inheritedName={
          binding.provenance === "scene" ? null : binding.model_display_name
        }
      />
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Medium, description and model are the three things this scene binds.
        Changing the Media Type above changes which models are offered here.
        {mediaType === "motion_graphics" || mediaType === "animation" ? (
          <>
            {" "}
            <span className="text-gray-600 dark:text-gray-300">
              Animation and Motion Graphics share the{" "}
              <code>animation_generation</code> stage and are offered{" "}
              <strong>different</strong> models: Wan2.2-Animate reenacts a
              person, and a motion-graphics template draws numbers. Neither can
              do the other&apos;s job, so neither is listed for it.
            </span>
          </>
        ) : null}
      </p>
    </div>
  );
}
