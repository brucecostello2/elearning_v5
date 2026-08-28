"""WP-67 Task 2 — (stage, engine, family) -> client, by declaration.

WHAT WAS ALREADY THERE, MEASURED 2026-08-26. A registry exists:
``register_engine_builder(engine, builder)`` (``factory.py:47``), populated at
import by ``ivgs-workers/providers/{llm,image,video,tts,talking_head}.py``.
Seven engines are registered.

**It is keyed on ENGINE ALONE, and that is the gap.** One engine key can serve
more than one model FAMILY, and where it does, the builder branches:

    # ivgs-workers/providers/image.py:31-51
    def build_comfyui(binding, **kwargs):
        if binding.stage == "animation_generation":
            return WanAnimateClient(...)
        return FluxClient(...)

That is the "chain of ifs" this task exists to replace, and it is already two
branches deep on a single engine. A third ComfyUI family -- AnimateDiff,
MimicMotion, motion graphics -- means a third branch, and the branch is on
``stage``, which cannot separate two animation families from each other at all.

**``ModelBinding`` HAS NO ``family`` FIELD.** Measured: its fields are
``model_id, name, display_name, stage, engine, tier, endpoint, node_id,
vram_requirement_mb, dynamically_loadable, default_params, selection_id,
selected_by, rationale`` (``binding.py:105-121``). So this is NOT a fourth
declared-but-unused mechanism -- the mechanism does not exist. Family is derived
here, from ``default_params`` (where the AD-01 ingest parks everything MBCP
sends that has no column, ``ad01_ingest.py:136-147``) with a fallback to the
model NAME, so today's models resolve without any data migration.

WHAT THIS MODULE DELIBERATELY DOES NOT DO. It does not import a client. It maps
a binding to a family and a CONTRACT, and names the factory to call. The import
stays in the worker layer, because ``shared/`` is imported by ``ivgs-api`` too
and the API has no business loading a ComfyUI client to answer "can this model
run this scene?".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from collections.abc import Iterable
from typing import Any, Callable

from shared.providers.contracts import ClientContract, SceneInput

# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class ClientResolutionError(Exception):
    """Base for registry refusals. Each carries an actionable ``reason``."""

    reason = "client_resolution_failed"


class NoClientForFamilyError(ClientResolutionError):
    """No client is registered for this model's family.

    THE HONEST REFUSAL, and the one AnimateDiff-SD15 would hit today. Before
    WP-67 the selection resolved, the endpoint resolved, and
    ``WanAnimateClient`` ran against it -- the model blindfolded in a new way.
    """

    reason = "no_client_for_family"


class AmbiguousFamilyError(ClientResolutionError):
    """A model's family could not be determined at all."""

    reason = "family_unknown"


# ---------------------------------------------------------------------------
# the registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClientSpec:
    """One registered client: its contract, and how to build it."""

    contract: ClientContract
    #: Dotted path to the client class, resolved by the worker layer. A STRING
    #: on purpose: this module is imported by ivgs-api, which must be able to
    #: answer "is there a client for this?" without importing one.
    client_path: str
    #: Graph or template this client renders through, where it has one.
    graph: str | None = None
    #: Extra keys the builder needs.
    build_kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def family(self) -> str:
        return self.contract.family


_REGISTRY: dict[tuple[str, str, str], ClientSpec] = {}

#: MBCP's runtime engine name for BOTH voiceover families. Not a family name:
#: MBCP serves XTTS-v2 and Kokoro on one `tts_coqui` adapter and certifies both
#: with `engine="tts"` (`scripts/seed_stage.py:543,576`).
MBCP_TTS_RUNTIME_ENGINE = "tts"

#: The engine key each voiceover family is registered under TODAY. Read, never
#: written -- the runtime-name registration below derives from these so it
#: cannot drift from the entries that serve the live rows.
_ENGINE_BY_TTS_FAMILY: dict[str, str] = {"xtts": "coqui", "kokoro": "kokoro"}

#: family -> the names/patterns that resolve to it, for models whose rows
#: predate any family field. Checked in order; first match wins.
_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = []


def register_client(
    spec: ClientSpec, *, name_patterns: tuple[str, ...] = ()
) -> None:
    """Declare a client. Re-registering the same key replaces it."""
    key = (spec.contract.stage, spec.contract.engine, spec.contract.family)
    _REGISTRY[key] = spec
    for pattern in name_patterns:
        _NAME_PATTERNS.append((re.compile(pattern, re.I), spec.contract.family))


def registered_families(stage: str | None = None) -> tuple[str, ...]:
    """Every family with a client, optionally for one stage."""
    return tuple(sorted(
        {f for (s, _e, f) in _REGISTRY if stage is None or s == stage}
    ))


def contract_for(stage: str, engine: str, family: str) -> ClientContract | None:
    spec = _REGISTRY.get((stage, engine, family))
    return spec.contract if spec else None


def engines_for_families(stage: str, families: Iterable[str]) -> frozenset[str]:
    """The engine keys that serve ``families`` on ``stage``.

    WP-IVGS-09b. A STAGE IS NOT A MEDIUM, and on ``animation_generation`` the
    difference is load-bearing: ``wan_animate`` and ``animatediff`` serve the
    ``animation`` medium on engine ``comfyui``, while ``maths_motion`` serves
    ``motion_graphics`` on engine ``motion_graphics``. Anything that offers an
    operator "the models for this stage" offers both, and one of them cannot
    run the other's scene -- Wan2.2-Animate needs a person in a reference still
    and refuses a personless one by name.

    Derived from the registry rather than restated beside it. A second list of
    "which engines are animation engines" is a second definition, and this
    module exists to be the first one.

    Returns an EMPTY set for a family nobody registered, and the caller must
    decide what that means -- offering everything would be the wrong answer,
    which is why this does not fall back.
    """
    wanted = set(families)
    return frozenset(
        engine for (s, engine, family) in _REGISTRY
        if s == stage and family in wanted
    )


def family_of(binding: Any) -> str:
    """The model family for a binding.

    Order, and the reason for it:

      1. ``default_params["family"]`` -- what MBCP would send, if it sent one.
      2. ``default_params["weight_family"]`` -- the materialization-map spelling.
      3. A NAME PATTERN registered alongside the client. Today's Model Store
         rows carry no family at all, and inventing a migration to backfill one
         would be guessing at rows nobody has re-certified. A pattern declared
         BESIDE the client that claims it is auditable in one place.
      4. The model name itself, lowercased -- so an unregistered model produces
         a refusal naming something a human recognises rather than "unknown".
    """
    params = getattr(binding, "default_params", None) or {}
    if isinstance(params, dict):
        for key in ("family", "weight_family"):
            value = params.get(key)
            if value:
                return str(value)

    name = str(getattr(binding, "name", "") or "")
    for pattern, family in _NAME_PATTERNS:
        if pattern.search(name):
            return family
    return name.lower()


def _key(value: Any) -> str:
    """The registry key for a stage or engine, from a binding OR an ORM row.

    A ``ModelBinding`` carries plain strings (``binding.py:111-112``); a
    ``Model`` row carries ``ModelStage`` / ``ModelEngine`` enum members. Both
    must resolve to the same key, or asking "does a client exist for this row?"
    silently answers no for every row -- which is exactly what happened before
    this function existed: ``str(ModelStage.IMAGE_GENERATION)`` is
    ``'ModelStage.IMAGE_GENERATION'``, and nothing is registered under that.
    """
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def resolve_client(binding: Any) -> ClientSpec:
    """The client for this binding, or a NAMED refusal.

    Accepts a ``ModelBinding`` or a ``Model`` row -- see :func:`_key`.

    :raises AmbiguousFamilyError: the binding names no model at all.
    :raises NoClientForFamilyError: nothing is registered for its family.
    """
    stage = _key(getattr(binding, "stage", None))
    engine = _key(getattr(binding, "engine", None))
    family = family_of(binding)
    if not family:
        raise AmbiguousFamilyError(
            f"cannot determine a model family for binding {binding!r}; without "
            f"one there is no way to choose a client"
        )

    spec = _REGISTRY.get((stage, engine, family))
    if spec is not None:
        return spec

    known = registered_families(stage)
    raise NoClientForFamilyError(
        f"model {getattr(binding, 'name', family)!r} is selected for stage "
        f"{stage!r} on engine {engine!r}, but IVGS has no client for family "
        f"{family!r}. "
        + (
            f"Clients exist for: {', '.join(known)}."
            if known
            else f"No client is registered for stage {stage!r} at all."
        )
        + " A model can be certified, fetched and selected and still have "
        "nothing in IVGS that knows how to call it; that is this state."
    )


def can_client_run(binding: Any, scene: Any) -> Any:
    """Pre-flight: resolve the client, then evaluate its contract on the scene.

    Returns a ``PreflightResult``. Raises only the resolution errors above --
    "no client" is a different failure from "this client cannot run this
    scene", and collapsing them would tell an operator to do the wrong thing.
    """
    from shared.providers.contracts import preflight

    spec = resolve_client(binding)
    return preflight(spec.contract, scene)


# ---------------------------------------------------------------------------
# TODAY'S CLIENTS, registered so the registry reproduces current routing
# ---------------------------------------------------------------------------
#
# A registry that produces exactly today's routing for today's models is the
# correct first state, and the tests prove that equivalence rather than
# assuming it. Nothing here changes any client's behaviour.

def register_builtin_clients() -> None:
    """Declare the clients IVGS ships. Idempotent."""

    # --- animation_generation -------------------------------------------
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="wan_animate",
                display_name="Wan2.2-Animate",
                stage="animation_generation",
                engine="comfyui",
                # THE STAGE CONSTANT BECOMES A CLIENT FACT. This is the
                # requirement `animation_generation_task.py:481` enforces as a
                # property of the stage; it is Wan's, and only Wan's.
                requires=frozenset({
                    SceneInput.PROMPT,
                    SceneInput.REFERENCE_IMAGE,
                    SceneInput.PERSON_IN_REFERENCE,
                    SceneInput.REFERENCE_CLIP,
                }),
                accepts_params=frozenset({
                    "width", "height", "fps", "steps", "cfg", "seed",
                    "served_model_name",
                }),
                produces="video/mp4",
                notes=(
                    "Pose reenactment. With no subject in the reference it does "
                    "not decline -- it hallucinates one, which is why the person "
                    "requirement is hard rather than advisory."
                ),
            ),
            client_path="clients.wan_animate_client.WanAnimateClient",
            graph="graphs/wan_animate.json",
        ),
        name_patterns=(r"wan.?2\.?2.?animate", r"^wan_animate$"),
    )

    # WP-67 Task 3. The SECOND animation family, and the proof that the
    # registry admits one without touching the first. Chosen on measured
    # evidence: MBCP's certified graph is 8 nodes and starts from an EMPTY
    # latent, so it needs a prompt and nothing else -- while MimicMotion's is
    # 16 nodes and needs a still AND a driving video, the same contract that
    # makes Wan unusable for a mathematics lesson.
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="animatediff",
                display_name="AnimateDiff-SD15",
                stage="animation_generation",
                engine="comfyui",
                # NO person, NO reference image, NO driving clip. This is the
                # whole reason the family was chosen, and stating it here is
                # what lets a selection screen tell the two animation families
                # apart before anything is dispatched.
                requires=frozenset({SceneInput.PROMPT}),
                accepts_params=frozenset({
                    "prompt", "negative_prompt", "served_model_name",
                    "output_width", "output_height", "num_frames",
                    "output_fps", "seed",
                }),
                produces="video/mp4",
                notes=(
                    "Text-to-video. Needs the AnimateDiff-Evolved custom nodes "
                    "(ADE_*), which no ComfyUI on this fleet currently has -- "
                    "an engine-image problem, not a weights problem."
                ),
            ),
            client_path="clients.animatediff_client.AnimateDiffClient",
            graph="graphs/animatediff_sd15.json",
        ),
        name_patterns=(r"animatediff",),
    )

    # --- image_generation ------------------------------------------------
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="flux",
                display_name="FLUX",
                stage="image_generation",
                engine="comfyui",
                requires=frozenset({SceneInput.PROMPT}),
                accepts_params=frozenset({
                    "width", "height", "steps", "cfg", "seed", "sampler",
                }),
                produces="image/png",
                notes="Text-to-image. Needs a prompt and nothing else.",
            ),
            client_path="clients.flux_client.FluxClient",
        ),
        name_patterns=(r"flux",),
    )

    # --- video_generation ------------------------------------------------
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="cogvideox",
                display_name="CogVideoX-5b",
                stage="video_generation",
                engine="cogvideox",
                requires=frozenset({SceneInput.PROMPT}),
                optional=frozenset({SceneInput.REFERENCE_IMAGE}),
                accepts_params=frozenset({
                    "width", "height", "num_frames", "fps", "guidance_scale",
                }),
                produces="video/mp4",
            ),
            client_path="clients.cogvideox_client.CogVideoXClient",
        ),
        name_patterns=(r"cogvideo",),
    )
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="wan21",
                display_name="Wan2.1 / Wan2.2-T2V",
                stage="video_generation",
                engine="cogvideox",
                requires=frozenset({SceneInput.PROMPT}),
                accepts_params=frozenset({"width", "height", "fps"}),
                produces="video/mp4",
                notes=(
                    "Registered under engine 'cogvideox' because that is what "
                    "the live Wan2.2-T2V row carries, and the row is the truth "
                    "about what endpoint resolves."
                ),
            ),
            client_path="clients.wan21_client.Wan21Client",
        ),
        name_patterns=(r"wan.?2\.?[12].?t2v", r"^wan21$"),
    )

    # --- the LLM stages --------------------------------------------------
    #
    # One client, three stages. Registered per stage rather than once, because
    # the key is (stage, engine, family) and a model row exists per stage --
    # AD-01.5.2 records one row per stage, which is why llama-3.3-70b-transcript
    # and llama-3.3-70b-storyboard are two rows for one served model.
    for _llm_stage in (
        "transcript_refinement", "storyboard_generation", "translation",
    ):
        register_client(
            ClientSpec(
                contract=ClientContract(
                    family="vllm_chat",
                    display_name="vLLM chat model",
                    stage=_llm_stage,
                    engine="vllm",
                    requires=frozenset({SceneInput.PROMPT}),
                    accepts_params=frozenset({
                        "temperature", "max_tokens", "top_p",
                    }),
                    produces="text/plain",
                ),
                client_path="clients.vllm_client.VLLMClient",
            ),
            name_patterns=(),
        )
    # Registered ONCE, after the loop: a pattern list is global, so registering
    # it per stage would add three identical patterns.
    _NAME_PATTERNS.append((re.compile(r"llama|qwen|mistral", re.I), "vllm_chat"))

    # --- composition -----------------------------------------------------
    #
    # ffmpeg is not a generative model and has no weights, but it IS an AD-01
    # engine row (IVGS commit e613e84 added it to ModelEngine specifically to
    # unblock MBCP composition exports) and FFmpeg-composition is the approved
    # default for the stage. Registering it keeps the surface honest: without
    # this the admin page would say "no client -- IVGS cannot run this model"
    # about the compositor that assembles every render.
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="ffmpeg_concat",
                display_name="FFmpeg composition",
                stage="composition",
                engine="ffmpeg",
                requires=frozenset({SceneInput.STRUCTURED_SCENE_DATA}),
                produces="video/mp4",
                notes="Local binary, not a served model. No weights, no endpoint.",
            ),
            client_path="clients.ffmpeg_client.FFmpegClient",
        ),
        name_patterns=(r"ffmpeg",),
    )

    # --- motion graphics (WP-68 Task 2) ----------------------------------
    #
    # Registered under `animation_generation`, not a new stage: the orchestrator
    # routes media types to three stages and nothing else
    # (`pipeline_orchestrator_v2.py:653-655`), and a fourth stage would need a
    # queue, a worker and a task. The family distinguishes it from Wan inside
    # the stage it already has.
    #
    # ITS INPUTS ARE STRUCTURED SCENE DATA, NOT A STILL. That is the whole
    # difference: Wan needs a person in a picture, AnimateDiff needs a prompt,
    # and this needs {"template": "place_value_split", "number": 23}. A
    # renderer that draws digits cannot misspell them, which is the failure
    # RULE 1 exists to route around.
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="maths_motion",
                display_name="Maths motion graphics",
                stage="animation_generation",
                engine="motion_graphics",
                requires=frozenset({SceneInput.STRUCTURED_SCENE_DATA}),
                accepts_params=frozenset({
                    "template", "number", "top", "bottom", "step", "column",
                    "label",
                }),
                produces="video/mp4",
                notes=(
                    "Template-driven. No weights by nature, and no renderer is "
                    "deployed on this fleet -- the templates are proven against "
                    "a local rasteriser and the stand-up is an operator action."
                ),
            ),
            client_path="clients.motion_graphics_client.MotionGraphicsClient",
            graph=None,
        ),
        name_patterns=(r"maths.?motion", r"motion.?graphics"),
    )

    # --- talking_head ----------------------------------------------------
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="latentsync",
                display_name="LatentSync",
                stage="talking_head",
                engine="latentsync",
                requires=frozenset({
                    SceneInput.REFERENCE_CLIP, SceneInput.AUDIO_TRACK,
                }),
                accepts_params=frozenset({"mode", "output_fps"}),
                produces="video/mp4",
            ),
            client_path="clients.latentsync_client.LatentSyncClient",
        ),
        name_patterns=(r"latentsync",),
    )
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="sadtalker",
                display_name="SadTalker",
                stage="talking_head",
                engine="sadtalker",
                requires=frozenset({
                    SceneInput.REFERENCE_IMAGE, SceneInput.AUDIO_TRACK,
                }),
                produces="video/mp4",
                notes="Still + audio, unlike LatentSync which drives a clip.",
            ),
            client_path="clients.sadtalker_client.SadTalkerClient",
        ),
        name_patterns=(r"sadtalker",),
    )

    # --- voiceover_tts ---------------------------------------------------
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="xtts",
                display_name="XTTS-v2",
                stage="voiceover_tts",
                engine="coqui",
                requires=frozenset({SceneInput.PROMPT}),
                # WP-IVGS-06 Task 3 (D-7). ONLY `speed`, and that is the honest
                # answer today rather than the flattering one.
                #
                # The client sends `temperature`, `top_k`, `top_p`,
                # `length_penalty` and `repetition_penalty`, the engine's
                # `TTSRequest` declares all five, and `Xtts.inference` genuinely
                # supports every one -- measured on node-04. But `ivgs-coqui`'s
                # `server.py` builds `kwargs = {text, language, speed}` and
                # forwards nothing else, so all five are accepted and dropped.
                #
                # WIDENED 2026-08-28 by WP-IVGS-07 Task 6, in the SAME deploy
                # window as the engine rebuild that made them real. The rule
                # this follows in both directions: the surface must never
                # advertise ahead of the deploy, and must not stay narrowed
                # after it.
                #
                # `ivgs-coqui:coqui-v5.2.9-params` now forwards all of these to
                # `Xtts.inference`. Two were proven to move the output on the
                # deployed engine rather than assumed:
                #   temperature           -- mean intra-pair LTAS 0.99767 @0.05
                #                            vs 0.97369 @0.99. Before the
                #                            rebuild the ordering was INVERTED
                #                            (0.92024 vs 0.95473), i.e. noise.
                #   enable_text_splitting -- 248460 B / 5.18 s (True) vs
                #                            273036 B / 5.69 s (False).
                # ⚠ `top_k`, `top_p`, `length_penalty` and `repetition_penalty`
                # travel on the same `kwargs.update` line and are accepted by
                # `Xtts.inference`, but were NOT individually demonstrated.
                accepts_params=frozenset({
                    "speed", "temperature", "top_k", "top_p",
                    "length_penalty", "repetition_penalty",
                    "enable_text_splitting",
                }),
                produces="audio/wav",
            ),
            client_path="clients.coqui_client.CoquiClient",
        ),
        name_patterns=(r"xtts",),
    )
    register_client(
        ClientSpec(
            contract=ClientContract(
                family="kokoro",
                display_name="Kokoro",
                stage="voiceover_tts",
                engine="kokoro",
                requires=frozenset({SceneInput.PROMPT}),
                # WP-IVGS-06 Task 3. `speed` only, and for Kokoro this is FINAL
                # rather than pending an engine fix: its server states in its
                # own docstring that "Kokoro uses only text / language / speed;
                # the XTTS-specific fields and speaker_wav are accepted for
                # contract symmetry". Kokoro does not voice-clone either.
                accepts_params=frozenset({"speed"}),
                produces="audio/wav",
            ),
            client_path="clients.kokoro_client.KokoroClient",
        ),
        name_patterns=(r"kokoro",),
    )

    # --- voiceover_tts on the RUNTIME engine name -------------------------
    #
    # WP-IVGS-04 Task 1, closing WP-IVGS-03 D-1.
    #
    # THE TWO ENTRIES ABOVE ARE KEYED ON A MODEL FAMILY, NOT AN ENGINE.
    # `coqui` and `kokoro` are the names of TTS model families; MBCP's actual
    # runtime name for both is `tts` (`scripts/seed_stage.py:543,576` on
    # origin/main -- XTTS-v2 and Kokoro are two config rows on ONE
    # `tts_coqui` adapter). WP-IVGS-03 added `tts` to `ModelEngine` so those
    # certificates could be INGESTED; until this registration exists, a row
    # carrying the correct runtime name is certified, stored, selectable --
    # and resolves to nothing.
    #
    # REGISTERED ON THE THREE-TUPLE, NOT AS AN `engine -> client` ALIAS, and
    # the distinction is load-bearing: `tts` is ONE runtime serving TWO
    # families. An alias maps an engine to a single client, so it would pick
    # one model and be silently wrong for the other -- the exact failure
    # shape (right engine, wrong weights, plausible output) that AD-01
    # selection exists to prevent. The registry already separates families;
    # these are two more keys reusing the two that are already here.
    #
    # THE CONTRACT IS DERIVED, NOT RETYPED. `replace(engine=...)` on the
    # contract just registered means "what Kokoro requires" cannot fork into
    # two drifting copies as the runtime key ages. `name_patterns` are
    # deliberately NOT passed again -- they are family-keyed and engine-
    # independent, and re-declaring them would only duplicate entries in
    # `_NAME_PATTERNS`.
    #
    # NOTHING ABOVE IS REMOVED OR ALTERED. The Kokoro row rendering today is
    # live on engine `kokoro` and keeps resolving through the entry above it;
    # the `coqui`/`kokoro` value-domain cleanup remains deferred to AD-10
    # (WP-IVGS-03 S7.1).
    for _family in ("xtts", "kokoro"):
        _spec = _REGISTRY[("voiceover_tts", _ENGINE_BY_TTS_FAMILY[_family], _family)]
        register_client(
            ClientSpec(
                contract=replace(_spec.contract, engine=MBCP_TTS_RUNTIME_ENGINE),
                client_path=_spec.client_path,
                graph=_spec.graph,
                build_kwargs=dict(_spec.build_kwargs),
            )
        )


register_builtin_clients()
