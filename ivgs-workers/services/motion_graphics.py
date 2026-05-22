"""
IVGS v5 — Motion Graphics Service
========================================

MotionGraphicsService for L2/L3 fallback strategies per §7.1.8 and Table 6-6.

L2 — Ken Burns Effect:
  Slow zoom-in with gentle pan across the image. Creates cinematic motion
  from a static image. 6-second duration at 30fps.

L3 — Simple Pan/Zoom:
  Basic horizontal or vertical pan with slight zoom. Simpler than Ken Burns
  but still provides motion. 6-second duration at 30fps.

Implementation: FFmpeg filtergraph with zoompan and scale filters.

Output format per §10.7:
- MP4 H.264, 480p or 720p, 24fps, 3–8 second clips

Remotion integration (§7.1.8):
  For more complex motion graphics (lower-thirds, animated titles),
  Remotion on node-06 is the primary tool. This service handles the
  simpler Ken Burns and pan/zoom effects that don't require React rendering.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DURATION_SECONDS: float = 6.0
DEFAULT_FPS: int = 30
DEFAULT_OUTPUT_WIDTH: int = 1280
DEFAULT_OUTPUT_HEIGHT: int = 720


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class MotionGraphicsConfig(BaseModel):
    """Configuration for motion graphics generation."""

    duration_seconds: float = Field(
        default=DEFAULT_DURATION_SECONDS,
        description="Output clip duration in seconds",
    )
    fps: int = Field(default=DEFAULT_FPS, description="Output frame rate")
    output_width: int = Field(
        default=DEFAULT_OUTPUT_WIDTH,
        description="Output video width in pixels",
    )
    output_height: int = Field(
        default=DEFAULT_OUTPUT_HEIGHT,
        description="Output video height in pixels",
    )
    zoom_start: float = Field(
        default=1.0,
        description="Starting zoom level (1.0 = no zoom)",
    )
    zoom_end: float = Field(
        default=1.3,
        description="Ending zoom level for Ken Burns",
    )
    pan_direction: str = Field(
        default="right",
        description="Pan direction: left, right, up, down",
    )


class MotionGraphicsResult(BaseModel):
    """Result of a motion graphics generation."""

    asset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    output_path: str = Field(..., description="SeaweedFS output path")
    duration_seconds: float
    resolution: str
    fps: int
    file_size_bytes: int = 0
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Motion Graphics Service
# ---------------------------------------------------------------------------

class MotionGraphicsService:
    """
    Motion graphics generation using FFmpeg per §7.1.8 and Table 6-6.

    Provides Ken Burns (L2) and pan/zoom (L3) effects for the fallback
    chain. Takes a static image and produces a short video clip with
    cinematic motion.

    FFmpeg filter chains:
    - Ken Burns: zoompan with smooth zoom progression + gentle pan
    - Pan/Zoom: simpler zoompan with linear horizontal/vertical motion

    Dependencies:
    - FFmpeg binary available in PATH
    - SeaweedFS filer for input image retrieval and output storage
    - Sufficient disk space for temporary files
    """

    def __init__(
        self,
        seaweedfs_filer_url: str = "http://node-01:8888",
        ffmpeg_binary: str = "ffmpeg",
        temp_dir: str = "/tmp/ivgs_motion",
    ) -> None:
        """
        Initialize motion graphics service.

        Args:
            seaweedfs_filer_url: SeaweedFS filer URL for file I/O.
            ffmpeg_binary: Path to FFmpeg binary.
            temp_dir: Directory for temporary processing files.
        """
        self._seaweedfs_filer_url = seaweedfs_filer_url
        self._ffmpeg_binary = ffmpeg_binary
        self._temp_dir = temp_dir
        self._http_client: httpx.AsyncClient | None = None
        self._log = logger.bind(service="motion_graphics")

        os.makedirs(temp_dir, exist_ok=True)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ------------------------------------------------------------------
    # Ken Burns (L2 Fallback)
    # ------------------------------------------------------------------

    async def apply_ken_burns(
        self,
        *,
        image_asset_id: str,
        job_id: str,
        scene_id: str,
        duration_seconds: float = DEFAULT_DURATION_SECONDS,
        config: MotionGraphicsConfig | None = None,
    ) -> dict[str, str]:
        """
        Apply Ken Burns effect to a static image (L2 fallback per Table 6-6).

        Creates a slow zoom-in with gentle pan across the image to produce
        cinematic motion from a static source. Output is an MP4 clip.

        FFmpeg filtergraph:
          zoompan=z='min(zoom+0.0015,1.3)':d=180:s=1280x720:fps=30,
          format=yuv420p

        Args:
            image_asset_id: Source image asset UUID.
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            duration_seconds: Output clip duration.
            config: Optional custom configuration.

        Returns:
            Dict with 'asset_id' and 'output_path'.

        Raises:
            RuntimeError: If FFmpeg processing fails.
        """
        cfg = config or MotionGraphicsConfig(
            duration_seconds=duration_seconds,
        )

        total_frames = int(cfg.duration_seconds * cfg.fps)
        zoom_increment = (cfg.zoom_end - cfg.zoom_start) / total_frames

        # Retrieve source image from SeaweedFS
        image_path = await self._get_asset_storage_path(image_asset_id)
        local_input = await self._download_from_seaweedfs(image_path)

        # Generate output path
        output_filename = f"ken_burns_{scene_id}_{uuid.uuid4().hex[:8]}.mp4"
        local_output = os.path.join(self._temp_dir, output_filename)

        # Build FFmpeg command
        zoompan_filter = (
            f"zoompan="
            f"z='min(zoom+{zoom_increment:.6f},{cfg.zoom_end})':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)+((iw/zoom/2)*sin(on/{total_frames}*PI/4))':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={cfg.output_width}x{cfg.output_height}:"
            f"fps={cfg.fps},"
            f"format=yuv420p"
        )

        cmd = [
            self._ffmpeg_binary,
            "-y",
            "-i", local_input,
            "-vf", zoompan_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-movflags", "+faststart",
            "-t", str(cfg.duration_seconds),
            local_output,
        ]

        self._log.info(
            "ken_burns_processing",
            image_asset_id=image_asset_id,
            job_id=job_id,
            scene_id=scene_id,
            duration_seconds=cfg.duration_seconds,
            total_frames=total_frames,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=300.0
            )

            if process.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg Ken Burns failed (exit {process.returncode}): "
                    f"{stderr.decode('utf-8', errors='replace')[:500]}"
                )

            # Upload to SeaweedFS
            seaweedfs_path = (
                f"/ivgs/animations/{job_id}/{scene_id}/{output_filename}"
            )
            await self._upload_to_seaweedfs(local_output, seaweedfs_path)

            # Get file size
            file_size = os.path.getsize(local_output)

            # Register asset in database
            asset_id = await self._register_asset(
                job_id=job_id,
                scene_id=scene_id,
                asset_type="animation",
                storage_path=seaweedfs_path,
                file_size_bytes=file_size,
                metadata={
                    "effect": "ken_burns",
                    "source_image_id": image_asset_id,
                    "duration_seconds": cfg.duration_seconds,
                    "resolution": f"{cfg.output_width}x{cfg.output_height}",
                },
            )

            self._log.info(
                "ken_burns_completed",
                asset_id=asset_id,
                output_path=seaweedfs_path,
                file_size_bytes=file_size,
            )

            return {"asset_id": asset_id, "output_path": seaweedfs_path}

        finally:
            # Cleanup temp files
            for path in [local_input, local_output]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Pan/Zoom (L3 Fallback)
    # ------------------------------------------------------------------

    async def apply_zoom_pan(
        self,
        *,
        image_asset_id: str,
        job_id: str,
        scene_id: str,
        duration_seconds: float = DEFAULT_DURATION_SECONDS,
        config: MotionGraphicsConfig | None = None,
    ) -> dict[str, str]:
        """
        Apply simple pan/zoom effect (L3 fallback per Table 6-6).

        Simpler than Ken Burns — linear horizontal pan with slight zoom.
        Less cinematic but more reliable as a deeper fallback.

        FFmpeg filtergraph:
          zoompan=z='1.1':d=180:x='iw*on/180':y='0':s=1280x720:fps=30,
          format=yuv420p

        Args:
            image_asset_id: Source image asset UUID.
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            duration_seconds: Output clip duration.
            config: Optional custom configuration.

        Returns:
            Dict with 'asset_id' and 'output_path'.

        Raises:
            RuntimeError: If FFmpeg processing fails.
        """
        cfg = config or MotionGraphicsConfig(
            duration_seconds=duration_seconds,
            zoom_start=1.0,
            zoom_end=1.1,
            pan_direction="right",
        )

        total_frames = int(cfg.duration_seconds * cfg.fps)

        # Retrieve source image
        image_path = await self._get_asset_storage_path(image_asset_id)
        local_input = await self._download_from_seaweedfs(image_path)

        output_filename = f"zoom_pan_{scene_id}_{uuid.uuid4().hex[:8]}.mp4"
        local_output = os.path.join(self._temp_dir, output_filename)

        # Pan direction mapping
        pan_expressions = {
            "right": f"x='iw*on/{total_frames}':y='0'",
            "left": f"x='iw*(1-on/{total_frames})':y='0'",
            "down": f"x='0':y='ih*on/{total_frames}'",
            "up": f"x='0':y='ih*(1-on/{total_frames})'",
        }
        pan_expr = pan_expressions.get(
            cfg.pan_direction,
            pan_expressions["right"],
        )

        zoompan_filter = (
            f"zoompan="
            f"z='{cfg.zoom_end}':"
            f"d={total_frames}:"
            f"{pan_expr}:"
            f"s={cfg.output_width}x{cfg.output_height}:"
            f"fps={cfg.fps},"
            f"format=yuv420p"
        )

        cmd = [
            self._ffmpeg_binary,
            "-y",
            "-i", local_input,
            "-vf", zoompan_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-movflags", "+faststart",
            "-t", str(cfg.duration_seconds),
            local_output,
        ]

        self._log.info(
            "zoom_pan_processing",
            image_asset_id=image_asset_id,
            job_id=job_id,
            scene_id=scene_id,
            pan_direction=cfg.pan_direction,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=300.0
            )

            if process.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg zoom/pan failed (exit {process.returncode}): "
                    f"{stderr.decode('utf-8', errors='replace')[:500]}"
                )

            seaweedfs_path = (
                f"/ivgs/animations/{job_id}/{scene_id}/{output_filename}"
            )
            await self._upload_to_seaweedfs(local_output, seaweedfs_path)

            file_size = os.path.getsize(local_output)

            asset_id = await self._register_asset(
                job_id=job_id,
                scene_id=scene_id,
                asset_type="animation",
                storage_path=seaweedfs_path,
                file_size_bytes=file_size,
                metadata={
                    "effect": "zoom_pan",
                    "source_image_id": image_asset_id,
                    "duration_seconds": cfg.duration_seconds,
                    "pan_direction": cfg.pan_direction,
                    "resolution": f"{cfg.output_width}x{cfg.output_height}",
                },
            )

            self._log.info(
                "zoom_pan_completed",
                asset_id=asset_id,
                output_path=seaweedfs_path,
                file_size_bytes=file_size,
            )

            return {"asset_id": asset_id, "output_path": seaweedfs_path}

        finally:
            for path in [local_input, local_output]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # SeaweedFS I/O Helpers
    # ------------------------------------------------------------------

    async def _download_from_seaweedfs(self, storage_path: str) -> str:
        """
        Download a file from SeaweedFS to a local temp path.

        Args:
            storage_path: SeaweedFS file path.

        Returns:
            Local filesystem path to the downloaded file.

        Raises:
            RuntimeError: If download fails.
        """
        client = await self._get_client()
        local_path = os.path.join(
            self._temp_dir,
            f"input_{uuid.uuid4().hex[:8]}{os.path.splitext(storage_path)[1]}",
        )

        response = await client.get(
            f"{self._seaweedfs_filer_url}{storage_path}"
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"SeaweedFS download failed ({response.status_code}): "
                f"{storage_path}"
            )

        with open(local_path, "wb") as f:
            f.write(response.content)

        return local_path

    async def _upload_to_seaweedfs(
        self,
        local_path: str,
        storage_path: str,
    ) -> None:
        """
        Upload a local file to SeaweedFS.

        Args:
            local_path: Local filesystem path.
            storage_path: Target SeaweedFS path.

        Raises:
            RuntimeError: If upload fails.
        """
        client = await self._get_client()

        with open(local_path, "rb") as f:
            response = await client.post(
                f"{self._seaweedfs_filer_url}{storage_path}",
                content=f.read(),
                headers={"Content-Type": "video/mp4"},
            )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"SeaweedFS upload failed ({response.status_code}): "
                f"{storage_path}"
            )

    async def _get_asset_storage_path(self, asset_id: str) -> str:
        """
        Look up an asset's storage_path from the database.

        Args:
            asset_id: Asset UUID.

        Returns:
            SeaweedFS storage path string.

        Raises:
            ValueError: If asset not found.
        """
        # Import here to avoid circular dependency
        from ivgs_api.app.models import Asset
        from sqlalchemy import select

        # Use a lightweight query approach
        async with self._get_db_session() as session:
            result = await session.execute(
                select(Asset.__table__.c.storage_path).where(
                    Asset.__table__.c.id == asset_id
                )
            )
            row = result.fetchone()

        if row is None or not row[0]:
            raise ValueError(f"Asset not found or no storage path: {asset_id}")

        return str(row[0])

    async def _get_db_session(self) -> Any:
        """
        Placeholder for database session acquisition.

        In production, this would use the shared db_session_factory
        passed via dependency injection.
        """
        raise NotImplementedError(
            "DB session factory must be injected — see integration notes"
        )

    async def _register_asset(
        self,
        *,
        job_id: str,
        scene_id: str,
        asset_type: str,
        storage_path: str,
        file_size_bytes: int,
        metadata: dict[str, Any],
    ) -> str:
        """
        Register a generated asset in the database.

        Creates an entry in the assets table for the motion graphics output.

        Args:
            job_id: Parent render job UUID.
            scene_id: Scene UUID.
            asset_type: Asset type (animation).
            storage_path: SeaweedFS output path.
            file_size_bytes: File size in bytes.
            metadata: Additional metadata dict.

        Returns:
            Generated asset UUID.
        """
        asset_id = str(uuid.uuid4())

        async with self._get_db_session() as session:
            async with session.begin():
                from sqlalchemy import text

                await session.execute(
                    text(
                        "INSERT INTO assets "
                        "(id, project_id, scene_id, asset_type, "
                        "storage_path, file_size_bytes, metadata, "
                        "status, created_at) "
                        "VALUES (:id, "
                        "(SELECT project_id FROM render_jobs WHERE id = :job_id), "
                        ":scene_id, :asset_type, :storage_path, "
                        ":file_size, :metadata, 'generated', NOW())"
                    ),
                    {
                        "id": asset_id,
                        "job_id": job_id,
                        "scene_id": scene_id,
                        "asset_type": asset_type,
                        "storage_path": storage_path,
                        "file_size": file_size_bytes,
                        "metadata": str(metadata),
                    },
                )

        return asset_id
