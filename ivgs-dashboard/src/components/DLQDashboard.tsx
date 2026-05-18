import React, { useState, useEffect, useCallback } from 'react';

interface DLQMessage {
  id: number;
  original_queue: string;
  task_name: string;
  exception_type: string;
  exception_message: string;
  traceback?: string;
  failure_category: string;
  retry_count_exhausted: number;
  job_id?: string;
  resolution: string;
  created_at: string;
}

interface Analytics {
  by_category: Record<string, number>;
  by_task: Record<string, number>;
  total_pending: number;
}

const API_BASE = '/api/v1/dlq';
const CATEGORY_COLORS: Record<string, string> = {
  transient:      '#3b82f6',
  config:         '#ef4444',
  external:       '#f59e0b',
  resource:       '#8b5cf6',
  data_corruption:'#ec4899',
  timeout:        '#06b6d4',
  unknown:        '#6b7280',
};

export const DLQDashboard: React.FC = () => {
  const [messages, setMessages]       = useState<DLQMessage[]>([]);
  const [analytics, setAnalytics]     = useState<Analytics | null>(null);
  const [selected, setSelected]       = useState<DLQMessage | null>(null);
  const [filterCategory, setFilterCat] = useState('');
  const [filterTask, setFilterTask]   = useState('');
  const [page, setPage]               = useState(1);
  const [total, setTotal]             = useState(0);
  const [loading, setLoading]         = useState(false);

  const fetchMessages = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      page_size: '50',
      resolution: 'pending',
    });
    if (filterCategory) params.set('category', filterCategory);
    if (filterTask) params.set('task_name', filterTask);
    try {
      const res = await fetch(`${API_BASE}/messages?${params}`);
      const data = await res.json();
      setMessages(data.messages);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [page, filterCategory, filterTask]);

  const fetchAnalytics = async () => {
    const res = await fetch(`${API_BASE}/analytics?hours=24`);
    setAnalytics(await res.json());
  };

  useEffect(() => {
    fetchMessages();
    fetchAnalytics();
    const timer = setInterval(() => { fetchMessages(); fetchAnalytics(); }, 30000);
    return () => clearInterval(timer);
  }, [fetchMessages]);

  const handleReplay = async (id: number) => {
    if (!window.confirm('Replay this message?')) return;
    const res = await fetch(`${API_BASE}/messages/${id}/replay`, { method: 'POST' });
    if (res.ok) { fetchMessages(); fetchAnalytics(); }
  };

  const handleDiscard = async (id: number) => {
    if (!window.confirm('Permanently discard this message?')) return;
    const res = await fetch(`${API_BASE}/messages/${id}/discard?reviewer=ops`, { method: 'POST' });
    if (res.ok) { setSelected(null); fetchMessages(); fetchAnalytics(); }
  };

  return (
    <div style={{ display: 'flex', gap: 24, padding: 24 }}>
      {/* Left panel: analytics + table */}
      <div style={{ flex: 2 }}>
        {/* Analytics bar */}
        {analytics && (
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div style={{ background: '#fee2e2', padding: '10px 16px', borderRadius: 8, minWidth: 120 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#dc2626' }}>
                {analytics.total_pending}
              </div>
              <div style={{ fontSize: 11, color: '#666' }}>Pending Messages</div>
            </div>
            {Object.entries(analytics.by_category).map(([cat, cnt]) => (
              <div key={cat} style={{
                background: CATEGORY_COLORS[cat] + '18',
                borderLeft: `3px solid ${CATEGORY_COLORS[cat]}`,
                padding: '8px 14px', borderRadius: 4, minWidth: 90
              }}>
                <div style={{ fontSize: 22, fontWeight: 600, color: CATEGORY_COLORS[cat] }}>{cnt}</div>
                <div style={{ fontSize: 10, color: '#666' }}>{cat}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          <select value={filterCategory} onChange={e => setFilterCat(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ddd' }}>
            <option value="">All Categories</option>
            {Object.keys(CATEGORY_COLORS).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <input placeholder="Filter by task name..." value={filterTask}
            onChange={e => setFilterTask(e.target.value)}
            style={{ flex: 1, padding: '6px 10px', borderRadius: 4, border: '1px solid #ddd' }} />
        </div>

        {/* Message table */}
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#1e3a1e', color: '#fff' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left' }}>ID</th>
              <th style={{ padding: '8px 12px', textAlign: 'left' }}>Task</th>
              <th style={{ padding: '8px 12px', textAlign: 'left' }}>Category</th>
              <th style={{ padding: '8px 12px', textAlign: 'left' }}>Queue</th>
              <th style={{ padding: '8px 12px', textAlign: 'left' }}>Created</th>
              <th style={{ padding: '8px 12px', textAlign: 'left' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {messages.map((msg, i) => (
              <tr key={msg.id}
                style={{ background: i % 2 === 0 ? '#fff' : '#f8fdf8',
                         cursor: 'pointer' }}
                onClick={() => setSelected(msg)}>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>#{msg.id}</td>
                <td style={{ padding: '7px 12px', maxWidth: 180, overflow: 'hidden',
                             textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {msg.task_name.split('.').pop()}
                </td>
                <td style={{ padding: '7px 12px' }}>
                  <span style={{ background: CATEGORY_COLORS[msg.failure_category] + '25',
                    color: CATEGORY_COLORS[msg.failure_category],
                    padding: '2px 8px', borderRadius: 12, fontSize: 11 }}>
                    {msg.failure_category}
                  </span>
                </td>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace', fontSize: 11 }}>
                  {msg.original_queue}
                </td>
                <td style={{ padding: '7px 12px', fontSize: 11, color: '#666' }}>
                  {new Date(msg.created_at).toLocaleString()}
                </td>
                <td style={{ padding: '7px 12px' }}>
                  <button onClick={e => { e.stopPropagation(); handleReplay(msg.id); }}
                    style={{ marginRight: 8, padding: '3px 10px', background: '#22c55e',
                             color: '#fff', border: 'none', borderRadius: 4,
                             cursor: 'pointer', fontSize: 12 }}>
                    Replay
                  </button>
                  <button onClick={e => { e.stopPropagation(); handleDiscard(msg.id); }}
                    style={{ padding: '3px 10px', background: '#ef4444',
                             color: '#fff', border: 'none', borderRadius: 4,
                             cursor: 'pointer', fontSize: 12 }}>
                    Discard
                  </button>
                </td>
              </tr>
            ))}
            {messages.length === 0 && (
              <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#999' }}>
                {loading ? 'Loading...' : 'No pending DLQ messages'}
              </td></tr>
            )}
          </tbody>
        </table>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
          <span style={{ fontSize: 12, color: '#666' }}>{total} total pending</span>
          <div>
            <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
              style={{ marginRight: 8 }}>Prev</button>
            <span style={{ fontSize: 12 }}>Page {page}</span>
            <button disabled={page * 50 >= total} onClick={() => setPage(p => p + 1)}
              style={{ marginLeft: 8 }}>Next</button>
          </div>
        </div>
      </div>

      {/* Right panel: message detail */}
      {selected && (
        <div style={{ flex: 1, background: '#f8fdf8', border: '1px solid #c0d8c0',
                      borderRadius: 8, padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: 15 }}>Message #{selected.id}</h3>
            <button onClick={() => setSelected(null)}>×</button>
          </div>
          <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
            <strong>Task:</strong> {selected.task_name}</div>
          <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
            <strong>Error:</strong> {selected.exception_type}: {selected.exception_message}</div>
          {selected.job_id && (
            <div style={{ fontSize: 12, marginBottom: 8 }}>
              <strong>Job:</strong> {selected.job_id}</div>
          )}
          {selected.traceback && (
            <pre style={{ background: '#0e1f16', color: '#cdeedd', padding: 12,
                          fontSize: 10, borderRadius: 4, overflow: 'auto',
                          maxHeight: 300 }}>{selected.traceback}</pre>
          )}
          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <button onClick={() => handleReplay(selected.id)}
              style={{ flex: 1, padding: '8px', background: '#22c55e',
                       color: '#fff', border: 'none', borderRadius: 6,
                       cursor: 'pointer', fontWeight: 600 }}>
              Replay Task
            </button>
            <button onClick={() => handleDiscard(selected.id)}
              style={{ flex: 1, padding: '8px', background: '#ef4444',
                       color: '#fff', border: 'none', borderRadius: 6,
                       cursor: 'pointer', fontWeight: 600 }}>
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DLQDashboard;
