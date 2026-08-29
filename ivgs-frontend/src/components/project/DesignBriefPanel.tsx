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
            approving will be refused by name
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
