"""
IVGS v5 — FFmpeg Composition Engine
=======================================

FFmpeg subprocess client for timeline-based video composition per §6.1 Stages 7–8.

Composition layer stack (Table 6-3):
    Layer 0 (Background):   Scene image / video clip / animation — full frame
    Layer 1 (Talking Head):  Lip-synced presenter — bottom-right PiP or full-screen
    Layer 2 (Lower Third):  Remotion overlay — bottom 20% of frame
    Layer 3 (Captions):     Burned-in subtitles — bottom center
                            (Noto Sans, 36pt@1080p, 72pt@4K)
    Layer 4 (Audio):        TTS voice track (WAV 48kHz)

Output formats (Table 6-2):
    Draft:  1280×720 H.264 CRF 23, 30fps
    1080p:  1920×1080 H.264 CRF 18, VBV 8 Mbps, AAC 192 kbps 48kHz stereo
    4K:     3840×2160 H.265 CRF 20, VBV 20 Mbps, AAC 256 kbps 48kHz stereo

All FFmpeg operations use subprocess with explicit timeout management.
SHA-256 checksums computed post-render for integrity verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger("ivgs.ffmpeg_client")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FFmpegError(Exception):
    """Base exception for FFmpeg errors."""

    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg binary not found on system."""
    pass


class FFmpegTimeoutError(FFmpegError):
    """FFmpeg process timed out."""
    pass


class FFmpegCompositionError(FFmpegError):
    """FFmpeg composition/render failed."""
    pass


class FFmpegConcatError(FFmpegError):
    """FFmpeg concat demuxer operation failed."""
    pass


class FFmpegProbeError(FFmpegError):
    """FFprobe analysis failed."""
    pass


# ---------------------------------------------------------------------------
# Enums and config
# ---------------------------------------------------------------------------

class RenderProfile(str, Enum):
    """Render quality profiles per Table 6-2."""
    DRAFT = "draft"
    HD_1080P = "1080p"
    UHD_4K = "4k"


class PiPPosition(str, Enum):
    """Picture-in-Picture positioning for talking head overlay."""
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_LEFT = "bottom_left"
    TOP_RIGHT = "top_right"
    TOP_LEFT = "top_left"
    FULL_SCREEN = "full_screen"


@dataclass(frozen=True)
class RenderProfileConfig:
    """Configuration for a render profile."""
    width: int
    height: int
    video_codec: str
    audio_codec: str
    crf: int
    fps: int
    video_bitrate: Optional[str]
    vbv_maxrate: Optional[str]
    vbv_bufsize: Optional[str]
    audio_bitrate: str
    audio_sample_rate: int
    audio_channels: int
    preset: str
    pixel_format: str
    caption_font_size: int


# Profile presets per Table 6-2
RENDER_PROFILES: Dict[RenderProfile, RenderProfileConfig] = {
    RenderProfile.DRAFT: RenderProfileConfig(
        width=1280,
        height=720,
        video_codec="libx264",
        audio_codec="aac",
        crf=23,
        fps=30,
        video_bitrate=None,
        vbv_maxrate=None,
        vbv_bufsize=None,
        audio_bitrate="128k",
        audio_sample_rate=48000,
        audio_channels=2,
        preset="fast",
        pixel_format="yuv420p",
        caption_font_size=24,
    ),
    RenderProfile.HD_1080P: RenderProfileConfig(
        width=1920,
        height=1080,
        video_codec="libx264",
        audio_codec="aac",
        crf=18,
        fps=30,
        video_bitrate="8M",
        vbv_maxrate="8M",
        vbv_bufsize="16M",
        audio_bitrate="192k",
        audio_sample_rate=48000,
        audio_channels=2,
        preset="medium",
        pixel_format="yuv420p",
        caption_font_size=36,
    ),
    RenderProfile.UHD_4K: RenderProfileConfig(
        width=3840,
        height=2160,
        video_codec="libx265",
        audio_codec="aac",
        crf=20,
        fps=30,
        video_bitrate="20M",
        vbv_maxrate="20M",
        vbv_bufsize="40M",
        audio_bitrate="256k",
        audio_sample_rate=48000,
        audio_channels=2,
        preset="medium",
        pixel_format="yuv420p10le",
        caption_font_size=72,
    ),
}


@dataclass
class SceneLayer:
    """A single layer in the composition timeline."""
    layer_type: str  # background, talking_head, lower_third, caption, audio
    file_path: str
    start_time: float = 0.0
    duration: float = 0.0
    position: Optional[PiPPosition] = None
    scale: float = 1.0
    opacity: float = 1.0
    has_alpha: bool = False


@dataclass
class TimelineScene:
    """A scene in the composition timeline with all its layers."""
    scene_id: str
    scene_index: int
    start_time: float
    duration: float
    layers: List[SceneLayer] = field(default_factory=list)


@dataclass
class CompositionTimeline:
    """Full composition timeline with all scenes and layers."""
    project_id: str
    scenes: List[TimelineScene] = field(default_factory=list)
    total_duration: float = 0.0
    profile: RenderProfile = RenderProfile.DRAFT

    @property
    def scene_count(self) -> int:
        return len(self.scenes)


@dataclass
class FFmpegRenderResult:
    """Result from an FFmpeg render operation."""
    output_path: str
    file_size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    video_bitrate_kbps: float
    audio_bitrate_kbps: float
    sha256_hash: str
    render_time_seconds: float
    profile: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# FFmpegClient
# ---------------------------------------------------------------------------

class FFmpegClient:
    """
    FFmpeg subprocess client for video composition.

    Provides:
    - compose_scene(): Single scene composition with layer stacking
    - compose_timeline(): Full timeline composition (all scenes)
    - render_draft(): 720p prototype draft (Stage 7)
    - render_final(): 1080p/4K final render (Stage 8)
    - concat_segments(): Concatenate rendered segments (Stage 8)
    - probe(): FFprobe metadata extraction

    All operations write to a temp directory and return paths to output files.
    """

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        temp_dir: Optional[str] = None,
        default_timeout: float = 900.0,
        hardware_accel: Optional[str] = None,
    ):
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path
        self._temp_dir = temp_dir or tempfile.mkdtemp(prefix="ivgs_ffmpeg_")
        self._default_timeout = default_timeout
        self._hw_accel = hardware_accel

        # Verify ffmpeg is available
        if not shutil.which(self._ffmpeg):
            raise FFmpegNotFoundError(f"FFmpeg not found at: {self._ffmpeg}")
        if not shutil.which(self._ffprobe):
            raise FFmpegNotFoundError(f"FFprobe not found at: {self._ffprobe}")

    # ----- Probe -----

    def probe(self, file_path: str, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Run ffprobe on a media file and return parsed JSON metadata.

        Returns dict with 'streams' and 'format' keys.
        """
        cmd = [
            self._ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise FFmpegProbeError(
                f"FFprobe timed out after {timeout}s: {file_path}",
            ) from e

        if result.returncode != 0:
            raise FFmpegProbeError(
                f"FFprobe failed (rc={result.returncode}): {result.stderr[:500]}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise FFmpegProbeError(
                f"FFprobe output not valid JSON: {e}",
            ) from e

    def get_duration(self, file_path: str) -> float:
        """Get media file duration in seconds."""
        probe_data = self.probe(file_path)
        fmt = probe_data.get("format", {})
        duration_str = fmt.get("duration", "0")
        return float(duration_str)

    def get_resolution(self, file_path: str) -> Tuple[int, int]:
        """Get video resolution (width, height)."""
        probe_data = self.probe(file_path)
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                return (
                    int(stream.get("width", 0)),
                    int(stream.get("height", 0)),
                )
        return (0, 0)

    # ----- Single scene composition -----

    def compose_scene(
        self,
        scene: TimelineScene,
        profile: RenderProfile,
        output_path: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> FFmpegRenderResult:
        """
        Compose a single scene with layer stacking per Table 6-3.

        Builds a complex filtergraph:
        1. Scale background to target resolution
        2. Overlay talking head (PiP or full-screen)
        3. Overlay lower-third (transparent WebM)
        4. Burn in captions (subtitle filter)
        5. Mix audio track
        """
        start_time = time.monotonic()
        config = RENDER_PROFILES[profile]
        timeout = timeout or self._default_timeout

        if output_path is None:
            output_path = os.path.join(
                self._temp_dir,
                f"scene_{scene.scene_id}_{profile.value}.mp4",
            )

        log = logger.bind(
            scene_id=scene.scene_id,
            profile=profile.value,
            num_layers=len(scene.layers),
        )

        # Classify layers
        background = None
        talking_head = None
        lower_third = None
        caption = None
        audio = None

        for layer in scene.layers:
            if layer.layer_type == "background":
                background = layer
            elif layer.layer_type == "talking_head":
                talking_head = layer
            elif layer.layer_type == "lower_third":
                lower_third = layer
            elif layer.layer_type == "caption":
                caption = layer
            elif layer.layer_type == "audio":
                audio = layer

        if not background:
            raise FFmpegCompositionError(
                f"Scene {scene.scene_id} has no background layer"
            )

        # Build ffmpeg command
        cmd = [self._ffmpeg, "-y"]

        # Hardware acceleration
        if self._hw_accel:
            cmd.extend(["-hwaccel", self._hw_accel])

        # Input files
        input_idx = 0
        input_map: Dict[str, int] = {}

        # Background input
        cmd.extend(["-i", background.file_path])
        input_map["background"] = input_idx
        input_idx += 1

        # Talking head input
        if talking_head:
            cmd.extend(["-i", talking_head.file_path])
            input_map["talking_head"] = input_idx
            input_idx += 1

        # Lower third input (transparent WebM)
        if lower_third:
            cmd.extend(["-i", lower_third.file_path])
            input_map["lower_third"] = input_idx
            input_idx += 1

        # Audio input
        if audio:
            cmd.extend(["-i", audio.file_path])
            input_map["audio"] = input_idx
            input_idx += 1

        # Build filtergraph
        filters = []
        current_video = f"[{input_map['background']}:v]"

        # Scale background to target resolution
        filters.append(
            f"{current_video}scale={config.width}:{config.height}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1[bg]"
        )
        current_video = "[bg]"

        # If background is an image, loop it for the scene duration
        bg_probe = self.probe(background.file_path)
        is_image = not any(
            s.get("codec_type") == "video" and float(s.get("duration", 0)) > 0.1
            for s in bg_probe.get("streams", [])
        )
        if is_image:
            # Re-encode image as video loop
            filters[-1] = (
                f"[{input_map['background']}:v]"
                f"loop=loop=-1:size=1:start=0,"
                f"trim=duration={scene.duration},"
                f"fps={config.fps},"
                f"scale={config.width}:{config.height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1[bg]"
            )

        # Overlay talking head
        if talking_head:
            th_idx = input_map["talking_head"]
            pos = talking_head.position or PiPPosition.BOTTOM_RIGHT
            scale = talking_head.scale or 0.25

            if pos == PiPPosition.FULL_SCREEN:
                filters.append(
                    f"[{th_idx}:v]scale={config.width}:{config.height}[th_scaled]"
                )
                filters.append(
                    f"{current_video}[th_scaled]overlay=0:0:shortest=1[with_th]"
                )
            else:
                th_w = int(config.width * scale)
                th_h = int(config.height * scale)
                margin = 20

                if pos == PiPPosition.BOTTOM_RIGHT:
                    x = f"{config.width - th_w - margin}"
                    y = f"{config.height - th_h - margin}"
                elif pos == PiPPosition.BOTTOM_LEFT:
                    x = f"{margin}"
                    y = f"{config.height - th_h - margin}"
                elif pos == PiPPosition.TOP_RIGHT:
                    x = f"{config.width - th_w - margin}"
                    y = f"{margin}"
                else:  # TOP_LEFT
                    x = f"{margin}"
                    y = f"{margin}"

                filters.append(
                    f"[{th_idx}:v]scale={th_w}:{th_h}[th_scaled]"
                )
                filters.append(
                    f"{current_video}[th_scaled]overlay={x}:{y}:shortest=1[with_th]"
                )

            current_video = "[with_th]"

        # Overlay lower third (transparent WebM)
        if lower_third:
            lt_idx = input_map["lower_third"]
            filters.append(
                f"[{lt_idx}:v]scale={config.width}:-1[lt_scaled]"
            )
            lt_y = int(config.height * 0.8)
            filters.append(
                f"{current_video}[lt_scaled]overlay=0:{lt_y}:shortest=1[with_lt]"
            )
            current_video = "[with_lt]"

        # Burn in captions
        if caption and caption.file_path:
            font_size = config.caption_font_size
            # Use subtitles filter for SRT/ASS files
            escaped_path = caption.file_path.replace(":", "\\:").replace("'", "\\'")
            filters.append(
                f"{current_video}subtitles='{escaped_path}':"
                f"force_style='FontName=Noto Sans,FontSize={font_size},"
                f"PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
                f"Outline=2,Shadow=1,Alignment=2,MarginV=40'[with_cap]"
            )
            current_video = "[with_cap]"

        # Finalize video label
        final_video_label = current_video.strip("[]")
        if current_video.startswith("[") and current_video.endswith("]"):
            final_video_label = current_video[1:-1]

        # Build filter_complex string
        filter_complex = ";".join(filters)
        cmd.extend(["-filter_complex", filter_complex])

        # Map outputs
        cmd.extend(["-map", f"[{final_video_label}]"])

        if audio:
            cmd.extend(["-map", f"{input_map['audio']}:a"])
        else:
            # Generate silent audio track
            cmd.extend([
                "-f", "lavfi", "-i",
                f"anullsrc=r={config.audio_sample_rate}:cl=stereo",
            ])
            cmd.extend(["-map", f"{input_idx}:a"])
            cmd.extend(["-t", str(scene.duration)])

        # Output encoding
        cmd.extend(["-c:v", config.video_codec])
        cmd.extend(["-crf", str(config.crf)])
        cmd.extend(["-preset", config.preset])
        cmd.extend(["-pix_fmt", config.pixel_format])

        if config.vbv_maxrate:
            cmd.extend(["-maxrate", config.vbv_maxrate])
        if config.vbv_bufsize:
            cmd.extend(["-bufsize", config.vbv_bufsize])

        cmd.extend(["-c:a", config.audio_codec])
        cmd.extend(["-b:a", config.audio_bitrate])
        cmd.extend(["-ar", str(config.audio_sample_rate)])
        cmd.extend(["-ac", str(config.audio_channels)])

        cmd.extend(["-r", str(config.fps)])
        cmd.extend(["-movflags", "+faststart"])
        cmd.extend([output_path])

        log.info(
            "ffmpeg_scene_compose_start",
            cmd_length=len(cmd),
        )

        # Execute
        result = self._run_ffmpeg(cmd, timeout=timeout)
        elapsed = time.monotonic() - start_time

        # Compute SHA-256
        sha256 = _compute_file_sha256(output_path)
        file_size = os.path.getsize(output_path)

        # Probe output
        output_probe = self.probe(output_path)
        output_duration = float(output_probe.get("format", {}).get("duration", 0))
        video_bitrate = 0.0
        audio_bitrate_actual = 0.0
        for stream in output_probe.get("streams", []):
            br = float(stream.get("bit_rate", 0))
            if stream.get("codec_type") == "video":
                video_bitrate = br / 1000
            elif stream.get("codec_type") == "audio":
                audio_bitrate_actual = br / 1000

        log.info(
            "ffmpeg_scene_compose_success",
            elapsed=round(elapsed, 2),
            file_size=file_size,
            duration=round(output_duration, 2),
        )

        return FFmpegRenderResult(
            output_path=output_path,
            file_size_bytes=file_size,
            duration_seconds=output_duration,
            width=config.width,
            height=config.height,
            fps=config.fps,
            video_codec=config.video_codec,
            audio_codec=config.audio_codec,
            video_bitrate_kbps=video_bitrate,
            audio_bitrate_kbps=audio_bitrate_actual,
            sha256_hash=sha256,
            render_time_seconds=round(elapsed, 2),
            profile=profile.value,
        )

    # ----- Full timeline composition -----

    def compose_timeline(
        self,
        timeline: CompositionTimeline,
        output_path: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> FFmpegRenderResult:
        """
        Compose a full timeline by rendering each scene and concatenating.

        1. Render each scene individually
        2. Generate concat file list
        3. Concatenate all scenes using concat demuxer
        4. Return final output
        """
        start_time = time.monotonic()
        profile = timeline.profile
        config = RENDER_PROFILES[profile]
        timeout = timeout or self._default_timeout

        if output_path is None:
            output_path = os.path.join(
                self._temp_dir,
                f"timeline_{timeline.project_id}_{profile.value}.mp4",
            )

        log = logger.bind(
            project_id=timeline.project_id,
            profile=profile.value,
            scene_count=timeline.scene_count,
        )

        # Render each scene
        scene_outputs: List[str] = []
        for scene in timeline.scenes:
            scene_output = self.compose_scene(
                scene=scene,
                profile=profile,
                timeout=timeout / max(timeline.scene_count, 1),
            )
            scene_outputs.append(scene_output.output_path)

        # Concatenate
        result = self.concat_segments(
            segment_paths=scene_outputs,
            output_path=output_path,
            profile=profile,
            timeout=timeout,
        )

        elapsed = time.monotonic() - start_time
        log.info(
            "ffmpeg_timeline_compose_success",
            elapsed=round(elapsed, 2),
            file_size=result.file_size_bytes,
        )

        result.render_time_seconds = round(elapsed, 2)
        return result

    # ----- Concat segments -----

    def concat_segments(
        self,
        segment_paths: List[str],
        output_path: str,
        profile: RenderProfile = RenderProfile.HD_1080P,
        timeout: Optional[float] = None,
        verify_checksums: Optional[Dict[str, str]] = None,
    ) -> FFmpegRenderResult:
        """
        Concatenate rendered segments using FFmpeg concat demuxer.

        Optionally verify SHA-256 checksums of each segment before concat.
        """
        start_time = time.monotonic()
        config = RENDER_PROFILES[profile]
        timeout = timeout or self._default_timeout

        log = logger.bind(
            num_segments=len(segment_paths),
            profile=profile.value,
        )

        # Verify checksums if provided (§6.1 Stage 8)
        if verify_checksums:
            for seg_path, expected_hash in verify_checksums.items():
                actual_hash = _compute_file_sha256(seg_path)
                if actual_hash != expected_hash:
                    raise FFmpegConcatError(
                        f"Segment checksum mismatch: {seg_path} "
                        f"(expected {expected_hash[:16]}..., got {actual_hash[:16]}...)"
                    )
            log.info("segment_checksums_verified", count=len(verify_checksums))

        # Verify all segments exist
        for seg_path in segment_paths:
            if not os.path.exists(seg_path):
                raise FFmpegConcatError(
                    f"Segment file not found: {seg_path}"
                )

        # Create concat file list
        concat_file = os.path.join(self._temp_dir, "concat_list.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for seg_path in segment_paths:
                # Escape single quotes in path
                escaped = seg_path.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # Build concat command
        cmd = [
            self._ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", config.video_codec,
            "-crf", str(config.crf),
            "-preset", config.preset,
            "-pix_fmt", config.pixel_format,
        ]

        if config.vbv_maxrate:
            cmd.extend(["-maxrate", config.vbv_maxrate])
        if config.vbv_bufsize:
            cmd.extend(["-bufsize", config.vbv_bufsize])

        cmd.extend([
            "-c:a", config.audio_codec,
            "-b:a", config.audio_bitrate,
            "-ar", str(config.audio_sample_rate),
            "-ac", str(config.audio_channels),
            "-r", str(config.fps),
            "-movflags", "+faststart",
            output_path,
        ])

        log.info("ffmpeg_concat_start")

        self._run_ffmpeg(cmd, timeout=timeout)

        elapsed = time.monotonic() - start_time
        sha256 = _compute_file_sha256(output_path)
        file_size = os.path.getsize(output_path)

        # Probe output
        output_probe = self.probe(output_path)
        output_duration = float(output_probe.get("format", {}).get("duration", 0))
        video_bitrate = 0.0
        audio_bitrate_actual = 0.0
        for stream in output_probe.get("streams", []):
            br = float(stream.get("bit_rate", 0))
            if stream.get("codec_type") == "video":
                video_bitrate = br / 1000
            elif stream.get("codec_type") == "audio":
                audio_bitrate_actual = br / 1000

        log.info(
            "ffmpeg_concat_success",
            elapsed=round(elapsed, 2),
            file_size=file_size,
            duration=round(output_duration, 2),
        )

        return FFmpegRenderResult(
            output_path=output_path,
            file_size_bytes=file_size,
            duration_seconds=output_duration,
            width=config.width,
            height=config.height,
            fps=config.fps,
            video_codec=config.video_codec,
            audio_codec=config.audio_codec,
            video_bitrate_kbps=video_bitrate,
            audio_bitrate_kbps=audio_bitrate_actual,
            sha256_hash=sha256,
            render_time_seconds=round(elapsed, 2),
            profile=profile.value,
        )

    # ----- Utility: scale/convert -----

    def scale_video(
        self,
        input_path: str,
        output_path: str,
        width: int,
        height: int,
        timeout: float = 120.0,
    ) -> str:
        """Scale a video to target resolution."""
        cmd = [
            self._ffmpeg, "-y",
            "-i", input_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        self._run_ffmpeg(cmd, timeout=timeout)
        return output_path

    def extract_audio(
        self,
        input_path: str,
        output_path: str,
        sample_rate: int = 48000,
        timeout: float = 60.0,
    ) -> str:
        """Extract audio track from video."""
        cmd = [
            self._ffmpeg, "-y",
            "-i", input_path,
            "-vn",
            "-acodec", "pcm_s24le",
            "-ar", str(sample_rate),
            "-ac", "1",
            output_path,
        ]
        self._run_ffmpeg(cmd, timeout=timeout)
        return output_path

    def generate_silence(
        self,
        output_path: str,
        duration: float,
        sample_rate: int = 48000,
        channels: int = 2,
        timeout: float = 30.0,
    ) -> str:
        """Generate a silent audio file."""
        cmd = [
            self._ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={sample_rate}:cl={'stereo' if channels == 2 else 'mono'}",
            "-t", str(duration),
            "-acodec", "pcm_s24le",
            output_path,
        ]
        self._run_ffmpeg(cmd, timeout=timeout)
        return output_path

    def concat_audio(
        self,
        audio_paths: List[str],
        output_path: str,
        timeout: float = 120.0,
    ) -> str:
        """Concatenate multiple audio files."""
        concat_file = os.path.join(self._temp_dir, "audio_concat.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for p in audio_paths:
                escaped = p.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        cmd = [
            self._ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:a", "copy",
            output_path,
        ]
        self._run_ffmpeg(cmd, timeout=timeout)
        return output_path

    # ----- Internal: run FFmpeg -----

    def _run_ffmpeg(
        self,
        cmd: List[str],
        timeout: float,
    ) -> subprocess.CompletedProcess:
        """Run an FFmpeg command with timeout and error handling."""
        log = logger.bind(cmd_head=" ".join(cmd[:6]))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise FFmpegTimeoutError(
                f"FFmpeg timed out after {timeout}s",
            ) from e
        except FileNotFoundError as e:
            raise FFmpegNotFoundError(
                f"FFmpeg binary not found: {e}",
            ) from e

        if result.returncode != 0:
            stderr_snippet = (result.stderr or "")[-1000:]
            log.error(
                "ffmpeg_command_failed",
                returncode=result.returncode,
                stderr=stderr_snippet,
            )
            raise FFmpegCompositionError(
                f"FFmpeg failed (rc={result.returncode}): {stderr_snippet}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        return result

    def cleanup(self) -> None:
        """Remove temporary directory and all files."""
        if os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            logger.info("ffmpeg_temp_cleaned", temp_dir=self._temp_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_file_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
