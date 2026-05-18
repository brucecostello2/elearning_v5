import React, { useState, useCallback } from "react";
import { PipelineProgress } from "./PipelineProgress";

// ─── Types ───────────────────────────────────────────────────────────────────

interface JobSubmitRequest {
  prompt: string;
  style?: string;
  duration_s?: number;
  budget_usd?: number;
  checkpoint_enabled?: boolean;
}

interface JobSubmitResponse {
  job_id: string;
  estimated_cost_usd: number;
  estimated_duration_s: number;
  status: string;
}

// ─── Preset Templates ────────────────────────────────────────────────────────

const PRESETS = [
  {
    label: "Product Explainer",
    prompt: "Create a 60-second product explainer video for a B2B SaaS analytics tool. Use a professional talking-head presenter with animated charts showing growth metrics.",
    style: "corporate",
    duration_s: 60,
  },
  {
    label: "Social Short",
    prompt: "Generate a 15-second social media clip promoting a new mobile app. Upbeat music, bold text overlays, quick cuts showing app screenshots.",
    style: "social",
    duration_s: 15,
  },
  {
    label: "Educational Tutorial",
    prompt: "Produce a 90-second tutorial video explaining how neural networks work. Use animated diagrams and a calm narrating voice.",
    style: "educational",
    duration_s: 90,
  },
];

// ─── Subcomponents ───────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155",
  borderRadius: 6, padding: "8px 12px", fontSize: 13, width: "100%",
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  fontSize: 12, color: "#94a3b8", marginBottom: 4, display: "block",
};

// ─── Main Component ──────────────────────────────────────────────────────────

interface PromptPlaygroundProps {
  apiBase?: string;
}

export const PromptPlayground: React.FC<PromptPlaygroundProps> = ({
  apiBase = "/api/v4",
}) => {
  const [prompt, setPrompt]           = useState("");
  const [style, setStyle]             = useState("corporate");
  const [duration, setDuration]       = useState(60);
  const [budget, setBudget]           = useState(5.0);
  const [checkpoints, setCheckpoints] = useState(true);

  const [submitting, setSubmitting]   = useState(false);
  const [jobId, setJobId]             = useState<string | null>(null);
  const [submitResp, setSubmitResp]   = useState<JobSubmitResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showRaw, setShowRaw]         = useState(false);

  const applyPreset = useCallback((preset: typeof PRESETS[0]) => {
    setPrompt(preset.prompt);
    setStyle(preset.style);
    setDuration(preset.duration_s);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!prompt.trim()) return;
    setSubmitting(true);
    setJobId(null);
    setSubmitResp(null);
    setSubmitError(null);
    try {
      const body: JobSubmitRequest = {
        prompt: prompt.trim(),
        style,
        duration_s: duration,
        budget_usd: budget,
        checkpoint_enabled: checkpoints,
      };
      const res = await fetch(`${apiBase}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      const data: JobSubmitResponse = await res.json();
      setSubmitResp(data);
      setJobId(data.job_id);
    } catch (e: any) {
      setSubmitError(e.message ?? "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }, [prompt, style, duration, budget, checkpoints, apiBase]);

  return (
    <div style={{ fontFamily: "Inter, sans-serif", color: "#e2e8f0",
                  display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: "#f8fafc" }}>
          Prompt Playground
        </h3>
        <span style={{ fontSize: 11, background: "#1d4ed8", color: "#bfdbfe",
                       padding: "2px 8px", borderRadius: 12 }}>Phase 1</span>
      </div>

      {/* Preset buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        {PRESETS.map(p => (
          <button key={p.label} onClick={() => applyPreset(p)}
            style={{ padding: "5px 12px", fontSize: 12, background: "#1e293b",
                     color: "#94a3b8", border: "1px solid #334155",
                     borderRadius: 4, cursor: "pointer" }}>
            {p.label}
          </button>
        ))}
      </div>

      {/* Prompt input */}
      <div>
        <label style={labelStyle}>Prompt</label>
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)}
          rows={4} style={{ ...inputStyle, resize: "vertical" }}
          placeholder="Describe the video you want to generate…" />
      </div>

      {/* Parameters row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr",
                    gap: 12 }}>
        <div>
          <label style={labelStyle}>Style</label>
          <select value={style} onChange={e => setStyle(e.target.value)}
            style={inputStyle}>
            <option value="corporate">Corporate</option>
            <option value="social">Social</option>
            <option value="educational">Educational</option>
            <option value="cinematic">Cinematic</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Duration (s)</label>
          <input type="number" value={duration} min={10} max={300}
            onChange={e => setDuration(Number(e.target.value))}
            style={inputStyle} />
        </div>
        <div>
          <label style={labelStyle}>Budget (USD)</label>
          <input type="number" value={budget} min={0.5} max={50} step={0.5}
            onChange={e => setBudget(Number(e.target.value))}
            style={inputStyle} />
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <label style={labelStyle}>Checkpoints</label>
          <label style={{ display: "flex", alignItems: "center", gap: 8,
                          cursor: "pointer", marginTop: 6 }}>
            <input type="checkbox" checked={checkpoints}
              onChange={e => setCheckpoints(e.target.checked)} />
            <span style={{ fontSize: 13 }}>Enabled</span>
          </label>
        </div>
      </div>

      {/* Submit button */}
      <button onClick={handleSubmit} disabled={submitting || !prompt.trim()}
        style={{ padding: "10px 24px", fontSize: 14, fontWeight: 600,
                 background: submitting ? "#1e3a5f" : "#1d4ed8",
                 color: "#fff", border: "none", borderRadius: 6,
                 cursor: submitting ? "not-allowed" : "pointer",
                 alignSelf: "flex-start" }}>
        {submitting ? "Submitting…" : "Submit Job"}
      </button>

      {/* Error */}
      {submitError && (
        <div style={{ color: "#f87171", fontSize: 13 }}>Error: {submitError}</div>
      )}

      {/* Response summary */}
      {submitResp && (
        <div style={{ background: "#0f172a", borderRadius: 8, padding: 14,
                      border: "1px solid #1e3a5f" }}>
          <div style={{ display: "flex", gap: 24, marginBottom: 10 }}>
            <span style={{ fontSize: 13 }}>
              Job ID: <code style={{ color: "#60a5fa" }}>{submitResp.job_id}</code>
            </span>
            <span style={{ fontSize: 13 }}>
              Est. cost: <strong style={{ color: "#22c55e" }}>
                ${submitResp.estimated_cost_usd.toFixed(3)}
              </strong>
            </span>
            <span style={{ fontSize: 13 }}>
              Est. time: {submitResp.estimated_duration_s}s
            </span>
            <button onClick={() => setShowRaw(v => !v)}
              style={{ marginLeft: "auto", fontSize: 11, background: "none",
                       color: "#64748b", border: "none", cursor: "pointer" }}>
              {showRaw ? "Hide" : "Show"} raw JSON
            </button>
          </div>
          {showRaw && (
            <pre style={{ fontSize: 11, color: "#94a3b8", margin: 0,
                          overflowX: "auto" }}>
              {JSON.stringify(submitResp, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Pipeline progress */}
      {jobId && (
        <PipelineProgress jobId={jobId} apiBase={apiBase} />
      )}
    </div>
  );
};

export default PromptPlayground;
