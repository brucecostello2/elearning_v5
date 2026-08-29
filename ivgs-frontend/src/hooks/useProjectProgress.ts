import useSWR from "swr";
import { apiClient } from "@/lib/api-client";

/**
 * WP-62 Task 3, RULED. ONE progress computation, polled, feeding every surface.
 *
 * `GET /api/v1/projects/{id}/progress` is the single answer to "where is this
 * project". The top stepper, the per-tab indicators and the Overview run
 * panel's heading all read this hook, so they cannot disagree — which they did:
 * the stepper sat grey at DRAFT on a project whose Jobs tab listed a
 * successful final render, because the stepper read `projects.state` and the
 * Jobs tab read `render_jobs`.
 *
 * WHY `projects.state` COULD NOT BE THE ANSWER. Measured 2026-08-26 on project
 * 64207933: a stale job's failure callback reset the project to DRAFT 400 ms
 * after a storyboard approval, and the three subsequent stage hops were all
 * refused as illegal transitions out of DRAFT while the run carried on. The
 * writer is fixed for new runs; the server recomputes the stepper from
 * `pipeline_checkpoints` so EXISTING projects are true without anybody editing
 * a stored row.
 */

/** The five colours, RULED. */
export type StepStatus =
  | "complete"
  | "active"
  | "failed"
  | "gated"
  | "pending";

export interface ProgressStep {
  /** 1-indexed position. Step 9 is Review — the draft gate's home. */
  index: number;
  key: string;
  label: string;
  status: StepStatus;
  /** "storyboard" | "draft" when this step is a human gate. */
  gate: string | null;
}

export interface GateState {
  gate: string;
  artifact_version: string;
  approved: boolean;
  /** Waiting on a human right now. */
  open: boolean;
  decision: string | null;
  decided_at: string | null;
  decided_by_name: string | null;
  note: string | null;
  /** Words, not a boolean. "approved, but the artifact has changed since"
   *  and "never approved" are different situations. */
  reason: string;
  /** WP-IVGS-10 Task 3. Per-scene completeness, storyboard gate only.
   *
   *  Every scene appears, not only the failing ones: a list showing only
   *  problems cannot be told from a list that was never computed. `severity`
   *  is the load-bearing field — `refuse` means approving will be refused by
   *  name, `flag` blocks nothing and is the reviewer's to judge. */
  completeness?: SceneCompleteness[];
  completeness_refusals?: number;
  completeness_flags?: number;
}

export interface SceneCompleteness {
  scene_index: number;
  media_type: string;
  /** DEPICTS | GENERIC | DELEGATES-TO-WRONG-MEDIUM */
  verdict: string;
  /** ok | flag | refuse */
  severity: string;
  reason: string;
  referents: {
    numerals: string[];
    written: string[];
    quoted: string[];
    changes: string[];
  };
  depicted: string[];
}

export interface ProjectProgress {
  project_id: string;
  /** What `projects.state` holds. */
  stored_state: string;
  /** What the checkpoints and gates say. */
  derived_state: string;
  /** False on every project that ran before WP-62. Shown, not hidden. */
  stored_state_matches: boolean;
  steps: ProgressStep[];
  /** Tab id -> the status its indicator draws. Tabs absent from this map are
   *  not pipeline stages and get no indicator. */
  tabs: Record<string, StepStatus>;
  gates: Record<string, GateState>;
  active_run: {
    id: string;
    job_type: string;
    status: string;
    started_at: string | null;
    step: string | null;
  } | null;
}

const fetcher = async (url: string): Promise<ProjectProgress> => {
  const response = await apiClient.get<ProjectProgress>(url);
  return response.data;
};

export function useProjectProgress(projectId?: string): {
  progress: ProjectProgress | undefined;
  isLoading: boolean;
  error: Error | undefined;
  mutate: () => void;
} {
  const { data, error, isLoading, mutate } = useSWR<ProjectProgress>(
    projectId ? `/api/v1/projects/${projectId}/progress` : null,
    fetcher,
    {
      /* 5 s. The stepper is the thing an operator watches while a stage runs,
         so it polls faster than the 10 s project detail. It is three indexed
         reads and a gate recompute; nothing here writes. */
      refreshInterval: 5000,
      revalidateOnFocus: true,
    }
  );
  return {
    progress: data,
    isLoading,
    error: error as Error | undefined,
    mutate,
  };
}

/** Tailwind classes for a step dot, by status. RULED colours. */
export function stepDotClasses(status: StepStatus): string {
  switch (status) {
    case "complete":
      return "bg-green-600 text-white";
    case "active":
      return "bg-blue-600 text-white ring-4 ring-blue-600/30 animate-pulse";
    case "failed":
      return "bg-red-600 text-white";
    case "gated":
      return "bg-amber-500 text-white ring-4 ring-amber-500/30";
    default:
      return "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400";
  }
}

/** Tailwind classes for the connector to the NEXT step. */
export function stepBarClasses(status: StepStatus): string {
  switch (status) {
    case "complete":
      return "bg-green-600";
    case "failed":
      return "bg-red-600";
    case "gated":
      return "bg-amber-500";
    default:
      return "bg-gray-200 dark:bg-gray-700";
  }
}

/** The small dot a tab shows. Null for tabs that are not a stage. */
export function tabDotClasses(status: StepStatus | undefined): string | null {
  if (!status) return null;
  switch (status) {
    case "complete":
      return "bg-green-600";
    case "active":
      return "bg-blue-600 animate-pulse";
    case "failed":
      return "bg-red-600";
    case "gated":
      return "bg-amber-500";
    default:
      /* Grey is drawn, not omitted: a stage that has not run yet is a real
         state, and leaving the dot off would make "not started" and "not a
         stage" look identical. */
      return "bg-gray-300 dark:bg-gray-600";
  }
}
