"""
Execution order as data, not control flow (AD-05 Draft 2 §5).

The workflow body in ``workflow.py`` names no stage. It walks whatever graph
this module hands it, so the day AD-07 v2.x carries per-scene ``depends_on``
the change lands here and the workflow is untouched — which is the whole point
of the design input added to AD-05 §5.1 on 2026-08-22.

Three things this module is careful about
-----------------------------------------

**1. Three media labels, not two.** WP-39 (job ``bd99fe37``, 2026-08-23):
``STAGE_TASK_MAP`` maps *both* ``image_generation`` and ``animation_generation``
to ``tasks.stage3_images.generate_scene_images_task``. Two runs of one task
reported under one label, the join's per-label idempotency key
(``ivgs:media_join_seen:{job}:{stage}``) was already set by the image run, and
the 12-scene animation completion was dropped as a duplicate of something it
was not. Here image, video and animation are three separate ``DagNode``s with
three separate labels, and — see ``workflow.py`` — the join does not key on the
label at all.

**2. Branches exist only for media types the storyboard actually contains.**
That mirrors ``dispatch_media_generation``, which dispatched exactly three
tasks for ``bd99fe37`` because that storyboard held all three types. A
two-type storyboard compiles to two branches.

**3. Stage numbering is not one thing.** ``spec_stage`` is AD-05 §5.1's
1..8. ``checkpoint_stage_index`` is what the live pipeline actually writes into
``pipeline_checkpoints.stage_index`` — which is NOT the same sequence, and is
recorded here because the conformance check in ``conformance.py`` compares
against a real checkpoint record. See ``CHECKPOINT_STAGE_INDEX`` below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from models.task_result import MediaType, PipelineStage


class NodeKind(str, Enum):
    """What the workflow does when it reaches a node."""

    ACTIVITY = "activity"   # exactly one activity execution
    FANOUT = "fanout"       # one activity per scene, all concurrent
    GATE = "gate"           # blocks on a signal; executes nothing


# ---------------------------------------------------------------------------
# Signals (AD-05 §5.3)
# ---------------------------------------------------------------------------

SIGNAL_STORYBOARD_APPROVED = "storyboard_approved"
SIGNAL_DRAFT_APPROVED = "draft_approved"
SIGNAL_STORYBOARD_REJECTED = "storyboard_rejected"
SIGNAL_CANCEL_JOB = "cancel_job"


# ---------------------------------------------------------------------------
# Checkpoint stage_index, as the LIVE pipeline writes it
# ---------------------------------------------------------------------------
#
# Read off the call sites at HEAD, not off the spec:
#
#   stage1_transcript.py:496,642,695      stage_index=1
#   stage2_storyboard.py:514,704          stage_index=2
#   stage3_images.py:716,771              stage_index=3
#   video_generation_task.py:542,615      stage_index=3
#   stage5_voiceover.py:619,668           stage_index=4   <- NOT 5
#   talking_head_task.py:962              stage_index=5
#   stage7_prototype_draft.py:467,581     stage_index=6
#   stage8_final_render.py:709            stage_index=7
#
# `composition_manifest` has NO live checkpoint write. The only one
# (pipeline_orchestrator_v2.py:620, stage_index=4 — colliding with tts_audio)
# sits in a task that STAGE_TASK_MAP does not dispatch, so it has never run;
# WP-07 F5 records that it would raise TypeError if it did. The live Stage 4
# task, tasks.stage4_manifest.build_composition_manifest, writes no checkpoint
# at all. That is why the banked reference run has no composition_manifest row,
# and why this maps to None rather than to 4.
CHECKPOINT_STAGE_INDEX: Dict[str, Optional[int]] = {
    PipelineStage.TRANSCRIPT_REFINEMENT.value: 1,
    PipelineStage.STORYBOARD_GENERATION.value: 2,
    PipelineStage.IMAGE_GENERATION.value: 3,
    PipelineStage.VIDEO_GENERATION.value: 3,
    PipelineStage.ANIMATION_GENERATION.value: 3,
    PipelineStage.COMPOSITION_MANIFEST.value: None,
    PipelineStage.TTS_AUDIO.value: 4,
    PipelineStage.TALKING_HEAD_RENDER.value: 5,
    PipelineStage.PROTOTYPE_DRAFT.value: 6,
    PipelineStage.FINAL_RENDER.value: 7,
}


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DagNode:
    """One vertex of the compiled pipeline graph."""

    id: str
    kind: NodeKind
    label: str                      # PipelineStage value, or "" for a gate
    queue: str                      # AD-05 §4.2 task queue, or "-" for a gate
    depends_on: Tuple[str, ...] = ()
    spec_stage: Optional[int] = None            # AD-05 §5.1, 1..8
    checkpoint_stage_index: Optional[int] = None
    signal_name: str = ""
    media_type: str = ""            # fanout only: which storyboard media_type
    scene_indexes: Tuple[int, ...] = ()         # fanout only
    idempotency_stage: str = ""     # token used in the activity key

    @property
    def is_gate(self) -> bool:
        return self.kind is NodeKind.GATE


@dataclass(frozen=True)
class SceneRef:
    """
    A storyboard scene, as the DAG compiler needs to see it.

    Field names and defaults mirror ``storyboard_scenes`` and
    ``models.task_result.StoryboardScene``; nothing else about a scene matters
    to the graph.
    """

    scene_id: str
    scene_index: int
    media_type: str = MediaType.IMAGE.value
    narration_text: str = ""
    visual_description: str = ""
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None
    # AD-07 v2.x will carry this. Nothing here requires it to exist yet —
    # AD-05 Draft 2 §5.3 is explicit that the design must not. A list, not a
    # tuple, because a SceneRef crosses the wire as a workflow argument and
    # lands in the event history as JSON.
    depends_on: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Media branches — three labels, in dispatch order
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MediaBranch:
    media_type: str
    node_id: str
    label: str
    queue: str
    idempotency_stage: str


# Order matches dispatch_media_generation's plan loop after the WP-39 fix and
# the WP-46 re-route: (image_generation, gpu_image),
# (video_generation, gpu_video), (animation_generation, gpu_animation).
MEDIA_BRANCHES: Tuple[MediaBranch, ...] = (
    MediaBranch(
        media_type=MediaType.IMAGE.value,
        node_id="s3_image",
        label=PipelineStage.IMAGE_GENERATION.value,
        queue="gpu_image",
        idempotency_stage="s3",
    ),
    MediaBranch(
        media_type=MediaType.VIDEO_CLIP.value,
        node_id="s3_video",
        label=PipelineStage.VIDEO_GENERATION.value,
        queue="gpu_video",
        idempotency_stage="s3v",
    ),
    MediaBranch(
        # Animation ran the image engine and the image queue until WP-46, which
        # is why an animation was a still. It now has its own task, its own
        # engine (Wan2.2-Animate on the Wan ComfyUI) and its own queue on the
        # node where those weights live. WP-39 had already given it the label.
        media_type=MediaType.ANIMATION.value,
        node_id="s3_animation",
        label=PipelineStage.ANIMATION_GENERATION.value,
        queue="gpu_animation",
        idempotency_stage="s3a",
    ),
    MediaBranch(
        # ⛔ THE FOURTH BRANCH, ADDED 2026-08-29 BY WP-IVGS-10.
        #
        # It was missing, and nothing had noticed for the same reason RC-P4's
        # gap went unnoticed: `MediaType` had only three members, so
        # `test_media_branch_table_covers_every_media_type` compared two
        # three-element sets and passed. Adding `MOTION_GRAPHICS` to the enum
        # made that test do its job immediately — which is what an invariant
        # test is for, and why the enum and this table belong to one commit.
        #
        # ⚠ THE SHADOW WAS BEHIND THE LIVE ORCHESTRATOR, not ahead of it.
        # `pipeline_orchestrator_v2` has routed this media type since
        # WP-IVGS-09 (`:716` fans it into `motion_scenes`, `:117` dispatches
        # `tasks.motion_graphics_task.render_scene_motion_graphics`). M3.3-R3
        # realizes activities FROM THIS TABLE, so a branch missing here would
        # have produced a Temporal pipeline that silently dropped every motion
        # scene while the Celery one rendered them.
        #
        # `default`, not a `gpu_*` queue, and that is deliberate rather than a
        # placeholder: the renderer is CPU-only, has no weights and no GPU, and
        # lives on node-01 beside that queue's worker (RC-I1's placement).
        media_type=MediaType.MOTION_GRAPHICS.value,
        node_id="s3_motion",
        label=PipelineStage.MOTION_GRAPHICS.value,
        queue="default",
        idempotency_stage="s3m",
    ),
)

MEDIA_BRANCH_BY_TYPE: Dict[str, MediaBranch] = {b.media_type: b for b in MEDIA_BRANCHES}


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def build_pipeline_dag(
    scenes: Sequence[SceneRef],
    *,
    include_final_render: bool = True,
) -> Tuple[DagNode, ...]:
    """
    Compile a storyboard into the pipeline graph.

    ``scenes`` may be empty — stages 1 and 2 produce the storyboard, so a job
    that has not reached gate 1 yet has no scenes to fan out over. In that case
    the media wave is empty and Stage 4 depends on the gate directly, which is
    what the real pipeline does when a storyboard yields nothing.

    ``include_final_render=False`` compiles the graph as far as the draft. The
    banked 2026-08-23 reference run stops there (``render_jobs.resume_from_stage
    = 'prototype_draft'``; no ``final_render`` checkpoint), so the conformance
    check needs to be able to ask for the same shape.
    """
    nodes: List[DagNode] = [
        DagNode(
            id="s1_transcript",
            kind=NodeKind.ACTIVITY,
            label=PipelineStage.TRANSCRIPT_REFINEMENT.value,
            queue="gpu_llm",
            depends_on=(),
            spec_stage=1,
            checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[
                PipelineStage.TRANSCRIPT_REFINEMENT.value
            ],
            idempotency_stage="s1",
        ),
        DagNode(
            id="s2_storyboard",
            kind=NodeKind.ACTIVITY,
            label=PipelineStage.STORYBOARD_GENERATION.value,
            queue="gpu_llm",
            depends_on=("s1_transcript",),
            spec_stage=2,
            checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[
                PipelineStage.STORYBOARD_GENERATION.value
            ],
            idempotency_stage="s2",
        ),
        DagNode(
            id="gate_storyboard",
            kind=NodeKind.GATE,
            label="",
            queue="-",
            depends_on=("s2_storyboard",),
            signal_name=SIGNAL_STORYBOARD_APPROVED,
        ),
    ]

    media_node_ids = _append_media_nodes(nodes, scenes)

    # Stage 4 joins every media branch that exists. With no branches it falls
    # back to the gate, so the graph is still connected.
    manifest_deps: Tuple[str, ...] = tuple(media_node_ids) or ("gate_storyboard",)
    nodes.append(
        DagNode(
            id="s4_manifest",
            kind=NodeKind.ACTIVITY,
            label=PipelineStage.COMPOSITION_MANIFEST.value,
            queue="default",
            depends_on=manifest_deps,
            spec_stage=4,
            checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[
                PipelineStage.COMPOSITION_MANIFEST.value
            ],
            idempotency_stage="s4",
        )
    )
    nodes.append(
        DagNode(
            id="s5_voiceover",
            kind=NodeKind.ACTIVITY,
            label=PipelineStage.TTS_AUDIO.value,
            queue="gpu_tts",
            depends_on=("s4_manifest",),
            spec_stage=5,
            checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[PipelineStage.TTS_AUDIO.value],
            idempotency_stage="s5",
        )
    )
    nodes.append(
        DagNode(
            id="s6_talking_head",
            kind=NodeKind.ACTIVITY,
            label=PipelineStage.TALKING_HEAD_RENDER.value,
            queue="gpu_talking_head",
            depends_on=("s5_voiceover",),
            spec_stage=6,
            checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[
                PipelineStage.TALKING_HEAD_RENDER.value
            ],
            idempotency_stage="s6",
        )
    )
    nodes.append(
        DagNode(
            id="s7_draft",
            kind=NodeKind.ACTIVITY,
            label=PipelineStage.PROTOTYPE_DRAFT.value,
            queue="composition",
            # Genuinely two parents: the locked manifest and the head render.
            # This is the first place the graph is a graph and not a line.
            depends_on=("s6_talking_head", "s4_manifest"),
            spec_stage=7,
            checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[
                PipelineStage.PROTOTYPE_DRAFT.value
            ],
            idempotency_stage="s7",
        )
    )

    if include_final_render:
        nodes.append(
            DagNode(
                id="gate_draft",
                kind=NodeKind.GATE,
                label="",
                queue="-",
                depends_on=("s7_draft",),
                signal_name=SIGNAL_DRAFT_APPROVED,
            )
        )
        nodes.append(
            DagNode(
                id="s8_final",
                kind=NodeKind.ACTIVITY,
                label=PipelineStage.FINAL_RENDER.value,
                queue="composition",
                depends_on=("gate_draft",),
                spec_stage=8,
                checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[
                    PipelineStage.FINAL_RENDER.value
                ],
                idempotency_stage="s8",
            )
        )

    return tuple(nodes)


def _append_media_nodes(nodes: List[DagNode], scenes: Sequence[SceneRef]) -> List[str]:
    """Append one fan-out node per media type PRESENT in the storyboard."""
    by_type: Dict[str, List[int]] = {}
    for scene in scenes:
        if scene.media_type not in MEDIA_BRANCH_BY_TYPE:
            raise ValueError(
                f"scene {scene.scene_id!r} (index {scene.scene_index}) carries "
                f"media_type {scene.media_type!r}, which is not one of "
                f"{sorted(MEDIA_BRANCH_BY_TYPE)}"
            )
        by_type.setdefault(scene.media_type, []).append(scene.scene_index)

    appended: List[str] = []
    for branch in MEDIA_BRANCHES:
        indexes = by_type.get(branch.media_type)
        if not indexes:
            continue
        nodes.append(
            DagNode(
                id=branch.node_id,
                kind=NodeKind.FANOUT,
                label=branch.label,
                queue=branch.queue,
                depends_on=("gate_storyboard",),
                spec_stage=3,
                checkpoint_stage_index=CHECKPOINT_STAGE_INDEX[branch.label],
                media_type=branch.media_type,
                scene_indexes=tuple(sorted(indexes)),
                idempotency_stage=branch.idempotency_stage,
            )
        )
        appended.append(branch.node_id)
    return appended


def topological_waves(nodes: Sequence[DagNode]) -> List[List[DagNode]]:
    """
    Compile the graph into ordered parallel groups.

    Every node in wave N has all its dependencies satisfied by waves < N, so
    the whole wave may execute concurrently. Two nodes with no dependency path
    between them land in the same wave without anyone having to remember to
    parallelise them.

    Raises ``ValueError`` on a cycle or a dangling dependency, at COMPILE time —
    the alternative is a workflow that hangs on an await nobody will ever
    satisfy, which is a far worse way to find out.
    """
    by_id: Dict[str, DagNode] = {}
    for node in nodes:
        if node.id in by_id:
            raise ValueError(f"duplicate node id {node.id!r}")
        by_id[node.id] = node

    for node in nodes:
        for dep in node.depends_on:
            if dep not in by_id:
                raise ValueError(f"node {node.id!r} depends on unknown node {dep!r}")

    remaining: Dict[str, set] = {n.id: set(n.depends_on) for n in nodes}
    done: set = set()
    waves: List[List[DagNode]] = []

    # Ready nodes keep DECLARATION order, not alphabetical order. Within the
    # media wave that is image, video, animation -- the same order
    # dispatch_media_generation plans its three branches in, so a wave printed
    # here reads the same way a media_generation_dispatched log line does.
    while remaining:
        ready = [nid for nid in by_id if nid in remaining and remaining[nid] <= done]
        if not ready:
            raise ValueError(f"cycle or unreachable nodes: {sorted(remaining)}")
        waves.append([by_id[nid] for nid in ready])
        for nid in ready:
            del remaining[nid]
        done |= set(ready)

    return waves


def stage_sequence(nodes: Sequence[DagNode]) -> List[str]:
    """
    The ordered stage labels the graph will execute, gates excluded.

    Within a wave, order is the wave's own (node-id sorted) order, so the
    sequence is deterministic for a given storyboard. This is the value the
    conformance check compares against a real run's checkpoint record.
    """
    return [n.label for wave in topological_waves(nodes) for n in wave if not n.is_gate]


def gate_positions(nodes: Sequence[DagNode]) -> Dict[str, int]:
    """
    Map each gate's signal name to its index in ``stage_sequence``.

    A gate at index *i* means: every stage at position < i runs before the
    signal, every stage at position >= i runs after it. That is the property
    the conformance check asserts against the reference run's timing gaps.
    """
    positions: Dict[str, int] = {}
    executed = 0
    for wave in topological_waves(nodes):
        for node in wave:
            if node.is_gate:
                positions[node.signal_name] = executed
            else:
                executed += 1
    return positions
