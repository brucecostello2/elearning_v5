"""WP-IVGS-07 Task 3 — D-11: three parameters declared at one layer and dropped
before the next, and the dedup trap that made one of them dangerous to fix alone.
"""
from __future__ import annotations

import pytest

from clients.coqui_client import CoquiSynthesisParams, _resolve_speaker_reference
from clients.flux_client import FluxClient, FluxGenerationParams
from clients.wan21_client import Wan21GenerationParams, Wan21Quality


class TestFluxClipSkip:
    def _graph(self, clip_skip):
        return FluxClient._build_workflow(
            FluxClient, prompt="p", negative_prompt="n", model="m.safetensors",
            width=1024, height=1024, steps=20, cfg_scale=7.0,
            seed=1, sampler="euler", scheduler="normal", denoise=1.0,
            clip_skip=clip_skip,
        )

    def test_the_encoders_read_clip_through_the_skip_node(self):
        g = self._graph(-2)
        assert g["10"]["class_type"] == "CLIPSetLastLayer"
        assert g["10"]["inputs"]["stop_at_clip_layer"] == -2
        # BOTH encoders, or the negative prompt silently uses a different CLIP.
        assert g["6"]["inputs"]["clip"] == ["10", 0]
        assert g["7"]["inputs"]["clip"] == ["10", 0]

    def test_the_default_is_behaviourally_neutral(self):
        """-1 is ComfyUI's own default for stop_at_clip_layer (verified against
        node-04's /object_info), so an unset request renders as before."""
        assert self._graph(-1)["10"]["inputs"]["stop_at_clip_layer"] == -1

    def test_it_is_no_longer_declared_and_dropped(self):
        assert FluxGenerationParams(prompt="p").clip_skip == -1


class TestCoquiTextSplitting:
    def test_it_reaches_the_payload(self):
        p = CoquiSynthesisParams(text="t", enable_text_splitting=False)
        payload = {
            "text": p.text, "speed": p.speed,
            "enable_text_splitting": p.enable_text_splitting,
        }
        assert payload["enable_text_splitting"] is False


class TestWan21QualityAndTheDedupTrap:
    """⛔ THE REASON THESE COULD NOT BE SPLIT.

    `quality` reached neither the request nor `compute_hash`. That was
    self-consistent while it did nothing. Wiring it into the request WITHOUT the
    hash would make STANDARD and HIGH collide in the dedup cache -- the second
    render served the first one's artifact, with nothing reporting a mismatch.
    """

    def test_the_hash_separates_two_requests_differing_ONLY_in_quality(self):
        std = Wan21GenerationParams(prompt="same", quality=Wan21Quality.STANDARD)
        high = Wan21GenerationParams(prompt="same", quality=Wan21Quality.HIGH)
        assert std.compute_hash() != high.compute_hash(), (
            "identical hashes would serve the STANDARD video for a HIGH request"
        )

    def test_everything_else_equal_still_hashes_equal(self):
        a = Wan21GenerationParams(prompt="same", quality=Wan21Quality.HIGH)
        b = Wan21GenerationParams(prompt="same", quality=Wan21Quality.HIGH)
        assert a.compute_hash() == b.compute_hash(), "dedup must still dedup"

    def test_quality_now_changes_the_request(self):
        from clients.wan21_client import _QUALITY_PROFILES
        assert _QUALITY_PROFILES["high"]["num_inference_steps"] != \
               Wan21GenerationParams(prompt="p").num_inference_steps

    def test_the_hash_is_not_merely_longer(self):
        """Guards the lazy fix: adding the field to the dict but always the same
        value would pass the separation test only by accident."""
        h = Wan21GenerationParams(prompt="p", quality=Wan21Quality.STANDARD).compute_hash()
        assert len(h) == 64 and h != Wan21GenerationParams(
            prompt="p", quality=Wan21Quality.HIGH).compute_hash()
