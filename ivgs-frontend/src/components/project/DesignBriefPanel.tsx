"use client";

import React from "react";

import { useDesignReview } from "@/hooks/useDesignReview";
import type { ArcRow, DesignFinding, OutcomeCoverage } from "@/hooks/useDesignReview";

/**
 * THE DESIGN BRIEF — what a storyboard gate was always supposed to show.
 *
 * WP-IVGS-12 Task 5. Instructional Design Foundation §7: the reviewer sees,
 * BEFORE ANY PIXEL IS RENDERED, the outcomes with any refinement to approve,
 * the event arc, the outcomes × scenes × evidence matrix, every rewrite diffed
 * against its source span, every drop with its reason, and the modality
 * rationale per scene. Approving this is approving a course design, which is
 * what a storyboard gate was always for.
 *
 * ⛔ THE TWO-LIMB DISCIPLINE IS WP-IVGS-10's AND IT IS UNCHANGED HERE.
 * `refuse` is objective and is shown in red before the buttons; `flag` is a
 * judgment, blocks nothing, and is shown in amber as information. This
 * component must never render a flag as a verdict — the reviewer is the judge.
 *
 * The existing depicts-narration completeness panel remains BENEATH this one.
 * They answer different questions: this one asks whether the course is designed,
 * that one asks whether each visual depicts its own narration.
 */

const EVENT_ORDER = [
  "hook", "objective", "recall_prior", "present", "guide",
  "practice", "feedback", "assess", "transfer",
];

const ASSESSING = new Set(["practice", "assess"]);

function EventArc({ arc }: { arc: ArcRow[] }): React.ReactElement {
  const present = new Set(arc.map((s) => s.instructional_event ?? ""));
  return (
    <div className="mt-2">
      <div className="flex flex-wrap gap-1">
        {EVENT_ORDER.map((event) => {
          const used = present.has(event);
          return (
            <span
              key={event}
              className={
                used
                  ? "rounded bg-emerald-600/15 px-2 py-0.5 text-[11px] font-medium text-emerald-900 dark:bg-emerald-400/15 dark:text-emerald-200"
                  : "rounded bg-neutral-500/10 px-2 py-0.5 text-[11px] text-neutral-500 line-through dark:text-neutral-500"
              }
              title={used ? `${event}: present in the arc` : `${event}: no scene performs this event`}
            >
              {event}
            </span>
          );
        })}
      </div>
      <p className="mt-1 text-[11px] text-amber-800/70 dark:text-amber-300/70">
        Gagné&apos;s nine events. A design drawn entirely from the first five has
        demonstrated without ever asking the learner to apply.
      </p>
    </div>
  );
}

function CoverageMatrix({
  coverage,
  arc,
}: {
  coverage: OutcomeCoverage[];
  arc: ArcRow[];
}): React.ReactElement {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="text-amber-900/70 dark:text-amber-200/70">
            <th className="py-1 pr-3 font-medium">Outcome</th>
            <th className="py-1 pr-3 font-medium">Bloom</th>
            <th className="py-1 pr-3 font-medium">Served by</th>
            <th className="py-1 pr-3 font-medium">Assessed by</th>
          </tr>
        </thead>
        <tbody>
          {coverage.map((row) => (
            <tr key={row.outcome_id} className="align-top">
              <td className="py-1 pr-3">
                <span className="font-mono text-[11px]">{row.outcome_id}</span>{" "}
                <span className="text-amber-900 dark:text-amber-100">{row.text}</span>
                {!row.measurable && row.proposed_refinement && (
                  <div className="mt-1 rounded border border-amber-500/40 bg-amber-500/5 p-2">
                    <div className="text-[11px] font-semibold text-amber-900 dark:text-amber-200">
                      Not stated measurably. An ABCD refinement is PROPOSED for your
                      approval and has NOT been applied — the design was made against
                      your words as written.
                    </div>
                    <div className="mt-1 text-[11px] italic text-amber-900/80 dark:text-amber-200/80">
                      {row.proposed_refinement}
                    </div>
                  </div>
                )}
              </td>
              <td className="py-1 pr-3 font-mono text-[11px]">{row.bloom_level ?? "—"}</td>
              <td className={row.served ? "py-1 pr-3" : "py-1 pr-3 font-semibold text-red-700 dark:text-red-300"}>
                {row.served ? row.served_by.join(", ") : "NOTHING"}
              </td>
              <td className={row.assessed ? "py-1 pr-3" : "py-1 pr-3 font-semibold text-red-700 dark:text-red-300"}>
                {row.assessed ? row.assessed_by.join(", ") : "NOTHING"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[11px] text-amber-800/70 dark:text-amber-300/70">
        Serving is not evidence. “Assessed by” counts only scenes whose event is{" "}
        {[...ASSESSING].join(" or ")} — deciding what would PROVE an outcome is a
        separate question from teaching it, and it is asked separately here.
        {arc.length > 0 && ` ${arc.length} scenes in this design.`}
      </p>
    </div>
  );
}

/** WP-IVGS-12i. One declared repair, as `storyboard_repair.Correction` writes it. */
interface SystemCorrectionRow {
  scene_index: number;
  refusal_code: string;
  refusal_reason: string;
  media_type_was: string;
  media_type_is: string;
  applied: boolean;
  template?: string | null;
  params?: Record<string, unknown>;
  original_visual_description?: string | null;
  repair_error?: string | null;
}

/** WP-IVGS-12i2 RC-S1. One surplus row removed, recorded in full. */
interface PrunedSceneRow {
  scene_index: number;
  instructional_event?: string | null;
  serves_outcomes?: string[];
  media_type?: string | null;
  narration_text?: string | null;
  updated_at?: string | null;
}

/** One auto-repair pass, as the design brief stores it. */
interface SystemCorrectionsRecord {
  ran_at?: string;
  pruned?: PrunedSceneRow[];
  prune_skipped_because?: string | null;
  scenes?: number;
  refusals_before: number;
  refusals_after: number;
  mechanical_before: number;
  judgment_before: number;
  repaired: number;
  repair_refused: number;
  corrections?: SystemCorrectionRow[];
}

/**
 * WP-IVGS-12i RC-R4. WHAT CODE CORRECTED BEFORE THIS GATE OPENED.
 *
 * The operator's ruling of 2026-08-30 lets code repair a MECHANICAL refusal —
 * one with a deterministic default fix — before a human ever sees it. The whole
 * safety of that rule is this section: a repair that is not declared is a
 * silent correction, and a reviewer approving a storyboard is entitled to know
 * which scenes are as the designer wrote them and which ones code moved.
 *
 * ⛔ THE FAILED REPAIRS RENDER TOO, AND FIRST. When authoring refused, the scene
 * was PUT BACK and its original refusal still stands in the panel below; this
 * says that code tried and what it was told, so the reviewer is not left to
 * infer it from a refusal that looks untouched.
 *
 * Absent (`null`) means the pass never ran — a brief from before this package.
 * A pass that ran and repaired nothing still renders, because "looked and found
 * nothing" and "never looked" are different facts about the same screen.
 */
function SystemCorrections({
  corrections,
}: {
  corrections: SystemCorrectionsRecord | null | undefined;
}): React.ReactElement | null {
  if (!corrections) return null;
  const rows = corrections.corrections ?? [];
  const applied = rows.filter((c) => c.applied);
  const refused = rows.filter((c) => !c.applied);
  const pruned = corrections.pruned ?? [];

  return (
    <div className="mt-3 rounded border border-sky-500/40 bg-sky-500/[0.04] p-2">
      <div className="text-xs font-semibold text-sky-900 dark:text-sky-200">
        System corrections — {applied.length} repaired
        {refused.length > 0 ? `, ${refused.length} could not be` : ""}
      </div>
      <div className="mt-0.5 text-[11px] text-sky-900/80 dark:text-sky-200/80">
        {corrections.refusals_before} hard refusal
        {corrections.refusals_before === 1 ? "" : "s"} before the pass,{" "}
        {corrections.refusals_after} after ·{" "}
        {corrections.mechanical_before} mechanical ·{" "}
        {corrections.judgment_before} judgment, left for you. Original visual
        descriptions are preserved; nothing below was rewritten.
      </div>

      {/* ── RC-S1. ROWS THAT WERE REMOVED, AND WHAT THEY SAID ──────────
          A scene that vanishes without a trace is the silent correction this
          whole section exists to forbid — and a reviewer who remembers a scene
          that is no longer there is owed the reason. The full narration is
          kept so the removal can be checked rather than trusted. */}
      {pruned.length > 0 && (
        <div className="mt-2 rounded border border-slate-400/50 bg-slate-500/5 p-1.5">
          <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-200">
            {pruned.length} surplus scene{pruned.length === 1 ? "" : "s"} removed —
            rows from a previous design that survived regeneration
          </div>
          <ul className="mt-1 space-y-1">
            {pruned.map((p) => (
              <li
                key={`pruned-${p.scene_index}`}
                className="text-[11px] text-slate-800 dark:text-slate-300"
              >
                <span className="font-medium">Scene {p.scene_index}</span>
                {p.instructional_event ? ` · ${p.instructional_event}` : ""}
                {p.serves_outcomes && p.serves_outcomes.length > 0
                  ? ` · ${p.serves_outcomes.join(", ")}`
                  : ""}
                {p.updated_at ? ` · last written ${p.updated_at}` : ""}
                {p.narration_text ? (
                  <div className="mt-0.5 rounded bg-black/5 p-1 italic dark:bg-white/5">
                    {p.narration_text}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      {refused.length > 0 && (
        <ul className="mt-2 space-y-1">
          {refused.map((c) => (
            <li
              key={`fix-refused-${c.scene_index}`}
              className="rounded border border-red-500/40 bg-red-500/5 p-1.5 text-[11px] text-red-900 dark:text-red-200"
            >
              <span className="font-medium">Scene {c.scene_index}</span>{" "}
              <span className="font-mono text-[10px] opacity-60">
                {c.refusal_code}
              </span>{" "}
              — the repair was refused and the scene was left as{" "}
              <span className="font-mono">{c.media_type_was}</span>. Its original
              refusal stands. Authoring said: {c.repair_error}
            </li>
          ))}
        </ul>
      )}

      {applied.length > 0 && (
        <ul className="mt-2 space-y-1">
          {applied.map((c) => (
            <li
              key={`fix-${c.scene_index}`}
              className="text-[11px] text-sky-900 dark:text-sky-200"
            >
              <span className="font-medium">Scene {c.scene_index}</span>{" "}
              <span className="font-mono text-[10px] opacity-60">
                {c.refusal_code}
              </span>{" "}
              — <span className="font-mono">{c.media_type_was}</span> →{" "}
              <span className="font-mono">{c.media_type_is}</span>, drawn by{" "}
              <span className="font-mono">{c.template ?? "—"}</span>
              {c.params && Object.keys(c.params).length > 0
                ? ` (${Object.entries(c.params)
                    .map(([k, v]) => `${k}=${String(v)}`)
                    .join(", ")})`
                : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Findings({ findings }: { findings: DesignFinding[] }): React.ReactElement | null {
  const refusals = findings.filter((f) => f.severity === "refuse");
  const flags = findings.filter((f) => f.severity === "flag");
  if (refusals.length === 0 && flags.length === 0) return null;

  const label = (f: DesignFinding) =>
    f.scene_index !== null && f.scene_index !== undefined
      ? `Scene ${f.scene_index}`
      : f.outcome_id
        ? `Outcome ${f.outcome_id}`
        : "This design";

  return (
    <div className="mt-3 space-y-2">
      {refusals.length > 0 && (
        <div className="rounded border border-red-500/50 bg-red-500/5 p-2">
          <div className="text-xs font-semibold text-red-800 dark:text-red-300">
            {refusals.length} design {refusals.length === 1 ? "refusal" : "refusals"} —
            objectively checkable, and yours to resolve before approving
          </div>
          <ul className="mt-1 space-y-0.5">
            {refusals.map((f, i) => (
              <li key={`${f.code}-${i}`} className="text-[11px] text-red-900 dark:text-red-200">
                <span className="font-medium">{label(f)}</span>{" "}
                <span className="font-mono text-[10px] opacity-60">{f.code}</span> — {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {flags.length > 0 && (
        <div className="rounded border border-amber-500/40 bg-amber-500/5 p-2">
          <div className="text-xs font-semibold text-amber-900 dark:text-amber-200">
            {flags.length} {flags.length === 1 ? "flag" : "flags"} — information, not a verdict.
            These block nothing.
          </div>
          <ul className="mt-1 space-y-0.5">
            {flags.map((f, i) => (
              <li key={`${f.code}-${i}`} className="text-[11px] text-amber-900 dark:text-amber-200">
                <span className="font-medium">{label(f)}</span>{" "}
                <span className="font-mono text-[10px] opacity-60">{f.code}</span> — {f.message}
                {f.code === "UNDECLARED_SCRIPT_GAP" && typeof f.detail?.text === "string" && (
                  <div className="mt-0.5 rounded bg-black/5 p-1 font-mono text-[10px] dark:bg-white/5">
                    “{f.detail.text as string}”
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function DesignBriefPanel({
  projectId,
}: {
  projectId: string;
}): React.ReactElement | null {
  const { review, isLoading } = useDesignReview(projectId);

  if (isLoading || !review) return null;

  if (!review.has_brief) {
    return (
      <div className="mt-3 rounded border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-900/80 dark:text-amber-200/80">
        No design brief. This storyboard was authored before the Design Core, or by a
        prompt earlier than v8, so there are no declared outcomes, sources or evidence
        to review. The depicts-narration checks below still apply.
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/[0.03] p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
          Design brief — you are approving a course design
        </h3>
        <span className="font-mono text-[10px] text-amber-800/60 dark:text-amber-300/60">
          {review.brief?.contract_version ?? "—"} · {review.brief?.model_used ?? "—"}
          {review.brief?.prompt_fingerprint ? ` · ${review.brief.prompt_fingerprint}` : ""}
        </span>
      </div>

      <EventArc arc={review.event_arc} />
      <CoverageMatrix coverage={review.coverage} arc={review.event_arc} />
      <SystemCorrections
        corrections={
          (review.brief?.system_corrections as
            | SystemCorrectionsRecord
            | null
            | undefined) ?? null
        }
      />
      <Findings findings={review.findings} />

      {review.rewrites.length > 0 && (
        <div className="mt-3">
          <h4 className="text-xs font-semibold text-amber-900 dark:text-amber-200">
            {review.rewrites.length} narration{" "}
            {review.rewrites.length === 1 ? "rewrite" : "rewrites"}, each beside the
            script&apos;s own words
          </h4>
          <div className="mt-1 space-y-2">
            {review.rewrites.map((r) => (
              <div key={r.scene_index} className="rounded border border-amber-500/30 p-2">
                <div className="text-[11px] font-medium text-amber-900 dark:text-amber-200">
                  Scene {r.scene_index}
                  {r.reason ? ` — ${r.reason}` : ""}
                </div>
                <div className="mt-1 grid gap-2 md:grid-cols-2">
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-amber-800/60 dark:text-amber-300/60">
                      The script said
                    </div>
                    <div className="text-[11px] text-neutral-700 dark:text-neutral-300">
                      {r.original ?? "— not carried —"}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-amber-800/60 dark:text-amber-300/60">
                      The design says
                    </div>
                    <div className="text-[11px] text-neutral-900 dark:text-neutral-100">
                      {r.rewritten ?? ""}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {review.dropped_beats.length > 0 && (
        <div className="mt-3">
          <h4 className="text-xs font-semibold text-amber-900 dark:text-amber-200">
            {review.dropped_beats.length} beat
            {review.dropped_beats.length === 1 ? "" : "s"} consciously dropped
          </h4>
          <ul className="mt-1 space-y-1">
            {review.dropped_beats.map((b, i) => (
              <li key={i} className="text-[11px] text-amber-900 dark:text-amber-200">
                <span className="font-medium">{b.summary ?? "(no summary)"}</span> —{" "}
                {b.reason ?? "(no reason given)"}
                {b.span?.quote && (
                  <div className="mt-0.5 rounded bg-black/5 p-1 font-mono text-[10px] dark:bg-white/5">
                    “{b.span.quote}”
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3">
        <h4 className="text-xs font-semibold text-amber-900 dark:text-amber-200">
          Modality, scene by scene
        </h4>
        <ul className="mt-1 space-y-0.5">
          {review.event_arc.map((s) => (
            <li key={s.scene_index} className="text-[11px] text-amber-900/90 dark:text-amber-200/90">
              <span className="font-mono">{String(s.scene_index).padStart(2, "0")}</span>{" "}
              <span className="font-medium">{s.instructional_event ?? "—"}</span>{" "}
              <span className="opacity-70">/ {s.media_type ?? "—"}</span>
              {s.serves_outcomes.length > 0 && (
                <span className="opacity-70"> → {s.serves_outcomes.join(", ")}</span>
              )}
              {s.media_rationale ? <> — {s.media_rationale}</> : <> — <em>no rationale recorded</em></>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
