import React, { useState, useEffect, useCallback } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface GpuInfo {
  id: number;
  vram_total_gb: number;
  vram_used_gb: number;
  utilization_pct: number;
  model: string;
}

interface NodeStatus {
  node_id: string;
  ip: string;
  status: "healthy" | "degraded" | "offline";
  last_heartbeat: string;
  active_tasks: number;
  gpus: GpuInfo[];
  uptime_s: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const NODE_STATUS_COLOR: Record<string, string> = {
  healthy:  "#22c55e",
  degraded: "#f59e0b",
  offline:  "#ef4444",
};

function vramPct(gpu: GpuInfo): number {
  return Math.round((gpu.vram_used_gb / gpu.vram_total_gb) * 100);
}

function fmtUptime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

// ─── VramBar ─────────────────────────────────────────────────────────────────

const VramBar: React.FC<{ gpu: GpuInfo }> = ({ gpu }) => {
  const pct = vramPct(gpu);
  const barColor = pct > 85 ? "#ef4444" : pct > 65 ? "#f59e0b" : "#22c55e";
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    fontSize: 10, color: "#94a3b8", marginBottom: 2 }}>
        <span>GPU {gpu.id} · {gpu.model}</span>
        <span>{gpu.vram_used_gb.toFixed(1)}/{gpu.vram_total_gb}GB ({pct}%)</span>
      </div>
      <div style={{ background: "#1e293b", borderRadius: 3, height: 6 }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3,
                      background: barColor, transition: "width 0.5s ease" }} />
      </div>
    </div>
  );
};

// ─── NodeCard ─────────────────────────────────────────────────────────────────

const NodeCard: React.FC<{ node: NodeStatus }> = ({ node }) => {
  const statusColor = NODE_STATUS_COLOR[node.status] ?? "#6b7280";
  return (
    <div style={{ background: "#0f172a", borderRadius: 8, padding: 14,
                  border: `1px solid ${statusColor}33`, minWidth: 220 }}>
      {/* Node header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ width: 10, height: 10, borderRadius: "50%",
                      background: statusColor, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: "#f8fafc" }}>
          {node.node_id}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#64748b" }}>
          {node.ip}
        </span>
      </div>
      {/* GPU bars */}
      {node.gpus.map(g => <VramBar key={g.id} gpu={g} />)}
      {/* Footer stats */}
      <div style={{ display: "flex", gap: 12, marginTop: 8,
                    fontSize: 11, color: "#64748b" }}>
        <span>Tasks: {node.active_tasks}</span>
        <span>Up: {fmtUptime(node.uptime_s)}</span>
        <span style={{ marginLeft: "auto", color: statusColor }}>
          {node.status}
        </span>
      </div>
    </div>
  );
};

// ─── Main Component ──────────────────────────────────────────────────────────

interface GpuFleetStatusProps {
  apiBase?: string;
  pollIntervalMs?: number;
}

export const GpuFleetStatus: React.FC<GpuFleetStatusProps> = ({
  apiBase = "/api/v4",
  pollIntervalMs = 15000,
}) => {
  const [nodes, setNodes]     = useState<NodeStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLast] = useState<Date | null>(null);

  const fetchNodes = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/gpu/nodes`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: NodeStatus[] = await res.json();
      setNodes(data);
      setLast(new Date());
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchNodes();
    const id = setInterval(fetchNodes, pollIntervalMs);
    return () => clearInterval(id);
  }, [fetchNodes, pollIntervalMs]);

  const healthy   = nodes.filter(n => n.status === "healthy").length;
  const degraded  = nodes.filter(n => n.status === "degraded").length;
  const offline   = nodes.filter(n => n.status === "offline").length;

  return (
    <div style={{ fontFamily: "Inter, sans-serif", color: "#e2e8f0" }}>
      {/* Header bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 15, color: "#f8fafc" }}>GPU Fleet Status</h3>
        <span style={{ fontSize: 12, color: "#22c55e" }}>{healthy} healthy</span>
        {degraded > 0 && <span style={{ fontSize: 12, color: "#f59e0b" }}>{degraded} degraded</span>}
        {offline  > 0 && <span style={{ fontSize: 12, color: "#ef4444" }}>{offline} offline</span>}
        <button onClick={fetchNodes}
          style={{ marginLeft: "auto", padding: "4px 12px", fontSize: 12,
                   background: "#1e293b", color: "#94a3b8", border: "none",
                   borderRadius: 4, cursor: "pointer" }}>
          Refresh
        </button>
      </div>
      {loading && <div style={{ color: "#64748b" }}>Loading…</div>}
      {/* Node grid */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {nodes.map(n => <NodeCard key={n.node_id} node={n} />)}
      </div>
      {lastRefresh && (
        <div style={{ marginTop: 10, fontSize: 11, color: "#475569" }}>
          Last updated: {lastRefresh.toLocaleTimeString()}
        </div>
      )}
    </div>
  );
};

export default GpuFleetStatus;
