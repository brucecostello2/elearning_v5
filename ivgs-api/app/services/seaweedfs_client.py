"""
SeaweedFS HTTP client — replaces all boto3/S3 operations.
Endpoints:
  Master:  http://node-01:9333
  Filer:   http://node-01:8888
  Volumes: http://node-{02-06}:8080
"""
import io
import hashlib
from typing import Optional
import requests
from app.core.config import settings

MASTER_URL  = settings.SEAWEEDFS_MASTER_URL   # http://node-01:9333
FILER_URL   = settings.SEAWEEDFS_FILER_URL    # http://node-01:8888
TIMEOUT     = 30


class SeaweedFSClient:

    # ------------------------------------------------------------------
    # FILE ASSIGNMENT & UPLOAD
    # ------------------------------------------------------------------
    def assign(self, collection: str, replication: str = "001") -> dict:
        """Request a new FID from master for the given collection/tier."""
        resp = requests.get(
            f"{MASTER_URL}/dir/assign",
            params={"collection": collection, "replication": replication},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()   # {"fid": "3,01637037d6", "url": "node-02:8080", ...}

    def upload(self, collection: str, data: bytes,
               filename: str = "file",
               mime: str = "application/octet-stream") -> dict:
        """Assign FID and upload data in one call. Returns assignment info."""
        assignment = self.assign(collection)
        vol_url = f"http://{assignment['url']}/{assignment['fid']}"
        r = requests.post(
            vol_url,
            files={"file": (filename, io.BytesIO(data), mime)},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return {**assignment, "size": len(data)}

    # ------------------------------------------------------------------
    # FILE DOWNLOAD
    # ------------------------------------------------------------------
    def download(self, fid: str, collection: str) -> bytes:
        """Download file bytes by FID. Looks up URL via master first."""
        lookup = self._lookup(fid)
        vol_url = f"http://{lookup['locations'][0]['url']}/{fid}"
        r = requests.get(vol_url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.content

    def _lookup(self, fid: str) -> dict:
        volume_id = fid.split(",")[0]
        r = requests.get(
            f"{MASTER_URL}/dir/lookup",
            params={"volumeId": volume_id},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # FILE DELETE
    # ------------------------------------------------------------------
    def delete(self, fid: str) -> bool:
        """Delete a file from a volume server by FID."""
        lookup = self._lookup(fid)
        vol_url = f"http://{lookup['locations'][0]['url']}/{fid}"
        r = requests.delete(vol_url, timeout=TIMEOUT)
        return r.status_code in (200, 204, 404)

    # ------------------------------------------------------------------
    # FILER OPERATIONS (POSIX-like path interface)
    # ------------------------------------------------------------------
    def filer_put(self, filer_path: str, data: bytes,
                  mime: str = "application/octet-stream") -> bool:
        """Write bytes to SeaweedFS filer at the given path."""
        r = requests.put(
            f"{FILER_URL}{filer_path}",
            data=data,
            headers={"Content-Type": mime},
            timeout=TIMEOUT,
        )
        return r.status_code in (200, 201)

    def filer_get(self, filer_path: str) -> bytes:
        r = requests.get(f"{FILER_URL}{filer_path}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.content

    def filer_delete(self, filer_path: str) -> bool:
        r = requests.delete(f"{FILER_URL}{filer_path}", timeout=TIMEOUT)
        return r.status_code in (200, 204, 404)

    def filer_list(self, dir_path: str) -> list[dict]:
        """List files in a filer directory. Returns list of entry dicts."""
        r = requests.get(
            f"{FILER_URL}{dir_path}",
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("Entries", [])

    # ------------------------------------------------------------------
    # VOLUME STATUS (used by StorageAnalyticsService)
    # ------------------------------------------------------------------
    def volume_status(self) -> dict:
        r = requests.get(f"{MASTER_URL}/vol/status", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def collection_status(self, collection: str) -> dict:
        r = requests.get(
            f"{MASTER_URL}/col/info",
            params={"collection": collection},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------
    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def health(self) -> bool:
        try:
            r = requests.get(f"{MASTER_URL}/cluster/status", timeout=5)
            return r.ok
        except Exception:
            return False


# Module-level singleton
seaweedfs = SeaweedFSClient()
