"""Caption reconciliation via STT + forced alignment.
Produces SRT/VTT with word-level timestamps aligned to actual audio."""
import os
import re
import json
import logging
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from app.models.caption_alignment import CaptionAlignment
from app.core.database import get_db_context

logger = logging.getLogger(__name__)

LEAD_TIME_MS = 200    # Caption appears 200ms before word
MAX_DRIFT_MS = 100.0  # Acceptable drift threshold
REVIEW_THRESHOLD_MATCH = 0.90  # Flag for review if STT match < 90%


class CaptionReconciliation:
    def __init__(
        self,
        workdir: str = "/mnt/workdir",
        mfa_path: str = "/opt/mfa",
        whisper_model: str = "large-v3",
    ):
        self.workdir = workdir
        self.mfa_path = mfa_path
        self.whisper_model = whisper_model

    # ------------------------------------------------------------------
    # Step 1: STT transcription via Whisper
    # ------------------------------------------------------------------
    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "en",
    ) -> Dict:
        """Transcribe audio to text with word-level timestamps via Whisper."""
        logger.info("Transcribing: %s (lang=%s)", audio_path, language)
        try:
            import whisper
            model = whisper.load_model(self.whisper_model)
            result = model.transcribe(
                audio_path,
                language=language,
                word_timestamps=True,
                verbose=False,
            )
            return result
        except ImportError:
            # Fallback: call whisper CLI
            output_json = audio_path + ".whisper.json"
            cmd = [
                "whisper", audio_path,
                "--model", self.whisper_model,
                "--language", language,
                "--word_timestamps", "True",
                "--output_format", "json",
                "--output_dir", str(Path(audio_path).parent),
            ]
            subprocess.run(cmd, check=True, timeout=300)
            with open(output_json) as f:
                return json.load(f)

    # ------------------------------------------------------------------
    # Step 2: Compare spoken vs original text
    # ------------------------------------------------------------------
    def compare_transcripts(
        self,
        original: str,
        spoken: str,
    ) -> float:
        """Return SequenceMatcher similarity ratio."""
        orig_clean = re.sub(r'[^\w\s]', '', original.lower().strip())
        spoken_clean = re.sub(r'[^\w\s]', '', spoken.lower().strip())
        ratio = SequenceMatcher(None, orig_clean, spoken_clean).ratio()
        return ratio

    # ------------------------------------------------------------------
    # Step 3: Forced alignment (MFA or Gentle)
    # ------------------------------------------------------------------
    def run_forced_alignment(
        self,
        audio_path: str,
        transcript_text: str,
        language: str = "en",
    ) -> List[Dict]:
        """Run MFA forced alignment, return word-level timestamps."""
        tmp_dir = os.path.join(self.workdir, "mfa_tmp",
                               Path(audio_path).stem)
        os.makedirs(tmp_dir, exist_ok=True)

        # Write transcript for MFA
        transcript_path = os.path.join(tmp_dir, "transcript.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        # Try MFA first
        try:
            cmd = [
                os.path.join(self.mfa_path, "bin", "mfa_align"),
                tmp_dir,
                f"english_mfa" if language == "en" else f"{language}_mfa",
                "english_us_arpa",
                os.path.join(tmp_dir, "output"),
                "--clean",
            ]
            result = subprocess.run(cmd, capture_output=True,
                                    timeout=120, text=True)
            if result.returncode == 0:
                return self._parse_textgrid(
                    os.path.join(tmp_dir, "output",
                                 Path(audio_path).stem + ".TextGrid"))
        except Exception as exc:
            logger.warning("MFA failed (%s) — trying Gentle", exc)

        # Fallback: Gentle HTTP API
        return self._run_gentle(audio_path, transcript_text)

    def _run_gentle(self, audio_path: str, text: str) -> List[Dict]:
        """Use Gentle forced aligner HTTP API."""
        try:
            import requests
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    "http://localhost:8765/transcriptions",
                    data={"transcript": text},
                    files={"audio": f},
                    timeout=120,
                )
            words = resp.json().get("words", [])
            return [
                {
                    "word": w["word"],
                    "start_ms": int(w.get("start", 0) * 1000),
                    "end_ms": int(w.get("end", 0) * 1000),
                    "score": 1.0 if w.get("case") == "success" else 0.5,
                }
                for w in words
                if w.get("case") in ("success", "unaligned")
            ]
        except Exception as exc:
            logger.error("Gentle alignment failed: %s", exc)
            return []

    def _parse_textgrid(self, textgrid_path: str) -> List[Dict]:
        """Parse Praat TextGrid file for word-level timestamps."""
        words = []
        try:
            with open(textgrid_path, "r") as f:
                content = f.read()
            # Simple regex-based TextGrid parser
            intervals = re.findall(
                r'xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "([^"]*)"',
                content)
            for xmin, xmax, text in intervals:
                if text.strip() and text not in ("", "sp", "sil"):
                    words.append({
                        "word": text.strip(),
                        "start_ms": int(float(xmin) * 1000),
                        "end_ms": int(float(xmax) * 1000),
                        "score": 0.95,
                    })
        except Exception as exc:
            logger.error("TextGrid parse failed: %s", exc)
        return words

    # ------------------------------------------------------------------
    # Step 4: Generate SRT/VTT
    # ------------------------------------------------------------------
    def generate_srt(
        self,
        word_timestamps: List[Dict],
        output_path: str,
        group_size: int = 6,
    ) -> str:
        """Generate SRT file grouping words into caption blocks."""
        def ms_to_srt(ms: int) -> str:
            h = ms // 3600000
            m = (ms % 3600000) // 60000
            s = (ms % 60000) // 1000
            ms_r = ms % 1000
            return f"{h:02d}:{m:02d}:{s:02d},{ms_r:03d}"

        lines = []
        for i in range(0, len(word_timestamps), group_size):
            group = word_timestamps[i: i + group_size]
            start_ms = max(0, group[0]["start_ms"] - LEAD_TIME_MS)
            end_ms = group[-1]["end_ms"]
            text = " ".join(w["word"] for w in group)
            lines.append(f"{i // group_size + 1}")
            lines.append(f"{ms_to_srt(start_ms)} --> {ms_to_srt(end_ms)}")
            lines.append(text)
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return output_path

    def generate_vtt(
        self,
        word_timestamps: List[Dict],
        output_path: str,
        group_size: int = 6,
    ) -> str:
        """Generate WebVTT file from word timestamps."""
        def ms_to_vtt(ms: int) -> str:
            h = ms // 3600000
            m = (ms % 3600000) // 60000
            s = (ms % 60000) // 1000
            ms_r = ms % 1000
            return f"{h:02d}:{m:02d}:{s:02d}.{ms_r:03d}"

        lines = ["WEBVTT", ""]
        for i in range(0, len(word_timestamps), group_size):
            group = word_timestamps[i: i + group_size]
            start_ms = max(0, group[0]["start_ms"] - LEAD_TIME_MS)
            end_ms = group[-1]["end_ms"]
            text = " ".join(w["word"] for w in group)
            lines.append(f"{ms_to_vtt(start_ms)} --> {ms_to_vtt(end_ms)}")
            lines.append(text)
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return output_path

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def align_captions(
        self,
        job_id: str,
        scene_id: str,
        audio_path: str,
        original_text: str,
        language_code: str = "en",
    ) -> Tuple[str, str]:
        """Full pipeline: STT → compare → align → SRT/VTT.
        Returns (srt_path, vtt_path)."""
        out_dir = os.path.join(self.workdir, job_id, "captions",
                               scene_id, language_code)
        os.makedirs(out_dir, exist_ok=True)

        # Step 1: STT
        logger.info("Running STT on %s", audio_path)
        stt_result = self.transcribe_audio(audio_path, language_code)
        spoken_text = stt_result.get("text", "")

        # Step 2: Compare
        match_ratio = self.compare_transcripts(original_text, spoken_text)
        logger.info("Text match ratio: %.3f", match_ratio)

        # Step 3: Forced alignment
        word_timestamps = self.run_forced_alignment(
            audio_path, original_text, language_code)
        if not word_timestamps:
            # Fallback: use Whisper word timestamps directly
            word_timestamps = [
                {"word": w["word"],
                 "start_ms": int(w["start"] * 1000),
                 "end_ms":   int(w["end"] * 1000),
                 "score": 0.8}
                for seg in stt_result.get("segments", [])
                for w in seg.get("words", [])
            ]

        # Calculate drift metrics
        drifts = []
        for wt in word_timestamps:
            if "expected_ms" in wt:
                drifts.append(abs(wt["expected_ms"] - wt["start_ms"]))
        drift_max = max(drifts) if drifts else 0.0
        drift_p95 = float(np.percentile(drifts, 95)) if drifts else 0.0

        # Step 4: Generate SRT + VTT
        srt_path = self.generate_srt(
            word_timestamps, os.path.join(out_dir, f"{scene_id}.srt"))
        vtt_path = self.generate_vtt(
            word_timestamps, os.path.join(out_dir, f"{scene_id}.vtt"))

        # Persist to DB
        status = "aligned"
        if drift_max > MAX_DRIFT_MS:
            status = "drifted"
        if match_ratio < REVIEW_THRESHOLD_MATCH:
            status = "review_required"

        with get_db_context() as db:
            record = CaptionAlignment(
                job_id=job_id,
                scene_id=scene_id,
                language_code=language_code,
                original_text=original_text,
                spoken_text=spoken_text,
                text_match_ratio=match_ratio,
                word_timestamps=word_timestamps,
                drift_ms_max=drift_max,
                drift_ms_p95=drift_p95,
                output_srt_path=srt_path,
                output_vtt_path=vtt_path,
                status=status,
            )
            db.add(record)
            db.commit()

        logger.info("Caption alignment done: status=%s drift_max=%.0f ms",
                    status, drift_max)
        return srt_path, vtt_path
