"""
IVGS v5 — Composition Manifest Builder
==========================================

Builds a composition manifest from locked storyboard and generated assets
per §6.1 Stage 4 (Composition Manifest Generation).

The manifest encodes the full timeline:
- Scene boundaries
- Layer assignments (background/talking_head/lower_third/captions/audio)
- Asset references with SHA-256 checksums
- Render parameters

Manifest states:
    draft  → locked (after validation confirms all checksums match)
    locked → cannot be modified; regeneration requires a new manifest

The manifest is the single source of truth for Stages 7 (prototype) and 8 (final render).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("ivgs.services.manifest_builder")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ManifestAssetRef(BaseModel):
    """Reference to a generated asset with checksum."""
    asset_id: str
    asset_type: str  # image, video_clip, animation, audio, talking_head
    storage_path: str = ""
    content_hash: str = ""
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0


class ManifestLayerConfig(BaseModel):
    """Configuration for a composition layer."""
    layer_type: str  # background, talking_head, lower_third, caption, audio
    asset_ref: Optional[ManifestAssetRef] = None
    position: str = ""  # For talking head: bottom_right, full_screen, etc.
    scale: float = 1.0
    opacity: float = 1.0
    start_offset: float = 0.0
    duration_override: Optional[float] = None
    has_alpha: bool = False
    render_params: Dict[str, Any] = Field(default_factory=dict)


class ManifestSceneConfig(BaseModel):
    """Configuration for a single scene in the manifest."""
    scene_id: str
    scene_index: int
    scene_title: str = ""
    narration_text: str = ""
    duration_seconds: float = 10.0
    media_type: str = "image"
    layers: List[ManifestLayerConfig] = Field(default_factory=list)
    caption_timestamps: List[Dict[str, Any]] = Field(default_factory=list)
    transition_in: Optional[str] = None
    transition_out: Optional[str] = None
    transition_duration: float = 0.5


class CompositionManifest(BaseModel):
    """Full composition manifest."""
    manifest_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    language_code: str = "en-US"
    status: str = "draft"
    total_duration_seconds: float = 0.0
    scene_count: int = 0
    scenes: List[ManifestSceneConfig] = Field(default_factory=list)
    talking_head_asset: Optional[ManifestAssetRef] = None
    render_profiles: List[str] = Field(default=["draft", "1080p", "4k"])
    created_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    manifest_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ManifestBuilder
# ---------------------------------------------------------------------------

class ManifestBuilder:
    """
    Builds and validates composition manifests.

    Workflow:
    1. build_manifest() — Create draft manifest from storyboard + assets
    2. validate_manifest() — Verify all asset checksums
    3. lock_manifest() — Set status=locked, compute manifest hash
    4. save_manifest() — Persist to database via Pipeline API
    """

    def __init__(
        self,
        api_base_url: str = "",
        service_token: str = "",
    ):
        self._api_base_url = api_base_url
        self._service_token = service_token

    def build_manifest(
        self,
        project_id: str,
        language_code: str,
        scenes: List[Dict[str, Any]],
        talking_head_asset: Optional[Dict[str, Any]] = None,
    ) -> CompositionManifest:
        """
        Build a composition manifest from storyboard scenes and generated assets.

        Each scene dict should contain:
        - scene_id, scene_index, scene_title, narration_text, duration_seconds
        - media_type (image/video_clip/animation)
        - background_asset: {asset_id, storage_path, content_hash, ...}
        - audio_asset: {asset_id, storage_path, content_hash, ...} (optional)
        - caption_timestamps: [{start, end, text}, ...] (optional)
        - talking_head_position, talking_head_scale (optional)
        """
        log = logger.bind(
            project_id=project_id,
            scene_count=len(scenes),
        )

        manifest_scenes: List[ManifestSceneConfig] = []
        total_duration = 0.0

        for scene_data in sorted(scenes, key=lambda s: s.get("scene_index", 0)):
            layers: List[ManifestLayerConfig] = []

            # Background layer
            bg_asset = scene_data.get("background_asset")
            if bg_asset:
                layers.append(ManifestLayerConfig(
                    layer_type="background",
                    asset_ref=ManifestAssetRef(**bg_asset) if isinstance(bg_asset, dict) else bg_asset,
                    position="full_frame",
                ))

            # Audio layer
            audio_asset = scene_data.get("audio_asset")
            if audio_asset:
                layers.append(ManifestLayerConfig(
                    layer_type="audio",
                    asset_ref=ManifestAssetRef(**audio_asset) if isinstance(audio_asset, dict) else audio_asset,
                ))

            # Talking head layer reference (actual asset is project-level)
            if talking_head_asset:
                th_position = scene_data.get("talking_head_position", "bottom_right")
                th_scale = scene_data.get("talking_head_scale", 0.25)
                layers.append(ManifestLayerConfig(
                    layer_type="talking_head",
                    position=th_position,
                    scale=th_scale,
                ))

            # Lower third layer (rendered at compose time by Remotion)
            if scene_data.get("scene_title"):
                layers.append(ManifestLayerConfig(
                    layer_type="lower_third",
                    has_alpha=True,
                    render_params={
                        "title": scene_data.get("scene_title", ""),
                        "composition": "LowerThird",
                    },
                ))

            # Caption layer (timestamps for burn-in)
            timestamps = scene_data.get("caption_timestamps", [])
            if timestamps:
                layers.append(ManifestLayerConfig(
                    layer_type="caption",
                    render_params={"timestamps": timestamps},
                ))

            scene_duration = scene_data.get("duration_seconds", 10.0)
            manifest_scenes.append(ManifestSceneConfig(
                scene_id=scene_data["scene_id"],
                scene_index=scene_data.get("scene_index", 0),
                scene_title=scene_data.get("scene_title", ""),
                narration_text=scene_data.get("narration_text", ""),
                duration_seconds=scene_duration,
                media_type=scene_data.get("media_type", "image"),
                layers=layers,
                caption_timestamps=timestamps,
            ))

            total_duration += scene_duration

        # Build talking head asset ref
        th_ref = None
        if talking_head_asset:
            th_ref = ManifestAssetRef(
                **talking_head_asset
            ) if isinstance(talking_head_asset, dict) else talking_head_asset

        manifest = CompositionManifest(
            project_id=project_id,
            language_code=language_code,
            status="draft",
            total_duration_seconds=total_duration,
            scene_count=len(manifest_scenes),
            scenes=manifest_scenes,
            talking_head_asset=th_ref,
            created_at=datetime.now(timezone.utc),
        )

        log.info(
            "manifest_built",
            manifest_id=manifest.manifest_id,
            total_duration=total_duration,
            scene_count=len(manifest_scenes),
        )

        return manifest

    def validate_manifest(
        self,
        manifest: CompositionManifest,
        asset_checksums: Dict[str, str],
    ) -> List[str]:
        """
        Validate manifest: verify all asset checksums match.

        Returns list of validation errors (empty = valid).
        """
        errors: List[str] = []

        for scene in manifest.scenes:
            for layer in scene.layers:
                if layer.asset_ref and layer.asset_ref.content_hash:
                    expected = asset_checksums.get(layer.asset_ref.asset_id)
                    if expected and expected != layer.asset_ref.content_hash:
                        errors.append(
                            f"Scene {scene.scene_id}, layer {layer.layer_type}: "
                            f"checksum mismatch for asset {layer.asset_ref.asset_id}"
                        )

        if manifest.talking_head_asset and manifest.talking_head_asset.content_hash:
            expected = asset_checksums.get(manifest.talking_head_asset.asset_id)
            if expected and expected != manifest.talking_head_asset.content_hash:
                errors.append(
                    f"Talking head asset checksum mismatch: "
                    f"{manifest.talking_head_asset.asset_id}"
                )

        return errors

    def lock_manifest(
        self,
        manifest: CompositionManifest,
    ) -> CompositionManifest:
        """Lock the manifest: set status=locked and compute manifest hash."""
        manifest.status = "locked"
        manifest.locked_at = datetime.now(timezone.utc)

        # Compute manifest content hash
        content = manifest.model_dump_json(exclude={"manifest_hash", "locked_at"})
        manifest.manifest_hash = hashlib.sha256(content.encode()).hexdigest()

        logger.info(
            "manifest_locked",
            manifest_id=manifest.manifest_id,
            manifest_hash=manifest.manifest_hash[:16],
        )

        return manifest

    async def save_manifest(
        self,
        manifest: CompositionManifest,
    ) -> Dict[str, Any]:
        """Persist manifest to database via Pipeline API."""
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bearer {self._service_token}"},
        ) as client:
            resp = await client.post(
                f"{self._api_base_url}/composition-manifests",
                json=manifest.model_dump(mode="json"),
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"Manifest save failed: HTTP {resp.status_code}"
                )
            return resp.json()
