"""WP-65 Task 3 -- where an engine's weights go, and which node hosts it.

Placement is DATA. The alternative -- paths built inline in the fetch code --
is how bytes end up somewhere no loader looks while the store records them as
available, which is the defect this package exists to close.

MEASURED 2026-08-26 from the committed compose files, not from AD-02's prose
(AD-02 describes roles; the compose files say which engine actually has a
container and which directory it mounts):

``ivgs-infra/docker-compose.node04.yml:59-68``
    ``comfyui`` / ``ivgs-comfyui-primary`` mounts ONE directory --
    ``/data/models/comfyui/checkpoints`` -> ``models/checkpoints:ro``. Probed
    live the same day: ``ckpt_name = ['flux1-schnell-fp8.safetensors']`` and
    ``unet_name``, ``lora_name``, ``clip_name`` all ``[]``. It is a
    FLUX-only ComfyUI.

``ivgs-infra/docker-compose.node03.yml:191-207``
    ``wan-animate-server`` / ``ivgs-wan-animate-server-node03`` mounts eight
    directories under ``/opt/models/comfyui-wan/models/``. Probed live:
    ``WanVideoModelLoader.model =
    ['Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors']``.

THE TWO ARE THE SAME IVGS ENGINE KEY. ``docker-compose.node03.yml:113-120``
says so in as many words: both resolve through ``IVGS_COMFYUI_URL``, and they
are told apart by the PER-WORKER value of that variable plus queue routing
(node-03 consumes ``gpu_video,gpu_animation``; node-04 consumes
``gpu_image,gpu_tts,gpu_talking_head``). So an IVGS engine key does NOT
identify a host, and placement cannot be keyed on the engine enum alone -- it
is keyed on the (engine, deployment) pair this module calls an ENGINE HOST.

Directory layout under each host is transcribed from MBCP's own
``ENGINE_MATERIALIZATION`` (``mbcp_core/weights/materialization.py:37-100``),
which is the map the .51 materializer already writes node-03's tree with. IVGS
follows it rather than inventing a second convention.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shared.weights.errors import NoHostForEngineError, NoPlacementRuleError

# WP-66 found this as a global constant reading ``"diffusion_models"``, applied
# to every host. It is a WAN-PACK convention, and applying it to node-04's
# FLUX ComfyUI -- which mounts ``checkpoints`` and nothing else -- made every
# familyless image model look unplaceable, which in turn made WP-66's selection
# refusal reject models that are perfectly fine. The fallback belongs to the
# HOST, because "where does a bundle go when it declares no family" is a
# property of the engine deployment's layout, not of the fleet.
#
# ``EngineHost.default_dest`` carries it now, and it must be one of the
# directories that host actually mounts -- asserted in the tests, so a new host
# cannot be added with a destination no loader reads.


@dataclass(frozen=True)
class EngineHost:
    """One engine deployment: a node, a container, and a model root.

    ``node_id`` is the fleet node name (``node-03``), NOT the GPU-suffixed
    scheduler form (``node-03:gpu0``) -- weights live on a node, not on a GPU.
    """

    engine: str
    node_id: str
    container: str
    #: Host-side root the container mounts its ``models/`` tree from.
    model_root: str
    #: Subdirectories the container actually mounts. A destination outside
    #: this set is refused: writing there puts bytes where no loader looks.
    mounted_dests: tuple[str, ...]
    #: MBCP engine-image key, where one exists -- the key into
    #: ``ENGINE_MATERIALIZATION``.
    mbcp_engine_key: str | None = None
    #: Which Celery queues route work here. Placement that ignores this
    #: attributes a model to a node that never receives its stage's jobs.
    queues: tuple[str, ...] = ()
    #: Where a bundle goes when it declares no family. MUST be in
    #: ``mounted_dests``. Defaults to the first mount, which is the honest
    #: choice for a host with only one.
    default_dest: str = ""
    notes: str = ""

    def fallback_dest(self) -> str:
        return self.default_dest or self.mounted_dests[0]


@dataclass(frozen=True)
class PlacementRule:
    """Where one bundle's files go under a host's model root."""

    host: EngineHost
    #: family -> destination subdirectory, from MBCP's materialization map.
    dest_by_family: dict[str, str] = field(default_factory=dict)

    def dest_for(self, family: str | None) -> str:
        """Absolute host-side directory for ``family``.

        A bundle with no declared family lands in the HOST's fallback, not in a
        fleet-wide constant -- see the note above ``EngineHost.default_dest``.

        :raises NoPlacementRuleError: the resolved destination is not one the
            host container mounts.
        """
        if not family:
            # No declared family: the host's own fallback is the honest answer.
            sub = self.host.fallback_dest()
        elif family in self.dest_by_family:
            sub = self.dest_by_family[family]
        else:
            # A NAMED family this host has no convention for. Refused rather
            # than dropped into the fallback: "wan_animate" means something
            # specific, and silently writing it to node-04's `checkpoints`
            # would put a 14B video model where a checkpoint loader will try to
            # read it. Only a familyless bundle may use the fallback.
            raise NoPlacementRuleError(
                f"engine host {self.host.container} on {self.host.node_id} "
                f"declares no placement for family {family!r}"
                + (
                    f" (it knows {', '.join(sorted(self.dest_by_family))})"
                    if self.dest_by_family
                    else " (it declares no family conventions at all)"
                )
            )
        if sub not in self.host.mounted_dests:
            raise NoPlacementRuleError(
                f"engine host {self.host.container} on {self.host.node_id} does "
                f"not mount a {sub!r} directory (it mounts "
                f"{', '.join(self.host.mounted_dests)}), so weights for family "
                f"{family!r} have nowhere a loader would find them"
            )
        return f"{self.host.model_root.rstrip('/')}/{sub}"


# ---------------------------------------------------------------------------
# The fleet, as measured. One row per ENGINE DEPLOYMENT, not per engine.
# ---------------------------------------------------------------------------

#: node-03's Wan pack. Directories transcribed from
#: docker-compose.node03.yml:197-206.
_WAN_DESTS = (
    "diffusion_models",
    "text_encoders",
    "vae",
    "clip_vision",
    "detection",
    "loras",
    "sam2",
    "onnx",
)

#: family -> dest, from mbcp_core/weights/materialization.py
#: ENGINE_MATERIALIZATION["comfyui-wan"].
_WAN_FAMILY_DESTS = {
    "wan_animate": "diffusion_models",
    "wan_vae": "vae",
    "wan_textenc": "text_encoders",
    "wan_clipvision": "clip_vision",
    "wan_lora": "loras",
    "wan_lora_distill": "loras",
    "wan_t2v_high": "diffusion_models",
    "wan_t2v_low": "diffusion_models",
    "wan_t2v_lora_high": "loras",
    "wan_t2v_lora_low": "loras",
    "wan_preproc_sam": "sam2",
    "wan_preproc_det": "detection",
    "wan_preproc_pose": "onnx",
}

#: node-04's FLUX ComfyUI. It mounts `checkpoints` and nothing else, so every
#: family it can host lands there. Declared rather than left empty: WP-67's
#: client registry gave models a real family for the first time, and a host with
#: no family map refuses every NAMED family by design (see `dest_for`). Before
#: this, `flux` on node-04 was refused with "declares no family conventions at
#: all" -- correct given the rule, and wrong about the fleet.
_FLUX_FAMILY_DESTS = {
    "flux": "checkpoints",
    "sd15": "checkpoints",
    "sdxl": "checkpoints",
    "sd35": "checkpoints",
    # AnimateDiff-SD15 renders from an SD-1.5 CHECKPOINT plus a motion module;
    # the checkpoint is what a bundle would carry, and it goes where every other
    # checkpoint goes. (The motion module ships in the engine image -- MBCP's
    # certified graph names `mm_sd_v15_v2.ckpt` as a literal, not a slot.)
    "animatediff": "checkpoints",
}

#: The cogvideox server mounts one model directory, named for the model.
_COGVIDEOX_FAMILY_DESTS = {"cogvideox": "cogvideox-5b"}

#: vLLM reads an HF cache; every family lands in the same hub directory.
_VLLM_FAMILY_DESTS = {"vllm_chat": "hub"}

ENGINE_HOSTS: tuple[EngineHost, ...] = (
    EngineHost(
        engine="comfyui",
        node_id="node-03",
        container="ivgs-wan-animate-server-node03",
        model_root="/opt/models/comfyui-wan/models",
        mounted_dests=_WAN_DESTS,
        mbcp_engine_key="comfyui-wan",
        queues=("gpu_video", "gpu_animation"),
        default_dest="diffusion_models",
        notes=(
            "The animation host. docker-compose.node03.yml:191-207. Reached by "
            "node-03's worker as IVGS_COMFYUI_URL=http://wan-animate-server:8188 "
            "(:120) and cross-node on 192.168.1.92:8220 (:208)."
        ),
    ),
    EngineHost(
        engine="comfyui",
        node_id="node-04",
        container="ivgs-comfyui-primary",
        model_root="/data/models/comfyui",
        mounted_dests=("checkpoints",),
        mbcp_engine_key=None,
        queues=("gpu_image", "gpu_tts", "gpu_talking_head"),
        default_dest="checkpoints",
        notes=(
            "The image host. docker-compose.node04.yml:59-68 mounts checkpoints "
            "ONLY, read-only. Probed 2026-08-26: one checkpoint, "
            "flux1-schnell-fp8.safetensors. It cannot host an animation bundle "
            "-- there is no diffusion_models mount to put one in."
        ),
    ),
    EngineHost(
        engine="cogvideox",
        node_id="node-03",
        container="ivgs-cogvideox-server-node03",
        model_root="/opt/models",
        mounted_dests=("cogvideox-5b",),
        mbcp_engine_key=None,
        queues=("gpu_video",),
        notes="docker-compose.node03.yml:150-161, MODEL_PATH=/opt/models/cogvideox-5b.",
    ),
    EngineHost(
        engine="vllm",
        node_id="node-02",
        container="ivgs-vllm-primary",
        model_root="/data/models",
        mounted_dests=("hub",),
        mbcp_engine_key=None,
        queues=("gpu_llm",),
        notes="docker-compose.node02.yml:57-70, HF_HOME=/data/models.",
    ),
)

#: (engine, node) -> family placement map. One table rather than a conditional,
#: so adding a host means adding a row here and nothing else.
_FAMILY_DESTS_BY_HOST: dict[tuple[str, str], dict[str, str]] = {
    ("comfyui", "node-03"): _WAN_FAMILY_DESTS,
    ("comfyui", "node-04"): _FLUX_FAMILY_DESTS,
    ("cogvideox", "node-03"): _COGVIDEOX_FAMILY_DESTS,
    ("vllm", "node-02"): _VLLM_FAMILY_DESTS,
}


#: WP-68 Task 2. Engines that HAVE NO WEIGHTS TO FETCH, ever, by nature.
#:
#: WP-65's availability model had two answers for a model with no bytes on a
#: node -- "not fetched yet" and "engine-only certification" -- and both imply
#: bytes are a thing that could exist. A template-driven renderer has no
#: weights at all: a motion graphic is code and parameters, and `ffmpeg` is a
#: local binary. Reporting either as permanently un-fetched is the fabricated
#: -absence defect WP-57/60 exists to stop, one level along.
#:
#: This is the extension the brief asked for ("WP-65's availability model must
#: be able to express 'this engine needs no weights' rather than reporting it
#: as permanently unfetched. If it cannot, extend it here").
WEIGHTLESS_ENGINES: dict[str, str] = {
    "motion_graphics": (
        "a motion graphic is rendered from a template and its parameters; "
        "there are no weights and there is nothing to fetch"
    ),
    "ffmpeg": (
        "ffmpeg is a local binary invoked by the compositor, not a served "
        "model; it has no weights and no endpoint"
    ),
}


#: Engines IVGS knows by name but which NO node on this fleet hosts. Listed
#: rather than left to fall through, so the refusal can say something true.
#: ``animatediff`` is here because it is a stale IVGS-only engine key -- MBCP
#: serves AnimateDiff on ComfyUI (see WP-65 Task 5); no container answers it.
UNHOSTED_ENGINES: dict[str, str] = {
    "animatediff": (
        "no container on this fleet serves the 'animatediff' engine; MBCP "
        "certifies AnimateDiff against 'comfyui' and IVGS's own ingest default "
        "has agreed since WP-46 (ad01_ingest.py:70)"
    ),
    "remotion": (
        "no Remotion container runs on node-02, node-03 or node-04 "
        "(verified 2026-08-26)"
    ),
    # `motion_graphics` WAS HERE and is deliberately gone. WP-IVGS-09 (RC-I1)
    # deployed `ivgs-motion-renderer` on node-01, so the sentence this row
    # carried -- "no motion-graphics renderer is deployed on this fleet" -- is
    # no longer true, and a refusal that gives a false reason is worse than one
    # that gives none.
    #
    # It is not moved into ENGINE_HOSTS either, and that is not an omission.
    # ENGINE_HOSTS answers "where do this engine's WEIGHTS go"; `motion_graphics`
    # is in WEIGHTLESS_ENGINES above precisely because that question does not
    # apply to it. A hosted engine with no weights belongs in NEITHER map, and
    # `compute_status` checks weightless FIRST so no weight state is ever
    # computed for it.
    "sadtalker": "no sadtalker container is deployed on this fleet",
    "wan21": "no standalone wan21 server is deployed; Wan runs under comfyui on node-03",
}


def hosts_for_engine(engine: str) -> tuple[EngineHost, ...]:
    """Every deployment of ``engine`` on this fleet, in placement order."""
    return tuple(h for h in ENGINE_HOSTS if h.engine == engine)


def placement_for(engine: str, *, node_id: str | None = None) -> PlacementRule:
    """The placement rule for ``engine``, optionally pinned to one node.

    :raises NoHostForEngineError: nothing on this fleet serves ``engine``, or
        nothing on ``node_id`` does. **This is a correct outcome**, not a
        fault: it is the state AnimateDiff-SD15 and MimicMotion are in.
    """
    candidates = hosts_for_engine(engine)
    if node_id is not None:
        candidates = tuple(h for h in candidates if h.node_id == node_id)

    if not candidates:
        known = UNHOSTED_ENGINES.get(engine)
        where = f" on {node_id}" if node_id else ""
        if known:
            raise NoHostForEngineError(f"no node hosts engine {engine!r}{where}: {known}")
        raise NoHostForEngineError(
            f"no node hosts engine {engine!r}{where}; the fleet serves "
            f"{', '.join(sorted({h.engine for h in ENGINE_HOSTS}))}"
        )

    host = candidates[0]
    return PlacementRule(host=host, dest_by_family=dict(_FAMILY_DESTS_BY_HOST.get(
        (host.engine, host.node_id), {}
    )))


def host_for_model(engine: str, stage: str) -> EngineHost:
    """The host that will actually RUN ``(engine, stage)`` on this fleet.

    Disambiguates the two ``comfyui`` deployments the way the running system
    does -- by which node's worker consumes the stage's queue -- instead of
    taking whichever row comes first.

    :raises NoHostForEngineError: no host serves that pair.
    """
    queue = _STAGE_QUEUE.get(stage)
    candidates = hosts_for_engine(engine)
    if not candidates:
        return placement_for(engine).host  # raises with the right message
    if queue is not None:
        matched = tuple(h for h in candidates if queue in h.queues)
        if matched:
            return matched[0]
        raise NoHostForEngineError(
            f"engine {engine!r} is hosted on this fleet, but no host of it "
            f"consumes queue {queue!r} (stage {stage!r}); "
            + "; ".join(f"{h.container} serves {', '.join(h.queues)}" for h in candidates)
        )
    return candidates[0]


#: stage -> Celery queue. Transcribed from the compose ``--queues`` lines
#: measured 2026-08-26 and from ivgs-workers task routing.
_STAGE_QUEUE: dict[str, str] = {
    "image_generation": "gpu_image",
    "video_generation": "gpu_video",
    "animation_generation": "gpu_animation",
    "voiceover_tts": "gpu_tts",
    "talking_head": "gpu_talking_head",
    "transcript_refinement": "gpu_llm",
    "storyboard_generation": "gpu_llm",
    "translation": "gpu_llm",
    "composition": "composition",
}
