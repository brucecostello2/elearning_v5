# `temporal_pipeline` — the Temporal shadow of the IVGS pipeline

**WP-41-TEMPORAL-PREP, 2026-08-23.** Built against AD-05 Draft 2 (APPROVED
2026-08-22) and the WP-31 findings.

> **This package touches no production path.** It registers no Celery task, is
> imported by no Celery worker, reaches no engine, no Pipeline API, no
> database and no SeaweedFS. Its activities are stubs. It exists so that the
> workflow *shape* — stage graph, gates, fan-out, retry policy, idempotency
> binding — can be built and proven before any of it carries real work.
>
> Unlike `dev/spikes/temporal/` (WP-31, throwaway evidence), this **is**
> foundation: it imports the live `models.task_result` enums, mirrors the live
> stage models field for field with a test that keeps them mirrored, and its
> activity bodies are where the real wrappers go.

## Layout

| File | Needs `temporalio` | What |
|---|---|---|
| `dag.py` | no | Execution order as data. `DagNode`, `build_pipeline_dag(storyboard)`, `topological_waves`. AD-05 Draft 2 §5. |
| `policies.py` | no | Retry / timeout / heartbeat per activity, carrying today's Celery constants beside AD-05's target values. §9, Appendix C. |
| `idempotency.py` | no | `(job_id, stage, scene_index)` keys, and a store that makes a twice-delivered activity produce one effect. Draft 2 §6. |
| `payloads.py` | no | Activity I/O shapes, mirroring the live stage models. |
| `reference_storyboard.py` | no | The banked 2026-08-23 storyboard as data: 4 image / 12 animation / 2 video_clip. |
| `conformance.py` | no | Loads a banked run's checkpoint record and compares it to a compiled graph. WP-41 Task 4. |
| `activities.py` | **yes** | Stub activity bodies. |
| `workflow.py` | **yes** | `VideoPipelineWorkflow`. |
| `worker.py` | **yes** | The dev worker: one worker per AD-05 §4.2 queue, in one process. |
| `client.py` | **yes** | Driver: start / signal / state / result / history / evidence / export. |
| `demos/` | **yes** | The three demonstrations. |

The first six import nothing from `temporalio` on purpose: the DAG compiler,
the policy table, the key scheme and the conformance check are unit-testable in
`/opt/ivgs/.venv`, which has no Temporal SDK in it and is not being given one.

## Running it

The SDK lives in a venv **outside the repo**, so it cannot be committed and
cannot change what the repo's test suite resolves:

```bash
python3 -m venv /home/dev/.venv-ivgs-temporal
/home/dev/.venv-ivgs-temporal/bin/pip install temporalio==1.31.0 pydantic==2.10.4 pytest==8.3.4
```

Cluster: **node-07, `192.168.1.96:7233`**, namespace `dev`, UI on `:8080`.

The two shell demos source `shadow_env.sh`, so they need no environment of
their own:

```bash
cd /opt/ivgs/ivgs-workers/temporal_pipeline/demos

# Task 2 -- start -> gate 1 -> three-branch fan-out -> gate 2 -> final
./demo_shadow_run.sh

# Task 3 -- SIGKILL mid-fan-out, resume, at-least-once observed
./demo_resume.sh

# Task 2 again, exercising AD-05 s12 test 4: two scenes forced to fail, the
# pipeline partial-advances rather than failing the job
. ./shadow_env.sh
start_worker /tmp/pa.log --gpu-concurrency 4 --fail-scenes "pa-demo=1,3"
drive start pa-demo --scenes "image:2,video_clip:1,animation:2" --stop-at-draft
drive signal pa-demo storyboard_approved
sleep 25 && drive state pa-demo    # scenes_failed: 2, finished: true
stop_worker SIGTERM
```

The Python demo needs the two variables the shell demos set for it:

```bash
cd /opt/ivgs/ivgs-workers
PYTHONPATH=/opt/ivgs/ivgs-workers \
IVGS_TEMPORAL_SHADOW_STATE=/tmp/ivgs-temporal-shadow \
  /home/dev/.venv-ivgs-temporal/bin/python \
  -m temporal_pipeline.demos.demo_duplicate_delivery      # Task 3, no cluster needed
```

Evidence lands in `$EVIDENCE_DIR` (default
`/tmp/ivgs-temporal-shadow/evidence/<workflow_id>/`).

## Tests

```bash
# 162 pass, 2 files skip (the SDK ones) -- part of the ordinary repo suite
/opt/ivgs/.venv/bin/python -m pytest ivgs-workers/tests/temporal/

# 78 pass, 2 files skip (the ones that read live Celery task objects)
PYTHONPATH=/opt/ivgs/ivgs-workers /home/dev/.venv-ivgs-temporal/bin/python \
  -m pytest ivgs-workers/tests/temporal/
```

## The three properties worth knowing

**The workflow body names no stage.** It compiles a graph and walks waves.
After Stage 2 returns, it recompiles from the storyboard that stage produced —
so the media branches that appear are derived, not written. When AD-07 v2.x
carries per-scene `depends_on`, the change lands in `dag.py` and the workflow
is untouched.

**The media join has no labels in it.** WP-39 (job `bd99fe37`, 2026-08-23) lost
a 12-scene animation completion because image and animation shared one Celery
task *and* one stage label, so the join's per-label duplicate guard dropped the
second report as a repeat of the first. Here the join is `asyncio.gather` over
per-scene activity handles: the server matches each completion to the
`ActivityTaskScheduled` event that created it, by event id. Nothing consults a
stage name, so no stage name can collide — and the unit is a scene, so one lost
report cannot strand twelve scenes of finished work.

**Activities execute at least once.** WP-31 Lane C measured it: two scene
bodies ran twice across a `SIGKILL`. So every writing activity routes its
effect through `IdempotentEffectStore.apply` on its own key. `demo_resume.sh`
reproduces both halves — 39 schedules each completed exactly once, two bodies
executed twice, 25 effects.

A whole-directory run is clean in either interpreter: each file skips, loudly,
in the venv it does not belong to. A failure that only means "wrong
interpreter" hides the real ones.
