"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { fieldErrors } from "@/lib/errors";
import { useModels } from "@/hooks/useModels";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  ModelApprovePayload,
  ModelRegisterPayload,
  ModelState,
  ModelUpdatePayload,
  ClientState,
  StoreModel,
  WeightState,
} from "@/types/models";
import { MODEL_ENGINES, MODEL_STAGES, MODEL_TIERS } from "@/types/models";

/**
 * AD-01 Model Store — admin GUI for the model/engine registry.
 *
 * Zero-CLI management surface:
 * - GET    /api/v1/models                    — list (operator/admin)
 * - POST   /api/v1/models                    — register (admin)
 * - PATCH  /api/v1/models/{id}               — edit editorial fields (admin)
 * - POST   /api/v1/models/{id}/approve       — CANDIDATE -> APPROVED (admin)
 * - POST   /api/v1/models/{id}/deprecate     — APPROVED -> DEPRECATED (admin)
 * - POST   /api/v1/models/{id}/retire        — -> RETIRED (admin)
 *
 * MBCP-certified models arrive via the AD-04 seam as CANDIDATE rows and are
 * reviewed/approved here. Operators see the registry read-only; admins mutate.
 */

const STATE_BADGE: Record<ModelState, string> = {
  candidate: "bg-yellow-900/50 text-yellow-300 border border-yellow-800",
  approved: "bg-green-900/50 text-green-300 border border-green-800",
  deprecated: "bg-orange-900/50 text-orange-300 border border-orange-800",
  retired: "bg-gray-700/50 text-gray-300 border border-gray-600",
};

/**
 * WP-65 — the weight states, and the ACTION each one implies.
 *
 * Before WP-65 this column was `node_availability.filter(status ===
 * "available").length`, rendered as "N available" or the bare word "none".
 * Those rows are a projection of the GPU scheduler's Redis LRU of models a JOB
 * once loaded (no TTL, so it never expires), which means "none" was standing
 * in for at least four different facts that need four different actions. It
 * also meant the one model the store called available was attributed to the
 * wrong node: measured 2026-08-26, `wan2.2-animate` showed node-04 while its
 * bytes are on node-03.
 *
 * Nothing here fabricates a zero. A model with no measurement says so in
 * words (WP-57/60).
 */
const WEIGHT_BADGE: Record<WeightState, string> = {
  available: "bg-green-900/50 text-green-300 border border-green-800",
  not_fetched: "bg-blue-900/50 text-blue-300 border border-blue-800",
  engine_only: "bg-purple-900/50 text-purple-300 border border-purple-800",
  no_host: "bg-orange-900/50 text-orange-300 border border-orange-800",
  no_reference: "bg-gray-700/50 text-gray-300 border border-gray-600",
  unknown_reference: "bg-red-900/50 text-red-300 border border-red-800",
  fetching: "bg-yellow-900/50 text-yellow-300 border border-yellow-800",
  failed: "bg-red-900/50 text-red-300 border border-red-800",
};

/** What an admin should DO about each state. Shown under the badge. */
const WEIGHT_ACTION: Record<WeightState, string> = {
  available: "",
  not_fetched:
    "IVGS has no record of a fetch for this model. That is a fact about IVGS's records, not proof the node is empty - weights placed by hand before this record existed do not appear here. Fetch weights verifies and records them; an already-present, hash-matching bundle is a no-op that says so.",
  engine_only:
    "MBCP certified the engine image, not a weight bundle. Making this runnable means deploying that image to a node — there is nothing to fetch.",
  no_host:
    "No container on this fleet serves this engine. A host has to exist before weights have anywhere to go.",
  no_reference:
    "This row was registered by hand, not ingested from MBCP, so IVGS has no reference to fetch from.",
  unknown_reference:
    "The stored weights_ref is in a form IVGS cannot parse. Refused rather than guessed at.",
  fetching: "A fetch is running.",
  failed: "The last fetch failed. The reason is recorded on the row.",
};

/**
 * WP-67 Task 5 — the SECOND absence, kept visibly separate from the first.
 *
 * WP-65's Weights column answers "are the bytes here". This answers "does IVGS
 * have code that knows how to call this model". They are independent: the two
 * MBCP animation candidates have neither, `wan2.2-animate` has a client and no
 * recorded fetch, and a model could in principle have bytes and no client.
 * Merging them into one column would put an operator back where WP-65 found
 * them -- one word standing for several different jobs.
 */
const CLIENT_BADGE: Record<ClientState, string> = {
  client_available: "bg-green-900/50 text-green-300 border border-green-800",
  no_client: "bg-red-900/50 text-red-300 border border-red-800",
  family_unknown: "bg-gray-700/50 text-gray-300 border border-gray-600",
};

const CLIENT_ACTION: Record<ClientState, string> = {
  client_available: "",
  no_client:
    "IVGS has no client for this model's family. Fetching weights will not help and neither will deploying an engine: this needs code. It is certified, it may be fetchable, and this system cannot call it.",
  family_unknown:
    "The model's family could not be determined, so no client can be chosen for it. An ingest that carried a family, or a registered name pattern, would resolve it.",
};

/** Bytes, or the honest absence of a measurement. Never "0 B" for unknown. */
function formatBytes(n: number | null): string {
  if (n === null || n === undefined) return "not measured";
  if (n === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const inputCls =
  "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none";
const labelCls = "block text-sm font-medium text-gray-300 mb-1";
const btnPrimary =
  "inline-flex items-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";
const btnSubtle =
  "inline-flex items-center rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm font-medium text-gray-200 hover:bg-gray-700 disabled:opacity-50";

interface RegisterFormState {
  name: string;
  display_name: string;
  stage: string;
  engine: string;
  tier: string;
  description: string;
  source_url: string;
  weights_ref: string;
  weights_checksum: string;
  license: string;
  vram_gb: string;
  dynamically_loadable: boolean;
  default_params: string; // JSON text
}

const EMPTY_REGISTER: RegisterFormState = {
  name: "",
  display_name: "",
  stage: "storyboard_generation",
  engine: "vllm",
  tier: "both",
  description: "",
  source_url: "",
  weights_ref: "",
  weights_checksum: "",
  license: "",
  vram_gb: "",
  dynamically_loadable: true,
  default_params: "{}",
};

interface EditFormState {
  display_name: string;
  description: string;
  source_url: string;
  vram_gb: string;
  default_params: string;
}

interface ApproveFormState {
  attested_by: string;
  vetting_reference: string;
  checklist: string; // JSON text
}

/**
 * WP-43 Task 6a. `parseJsonField` THREW, and every caller's `catch` routed
 * the message to `flashErr` -> the `actionError` banner, which is rendered
 * at page level, at line ~419 -- **underneath the modal's `fixed inset-0`
 * backdrop**. So a checklist that was valid JSON but not an object (an
 * ARRAY, the exact case the operator hit) produced: no inline message, no
 * banner the operator could see, and not even a spinner, because the throw
 * happens before `setBusyId`. The Approve button simply did nothing.
 *
 * The validation itself was right. What was missing was somewhere to say so.
 * `jsonFieldError` returns the message instead of throwing, so each dialog
 * can render it at the field that is wrong; `parseJsonField` keeps the
 * throwing behaviour for the paths that still want it.
 */
function jsonFieldError(text: string, field: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (e) {
    return `${field} is not valid JSON: ${
      e instanceof Error ? e.message : "parse failed"
    }`;
  }
  if (parsed === null) {
    return `${field} must be a JSON object, e.g. {"reviewed": true} — got null.`;
  }
  if (Array.isArray(parsed)) {
    return `${field} must be a JSON object, e.g. {"reviewed": true} — got an array. Wrap the entries in an object, such as {"checks": [...]}.`;
  }
  if (typeof parsed !== "object") {
    return `${field} must be a JSON object, e.g. {"reviewed": true} — got a ${typeof parsed}.`;
  }
  return null;
}

function parseJsonField(
  text: string,
  field: string,
): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const err = jsonFieldError(text, field);
  if (err) throw new Error(err);
  return JSON.parse(trimmed) as Record<string, unknown>;
}

export default function ModelStorePage(): React.ReactElement | null {
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";

  /* viewers have no registry access (API is operator/admin) */
  useEffect(() => {
    if (user && user.role === "viewer") {
      router.replace("/");
    }
  }, [user, router]);

  const {
    models,
    isLoading,
    error,
    refresh,
    registerModel,
    updateModel,
    approveModel,
    deprecateModel,
    retireModel,
    fetchWeights,
  } = useModels();

  /* ── filters ─────────────────────────────────────────────────────── */
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [stateFilter, setStateFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");

  const filtered = useMemo(() => {
    const list = models ?? [];
    const q = search.trim().toLowerCase();
    return list.filter((m) => {
      if (stageFilter !== "all" && m.stage !== stageFilter) return false;
      if (stateFilter !== "all" && m.state !== stateFilter) return false;
      if (
        q &&
        !m.name.toLowerCase().includes(q) &&
        !m.display_name.toLowerCase().includes(q) &&
        !m.engine.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [models, stageFilter, stateFilter, search]);

  const candidateCount = useMemo(
    () => (models ?? []).filter((m) => m.state === "candidate").length,
    [models],
  );

  /* ── ui state ────────────────────────────────────────────────────── */
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [showRegister, setShowRegister] = useState(false);
  const [registerForm, setRegisterForm] =
    useState<RegisterFormState>(EMPTY_REGISTER);

  const [editTarget, setEditTarget] = useState<StoreModel | null>(null);
  const [editForm, setEditForm] = useState<EditFormState>({
    display_name: "",
    description: "",
    source_url: "",
    vram_gb: "",
    default_params: "{}",
  });

  const [approveTarget, setApproveTarget] = useState<StoreModel | null>(null);
  const [approveForm, setApproveForm] = useState<ApproveFormState>({
    attested_by: "",
    vetting_reference: "",
    checklist: "{}",
  });
  /* WP-43 Task 6a: messages that belong AT the field, inside the modal --
     not on a banner the modal's own backdrop is covering. */
  const [approveFieldErrors, setApproveFieldErrors] = useState<
    Partial<Record<keyof ApproveFormState, string>>
  >({});
  const [approveFormError, setApproveFormError] = useState<string | null>(null);

  const flashOk = (msg: string): void => {
    setActionSuccess(msg);
    setActionError(null);
  };
  const flashErr = (e: unknown, fallback: string): void => {
    const msg =
      e instanceof Error && e.message ? e.message : fallback;
    setActionError(msg);
    setActionSuccess(null);
  };

  /* ── actions ─────────────────────────────────────────────────────── */
  const submitRegister = async (): Promise<void> => {
    try {
      const f = registerForm;
      if (!f.name.trim() || !f.display_name.trim()) {
        throw new Error("Name and display name are required.");
      }
      const payload: ModelRegisterPayload = {
        name: f.name.trim(),
        display_name: f.display_name.trim(),
        stage: f.stage as ModelRegisterPayload["stage"],
        engine: f.engine as ModelRegisterPayload["engine"],
        tier: f.tier as ModelRegisterPayload["tier"],
        description: f.description.trim() || null,
        source_url: f.source_url.trim() || null,
        weights_ref: f.weights_ref.trim() || null,
        weights_checksum: f.weights_checksum.trim() || null,
        license: f.license.trim() || null,
        vram_gb: f.vram_gb.trim() ? Number(f.vram_gb) : null,
        dynamically_loadable: f.dynamically_loadable,
        default_params: parseJsonField(f.default_params, "Default params"),
      };
      if (payload.vram_gb !== null && Number.isNaN(payload.vram_gb)) {
        throw new Error("VRAM must be a number (GB).");
      }
      setBusyId("register");
      const created = await registerModel(payload);
      setShowRegister(false);
      setRegisterForm(EMPTY_REGISTER);
      flashOk(`Registered "${created.display_name}" as CANDIDATE.`);
    } catch (e) {
      flashErr(e, "Failed to register model.");
    } finally {
      setBusyId(null);
    }
  };

  const openEdit = (m: StoreModel): void => {
    setEditTarget(m);
    setEditForm({
      display_name: m.display_name,
      description: m.description ?? "",
      source_url: m.source_url ?? "",
      vram_gb: m.vram_gb === null ? "" : String(m.vram_gb),
      default_params: JSON.stringify(m.default_params ?? {}, null, 2),
    });
  };

  const submitEdit = async (): Promise<void> => {
    if (!editTarget) return;
    try {
      const f = editForm;
      const payload: ModelUpdatePayload = {
        display_name: f.display_name.trim(),
        description: f.description.trim() || null,
        source_url: f.source_url.trim() || null,
        vram_gb: f.vram_gb.trim() ? Number(f.vram_gb) : null,
        default_params: parseJsonField(f.default_params, "Default params"),
      };
      if (payload.vram_gb !== null && Number.isNaN(payload.vram_gb!)) {
        throw new Error("VRAM must be a number (GB).");
      }
      setBusyId(editTarget.id);
      const updated = await updateModel(editTarget.id, payload);
      setEditTarget(null);
      flashOk(`Updated "${updated.display_name}".`);
    } catch (e) {
      flashErr(e, "Failed to update model.");
    } finally {
      setBusyId(null);
    }
  };

  const openApprove = (m: StoreModel): void => {
    setApproveTarget(m);
    setApproveFieldErrors({});
    setApproveFormError(null);
    setApproveForm({
      attested_by: user?.username ?? "",
      vetting_reference: "",
      checklist: JSON.stringify({ reviewed: true }, null, 2),
    });
  };

  const submitApprove = async (): Promise<void> => {
    if (!approveTarget) return;
    const f = approveForm;

    /* Validate every field before deciding anything, so the operator sees
       all of the problems at once rather than one per press. */
    const errs: Partial<Record<keyof ApproveFormState, string>> = {};
    if (!f.attested_by.trim()) {
      errs.attested_by = "Required — who vetted this model.";
    }
    if (!f.vetting_reference.trim()) {
      errs.vetting_reference =
        "Required — the evidence reference (cert id, review doc, benchmark run).";
    }
    const checklistErr = jsonFieldError(f.checklist, "Checklist");
    if (checklistErr) {
      errs.checklist = checklistErr;
    } else if (
      Object.keys(
        (JSON.parse(f.checklist.trim() || "{}") ?? {}) as Record<string, unknown>,
      ).length === 0
    ) {
      /* The route refuses an empty checklist itself -- `if not body.checklist`
         (model_store.py:174) -> "attestation checklist must not be empty
         (AD-01.7.2)". Saying it here avoids a round trip; the server's own
         wording still wins if it refuses for a reason this does not know. */
      errs.checklist =
        "The attestation checklist must not be empty (AD-01.7.2). Record at least one check, e.g. {\"reviewed\": true}.";
    }

    setApproveFieldErrors(errs);
    setApproveFormError(null);
    if (Object.keys(errs).length > 0) return;

    try {
      const payload: ModelApprovePayload = {
        attested_by: f.attested_by.trim(),
        vetting_reference: f.vetting_reference.trim(),
        checklist: JSON.parse(f.checklist.trim()) as Record<string, unknown>,
      };
      setBusyId(approveTarget.id);
      const updated = await approveModel(approveTarget.id, payload);
      setApproveTarget(null);
      flashOk(`Approved "${updated.display_name}" — now selectable.`);
    } catch (e) {
      /* A server refusal lands in the modal, where the operator is looking.
         A 422 arrives with per-field detail, so it is placed at the field. */
      const perField = fieldErrors(
        (e as { body?: unknown } | null)?.body ?? null,
      );
      const mapped: Partial<Record<keyof ApproveFormState, string>> = {};
      for (const key of ["attested_by", "vetting_reference", "checklist"] as const) {
        if (perField[key]) mapped[key] = perField[key]!;
      }
      setApproveFieldErrors(mapped);
      setApproveFormError(
        Object.keys(mapped).length > 0
          ? null
          : e instanceof Error && e.message
          ? e.message
          : "Failed to approve model.",
      );
    } finally {
      setBusyId(null);
    }
  };

  const doToggleEnabled = async (m: StoreModel): Promise<void> => {
    try {
      setBusyId(m.id);
      await updateModel(m.id, { enabled: !m.enabled });
      flashOk(`${m.enabled ? "Disabled" : "Enabled"} "${m.display_name}".`);
    } catch (e) {
      flashErr(e, "Failed to toggle enabled.");
    } finally {
      setBusyId(null);
    }
  };

  const doSetDefault = async (m: StoreModel): Promise<void> => {
    try {
      setBusyId(m.id);
      await updateModel(m.id, { is_default: true });
      flashOk(`"${m.display_name}" is now the ${m.stage} default.`);
    } catch (e) {
      flashErr(e, "Failed to set default.");
    } finally {
      setBusyId(null);
    }
  };

  /**
   * WP-65 Task 4 — Fetch weights. Admin-only, GUI-only (the standing IVGS
   * rule: admin functionality has no CLI).
   *
   * A REFUSAL IS NOT AN ERROR. The route answers 202 for every outcome and
   * says which one it was, so "this model's engine has no host" is reported as
   * the durable fact it is rather than as a failed request. That distinction
   * is the whole point of the action: three of the states this can return mean
   * "do something else entirely", not "try again".
   */
  const doFetchWeights = async (m: StoreModel): Promise<void> => {
    const st = m.weight_status;
    if (st && !st.can_fetch) {
      flashErr(
        new Error(st.detail ?? st.label),
        `Cannot fetch weights for "${m.display_name}".`,
      );
      return;
    }
    if (st && !st.credentials_present) {
      flashErr(
        new Error(
          "The MBCP serving token is not present on the API host. An operator supplies it as an environment variable on node-01; IVGS never stores it.",
        ),
        `Cannot fetch weights for "${m.display_name}".`,
      );
      return;
    }
    if (
      !window.confirm(
        `Fetch weights for "${m.display_name}"?\n\n` +
          `Destination: ${st?.target_dir ?? "(resolved at fetch time)"}\n` +
          `Node: ${st?.target_node ?? "(resolved at fetch time)"}\n` +
          `Container: ${st?.target_container ?? "(resolved at fetch time)"}\n\n` +
          `Bytes are staged and every checksum verified before anything is moved into place.`,
      )
    ) {
      return;
    }
    try {
      setBusyId(m.id);
      const result = await fetchWeights(m.id);
      if (result.accepted) {
        flashOk(`${m.display_name}: ${result.message}`);
      } else {
        // Recorded, not lost: the placement row carries the reason.
        flashErr(new Error(result.message), `Weights not fetched (${result.reason}).`);
      }
    } catch (e) {
      flashErr(e, "Fetch weights failed.");
    } finally {
      setBusyId(null);
    }
  };

  const doDeprecate = async (m: StoreModel): Promise<void> => {
    if (
      !window.confirm(
        `Deprecate "${m.display_name}"? It stays runnable where loaded but is deprioritised for new selections.`,
      )
    ) {
      return;
    }
    try {
      setBusyId(m.id);
      await deprecateModel(m.id);
      flashOk(`Deprecated "${m.display_name}".`);
    } catch (e) {
      flashErr(e, "Failed to deprecate model.");
    } finally {
      setBusyId(null);
    }
  };

  const doRetire = async (m: StoreModel): Promise<void> => {
    if (
      !window.confirm(
        `Retire "${m.display_name}"? Retired models are excluded from selection entirely.`,
      )
    ) {
      return;
    }
    try {
      setBusyId(m.id);
      await retireModel(m.id);
      flashOk(`Retired "${m.display_name}".`);
    } catch (e) {
      flashErr(e, "Failed to retire model.");
    } finally {
      setBusyId(null);
    }
  };

  /* ── render ──────────────────────────────────────────────────────── */
  if (!user) return null;

  return (
    <ErrorBoundary>
      <div className="min-h-screen">
        <header className="border-b border-gray-200 dark:border-gray-800 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                Model Store
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                AD-01 registry — models &amp; engines per pipeline stage.
                {candidateCount > 0 && (
                  <span className="ml-2 rounded-full bg-yellow-100 dark:bg-yellow-900/50 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:text-yellow-300">
                    {candidateCount} candidate{candidateCount === 1 ? "" : "s"}{" "}
                    awaiting review
                  </span>
                )}
              </p>
            </div>
            {isAdmin && (
              <button
                type="button"
                className={btnPrimary}
                onClick={() => {
                  setRegisterForm(EMPTY_REGISTER);
                  setShowRegister(true);
                }}
              >
                Register Model
              </button>
            )}
          </div>
        </header>

        <div className="px-6 py-6">
          {actionSuccess && (
            <div className="bg-green-100 dark:bg-green-900/40 border border-green-200 dark:border-green-800 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-green-800 dark:text-green-300">{actionSuccess}</p>
                <button
                  type="button"
                  onClick={() => setActionSuccess(null)}
                  className="text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-200"
                >
                  ✕
                </button>
              </div>
            </div>
          )}
          {actionError && (
            <div className="bg-red-100 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-red-800 dark:text-red-300">{actionError}</p>
                <button
                  type="button"
                  onClick={() => setActionError(null)}
                  className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          {/* filters */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <input
              type="text"
              placeholder="Search name / engine…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-64 rounded-md border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-500"
            />
            <select
              value={stageFilter}
              onChange={(e) => setStageFilter(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              <option value="all">All stages</option>
              {MODEL_STAGES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              <option value="all">All states</option>
              {(["candidate", "approved", "deprecated", "retired"] as const).map(
                (s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ),
              )}
            </select>
            <button type="button" className={btnSubtle} onClick={() => refresh()}>
              Refresh
            </button>
          </div>

          {isLoading && <LoadingSpinner />}
          {error && !isLoading && (
            <div className="bg-red-100 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <p className="text-sm text-red-800 dark:text-red-300">
                Failed to load the model registry: {error.message}
              </p>
            </div>
          )}

          {!isLoading && !error && (
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800 text-sm">
                <thead className="bg-gray-100 dark:bg-gray-800/60">
                  <tr>
                    {[
                      "Model",
                      "Stage",
                      "Engine",
                      "Tier",
                      "State",
                      "VRAM",
                      "Weights",
                      "Client",
                      "Flags",
                      "Actions",
                    ].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {filtered.length === 0 && (
                    <tr>
                      <td
                        colSpan={10}
                        className="px-4 py-8 text-center text-gray-500 dark:text-gray-400"
                      >
                        No models match. MBCP-certified models arrive here as
                        CANDIDATE; admins can also register manually.
                      </td>
                    </tr>
                  )}
                  {filtered.map((m) => {
                    const busy = busyId === m.id;
                    // WP-65. `node_availability` is still read — it is a real
                    // signal about the SCHEDULER — but it no longer decides
                    // what this row says about weights. `weight_status` does,
                    // and it is computed server-side so the page cannot infer
                    // availability from a row count the way it used to.
                    const loadedOnNodes = m.node_availability.filter(
                      (a) => a.status === "available",
                    ).length;
                    const ws = m.weight_status;
                    const cs = m.client_status;
                    return (
                      <React.Fragment key={m.id}>
                        <tr
                          className="cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800/50"
                          onClick={() =>
                            setExpanded(expanded === m.id ? null : m.id)
                          }
                        >
                          <td className="px-4 py-3">
                            <div className="font-medium text-gray-900 dark:text-white">
                              {m.display_name}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">{m.name}</div>
                          </td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{m.stage}</td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{m.engine}</td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{m.tier}</td>
                          <td className="px-4 py-3">
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_BADGE[m.state]}`}
                            >
                              {m.state}
                            </span>
                          </td>
                          {/* VRAM. `models.vram_gb` is a number typed into
                              the registration form, not a measurement — so it
                              is labelled as declared, and the REAL on-disk
                              size sits beneath it when one has been measured. */}
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                            {m.vram_gb !== null ? (
                              <span title="Declared at registration, not measured">
                                {m.vram_gb} GB
                              </span>
                            ) : (
                              <span className="text-gray-500 dark:text-gray-400">
                                not declared
                              </span>
                            )}
                            {ws && ws.state === "available" && (
                              <div className="text-xs text-gray-500 dark:text-gray-400">
                                {formatBytes(ws.bytes_on_disk)} on disk
                              </div>
                            )}
                          </td>
                          {/* Weights. Was "N available" / "none"; now the
                              state and the node, which are different facts. */}
                          <td className="px-4 py-3">
                            {ws ? (
                              <>
                                <span
                                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${WEIGHT_BADGE[ws.state]}`}
                                  title={ws.detail ?? ws.label}
                                >
                                  {ws.label}
                                </span>
                                {loadedOnNodes > 0 && ws.state !== "available" && (
                                  <div
                                    className="mt-1 text-xs text-gray-500 dark:text-gray-400"
                                    title="The GPU scheduler has this model name in its per-node LRU, which records that a job loaded it once. That is not evidence that bytes are on disk."
                                  >
                                    scheduler: loaded on {loadedOnNodes} node
                                    {loadedOnNodes === 1 ? "" : "s"}
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-gray-500 dark:text-gray-400">
                                unknown (API predates v5.24.0-weights)
                              </span>
                            )}
                          </td>
                          {/* WP-67 — can IVGS RUN it. Independent of the bytes. */}
                          <td className="px-4 py-3">
                            {cs ? (
                              <span
                                className={`rounded-full px-2 py-0.5 text-xs font-medium ${CLIENT_BADGE[cs.state]}`}
                                title={cs.detail ?? CLIENT_ACTION[cs.state] ?? cs.label}
                              >
                                {cs.label}
                              </span>
                            ) : (
                              <span className="text-gray-500 dark:text-gray-400">
                                unknown (API predates v5.26.0-clients)
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                            {m.is_default && (
                              <span className="mr-1 rounded bg-blue-100 dark:bg-blue-900/50 px-1.5 py-0.5 text-blue-800 dark:text-blue-300">
                                default
                              </span>
                            )}
                            {!m.enabled && (
                              <span className="rounded bg-gray-200 dark:bg-gray-700/50 px-1.5 py-0.5 text-gray-700 dark:text-gray-300">
                                disabled
                              </span>
                            )}
                          </td>
                          <td
                            className="px-4 py-3"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {isAdmin ? (
                              <div className="flex flex-wrap gap-1.5">
                                {m.state === "candidate" && (
                                  <button
                                    type="button"
                                    disabled={busy}
                                    className="rounded bg-green-600 px-2 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                                    onClick={() => openApprove(m)}
                                  >
                                    Approve
                                  </button>
                                )}
                                <button
                                  type="button"
                                  disabled={busy}
                                  className="rounded border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs text-gray-800 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
                                  onClick={() => openEdit(m)}
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  disabled={busy}
                                  className="rounded border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs text-gray-800 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
                                  onClick={() => void doToggleEnabled(m)}
                                >
                                  {m.enabled ? "Disable" : "Enable"}
                                </button>
                                {m.state === "approved" && !m.is_default && (
                                  <button
                                    type="button"
                                    disabled={busy}
                                    className="rounded border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs text-gray-800 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
                                    onClick={() => void doSetDefault(m)}
                                  >
                                    Set default
                                  </button>
                                )}
                                {m.state === "approved" && (
                                  <button
                                    type="button"
                                    disabled={busy}
                                    className="rounded border border-orange-200 dark:border-orange-700 px-2 py-1 text-xs text-orange-800 dark:text-orange-300 hover:bg-orange-100 dark:hover:bg-orange-900/30 disabled:opacity-50"
                                    onClick={() => void doDeprecate(m)}
                                  >
                                    Deprecate
                                  </button>
                                )}
                                {m.state === "deprecated" && (
                                  <button
                                    type="button"
                                    disabled={busy}
                                    className="rounded border border-red-200 dark:border-red-700 px-2 py-1 text-xs text-red-800 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30 disabled:opacity-50"
                                    onClick={() => void doRetire(m)}
                                  >
                                    Retire
                                  </button>
                                )}
                                {/* WP-65. Present for every model, DISABLED
                                    where it cannot work, with the reason on
                                    the tooltip — a model whose engine has no
                                    host must be visible and explained, not
                                    silently absent. */}
                                <button
                                  type="button"
                                  disabled={
                                    busy ||
                                    ws?.state === "fetching" ||
                                    (ws !== null && !ws.can_fetch)
                                  }
                                  title={
                                    ws && !ws.can_fetch
                                      ? `${ws.label} — ${WEIGHT_ACTION[ws.state]}`
                                      : ws && !ws.credentials_present
                                        ? "The MBCP serving token is not present on the API host."
                                        : ws?.target_dir
                                          ? `Fetch to ${ws.target_node}:${ws.target_dir}`
                                          : "Fetch this model's certified weights"
                                  }
                                  className="rounded border border-blue-200 dark:border-blue-700 px-2 py-1 text-xs text-blue-800 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30 disabled:opacity-50"
                                  onClick={() => void doFetchWeights(m)}
                                >
                                  {ws?.state === "fetching"
                                    ? "Fetching…"
                                    : ws?.state === "available"
                                      ? "Re-verify weights"
                                      : "Fetch weights"}
                                </button>
                              </div>
                            ) : (
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                read-only
                              </span>
                            )}
                          </td>
                        </tr>
                        {expanded === m.id && (
                          <tr className="bg-gray-100 dark:bg-gray-800/40">
                            <td colSpan={10} className="px-6 py-4">
                              <div className="grid grid-cols-1 gap-4 text-xs text-gray-500 dark:text-gray-400 md:grid-cols-3">
                                <div>
                                  <div className="mb-1 font-semibold text-gray-800 dark:text-gray-200">
                                    Weights &amp; provenance
                                  </div>
                                  <div>ref: {m.weights_ref ?? "—"}</div>
                                  <div className="break-all">
                                    checksum: {m.weights_checksum ?? "—"}
                                  </div>
                                  <div>license: {m.license ?? "—"}</div>
                                  <div>source: {m.source_url ?? "—"}</div>
                                  <div>registered by: {m.created_by ?? "—"}</div>
                                </div>
                                <div>
                                  <div className="mb-1 font-semibold text-gray-800 dark:text-gray-200">
                                    Weights on disk
                                  </div>
                                  {ws && (
                                    <>
                                      <div>{ws.label}</div>
                                      {ws.detail && (
                                        <div className="mt-1 italic">{ws.detail}</div>
                                      )}
                                      {WEIGHT_ACTION[ws.state] && (
                                        <div className="mt-1">
                                          {WEIGHT_ACTION[ws.state]}
                                        </div>
                                      )}
                                    </>
                                  )}
                                  {m.weight_placements.length === 0 && (
                                    <div className="text-gray-500 dark:text-gray-400">
                                      no fetch has been attempted
                                    </div>
                                  )}
                                  {m.weight_placements.map((wp) => (
                                    <div key={wp.id} className="mt-1">
                                      <div>
                                        {wp.node_id}: {wp.status}
                                        {wp.checksum_verified
                                          ? " (checksums verified)"
                                          : ""}
                                        {wp.signature_verified
                                          ? " (signature verified)"
                                          : ""}
                                      </div>
                                      {wp.dest_dir && (
                                        <div className="break-all">
                                          dir: {wp.dest_dir}
                                        </div>
                                      )}
                                      {wp.bytes_on_disk !== null && (
                                        <div>
                                          {formatBytes(wp.bytes_on_disk)} in{" "}
                                          {wp.file_count ?? "?"} file(s)
                                        </div>
                                      )}
                                      {wp.last_error && (
                                        <div className="text-red-600 dark:text-red-400">
                                          {wp.last_error_reason}: {wp.last_error}
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                                <div>
                                  <div className="mb-1 font-semibold text-gray-800 dark:text-gray-200">
                                    Client
                                  </div>
                                  {cs ? (
                                    <>
                                      <div>{cs.label}</div>
                                      {cs.family && <div>family: {cs.family}</div>}
                                      {cs.requires.length > 0 && (
                                        <div>
                                          needs from a scene:{" "}
                                          {cs.requires.join(", ")}
                                        </div>
                                      )}
                                      {cs.detail && (
                                        <div className="mt-1 italic">{cs.detail}</div>
                                      )}
                                      {CLIENT_ACTION[cs.state] && (
                                        <div className="mt-1">
                                          {CLIENT_ACTION[cs.state]}
                                        </div>
                                      )}
                                    </>
                                  ) : (
                                    <div className="text-gray-500 dark:text-gray-400">
                                      not reported by this API
                                    </div>
                                  )}
                                </div>
                                <div>
                                  <div
                                    className="mb-1 font-semibold text-gray-800 dark:text-gray-200"
                                    title="A projection of the GPU scheduler's per-node LRU. It records that a job loaded this model name on a node at some point; the key has no expiry, so it is history, not residency, and it never inspects a disk."
                                  >
                                    Scheduler residency (not weights)
                                  </div>
                                  {m.node_availability.length === 0 && (
                                    <div className="text-gray-500 dark:text-gray-400">
                                      no residency reported
                                    </div>
                                  )}
                                  {m.node_availability.map((a) => (
                                    <div key={a.node_id}>
                                      {a.node_id}: {a.status}
                                      {a.served ? " (served)" : ""}
                                    </div>
                                  ))}
                                </div>
                                <div>
                                  <div className="mb-1 font-semibold text-gray-800 dark:text-gray-200">
                                    Approvals ({m.approvals.length})
                                  </div>
                                  {m.approvals.length === 0 && (
                                    <div className="text-gray-500 dark:text-gray-400">none</div>
                                  )}
                                  {m.approvals.map((a) => (
                                    <div key={a.id} className="break-all">
                                      {a.attested_by} — {a.vetting_reference}
                                    </div>
                                  ))}
                                  {m.description && (
                                    <div className="mt-2">
                                      <span className="font-semibold text-gray-800 dark:text-gray-200">
                                        Description:{" "}
                                      </span>
                                      {m.description}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Register modal ─────────────────────────────────────────── */}
        {showRegister && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 shadow-xl mx-4">
              <div className="border-b border-gray-200 dark:border-gray-800 px-6 py-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Register Model
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Registers as CANDIDATE; approve it to make it selectable.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-4 px-6 py-4 md:grid-cols-2">
                <div>
                  <label className={labelCls}>Name (unique id)</label>
                  <input
                    className={inputCls}
                    value={registerForm.name}
                    onChange={(e) =>
                      setRegisterForm((f) => ({ ...f, name: e.target.value }))
                    }
                    placeholder="flux1-schnell"
                  />
                </div>
                <div>
                  <label className={labelCls}>Display name</label>
                  <input
                    className={inputCls}
                    value={registerForm.display_name}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        display_name: e.target.value,
                      }))
                    }
                    placeholder="FLUX.1 Schnell"
                  />
                </div>
                <div>
                  <label className={labelCls}>Stage</label>
                  <select
                    className={inputCls}
                    value={registerForm.stage}
                    onChange={(e) =>
                      setRegisterForm((f) => ({ ...f, stage: e.target.value }))
                    }
                  >
                    {MODEL_STAGES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Engine</label>
                  <select
                    className={inputCls}
                    value={registerForm.engine}
                    onChange={(e) =>
                      setRegisterForm((f) => ({ ...f, engine: e.target.value }))
                    }
                  >
                    {MODEL_ENGINES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Tier</label>
                  <select
                    className={inputCls}
                    value={registerForm.tier}
                    onChange={(e) =>
                      setRegisterForm((f) => ({ ...f, tier: e.target.value }))
                    }
                  >
                    {MODEL_TIERS.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>VRAM (GB, optional)</label>
                  <input
                    className={inputCls}
                    value={registerForm.vram_gb}
                    onChange={(e) =>
                      setRegisterForm((f) => ({ ...f, vram_gb: e.target.value }))
                    }
                    placeholder="26"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className={labelCls}>Description (optional)</label>
                  <input
                    className={inputCls}
                    value={registerForm.description}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        description: e.target.value,
                      }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Source URL (optional)</label>
                  <input
                    className={inputCls}
                    value={registerForm.source_url}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        source_url: e.target.value,
                      }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>License (optional)</label>
                  <input
                    className={inputCls}
                    value={registerForm.license}
                    onChange={(e) =>
                      setRegisterForm((f) => ({ ...f, license: e.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Weights ref (optional)</label>
                  <input
                    className={inputCls}
                    value={registerForm.weights_ref}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        weights_ref: e.target.value,
                      }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Weights checksum (optional)</label>
                  <input
                    className={inputCls}
                    value={registerForm.weights_checksum}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        weights_checksum: e.target.value,
                      }))
                    }
                  />
                </div>
                <div className="md:col-span-2">
                  <label className={labelCls}>
                    Default params (JSON object)
                  </label>
                  <textarea
                    className={`${inputCls} h-24 font-mono`}
                    value={registerForm.default_params}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        default_params: e.target.value,
                      }))
                    }
                  />
                </div>
                <div className="flex items-center gap-2 md:col-span-2">
                  <input
                    id="dyn-loadable"
                    type="checkbox"
                    checked={registerForm.dynamically_loadable}
                    onChange={(e) =>
                      setRegisterForm((f) => ({
                        ...f,
                        dynamically_loadable: e.target.checked,
                      }))
                    }
                  />
                  <label htmlFor="dyn-loadable" className="text-sm text-gray-700 dark:text-gray-300">
                    Dynamically loadable (unchecked = fixed serving, e.g. vLLM)
                  </label>
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t border-gray-200 dark:border-gray-800 px-6 py-4">
                <button
                  type="button"
                  className={btnSubtle}
                  onClick={() => setShowRegister(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={btnPrimary}
                  disabled={busyId === "register"}
                  onClick={() => void submitRegister()}
                >
                  Register
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Edit modal ─────────────────────────────────────────────── */}
        {editTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 shadow-xl mx-4">
              <div className="border-b border-gray-200 dark:border-gray-800 px-6 py-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Edit — {editTarget.name}
                </h2>
              </div>
              <div className="space-y-4 px-6 py-4">
                <div>
                  <label className={labelCls}>Display name</label>
                  <input
                    className={inputCls}
                    value={editForm.display_name}
                    onChange={(e) =>
                      setEditForm((f) => ({ ...f, display_name: e.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Description</label>
                  <input
                    className={inputCls}
                    value={editForm.description}
                    onChange={(e) =>
                      setEditForm((f) => ({ ...f, description: e.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Source URL</label>
                  <input
                    className={inputCls}
                    value={editForm.source_url}
                    onChange={(e) =>
                      setEditForm((f) => ({ ...f, source_url: e.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>VRAM (GB)</label>
                  <input
                    className={inputCls}
                    value={editForm.vram_gb}
                    onChange={(e) =>
                      setEditForm((f) => ({ ...f, vram_gb: e.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Default params (JSON object)</label>
                  <textarea
                    className={`${inputCls} h-28 font-mono`}
                    value={editForm.default_params}
                    onChange={(e) =>
                      setEditForm((f) => ({
                        ...f,
                        default_params: e.target.value,
                      }))
                    }
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t border-gray-200 dark:border-gray-800 px-6 py-4">
                <button
                  type="button"
                  className={btnSubtle}
                  onClick={() => setEditTarget(null)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={btnPrimary}
                  disabled={busyId === editTarget.id}
                  onClick={() => void submitEdit()}
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Approve modal ──────────────────────────────────────────── */}
        {approveTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="w-full max-w-lg rounded-lg bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 shadow-xl mx-4">
              <div className="border-b border-gray-200 dark:border-gray-800 px-6 py-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Approve — {approveTarget.display_name}
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  AD-01.7.2 attestation: records who vetted this model and the
                  evidence reference (e.g. an MBCP certification id).
                </p>
              </div>
              <div className="space-y-4 px-6 py-4">
                {/* WP-43 Task 6a. Every message below is rendered INSIDE the
                    modal. The page-level banner these used to reach sits
                    behind this dialog's own backdrop, which is why an array
                    in the checklist produced a dead Approve button and no
                    message of any kind. */}
                <div>
                  <label className={labelCls}>Attested by</label>
                  <input
                    className={`${inputCls} ${
                      approveFieldErrors.attested_by
                        ? "border-red-500 dark:border-red-500"
                        : ""
                    }`}
                    aria-invalid={approveFieldErrors.attested_by ? true : undefined}
                    value={approveForm.attested_by}
                    onChange={(e) => {
                      setApproveFieldErrors((p) => ({ ...p, attested_by: undefined }));
                      setApproveForm((f) => ({
                        ...f,
                        attested_by: e.target.value,
                      }));
                    }}
                  />
                  {approveFieldErrors.attested_by && (
                    <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">
                      {approveFieldErrors.attested_by}
                    </p>
                  )}
                </div>
                <div>
                  <label className={labelCls}>Vetting reference</label>
                  <input
                    className={`${inputCls} ${
                      approveFieldErrors.vetting_reference
                        ? "border-red-500 dark:border-red-500"
                        : ""
                    }`}
                    aria-invalid={
                      approveFieldErrors.vetting_reference ? true : undefined
                    }
                    value={approveForm.vetting_reference}
                    onChange={(e) => {
                      setApproveFieldErrors((p) => ({
                        ...p,
                        vetting_reference: undefined,
                      }));
                      setApproveForm((f) => ({
                        ...f,
                        vetting_reference: e.target.value,
                      }));
                    }}
                    placeholder="cert id / review doc / benchmark run"
                  />
                  {approveFieldErrors.vetting_reference && (
                    <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">
                      {approveFieldErrors.vetting_reference}
                    </p>
                  )}
                </div>
                <div>
                  <label className={labelCls}>Checklist (JSON object)</label>
                  <textarea
                    className={`${inputCls} h-24 font-mono ${
                      approveFieldErrors.checklist
                        ? "border-red-500 dark:border-red-500"
                        : ""
                    }`}
                    aria-invalid={approveFieldErrors.checklist ? true : undefined}
                    value={approveForm.checklist}
                    onChange={(e) => {
                      setApproveFieldErrors((p) => ({ ...p, checklist: undefined }));
                      setApproveForm((f) => ({ ...f, checklist: e.target.value }));
                    }}
                  />
                  {approveFieldErrors.checklist ? (
                    <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">
                      {approveFieldErrors.checklist}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      A JSON object — an array or a bare value is refused.
                      Example: {"{"}&quot;reviewed&quot;: true,
                      &quot;benchmarked&quot;: true{"}"}
                    </p>
                  )}
                </div>
                {approveFormError && (
                  <p
                    role="alert"
                    className="rounded-md border border-red-200 bg-red-100 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300"
                  >
                    {approveFormError}
                  </p>
                )}
              </div>
              <div className="flex justify-end gap-2 border-t border-gray-200 dark:border-gray-800 px-6 py-4">
                <button
                  type="button"
                  className={btnSubtle}
                  onClick={() => setApproveTarget(null)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="inline-flex items-center rounded-md bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                  disabled={busyId === approveTarget.id}
                  onClick={() => void submitApprove()}
                >
                  Approve
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
