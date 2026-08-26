"use client";

import React, { useState, useCallback } from "react";
import { useNodes } from "@/hooks/useNodes";
import { useAuth } from "@/hooks/useAuth";
import NodeCard from "@/components/NodeCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import NodeLogPanel from "@/components/monitoring/NodeLogPanel";
import type { NodeStatus } from "@/types/api";
import StateBadge from "@/components/StateBadge";

/**
 * §8.1.5 Node Monitor Page
 *
 * Card grid: one card per node (node-01 through node-06). Each card shows:
 *   - Node name, online/offline status
 *   - GPU model, VRAM total/used (progress bar)
 *   - GPU utilization %, GPU temperature (color coded)
 *   - GPU power draw vs TDP
 *   - CPU/RAM mini-bars
 *   - Current active job
 *
 * Polls /api/v1/nodes every 10 seconds.
 *
 * Node Detail Modal:
 *   - Real container logs (WP-48). A POLLED TAIL from that node's
 *     `ivgs-node-logs` source, NOT a WebSocket stream. This block used to say
 *     "Live-streaming log output (WebSocket)" and the pane below it printed the
 *     ws:// URL as prose; no line was ever displayed on any node, because the
 *     advertised endpoint did not exist. See components/monitoring/NodeLogPanel.
 *   - Log level filter, free-text search - now applied to real lines
 *   - Log download - now the fetched lines, not a broken <a download> to an
 *     unauthenticated route that never existed either
 *
 * RBAC per Table 8-3:
 *   - admin: full detail + logs
 *   - operator: status only
 *   - viewer: no access (handled by middleware)
 */

export default function NodesPage(): React.ReactElement {
  const { user } = useAuth();
  const { nodes, isLoading, error } = useNodes();

  const [selectedNode, setSelectedNode] = useState<NodeStatus | null>(null);
  const [showDetailModal, setShowDetailModal] = useState<boolean>(false);
  const [logFilter, setLogFilter] = useState<string>("all");
  const [logSearch, setLogSearch] = useState<string>("");

  const isAdmin = user?.role === "admin";

  const handleNodeClick = useCallback(
    (node: NodeStatus): void => {
      if (!isAdmin) return;
      setSelectedNode(node);
      setShowDetailModal(true);
    },
    [isAdmin]
  );

  const handleCloseModal = useCallback((): void => {
    setShowDetailModal(false);
    setSelectedNode(null);
    setLogFilter("all");
    setLogSearch("");
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" label="Loading node status…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400">
          Failed to load node status: {error.message}
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Node Monitor</h1>
            <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
              {/* WP-57 Task 4. "6 nodes" and Operational Monitoring's "3"
                  are both true and were both unlabelled, so they read as a
                  contradiction. This page counts MACHINES in the fleet
                  topology - including node-01, which is CPU-only
                  infrastructure. Operational Monitoring counts GPU workers
                  registered with the scheduler, which is a subset. */}
              {nodes?.length || 0} machines in the fleet — including node-01
              (CPU-only) — polling every 10s
            </p>
          </div>
          {/* WP-24: counts derive from real per-node checks. The old version
              counted `status !== "online"` as offline, which folded "unknown"
              into "offline" -- the same collapse the API fix removed. Unknown
              is counted, and shown, separately. */}
          <div className="flex items-center gap-2 text-sm">
            <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              {nodes?.filter((n: NodeStatus) => n.status?.toLowerCase() === "online").length ?? 0}{" "}
              online
            </span>
            <span className="text-gray-600 dark:text-gray-400">|</span>
            <span className="text-red-600 dark:text-red-400">
              {nodes?.filter((n: NodeStatus) => n.status?.toLowerCase() === "offline").length ?? 0}{" "}
              offline
            </span>
            {(nodes?.filter((n: NodeStatus) => n.status?.toLowerCase() === "unknown").length ?? 0) > 0 && (
              <>
                <span className="text-gray-600 dark:text-gray-400">|</span>
                <span className="text-gray-500 dark:text-gray-400">
                  {nodes?.filter((n: NodeStatus) => n.status?.toLowerCase() === "unknown").length ?? 0}{" "}
                  unknown
                </span>
              </>
            )}
          </div>
        </div>

        {!nodes || nodes.length === 0 ? (
          <div className="text-center py-16 text-gray-500 dark:text-gray-400">
            No nodes registered in the cluster.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {nodes.map((node: NodeStatus) => (
              <NodeCard
                key={node.node_id}
                node={node}
                onClick={isAdmin ? handleNodeClick : undefined}
                showDetailHint={isAdmin}
              />
            ))}
          </div>
        )}

        {/* ── Node Detail Modal (Admin only) ───────────────────────── */}
        {showDetailModal && selectedNode && isAdmin && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
            onClick={handleCloseModal}
          >
            <div
              className="bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-300 dark:border-gray-700">
                <div>
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                    {selectedNode.hostname}
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {selectedNode.gpu_model ?? "Unknown GPU"} — {selectedNode.status.charAt(0).toUpperCase() + selectedNode.status.slice(1)}
                  </p>
                </div>
                <button
                  onClick={handleCloseModal}
                  className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                >
                  <svg
                    className="w-6 h-6"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Log Controls */}
              <div className="flex items-center gap-4 px-6 py-3 border-b border-gray-300 dark:border-gray-700">
                <select
                  value={logFilter}
                  onChange={(e) => setLogFilter(e.target.value)}
                  className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="all">All Levels</option>
                  <option value="error">Error</option>
                  <option value="warning">Warning</option>
                  <option value="info">Info</option>
                  <option value="debug">Debug</option>
                </select>
                <input
                  type="text"
                  value={logSearch}
                  onChange={(e) => setLogSearch(e.target.value)}
                  placeholder="Search logs…"
                  className="flex-1 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {/* Download moved into NodeLogPanel: an <a download> cannot
                    carry the Bearer token this API requires, and
                    /logs/download was never a registered route. */}
              </div>

              {/* Container logs - real ones. WP-48. */}
              <div className="flex-1 overflow-hidden flex flex-col">
                <NodeLogPanel
                  nodeId={selectedNode.node_id}
                  hostname={selectedNode.hostname}
                  levelFilter={logFilter}
                  search={logSearch}
                />
              </div>

              {/* Historical Jobs */}
              <div className="px-6 py-4 border-t border-gray-300 dark:border-gray-700">
                <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                  Recent Jobs on {selectedNode.hostname}
                </h4>
                <p className="text-xs text-gray-600 dark:text-gray-400 italic">
                  Per-node job history not yet available. Pending Phase H multi-node
                  deployment; see GPU Fleet Monitoring Spec v1.1 carry-forward.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
