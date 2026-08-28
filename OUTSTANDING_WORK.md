# IVGS v5 — Outstanding Work (Single Source of Truth)

| | |
|---|---|
| **Version** | **v4.1 — 2026-08-14 (evening).** Updates v4.0 with the storage migration, the backup remediation, and the Step-10 cross-system register. v4.0 superseded v3.1 + Addenda A/B, all folded in. |
| **Repo state** | `brucecostello2/elearning_v5` @ `main` = **`e1f4c58`**. node-01 and `origin/main` in exact sync. `.env.node01` now untracked and gitignored (P1.5 CLOSED). |
| **Live stack** | **As of 2026-08-23 (P1.4p):** ivgs-api `v5.6.0-m2`, ivgs-workers `v5.6.0-m2` **on all four nodes**, ivgs-frontend `v5.6.0-m2`, ivgs-scheduler `latest` (unpinned — P2.11), ivgs-backup-worker `v5.1.0-stream-b` (not rebuilt). Alembic head **0027**. |
| **Code currency** | The tree at `e613e844` was byte-identical to the 2026-07-10 capture — no code had been committed for five weeks. Two commits landed 2026-08-14: `1f0fd31` (backup rsync/NFS) and `e1f4c58` (untrack `.env.node01`, record host config). |
| **Infrastructure** | node-01 memory is **31 GB reduced to 16 GB** — every prior document said 16 GB and was wrong; the VM was over-provisioned. Proxmox host `n5Pro` was **OOM-killing VMs**; 32 GB swap added. Backup NAS migrated `.9` CIFS (100% full) → **`.7` NFS4.2** (22 TB). |
| **Sources merged** | v3.1 ledger; Addendum A; Addendum B; `SESSION_HANDOFF_2026-07-09.md` register; `AD-04-v3` + its Phase-0 analysis; Master Plan v0.3; AD-01/02/03; direct code audit of `e613e844` (2026-08-14). |
| **Operating principle** | *"Fix, don't park — clean as we go."* Nothing is deferred without an entry. Closures require evidence (commit SHA, image tag, file:line, or transcript pointer). |
| **Companion docs** | `OUTSTANDING_WORK_archive_v3.1.md` (full historical closure detail — nothing lost); `IVGS_v5_Master_Sequence_Plan_to_Production.md` (milestone map); `IVGS_v5_Addendum_AD-05_Orchestration_Migration.md` (to be authored — WS-T). |

---

## Priority definitions

- **P0 — Blocking.** System broken or unsafe; address before any other work.
- **P1 — High.** Blocks the critical path, hides regressions, or required for the next increment.
- **P2 — Medium.** Real defect or hygiene work; will compound if deferred.
- **P3 — Low.** Cosmetic, documentation, or strategic multi-session work.
- **DEFERRED.** Consciously not-now, with a stated reason and a re-open trigger.

## Snapshot

| Priority | Count | Headline |
|---|---|---|
| **P0** | 1 | D1 broker visibility timeout → duplicate GPU execution *(P0.2 backup gap CLOSED 2026-08-14)* |
| **P1** | 9 | ORCH-6 head-model binding on the dead file; D2 join; D3 checkpoints; D4 GPU reservations; backup reporting; prompt ENUM; smoke; GPU acceptance; AD-02 governance |
| **P2** | 31 | orphaned operational layer (F1); zero orchestrator tests (F2); orchestrator cleanup (F3); 4xx cluster; ORCH-5 state; GPU telemetry; + carried hygiene |
| **P3** | 17 | dead code; test coverage; UI polish; schema parity; observability |
| **DEFERRED** | 2 | comprehensive DR; localisation |
| **WS-T** | 7 | Temporal orchestration migration (new workstream) |
| **§S** | 10 | Cross-system seam items (new — belong to neither register) |

## Pipeline status (2026-08-14)

| Stage | State |
|---|---|
| 1 transcript_refinement | ✅ proven e2e |
| 2 storyboard_generation | ✅ proven e2e; user gate working |
| 3 media (image/video/animation) | ✅ proven e2e; scene-linked |
| 4 composition_manifest | ✅ proven e2e; server-side build, locked manifest |
| 5 tts_audio | ✅ proven e2e; 48 kHz/24-bit, scene-linked |
| 6 talking_head_render | ✅ **runs** (LatentSync, node-04) — ⚠️ engine **hardcoded**, not AD-01-selectable (ORCH-6) |
| 7 prototype_draft | ✅ proven — draft `f78eb063`, 214.94s, 1280×720, corruption 6/6 |
| 8 final_render | ✅ **runs** — final `9007b2cf`, **215.07s, 1920×1080, 30fps, AAC 48k stereo**; used as evidence in the AD-04 head-model judgment. ⚠️ never formally validated; visual QA outstanding (M1-QA) |

> **Correction to all prior documents.** v3.1 and Addendum B show Stage 6 as *BUILD REQUIRED* and Stages 7/8 as *unbuilt/untested*. That is two months stale. **All eight stages execute end-to-end.** The remaining M1 work is validation and model-binding, not construction.

## Critical path (in order)

1. **ORCH-6** — make the head model selectable, else the entire MBCP certification chain is unconsumable.
2. **M1-QA** — visual acceptance of `final_1080p_9007b2cf.mp4`; formal Stage-8 validation.
3. **D1–D4** — the four orchestration correctness defects.
4. **WS-T** — orchestration migration, before fleet rollout and before long-video testing.

---

# P0 — Blocking

## P0.1 — `broker_visibility_timeout` below two tasks' hard time limits → duplicate execution *(new, code audit 2026-08-14; was "D1")*
**Status:** OPEN — live latent defect, verified at `e613e844`.
`config.py:214-215` sets `broker_visibility_timeout = 3600`. `talking_head_task.py:284` and `video_generation_task.py:445` both declare `time_limit=3900`. With the Redis broker and `task_acks_late = True` (`celery_app.py:293`), a message unacked past the visibility timeout is **redelivered while the original still runs**.
- `gpu_video` is consumed by node-02 **and** node-03 → the duplicate can execute **concurrently on the other node**, two CogVideoX jobs on the same scene contending for VRAM.
- `gpu_talking_head` is node-04 only → duplicate runs sequentially, wasting a full render.
- Either way the duplicate reaches the task tail and fires `handle_stage_completion` again → **double join decrement** (P1.2).

Latent today only because renders are short; near-certain at the M3 30-minute target.
**Scope/action:** raise `IVGS_BROKER_VISIBILITY_TIMEOUT` above the longest hard `time_limit` with margin (7200); add a config-time assert that `visibility_timeout > max(task time_limit)`. One config line + one guard. **Do not** swap the broker for this — WS-T removes the mechanism entirely.

---

# P1 — High Priority

## P1.0 — ORCH-6: live Stage-6 task hardcodes LatentSync; ARCH-1 provider binding is on the *dead* duplicate *(new, code audit 2026-08-14)*
**Status:** **CLOSED 2026-08-15** by WP-02-ORCH6 — code complete and unit-verified on
node-01; **the on-hardware GUI-swap gate is outstanding and is operator-run** (node-04).
Report: `dev/workpackages/reports/WP-02-ORCH6-report_2026-08-15.md`.

**What was wrong.** `STAGE_TASK_MAP` dispatches `tasks.talking_head_task.render_talking_head`.
That live file imported `LatentSyncClient` directly — the engine was hardcoded. The
AD-01/ARCH-1 provider-factory implementation lived in `stage6_talking_head.py`, the dead
duplicate nothing dispatched. Certified MBCP models could not be selected.

**What changed.** The binding was promoted into the live task: `ensure_registered()` +
`get_binding("talking_head", project_id=..., tier=...)` + `build_provider(...)` resolved
once per job, the GPU reservation now asks for `binding.name` /
`provider.vram_requirement_mb()`, each segment renders through `provider.render(...)`, and
`model_used` is stamped from `binding.name`. The duplicate and its test are deleted; all
map, route, `imports` and `__all__` references are cleaned. The registered task name,
segment/OOM strategy, AD-03 Pillar-2 behaviour and the correct
`/projects/{id}/assets/upload` URL are unchanged.

**Three things this did NOT close — carried forward.**

1. **The SadTalker fallback is still engine-direct.** `SadTalkerProvider` requires a
   per-scene still image that this whole-project stage does not have, so a
   `sadtalker`-engine selection raises `ValueError` at render time. A true cross-engine
   GUI swap needs that provider fixed. *(New item — see P1.0a.)*
2. **AD-01.13 criterion 5 remains open.** Stage 6 renders once and both Stage 7 and
   Stage 8 consume the single asset, so prototype- and production-tier models cannot be
   applied to draft and final respectively without a pipeline change. `tier` is a
   constant (`"prototype"`) on `Stage6Input`.
3. **Stage 6 now fails loudly** with `SelectionError` when no approved, enabled, default
   `talking_head` model exists. Deliberate: a silent fallback to a hardcoded engine would
   make a GUI swap appear to work when it had not.

*(Note: Stage 8 consumes a pre-rendered head asset by `asset_id` and overlays it — it does
not render the head. B5's "Stage 8 must bind via the factory" was misframed; the binding
belongs at Stage 6. Recorded here so B5 is not lost.)*

## P1.0a — Stage-6 SadTalker fallback is not selection-driven *(new, WP-02-ORCH6 finding F2, 2026-08-15)*

**⚖ RULING (operator ruling 2026-08-28): CLOSED — superseded by AD-01 selection.** The row asked whether
the Stage-6 SadTalker fallback is selection-driven work. It is not work: AD-01 selection
is the mechanism that chooses a Stage-6 engine, and a hardcoded fallback inside a provider
is not a second opinion it is entitled to. **One cross-check carries forward, and only one:
at M3.3-R3 (activities realized), confirm that NO HARDCODED SadTalker FALLBACK SURVIVES the
stage-6 activity realization.** That is a line on the M3.3-R3 checklist, not a reopening of
this row — see §RC-I.1.

**Status:** CLOSED *(was: OPEN — blocks a true cross-engine GUI swap at Stage 6.)*
`ivgs-workers/providers/talking_head.py` `SadTalkerProvider.render` raises
`ValueError("sadtalker provider requires scene image and voiceover audio")` unless a
per-scene still is supplied. Stage 6 renders the presenter from the reference clip against
narration audio and has no scene image, so the provider cannot serve this stage. The live
task therefore keeps its own engine-direct `_render_with_sadtalker` fallback.

Second, independent defect in the same provider: `_spill` writes bytes to a **worker-local**
`tempfile.TemporaryDirectory()`, and `SadTalkerClient._submit_job` posts those paths as JSON
to the remote SadTalker service, which cannot open them unless it shares the worker's
`/tmp`. **Unverified against a running SadTalker service** — node-04 was out of scope.

Three mutually incompatible SadTalker contracts now exist: the live task's
`POST {base}/generate` multipart (the only one exercised), `SadTalkerClient`'s
`POST /api/render` JSON-of-paths, and `SadTalkerProvider`'s worker-local paths handed to the
second. **Which one node-04 actually implements is unknown and should be established first.**

## P1.0b — Every GPU node except node-01 names a database driver that is not installed; this blocks the entire AD-01 binding on the fleet *(new, WP-02 check-6b deployment, 2026-08-15)*

**⚖ RULING (operator ruling 2026-08-28): CLOSED.** WP-IVGS-08 Task 8 settled it by measurement: **nine
consumers connect; the engines are not consumers.** A vLLM server is not a Celery worker and
does not open a database session, so "every GPU node names a driver that is not installed"
was true of a set that does not include the engines. The nodes that DO bind (the Celery
workers on 02/03/04) use `+asyncpg` and connect.

**Status:** CLOSED *(was: OPEN — **node-04 fixed; nodes 02, 03, 05, 06 still broken.** Severity proposed P1; operator to confirm.)*

**The defect.** `DATABASE_URL` in the per-node compose files:

```
docker-compose.node01.yml   postgresql+asyncpg     <- correct
docker-compose.node02.yml   postgresql+psycopg     <- broken
docker-compose.node03.yml   postgresql+psycopg     <- broken
docker-compose.node04.yml   postgresql+asyncpg     <- FIXED 2026-08-15 (was +psycopg)
docker-compose.node05.yml   postgresql+psycopg     <- broken
docker-compose.node06.yml   postgresql+psycopg     <- broken
```

The workers image ships **`psycopg2` and `asyncpg`, not `psycopg` (v3)** — verified by
import inside `ghcr.io/brucecostello2/ivgs-workers:v5.5.2-orch6` on both nodes. So
SQLAlchemy's `postgresql+psycopg` dialect raises at engine creation:

```
ModuleNotFoundError: No module named 'psycopg'
  sqlalchemy/dialects/postgresql/psycopg.py -> import psycopg
```

`DATABASE_URL` is consumed **only** by `create_async_engine` (`shared/database.py:38`,
`ivgs-workers/tasks/periodic_tasks.py:656`), so it must name an **async** driver
regardless — `psycopg2` would not work either. `asyncpg` is the only installed async
driver, and node-01 has used it successfully throughout.

**Why it was invisible until now.** Pre-ARCH-1 worker images never opened a database
session from a worker, so the wrong driver cost nothing. ARCH-1 changed that:
`get_binding` opens a short-lived session (`factory.py:218-221`). **Any GPU node
running an ARCH-1 image cannot resolve a model binding** — which fails Stages 1, 2, 3
and 5 (already factory-bound per AD-01.12) as well as Stage 6 (WP-02).

**Observed.** On node-04 with `v5.5.2-orch6` and the original `+psycopg`, the first
`get_binding` call raised `ModuleNotFoundError`. After changing the line to `+asyncpg`
and recreating, the same call returned
`latentsync-alt [latentsync] tier=prototype via=default endpoint=http://latentsync:7860`
and `LatentSyncProvider` built with `engine_health: True`.

**This is a hard blocker for M4 (fleet rollout).** Standing up nodes 02/03/05/06 on any
ARCH-1 image without this fix will fail every model-bound stage on those nodes, and the
failure surfaces as a Python import error deep in SQLAlchemy rather than as anything
that names the real cause.

**Scope/action:** change `postgresql+psycopg` to `postgresql+asyncpg` in
`docker-compose.node02.yml`, `node03`, `node05`, `node06` (one line each; node-04 is
done). Leave `db+postgresql+psycopg2` result-backend URLs alone — psycopg2 **is**
installed and that path is sync. Consider a start-up assertion in the worker that
resolves the configured driver and fails loudly at boot rather than at first query.

*(node-04's on-disk checkout was edited directly to unblock verification and now differs
from the repo until synced; a backup `docker-compose.node04.yml.bak.pre-asyncpg` sits
beside it.)*

## P1.1 — Media join advances prematurely on Redis error; not idempotent *(new, code audit; was "D2")*
**Status:** **FIXED 2026-08-23 by WP-06-MEDIA-JOIN; DEPLOYED 2026-08-23 in `v5.6.0-m2` (P1.4p).** The `unknown` outcome was observed live on the deployed image - swallow-register entry 2 is CLOSED. Report:
`dev/workpackages/reports/WP-06-MEDIA-JOIN-report_2026-08-23.md`. All four exit-gate
clauses met against a real Redis. Swallow-register entry 2 marked fixed-pending-deploy.

> **CORRECTED, operator ruling 2026-08-23 (WP-06 D-1).** The scope line below says a
> per-`(job_id, scene_id)` SETNX guard. **There is no scene granularity in the join.**
> `dispatch_media_generation` increments `total_media_tasks` once per media **stage**
> dispatched — image / video / animation, at `:471`, `:491`, `:512` — so the counter's
> maximum is 3, each stage sends exactly one whole-stage completion, and no callback
> carries a `scene_id`. The correct key is **`(job_id, completed_stage)`**, and that is
> what shipped. The guard and the decrement are one Lua script, so a Redis failure
> leaves nothing done and the task's retry is clean.
>
> **WP-06 D-2, ruled 2026-08-23:** a callback arriving after `media_join_watchdog` has
> claimed the job now reports `unknown`, retries, and lands in the DLQ. The pre-fix code
> decremented a missing key to `-1`, clamped to `0`, and **dispatched Stage 4 a second
> time**. The louder behaviour is wanted.

`pipeline_orchestrator_v2.py:869-880` — `_decrement_media_task_count` returns **`0`** on any exception. The caller at `:672` treats `remaining <= 0` as *"all media reported, dispatch Stage 4."* A single transient Redis error during any one scene's callback **advances the pipeline with incomplete footage**. Same class: `_store_media_task_count` (`:856-866`) swallows its failure — if the counter was never written, `decr` on a missing key returns `-1`, `max(0,-1) == 0`, and the join collapses on the *first* scene to report.
No idempotency: every media task fires the callback at the end of its body then returns (`stage3_images.py:736-741`, `video_generation_task.py:574-580`); with `acks_late` + `task_reject_on_worker_lost`, a worker death in that window requeues and re-decrements.
**Scope/action:** distinguish "unknown" from "zero" (return `None` / raise and let the task retry); per-`(job_id, scene_id)` SETNX guard on the decrement.

## P1.2 — Checkpoint subsystem is a silent no-op; `resume` has nothing to resume from *(new, code audit; was "D3"; supersedes the P2.27 405 line item)*
**Status:** OPEN — **upgraded from P2.** Prior framing ("non-blocking 405 noise") understated it.
`utils/error_handler.py:409` POSTs to `/jobs/{job_id}/checkpoints`. `ivgs-api/app/api/v1/checkpoints.py` declares only `GET /checkpoints` (`:79`), `GET /checkpoints/{stage}` (`:106`), `POST /resume` (`:137`), `DELETE /checkpoints` (`:175`). **There is no `POST /jobs/{id}/checkpoints`** — hence the 405. `save_checkpoint` logs a warning and returns `False` (`:435-441`); **no call site checks the return value**. Every stage calls it; nothing is ever written. `POST /jobs/{id}/resume` therefore resumes from an empty table.
The §6.2 checkpoint/resume guarantee is **fictional**. This is the only stated mechanism for not re-running a 30-minute render after a transient failure — i.e. the single biggest lever on long-video test-cycle cost.
**Scope/action:** ~~add the POST route (~40 lines) + assert on the return value at call sites~~ — **both DONE 2026-08-23 by WP-07-CHECKPOINTS; DEPLOYED 2026-08-23 in `v5.6.0-m2` / `ivgs-api:v5.6.0-m2` (P1.4p).** The route is live (OpenAPI shows `post`; the 405 is gone) and `CheckpointWriteError` was observed raising on the deployed image - swallow-register entry 3 is CLOSED. Report: `dev/workpackages/reports/WP-07-CHECKPOINTS-report_2026-08-23.md`.

> **What WP-07 found that this item did not have.**
> - **15 `save_checkpoint` call sites, not 5.** This item, `dev/CLAUDE.md` §7 and
>   swallow-register entry 3 all said five. Corrected in the register.
> - **The Postgres enum and the workers' vocabulary share exactly one value.**
>   `checkpoint_status` is `pending|complete|failed|skipped`; the workers send
>   `running|success|partial_success|failed`. Adding the route alone would have left the
>   table holding nothing but failures. **Operator ruling 2026-08-23 (WP-07 D-2):** map in
>   the API schema, not at the 14 stage call sites, which are out of scope. Done.
> - **Operator ruling 2026-08-23 (WP-07 D-3):** `save_checkpoint` **raising** is correct —
>   an unrecorded stage is an unresumable stage. A `required=False` opt-out exists; a test
>   fails if any call site starts using it.
> - `pipeline_orchestrator_v2.py:625` passed `stage=` and would raise `TypeError` if it
>   ran. It is registered and unrouted (`STAGE_TASK_MAP:106` sends `composition_manifest`
>   to `tasks.stage4_manifest.build_composition_manifest`). Fixed anyway.

> ### RULED 2026-08-23 (WP-07 D-1): resume-for-real is NOT being built. It arrives with M3.
>
> `POST /jobs/{id}/resume` **executes nothing.** `ivgs-api/app/services/checkpoint_service.py:169-175`
> — the Celery dispatch is commented out under a "Phase 5" heading, and the task name it
> names, `pipeline.execute_stage`, is not registered anywhere. The endpoint inserts a
> `render_jobs` row, logs "Pipeline resume", and returns a 200 whose message says the
> pipeline resumed. Its stage map (`:127-137`) also disagrees with `PipelineStage` in
> three of eight names — it expects `media_generation`, `manifest_generation`,
> `audio_generation` where the workers write `image_generation`, `composition_manifest`,
> `tts_audio` — and `:138-147` falls back to `resume_stage = last_checkpoint.stage_name`,
> i.e. **the stage that just completed**.
>
> **Do not build it.** The approved Temporal migration (AD-05, WS-T, M3) replaces
> resume-from-checkpoint with workflow event history; a real resume dispatcher written now
> is throwaway. **The checkpoint rows have diagnostic value on their own** and that is why
> WP-07 shipped — per-stage `started_at`/`completed_at`, real outcomes, one row per stage.
>
> **`POST /resume`'s false success is swallow-register instance 17**, added 2026-08-23:
> it manufactures a success, the same shape as entry 5.


## P1.3 — GPU reservations: 7 acquires, 4 releases, and 3 of those raise `TypeError` *(new, code audit; was "D4"; absorbs old P3 "extra-kwarg debt")*
**Status:** **FIXED 2026-08-23 by WP-08-GPU-RESERVATIONS; DEPLOYED 2026-08-23 in `v5.6.0-m2` (P1.4p)** - `release_acquired_reservation` verified present in every running worker on all four nodes. Report: `dev/workpackages/reports/WP-08-GPU-RESERVATIONS-report_2026-08-23.md`.
> **CORRECTED 2026-08-23 by WP-08.** The `TypeError` claim below was **right and is now
> proven on the deployed image** — inside `ivgs-celery-default` running
> `ivgs-workers:v5.5.4-metrics`, whose `gpu_utils.py` is byte-identical to the tree:
> `TypeError: release_gpu_reservation() takes 1 positional argument but 2 were given`.
> `dev/CLAUDE.md` §7 claimed *this file* recorded that it does not reproduce, citing
> `OUTSTANDING_WORK.md:293` — a line about AD-01 engine registration. **There was never a
> contradiction**, only a stale cross-reference. Corrected in `dev/CLAUDE.md` the same day.
>
> **Four figures below were wrong**, and are corrected in place:
> **7** acquires, not 8 (`stage1:517`, `stage2:537`, `stage3:630`, `stage5:551`,
> `video_generation:478`, `talking_head:449` and `:701`, all at `9af5a48`).
> **`talking_head_task.py:543` is not a release site** — it is `last_seg_err = None`
> inside the segment retry loop. The releases are `video_generation_task.py:540`,
> `talking_head_task.py:699`, `:884` (all broken) **and `celery_app.py:601`, which is
> correct** and which this item missed entirely.
> The three broken calls are broken **twice**: they also pass the `Dict` that `acquire`
> returns where the id belongs. The `TypeError` fired first, hiding it.
> **"stages 1/2/3/5/6 never release" is backwards.** Stages 1, 2, 3 and 5 all store the id
> (`stage1:526`, `stage2:545`, `stage3:637`, `stage5:558`) and `IVGSBaseTask` releases it
> correctly on `on_success` and `on_failure`. `video_generation` and `talking_head` never
> stored it — **they** are the two that leaked to TTL.

`utils/gpu_utils.py:211` — `def release_gpu_reservation(reservation_id: str) -> bool:` takes **one** parameter. Three call sites passed two — `talking_head_task.py:699,884`, `video_generation_task.py:540` — `release_gpu_reservation(reservation, config)`; every one raised `TypeError`, **measured**. A fourth, `celery_app.py:601`, was always correct. There are **7** `acquire_gpu_reservation(` call sites. Every acquire is wrapped in `except Exception` (two different event names, `gpu_reservation_skipped` and `gpu_reservation_failed`) — the subsystem fails open and silently, which is why `total_nodes:0` (P2.29) has been invisible. Live 2026-08-23, `/fleet` also reports **`queue_depth.urgent: 23`** — twenty-three scheduling requests stranded against a zero-node fleet, which nothing owns.

**Done by WP-08:** the three releases fixed (arity *and* argument); all seven acquires bracketed so `IVGSBaseTask` releases them; `on_retry` now releases too (it did not, so a retried task orphaned its previous reservation); one greppable event `gpu_reservation_unavailable` with `stage`/`model`/`vram_mb`/`error_type`/`fail_open=True` at every site; 53 tests. **Fail-open deliberately NOT changed to fatal** — the registry is empty, so it would fail every render; that is AD-05 O-3, after P2.6.

> **Operator rulings 2026-08-23.** **D-1 CONFIRMED** — the corrected figures above (7
> acquires; `:699`/`:884`/`video_generation:540` broken, `celery_app:601` correct; stages
> 1/2/3/5 release correctly) stand as applied to both `dev/CLAUDE.md` §7 and this item.
> **D-2 acknowledged** — 404-as-success stays until P2.6 makes the registry real; the
> swallow-register annotation (entry 11) is sufficient, no code change.
> **D-3 YES** — the 23 stranded urgent requests are now **P2.39**.
> **D-4 APPROVED retroactively** — the `on_retry` release fix stays.

**Still open:** `release_gpu_reservation` treats HTTP **404 as success** (`gpu_utils.py:217-223`), so with an empty registry every correctly-shaped release reports success — a reservation-count baseline check is vacuous until P2.6. There is no `GET /reservations` on the scheduler (only `DELETE /reservations/{id}`), so there is no reservation-count query to run.
**Scope/action:** ~~fix the signature at 3 sites; add `finally`-block releases at the other 5~~ — both done 2026-08-23 (the "other 5" were in fact 4, and already released via `IVGSBaseTask`; the real gap was the two GPU render stages). **Remaining:** decide explicitly whether reservation failure should be fatal (AD-05 O-3, after P2.6), and the 404-as-success behaviour above. Pairs with P2.29.

## P1.4 — M1-QA: formal Stage-8 validation + visual acceptance *(new)*

**⚖ RULING (operator ruling 2026-08-28): ARCHIVED — superseded by AD-03 §10.** M1-QA's remaining
acceptance criteria are AD-03 §10's criteria now; keeping a second list of them is how two
definitions of "acceptable" come to disagree. No work is dropped — it moved.

**Status:** ARCHIVED *(was: **(a), (b), (c) all DONE 2026-08-15 by WP-03-STAGE8-VALIDATION.** Report:)*
`dev/workpackages/reports/WP-03-STAGE8-VALIDATION-report_2026-08-15.md`.

- **(a) Operator visual QA — DONE. Both the 1080p and the 4K finals PASS on picture
  quality at full screen.** The encoder question is **CLOSED as not-a-defect**: the
  measured 506 kb/s (1080p) and 939 kb/s (4K) against 8/20 Mbps VBV ceilings are CRF
  behaving correctly on near-static content, exactly as AD-03 §14 predicted. `-crf`
  demonstrably reaches the executed command — the output carries `libx265` /
  `yuv420p10le` at 3840×2160. AD-03 §14 annotated closed.
- **(b) 4K profile — DONE, exercised for the first time ever.** hevc, 3840×2160,
  yuv420p10le, 30 fps, 215.067 s, 31,149,351 bytes, corruption checks passed.
- **(c) Bitrate assertion — DONE.** `video_bitrate_floor` in
  `validators/corruption_detector.py`: a 20 kb/s *collapse* floor at WARNING severity,
  set far below every known-good measurement so it cannot fail a reference. Passes the
  reference at 939,325 bps; fires on black at 10,501 bps. **Not yet in a deployed
  image** — ships on the next rebuild.

Reference banked at `dev/workpackages/reference/REFERENCE-OUTPUT_2026-08-15.md`
(narrow — see P1.0b/WP-26; Stages 1–5 were not run).

**Remaining under P1.4: nothing.** The lip-sync finding from the same QA session is a
separate item — see **P1.4d**.

## P1.4e — Neither system has ever measured lip-sync articulation: three unfailable metrics *(new, 2026-08-15, IVGS+MBCP joint investigation)*
**Status:** OPEN. Investigation complete; no code proposed yet.

**Three metrics, none of which can detect the defect that matters.**

| # | Metric | Where | Why it cannot fail |
|---|---|---|---|
| 1 | `alignment_score = 0.90` | `servers/latentsync/server.py:39,120` — `DEFAULT_ALIGNMENT`, env-overridable, emitted with `"scored": False` | A constant. Gated at 0.85 by the segment check in `talking_head_task.py` |
| 2 | `lip_sync_score = 0.9971` | `validators/lipsync_validator.py` | Computed, but measures **A/V duration agreement only**: `1 - (mismatch / audio_duration)`. `base_score` saturates at 1.0 via `min(1.0, (frame+energy)/2 + 0.2)`. Gated at 0.85 by `quality_thresholds.yaml` |
| 3 | `lse_c 6.58 / 6.68` | MBCP, on `.52` | **TH1**: the benchmark fixture's `audio_matched.wav` IS `presenter_face.mp4`'s own soundtrack. RMS difference -135.4 dB, 102 dB below baseline; durations differ by 104 microseconds |

**Metric 2 in detail.** `talking_head_task.py` calls `lipsync_validator.validate()`
**without** `latentsync_score`, so the engine's 0.90 is discarded and the module falls
to its ffprobe heuristic. Verified arithmetic against tonight's log:
`0.618667 / 214.881333 = 0.00287911` (logged exactly) and
`1.0 - 0.00287911 = 0.9971`. `base_score` was exactly 1.0, so `correlation` was
saturated. The module docstring advertises "Audio-visual correlation analysis" and
"Phoneme-to-viseme timing verification"; **neither is implemented.**

**Why 0.9971 was identical on 2026-06-08 and 2026-08-15:** it tracks duration, and the
duration mismatch (0.6187 s, the WP-04 frame-align defect) and audio length have not
changed. It would be unmoved by any articulation change.

**Consequence.** The only real measurement of articulation that has ever been taken is
the human verdict of 2026-06-08 (`docs/archive/OUTSTANDING_WORK_Addendum_B_2026-06-08.md:32`,
"a deal-breaker"). Both automated systems have reported approval ever since. Certificates
`9e0fc3cd` and `7b26811f` are unsupported (operator, MBCP side).

**Scope/action:** IVGS-2 addresses the two IVGS-side gates — **DONE 2026-08-15**
(both marked non-functional; `av_drift_seconds` added as the first working check).
Metric 3 is MBCP's. Metric 1 needs `server.py` and is deferred with IVGS-3/4
(digest/provenance coupling).

**Follow-up tied to IVGS-3/4 — typed face-detection error.** IVGS-5 detects
face-detection failure by matching the exception *message*, because the engine raises a
bare `RuntimeError("Face not detected")` and a typed exception would require `server.py`.
That file's image digest is pinned by MBCP certificate provenance, so it cannot be
rebuilt unilaterally. **When `server.py` is eventually rebuilt under IVGS-3/4, replace
the message predicate `_is_face_detection_failure` in `talking_head_task.py` with a
typed error.** Recorded so the compromise is not forgotten once the constraint lifts.

## P1.4f — Model Store hygiene items *(new, 2026-08-15; record only, do not act)*

**⚖ RULING (operator ruling 2026-08-28): ARCHIVED.** The row is marked *"record only, do not act"* and
has been since 2026-08-15. **Record-only IS archive.** A row that may never be acted on does
not belong in an open backlog; it belongs in the record, which is where it now is.

**Status:** ARCHIVED *(was: OPEN, recorded at operator instruction.)*

1. **`latentsync-alt` must never become a production default.** A deliberate test model
   created to debug the WP-02 check-6b GUI swap — not an error. **Once WP-02 is closed,
   retire it or move it out of `approved`** so it cannot be selected. Currently
   `state=approved`.
2. **Can IVGS distinguish attested-by-certificate from attested-by-free-text?**
   `model_approvals.vetting_reference` is free text. 22 of 26 rows hold certificate
   UUIDs; 4 hold prose (`"a test model"`, `"MBCP bake-off 2026-07"`, `"anything text"`).
   **Nothing in the schema or the enumeration path distinguishes them**, so an
   approved-models listing cannot tell a certified model from a hand-attested one.
   Gap worth knowing independently of `latentsync-alt`.
3. **20 of 26 attestations belong to models still in `candidate`.** Attestation exists,
   approval never happened. **Flag whether that is intended** — if attestation is meant
   to imply approval-readiness, 20 models are sitting one click away with nobody having
   decided.
4. **A MagiHuman or HuMo win needs an IVGS provider builder that does not exist.**
   `registered_engines()` on 2026-08-15: `cogvideox, comfyui, coqui, kokoro, latentsync,
   sadtalker, vllm`. Neither engine is present, and `build_provider` raises
   `EngineNotRegisteredError` for an unregistered engine. **Scope this now** so it is not
   discovered after MBCP R-11 delivers adapters.

> **Extended 2026-08-23 by WP-33-MODELSTORE-PREP** (read-only measurement; report at
> `dev/workpackages/reports/WP-33-MODELSTORE-PREP-report_2026-08-23.md`). Item 4's
> `registered_engines()` list is unchanged eight days on, verified by executing it inside
> the deployed `ivgs-celery-node04`.

5. **Kokoro is unbindable, though its container is healthy.** `IVGS_KOKORO_URL` is unset on
   every worker on the fleet, so `resolve_endpoint('kokoro')`
   (`shared/providers/binding.py:29`) falls back to `http://node-05:8021` — and node-05 is
   offline. The live Kokoro is `ivgs-kokoro` on node-04, alias `kokoro-tts:5003`. Any
   `voiceover_tts` binding on engine `kokoro` resolves to a dead host. Measured 2026-08-23.
6. **`sadtalker` resolves to a container that does not exist.** node-04's worker carries
   `IVGS_SADTALKER_URL=http://sadtalker:7861`; nothing listens on 7861 and no such container
   is present on any node. `talking_head_task.py`'s SadTalker fallback path is dead.
   Measured 2026-08-23.
7. **`weights_checksum` on all eleven MBCP-backfilled rows is an engine image digest, not a
   weights hash.** Six of them carry the `sha256:`-prefixed *container image* digest. The
   backfill's own attestation payloads record `"weights_checksum": null` — so the field
   named for weight provenance is holding container provenance, and the honest value is
   absent. Measured 2026-08-23.
8. **The `models` audit trail is lossy.** Of the five `audit_log` rows with
   `resource_type='models', action_type='UPDATE'`, three have `after_payload = NULL`; model
   CREATE rows carry `resource_id = NULL`; and approvals *and* lifecycle transitions are all
   recorded as `action_type='CREATE'`. WP-33 could answer its Task 2 only because
   `before_payload` happened to carry the changed field. Do not rely on this trail for a
   harder question until it is fixed.
9. **`SelectionError` is retried.** WP-03 S1.9 observed Stage 5 retrying a `SelectionError`
   to `retry_number 2`. The store cannot change between attempts; the retries are pure waste
   and they delay the failure signal by minutes. Make it non-retryable.

## P1.4d — Lip-sync quality is poor. Diagnostic only: NO model swap is scoped *(new, operator visual QA 2026-08-15; scope clarified by operator 2026-08-15)*

> **SCOPE CLARIFICATION, operator, 2026-08-15.** The talking-head model is **NOT being
> swapped out.** Substantial IVGS development continues on the current model. Everything
> recorded under P1.4d/e/f is **diagnostic and metric-honesty work, which stands
> regardless of which model runs.** If LatentSync later proves unsuitable that is a
> separate decision at a later date. **Do not scope, plan or prepare a model swap.**
> The earlier framing of this item ("remediation is to consume the certified winner")
> is superseded by this paragraph.

> **SUPERSEDED IN PART — operator ruling, 2026-08-22.** The
> `IVGS_Directive_Consume_MBCP_Envelope_2026-08-19.md` directive **supersedes this
> item's hold** to the following extent, and no further:
>
> - **Proceeds now:** the operating-envelope / `EngineDeploymentSpec` ingest, the
>   placement check at engine bring-up, and digest-pinned launch. **This is generic
>   infrastructure** — it is about whether a machine can run a model at all, and it is
>   correct regardless of which model IVGS runs. Tracked as **P1.4g**.
> - **Still held:** the model swap itself. It waits for a certified MagiHuman bundle
>   carrying a *measured* envelope. **P1.4f.4 remains in force — record only, do not
>   act** on a provider builder for MagiHuman or HuMo.
> - Unchanged: the 2026-08-15 clarification above still governs everything in
>   P1.4d/e/f. Building the machinery is not scoping a swap; do not read it as one.

**Status:** OPEN. **Not** an encoder or composition defect — does not reopen P1.4 or
AD-03 §14.

Operator visual QA on 2026-08-15 records lip-sync quality as poor on both finals. That
is the **known LatentSync limitation** the MBCP bake-off was built and run to settle
(AD-04 §3.19: "the talking-head production model decision — the reason MBCP was built
and the M1 quality blocker — is settled on data").

**The problem: the winner is not in the Model Store.** `stage='talking_head'` holds
exactly two rows, measured 2026-08-15:

```
latentsync      engine=latentsync  approved  is_default=t
latentsync-alt  engine=latentsync  approved  is_default=f
```

Both are the **same engine**, so the GUI swap proved in WP-02 check 6b changes the
binding but **cannot improve lip-sync**. The certified winner was never landed.

**Scope/action:** folded into **WP-26-MODEL-STORE task 5** — establish which model MBCP
certified, whether an export was ever attempted (AD-04 §3.22: certification and export
are distinct admin actions, so certifying alone would not have landed it), whether it
failed or was parked by `drain-pending-exports` or simply never clicked, and what it
takes to land it including whether its engine has a registered provider builder.

*Data-integrity note — RETRACTED 2026-08-15.* An earlier note here claimed an orphaned
attestation (13 distinct `model_id`s vs 12 `models` rows). That was a **snapshot
artefact**: `models` was counted at 12 before `latentsync-alt` was created and approvals
at 13 after. Re-measured: 13 models, 13 distinct approval `model_id`s, **0 orphans**.
No integrity problem exists.
Evidence on node-01: `final_1080p_9007b2cf.mp4` — 215.07s, 1920×1080, 30fps, h264 High, AAC 48 kHz stereo; 0.13s from the draft's 214.94s. Segment planning, parallel render, concat, A/V alignment and head carry-through all work.
**Open question — encoder:** measured video bitrate is 506 kb/s (draft 153 kb/s at 720p). The profile constants are **correct** per spec (`ffmpeg_client.py:144-148`: `crf=18, vbv_maxrate="8M", vbv_bufsize="16M"`, applied at `:560-567` and `:834-842`). CRF targets *quality*, not bitrate, and near-static content (stills + slow Ken Burns + 0.25-scale PiP head) legitimately encodes low. **This is not yet a defect — resolve by visual inspection, not by the number.** If full-screen playback is clean, close it; if soft, investigate whether `-crf` reaches the executed command.
**Scope/action:** (a) operator visual QA at full screen; (b) 4K profile never exercised — run it; (c) add a corruption-check assertion on output bitrate/quality so this is measured, not eyeballed, next time; (d) record the run as the **known-good reference output** for WS-T verification.

## P1.4g — Consume MBCP's operating envelope and deployment spec *(new; operator directive 2026-08-19, ruled in force 2026-08-22)*
**Status:** OPEN, **in scope and proceeding.** Brief:
`dev/workpackages/IVGS_Directive_Consume_MBCP_Envelope_2026-08-19.md`.

**Why.** MBCP proved daVinci-MagiHuman renders 1080p talking heads, but only on a host
with 82 GB RAM and a 128 GB swapfile, in an environment that **permits paging**. Every
earlier attempt "proved" the model needed more memory than existed, because container
limits silently forbade swap — a memory-swap cap equal to the memory cap forbids paging
and the failure then blames the model. That cost three weeks on the MBCP side. If IVGS
stands a model up from the weight bundle alone it will faithfully reproduce the failure
and misdiagnose it the same way.

**The rule:** a certified model arrives with its machine requirements, and IVGS refuses
to schedule it onto a machine that cannot meet them — **loudly, before any GPU time,
naming the node, the requirement and the shortfall.** Never a mid-render death.

**Scope/action:** (1) ingest and store `operating_envelope` and `deployment`
(`EngineDeploymentSpec`) with the AD-01 candidate record — they are part of the model's
identity, not documentation; (2) placement check at engine bring-up covering host RAM,
swap **and whether the execution environment actually permits paging**, scratch disk and
GPU VRAM; (3) launch from the digest-pinned deployment spec, never a hand-written service
definition — the digest carries the patches; (4) honour request-side constraints already
travelling with the adapter (MagiHuman: dimensions divisible by 32, so 1080p renders at
1920×1088 and is trimmed on delivery; frame rate fixed by engine config); (5) surface
envelope satisfaction wherever IVGS shows which model serves a stage.

**Absent is a fact, not a default.** A bundle may carry neither block; historical
certificates say "not recorded". Treat a missing envelope as *"requirements unknown —
operator decision to schedule"*, never as *"no requirements"*.

**Acceptance:** IVGS takes a bundle for a model it has never seen, answers "which of my
nodes can run this?" without consulting any MBCP document or person, places it correctly,
and refuses incorrect placement in a sentence a human can act on.

**Boundary:** this is the machinery only. Landing MagiHuman as a production head remains
held under P1.4d and P1.4f.4. The figures in the directive are provisional pending MBCP's
30-second measurement round — **build against the contract shape, not those numbers.**

## P1.4h — IVGS-0.6: animation scenes render a still image *(new, operator ruling 2026-08-22)*

**⚖ RULING (operator ruling 2026-08-28): JOINS THE RUN-2 SWEEP.** Whether an animation scene still
renders a still is a question RUN-2 answers by observation, not one to be argued from code.
Gated on **P2.46**, the bounded sweep immediately after RUN-2.

**Status:** GATED — RUN-2 sweep (P2.46) *(was: OPEN, **numbered but not yet in any work order.**)*

AD-07 §4.6 records that IVGS animation scenes render a still image rather than motion,
and calls it "defect IVGS-0.5". **That number is already taken** — IVGS-0.5 in both
WP-IVGS-0 and AD-07 §5.1 item 5 is the New Project form. Operator ruling 2026-08-22:
**do not renumber the existing defects.** The animation-stills defect takes the next free
number, **IVGS-0.6**.

**Two consequences, both recorded rather than acted on:**
1. **AD-07 §4.6 carries a mis-citation** — "defect IVGS-0.5" should read "defect
   IVGS-0.6". AD-07 is an unratified draft and is committed as record unedited;
   **correct this at ratification**, not before.
2. **IVGS-0.6 is not in WP-IVGS-0's scope.** That order is operator-approved and
   standalone at five defects; a sixth is not added to it here. IVGS-0.6 needs its own
   order, and AD-07 §4.6 already describes the intended shape — split the capability into
   a deterministic `motion_graphic` renderer (adopting the orphaned
   `services/motion_graphics.py`) and the existing pose-guided `animation_generation`,
   and stop presenting one as the other.

## P1.4i — Report/work-order path convention: FINAL *(operator ruling 2026-08-22)*
**Status:** CLOSED by ruling. Recorded so it cannot be re-litigated.

`dev/workpackages/` and `dev/workpackages/reports/` are **the** convention for work
packages, work orders and reports. **`dev/workorders/` is not adopted and must not be
created.**

It has now been proposed twice: by `WP-IVGS-0_Defect_Fixes.md`'s own STEP 0.3 ("mirroring
the MBCP convention") and again as a session instruction on 2026-08-22, under which a
`dev/workorders/reports/` directory **was** created and one report written into it. Both
were reversed the same day: the directory removed, the report moved to
`dev/workpackages/reports/WP-DEPLOY-INCIDENT_2026-08-22.md`, and WP-IVGS-0's two path
references amended.

**Why it kept flipping:** MBCP genuinely uses `workorders/`, and this repo's agents read
MBCP documents. MBCP's layout does not govern here. Recorded in CLAUDE.md §12 as well, so
a cold-start session sees it without reading the ledger. If an incoming order names
`dev/workorders/`, **amend the order** — do not create the directory.

## P1.4j — v5.5.4-metrics deployed to node-01 AND node-04; five doc defects closed *(2026-08-22)*
**Status:** DEPLOY **CLOSED**. Five findings **CLOSED by edit**. One item OPEN (rotation, folded into S-1).

**What shipped.** `ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics`, built from `874a0c8`,
digest `sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9` — identical
across node-01's store, node-04's store and GHCR. Carries **P1.4e / IVGS-5** (alignment gate
marked non-functional, `av_drift_seconds`, face-detection abort) and **P1.4(c)/WP-03** (the
`video_bitrate_floor` assertion). Both verified present *inside the running containers* on
both nodes (`1` / `2` / `0`). Report:
`dev/workpackages/reports/WP-DEPLOY-R2-R5-NODE04_2026-08-22.md`.

**Node-04 address contradiction — RESOLVED.** CLAUDE.md §2 was right: node-04 is
**`192.168.1.93`**. `.93` answers ping and tcp/22, is in `known_hosts`, and returns
`hostname: node-04`; `.52` is DOWN and absent from `known_hosts`. The incident report §8.4
held that the node-04 block could not be labelled honestly until this was settled — it is now.
Dated erratum added to `HANDOFF_metric-honesty_2026-08-15.md` §6.

**LatentSync is no longer a single copy.** `latentsync-v5.2.7-h0` (23.3GB, irreplaceable —
absent from ghcr.io) is banked at
`/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_latentsync-v5.2.7-h0.tar.zst`,
7.7G, sha256 `2da83e5a2bb60f4f…`. Verified **restorable**, not merely present: checksum,
`zstd -t`, `tar -t`, and `manifest.json` `RepoTags`.

**Five documentation/tooling defects, all closed by edit in this package:**

| # | Defect | Fix |
|---|---|---|
| 1 | CLAUDE.md §6 said to verify a recreate with `docker exec <c> env` — **misleading for tag variables**. `env_file: .env.node0X` injects stale `IVGS_*_TAG` independent of the `--env-file .env` that selects the image. Both nodes reported wrong tags while running the right image | §6 rewritten: `docker ps` / `.Config.Image` for the image, `env` for config only. `depends_on` note added |
| 2 | `save-image-artifact.sh` needs root (store is `root:root 0755`); it failed at the redirect *after* `docker save` began, reading as a save failure | Usage says `sudo`; an explicit writability precheck now fails fast with a clear message |
| 3 | The R4 block printed two secrets | Narrowed to `^IVGS_[A-Z]*_TAG=` in the R4 block **and** runbook §3.4, which carried the same live grep |
| 4 | Handoff §6 gave node-04's address as `.52` | Dated erratum |
| 5 | R5 coupled push-and-bank, so a transient push failure suppressed the durable artifact save | Runbook **§3.5a**: bank first, separate steps, verify from the registry/filesystem never an exit code, never rebuild to work around a push failure |

**`.7` backup coverage of the artifact store — CONFIRMED, with one gap.** `asset_backup.sh:71`
takes `/mnt/ivgs-shared` wholesale as `SRC_SHARED_VOLUME`, rsynced to `shared-volume/` with
**no `--exclude` anywhere in the script**; daily 03:00 host cron; 14-day retention;
hard-linked across generations. Verified on `.7`:
`/mnt/backup/ivgs/assets/2026-08-22/shared-volume/image-artifacts/` holds the artifacts, with
daily directories 08-15 → 08-22. **This corrects the residual-risk note in
`WP-DEPLOY-R2-R5-NODE04` §10, which said coverage was unconfirmed — it is confirmed, and
DEF.1 already recorded it.**

**The gap that IS real:** the 03:00 cron means a freshly banked artifact spends up to ~24 h on
node-01's disk alone. Today's run was 03:00; the two new artifacts were banked at 19:26 and
19:32, so they reach `.7` at 03:00 on 2026-08-23. **One-line fix — run the asset backup by
hand immediately after banking anything irreplaceable:**

    (set -a; . /etc/ivgs/cron-backup-env; set +a; sudo /opt/ivgs/scripts/asset_backup.sh)

Not run in this package: it is a multi-GB rsync on a 16 GB node with a documented OOM history
(CLAUDE.md §7), and no ruling covered it. **Operator decision.**

**Also observed, not acted on.** node-04's `ivgs-infra/.env` carries `IVGS_API_TAG=v5.1.18-node-config`
and `IVGS_FRONTEND_TAG=v5.2.16-node-config`. node-04 runs neither service, so these are
probably vestigial — but that is inference, not measurement.

## P1.4k — The CI gate has been blind for 87 days; runner revival DEFERRED *(2026-08-22)*
**Status:** Gate **RESTORED** by moving off self-hosted. CD workflow **DISABLED**. Runner
revival **DEFERRED** with binding conditions. Blindness window **recorded, not remediable** —
see below.

### What was wrong
`.github/workflows/compliance-check.yml` and all three `cd-deploy.yml` jobs specify
`runs-on: [self-hosted, linux, x64, ivgs-infra]`. **No such runner has existed since
2026-05-26T22:41:36Z** — `ivgs-github-runner` started and exited 0.145 s later, exit 0, zero
log output, no restarts, no systemd unit, though still declared at
`docker-compose.node01.yml:557`.

**The failure mode is silence, not red.** A job with no matching runner does not fail; it
**queues indefinitely**. GitHub shows "queued", never a failure, and nothing raises an alarm.
Spec §F.2 describes this workflow as "fail build on any violation". **It has gated nothing for
87 days**, including all five commits of 2026-08-22. Every green CI signal in that period came
from `ci.yml`, which is entirely `ubuntu-latest` — and whose two Python jobs are `if: false`.
Recorded as WP-00 instance **16**.

Discovered only because run **#341** was noticed sitting queued against `a918fb9`. Nothing in
the tooling would have reported it.

### What was done
| Action | Detail |
|---|---|
| Compliance Audit restored | `runs-on: ubuntu-latest`. It needs nothing from node-01 — checkout, setup-python, four greps, `scripts/compliance_scanner.py .`, all against the checked-out repo. No docker, ssh, host path or network. Runs on the next push, with no runner and no host exposure |
| CD Deploy disabled | `push:` trigger removed (`workflow_dispatch` only) **and** `if: false` on all three jobs, matching `ci.yml`'s existing convention. Original trigger preserved verbatim in the header comment so re-enabling is exact |

**Correction to an earlier assumption.** CD Deploy did **not** queue a phantom run on every
push to main — its `push:` trigger carries a `paths:` filter (`docker-compose.*.yml`,
`.env.*.template`, `scripts/deploy-node.sh`, `configs/**`). Checked against all nine commits
of 2026-08-22: **none matched**, so it fired on none of them. It was disabled on the other
two grounds, not on trigger frequency.

**Why CD Deploy stays off regardless of the runner.** It runs `scripts/deploy-node.sh`, which
does `docker compose down` on the **whole stack** and pulls from GHCR — precisely what the
runbook's `--no-deps` rule and the `--pull never` correction exist to prevent
(`WP-DEPLOY-INCIDENT` §4). It would restart Postgres to deploy a worker. It carries
`environment: production` with real secrets and auto-triggers on a path match. Manual
deployment as practised on 2026-08-22 is gated, verified and reversible; this is not.

### Runner revival — DEFERRED
**Re-open trigger:** a decision that CD should be automated at all, or another workflow that
genuinely needs node-01. Not needed for the compliance gate, which now runs GitHub-hosted.

Four requirements, all necessary — the service as written cannot work even if started:
1. **A fresh registration token.** `GITHUB_RUNNER_TOKEN` in `.env` is non-empty but ~3 months
   stale; registration tokens expire in about an hour.
   `gh api -X POST /repos/{owner}/{repo}/actions/runners/registration-token`
2. **A `command:`/entrypoint.** The compose block has neither. The official
   `ghcr.io/actions/actions-runner` image does not self-register — it ships `config.sh` and
   `run.sh` and must be told to run them. This is why it exits in 0.145 s.
3. **A named volume** for runner config and `_work`. Only `/var/run/docker.sock` is mounted
   today, so registration would live in the container layer and vanish on any recreate.
4. **A decision on the Docker socket** — see condition A.

**TWO BINDING CONDITIONS, operator ruling 2026-08-22. Neither is advisory.**

> **A. No Docker socket mounted unless a specific job demonstrably needs it.** The service
> currently mounts `/var/run/docker.sock`. A self-hosted runner holding the host Docker
> socket while executing workflow-authored code is root on node-01 for whoever authored that
> code. If some job genuinely needs it, that job gets it — not the runner as a standing grant.
>
> **B. `pull_request` never targets self-hosted.** `compliance-check.yml:17` triggers on
> `pull_request`; combined with A, that was root on node-01 for whoever opened a PR.
> GitHub's fork-approval default is a policy setting, not a guarantee, and is the wrong
> thing to rely on. Now moot for the compliance audit — it is GitHub-hosted — and it must
> stay moot.

### Not verified
No GitHub-side state was inspected: there is no `gh` credential on node-01 (`gh auth status`:
not logged in). Whether other runners are registered, how many runs sit queued behind #341,
and whether repo settings permit fork workflows are all unknown from this box. **Run #341 and
any siblings will stay queued until cancelled in the UI** — the fix stops new ones, it does
not drain the existing queue.

## P1.4l — Compliance Rules 1 and 3 fixed; gate green — **RESOLVED** *(2026-08-22)*
**Status:** **RESOLVED.** Rule 1 **FIXED**. Rule 3 **FIXED** by operator ruling 2026-08-22.
All five rules verified passing against a simulated CI checkout. Node-20 deprecation **P3, noted**.

### Rule 1 — fixed
The rule was a bare substring match, so it fired on the prohibition comments that *document*
the policy — `# OPENAI_API_KEY — NEVER` in `.env.template` and all six
`.env.node0X.template` files — and on the scanner's own test fixtures in
`tests/test_compliance_scanner.py`. **Operator ruling: fix the rule, not the sources** —
those comments are the policy's documentation and must not have to hide from its enforcement.

Now anchored: `^[[:space:]]*(VAR1|...)[[:space:]]*[=:]` — start of line, optional whitespace,
name, optional whitespace, `=` or `:`. Gated both ways: **zero** hits across a simulated CI
checkout (651 tracked files), and it still catches a synthetic real assignment at column 0,
an indented one, and the YAML `KEY: value` form. The `[=:]` alternation closes a real gap —
this rule scans `*.yml`/`*.yaml`, where a leak reads `OPENAI_API_KEY: sk-...` with a colon,
which an `=`-only anchor would miss entirely.

### Rule 3 — the same defect, newly found, NOT fixed
**Each rule `exit 1`s on its first hit, so the job stopped at Rule 1 and Rules 2-5 never
ran.** Fixing Rule 1 does not produce a green run; it reveals Rule 3, which fails on:

| File | Lines | What it actually is |
|---|---|---|
| `ivgs-infra/scripts/v4_to_v5_migration.py:52-56` | 3 | `CLOUD_ASSET_PATTERNS` — the list of cloud URLs the migration script **searches for and removes**. Detection code, not usage |
| `tests/test_compliance_scanner.py` | 4 | The scanner's own test fixtures |

Identical class to Rule 1: **the enforcement's own references to the thing it forbids trip
the enforcement.** But the fix is a genuine judgement call rather than a mechanical one, so it
is recorded here rather than applied. A comment is distinguishable from an assignment by
regex; a URL in a *pattern list* is not distinguishable from a URL being *called*.

**RESOLVED — operator ruling 2026-08-22: APPROVED.** File-level exclusions applied to Rule 3,
mirroring the existing `--exclude="compliance_scanner.py"`:
`--exclude="test_compliance_scanner.py"` and `--exclude="v4_to_v5_migration.py"`, with an
inline comment in the workflow stating that both hold detection patterns and fixtures rather
than live calls, and that Rule 5 still covers them.

**The accepted trade, stated plainly so it is not rediscovered as a surprise:** a genuine
prohibited call added to either file would not be caught by *this rule*. Accepted because a
URL in a pattern list is not distinguishable by regex from a URL being called, and because
**Rule 5 — `scripts/compliance_scanner.py`, the scanner §F.2 actually names — still scans both
files** and reports 0 violations across all 651 tracked files.

**Verified after the change**, against a simulated CI checkout built from tracked files only:

| Rule | Result |
|---|---|
| 1 prohibited env vars | PASS |
| 2 prohibited pip packages | PASS |
| 3 prohibited API endpoints | **PASS** |
| 4 prohibited imports | PASS |
| 5 `compliance_scanner.py` | PASS — 0 violations, 651 files, exit 0 |

**Negative control:** a synthetic `httpx.post("https://api.openai.com/...")` dropped into a
non-excluded file is still **caught** by Rule 3. The exclusions narrow the rule to two named
files; they do not disable it.

**Reassurance on the substance:** `scripts/compliance_scanner.py`, the actual §F.2 scanner and
the more capable tool, was run over the same simulated checkout and reports **0 violations
across 651 files, exit 0**. Rules 2 and 4 also pass. The repository is compliant; only two of
the five grep rules mis-classify their own enforcement code.

### P3 — actions run on deprecated Node 20
`actions/checkout@v4` and `actions/setup-python@v5` execute on the Node 20 runtime, which
GitHub has scheduled for deprecation; runs emit a warning. Cosmetic today, breaking whenever
GitHub retires the runtime. **Fix when convenient:** bump to whatever major currently ships a
Node 24 runtime. Not urgent, not touched here — it is a warning, not a failure, and bumping
action majors unreviewed is how unrelated breakage arrives.

## P1.4m — The Model Store cannot bind eight of nine stages; Stage 1 dies before it starts *(new, WP-IVGS-0 pre-deploy gate, operator ruling 2026-08-22)*
**Status:** OPEN — **blocks the whole pipeline.** Read-only measurement of the live `ivgs`
database, 2026-08-22. Not caused by WP-IVGS-0; found by its pre-deploy gate.

`get_binding` (AD-01.9, `shared/providers/factory.py:171-190`) falls back to the
`(stage, tier)` default only for a model that is `is_default` **and** `state=approved`
**and** `enabled`. Measured against every (stage, tier) pair:

| Stage | prototype | production |
|---|---|---|
| `talking_head` | RESOLVES | RESOLVES |
| **all eight others** | **SelectionError** | **SelectionError** |

`project_model_selections` holds **0 rows**, so nothing reaches the selection branch either;
`model_node_availability` holds **0 rows**, so any binding that did resolve would carry
`node_id=None`. Of 13 models, only the two `talking_head` rows are `approved`; the rest are
`candidate` (11) or `retired` (1), and **no `transcript_refinement` model exists at all**.

**Consequence:** `stage1_transcript.py:498` resolves its binding before any prompt or vLLM
work, so **Stage 1 raises `SelectionError` on every run today** and nothing downstream is
reachable. This is independent of, and prior to, every defect WP-IVGS-0 fixed — those fixes
are correct and tested, and none of them can be observed end to end until this is resolved.

**Interaction with WP-IVGS-0.2** (recorded so it is not rediscovered): Stage 3's prompt
writer now resolves a `storyboard_generation` binding at `stage3_images.py:649` and raises if
it cannot, where it previously fell through to the env profile. With the store in this state
that turns Stage 3 from "every scene reports failed" into "the task raises". Moot while
Stage 1 cannot run, and the loud failure is the intended behaviour, but it is a real change.

**Action:** approve and enable a default model per stage, or create selection rows. Needs an
operator decision on which models are certified enough to mark `approved`; P1.4f already
records Model Store hygiene items. **Do not deploy WP-IVGS-0 expecting a working pipeline
until this is closed** — the package fixes real defects but this gate sits in front of them.

> ### AMENDED 2026-08-23 — WP-33-MODELSTORE-PREP
>
> Report: `dev/workpackages/reports/WP-33-MODELSTORE-PREP-report_2026-08-23.md`.
> Operator checklist: `dev/workpackages/WP-33-POPULATION-CHECKLIST.md`.
> Re-validation query: `dev/workpackages/reference/wp33-validate-binding.sql`.
> All findings read-only; zero writes performed against any live system.
>
> **VERDICT: NEWLY-EXPOSED TRUTH, not a regression. Nothing needs un-breaking.**
> No operator action broke this. The store never could bind stages 1–5, and the pipeline
> never relied on it to. Disproved three ways: (a) `audit_log` holds **zero** `models`
> DELETE rows and the only lifecycle transition out of `approved` in the store's entire
> history is `test-model-1` on 2026-07-10, five weeks *before* the run in question;
> (b) WP-03 S1.8 measured the identical store on 2026-08-15 and S1.9 captured the identical
> `voiceover_tts` `SelectionError` that day; (c) the MBCP backfill's 24 revocations were
> *skipped, never transmitted* (AD-01/AD-04), so they never created an IVGS row and cannot
> have removed one.
>
> **The 08-15 "end-to-end run" did not happen.** WP-03's own headline is *"a full Stages
> 1–8 run is not possible today"*. Stages 1, 2 and 3 did not run; the run reused Stage 1/2
> artefacts measured this session as created **2026-06-01 22:29** — five and a half weeks
> before migration `0026_ad01_model_store` and `shared/providers/factory.py` existed at all
> (both landed in `303681e`, 2026-07-09). The 4K render came from stages 7 and 8 against the
> June manifest.
>
> **What actually changed was the code, in the direction opposite to a regression.** ARCH-1
> installed a binding gate in front of an empty store, node by node. `303681e` *added* the
> unguarded `get_binding` calls to stages 1/2/3/5 on 2026-07-09; `09e4212` added Stage 6's on
> 2026-08-15 — which is exactly why the operator approved `latentsync` at 00:35 and set it
> default at 05:37 that day. One stage needed a binding; one stage was populated.
>
> **CORRECTION to this entry's own text.** "Stage 1 raises `SelectionError` on every run
> today" is true of HEAD but **not of the deployed fleet**. Stage 1 is routed to `gpu_llm`
> (`celery_app.py:127`), consumed only by node-02, which runs **pre-ARCH-1 `v5.4.7-h0`**.
> Verified by execution inside the container: `from shared.providers.factory import
> get_binding` → `ModuleNotFoundError`. On the fleet as deployed, Stage 1 does not raise —
> it ignores the store entirely. Same for Stage 2 and Stage 3-video (node-03, same image).
> The stages that genuinely raise today are the three on node-04. Stage 1 is still
> unrunnable, for a more basic reason: node-02's NVIDIA driver is not loaded and its vLLM
> exits 128.
>
> **Closing this needs three things that are NOT store state**, none fixable from the GUI:
> 1. node-02 has no GPU driver (`nvml error: driver not loaded`, 2026-08-22 23:47), so no
>    chat LLM is served there. The fleet's only live chat LLM is node-04's `mistral-24b`.
> 2. `IVGS_VLLM_URL` is unset on **every** worker, so the `vllm` engine resolves to
>    `http://node-02:8000` regardless of what is bound. Endpoints are env, not a `models`
>    column — `resolve_endpoint` (`shared/providers/binding.py:36-53`) ignores `node_id`.
> 3. node-02 and node-03 must reach an ARCH-1 image before they consult the store at all.
>
> **Two of the plan's stages cannot be closed by promotion, contrary to the assumption in
> this entry's Action line.** `RETIRED` is terminal (no reverse route in
> `ivgs-api/app/api/v1/model_store.py`), so `storyboard_generation` needs a fresh
> registration, not a promotion; and `FLUX.1-dev`'s weights are not on this fleet —
> node-04's ComfyUI holds exactly one checkpoint, `flux1-schnell-fp8.safetensors`. Promoting
> `FLUX.1-dev` or `Wan2.2-T2V` would produce a binding that resolves and then raises
> `ValueError` inside the stage, because `engine_model_id(binding)` returns the store name
> verbatim and both Stage 3 call sites coerce it into a closed enum. Verified by execution.
>
> **The checklist is proven.** Applying it in a read-only projection against the real
> predicate resolves all six bound stages on both tiers with `candidates_matching = 1`;
> the endpoint, builder and engine-enum chain behind each was executed inside the deployed
> `ivgs-celery-node04`. Four of six are complete end to end; the two vLLM stages are gated
> only by the three items above.
>
> **Status: still OPEN.** WP-33 was read-only by binding constraint — store mutations are
> admin/GUI-only under AD-01.11 and require operator attestation. The work is now fully
> specified and waiting on the operator.

## P1.4n — The `ffmpeg` engine can never resolve a binding *(new, WP-33-MODELSTORE-PREP 2026-08-23)*
**Status:** OPEN. Latent — no task binds `composition` today, so nothing fails yet.

`e613e84` (migration 0027) added `ffmpeg` to the `ModelEngine` enum "to unblock MBCP
composition exports", and added it to `shared/models/model_store.py` and the frontend
types. **It was never added to `_ENGINE_ENDPOINTS` in `shared/providers/binding.py`, and no
builder was ever registered for it.** Verified by execution inside the deployed
`ivgs-celery-node04`, 2026-08-23:

```
resolve_endpoint('ffmpeg')   -> EndpointResolutionError: no endpoint mapping for engine 'ffmpeg'
registered_engines()         -> ['cogvideox','comfyui','coqui','kokoro','latentsync','sadtalker','vllm']
```

`_binding_from_model` (`shared/providers/factory.py:96`) calls `resolve_endpoint` on every
successful resolution, so approving `FFmpeg-composition` and setting it default would turn
`composition`'s `SelectionError` into an `EndpointResolutionError` — a *worse* failure,
because it arrives after the model looks correctly configured. This is precisely the
untested cross-schema coupling CLAUDE.md S11 records ("the two schemas are coupled with no
test on either side").

**Scope/action — operator decision D-5.** A one-line `_ENGINE_ENDPOINTS` entry is not the
fix: there is no builder either, and ffmpeg is an in-process compositor, not a served HTTP
endpoint, so it does not fit the engine/endpoint model AD-01.9 assumes. The honest options
are (a) give `ffmpeg` a null-endpoint special case plus an in-process builder, or (b)
formally exclude `composition` from AD-01 selection and document why the enum value exists
only for MBCP export compatibility. **Decide before anything binds `composition`.**
`animatediff`, `wan21`, `ollama` and `remotion` share the missing-builder half of this
problem (P1.4f.4); `ffmpeg` is the only one missing both halves.

## P1.4o — AD-03 §10 criterion 3: the head A/V drift is measured, and the splitter is only a fifth of it *(new, WP-04-FRAME-ALIGN, operator rulings 2026-08-23)*
**Status:** OPEN. Frame-aligned splitting is **DONE 2026-08-23 (WP-04) and DEPLOYED 2026-08-23 in `v5.6.0-m2` (P1.4p)** - `plan_frame_aligned_pieces` verified inside the running node-04 worker, which is where the residual must be measured; **the measurement itself was not taken, because WP-34's exit gate excludes running the pipeline**;
criterion 3 does **not** close on it. Report:
`dev/workpackages/reports/WP-04-FRAME-ALIGN-report_2026-08-23.md`.

**AD-03 §7 Q5 — SETTLED, operator ruling 2026-08-23: target fps = 30.** Corroborated by
measurement the same day, not only by ruling: the stored head artifact carries
`r_frame_rate 30/1` **and** `avg_frame_rate 30/1` — constant, exactly 30.

**The ~0.62 s is now a measurement.** `ffprobe` on the real stored head
(`assets` fid `5,5b66d602e3`, project `3814f845`) against the six Stage-5 scene WAVs it
was lip-synced to:

    head video : 6465 frames @ 30/1 CFR      = 215.500000 s
    narration  : 7.094667 + 5.558667 + 31.397333
               + 75.349333 + 57.108667 + 38.372667 = 214.881334 s
    drift      = 0.618666 s = 18.56 frames

This independently reproduces the figure P1.4e already carried
(`0.618667 / 214.881333`, logged) from a different direction. Reproducible via
`scripts/measure_head_av_drift.sh` (ffprobe-based; the header carries the docker
invocation, node-01 has no host ffprobe).

**The brief's attribution was wrong.** Modelling the splitter over those six real
durations gives 11 pieces and **0.118666 s (3.56 frames)** pre-fix, **0.085333 s (2.56
frames)** post-fix. The arithmetic is worth about **a fifth** of the measured drift and
the fix buys exactly one frame on this material. Predicted post-fix drift is ~0.5 s, not
< 1 frame.

**RULED 2026-08-23 (WP-04 D-1): APPROVED as a deploy-time investigation.** The ~0.5 s
residual is measured on **node-04 during deploy verification** — the engine is the only
thing that can explain it, it runs there, and this session was confined to node-01
(common rule 5). Two hypotheses to separate: LatentSync padding each render to a
mel-chunk or batch multiple (a per-piece quantum larger than one frame — the measured
0.618666 s over 11 pieces is **0.0562 s ≈ 1.69 frames per piece**, which a simple
`ceil(d·fps)` cannot produce), versus a fixed pad per render call, in which case only
piece **count** matters and WP-04's fix removes none of it. **Which it is decides
criterion 3.** Run a short job with at least one scene over `MAX_SEGMENT_SECONDS` (30 s)
— a shorter scene is never split and exercises nothing.

**The residual the fix cannot reach, regardless.** Post-fix, rounding survives once per
**scene** (the last piece carries the remainder), because the Stage-5 scene durations are
not themselves whole frames — 7.094667 s is 212.84 frames. Removing that means
frame-aligning the timeline's scene durations: the Stage 4/5 timeline model, not the
splitter.

**Related, ruled record-only 2026-08-23:** **P2.37** (`segment_planner`, WP-04 D-2) and
**P2.38** (`output_fps`, WP-04 D-3).

## P1.4p — `v5.6.0-m2` deployed to all four nodes; the M2 + WP-IVGS-0 + WP-04 batch is live *(2026-08-23, WP-34-DEPLOY-BATCH)*
**Status:** DEPLOY **CLOSED**. Swallow-register entries **2 and 3 CLOSED** on observed
evidence. WP-33 population checklist **AMENDED** to `llama-3.3-70b`. Three items OPEN and
recorded below. Report: `dev/workpackages/reports/WP-34-DEPLOY-BATCH-report_2026-08-23.md`.

**What shipped.** Three images, all built from `4d61cab` on a clean tree with
`HEAD == origin/main`:

| Image | Digest (registry index == local image id) | Artifact sha256 |
|---|---|---|
| `ivgs-workers:v5.6.0-m2` | `sha256:13c020a50463fa57...73a893a` | `a1cd26c30a86d9d9...364f1248` |
| `ivgs-api:v5.6.0-m2` | `sha256:33641464ffe54bcc...2ade02` | `0280f6cdd9dfa5db...4af306e1` |
| `ivgs-frontend:v5.6.0-m2` | `sha256:ce8a60a9875837f9...4002078` | `a85aa3cb01c63a0b...318a96a0` |

Banked to `/mnt/ivgs-shared/image-artifacts` **before** any push (runbook 3.5a), each
verified by `sha256sum -c` (rc 0), `zstd -t` (rc 0), one MANIFEST line, and the image-config
blob present inside the archive. The GHCR push was separate and succeeded; **the artifact,
not the registry, was the distribution path to nodes 02/03/04** (`zstd -d | docker load`).

**Carries:** WP-04 frame alignment, WP-05 visibility timeout, WP-06 media join, WP-07
checkpoints (both halves), WP-08 GPU reservation releases, WP-IVGS-0 (5 defects + F6/F9).
Every marker was verified by grep **inside a running container** on the node that runs it,
never by tag.

**Per node.**

| Node | Services recreated | From -> to | Untouched, verified |
|---|---|---|---|
| node-01 | `fastapi-backend`, `nextjs-frontend`, `celery-worker-default`, `celery-worker-composition`, `celery-beat` | api `v5.5.3-arch1`, frontend `v5.4.2-themes`, workers `v5.5.4-metrics` -> `v5.6.0-m2` | Postgres / Redis / SeaweedFS up 8 days (`--no-deps` held) |
| node-02 | `celery-worker` | `v5.4.7-h0` -> `v5.6.0-m2` | `ivgs-vllm-primary` - same container id and `StartedAt`, still serving `llama-3.3-70b` |
| node-03 | `cogvideox-worker` | `v5.4.7-h0` -> `v5.6.0-m2` | `ivgs-cogvideox-server-node03` - same container id and `StartedAt` |
| node-04 | `celery-worker` | `v5.5.4-metrics` -> `v5.6.0-m2` | `IVGS_LATENTSYNC_TAG=v5.2.7-h0` before **and** after; latentsync / comfyui / coqui / kokoro / whisperx all identical container ids and `StartedAt` |

`celery inspect active_queues` reports **5 workers online with a queue map identical to the
pre-deploy baseline**, diffed line for line.

**`POST /jobs/{id}/checkpoints` now exists in production.** Live OpenAPI lists
`['delete','get','post']` on `/api/v1/jobs/{job_id}/checkpoints`; an unauthenticated POST
returns 403 (auth) where `v5.5.3-arch1` returned **405 Method Not Allowed / allow: GET**.
This retires the CLAUDE.md 7 trap "Checkpoint resume - does not exist ... no POST route was
ever built" as a statement about the *route*; resume itself is still M3.

**The WP-05 gate was probed, not assumed.** Inside the running `ivgs-celery-default`,
`check_visibility_timeout(3600, {talking_head: 3900, video_generation: 3900})` raises
`VisibilityTimeoutError`; `7200` passes. `IVGS_BROKER_VISIBILITY_TIMEOUT=7200` is in the
environment of every node-01 worker and of node-04's; on node-02/03 the effective value is
7200 from the code default (`config.py:227`), read back out of the running worker.

**Two node `.env` files were lying, and it would have been a silent downgrade.** node-02 and
node-03 were *running* `v5.4.7-h0` while their `ivgs-infra/.env` said
`IVGS_WORKERS_TAG=v5.3.0-h0`. A plain `docker compose up -d` on either node would have
rolled the worker **back** two releases. Rollback tags were therefore recorded from
`.Config.Image`, not from `.env` - CLAUDE.md 6, applied in the direction it was written for.

### Open items from this package

1. **node-02 cannot reach its own published vLLM port from a container.** From inside
   `ivgs-celery-node02`, `http://node-02:8000` and `http://192.168.1.91:8000` both time out
   (`curl rc=28`): `ufw` admits `192.168.1.0/24` to the host and the compose bridge is
   `172.x`. The same URL returns **200** from node-03 and node-04. This matters because
   stages 1 and 2 run on node-02's `gpu_llm` queue and now dial `binding.endpoint`
   (`stage1_transcript.py:349`), not the old `VLLM_PRIMARY_URL` profile - so WP-IVGS-0 would
   have regressed those two stages on this node. WP-34 set
   `IVGS_VLLM_URL: http://vllm:8000` on node-02's `celery-worker` (tracked compose), the
   identical server over the compose network, verified 200.

   > **OPERATOR RULING 2026-08-23: the override STANDS. `ufw` is NOT to be opened.**
   > Grounds given: it is the documented mechanism (`binding.py:6-9` - per-engine env
   > override first), its blast radius is one service, and it is reversible by deleting one
   > line. The alternative - opening node-02's host firewall to the docker bridge for a
   > uniform fleet-wide endpoint - is **rejected**, not deferred. This item is **CLOSED**;
   > it is no longer an open decision.
2. **P1.4o's deploy-time A/V-drift investigation was NOT run.** It needs a real pipeline job
   with a scene over 30 s. WP-34's exit gate explicitly excludes running the pipeline, and the
   Model Store is not populated yet, so Stage 1 cannot bind.
   **OPERATOR RULING 2026-08-23: accepted as owed to the first pipeline run. No action.**
   P1.4o stays open and carries it; nothing further is expected of this package.
3. **The node compose files had drifted from `main` and were reconciled.** node-02 and
   node-03 carried `DATABASE_URL: postgresql+psycopg` - the v3 driver **that is not in the
   workers image**. `main` had already fixed this to `+asyncpg` (ledger P1.0b) and the node
   copies had never been updated. Left alone, the ARCH-1 catch-up would have deployed cleanly
   and then failed on the first DB session. Each node's file was backed up
   (`docker-compose.node0X.yml.bak-pre-wp34-<ts>`) before replacement, and `+asyncpg` was
   read back out of the running workers. node-04's file gained only the explicit
   `IVGS_BROKER_VISIBILITY_TIMEOUT: "7200"`.

**Rollback path verified present, not assumed.** `v5.5.4-metrics` (node-01, node-04),
`v5.4.7-h0` (node-02, node-03) and the node-01 `ivgs-api` / `ivgs-frontend` predecessors are
all still in their nodes' local image stores, checked with `docker images -q` on each box.
Every `.env` was copied to `.env.bak.pre-wp34-<ts>` before it was written.

**The `v5.4.7-h0` banking gap is CLOSED. OPERATOR RULING 2026-08-23**, acted on the same day.
The node-02/03 rollback image was banked from node-02's local copy - the rollback target
itself, not a registry re-pull:

    /mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.4.7-h0.tar.zst
    257M   sha256:f6a3064a75c13cb50102d5b3e8edcef3680d84593f12fc08c98f62d8fbcc39e9

`sha256sum -c` rc 0, `zstd -t` rc 0, exactly one MANIFEST line, and the archive contains
`blobs/sha256/7f53228e9616...` - the image-config blob of the image node-02 and node-03
actually ran. **node-02 and node-03 carry byte-identical copies** (same image id
`sha256:7f53228e9616...`, same `Created` timestamp), so the single artifact is a valid
rollback source for both. Three copies now exist where there were two.

> Banked using **node-01's** `scripts/save-image-artifact.sh`, shipped to node-02 under a
> SHA gate and run from `/tmp`. node-02's own `/opt/ivgs/scripts/save-image-artifact.sh` is
> the **stale pre-P1.4j version** (1187 bytes vs 2401; missing both the root-writability
> precheck and the MANIFEST dedupe guard). Left in place - syncing node scripts is outside
> this package - but it is a live trap for anyone who banks from node-02 again.

## P1.4q — A failed render job strands its project in a non-retriggerable state *(new, 2026-08-23, WP-37 record-only)*

**⚖ RULING (operator ruling 2026-08-28): JOINS THE RUN-2 SWEEP.** Whether a failed render still strands
its project non-retriggerable is a question RUN-2 exercises. Gated on **P2.46**.

**Status:** GATED — RUN-2 sweep (P2.46) *(was: OPEN. **Record only** - no code was written for this.)*

**Observed twice on 2026-08-23**, both times during the first end-to-end run. A render
job fails terminally; the project is left in whatever in-progress state it had reached
(e.g. `TRANSCRIPT_REFINEMENT`). `POST /api/v1/projects/{id}/trigger` then rejects the
retry with **409 `INVALID_STATE_TRANSITION`**, because the state machine only admits a
trigger from a resting state.

The operator's only recourse is to reach into the database by hand:

    UPDATE projects SET state='DRAFT' WHERE id='...';

**Why it matters beyond inconvenience.** The pipeline is being debugged right now, so
failures are the normal case, and every one of them currently requires manual SQL before
the next attempt. It also means the project's state is not a truthful description of the
project: it says "refining the transcript" about a project where nothing is running.

**A terminal job failure should return the project to a retriggerable state** - either
`DRAFT` or a distinct `FAILED` that `trigger` accepts. That is a state-machine decision,
not a patch, which is why it is recorded rather than fixed here.

## P1.4r — Frontend: unguarded `.split()` on the project detail page *(new, 2026-08-23, WP-37 record-only)*

**⚖ RULING (operator ruling 2026-08-28): FOLDS INTO THE FRONTEND REBUILD.** Not a standalone row: the
guard is fixed in the same rebuild that lifts the Media Type dropdown — **WP-IVGS-09 Task 3**,
which is itself gated on Task 2's draft existing. If the dropdown does not lift, this does not
ship either, and the row returns here rather than half-landing.

**Status:** GATED — WP-IVGS-09 Task 3 (frontend rebuild) *(was: OPEN. **Record only.** Added to the frontend fix list; not fixed in WP-37.)*

Console error on `/projects/[id]`, in the `page-*.js` chunk:

    Cannot read properties of undefined (reading 'split')

**The page renders** - this is a caught/console-level error, not the crash WP-35 fixed.

**Same family as WP-35** (`reports/WP-35-DETAIL-CRASH-report_2026-08-23.md`): an
unguarded field access against a shape the API does not actually send. WP-35 fixed the
one that took the page down and recorded that `project.target_languages` does not exist
on the wire at all; a `.split()` on an absent string field is the same defect in a
non-fatal position. Worth fixing with the next frontend pass, along with the
`Promise<any>` fetchers WP-35 listed.

## P1.5 — Backup subsystem failure reporting *(new 2026-08-14; replaces the closed secret-hygiene item)*
**Status:** OPEN — the reason a 75-day backup gap went undetected.
Backup tasks return `{'status':'failed', 'returncode':N}` instead of raising, so Celery logs `Task ... succeeded` for a failed backup and every dashboard shows green. Related: direct script runs create no `backup_records` row (the GUI showed 13 records for 75 days of daily attempts, and could not see the only good backup); verification stamps `completed_at` on historical rows, producing 110,502-minute durations; `scripts/backup.sh:374` reads `n_live_tup`, a statistic that resets on restart, which `verify_backup.sh` then compares with a 1% tolerance.
**Scope/action:** raise on non-zero return; `_update_record_failed` sets `completed_at` + `error_message` before raising; record coverage for all invocation paths; write `verified_at` not `completed_at`; frontend duration sanity clamp; real row counts or drop the check. Also investigate why the worker path takes 64 s for work the CLI does in under 1 s. **Agent plan WP-01.**

## P1.5a — `verify_backup.sh` has never been able to pass *(new 2026-08-14)*

**⚖ RULING (operator ruling 2026-08-28): CLOSED — STALE.** The row describes `verify_backup.sh` reading
the staging directory and spawning a 2 GB tmpfs. Neither is true: `dev/CLAUDE.md` §8 records
both fixed on 2026-08-14 (bare-filename checksums; PGDATA on disk, `--memory=512m`), gated
both ways — passes on a known-good backup, fails on a byte-corrupted copy — and the script is
scheduled again at 05:00.

**Status:** CLOSED — stale *(was: OPEN.)*
It reads the **staging** directory (`/tmp/ivgs-backup/<date>`), not the NAS. Compounding this, `backup.sh` writes the checksum file with the staging path embedded, so `sha256sum -c` can never succeed from the NAS. It also spawns a sibling Postgres container with a 2 GB tmpfs via the mounted Docker socket — affordable on 31 GB, and it was never affordable when the box was thought to be 16 GB.
**Scope/action:** point at the NAS directory; write checksums with bare filenames; use real row counts. **Do not run it until fixed.** Agent plan **WP-20**.

## P1.5b — No alert on backup staleness *(new 2026-08-14)*

**⚖ RULING (operator ruling 2026-08-28): CLOSED ON EVIDENCE.** Probed in WP-IVGS-09 Task 0(b). The
alert exists, is loaded, and is healthy:

* **Rule text:** `ivgs-infra/configs/prometheus/alert_rules.yml:190` — `alert: BackupStale`,
  `expr: time() - ivgs_backup_last_timestamp{backup_type!="physical_base_backup"} > 93600`
  (26 hours; severity critical). A second rule, `BaseBackupStale` (`:257`, WP-59 Task 8),
  covers the weekly physical base backup at its own threshold.
* **Live:** `GET :9090/api/v1/rules` on node-01, 2026-08-28 —
  `ivgs_critical_alerts | BackupStale | state=inactive | health=ok`. Loaded and evaluating,
  not merely present in a file.
* An `inhibit_rule` in `alertmanager.yml:63-68` stops `BackupStale` and `BackupFailed`
  double-paging for the same `backup_type`.

**Status:** CLOSED — evidence in WP-IVGS-09 §0(b) *(was: OPEN. `BackupFailed` fires on failure. Nothing fires when a backup simply does not happen — which is the actual failure mode, and was invisible for 75 days because of P1.5.)*
**Scope/action:** alert on the age of the newest `full_database` record, beyond ~26 hours. Agent plan **WP-21**.

## P1.6 — Defect #4: `Prompt.prompt_type` ENUM-as-String *(carried, v3.1 P1.1)*

**⚖ RULING (operator ruling 2026-08-28): ACCEPTED AS `String` — ARCHIVED.** The schema is not changing.
**Validation lives in code**, not in a PostgreSQL type. Consequence, stated rather than left
implicit: **P1.7 is no longer blocked by this row** — its "hard-blocked by P1.6" line is
superseded by this ruling.

**Status:** ARCHIVED — accepted as String *(was: OPEN (latent — prompt library empty). Will 500 on first INSERT with `DatatypeMismatchError`; architecturally identical to the fixed Defect #3 (`User.role`). **Blocks P1.7.**)*
**Scope/action:** `app/models/prompt.py:40-43` — swap `String(32)` for `PG_ENUM` mirroring migration 0001's 10 values; the `.cast(String)` workarounds in `prompt_service.py:61,77` become dead. Build, CLI-verify an INSERT. ~45–60 min.

## P1.7 — Prompt-management 9-step browser smoke *(carried, v3.1 P1.2)*

**⚖ RULING (operator ruling 2026-08-28): GATED — "before first production content render".** It is a
smoke test of a surface an author uses, so it gates the first real course, not a milestone.
Its old blocker P1.6 is archived-as-accepted above, so nothing stands in front of it but the
gate.

**Status:** GATED — before first production content render *(was: OPEN; code deployed in v5.1.8, never functionally smoke-tested. **Hard-blocked by P1.6.**)*
**Scope/action:** seed 10 system-tier prompts → list → filter → detail → project-tier override → effective resolution → edit → delete → fallback. ~30–45 min once unblocked.

## P1.8 — GPU Fleet acceptance bullets (~18 of 24 deferred) *(carried, v3.1 P1.3)*
**Status:** PARTIAL — ~6/24 walked via browser smoke (Session 9); ~18 edge cases unverified (range validation, 30-day bound, `MAX_HISTORY_POINTS=5000` → 413, multi-node JOIN, sort stability, auth gate 403-vs-401, `power_tdp_w`, chart/legend variants, focus re-fetch, 4xx-no-retry, empty-vs-undefined). Unblocked (test infra restored via PR #48).
**Scope/action:** write `TestGpuUtilizationHistory` covering the deferred bullets. 3–5 h.

## P1.9 — AD-02 governance: record deviation, SPOF failover, long-context decision *(carried, v3.1 P1.6)*
**Status:** OPEN (governance/recording). AD-02 is implemented + verified; the deviation and two decisions are not captured.
**Scope/action:** (a) mark **gap N23-4** (LLM-vs-video card contention) RESOLVED by workload separation; (b) document per-stage manual failover for the new SPOFs (node-02 = sole LLM, node-03 = sole video engine) per AD-02.11; (c) **open decision (AD-02.12 #1):** node-02 vLLM runs `--max-model-len 32768` (below the 128 K aspiration), no explicit `--kv-cache-dtype fp8` — interim pending KV-headroom validation; record + schedule. **Update to AD-02 Draft 3** (node-06 Intel→CUDA, card swapped to RTX 6000 96GB).

---

# WS-T — Orchestration Migration (Temporal) *(new workstream)*

**Rationale.** The orchestration layer is ~6,283 lines, of which ~1,957 is orphaned (P2.1) and the live 1,397-line orchestrator has zero test coverage (P2.2). Four correctness defects (P0.1, P1.1–P1.3) are instances of three structural limits that cannot be fixed in place: (a) Redis-as-broker has no liveness signal, only a guessed timeout; (b) at-least-once delivery requires a hand-written idempotency guard at every fan-out, forever; (c) crash recovery must be designed per-stage, eight times.

**Decision context.** The alternative is not "do nothing" — it is finishing the bespoke layer: wiring P2.1's three services into eight stage tasks, building the checkpoint write path, join idempotency, orchestrator tests, plus the still-unwritten `render_segments` resume and parallel talking-head fan-out. That is ~9–13 sessions for a structurally weaker result maintained by one operator. Temporal is ~8–14 sessions, deletes ~5,200 lines net, and turns the last two items into child workflows.

**Agreed sequence** (supersedes any earlier ordering):

| ID | Item | Status |
|---|---|---|
| **WS-T.1** | Fix P0.1 + P1.1–P1.3 (config + point fixes; **not** a broker swap) | OPEN |
| **WS-T.2** | Close M1: ORCH-6 (P1.0) + Stage-8 validation (P1.4) → verified end-to-end at short duration on node-01 + node-04 | OPEN |
| **WS-T.3** | Capture the known-good short-job reference output (the migration's verification target) | OPEN |
| **WS-T.4** | Author **AD-05 — Orchestration Migration** (§18 amendment artifact): workflow shape per stage, activity boundaries, the two human gates as signals, cutover + rollback, in-flight job handling. Review-board approval before code. | OPEN |
| **WS-T.5** | Stand up the Temporal node (dedicated host — **not** node-01; see risk note) + migrate the coordinator across all 8 stages **in one arc** | OPEN |
| **WS-T.6** | Verify against WS-T.3's reference output; keep the Celery path behind a flag until verified | OPEN |
| **WS-T.7** | Roll out nodes 02/03/05/06 on the new architecture — each node configured **once** (absorbs P3.3 / handoff register #4) | OPEN |

**M3.1 review-board gate PASSED 2026-08-22** (operator Bruce Costello; AD-05 Draft 2 items A-1…A-8 all approved, none withheld) — **migration code authorized**; preconditions (M1 close, M2 close, fleet-to-node-07 reachability, quiet window) still gate cutover per §11.2.

**Then:** long-video testing (M3) with resume-from-failure.

**Scope discipline (hard).** Replace the coordination layer only — stage transitions, completion callbacks, join counters, watchdog, checkpointing, retry/DLQ plumbing. **Preserve** the eight stage bodies (~25,000 lines of June's hard-won domain knowledge: Jinja fixes, extensible-WAV handling, scene linkage, AD-03 duration anchoring, ffmpeg logic) as activities with thin wrappers. **Keep** `ivgs-scheduler`, the API, frontend, DB schema, MBCP seam, Model Store. *If a migration session finds itself editing stage internals, stop — scope control has been lost.*

**Risks to manage.**
- **Half-migration.** P2.3 is a v1→v2 orchestrator migration half-done since June. Mitigation: all 8 stages in one arc; no long-term coexistence; Celery path flag-gated until WS-T.6 passes.
- **node-01 capacity.** 8 vCPU / 16 GB already runs ~13 services and is the P1.9 SPOF. Operator has confirmed additional compute is available — **provision a dedicated Temporal node.** If that changes, DBOS Transact (library-only, no new server, uses existing Postgres) is the resource-respecting alternative.
- **New failure modes.** Determinism constraints; replay-only bugs; versioning discipline for in-flight workflows during deploys (multi-hour renders + multi-day gates make this constant, not occasional).
- **Not a quality fix.** WS-T addresses none of M1. Do not let it displace P1.0/P1.4.

---

# P2 — Medium Priority

## P2.0a — Establish which API endpoint node-04 workers actually call, and why its traffic does not appear in `ivgs-fastapi`'s access log *(new, WP-02 check-5 verification, 2026-08-15)*
**Status:** OPEN — unresolved observability gap. Not a known-broken path: the calls **succeed**.

**What was observed.** During the WP-02 check-5 Stage-6 render on node-04
(2026-08-15 01:54–02:24), the worker demonstrably made successful Pipeline-API
calls against **this** database:

- It downloaded 13 assets (1 reference clip + 12 scene audio) via
  `GET /assets/{id}/download` — the render could not have produced output otherwise.
- Its upload was content-hash deduplicated against asset
  `b45b19ce-c12a-459f-bdf0-1dcae7625a4e`, whose `reference_count` went 1 → 2 and
  whose `last_accessed_at` was stamped `2026-08-15 02:24:01.236` — 33 ms before the
  task's own `stage6_talking_head_complete` at `02:24:01.269`.
- Its checkpoint POST returned **405**, which matches `ivgs-fastapi`'s actual route
  table exactly (GET-only on `/jobs/{id}/checkpoints`, ledger P1.2) — so whatever
  answered behaves like this API.

**What contradicts it.**

- `docker logs ivgs-fastapi` contains **zero** `/assets` or `/jobs` requests across
  **74,969 lines**, spanning container start (2026-08-14 16:48) through the render.
- The access log **does** capture that route family — a control probe from node-01
  appears as `192.168.1.90 … "GET /api/v1/projects/{uuid}/assets" 403 Forbidden`.
- `pg_stat_activity` showed **no** client connection from `192.168.1.93`; only the
  node-01 docker-bridge clients `172.20.0.6` and `172.20.0.12`.

**Candidate explanations — none asserted, all untested:**

1. A second API instance somewhere (on node-04, or elsewhere) sharing this Postgres.
2. A different ingress path (nginx, another published port, or a proxy) whose
   requests are attributed differently.
3. Access-log level or filtering that suppresses these specific routes under some
   condition not reproduced by the control probe.
4. Worker environment on node-04 pointing `API_BASE_URL` at an unexpected URL.

**Why it matters.** Until this is settled, `ivgs-fastapi`'s access log cannot be
used as evidence of what the fleet did or did not call — which is precisely the
kind of blind spot the WP-00 register exists to eliminate. It also means any
audit, rate-limit, or incident timeline built on that log is incomplete for
worker traffic.

**Scope/action:** on node-04, read the worker's effective `API_BASE_URL` and
`full_base_url`, `curl` the resolved host, and trace where the request terminates
(`ss`, `iptables -t nat -L`, container inspect). Then reconcile against
`ivgs-fastapi`'s logging configuration. Cross-node work — operator-run.
*(Deliberately not investigated at discovery time; recorded to avoid an unbounded
detour mid-verification.)*

## P2.1 — 1,957 lines of orphaned operational machinery *(new, code audit; **decide before wiring**)*

**⚖ RULING (operator ruling 2026-08-28): THE LOST TEXT IS FOUND AND RESTORED — no REMOVE-per-A1.**
The row's title says *"decide before wiring"* and §RC-H3 asked *decided what?*. WP-IVGS-09
Task 0(b) grepped the reports and specs; **the decision exists in three places and agrees
with itself**:

* `docs/adr/ADR-005-durable-execution-engine.md:1-6` — **Status: Accepted**, 2026-08-14,
  decider Bruce Costello. The WS-T fork was taken, in favour of Temporal.
* `docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md:219-221` — `RetryEngine`,
  `DLQService` and (then) `FallbackChain` sit in the **Replace/Delete** column of the binding
  §8 scope boundary.
* `docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md:287` — migration step **8**:
  *"After a clean verified run, delete the Celery coordinator and the ~1,957 orphaned lines;
  retire ledger P0.1, P1.1–P1.2, P2.1–P2.3 together."*

**So the decision is: DELETE, at AD-05 migration step 8, with `FallbackChain`'s L1→L4 policy
extracted first** (AD-05 §8's named special case). Two of the three modules are already gone —
WP-IVGS-08 Task 2(a) deleted `services/fallback_chain.py` under an operator ruling. **Gate:
AD-05 step 8 (post-cutover), i.e. after M3.3-R5.**

**Status:** GATED — AD-05 migration step 8 (post-cutover) *(was: OPEN — **this is the WS-T fork in the road.**)*
`RetryEngine` (461), `DLQService` (754), `FallbackChain` (742) are **imported by no stage task**. They reference each other only in docstrings describing an integration that was never built (`dlq_service.py:18`, `fallback_chain.py:23`). Their internal lazy imports use a package that does not exist anywhere in the repo — there is no `ivgs_workers/` directory and nothing in `pyproject.toml` creates the alias — e.g. `fallback_chain.py:459`, `periodic_tasks.py:166`. **14 such imports.** Being inside function bodies they don't break registration; they would `ModuleNotFoundError` on first execution. This is why `periodic_tasks.py` is dormant: it cannot run.
Meanwhile actual retry behaviour is ad-hoc `self.retry()` with hand-rolled `retry_config` lookups (`stage1_transcript.py:678-694`, `stage2_storyboard.py:702-718`), and Table 6-4's backoff sequences are re-encoded as decorator constants across eight files.
**Scope/action:** **Do not wire these in pending the WS-T decision** — 2–4 sessions of work a durable engine makes redundant. **Do** extract `FallbackChain`'s L1→L4 *policy* (needed either way; it is domain logic). Under WS-T these 1,957 lines are deleted outright.

## P2.2 — Test coverage is inverted *(new, code audit)*

**⚖ RULING (operator ruling 2026-08-28): ARCHIVED AS OBSERVATION.** "Coverage is inverted" is a
measurement, not a task, and it has no target to be measured against. **The target is set by
M3.3-R3**: tests are written against the realized activities, not against the orchestrator
they replace — which is what the row's own scope/action already said. Archived rather than
carried, so it stops being counted as open work nobody can finish.

**Status:** ARCHIVED — observation *(was: OPEN — most significant supportability finding.)*
Zero tests reference `pipeline_orchestrator*`, `handle_stage_completion`, or the media join. Meanwhile `test_retry_engine.py` (236), `test_dlq_service.py` (379), `test_fallback_chain.py` (244) — **859 lines** — cover the P2.1 modules that never execute. The 1,397-line live orchestrator, source of most ledger incidents, is untested.
**Scope/action:** if WS-T proceeds, write tests against the new workflow definitions rather than the doomed orchestrator. If it does not, orchestrator tests become P1.

## P2.3 — Orchestrator cleanup (v1→v2 remaining half) *(carried, v3.1 P2.26; **partially reframed by P1.0**)*
**Status:** OPEN. Safe — nothing calls v1's stage orchestration (functional half closed in `9f692ab`).
**Scope:** (a) excise v1 `pipeline_orchestrator.py` stage-orchestration (`dispatch_pipeline`, `handle_stage_completion`, stub maps) **but keep v1's 6 periodic tasks** that `beat_schedule` actually uses; (b) delete v2's dead inline `build_composition_manifest` (`pipeline_orchestrator_v2.py:~522`; the map dispatches `stage4_manifest`); (c) **dual talking-head file — see P1.0: promote the provider-factory version, don't simply delete it**; (d) the systemic filename-vs-registered-name off-by-one (below) — `9f692ab` aligned the *map*; do **not** rename tasks; (e) kill the dead worker-side `ManifestBuilder`; (f) consolidate `tasks/periodic_tasks.py` (dormant per P2.1); (g) the dead `stage6_talking_head.py:241` carries the wrong `/assets/upload` URL — dies with the file.

**Registered-name mismatch table (verified `e613e844`):**

| File | Registered name |
|---|---|
| `stage5_voiceover.py` | `tasks.stage4_voiceover.generate_voiceover_task` |
| `stage6_talking_head.py` | `tasks.stage5_talking_head.generate_talking_head_task` *(in no map)* |
| `stage7_prototype_draft.py` | `tasks.prototype_draft_task.assemble_prototype_draft` |
| `stage8_final_render.py` | `tasks.final_render_task.render_final` |

Each is a runtime-only `next_stage_task_not_registered` waiting to happen; none is caught by any static check. *(Independently corroborated by AD-04-v3 §8, which flags the Stage-6 map entry.)* WS-T removes this class entirely (typed calls, import-time failure).

## P2.4 — Residual 4xx cluster *(carried, v3.1 P2.27; checkpoint line item promoted to P1.2)*
**Status:** OPEN — render proceeds through all of these.
`POST /clip/score` → **404** (images get `quality_decision: flagged`, `clip_score: null`); `GET /assets?sha256=` → **404** (dedup absent → duplicate rows on re-fires; dedup also wouldn't backfill `scene_id`); `POST /quality-scores` → **404** (quality persistence absent). Re-enable dedup/quality when the quality/composition stages need them.

## P2.5 — ORCH-5: worker → `projects.state` mapping (+ tighten `approve_storyboard` guard) *(carried, v3.1 P2.28)*

**⚖ RULING (operator ruling 2026-08-28): JOINS RC-F / M3.3.** Worker → `projects.state` mapping is
orchestration-layer behaviour and moves with the orchestration layer. Tracked in **§RC-F**
alongside P1.2 and P2.4 rather than separately here.

**Status:** GATED — M3.3 (§RC-F) *(was: OPEN — confirmed reproducing. After a full run `projects.state` stays stale even though the pipeline advanced; the dashboard view is misleading (render-job stage + dispatched tasks are the de facto truth). The deliberately lenient `approve_storyboard` guard (`project_service.py`) accepts pre-`STORYBOARD_GENERATION` states and is empirically relied upon by the e2e.)*
**Scope/action:** update `projects.state` on each transition. **FIX-WHEN:** once state advances correctly, tighten the guard per spec Table 4-3. *(Under WS-T this becomes a workflow query — truthful by construction. Consider deferring the full fix into WS-T rather than fixing twice.)*

## P2.6 — GPU monitoring + heartbeat registry (Blackwell) *(carried, v3.1 P2.29)*
**Status:** **(a) CLOSED 2026-08-25 (WP-48-TELEMETRY). (b) still OPEN.**

**(a) Exporter — CLOSED.** The panic diagnosis was right and the fix was the restricted
`--query-field-names` list, now in ONE tracked file — `ivgs-infra/docker-compose.telemetry.yml`,
its own compose project `ivgs-telemetry` so it cannot recreate an engine — deployed to
nodes **02, 03, 04 and 05**. Evidence, measured 2026-08-25 after deploy: all four
`nvidia-gpu-exporter` Prometheus targets **UP**; `nvidia_smi_power_draw_watts` present for
all four (16.32 / 16.29 / 19.31 / 15.93 W); `GET /api/v1/nodes` returns non-null
`used_vram_mb`, `gpu_utilization_pct`, `temperature_c` **and** `power_draw_w` for all four.
This replaced three separately hand-written untracked `docker-compose.gpuexp.yml` files
(three shapes, two container names) that had each drifted on their own node.

Two things the old diagnosis had wrong, recorded because they cost hours:
* **node-02 was not a panic.** Its exporter was running and logging `Listening on
  [::]:9835`, and the host port returned nothing because the container held **no network
  at all** — `NetworkSettings.Networks == {}`, no docker-proxy, no DNAT rule. Its compose
  project's network had been removed underneath the running container. A `down` + `up`
  reattached it. "The process is up" and "the port is published" are independent facts.
* **The dcgm detour is traced and cleaned.** `ivgs-dcgm-exporter` on node-02 came from
  hand-run `docker run` trials (`/root/.bash_history` 378–423) that were then written into
  a compose block and a systemd unit (lines 449–451, 476, 495). Its metric names are
  `DCGM_FI_DEV_*`, which nothing in this repo reads. The 928 MB dangling image is removed;
  no dcgm container, compose block or unit file remains. See P2.42 for the one inert trace.

**(b) Heartbeat — still OPEN.** Registry still empty (`total_nodes:0` → `gpu_reservation_skipped`;
scheduler `:8002` → 503). Wire node GPU heartbeat registration. **Pairs with P1.3** — the
reservation subsystem fails open, which is why this stayed invisible. **Note:** the exporters
are now real, so (b) is no longer blocked on measurement — a heartbeat can be sourced from
the same Prometheus series `/api/v1/nodes` already reads. *Not addressed by WS-T.*

## P2.7 — MBCP: `serving-authoring-loop-1` unhealthy *(new, handoff register #2)*
**Status:** OPEN — pre-existing on `.51`. Diagnose.

## P2.8 — MBCP RuntimeClass refactor — **CLOSED** *(corrected 2026-08-14)*
**Status:** CLOSED. The consolidation was **already merged as PR #48** — `mbcp_adapters/runtimes/comfyui.py` plus nine JSON graphs. The "awaiting approval on Tasks B/C/D" framing in v4.0 was stale, and the Option-B split decision taken on that basis is moot. Recorded so the trail is visible rather than silently dropped.

## P2.9 — MBCP: CogVideoX adapter — **rebuilt, never GPU-tested** *(corrected 2026-08-14)*
**Status:** Code defect CLOSED; re-opened as MBCP **WP-A**. Verified in `cogvideox-5b.json`: `CLIPLoader`, `CogVideoTextEncode`, `CogVideoSampler`, `CogVideoDecode`, `DownloadAndLoadCogVideoModel` — the correct names, no X-suffixed phantoms. **But it has never touched a GPU.** MBCP WP-A is that smoke test and blocks WP-B. Every VRAM figure in `comfyui.py` remains `PROVISIONAL` (see S-7). Treat the first GPU smoke as a gate, not a formality.

## P2.10 — Weight-fetch live pass *(carried, handoff register #5)*

**⚖ RULING (operator ruling 2026-08-28): GATED, TWO STEPS, IN ORDER.** (1) the **MBCP session, steps
1–3** (engine-values query → WO-MBCP-01 → re-send); then (2) **WP-65 §8 Block A**. It is not
runnable before both: a weight fetch needs a bundle whose engine values MBCP has agreed, and
the block that runs it is already written and held.

**Status:** GATED — MBCP session steps 1-3, then WP-65 §8 Block A *(was: OPEN — never exercised. IVGS **pulls** weights via `ivgs-models/mbcp_fetch.py` against `{serving_url}/weights/{model}/manifest`. Needs the fleet up (WS-T.7) plus `MBCP_SERVING_TOKEN` + `MBCP_WEIGHT_SIGNING_KEY` handoff. *(Direction is pull, not push — do not invert in docs or code.)*)*

## P2.11 — `IVGS_SCHEDULER_TAG=latest` — pin *(carried, v3.1 P2.11)*
**Status:** OPEN. §19.5 no-`:latest` violation; the only unpinned tag in `.env`. Confirmed `:v5.1.0` == `:latest` (same image ID) → pinning is a zero-behaviour-change close.

## P2.12 — No manifest regenerate/reset *(carried, v3.1 P2.30)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.

`composition_manifests.job_id` is UNIQUE with no reset endpoint; re-running Stage 4 can't regenerate. Add a reset/regenerate path.

## P2.13 — Animation stored as `asset_type="image"` *(carried, v3.1 P2.31)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Interim relabel; the manifest groups animation as image. Give animation a distinct type for correct layer semantics.

## P2.14 — `assets.duration_seconds` not persisted on upload *(carried, v3.1 P2.32 + Addendum B1 — merged)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
The voiceover task computes real per-scene durations and the column exists, but `POST …/assets/upload` accepts only `file/asset_type/scene_id/language_code` → all audio rows `NULL`. Stage 7 works around it by re-deriving the timeline via `ffprobe`. **Root of the "duration disease"** — Stage-4 storyboard estimates (115s) were never reconciled against real narration (~214.94s). **Fix:** add a `duration` form field (plus `sample_rate`/`bit_depth`) or probe server-side.

## P2.15 — `seaweedfs_path` not unique per scene *(carried, v3.1 P2.33)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Server derives the audio path from project + language only, so all same-language audio share one path string with distinct FIDs; the worker reports a *different* path. Latent trap for anything reconstructing paths instead of using `seaweedfs_fid`/`asset_id`. Include `scene_id` in the server path; align the worker's reported path.

## P2.16 — Rollback snapshot/restore unwired *(carried, v3.1 P2.35)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Storage-path crash fixed (`c3e8a1a`), but `rollback_service.py` (~164/241/244) still references `/ivgs/ivgs-api/config` and `/ivgs/.env`, and `rollback_to` restarts containers — full §14.3 rollback needs host-level `deploy-node.sh` integration. Decide: wire to the real layout, or remove.

## P2.17 — Voiceover dead scene→audio back-link PATCH (401) *(carried, v3.1 P2.36)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Fires 6×/run. Audio is already scene-linked via the upload form's `scene_id` (`eaddebb`), so the back-link adds nothing and is swallowed as a warning. Confirm nothing reads `scene.audio_asset_id`, then delete the call + helper. Bundle with P2.3.

## P2.18 — `GET /assets?asset_type=reference_clip` returns 500 *(carried, v3.1 P2.37)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Orchestrator's presenter-clip lookup 500s; the orchestrator soft-continues so it doesn't block. A 5xx server bug — likely an enum/query mishandle in `list_assets`. Return empty list / clean 404 so Stage 6 can take the no-clip skip path.

## P2.19 — stage7 caption clock not audio-anchored *(carried, Addendum B2)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Latent until captions are enabled (Remotion on node-06, WS-T.7). Anchor the caption clock on real audio length, same principle as the Pillar-1 fix.

## P2.20 — Duplicate/accumulated assets; no supersede-or-prune *(carried, Addendum B3)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Re-fires accumulated multiple draft assets (`0a83f6f2`, `8e0c8531`, `4a9ce479`, `061f64eb`, `f78eb063`) plus duplicate per-scene audio. Add an asset supersede/cleanup policy. Inflates SeaweedFS and muddies "current best".

## P2.21 — Defect #5: "[object Object]" validation banner *(carried, v3.1 P2.3)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Frontend error-handler doesn't string-coerce FastAPI's structured detail envelope. Extract `detail[0].msg`. Pairs with P2.23.

## P2.22 — Defect #9: `/api/v1/nodes` stub hardcodes `status="online"` *(carried, v3.1 P2.4)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.

`nodes.py:82` returns "online" unconditionally → "6 online" when only node-01 runs. Interim ICMP/DNS ping, or full fix at fleet rollout. Don't add `test_nodes.py` until then (would freeze the lie).

## P2.23 — Backend UUID path-param validation (422 not 500) *(carried, v3.1 P2.7)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Class-level UUID validation; architectural decision on scope + error envelope. Pair with P2.21.

## P2.24 — Migrate ad-hoc `fetch()` to centralized api-client *(carried, v3.1 P2.6)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
16 sites in 7 files + GPU-history call → `src/lib/api-client.ts`; add a pre-commit hook blocking unprefixed `access_token` reads.

## P2.25 — CI scaffolding (Actions + Playwright + pytest) *(carried, v3.1 P2.13)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
(a) Playwright smoke for the 8-page + 9-step walks; (b) `build-images.yml`; (c) PR template (stale-base + tsc + migration-roundtrip + overlay-rule). Multi-session.

## P2.26 — Test directory scope unification *(carried, v3.1 P2.1)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.

`tests/` (9), `ivgs-workers/tests/` (16), `ivgs-scheduler/tests/` (4) unrunnable; `conftest.py` collision blocks a unified `testpaths`. Resolve via `importmode=importlib`; wire testcontainers + Alembic. Pairs with P2.27, P2.2.

## P2.27 — `tests/` pytest collection fails on SQLite *(carried, v3.1 P2.24)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.

`shared/database.py:31` passes `pool_size`/`max_overflow`/`pool_timeout` unconditionally; SQLite/NullPool → TypeError at `create_engine`. Make the factory dialect-aware.

## P2.28 — Author RUNBOOK.md *(carried, v3.1 P2.18)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
High institutional value; more material than ever. §1 session-start gate; §2 deploy invariants (build from monorepo root; `--env-file` + `-f` overlay rules; `--force-recreate --no-deps <svc>`; derive compose invocation from container labels); §3 image-drift lesson; §4 backup; §5 incident response. **Absorbs P2.21-tag-taxonomy from v3.1.** Prerequisite for delegating work to agents.

## P2.29 — Compose reconciliation: `base.yml` vs `node01.yml`; monitoring net *(merges v3.1 P2.19 + P2.25)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.

`base.yml` (seaweedfs 3.80, underscore volumes) vs `node01.yml` (3.71, hyphen volumes) — twice caused recreate accidents; reconcile or delete `base.yml`. `docker-compose.monitoring.yml` references non-existent external net `ivgs_default` (real net: `ivgs-infra_ivgs-net`) — latent because deploys use `--no-deps`.

## P2.30 — Image/dependency hygiene *(merges v3.1 P2.8, P2.10, P2.15, P2.22)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
(a) Old GHCR image cleanup — 14+ stale tags each for api/frontend; author a retention policy. (b) bcrypt/passlib version warning at startup — pin compatible versions. (c) Restore `@sha256` digest pins on base images lost in `b933357`; pin live `v5.5.x` digests in compose. (d) Pre-commit hook failing `*.key`/`*.crt`/`*.pem` under `configs/nginx/ssl/`.

## P2.31 — Update `IVGS_INFRASTRUCTURE_REFERENCE` *(carried, v3.1 P2.17)*

**Status:** VERIFY-AT-RUN-2 — see the ruling above

**⚖ RULING (operator ruling 2026-08-28): VERIFY-AT-RUN-2.** This row is one of the **20 carried-from-v3.1
rows, P2.12 through P2.31 inclusive**, ruled as one block. They are not closed on reading and
not archived on age: **RUN-2 exercises them, and observation closes or confirms each one.**
Whatever RUN-2 does not touch gets **one bounded sweep immediately afterwards — P2.46**.

⚠ Two rows in this range were missing from §RC-H3's grouped entry (`P2.12–P2.14, P2.16–P2.28,
P2.30, P2.31`, which is **18**, not the 20 the same section claimed): **P2.15** and **P2.29**.
The ruling is on the **contiguous range**, so both are included and the count reconciles at 20.
Still describes a split repo. Update to the monorepo at `/opt/ivgs`.

---


## P2.32 — AD-07 v2.x contract extension: style bible, continuity IDs, source refs *(new 2026-08-22)*

**Status:** OPEN — **recording only, nothing implemented.**
**Origin:** operator-commissioned external design review, 2026-08-22. Working note on node-01
at `docs/Assessment_External_Orchestrator_Prompt_vs_IVGS_2026-08-22.md` — **currently
untracked**; commit it if this entry is to have a durable citation.

Extend the AD-07 Scene Contract (§2.2) with three additions:

1. **`style_bible`** — a per-project block, authored once and carried whole, describing the
   visual language every generated asset must obey.
2. **Persistent continuity IDs** — stable identifiers for characters, environments and
   reusable assets, so the same person or place is recognisably the same across scenes and
   across regenerations.
3. **`source_refs` per scene** — optional, pointing at the material a scene was derived from.

**Gate — this is the point of the entry.** This extension MUST be drafted **and ratified**
before implementation of **WS-H (certified head model)** begins. Generated-visual continuity
depends on it: standing up a certified head without a continuity contract produces a model
that is certified against a looser private contract than the one the pipeline needs, which is
exactly the drift AD-07 §6.3 exists to prevent.

**Relationship to AD-07 as ratified.** This is a v2.x *extension*, not an amendment to what is
already ratified — the Brief and Scene Contract v2 stand unchanged. It needs its own draft and
its own ratification.

## P2.33 — Stage-2 computes a duration total and never checks it *(new 2026-08-22)*
**Status:** OPEN — **recording only.** Cheap; **Track P candidate.**

`stage2_storyboard.py` computes `total_duration` but never compares it against
`max_runtime_seconds`. The runtime target reaches the model as a **prompt suggestion only**,
so a storyboard may plan well past the user's stated budget and nothing says so at plan time.
The first hint arrives after audio and render time have already been spent.

**Scope/action:** add an **advisory** check — warn or flag when the planned total falls outside
`runtime_tolerance_pct` of `runtime_target_seconds`.

**Binding constraint on the fix.** It must **never override the AD-03 measured-audio anchor.**
Measured audio is ground truth for duration; this check is a plan-time smell test, not an
authority. A gate that trims scenes to hit a planned number, in preference to what the audio
actually measures, would be a regression dressed as a feature.

**Relationship to AD-07.** AD-07 §2.2 specifies a real duration validator with a body. This
entry is the cheap advisory version available **now**, on the current contract, and is not a
substitute for that validator.

## P2.34 — `visual_style` is a dead knob *(new 2026-08-22)*
**Status:** OPEN — **recording only.**

`stage3_images.py` reads `visual_style` from `project_context`, but **nothing in `ivgs-api`
ever populates it**. Every project therefore generates with the hardcoded default, and the
knob appears to exist while doing nothing.

**Same defect family as WP-IVGS-0 defect 0.1** — a user-facing field that never reaches the
stage that would consume it, the read side built and the write side absent. See
`dev/workpackages/WP-IVGS-0_Defect_Fixes.md`.

**Scope/action:** fix alongside **P2.32** (where `style_bible` supersedes a bare
`visual_style` and the field needs designing rather than merely wiring), or as part of the
WP-IVGS-0 follow-up if that lands first. **Do not wire it in isolation** without deciding
which of the two owns the field, or the same conflict is rebuilt one layer up.

# P3 — Low Priority

| ID | Item | Note |
|---|---|---|
| P3.1 | `GpuNodeStatus` UPPERCASE half (dead code) | `types/api.ts`; backend emits lowercase only. Delete + `tsc --noEmit`. |
| P3.2 | Empty underscore-named seaweedfs volumes | Four empty 4K volumes from an S5 mis-application. Verify no compose refs, then remove. |
| P3.3 | Endpoint test coverage (9 modules) | No tests for `alerts`, `jobs`, `languages`, `manifests`, `nodes`, `quotas`, `rollback`, `ws_logs`. Priority `jobs`/`rollback`. |
| P3.4 | Rogue-branch attribution investigation | 10 commits by `node01-ops <ops@ivgs>`; branch force-deleted Session 9. Operator-driven; blocks nothing. |
| P3.5 | Cosmetic / UI polish | Banner auto-dismiss; action-message badge polish. |
| P3.6 | Session hygiene bundle | `.bak` cruft in `ivgs-workers/`; GPU-node source-tree drift; ~30 `.env.bak.*` in `ivgs-infra`; `/root` tarball + stage cleanup on both hosts. *(Absorbs v3.1 P3.7 + handoff register #3.)* |
| P3.7 | `composition_manifests.manifest_version` left NULL | API `generate` doesn't populate it. |
| P3.8 | `render_jobs` has no `updated_at` column | Minor schema inconsistency; add for audit parity. |
| P3.9 | In-code Coqui default still wrong (guarded) | `stage5_voiceover.py:~516` hardcodes `http://node-04:5002`; env URLs override. Correct on next build. |
| P3.10 | Audio validator doesn't parse `WAVE_FORMAT_EXTENSIBLE` SubFormat GUID | `_parse_wav_header` reads only the first 16 `fmt ` bytes. Fine for current XTTS output. |
| P3.11 | Downstream audio readers must tolerate extensible WAV | Any stage using stdlib `wave` (raises on `0xFFFE`) will fail. Verify tolerant decoders or transcode at the Stage-5 boundary. |
| P3.12 | Clients swallow real exceptions to `""` | `flux_client`/cogvideox/coqui mask root causes (the Stage-5 10s Coqui timeout hid this way). Surface real errors. |
| P3.13 | Properly type `FlaggedAsset.metrics` | Currently `any`; define a discriminated union. |
| P3.14 | Forensic correction: Session 5 close | Record PR #45/#46/#47 merges; note the `deps.py` path typo. |
| P3.15 | Dead `get_beat_schedule()` in `periodic_tasks.py` | *(handoff register #3)* Dies with P2.3(f). |
| P3.16 | Backup-worker hardcoded DSN fallback | *(handoff register #3)* |
| P3.17 | Per-project model-selection GUI + auto-weight-fetch-on-approve; light-mode contrast sweep; authenticated `/nodes` topology check | *(handoff register #6 — optional/future)* |

---

# S — Cross-System (IVGS ↔ MBCP)

**These belong to neither register and will be dropped by both unless owned.** Source: Step 10 reconciliation, 2026-08-14.

| ID | Item | Owner | Note |
|---|---|---|---|
| **S-1** | Coordinated ingest-token rotation **+ Postgres password** | **Operator** | `MBCP_AD01_TOKEN` == `IVGS_MBCP_INGEST_TOKEN`. Exposed on the MBCP side 2026-08-04. Rotating one side alone breaks the seam **silently** — exports park in `drain-pending-exports` and retry every 5 min. Both hosts in one window. **WIDENED 2026-08-22 (WP-DEPLOY-R2-R5-NODE04 §4.1):** the incident report's R4 verification block ran `docker exec … env \| grep IVGS_`, printing **`IVGS_MBCP_INGEST_TOKEN`** — the one variable CLAUDE.md §3 forbids printing — **and the Postgres password**, carried in clear text inside `IVGS_CELERY_RESULT_BACKEND`. Both reached a terminal and an agent transcript. **The Postgres password is now in this rotation set**; it was not before. Blast radius is wider than the token's: `DATABASE_URL`, `IVGS_CELERY_RESULT_BACKEND`, `ivgs-infra/.env`, `.env.node0*` on every node, `/etc/ivgs/cron-backup-env`, and the backup scripts. The offending grep has been narrowed in all four places it appeared (R4 block, runbook §3.4, CLAUDE.md §6, and this package's own report). |
| **S-2** | Stage taxonomy divergence | IVGS agent | IVGS has 8 **pipeline** stages; MBCP has 9 **capability** stages (`mbcp_core/enums.py`). MBCP's image/video/animation → IVGS Stage 3; `composition` collapses 4/7/8; `translation` is not an IVGS stage. AD-01's `(stage,tier)` key uses MBCP's taxonomy. Document in AD-01 §AD-01.16 + glossary. |
| **S-3** | Addendum number collision | Operator | Two different AD-05s (IVGS orchestration, MBCP adapter authoring) and MBCP also has AD-06. **Decision D-7: namespace as `IVGS-AD-NN` / `MBCP-AD-NN`.** No renumbering. |
| **S-4** | Weight-fetch unblocked earlier than assumed | IVGS agent | IVGS is cloned at `/root/IVGS` on `.51`, so `mbcp_fetch.py` can be proven now. Only the production pass needs M4. Sequence **after** S-1, since `WEIGHT_SIGNING_KEY` and `WEIGHT_SERVICE_TOKEN` are in that rotation set. |
| **S-5** | Schema coupling with no test | MBCP agent | `e613e84` added `ffmpeg` to `ModelEngine` to unblock MBCP composition exports; MBCP added `ExportBundle.engine`. Coupled across two repos, **no test either side**. Agent plan **WP-17**. |
| **S-6** | 8 of 18 certifications rest on audited overrides | MBCP (WP-I) | AD-01 treats certification as evidence for approval. IVGS cannot see which certificates are full-gate. Attestation should carry gate status. |
| **S-7** | VRAM figures are `PROVISIONAL` | IVGS agent | 15 placeholders in MBCP's `comfyui.py`. **D-8: does `ivgs-scheduler` consume declared VRAM, or measure locally?** If declared, MBCP WP-A becomes an M4 prerequisite. Agent plan **WP-19**. |
| **S-8** | CogVideoX resolution overclaim | MBCP (WP-B) | Declared 1920×1080; engine is 720×480. If IVGS ever sizes a request from these specs it will ask for the impossible. |
| **S-9** | `.7` and `.53` absent from IVGS docs | IVGS agent | **Partially closed 2026-08-14** — `.7` is now IVGS's backup target and appears in `dev/CLAUDE.md` and `configs/systemd/README.md`. `.53` (authoring LLM, firewall permits only `.51`) still undocumented on the IVGS side. |
| **S-10** | `.51` is a Proxmox clone with a parked twin | Operator | Shares `machine-id` and SSH host keys with the parked production VM. node-01 holds a known-hosts entry for `.51`. Regenerate before both run; expect to clear node-01's entry. |

## P2.35 — Proposed AD-01 amendment: an auxiliary text-generation ModelStage *(new, WP-IVGS-0.2, operator ruling 2026-08-22)*

**⚖ RULING (operator ruling 2026-08-28): DROPPED — zero named consumer.** The proposed auxiliary
text-generation `ModelStage` has no caller, no stage and nobody asking for it. An amendment
to AD-01 that nothing would use is a schema change bought with no benefit. Dropped, not
deferred: there is no trigger that would make it right later that would not also be a fresh
proposal.

**Status:** DROPPED — see the ruling above

`ModelStage` has nine members and none covers an auxiliary chat-LLM call, so Stage 3's image-prompt writer borrows `storyboard_generation` and Stage 5's narration optimiser borrows `transcript_refinement` (`utils/llm_binding.py`; bindings KEPT as implemented by ruling) — propose a dedicated stage at the next AD-01 amendment and repoint those two call sites.

## P2.36 — Per-run tier selector in the UI — DEFERRED to M6 *(new, WP-IVGS-0.3, operator ruling 2026-08-22)*
`?tier=` is plumbed end to end on `POST /projects/{id}/trigger` and `POST /projects/{id}/storyboard/approve` and defaults to prototype, but nothing in the frontend sets it; surface a per-run choice at M6.

## P2.37 — `segment_planner` splits Stage-8 render segments on float boundaries *(new, WP-04-FRAME-ALIGN D-2, operator ruling 2026-08-23 — RECORD ONLY, do not touch)*

**⚖ RULING (operator ruling 2026-08-28): CLOSED — settled by AD-03 §10.** The float-boundary question
the row records is answered by AD-03 §10's criteria; there is no separate decision left to
make about `segment_planner`.

**Status:** CLOSED — settled by AD-03 §10 *(was: OPEN — **record only.** Ruled 2026-08-23: do **not** fold this into WP-04.)*
`ivgs-workers/services/segment_planner.py:239-241`:

    num_segments = math.ceil(scene_duration / self._max_duration)
    segment_duration = scene_duration / num_segments

then float `start_time` / `end_time` at `:244-246`. Same defect class as the head
splitter WP-04 fixed, on a different path: this is Stage 8's render-segment planner
(`stage8_final_render.py:395-399`), so it does **not** bear on AD-03 criterion 3 (head
A/V drift). Each segment is rendered independently and concatenated, so per-segment frame
quantisation accumulates the same way.

**Plausible, unmeasured:** the **0.13 s draft-to-final delta** recorded in AD-03 v0.4 §13
(draft 214.94 s, final 215.07 s). Nobody has measured it.

**Why record-only.** Stage 8 is the one end-to-end-validated render path (P1.4a/b: both
the 1080p and the 4K finals passed operator visual QA). Changing its segment boundaries
for a defect nobody has measured is a bad trade. **Scope it separately, measure first.**

## P2.38 — `output_fps` is accepted and discarded; `output.fps` is a claim, never a measurement *(new, WP-04-FRAME-ALIGN D-3, operator ruling 2026-08-23 — RECORD ONLY, do not build)*

**⚖ RULING (operator ruling 2026-08-28): RECLASSIFIED — FIX, not record-only.** `output_fps` is
accepted and discarded, which means the API takes a parameter it does not honour. **Either
wire it or answer 400.** Silently accepting is the one option ruled out. Batched
**post-RUN-2**, so the fix does not move a parameter under the run RUN-2 is banking.

**Status:** FIX — post-RUN-2 batch *(was: OPEN — **record only.** Ruled 2026-08-23: do **not** plumb it now.)*
`ivgs-workers/servers/latentsync/server.py:145` declares `output_fps: int = Form(30)`.
It is **never passed to `_runner`** (`:164-165` passes width, height, mode, seed only) and
`_runner`'s final ffmpeg pass (`:105-109`) carries no `-r`. IVGS therefore **cannot set
the head's frame rate**; it gets whatever LatentSync emits.

Meanwhile `ivgs-workers/clients/latentsync_client.py:380` returns `fps=params.output_fps`
— the client **reports the fps it asked for, not the fps it received**. That value flows
to `talking_head_task.py:616` (`output.fps = seg_result.fps`) and into the asset metadata
at `:827`. **`output.fps` is a claim at every point it is stored.**

It happens to be true today — measured 2026-08-23, the stored head is `30/1` CFR (P1.4o)
— so nothing is currently wrong on the wire. The hazard is that **a Q5 change to any
other value would silently not take effect**, and no stored metadata would reveal it.

**Cheap partial mitigation, not scoped here:** have the task probe its own output and
record the measured fps rather than the requested one.

## P2.39 — 23 urgent scheduling requests are stranded against a zero-node fleet, and nothing owns them *(new, WP-08-GPU-RESERVATIONS D-3, operator ruling 2026-08-23)*

**⚖ RULING (operator ruling 2026-08-28): WP-IVGS-09 Task 0(c), OPERATOR-ATTENDED.** The queue is
listed before anything is drained, and the drain waits for an explicit GO. **The row's
premise has moved twice and both corrections are recorded in the WP-IVGS-09 report §0(c):**
the fleet is no longer zero nodes (3 alive, 293,661 MB), and the "23" is a DEPTH COUNTER, not
a queue census — the counters read `urgent 22 / normal -2 / batch 0` against actual sorted
sets of `urgent 18 / normal 2 / batch 0`. **A queue length of −2 is not a queue length.**

**Status:** ✅ **CLOSED — DRAINED 2026-08-28 on the operator's GO** *(was: OPEN — new item, ruled in 2026-08-23. Nothing owns this today.)*

**⛳ THE DRAIN, EXECUTED.** Disposition table approved as proposed (WP-IVGS-09 report §3.3),
then run inside `ivgs-scheduler` using the scheduler's **own** `PriorityQueueManager.remove_job`
so the disposition is what production does, not what a script thinks production does.

| Group | Count | Method | Result |
|---|---:|---|---|
| Synthetic probes left by WP-IVGS-06/07 | 6 | `remove_job` | hash deleted, zset entry cleared |
| Terminal jobs, hash still present | 2 | `remove_job` | cleared |
| Terminal jobs, hash expired >72 h | 2 | **direct `zrem pq:queue:urgent`** — `remove_job` is a no-op without a hash (`:284`) | cleared |
| Deleted projects, in the urgent zset | 10 | `remove_job` | cleared |
| Deleted projects, in the NORMAL zset with `effective_priority=urgent` | 2 | **direct `zrem pq:queue:normal` + `del`** — `remove_job` would have `zrem`'d from `urgent` (a miss) and decremented `urgent` for a job that never joined it | cleared |
| **Total** | **22** | | |

```
BEFORE  zcards = {urgent: 20, normal: 2, batch: 0}   depths = {urgent: 24, normal: -2, batch: 0}
AFTER   zcards = {urgent:  0, normal: 0, batch: 0}   depths = {urgent:  6, normal: -2, batch: 0}
RESET   zcards = {urgent:  0, normal: 0, batch: 0}   depths = {urgent:  0, normal:  0, batch: 0}
```

⛔ **The middle line is the finding.** With the queue verifiably empty, the counter still read
**`urgent: 6, normal: −2`**. `pq:depths` was reset to the measured `ZCARD` under the same
ruling — **the only reconciliation of these two records that has ever happened, performed by
hand.** The mechanisms that produced the drift are untouched and are now **P2.47**.

Live afterwards: `GET /fleet` → `queue_depth {urgent: 0, normal: 0, batch: 0}`, 3/3 nodes alive,
293,661 MB VRAM. `gpu_reservations` is empty, as it was throughout. Only `pq:depths` remains
under `pq:*`, which is correct — it is the counter hash itself.

⚠ **The list grew by two between §3.2 and the drain, and both fall inside an approved group.**
`3f489575…` and `8cdb79b6…` are this package's own Task-2 test jobs. Their projects were deleted
through the WP-59 flow and **their queue entries survived it** — which is P2.47 site 5,
reproduced live rather than inferred. Disposition: *deleted projects*, as approved.
Measured live on node-01, 2026-08-23:

    $ docker exec ivgs-scheduler sh -lc 'curl -s localhost:8001/fleet'
    {"total_nodes":0,"alive_nodes":0,"draining_nodes":0,"total_vram_mb":0,
     "used_vram_mb":0,"available_vram_mb":0,"fleet_utilization_pct":0.0,
     "queue_depth":{"urgent":23,"normal":0,"batch":0},"nodes":[]}

    $ docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
        "select status, count(*) from gpu_reservations group by 1;"
    (0 rows)

**Twenty-three scheduling requests are queued at `urgent` against a fleet of zero
nodes.** Nothing dequeues them, nothing ages them out, nothing alerts, and no render has
ever noticed — because every acquire fails open (P1.3, swallow-register entry 4). The
`gpu_reservations` table is empty, so the queue is the *only* place this state exists.

**Unknown and worth establishing:** where the queue lives (in-process in `ivgs-scheduler`
or backed by Redis), whether it survives a scheduler restart, whether it is bounded, and
what these 23 requests are — the scheduler has been up 8 days.

## P2.40 — Five of node-01's own Prometheus targets have been DOWN the whole time *(new, WP-48-TELEMETRY, 2026-08-25)*
**Status:** OPEN — measured, not inferred. `GET /api/v1/targets` on node-01, 2026-08-25:

    ivgs-api           http://node-01:8000/metrics   down   context deadline exceeded
    ivgs-scheduler     http://node-01:8001/metrics   down   context deadline exceeded
    node-exporter      http://node-01:9100/metrics   down   context deadline exceeded
    postgres-exporter  http://node-01:9187/metrics   down   context deadline exceeded
    redis-exporter     http://node-01:9121/metrics   down   context deadline exceeded

while **every remote node target is UP** from the same Prometheus. That asymmetry is the
tell: this is the ufw blind spot `node_health.py` already documents — ufw on node-01 admits
only `192.168.1.0/24` to the host and the compose bridge is `172.x`, so a container on
node-01 cannot reach node-01's own published ports. Prometheus is such a container.

**Consequence.** node-01 has no host metrics, no API metrics, no Postgres or Redis metrics
in Prometheus, and has not had them for as long as this configuration has stood. Grafana's
`pipeline_overview` dashboard is reading a Prometheus that holds nothing for the hub. Five
permanently-firing `up == 0` targets also desensitise anyone watching the target page.

**Scope/action:** scrape these over the container network instead of the host port — the
services are all siblings on `ivgs-infra_ivgs-net`, so `http://fastapi-backend:8000`,
`http://postgres-exporter:9187`, `http://redis-exporter:9121` need no firewall change at
all. `node-exporter` is the one genuine exception (it wants the host namespace) and is the
only one that needs a ufw decision. **Note the precedent:** WP-48 solved the identical
problem for node-01's log source by attaching it to `ivgs-net` and addressing it by
container DNS (`docker-compose.telemetry.node01.yml`) rather than opening a port.
**Pairs with P2.29** (compose/monitoring-net reconciliation).

## P2.41 — AD-04 "pull-only" doctrine contradicts the SSOT on the metadata seam *(new, WP-48-TELEMETRY Task 4, 2026-08-25; **CLOSED 2026-08-26 by WP-44-QUALITY Task 6a**)*
**Status:** **CLOSED — ruled option (i): the doctrine is Seam-2-scoped.** The ruling is
written into `dev/CLAUDE.md` §11.1 as a table of the two seams, their directions, their
mechanisms and their authorities, with the AD-04 v3.1 decision-#2 quote that scopes it to
weights and the AD-04-v3 §3.14 quote that sends the metadata seam the other way. Nothing
in the implementation changes: it already conformed to the SSOT on both seams, and the
sentence was what needed correcting. `ad01_ingest.py` stays a receiver — §12.6 makes it
one, and turning it into a poller would be an MBCP-owned amendment to a section §787
freezes. Anyone quoting "pull-only" without naming the seam is quoting it wrong.

<details><summary>Original analysis (WP-48), retained</summary>

**Status when raised:** OPEN — **spec/doctrine conflict, not an implementation defect.** The
implementation was checked against primary sources and **conforms to the SSOT**; what does
not fit is the rule as stated in the work order ("PULL-ONLY: IVGS initiates all transfers
from MBCP; MBCP never pushes").

**What the SSOT says — verbatim.** `MBCP_Master_Functional_Specification_SSOT_v3.3.md`:

> §12.4 — `connected` → `AD01Export`: transmits to the live AD-01 ingest endpoint.

> §12.6 — In `connected` mode, `AD01Export` **posts the package** to `MBCP_AD01_URL`
> authenticated by `MBCP_AD01_TOKEN`. On the IVGS side, AD-01 ingests the package as a
> `CANDIDATE` registration whose attestation is the MBCP certification, and a new
> IVGS-side fetch client (in `ivgs-models`) retrieves the weight bundle from the serving
> plane.

**Where "pull-only" actually comes from.** `IVGS_v5_Addendum_AD-04_v3.1_Amendment.md`,
closed decision **#2 — Weight-serving transport**:

> **Direction is pull: IVGS pulls, MBCP does not push.**

That sentence is scoped to decision #2, the **weight** transport (Seam 2). AD-04-v3 §3.14
is explicit that the other seam runs the other way: *"`AD01Export` (**Phase 4**): POSTs the
bundle to AD-01"*.

**So the two seams have opposite directions by design** — metadata/attestation pushed by
MBCP, weights pulled by IVGS — and a rule stated as "IVGS initiates all transfers" is true
of one and false of the other.

**The ruling needed.** Either (i) the doctrine is Seam-2-scoped and the fleet documents
should say so explicitly, or (ii) the doctrine stands as written, in which case the SSOT
§12.4/§12.6 and MBCP's `AD01Export` + `export_drain` must change — an MBCP-owned,
change-controlled spec amendment (SSOT §787 freezes the export-factory seam), plus a new
IVGS-side scheduled puller and demotion of `ad01_ingest.py` to a disabled receiver.
**Nothing is implemented either way.** Full evidence in the WP-48 report, S6.

</details>

## P2.42 — node-02 `vllm.service`: a disabled unit that would run the wrong compose *(new, WP-48-TELEMETRY, 2026-08-25)*
**Status:** OPEN — inert today, a landmine if ever enabled. `/etc/systemd/system/vllm.service`
on node-02 is `disabled` and `inactive`, and:

    Description=IVGS node-02 container stack (vLLM + dcgm + node-exporter)
    WorkingDirectory=/opt/ivgs
    ExecStart=/usr/bin/docker compose up -d

Two problems. The description still names **dcgm**, which is the last trace of the removed
exporter (P2.6a) and will mislead the next person who greps for it. And `docker compose up -d`
with **no `-f`** in `/opt/ivgs` does not describe any stack this fleet runs — node-02's
services come from `-f ivgs-infra/docker-compose.node02.yml` with `--env-file`. Enabling this
unit would not restore node-02; it would fail, or act on whatever compose file happens to
resolve. **Scope/action:** delete the unit, or rewrite it to the real invocation. Left
untouched by WP-48 deliberately — editing a systemd unit is outside an additive-exporter
package, and the unit is inert.

## P2.43 — node-05's hardware is corrected in the operational docs but not in the specs *(new, WP-48-TELEMETRY Task 5, 2026-08-25)*
**Status:** OPEN — a spec amendment, needs the change-control path, not a quiet edit.
Measured on the box 2026-08-25: `NVIDIA RTX PRO 5000 Blackwell, 48935 MiB, driver 580.173.02`,
node online, node-exporter UP in Prometheus throughout. Every document said **RTX 5080,
16 GB, OFFLINE**. All three claims were wrong, and a fallback sized against 16 GB on a 48 GB
card is the node-04 error WP-24 corrected, inverted.

**Corrected by WP-48** (operational, safe to change): `dev/CLAUDE.md` §2 (+ a node-07
Temporal row, which was missing entirely), `README.md` ×3 tables,
`ivgs-api/app/api/v1/nodes.py` `NODE_TOPOLOGY`, both `prometheus.yml` copies' node-05 labels,
and `tests/test_wp24_node_honesty.py` (node-05 is measured now, so `topology_verified` is
True and only node-06 stays unverified).

**Still wrong, and NOT changed** — these are specification documents:
* `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md` — §"node-05" and the Draft-3 role
  table both read *"RTX 5080, 16 GB — ComfyUI SDXL/SD3.5 image fallback … Ollama … Unchanged."*
* `docs/ivgs_v5_functional_spec.md` — three sites (`:855`, `:951`, `:1431`).
* `ivgs-infra/docker-compose.node05.yml:7` header comment, and `tests_system/smoke/test_gpu_nodes.py`
  (`node-05 GPU smoke tests — RTX 5080 16 GB`, plus a ComfyUI/Ollama service map for services
  the node does not run).

**Scope/action:** amend AD-02 and the functional spec under change control, and decide what
node-05's role actually is — the work order says *quality-services stack*, which is neither
the AD-02 "image fallback + Ollama" role nor anything currently deployed (the node runs the
telemetry pair and nothing else; it has no `/opt/ivgs` checkout at all).

**Update 2026-08-26 (WP-44-QUALITY Task 6b): the amendment is DRAFTED and awaits review.**
`docs/IVGS_v5_Addendum_AD-02_Draft4_node05_quality_services_DRAFT.md` — a document, under
§18 change control. **No specification text has been edited**: AD-02 Draft 3 and
`docs/ivgs_v5_functional_spec.md` are untouched, deliberately. The draft proposes replacing
the node-05 bullet and the Appendix AD-B row with *the quality-services node*, carries the
measured basis (RTX PRO 5000 Blackwell 48935 MiB; the deployed CLIP scorer occupying 1040
MiB / **2.1%** of the card at 21 ms median compute), inventories the four consequential
edit sites, and leaves four questions for the reviewer — including whether the SDXL and
Ollama fallbacks survive anywhere at all, and where §11.1's unimplemented safety
classifier goes. **This item stays OPEN until the draft is reviewed and adopted**; it is
now blocked on a decision rather than on the work.

**Also now true, and new:** node-05 *does* have `/opt/ivgs/ivgs-infra` and *does* run a
service — `ivgs-clip-scorer` on :8300, from the tracked
`ivgs-infra/docker-compose.quality.node05.yml` overlay. The "runs nothing" half of the
description above is superseded.

## P2.45 — `ivgs-workers/tests/test_stage3.py`: five tests red on `main`, against a signature that no longer exists *(new, WP-44-QUALITY, 2026-08-26)*
**Status:** OPEN — a stale test module, not a product defect. **Pre-existing: verified red at
`5a9fd23` with the WP-44 working tree stashed**, i.e. before this package touched anything.

Five of the module's tests fail at collection or setup for three separate reasons, all of
them drift between the tests and a Stage 3 that has been rewritten under them:

| Symptom | Cause |
|---|---|
| `AttributeError: ... does not have the attribute '_update_scene_asset'` (×3 patch sites) | that helper does not exist in `tasks/stage3_images` and per `git log` never has |
| `AttributeError: ... does not have the attribute 'CogVideoXClient'` | the module imports `CogVideoXGenerationParams` / `CogVideoXModel`, not the client class — the provider-factory rewrite (WP-IVGS-0) moved client construction out |
| `TypeError: _process_single_scene() got an unexpected keyword argument 'flux_client'` | same rewrite: the function takes a provider, not per-engine clients |

**Why WP-44 did not fix it.** The first cause is a three-line deletion and WP-44 made it,
then reverted: the second and third need four tests rewritten against the provider-factory
signature, with mocks for a path that reaches `build_provider`. That is real work with its
own failure modes, and half-repairing a stale module leaves it broken in a *different*
shape — worse for the next person than finding it broken in the documented one. The revert
is deliberate and this entry is the record.

**What covers Stage 3 in the meantime.** WP-44 added
`ivgs-workers/tests/test_wp44_quality_gate.py::TestStage3CarriesTheRecord` — six tests
pinning the validator→result→API seam this package changed (the single `_quality_fields`
helper at all three constructors, the honesty fields on `SceneImageResult`, the submitted
record being the validator's own, submission no longer gated on `enable_clip_scoring`, and
the non-2xx logging). That is narrower than what `test_stage3.py` claims to cover.

**Scope/action:** rewrite the four `_process_single_scene` tests against the current
signature and drop the three dead patch targets. Small, self-contained, and best done by
whoever next touches Stage 3's control flow.

## P2.44 — node-04 `wp42probe`: a container left in `Created` since WP-42 *(new, WP-48-TELEMETRY, 2026-08-25)*
**Status:** OPEN — trivial, recorded so it is not rediscovered. `docker ps -a` on node-04 shows
`wp42probe  ghcr.io/brucecostello2/ivgs-workers:coqui-v5.2.7-h0  Created`. It never ran and
never will; it pins an image and clutters every container listing on the node — including,
now, the Node Monitor's log panel container picker. **Scope/action:** `docker rm wp42probe`.

**Related, and why it is not the same item:** there is **no `GET /reservations`** on the
scheduler at all — only `DELETE /reservations/{reservation_id}` — so there is no
reservation-count query to run. That is why WP-08's exit-gate clause "reservation count
returns to baseline" is unmeasurable as written. **Pairs with P2.6.**

## P2.46 — The RUN-2 residue sweep: one bounded pass, immediately after RUN-2 *(new, operator ruling 2026-08-28, added by WP-IVGS-09 Task 0(a))*

**Status:** GATED — opens the moment RUN-2 is banked; closes in one pass.

**⚖ THIS ROW EXISTS BECAUSE THE RULING REQUIRED IT.** The 2026-08-28 ruling on the
carried-v3.1 block reads: *"Rows RUN-2 exercises close-or-confirm by observation; residue gets
one bounded sweep immediately after RUN-2. Add that sweep as a row."* This is that row.

**What it sweeps.** Everything the ruling routed here, and nothing else:

| Row | Why it is here |
|---|---|
| **P2.12 – P2.31** (20 rows, contiguous) | VERIFY-AT-RUN-2. RUN-2 closes or confirms whatever it touches; this sweep takes the remainder |
| **P1.4h** | IVGS-0.6 — does an animation scene still render a still? Observation, not code reading |
| **P1.4q** | Does a failed render still strand its project non-retriggerable? |

**BOUNDED, and the bound is the point.** ⛔ **One pass. Each row gets a verdict — CLOSED with
the observation that closed it, or CONFIRMED-OPEN with what was seen — and no row is carried
forward for a second look.** A sweep that may run twice is not a sweep; it is the backlog
growing a new place to hide, which is the condition §RC-H3 was opened to end.

**Not a licence to widen.** Rows not in the table above do not join this sweep because they
happen to be nearby. If RUN-2 surfaces something new, it opens its own row.

**Depends on:** RUN-2 existing (Next item 1 on the board). **Blocks:** nothing — it is a
close-out, not a prerequisite.

## P2.47 — The scheduler's queue-depth counter is a second, unreconciled record of the queue, and five sites let it drift *(new, operator ruling 2026-08-28, opened by WP-IVGS-09 Task 0(c) after the P2.39 drain)*

**Status:** OPEN — P2. **Opened by operator ruling on the GO**, alongside P2.39's drain.

**⛔ THE EVIDENCE IS A NUMBER THAT CANNOT EXIST.** Measured on node-01, 2026-08-28, immediately
before the drain:

| | urgent | normal | batch |
|---|---:|---:|---:|
| `pq:depths` — the counter `/fleet` reports | **24** | **−2** | 0 |
| `ZCARD pq:queue:<level>` — the actual queue | **20** | **2** | 0 |

**A queue length of −2 is not a queue length.** `pq:depths` is a hash of counters maintained
*alongside* the sorted sets rather than derived from them, and **nothing in the scheduler ever
reconciles the two**.

**And the drain proved it in the open.** After removing all 22 entries — queue verifiably empty,
`ZCARD` 0/0/0 — the counter still read **`urgent: 6, normal: −2`**. It was reset to the measured
`ZCARD` by hand, under the same ruling. That reset is the only reconciliation that has ever
happened, and it was performed by a person.

### The five sites, all in `ivgs-scheduler/priority_queue.py`

**The three the ruling names:**

1. **`apply_aging` never scans `urgent`** — `:211`, `for priority_level in ["batch", "normal"]`.
   Its expired-job cleanup at `:217-220` `zrem`s an entry whose hash has gone **without**
   `hincrby`-ing the depth down — and it cannot reach an `urgent` entry at all. **So an urgent
   entry whose 72-hour job hash has expired is immortal and permanently uncounted.** Two of the
   22 drained were exactly that, submitted 2026-08-25.
2. **`resolve_priority` on an EXISTING job** — `:129-137`. It recomputes `effective_priority`
   and `hset`s it into the hash **without moving the zset entry and without touching the
   counter**. That is why two jobs sat in `pq:queue:normal` carrying
   `effective_priority=urgent` with `aging_bumps=0`.
3. **`remove_job` decrements a queue the job never joined** — `:288-292`. It `zrem`s from, and
   `hincrby`s down, `DEPTHS[effective_priority]`. After (2) the entry is in a *different* zset,
   so the `zrem` misses and the decrement lands on the wrong counter. **That is where
   `normal = −2` comes from**, and it is why those two rows needed a direct
   `zrem pq:queue:normal` in the drain rather than `remove_job`.

**Two more the drain exposed, recorded rather than left for the next package to re-find:**

4. **⛔ `get_queue_depths` HIDES the defect from the surface an operator would use to notice
   it** — `:309-313`, `max(0, int(depths.get(...)))`. `/fleet` reported `normal: 0` while the
   stored counter was `−2`. The clamp turns an impossible value into a plausible one. **A
   negative counter is information; clamping it away is the fabricated-absence rule (WP-57/60)
   inverted — reporting a plausible number about something that is broken.**
5. **⛔ PROJECT DELETION NEVER PURGES THE SCHEDULER QUEUE, AND THIS IS THE SOURCE OF THE
   ACCUMULATION.** `project_deletion.py:401-410` purges `ivgs:job_context`, `ivgs:media_tasks`,
   `ivgs:media_join_ctx`, `ivgs:media_failures` and `ivgs:media_join_seen:*` — **all in Redis
   db 0**. The priority queue lives in **db 1** (`SCHEDULER_REDIS_URL=redis://redis:6379/1`) and
   is not touched. **Twelve of the 22 entries drained had no `render_jobs` row at all**: their
   projects were deleted through the WP-59 flow and their queue entries were left behind.
   Reproduced in this package — the two test projects created for Task 2 were deleted through
   that flow and their queue entries were still present afterwards.

### Why this is P2 and not P1

Nothing is scheduled off this counter. `admission_control` and `load_balancer` read the fleet
registry, not `pq:depths`; the queue has no dequeuer at all (P2.39, and AD-05 O-3 / P2.6 own
that). **It is a reporting and hygiene defect, not a dispatch defect** — today. It becomes P1
the moment anything schedules off the depth, which is exactly what a Temporal-era admission
gate would want to do.

### Scope, and one thing NOT to do

**Do not "fix" this by making `get_queue_depths` return the `ZCARD`s.** That would make the
surface honest and leave three write paths still corrupting a value nobody reads — the
half-fix that removes the evidence. Either derive depth from the sorted sets *and delete
`pq:depths`*, so there is one record instead of two, or repair all three write paths and add
the reconciliation that has never existed. **One record is the better answer**, and it is the
same reasoning that governs every other "two definitions, free to drift" row in this register.

Site 5 is separable and is arguably the most valuable single fix: **project deletion should
purge db 1 too**, which stops the accumulation at its source regardless of what happens to the
counter.

**Gate:** none — it is ordinary work. **Re-open trigger if deferred:** any change that makes a
dispatch, admission or alerting decision from `pq:depths`.

**Related:** **P2.39** (the drain, done, operator-attended), **P2.6** / AD-05 **O-3** (the GPU
monitoring and heartbeat registry that would give the queue a dequeuer), **RC-J6**.

# DEFERRED (conscious, with re-open trigger)

## DEF.1 — Comprehensive disaster recovery *(carried, v3.1 P3.14 — **premise materially changed 2026-08-14**)*
**Deferred until:** full fleet up + AD-01 complete. **Re-examine now:** the storage leg is done. Backups run to `.7` NFS (22 TB, hard mount) and 38 GB of image artifacts have an off-node copy with six verified checksums. v4.0's statement that backups lived on node-01's disk was wrong — they were on `.9` CIFS, now retired. What genuinely still needs the full fleet is per-node compose/`.env` capture and the fleet-wide restore procedure. **A restore drill against `.7` has not yet been run for IVGS** (MBCP has run one). Design DR using non-node location(s) — local NAS + offsite — covering git repo, `/mnt/models` weights, Postgres, SeaweedFS/Redis, per-node compose + `.env`. Closes the gap where `/mnt/ivgs-shared` backups live on node-01's disk and don't survive a node-01 failure.
**Decided 2026-06-02 (recovery/image-artifact policy):** large GPU images are **not** pushed to GHCR (free-tier limits); recovery = Dockerfile-in-git + `docker save` artifact on owned storage (`scripts/save-image-artifact.sh` → `/mnt/ivgs-shared/image-artifacts/` with SHA-256 + MANIFEST) + re-acquirable weights; compose uses `pull_policy: never`. Procedure in `RECOVERY.md`.

## DEF.2 — Localisation pipeline (§17)
**Deferred until:** M8 / post-launch. `language_variants` table and state exist; no variant has been exercised end-to-end. Re-open when a second language is actually required.

## DEF.3 — PowerPoint ingestion *(new 2026-08-22 — backlog, no milestone)*
**Deferred until:** PPT input becomes a **real requirement**. **Re-open trigger:** a stated
need to ingest customer decks — not an assumption that it would be nice. Nothing is scheduled
and nothing should be built speculatively.

**Shape, recorded so the idea is not re-derived from scratch.** Ingestion is **per-slide
triage**, not bulk conversion. Each slide is classified into one of six dispositions:

| Disposition | Meaning |
|---|---|
| `REUSE` | take the slide essentially as-is |
| `RESTYLE` | keep content, regenerate to the project's visual language |
| `REBUILD` | keep intent, author the visual afresh |
| `EXTRACT` | harvest specific content (a figure, a table) and discard the rest |
| `REFERENCE_ONLY` | informs the script; never appears on screen |
| `OMIT` | drop entirely |

**Speaker notes are a separate source** from slide content, with their own path into the
pipeline — they are usually the narration intent, while the slide is usually the visual, and
collapsing the two loses exactly the distinction that makes a deck worth ingesting.

**Requires its own addendum.** This touches the Brief, the Scene Contract and the asset model
at once; it is not a work package against the current contract. **Origin:**
operator-commissioned external design review, 2026-08-22.

---

# Operator tasks (not Claude-actionable)

| Item | Notes |
|---|---|
| GPG private key off-network backup | Signing key `4F2243FAB5A25808` needs an off-node copy. Security-sensitive. |
| `.env.node01` gitignore + credential rotation | See P1.5. Operator-driven. |
| Visual QA of `final_1080p_9007b2cf.mp4` | See P1.4(a). Only the operator can judge acceptance. |
| MBCP serving token + weight-signing key handoff | Gates P2.10. |
| Provision the Temporal node | Gates WS-T.5. |
| Commit the two untracked docs | `docs/IVGS_v5_Addendum_AD-04-v3_…md` (451 lines) and `docs/MBCP_Dev_VM_Setup_verified.md` (214) exist only on node-01 — SSOT material with no version control. Scan for tokens/IP literals first. |

---

# Items closed (compressed evidence)

*Full narrative detail preserved in `OUTSTANDING_WORK_archive_v3.1.md`.*

### Closed since v3.1 (2026-06-08 → 2026-08-14)

| Item | Closed | Evidence |
|---|---|---|
| **B4 — LatentSync not production-viable → certified replacement** | 2026-07/08 | MBCP built and operating; bake-off complete; certified models serving to IVGS. *(Consumption blocked by P1.0 — the decision is closed, the plumbing is not.)* |
| **Stage 6 — talking head: BUILD REQUIRED** | 2026-06-07 | LatentSync engine built + proven on node-04 (`latentsync-v5.2.7-h0`); head renders, uploads, composites. |
| **Stage 7 — prototype draft** | 2026-06-07/08 | Draft `f78eb063`, 214.94s, 1280×720, corruption 6/6, operator-confirmed. |
| **Stage 8 — final render executes** | 2026-06-08 | `final_1080p_9007b2cf.mp4`, 215.07s, 1920×1080/30fps, AAC 48k stereo; used as evidence in the AD-04 head judgment. *(Formal validation → P1.4.)* |
| **AD-03 Pillar 1 — A/V duration + corruption** | 2026-06-08 (`v5.4.22-h0`, `4c38240`+`10b2290`) | Scene durations anchored on real audio; draft `061f64eb` 214.97s, video==audio (3.7 ms), corruption 6/6. |
| **AD-03 Pillar 2 — head per-scene desync** | 2026-06-08 (`v5.4.23-h0`, `f0b1f9a`) | Head composited once as a continuous timeline overlay; `num_layers` 3→2; draft `f78eb063` ≈5 ms A/V. |
| **ARCH-1 — Model Store + selection-aware provider factory** | 2026-07-09 | `shared/providers/{factory,binding}.py`, `app/services/model_selection.py`; stages 1/2/3/5 bound. *(Stage 6 → P1.0.)* |
| **AD-01 admin GUI — model lifecycle** | 2026-07-09 | `/admin/models`: candidate → approve (attestation) → set-default (transactional per-(stage,tier)) → deprecate (auto-clears default) → retire. GUI-only. |
| **MBCP ↔ IVGS connected mode** | 2026-07-09 | AD-01 seam receiver `/ad01/v1` + `X-Service-Token`; node self-registration + 30s availability poller; migration 0027 (`ffmpeg` enum) + `ExportBundle.engine`. |
| **MBCP certification backfill** | 2026-07-09 | 21 exports + 2 composition transmitted; all non-revoked certs landed as CANDIDATEs; 24 revoked correctly skipped. |
| **MBCP "Export to IVGS" button** | 2026-07-12 | `docs/MBCP_Delivery_20260712_ExportButton_WSTEST.md`. *(Handoff register #1.)* |
| **P1.5 (old) — `.env.node01` secret hygiene** | 2026-08-14 (`e1f4c58`) | `git rm --cached` + gitignored. Token verified never committed (single added line, no removal; last commit to the file `fa6f4db`, May). File remains on disk. |
| **P0.2 — 75-day database backup gap** | 2026-08-14 | Six root causes: host cron used `POSTGRES_HOST=localhost` against a containerised Postgres (exit 4 daily); `/var/run/ivgs` root-owned so the container path failed on the lock file; `set -euo pipefail` aborted before the rsync check; checksum files recorded the staging path; `.9` was 100% full; Proxmox was OOM-killing the VM. Backup verified: `a4cee889…`, decrypts to 38 `CREATE TABLE`, 12,673 rows. |
| **Storage migration `.9` → `.7`** | 2026-08-14 | 100 GB copied and verified by dry-run rsync; fstab updated to NFS4.2 `hard`; all four backup types (db/assets/config/wal) writing to `.7`. Asset backup 47.7 GB — first since 20 July. `.9` retired, retained as fallback. |
| **Image artifacts off node-01** | 2026-08-14 | 38 GB to `/mnt/store/ivgs-archive`, six checksums verified against the copies. First off-node copy; these are the only reliable recovery route for the Blackwell engine images. |
| **Proxmox host OOM-killing VMs** | 2026-08-14 | Host `n5Pro`, 61 GB, swap fully consumed; killed VM 102 twice during NFS transfers. node-01 reduced 31 GB → 16 GB; 32 GB swap file added. Guest logs were clean because the kills came from outside. |
| **`.61` reference sweep** | 2026-08-14 | Zero references in repo, env files, fstab, mounts, systemd, hosts, cron or container environments. The `.61` NAS does not exist; the retired share was `//192.168.1.9/elearning` over CIFS. |
| **P2.34 — Stage-6 upload-URL pre-check** | verified 2026-08-14 | `talking_head_task.py:155` posts to the correct `…/projects/{id}/assets/upload`. *(The wrong URL survives only in the dead duplicate → P2.3.)* |
| Light/dark theming; login crash fixes; JWT username claim; celery-beat pidfile; AD-02 Draft-3 topology in `nodes.py`; Tier-0 harness; backup-test closeout | 2026-07-09 | Per `SESSION_HANDOFF_2026-07-09.md` §1. |

### Closed in v3.1 and earlier (one line each)

| Item | Closed | Evidence |
|---|---|---|
| A1 — image-generation regression | 2026-06-05 (`d3d1fb4`) | Not a code regression; latent `IVGS_*` env-name mismatch sprung by `--force-recreate`. Cure = canonical names in tracked compose. |
| A2 — node-04 vLLM model name de-band-aided | 2026-06-05 (`d3d1fb4`) | `IVGS_VLLM_MIDSIZE_MODEL=mistral-24b` in tracked compose. |
| A4 — scene-asset linkage (`scene_id` NULL) | 2026-06-05 (`a914352`) | Worker-side root cause; `_upload_to_seaweedfs` omitted `scene_id`. |
| Stage 3 — media generation e2e | 2026-06-05/06 | FLUX 4/4 images+animation; CogVideoX 2/2 videos, ~26 GB peak on the 48 GB card. |
| Stage 4 — composition manifest e2e | 2026-06-05 (`a91cdce`) | Server-side build; manifest `b636fe87` locked, scene_count 6. |
| Stage 4 — media-join failure decrement | 2026-06-05 (`35d9226`) | Failure path decrements + advances with `failed_count`. *(Superseded by P1.1.)* |
| Stage 4 — media-join crash watchdog | 2026-06-05 (`0bde15e`) | Beat `media_join_watchdog` (5 min). *(Compensating code — deleted under WS-T.)* |
| Stage 5 — TTS/voiceover e2e | 2026-06-06 (7 fixes) | Run `3cb8c4d6`: 6/6 scenes, 48 kHz/24-bit, SNR 60 dB, all scene-linked. |
| Storyboard prompt truncation | 2026-06-04 (`a9b2e47`) | Truncated Jinja templates at v5.0.0; reconstructed + baked. |
| AD-02 node specialization implemented | 2026-06-04 | node-02 LLM-only, node-03 video-only, node-04 image+TTS; Stage-3 conformance PASS. *(Governance → P1.9.)* |
| `MEDIA_GENERATION` park (functional half of v1→v2) | 2026-06-05 (`9f692ab`) | 6 call-site repoints + 3 advances + 4 map fixes. *(Cleanup half → P2.3.)* |
| node-03↔04 GPU swap + Stages 1–5 re-validation | 2026-06-06 | node-04 = 96 GB RTX PRO 6000; node-03 = 48 GB RTX PRO 5000. |
| Make Main Honest — merged to `main` | 2026-06-06 (`5657f95`) | 70 commits `--ff-only`; tag `stages-1-5-green-2026-06-06`. |
| API `/ivgs` crash (rollback storage) | 2026-06-05 (`c3e8a1a`) | Repointed to `/mnt/ivgs-shared/rollback_points`. *(Full wiring → P2.16.)* |
| Profile-gating of AD-02 standby services | 2026-06-05 (`68ac33b`) | `profiles: ["standby"]` prevents accidental resurrection. |
| P1.5 — API never dispatches the orchestrator | 2026-06-01 | `trigger_pipeline` → `dispatch_pipeline`; broker options aligned. |
| P2.2 — config externalization (2a–2h) | 2026-05-29/30 | Node IPs single-sourced; `10.10.0.x` eliminated + guarded. |
| P2.12 — Nginx dynamic-resolution hardening | 2026-05-29 (`7173797`) | resolver + variable `proxy_pass` (7 sites) + http2. |
| P2.14 — pre-commit guard for `10.10.0.x` | 2026-05-30 (`e5816d8`) | Hook + `test_no_hardcoded_ips.py`. |
| P2.23 — workers image broken HEALTHCHECK | H.0 (`d349c46`) | Module `worker` → `celery_app`. |
| Phase H.0 — Make Main Honest (code surgery) | 2026-05-31 (`d349c46`) | Provider refactor repaired; all 8 stages wired; 22-task registration green. |
| Defect #8 — test suite restoration | PR #48 (`a836668`) | 512 tests passing; 28 bugs fixed. |
| Phase 14 backup (Stream A + B) | PR #49 | NAS/GPG/pushgateway/WAL/cron + `ivgs-backup-worker`. |
| Engine images (ComfyUI/Coqui/Kokoro/WhisperX) | 2026-06-02+ | Blackwell cu128/sm_120; deployed + healthy on node-04. |
| NFS bulk-transfer wedge | 2026-06-03 | Root cause = inter-switch path, not NIC offload. |
| Node Configuration admin GUI; P1.4 backup-worker GHCR push; P2.9 compose `version:`; Stage-0/2 bring-up; node-02/03/04 de-conflict | May–June | See archive. |

---

# Renumbering map (v3.1 → v4.0)

*Nothing was dropped. Every v3.1 / Addendum ID resolves here.*

| Old | New | Old | New |
|---|---|---|---|
| P1.1 | P1.6 | P2.27 | P2.4 *(405 → P1.2)* |
| P1.2 | P1.7 | P2.28 | P2.5 |
| P1.3 | P1.8 | P2.29 | P2.6 |
| P1.6 | P1.9 | P2.30 | P2.12 |
| P1.7 | P1.5 *(severity revised)* | P2.31 | P2.13 |
| P2.1 | P2.26 | P2.32 + B1 | P2.14 *(merged)* |
| P2.3 | P2.21 | P2.33 | P2.15 |
| P2.4 | P2.22 | P2.34 | **CLOSED** |
| P2.5 | **CLOSED** *(fixed in PR #48 sweep)* | P2.35 | P2.16 |
| P2.6 | P2.24 | P2.36 | P2.17 |
| P2.7 | P2.23 | P2.37 | P2.18 |
| P2.8, P2.10, P2.15, P2.22 | P2.30 *(merged)* | P3.1–P3.2 | P3.1–P3.2 |
| P2.11 | P2.11 | P3.3 | **WS-T.7** |
| P2.13 | P2.25 | P3.4 | P3.3 |
| P2.17 | P2.31 | P3.5 | P3.4 |
| P2.18 + P2.21 | P2.28 *(merged)* | P3.6 | P3.5 |
| P2.19 + P2.25 | P2.29 *(merged)* | P3.7 | P3.6 |
| P2.20 | P3.14 | P3.8–P3.13 | P3.7–P3.12 |
| P2.24 | P2.27 | P3.14 | **DEF.1** |
| P2.26 | P2.3 | B2 | P2.19 |
| Stage-6 BUILD REQUIRED | **CLOSED** | B3 | P2.20 |
| B4 | **CLOSED** | B5 | **P1.0** *(reframed)* |
| Handoff #1 | **CLOSED** | Handoff #2 | P2.7 |
| Handoff #3 | P1.5, P3.6, P3.15, P3.16 | Handoff #4 | **WS-T.7** |
| Handoff #5 | P2.10 | Handoff #6 | P3.17 |

---

# Source documents

| Path | Notes |
|---|---|
| `OUTSTANDING_WORK_archive_v3.1.md` | Full closure narrative preserved from v3.1 + Addenda A/B. |
| `SESSION_HANDOFF_2026-07-09.md` | Live-state snapshot; register folded in above. |
| `IVGS_v5_Master_Sequence_Plan_to_Production.md` | Milestone map — **needs v0.4 to absorb WS-T + the corrected stage status.** |
| `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` | Model lifecycle; the consumer of certifications. |
| `docs/IVGS_v5_Addendum_AD-02_Node_Specialization_Draft3.md` | Authoritative topology; node-06 Intel→CUDA. |
| `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` | Pillars 1–3; frame-aligned splitting. |
| `docs/IVGS_v5_Addendum_AD-04-v3_…md` | MBCP design spec — **untracked on node-01; commit it.** |
| `ivgs_v5_functional_spec.md` | §1.4 SSOT — **§2.1/§6.2/§6.4 need amendment under WS-T.4.** |
| `MBCP_RuntimeClass_Refactor_TaskA_Audit.md` | MBCP adapter audit; drives P2.8/P2.9. |
| `/mnt/transcripts/*.txt` + `journal.txt` | Primary historical record. |

---

# Update protocol

1. Every closure records evidence: commit SHA, image tag, `file:line`, or transcript pointer.
2. New deferrals require a `DEF.n` entry with a stated re-open trigger. Nothing is parked silently.
3. Re-snapshot the counts table at every session close.
4. **Verify against committed code, not summaries** — this document is a map, the repo is the territory.
5. When WS-T lands, retire P2.1/P2.2/P2.3 and the P0.1/P1.1–P1.2 entries together, in one arc, with the reference-output diff as evidence.

*Rebuilt 2026-08-14 against `e613e844` (node-01 == origin/main). Next: Master Plan v0.4, then AD-05.*

---
---

# RECONCILIATION — 2026-08-28 (WP-IVGS-08)

**Why this section exists.** A transcript-wide debt audit found that this document
had gone stale: its last dated entry was **2026-08-23**, while WP-IVGS-03 through
WP-IVGS-07 shipped between the 27th and 28th and recorded their findings as **prose in
reports** instead of **rows here**. That is the drift this document's own rules exist to
prevent — *"Fix, don't park; nothing is deferred without an entry; DEFERRED means a stated
reason AND a re-open trigger."*

⚠ **This section is APPENDED, not merged into the P0–P3 numbering above.** Renumbering a
1,846-line register mid-audit would break every inbound citation in the report archive. New
rows carry `RC-` ids and name the priority they would hold.

⛔ **SCOPE OF VERIFICATION — read before trusting a row.** Task 1(b) asked for every existing
row to be verified live. **I did not do that.** ~60 rows across P0–P3 exist above; I verified
the four named in Task 1(e) plus the rows this package touched. **Every other pre-existing row
is UNVERIFIED by this pass and retains whatever status it already had.** Stating that plainly
is worth more than a sweep I did not perform.

---

## RC-A — Closed by this package, with evidence

| id | Row | Evidence |
|---|---|---|
| **RC-A1** | Fallback subsystem was dead design with a deliberate tripwire | **DELETED.** `services/fallback_chain.py` + its 9 tests. Verified before deleting: only its own module and test referenced `FallbackChainService`. ⚠ The live `fallback_policies` table (4 rows) and its API-side ORM model are a **different thing** and were not touched. Commit `6a817d7` |
| **RC-A2** | **P2.60** — five `ivgs_api.app.models` imports from inside `ivgs-workers` | **CLOSED.** One died with `fallback_chain.py`; the other four already resolve to `shared.models.*` and were verified importable **inside the running container** (WP-54's own method): `DeadLetterMessage`, `Asset`, `TaskRetry` all OK |
| **RC-A3** | `get_beat_schedule()` dead code | **REMOVED**, zero callers. Its regression test is **inverted, not deleted** — a second copy of the schedule cannot drift out of a function that does not exist |
| **RC-A4** | Backup worker's hardcoded DSN fallback | **REMOVED** from `celery_app.py` and `tasks/backup_tasks.py`; the worker now refuses at import with a named error. Proven both ways. ⛔ **See RC-C1 — this was a live credential, not just a default** |
| **RC-A5** | Build identity: image unidentifiable from inside | **CLOSED.** `ARG/ENV/LABEL IVGS_BUILD_REF/SHA` in all four Dockerfiles; `/api/v1/version` reports `v5.31.0-hygiene` / `6a817d7` **through the ingress**; `/health` no longer reports the literal `5.0.0` |
| **RC-A6** | ⛔ Ingress `/health` false green on the control plane | **CLOSED.** Two `location = /health { return 200 }` stubs replaced with a proxy to the API. **Proven: API stopped → 502 (was 200); API up → 200.** An honest `/nginx-alive` keeps the process check under a name that asserts only what it checks |
| **RC-A7** | `IVGS_API_TAG` stale wherever set | **CLOSED by deletion.** The four `IVGS_*_TAG` lines are **removed** from `.env.node01`, not corrected — they are the liar `dev/CLAUDE.md` §6 documents. Nothing reads them; the compose-level `.env` selects the image |
| **RC-A8** | **P2.11** — `ivgs-scheduler` runs `:latest`, unpinned | **CLOSED, and its origin identified.** The scheduler has been pinned since WP-IVGS-06; the *belief* came from `.env.node01`'s injected `IVGS_SCHEDULER_TAG=latest`, deleted in RC-A7. Now `v5.31.0-hygiene`, verified by opening the image |
| **RC-A9** | `dynamically_loadable` defaulted to an unconditional `true` | **CLOSED.** Set explicitly at ingest from the engine class; migration **0043** drops the server default; 2 rows corrected. See RC-B1 for the class-boundary correction |
| **RC-A10** | **D-13** — node-01's worker identified by container id | **CLOSED.** `IVGS_NODE_NAME=node-01` set; worker verified reporting `node-01` after redeploy |
| **RC-A11** | backup-worker on a v5.1.x-era image | **CLOSED.** Now `v5.31.0-hygiene`; backup window checked before the recreate (10:41 UTC vs 02:00/05:00 schedules); image asserted after |
| **RC-A12** | **P2.45** — `test_stage3.py` five tests red against a dead signature | **CLOSED.** Measured this pass: **8 passed, 0 failed** |
| **RC-A13** | `.env.*.bak-*` litter from deploy loops | **CLOSED.** **212 → 4** (newest retained per node), across nodes 01–04 |

---

## RC-B — Corrections to premises, recorded because they change what is true

| id | Finding |
|---|---|
| **RC-B1** | ⛔ **The `dynamically_loadable` fixed-class list was wrong about Ollama**, and the order asked for it to be checked rather than assumed. **AD-01 §91 and §211 both put Ollama in the LOADABLE class** — *"ComfyUI checkpoints and Ollama models can be loaded/unloaded on demand, but vLLM serves a fixed model per process"*. Only vLLM is named fixed. ⚠ **The TTS engines (`coqui`, `kokoro`, `tts`) are in the fixed set on MEASUREMENT, not on AD-01's prose**: both servers build their model inside `load()` at container start from an env var, which is AD-08 §5's reasoning applied to engines AD-01's sentence predates. **If an operator disagrees with extending the class that way, this is the row to argue with.** |
| **RC-B2** | ⛔ **Task 7(a)'s premise does not hold: the MBCP ingest token was never committed.** `git log -S "IVGS_MBCP_INGEST_TOKEN" --all -- ivgs-infra/.env.node01` returns **nothing**; the key appears in history only in `.gitignore`, `.env.node05.example` and reports. The file was untracked at `e1f4c58` and is ignored at `.gitignore:130`, exactly as `dev/CLAUDE.md` §3 records. **The rotation was NOT performed** — see RC-C2 |
| **RC-B3** | **`ivgs-workers` baseline moved DOWN deliberately: 933 → 930**, from Task 2(a)'s deletion. Collection confirms it exactly: **1018 → 1009**. ⚠ **An arithmetic gap of six is unresolved and logged rather than smoothed** — see `TEST-BASELINE_2026-08-25.md` |

---

## RC-C — NEW, opened by this package

| id | Pri | Row | Gate / owner |
|---|---|---|---|
| **RC-C1** | **P1** | ⛔ **The Postgres password was in TRACKED source** — `ivgs-backup-worker/celery_app.py` and `tasks/backup_tasks.py`, as `os.environ.get` defaults. The code is fixed (RC-A4) but **the value remains in git history and is live until rotated.** A rotation is high-blast-radius (every service DSN) and was **not** attempted unilaterally | **Gate: operator ruling on a Postgres credential rotation.** Owner OPERATOR. Re-open trigger: none needed — this is open until rotated |
| **RC-C2** | — | **CLOSED — NOT A DEFECT. Premise false.** The MBCP ingest token was **never tracked**: `git log -S "IVGS_MBCP_INGEST_TOKEN" --all -- ivgs-infra/.env.node01` returns nothing, and the file was untracked at `e1f4c58`. **Source of the false premise: the operator's July register.** Rotation was declined because it would have been an outage (MBCP's sender on `.51` fails until updated) to remediate a non-exposure. **Operator ruling 2026-08-28: measurement wins; declining was correct.** ⛔ **MBCP needs no token install** — the Task 7(a) amendment's staged-handoff row is withdrawn and deleted | Closed, no gate |
| **RC-C3** | **P3** | The unattended-upgrades / kernel driver-hold mitigation could not be confirmed: `apt-mark showhold` returns **empty** on node-01 | **Gate: none set.** Needs a measurement pass; UNVERIFIED, not closed |

---

## RC-D — Register-only rows (added, NOT executed, per Task 1(c))

| id | Pri | Row | Gate | Owner |
|---|---|---|---|---|
| **RC-D1** | **P1** | MBCP security: shared weight-service token unscoped; signing key never rotated since 2026-06-18 | **BEFORE FIRST PRODUCTION CONTENT RENDER** — token scoping + one rotation rehearsal | MBCP |
| **RC-D2** | P2 | MBCP Slice 7: LatentSync-vs-Wan2.2 side-by-side results never pasted | Paste at next MBCP session **or formally drop** | MBCP |
| **RC-D3** | P2 | MagiHuman `actors.engine_bindings`: operator knowledge **not yet recorded** | Before MagiHuman certification (WO-MBCP-03) | **OPERATOR** |
| **RC-D4** | P2 | AD-09 open questions 3–6: voice-identity metric, reproducibility policy, portrait engines, font provisioning | AD-09 item 6 | — |
| **RC-D5** | P3 | Preset drift — **UNRULED by ruling** | Re-open trigger: **AD-09 item 5 landing** | — |
| **RC-D6** | P2 | CHAOS-1 two-project de-risk run | **Post-M3.3; precondition for concurrency** | — |
| **RC-D7** | P2 | node-06 AD-02 Draft 3 compose rewrite (Intel → CUDA) | A-4 motion-renderer decision | **OPERATOR** |
| **RC-D8** | P2 | `ModelEngine` family-shaped values cleanup (§7.1): `coqui`, `kokoro`, `animatediff`, `sadtalker` are family names, not engines | **AD-10 step I reconciliation** | — |
| **RC-D9** | P2 | MBCP `serving-authoring-loop-1` unhealthy (pre-existing) | Next MBCP session | MBCP |
| **RC-D10** | P2 | MBCP "Export to IVGS" per-cert button — superseded by the `pending_exports` drain? | ⚠ **SCHEDULED, not closed.** See RC-E | MBCP |
| **RC-D11** | P2 | **O-3** fatal-reservation flip re-evaluation (WP-41 D-1) | **M3.3** | — |

---

## RC-E — The "Export to IVGS" button question

Answered from `/opt/MBCP`'s fetched `origin/main` refs only — **the working tree was not
checked out and `.51` was not touched**, per `dev/CLAUDE.md` §11.

⚠ **Code reading did not settle it**, so per the amendment this row is **SCHEDULED for the next
MBCP session, not closed**. What is known: `mbcp_worker/export_drain.py` exists on `origin/main`
and `pending_exports` carries `attempts` / `transmitted` columns (migration `0029_pending_export_retry`),
which is a drain shape. Whether the per-certificate button still exists as a separate path, and
whether it writes to the same queue, was not established. **RC-D10 carries it.**

---

## RC-F — THE M3.3 GATE TABLE

**This is what makes "gated on M3.3" a checklist instead of folklore.** Every row is a
frozen-stage-body edit or an M3.3-scheduled decision. Rows marked ✅ carry the exact edit; rows
marked ⚠ state the measurement M3.3 needs **first**.

### F.1 — Fail-open enforcement (D-12). Exact edits, all eight sites.

`GpuReservationRefused` is **already shipped** in `utils/gpu_utils.py`, deliberately unraised, so
each site is a one-line insert plus one import per file.

**Insert immediately above the existing `except`:**
```python
except GpuReservationRefused:
    raise
```

| # | File | Line | Current text | Status |
|---|---|---|---|---|
| 1 | `ivgs-workers/tasks/stage1_transcript.py` | 536 | `except Exception as gpu_err:` | ✅ |
| 2 | `ivgs-workers/tasks/stage2_storyboard.py` | 592 | `except Exception as gpu_err:` | ✅ |
| 3 | `ivgs-workers/tasks/stage3_images.py` | 699 | `except Exception as gpu_err:` | ✅ |
| 4 | `ivgs-workers/tasks/stage5_voiceover.py` | 637 | `except Exception as gpu_err:` | ✅ |
| 5 | `ivgs-workers/tasks/animation_generation_task.py` | 734 | `except Exception as e:` | ✅ |
| 6 | `ivgs-workers/tasks/video_generation_task.py` | 597 | `except Exception as e:` | ✅ |
| 7 | `ivgs-workers/tasks/talking_head_task.py` | 528 | `except Exception as e:` (latentsync leg) | ✅ |
| 8 | `ivgs-workers/tasks/talking_head_task.py` | 811 | `except Exception as e:` (sadtalker leg) | ✅ |

⚠ **Line numbers are as of `a10fddd` and WILL drift. Anchor on the `except` immediately
following each `acquire_gpu_reservation(` call, never on the number.**
**Closure:** `IVGS_GPU_RESERVATION_FAILURE_POLICY=refuse` makes a stage fail rather than proceed,
proven red-green.

### F.2 — Other M3.3-gated rows

| id | Row | Exact edit, or the measurement needed first |
|---|---|---|
| **F2.1** | **`video_generation_task` `get_binding` wiring** — the inert video selection (WP-67's top item) | ⚠ **Measurement first.** The stage must resolve its model through `get_binding` like stages 1/2/3/5 do rather than hardcoding. M3.3 needs: which model row video generation *should* bind to, and whether `cogvideox` vs `wan21` is a selection or a node fact |
| **F2.2** | **stage5 `speaker_wav` declaration removal** (D-6 residue) | ✅ **Exact:** delete `speaker_wav_data` at `stage5_voiceover.py:100` and its use at `:369`. Nothing supplies it (measured: zero assignments tree-wide). The client-side transport gap is already closed, so this is pure surface removal |
| **F2.3** | **P2.65** per-medium prompt writers | ⚠ Measurement first: which media types diverge enough to need their own writer |
| **F2.4** | **P2.66** `learning_outcomes` real hand-off | ⚠ Measurement first: what consumes it today vs what should |
| **F2.5** | **storyboard/transcript move to Qwen** | ⚠ **Blocked by design, not effort.** `dev/CLAUDE.md` §7 freezes both on Llama until after M3.3 so the Temporal conformance baseline is not re-scored against a different model mid-diff. The edit is `_STAGE_ENGINE_ENDPOINTS` in `binding.py`; the gate is M3.3 completion |
| **F2.6** | **WP62-L7** deterministic arithmetic checker | ⚠ Measurement first. Related: `reference-run-2026-08-23` teaches `10x3=30, 10x2=20 ⇒ "320"` written as 230, and **no pipeline stage can catch it** — every quality gate measures output-against-input |
| **F2.7** | **reference-run regeneration** | ⚠ **Do NOT regenerate before M3.3** (`dev/CLAUDE.md` §7). Gate: M3.3 complete AND F2.6 landed, so the regenerated run is checked by something |
| **F2.8** | **O-3** — flip GPU reservation failure from fail-open to fatal | ⚠ Depends on F.1 landing first (a refusal cannot stick while the catches are bare) **and** on the registry being non-empty. Same row as RC-D11 |


---

## RC-G — Second pass (completion order, 2026-08-28)

### G.1 Closed with evidence

| id | Row | Evidence |
|---|---|---|
| **RC-G1** | **P0.1** — `broker_visibility_timeout` below two tasks' hard time limits → duplicate GPU execution. **The register's last P0.** | ✅ **CLOSED.** Measured live in the running worker: `broker_visibility_timeout = 7200`, against `time_limit=3900` on `animation_generation_task.py:664` and `video_generation_task.py:545`. **7200 > 3900** — the duplicate-execution window the row describes is gone |
| **RC-G2** | **P1.3** — three `release_gpu_reservation(reservation, config)` two-argument calls that raise `TypeError` | ✅ **CLOSED.** All three sites now carry only a WP-08 comment recording the old call; no two-arg invocation remains in the tree |
| **RC-G3** | Task 5 — the service layer did not audit what it wrote | ✅ **CLOSED.** The audit moved to `manual_override` (the one function that performs an operator-intent selection write), so the preset path can no longer bypass it. The route's duplicate was removed — one writer, one definition. 4 tests |
| **RC-G4** | **RC-C1** — Postgres password in tracked source | ✅ **CLOSED as rotated-and-dead.** See RC-G8 |

### G.2 New, opened by the second pass

| id | Pri | Row | Gate / owner |
|---|---|---|---|
| **RC-G5** | — | ⛔ **WITHDRAWN — I WAS WRONG.** I reported project deletion as "audited nowhere". **It is audited.** `services/project_deletion.py:952` writes `INSERT INTO audit_log` in **raw SQL**, and commits it BEFORE destruction precisely so the row outlives the project (`audit_log` has no FK to `projects`, verified in that module against the live schema). Live proof: **16 `PROJECT_DELETE_COMPLETED` rows**. My sweep grepped for the `AuditLog` ORM symbol and missed every raw-SQL writer. **Caught by the operator requiring this be verified before the row was written** | Withdrawn, no gate |
| **RC-G6** | **P2** | **Service-layer audit parity sweep — project deletion path first.** Corrected count after re-running the sweep across BOTH mechanisms (ORM `AuditLog` and raw `INSERT INTO audit_log`): **4 of 20 service modules audit** — `adaptation_service`, `gate_service`, `model_selection` (added by this package) and `project_deletion`. **16 do not.** ⚠ Not all should: asset/checkpoint/DLQ writes are operational, not operator-intent. The scope is a parity sweep that decides, per module, which class each write belongs to. ⓘ **The gap this names is `audit_log` coverage, not the deletion record** — the deletion record exists and works | **BEFORE FIRST PRODUCTION CONTENT RENDER** (same gate as RC-D1) | **IVGS** |
| **RC-G7** | **P2** | ⛔ **50 of the register's 71 open rows carry no gate, owner, or re-open trigger**, violating this document's own DEFERRED definition. 76 rows total, 5 marked closed in place | **Gate: the next register pass.** This is the structural finding of Task 1(b) |
| **RC-G8** | — | **Postgres credential rotated 2026-08-28**, attended. ⚠ **The old value remains in git history and is dead because rotated**, not because history was cleaned — history rewrite was out of scope and is not proposed | **CLOSED** |

### G.3 Register-only additions (operator addendum, execute nothing)

| id | Pri | Row | Gate | Owner |
|---|---|---|---|---|
| **RC-G9** | **P1** | ⛔ **`magihuman` / `humo` / `wan22_s2v` engine values are INFERRED, never read.** WP-IVGS-03 derived them from MBCP's `engine == adapter_key` convention and recorded them as *not verified*. One read-only query on `.51` settles it: `select name, engine from models where name in ('davinci-magihuman','humo-17B')` | **BEFORE those models are certified** — a wrong guess is a second 422 and a second migration | **OPERATOR**, next MBCP session, **step 0, before WO-MBCP-01** |
| **RC-G10** | **P1** | **AD-10 §7.2 mirror-rule amendment**, promised by the MBCP orchestrator and never received or ratified: *"no field with an enumerated domain without a mechanism keeping both sides in step; no MBCP adapter without its engine value landing in IVGS first."* ⓘ This is the rule whose absence produced WP-IVGS-03 and WP-IVGS-04 in the first place | **Before the next MBCP adapter is added** | MBCP session |
| **RC-G11** | — | **Cross-reference: WP-IVGS-03 §5.4's intent is CLOSED by WP-IVGS-08 Task 3.** §5.4 wanted version identity and declined to build it because nothing in the image knew its own build. Evidence now: `GET /api/v1/version` through the ingress returns `{"build_ref":"v5.31.0-hygiene","commit_sha":"914277c"}`, and all four version sources agree | Closed — see RC-G12 for the residue |
| **RC-G12** | P2 | The residue of the above: **`ExportBundleIn`'s `extra` policy on the DEPLOYED build was "undetermined"** in WP-IVGS-03 solely because the build was unidentifiable. It is now identifiable, so the row is **verifiable and must be verified** rather than carried | **Gate: next package.** Method: read `model_config` from the running image at a known build ref |


---

## RC-H — Gate assignment pass (2026-08-28)

Task 1(b) found **50 of 71 open rows with no gate, owner or re-open trigger**. This pass
assigns one **only where the row itself supplies it**. ⛔ **No gate here was invented to shorten
the list** — the residue is §RC-H3 and the operator rules it.

### H.1 Closed by this package's evidence

| Row | Evidence |
|---|---|
| **P0.1** — `broker_visibility_timeout` below two tasks' hard time limits → duplicate GPU execution | ✅ **CLOSED. THE REGISTER'S LAST P0.** Measured in the running worker 2026-08-28: `WorkerConfig().broker_visibility_timeout` = **7200**, against `time_limit=3900` on `animation_generation_task.py:664` and `video_generation_task.py:545`. **7200 > 3900 by 3300 s.** The row was written when the value was 3600, i.e. *below* both limits — a task could exceed the visibility timeout and be redelivered while still running. What changed: the timeout was raised to 7200. The window the row describes cannot occur at these values. ⚠ **It re-opens if either number moves**: re-open trigger = any change to `broker_visibility_timeout` or to a task `time_limit` |
| **P1.3** — 3 `release_gpu_reservation(reservation, config)` calls raising `TypeError` | ✅ **CLOSED.** No two-argument invocation remains; all three sites carry only a WP-08 comment recording the old call |
| **P2.11** — `IVGS_SCHEDULER_TAG=latest`, pin it | ✅ **CLOSED**, and its origin found: the belief came from `.env.node01`'s injected variable, deleted in RC-A7. Scheduler pinned at `v5.31.0-hygiene` |
| **P2.40** — five of node-01's Prometheus targets DOWN | ✅ **CLOSED. 14/14 targets up, zero red.** Count was 4, not 5. Two node-01 exporters were declared but never started — `redis-exporter`/`postgres-exporter` referenced network `ivgs_default`, which does not exist (`network ivgs_default declared as external, but could not be found`), and dual-attachment left them unresolvable by name. Fixed to `ivgs-net` alone, scrape targets repointed to container-DNS. **node-06's two targets REMOVED with a reason** — node-06 is operator-managed and out of bounds, so those rows could never go green from here |
| **P2.29** — compose reconciliation, *"monitoring net"* | ⚠ **PARTIAL.** The monitoring-net half is fixed (above). The `base.yml` vs `node01.yml` half is untouched — stays open |

### H.2 Gated where the row itself supplies the gate

| Row | Gate | Owner |
|---|---|---|
| **P1.4g** — consume MBCP's operating envelope and deployment spec | Next MBCP session | MBCP |
| **P2.7** — MBCP `serving-authoring-loop-1` unhealthy | Next MBCP session | MBCP |
| **P1.2** — checkpoint `stage_order` mismatch; resume computes the wrong stage | **M3.3** — it is an orchestration-migration item and belongs in RC-F | — |
| **P2.4** — residual 4xx cluster (checkpoint line item promoted out) | **M3.3**, with P1.2 | — |

### H.3 ✅ RULED — the residue, and where each row went

⚖ **RULED IN FULL, 2026-08-28.** This section listed **41 rows with no derivable gate** and
asked the operator one question each. **Every one is answered.** The rulings are recorded on
the rows themselves — each carries a `⚖ RULING (operator ruling 2026-08-28)` block — and are
summarised here so the section reads as a settled record rather than an open question.

**Nothing was invented to shorten the list.** Where a ruling closes a row it names the
evidence; where it archives one it says why archive is the right shelf; where it gates one it
names the gate.

| Row(s) | Ruling | Where it now lives |
|---|---|---|
| **P1.0a** | **CLOSED** — superseded by AD-01 selection | one cross-check line on **M3.3-R3**: no hardcoded SadTalker fallback survives stage-6 activity realization |
| **P1.0b** | **CLOSED** — WP-IVGS-08 Task 8 proved **nine consumers connect; the engines are not consumers** | — |
| **P1.4** | **ARCHIVED** — superseded by **AD-03 §10** | AD-03 §10 |
| **P1.4f** | **ARCHIVED** — record-only *is* archive | — |
| **P1.4h** | joins the RUN-2 sweep | **P2.46** |
| **P1.4n** | probed in **WP-IVGS-09 Task 0(b)** — resolves-or-named-refusal, evidence on the row | ruled on the evidence |
| **P1.4q** | joins the RUN-2 sweep | **P2.46** |
| **P1.4r** | folds into the frontend rebuild | **WP-IVGS-09 Task 3** |
| **P1.5a** | **CLOSED** — stale; `dev/CLAUDE.md` §8 records the fix and the two-way gate | — |
| **P1.5b** | **CLOSED** on the Task 0(b) grep + live-Prometheus evidence | `alert_rules.yml:190`, loaded and healthy |
| **P1.6** | **ACCEPTED as `String` → ARCHIVED**; validation lives in code | ⚠ this also unblocks **P1.7** |
| **P1.7** | **GATED** — *"before first production content render"* | — |
| **P2.1** | the lost *"decided"* text was **found and restored** by Task 0(b): the decision is **DELETE at AD-05 migration step 8** | gated on **AD-05 step 8** (post-cutover) |
| **P2.2** | **ARCHIVED** as observation; the target is set by **M3.3-R3** | M3.3-R3 |
| **P2.5** | joins **RC-F / M3.3** | §RC-F |
| **P2.10** | **GATED** — MBCP session steps 1–3, **then** WP-65 §8 Block A | — |
| **P2.12 – P2.31** (**20 rows, contiguous**) | **VERIFY-AT-RUN-2** — RUN-2 exercises them; observation closes or confirms each | residue → **P2.46** |
| **P2.35** | **DROPPED** — zero named consumer | — |
| **P2.37** | **CLOSED** — settled by AD-03 §10 | — |
| **P2.38** | reclassified **FIX** — wire `output_fps` or answer **400**; silently accepting is ruled out | post-RUN-2 batch |
| **P2.39** | **OPERATOR-ATTENDED** — listed, then drained on an explicit GO | **WP-IVGS-09 Task 0(c)** |

#### ⚠ The count this section carried was wrong, and the ruling exposed it

§RC-H3 said *"P2.12–P2.31 is 20 of the 41"* while its grouped entry enumerated
`P2.12–P2.14, P2.16–P2.28, P2.30, P2.31` — which is **18**. **P2.15** and **P2.29** were
inside the stated range and outside the enumeration. The ruling is on the **contiguous
range**, so both are included, the block is genuinely 20, and the count reconciles.

**P2.29 is a partial**: §H.1 closed its monitoring-net half and left the
`base.yml` vs `node01.yml` half open. VERIFY-AT-RUN-2 applies to the open half only.


## RC-I — M3.3 runway, A-4 ruling, and fleet facts (2026-08-28)

### I.1 M3.3 GATE TABLE — the ordered runway (rows, not work)

**Verified independently before writing, as instructed:** `ivgs-workers/temporal_pipeline/` is
**11 modules, 4,384 lines**; `temporalio` appears **0 times** in `ivgs-workers/requirements.txt`
and `ivgs-api/requirements.txt` and is **not importable** in the deployed worker
(`ModuleNotFoundError`); `192.168.1.96` `:7233` and `:8080` are **both open from node-01**.
Temporal **1.29.7** live (operator measurement, 2026-08-28).

| id | Row | Note |
|---|---|---|
| **M3.3-R1** | `temporalio` into `ivgs-workers` requirements + image | ⚠ Verify SDK/server compatibility against **1.29.7** `supportedClients` before pinning a version |
| **M3.3-R2** | Temporal worker service + infra wiring: compose service, `TEMPORAL_ADDRESS=192.168.1.96:7233`, namespace decision (create `ivgs` vs default) | ⛔ **.96 admin access method is an OPERATOR INPUT** — node-01 root ssh is not authorized there |
| **M3.3-R3** | Activities realized: stubs bind to engines / DB / SeaweedFS, honouring WP-31's **idempotency** requirement | ⛔ **This is the step the frozen-body edits execute under.** Every per-site edit row in **RC-F.1** cross-links here rather than duplicating |
| **M3.3-R4** | Conformance replay: `temporal_pipeline/conformance.py` against the **RUN-2 banked golden run**; byte/shape verdict recorded | Depends on RUN-2 existing |
| **M3.3-R5** | Cutover + fail-open flip + **O-3** re-evaluation | Re-sequences existing rows **RC-D11 / D-12** under this runway |

### I.2 A-4 motion renderer — RULED

| id | Row | Status |
|---|---|---|
| **RC-I1** | **A-4 renderer: APPROVED. Technology RULED = the Pillow reference service** — `shared/motion/raster.py` promoted behind a small HTTP service. Deterministic by construction, fonts pinned, **CPU-only**. ⛔ **Remotion explicitly NOT chosen**; its integration is the **L-3** swallow-register item | **RULED-AWAITING-EXECUTION.** Execution = the next package |
| **RC-I2** | **RC-D7 premise CORRECTED.** The node-06 Intel→CUDA compose rewrite was gated on the A-4 decision. ⛔ **Its card-swap premise was falsified by the 2026-08-28 audit — RTX 5080 confirmed**, not the 96 GB card the row assumed. And the ruled renderer is **CPU-only**, so A-4 does not imply a CUDA workload on node-06 | **Re-gated: "if/when node-06 gains a CUDA workload."** NOT gated on A-4. Owner OPERATOR |
| **RC-I3** | **L-1, L-2, L-6** close with A-4 execution — cross-reference only, no separate work | Closes with RC-I1 |

### I.3 Fleet facts, recorded — no action

| id | Fact |
|---|---|
| **RC-I4** | **Nodes 02–05 all rebooted 2026-08-28 between 02:31 and 03:16** — .94 02:31:48, .91 02:32:41, .93 02:34:31, .92 03:16:11. `/var/log/apt/history.log` is present on all four (the July unattended-upgrades precedent). ⚠ **I did not read the journal deeply enough to name the cause** — the correlation is recorded, the cause is not established. ✅ **node-04's 450 W cap HELD** (`power.limit = 450.00 W`, measured post-reboot). ✅ **node-05's vLLM is still on `sha256:3dbe092e…`**, the pinned digest |
| **RC-I5** | ⛔ **node-03 runs two server containers no IVGS package placed**: `ivgs-cogvideox-server-node03` (`ivgs-workers:cogvideox-pilot-1`) and `ivgs-wan-animate-server-node03`, the latter pulled from **`192.168.1.51:5000/mbcp/comfyui-wan`**. **An MBCP-hosted Docker registry serving IVGS nodes is a seam fact** — it is a third transport alongside AD-04's two seams, and it is not in AD-04. Belongs on the record and in any future seam audit |


---

## RC-J — WP-IVGS-09: the renderer executes, and what executing it found (2026-08-28)

### J.1 RC-I1 — **EXECUTED**, with evidence

| id | Row | Status |
|---|---|---|
| **RC-I1** | **A-4 renderer — the Pillow reference service, promoted behind HTTP.** `ivgs-motion-renderer` on **node-01**, CPU-only, no weights, no GPU. Deterministic: two identical `POST /render` calls give a byte-identical MP4 (`ae3df1ad…`) and an identical frames digest (`bce6e932…`); four sampled frames byte-identical across independent requests. `/healthz` reports build ref, template inventory, ffmpeg version and the sha256 of **every** font candidate. Failures are named — 400 / 502 / 503 — and never a fabricated frame. **Fonts vendored in-repo** at `shared/motion/fonts/` with their licence | ✅ **EXECUTED.** Evidence: `dev/workpackages/reports/WP-IVGS-09-RENDERER-report_2026-08-28.md` §6 |
| **RC-I1a** | ⚠ **PLACEMENT REVIEW TRIGGER, as the ruling required.** node-01 is a 16 GB CPU hub already running Postgres, Redis, SeaweedFS, the API, the frontend, the scheduler and three Celery workers. **Revisit placement only if render CPU load measures material.** First data point: a 128-frame render is **14,898 bytes and sub-second**, `--workers 1`. | OPEN as a trigger, not as work. Owner: whoever next measures node-01 load |

### J.2 RC-I3 — **L-1, L-2 and L-6 close**

| id | WP-68 ledger row | Closed by |
|---|---|---|
| **L-1** | *"No renderer is deployed for the `motion_graphics` engine, so no motion-graphics frame has reached a draft."* | ✅ **CLOSED.** Draft asset `2ee07595-c143-49c1-b361-71c1b7b1c959`, 115,034 bytes, H.264 1280x720 30 fps + AAC. Two frames banked at `dev/workpackages/reference/wpivgs09-draft-frames/` |
| **L-2** | *"RULE 1 has promised since v3 that the composition overlay renders the numbers in a real font, and **nothing draws them**. The largest finding in this package."* | ✅ **CLOSED.** Something draws them. A frame of the draft shows `20 tens / 3 units` in DejaVu Sans Bold, and another shows `23 x 14` with the carried `1` in red and the partial product `92` |
| **L-4** | *"`motion_graphics` scenes are HELD, not dispatched."* | ✅ **CLOSED as unconditional; RETAINED as a measured condition.** The hold now fires only when the renderer is absent, unreachable or degraded, and it says which. Proved by a live negative control |
| **L-6** | *"The Media Type dropdown does not offer `motion_graphics`."* | ✅ **CLOSED.** The option is offered, gated on L-1 closing first, and the served bundle carries it |
| **L-3** | Remotion lower-third failures swallowed at `stage7_prototype_draft.py:230-236` | ⛔ **STILL OPEN.** Frozen stage body; it is on the standing swallow register and is not touched by this package |
| **L-5** | `services/motion_graphics.py` reachable only from `FallbackChain` | ⛔ **STILL OPEN**, and now partly moot: `fallback_chain.py` was deleted by WP-IVGS-08, so its only caller no longer exists at all. Belongs with **P2.1**'s AD-05 step-8 disposition |

### J.3 New, opened by this package

| id | What | Why it is not closed here |
|---|---|---|
| **RC-J1** | ✅ **The Model Store row is REGISTERED and AWAITS THE OPERATOR'S APPROVE CLICK.** `maths-motion` / *Maths motion graphics*, `animation_generation` / `motion_graphics`, tier `both`, **state `candidate`**, `dynamically_loadable=true`, GUI weight status **`weightless` — "no weights needed"**. Registered through `POST /api/v1/models`, which lands in CANDIDATE by AD-01.5.1 and cannot land elsewhere | **Approving is an operator act.** Nothing in this package selects it, defaults it or enables it for a project |
| **RC-J2** | ⛔ **The client registry named a module that did not exist.** `client_registry.py:453` has declared `clients.motion_graphics_client.MotionGraphicsClient` since WP-68 (2026-08-26) and the module was absent — so the Model Store's client surface reported a client for `maths_motion` that could not be constructed. It never raised because `client_path` is a declarative string the registry stores and never imports | ✅ **CLOSED by making the claim true**, not by deleting it: the module exists now, because the renderer does. **The class of defect is not closed** — nothing validates that a registered `client_path` is importable, and a test for that is a candidate for the next hygiene package |
| **RC-J3** | ⛔ **`ffmpeg_client.compose_scene`'s AUDIO-LESS branch has never worked.** `ffmpeg_client.py:548-554` appends the silent-audio input (`-f lavfi -i anullsrc=…`) **after** `-filter_complex` and `-map [video]` — i.e. in the output section — and ffmpeg requires every input before any output: *"Option map … cannot be applied to input url anullsrc… Error opening input files"*. Measured 2026-08-28 composing a scene with no audio layer | **FROZEN.** AD-05 §8 preserves the eight stage bodies **and their supporting services**, and the standing instruction is *"if a migration session finds itself editing stage internals, stop."* Invisible in normal operation because stage 5 always precedes stage 7. **Re-open trigger: any path that composes a scene without audio** — a preview, a partial re-render, or a motion-only job that skips TTS |
| **RC-J4** | ⛔ **WP-IVGS-08's vLLM digest pin never reached the repository.** The `vllm/vllm-openai@${VLLM_IMAGE_DIGEST:?…}` pin — the thing that gated WP-IVGS-08's push — existed only in the untracked compose files ON nodes 02 and 04. `grep -c VLLM_IMAGE_DIGEST` on the tracked files was **0**. A redeploy from the tracked tree would silently have restored the floating `cu130-nightly` while the board still read "digest-pinned" | ✅ **CLOSED by WP-IVGS-09**: the node-side hunks are brought into `ivgs-infra/docker-compose.node02.yml` and `…node04.yml`. ⚠ **The class is not closed** — nothing compares a node's deployed compose file against the tracked one, and this is the second package to find drift by diffing them by hand |
| **RC-J5** | ⛔ **An env-file edit that was never deployed, caught in the act.** `.env.node04:50` carries `IVGS_VLLM_MAX_TOKENS=2048`, written at **14:59:45** on 2026-08-28 — **33 minutes after** `ivgs-celery-node04` was created at 14:26:59. The container has never had the variable. It is untracked and node-local, so nothing in the repo recorded it, and it would have taken effect silently on the next unrelated recreate | ✅ **NEUTRALISED**, not deleted: a compose-level `environment:` entry beats `env_file:`, and node-04 now declares **4096** — the value it is actually running. The stale line is left in place and recorded rather than edited on a node ⚠ **Also recorded:** a stray `.env.node02` (mtime 2026-06-01) sits on node-03 and node-04, referenced by no compose file there |
| **RC-J6** | ✅ **RULED AND ROWED — see P2.47.** The operator opened a P2 on the GO of 2026-08-28, with all three named sites plus the two the drain exposed. ⛔ **The scheduler's queue-depth counter is not the queue.** `pq:depths` read `urgent 22 / normal −2 / batch 0` against sorted sets of `18 / 2 / 0`. **A queue length of −2 is not a queue length.** Three sites in `ivgs-scheduler/priority_queue.py` diverge: `apply_aging` never scans `urgent` (`:211`) and its expired-entry cleanup (`:217-220`) `zrem`s without decrementing; `resolve_priority` on an existing job (`:129-137`) rewrites `effective_priority` without moving the zset entry or touching the counter; `remove_job` (`:288-292`) then decrements a queue the job never joined. **And every queued job reads `base_priority=normal`** — not one of the "23 urgent requests" was submitted as urgent; they are anti-starvation promotions | ✅ **RULED. Opened as P2.47** — *"open the P2 row for the three §3.1 counter defects, all three sites named"* (operator, 2026-08-28). P2.47 names those three and **two more the drain exposed**: `get_queue_depths` clamps the negative to 0 so `/fleet` never showed it, and **project deletion never purges Redis db 1**, which is the source of the accumulation. Still NOT FIXED — rowed, scoped, and gated on nothing |
| **RC-J7** | ⛔ **A test asserted set EQUALITY on `ModelEngine` under a name that promised subset.** `test_api_model_export.py::test_no_existing_value_was_removed` failed on migration 0044 ADDING `motion_graphics` — an addition, which is not what the test is named for | ✅ **CORRECTED in the same commit**, to the subset relation its name states. `test_domain_is_still_closed` in the same file is what keeps the enum from becoming free text; equality was doing a job nothing asked for |
| **RC-J8** | ⚠ **`TEST-BASELINE_2026-08-25` §1's environment block is incomplete.** The `ivgs-backup-worker` suite is **4 failed**, not 4 passed, unless `IVGS_CELERY_BROKER_URL`, `IVGS_CELERY_RESULT_BACKEND` and `POSTGRES_DSN_SYNC` are supplied the way compose does — WP-IVGS-08 Task 2(d)'s import-time refusal doing its job | ✅ **The baseline document is corrected in the same commit** |
| **RC-J9** | ⚠ **The latest DB dump is two migrations behind production.** `/mnt/backup/ivgs/db/2026-08-28/` restores to `alembic_version = 0041`; production is at `0044`. 0042/0043 were applied after the 02:00 backup. **A restore from the latest dump does not carry the current schema; `alembic upgrade` is a required recovery step** | Recorded, not acted on. Worth knowing before an incident rather than during one. Belongs with **DEF.1** (disaster recovery) |
| **RC-J10** | ⚠ **`dev/CLAUDE.md` §1 no longer describes practice.** It reads *"Claude does NOT commit, push, merge, or deploy"*; the last several work orders have explicitly directed commits and node-01–04 deploys, this one included. The rule and the standing instructions disagree, and a rule contradicted every week stops being read | **Operator ruling needed.** Amend §1 to the actual boundary (commit yes, push never, deploy 01–04 when the order says so) or restate the prohibition and change the orders. **Not amended here** — `dev/CLAUDE.md` is the cold-start contract and is not edited on a package's own initiative |

### J.4 The task-registration gap, worth its own line

⛔ **`app.conf.include` is the registry, and a task module absent from it does not exist to the
worker.** With `tasks/motion_graphics_task.py` written, the client written, the queue mapped and
the dispatcher routing to it, `celery inspect registered` on `default-worker@node01` still had
no motion entry — a dispatch would have gone to a task nobody serves. Added
(`celery_app.py`, the Replace column of AD-05 §8), verified live:

    ->  default-worker@node01: OK
        * tasks.motion_graphics_task.render_scene_motion_graphics

`_assert_registry_is_not_vacuous` exists for this class of miss and did not catch it, because
the registry was not vacuous — it was merely incomplete. **Named here rather than quietly
fixed.**


---

## RC-K — WP-IVGS-09b: the scene model picker offered no motion-graphics model (2026-08-28)

**Reported live during RUN-2, from the GUI.** *"A scene switched to media type motion_graphics
offers NO model. The picker keeps 'image generation' and 'change model' lists nothing, despite
maths-motion being approved+enabled."*

### K.1 What the picker asks, and what it got

The request is `useModelSelections.useSceneSelection` (`ivgs-frontend/src/hooks/useModelSelections.ts:127-132`):

    GET /api/v1/projects/{pid}/model-selections/scene/{sid}?media_type=<medium>&tier=production

Measured through **nginx over https — the browser's own route**, before any change:

| media_type | stage returned | candidates |
|---|---|---|
| image | `image_generation` | flux1-schnell, FLUX.1-dev |
| video_clip | `video_generation` | CogVideoX-5b, Wan2.2-T2V |
| animation | `animation_generation` | wan2.2-animate, AnimateDiff-SD15, **maths-motion**, MimicMotion, Wan2.2-Animate |
| **motion_graphics** | ⛔ **`image_generation`** | ⛔ **flux1-schnell, FLUX.1-dev** |

### K.2 Which side dropped it — **the API, and the frontend was innocent**

| id | Finding | Site |
|---|---|---|
| **RC-K1** | ⛔ **`MEDIA_TYPE_STAGE` had three entries and the lookup defaulted.** `motion_graphics` was absent, and `MEDIA_TYPE_STAGE.get(media_type or "image", ModelStage.IMAGE_GENERATION)` silently made it an image. **The default is what made it silent** — nothing failed, nothing warned, and the picker confidently offered FLUX for a scene that draws arithmetic | `ivgs-api/app/services/selection_panel.py:319-323` (the map) and `:335` (the defaulting lookup) |
| **RC-K2** | ✅ **The frontend passes the medium correctly and filters nothing.** `SceneEditModal.tsx:751-755` sends the draft medium; `ModelPicker.tsx:133` renders every candidate the server sends. **There is no frontend map and no frontend filter** — the whole of the eligibility decision is server-side | measured, not inferred |
| **RC-K3** | ⛔ **The mirror defect, found by the same measurement and live before this package: the `animation` picker listed `maths-motion` as SELECTABLE.** `_candidates_for` filtered on `(stage, tier)` with **no family dimension**, and `animation` and `motion_graphics` share `animation_generation` in MBCP's taxonomy. Wan2.2-Animate reenacts a person and refuses a personless still by name; a template renderer cannot animate a person. Each medium was being offered the other's model | `ivgs-api/app/services/selection_panel.py:109-117` |
| **RC-K4** | ⛔ **THE HALF THAT WAS STILL WRONG AFTER THE CANDIDATE FILTER LANDED.** With candidates narrowed but `resolve_binding` left stage-wide, a `motion_graphics` scene with no selection of its own resolved to **`wan2.2-animate`** — the panel offered exactly one model and announced underneath it that the scene was bound to one that cannot render it. `is_default` is one flag per stage and on `animation_generation` it belongs to the animation medium | `ivgs-api/app/services/selection_panel.py`, the stage-default fallback |

### K.3 The fix

**A STAGE IS NOT A MEDIUM.** Both halves keyed on `(stage, family)`:

* `MEDIA_TYPE_STAGE` gains `motion_graphics -> ANIMATION_GENERATION`, and the defaulting lookup
  becomes `stage_for_media_type()`, which **refuses an unmapped medium by name** (422). A test
  asserts every value of the `MediaType` enum is mapped, so this gap cannot reopen silently.
* `MEDIA_TYPE_FAMILIES` names the families each medium may use, **only for the media types that
  share a stage**. `talking_head`, `video_generation` and `voiceover_tts` also serve several
  families but each serves one medium, so they are untouched and still get every model on their
  stage.
* The engine set is **derived from the WP-67 client registry**
  (`client_registry.engines_for_families`, new), not restated beside it — a second list of
  "which engines are animation engines" is a second definition, free to drift.
* `resolve_binding` takes the same engine set for its **default** lookup only. It does **not**
  narrow the two selection lookups: a row an operator wrote is theirs, and if it points
  somewhere the medium cannot use, the existing warning machinery surfaces it rather than a
  filter making their choice vanish.
* New provenance **`only_candidate`** — deliberately not "default": a medium sharing a stage may
  have no `is_default` of its own, and when exactly one servable model exists that model is what
  will run. Two or more, or none, yields `none` and asks the operator to choose. Nobody chose
  it, so it is not called a default.

### K.4 Proved, before and after, on the same endpoint through the GUI path

| media_type | before | after |
|---|---|---|
| image | 2 candidates, `image_generation` | **unchanged** |
| video_clip | 2 candidates, `video_generation` | **unchanged** |
| animation | **5**, incl. `maths-motion` selectable | **4** — `maths-motion` gone; `wan2.2-animate` still the default |
| **motion_graphics** | `image_generation`, 2 FLUX rows | ✅ **`animation_generation`, 1 candidate: `maths-motion`, approved, selectable; `provenance=only_candidate`** |

**And through the GUI's own action path, not a bypass** — the read the modal makes on open, then
the `PUT` the *"Use this model"* button makes (`useModelSelections.select:69-75`): offered
`maths-motion` → pressed → HTTP 200 with `scene_id` set → re-read shows `provenance=scene`. The
animation medium was unchanged throughout.

⚠ **Why WP-IVGS-09's acceptance did not catch it.** That harness created scenes and dispatched
media **below the GUI** — it never opened the picker, because dispatch does not consult the model
binding for this branch at all (`motion_graphics_task` resolves its endpoint directly). The
render path was right and the *selection surface* was wrong, and only a person opening the modal
would meet it. **A test that exercises the pipeline is not a test of the page.**

⚠ **The test database was two migrations behind and this is where it showed.** `ivgs_reconciliation_test`
was at `0043`; the new tests insert a `motion_graphics`-engine row and got
`InvalidTextRepresentationError: invalid input value for enum model_engine`. Brought to `0044`.
Recorded in `TEST-BASELINE`.
