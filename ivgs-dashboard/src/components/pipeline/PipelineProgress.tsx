import React, { useState, useEffect, useCallback, useRef } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface StageStatus {
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  started_at: string | null;
  completed_at: string | null;
  attempt: number;
  checkpoint_restored: boolean;
  elapsed_s: number | null;
}

interface JobStatus {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  progress: number;        // 0–100
  stages: StageStatus[];
  cost_usd: number;
  checkpoint_count: number;
  created_at: string;
  estimated_remaining_s: number | null;
  error?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const STAGE_ORDER = [
  "transcript", "storyboard", "image_generation",
  "tts", "talking_head", "motion_graphics", "composition",
];

const STATUS_COLOR: Record<string, string> = {
  pending:   "#6b7280",
  running:   "#3b82f6",
  completed: "#22c55e",
  failed:    "#ef4444",
  skipped:   "#d1d5db",
};

function fmtDuration(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

const StageRow: React.FC<{ stage: StageStatus }> = ({ stage }) => {
  const color = STATUS_COLOR[stage.status] ?? "#6b7280";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0",
                  borderBottom: "1px solid #1e293b" }}>
      {/* Status indicator */}
      <div style={{ width: 12, height: 12, borderRadius: "50%",
                    background: color, flexShrink: 0 }} />
      {/* Stage name */}
      <span style={{ width: 160, fontSize: 13, color: "#e2e8f0",
                     textTransform: "capitalize" }}>
        {stage.name.replace("_", " ")}
      </span>
      {/* Status text */}
      <span style={{ width: 80, fontSize: 12, color }}>{stage.status}</span>
      {/* Elapsed */}
      <span style={{ width: 60, fontSize: 11, color: "#94a3b8" }}>
        {stage.elapsed_s !== null ? fmtDuration(stage.elapsed_s) : "—"}
      </span>
      {/* Attempt count */}
      {stage.attempt > 1 && (
        <span style={{ fontSize: 11, color: "#f59e0b", marginLeft: 4 }}>
          retry ×{stage.attempt - 1}
        </span>
      )}
      {/* Checkpoint restored badge */}
      {stage.checkpoint_restored && (
        <span style={{ fontSize: 10, background: "#1d4ed8", color: "#bfdbfe",
                       padding: "1px 6px", borderRadius: 4 }}>
          ckpt restored
        </span>
      )}
    </div>
  );
};

// ─── Main Component ──────────────────────────────────────────────────────────

interface PipelineProgressProps {
  jobId: string;
  apiBase?: string;
  pollIntervalMs?: number;
}

export const PipelineProgress: React.FC<PipelineProgressProps> = ({
  jobId,
  apiBase = "/api/v4",
  pollIntervalMs = 5000,
}) => {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const timerRef            = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/jobs/${jobId}/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: JobStatus = await res.json();
      setStatus(data);
      setError(null);
      // Stop polling once terminal
      if (data.status === "completed" || data.status === "failed") {
        if (timerRef.current) clearInterval(timerRef.current);
      }
    } catch (e: any) {
      setError(e.message ?? "Unknown error");
    }
  }, [jobId, apiBase]);

  useEffect(() => {
    fetchStatus();
    timerRef.current = setInterval(fetchStatus, pollIntervalMs);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetchStatus, pollIntervalMs]);

  if (error) return (
    <div style={{ color: "#ef4444", padding: 12 }}>Error: {error}</div>
  );
  if (!status) return (
    <div style={{ color: "#94a3b8", padding: 12 }}>Loading…</div>
  );

  const orderedStages = STAGE_ORDER.map(
    name => status.stages.find(s => s.name === name)
  ).filter(Boolean) as StageStatus[];

  return (
    <div style={{ fontFamily: "Inter, sans-serif", background: "#0f172a",
                  borderRadius: 8, padding: 20, color: "#e2e8f0" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 15, color: "#f8fafc" }}>
          Pipeline Progress — {jobId.slice(0, 8)}…
        </h3>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>
          Cost: ${status.cost_usd.toFixed(3)}
          {status.estimated_remaining_s !== null &&
            ` · ETA ${fmtDuration(status.estimated_remaining_s)}`}
        </span>
      </div>
      {/* Overall progress bar */}
      <div style={{ background: "#1e293b", borderRadius: 4,
                    height: 8, marginBottom: 16, overflow: "hidden" }}>
        <div style={{
          width: `${status.progress}%`, height: "100%",
          background: status.status === "failed" ? "#ef4444" : "#3b82f6",
          transition: "width 0.5s ease",
        }} />
      </div>
      {/* Stage rows */}
      {orderedStages.map(s => <StageRow key={s.name} stage={s} />)}
      {/* Footer */}
      <div style={{ marginTop: 12, fontSize: 11, color: "#64748b",
                    display: "flex", gap: 16 }}>
        <span>Checkpoints: {status.checkpoint_count}</span>
        <span>Status: {status.status}</span>
        {status.error && <span style={{ color: "#f87171" }}>{status.error}</span>}
      </div>
    </div>
  );
};

export default PipelineProgress;
