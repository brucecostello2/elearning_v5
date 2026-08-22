"""
WP-31 Lane C spike — the eight-stage pipeline as a durable workflow.

THIS IS THROWAWAY EVIDENCE, NOT FOUNDATION. See README.md.

What this file is here to prove, for the AD-05 review board:

  1. Stage ordering is DERIVED from a DAG (pipeline_dag.PIPELINE_DAG), not
     written as a call sequence. AD-05 section 5.1's design-input line.
  2. The per-scene fan-out is `asyncio.gather` over activity handles, with no
     Redis counter to mis-read. AD-05 section 5.2, defect D2.
  3. The human gates are signals, blocking indefinitely. AD-05 section 5.3.
  4. A killed worker resumes without re-running completed activities.
     AD-05 section 12 test 5 -- the headline property.
  5. A failing activity retries a bounded number of times and the failure
     surfaces in queryable workflow state rather than being swallowed.

Determinism: this module performs no I/O, reads no clock, and imports nothing
from IVGS. All side effects live in activities.py.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Dict, List

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from pipeline_dag import PIPELINE_DAG, DagNode, topological_waves
    from shared_types import (
        FlakyInput,
        PipelineInput,
        PipelineState,
        SceneInput,
        SceneResult,
        StageInput,
        StageResult,
    )
    import activities


# AD-05 section 9: retry becomes declarative, enforced by the server, visible
# in the UI. These stand in for spec Table 6-4's per-stage values, which the
# real migration preserves rather than redesigns.
STAGE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)

FLAKY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    non_retryable_error_types=["StubPermanentError"],
)


@workflow.defn
class VideoPipelineShadowWorkflow:
    def __init__(self) -> None:
        self._storyboard_approved = False
        self._draft_approved = False
        self._cancelled = False
        self._state = PipelineState(job_id="")

    # ---- signals (AD-05 section 5.3) -------------------------------------

    @workflow.signal
    def storyboard_approved(self, edits: str = "") -> None:
        self._storyboard_approved = True

    @workflow.signal
    def draft_approved(self) -> None:
        self._draft_approved = True

    @workflow.signal
    def cancel_job(self, reason: str = "") -> None:
        self._cancelled = True
        self._state.failure = f"cancelled: {reason}"

    # ---- query (AD-05 section 10: the workflow's own state) --------------

    @workflow.query
    def state(self) -> PipelineState:
        return self._state

    # ---- the run --------------------------------------------------------

    @workflow.run
    async def run(self, inp: PipelineInput) -> Dict[str, object]:
        self._state = PipelineState(job_id=inp.job_id)

        # The graph is compiled once, here. Nothing below names a stage.
        waves = topological_waves(PIPELINE_DAG)
        results: Dict[str, object] = {}

        for wave_index, wave in enumerate(waves, 1):
            self._state.current_wave = wave_index

            if self._cancelled:
                self._state.finished = True
                return {"status": "cancelled", "state": self._state.__dict__}

            # Every node in a wave is independent by construction, so the whole
            # wave runs concurrently. A single-node wave costs nothing extra.
            try:
                wave_results = await asyncio.gather(
                    *[self._execute_node(inp, node) for node in wave]
                )
            except ActivityError as exc:
                # AD-05 section 9: exhaustion is a failed workflow, visible in
                # the UI -- not a swallowed return value.
                self._state.failure = f"{type(exc.cause).__name__}: {exc.cause}"
                self._state.finished = True
                raise

            for node, res in zip(wave, wave_results):
                results[node.id] = res
                self._state.completed_nodes.append(node.id)

        if inp.include_failing_activity:
            await self._run_failing_activity(inp)

        self._state.finished = True
        return {"status": "completed", "state": self._state.__dict__}

    # ---- node dispatch ---------------------------------------------------

    async def _execute_node(self, inp: PipelineInput, node: DagNode):
        if node.kind == "gate":
            return await self._await_gate(node)
        if node.kind == "fanout":
            return await self._fan_out_scenes(inp, node)
        return await self._run_stage(inp, node)

    async def _await_gate(self, node: DagNode) -> str:
        # Blocks for as long as the operator takes. Days is normal.
        self._state.waiting_on_signal = node.signal_name
        if node.signal_name == "storyboard_approved":
            await workflow.wait_condition(
                lambda: self._storyboard_approved or self._cancelled
            )
        else:
            await workflow.wait_condition(
                lambda: self._draft_approved or self._cancelled
            )
        self._state.waiting_on_signal = ""
        return f"{node.signal_name}:received"

    async def _run_stage(self, inp: PipelineInput, node: DagNode) -> StageResult:
        return await workflow.execute_activity(
            activities.run_stage,
            StageInput(
                job_id=inp.job_id,
                node_id=node.id,
                label=node.label,
                queue=node.queue,
                duration_s=node.duration_s,
            ),
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=15),
            retry_policy=STAGE_RETRY,
        )

    async def _fan_out_scenes(
        self, inp: PipelineInput, node: DagNode
    ) -> List[SceneResult]:
        """
        AD-05 section 5.2. There is no counter, no join key, no watchdog.
        `return_exceptions=True` preserves today's deliberate partial-advance
        behaviour (commit 35d9226) rather than silently converting it to
        fail-fast -- AD-05 is explicit that this must not change.
        """
        handles = [
            workflow.execute_activity(
                activities.render_scene,
                SceneInput(
                    job_id=inp.job_id,
                    scene_index=i,
                    duration_s=node.duration_s,
                ),
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(seconds=15),
                retry_policy=STAGE_RETRY,
            )
            for i in range(inp.scene_count)
        ]
        settled = await asyncio.gather(*handles, return_exceptions=True)

        ok: List[SceneResult] = []
        failed = 0
        for res in settled:
            if isinstance(res, BaseException):
                failed += 1
                continue
            ok.append(res)
            self._state.scenes_completed.append(res.scene_index)

        if failed:
            workflow.logger.warning("scenes failed, partial-advancing: %d", failed)
        return ok

    async def _run_failing_activity(self, inp: PipelineInput) -> None:
        try:
            await workflow.execute_activity(
                activities.flaky_stage,
                FlakyInput(job_id=inp.job_id, fail_times=inp.failing_activity_fails),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=FLAKY_RETRY,
            )
        except ActivityError as exc:
            # Surfaced, not swallowed: readable via the `state` query and
            # visible in the Web UI event history.
            self._state.failure = f"flaky_stage exhausted retries: {exc.cause}"
