"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";

/**
 * §2.3 Node Configuration
 *
 * Admin-only page for viewing and staging the cluster node IP registry
 * (NODE_01_IP … NODE_06_IP). Used primarily at commissioning time.
 *
 * node-01 (the infrastructure host) is shown for reference but is NOT editable:
 * its address is set at the router / host level, and changing the address of the
 * host serving this UI mid-restart is unsafe. The backend reports it with
 * editable=false and never stages it.
 *
 * Least-privilege model — the API never edits ivgs-infra/.env or Docker:
 *   - GET  /api/v1/node-config — applied IPs (from the API container env) plus
 *          any staged (pending) change.
 *   - PUT  /api/v1/node-config — stage a change (written to a pending file under
 *          the API's existing /ivgs mount; .env is NOT touched here).
 *
 * Applying a staged change is a deliberate host step (scripts/apply-node-config.sh),
 * which backs up and rewrites .env then recreates the stack; node-01 goes briefly
 * offline during that restart. This page shows applied vs. pending state, a live
 * "different subnet from node-01" advisory, and the restart-required notice.
 *
 * RBAC: Admin only (enforced by the /admin layout, per §8.3 Table 8-3).
 */

interface NodeEntry {
  node_id: string;
  role: string;
  applied_ip: string;
  pending_ip: string | null;
  editable: boolean;
}

interface NodeConfigResponse {
  nodes: NodeEntry[];
  restart_required: boolean;
  expected_subnet: string;
  warnings: string[];
}

/* Basic IPv4 dotted-quad check for client-side guarding (server re-validates). */
function isValidIPv4(value: string): boolean {
  const m = value.trim().match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!m) return false;
  return m.slice(1).every((octet) => {
    const n = Number(octet);
    return n >= 0 && n <= 255 && String(n) === octet;
  });
}

/* /24 comparison against node-01's address (server is authoritative). */
function sameSubnet24(ip: string, node01Ip: string | null): boolean {
  if (!node01Ip) return true;
  const a = ip.trim().split(".");
  const b = node01Ip.trim().split(".");
  if (a.length !== 4 || b.length !== 4) return true;
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
}

function extractError(err: any): string {
  const d = err?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d?.error?.message) return d.error.message;
  if (Array.isArray(d) && d[0]?.msg) return d.map((e: any) => e.msg).join("; ");
  return err?.message || "Request failed.";
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export default function NodeConfigPage(): React.ReactElement {
  const { user } = useAuth();

  const [config, setConfig] = useState<NodeConfigResponse | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [applying, setApplying] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);

  const seedEdits = useCallback((data: NodeConfigResponse) => {
    const next: Record<string, string> = {};
    for (const node of data.nodes) {
      next[node.node_id] = node.pending_ip ?? node.applied_ip;
    }
    setEdits(next);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await api.get("/api/v1/node-config");
      const data = res.data as NodeConfigResponse;
      setConfig(data);
      seedEdits(data);
    } catch (err: any) {
      setLoadError(extractError(err));
    } finally {
      setLoading(false);
    }
  }, [seedEdits]);

  useEffect(() => {
    load();
  }, [load]);

  const node01Ip = config?.nodes.find((n) => n.node_id === "node-01")?.applied_ip ?? null;

  const dirty = config
    ? config.nodes.some((node) => node.editable && (edits[node.node_id] ?? "").trim() !== node.applied_ip)
    : false;

  const invalidCount = config
    ? config.nodes.filter((node) => node.editable && !isValidIPv4(edits[node.node_id] ?? "")).length
    : 0;

  const submit = useCallback(
    async (payloadNodes: { node_id: string; ip: string }[], successText: string) => {
      setSaving(true);
      setActionMessage(null);
      try {
        const res = await api.put("/api/v1/node-config", { nodes: payloadNodes });
        const data = res?.data as NodeConfigResponse | undefined;
        if (data) {
          setConfig(data);
          seedEdits(data);
        } else {
          await load();
        }
        setActionMessage({ type: "success", text: successText });
      } catch (err: any) {
        setActionMessage({ type: "error", text: extractError(err) });
      } finally {
        setSaving(false);
      }
    },
    [seedEdits, load],
  );

  const editablePayload = useCallback(
    (pick: (node: NodeEntry) => string) => {
      if (!config) return [];
      return config.nodes
        .filter((node) => node.editable)
        .map((node) => ({ node_id: node.node_id, ip: pick(node) }));
    },
    [config],
  );

  const handleSave = useCallback(() => {
    if (!config) return;
    void submit(
      editablePayload((node) => (edits[node.node_id] ?? "").trim()),
      "Node IP changes staged. A stack restart on node-01 is required to apply them.",
    );
  }, [config, edits, editablePayload, submit]);

  const resetToApplied = useCallback(() => {
    if (!config) return;
    const next: Record<string, string> = {};
    for (const node of config.nodes) {
      next[node.node_id] = node.applied_ip;
    }
    setEdits(next);
  }, [config]);

  const handleDiscard = useCallback(() => {
    if (!config) return;
    resetToApplied();
    if (config.restart_required) {
      void submit(
        editablePayload((node) => node.applied_ip),
        "Pending changes discarded. The applied configuration is unchanged.",
      );
    } else {
      setActionMessage({ type: "success", text: "Edits reverted to the applied configuration." });
    }
  }, [config, resetToApplied, editablePayload, submit]);

  const handleApply = useCallback(async () => {
    if (!config) return;
    setConfirmApply(false);
    setApplying(true);
    setActionMessage(null);
    try {
      await api.post("/api/v1/node-config/apply");
    } catch (err: any) {
      setApplying(false);
      setActionMessage({ type: "error", text: extractError(err) });
      return;
    }
    const maxAttempts = 40; // poll ~2 minutes (3s interval) while the stack recreates
    for (let i = 0; i < maxAttempts; i++) {
      await sleep(3000);
      try {
        const res = await api.get("/api/v1/node-config");
        const data = res.data as NodeConfigResponse;
        if (!data.restart_required) {
          setConfig(data);
          seedEdits(data);
          setApplying(false);
          setActionMessage({ type: "success", text: "Node IPs applied. The stack has restarted." });
          return;
        }
      } catch {
        // API is recreating and briefly unavailable; keep polling.
      }
    }
    setApplying(false);
    setActionMessage({
      type: "error",
      text: "Apply is taking longer than expected. The restart may still be in progress - refresh in a moment to check.",
    });
  }, [config, seedEdits]);

  const restartRequired = config?.restart_required ?? false;
  const warnings = config?.warnings ?? [];

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Page header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Node Configuration</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            §2.3 — Cluster node IP registry. Welcome, {user?.username}.
          </p>
        </div>

        {/* Action feedback */}
        {actionMessage && (
          <div
            className={`mb-4 rounded-lg px-4 py-3 text-sm ${
              actionMessage.type === "success"
                ? "border border-green-200 dark:border-green-800 bg-green-100 dark:bg-green-900/20 text-green-600 dark:text-green-400"
                : "border border-red-200 dark:border-red-800 bg-red-100 dark:bg-red-900/20 text-red-600 dark:text-red-400"
            }`}
          >
            {actionMessage.text}
            <button onClick={() => setActionMessage(null)} className="ml-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
              ✕
            </button>
          </div>
        )}

        {/* Applying state */}
        {applying && (
          <div className="mb-4 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-100 dark:bg-blue-900/20 px-4 py-3 text-sm text-blue-800 dark:text-blue-300">
            <span className="font-semibold">Applying node IP changes…</span> The API is restarting and will be briefly
            unavailable; this page updates automatically when it returns.
          </div>
        )}

        {/* Restart-required notice */}
        {restartRequired && (
          <div className="mb-6 rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-100 dark:bg-yellow-900/20 p-4 text-sm text-yellow-800 dark:text-yellow-300">
            <p className="font-semibold">Restart required to apply staged changes</p>
            <p className="mt-1 text-yellow-800 dark:text-yellow-200">
              One or more node IPs are staged but not yet applied. To apply them, an operator runs the following on
              node-01, which backs up and rewrites{" "}
              <code className="rounded bg-black/30 px-1">ivgs-infra/.env</code> then recreates the stack:
            </p>
            <pre className="mt-2 overflow-x-auto rounded bg-black/40 px-3 py-2 text-xs text-yellow-100">scripts/apply-node-config.sh</pre>
            <p className="mt-2 text-yellow-800 dark:text-yellow-200">node-01 will go briefly offline during the restart.</p>
          </div>
        )}

        {/* Server advisories (out-of-subnet / duplicates / ignored node-01) */}
        {warnings.length > 0 && (
          <div className="mb-6 rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-100 dark:bg-orange-900/20 p-4 text-sm text-orange-800 dark:text-orange-300">
            <p className="font-semibold">Advisories</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-orange-800 dark:text-orange-200">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Node IP table */}
        {loading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="lg" label="Loading node configuration..." />
          </div>
        ) : loadError ? (
          <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-100 dark:bg-red-900/20 p-6 text-center text-red-600 dark:text-red-400">
            <p>Failed to load node configuration</p>
            <p className="mt-1 text-sm text-red-800 dark:text-red-300">{loadError}</p>
            <button onClick={() => load()} className="mt-2 rounded bg-gray-100 dark:bg-gray-800 px-3 py-1 text-sm hover:bg-gray-200 dark:hover:bg-gray-700">
              Retry
            </button>
          </div>
        ) : !config ? (
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-8 text-center text-gray-500 dark:text-gray-400">
            No node configuration available.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/50 text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  <tr>
                    <th className="px-4 py-3">Node</th>
                    <th className="px-4 py-3">Role</th>
                    <th className="px-4 py-3">Applied IP</th>
                    <th className="px-4 py-3">New IP</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {config.nodes.map((node) => {
                    if (!node.editable) {
                      return (
                        <tr key={node.node_id} className="hover:bg-gray-100 dark:hover:bg-gray-800/50">
                          <td className="whitespace-nowrap px-4 py-3 font-mono text-gray-800 dark:text-gray-200">{node.node_id}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-gray-700 dark:text-gray-300">{node.role}</td>
                          <td className="whitespace-nowrap px-4 py-3 font-mono text-gray-500 dark:text-gray-400">{node.applied_ip}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-xs text-gray-500 dark:text-gray-400">Router / host assigned</td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <span className="inline-flex rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs font-medium text-gray-500 dark:text-gray-400">
                              Fixed
                            </span>
                          </td>
                        </tr>
                      );
                    }
                    const value = edits[node.node_id] ?? "";
                    const changed = value.trim() !== node.applied_ip;
                    const invalid = !isValidIPv4(value);
                    const offSubnet = !invalid && !sameSubnet24(value, node01Ip);
                    return (
                      <tr key={node.node_id} className="hover:bg-gray-100 dark:hover:bg-gray-800/50">
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-gray-800 dark:text-gray-200">{node.node_id}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-gray-700 dark:text-gray-300">{node.role}</td>
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-gray-500 dark:text-gray-400">{node.applied_ip}</td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <input
                            type="text"
                            value={value}
                            onChange={(e) => setEdits((prev) => ({ ...prev, [node.node_id]: e.target.value }))}
                            aria-label={`${node.node_id} IP address`}
                            className={`w-40 rounded-lg border bg-gray-100 dark:bg-gray-800 px-3 py-2 font-mono text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 ${
                              invalid
                                ? "border-red-200 dark:border-red-700 focus:border-red-500 focus:ring-red-500"
                                : "border-gray-300 dark:border-gray-700 focus:border-ivgs-500 focus:ring-ivgs-500"
                            }`}
                          />
                          {offSubnet && (
                            <p className="mt-1 text-xs text-orange-600 dark:text-orange-400">Different subnet from node-01</p>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          {invalid ? (
                            <span className="inline-flex rounded-full bg-red-100 dark:bg-red-900/30 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400">
                              Invalid IPv4
                            </span>
                          ) : changed ? (
                            <span className="inline-flex rounded-full bg-yellow-100 dark:bg-yellow-900/30 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:text-yellow-300">
                              Pending
                            </span>
                          ) : (
                            <span className="inline-flex rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-xs font-medium text-green-600 dark:text-green-400">
                              Applied
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
              Expected subnet: <span className="font-mono">{config.expected_subnet}</span> (derived from node-01).
              node-01 is fixed and shown for reference. IPs outside the subnet are allowed but flagged as advisories.
              Staged changes take effect only after the host apply step and stack restart.
            </p>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                onClick={handleDiscard}
                disabled={saving || applying || !(dirty || restartRequired)}
                className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
              >
                Discard Pending
              </button>
              <button
                onClick={handleSave}
                disabled={saving || applying || !dirty || invalidCount > 0}
                className="rounded-lg bg-ivgs-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ivgs-500 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Stage Changes"}
              </button>
              <button
                onClick={() => setConfirmApply(true)}
                disabled={saving || applying || !restartRequired}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-500 disabled:opacity-50"
              >
                {applying ? "Applying..." : "Apply & Restart"}
              </button>
            </div>
          </>
        )}

        {/* Apply & Restart confirmation */}
        {confirmApply && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="mx-4 w-full max-w-md rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Apply node IP changes and restart?</h2>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                This rewrites <code className="rounded bg-black/30 px-1">ivgs-infra/.env</code> on node-01 (a backup is
                kept) and recreates the stack so the staged IPs take effect. The API will be briefly unavailable
                (typically 10–30 seconds) while it restarts. This page updates automatically when it returns.
              </p>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setConfirmApply(false)}
                  className="rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleApply()}
                  className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-500"
                >
                  Apply &amp; Restart
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
