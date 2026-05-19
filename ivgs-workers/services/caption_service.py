"""
IVGS v5 — Caption Service
=============================

SRT and VTT caption file generation from WhisperX word-level timestamps
per §7.1.6 and §17.3.

Caption formats:
- SRT: Standard SubRip format for FFmpeg subtitle filter
- VTT: WebVTT for web player overlay
- Burned-in: Parameters for FFmpeg subtitles filter
    - Font: Noto Sans (CJK + RTL support)
    - Size: 36pt at 1080p, 72pt at 4K
    - Color: White with black outline (2px) and shadow

WhisperX provides word-level timestamps:
    [{"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.98}, ...]

Caption grouping strategy:
- Group words into lines of max ~10 words or ~60 characters
- Each caption entry: 2–4 seconds duration
- Respect sentence boundaries where possible
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger("ivgs.services.captions")


# ---------------------------------------------------------------------------
# Caption grouping
# ---------------------------------------------------------------------------

class CaptionEntry:
    """A single caption entry with timing."""

    def __init__(
        self,
        index: int,
        start_seconds: float,
        end_seconds: float,
        text: str,
    ):
        self.index = index
        self.start_seconds = start_seconds
        self.end_seconds = end_seconds
        self.text = text

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


class CaptionService:
    """
    Generates SRT and VTT caption files from WhisperX timestamps.

    Handles:
    - Word-level timestamp grouping
    - Sentence boundary detection
    - Multi-line caption formatting
    - SRT and VTT output
    """

    def __init__(
        self,
        max_words_per_line: int = 10,
        max_chars_per_line: int = 60,
        max_duration_seconds: float = 4.0,
        min_duration_seconds: float = 1.0,
        gap_seconds: float = 0.1,
    ):
        self._max_words = max_words_per_line
        self._max_chars = max_chars_per_line
        self._max_duration = max_duration_seconds
        self._min_duration = min_duration_seconds
        self._gap = gap_seconds

    def group_words(
        self,
        timestamps: List[Dict[str, Any]],
    ) -> List[CaptionEntry]:
        """
        Group word-level timestamps into caption entries.

        Input: [{"word": "Hello", "start": 0.0, "end": 0.5}, ...]
        Output: List of CaptionEntry with grouped words.
        """
        if not timestamps:
            return []

        entries: List[CaptionEntry] = []
        current_words: List[str] = []
        current_start: Optional[float] = None
        current_end: float = 0.0
        entry_index = 1

        for ts in timestamps:
            word = ts.get("word", ts.get("text", "")).strip()
            start = ts.get("start", 0.0)
            end = ts.get("end", start + 0.3)

            if not word:
                continue

            # Start new group if:
            # 1. No current group
            # 2. Word count exceeds max
            # 3. Character count exceeds max
            # 4. Duration exceeds max
            # 5. Sentence boundary detected

            current_text = " ".join(current_words + [word])
            is_sentence_end = bool(re.search(r"[.!?]$", word))
            duration = end - (current_start or start)

            should_break = False
            if not current_words:
                pass  # Start new group
            elif len(current_words) >= self._max_words:
                should_break = True
            elif len(current_text) > self._max_chars:
                should_break = True
            elif duration > self._max_duration:
                should_break = True

            if should_break and current_words:
                # Flush current group
                entries.append(CaptionEntry(
                    index=entry_index,
                    start_seconds=current_start or 0.0,
                    end_seconds=current_end,
                    text=" ".join(current_words),
                ))
                entry_index += 1
                current_words = []
                current_start = None

            if current_start is None:
                current_start = start

            current_words.append(word)
            current_end = end

            # Break on sentence end
            if is_sentence_end and current_words:
                entries.append(CaptionEntry(
                    index=entry_index,
                    start_seconds=current_start,
                    end_seconds=current_end,
                    text=" ".join(current_words),
                ))
                entry_index += 1
                current_words = []
                current_start = None

        # Flush remaining
        if current_words:
            entries.append(CaptionEntry(
                index=entry_index,
                start_seconds=current_start or 0.0,
                end_seconds=current_end,
                text=" ".join(current_words),
            ))

        # Enforce minimum duration
        for entry in entries:
            if entry.duration < self._min_duration:
                entry.end_seconds = entry.start_seconds + self._min_duration

        return entries

    # ----- SRT output -----

    def generate_srt(
        self,
        timestamps: List[Dict[str, Any]],
    ) -> str:
        """Generate SRT content from word-level timestamps."""
        entries = self.group_words(timestamps)
        lines: List[str] = []

        for entry in entries:
            start_tc = self._format_srt_timecode(entry.start_seconds)
            end_tc = self._format_srt_timecode(entry.end_seconds)
            lines.append(str(entry.index))
            lines.append(f"{start_tc} --> {end_tc}")
            lines.append(entry.text)
            lines.append("")

        return "\n".join(lines)

    def write_srt(
        self,
        timestamps: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Write SRT file from timestamps."""
        content = self.generate_srt(timestamps)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(
            "srt_written",
            path=output_path,
            entry_count=len(self.group_words(timestamps)),
        )
        return output_path

    # ----- VTT output -----

    def generate_vtt(
        self,
        timestamps: List[Dict[str, Any]],
    ) -> str:
        """Generate WebVTT content from word-level timestamps."""
        entries = self.group_words(timestamps)
        lines: List[str] = ["WEBVTT", ""]

        for entry in entries:
            start_tc = self._format_vtt_timecode(entry.start_seconds)
            end_tc = self._format_vtt_timecode(entry.end_seconds)
            lines.append(f"{start_tc} --> {end_tc}")
            lines.append(entry.text)
            lines.append("")

        return "\n".join(lines)

    def write_vtt(
        self,
        timestamps: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Write VTT file from timestamps."""
        content = self.generate_vtt(timestamps)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(
            "vtt_written",
            path=output_path,
            entry_count=len(self.group_words(timestamps)),
        )
        return output_path

    # ----- Timecode formatting -----

    @staticmethod
    def _format_srt_timecode(seconds: float) -> str:
        """Format seconds to SRT timecode: HH:MM:SS,mmm"""
        td = timedelta(seconds=max(0, seconds))
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_vtt_timecode(seconds: float) -> str:
        """Format seconds to VTT timecode: HH:MM:SS.mmm"""
        td = timedelta(seconds=max(0, seconds))
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
