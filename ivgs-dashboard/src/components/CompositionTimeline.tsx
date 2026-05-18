import React, { useState, useEffect, useRef, useCallback } from 'react';

interface TimelineLayer {
  type: 'video' | 'audio' | 'caption' | 'image';
  path: string;
  start_ms: number;
  duration_ms: number;
  z_index: number;
}

interface TimelineScene {
  scene_id: string;
  scene_index: number;
  start_ms: number;
  duration_ms: number;
  transition: string;
  layers: TimelineLayer[];
}

interface Manifest {
  job_id: string;
  manifest_version: number;
  total_duration_ms: number;
  status: 'draft' | 'locked' | 'rendered' | 'invalid';
  checksum?: string;
  scene_count: number;
}

const LAYER_COLORS: Record<string, string> = {
  video:   '#3b82f6',
  image:   '#6366f1',
  audio:   '#22c55e',
  caption: '#f59e0b',
};

const STATUS_COLORS: Record<string, string> = {
  draft:    '#f59e0b',
  locked:   '#22c55e',
  rendered: '#3b82f6',
  invalid:  '#ef4444',
};

interface Props {
  jobId: string;
}

export const CompositionTimeline: React.FC<Props> = ({ jobId }) => {
  const [manifest, setManifest]         = useState<Manifest | null>(null);
  const [scenes, setScenes]             = useState<TimelineScene[]>([]);
  const [selectedScene, setSelectedSc] = useState<TimelineScene | null>(null);
  const [zoomLevel, setZoom]            = useState(1);
  const [scrollX, setScrollX]           = useState(0);
  const [loading, setLoading]           = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const TRACK_HEIGHT = 30;
  const HEADER_HEIGHT = 48;

  const fetchManifest = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/jobs/${jobId}/manifest`);
      if (!res.ok) return;
      const data = await res.json();
      setManifest(data);
      // Fetch full timeline data
      const detailRes = await fetch(`/api/v1/jobs/${jobId}/manifest`);
      const detail = await detailRes.json();
      setScenes(detail.timeline?.scenes || []);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    fetchManifest();
    const t = setInterval(fetchManifest, 10000);
    return () => clearInterval(t);
  }, [fetchManifest]);

  const handleGenerate = async () => {
    await fetch(`/api/v1/jobs/${jobId}/manifest/generate`, { method: 'POST' });
    fetchManifest();
  };

  const handleLock = async () => {
    const res = await fetch(`/api/v1/jobs/${jobId}/manifest/lock`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      alert(`Lock failed: ${err.detail}`);
    }
    fetchManifest();
  };

  const totalMs = manifest?.total_duration_ms || 1;
  const pxPerMs = (800 * zoomLevel) / totalMs;

  const msToX = (ms: number) => Math.round(ms * pxPerMs);
  const msToPct = (ms: number) => (ms / totalMs * 100).toFixed(2) + '%';

  const formatTime = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, '0')}`;
  };

  return (
    <div style={{ fontFamily: 'Georgia, serif', padding: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: '#0f3020' }}>Composition Timeline — {jobId}</h3>
        {manifest && (
          <span style={{ padding: '3px 12px', borderRadius: 12, fontSize: 12,
            background: STATUS_COLORS[manifest.status] + '22',
            color: STATUS_COLORS[manifest.status], fontWeight: 600 }}>
            {manifest.status.toUpperCase()}
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
          <button onClick={handleGenerate}
            style={{ padding: '6px 14px', background: '#0f3020', color: '#fff',
                     border: 'none', borderRadius: 6, cursor: 'pointer' }}>
            Generate
          </button>
          <button onClick={handleLock}
            disabled={manifest?.status !== 'draft'}
            style={{ padding: '6px 14px',
                     background: manifest?.status === 'draft' ? '#22c55e' : '#ccc',
                     color: '#fff', border: 'none', borderRadius: 6,
                     cursor: manifest?.status === 'draft' ? 'pointer' : 'not-allowed' }}>
            Lock Manifest
          </button>
          <label style={{ fontSize: 12 }}>
            Zoom:
            <input type="range" min="0.5" max="8" step="0.5" value={zoomLevel}
              onChange={e => setZoom(Number(e.target.value))}
              style={{ marginLeft: 8, width: 80 }} />
          </label>
        </div>
      </div>

      {/* Manifest info bar */}
      {manifest && (
        <div style={{ display: 'flex', gap: 24, padding: '8px 16px',
                      background: '#f0f8f4', borderRadius: 6, marginBottom: 16,
                      fontSize: 12, color: '#444' }}>
          <span><strong>Duration:</strong> {formatTime(manifest.total_duration_ms)}</span>
          <span><strong>Scenes:</strong> {manifest.scene_count}</span>
          <span><strong>Version:</strong> {manifest.manifest_version}</span>
          {manifest.checksum && (
            <span><strong>Checksum:</strong>
              <code style={{ fontSize: 11 }}>{manifest.checksum.slice(0, 16)}...</code>
            </span>
          )}
        </div>
      )}

      {loading && !manifest && (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          Loading manifest...
        </div>
      )}

      {/* Timeline canvas */}
      {scenes.length > 0 && (
        <div style={{ overflowX: 'auto', border: '1px solid #c0d8c0',
                      borderRadius: 6, background: '#fafff8' }}>
          <div style={{ minWidth: 800 * zoomLevel + 60, position: 'relative',
                        paddingLeft: 60 }}>
            {/* Time ruler */}
            <div style={{ height: HEADER_HEIGHT, position: 'relative',
                          borderBottom: '1px solid #c0d8c0' }}>
              {Array.from({ length: 10 }).map((_, i) => {
                const ms = (i / 10) * totalMs;
                return (
                  <span key={i} style={{
                    position: 'absolute', left: msToX(ms),
                    fontSize: 10, color: '#888', top: 6,
                    borderLeft: '1px solid #ddd', paddingLeft: 4,
                    height: HEADER_HEIGHT - 6
                  }}>
                    {formatTime(ms)}
                  </span>
                );
              })}
            </div>

            {/* Layer rows */}
            {(['video', 'audio', 'caption'] as const).map((layerType, row) => (
              <div key={layerType} style={{ position: 'relative', height: TRACK_HEIGHT + 8,
                                            borderBottom: '1px solid #e8f4e8' }}>
                {/* Row label */}
                <span style={{ position: 'absolute', left: -55, top: 8,
                               fontSize: 10, color: '#666', fontFamily: 'monospace' }}>
                  {layerType}
                </span>
                {scenes.map(scene => {
                  const layer = scene.layers.find(l => l.type === layerType);
                  if (!layer) return null;
                  return (
                    <div key={scene.scene_id}
                      onClick={() => setSelectedSc(scene)}
                      style={{
                        position: 'absolute',
                        left: msToX(scene.start_ms) + 'px',
                        width: Math.max(msToX(scene.duration_ms) - 2, 4) + 'px',
                        top: 4, height: TRACK_HEIGHT,
                        background: LAYER_COLORS[layerType],
                        borderRadius: 3, cursor: 'pointer',
                        opacity: selectedScene?.scene_id === scene.scene_id ? 1 : 0.75,
                        transition: 'opacity 0.15s',
                        overflow: 'hidden',
                        display: 'flex', alignItems: 'center',
                        paddingLeft: 4,
                      }}>
                      <span style={{ color: '#fff', fontSize: 9,
                                     fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                        {scene.scene_id}
                      </span>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Scene detail panel */}
      {selectedScene && (
        <div style={{ marginTop: 20, padding: 16, background: '#f0f8f4',
                      border: '1px solid #c0d8c0', borderRadius: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between',
                        marginBottom: 12 }}>
            <h4 style={{ margin: 0 }}>Scene: {selectedScene.scene_id}</h4>
            <button onClick={() => setSelectedSc(null)}>×</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div><strong>Start:</strong> {formatTime(selectedScene.start_ms)}</div>
            <div><strong>Duration:</strong> {(selectedScene.duration_ms/1000).toFixed(2)}s</div>
            <div><strong>Transition:</strong> {selectedScene.transition}</div>
            <div><strong>Layers:</strong> {selectedScene.layers.length}</div>
          </div>
          <table style={{ width: '100%', marginTop: 12, fontSize: 12,
                          borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#0f3020', color: '#fff' }}>
                <th style={{ padding: '6px 10px', textAlign: 'left' }}>Type</th>
                <th style={{ padding: '6px 10px', textAlign: 'left' }}>Duration</th>
                <th style={{ padding: '6px 10px', textAlign: 'left' }}>Path</th>
              </tr>
            </thead>
            <tbody>
              {selectedScene.layers.map((l, i) => (
                <tr key={i} style={{ background: i%2===0?'#fff':'#f0f8f4' }}>
                  <td style={{ padding: '5px 10px' }}>
                    <span style={{ background: LAYER_COLORS[l.type]+'22',
                      color: LAYER_COLORS[l.type], padding: '2px 8px',
                      borderRadius: 10, fontSize: 11 }}>{l.type}</span>
                  </td>
                  <td style={{ padding: '5px 10px' }}>{(l.duration_ms/1000).toFixed(2)}s</td>
                  <td style={{ padding: '5px 10px', fontFamily: 'monospace',
                               fontSize: 10, color: '#555', wordBreak: 'break-all' }}>
                    {l.path.split('/').pop()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CompositionTimeline;
