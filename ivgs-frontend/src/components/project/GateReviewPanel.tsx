"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";

import { apiClient } from "@/lib/api-client";
import { useAssets } from "@/hooks/useAssets";
import { useStoryboard } from "@/hooks/useStoryboard";
import { useAssetObjectUrl } from "@/hooks/useAssetMedia";
import { assetRenderKind } from "@/lib/media";
import type { Asset } from "@/types/api";
import type { GateState } from "@/hooks/useProjectProgress";

/**
 * An open human review gate, as the PRIMARY action, with its preview adjacent.
 *
 * WP-62 Task 2(d), RULED. Before this package the storyboard gate's only
 * surface was a green "Approve storyboard" button in the top-right corner of
 * the Storyboard tab, beside the Grid/Timeline view toggle — the same size and
 * weight as a view toggle, on a tab an operator only reaches deliberately. The
 * draft gate had no surface at all: `POST /projects/{id}/trigger` from
 * USER_REVIEW WAS the approval, so approving the draft and spending the GPU
 * time on the final render were one irreversible press with no record.
 *
 * A blocking gate is the single most important thing on the screen while it is
 * open, because nothing moves until somebody acts on it. So it renders as a
 * full-width amber panel above everything else, with the artefact under review
 * beside the decision — an operator must never have to navigate away to see
 * what they are being asked to approve, and then navigate back to approve it.
 *
 * All three §6.4 decisions are offered. Reject and Regenerate were not
 * available anywhere in the application before this package: the only thing a
 * reviewer could do was approve, or do nothing and leave no trace of having
 * looked.
 */

type Decision = "approved" | "rejected" | "regenerate";

const DECISION_LABEL: Record<Decision, string> = {
  approved: "Approve",
  rejected: "Reject",
  regenerate: "Regenerate",
};

const DECISION_HELP: Record<Decision, string> = {
  approved: "Releases the pipeline. This consumes GPU time.",
  rejected:
    "Records that this artefact is not acceptable. Nothing is dispatched and the gate stays open.",
  regenerate:
    "Records that this artefact should be produced again. Nothing is dispatched here; re-run the stage that produced it.",
};

export default function GateReviewPanel({
  projectId,
  gate,
  state,
  canDecide,
  onDecided,
}: {
  projectId: string;
  /** "storyboard" | "draft" */
  gate: string;
  state: GateState;
  /** Operator or admin. A viewer must not be offered a decision. */
  canDecide: boolean;
  onDecided: () => void;
}): React.ReactElement | null {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);

  /* Not open means nothing to do. A closed gate is reported by the stepper's
     green step; a second "approved ✓" panel here would be the duplication
     Task 4 removes elsewhere on this page. */
  if (!state.open) return null;

  const submit = async (decision: Decision): Promise<void> => {
    setBusy(decision);
    setError(null);
    try {
      await apiClient.post(`/api/v1/projects/${projectId}/gates/${gate}`, {
        decision,
        note: note.trim() || null,
      });
      setNote("");
      onDecided();
    } catch (err) {
      /* The server's own wording. A gate refusal says which gate, in which
         state, over which artefact version — none of which this component
         could reconstruct. */
      const detail = (err as { response?: { data?: { detail?: { error?: { message?: string } } } } })
        ?.response?.data?.detail?.error?.message;
      setError(
        detail ??
          (err instanceof Error ? err.message : "The decision was not recorded.")
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-xl border-2 border-amber-400 bg-amber-50 p-5 dark:border-amber-600 dark:bg-amber-950/40">
      <div className="flex flex-col gap-5 lg:flex-row">
        {/* ── The decision ─────────────────────────────────────────── */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-500 text-[11px] font-bold text-white">
              ?
            </span>
            <h2 className="text-lg font-semibold text-amber-900 dark:text-amber-200">
              {gate === "draft"
                ? "Draft review — your decision is required"
                : "Storyboard review — your decision is required"}
            </h2>
          </div>
          <p className="mt-2 text-sm text-amber-900/90 dark:text-amber-200/90">
            {gate === "draft"
              ? "The prototype draft is ready. The full-resolution render will not start until this is approved."
              : "The storyboard is ready. No media generation will start until this is approved."}
          </p>
          <p className="mt-1 text-xs text-amber-800/80 dark:text-amber-300/80">
            {state.reason}
          </p>
          {state.decision && (
            <p className="mt-1 text-xs text-amber-800/80 dark:text-amber-300/80">
              Last decision: <strong>{state.decision}</strong>
              {state.decided_by_name ? ` by ${state.decided_by_name}` : ""}
              {state.decided_at
                ? ` on ${new Date(state.decided_at).toLocaleString()}`
                : ""}
              {state.note ? ` — “${state.note}”` : ""}
            </p>
          )}

          {canDecide ? (
            <>
              <label
                htmlFor={`gate-note-${gate}`}
                className="mt-4 block text-xs font-medium text-amber-900 dark:text-amber-200"
              >
                Note (recorded with the decision and in the audit log)
              </label>
              <textarea
                id={`gate-note-${gate}`}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                maxLength={4000}
                placeholder="Why? A rejection without a reason is a decision nobody can act on."
                className="mt-1 w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 dark:border-amber-700 dark:bg-gray-900 dark:text-gray-100"
              />
              <div className="mt-3 flex flex-wrap gap-2">
                {(["approved", "rejected", "regenerate"] as Decision[]).map(
                  (d) => (
                    <button
                      key={d}
                      type="button"
                      disabled={busy !== null}
                      onClick={() => submit(d)}
                      title={DECISION_HELP[d]}
                      className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                        d === "approved"
                          ? "bg-green-600 text-white hover:bg-green-700"
                          : d === "rejected"
                          ? "bg-red-600 text-white hover:bg-red-700"
                          : "border border-amber-500 bg-white text-amber-800 hover:bg-amber-100 dark:bg-gray-900 dark:text-amber-300"
                      }`}
                    >
                      {busy === d ? "Recording…" : DECISION_LABEL[d]}
                    </button>
                  )
                )}
              </div>
              {error && (
                <p className="mt-2 text-sm text-red-700 dark:text-red-400">
                  {error}
                </p>
              )}
            </>
          ) : (
            <p className="mt-4 text-sm text-amber-800 dark:text-amber-300">
              This decision is an operator or administrator action. You are
              seeing the gate because it explains why the pipeline is not
              moving.
            </p>
          )}
        </div>

        {/* ── The artefact under review, adjacent ──────────────────── */}
        <div className="w-full lg:w-[26rem] lg:shrink-0">
          {gate === "storyboard" ? (
            <StoryboardPreview projectId={projectId} />
          ) : (
            <DraftPreview projectId={projectId} />
          )}
        </div>
      </div>
    </section>
  );
}

/** The first scenes, so a reviewer sees what they are approving. */
function StoryboardPreview({
  projectId,
}: {
  projectId: string;
}): React.ReactElement {
  const { scenes, isLoading } = useStoryboard(projectId);
  const shown = (scenes ?? []).slice(0, 3);
  return (
    <div className="rounded-lg border border-amber-300 bg-white p-3 dark:border-amber-700 dark:bg-gray-900">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Storyboard under review
        </h3>
        <Link
          href={`/projects/${projectId}/storyboard`}
          className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          Open editor →
        </Link>
      </div>
      {isLoading ? (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Loading…</p>
      ) : shown.length === 0 ? (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          No scenes are stored for this project.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {scenes?.length ?? 0} scene{(scenes?.length ?? 0) === 1 ? "" : "s"};
            the first {shown.length} shown.
          </p>
          <ol className="mt-2 space-y-2">
            {shown.map((s) => (
              <li key={s.id} className="text-xs text-gray-700 dark:text-gray-300">
                <span className="font-mono text-gray-400">
                  {s.scene_index}
                </span>{" "}
                {s.narration_text ?? "(no narration)"}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

/** The prototype draft itself, playable in place. */
function DraftPreview({ projectId }: { projectId: string }): React.ReactElement {
  const { assets, isLoading } = useAssets(projectId);
  const draft = useMemo<Asset | null>(
    () =>
      (assets || [])
        .filter((a: Asset) => assetRenderKind(a) === "draft")
        .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0] ?? null,
    [assets]
  );
  /* Same mechanism the Draft Preview tab uses. Drafts and final renders share
     `asset_type: "final_render"` and are told apart by filename prefix
     (`assetRenderKind`) — see that page's header for the measurement. */
  const { url } = useAssetObjectUrl(draft?.id ?? null, draft !== null);

  return (
    <div className="rounded-lg border border-amber-300 bg-white p-3 dark:border-amber-700 dark:bg-gray-900">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Draft under review
        </h3>
        <Link
          href={`/projects/${projectId}/draft`}
          className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          Open full preview →
        </Link>
      </div>
      {isLoading ? (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Loading…</p>
      ) : draft === null ? (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          No prototype draft asset was found for this project.
        </p>
      ) : url ? (
        <video
          src={url}
          controls
          className="mt-2 w-full rounded bg-black"
          preload="metadata"
        />
      ) : (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          Loading the draft…
        </p>
      )}
    </div>
  );
}
