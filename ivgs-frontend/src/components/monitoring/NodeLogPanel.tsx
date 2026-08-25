"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  NodeContainersResponse,
  NodeLogLine,
  NodeLogsResponse,
} from "@/types/api";

/**
 * Node Monitor - per-node container logs (WP-48-TELEMETRY Task 3).
 *
 * WHAT THIS REPLACES. The node detail modal used to render two static
 * paragraphs:
 *
 *     Live log streaming via WebSocket - connect to
 *     ws://node-01:8000/api/v1/nodes/{hostname}/logs/stream
 *     [Log output will appear here in real-time]
 *
 * No line ever appeared, on any node, because that endpoint has never existed
 * and the one that did (`WS /api/v1/ws/nodes/{id}/logs`) shelled out to `ssh`
 * from a container with no ssh binary. Both are gone; see
 * ivgs-api/app/core/node_logs.py.
 *
 * WHAT THIS IS. A POLLED TAIL of one container's logs, read from that node's
 * `ivgs-node-logs` source. It says so on the panel rather than calling itself
 * live: the honest name for re-fetching the last N lines every few seconds is
 * not "streaming", and the difference is visible to anyone watching a chatty
 * container.
 *
 * WHAT IT DOES WHEN IT CANNOT. A node with no log source deployed, or one that
 * is down, shows the reason the API gave. It never shows an empty pane, because
 * an empty pane is indistinguishable from a quiet container - which is exactly
 * how the old placeholder went unnoticed for as long as it did.
 */

const POLL_MS = 3000;
const TAIL = 300;

const LEVEL_ORDER: Record<string, number> = {
  critical: 0,
  error: 1,
  warning: 2,
  info: 3,
  debug: 4,
};

const LEVEL_CLASS: Record<string, string> = {
  critical: "text-red-500 dark:text-red-400 font-semibold",
  error: "text-red-600 dark:text-red-400",
  warning: "text-amber-600 dark:text-amber-400",
  info: "text-gray-700 dark:text-gray-300",
  debug: "text-gray-500 dark:text-gray-500",
};

interface NodeLogPanelProps {
  nodeId: string;
  hostname: string;
  /** Level filter from the modal's existing control: all|error|warning|info|debug */
  levelFilter: string;
  /** Free-text search from the modal's existing control. */
  search: string;
}

export default function NodeLogPanel({
  nodeId,
  hostname,
  levelFilter,
  search,
}: NodeLogPanelProps): React.ReactElement {
  const [containers, setContainers] = useState<NodeContainersResponse | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [logs, setLogs] = useState<NodeLogsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [follow, setFollow] = useState<boolean>(true);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // --- container list, once per node ---------------------------------------
  useEffect(() => {
    let cancelled = false;
    setContainers(null);
    setLogs(null);
    setSelected("");
    setLoadError(null);
    apiClient
      .get<NodeContainersResponse>(`/api/v1/nodes/${nodeId}/containers`)
      .then((res) => {
        if (cancelled) return;
        setContainers(res.data);
        const first =
          res.data.containers.find((c) => c.state === "running") ??
          res.data.containers[0];
        if (first) setSelected(first.name);
      })
      .catch((err: Error) => {
        if (!cancelled) setLoadError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  // --- poll the tail --------------------------------------------------------
  const poll = useCallback(async (): Promise<void> => {
    if (!selected) return;
    try {
      const res = await apiClient.get<NodeLogsResponse>(
        `/api/v1/nodes/${nodeId}/logs`,
        { container: selected, tail: String(TAIL) }
      );
      setLogs(res.data);
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message);
    }
  }, [nodeId, selected]);

  useEffect(() => {
    if (!selected) return;
    void poll();
    const id = setInterval(() => void poll(), POLL_MS);
    return () => clearInterval(id);
  }, [selected, poll]);

  // --- client-side filtering ------------------------------------------------
  const visible: NodeLogLine[] = useMemo(() => {
    const lines = logs?.lines ?? [];
    const needle = search.trim().toLowerCase();
    const wanted = levelFilter.toLowerCase();
    return lines.filter((line) => {
      if (wanted !== "all") {
        // A line whose level could not be inferred is NOT silently counted as
        // matching. The API returns null for those on purpose.
        if (line.level === null) return false;
        const lineRank = LEVEL_ORDER[line.level];
        const wantedRank = LEVEL_ORDER[wanted];
        // An unrecognised filter value must not silently hide everything.
        if (lineRank === undefined || wantedRank === undefined) return true;
        if (lineRank > wantedRank) return false;
      }
      if (needle && !line.message.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [logs, levelFilter, search]);

  useEffect(() => {
    if (follow) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [visible, follow]);

  const download = useCallback((): void => {
    const body = (logs?.lines ?? [])
      .map((l) => `${l.timestamp ?? ""} ${l.message}`.trim())
      .join("\n");
    const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${hostname}-${selected || "logs"}.log`;
    a.click();
    URL.revokeObjectURL(url);
  }, [logs, hostname, selected]);

  const unavailableReason =
    loadError ??
    (containers && !containers.available ? containers.reason : null) ??
    (logs && !logs.available ? logs.reason : null);

  return (
    <div className="flex flex-col min-h-[300px]">
      {/* Source line + container picker */}
      <div className="flex flex-wrap items-center gap-3 px-6 py-2 border-b border-gray-200 dark:border-gray-800 text-xs">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={!containers?.available || containers.containers.length === 0}
          className="px-2 py-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-white text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        >
          {(containers?.containers ?? []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
              {c.state === "running" ? "" : ` (${c.state ?? "stopped"})`}
            </option>
          ))}
          {(containers?.containers.length ?? 0) === 0 && (
            <option value="">no containers</option>
          )}
        </select>

        <label className="flex items-center gap-1 text-gray-500 dark:text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
            className="accent-blue-500"
          />
          follow
        </label>

        <button
          type="button"
          onClick={download}
          disabled={!logs?.lines?.length}
          className="px-2 py-1 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-40 transition-colors"
        >
          Download
        </button>

        {/* Say what this is. It is not a stream, and calling it one was the
            original defect. */}
        <span className="ml-auto text-gray-500 dark:text-gray-500">
          polled tail — last {TAIL} lines every {POLL_MS / 1000}s
          {logs?.source ? ` from ${logs.source}` : ""}
        </span>
      </div>

      {/* The pane */}
      <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50 dark:bg-gray-950 font-mono text-xs min-h-[260px]">
        {unavailableReason ? (
          <div className="rounded-lg border border-amber-300 dark:border-amber-700/60 bg-amber-50 dark:bg-amber-900/20 p-3">
            <p className="text-amber-800 dark:text-amber-300 font-sans font-medium mb-1">
              No logs available for {hostname}
            </p>
            <p className="text-amber-700 dark:text-amber-400/90 font-sans text-[11px] leading-snug">
              {unavailableReason}
            </p>
          </div>
        ) : !logs ? (
          <p className="text-gray-500 dark:text-gray-400 italic font-sans">
            Loading logs from {hostname}…
          </p>
        ) : visible.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 italic font-sans">
            {logs.lines.length === 0
              ? `${selected} has produced no log output.`
              : `None of the last ${logs.lines.length} lines match this filter.`}
          </p>
        ) : (
          <>
            {visible.map((line, i) => (
              <div
                key={`${line.timestamp ?? i}-${i}`}
                className="whitespace-pre-wrap break-all leading-relaxed"
              >
                {line.timestamp && (
                  <span className="text-gray-400 dark:text-gray-600 mr-2">
                    {line.timestamp.slice(11, 23)}
                  </span>
                )}
                <span className={LEVEL_CLASS[line.level ?? "info"]}>
                  {line.message}
                </span>
              </div>
            ))}
            <div ref={bottomRef} />
          </>
        )}
      </div>
    </div>
  );
}
