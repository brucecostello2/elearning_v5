"""WP-65 Task 2 -- fetch a Model Store row's weights to a node, and record it.

The link that was missing. Every other piece existed: MBCP certifies and
exports (``ivgs-api/app/api/ad01_ingest.py:75``), the bundle fetch verifies
correctly (``shared/weights/bundle.py``, relocated from a proven CLI), and the
store has somewhere to show the answer. Nothing joined them, so a certified
model's bytes never moved unless an operator ran the CLI by hand.

ORDER OF REFUSALS. Each check runs before the one that would be more expensive
or less specific, so the admin gets the most actionable sentence available:

  1. no ``weights_ref``            -> nothing was ever ingested for this row
  2. engine-only certification     -> there are no bytes; deploy the image
  3. unknown reference form        -> refuse rather than guess
  4. no host for the engine        -> WP-65 Task 3; a correct end state
  5. no placement rule / no mount  -> the host cannot hold this family
  6. no credentials                -> the operator has not supplied the token
  7. fetch + verify                -> the only path that touches the network

Steps 1-5 need no credentials and no network, which is what makes the refusal
set testable and what lets the admin surface pre-compute a model's state
without attempting anything.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from shared.weights.bundle import FetchError, FetchResult, fetch_bundle
from shared.weights.errors import (
    BundleVerificationError,
    CredentialsUnavailableError,
    DigestMismatchError,
    PlacementNotLocalError,
    WeightFetchError,
)
from shared.weights.placement import EngineHost, host_for_model, placement_for
from shared.weights.refs import WeightRef, parse_weights_ref

logger = logging.getLogger(__name__)

#: The MBCP serving service token. Supplied as an environment variable on
#: node-01 and NEVER logged, never persisted, never written to a Model Store
#: row. Only its PRESENCE is ever reported.
SERVING_TOKEN_ENV = "MBCP_SERVING_TOKEN"

#: HMAC key for manifest-signature verification, shared out of band. When it
#: is absent the fetch still runs -- per-file and bundle-digest checks are
#: unaffected -- but ``signature_verified`` is recorded False, which is the
#: honest statement that the bundle is self-consistent but not proven MBCP's.
SIGNING_KEY_ENV = "MBCP_WEIGHT_SIGNING_KEY"

#: Base URL for references that used the ``mbcp://serving`` placeholder.
SERVING_URL_ENV = "MBCP_SERVING_URL"

#: Which fleet node this process is running on. Set per-service in the compose
#: files (``docker-compose.node03.yml:110`` sets ``NODE_HOSTNAME: node-03``).
#: When it is absent the host is unknown, and an unknown host is treated as
#: "not the target" -- fail closed.
NODE_HOSTNAME_ENV = "NODE_HOSTNAME"


class ModelRowLike(Protocol):
    """The subset of ``shared.models.model_store.Model`` this service reads."""

    name: Any
    engine: Any
    stage: Any
    weights_ref: Any
    weights_checksum: Any
    default_params: Any


@dataclass
class FetchPlan:
    """What a fetch WOULD do, computed without credentials or network.

    The admin surface renders this; the fetch executes it. Keeping them the
    same object is what stops the page claiming one outcome and the action
    producing another.
    """

    model_name: str
    engine: str
    stage: str
    ref: WeightRef | None = None
    host: EngineHost | None = None
    dest_dir: str | None = None
    family: str | None = None
    #: ``None`` when the plan is executable; otherwise the refusal.
    refusal: WeightFetchError | None = None

    @property
    def can_fetch(self) -> bool:
        return self.refusal is None

    @property
    def reason(self) -> str | None:
        return self.refusal.reason if self.refusal else None

    @property
    def message(self) -> str | None:
        return str(self.refusal) if self.refusal else None


def _engine_value(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _family_of(row: ModelRowLike) -> str | None:
    """The MBCP weight family for this row, if the ingest recorded one.

    ``default_params`` is where the ingest parks everything MBCP sent that has
    no column (``ad01_ingest.py:136-147``). ``family`` is read rather than
    required: a bundle without one lands in the engine's default destination.
    """
    params = getattr(row, "default_params", None) or {}
    if not isinstance(params, dict):
        return None
    fam = params.get("family") or params.get("weight_family")
    return str(fam) if fam else None


def plan_fetch(row: ModelRowLike, *, node_id: str | None = None) -> FetchPlan:
    """Work out what fetching ``row``'s weights would involve. Never raises.

    Steps 1-5 of the refusal order, all offline. Used both by the admin
    surface (to label a model honestly before anyone clicks) and by
    :func:`fetch_model_weights` (so the two cannot diverge).
    """
    engine = _engine_value(row.engine)
    stage = _engine_value(row.stage)
    plan = FetchPlan(
        model_name=str(row.name), engine=engine, stage=stage,
        family=_family_of(row),
    )

    try:
        plan.ref = parse_weights_ref(getattr(row, "weights_ref", None))
    except WeightFetchError as exc:
        plan.refusal = exc
        return plan

    try:
        # Which host will actually RUN this pair, not merely which node has a
        # container for the engine -- the two comfyui deployments differ.
        host = host_for_model(engine, stage) if node_id is None else None
        rule = placement_for(engine, node_id=node_id or (host.node_id if host else None))
        plan.host = rule.host
        plan.dest_dir = rule.dest_for(plan.family)
    except WeightFetchError as exc:
        plan.refusal = exc
        return plan

    return plan


def credentials_present() -> bool:
    """True when the serving token is in this process's environment.

    Presence only. The value is never returned, logged or recorded.
    """
    return bool(os.environ.get(SERVING_TOKEN_ENV, "").strip())


@dataclass
class FetchOutcome:
    """The result of one fetch attempt, ready to be recorded."""

    plan: FetchPlan
    ok: bool
    result: FetchResult | None = None
    error: WeightFetchError | None = None
    at: datetime | None = None

    @property
    def skipped_present(self) -> bool:
        return bool(self.result and self.result.skipped_present)


def fetch_model_weights(
    row: ModelRowLike,
    *,
    node_id: str | None = None,
    fetcher: Callable[..., FetchResult] = fetch_bundle,
    env: dict[str, str] | None = None,
    timeout: float = 1800.0,
) -> FetchOutcome:
    """Fetch, verify and place ``row``'s weights. Returns; does not raise.

    ``fetcher`` is injected so the whole path is testable against a local fake
    serving plane without the real credentials -- which is how this was proven,
    the live pass being held for the operator's MBCP token.
    """
    environ = env if env is not None else dict(os.environ)
    plan = plan_fetch(row, node_id=node_id)
    now = datetime.now(timezone.utc)

    if not plan.can_fetch:
        return FetchOutcome(plan=plan, ok=False, error=plan.refusal, at=now)

    # A fetch writes to a directory an ENGINE mounts, and that directory is on
    # the target node. A process elsewhere would happily create the same path
    # locally, verify a bundle into it, and record it as available -- bytes
    # where no loader looks, which is the defect this package closes. Refuse.
    target_node = plan.host.node_id if plan.host else None
    this_node = (environ.get(NODE_HOSTNAME_ENV) or "").strip()
    if target_node and this_node != target_node:
        err = PlacementNotLocalError(
            f"{plan.model_name}'s weights belong on {target_node} at "
            f"{plan.dest_dir} ({plan.host.container if plan.host else '?'}), and "
            f"this process is running on "
            f"{this_node or 'a host that does not declare ' + NODE_HOSTNAME_ENV}. "
            f"Fetching from here would place verified bytes in a directory no "
            f"engine mounts. Run the fetch on {target_node}."
        )
        return FetchOutcome(plan=plan, ok=False, error=err, at=now)

    token = (environ.get(SERVING_TOKEN_ENV) or "").strip()
    if not token:
        err = CredentialsUnavailableError(
            f"the MBCP serving token is not available to this process: set "
            f"{SERVING_TOKEN_ENV} on node-01 before fetching. IVGS never stores "
            f"it and never puts it in a Model Store row."
        )
        return FetchOutcome(plan=plan, ok=False, error=err, at=now)

    key_raw = (environ.get(SIGNING_KEY_ENV) or "").strip()
    signing_key = key_raw.encode() if key_raw else None
    if signing_key is None:
        logger.warning(
            "weight_fetch_signature_unverified model=%s reason=%s_unset",
            plan.model_name, SIGNING_KEY_ENV,
        )

    assert plan.ref is not None and plan.dest_dir is not None
    serving_url = plan.ref.resolve_serving_url(environ.get(SERVING_URL_ENV))

    try:
        result = fetcher(
            serving_url,
            plan.ref.model_id,
            token,
            plan.dest_dir,
            tier=plan.ref.tier,
            signing_key=signing_key,
            timeout=timeout,
        )
    except FetchError as exc:
        # The bundle layer already removed its staging tree on every failure
        # path; nothing partial is left where a loader could reach it.
        err = BundleVerificationError(
            f"fetching {plan.model_name} from {serving_url} failed: {exc}"
        )
        return FetchOutcome(plan=plan, ok=False, error=err, at=now)

    # Cross-check against what the row was certified for, WHERE THAT IS
    # MEANINGFUL. It is not always: for an engine-only certification MBCP puts
    # the engine image digest in `bundle_digest`, which IVGS stores in a column
    # named `weights_checksum` -- five live rows share one value. Those rows
    # never reach here (they are refused at step 2), so a mismatch at this
    # point is a real one.
    expected = (getattr(row, "weights_checksum", None) or "").strip()
    if expected:
        got = result.bundle_digest
        if expected.removeprefix("sha256:") != got.removeprefix("sha256:"):
            err = DigestMismatchError(
                f"{plan.model_name}: the bundle that verified against its own "
                f"manifest ({got}) is not the one this row was certified for "
                f"({expected}). The bytes were fetched and verified but are "
                f"not this model's; nothing has been recorded as available."
            )
            return FetchOutcome(plan=plan, ok=False, error=err, at=now)

    return FetchOutcome(plan=plan, ok=True, result=result, at=now)
