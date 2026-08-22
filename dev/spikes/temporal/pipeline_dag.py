"""
WP-31 Lane C spike — the pipeline expressed as an explicit dependency DAG.

THIS IS THROWAWAY EVIDENCE, NOT FOUNDATION. See README.md.

The point of this module is the AD-05 design-input line added 2026-08-22:

    the workflow MUST support compiling the storyboard into an explicit
    dependency DAG -- per-scene depends_on and parallel groups -- rather
    than hardcoding the stage sequence.

So the stage order below is *data*, not control flow. The workflow body walks
whatever graph it is handed; it contains no `await stage1(); await stage2()`
sequence. Swapping in a storyboard-derived graph later changes this file and
nothing in the workflow.

Zero IVGS imports. Nothing here talks to the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# "activity" -- one stub activity
# "fanout"   -- one stub activity per scene, all concurrent
# "gate"     -- blocks until a signal arrives; executes nothing
NodeKind = str


@dataclass(frozen=True)
class DagNode:
    id: str
    label: str
    kind: NodeKind
    queue: str
    depends_on: Tuple[str, ...] = ()
    duration_s: float = 2.0
    signal_name: str = ""


# The eight IVGS stages plus the two human gates, as AD-05 section 5.1 lists
# them. Queue names are AD-05 section 4.2's, preserved verbatim so the mapping
# is legible to the review board.
#
# Note stage 6 depends on stage 5 only, and stage 7 on both 6 and 4 -- that
# pair is the first place the graph is genuinely a graph rather than a line,
# which is the property being demonstrated.
PIPELINE_DAG: Tuple[DagNode, ...] = (
    DagNode("s1_transcript", "Stage 1 refine_transcript", "activity", "gpu_llm",
            depends_on=(), duration_s=3.0),
    DagNode("s2_storyboard", "Stage 2 generate_storyboard", "activity", "gpu_llm",
            depends_on=("s1_transcript",), duration_s=3.0),
    DagNode("gate_storyboard", "GATE 1 storyboard review", "gate", "-",
            depends_on=("s2_storyboard",), signal_name="storyboard_approved"),
    DagNode("s3_media", "Stage 3 render_scene_media (per-scene fan-out)", "fanout", "gpu_image",
            depends_on=("gate_storyboard",), duration_s=20.0),
    DagNode("s4_manifest", "Stage 4 build_composition_manifest", "activity", "default",
            depends_on=("s3_media",), duration_s=3.0),
    DagNode("s5_voiceover", "Stage 5 generate_voiceover", "activity", "gpu_tts",
            depends_on=("s4_manifest",), duration_s=4.0),
    DagNode("s6_talking_head", "Stage 6 render_talking_head", "activity", "gpu_talking_head",
            depends_on=("s5_voiceover",), duration_s=4.0),
    DagNode("s7_draft", "Stage 7 assemble_prototype_draft", "activity", "composition",
            # genuinely two parents: the manifest and the head
            depends_on=("s6_talking_head", "s4_manifest"), duration_s=3.0),
    DagNode("gate_draft", "GATE 2 draft review", "gate", "-",
            depends_on=("s7_draft",), signal_name="draft_approved"),
    DagNode("s8_final", "Stage 8 render_final", "activity", "composition",
            depends_on=("gate_draft",), duration_s=3.0),
)


def topological_waves(nodes: Tuple[DagNode, ...]) -> List[List[DagNode]]:
    """
    Compile the DAG into ordered parallel groups.

    Each returned wave is a list of nodes whose dependencies are all satisfied
    by earlier waves, so every node within a wave may execute concurrently.
    This is the function that would consume storyboard-declared `depends_on`
    once AD-07 v2.x carries the field -- the workflow body does not change.

    Raises on a cycle rather than deadlocking, which is the whole reason for
    doing this at compile time instead of at await time.
    """
    by_id: Dict[str, DagNode] = {n.id: n for n in nodes}
    for n in nodes:
        for d in n.depends_on:
            if d not in by_id:
                raise ValueError(f"node {n.id!r} depends on unknown node {d!r}")

    remaining = {n.id: set(n.depends_on) for n in nodes}
    done: set = set()
    waves: List[List[DagNode]] = []

    while remaining:
        ready = sorted(nid for nid, deps in remaining.items() if deps <= done)
        if not ready:
            raise ValueError(f"cycle or unreachable nodes: {sorted(remaining)}")
        waves.append([by_id[nid] for nid in ready])
        for nid in ready:
            del remaining[nid]
        done |= set(ready)

    return waves


if __name__ == "__main__":
    for i, wave in enumerate(topological_waves(PIPELINE_DAG), 1):
        names = ", ".join(f"{n.id}({n.kind})" for n in wave)
        print(f"wave {i}: {names}")
