"""WP-65 weight-fetch refusals — every one named, none generic.

The Model Store has to tell an admin *which* of several different absences it
is looking at, because each needs a different action (AD-01.5.2 surfaces;
WP-65 Task 4). A single ``FetchError`` string would collapse them again, so
each refusal is its own class and carries a ``reason`` slug the API and the
frontend switch on.
"""
from __future__ import annotations


class WeightFetchError(Exception):
    """Base class for every WP-65 fetch refusal.

    ``reason`` is the stable machine slug (rendered by the admin surface);
    ``str(exc)`` is the sentence a human acts on.
    """

    reason: str = "weight_fetch_failed"


class NoWeightReferenceError(WeightFetchError):
    """The Model Store row carries no ``weights_ref`` at all.

    A hand-registered row (``latentsync-alt``) rather than an MBCP ingest.
    """

    reason = "no_weight_reference"


class EngineOnlyCertificationError(WeightFetchError):
    """MBCP certified the ENGINE IMAGE, not a weight bundle.

    ``mbcp_api/api/v1/certifications.py:603-620``: when a certification has no
    ``weights_checksum`` MBCP sets ``is_engine_only`` and points
    ``bundle_manifest_url`` at ``/engines/{engine_digest}/manifest`` --
    "engine_only has NO weights to serve". IVGS stores that URL in a column
    called ``weights_ref`` and the digest in one called ``weights_checksum``,
    which is why the store *looks* as though bytes are pending when there are
    none and never will be. The action is to deploy the engine image, not to
    fetch.
    """

    reason = "engine_only_certification"


class UnknownReferenceFormError(WeightFetchError):
    """``weights_ref`` is in no form this client can speak.

    Refused rather than guessed: a mis-parsed reference would fetch the wrong
    bytes and record them as verified.
    """

    reason = "unknown_reference_form"


class NoHostForEngineError(WeightFetchError):
    """No node on this fleet hosts the engine this model runs on.

    WP-65 Task 3. A correct outcome, not a fault -- and the state
    ``AnimateDiff-SD15`` and ``MimicMotion`` are in until a host exists.
    """

    reason = "no_host_for_engine"


class NoPlacementRuleError(WeightFetchError):
    """The engine has a host but no placement convention is declared for it.

    Placement is data (``shared/weights/placement.py``). Refusing here is the
    alternative to inventing a directory, which would put bytes somewhere no
    loader looks and then record them as available.
    """

    reason = "no_placement_rule"


class CredentialsUnavailableError(WeightFetchError):
    """The MBCP serving token is not present in this process's environment.

    The token is supplied as a named env var on node-01 and is never logged,
    never persisted, and never carried in a Model Store row.
    """

    reason = "credentials_unavailable"


class BundleVerificationError(WeightFetchError):
    """A per-file SHA-256, the bundle digest, or the manifest HMAC failed.

    Hard failure. The partial tree is removed before this is raised -- a
    half-verified bundle is never left where a loader could find it.
    """

    reason = "bundle_verification_failed"


class DigestMismatchError(WeightFetchError):
    """The fetched bundle digest is not the one the Model Store row expects.

    Distinct from :class:`BundleVerificationError`: the bundle verified against
    its OWN manifest, but it is not the bundle this row was certified for.
    """

    reason = "digest_mismatch"


class PlacementNotLocalError(WeightFetchError):
    """The destination node is not the host this process runs on.

    Found while authoring WP-65's operator block. The fetch service resolves a
    destination correctly -- for the animation family,
    ``/opt/models/comfyui-wan/models/diffusion_models`` on **node-03** -- but a
    process on node-01 that simply opened that path would create it locally and
    verify a bundle into a directory no engine mounts, then record it as
    available. That is the precise failure this package exists to remove, so it
    is refused rather than attempted.

    Placing weights on a remote node needs the fetch to RUN on that node. The
    operator CLI (``ivgs-models/mbcp_fetch.py``, same verification core) does
    that today; routing it through a worker on the target node's queue is
    ledgered, not guessed at.
    """

    reason = "placement_not_local"
