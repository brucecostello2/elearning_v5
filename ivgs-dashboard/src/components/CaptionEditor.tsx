import React, { useState, useEffect, useRef, useCallback } from 'react';

interface WordTimestamp {
  word: string;
  start_ms: number;
  end_ms: number;
  score: number;
  expected_ms?: number;
}

interface CaptionAlignmentRecord {
  id: number;
  scene_id: string;
  language_code: string;
  original_text: string;
  spoken_text: string | null;
  text_match_ratio: number | null;
  word_timestamps: WordTimestamp[] | null;
  drift_ms_max: number | null;
  status: string;
  output_srt_path: string | null;
  output_vtt_path: string | null;
}

interface CaptionEditorProps {
  jobId: string;
  sceneId: string;
  languageCode?: string;
  audioSrc?: string;
  onSave?: (words: WordTimestamp[]) => void;
}

const DRIFT_WARN_MS = 100;
const DRIFT_ERROR_MS = 300;

export const CaptionEditor: React.FC<CaptionEditorProps> = ({
  jobId, sceneId, languageCode = 'en', audioSrc, onSave,
}) => {
  const [alignment, setAlignment] =
    useState<CaptionAlignmentRecord | null>(null);
  const [words, setWords] = useState<WordTimestamp[]>([]);
  const [selectedWord, setSelectedWord] = useState<number | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [saving, setSaving] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  const API = process.env.REACT_APP_API_URL || '';

  useEffect(() => {
    fetch(`${API}/api/v1/jobs/${jobId}/captions/${sceneId}?lang=${languageCode}`)
      .then(r => r.ok ? r.json() : null)
      .then((data: CaptionAlignmentRecord | null) => {
        if (data) {
          setAlignment(data);
          setWords(data.word_timestamps || []);
        }
      })
      .catch(() => {});
  }, [jobId, sceneId, languageCode]);

  const getDriftColor = (word: WordTimestamp): string => {
    if (!word.expected_ms) return '#ccc';
    const drift = Math.abs(word.start_ms - word.expected_ms);
    if (drift > DRIFT_ERROR_MS) return '#cc3300';
    if (drift > DRIFT_WARN_MS)  return '#e07800';
    return '#22aa44';
  };

  const handleWordClick = (index: number) => {
    setSelectedWord(index === selectedWord ? null : index);
    const word = words[index];
    if (audioRef.current) {
      audioRef.current.currentTime = word.start_ms / 1000;
    }
  };

  const handleAdjustStart = (index: number, delta: number) => {
    setWords(prev => prev.map((w, i) =>
      i === index ? { ...w, start_ms: Math.max(0, w.start_ms + delta) } : w
    ));
  };

  const handleAdjustEnd = (index: number, delta: number) => {
    setWords(prev => prev.map((w, i) =>
      i === index ? { ...w, end_ms: Math.max(w.start_ms + 50, w.end_ms + delta) } : w
    ));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch(
        `${API}/api/v1/jobs/${jobId}/captions/${sceneId}/timestamps`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ word_timestamps: words, language: languageCode }),
        });
      onSave?.(words);
    } catch (e) {
      alert('Save failed');
    } finally {
      setSaving(false);
    }
  };

  const timelineWidth = timelineRef.current?.clientWidth || 800;
  const pxPerMs = audioDuration > 0 ? timelineWidth / audioDuration : 0;

  return (
    <div style={{
      background: '#1a1a1a', color: '#eee', borderRadius: 8,
      padding: 20, fontFamily: 'monospace',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0, color: '#ffcc44' }}>
          Caption Editor — {sceneId} [{languageCode}]
        </h3>
        {alignment && (
          <div style={{ fontSize: 10, color: '#888', textAlign: 'right' }}>
            <div>Match: {
              alignment.text_match_ratio != null
                ? `${(alignment.text_match_ratio * 100).toFixed(1)}%`
                : 'N/A'
            }</div>
            <div style={{
              color: (alignment.drift_ms_max ?? 0) > DRIFT_ERROR_MS
                ? '#cc3300' : (alignment.drift_ms_max ?? 0) > DRIFT_WARN_MS
                ? '#e07800' : '#22aa44',
            }}>
              Max drift: {alignment.drift_ms_max?.toFixed(0) ?? 'N/A'}ms
            </div>
            <div style={{
              color: alignment.status === 'aligned' ? '#22aa44' :
                     alignment.status === 'drifted' ? '#e07800' : '#cc3300',
              textTransform: 'uppercase', fontSize: 9,
            }}>
              {alignment.status}
            </div>
          </div>
        )}
      </div>

      {/* Audio player */}
      {audioSrc && (
        <audio
          ref={audioRef}
          src={audioSrc}
          controls
          onTimeUpdate={e => setPlayhead(
            (e.target as HTMLAudioElement).currentTime * 1000)}
          onLoadedMetadata={e => setAudioDuration(
            (e.target as HTMLAudioElement).duration * 1000)}
          style={{ width: '100%', marginBottom: 12 }}
        />
      )}

      {/* Timeline */}
      <div
        ref={timelineRef}
        style={{
          position: 'relative', height: 40, background: '#222',
          borderRadius: 4, marginBottom: 12, overflow: 'hidden',
          border: '1px solid #333',
        }}
      >
        {words.map((word, i) => (
          <div
            key={i}
            onClick={() => handleWordClick(i)}
            title={`${word.word}: ${word.start_ms}ms–${word.end_ms}ms`}
            style={{
              position: 'absolute',
              left: word.start_ms * pxPerMs,
              width: Math.max(2, (word.end_ms - word.start_ms) * pxPerMs),
              top: 4, height: 32,
              background: selectedWord === i ? '#e07800' : getDriftColor(word),
              opacity: 0.75,
              borderRadius: 2,
              overflow: 'hidden',
              cursor: 'pointer',
              fontSize: 8,
              padding: '1px 2px',
              color: '#000',
              boxSizing: 'border-box',
            }}
          >
            {word.word}
          </div>
        ))}
        {/* Playhead */}
        {audioDuration > 0 && (
          <div style={{
            position: 'absolute',
            left: playhead * pxPerMs,
            top: 0, width: 2, height: '100%',
            background: '#fff', opacity: 0.9, pointerEvents: 'none',
          }} />
        )}
      </div>

      {/* Selected word edit controls */}
      {selectedWord !== null && words[selectedWord] && (
        <div style={{ background: '#222', padding: 12, borderRadius: 6,
                      marginBottom: 12 }}>
          <div style={{ marginBottom: 8, fontWeight: 700, color: '#ffcc44' }}>
            "{words[selectedWord].word}"
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 11 }}>
            <div>
              <div style={{ color: '#888' }}>Start: {words[selectedWord].start_ms}ms</div>
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                {[-100,-50,-10,+10,+50,+100].map(delta => (
                  <button
                    key={delta}
                    onClick={() => handleAdjustStart(selectedWord, delta)}
                    style={{
                      background: delta < 0 ? '#3a1500' : '#003a15',
                      color: '#eee', border: 'none', padding: '2px 6px',
                      borderRadius: 3, cursor: 'pointer', fontSize: 10,
                    }}
                  >
                    {delta > 0 ? '+' : ''}{delta}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ color: '#888' }}>End: {words[selectedWord].end_ms}ms</div>
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                {[-100,-50,-10,+10,+50,+100].map(delta => (
                  <button
                    key={delta}
                    onClick={() => handleAdjustEnd(selectedWord, delta)}
                    style={{
                      background: delta < 0 ? '#3a1500' : '#003a15',
                      color: '#eee', border: 'none', padding: '2px 6px',
                      borderRadius: 3, cursor: 'pointer', fontSize: 10,
                    }}
                  >
                    {delta > 0 ? '+' : ''}{delta}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Save button */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            background: '#e07800', color: '#fff', border: 'none',
            padding: '8px 20px', borderRadius: 4, cursor: 'pointer',
            fontSize: 12, fontFamily: 'monospace', opacity: saving ? 0.5 : 1,
          }}
        >
          {saving ? 'Saving...' : 'Save Alignment'}
        </button>
        {alignment?.output_srt_path && (
          <a href={`${API}/api/v1/jobs/${jobId}/captions/${sceneId}/download?format=srt`}
             style={{ fontSize: 11, color: '#e07800' }}>
            Download SRT
          </a>
        )}
        {alignment?.output_vtt_path && (
          <a href={`${API}/api/v1/jobs/${jobId}/captions/${sceneId}/download?format=vtt`}
             style={{ fontSize: 11, color: '#e07800', marginLeft: 8 }}>
            Download VTT
          </a>
        )}
      </div>
    </div>
  );
};
