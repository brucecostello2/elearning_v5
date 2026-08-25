"""
Library service — AD-09.4.2 asset library, with reference-don't-copy and
upload-on-use.

TWO RULES THIS MODULE EXISTS TO ENFORCE.

**Reference, don't copy.** ``reference_into_project`` creates an ``assets`` row
that points at the SAME SeaweedFS object and records ``library_asset_id``. It
never re-uploads bytes. That is what makes a logo swap across a finished course
a reference change (AD-09.8 fork depth) rather than a re-upload, and it is the
direct answer to ledger B3 duplicate-asset accumulation.

**Upload-on-use.** Media uploaded through the project surface can be written to
the library at the same time, ``owner_scope='user'`` by default, with a
promote-to-global admin action. It is OPT-IN per call and the GUI is the only
caller that opts in: worker-generated media must never enter the library, and
``AssetService.upload_asset`` is the route every media task in the fleet uses.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.library_asset import LibraryAsset
from shared.models.asset import Asset
from shared.seaweedfs_client import seaweedfs_client

logger = logging.getLogger(__name__)

# SeaweedFS directory routing for library media. Deliberately a SIBLING of
# `AssetService.ASSET_TYPE_PATHS` and not a reuse of it: library assets are not
# project-scoped, so they have no `/{project_id}/` path segment to slot into.
LIBRARY_KIND_PATHS = {
    "logo": "/ivgs/library/logos",
    "video_clip": "/ivgs/library/video",
    "audio_clip": "/ivgs/library/audio",
    "music_bed": "/ivgs/library/music",
    "reference_clip": "/ivgs/library/reference-clips",
    "reference_image": "/ivgs/library/reference-images",
    "font": "/ivgs/library/fonts",
    "document": "/ivgs/library/documents",
}

MAX_LIBRARY_FILE_SIZES = {
    "logo": 25 * 1024 * 1024,
    "video_clip": 2 * 1024 * 1024 * 1024,
    "audio_clip": 500 * 1024 * 1024,
    "music_bed": 500 * 1024 * 1024,
    "reference_clip": 2 * 1024 * 1024 * 1024,
    "reference_image": 50 * 1024 * 1024,
    "font": 25 * 1024 * 1024,
    "document": 100 * 1024 * 1024,
}

# Which project-side `assets.asset_type` a library kind may be referenced as.
# The two vocabularies are DIFFERENT and this map is the only place they meet.
# `assets.asset_type` is a PostgreSQL ENUM with seven values; sending it a
# library kind it does not know is a database error at INSERT, which is a worse
# way to find out than a 400 here.
KIND_TO_ASSET_TYPE = {
    "logo": {"image"},
    "video_clip": {"video"},
    "audio_clip": {"audio"},
    "music_bed": {"audio"},
    "reference_clip": {"reference_clip", "video", "talking_head"},
    "reference_image": {"image"},
    "font": {"document"},
    "document": {"document"},
}


class LibraryError(ValueError):
    """Caller error — surfaced as a 400/409, never a 500."""


class LibraryService:
    """Business logic for `library_assets`."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -- reads ----------------------------------------------------------

    async def list_assets(
        self,
        *,
        kind: Optional[str] = None,
        owner_scope: Optional[str] = None,
        search: Optional[str] = None,
        include_superseded: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[Sequence[LibraryAsset], int]:
        """List library assets, newest first.

        Superseded assets are EXCLUDED by default. They are never deleted
        (AD-09.4.2) precisely so historical projects stay resolvable, but a
        browser that lists them presents retired branding as a live choice.
        """
        conditions = []
        if kind:
            conditions.append(LibraryAsset.kind == kind)
        if owner_scope:
            conditions.append(LibraryAsset.owner_scope == owner_scope)
        if not include_superseded:
            conditions.append(LibraryAsset.superseded_by.is_(None))
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                or_(LibraryAsset.name.ilike(like), LibraryAsset.description.ilike(like))
            )

        total = await self.db.scalar(
            select(func.count()).select_from(LibraryAsset).where(*conditions)
        )
        rows = await self.db.execute(
            select(LibraryAsset)
            .where(*conditions)
            .order_by(LibraryAsset.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return rows.scalars().all(), int(total or 0)

    async def get_asset(self, asset_id: UUID) -> Optional[LibraryAsset]:
        return await self.db.get(LibraryAsset, asset_id)

    # -- writes ---------------------------------------------------------

    async def upload_asset(
        self,
        *,
        kind: str,
        name: str,
        file_content: bytes,
        filename: str,
        content_type: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        owner_scope: str = "user",
        created_by: Optional[UUID] = None,
        duration_seconds: Optional[float] = None,
    ) -> Tuple[LibraryAsset, bool]:
        """Store bytes in SeaweedFS and create a library row.

        Returns ``(asset, was_deduplicated)``. Dedup is on
        ``(content_hash, owner_scope)`` and matches the partial unique index
        ``uq_library_assets_hash_scope`` in migration 0030 — the same bytes
        uploaded twice into the same scope resolve to the existing row rather
        than accumulating copies. Scope is part of the key because a global
        asset and a user's own copy of it are different facts about ownership
        even when the bytes are identical.
        """
        if kind not in LIBRARY_KIND_PATHS:
            raise LibraryError(
                f"Invalid kind {kind!r}. Valid: {sorted(LIBRARY_KIND_PATHS)}"
            )
        if owner_scope not in ("global", "user"):
            raise LibraryError(f"Invalid owner_scope {owner_scope!r}")
        if not name or not name.strip():
            raise LibraryError("name is required")

        max_size = MAX_LIBRARY_FILE_SIZES.get(kind, 100 * 1024 * 1024)
        if len(file_content) > max_size:
            raise LibraryError(
                f"File too large: {len(file_content)} bytes. "
                f"Maximum for {kind}: {max_size} bytes"
            )

        content_hash = hashlib.sha256(file_content).hexdigest()

        existing = await self.db.scalar(
            select(LibraryAsset).where(
                LibraryAsset.content_hash == content_hash,
                LibraryAsset.owner_scope == owner_scope,
                LibraryAsset.superseded_by.is_(None),
            ).limit(1)
        )
        if existing is not None:
            logger.info(
                "library_asset_deduplicated: hash=%s... existing_id=%s scope=%s",
                content_hash[:16], existing.id, owner_scope,
            )
            return existing, True

        fid = await seaweedfs_client.upload_file(
            file_data=file_content,
            collection="hot",
            filename=filename,
        ) or ""

        asset = LibraryAsset(
            kind=kind,
            name=name.strip(),
            description=description,
            seaweedfs_fid=fid,
            seaweedfs_path=f"{LIBRARY_KIND_PATHS[kind]}/{filename}",
            mime_type=content_type,
            file_size_bytes=len(file_content),
            duration_seconds=duration_seconds,
            content_hash=content_hash,
            tags=tags,
            owner_scope=owner_scope,
            created_by=created_by,
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        logger.info(
            "library_asset_uploaded: id=%s kind=%s scope=%s size=%s",
            asset.id, kind, owner_scope, len(file_content),
        )
        return asset, False

    async def update_metadata(
        self,
        asset_id: UUID,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[LibraryAsset]:
        """Metadata-only edit. The BYTES of a library asset are immutable.

        Replacing the file is ``supersede``, not an update: projects already
        referencing this row must keep resolving to the bytes they were built
        against.
        """
        asset = await self.db.get(LibraryAsset, asset_id)
        if asset is None:
            return None
        if name is not None:
            asset.name = name.strip()
        if description is not None:
            asset.description = description
        if tags is not None:
            asset.tags = tags
        asset.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def supersede(
        self, asset_id: UUID, replacement_id: UUID,
    ) -> Optional[LibraryAsset]:
        """Retire ``asset_id`` in favour of ``replacement_id``.

        This is the ONLY retirement path. There is no hard delete: AD-09.4.2
        rules library assets are never hard-deleted while referenced, and
        ``assets.library_asset_id`` means "referenced" includes every project
        ever built from it.
        """
        asset = await self.db.get(LibraryAsset, asset_id)
        if asset is None:
            return None
        if asset_id == replacement_id:
            raise LibraryError("An asset cannot supersede itself")
        replacement = await self.db.get(LibraryAsset, replacement_id)
        if replacement is None:
            raise LibraryError(f"Replacement {replacement_id} does not exist")
        if replacement.superseded_by is not None:
            raise LibraryError(
                "Replacement is itself superseded — point at the current asset"
            )
        if replacement.kind != asset.kind:
            raise LibraryError(
                f"Kind mismatch: cannot supersede a {asset.kind} with a "
                f"{replacement.kind}"
            )
        asset.superseded_by = replacement_id
        asset.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def promote_to_global(self, asset_id: UUID) -> Optional[LibraryAsset]:
        """Admin action — AD-09.4.2. `global` is admin-mutable only; the RBAC
        check lives on the route."""
        asset = await self.db.get(LibraryAsset, asset_id)
        if asset is None:
            return None
        if asset.owner_scope == "global":
            return asset
        clash = await self.db.scalar(
            select(LibraryAsset).where(
                LibraryAsset.content_hash == asset.content_hash,
                LibraryAsset.owner_scope == "global",
                LibraryAsset.superseded_by.is_(None),
            ).limit(1)
        )
        if clash is not None:
            # The partial unique index would raise here anyway. Catching it
            # first turns a 500 into an actionable 409.
            raise LibraryError(
                f"These bytes are already in the global library as {clash.id} "
                f"({clash.name!r})"
            )
        asset.owner_scope = "global"
        asset.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    # -- the seam: library -> project -----------------------------------

    async def reference_into_project(
        self,
        *,
        library_asset_id: UUID,
        project_id: UUID,
        asset_type: str,
        scene_id: Optional[UUID] = None,
        language_code: Optional[str] = None,
    ) -> Asset:
        """AD-09.4.2 REFERENCE-DON'T-COPY.

        Creates an ``assets`` row pointing at the library asset's EXISTING
        SeaweedFS object. No bytes are read, moved or re-uploaded, so this is
        O(1) in file size — which is the point when the asset is a 2 GB
        reference clip.

        ``reference_count`` is left at its default of 1 on the new row. The
        project asset is a distinct row with its own lifecycle; the shared
        object's fan-out is expressed by ``library_asset_id``, and conflating
        the two counters would make a project deletion look like a library
        de-reference.
        """
        lib = await self.db.get(LibraryAsset, library_asset_id)
        if lib is None:
            raise LibraryError(f"Library asset {library_asset_id} does not exist")
        if lib.superseded_by is not None:
            raise LibraryError(
                f"Library asset {library_asset_id} is superseded by "
                f"{lib.superseded_by} — reference the current one"
            )
        allowed = KIND_TO_ASSET_TYPE.get(lib.kind, set())
        if asset_type not in allowed:
            raise LibraryError(
                f"A library {lib.kind!r} cannot be referenced as asset_type "
                f"{asset_type!r}. Allowed: {sorted(allowed)}"
            )

        # Idempotent: referencing the same library asset into the same project
        # scope twice returns the existing row. The GUI's "use this" button is
        # exactly the kind of control that gets double-clicked.
        existing = await self.db.scalar(
            select(Asset).where(
                Asset.project_id == project_id,
                Asset.library_asset_id == library_asset_id,
                Asset.asset_type == asset_type,
                (Asset.scene_id == scene_id if scene_id is not None
                 else Asset.scene_id.is_(None)),
                Asset.storage_tier != "deleted",
            ).limit(1)
        )
        if existing is not None:
            return existing

        asset = Asset(
            project_id=project_id,
            scene_id=scene_id,
            asset_type=asset_type,
            seaweedfs_fid=lib.seaweedfs_fid,
            seaweedfs_path=lib.seaweedfs_path,
            mime_type=lib.mime_type,
            file_size_bytes=lib.file_size_bytes,
            duration_seconds=lib.duration_seconds,
            language_code=language_code,
            content_hash=lib.content_hash,
            library_asset_id=lib.id,
            storage_tier="hot",
            # A referenced library asset must not be tiered out from under the
            # projects that point at it. RetentionService keys on this flag.
            preserve_flag=True,
            last_accessed_at=datetime.now(timezone.utc),
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        logger.info(
            "library_asset_referenced: library_id=%s project=%s asset_id=%s type=%s",
            lib.id, project_id, asset.id, asset_type,
        )
        return asset


class ActorService:
    """Business logic for `actors` — AD-09.4.3."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_actors(
        self,
        *,
        owner_scope: Optional[str] = None,
        include_inactive: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[Sequence[Actor], int]:
        conditions = []
        if owner_scope:
            conditions.append(Actor.owner_scope == owner_scope)
        if not include_inactive:
            conditions.append(Actor.is_active.is_(True))
        total = await self.db.scalar(
            select(func.count()).select_from(Actor).where(*conditions)
        )
        rows = await self.db.execute(
            select(Actor).where(*conditions).order_by(Actor.name.asc())
            .offset((page - 1) * per_page).limit(per_page)
        )
        return rows.scalars().all(), int(total or 0)

    async def get_actor(self, actor_id: UUID) -> Optional[Actor]:
        return await self.db.get(Actor, actor_id)

    async def create_actor(self, data: dict[str, Any], created_by: Optional[UUID]) -> Actor:
        await self._validate_references(data)
        name = (data.get("name") or "").strip()
        if not name:
            raise LibraryError("name is required")
        scope = data.get("owner_scope", "user")
        clash = await self.db.scalar(
            select(Actor).where(
                Actor.name == name,
                Actor.owner_scope == scope,
                Actor.is_active.is_(True),
            ).limit(1)
        )
        if clash is not None:
            raise LibraryError(
                f"An active actor named {name!r} already exists in the "
                f"{scope} scope ({clash.id})"
            )
        actor = Actor(
            name=name,
            description=data.get("description"),
            reference_clip_id=data.get("reference_clip_id"),
            reference_image_id=data.get("reference_image_id"),
            voice_profile=data.get("voice_profile"),
            engine_bindings=data.get("engine_bindings"),
            default_orientation=data.get("default_orientation") or "landscape",
            certified_model_id=data.get("certified_model_id"),
            owner_scope=scope,
            created_by=created_by,
        )
        self.db.add(actor)
        await self.db.commit()
        await self.db.refresh(actor)
        return actor

    async def update_actor(self, actor_id: UUID, data: dict[str, Any]) -> Optional[Actor]:
        actor = await self.db.get(Actor, actor_id)
        if actor is None:
            return None
        await self._validate_references(data)
        for field in (
            "name", "description", "reference_clip_id", "reference_image_id",
            "voice_profile", "engine_bindings", "default_orientation",
            "certified_model_id", "is_active",
        ):
            if field in data and data[field] is not None:
                setattr(actor, field, data[field].strip() if field == "name" else data[field])
        actor.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(actor)
        return actor

    async def _validate_references(self, data: dict[str, Any]) -> None:
        """Reject FKs that point at nothing, or at the wrong KIND of thing.

        The database's foreign keys catch a missing row; they cannot catch a
        reference_clip_id that points at a font. Both are operator mistakes and
        both must be a 400 with the reason, not a silent identity that never
        reproduces.
        """
        for field, wanted in (
            ("reference_clip_id", {"reference_clip", "video_clip"}),
            ("reference_image_id", {"reference_image", "logo"}),
        ):
            ref = data.get(field)
            if ref is None:
                continue
            lib = await self.db.get(LibraryAsset, ref)
            if lib is None:
                raise LibraryError(f"{field}: library asset {ref} does not exist")
            if lib.kind not in wanted:
                raise LibraryError(
                    f"{field}: library asset {ref} is kind {lib.kind!r}; "
                    f"expected one of {sorted(wanted)}"
                )
            if lib.superseded_by is not None:
                raise LibraryError(
                    f"{field}: library asset {ref} is superseded — an actor "
                    "must be bound to current reference media"
                )
