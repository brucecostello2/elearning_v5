/**
 * The project lifecycle strip (WP-43 Task 1).
 *
 * WHY THIS EXISTS. The Overview's "Project Timeline" drew four steps --
 * Draft, In Progress, Review, Complete -- and found the current one with
 * `stateTimeline.findIndex((s) => s.state === project.state)`.
 *
 * `IN_PROGRESS` and `REVIEW` are not project states. `ProjectState`
 * (`shared/models/enums.py:15`) is a THIRTEEN-state machine and contains
 * neither. The reference project's live state is `MEDIA_GENERATION`, so
 * `findIndex` returned **-1**, `idx <= currentOrder` was false for every
 * step, and the strip rendered four grey circles for a project that had
 * completed transcript refinement, storyboard generation, audio and a
 * prototype draft. It could only ever have lit up for a project sitting in
 * `DRAFT` or `COMPLETE`.
 *
 * The strip now moves into the shared project shell (so it is visible from
 * every tab) and is drawn against the real FSM.
 *
 * WP-62 Task 3. `PROJECT_STATE_SEQUENCE` and `stateStepStatuses` NO LONGER
 * DRAW THE STRIP, and they are kept rather than deleted for two reasons that
 * are not sentiment.
 *
 * The strip is now computed on the SERVER (`GET /projects/{id}/progress`,
 * `app/services/project_progress.py`) because `project.state` alone could not
 * produce a true answer: it was frozen fleet-wide by the P1.4q reset firing on
 * stale jobs, so a project with a completed final render read DRAFT. The
 * server's step list is the same eleven states in the same order, and
 * `ui-nav.test.mjs` pins THIS list — so it is the client-side statement of the
 * order the server must also hold, and a divergence would show up as a failing
 * test rather than as a strip that quietly renumbered itself.
 *
 * `projectStateProgress` IS still used by the shell, for the off-sequence
 * caption: ERROR and LOCALISATION have no position on the linear path and
 * saying so is still the right answer.
 */

/** The linear path through the FSM, in order. */
export const PROJECT_STATE_SEQUENCE: readonly { state: string; label: string }[] = [
  { state: "DRAFT", label: "Draft" },
  { state: "TRANSCRIPT_REFINEMENT", label: "Transcript" },
  { state: "STORYBOARD_GENERATION", label: "Storyboard" },
  { state: "MEDIA_GENERATION", label: "Media" },
  { state: "MANIFEST_GENERATION", label: "Manifest" },
  { state: "AUDIO_GENERATION", label: "Audio" },
  { state: "TALKING_HEAD_RENDER", label: "Talking Head" },
  { state: "PROTOTYPE_DRAFT", label: "Draft Render" },
  { state: "USER_REVIEW", label: "Review" },
  { state: "FINAL_RENDER", label: "Final Render" },
  { state: "COMPLETE", label: "Complete" },
];

/**
 * States that are real but sit off the linear path.
 *
 * `LOCALISATION` follows COMPLETE for additional languages and `ERROR` can
 * be entered from anywhere. Neither has a position on the strip, and saying
 * so is better than placing them at a rank they do not hold.
 */
export const OFF_SEQUENCE_STATES: readonly string[] = ["LOCALISATION", "ERROR"];

export interface ProjectStateProgress {
  /** Position on the strip, or -1 when the state is not on it. */
  index: number;
  /** The state as given, uppercased; "UNKNOWN" when absent. */
  state: string;
  isError: boolean;
  /** A real state that has no position on the linear strip. */
  isOffSequence: boolean;
}

export function projectStateProgress(state: unknown): ProjectStateProgress {
  const raw =
    typeof state === "string" && state.trim().length > 0
      ? state.trim().toUpperCase()
      : "UNKNOWN";
  const index = PROJECT_STATE_SEQUENCE.findIndex((s) => s.state === raw);
  return {
    index,
    state: raw,
    isError: raw === "ERROR",
    isOffSequence: index === -1 && OFF_SEQUENCE_STATES.includes(raw),
  };
}

export type StepStatus = "done" | "current" | "todo" | "unknown";

/** How each step of the strip should be drawn for a given state. */
export function stateStepStatuses(state: unknown): StepStatus[] {
  const { index } = projectStateProgress(state);
  if (index === -1) {
    return PROJECT_STATE_SEQUENCE.map(() => "unknown");
  }
  return PROJECT_STATE_SEQUENCE.map((_, i) =>
    i < index ? "done" : i === index ? "current" : "todo",
  );
}
