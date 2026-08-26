"""
Asset service: SeaweedFS upload, metadata management, download proxy, deduplication.

Per §5.1.5, §10.1–10.4:
- Upload to SeaweedFS with collection routing based on asset type
- SHA-256 deduplication (§10.4)
- Storage tier assignment (default: hot)
- Download proxy from SeaweedFS through API
"""
import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from shared.seaweedfs_client import seaweedfs_client

logger = logging.getLogger(__name__)

# SeaweedFS directory routing per §10.2
ASSET_TYPE_PATHS = {
    "image": "/ivgs/images",
    "video": "/ivgs/videos",
    "audio": "/ivgs/audio",
    "document": "/ivgs/uploads",
    "talking_head": "/ivgs/talking-heads",
    "final_render": "/ivgs/final",
    "reference_clip": "/ivgs/reference-clips",
}

# Storage tier routing based on asset type (§10.1)
# Hot tier (SSD): active generation assets
# All new uploads go to hot tier; RetentionService handles migration
INITIAL_TIER = "hot"

# Maximum file sizes per type
MAX_FILE_SIZES = {
    "image": 50 * 1024 * 1024,       # 50 MB
    "video": 2 * 1024 * 1024 * 1024,  # 2 GB
    "audio": 500 * 1024 * 1024,        # 500 MB
    "document": 100 * 1024 * 1024,     # 100 MB
    "talking_head": 500 * 1024 * 1024,  # 500 MB
    "final_render": 5 * 1024 * 1024 * 1024,  # 5 GB
    "reference_clip": 2 * 1024 * 1024 * 1024,  # 2 GB
}


class AssetService:
    """Business logic for asset management and SeaweedFS integration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_assets(
        self,
        project_id: UUID,
        scene_id: Optional[UUID] = None,
        asset_type: Optional[str] = None,
        language_code: Optional[str] = None,
        storage_tier: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Asset], int]:
        """List assets for a project with optional filters."""
        query = select(Asset).where(Asset.project_id == project_id)

        if scene_id:
            query = query.where(Asset.scene_id == scene_id)
        if asset_type:
            query = query.where(Asset.asset_type == asset_type)
        if language_code:
            query = query.where(Asset.language_code == language_code)
        if storage_tier:
            query = query.where(Asset.storage_tier == storage_tier)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(Asset.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        assets = list(result.scalars().all())

        return assets, total

    async def get_asset(self, asset_id: UUID) -> Optional[Asset]:
        """Get asset metadata by ID."""
        result = await self.db.execute(
            select(Asset).where(Asset.id == asset_id)
        )
        asset = result.scalar_one_or_none()
        if asset:
            # Update last_accessed_at for LRU tier management
            asset.last_accessed_at = datetime.now(timezone.utc)
            await self.db.commit()
        return asset

    async def find_by_hash(
        self,
        content_hash: Optional[str] = None,
        generation_params_hash: Optional[str] = None,
        any_hash: Optional[str] = None,
        project_id: Optional[UUID] = None,
        limit: int = 10,
    ) -> List[Asset]:
        """Find live assets by content hash and/or generation-parameters hash.

        WP-45 Task 1. This is the lookup behind ``GET /api/v1/assets?sha256=``,
        the route ``check_duplicate_asset`` (``ivgs-workers/utils/media_converter.py``)
        has called since it was written and which **did not exist** — ``asset_router``
        had only ``/{asset_id}`` and its children, so every dedup probe on the fleet
        404'd into a bare ``except`` and returned ``None``. Content-hash dedup was
        therefore dead for image, video, animation and audio alike (WP-46 addendum
        A5.2, ledger L-8).

        The two hashes answer different questions and both are needed:

        * ``content_hash`` — "have these exact bytes been stored before?" It is
          computed from the bytes on upload, so it can only be known *after* the
          GPU work. Stage 3 and Stage 5 dedup on it: it saves the upload, not the
          render.
        * ``generation_params_hash`` — "has this exact request been rendered
          before?" It is the caller's idempotency key over prompt/params/inputs
          and is known *before* the GPU work. Video and animation dedup on it,
          which is what makes a repeat run cost seconds instead of minutes.

        ``any_hash`` matches either column, because ``check_duplicate_asset``'s
        wire contract has one ``sha256`` parameter and its four callers put
        different kinds of hash in it. A 64-hex value colliding across the two
        columns is not a practical risk; a caller that wants precision passes the
        named parameter instead.

        Deleted-tier assets are excluded: a tombstone is not a dedup target.
        """
        conditions = []
        if content_hash:
            conditions.append(Asset.content_hash == content_hash)
        if generation_params_hash:
            conditions.append(
                Asset.generation_params_hash == generation_params_hash
            )
        if any_hash:
            conditions.append(
                or_(
                    Asset.content_hash == any_hash,
                    Asset.generation_params_hash == any_hash,
                )
            )
        if not conditions:
            return []

        query = select(Asset).where(
            and_(or_(*conditions), Asset.storage_tier != "deleted")
        )
        if project_id is not None:
            query = query.where(Asset.project_id == project_id)

        # Oldest first: the original is the canonical row to re-reference, and a
        # newest-first order would hand back a copy made by an earlier dedup miss.
        query = query.order_by(Asset.created_at.asc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def upload_asset(
        self,
        project_id: UUID,
        file_content: bytes,
        filename: str,
        content_type: str,
        asset_type: str,
        scene_id: Optional[UUID] = None,
        language_code: Optional[str] = None,
        claimed_content_hash: Optional[str] = None,
        generation_params_hash: Optional[str] = None,
        generation_metadata: Optional[Dict[str, Any]] = None,
        library_kind: Optional[str] = None,
        library_name: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> Tuple[Asset, bool]:
        """
        Upload an asset to SeaweedFS and create metadata record.

        Returns ``(asset, was_deduplicated)``.

        Implements deduplication via SHA-256 hash (§10.4):
        - If a completed asset with the same hash exists, increment reference_count
          and return existing asset reference.
        - Otherwise, upload to SeaweedFS and create new record.

        WP-45 Task 1: ``claimed_content_hash``, ``generation_params_hash`` and
        ``generation_metadata`` are the three fields every media task in the fleet
        has always sent and this route has always discarded — FastAPI drops unknown
        form fields silently, so the workers' provenance and idempotency keys went
        nowhere and no caller could tell (WP-46 addendum A5.2 / ledger L-7).

        ``claimed_content_hash`` is **verified, not trusted**: it is a claim about
        the bytes that arrived, and the server hashes those bytes itself. A
        mismatch means the upload was corrupted in transit and raises, because the
        alternative — storing bytes under a hash that is not theirs — poisons every
        future dedup lookup with a row that can never be found by its real content.
        ``generation_params_hash`` is a caller-owned idempotency key over inputs the
        server never sees, so it is stored as given.

        WP-56 Task 2 — AD-09.4.2 UPLOAD-ON-USE. Passing ``library_kind`` also
        writes the media into the asset library (``owner_scope='user'``) and
        links this row to it via ``library_asset_id``, so media supplied during
        project creation becomes reusable without a second upload.

        IT IS OPT-IN AND MUST STAY OPT-IN. Every media task in the fleet uploads
        through this method; defaulting it on would pour generated frames,
        per-scene audio and talking-head renders into the library at a rate no
        retention policy governs (AD-09.14 open question 7 — library retention
        and quota — is unanswered). The GUI is the only caller that passes it,
        and no worker sends the field.
        """
        # Validate asset type
        if asset_type not in ASSET_TYPE_PATHS:
            raise ValueError(f"Invalid asset_type '{asset_type}'. Valid: {list(ASSET_TYPE_PATHS.keys())}")

        # Validate file size
        max_size = MAX_FILE_SIZES.get(asset_type, 100 * 1024 * 1024)
        if len(file_content) > max_size:
            raise ValueError(
                f"File too large: {len(file_content)} bytes. "
                f"Maximum for {asset_type}: {max_size} bytes"
            )

        # Compute SHA-256 hash for deduplication
        content_hash = hashlib.sha256(file_content).hexdigest()

        if generation_params_hash is not None:
            generation_params_hash = generation_params_hash.strip() or None

        if claimed_content_hash:
            claimed = claimed_content_hash.strip().lower()
            if len(claimed) != 64 or any(c not in "0123456789abcdef" for c in claimed):
                raise ValueError(
                    f"content_hash must be 64 lowercase hex characters; got "
                    f"{len(claimed_content_hash)} characters"
                )
            if claimed != content_hash:
                if generation_params_hash is None:
                    # PRE-WP-45 ANIMATION CALLER. Compatibility, with a shelf
                    # life, and it is not a guess.
                    #
                    # animation_generation_task used to send its PARAMETERS hash
                    # in the content_hash field and put the real content hash in
                    # metadata. The moment this route started honouring
                    # content_hash, every animation upload from a worker still on
                    # v5.10.0 would have been rejected as corrupt - and the
                    # workers on nodes 02-05 update on a separate operator step,
                    # so that window is real rather than theoretical.
                    #
                    # A mismatch with NO generation_params_hash is unambiguous:
                    # every WP-45 caller sends the two in their own fields, so a
                    # caller that sends one hash under the wrong name and no
                    # params hash is the old animation task. The value is stored
                    # where it was always meant to go.
                    #
                    # REMOVE THIS once every node runs >= v5.11.0-apibatch. The
                    # event below is the greppable proof of when that is true:
                    # when it stops appearing, the branch is dead.
                    logger.warning(
                        "asset_upload_legacy_hash_field: project=%s type=%s "
                        "claimed=%s computed=%s - a pre-WP-45 caller sent its "
                        "generation-parameters hash in the content_hash field. "
                        "Stored as generation_params_hash. Upgrade this node's "
                        "worker to retire this path.",
                        project_id, asset_type, claimed[:16], content_hash[:16],
                    )
                    generation_params_hash = claimed
                else:
                    raise ValueError(
                        "content_hash does not match the uploaded bytes "
                        f"(claimed {claimed[:16]}..., computed {content_hash[:16]}...). "
                        "The upload was corrupted in transit, or the caller hashed "
                        "something other than what it sent."
                    )

        # Check for existing asset with same hash (deduplication per §10.4).
        # The generation-parameters hash counts too: video and animation dedup on
        # it before they render, and a params hit means these exact bytes were
        # produced from these exact inputs already.
        dedup_conditions = [Asset.content_hash == content_hash]
        if generation_params_hash:
            dedup_conditions.append(
                Asset.generation_params_hash == generation_params_hash
            )
        existing = await self.db.execute(
            select(Asset).where(
                and_(
                    or_(*dedup_conditions),
                    Asset.project_id == project_id,
                    Asset.storage_tier != "deleted",
                )
            ).order_by(Asset.created_at.asc()).limit(1)
        )
        existing_asset = existing.scalar_one_or_none()

        if existing_asset:
            # Deduplication: increment reference_count, don't re-upload
            existing_asset.reference_count += 1
            existing_asset.last_accessed_at = datetime.now(timezone.utc)
            # Backfill the keys the original row was uploaded without, so an
            # asset stored before this fix becomes findable by params hash the
            # first time it is re-uploaded rather than staying invisible forever.
            if generation_params_hash and not existing_asset.generation_params_hash:
                existing_asset.generation_params_hash = generation_params_hash
            if generation_metadata and not existing_asset.generation_metadata:
                existing_asset.generation_metadata = generation_metadata
            await self.db.commit()
            await self.db.refresh(existing_asset)
            logger.info(
                f"Asset deduplicated: hash={content_hash[:16]}... "
                f"existing_id={existing_asset.id} ref_count={existing_asset.reference_count}"
            )
            return existing_asset, True

        # Build SeaweedFS path
        base_path = ASSET_TYPE_PATHS[asset_type]
        seaweedfs_path = f"{base_path}/{project_id}/{filename}"

        # Upload to SeaweedFS
        seaweedfs_fid = await seaweedfs_client.upload_file(
            file_data=file_content,
            collection=INITIAL_TIER,
            filename=filename,
        ) or ""

        # Create asset record
        asset = Asset(
            project_id=project_id,
            scene_id=scene_id,
            asset_type=asset_type,
            seaweedfs_fid=seaweedfs_fid,
            seaweedfs_path=seaweedfs_path,
            mime_type=content_type,
            file_size_bytes=len(file_content),
            language_code=language_code,
            content_hash=content_hash,
            generation_params_hash=generation_params_hash,
            generation_metadata=generation_metadata,
            storage_tier=INITIAL_TIER,
            last_accessed_at=datetime.now(timezone.utc),
        )
        # AD-09.4.2 upload-on-use. Written BEFORE the project asset is committed
        # so a library failure cannot leave a project row pointing at a library
        # id that was never created.
        if library_kind:
            from app.services.library_service import LibraryService
            lib_asset, _ = await LibraryService(self.db).upload_asset(
                kind=library_kind,
                name=(library_name or filename).strip(),
                file_content=file_content,
                filename=filename,
                content_type=content_type,
                owner_scope="user",
                created_by=created_by,
            )
            asset.library_asset_id = lib_asset.id
            # A project asset that IS a library reference must not be tiered out
            # from under the library entry it mirrors.
            asset.preserve_flag = True

        self.db.add(asset)
        await self.db.flush()

        superseded = await self._supersede_previous_scene_asset(asset)

        await self.db.commit()
        await self.db.refresh(asset)

        if superseded:
            logger.info(
                "Asset supersede: new=%s replaces=%s scene=%s type=%s "
                "(the previous asset is RETAINED, marked superseded)",
                asset.id, ", ".join(str(i) for i in superseded),
                asset.scene_id, asset_type,
            )

        logger.info(
            f"Asset uploaded: id={asset.id} type={asset_type} "
            f"size={len(file_content)} path={seaweedfs_path} "
            f"params_hash={(generation_params_hash or '-')[:16]} "
            f"provenance_keys={sorted(generation_metadata) if generation_metadata else []}"
        )
        return asset, False

    #: Scene-scoped media. An asset of one of these types, attached to a scene,
    #: is THE media for that scene of that type — so a new one supersedes the
    #: old one. Project-level types (reference_clip, document, final_render)
    #: are deliberately absent: they are not per-scene and a second one is a
    #: second artefact, not a replacement.
    SUPERSEDING_SCENE_ASSET_TYPES = ("image", "video", "animation", "audio")

    async def _supersede_previous_scene_asset(self, new_asset: Asset) -> List[UUID]:
        """Mark this scene's previous asset of the same type as superseded.

        WP-63 Task 7(c), the WP-45 supersede pattern. Returns the ids marked.

        WHY IT IS HERE AND NOT IN THE REGENERATION SERVICE. This is the one
        place a project asset is created, and the assets that need superseding
        arrive from a Celery worker, not from the request that asked for the
        regeneration — by the time Stage 3 uploads the new frame, the API call
        that dispatched it returned minutes ago. Keying on the arrival of the
        replacement is also what makes it correct for every route into media
        generation, including a full pipeline re-run, rather than only the
        regenerate button.

        NOTHING IS DELETED. `superseded_by` points forward to the replacement;
        the row, its bytes and its quality score all stay. That is the pattern
        WP-56 set for the library and WP-45 named as the rule: replacing bytes
        is a supersede, not an update.

        A dedup hit never reaches here — `upload_asset` returns early on one —
        which is right: identical bytes are the SAME asset, and an asset cannot
        supersede itself.
        """
        if new_asset.scene_id is None:
            return []
        if new_asset.asset_type not in self.SUPERSEDING_SCENE_ASSET_TYPES:
            return []

        conditions = [
            Asset.scene_id == new_asset.scene_id,
            Asset.asset_type == new_asset.asset_type,
            Asset.id != new_asset.id,
            Asset.superseded_by.is_(None),
        ]
        # A per-scene asset is per LANGUAGE too: the es-ES voiceover of a scene
        # does not replace its en-US one. Rows written before `language_code`
        # was populated carry NULL and are matched only by a NULL.
        if new_asset.language_code is None:
            conditions.append(Asset.language_code.is_(None))
        else:
            conditions.append(Asset.language_code == new_asset.language_code)

        previous = list(
            (await self.db.scalars(select(Asset).where(and_(*conditions)))).all()
        )
        now = datetime.now(timezone.utc)
        for old in previous:
            old.superseded_by = new_asset.id
            old.superseded_at = now
        return [old.id for old in previous]

    async def download_asset(self, asset_id: UUID) -> Optional[Tuple[bytes, str, str]]:
        """
        Download asset content from SeaweedFS.

        Returns (content_bytes, mime_type, filename) or None if not found.
        """
        asset = await self.get_asset(asset_id)
        if asset is None or not asset.seaweedfs_fid:
            return None

        # Download from SeaweedFS by fid (master volume lookup -> volume fetch)
        content = await seaweedfs_client.download_file(asset.seaweedfs_fid)
        if content is None:
            logger.error("SeaweedFS download failed: fid=%s", asset.seaweedfs_fid)
            return None

        # Extract filename from path
        filename = asset.seaweedfs_path.split("/")[-1] if asset.seaweedfs_path else "download"
        mime_type = asset.mime_type or "application/octet-stream"

        return content, mime_type, filename

    async def build_thumbnail(
        self, asset: Asset, width: int = 320,
    ) -> Tuple[bytes, str]:
        """Downscale an image asset to ``width`` px wide, preserving aspect.

        WP-45 Task 6(b). Raises ``FileNotFoundError`` when the bytes cannot be
        retrieved and ``ValueError`` when they are not a decodable image — the
        two failures a caller must distinguish, and neither of which may be
        answered with a placeholder that looks like a real thumbnail.

        The output is JPEG for opaque images and PNG when the source has an
        alpha channel, because flattening transparency onto an assumed white
        background silently changes what the operator is looking at.
        """
        result = await self.download_asset(asset.id)
        if result is None:
            raise FileNotFoundError(f"asset {asset.id} has no retrievable content")
        content, _mime, _filename = result

        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ValueError(
                "Pillow is not installed in this API image, so thumbnails "
                f"cannot be generated: {exc}"
            ) from exc

        try:
            with Image.open(io.BytesIO(content)) as img:
                img.load()
                has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                    img.mode == "P" and "transparency" in img.info
                )
                if img.width <= width:
                    # Already smaller than asked for. Re-encoding would only lose
                    # quality; hand back the original bytes and say what they are.
                    return content, asset.mime_type or "image/png"

                height = max(1, round(img.height * (width / img.width)))
                resized = img.convert("RGBA" if has_alpha else "RGB").resize(
                    (width, height), Image.LANCZOS
                )
                buf = io.BytesIO()
                if has_alpha:
                    resized.save(buf, format="PNG", optimize=True)
                    return buf.getvalue(), "image/png"
                resized.save(buf, format="JPEG", quality=82, optimize=True)
                return buf.getvalue(), "image/jpeg"
        except UnidentifiedImageError as exc:
            raise ValueError(
                f"asset {asset.id} is stored as an image but its bytes are not "
                f"a decodable image: {exc}"
            ) from exc
        except OSError as exc:
            raise ValueError(
                f"asset {asset.id} could not be decoded: {exc}"
            ) from exc

    async def delete_asset(self, asset_id: UUID) -> bool:
        """
        Delete an asset from SeaweedFS and database.

        If reference_count > 1, decrements count instead of deleting.
        """
        asset = await self.get_asset(asset_id)
        if asset is None:
            return False

        if asset.reference_count > 1:
            # Decrement reference count (dedup scenario)
            asset.reference_count -= 1
            await self.db.commit()
            logger.info(
                f"Asset reference decremented: id={asset_id} "
                f"ref_count={asset.reference_count}"
            )
            return True

        # Delete from SeaweedFS
        if asset.seaweedfs_path:
            try:
                await seaweedfs_client.delete(asset.seaweedfs_path)
            except Exception as e:
                logger.error("SeaweedFS delete failed: path=%s error=%s", asset.seaweedfs_path, e)

        # Delete from database
        await self.db.delete(asset)
        await self.db.commit()
        logger.info("Asset deleted: id=%s", asset_id)
        return True
