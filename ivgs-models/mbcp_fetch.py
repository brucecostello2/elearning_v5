"""AD-04 seam 2 -- IVGS-side weight-fetch CLI.

THE IMPLEMENTATION MOVED. WP-65 relocated the verification core to
``shared/weights/bundle.py`` so ``ivgs-api`` and ``ivgs-workers`` can import it
-- both Dockerfiles ``COPY shared/``, and neither ships ``ivgs-models/``, which
is why a correct and proven fetch client sat unreachable from the running
system for weeks while the Model Store reported models as un-placed.

This file stays because the operator CLI is the documented way to fetch a
bundle by hand (MBCP SSOT S9.11, operator-initiated) and the WP-46 attestation
cites it by name. Its arguments, exit codes and output are unchanged. Every
name it used to define is re-exported below, so anything importing it keeps
working -- but there is now ONE copy of the HMAC, per-file SHA-256 and
bundle-digest checks, which is the point: two copies of security-critical
verification drift, and a bundle that verifies on one plane fails on the other.

WP-65 also added STAGING to the shared core: bytes are written to a sibling
``.staging-*`` directory, fully verified there, and only then moved into place.
The previous behaviour streamed each file straight to its final path, so an
interrupted fetch left a truncated file exactly where a loader would find it.
Run with ``--dest`` as before; the staging directory is created under it and
removed on every exit path.
"""
from __future__ import annotations

import argparse
import os
import sys

from shared.weights.bundle import (
    AuthError,
    ChecksumError,
    FetchError,
    FetchResult,
    ManifestError,
    PathSafetyError,
    RevokedError,
    SignatureError,
    compute_bundle_digest,
    fetch_bundle,
    fetch_manifest,
    verify_signature,
)

__all__ = [
    "AuthError",
    "ChecksumError",
    "FetchError",
    "FetchResult",
    "ManifestError",
    "PathSafetyError",
    "RevokedError",
    "SignatureError",
    "compute_bundle_digest",
    "fetch_bundle",
    "fetch_manifest",
    "main",
    "verify_signature",
]


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
