"""
Conformance against a banked reference run (WP-41 Task 4).

AD-05 §12 verifies the migration against a known-good reference output. This
module is the part of that gate that can be checked *before* any real render:
does the workflow's stage graph, compiled from the reference run's own
storyboard, produce the stage sequence the real pipeline actually executed, with
the gates in the right places?

Input is the banked pg_dump at
``/mnt/ivgs-shared/reference-run-2026-08-23/reference_run_tables.sql``
(``storyboard_scenes``, ``assets``, ``render_jobs``, ``pipeline_checkpoints``).
Nothing here connects to a database.

What the reference record can and cannot tell you
-------------------------------------------------

Job ``bd99fe37-0621-40da-aa30-e058cc776c23`` ran on 2026-08-23 with an
18-scene storyboard: 4 image, 12 animation, 2 video_clip. Its checkpoint
record holds **seven** rows and only **two** media labels:

    1  transcript_refinement   complete  16:00:59 -> 16:01:37
    2  storyboard_generation   complete  16:01:37 -> 16:03:25
       .................................. 41m 40s ..........   <- GATE 1
    3  image_generation        complete  16:45:05 -> 16:46:54
    3  video_generation        pending   16:47:01 -> (never)
    4  tts_audio               complete  18:45:02 -> 18:46:19
    5  talking_head_render     complete  19:23:07 -> 19:23:07
    6  prototype_draft         complete  19:23:10 -> 19:24:15

**Three media stages executed. Two rows exist.** That is not a gap in the
bank — it is WP-39, preserved. ``pipeline_checkpoints`` upserts on
``(job_id, stage_name)``, the animation run reported under
``image_generation``, and so the 12-scene animation result overwrote the
4-scene image result: the surviving row's ``successful_count`` is **12**, not
4. The record cannot name a stage that never had a name.

The ``video_generation`` row reading ``pending`` is the same defect from the
other side — the join never closed, so nothing ever came back to complete it.

So the comparison this module makes is deliberately two-sided:

  * the **spine** — everything outside stage 3 — must match exactly, in order;
  * the **media set** must match the storyboard's media types, and the module
    reports which of those the reference record is *missing*, as a named,
    explained divergence rather than a failure.

Anything else would either fail a correct workflow or quietly bless a record
that lost a stage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from temporal_pipeline.dag import (
    MEDIA_BRANCH_BY_TYPE,
    SIGNAL_DRAFT_APPROVED,
    SIGNAL_STORYBOARD_APPROVED,
    DagNode,
    SceneRef,
    build_pipeline_dag,
    gate_positions,
    stage_sequence,
)

REFERENCE_RUN_DIR = Path("/mnt/ivgs-shared/reference-run-2026-08-23")
REFERENCE_SQL = REFERENCE_RUN_DIR / "reference_run_tables.sql"

# The run banked on 2026-08-23: project c12fa967 "double digit multiplication".
REFERENCE_JOB_ID = "bd99fe37-0621-40da-aa30-e058cc776c23"
REFERENCE_PROJECT_ID = "c12fa967-f989-4ed4-8e20-3ea62cb92e8f"

_COPY_RE = re.compile(
    r"COPY public\.(\w+) \(([^)]*)\) FROM stdin;\n(.*?)\n\\\.\n", re.S
)


# ---------------------------------------------------------------------------
# pg_dump COPY parsing
# ---------------------------------------------------------------------------

def _unescape(value: str) -> Optional[str]:
    """COPY text format: ``\\N`` is NULL, and \\t \\n \\r \\\\ are escaped."""
    if value == r"\N":
        return None
    return (
        value.replace(r"\t", "\t")
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\\", "\\")
    )


def parse_dump(sql_text: str) -> Dict[str, List[Dict[str, Optional[str]]]]:
    """Split a pg_dump into ``{table: [row dicts]}``. Data sections only."""
    tables: Dict[str, List[Dict[str, Optional[str]]]] = {}
    for table, columns, body in _COPY_RE.findall(sql_text):
        names = [c.strip() for c in columns.split(",")]
        rows: List[Dict[str, Optional[str]]] = []
        for line in body.split("\n"):
            if not line:
                continue
            values = line.split("\t")
            rows.append({n: _unescape(v) for n, v in zip(names, values)})
        tables[table] = rows
    return tables


def _ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # '2026-08-23 16:00:59.900851+00' -> ISO with a full offset
    text = value.strip()
    if re.search(r"[+-]\d{2}$", text):
        text += ":00"
    return datetime.fromisoformat(text.replace(" ", "T"))


# ---------------------------------------------------------------------------
# The reference run
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReferenceCheckpoint:
    stage_name: str
    stage_index: Optional[int]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


@dataclass
class ReferenceRun:
    job_id: str
    project_id: str
    job_status: str = ""
    resume_from_stage: Optional[str] = None
    checkpoints: List[ReferenceCheckpoint] = field(default_factory=list)
    scenes: List[SceneRef] = field(default_factory=list)

    # ---- what the record says ---------------------------------------------

    def stage_sequence(self) -> List[str]:
        """Stage labels in the order the run started them."""
        ordered = sorted(
            self.checkpoints,
            key=lambda c: (c.started_at or datetime.max.replace(tzinfo=None)),
        )
        return [c.stage_name for c in ordered]

    def media_labels(self) -> List[str]:
        return [c.stage_name for c in self.checkpoints if c.stage_index == 3]

    def media_types(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for scene in self.scenes:
            counts[scene.media_type] = counts.get(scene.media_type, 0) + 1
        return counts

    def reached_final_render(self) -> bool:
        return any(c.stage_name == "final_render" for c in self.checkpoints)

    def gap_seconds(self, before: str, after: str) -> Optional[float]:
        """
        Wall-clock between one stage completing and another starting.

        A large gap where a gate sits is the record's only evidence that a human
        was asked something -- ``pipeline_checkpoints`` has no row for a gate.
        On ``bd99fe37`` the storyboard-to-media gap is 41m 40s.
        """
        done = next(
            (c.completed_at for c in self.checkpoints if c.stage_name == before), None
        )
        start = next(
            (c.started_at for c in self.checkpoints if c.stage_name == after), None
        )
        if done is None or start is None:
            return None
        return (start - done).total_seconds()


def load_reference_run(
    sql_path: Path | str = REFERENCE_SQL,
    job_id: str = REFERENCE_JOB_ID,
) -> ReferenceRun:
    """Load one job's checkpoint record and its project's storyboard."""
    tables = parse_dump(Path(sql_path).read_text(encoding="utf-8"))

    job_rows = [r for r in tables.get("render_jobs", []) if r.get("id") == job_id]
    if not job_rows:
        raise ValueError(f"job {job_id!r} not present in {sql_path}")
    job = job_rows[0]
    project_id = job.get("project_id") or ""

    checkpoints = [
        ReferenceCheckpoint(
            stage_name=r.get("stage_name") or "",
            stage_index=int(r["stage_index"]) if r.get("stage_index") else None,
            status=r.get("status") or "",
            started_at=_ts(r.get("started_at")),
            completed_at=_ts(r.get("completed_at")),
        )
        for r in tables.get("pipeline_checkpoints", [])
        if r.get("job_id") == job_id
    ]

    scenes = [
        SceneRef(
            scene_id=r.get("id") or "",
            scene_index=int(r.get("scene_index") or 0),
            media_type=r.get("media_type") or "image",
            narration_text=r.get("narration_text") or "",
            visual_description=r.get("visual_description") or "",
            duration_seconds=float(r.get("duration_seconds") or 0.0),
        )
        for r in tables.get("storyboard_scenes", [])
        if r.get("project_id") == project_id
    ]
    scenes.sort(key=lambda s: s.scene_index)

    return ReferenceRun(
        job_id=job_id,
        project_id=project_id,
        job_status=job.get("status") or "",
        resume_from_stage=job.get("resume_from_stage"),
        checkpoints=checkpoints,
        scenes=scenes,
    )


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

MEDIA_LABELS = ("image_generation", "video_generation", "animation_generation")

# Stages that EXECUTE but leave no row in `pipeline_checkpoints`, so a
# checkpoint record can never contain them and their absence is not evidence
# that they did not run.
#
# There is exactly one today. `tasks.stage4_manifest.build_composition_manifest`
# -- the Stage 4 task the orchestrator actually dispatches -- writes no
# checkpoint at all (stage4_manifest.py:82-170, no save_checkpoint call). The
# only composition_manifest checkpoint write in the tree sits in
# pipeline_orchestrator_v2.py:620, in a task STAGE_TASK_MAP does not dispatch
# and which WP-07 F5 records would raise TypeError if it ever ran. It also uses
# stage_index=4, which tts_audio already occupies.
#
# On the banked run this is visible as an 8-second hole: the media join was
# force-advanced by the watchdog at 18:44:54Z and tts_audio started at
# 18:45:02Z, with nothing in between. Stage 4 has to have run in that window --
# tts needs a locked manifest -- but the record cannot say so. Stated as
# inference, not as measurement.
UNCHECKPOINTED_STAGES = ("composition_manifest",)


@dataclass
class ConformanceReport:
    reference_sequence: List[str]
    workflow_sequence: List[str]
    reference_spine: List[str]
    workflow_spine: List[str]
    spine_matches: bool
    reference_media: List[str]
    workflow_media: List[str]
    media_missing_from_reference: List[str]
    media_missing_from_workflow: List[str]
    gate_positions: Dict[str, int]
    gate1_after: Optional[str]
    gate1_before: Optional[str]
    gate1_reference_gap_seconds: Optional[float]
    gate2_after: Optional[str]
    reference_reached_final: bool
    storyboard_media_types: Dict[str, int] = field(default_factory=dict)
    media_types_uncovered: List[str] = field(default_factory=list)
    stages_excluded_from_comparison: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def conforms(self) -> bool:
        """
        Conformance is: the spine matches exactly, the workflow's media set
        covers the storyboard's media types, and both gates sit where the
        reference's own timing and terminal state say they sat.

        ``media_missing_from_reference`` does NOT break conformance. It is the
        WP-39 loss, and the workflow supplying the label the record lacks is
        the migration working, not diverging.

        ``media_types_uncovered`` DOES break it, and it is the reason the
        record's own gap cannot be used as the only yardstick: the reference
        never named ``animation_generation``, so comparing against the record
        alone would happily pass a graph with no animation branch at all. The
        storyboard is the authority on which branches must exist. Checking
        against the record and against the storyboard is what makes this test
        catch the defect the record is a victim of.
        """
        return (
            self.spine_matches
            and not self.media_missing_from_workflow
            and not self.media_types_uncovered
            and self.gate1_after == "storyboard_generation"
            and self.gate1_before in MEDIA_LABELS
            and self.gate2_after == "prototype_draft"
        )


def _spine(sequence: Sequence[str]) -> List[str]:
    """The sequence with the media stages collapsed to a single marker."""
    out: List[str] = []
    for label in sequence:
        if label in MEDIA_LABELS:
            if not out or out[-1] != "<media>":
                out.append("<media>")
            continue
        out.append(label)
    return out


def compare(run: ReferenceRun, nodes: Optional[Sequence[DagNode]] = None) -> ConformanceReport:
    """
    Compile the workflow graph from the reference run's own storyboard and
    compare it to what the run actually executed.
    """
    if nodes is None:
        nodes = build_pipeline_dag(
            run.scenes,
            # The banked run stops at the draft: render_jobs.resume_from_stage
            # is 'prototype_draft' and no final_render checkpoint exists. The
            # compared graph is compiled to the same extent so an unrun stage
            # is not counted as a mismatch.
            include_final_render=run.reached_final_render(),
        )

    # Gate placement is read off the FULL graph, always. Gate 2 sits after the
    # draft whether or not this particular run went on to the final render --
    # and on this run, not going on is itself the evidence that gate 2 held.
    full_nodes = build_pipeline_dag(run.scenes, include_final_render=True)

    workflow_sequence = stage_sequence(nodes)
    reference_sequence = run.stage_sequence()

    # Compare only what a checkpoint record is capable of holding.
    comparable = [s for s in workflow_sequence if s not in UNCHECKPOINTED_STAGES]
    ref_spine = _spine(reference_sequence)
    wf_spine = _spine(comparable)

    ref_media = [s for s in reference_sequence if s in MEDIA_LABELS]
    wf_media = [s for s in workflow_sequence if s in MEDIA_LABELS]

    gates = gate_positions(full_nodes)
    full_sequence = stage_sequence(full_nodes)
    g1 = gates.get(SIGNAL_STORYBOARD_APPROVED)
    g2 = gates.get(SIGNAL_DRAFT_APPROVED)

    notes: List[str] = []
    for skipped in UNCHECKPOINTED_STAGES:
        if skipped in workflow_sequence:
            notes.append(
                f"{skipped} is excluded from the sequence comparison: the live "
                "Stage 4 task writes no pipeline_checkpoints row, so no real "
                "run can produce one (see UNCHECKPOINTED_STAGES)."
            )
    # The STORYBOARD, not the record, decides which branches must exist. This
    # is the check the reference record cannot make for itself.
    storyboard_media = run.media_types()
    covered = {
        MEDIA_BRANCH_BY_TYPE[t].label for t in storyboard_media if t in MEDIA_BRANCH_BY_TYPE
    }
    uncovered = sorted(label for label in covered if label not in wf_media)
    if uncovered:
        notes.append(
            "the storyboard contains media types the compiled graph has no "
            "branch for: " + ", ".join(uncovered)
        )

    missing_ref = [m for m in wf_media if m not in ref_media]
    if missing_ref:
        notes.append(
            "reference checkpoint record is missing "
            + ", ".join(missing_ref)
            + " -- pipeline_checkpoints upserts on (job_id, stage_name) and the "
            "animation run reported under image_generation (WP-39), so the "
            "surviving row carries the animation counts. Expected, explained, "
            "and not a conformance failure."
        )
    if any(c.status == "pending" and c.stage_index == 3 for c in run.checkpoints):
        notes.append(
            "a stage-3 checkpoint is still 'pending' in the reference record: "
            "the media join never closed on this job, which is the same defect "
            "seen from the other side."
        )

    return ConformanceReport(
        reference_sequence=reference_sequence,
        workflow_sequence=workflow_sequence,
        reference_spine=ref_spine,
        workflow_spine=wf_spine,
        spine_matches=ref_spine == wf_spine,
        reference_media=ref_media,
        workflow_media=wf_media,
        media_missing_from_reference=missing_ref,
        media_missing_from_workflow=[m for m in ref_media if m not in wf_media],
        gate_positions=gates,
        gate1_after=full_sequence[g1 - 1] if g1 else None,
        gate1_before=full_sequence[g1] if g1 is not None and g1 < len(full_sequence) else None,
        gate1_reference_gap_seconds=run.gap_seconds(
            "storyboard_generation", "image_generation"
        ),
        gate2_after=full_sequence[g2 - 1] if g2 else None,
        reference_reached_final=run.reached_final_render(),
        storyboard_media_types=storyboard_media,
        media_types_uncovered=uncovered,
        stages_excluded_from_comparison=[
            st for st in UNCHECKPOINTED_STAGES if st in workflow_sequence
        ],
        notes=notes,
    )


def render_report(report: ConformanceReport) -> str:
    """Human-readable form, used by the demo script and quoted in the report."""
    lines = [
        f"conforms                    : {report.conforms}",
        f"reference stage sequence    : {report.reference_sequence}",
        f"workflow stage sequence     : {report.workflow_sequence}",
        f"spine (media collapsed)     : {'MATCH' if report.spine_matches else 'MISMATCH'}",
        f"  reference                 : {report.reference_spine}",
        f"  workflow                  : {report.workflow_spine}",
        f"media in reference record   : {report.reference_media}",
        f"media in workflow graph     : {report.workflow_media}",
        f"missing from reference      : {report.media_missing_from_reference}",
        f"missing from workflow       : {report.media_missing_from_workflow}",
        f"gate 1 sits after           : {report.gate1_after}",
        f"gate 1 sits before          : {report.gate1_before}",
        f"gate 1 gap in the real run  : {report.gate1_reference_gap_seconds} s",
        f"gate 2 sits after           : {report.gate2_after}",
        f"reference reached final     : {report.reference_reached_final}",
        f"storyboard media types     : {report.storyboard_media_types}",
        f"media types with no branch  : {report.media_types_uncovered}",
        f"excluded (never checkpointed): {report.stages_excluded_from_comparison}",
    ]
    for note in report.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - operator convenience
    run = load_reference_run()
    print(f"job {run.job_id} project {run.project_id}")
    print(f"storyboard media mix: {run.media_types()}")
    print(render_report(compare(run)))
