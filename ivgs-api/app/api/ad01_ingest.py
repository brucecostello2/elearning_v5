"""AD-04 seam 1 — MBCP certification-export receiver.

Mounted at the app root so the path matches MBCP's ``AD01Export`` exactly:
``POST {MBCP_AD01_URL}/ad01/v1/certified-models`` with an ``X-Service-Token``
header and an ``Idempotency-Key`` (the certification id). Ingests the bundle
as a CANDIDATE model + AD-01.7.2 attestation and returns ``{"ad01_id": ...}``.

Contract gap (recorded): MBCP's ExportBundle does not carry the engine *type*
or measured VRAM. The engine is derived from ``ivgs_stage`` (multi-engine
stages get the stage default) and VRAM is left null; both are operator-
correctable at the CANDIDATE -> APPROVED gate, before the model is selectable.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_mbcp_ingest
from app.schemas.model_store import ExportBundleIn, ExportReceiptOut
from shared.database import get_session
from shared.models.model_store import (
    Model,
    ModelApproval,
    ModelEngine,
    ModelStage,
    ModelState,
    ModelTier,
)

logger = logging.getLogger(__name__)

ad01_router = APIRouter(prefix="/ad01/v1", tags=["AD-01 Ingest"])

# MBCP IvgsStage value -> IVGS ModelStage (names differ for a couple of stages).
_IVGS_STAGE_MAP: dict[str, ModelStage] = {
    "transcript_refinement": ModelStage.TRANSCRIPT_REFINEMENT,
    "storyboard": ModelStage.STORYBOARD_GENERATION,
    "translation": ModelStage.TRANSLATION,
    "image_generation": ModelStage.IMAGE_GENERATION,
    "video_generation": ModelStage.VIDEO_GENERATION,
    "animation_generation": ModelStage.ANIMATION_GENERATION,
    "tts": ModelStage.VOICEOVER_TTS,
    "talking_head": ModelStage.TALKING_HEAD,
    "composition": ModelStage.COMPOSITION,
}

# Default engine per stage, used ONLY when the bundle omits ``engine``
# (recorded gap: older MBCP exports do not send the engine type).
#
# WP-46 — this table mis-registered every animation model IVGS has.
# ``animation_generation`` defaulted to ``animatediff``, which is the name of
# ONE MBCP model family, not of an engine. MBCP serves its whole animation
# line — Wan2.2-Animate, MimicMotion and AnimateDiff-SD15 alike — on the
# unified ComfyUI runtime (``mbcp_adapters/comfyui.py``: one ComfyUIAdapter,
# one graph per family), so the engine is ``comfyui`` for all three. All three
# IVGS candidate rows landed with engine ``animatediff`` because of this line,
# and ``models`` registration fields are immutable, so each has to be
# disabled and re-registered by hand. The default is now what MBCP actually
# serves; the fix does not touch the rows already written.
_STAGE_DEFAULT_ENGINE: dict[ModelStage, ModelEngine] = {
    ModelStage.TRANSCRIPT_REFINEMENT: ModelEngine.VLLM,
    ModelStage.STORYBOARD_GENERATION: ModelEngine.VLLM,
    ModelStage.TRANSLATION: ModelEngine.VLLM,
    ModelStage.IMAGE_GENERATION: ModelEngine.COMFYUI,
    ModelStage.VIDEO_GENERATION: ModelEngine.COGVIDEOX,
    ModelStage.ANIMATION_GENERATION: ModelEngine.COMFYUI,
    ModelStage.VOICEOVER_TTS: ModelEngine.COQUI,
    ModelStage.TALKING_HEAD: ModelEngine.LATENTSYNC,
}


@ad01_router.post(
    "/certified-models",
    response_model=ExportReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
async def receive_certified_model(
    bundle: ExportBundleIn,
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_mbcp_ingest),
) -> ExportReceiptOut:
    """Ingest an MBCP certified model as a CANDIDATE + attestation.

    Idempotent two ways: a replay of the *same* certification (same
    certification_id, MBCP's Idempotency-Key) returns the existing record
    without duplicating; a *re-certification* of the same model name updates
    the weight reference/checksum and appends a fresh attestation, keeping the
    trail and the lifecycle state.
    """
    stage = _IVGS_STAGE_MAP.get(bundle.ivgs_stage)
    if stage is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "UNKNOWN_STAGE",
                    "message": f"unmapped ivgs_stage: {bundle.ivgs_stage!r}",
                }
            },
        )

    # WP-53. `ExportBundleIn` was `extra="ignore"`, so a field MBCP added to the
    # bundle was accepted with a 201 and discarded without a trace -- which is
    # what happened to `request_constraints` for the four days before this
    # change. Logged FIRST, before the replay branch can return, so a re-send of
    # a drifted bundle still says so.
    unknown = bundle.unknown_fields
    if unknown:
        logger.warning(
            "ad01_export_unknown_fields certification_id=%s model_name=%s fields=%s",
            bundle.certification_id,
            bundle.model_name,
            ",".join(unknown),
        )

    cert_ref = str(bundle.certification_id)

    # Replay dedup on the certification id (MBCP's Idempotency-Key).
    replayed = (
        await db.execute(
            select(ModelApproval).where(ModelApproval.vetting_reference == cert_ref)
        )
    ).scalar_one_or_none()
    if replayed is not None:
        model = await db.get(Model, replayed.model_id)
        return ExportReceiptOut(
            ad01_id=str(replayed.model_id),
            accepted=True,
            created=False,
            state=model.state if model else ModelState.CANDIDATE,
        )

    params: dict = {"weight_tier": bundle.weight_tier}
    if unknown:
        # A durable record, because a log line rotates and the question "when
        # did the seam drift?" gets asked months later. Underscore-prefixed:
        # this is IVGS bookkeeping about the transfer, not an MBCP parameter.
        params["_unknown_export_fields"] = unknown
    if bundle.engine_version:
        params["engine_version"] = bundle.engine_version
    if bundle.quantization:
        params["quantization"] = bundle.quantization
    if bundle.provenance is not None:
        params["provenance"] = bundle.provenance.model_dump(mode="json")

    existing = (
        await db.execute(select(Model).where(Model.name == bundle.model_name))
    ).scalar_one_or_none()
    created = existing is None

    if created:
        engine = bundle.engine or _STAGE_DEFAULT_ENGINE.get(stage)
        if engine is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "ENGINE_REQUIRED",
                        "message": (
                            f"engine must be supplied for stage "
                            f"{bundle.ivgs_stage!r} (no stage default)"
                        ),
                    }
                },
            )
        model = Model(
            name=bundle.model_name,
            display_name=bundle.model_name,  # AD-01 editorial; seed with name
            stage=stage,
            engine=engine,  # supplied (SSOT) or stage-derived (recorded gap)
            tier=ModelTier.BOTH,  # MBCP sends weight_tier, not the model tier
            state=ModelState.CANDIDATE,
            weights_ref=bundle.bundle_manifest_url,  # signed manifest endpoint
            weights_checksum=bundle.bundle_digest,
            license=bundle.license,
            vram_gb=bundle.measured_vram_gb,
            default_params=params,
            # WP-53: carried and stored, never interpreted here. Passed
            # through as-is: MBCP distinguishes `null` ("we have declared
            # nothing") from a block, and collapsing either into the other
            # would be IVGS inventing a claim on the sender's behalf.
            request_constraints=bundle.request_constraints,
            created_by=bundle.certified_by,
        )
        db.add(model)
        await db.flush()
    else:
        model = existing
        model.stage = stage
        # Only overwrite supplied fields — a lean re-cert must not clobber an
        # operator's editorial correction of engine/VRAM/license.
        if bundle.engine is not None:
            model.engine = bundle.engine
        model.weights_ref = bundle.bundle_manifest_url
        model.weights_checksum = bundle.bundle_digest
        if bundle.measured_vram_gb is not None:
            model.vram_gb = bundle.measured_vram_gb
        if bundle.license is not None:
            model.license = bundle.license
        # WP-53: same supplied-wins rule as engine/VRAM/license above. A lean
        # re-cert that omits constraints must not erase the ones the previous
        # cert declared -- silently dropping them on re-certification would be
        # the same defect this field exists to fix, one step later.
        if bundle.request_constraints is not None:
            model.request_constraints = bundle.request_constraints
        merged = dict(model.default_params or {})
        merged.update(params)
        model.default_params = merged

    approval = ModelApproval(
        model_id=model.id,
        attested_by=bundle.certified_by,
        vetting_reference=cert_ref,
        checklist=bundle.quality_summary,
    )
    db.add(approval)
    await db.commit()
    await db.refresh(model)

    return ExportReceiptOut(
        ad01_id=str(model.id),
        accepted=True,
        created=created,
        state=model.state,
    )
