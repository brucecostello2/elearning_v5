"""WP-67 — a selected model reaches the code that knows how to run it.

THE FINDING. WP-65 gets the bytes onto a node; WP-66 lets a user select the
model; neither changes WHICH CODE TALKS TO IT.
``animation_generation_task.py:61`` imports ``WanAnimateClient`` at module
level -- not selected from the binding, imported -- so selecting AnimateDiff-SD15
would fetch its weights, record the selection, resolve its endpoint, and then
run Wan's client, Wan's graph and Wan's preprocessors against it.

WHAT TASK 1 MEASURED, and how it differs from what the brief expected:

  * ``clients/graphs/`` held exactly ONE file, ``wan_animate.json``, and graph
    choice is NOT parameterised by model: ``wan_animate_client.py:50`` is a
    module-level ``GRAPH_PATH`` constant.
  * A registry ALREADY EXISTS -- ``register_engine_builder(engine, builder)``
    (``factory.py:47``), populated by ``ivgs-workers/providers/*.py``. It is
    keyed on ENGINE ALONE, and where one engine serves two families the builder
    branches: ``providers/image.py:31-51`` is already a two-branch ``if`` on
    ``binding.stage``, which cannot separate two ANIMATION families at all.
  * ``ModelBinding`` HAS NO ``family`` FIELD (``binding.py:105-121``). So this
    is not "a fourth declared-but-unused mechanism" -- the mechanism does not
    exist, and family has to be derived.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from shared.providers.binding import ModelBinding
from shared.providers.client_registry import (
    AmbiguousFamilyError,
    ClientSpec,
    NoClientForFamilyError,
    can_client_run,
    contract_for,
    family_of,
    registered_families,
    resolve_client,
)
from shared.providers.contracts import (
    ClientContract,
    SceneCapabilities,
    SceneInput,
    preflight,
)


def _binding(name, stage, engine, **params) -> ModelBinding:
    return ModelBinding(
        model_id=uuid.uuid4(), name=name, display_name=name, stage=stage,
        engine=engine, tier="production", endpoint="http://engine:8188",
        default_params=params,
    )


# ---------------------------------------------------------------------------
# TASK 2 — the registry reproduces today's routing
# ---------------------------------------------------------------------------

class TestTheRegistryIsEquivalentToTodaysRouting:
    """A registry that produces exactly today's routing for today's models is
    the correct first state, and this proves the equivalence rather than
    assuming it. Nothing about any client's behaviour changed."""

    @pytest.mark.parametrize("name,stage,engine,expect_path", [
        # The two branches of providers/image.py:31-51, now two registrations.
        ("wan2.2-animate", "animation_generation", "comfyui",
         "clients.wan_animate_client.WanAnimateClient"),
        ("flux1-schnell", "image_generation", "comfyui",
         "clients.flux_client.FluxClient"),
        # video_generation's two clients.
        ("CogVideoX-5b", "video_generation", "cogvideox",
         "clients.cogvideox_client.CogVideoXClient"),
        ("Wan2.2-T2V", "video_generation", "cogvideox",
         "clients.wan21_client.Wan21Client"),
        # talking_head's two.
        ("latentsync", "talking_head", "latentsync",
         "clients.latentsync_client.LatentSyncClient"),
        # tts's two.
        ("kokoro-82m", "voiceover_tts", "kokoro",
         "clients.kokoro_client.KokoroClient"),
        ("XTTS-v2", "voiceover_tts", "coqui",
         "clients.coqui_client.CoquiClient"),
        # the three LLM stages, one client.
        ("llama-3.3-70b-transcript", "transcript_refinement", "vllm",
         "clients.vllm_client.VLLMClient"),
        ("llama-3.3-70b-storyboard", "storyboard_generation", "vllm",
         "clients.vllm_client.VLLMClient"),
        ("Llama-3.3-70B-Instruct", "translation", "vllm",
         "clients.vllm_client.VLLMClient"),
        ("FFmpeg-composition", "composition", "ffmpeg",
         "clients.ffmpeg_client.FFmpegClient"),
    ])
    def test_every_live_model_resolves_to_the_client_it_uses_today(
        self, name, stage, engine, expect_path
    ):
        assert resolve_client(_binding(name, stage, engine)).client_path == expect_path

    def test_one_engine_now_separates_two_animation_families(self):
        """The thing the engine-keyed registry could not do. Both are
        `comfyui`, both are `animation_generation`, and they are different
        clients with different contracts."""
        wan = resolve_client(_binding("wan2.2-animate", "animation_generation", "comfyui"))
        ad = resolve_client(_binding("AnimateDiff-SD15", "animation_generation", "comfyui"))
        assert wan.client_path != ad.client_path
        assert wan.contract.requires != ad.contract.requires

    def test_the_registry_accepts_an_orm_row_as_well_as_a_binding(self):
        """A `ModelBinding` carries strings; a `Model` row carries enum
        members. Both must key the same, or asking "is there a client for this
        row?" answers no for every row -- which it did, silently, until
        `_key` existed."""
        from shared.models.model_store import ModelEngine, ModelStage

        class _Row:
            name = "flux1-schnell"
            stage = ModelStage.IMAGE_GENERATION
            engine = ModelEngine.COMFYUI
            default_params = {}

        assert resolve_client(_Row()).family == "flux"


class TestFamilyResolution:
    def test_an_explicit_family_wins(self):
        b = _binding("anything-at-all", "image_generation", "comfyui", family="flux")
        assert family_of(b) == "flux"
        assert resolve_client(b).client_path == "clients.flux_client.FluxClient"

    def test_the_materialization_spelling_is_also_read(self):
        b = _binding("x", "animation_generation", "comfyui", weight_family="wan_animate")
        assert family_of(b) == "wan_animate"

    def test_a_name_pattern_covers_rows_that_carry_no_family(self):
        """Every live Model row carries no family. Backfilling one by migration
        would be guessing at rows nobody has re-certified; a pattern declared
        BESIDE the client that claims it is auditable in one place."""
        assert family_of(_binding("wan2.2-animate", "a", "b")) == "wan_animate"
        assert family_of(_binding("AnimateDiff-SD15", "a", "b")) == "animatediff"

    def test_an_unrecognised_model_falls_back_to_its_own_name(self):
        """So the refusal names something a human recognises rather than
        'unknown'."""
        assert family_of(_binding("Zephyr-9000", "a", "b")) == "zephyr-9000"


class TestTheNoClientRefusal:
    def test_it_is_named_and_actionable(self):
        """THE STATE ANIMATEDIFF WOULD HAVE HIT TODAY, before this package."""
        with pytest.raises(NoClientForFamilyError) as exc:
            resolve_client(_binding("MimicMotion", "animation_generation", "comfyui"))
        assert exc.value.reason == "no_client_for_family"
        text = str(exc.value)
        assert "MimicMotion" in text
        assert "no client for family" in text
        assert "certified, fetched and selected" in text

    def test_it_lists_what_clients_DO_exist_for_the_stage(self):
        with pytest.raises(NoClientForFamilyError) as exc:
            resolve_client(_binding("MimicMotion", "animation_generation", "comfyui"))
        assert "wan_animate" in str(exc.value)
        assert "animatediff" in str(exc.value)

    def test_a_binding_with_no_name_at_all_is_a_different_error(self):
        with pytest.raises(AmbiguousFamilyError):
            resolve_client(_binding("", "image_generation", "comfyui"))

    def test_the_two_resolution_errors_have_distinct_reasons(self):
        assert (
            NoClientForFamilyError.reason != AmbiguousFamilyError.reason
        )


# ---------------------------------------------------------------------------
# TASK 2 — the capability contract, and pre-flight
# ---------------------------------------------------------------------------

class TestTheStagesLawBecomesTheClientsRequirement:
    """`animation_generation_task.py:481` refuses a personless reference as a
    property of the STAGE. It is correct for Wan2.2-Animate -- pose reenactment
    hallucinates a subject rather than declining -- and wrong for the stage:
    AnimateDiff needs no person at all."""

    def test_wan_declares_the_person_requirement(self):
        c = contract_for("animation_generation", "comfyui", "wan_animate")
        assert SceneInput.PERSON_IN_REFERENCE in c.requires
        assert SceneInput.REFERENCE_CLIP in c.requires

    def test_animatediff_declares_none_of_them(self):
        c = contract_for("animation_generation", "comfyui", "animatediff")
        assert c.requires == frozenset({SceneInput.PROMPT})
        assert SceneInput.PERSON_IN_REFERENCE not in c.requires

    def test_the_same_scene_is_refused_by_one_and_accepted_by_the_other(self):
        """The whole point, in one assertion. A maths scene has a prompt and no
        person; the stage-level law refused it, and one of these two clients
        can render it."""
        scene = SceneCapabilities.of(SceneInput.PROMPT)
        wan = preflight(
            contract_for("animation_generation", "comfyui", "wan_animate"), scene
        )
        ad = preflight(
            contract_for("animation_generation", "comfyui", "animatediff"), scene
        )
        assert not wan.ok
        assert ad.ok

    def test_the_refusal_names_what_is_missing_and_what_to_do(self):
        scene = SceneCapabilities.of(SceneInput.PROMPT, SceneInput.REFERENCE_IMAGE)
        r = preflight(
            contract_for("animation_generation", "comfyui", "wan_animate"), scene
        )
        assert not r.ok
        assert r.reason == "unsatisfiable_inputs"
        assert "person_in_reference" in r.message
        assert "hallucinates one" in r.message

    def test_a_fully_satisfied_scene_passes(self):
        scene = SceneCapabilities.of(
            SceneInput.PROMPT, SceneInput.REFERENCE_IMAGE,
            SceneInput.PERSON_IN_REFERENCE, SceneInput.REFERENCE_CLIP,
        )
        assert preflight(
            contract_for("animation_generation", "comfyui", "wan_animate"), scene
        ).ok

    def test_optional_inputs_are_not_required(self):
        c = contract_for("video_generation", "cogvideox", "cogvideox")
        assert SceneInput.REFERENCE_IMAGE in c.optional
        assert preflight(c, SceneCapabilities.of(SceneInput.PROMPT)).ok

    def test_preflight_through_a_binding_resolves_the_client_first(self):
        r = can_client_run(
            _binding("wan2.2-animate", "animation_generation", "comfyui"),
            SceneCapabilities.of(SceneInput.PROMPT),
        )
        assert not r.ok

    def test_no_client_is_a_DIFFERENT_failure_from_cannot_run_this_scene(self):
        """Collapsing them would tell an operator to do the wrong thing: one
        needs a developer, the other needs a different scene or model."""
        with pytest.raises(NoClientForFamilyError):
            can_client_run(
                _binding("MimicMotion", "animation_generation", "comfyui"),
                SceneCapabilities.of(SceneInput.PROMPT),
            )


# ---------------------------------------------------------------------------
# TASK 3 — the new family
# ---------------------------------------------------------------------------

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / "ivgs-workers" / "clients" / "graphs" / "animatediff_sd15.json"
)


class TestAnimateDiffWasChosenOnEvidence:
    """MEASURED against MBCP's own certified graphs, not preferred:

      animatediff-sd15.json   8 nodes, EMPTY latent -> prompt only
      mimicmotion.json       16 nodes, LoadImage + VHS_LoadVideo + GetPoses

    MimicMotion has the same contract that makes Wan unusable for a mathematics
    lesson. AnimateDiff needs a prompt.
    """

    def test_the_graph_ships_and_is_the_certified_one(self):
        assert _GRAPH.is_file()
        graph = json.loads(_GRAPH.read_text())
        types = {n["class_type"] for n in graph.values()}
        assert "ADE_AnimateDiffLoaderGen1" in types
        assert "ADE_EmptyLatentImageLarge" in types

    def test_it_starts_from_an_empty_latent_which_is_why_it_needs_no_still(self):
        graph = json.loads(_GRAPH.read_text())
        assert not any(
            n["class_type"] in ("LoadImage", "VHS_LoadVideo") for n in graph.values()
        )

    def test_it_is_smaller_than_the_family_that_was_not_chosen(self):
        graph = json.loads(_GRAPH.read_text())
        assert len(graph) == 8

    def test_the_motion_module_is_a_literal_not_a_slot(self):
        """MBCP certified the model against THIS module. A slot would let it be
        swapped silently, and the attestation would then describe a different
        render."""
        graph = json.loads(_GRAPH.read_text())
        loader = next(
            n for n in graph.values()
            if n["class_type"] == "ADE_AnimateDiffLoaderGen1"
        )
        assert loader["inputs"]["model_name"] == "mm_sd_v15_v2.ckpt"

    def test_every_slot_the_graph_declares_is_one_the_params_supply(self):
        """A slot the client cannot fill reaches ComfyUI as the literal string
        '{seed}', which some sockets accept -- producing a render that looks
        fine and is wrong."""
        import re

        text = _GRAPH.read_text()
        slots = set(re.findall(r"\{([a-z_]+)\}", text))
        # `ivgs-workers` is on pythonpath (pyproject `pythonpath`), so the
        # client is importable from this tree.
        from clients.animatediff_client import AnimateDiffParams

        supplied = set(AnimateDiffParams().as_context())
        assert slots <= supplied, f"unfillable slots: {sorted(slots - supplied)}"
