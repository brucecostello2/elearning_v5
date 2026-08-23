# WP-07-CHECKPOINTS - report

| | |
|---|---|
| **Package** | WP-07-CHECKPOINTS (Track S #8, Tier A) |
| **HEAD SHA at session start** | `9af5a485dfbd732bd9f0ce2519523f3fb267936f` |
| **HEAD at package start** | `148125d` (WP-06, committed and held earlier this session) |
| **Date** | 2026-08-23 |
| **Session** | Overnight unattended batch, Track S, sequential (package 4 of 5) |
| **Ledger** | **P1.2** - M2 - "highest-leverage item in the milestone" |

---

## Pass 1 - findings

### Evidence basis: VERIFIED LIVE (measured on node-01 this session)

**Finding 1 - the POST route really is absent. 405, measured.**

    $ docker exec ivgs-fastapi sh -lc 'python - <<PY
    ... POST /api/v1/jobs/00000000-.../checkpoints ...
    PY'
    HTTPError 405 Method Not Allowed   allow: GET

Live OpenAPI, from the running `ivgs-fastapi` (`v5.5.3-arch1`):

    /api/v1/jobs/{job_id}/checkpoints              ['DELETE', 'GET']
    /api/v1/jobs/{job_id}/checkpoints/{stage_name} ['GET']
    /api/v1/jobs/{job_id}/resume                   ['POST']

No POST on `/checkpoints`. The brief is exactly right.

**Finding 2 - no checkpoint row has ever been written.**

    $ docker exec ivgs-postgres psql -U ivgs -d ivgs -c "select count(*) from pipeline_checkpoints;"
     0

`POST /resume` resumes from an empty table, as the brief says.

**Finding 3 - the DB enum and the workers' vocabulary do not intersect.**

    $ select enumlabel from pg_enum ... where typname='checkpoint_status'
    pending
    complete
    failed
    skipped

What the 15 call sites actually send (grep over `ivgs-workers/tasks/`):

| Sent | Valid enum label? |
|---|---|
| `"running"` (6 sites) | **no** |
| `StageStatus.SUCCESS.value` = `"success"` | **no** |
| `StageStatus.PARTIAL_SUCCESS.value` = `"partial_success"` | **no** |
| `StageStatus.FAILED.value` = `"failed"` | yes |

`StageStatus` is `models/task_result.py:53-58`. **Adding the POST route alone would
make 3 of 4 status values fail on the Postgres enum**, so the checkpoint table would
stay empty except for failures. This is not in the brief and it is load-bearing.

### Evidence basis: INFERRED FROM READING CODE

**Finding 4 - there are 15 call sites, not 5.**

The brief, `dev/CLAUDE.md` s7 and swallow-register entry 3 all say five. Actual, at
`9af5a48`:

    stage1_transcript.py:493, :625, :678        stage2_storyboard.py:511, :688
    stage3_images.py:683, :734                  stage5_voiceover.py:606, :655
    stage7_prototype_draft.py:447, :561         stage8_final_render.py:706
    video_generation_task.py:512                talking_head_task.py:926
    pipeline_orchestrator_v2.py:625

Fifteen. None checks the return value. `save_checkpoint` is
`utils/error_handler.py:395-448`; the brief's `:409` (the POST) is `:427` and its
`:435-441` (warn-and-return-False) is `:434-441`. Drift, all sites present.

**Finding 5 - one call site would raise TypeError if it ever ran.**

`pipeline_orchestrator_v2.py:625-633`:

    save_checkpoint(
        job_id=job_id,
        stage=PipelineStage.COMPOSITION_MANIFEST.value,   # <-- no such parameter
        checkpoint_data={...},
    )                                                     # <-- no stage_name,
                                                          #     stage_index, status

The signature is `save_checkpoint(job_id, stage_name, stage_index, status,
checkpoint_data)`. Commit `0ca2e78` (2026-06-07) fixed exactly this shape in Stage 6
- "save_checkpoint uses stage_name/stage_index/status (was bad stage= kwarg)" - and
missed this one.

**It is latent, not live.** `STAGE_TASK_MAP` (`:106`) dispatches
`tasks.stage4_manifest.build_composition_manifest`, a different module. The
orchestrator's own `build_composition_manifest` is registered and never dispatched -
the "filenames are not task identities" trap (runbook s6.4) in its other form: a
registered task nothing routes to. Had it been dispatched, the TypeError would have
been caught by the `except Exception` at `:642` and the job marked failed after the
manifest was already saved.

**Finding 6 - `POST /resume` does not resume. The dispatch is commented out.**

`ivgs-api/app/services/checkpoint_service.py:169-175`:

    # Phase 5: dispatch Celery task
    # celery_app.send_task(
    #     "pipeline.execute_stage",
    #     args=[str(new_job.id)],
    #     kwargs={"resume_from": resume_stage, "original_job_id": str(job_id)},
    # )

    return ResumeResponse(... message=f"Pipeline resumed from stage '{resume_stage}'...")

It inserts a `render_jobs` row carrying `resume_from_stage`, logs "Pipeline resume",
returns a 200 that **says** the pipeline resumed, and executes nothing. The brief
told me to read this rather than assume it works. It does not work.

The commented task name `pipeline.execute_stage` is not a registered task either -
nothing by that name exists in `celery_app.conf.include`'s modules.

**Finding 7 - and even if it dispatched, it would resume from the wrong stage.**

`checkpoint_service.py:127-137` hardcodes a stage order:

    "transcript_refinement", "storyboard_generation", "media_generation",
    "manifest_generation", "audio_generation", "talking_head_render",
    "prototype_draft", "final_render"

`PipelineStage` (`ivgs-workers/models/task_result.py:39-50`) - the values
`save_checkpoint` actually writes:

    transcript_refinement, storyboard_generation, image_generation,
    composition_manifest, tts_audio, talking_head_render, prototype_draft,
    final_render, video_generation, animation_generation

| Resume expects | Workers write | Match |
|---|---|---|
| `media_generation` | `image_generation` / `video_generation` / `animation_generation` | **no** |
| `manifest_generation` | `composition_manifest` | **no** |
| `audio_generation` | `tts_audio` | **no** |

Three of eight names are wrong. `:138-147`: if the completed stage is not found in
the list, `current_idx` stays `None` and `resume_stage = last_checkpoint.stage_name`
- **the stage that just completed**. So a job that got through image generation
would resume by re-running image generation, which is precisely what this package's
exit gate forbids.

`:112-116` also filters on `status == "complete"`, and no worker sends "complete"
(Finding 3), so today the filter matches nothing regardless.

**Finding 8 - `save_checkpoint` is swallow-register entry 3.**

`error_handler.py:434-441` logs `checkpoint_save_failed` at warning and returns
`False`; `:442-448` returns `False` on any exception. Fifteen callers, none checking.
Register entry 3 (`error_handler.py:395`) is this.

### Proposed fix

**In scope and being implemented:**

1. `ivgs-api/app/api/v1/checkpoints.py` - `POST /jobs/{job_id}/checkpoints`, matching
   the existing handlers' shape (`_verify_job_access`, service delegation, the same
   error envelope). RBAC: `require_operator_or_admin`, as `resume`/`clear` use.
2. `ivgs-api/app/schemas/checkpoint.py` - `CheckpointCreateRequest`.
3. `ivgs-api/app/services/checkpoint_service.py` - `upsert_checkpoint()`. UPSERT, not
   INSERT: `ix_pipeline_checkpoints_job_stage` is on `(job_id, stage_name)` and every
   stage writes twice (a "running" checkpoint then a terminal one), so a plain insert
   would leave two rows per stage and `list_checkpoints`'s "last successful" walk
   would be ambiguous.
4. **Status mapping, in the API schema.** `running -> pending`, `success -> complete`,
   `partial_success -> complete`, `failed -> failed`, plus the enum labels passed
   through unchanged. Done here rather than at 14 call sites because those are stage
   task bodies, which the brief puts out of scope.
5. `ivgs-workers/utils/error_handler.py` - `save_checkpoint` raises
   `CheckpointWriteError` instead of returning `False`. All 15 sites surface the
   failure without one of them being edited. A `required: bool = True` parameter is
   provided so a future caller can opt out explicitly rather than silently.
6. `ivgs-workers/tasks/pipeline_orchestrator_v2.py:625` - fix the TypeError.
7. Tests; swallow-register entry 3.

**In the brief, and NOT being implemented - scope stop-rule (common rule 6):**

| Item | Why stopped |
|---|---|
| Findings 6 and 7 - make `POST /resume` actually resume | Restoring the commented dispatch means the API publishing pipeline tasks to the broker, to a task name that does not exist, using a stage vocabulary that does not match. That is a design, not a fix. The brief also lists "resume UX" as out. |

**This is the finding that decides the exit gate.** The gate wants a killed worker to
resume without re-running completed stages. Rows are necessary and this package
delivers them; they are not sufficient, because the thing that consumes them is
commented out and its stage map is wrong. Stated now, not after.

### Decisions requested

| # | Decision |
|---|---|
| D-1 | Findings 6+7. Making resume real needs a package of its own: a registered resume task, a single shared stage vocabulary, and a decision on whether the API may publish to the broker. Scope it. |
| D-2 | Status mapping placement. Mapped in the API (in scope) rather than at 14 stage call sites (out of scope). The alternative is to widen the enum. Confirm. |
| D-3 | `save_checkpoint` now raises. A checkpoint-write failure will fail its stage. Deliberate - an unrecorded stage is an unresumable stage - but it changes 15 sites' failure semantics at once. Confirm. |
| D-4 | The exit gate cannot be met by an agent: it needs an API **and** worker deploy plus a killed worker on a live job. |

---

## Pass 2 - what changed

### Touched files, complete list

| File | Change |
|---|---|
| `ivgs-api/app/api/v1/checkpoints.py` | `POST /jobs/{job_id}/checkpoints` -> `create_checkpoint`, 201, `require_operator_or_admin`; module docstring |
| `ivgs-api/app/schemas/checkpoint.py` | `CheckpointCreateRequest`, `CHECKPOINT_STATUSES`, `WORKER_STATUS_MAP`, the `status` validator |
| `ivgs-api/app/services/checkpoint_service.py` | `upsert_checkpoint()` |
| `ivgs-workers/utils/error_handler.py` | `CheckpointWriteError`; `save_checkpoint` raises; `required: bool = True` |
| `ivgs-workers/tasks/pipeline_orchestrator_v2.py` | the `stage=` TypeError at `:625` |
| `ivgs-api/tests/test_wp07_checkpoint_write.py` | new, 19 tests |
| `ivgs-workers/tests/test_wp07_save_checkpoint_surfaces.py` | new, 20 tests |
| `dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | entry 3 fixed-with-evidence; entry 2's disposition corrected (below) |

**No stage task body was edited.** All fifteen call sites surface checkpoint
failures without one of them changing, because the raise is in `save_checkpoint`
itself and the status mapping is in the API schema.

### The change

**Route.** `POST /jobs/{job_id}/checkpoints`, shaped like the existing handlers -
`_verify_job_access`, service delegation, the same `{"error": {"code", "message"}}`
envelope. `require_operator_or_admin`, matching `resume` and `clear`.

**Upsert, not insert.** `ix_pipeline_checkpoints_job_stage` is on
`(job_id, stage_name)` and each stage writes twice - "running" at entry, its outcome
at exit. A plain insert would leave two rows per stage and make
`list_checkpoints`'s "last successful stage" walk depend on insertion order.
`started_at` is stamped once and preserved; `completed_at` only on a terminal
status. That pair is the per-stage duration the exit gate needs as proof a completed
stage did not re-execute.

**Status mapping** (`running -> pending`, `success -> complete`,
`partial_success -> complete`, `failed -> failed`, enum labels passed through). An
unrecognised value raises, so a typo 422s rather than silently becoming `pending`.

**`save_checkpoint` raises.** With `required: bool = True` as an explicit opt-out no
caller uses - and a test that fails if one ever starts.

### Verification - OBSERVED

**1. Live, before the fix.** Against the running `ivgs-fastapi` `v5.5.3-arch1`:

    POST /api/v1/jobs/00000000-.../checkpoints  ->  405 Method Not Allowed, allow: GET
    live OpenAPI: /jobs/{job_id}/checkpoints ['DELETE','GET']   (no POST)
    select count(*) from pipeline_checkpoints  ->  0

**2. The API half, against a real Postgres with every migration applied.**

    docker run -d --rm --name wp07-pg -e POSTGRES_DB=ivgs_wp07_test ... postgres:17.2
    alembic upgrade head            # ran 0001..0027, 36 tables
    TEST_DATABASE_URL=postgresql+asyncpg://.../ivgs_wp07_test \
      pytest ivgs-api/tests/test_wp07_checkpoint_write.py -q
    19 passed in 8.38s

A throwaway container, not the production database. `ivgs-api/tests/conftest.py:93`
refuses any database whose name does not end in `_test` - it TRUNCATEs every table
between tests - so this could not have been pointed at `ivgs` even by mistake.

Real Postgres was necessary, not preferred: `checkpoint_status` is a Postgres ENUM,
and the finding that matters most here (three of four worker statuses are not valid
labels) is invisible against SQLite or a mock.

Covered: POST is no longer 405 and returns 201; the row is **read back** through
`GET /checkpoints/{stage}` rather than trusting the 201; 404 for an unknown job; all
four worker statuses accepted and mapped; all four enum labels passed through; an
unknown status 422s; two writes leave one row; `started_at` survives the second
write and `completed_at` appears only at the end; distinct stages get distinct rows
and `last_successful_stage` is right; unauthenticated rejected, viewer 403, admin
201.

**3. No regression in the existing checkpoint suites.**

    pytest ivgs-api/tests/test_checkpoint_api.py ivgs-api/tests/test_service_checkpoint.py -q
    29 passed in 8.34s

**4. The worker half.**

    pytest ivgs-workers/tests/test_wp07_save_checkpoint_surfaces.py -q
    20 passed

Including `test_405_is_named_because_that_is_what_production_returned`, which drives
the exact live condition and asserts the raised message names the status, the job
and the stage. Eight HTTP codes plus a transport error are parameterised; the
success path is pinned; the payload shape is asserted against the route that now
accepts it; and two tests scan `ivgs-workers/tasks/*.py` to assert no call site opts
out of `required` and every call site passes `stage_name`.

**5. Whole-session worker regression.**

    pytest test_wp04 test_wp05 test_wp06 test_wp07 test_talking_head_task -q
    1 failed, 115 passed

The single failure is `TestStage6Input::test_requires_at_least_one_audio_ref`,
pre-existing at `9af5a48` and confirmed as such under WP-04 by stashing that
package's change and re-running it.

### Verification - NOT OBSERVED

- **Nothing deployed.** `ivgs-fastapi` still runs `v5.5.3-arch1` and still 405s;
  `ivgs-celery-default` still runs `v5.5.4-metrics`. Both halves need a build.
- No worker was killed mid-stage; no job was resumed; no checkpoint row was written
  by a real pipeline run. All three need the deploy above.
- The production `pipeline_checkpoints` table is still empty. Nothing in this
  session wrote to the production database.

### Exit gate: why it cannot be met, and it is not only the deploy

The gate: *kill a worker mid-stage on a test job; the job resumes without re-running
completed stages.*

Findings 6 and 7 say that cannot happen even after both deploys:

- **`POST /resume` executes nothing.** `checkpoint_service.py:169-175` - the Celery
  dispatch is commented out under a "Phase 5" heading. It inserts a `render_jobs`
  row, logs "Pipeline resume", and returns a 200 whose message says the pipeline
  resumed. The commented task name `pipeline.execute_stage` is not a registered task.
- **The resume stage map is wrong.** `checkpoint_service.py:127-137` expects
  `media_generation`, `manifest_generation`, `audio_generation`; the workers write
  `image_generation`, `composition_manifest`, `tts_audio`. Three of eight do not
  match, and `:138-147` falls back to `resume_stage = last_checkpoint.stage_name` -
  **the stage that just completed**. A job that got through image generation would
  resume by re-running image generation, which is precisely what the gate forbids.

This package delivers the necessary half - rows exist, and they are correct, dated
and de-duplicated. The sufficient half is a package of its own: a registered resume
task, one shared stage vocabulary between `checkpoint_service.py` and
`PipelineStage`, and a decision on whether the API may publish to the broker. That
is D-1.

Scope stop-rule (common rule 6): the brief lists "resume UX" as out and asked me to
**read** the resume implementation rather than assume it works. I read it, it does
not work, and I stopped rather than designing a resume dispatcher inside a package
scoped at "~40 lines per the ledger estimate".

### Deploy steps, left for the operator

    # node-01, per runbook s3.1 - derive the -f set from labels, do not guess
    docker compose -f ivgs-infra/docker-compose.node01.yml \
                   -f ivgs-infra/docker-compose.override.node01.yml \
                   -f ivgs-infra/docker-compose.monitoring.yml \
                   --env-file ivgs-infra/.env \
                   up -d --no-deps fastapi-backend celery-worker-default celery-worker-composition

    # then confirm the route is routed:
    docker exec ivgs-fastapi sh -lc 'python -c "
    import json,urllib.request
    s=json.load(urllib.request.urlopen(\"http://localhost:8001/api/v1/openapi.json\"))
    print(sorted(s[\"paths\"][\"/api/v1/jobs/{job_id}/checkpoints\"]))"'
    # expect: ['delete', 'get', 'post']

Worker nodes 02/03/04 need the same recreate for `save_checkpoint` to raise there.
**No migration is required** - `pipeline_checkpoints` already exists and this
package adds no column.

### Discrepancies recorded (common rule 4)

1. **Fifteen `save_checkpoint` call sites, not five.** The brief, `dev/CLAUDE.md` s7
   and swallow-register entry 3 all say five. Corrected in the register.
2. `error_handler.py:409` (the POST) is `:427`; `:435-441` is `:434-441`.
3. `pipeline_orchestrator_v2.py:625` would raise `TypeError` if dispatched. It is
   registered and unrouted - `STAGE_TASK_MAP:106` sends
   `composition_manifest` to `tasks.stage4_manifest.build_composition_manifest`.
   Fixed anyway.
4. The DB enum and the workers' status vocabulary intersect in exactly one value.
5. `POST /resume` does not resume (Finding 6) and its stage map is wrong (Finding 7).

### Swallowed-failure register

**Entry 3 marked FIXED, pending deploy**, with the evidence written out: the 405
measurement, the empty table, the fifteen call sites, and the twenty tests.

I did **not** mark it CLOSED. The register's own rule is "do not close one without
observed evidence that the failure now surfaces", and it does not surface in the
running system until the image is built - entry 1 sets that precedent
("Fixed, pending deploy"). **For the same reason I corrected entry 2's disposition,
written earlier in this session under WP-06, from CLOSED to FIXED, pending deploy.**
It was overstated; both fixes are in the tree and in neither image.

No new instance found. Noted not fixed: `error_handler.py:313, :383` (entry 8) are
the same shape in the same file, outside this brief's scope.

---

## Exit-gate verdict

**NOT MET.** Two reasons, one of them not fixable by a deploy.

| Gate clause | Status |
|---|---|
| `POST /jobs/{id}/checkpoints` exists and writes rows | **MET** - 19 tests against a real Postgres with the full migration chain; rows read back, not inferred from a 201 |
| A failed checkpoint write surfaces rather than vanishing | **MET** - 20 tests; the exact live 405 condition raises |
| Checkpoint rows in `pipeline_checkpoints` from a real run (query shown) | **NOT MET** - needs the API + worker deploy |
| Kill a worker mid-stage; the job resumes without re-running completed stages | **NOT MET** - and **not deploy-blocked**: `POST /resume`'s dispatch is commented out and its stage map disagrees with `PipelineStage` in three of eight names |

The brief calls this "the single biggest lever on long-render test cost". The lever
is now half-built and the half that is built is proven. The other half is D-1 and it
is a real package, not a leftover.

Commit-and-HOLD. Nothing pushed, nothing deployed.

---

## Operator rulings, 2026-08-23 — applied

| # | Ruling | Applied as |
|---|---|---|
| **D-1** | **RULED: do NOT build the real Celery resume.** The approved Temporal migration (AD-05, M3) replaces resume with event history; building it now is throwaway. The checkpoint rows have diagnostic value on their own. Add `POST /resume`'s false success to the swallow register as its own instance, and record in the ledger that resume-for-real arrives with M3. | `checkpoint_service.py`'s commented dispatch and its stage map are **left exactly as they are** — no code change. Swallow-register **instance 17** added. Ledger **P1.2** amended with a ruled block: do not build it, and why. |
| **D-2** | **CONFIRMED — status mapping in the API layer.** | No code change; `WORKER_STATUS_MAP` in `app/schemas/checkpoint.py` is where it shipped. Ledger P1.2 records the ruling and the reason: the 14 stage call sites are out of scope. |
| **D-3** | **CONFIRMED — `save_checkpoint` raising is correct.** | No code change. Ledger P1.2 records it, including the `required=False` opt-out and the test that fails if any call site starts using it. |
| **D-4** | Acknowledged — the exit gate needs an API **and** worker deploy plus a killed worker. | Exit-gate verdict above stands. |

### What D-1 changes about this package's verdict

The exit gate — *kill a worker mid-stage; the job resumes without re-running completed
stages* — is now **formally out of reach until M3**, by ruling rather than by
circumstance. That is a better outcome than leaving it open: the gate was written
against a resume mechanism that was never built and is now not going to be.

**What this package delivered is unaffected and stands on its own**, which is the
operator's stated reason for keeping it: `pipeline_checkpoints` will hold one row per
stage per job, with real outcomes and `started_at`/`completed_at` pairs — per-stage
durations, which is the first time this system has had them. That is diagnostic value
independent of resume, and it is available the moment the API and workers are rebuilt.

### Register instance 17, in brief

`checkpoint_service.py:169-175` returns HTTP 200 saying `"Pipeline resumed from stage
'...'"` having dispatched nothing — entry 5's *manufactures a success* shape, recorded
separately because the deceived caller is a **human operator through the API**, where no
downstream return-value check could help. It carries the second, latent defect too: the
stage map disagrees with `PipelineStage` in three of eight names, so even with rows it
would resume by re-running the completed stage.

**Entry 17 is OPEN and deliberately not fixed**, so the endpoint's lie stays on the
record until M3 removes it. The entry notes the minimum honest interim if anyone touches
the endpoint before then — a 501, or a message saying a resume job was *recorded* rather
than *resumed*.

### Observation, not acted on

The register's index table carries rows for instances 1–11, 16 and now 17. **Instances
12–15 have detail sections but no table row.** Pre-existing; not fixed here because
nothing in this batch's scope covers it, and adding four rows to someone else's register
index is the operator's call. Flagged so it is not mistaken for damage from this session.
