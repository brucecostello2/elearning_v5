import useSWR from "swr";
import { api } from "@/lib/api";

/**
 * The storyboard gate's DESIGN REVIEW — WP-IVGS-12 Task 5.
 *
 * GET /api/v1/projects/{id}/design-review
 *
 * Computed fresh on every read and writing nothing, exactly like the
 * completeness assessment beside it. A stored verdict goes stale the moment a
 * reviewer edits a scene, and this gate exists to be edited against.
 *
 * A project with no design brief — every storyboard authored before this
 * package, and any run of a pre-v8 prompt — returns `has_brief: false` and the
 * panel renders a single explanatory line rather than an empty matrix.
 */

export interface OutcomeCoverage {
  outcome_id: string;
  text: string;
  measurable: boolean;
  proposed_refinement: string | null;
  bloom_level: string | null;
  served_by: number[];
  assessed_by: number[];
  served: boolean;
  assessed: boolean;
}

export interface DesignFinding {
  severity: "refuse" | "flag";
  code: string;
  message: string;
  scene_index: number | null;
  outcome_id: string | null;
  detail: Record<string, unknown>;
}

export interface ArcRow {
  scene_index: number;
  instructional_event: string | null;
  bloom_level: string | null;
  media_type: string | null;
  serves_outcomes: string[];
  media_rationale: string | null;
  scene_origin: string | null;
  narration_text: string | null;
  text_carried_by: string | null;
}

export interface RewriteRow {
  scene_index: number;
  original: string | null;
  rewritten: string | null;
  reason: string | null;
  span: Record<string, unknown> | null;
}

export interface DroppedBeat {
  span?: { start?: number; end?: number; quote?: string };
  summary?: string;
  reason?: string;
}

export interface DesignReview {
  has_brief: boolean;
  brief: {
    id: string;
    contract_version: string | null;
    model_used: string | null;
    prompt_fingerprint: string | null;
    created_at: string;
  } | null;
  event_arc: ArcRow[];
  coverage: OutcomeCoverage[];
  rewrites: RewriteRow[];
  dropped_beats: DroppedBeat[];
  findings: DesignFinding[];
  refusals: number;
  flags: number;
}

export function useDesignReview(projectId: string | null | undefined) {
  // `api.get` returns the ApiResponse envelope, not the payload. Unwrapped
  // here rather than in the component, so the panel never sees `.data.data`.
  const { data, error, isLoading, mutate } = useSWR<DesignReview, Error>(
    projectId ? `/api/v1/projects/${projectId}/design-review` : null,
    async (url: string) => (await api.get<DesignReview>(url)).data,
    { revalidateOnFocus: true, revalidateOnReconnect: true, dedupingInterval: 5000 },
  );

  return {
    review: data ?? null,
    isLoading,
    error,
    refresh: mutate,
  };
}
