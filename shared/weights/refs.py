"""WP-65 -- parsing ``models.weights_ref`` into something fetchable.

MEASURED 2026-08-26. The column holds ``bundle_manifest_url`` verbatim
(``ivgs-api/app/api/ad01_ingest.py:176``, ``:197``) and MBCP emits **two
different shapes** through it, chosen at
``mbcp_api/api/v1/certifications.py:618-622``:

===========================================  ==============================
``.../weights/{model_id}/manifest?tier=X``   a real weight bundle; fetchable
``.../engines/{engine_digest}/manifest``     engine-only; NOTHING to fetch
===========================================  ==============================

A third shape exists in the live store because WP-46 hand-registered
``wan2.2-animate`` before the seam was wired: ``mbcp://serving/weights/{uuid}
?tier=candidate``. ``mbcp://serving`` is a placeholder authority, so the
serving base URL has to come from configuration.

Anything else is refused by name rather than guessed at
(:class:`UnknownReferenceFormError`) -- a mis-parsed reference fetches the
wrong bytes and then records them as verified, which is worse than not
fetching.
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from shared.weights.errors import (
    EngineOnlyCertificationError,
    NoWeightReferenceError,
    UnknownReferenceFormError,
)

#: ``mbcp://serving`` is not a resolvable authority; it names "the serving
#: plane this deployment is configured against".
_PLACEHOLDER_AUTHORITY = "serving"

_WEIGHTS_PATH = re.compile(r"^/weights/(?P<model_id>[^/]+)/manifest/?$")
_WEIGHTS_PATH_BARE = re.compile(r"^/weights/(?P<model_id>[^/?]+)/?$")
_ENGINES_PATH = re.compile(r"^/engines/(?P<digest>.+?)/manifest/?$")

_DEFAULT_TIER = "certified"


class RefKind(str, enum.Enum):
    """What a ``weights_ref`` actually points at."""

    #: ``/weights/{model_id}/manifest`` -- a signed bundle manifest.
    WEIGHT_BUNDLE = "weight_bundle"
    #: ``/engines/{digest}/manifest`` -- an engine image identity, no bytes.
    ENGINE_IMAGE = "engine_image"


@dataclass(frozen=True)
class WeightRef:
    """A parsed ``weights_ref``.

    ``serving_url`` is ``None`` when the reference used the ``mbcp://serving``
    placeholder authority; the caller supplies the configured base.
    """

    kind: RefKind
    raw: str
    serving_url: str | None = None
    model_id: str | None = None
    tier: str = _DEFAULT_TIER
    engine_digest: str | None = None

    @property
    def is_fetchable(self) -> bool:
        return self.kind is RefKind.WEIGHT_BUNDLE

    def resolve_serving_url(self, configured_base: str | None) -> str:
        """The base URL to fetch from, preferring what the reference carried.

        A reference that names its own host wins: it is what MBCP signed the
        bundle against. The configured base fills in only for the placeholder
        authority.
        """
        if self.serving_url:
            return self.serving_url
        if not configured_base:
            raise UnknownReferenceFormError(
                f"weights_ref {self.raw!r} uses the placeholder authority "
                f"'mbcp://{_PLACEHOLDER_AUTHORITY}' and no MBCP serving base "
                f"URL is configured for this deployment"
            )
        return configured_base.rstrip("/")


def parse_weights_ref(raw: str | None) -> WeightRef:
    """Parse ``models.weights_ref``; raise a NAMED refusal for every other case.

    :raises NoWeightReferenceError: the column is null or blank.
    :raises EngineOnlyCertificationError: MBCP certified an engine image.
    :raises UnknownReferenceFormError: any shape this client cannot speak.
    """
    if raw is None or not raw.strip():
        raise NoWeightReferenceError(
            "this model has no weight reference -- it was registered by hand "
            "rather than ingested from MBCP, so IVGS has nothing to fetch"
        )

    ref = raw.strip()
    parsed = urlparse(ref)
    scheme = parsed.scheme.lower()

    if scheme not in ("mbcp", "http", "https"):
        raise UnknownReferenceFormError(
            f"weights_ref {ref!r} uses scheme {scheme or '(none)'!r}; this "
            f"client speaks mbcp://, http:// and https:// only"
        )

    # --- engine-only certifications ---------------------------------------
    #
    # Checked BEFORE the weight-bundle shapes so the honest, specific refusal
    # wins over the generic one. This is the state all three MBCP-ingested
    # animation rows are in.
    engines = _ENGINES_PATH.match(parsed.path)
    if engines:
        digest = engines.group("digest")
        raise EngineOnlyCertificationError(
            f"MBCP certified this model as an ENGINE IMAGE ({digest}), not a "
            f"weight bundle -- there are no weights to fetch. The model ships "
            f"inside its engine image; making it runnable means deploying that "
            f"image to a node, not fetching bytes."
        )

    tier_values = parse_qs(parsed.query).get("tier")
    tier = tier_values[0] if tier_values else _DEFAULT_TIER

    weights = _WEIGHTS_PATH.match(parsed.path) or _WEIGHTS_PATH_BARE.match(parsed.path)
    if not weights:
        raise UnknownReferenceFormError(
            f"weights_ref {ref!r} is neither a weight-bundle manifest "
            f"(/weights/{{model_id}}/manifest) nor an engine manifest "
            f"(/engines/{{digest}}/manifest)"
        )

    if scheme == "mbcp":
        if parsed.netloc != _PLACEHOLDER_AUTHORITY:
            raise UnknownReferenceFormError(
                f"weights_ref {ref!r} uses scheme mbcp:// with authority "
                f"{parsed.netloc!r}; only 'mbcp://{_PLACEHOLDER_AUTHORITY}' is "
                f"recognised"
            )
        serving_url = None
    else:
        if not parsed.netloc:
            raise UnknownReferenceFormError(f"weights_ref {ref!r} has no host")
        serving_url = f"{scheme}://{parsed.netloc}"

    return WeightRef(
        kind=RefKind.WEIGHT_BUNDLE,
        raw=ref,
        serving_url=serving_url,
        model_id=weights.group("model_id"),
        tier=tier,
    )


def classify_weights_ref(raw: str | None) -> str:
    """``reason`` slug for a reference, without raising. Surface helper.

    Returns ``"weight_bundle"`` for a fetchable reference, otherwise the
    ``reason`` of the refusal it would raise.
    """
    from shared.weights.errors import WeightFetchError

    try:
        parse_weights_ref(raw)
    except WeightFetchError as exc:
        return exc.reason
    return RefKind.WEIGHT_BUNDLE.value
