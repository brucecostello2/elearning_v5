"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
import { useAssets } from "@/hooks/useAssets";
import { useAuth } from "@/hooks/useAuth";
import LoadingSpinner from "@/components/LoadingSpinner";
import Toast from "@/components/Toast";
import type { Asset } from "@/types/api";
import {
  assetLabel,
  assetMediaKind,
  formatBytes,
  formatDuration,
} from "@/lib/media";
import {
  useAssetDownload,
  useAssetObjectUrl,
  useInView,
  useSceneIndexMap,
} from "@/hooks/useAssetMedia";

/**
 * §8.1.3 Table 8-2 — Audio Tab
 *
 * Features:
 *   - Per-scene audio player with waveform visualization
 *   - Quality score (SNR) display
 *   - Regenerate button per scene
 *   - Play/pause, seek, volume controls
 *
 * Uses Web Audio API for waveform rendering.
 *
 * WP-40 addendum. This tab was blank for the same reason the Media Assets
 * grid was: `<audio src={asset.url}>` and `fetch(asset.url)` against a field
 * the API does not send, so the element got no `src` and the waveform fetch
 * never fired. `asset.scene_label`, `asset.filename` and `asset.quality_score`
 * are phantom too -- so the header read empty and the "SNR" badge was never
 * shown, because `quality_score` was always `undefined`.
 *
 * Audio now loads through the authenticated download proxy, and the header
 * carries facts the API actually sends.
 */

interface AudioSceneProps {
  asset: Asset;
  sceneIndex: number | null;
  canEdit: boolean;
  onRegenerate: (assetId: string) => Promise<void>;
}

function AudioScenePlayer({
  asset,
  sceneIndex,
  canEdit,
  onRegenerate,
}: AudioSceneProps): React.ReactElement {
  const cardRef = useRef<HTMLDivElement>(null);
  /* The bytes come from GET /api/v1/assets/{id}/download, which needs a
     Bearer header -- so they are fetched and handed over as an object URL.
     Gated on visibility: a project has one track per scene (18 here) and the
     waveform needs the whole buffer, so fetching them all on mount would
     pull every one before the operator has scrolled to any. */
  const inView = useInView(cardRef);
  const { url: audioUrl, isLoading: mediaLoading, error: mediaError } =
    useAssetObjectUrl(asset.id, inView);
  const { download, downloadingId } = useAssetDownload();
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(0);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);

  /**
   * Draw waveform from audio buffer onto canvas.
   */
  const drawWaveform = useCallback(
    (audioBuffer: AudioBuffer): void => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const data = audioBuffer.getChannelData(0);
      const step = Math.ceil(data.length / canvas.width);
      const amp = canvas.height / 2;

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.beginPath();
      ctx.strokeStyle = "#3b82f6";
      ctx.lineWidth = 1;

      for (let i = 0; i < canvas.width; i++) {
        let min = 1.0;
        let max = -1.0;
        for (let j = 0; j < step; j++) {
          const datum = data[i * step + j];
          if (datum !== undefined) {
            if (datum < min) min = datum;
            if (datum > max) max = datum;
          }
        }
        ctx.moveTo(i, (1 + min) * amp);
        ctx.lineTo(i, (1 + max) * amp);
      }

      ctx.stroke();
    },
    []
  );

  /**
   * Load audio and generate waveform on mount.
   */
  useEffect(() => {
    if (!audioUrl) return;

    const audioContext = new AudioContext();
    /* Fetching a blob: URL is same-origin and needs no header. */
    fetch(audioUrl)
      .then((res) => res.arrayBuffer())
      .then((buf) => audioContext.decodeAudioData(buf))
      .then((decoded) => drawWaveform(decoded))
      .catch(() => {
        // Waveform rendering failed — audio still plays
      });

    return () => {
      audioContext.close().catch(() => {});
    };
  }, [audioUrl, drawWaveform]);

  const togglePlay = useCallback((): void => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch(() => {});
    }
    setIsPlaying(!isPlaying);
  }, [isPlaying]);

  const handleTimeUpdate = useCallback((): void => {
    const audio = audioRef.current;
    if (!audio) return;
    setCurrentTime(audio.currentTime);
  }, []);

  const handleLoadedMetadata = useCallback((): void => {
    const audio = audioRef.current;
    if (!audio) return;
    setDuration(audio.duration);
  }, []);

  const handleSeek = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>): void => {
      const audio = audioRef.current;
      if (!audio) return;
      const time = parseFloat(e.target.value);
      audio.currentTime = time;
      setCurrentTime(time);
    },
    []
  );

  const handleRegenerate = useCallback(async (): Promise<void> => {
    setIsRegenerating(true);
    try {
      await onRegenerate(asset.id);
    } finally {
      setIsRegenerating(false);
    }
  }, [asset.id, onRegenerate]);

  const formatTime = (secs: number): string => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div
      ref={cardRef}
      className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl p-5"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {assetLabel(asset, sceneIndex)}
          </span>
          {/* Quality lives in `asset_quality_scores` behind /api/v1/quality
              and is not on this payload, so no SNR badge is claimed here. */}
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
            {formatBytes(asset.file_size_bytes)}
            {asset.duration_seconds != null
              ? ` · ${formatDuration(asset.duration_seconds)}`
              : ""}
            {asset.language_code ? ` · ${asset.language_code}` : ""}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => download(asset)}
            disabled={downloadingId === asset.id}
            className="px-3 py-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
          >
            {downloadingId === asset.id ? "Downloading…" : "↓ Download"}
          </button>
          {canEdit && (
            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="px-3 py-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
            >
              {isRegenerating ? "Regenerating…" : "Regenerate"}
            </button>
          )}
        </div>
      </div>

      {/* Waveform Canvas */}
      <canvas
        ref={canvasRef}
        width={600}
        height={60}
        className="w-full h-[60px] rounded-lg mb-3"
      />

      {mediaError && (
        <p className="text-xs text-red-500 dark:text-red-400 mb-2">
          Could not load this track: {mediaError}
        </p>
      )}

      {/* Audio Controls */}
      <div className="flex items-center gap-3">
        <button
          onClick={togglePlay}
          disabled={!audioUrl}
          title={mediaLoading ? "Loading audio…" : undefined}
          className="w-8 h-8 flex items-center justify-center bg-blue-600 rounded-full text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
        >
          {isPlaying ? (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        <span className="text-xs text-gray-500 dark:text-gray-400 font-mono w-12">
          {formatTime(currentTime)}
        </span>

        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={currentTime}
          onChange={handleSeek}
          className="flex-1 h-1 accent-blue-500"
        />

        <span className="text-xs text-gray-500 dark:text-gray-400 font-mono w-12 text-right">
          {formatTime(duration)}
        </span>
      </div>

      <audio
        ref={audioRef}
        src={audioUrl ?? undefined}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={() => setIsPlaying(false)}
        preload="metadata"
      />
    </div>
  );
}

export default function AudioPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;
  const { user } = useAuth();
  const { assets, isLoading, error, regenerateAsset, mutate } =
    useAssets(projectId);

  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastType, setToastType] = useState<"success" | "error">("success");
  const [showToast, setShowToast] = useState<boolean>(false);

  const canEdit = user?.role === "admin" || user?.role === "operator";

  const sceneIndexById = useSceneIndexMap(projectId);

  /**
   * Filter to audio by DERIVED media kind rather than `asset_type`, so a
   * track stored under any pipeline role still appears if its mime type
   * says it is audio.
   */
  const audioAssets = React.useMemo<Asset[]>(
    () =>
      (assets || [])
        .filter((a: Asset) => assetMediaKind(a) === "audio")
        .sort((a, b) => {
          const ai = a.scene_id ? sceneIndexById.get(a.scene_id) ?? 1e9 : 1e9;
          const bi = b.scene_id ? sceneIndexById.get(b.scene_id) ?? 1e9 : 1e9;
          return ai - bi;
        }),
    [assets, sceneIndexById]
  );

  const handleRegenerate = useCallback(
    async (assetId: string): Promise<void> => {
      try {
        await regenerateAsset(assetId);
        setToastMessage("Audio regeneration queued.");
        setToastType("success");
        setShowToast(true);
        mutate();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Regeneration failed.";
        setToastMessage(message);
        setToastType("error");
        setShowToast(true);
      }
    },
    [regenerateAsset, mutate]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner size="lg" label="Loading audio…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-red-600 dark:text-red-400">
          Failed to load audio: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Audio</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            {audioAssets.length} audio track
            {audioAssets.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {audioAssets.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          No audio tracks generated yet.
        </div>
      ) : (
        <div className="space-y-4">
          {audioAssets.map((asset: Asset) => (
            <AudioScenePlayer
              key={asset.id}
              asset={asset}
              sceneIndex={
                asset.scene_id ? sceneIndexById.get(asset.scene_id) ?? null : null
              }
              canEdit={canEdit}
              onRegenerate={handleRegenerate}
            />
          ))}
        </div>
      )}

      {showToast && (
        <Toast
          message={toastMessage}
          type={toastType}
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
}
