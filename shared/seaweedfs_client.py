"""
SeaweedFS client for distributed file storage.

Provides async upload, download, delete, and health check against
SeaweedFS master (port 9333) and filer (port 8888).
Uses httpx for async HTTP.
"""
import logging
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# Shared httpx client timeout
_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)


class SeaweedFSClient:
    """Async client for SeaweedFS master and filer APIs."""

    def __init__(self) -> None:
        self.master_url = settings.SEAWEEDFS_MASTER_URL
        self.filer_url = settings.SEAWEEDFS_FILER_URL
        self.mount_path = settings.SEAWEEDFS_MOUNT_PATH
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        file_data: bytes,
        collection: str,
        filename: str,
    ) -> Optional[str]:
        """
        Upload a file to SeaweedFS.

        Args:
            file_data: Raw file bytes.
            collection: Storage collection (hot / warm / cold / archive).
            filename: Desired filename.

        Returns:
            SeaweedFS fid string on success, None on failure.
        """
        client = await self._get_client()
        try:
            # Step 1 — obtain volume assignment from master
            assign_resp = await client.post(
                f"{self.master_url}/dir/assign",
                params={"collection": collection},
            )
            assign_resp.raise_for_status()
            assign_data = assign_resp.json()

            if "error" in assign_data:
                logger.error(f"SeaweedFS assign error: {assign_data['error']}")
                return None

            fid: str = assign_data["fid"]
            volume_url: str = assign_data["url"]

            # Step 2 — upload to assigned volume server
            upload_url = f"http://{volume_url}/{fid}"
            files = {"file": (filename, file_data)}
            upload_resp = await client.post(upload_url, files=files)
            upload_resp.raise_for_status()
            upload_data = upload_resp.json()

            if "error" in upload_data:
                logger.error(f"SeaweedFS upload error: {upload_data['error']}")
                return None

            logger.info(
                f"Uploaded file to SeaweedFS: fid={fid}, name={filename}, "
                f"size={upload_data.get('size', 'unknown')}"
            )
            return fid

        except httpx.HTTPError as e:
            logger.error(f"SeaweedFS upload failed for {filename}: {e}")
            return None

    # ------------------------------------------------------------------
    # Upload via Filer (path-based)
    # ------------------------------------------------------------------

    async def upload_to_filer(
        self,
        file_data: bytes,
        filer_path: str,
        filename: str,
    ) -> bool:
        """
        Upload a file through the SeaweedFS Filer (path-based storage).

        Args:
            file_data: Raw file bytes.
            filer_path: Directory path under the filer, e.g. /ivgs/images/
            filename: Target filename.

        Returns:
            True on success.
        """
        client = await self._get_client()
        try:
            url = f"{self.filer_url}{filer_path}{filename}"
            resp = await client.post(url, files={"file": (filename, file_data)})
            resp.raise_for_status()
            logger.info(f"Uploaded to filer: {filer_path}{filename}")
            return True
        except httpx.HTTPError as e:
            logger.error(f"SeaweedFS filer upload failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def download_file(self, fid: str) -> Optional[bytes]:
        """
        Download a file from SeaweedFS by fid.

        Args:
            fid: SeaweedFS file ID (e.g. "3,01234abc").

        Returns:
            File bytes on success, None on failure.
        """
        client = await self._get_client()
        try:
            volume_id = fid.split(",")[0]
            lookup_resp = await client.get(
                f"{self.master_url}/dir/lookup",
                params={"volumeId": volume_id},
            )
            lookup_resp.raise_for_status()
            lookup_data = lookup_resp.json()

            locations = lookup_data.get("locations", [])
            if not locations:
                logger.error(f"No locations for fid={fid}")
                return None

            download_url = f"http://{locations[0]['url']}/{fid}"
            dl_resp = await client.get(download_url)
            dl_resp.raise_for_status()
            return dl_resp.content

        except httpx.HTTPError as e:
            logger.error(f"SeaweedFS download failed for fid={fid}: {e}")
            return None

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_file(self, fid: str) -> bool:
        """Delete a file from SeaweedFS by fid."""
        client = await self._get_client()
        try:
            volume_id = fid.split(",")[0]
            lookup_resp = await client.get(
                f"{self.master_url}/dir/lookup",
                params={"volumeId": volume_id},
            )
            lookup_resp.raise_for_status()
            locations = lookup_resp.json().get("locations", [])

            if not locations:
                logger.error(f"No locations for fid={fid}")
                return False

            for loc in locations:
                del_resp = await client.delete(f"http://{loc['url']}/{fid}")
                del_resp.raise_for_status()

            logger.info(f"Deleted from SeaweedFS: fid={fid}")
            return True

        except httpx.HTTPError as e:
            logger.error(f"SeaweedFS delete failed for fid={fid}: {e}")
            return False

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        """Return True if both master and filer respond."""
        client = await self._get_client()
        try:
            master_resp = await client.get(
                f"{self.master_url}/dir/status", timeout=5.0
            )
            master_resp.raise_for_status()

            filer_resp = await client.get(
                f"{self.filer_url}/", timeout=5.0
            )
            filer_resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"SeaweedFS health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("SeaweedFS client closed")


# Global singleton
seaweedfs_client = SeaweedFSClient()
