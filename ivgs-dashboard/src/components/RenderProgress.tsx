import React, { useState, useEffect, useRef } from 'react';

interface SegmentStatus {
  segment_index: number;
  status: 'pending' | 'rendering' | 'complete' | 'failed' | 'validating';
  start_ms: number;
  end_ms: number;
  render_duration_seconds?: number;
  attempts: number;
}

interface ProgressData {
  percentage: number;
  segments_done?: number;
  segments_total?: number;
  speed?: string;
  eta_seconds?: number;
  status: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending:    '#e5e7eb',
  rendering:  '#3b82f6',
  complete:   '#22c55e',
  failed:     '#ef4444',
  validating: '#f59e0b',
};

interface Props {
  jobId: string;
}

export const RenderProgress: React.FC<Props> = ({ jobId }) => {
  const [segments, setSegments] = useState<SegmentStatus[]>([]);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Fetch initial segment state
    const fetchSegments = async () => {
      const res = await fetch(`/api/v1/jobs/${jobId}/segments`);
      if (res.ok) {
        const data = await res.json();
        setSegments(data.segments || []);
      }
    };
    fetchSegments();
    const timer = setInterval(fetchSegments, 5000);

    // Connect WebSocket for real-time progress
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(
      `${wsProtocol}//${window.location.host}/ws/render-progress/${jobId}`
    );
    wsRef.current = ws;
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data) as ProgressData;
        setProgress(data);
      } catch (_) {}
    };
    return () => {
      clearInterval(timer);
      ws.close();
    };
  }, [jobId]);

  const handleRetrySegment = async (index: number) => {
    await fetch(`/api/v1/jobs/${jobId}/segments/${index}/retry`, { method: 'POST' });
  };

  const formatEta = (seconds: number) => {
    if (seconds < 0) return 'calculating...';
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    return `${m}m ${seconds % 60}s`;
  };

  const formatMs = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, '0')}`;
  };

  const overallPct = progress?.percentage ?? 0;
  const done = progress?.segments_done || segments.filter(s => s.status === 'complete').length;
  const total = progress?.segments_total || segments.length;
  const failed = segments.filter(s => s.status === 'failed').length;

  return (
    <div style={{ padding: 20, fontFamily: 'Georgia, serif' }}>
      <h3 style={{ color: '#0f3020', marginBottom: 16 }}>
        Render Progress — {jobId}
      </h3>

      {/* Overall progress bar */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between',
                      marginBottom: 6, fontSize: 13 }}>
          <span>Overall Progress</span>
          <span style={{ fontWeight: 600, color: overallPct >= 100 ? '#22c55e' : '#0f3020' }}>
            {overallPct.toFixed(1)}%
          </span>
        </div>
        <div style={{ height: 12, background: '#e5e7eb', borderRadius: 6 }}>
          <div style={{ width: `${overallPct}%`, height: '100%', borderRadius: 6,
                        background: overallPct >= 100 ? '#22c55e' : '#3b82f6',
                        transition: 'width 0.5s' }} />
        </div>
        <div style={{ display: 'flex', gap: 24, marginTop: 8, fontSize: 12, color: '#666' }}>
          <span>Segments: {done}/{total}</span>
          {failed > 0 && (
            <span style={{ color: '#ef4444' }}>{failed} failed</span>
          )}
          {progress?.speed && <span>Speed: {progress.speed}</span>}
          {progress?.eta_seconds != null && progress.eta_seconds >= 0 && (
            <span>ETA: {formatEta(progress.eta_seconds)}</span>
          )}
        </div>
      </div>

      {/* Segment grid */}
      <div>
        <h4 style={{ marginBottom: 10, fontSize: 13, color: '#0f3020' }}>
          Segments ({segments.length})
        </h4>
        <div style={{ display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                      gap: 8 }}>
          {segments.map(seg => (
            <div key={seg.segment_index} style={{
              border: `2px solid ${STATUS_COLORS[seg.status]}`,
              borderRadius: 6, padding: '8px 10px',
              background: STATUS_COLORS[seg.status] + '18',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                            marginBottom: 4 }}>
                <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600 }}>
                  SEG-{String(seg.segment_index).padStart(3, '0')}
                </span>
                <span style={{ fontSize: 10, color: STATUS_COLORS[seg.status],
                               fontWeight: 600, textTransform: 'uppercase' }}>
                  {seg.status}
                </span>
              </div>
              <div style={{ fontSize: 10, color: '#666' }}>
                {formatMs(seg.start_ms)} – {formatMs(seg.end_ms)}
              </div>
              {seg.render_duration_seconds && (
                <div style={{ fontSize: 10, color: '#888' }}>
                  {seg.render_duration_seconds.toFixed(1)}s render
                </div>
              )}
              {seg.attempts > 1 && (
                <div style={{ fontSize: 10, color: '#f59e0b' }}>
                  Attempt {seg.attempts}
                </div>
              )}
              {seg.status === 'failed' && (
                <button onClick={() => handleRetrySegment(seg.segment_index)}
                  style={{ marginTop: 6, width: '100%', padding: '3px',
                           background: '#ef4444', color: '#fff',
                           border: 'none', borderRadius: 3,
                           cursor: 'pointer', fontSize: 10 }}>
                  Retry
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default RenderProgress;
