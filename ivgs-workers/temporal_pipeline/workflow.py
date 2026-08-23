"""
``VideoPipelineWorkflow`` — the eight-stage pipeline as one durable function.

AD-05 §5.1 replaces ``STAGE_TRANSITIONS``, ``STAGE_TASK_MAP``,
``STAGE_QUEUE_MAP``, ``handle_stage_completion`` and the 23 in-stage
``send_task`` dispatch sites with control flow. Draft 2 §5 goes one step
further: the control flow must not name the stages either. So the body below
compiles a graph and walks it, and the only stage-shaped thing in it is the
dispatch on ``DagNode.kind``.

Read this file for four properties
----------------------------------

**1. The graph is derived, not written.** The workflow starts with no
storyboard, so the first compile yields stages 1 and 2 and the gate. When
Stage 2 returns, the graph is recompiled from the storyboard it produced and
the media branches appear — one per media type actually present. Nothing here
is conditional on which contract version produced the scenes, which is AD-05
Draft 2 §5.3's constraint.

**2. The join cannot lose a completion.** ``asyncio.gather`` over per-scene
activity handles. There is no counter to mis-read, no ``media_join_seen`` key,
no watchdog, and — this is the WP-39 point — **no label anywhere in the join**.
The server matches each completion to the ``ActivityTaskScheduled`` event that
started it, by event id. Two branches that share a task, a queue and an engine
therefore cannot be confused for one another, because the join never asks what
they are. See §"On WP-39" below.

**3. Both gates are signals.** ``workflow.wait_condition`` blocks for as long
as the operator takes; days is normal. There is no state machine to guard, so
ledger P2.5's "deliberately lenient approve_storyboard guard" has nothing left
to guard.

**4. Reservations release in ``finally``.** D4 was seven acquire sites against
three releases that raised ``TypeError``. Here there are no release call sites
to get wrong: acquire and release bracket a stage, and the release is in the
``finally`` of the block that acquired.

Determinism (AD-05 §7.1)
------------------------

This module performs no I/O, reads no clock, uses no randomness, and queries no
database. ``dag.py``, ``policies.py`` and ``idempotency.py`` are imported
through ``workflow.unsafe.imports_passed_through()`` because they reach
``models.task_result`` (pydantic enums) — they are pure, but the sandbox cannot
know that. Every side effect is in ``activities.py``.

Versioning (AD-05 §7.2) is adopted on the first workflow written, not
retrofitted: ``WORKFLOW_PATCH_*`` below names the change points, and the
replay test in ``tests/temporal`` is the CI gate the section asks for.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from temporal_pipeline import activities, policies
    from temporal_pipeline.dag import (
        SIGNAL_CANCEL_JOB,
        SIGNAL_DRAFT_APPROVED,
        SIGNAL_STORYBOARD_APPROVED,
        SIGNAL_STORYBOARD_REJECTED,
        DagNode,
        NodeKind,
        SceneRef,
        build_pipeline_dag,
        topological_waves,
    )
    from temporal_pipeline.idempotency import IdempotencyKey
    from temporal_pipeline.payloads import (
        ActivityContext,
        AssembleDraftInput,
        BuildManifestInput,
        GenerateStoryboardInput,
        GenerateVoiceoverInput,
        JobContext,
        ManifestScene,
        RefineTranscriptInput,
        RenderFinalInput,
        RenderSceneImageInput,
        RenderSceneVideoInput,
        RenderTalkingHeadInput,
        Reservation,
        ReservationRequest,
        SceneAudioRef,
        SceneVoiceover,
        TranscriptRecord,
    )


# AD-05 §7.2. Named now so the first logic change ships behind
# workflow.patched() rather than discovering versioning after in-flight jobs
# exist -- which the section calls the failure mode.
WORKFLOW_PATCH_GPU_BRACKET = "wp41-gpu-reservation-bracket"

# Queues that take a GPU reservation bracket. `default` and `composition` do
# not touch a GPU, so they do not ask ivgs-scheduler for one.
GPU_QUEUES = frozenset({"gpu_llm", "gpu_image", "gpu_video", "gpu_tts", "gpu_talking_head"})


@dataclass
class PipelineInput:
    """
    ``VideoPipelineWorkflow(project_id, job_id, options)`` — AD-05 §5.1.

    ``storyboard`` is what the Stage 2 stub will produce. In production Stage 2
    derives it from the refined transcript and this field is empty; the shadow
    needs it declared so a run can be given the exact shape of a real job — for
    instance the 4 image / 12 animation / 2 video_clip storyboard of
    ``bd99fe37``, which is the run the conformance test compares against.
    """

    job_id: str
    project_id: str = ""
    project_name: str = ""
    language_code: str = "en-US"
    tier: str = "prototype"
    transcript_count: int = 1
    storyboard: List[SceneRef] = field(default_factory=list)
    include_final_render: bool = True
    gpu_reservations: bool = True


@dataclass
class SceneOutcome:
    scene_id: str
    scene_index: int
    label: str
    artifact: str


@dataclass
class PipelineState:
    """
    AD-05 §10: the workflow's own state, truthful by construction.

    Read by ``@workflow.query``. This is what replaces the three competing
    truths -- ``projects.state`` (stale, ledger P2.5), ``render_jobs.stage``,
    and live task inspection -- and what ``projects.state`` becomes a
    denormalised read model of.
    """

    job_id: str = ""
    current_wave: int = 0
    completed_nodes: List[str] = field(default_factory=list)
    waiting_on_signal: str = ""
    scenes_completed: List[SceneOutcome] = field(default_factory=list)
    scenes_failed: int = 0
    media_labels_completed: List[str] = field(default_factory=list)
    failure: str = ""
    cancelled: bool = False
    finished: bool = False


@workflow.defn(name="VideoPipelineWorkflow")
class VideoPipelineWorkflow:

    def __init__(self) -> None:
        self._storyboard_approved = False
        self._storyboard_rejected = False
        self._storyboard_edits: str = ""
        self._draft_approved = False
        self._cancelled = False
        self._cancel_reason = ""
        self._state = PipelineState()

    # ---- signals (AD-05 §5.3) --------------------------------------------

    @workflow.signal(name=SIGNAL_STORYBOARD_APPROVED)
    def storyboard_approved(self, edits: str = "") -> None:
        self._storyboard_edits = edits
        self._storyboard_approved = True

    @workflow.signal(name=SIGNAL_STORYBOARD_REJECTED)
    def storyboard_rejected(self, reason: str = "") -> None:
        """
        Required by §5.3 for the M6 UI flow; neither this nor `regenerate`
        exists today. The shadow records the rejection and releases the gate as
        a failure rather than looping back to Stage 2 -- the regeneration loop
        is M6 work and is deliberately not invented here.
        """
        self._storyboard_rejected = True
        self._storyboard_edits = reason

    @workflow.signal(name=SIGNAL_DRAFT_APPROVED)
    def draft_approved(self) -> None:
        self._draft_approved = True

    @workflow.signal(name=SIGNAL_CANCEL_JOB)
    def cancel_job(self, reason: str = "") -> None:
        self._cancelled = True
        self._cancel_reason = reason

    # ---- query (AD-05 §10) -----------------------------------------------

    @workflow.query
    def state(self) -> PipelineState:
        return self._state

    # ---- run -------------------------------------------------------------

    @workflow.run
    async def run(self, inp: PipelineInput) -> Dict[str, Any]:
        self._state = PipelineState(job_id=inp.job_id)

        # The storyboard is not known until Stage 2 returns, so the graph is
        # compiled from what is known now and RECOMPILED each wave. With no
        # scenes the media wave is empty; once Stage 2 has run, the branches
        # appear. Nothing below names a stage.
        scenes: List[SceneRef] = []
        completed: set = set()
        results: Dict[str, Any] = {}
        wave_number = 0

        while True:
            nodes = build_pipeline_dag(
                scenes, include_final_render=inp.include_final_render
            )
            pending = [
                [n for n in wave if n.id not in completed]
                for wave in topological_waves(nodes)
            ]
            pending = [wave for wave in pending if wave]
            if not pending:
                break

            wave = pending[0]
            wave_number += 1
            self._state.current_wave = wave_number

            if self._cancelled:
                return self._finish("cancelled")

            try:
                wave_results = await asyncio.gather(
                    *[self._execute(inp, node, results) for node in wave]
                )
            except ActivityError as exc:
                # AD-05 §9: exhaustion is a FAILED WORKFLOW, visible in the UI
                # and resettable -- not a return value nobody checks.
                self._state.failure = f"{type(exc.cause).__name__}: {exc.cause}"
                self._state.finished = True
                raise

            if self._cancelled:
                return self._finish("cancelled")
            if self._storyboard_rejected:
                return self._finish("storyboard_rejected")

            for node, res in zip(wave, wave_results):
                results[node.id] = res
                completed.add(node.id)
                self._state.completed_nodes.append(node.id)
                if node.id == "s2_storyboard":
                    # THE recompile. The graph the next iteration walks is the
                    # one this storyboard implies.
                    scenes = list(inp.storyboard)

        return self._finish("completed")

    def _finish(self, status: str) -> Dict[str, Any]:
        self._state.finished = True
        self._state.cancelled = status == "cancelled"
        if status == "cancelled" and not self._state.failure:
            self._state.failure = f"cancelled: {self._cancel_reason}"
        if status == "storyboard_rejected" and not self._state.failure:
            self._state.failure = f"storyboard rejected: {self._storyboard_edits}"
        return {"status": status, "state": self._state}

    # ---- node dispatch ---------------------------------------------------

    async def _execute(self, inp: PipelineInput, node: DagNode, results: Dict[str, Any]):
        if node.kind is NodeKind.GATE:
            return await self._await_gate(node)

        # AD-05 §6: acquire/release bracket each GPU stage, release in the
        # workflow's `finally`. The bracket lives HERE, once, around whatever
        # the node turns out to be -- so a new node kind cannot arrive without
        # one, and no stage body has a release call site it can get wrong.
        # That is D4 closed structurally: seven acquires against three
        # TypeError-ing releases was only possible because releasing was
        # something eight separate files had to remember.
        #
        # One reservation per NODE, not per scene. That mirrors today exactly:
        # dispatch_media_generation sends one Celery task per media stage and
        # that task acquires once (stage3_images.py:630). Per-scene admission
        # is ivgs-scheduler's job under AD-05 §4.2, not the workflow's.
        take_reservation = (
            inp.gpu_reservations
            and node.queue in GPU_QUEUES
            and workflow.patched(WORKFLOW_PATCH_GPU_BRACKET)
        )
        reservation: Optional[Reservation] = None
        try:
            if take_reservation:
                reservation = await self._acquire(inp, node)
            if node.kind is NodeKind.FANOUT:
                return await self._fan_out(inp, node)
            return await self._run_stage(inp, node, results)
        finally:
            if reservation is not None and reservation.granted:
                await workflow.execute_activity(
                    activities.release_gpu_reservation,
                    reservation,
                    **self._activity_opts(policies.RELEASE_GPU_RESERVATION),
                )

    # ---- gates -----------------------------------------------------------

    async def _await_gate(self, node: DagNode) -> str:
        self._state.waiting_on_signal = node.signal_name
        if node.signal_name == SIGNAL_STORYBOARD_APPROVED:
            await workflow.wait_condition(
                lambda: self._storyboard_approved
                or self._storyboard_rejected
                or self._cancelled
            )
        else:
            await workflow.wait_condition(lambda: self._draft_approved or self._cancelled)
        self._state.waiting_on_signal = ""
        return f"{node.signal_name}:received"

    # ---- fan-out ---------------------------------------------------------

    async def _fan_out(self, inp: PipelineInput, node: DagNode) -> List[SceneOutcome]:
        """
        AD-05 §5.2 — the media join, as ``asyncio.gather``.

        **On WP-39.** The defect of 2026-08-23 was that two runs of one Celery
        task reported under one stage label, and the join's duplicate guard
        (``ivgs:media_join_seen:{job}:{stage}``) dropped the second as a repeat
        of the first. Three things here make that class of failure
        unavailable, not merely unlikely:

        1. **The join has no labels in it.** Below there is a list of activity
           handles. Temporal matches each ``ActivityTaskCompleted`` to the
           ``ActivityTaskScheduled`` event that created it, by event id, in the
           server's own history. Nothing consults a stage name, so no stage
           name can collide.
        2. **The unit is a scene, not a stage.** WP-39's join expected three
           reports for eighteen scenes, so one lost report stranded twelve
           scenes of finished work. Here eighteen scenes are eighteen
           independently tracked futures.
        3. **The counter is gone.** There is no integer to decrement, so D2's
           "0 on any Redis exception, read as all-complete" has no home either.

        ``return_exceptions=True`` preserves today's deliberate partial-advance
        (commit ``35d9226``); AD-05 §5.2 is explicit that this must not
        silently become fail-fast.
        """
        handles = [
            self._scene_activity(inp, node, scene_index)
            for scene_index in node.scene_indexes
        ]
        settled = await asyncio.gather(*handles, return_exceptions=True)

        ok: List[SceneOutcome] = []
        failed = 0
        for res in settled:
            if isinstance(res, BaseException):
                failed += 1
                continue
            outcome = SceneOutcome(
                scene_id=res.scene_id,
                scene_index=res.scene_index,
                label=res.stage,
                artifact=res.asset_id or "",
            )
            ok.append(outcome)
            self._state.scenes_completed.append(outcome)

        self._state.scenes_failed += failed
        if node.label not in self._state.media_labels_completed:
            self._state.media_labels_completed.append(node.label)
        if failed:
            workflow.logger.warning(
                "media branch partial-advance: label=%s failed=%d of %d",
                node.label,
                failed,
                len(node.scene_indexes),
            )
        return ok

    def _scene_activity(self, inp: PipelineInput, node: DagNode, scene_index: int):
        scene = next(s for s in inp.storyboard if s.scene_index == scene_index)
        ctx = self._context(inp, node, scene_index=scene_index)
        policy = policies.POLICY_BY_LABEL[node.label]

        if node.id == "s3_video":
            return workflow.execute_activity(
                activities.render_scene_video,
                RenderSceneVideoInput(
                    ctx=ctx,
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    visual_description=scene.visual_description,
                    narration_text=scene.narration_text,
                    duration_seconds=scene.duration_seconds,
                    scene_title=scene.scene_title,
                    project_name=inp.project_name,
                    language_code=inp.language_code,
                ),
                **self._activity_opts(policy),
            )

        # Image and animation: one input shape, two activity names, two labels.
        activity_fn = (
            activities.render_scene_animation
            if node.id == "s3_animation"
            else activities.render_scene_image
        )
        return workflow.execute_activity(
            activity_fn,
            RenderSceneImageInput(
                ctx=ctx,
                scene_id=scene.scene_id,
                scene_index=scene.scene_index,
                visual_description=scene.visual_description,
                media_type=scene.media_type,
                narration_text=scene.narration_text,
                duration_seconds=scene.duration_seconds,
                scene_title=scene.scene_title,
                project_name=inp.project_name,
                tier=inp.tier,
            ),
            **self._activity_opts(policy),
        )

    # ---- single-activity stages -----------------------------------------

    async def _run_stage(self, inp: PipelineInput, node: DagNode, results: Dict[str, Any]):
        policy = policies.POLICY_BY_LABEL[node.label]
        ctx = self._context(inp, node)
        return await workflow.execute_activity(
            *self._stage_call(inp, node, ctx, results),
            **self._activity_opts(policy),
        )

    async def _acquire(self, inp: PipelineInput, node: DagNode) -> Optional[Reservation]:
        # Its own idempotency key. A reservation is not the stage's effect, and
        # sharing the stage's key would make the execution ledger read as if
        # the stage body had run twice -- a false positive on exactly the
        # signal the resume proof depends on.
        ctx = self._context(inp, node, key_suffix="gpu")
        try:
            return await workflow.execute_activity(
                activities.acquire_gpu_reservation,
                ReservationRequest(ctx=ctx, stage_label=node.label, queue=node.queue),
                **self._activity_opts(policies.ACQUIRE_GPU_RESERVATION),
            )
        except ActivityError as exc:
            if policies.GPU_RESERVATION_FAILURE_IS_FATAL:
                raise
            # O-3 was ruled fatal-with-retry, CONTINGENT on ledger P2.6 having
            # made the heartbeat registry real. It has not: total_nodes:0.
            # The ruling's own contingency therefore applies and this keeps
            # today's deliberate fail-open -- but says so, out loud, in a
            # place a query and the UI can both see. D4's version of this was
            # silent for months.
            workflow.logger.warning(
                "gpu_reservation_unavailable stage=%s fail_open=True cause=%s",
                node.label,
                exc.cause,
            )
            return Reservation(granted=False, fail_open=True, detail=str(exc.cause))

    def _stage_call(
        self,
        inp: PipelineInput,
        node: DagNode,
        ctx: ActivityContext,
        results: Dict[str, Any],
    ):
        """Return ``(activity_fn, arg)`` for a single-activity node."""
        if node.id == "s1_transcript":
            return activities.refine_transcript, RefineTranscriptInput(
                ctx=ctx,
                job_context=self._job_context(inp),
                transcripts=[
                    TranscriptRecord(
                        id=f"{inp.job_id}-t{i}",
                        project_id=inp.project_id,
                        sequence_order=i + 1,
                        original_text=f"stub transcript {i + 1}",
                        language_code=inp.language_code,
                    )
                    for i in range(max(1, inp.transcript_count))
                ],
            )

        if node.id == "s2_storyboard":
            prior = results.get("s1_transcript")
            return activities.generate_storyboard, GenerateStoryboardInput(
                ctx=ctx,
                job_context=self._job_context(inp),
                refined_transcripts=list(prior.refined_transcripts) if prior else [],
                target_scene_count=len(inp.storyboard),
            )

        if node.id == "s4_manifest":
            return activities.build_composition_manifest, BuildManifestInput(
                ctx=ctx, job_id=inp.job_id, project_id=inp.project_id
            )

        if node.id == "s5_voiceover":
            return activities.generate_voiceover, GenerateVoiceoverInput(
                ctx=ctx,
                job_id=inp.job_id,
                project_id=inp.project_id,
                project_name=inp.project_name,
                language_code=inp.language_code,
                tier=inp.tier,
                scenes=[
                    SceneVoiceover(
                        scene_id=s.scene_id,
                        scene_index=s.scene_index,
                        narration_text=s.narration_text,
                        duration_seconds=s.duration_seconds,
                        scene_title=s.scene_title,
                        language_code=inp.language_code,
                    )
                    for s in inp.storyboard
                ],
            )

        if node.id == "s6_talking_head":
            voiceover = results.get("s5_voiceover")
            return activities.render_talking_head, RenderTalkingHeadInput(
                ctx=ctx,
                job_id=inp.job_id,
                project_id=inp.project_id,
                project_name=inp.project_name,
                language_code=inp.language_code,
                tier=inp.tier,
                scene_audio_refs=[
                    SceneAudioRef(
                        scene_id=r.scene_id,
                        scene_index=r.scene_index,
                        audio_asset_id=r.asset_id or "",
                        duration_seconds=r.duration_seconds,
                    )
                    for r in (voiceover.scene_results if voiceover else [])
                ],
            )

        if node.id == "s7_draft":
            manifest = results.get("s4_manifest")
            head = results.get("s6_talking_head")
            return activities.assemble_prototype_draft, AssembleDraftInput(
                ctx=ctx,
                job_id=inp.job_id,
                project_id=inp.project_id,
                project_name=inp.project_name,
                language_code=inp.language_code,
                manifest_id=manifest.manifest_id if manifest else "",
                talking_head_asset_id=head.asset_id if head else None,
                scenes=[
                    ManifestScene(
                        scene_id=s.scene_id,
                        scene_index=s.scene_index,
                        narration_text=s.narration_text,
                        duration_seconds=s.duration_seconds,
                        media_type=s.media_type,
                    )
                    for s in inp.storyboard
                ],
            )

        if node.id == "s8_final":
            manifest = results.get("s4_manifest")
            head = results.get("s6_talking_head")
            return activities.render_final, RenderFinalInput(
                ctx=ctx,
                job_id=inp.job_id,
                project_id=inp.project_id,
                project_name=inp.project_name,
                language_code=inp.language_code,
                manifest_id=manifest.manifest_id if manifest else "",
                talking_head_asset_id=head.asset_id if head else None,
                scenes=[],
            )

        # Unreachable by construction: build_pipeline_dag emits no other ids.
        # It raises rather than falling through, because a silent no-op here
        # would be a stage that never ran and nobody noticed -- the exact
        # shape of P2.3's `next_stage_task_not_registered`.
        raise ApplicationError(f"no activity bound to DAG node {node.id!r}")

    # ---- helpers ---------------------------------------------------------

    def _job_context(self, inp: PipelineInput) -> JobContext:
        return JobContext(
            job_id=inp.job_id,
            project_id=inp.project_id,
            project_name=inp.project_name,
            language_code=inp.language_code,
            tier=inp.tier,
        )

    def _context(
        self,
        inp: PipelineInput,
        node: DagNode,
        scene_index: Optional[int] = None,
        key_suffix: str = "",
    ) -> ActivityContext:
        stage_token = node.idempotency_stage or "gpu"
        if key_suffix:
            stage_token = f"{stage_token}-{key_suffix}"
        key = IdempotencyKey(
            job_id=inp.job_id,
            stage=stage_token,
            scene_index=scene_index,
        )
        return ActivityContext(
            job_id=inp.job_id,
            project_id=inp.project_id,
            label=node.label,
            idempotency_key=key.render(),
            queue=node.queue,
            scene_index=scene_index,
        )

    @staticmethod
    def _activity_opts(policy) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "task_queue": policy.queue,
            "start_to_close_timeout": timedelta(seconds=policy.start_to_close_s),
            "retry_policy": RetryPolicy(
                initial_interval=timedelta(seconds=policy.initial_interval_s),
                backoff_coefficient=policy.backoff_coefficient,
                maximum_interval=timedelta(seconds=policy.maximum_interval_s),
                maximum_attempts=policy.maximum_attempts,
                non_retryable_error_types=list(policy.non_retryable_error_types),
            ),
        }
        if policy.heartbeat_s is not None:
            opts["heartbeat_timeout"] = timedelta(seconds=policy.heartbeat_s)
        return opts
