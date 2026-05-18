import React, { useState, useEffect, useCallback } from 'react';

interface LanguageStatus {
  code: string;
  name: string;
  status: string;
  config_id?: number;
}

interface SupportedLanguage {
  code: string;
  name: string;
  tts_voice: string;
}

interface LocalizationManagerProps {
  jobId: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#888',
  translating: '#e07800',
  tts_generating: '#e07800',
  captions_generating: '#e07800',
  composing: '#cc8800',
  complete: '#22aa44',
  failed: '#cc3300',
  already_complete: '#22aa44',
  queued: '#4488cc',
};

const STATUS_STEPS = [
  'pending', 'translating', 'tts_generating',
  'captions_generating', 'composing', 'complete',
];

export const LocalizationManager: React.FC<LocalizationManagerProps> = ({
  jobId,
}) => {
  const [supported, setSupported] = useState<SupportedLanguage[]>([]);
  const [active, setActive] = useState<LanguageStatus[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [launching, setLaunching] = useState(false);

  const API = process.env.REACT_APP_API_URL || '';

  const refresh = useCallback(async () => {
    try {
      const [supResp, activeResp] = await Promise.all([
        fetch(`${API}/api/v1/localization/languages`),
        fetch(`${API}/api/v1/jobs/${jobId}/localizations`),
      ]);
      if (supResp.ok) {
        const d = await supResp.json();
        setSupported(d.languages || []);
      }
      if (activeResp.ok) {
        const d = await activeResp.json();
        setActive(Array.isArray(d) ? d.flatMap(
          (r: any) => r.languages || []) : []);
      }
    } catch (e) { /* swallow */ }
  }, [jobId, API]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, [refresh]);

  const toggleLanguage = (code: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
  };

  const startLocalization = async () => {
    if (selected.size === 0) return;
    setLaunching(true);
    try {
      await fetch(`${API}/api/v1/jobs/${jobId}/localize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_language: 'en',
          target_languages: Array.from(selected),
          voice_map: {},
        }),
      });
      setSelected(new Set());
      await refresh();
    } catch (e) {
      alert('Failed to start localization');
    } finally {
      setLaunching(false);
    }
  };

  const getActiveStatus = (code: string): string | undefined =>
    active.find(l => l.code === code)?.status;

  const getStepIndex = (status: string) =>
    STATUS_STEPS.indexOf(status);

  return (
    <div style={{
      background: '#1a1a1a', color: '#eee',
      borderRadius: 8, padding: 20, fontFamily: 'monospace',
    }}>
      <h3 style={{ color: '#ffcc44', marginTop: 0 }}>
        Localization Manager
      </h3>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10,
                    marginBottom: 16 }}>
        {supported.map(lang => {
          const status = getActiveStatus(lang.code);
          const isActive = !!status;
          const isSelected = selected.has(lang.code);
          return (
            <div
              key={lang.code}
              onClick={() => !isActive && toggleLanguage(lang.code)}
              style={{
                padding: '8px 14px', borderRadius: 6,
                cursor: isActive ? 'default' : 'pointer',
                border: `2px solid ${
                  isActive ? (STATUS_COLORS[status!] || '#555') :
                  isSelected ? '#e07800' : '#444'}`,
                background: isSelected && !isActive ? '#2e1200' : '#222',
                minWidth: 100, textAlign: 'center',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 12 }}>{lang.name}</div>
              <div style={{ fontSize: 10, color: '#888' }}>{lang.code}</div>
              {isActive && (
                <>
                  <div style={{
                    fontSize: 9, color: STATUS_COLORS[status!] || '#888',
                    marginTop: 4, textTransform: 'uppercase',
                  }}>
                    {status!.replace(/_/g, ' ')}
                  </div>
                  {/* Progress pip bar */}
                  <div style={{ display: 'flex', gap: 2, marginTop: 4 }}>
                    {STATUS_STEPS.map((s, i) => (
                      <div
                        key={s}
                        style={{
                          flex: 1, height: 3, borderRadius: 2,
                          background: i <= getStepIndex(status!)
                            ? STATUS_COLORS[status!] || '#888'
                            : '#333',
                        }}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {selected.size > 0 && (
        <div style={{ marginBottom: 12, fontSize: 12, color: '#aaa' }}>
          {selected.size} language{selected.size > 1 ? 's' : ''} selected:{' '}
          {Array.from(selected).join(', ')}
        </div>
      )}

      <button
        onClick={startLocalization}
        disabled={selected.size === 0 || launching}
        style={{
          background: selected.size === 0 ? '#333' : '#e07800',
          color: '#fff', border: 'none', padding: '8px 20px',
          borderRadius: 4, cursor: selected.size === 0 ? 'not-allowed' : 'pointer',
          fontSize: 12, fontFamily: 'monospace',
          opacity: launching ? 0.6 : 1,
        }}
      >
        {launching ? 'Starting...' :
         `Start Localization (${selected.size} language${selected.size !== 1 ? 's' : ''})`}
      </button>
    </div>
  );
};
