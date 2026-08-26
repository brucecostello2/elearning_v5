"""WP-65 Task 4 -- making the Model Store's availability columns mean something.

WHAT THE COLUMNS MEANT BEFORE (measured 2026-08-26)
---------------------------------------------------
NODES was ``m.node_availability.filter(status == "available").length``
(``ivgs-frontend/src/app/admin/models/page.tsx:606``), rendered as
"N available" or the bare word "none" (``:637-643``). Those rows come from a
poller that projects the GPU scheduler's Redis LRU of models a JOB once loaded
(``ivgs-workers/tasks/periodic_tasks.py:1017`` -> ``:918``). The LRU key has no
TTL, so it is a permanent record of "this ran here once", not of residency, and
it never looks at a disk. VRAM was ``models.vram_gb``, a number typed into a
registration form.

So one word -- "none" -- was doing the work of at least four different facts,
each needing a different action:

  * nothing was ever ingested for this row            -> register or re-certify
  * MBCP certified an ENGINE IMAGE, no bytes exist     -> deploy the image
  * certified with a real bundle, never fetched        -> fetch it
  * fetched and verified, but no node hosts the engine -> stand up a host

This service computes which one, and never invents a number for a fact it does
not have. WP-57/60's rule applies: the absence is stated in words, not as a
fabricated zero.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.model_store import (
    Model,
    ModelWeightPlacement,
    WeightPlacementStatus,
)
from shared.weights.errors import WeightFetchError
from shared.weights.service import FetchOutcome, credentials_present, plan_fetch

logger = logging.getLogger(__name__)


# --- the states an admin has to tell apart ---------------------------------

#: Verified bytes on at least one node that hosts the engine.
STATE_AVAILABLE = "available"
#: A real weight bundle exists at MBCP and has never been fetched here.
STATE_NOT_FETCHED = "not_fetched"
#: MBCP certified the engine image; there are no weights and never will be.
STATE_ENGINE_ONLY = "engine_only"
#: Fetchable in principle, but nothing on this fleet serves the engine.
STATE_NO_HOST = "no_host"
#: The row carries no weight reference at all.
STATE_NO_REFERENCE = "no_reference"
#: A fetch was attempted and failed.
STATE_FAILED = "failed"
#: A fetch is in flight.
STATE_FETCHING = "fetching"
#: The reference is in a form this system cannot speak.
STATE_UNKNOWN_REFERENCE = "unknown_reference"

#: refusal slug -> surface state. Explicit rather than derived, so a new
#: refusal cannot silently fall into a state that implies the wrong action.
_REASON_TO_STATE: dict[str, str] = {
    "no_weight_reference": STATE_NO_REFERENCE,
    "engine_only_certification": STATE_ENGINE_ONLY,
    "unknown_reference_form": STATE_UNKNOWN_REFERENCE,
    "no_host_for_engine": STATE_NO_HOST,
    "no_placement_rule": STATE_NO_HOST,
    # Not a property of the model at all -- a property of WHERE the request was
    # made. The model is still "certified, not fetched"; the surface must say
    # that and not imply the model is at fault.
    "placement_not_local": STATE_NOT_FETCHED,
}

#: The sentence the admin page shows. Written for someone deciding what to do
#: next, which is why each names an action.
_STATE_LABEL: dict[str, str] = {
    STATE_AVAILABLE: "weights verified on {nodes}",
    # NOT "weights not fetched". IVGS knowing of no fetch is a fact about
    # IVGS's records; whether bytes are on the node is a fact about the node,
    # and until something verifies the disk the two are different claims.
    # Measured 2026-08-26: wan2.2-animate's bytes ARE on node-03 (its engine
    # enumerates them) and no placement row exists, because they were placed by
    # the operator's CLI before this table did. The label must not call that
    # "not fetched".
    STATE_NOT_FETCHED: "no fetch recorded by IVGS",
    STATE_ENGINE_ONLY: "engine-only certification - no weights to fetch",
    STATE_NO_HOST: "no node hosts this engine",
    STATE_NO_REFERENCE: "no weight reference - not ingested from MBCP",
    STATE_FAILED: "last fetch failed",
    STATE_FETCHING: "fetch in progress",
    STATE_UNKNOWN_REFERENCE: "weight reference not understood",
}


@dataclass
class WeightStatus:
    """The honest answer for one model, ready to serialise."""

    state: str
    label: str
    #: Longer sentence from the refusal itself, when there is one.
    detail: str | None = None
    #: Nodes carrying VERIFIED bytes. Empty is empty -- never rendered as 0.
    verified_nodes: list[str] | None = None
    #: Real on-disk size, summed from verified placements. ``None`` when
    #: nothing has been measured; NOT zero, which would read as "measured, and
    #: it is empty".
    bytes_on_disk: int | None = None
    #: Whether a Fetch weights action would do anything.
    can_fetch: bool = False
    #: Where a fetch would put the bytes, so the action is inspectable first.
    target_node: str | None = None
    target_dir: str | None = None
    target_container: str | None = None
    #: Whether the MBCP serving credentials are present in this process.
    #: PRESENCE ONLY -- the token itself is never read, logged or returned.
    credentials_present: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "label": self.label,
            "detail": self.detail,
            "verified_nodes": self.verified_nodes or [],
            "bytes_on_disk": self.bytes_on_disk,
            "can_fetch": self.can_fetch,
            "target_node": self.target_node,
            "target_dir": self.target_dir,
            "target_container": self.target_container,
            "credentials_present": self.credentials_present,
        }


def compute_status(
    model: Model, placements: list[ModelWeightPlacement] | None = None
) -> WeightStatus:
    """The state of one model's weights. Pure; no IO, no side effects.

    ``placements`` defaults to the relationship, which is ``selectin``-loaded.
    """
    # The relationship is `selectin`, so a model loaded by a query carries it --
    # but `session.get()` can return an identity-map instance with it unloaded,
    # and touching it then triggers sync IO inside an async session
    # (`MissingGreenlet`). Asked rather than assumed: an unloaded relationship
    # means "we do not know of any placement", which is exactly what the
    # `not_fetched` branch below is for, and is never a reason to raise.
    if placements is not None:
        rows = list(placements)
    else:
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(model)
        if "weight_placements" in state.unloaded:
            rows = []
        else:
            rows = list(model.weight_placements or [])
    verified = [r for r in rows if r.status is WeightPlacementStatus.VERIFIED]

    if verified:
        nodes = sorted({r.node_id for r in verified})
        sizes = [r.bytes_on_disk for r in verified if r.bytes_on_disk is not None]
        return WeightStatus(
            state=STATE_AVAILABLE,
            label=_STATE_LABEL[STATE_AVAILABLE].format(nodes=", ".join(nodes)),
            verified_nodes=nodes,
            # None, not 0, when no placement recorded a size: "we have not
            # measured this" is a different claim from "it is empty".
            bytes_on_disk=sum(sizes) if sizes else None,
            can_fetch=True,
            credentials_present=credentials_present(),
        )

    in_flight = [r for r in rows if r.status is WeightPlacementStatus.FETCHING]
    if in_flight:
        return WeightStatus(
            state=STATE_FETCHING,
            label=_STATE_LABEL[STATE_FETCHING],
            detail=f"started {in_flight[0].updated_at:%Y-%m-%d %H:%M UTC}"
            if in_flight[0].updated_at
            else None,
            credentials_present=credentials_present(),
        )

    plan = plan_fetch(model)

    if plan.can_fetch:
        failed = [r for r in rows if r.status is WeightPlacementStatus.FAILED]
        state = STATE_FAILED if failed else STATE_NOT_FETCHED
        return WeightStatus(
            state=state,
            label=_STATE_LABEL[state],
            detail=failed[0].last_error if failed else None,
            can_fetch=True,
            target_node=plan.host.node_id if plan.host else None,
            target_dir=plan.dest_dir,
            target_container=plan.host.container if plan.host else None,
            credentials_present=credentials_present(),
        )

    state = _REASON_TO_STATE.get(plan.reason or "", STATE_FAILED)
    return WeightStatus(
        state=state,
        label=_STATE_LABEL.get(state, _STATE_LABEL[STATE_FAILED]),
        detail=plan.message,
        can_fetch=False,
        credentials_present=credentials_present(),
    )


async def _upsert_placement(
    db: AsyncSession, model_id: Any, node_id: str
) -> ModelWeightPlacement:
    row = (
        await db.execute(
            select(ModelWeightPlacement).where(
                ModelWeightPlacement.model_id == model_id,
                ModelWeightPlacement.node_id == node_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = ModelWeightPlacement(model_id=model_id, node_id=node_id)
        db.add(row)
        await db.flush()
    return row


async def record_outcome(
    db: AsyncSession,
    model: Model,
    outcome: FetchOutcome,
    *,
    actor: str,
) -> ModelWeightPlacement:
    """Write what a fetch attempt actually did. Refusals are recorded too.

    A refusal that leaves no trace is how "we tried and it will never work"
    becomes indistinguishable from "nobody has tried yet" -- the conflation
    this package removes.
    """
    node_id = outcome.plan.host.node_id if outcome.plan.host else "unassigned"
    row = await _upsert_placement(db, model.id, node_id)
    row.engine_container = outcome.plan.host.container if outcome.plan.host else None
    row.dest_dir = outcome.plan.dest_dir
    row.fetched_by = actor
    row.updated_at = datetime.now(UTC)

    if outcome.ok and outcome.result is not None:
        res = outcome.result
        row.status = WeightPlacementStatus.VERIFIED
        row.bundle_digest = res.bundle_digest
        row.file_count = len(res.files)
        # A skipped (already-present) fetch transfers no bytes; keep whatever
        # size the run that placed them recorded rather than overwriting a real
        # measurement with 0.
        if not res.skipped_present or row.bytes_on_disk is None:
            row.bytes_on_disk = res.size_bytes
        row.checksum_verified = res.digest_verified
        row.signature_verified = res.signature_verified
        row.last_error = None
        row.last_error_reason = None
        row.fetched_at = outcome.at or datetime.now(UTC)
    else:
        err: WeightFetchError | None = outcome.error
        row.status = WeightPlacementStatus.FAILED
        row.checksum_verified = False
        row.signature_verified = False
        row.last_error_reason = err.reason if err else "weight_fetch_failed"
        row.last_error = str(err) if err else "fetch failed"

    await db.flush()
    logger.info(
        "weight_fetch_recorded model=%s node=%s status=%s reason=%s",
        model.name, node_id, row.status.value, row.last_error_reason,
    )
    return row
