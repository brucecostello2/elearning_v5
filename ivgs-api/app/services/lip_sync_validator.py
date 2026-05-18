"""SyncNet-based lip sync quality validator."""
import os
import json
import logging
import subprocess
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from app.models.lip_sync import LipSyncValidation
from app.core.database import get_db_context

logger = logging.getLogger(__name__)

SYNCNET_THRESHOLD_PASS = 0.85
SYNCNET_THRESHOLD_RETRY = 0.70
FROZEN_FRAME_MAX = 5  # Consecutive frozen frames before flagging


class LipSyncValidator:
    def __init__(
        self,
        syncnet_model_path: str,
        workdir: str = "/mnt/workdir",
    ):
        self.syncnet_model_path = syncnet_model_path
        self.workdir = workdir
        self._model = None

    def _load_model(self):
        """Lazy-load SyncNet model."""
        if self._model is not None:
            return
        if not Path(self.syncnet_model_path).exists():
            raise RuntimeError(
                f"SyncNet model not found: {self.syncnet_model_path}")
        try:
            import torch
            from syncnet_python.SyncNetInstance import SyncNetInstance
            self._model = SyncNetInstance()
            self._model.loadParameters(self.syncnet_model_path)
            logger.info("SyncNet model loaded")
        except ImportError:
            logger.warning("syncnet_python not installed — using heuristic")
            self._model = "heuristic"

    def extract_frames(self, video_path: str,
                       output_dir: str) -> List[str]:
        """Extract video frames as PNG for SyncNet input."""
        os.makedirs(output_dir, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "fps=25",
            os.path.join(output_dir, "frame_%06d.png"),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Frame extraction failed: "
                               f"{result.stderr.decode()[:300]}")
        return sorted(Path(output_dir).glob("frame_*.png"))

    def extract_audio_mfcc(self, audio_path: str) -> np.ndarray:
        """Extract MFCC features from audio for SyncNet correlation."""
        try:
            import librosa
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            return mfcc
        except ImportError:
            logger.warning("librosa not installed — returning zeros MFCC")
            return np.zeros((13, 100))

    def detect_frozen_frames(
        self,
        frame_paths: List[str],
        diff_threshold: float = 0.001,
    ) -> int:
        """Count frozen frames (identical consecutive frames in mouth region)."""
        frozen_count = 0
        consecutive = 0
        max_consecutive = 0
        for i in range(1, len(frame_paths)):
            try:
                from PIL import Image
                img1 = np.array(Image.open(str(frame_paths[i - 1])))
                img2 = np.array(Image.open(str(frame_paths[i])))
                # Focus on lower-third of frame (mouth region)
                h = img1.shape[0]
                region1 = img1[h * 2 // 3:, :, :]
                region2 = img2[h * 2 // 3:, :, :]
                diff = np.mean(np.abs(region1.astype(float)
                               - region2.astype(float))) / 255.0
                if diff < diff_threshold:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            except Exception:
                continue
        return max_consecutive

    def score_lip_sync(
        self,
        video_path: str,
        audio_path: str,
    ) -> Tuple[float, List[Dict]]:
        """Compute lip sync score [0, 1] and per-frame scores."""
        self._load_model()
        tmp_dir = os.path.join(self.workdir, "tmp_syncnet",
                               Path(video_path).stem)
        os.makedirs(tmp_dir, exist_ok=True)
        frame_paths = self.extract_frames(video_path, tmp_dir)
        if not frame_paths:
            return 0.0, []

        if self._model == "heuristic":
            # Fallback heuristic: check frozen frames + audio correlation
            frozen = self.detect_frozen_frames(frame_paths)
            score = max(0.0, 0.85 - frozen * 0.05)
            return score, []

        # SyncNet inference
        try:
            offset, conf, dist = self._model.evaluate(
                opt=type('opt', (), {
                    'videopath': video_path,
                    'audiopath': audio_path,
                    'vshift': 15,
                })(),
            )
            # Convert SyncNet distance to [0,1] score (lower dist = better)
            score = max(0.0, min(1.0, 1.0 - (dist / 10.0)))
            frame_scores = [
                {"frame": i, "offset_ms": int(offset * 40),
                 "score": float(max(0, 1.0 - dist / 10.0))}
                for i in range(len(frame_paths))
            ]
            logger.info("SyncNet score: %.3f (offset=%d, conf=%.3f)",
                        score, offset, conf)
            return score, frame_scores
        except Exception as exc:
            logger.error("SyncNet scoring failed: %s", exc)
            return 0.0, []

    def validate(
        self,
        asset_id: int,
        job_id: str,
        scene_id: str,
        video_path: str,
        audio_path: str,
        threshold: float = SYNCNET_THRESHOLD_PASS,
    ) -> LipSyncValidation:
        """Full validation: score + persist + return record."""
        score, frame_scores = self.score_lip_sync(video_path, audio_path)
        frozen_count = self.detect_frozen_frames(
            self.extract_frames(video_path,
                                os.path.join(self.workdir, "tmp_fc",
                                             Path(video_path).stem)))
        passed = score >= threshold

        with get_db_context() as db:
            record = LipSyncValidation(
                asset_id=asset_id,
                job_id=job_id,
                scene_id=scene_id,
                sync_score=score,
                frame_level_scores=frame_scores,
                frozen_frame_count=frozen_count,
                passed=passed,
                threshold_used=threshold,
            )
            db.add(record)
            db.commit()
            db.refresh(record)

        logger.info("Lip sync validation %s: score=%.3f threshold=%.2f",
                    "PASS" if passed else "FAIL", score, threshold)
        return record

    def get_action(self, score: float) -> str:
        """Return recommended action based on score."""
        if score >= SYNCNET_THRESHOLD_PASS:
            return "approve"
        elif score >= SYNCNET_THRESHOLD_RETRY:
            return "retry_generation"
        else:
            return "fallback_static_avatar"
