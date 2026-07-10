"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useModels } from "@/hooks/useModels";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type {
  ModelApprovePayload,
  ModelRegisterPayload,
  ModelState,
  ModelUpdatePayload,
  StoreModel,
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

function parseJsonField(
  text: string,
  field: string,
): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("not an object");
    }
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(`${field} must be a JSON object, e.g. {"temperature": 0.3}`);
  }
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
    setApproveForm({
      attested_by: user?.username ?? "",
      vetting_reference: "",
      checklist: JSON.stringify({ reviewed: true }, null, 2),
    });
  };

  const submitApprove = async (): Promise<void> => {
    if (!approveTarget) return;
    try {
      const f = approveForm;
      if (!f.attested_by.trim() || !f.vetting_reference.trim()) {
        throw new Error("Attested-by and vetting reference are required.");
      }
      const payload: ModelApprovePayload = {
        attested_by: f.attested_by.trim(),
        vetting_reference: f.vetting_reference.trim(),
        checklist: parseJsonField(f.checklist, "Checklist") ?? {},
      };
      setBusyId(approveTarget.id);
      const updated = await approveModel(approveTarget.id, payload);
      setApproveTarget(null);
      flashOk(`Approved "${updated.display_name}" — now selectable.`);
    } catch (e) {
      flashErr(e, "Failed to approve model.");
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
                      "Nodes",
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
                        colSpan={9}
                        className="px-4 py-8 text-center text-gray-500 dark:text-gray-400"
                      >
                        No models match. MBCP-certified models arrive here as
                        CANDIDATE; admins can also register manually.
                      </td>
                    </tr>
                  )}
                  {filtered.map((m) => {
                    const busy = busyId === m.id;
                    const availableNodes = m.node_availability.filter(
                      (a) => a.status === "available",
                    ).length;
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
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                            {m.vram_gb !== null ? `${m.vram_gb} GB` : "—"}
                          </td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                            {availableNodes > 0 ? (
                              <span className="text-green-600 dark:text-green-400">
                                {availableNodes} available
                              </span>
                            ) : (
                              <span className="text-gray-500 dark:text-gray-400">none</span>
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
                            <td colSpan={9} className="px-6 py-4">
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
                                    Node availability
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
                <div>
                  <label className={labelCls}>Attested by</label>
                  <input
                    className={inputCls}
                    value={approveForm.attested_by}
                    onChange={(e) =>
                      setApproveForm((f) => ({
                        ...f,
                        attested_by: e.target.value,
                      }))
                    }
                  />
                </div>
                <div>
                  <label className={labelCls}>Vetting reference</label>
                  <input
                    className={inputCls}
                    value={approveForm.vetting_reference}
                    onChange={(e) =>
                      setApproveForm((f) => ({
                        ...f,
                        vetting_reference: e.target.value,
                      }))
                    }
                    placeholder="cert id / review doc / benchmark run"
                  />
                </div>
                <div>
                  <label className={labelCls}>Checklist (JSON object)</label>
                  <textarea
                    className={`${inputCls} h-24 font-mono`}
                    value={approveForm.checklist}
                    onChange={(e) =>
                      setApproveForm((f) => ({ ...f, checklist: e.target.value }))
                    }
                  />
                </div>
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
