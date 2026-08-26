"""WP-65 -- AD-04 seam 2: getting a certified model's bytes onto a node.

``refs``      parse ``models.weights_ref`` (two MBCP shapes plus a legacy one)
``placement`` where an engine's weights go, and which node hosts it (data)
``bundle``    the verified fetch core: manifest -> per-file sha256 -> digest
``service``   plan, refuse by name, fetch, verify, record
``errors``    one class per refusal, each with a stable ``reason`` slug
"""
from shared.weights.errors import (
    BundleVerificationError,
    CredentialsUnavailableError,
    DigestMismatchError,
    EngineOnlyCertificationError,
    NoHostForEngineError,
    NoPlacementRuleError,
    NoWeightReferenceError,
    PlacementNotLocalError,
    UnknownReferenceFormError,
    WeightFetchError,
)
from shared.weights.refs import RefKind, WeightRef, classify_weights_ref, parse_weights_ref
from shared.weights.service import (
    FetchOutcome,
    FetchPlan,
    credentials_present,
    fetch_model_weights,
    plan_fetch,
)

__all__ = [
    "BundleVerificationError",
    "CredentialsUnavailableError",
    "DigestMismatchError",
    "EngineOnlyCertificationError",
    "FetchOutcome",
    "FetchPlan",
    "NoHostForEngineError",
    "NoPlacementRuleError",
    "NoWeightReferenceError",
    "PlacementNotLocalError",
    "RefKind",
    "UnknownReferenceFormError",
    "WeightFetchError",
    "WeightRef",
    "classify_weights_ref",
    "credentials_present",
    "fetch_model_weights",
    "parse_weights_ref",
    "plan_fetch",
]
