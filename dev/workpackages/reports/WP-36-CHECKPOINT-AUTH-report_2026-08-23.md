# WP-36-CHECKPOINT-AUTH — the worker was 401'd by the route built for it

| | |
|---|---|
| **Reported** | 2026-08-23, first end-to-end run. node-02 worker log 14:49:48: `PATCH /api/v1/jobs/{id}` succeeds with the worker's service auth, the checkpoint `POST` on the same job returns **401**, `save_checkpoint` raises `CheckpointWriteError` (as WP-07 designed), job `768c4b59` fails. |
| **HEAD at start** | `462f3f3` |
| **Date** | 2026-08-23 |
| **Ships** | `ivgs-api` + `ivgs-workers` as `v5.6.3-checkpointauth`; node-01, then nodes 02/03/04 by artifact copy |

## Root cause, confirmed in one line

WP-07 guarded `POST /jobs/{id}/checkpoints` with `require_operator_or_admin`, which resolves
through `get_current_user` and therefore **rejects the internal service token outright with 401
before any role is examined** — while the route's only production caller is the worker fleet,
which holds no human JWT.

**Not a token problem.** The worker sends the *same* credential to both routes —
`config.pipeline_api.service_token` (`IVGS_SERVICE_TOKEN`), at `error_handler.py:367` for the
PATCH that works and `:444` for the POST that fails. The difference is entirely the guard.

---

## 1. Isolated live, before changing anything

Run from inside `ivgs-celery-node02` with the worker's own config object, so the credential is
the real one and is never printed. A **nonexistent** job id was used deliberately: a route that
accepts the credential answers **404**, one that rejects it answers **401**, and nothing is
written either way.

```
base=http://192.168.1.90:8001/api/v1 token_len=17 (value never printed)
  PATCH /jobs/<bogus>              -> 404   (auth accepted, job absent)
  POST  /jobs/<bogus>/checkpoints  -> 401
        body: {"detail":{"error":{"code":"AUTHENTICATION_REQUIRED",
                                  "message":"Invalid authentication credentials"}}}
```

Same client, same host, same token, same request second — 404 on one route, 401 on the other.
That is the whole defect, with no ambiguity left in it.

| | Guard | Resolves through | Service token |
|---|---|---|---|
| `PATCH /jobs/{job_id}` (`jobs.py:110`) | `get_service_or_user` | service token **or** user JWT | **accepted** |
| `POST /jobs/{job_id}/checkpoints` (`checkpoints.py:117`) | `require_operator_or_admin` | `get_current_user` only | **401** |

`get_service_or_user` (`auth.py:152`) compares the bearer token against
`settings.IVGS_SERVICE_TOKEN` and resolves a match to the seeded `svc-pipeline` account —
verified in the live database as `role=admin, is_active=t`.

## 2. The fix

`require_service_or_privileged_user` **already existed** (`rbac.py:88`) for exactly this shape:
accepts the internal service token *or* an operator/admin human, and still denies viewers with
403. The change is a one-line dependency swap on the single route the worker calls.

```diff
-    current_user: User = Depends(require_operator_or_admin),
+    current_user: User = Depends(require_service_or_privileged_user),
```

**Deliberately not widened elsewhere.** `POST /resume`, `DELETE /checkpoints` and the two GET
routes stay human-only — no worker calls them, and tests pin that they still refuse the service
token. `_verify_job_access` (`checkpoints.py:40`) needed no change: it short-circuits its
ownership check for `ADMIN`, which `svc-pipeline` is.

## 3. Why 19 existing tests missed it

Every one of WP-07's 19 tests authenticates as `operator_token` — a human JWT. The route was
never once exercised as the caller that actually uses it. **The gap was the test's identity, not
its coverage**, and no amount of additional human-token cases would have found it.

`ivgs-api/tests/test_wp36_checkpoint_service_auth.py` — **13 tests, all passing** — sends the
shape the worker really sends: `Authorization: Bearer <IVGS_SERVICE_TOKEN>` against a
`svc-pipeline` account seeded through the same `create_user` path as
`app/scripts/seed_service_account.py`, so the fixture cannot drift from how the account exists in
production.

Coverage: the service token is not 401'd and returns 201; **a row actually lands** (read back and
asserted, because 201 alone is not WP-07's point); all four statuses the worker sends
(`running`/`success`/`partial_success`/`failed`) are accepted over service auth; the bogus-job
diagnostic returns 404 not 401; operators still work; **viewers still get 403**; unauthenticated
and wrong-token still denied; and `/resume` and `DELETE` still refuse the service token.

**Shown to discriminate.** With the guard temporarily reverted to
`require_operator_or_admin`, **7 of the 13 fail**; with the fix, 13/13 pass. WP-07's original 19
tests still pass unchanged — the gate was widened, not loosened.

## 4. Second defect — the DLQ filing crashed while handling the failure

From the same log: `dlq_routing_failed` with a pydantic `ValidationError`, `job_id` and
`project_id` both `None`.

`create_error_detail` (`error_handler.py:189`) declares both as `Optional[str] = None` and passes
them straight into `ErrorDetail`, where they are non-optional `str = ""`
(`models/task_result.py:314-315`). **Any task failing early enough not to know its own ids cannot
be filed** — and those are the failures most worth keeping.

**The consequence is worse than a noisy log.** `IVGSBaseTask._route_to_dlq`
(`celery_app.py:786`) catches it and logs `dlq_routing_failed` at critical, so nothing crashes,
nothing retries, and **the DLQ record is never written**. The failure is dropped from the queue
whose entire purpose is to retain it. A failure handler that fails is the worst place for this
pattern: it only runs when something has already gone wrong, so its own defects stay invisible
until they compound with another fault — which is exactly how this surfaced.

**Fixed** by coercing at the boundary (`job_id or ""`, `project_id or ""`, and the retry counters,
which are `None` outside a task context). The model contract is deliberately unchanged: `""` is
what `ErrorDetail` already declares as its absent value, and the DLQ schema and table are built
on it. 10 tests in `ivgs-workers/tests/test_wp36_dlq_missing_ids.py`, including one asserting
`ErrorDetail(job_id=None)` **still** raises — proof the fix is the coercion, not a quiet widening
of the model.

**Registered as swallow-register instance 20**, adjacent to instance 8 (same consequence, reached
by a different mechanism: there the error path returned `False`, here it threw and something else
ate it). **Not closed** — what is observed is that the record can now be *built*; nobody has yet
watched a real early-failing task land in the DLQ.

---

## 5. Build and deploy

Built from `c6f0968` under WP-34's binding rules. **Both** images changed, so all four nodes
were deployed — the worker fix (`error_handler.py`) ships in the workers image that every node
runs.

| | `ivgs-api` | `ivgs-workers` |
|---|---|---|
| Tag | `v5.6.3-checkpointauth` | `v5.6.3-checkpointauth` |
| Image id | `sha256:3efe34fbeaf0…` | `sha256:165b41c361fe…` |
| Banked **before** push | sha256 rc 0, `zstd -t` rc 0, 1 MANIFEST line, config blob present | same |
| Push (separate) | rc 0, registry digest **matches** local id | rc 0, **matches** |

**Content gates — all pass.** `create_checkpoint` uses `require_service_or_privileged_user` and
no longer `require_operator_or_admin`; `require_service_or_privileged_user` is present in the
image's `rbac.py`; **the two sibling routes still carry `require_operator_or_admin`** (count
exactly 2), proving the widening was surgical; the DLQ coercions are present.

> One negative gate was mis-scoped by me and is recorded rather than quietly re-run. A file-wide
> grep for `job_id=job_id,` in `error_handler.py` returns 1 — that hit is
> `route_to_dead_letter_queue` **calling** `create_error_detail` and legitimately passing whatever
> it has, which may be `None`. That is precisely the input the fix exists to tolerate; coercing
> there too would be redundant. Re-scoped to the `ErrorDetail(...)` construction, the gate returns
> 0 and the four coerced arguments are visible.

**Deploy.** node-01: `fastapi-backend`, `celery-worker-default`, `celery-worker-composition`,
`celery-beat` recreated (`--force-recreate --no-deps --pull never`). Nodes 02/03/04: workers
image distributed **by artifact copy + `docker load`**, never the registry; presence-gated before
each `.env` write; rollback tag recorded from `.Config.Image` first and `v5.6.0-m2` confirmed
still present on each; only the single worker service recreated per node. Every `.env` backed up
to `.env.bak.pre-wp36-<ts>`; none committed.

Postgres, Redis, SeaweedFS, the scheduler and node-04's engine containers were untouched.
`celery inspect active_queues`: **5 workers online, queue map identical to the baseline.**

## 6. Post-deploy verification — from inside the node-02 worker

The check the operator asked for, run with the worker's own credential inside
`ivgs-celery-node02`:

```
PATCH /jobs/<bogus>                  -> 404
POST  /jobs/<bogus>/checkpoints      -> 404   (was 401 - auth now accepted)
POST  /jobs/768c4b59.../checkpoints  -> 201   ← the real job from the failure
```

Then the **real production code path**, not a hand-rolled request — `save_checkpoint`, the exact
function that raised `CheckpointWriteError` at 14:49:48:

```
[info] checkpoint_saved job_id=768c4b59-9df5-4c3a-809a-80d3800142f5
       stage_name=wp36_post_deploy_verification status=running
  save_checkpoint returned True  -> NO CheckpointWriteError
```

**And the row landed:**

```
          stage_name           | status  |          created_at
-------------------------------+---------+------------------------------
 wp36_post_deploy_verification | pending | 2026-08-23 15:06:04.29803+00
```

That is the first checkpoint this pipeline has ever successfully written. `running` → `pending`
is WP-07's documented status mapping working as designed.

> The verification row is left in place on job `768c4b59` as evidence. It is a probe row on a job
> that already failed; delete it if it is noise.

## 7. Bonus — WP-24's outstanding exit-gate clause is now MET

The operator ran the WP-24 §2.5 GPU-exporter block on node-04 today (ruling 2).
`ivgs-nvidia-gpu-exporter` is **Up 7 hours** there and serving 11 `nvidia_smi_*` metrics, so the
Node Monitor now carries real telemetry for that node:

```
node-04  online   vram=38316.0   util=0.0   temp=31.0
```

which matches `nvidia-smi` on the box. **WP-24's node-04 clause — "real, changing VRAM/util/temp"
— is met.** Note `util=0.0` is a genuine zero reading rather than `null`, which is exactly the
distinction WP-24's `test_a_real_zero_reading_survives` pinned. node-02 and node-03 still read
`null`, correctly: their exporters were not fixed, per "extend nothing".

## 8. Retrigger

The failed job `768c4b59-9df5-4c3a-809a-80d3800142f5` is still `running` in `render_jobs` — its
task died without a terminal status. Clear it first, then retrigger the project:

```
# RUN ON: IVGS node-01 (192.168.1.90)
docker exec -i ivgs-postgres psql -U ivgs -d ivgs -c \
  "UPDATE render_jobs SET status='failed' WHERE id='768c4b59-9df5-4c3a-809a-80d3800142f5';"
```

Then, signed in to the GUI as operator/admin, open project
`c12fa967-f989-4ed4-8e20-3ea62cb92e8f` ("double digit multiplication") and trigger the pipeline —
or by API:

```
POST /api/v1/projects/c12fa967-f989-4ed4-8e20-3ea62cb92e8f/trigger?tier=prototype
```

**Before retriggering, note the Model Store is still unpopulated** — the WP-33 checklist has not
been executed, so Stage 1 will fail to resolve a binding (`SelectionError`) rather than reaching
the checkpoint path again. The checkpoint fix is verified independently above; the retrigger will
exercise it end-to-end only once the checklist is done.

## 9. Not verified

- **No pipeline run.** The fix is verified by direct probe and by the real `save_checkpoint`
  function against the real job, not by a stage completing and checkpointing on its own.
- **Register instance 20 is not closed.** The DLQ record can now be *built*; nobody has watched a
  real early-failing task land in the DLQ.
