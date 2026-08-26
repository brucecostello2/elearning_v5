"""WP-65 Task 5 -- an ingested model's engine is the engine MBCP certified it against.

THE MEASUREMENT. MBCP serves its whole animation line -- Wan2.2-Animate,
MimicMotion and AnimateDiff-SD15 alike -- on one ComfyUI runtime
(``mbcp_adapters/comfyui.py``: one ComfyUIAdapter, one graph per family), so
the engine is ``comfyui`` for all three. IVGS's store showed ``animatediff``.

WHERE THE TRANSFORM IS. ``ivgs-api/app/api/ad01_ingest.py:156`` --
``engine = bundle.engine or _STAGE_DEFAULT_ENGINE.get(stage)``. IVGS was not
overriding a value MBCP sent; it was supplying its own when MBCP sent none, and
its ANIMATION_GENERATION default was ``ANIMATEDIFF``.

IT WAS ALREADY FIXED, AND NOTHING PINNED IT. Commit ``d536967`` (WP-46) changed
that default to ``COMFYUI``. No test asserted it, so the next person to "tidy"
the table would have reverted it silently, and the three rows written before
that commit still carry the old value because ``models`` registration fields
are immutable on re-ingest unless the bundle supplies them (``:194-195``).

This file is the pin. The row correction itself is data, and is recorded in the
WP-65 report with a before/after per row.
"""
from __future__ import annotations

import pytest

from app.api.ad01_ingest import _STAGE_DEFAULT_ENGINE
from shared.models.model_store import ModelEngine, ModelStage


class TestIngestEngineDefaults:
    def test_animation_defaults_to_comfyui_not_animatediff(self):
        """The assertion WP-46's fix has been missing since d536967.

        RED against the pre-WP-46 tree, where this value was ANIMATEDIFF.
        """
        assert (
            _STAGE_DEFAULT_ENGINE[ModelStage.ANIMATION_GENERATION]
            is ModelEngine.COMFYUI
        ), (
            "MBCP serves its whole animation line on ComfyUI; defaulting to "
            "'animatediff' writes an engine MBCP never certified against, and "
            "'animatediff' has no host on this fleet"
        )

    def test_every_pipeline_stage_has_a_default_engine(self):
        """A stage with no default makes ingest 422 on a bundle that omits the
        engine (``ad01_ingest.py:157-168``), so a missing row is a seam
        failure, not a cosmetic gap."""
        required = {
            ModelStage.TRANSCRIPT_REFINEMENT,
            ModelStage.STORYBOARD_GENERATION,
            ModelStage.TRANSLATION,
            ModelStage.IMAGE_GENERATION,
            ModelStage.VIDEO_GENERATION,
            ModelStage.ANIMATION_GENERATION,
            ModelStage.VOICEOVER_TTS,
            ModelStage.TALKING_HEAD,
        }
        missing = required - set(_STAGE_DEFAULT_ENGINE)
        assert not missing, f"stages with no default engine: {sorted(s.value for s in missing)}"

    @pytest.mark.parametrize("stage", list(_STAGE_DEFAULT_ENGINE))
    def test_no_stage_defaults_to_an_engine_with_no_host(self, stage):
        """The consequence that makes this more than a naming tidy-up.

        ``animatediff`` resolves to ``IVGS_ANIMATEDIFF_URL``
        (``shared/providers/binding.py:31``), whose default is node-04:8188 --
        the FLUX ComfyUI, which mounts only ``checkpoints`` and has no
        WanVideo/AnimateDiff nodes installed (probed 2026-08-26). A default
        that names an unhosted engine points new ingests at an endpoint that
        cannot run them.
        """
        from shared.weights.placement import UNHOSTED_ENGINES

        engine = _STAGE_DEFAULT_ENGINE[stage].value
        assert engine not in UNHOSTED_ENGINES, (
            f"stage {stage.value!r} defaults to engine {engine!r}, which no "
            f"node on this fleet hosts: {UNHOSTED_ENGINES.get(engine)}"
        )


class TestEngineDisagreementIsVisible:
    def test_animatediff_is_declared_unhosted_with_its_reason(self):
        """So that a row still carrying it is explained rather than merely
        broken. This is the state the three uncorrected rows were in."""
        from shared.weights.placement import UNHOSTED_ENGINES

        assert "animatediff" in UNHOSTED_ENGINES
        assert "comfyui" in UNHOSTED_ENGINES["animatediff"]
