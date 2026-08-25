"""
Preset service — AD-09.5. Versioned bundles of choices, applied at project
creation.

THE ONE INVARIANT: a preset is never mutated. ``revise`` INSERTs a new row with
``version = max + 1`` and deactivates the previous one. Nothing in this module
UPDATEs ``payload``. That is what lets ``projects.preset_version`` mean
something a year later — an in-place edit would silently rewrite the provenance
of every project already created from it.

WHAT APPLYING ACTUALLY DOES, and what it honestly cannot do. AD-09.15
criterion 1 asks that a preset populate branding, actor, model selections and
media defaults, and that the project then render with them. Three of those four
have a consuming code path today and are really written:

  * model selections -> ``project_model_selections`` via
    ``model_selection.manual_override``, which the pipeline reads.
  * actor -> the actor's reference clip is REFERENCED into the project and
    bound as ``projects.talking_head_asset_id``, which Stage 6 reads.
  * media defaults / runtime / audience -> project columns and the payload the
    scene-creation surface seeds from.

Branding is the fourth and it has NO consuming code path. WP-56 Task 3 stopped
on the finding that the presenter/logo overlay chain is broken at three of its
four links (WP-56 report, Task 3). ``apply`` therefore returns branding under
``recorded_not_applied`` rather than counting it as applied. A preset apply that
reports plain success while silently skipping half the bundle is the AD-09.3
stub family — a green surface over an empty action — and this package does not
add a ninth instance to it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.preset import Preset
from app.models.project import Project
from app.services import model_selection
from app.services.library_service import LibraryError, LibraryService
from shared.models.model_store import ModelStage, ModelTier

logger = logging.getLogger(__name__)


class PresetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -- reads ----------------------------------------------------------

    async def list_presets(
        self,
        *,
        owner_scope: Optional[str] = None,
        active_only: bool = True,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[Sequence[Preset], int]:
        conditions = []
        if owner_scope:
            conditions.append(Preset.owner_scope == owner_scope)
        if active_only:
            conditions.append(Preset.is_active.is_(True))
        total = await self.db.scalar(
            select(func.count()).select_from(Preset).where(*conditions)
        )
        rows = await self.db.execute(
            select(Preset).where(*conditions)
            .order_by(Preset.name.asc(), Preset.version.desc())
            .offset((page - 1) * per_page).limit(per_page)
        )
        return rows.scalars().all(), int(total or 0)

    async def get_preset(self, preset_id: UUID) -> Optional[Preset]:
        return await self.db.get(Preset, preset_id)

    async def list_versions(self, name: str) -> Sequence[Preset]:
        """Every version of one preset, newest first. This is the provenance
        view: a project pinned to version 2 must stay inspectable after version
        5 is the active one."""
        rows = await self.db.execute(
            select(Preset).where(Preset.name == name)
            .order_by(Preset.version.desc())
        )
        return rows.scalars().all()

    # -- writes ---------------------------------------------------------

    async def create_preset(
        self,
        *,
        name: str,
        description: Optional[str],
        payload: dict[str, Any],
        owner_scope: str = "user",
        created_by: Optional[UUID] = None,
    ) -> Preset:
        name = (name or "").strip()
        if not name:
            raise LibraryError("name is required")
        existing = await self.db.scalar(
            select(Preset).where(Preset.name == name).limit(1)
        )
        if existing is not None:
            raise LibraryError(
                f"A preset named {name!r} already exists (version "
                f"{existing.version}). Create a new VERSION of it instead of a "
                "second preset with the same name."
            )
        await self._validate_payload(payload)
        preset = Preset(
            name=name,
            description=description,
            version=1,
            payload=payload,
            is_active=True,
            owner_scope=owner_scope,
            created_by=created_by,
        )
        self.db.add(preset)
        await self.db.commit()
        await self.db.refresh(preset)
        logger.info("preset_created: id=%s name=%s v1", preset.id, name)
        return preset

    async def revise(
        self,
        *,
        name: str,
        description: Optional[str],
        payload: dict[str, Any],
        created_by: Optional[UUID] = None,
    ) -> Preset:
        """Create the next version. The previous version is DEACTIVATED, not
        deleted — projects pinned to it keep resolving."""
        rows = await self.db.execute(
            select(Preset).where(Preset.name == name)
            .order_by(Preset.version.desc())
        )
        versions = list(rows.scalars().all())
        if not versions:
            raise LibraryError(f"No preset named {name!r}")
        await self._validate_payload(payload)

        current = versions[0]
        for v in versions:
            v.is_active = False
        new = Preset(
            name=name,
            description=description if description is not None else current.description,
            version=current.version + 1,
            payload=payload,
            is_active=True,
            owner_scope=current.owner_scope,
            created_by=created_by,
        )
        self.db.add(new)
        await self.db.commit()
        await self.db.refresh(new)
        logger.info("preset_revised: name=%s v%s -> v%s", name, current.version, new.version)
        return new

    # -- apply ----------------------------------------------------------

    async def apply_to_project(
        self, *, preset_id: UUID, project_id: UUID,
    ) -> dict[str, Any]:
        """Write a preset's concrete values into a project.

        PRESETS ARE DEFAULTS, NOT CONSTRAINTS (AD-09.5). Everything below writes
        into the PROJECT's own columns and rows. Nothing downstream re-reads the
        preset at render time, so a later revision cannot change what this
        project renders — and per-project edits after this call do not propagate
        back to the preset.

        Returns an itemised result. ``applied`` and ``recorded_not_applied`` are
        separate lists on purpose; see the module docstring.
        """
        preset = await self.db.get(Preset, preset_id)
        if preset is None:
            raise LibraryError(f"Preset {preset_id} does not exist")
        project = await self.db.get(Project, project_id)
        if project is None:
            raise LibraryError(f"Project {project_id} does not exist")

        payload = preset.payload or {}
        applied: List[str] = []
        recorded: List[str] = []

        # --- project scalars ---
        if payload.get("max_runtime_seconds") is not None:
            project.max_runtime_seconds = int(payload["max_runtime_seconds"])
            applied.append(f"max_runtime_seconds={project.max_runtime_seconds}")
        if payload.get("target_audience"):
            project.target_audience = payload["target_audience"]
            applied.append("target_audience")

        # --- actor: reference the clip in, then bind it ---
        actor_id = payload.get("actor_id")
        if actor_id:
            actor = await self.db.get(Actor, UUID(str(actor_id)))
            if actor is None:
                raise LibraryError(f"Preset names actor {actor_id}, which does not exist")
            if not actor.is_active:
                raise LibraryError(
                    f"Preset names actor {actor.name!r}, which is retired. "
                    "Revise the preset before applying it."
                )
            if actor.reference_clip_id:
                lib_service = LibraryService(self.db)
                asset = await lib_service.reference_into_project(
                    library_asset_id=actor.reference_clip_id,
                    project_id=project_id,
                    asset_type="talking_head",
                )
                project.talking_head_asset_id = asset.id
                applied.append(
                    f"actor={actor.name!r} (talking_head_asset_id={asset.id})"
                )
            else:
                # An actor with no reference clip is legitimate — which media a
                # binding needs is a property of the engine (AD-09.4.3) — but it
                # cannot become a talking-head asset, and saying so is better
                # than reporting the actor as applied.
                recorded.append(
                    f"actor={actor.name!r} has no reference_clip_id; nothing to bind"
                )

        # --- model selections (AD-01) ---
        for sel in payload.get("model_selections") or []:
            try:
                stage = ModelStage(sel["stage"])
                tier = ModelTier(sel["tier"])
            except (KeyError, ValueError) as e:
                raise LibraryError(f"Preset model_selections entry is invalid: {e}")
            # manual_override already validates that the model exists, is
            # servable and serves this stage. Not duplicated here: a preset
            # created while a model was approved and applied after it was
            # retired must fail with the CURRENT reason.
            await model_selection.manual_override(
                self.db,
                project_id=project_id,
                scene_id=None,
                stage=stage,
                tier=tier,
                model_id=UUID(str(sel["model_id"])),
                rationale=f"preset {preset.name!r} v{preset.version}",
            )
            applied.append(f"model_selection {stage.value}/{tier.value}")

        # --- media defaults: seeds for scenes that do not exist yet ---
        if payload.get("media_defaults"):
            recorded.append(
                "media_defaults recorded on the project's preset provenance; "
                "consumed when scenes are created"
            )

        # --- branding: RECORDED, NOT RENDERED ---
        if payload.get("branding"):
            recorded.append(
                "branding (logo, logo_policy, brand_colours, typography) — "
                "stored on the preset and readable, but NO render path consumes "
                "it. WP-56 Task 3 stopped on the presenter/logo chain; see the "
                "WP-56 report."
            )

        # --- provenance ---
        project.preset_id = preset.id
        project.preset_version = preset.version
        project.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        logger.info(
            "preset_applied: preset=%s v%s project=%s applied=%d recorded_only=%d",
            preset.name, preset.version, project_id, len(applied), len(recorded),
        )
        return {
            "project_id": project_id,
            "preset_id": preset.id,
            "preset_version": preset.version,
            "applied": applied,
            "recorded_not_applied": recorded,
        }

    # -- validation -----------------------------------------------------

    async def _validate_payload(self, payload: dict[str, Any]) -> None:
        """Check the FKs a preset payload carries.

        Pydantic has already checked the SHAPE. What it cannot check is that
        ``actor_id`` names a real, active actor and that a logo is a logo. A
        preset that names a deleted actor is a 422 at creation, which is where
        the operator can still fix it, rather than a failure at apply time in
        front of a project they were halfway through creating.
        """
        actor_id = payload.get("actor_id")
        if actor_id:
            actor = await self.db.get(Actor, UUID(str(actor_id)))
            if actor is None:
                raise LibraryError(f"actor_id {actor_id} does not exist")
            if not actor.is_active:
                raise LibraryError(f"actor {actor.name!r} is retired")

        branding = payload.get("branding") or {}
        logo_id = branding.get("logo_library_asset_id")
        if logo_id:
            from app.models.library_asset import LibraryAsset
            lib = await self.db.get(LibraryAsset, UUID(str(logo_id)))
            if lib is None:
                raise LibraryError(f"branding.logo_library_asset_id {logo_id} does not exist")
            if lib.kind != "logo":
                raise LibraryError(
                    f"branding.logo_library_asset_id points at a {lib.kind!r}, not a logo"
                )
        policy = branding.get("logo_policy")
        if policy is not None and policy not in ("always", "never", "per_scene"):
            raise LibraryError(
                f"branding.logo_policy must be always|never|per_scene; got {policy!r}"
            )
