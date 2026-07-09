"""AD-04 seam 2 — IVGS-side weight-fetch client.

`huggingface-cli` cannot be repointed at an arbitrary origin (MBCP SSOT
§9.11), so consuming MBCP-served certified weights needs a purpose-built
fetch path. This client mirrors MBCP's reference consumer
(``mbcp_core.weights.consumer.WeightBundleConsumer``) so the two verify a
bundle identically:

  1. GET /weights/{model_id}/manifest?tier={tier}      (X-Service-Token)
     -> BundleManifest; verify the HMAC-SHA256 signature.
  2. for each file: GET /weights/{model_id}/files/{logical_name}?tier={tier}
                                          (X-Service-Token + X-Bundle-Token)
     stream to disk, verifying each SHA-256.
  3. recompute and verify the bundle digest.

Digest and signature forms are byte-identical to the reference (P4-2):
  * bundle_digest = sha256(json.dumps(sorted([[logical_name, sha256], ...]),
                                      separators=(",", ":")))
  * signature     = HMAC-SHA256(json.dumps(manifest_without_signature,
                                sort_keys=True, separators=(",", ":")), key)

Additions over the reference: path-safety on logical names (defence in depth)
and a CLI. Operator-initiated (§9.11); no token is ever persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

_CHUNK = 1 << 20  # 1 MiB


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


def compute_bundle_digest(files: list[dict[str, Any]]) -> str:
    """Recompute the bundle digest — identical to the MBCP reference."""
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
) -> FetchResult:
    """Fetch and verify a certified bundle into ``dest_dir``.

    ``signing_key`` (shared out-of-band) enables manifest-signature
    verification; when ``None`` the signature step is skipped (per-file and
    bundle-digest checks still run). Raises a ``FetchError`` subclass on auth,
    revocation, path-safety, signature, or checksum failure.
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
        headers = {
            "X-Service-Token": service_token,
            "X-Bundle-Token": manifest["bundle_token"],
        }

        written: list[str] = []
        total = 0
        for entry in files:
            logical = entry["logical_name"]
            expected_sha = entry["sha256"]
            target = _safe_dest(dest, logical)
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
                target.unlink(missing_ok=True)
                raise ChecksumError(
                    f"{logical}: sha256 mismatch "
                    f"(manifest={expected_sha}, got={digest.hexdigest()})"
                )
            written.append(logical)
            total += nbytes

    recomputed = compute_bundle_digest(files)
    if recomputed != manifest["bundle_digest"]:
        raise ChecksumError(
            f"bundle digest mismatch (manifest={manifest['bundle_digest']}, "
            f"recomputed={recomputed})"
        )

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a certified weight bundle from the MBCP serving plane."
    )
    parser.add_argument("--serving-url", required=True, help="MBCP serving base URL")
    parser.add_argument("--model-id", required=True, help="Model UUID to fetch")
    parser.add_argument("--dest", required=True, help="Destination directory")
    parser.add_argument("--tier", default="certified")
    parser.add_argument(
        "--token-env",
        default="MBCP_SERVING_TOKEN",
        help="Env var holding the MBCP serving service token",
    )
    parser.add_argument(
        "--signing-key-env",
        default="MBCP_WEIGHT_SIGNING_KEY",
        help="Env var holding the HMAC signing key (skips signature check if unset)",
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)

    token = os.environ.get(args.token_env, "")
    if not token:
        print(f"error: {args.token_env} is not set", file=sys.stderr)
        return 2
    key_raw = os.environ.get(args.signing_key_env, "")
    signing_key = key_raw.encode() if key_raw else None

    try:
        result = fetch_bundle(
            args.serving_url,
            args.model_id,
            token,
            args.dest,
            tier=args.tier,
            signing_key=signing_key,
            timeout=args.timeout,
        )
    except FetchError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"ok: {len(result.files)} file(s), {result.size_bytes} bytes, digest "
        f"{result.bundle_digest} verified "
        f"(signature={'verified' if result.signature_verified else 'skipped'}) "
        f"-> {result.dest_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
