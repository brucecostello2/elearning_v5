import React, { useState, useEffect, useRef } from 'react';

interface AiVideoGeneration {
  id: number;
  scene_id: string;
  model_name: string;
  prompt: string;
  output_path: string | null;
  quality_score: number | null;
  fallback_level_used: number;
  generation_duration_seconds: number | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

interface AIVideoPreviewProps {
  jobId: string;
  onRegenerate?: (sceneId: string, model: string) => void;
}

const MODEL_OPTIONS = [
  { value: 'cogvideox', label: 'CogVideoX-5B (24GB VRAM)' },
  { value: 'cogvideox_2b', label: 'CogVideoX-2B (14GB VRAM)' },
  { value: 'wan21', label: 'Wan2.1 T2V (16GB VRAM, ≤30s)' },
];

const FALLBACK_LABELS: Record<number, string> = {
  1: 'AI Video (L1)',
  2: 'Ken Burns (L2)',
  3: 'Zoom/Pan (L3)',
  4: 'Static (L4)',
};

export const AIVideoPreview: React.FC<AIVideoPreviewProps> = ({
  jobId, onRegenerate,
}) => {
  const [generations, setGenerations] = useState<AiVideoGeneration[]>([]);
  const [selected, setSelected] = useState<AiVideoGeneration | null>(null);
  const [modelChoice, setModelChoice] = useState('cogvideox');
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<{
    success_rate: number; fallback_rate: number; avg_duration_s: number;
  } | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const API = process.env.REACT_APP_API_URL || '';

  useEffect(() => {
    fetchGenerations();
    fetchStats();
    const interval = setInterval(fetchGenerations, 15000);
    return () => clearInterval(interval);
  }, [jobId]);

  const fetchGenerations = async () => {
    try {
      const r = await fetch(
        `${API}/api/v1/jobs/${jobId}/ai-video/generations`);
      if (r.ok) setGenerations(await r.json());
    } catch (e) { /* swallow */ }
  };

  const fetchStats = async () => {
    try {
      const r = await fetch(`${API}/api/v1/ai-video/stats?hours=24`);
      if (r.ok) setStats(await r.json());
    } catch (e) { /* swallow */ }
  };

  const handleRegenerate = async (gen: AiVideoGeneration) => {
    if (!onRegenerate) return;
    setLoading(true);
    try {
      onRegenerate(gen.scene_id, modelChoice);
    } finally {
      setLoading(false);
    }
  };

  const getFallbackBadgeColor = (level: number) => {
    if (level === 1) return '#22aa44';
    if (level === 2) return '#e07800';
    return '#cc3300';
  };

  return (
    <div style={{
      background: '#1a1a1a', color: '#eee',
      borderRadius: 8, padding: 20, fontFamily: 'monospace',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: '#ffcc44' }}>AI Video Preview</h3>
        {stats && (
          <div style={{ fontSize: 11, color: '#aaa', textAlign: 'right' }}>
            <div>L1 success: {(stats.success_rate * 100).toFixed(1)}%</div>
            <div>Fallback rate: {(stats.fallback_rate * 100).toFixed(1)}%</div>
            <div>Avg: {stats.avg_duration_s.toFixed(0)}s</div>
          </div>
        )}
      </div>

      {/* Scene grid */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap',
                    marginBottom: 16 }}>
        {generations.map(gen => (
          <div
            key={gen.id}
            onClick={() => setSelected(gen)}
            style={{
              padding: '6px 10px', borderRadius: 4, cursor: 'pointer',
              background: selected?.id === gen.id ? '#3d1a00' : '#2a2a2a',
              border: `1px solid ${
                gen.status === 'complete' ? '#22aa44' :
                gen.status === 'failed' ? '#cc3300' : '#555'}`,
              fontSize: 11,
            }}
          >
            <div style={{ color: '#ffcc44' }}>{gen.scene_id}</div>
            <div style={{ color: getFallbackBadgeColor(gen.fallback_level_used) }}>
              {FALLBACK_LABELS[gen.fallback_level_used] || `L${gen.fallback_level_used}`}
            </div>
            <div style={{ color: '#888' }}>{gen.model_name}</div>
          </div>
        ))}
      </div>

      {/* Selected scene detail */}
      {selected && (
        <div style={{ background: '#222', padding: 16, borderRadius: 6 }}>
          <div style={{ display: 'flex', gap: 20 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#888' }}>PROMPT</div>
              <div style={{ fontSize: 12, lineHeight: 1.5,
                            marginBottom: 12 }}>{selected.prompt}</div>

              <div style={{ display: 'grid',
                            gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {[
                  ['Model', selected.model_name],
                  ['Fallback', FALLBACK_LABELS[selected.fallback_level_used]],
                  ['Quality', selected.quality_score?.toFixed(3) || 'N/A'],
                  ['Duration', selected.generation_duration_seconds
                    ? `${selected.generation_duration_seconds.toFixed(1)}s`
                    : 'N/A'],
                  ['Status', selected.status],
                  ['Error', selected.error_message || '—'],
                ].map(([label, value]) => (
                  <div key={label}>
                    <div style={{ fontSize: 9, color: '#666',
                                  textTransform: 'uppercase' }}>{label}</div>
                    <div style={{ fontSize: 11 }}>{value}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Video player */}
            {selected.output_path && (
              <video
                ref={videoRef}
                src={`${API}/media/${selected.output_path}`}
                controls
                style={{ width: 280, borderRadius: 4,
                         border: '1px solid #444' }}
              />
            )}
          </div>

          {/* Regenerate controls */}
          {onRegenerate && (
            <div style={{ marginTop: 12, display: 'flex',
                          gap: 10, alignItems: 'center' }}>
              <select
                value={modelChoice}
                onChange={e => setModelChoice(e.target.value)}
                style={{ background: '#333', color: '#eee',
                         border: '1px solid #555', padding: '4px 8px',
                         borderRadius: 4, fontSize: 11 }}
              >
                {MODEL_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <button
                onClick={() => handleRegenerate(selected)}
                disabled={loading}
                style={{
                  background: '#e07800', color: '#fff', border: 'none',
                  padding: '6px 16px', borderRadius: 4, cursor: 'pointer',
                  fontSize: 11, fontFamily: 'monospace',
                  opacity: loading ? 0.5 : 1,
                }}
              >
                {loading ? 'Queuing...' : 'Regenerate'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
