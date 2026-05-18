import React, { useState, useEffect, useCallback } from 'react';

interface FlaggedAsset {
  id: number;
  asset_id: string;
  job_id: string;
  scene_id?: string;
  asset_type: string;
  quality_score: number;
  safety_score?: number;
  scoring_model: string;
  scoring_details?: Record<string, unknown>;
  decision: string;
  rejection_reasons?: string[];
  created_at: string;
}

const ScoreBar: React.FC<{ score: number; label: string }> = ({ score, label }) => {
  const color = score >= 0.9 ? '#22c55e' : score >= 0.7 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    fontSize: 11, marginBottom: 3 }}>
        <span>{label}</span>
        <span style={{ color, fontWeight: 600 }}>{(score * 100).toFixed(0)}%</span>
      </div>
      <div style={{ height: 6, background: '#e5e7eb', borderRadius: 3 }}>
        <div style={{ width: `${score * 100}%`, height: '100%',
                      background: color, borderRadius: 3,
                      transition: 'width 0.4s' }} />
      </div>
    </div>
  );
};

export const QualityReview: React.FC = () => {
  const [assets, setAssets]     = useState<FlaggedAsset[]>([]);
  const [selected, setSelected] = useState<FlaggedAsset | null>(null);
  const [filterType, setFilter] = useState('');
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(false);

  const fetchFlagged = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: '1', page_size: '20' });
    if (filterType) params.set('asset_type', filterType);
    try {
      const res = await fetch(`/api/v1/quality/flagged?${params}`);
      const data = await res.json();
      setAssets(data.items || []);
      setTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    fetchFlagged();
    const t = setInterval(fetchFlagged, 15000);
    return () => clearInterval(t);
  }, [fetchFlagged]);

  const handleApprove = async (id: number) => {
    await fetch(`/api/v1/quality/${id}/approve?reviewer=ops`, { method: 'POST' });
    setSelected(null);
    fetchFlagged();
  };

  const handleReject = async (id: number) => {
    const reason = window.prompt('Rejection reason (optional):') || '';
    await fetch(`/api/v1/quality/${id}/reject?reviewer=ops&reason=${encodeURIComponent(reason)}`,
      { method: 'POST' });
    setSelected(null);
    fetchFlagged();
  };

  return (
    <div style={{ display: 'flex', gap: 24, padding: 20 }}>
      {/* Asset grid */}
      <div style={{ flex: 2 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
          <h3 style={{ margin: 0, color: '#0f3020' }}>Quality Review Queue</h3>
          <span style={{ background: '#fef3c7', color: '#92400e', padding: '3px 10px',
                         borderRadius: 12, fontSize: 12 }}>{total} pending</span>
          <select value={filterType} onChange={e => setFilter(e.target.value)}
            style={{ padding: '5px 10px', borderRadius: 4, border: '1px solid #ddd',
                     marginLeft: 'auto' }}>
            <option value="">All Types</option>
            {['image','video','audio','caption'].map(t =>
              <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
                      gap: 12 }}>
          {assets.map(asset => {
            const score = asset.quality_score;
            const color = score >= 0.9 ? '#22c55e' : score >= 0.7 ? '#f59e0b' : '#ef4444';
            return (
              <div key={asset.id}
                onClick={() => setSelected(asset)}
                style={{ border: selected?.id === asset.id
                  ? '2px solid #22c55e' : '1px solid #c0d8c0',
                  borderRadius: 8, padding: 14, cursor: 'pointer',
                  background: '#fff', transition: 'all 0.15s' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between',
                              marginBottom: 10 }}>
                  <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#666' }}>
                    {asset.asset_type}
                  </span>
                  <span style={{ fontSize: 18, fontWeight: 700, color }}>
                    {(score * 100).toFixed(0)}%
                  </span>
                </div>
                <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>
                  Job: {asset.job_id.slice(0, 12)}...
                </div>
                {asset.scene_id && (
                  <div style={{ fontSize: 11, color: '#888', marginBottom: 8 }}>
                    Scene: {asset.scene_id}
                  </div>
                )}
                <div style={{ height: 4, background: '#e5e7eb', borderRadius: 2 }}>
                  <div style={{ width: `${score * 100}%`, height: '100%',
                                background: color, borderRadius: 2 }} />
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button onClick={e => { e.stopPropagation(); handleApprove(asset.id); }}
                    style={{ flex: 1, padding: '4px', background: '#22c55e', color: '#fff',
                             border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 11 }}>
                    ✓ Approve
                  </button>
                  <button onClick={e => { e.stopPropagation(); handleReject(asset.id); }}
                    style={{ flex: 1, padding: '4px', background: '#ef4444', color: '#fff',
                             border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 11 }}>
                    ✗ Reject
                  </button>
                </div>
              </div>
            );
          })}
          {assets.length === 0 && !loading && (
            <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: 40, color: '#999' }}>
              No assets pending review
            </div>
          )}
        </div>
      </div>

      {/* Scoring detail panel */}
      {selected && (
        <div style={{ flex: 1, background: '#f8fdf8', border: '1px solid #c0d8c0',
                      borderRadius: 8, padding: 20, minWidth: 260 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
            <h4 style={{ margin: 0 }}>Score Details</h4>
            <button onClick={() => setSelected(null)}>×</button>
          </div>
          <ScoreBar score={selected.quality_score} label="Overall Quality" />
          {selected.safety_score != null &&
            <ScoreBar score={selected.safety_score} label="Safety" />
          }
          {selected.scoring_details && Object.entries(selected.scoring_details).map(([k, v]) =>
            typeof v === 'number' && v <= 1 ? (
              <ScoreBar key={k} score={v as number} label={k.replace(/_/g, ' ')} />
            ) : null
          )}
          {(selected.rejection_reasons || []).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <strong style={{ fontSize: 12 }}>Issues:</strong>
              <ul style={{ margin: '6px 0', paddingLeft: 20 }}>
                {(selected.rejection_reasons || []).map((r, i) =>
                  <li key={i} style={{ fontSize: 11, color: '#dc2626' }}>{r}</li>
                )}
              </ul>
            </div>
          )}
          <div style={{ fontSize: 11, color: '#888', marginTop: 12 }}>
            Model: {selected.scoring_model}
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
            <button onClick={() => handleApprove(selected.id)}
              style={{ flex: 1, padding: 10, background: '#22c55e', color: '#fff',
                       border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}>
              Approve
            </button>
            <button onClick={() => handleReject(selected.id)}
              style={{ flex: 1, padding: 10, background: '#ef4444', color: '#fff',
                       border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}>
              Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default QualityReview;
