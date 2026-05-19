"""
Asset service: SeaweedFS upload, metadata management, download proxy, deduplication.

Per §5.1.5, §10.1–10.4:
- Upload to SeaweedFS with collection routing based on asset type
- SHA-256 deduplication (§10.4)
- Storage tier assignment (default: hot)
- Download proxy from SeaweedFS through API
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
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

    async def upload_asset(
        self,
        project_id: UUID,
        file_content: bytes,
        filename: str,
        content_type: str,
        asset_type: str,
        scene_id: Optional[UUID] = None,
        language_code: Optional[str] = None,
    ) -> Asset:
        """
        Upload an asset to SeaweedFS and create metadata record.

        Implements deduplication via SHA-256 hash (§10.4):
        - If a completed asset with the same hash exists, increment reference_count
          and return existing asset reference.
        - Otherwise, upload to SeaweedFS and create new record.
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

        # Check for existing asset with same hash (deduplication per §10.4)
        existing = await self.db.execute(
            select(Asset).where(
                and_(
                    Asset.content_hash == content_hash,
                    Asset.project_id == project_id,
                    Asset.storage_tier != "deleted",
                )
            )
        )
        existing_asset = existing.scalar_one_or_none()

        if existing_asset:
            # Deduplication: increment reference_count, don't re-upload
            existing_asset.reference_count += 1
            existing_asset.last_accessed_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing_asset)
            logger.info(
                f"Asset deduplicated: hash={content_hash[:16]}... "
                f"existing_id={existing_asset.id} ref_count={existing_asset.reference_count}"
            )
            return existing_asset

        # Build SeaweedFS path
        base_path = ASSET_TYPE_PATHS[asset_type]
        seaweedfs_path = f"{base_path}/{project_id}/{filename}"

        # Upload to SeaweedFS
        upload_result = await seaweedfs_client.upload(
            path=seaweedfs_path,
            data=file_content,
            content_type=content_type,
        )
        seaweedfs_fid = upload_result.get("fid", "") if upload_result else ""

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
            storage_tier=INITIAL_TIER,
            last_accessed_at=datetime.now(timezone.utc),
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)

        logger.info(
            f"Asset uploaded: id={asset.id} type={asset_type} "
            f"size={len(file_content)} path={seaweedfs_path}"
        )
        return asset

    async def download_asset(self, asset_id: UUID) -> Optional[Tuple[bytes, str, str]]:
        """
        Download asset content from SeaweedFS.

        Returns (content_bytes, mime_type, filename) or None if not found.
        """
        asset = await self.get_asset(asset_id)
        if asset is None or not asset.seaweedfs_path:
            return None

        # Download from SeaweedFS
        content = await seaweedfs_client.download(asset.seaweedfs_path)
        if content is None:
            logger.error(f"SeaweedFS download failed: path={asset.seaweedfs_path}")
            return None

        # Extract filename from path
        filename = asset.seaweedfs_path.split("/")[-1] if asset.seaweedfs_path else "download"
        mime_type = asset.mime_type or "application/octet-stream"

        return content, mime_type, filename

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
                logger.error(f"SeaweedFS delete failed: path={asset.seaweedfs_path} error={e}")

        # Delete from database
        await self.db.delete(asset)
        await self.db.commit()
        logger.info(f"Asset deleted: id={asset_id}")
        return True
