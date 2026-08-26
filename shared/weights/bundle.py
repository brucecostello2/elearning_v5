"""AD-04 seam 2 -- the verified weight-bundle fetch core.

RELOCATED BY WP-65 from ``ivgs-models/mbcp_fetch.py``, which was correct and
proven (the WP-46 attestation records "9 bundles via mbcp_fetch.py,
HMAC+digest+SHA256 verified 23/23") but lived in a directory no image ships and
no module imports. It is now importable by ``ivgs-api`` and ``ivgs-workers``
alike (both Dockerfiles ``COPY shared/``); ``ivgs-models/mbcp_fetch.py`` stays
as the operator CLI and re-exports from here, so the security-critical
verification exists once.

The verification is byte-identical to MBCP's reference consumer
(``mbcp_core/weights/consumer.py``) -- the two must agree or a bundle that
verifies on one plane fails on the other:

  1. GET /weights/{model_id}/manifest?tier={tier}      (X-Service-Token)
     -> BundleManifest; verify the HMAC-SHA256 signature.
  2. for each file: GET /weights/{model_id}/files/{logical_name}?tier={tier}
                                          (X-Service-Token + X-Bundle-Token)
     stream to disk, verifying each SHA-256.
  3. recompute and verify the bundle digest.

  bundle_digest = sha256(json.dumps(sorted([[logical_name, sha256], ...]),
                                    separators=(",", ":")))
  signature     = HMAC-SHA256(json.dumps(manifest_without_signature,
                              sort_keys=True, separators=(",", ":")), key)

WHAT WP-65 ADDED: **staging**. The original streamed each file straight to its
final path, so an interrupted fetch -- a killed process, a full disk, a dropped
connection -- left a truncated file exactly where a loader would find it and
load it. ``fetch_bundle`` now writes the whole bundle into a sibling
``.staging-*`` directory, verifies every file and the bundle digest there, and
only then moves it into place. This is the WP-63 supersede discipline applied
to bytes: nothing is visible at the real path until all of it is right.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

_CHUNK = 1 << 20  # 1 MiB

#: Prefix for the staging sibling. Chosen so a loader globbing ``*.safetensors``
#: or scanning a models directory does not descend into it, and so an
#: interrupted run is greppable afterwards.
_STAGING_PREFIX = ".staging-"


class FetchError(Exception):
    """Base class for weight-fetch failures."""


class AuthError(FetchError):
    """Service/bundle token rejected (401)."""


class RevokedError(FetchError):
    """Bundle has been revoked (410)."""


class ManifestError(FetchError):
    """Manifest missing, malformed, or model not found."""


class PathSafetyError(FetchError):
    """A manifest logical_name escaped the destination subtree."""


class ChecksumError(FetchError):
    """A file hash or the bundle digest did not match the manifest."""


class SignatureError(FetchError):
    """The manifest HMAC signature did not verify."""


@dataclass
class FetchResult:
    model_id: str
    dest_dir: Path
    bundle_digest: str
    engine_version: str | None = None
    files: list[str] = field(default_factory=list)
    size_bytes: int = 0
    digest_verified: bool = False
    signature_verified: bool = False
    #: WP-65. True when every file was already present, byte-identical, and
    #: nothing was transferred -- the idempotent re-fetch.
    skipped_present: bool = False


def compute_bundle_digest(files: list[dict[str, Any]]) -> str:
    """Recompute the bundle digest -- identical to the MBCP reference."""
    canonical = sorted((f["logical_name"], f["sha256"]) for f in files)
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":")).encode()
    ).hexdigest()


def verify_signature(manifest: dict[str, Any], signing_key: bytes) -> None:
    """Verify the manifest HMAC-SHA256 signature (reference form)."""
    payload = {k: v for k, v in manifest.items() if k != "signature"}
    expected = hmac.new(
        signing_key,
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, manifest.get("signature", "")):
        raise SignatureError("bundle manifest signature mismatch")


def _safe_dest(dest_dir: Path, logical_name: str) -> Path:
    """Resolve ``logical_name`` under ``dest_dir``, rejecting traversal."""
    if not logical_name or logical_name.startswith(("/", "\\")):
        raise PathSafetyError(f"unsafe logical_name: {logical_name!r}")
    candidate = (dest_dir / logical_name).resolve()
    root = dest_dir.resolve()
    if root != candidate and root not in candidate.parents:
        raise PathSafetyError(f"logical_name escapes destination: {logical_name!r}")
    return candidate


def _raise_for_status(resp: httpx.Response, what: str) -> None:
    if resp.status_code == 401:
        raise AuthError(f"{what}: token rejected (401)")
    if resp.status_code == 410:
        raise RevokedError(f"{what}: bundle revoked (410)")
    if resp.status_code == 404:
        raise ManifestError(f"{what}: not found (404)")
    if resp.status_code >= 400:
        raise FetchError(f"{what}: HTTP {resp.status_code}")


def fetch_manifest(
    client: httpx.Client,
    serving_url: str,
    model_id: str,
    service_token: str,
    tier: str,
) -> dict[str, Any]:
    """GET the signed BundleManifest (service-token auth, tier-scoped)."""
    url = f"{serving_url.rstrip('/')}/weights/{model_id}/manifest"
    resp = client.get(
        url, params={"tier": tier}, headers={"X-Service-Token": service_token}
    )
    _raise_for_status(resp, "manifest fetch")
    try:
        manifest = resp.json()
    except ValueError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    for key in ("bundle_digest", "files", "bundle_token"):
        if key not in manifest:
            raise ManifestError(f"manifest missing required field {key!r}")
    return manifest


def file_sha256(path: Path, chunk_size: int = _CHUNK) -> str:
    """SHA-256 of an on-disk file, streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_is_present(dest_dir: Path, files: list[dict[str, Any]]) -> bool:
    """True when every manifest file is already on disk with the right hash.

    The idempotency test. Hashes rather than trusting size or mtime: a
    truncated or swapped file is exactly what this must not call present.
    """
    for entry in files:
        try:
            target = _safe_dest(dest_dir, entry["logical_name"])
        except PathSafetyError:
            return False
        if not target.is_file():
            return False
        if file_sha256(target) != entry["sha256"]:
            return False
    return True


def _promote(staging: Path, dest: Path) -> None:
    """Move a fully-verified staging tree into place, file by file.

    File-granular rather than a single directory rename: the destination is a
    LIVE engine model directory that already holds other bundles' files, so it
    cannot be replaced wholesale. Each move is a rename within one filesystem
    and is therefore atomic per file; a loader either sees the old file or the
    complete new one, never a partial.
    """
    for src in sorted(staging.rglob("*")):
        if not src.is_file():
            continue
        target = dest / src.relative_to(staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, target)


def fetch_bundle(
    serving_url: str,
    model_id: str,
    service_token: str,
    dest_dir: str | os.PathLike[str],
    *,
    tier: str = "certified",
    signing_key: bytes | None = None,
    timeout: float = 600.0,
    chunk_size: int = _CHUNK,
    skip_if_present: bool = True,
) -> FetchResult:
    """Fetch and verify a certified bundle into ``dest_dir``.

    ``signing_key`` (shared out-of-band) enables manifest-signature
    verification; when ``None`` the signature step is skipped (per-file and
    bundle-digest checks still run). Raises a ``FetchError`` subclass on auth,
    revocation, path-safety, signature, or checksum failure.

    WP-65: bytes are staged and verified before anything is moved into
    ``dest_dir``, and the staging tree is removed on every failure path. With
    ``skip_if_present`` an already-complete, hash-matching bundle is a no-op
    that reports ``skipped_present=True`` rather than a re-download.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0)) as client:
        manifest = fetch_manifest(client, serving_url, model_id, service_token, tier)

        sig_ok = False
        if signing_key is not None:
            verify_signature(manifest, signing_key)
            sig_ok = True

        files = manifest["files"]

        # The bundle digest is a property of the MANIFEST and is checked before
        # a byte is transferred -- a manifest that does not describe itself
        # correctly is not worth downloading against.
        recomputed = compute_bundle_digest(files)
        if recomputed != manifest["bundle_digest"]:
            raise ChecksumError(
                f"bundle digest mismatch (manifest={manifest['bundle_digest']}, "
                f"recomputed={recomputed})"
            )

        if skip_if_present and files and bundle_is_present(dest, files):
            return FetchResult(
                model_id=model_id,
                dest_dir=dest,
                bundle_digest=manifest["bundle_digest"],
                engine_version=manifest.get("engine_version"),
                files=[f["logical_name"] for f in files],
                size_bytes=0,
                digest_verified=True,
                signature_verified=sig_ok,
                skipped_present=True,
            )

        headers = {
            "X-Service-Token": service_token,
            "X-Bundle-Token": manifest["bundle_token"],
        }

        staging = dest / f"{_STAGING_PREFIX}{uuid.uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        written: list[str] = []
        total = 0
        try:
            for entry in files:
                logical = entry["logical_name"]
                expected_sha = entry["sha256"]
                # Path-safety is checked against the STAGING root and the real
                # destination alike: a name that is safe under one must be safe
                # under the other, or promotion would escape.
                _safe_dest(dest, logical)
                target = _safe_dest(staging, logical)
                target.parent.mkdir(parents=True, exist_ok=True)

                url = f"{serving_url.rstrip('/')}/weights/{model_id}/files/{logical}"
                digest = hashlib.sha256()
                nbytes = 0
                with client.stream(
                    "GET", url, params={"tier": tier}, headers=headers
                ) as resp:
                    _raise_for_status(resp, f"file fetch {logical!r}")
                    with open(target, "wb") as fh:
                        for chunk in resp.iter_bytes(chunk_size):
                            fh.write(chunk)
                            digest.update(chunk)
                            nbytes += len(chunk)

                if digest.hexdigest() != expected_sha:
                    raise ChecksumError(
                        f"{logical}: sha256 mismatch "
                        f"(manifest={expected_sha}, got={digest.hexdigest()})"
                    )
                written.append(logical)
                total += nbytes

            _promote(staging, dest)
        finally:
            # Every exit path. A staging tree left behind is a disk leak on a
            # node whose model volumes are sized to the byte.
            shutil.rmtree(staging, ignore_errors=True)

    return FetchResult(
        model_id=model_id,
        dest_dir=dest,
        bundle_digest=manifest["bundle_digest"],
        engine_version=manifest.get("engine_version"),
        files=written,
        size_bytes=total,
        digest_verified=True,
        signature_verified=sig_ok,
    )
