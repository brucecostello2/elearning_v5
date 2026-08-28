# WP-IVGS-09 — the numbers reach the screen

**Date:** 2026-08-28 · **Node:** node-01 (192.168.1.90) · **Branch:** `main`
**Target tag:** `v5.32.0-motion-live`
**Report path:** `dev/workpackages/reports/WP-IVGS-09-RENDERER-report_2026-08-28.md`

⛔ **COMMITTED AND HELD. NOTHING PUSHED.** The count-gated push block is §10.

---

## §0. Conflicts between the order and the governing documents, named up front

The order says: *"Read dev/CLAUDE.md and dev/DEVELOPMENT-STATUS.md first and follow both;
where they conflict with this order, tell me rather than choosing silently."* **Two conflicts.
Both are resolved in the order's favour and both are named rather than assumed.**

| # | The conflict | How it was resolved |
|---|---|---|
| **1** | `dev/CLAUDE.md` §1: *"Claude does NOT commit, push, merge, or deploy."* The order says **"Commit and HOLD"** and **"You may deploy nodes 01-04 under the Task-5 standard"**. | The order is **specific, scoped and current** (nodes 01–04 only; commit but never push). §1 is the standing default. I followed the order: commits are made, **nothing is pushed**, and deploys are confined to nodes 01–04. ⚠ **`dev/CLAUDE.md` §1 is now contradicted by the last several packages in practice** and is a candidate for amendment — flagged, not amended here. |
| **2** | `dev/CLAUDE.md` §3: *"The eight stage task bodies during the orchestration migration — the scope boundary in AD-05 section 8 is binding."* Task 1 required a motion-graphics scene to reach a draft. | **No frozen body was edited.** `tasks/motion_graphics_task.py` is a **new, ninth** body for a media branch that had none — the same move WP-46 made for `animation`. `tasks/pipeline_orchestrator_v2.py`, which routes to it, is explicitly in AD-05 §8's **Replace** column (*"the coordination layer only"*) and is not frozen. Detail in §2.3. |

**One scope statement.** Every existing project is untouched. No gate was pressed. Test
projects were created and deleted through the WP-59 flow. Nodes 05, 06, `.51`, `.52` and `.96`
were not contacted.

---

## §1. Headline

| Task | Verdict |
|---|---|
| **0(a)** apply the 20 rulings | ✅ **DONE.** 39 rows carry a `⚖ RULING (operator ruling 2026-08-28)` block; §RC-H3 rewritten as a settled record; **P2.46** added as the RUN-2 sweep the ruling required |
| **0(b)** three probes | ✅ **DONE.** P1.4n named-refusal measured; P1.5b **closed on live Prometheus evidence**; P2.1's lost "decided" text **found in three places and restored** |
| **0(c)** the 23 stranded requests | ✅ **LISTED, then DRAINED on the GO.** 22 entries, one line each; `pq:depths` reconciled to the queue for the first time. **P2.39 CLOSED**, **P2.47 opened**. §3 |
| **0(d)** WP-IVGS-08 §9 threads | ✅ **DONE.** Both suites re-baselined; the 0043 downgrade exercised on a scratch DB; `IVGS_VLLM_MAX_TOKENS` measured across four containers and declared at compose level per node |
| **1** the renderer | ✅ **DONE.** `ivgs-motion-renderer` deployed on node-01, deterministic, weightless Model Store row registered. ⛔ **STOPPED for your APPROVE click.** §6 |
| **2** acceptance | ✅ **PASSED.** A motion-graphics frame reached a **DRAFT**; negative control fires the named hold. §7 |
| **3** the dropdown | ✅ **LIFTED**, gated on Task 2 passing. L-6 closes, P1.4r fixed in the same rebuild. §8 |
| **4** closures and the board | ✅ **DONE.** RC-I1 EXECUTED, RC-I3 closes L-1/L-2/L-6, §RC-J added, board refreshed. §11 |

---

## §2. Task 0(a) — the rulings, applied

**39 rows now carry a `⚖ RULING (operator ruling 2026-08-28)` block**, each stating the
ruling in the ruling's own terms and, where the ruling changes the row's disposition,
rewriting the `**Status:**` token and preserving the previous text as `*(was: …)*`.

| Ruling | Rows | Applied as |
|---|---|---|
| CLOSED | P1.0a, P1.0b, P1.5a, P1.5b, P2.37 | status → `CLOSED`, with the evidence named on the row |
| ARCHIVED | P1.4, P1.4f, P1.6, P2.2 | status → `ARCHIVED` |
| DROPPED | P2.35 | status → `DROPPED` |
| GATED | P1.4h, P1.4q, P1.4r, P1.7, P2.1, P2.5, P2.10 | status → the gate, named |
| VERIFY-AT-RUN-2 | **P2.12 – P2.31, 20 rows** | status → `VERIFY-AT-RUN-2`; residue → **P2.46** |
| FIX | P2.38 | status → `FIX — post-RUN-2 batch` |
| OPERATOR-ATTENDED | P2.39 | status → `OPERATOR-ATTENDED — WP-IVGS-09 Task 0(c)` |

**§RC-H3 was rewritten** from *"⛔ NEEDS-RULING — the residue, one line each"* to
*"✅ RULED — the residue, and where each row went"*, with a row-by-row disposition table.
It is a settled record now, not an open question.

### 2.1 ⚠ Two corrections the rulings forced

**(a) The carried-v3.1 block was 18, not 20.** §RC-H3 said *"P2.12–P2.31 is 20 of the 41"*
while its own grouped entry enumerated `P2.12–P2.14, P2.16–P2.28, P2.30, P2.31` — **18 rows**.
**P2.15** and **P2.29** sat inside the stated range and outside the enumeration. The ruling
names the contiguous range `P2.12-P2.31`, so both are included, the block is genuinely 20, and
the count reconciles. P2.29 is a partial: §RC-H.1 closed its monitoring-net half, so
VERIFY-AT-RUN-2 applies to the `base.yml` vs `node01.yml` half only.

**(b) Twenty-one rows had no `**Status:**` line at all.** Every carried-v3.1 row plus P2.35
carried a title and a body and no status field — so their state was not derivable, only
inferable. Each now has one. This is why the register's own counts have been hard to reconcile
across packages.

### 2.2 P2.46 — the sweep the ruling required

> *"residue gets one bounded sweep immediately after RUN-2. Add that sweep as a row."*

Added. It sweeps **P2.12–P2.31**, **P1.4h** and **P1.4q**, and it is bounded in as many words:
**one pass, one verdict per row, nothing carried forward for a second look.** A sweep that may
run twice is not a sweep.

### 2.3 P1.0a's carried cross-check

The ruling asked for *"one M3.3-R3 cross-check line: no hardcoded SadTalker fallback survives
stage-6 activity realization."* It is on the P1.0a row and cross-referenced from §RC-I.1's
M3.3-R3 entry. It is a checklist line, not a reopened row.

---

## §3. ✅ Task 0(c) — the stranded queue: LISTED, then DRAINED on the GO

The order: *"LIST the 23 stranded urgent requests (age, project, stage) in the report, then
STOP and wait for the operator's GO before draining."*

**Listed at §3.2, drained at §3.3 on the operator's GO of 2026-08-28.** The list below is
kept as it was written *before* the GO — it is the census the disposition was approved against,
and rewriting it after the fact would hide that the queue grew by two in between (§3.3).

### 3.1 ⚠ The premise moved twice, and both corrections change what draining means

**(a) The fleet is no longer zero nodes.** P2.39 was written against
`{"total_nodes":0,"alive_nodes":0,...}`. Measured today:

```
$ docker exec ivgs-scheduler sh -lc 'curl -s localhost:8001/fleet'
"total_nodes":3, "alive_nodes":3, "total_vram_mb":293661, "available_vram_mb":293661,
"queue_depth":{"urgent":22,"normal":0,"batch":0}
nodes: node-02:gpu0, node-03:gpu0, node-04:gpu0 — all alive, heartbeating, circuit breakers closed
```

**(b) ⛔ "23" IS A COUNTER, NOT A CENSUS — and the counter is provably wrong.**
The queue lives in **Redis db 1** (`SCHEDULER_REDIS_URL=redis://redis:6379/1`), as a
`pq:depths` hash of counters *plus* `pq:queue:<level>` sorted sets. They disagree:

| | urgent | normal | batch |
|---|---:|---:|---:|
| `pq:depths` (what `/fleet` reports) | **22** | **−2** | 0 |
| `ZCARD pq:queue:<level>` (the actual queue) | **18** | **2** | 0 |

⛔ **A queue length of −2 is not a queue length.** The counter is a separate value that three
code paths update inconsistently, all in `ivgs-scheduler/priority_queue.py`:

1. **`apply_aging` never scans `urgent`** (`:211`, `for priority_level in ["batch", "normal"]`).
   Its expired-job cleanup (`:217-220`) `zrem`s the entry **without** decrementing `pq:depths`
   — and it cannot reach an urgent entry at all. **So an urgent entry whose job hash has
   expired is immortal and uncounted.** Two of the 18 are exactly that.
2. **`resolve_priority` on an EXISTING job** (`:129-137`) rewrites `effective_priority` in the
   hash **without moving the zset entry and without touching the counter** — which is why two
   jobs sit in `pq:queue:normal` with `effective_priority=urgent` and `aging_bumps=0`.
3. **`remove_job`** (`:288-292`) decrements `DEPTHS[effective_priority]` and `zrem`s from that
   queue — but after (2) the job is in a *different* zset, so the `zrem` misses and the
   decrement lands on a queue the job never joined. **That is where `normal = −2` comes from.**

**A third correction, and the largest.** Every one of the 18 hashes reads
`base_priority=normal`. ⛔ **Not one of these was submitted as urgent.** They are aged-in normal
jobs — the anti-starvation bump (`:196`, 30-minute interval) promoting `normal → urgent`. The
row's title, *"23 urgent scheduling requests"*, describes something that never happened.

### 3.2 THE LIST AS PRESENTED FOR APPROVAL — 20 entries (ages at 2026-08-28 16:5x UTC)

⛔ **Not one is a live pending job.** Four are terminal, ten reference `render_jobs` rows that
no longer exist, six are synthetic probes left by earlier packages.

| # | queue | id | age (h) | base → effective | project / job state |
|---:|---|---|---:|---|---|
| 1 | urgent | `b3df6eb6-…acb6` | ~72+ | *(hash expired)* | **double digit multiplication** — `image_generation`, **failed** ("tts_audio checkpoint write returned 429") |
| 2 | urgent | `1e65b11d-…8d0b` | ~72+ | *(hash expired)* | **double digit multiplication** — `final_render`, **success** ("Cancelled by user") |
| 3 | urgent | `89383cdd-…1e33` | 65.9 | normal → urgent (1 bump) | ⛔ no `render_jobs` row — project deleted |
| 4 | urgent | `1aa7b507-…19e3` | 65.9 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 5 | urgent | `98b32541-…7e51` | 65.9 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 6 | urgent | `8b881252-…3f16` | 55.5 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 7 | urgent | `d4b41765-…2dfd` | 51.1 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 8 | urgent | `02d2c773-…30c6` | 47.6 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 9 | urgent | `bd07f416-…4c37` | 47.6 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 10 | urgent | `610b35d8-…3905` | 47.3 | normal → urgent (1) | **another multiplication pass e2e** — `transcript_refinement`, **success** |
| 11 | urgent | `439b2779-…f375` | 45.5 | normal → urgent (1) | **another new multiplication test run** — `transcript_refinement`, **success** |
| 12 | urgent | `aae4f8cc-…2a41` | 12.8 | normal → urgent (1) | ⛔ no `render_jobs` row |
| 13 | urgent | `d04f0000-0000-4000-8000-0000000000d1` | 12.7 | normal → urgent (1) | 🧪 **synthetic** — WP-IVGS-0x probe id |
| 14 | urgent | `probe` | 7.6 | normal → urgent (1) | 🧪 **synthetic** |
| 15 | urgent | `wpivgs06-probe` | 7.5 | normal → urgent (1) | 🧪 **synthetic** — WP-IVGS-06 |
| 16 | urgent | `d06f0000-…00d1` | 7.2 | normal → urgent (1) | 🧪 **synthetic** — WP-IVGS-06 |
| 17 | urgent | `wpivgs07-dbl` | 6.9 | normal → urgent (1) | 🧪 **synthetic** — WP-IVGS-07 |
| 18 | urgent | `d07f0000-…00d1` | 6.8 | normal → urgent (1) | 🧪 **synthetic** — WP-IVGS-07 |
| 19 | normal | `de838c11-…ceac1e` | 65.9 | normal → **urgent in the hash, still in the normal zset** (0 bumps) | ⛔ no `render_jobs` row — mechanism (2) above |
| 20 | normal | `47be634d-…6287` | 65.9 | normal → **urgent in the hash, still in the normal zset** (0 bumps) | ⛔ no `render_jobs` row — mechanism (2) above |

Stage, where a job row survives, is `render_jobs.job_type`; `render_jobs` has no
`current_stage` column, so "stage" for the ten deleted ones is unrecoverable — the queue hash
carries `job_id`, `base_priority`, `effective_priority`, `submitted_at`, `aging_bumps` and
nothing else. **Stated rather than guessed.**

### 3.3 ✅ GO RECEIVED — DRAINED. One line per row, as ordered.

Disposition approved as proposed, including the `pq:depths` reset and the direct
`zrem pq:queue:normal` for rows 19 and 20. **Executed 2026-08-28**, inside `ivgs-scheduler`,
using the scheduler's **own** `PriorityQueueManager.remove_job` — so what each row got is what
production does, not what a script thinks production does.

⚠ **The list grew from 20 to 22 between §3.2 and the GO, and both new entries fall inside an
approved group.** `3f489575…` and `8cdb79b6…` are **this package's own Task-2 jobs**. Their
projects were deleted through the WP-59 flow and **their queue entries survived it** — the
accumulation mechanism reproduced live, three hours after §3.2 was written. Disposition:
*deleted projects*, as approved. Nothing else moved.

| # | job_id | group | method | result |
|---:|---|---|---|---|
| 14 | `probe` | synthetic | `remove_job` | hash deleted · urgent zset **CLEARED** |
| 15 | `wpivgs06-probe` | synthetic | `remove_job` | hash deleted · **CLEARED** |
| 17 | `wpivgs07-dbl` | synthetic | `remove_job` | hash deleted · **CLEARED** |
| 13 | `d04f0000-…00d1` | synthetic | `remove_job` | hash deleted · **CLEARED** |
| 16 | `d06f0000-…00d1` | synthetic | `remove_job` | hash deleted · **CLEARED** |
| 18 | `d07f0000-…00d1` | synthetic | `remove_job` | hash deleted · **CLEARED** |
| 10 | `610b35d8-…3905` | terminal (`transcript_refinement`, success) | `remove_job` | hash deleted · **CLEARED** |
| 11 | `439b2779-…f375` | terminal (`transcript_refinement`, success) | `remove_job` | hash deleted · **CLEARED** |
| 1 | `b3df6eb6-…acb6` | terminal (`image_generation`, failed), **hash expired >72 h** | **direct `zrem pq:queue:urgent`** — `remove_job` is a no-op without a hash (`:284`) | removed=1 |
| 2 | `1e65b11d-…8d0b` | terminal (`final_render`, success), **hash expired >72 h** | **direct `zrem pq:queue:urgent`** | removed=1 |
| 3 | `89383cdd-…1e33` | deleted project | `remove_job` | **CLEARED** |
| 4 | `1aa7b507-…19e3` | deleted project | `remove_job` | **CLEARED** |
| 5 | `98b32541-…7e51` | deleted project | `remove_job` | **CLEARED** |
| 6 | `8b881252-…3f16` | deleted project | `remove_job` | **CLEARED** |
| 7 | `d4b41765-…2dfd` | deleted project | `remove_job` | **CLEARED** |
| 8 | `02d2c773-…30c6` | deleted project | `remove_job` | **CLEARED** |
| 9 | `bd07f416-…4c37` | deleted project | `remove_job` | **CLEARED** |
| 12 | `aae4f8cc-…2a41` | deleted project | `remove_job` | **CLEARED** |
| 21 | `3f489575-…3383` | deleted project *(this package's Task-2 job)* | `remove_job` | **CLEARED** |
| 22 | `8cdb79b6-…3cfe` | deleted project *(this package's Task-2 job)* | `remove_job` | **CLEARED** |
| 19 | `de838c11-…ceac1e` | deleted project, **in the NORMAL zset with `effective_priority=urgent`** | **direct `zrem pq:queue:normal` + `del` hash** — `remove_job` would have `zrem`'d from `urgent` (a miss) and decremented `urgent` for a job that never joined it | zrem=1 · hash_del=1 |
| 20 | `47be634d-…6287` | deleted project, same shape | **direct `zrem pq:queue:normal` + `del` hash** | zrem=1 · hash_del=1 |

### 3.4 ⛔ THE DRAIN PROVED THE COUNTER DEFECT IN THE OPEN

```
BEFORE  zcards = {urgent: 20, normal: 2, batch: 0}   depths = {urgent: 24, normal: -2, batch: 0}
AFTER   zcards = {urgent:  0, normal: 0, batch: 0}   depths = {urgent:  6, normal: -2, batch: 0}
RESET   zcards = {urgent:  0, normal: 0, batch: 0}   depths = {urgent:  0, normal:  0, batch: 0}
```

**The middle line is the whole argument.** All 22 entries gone, the queue verifiably empty —
and the counter still read **`urgent: 6, normal: −2`**. Eighteen `remove_job` calls took urgent
from 24 to 6; the four direct removals had no counter to decrement; and `normal` never moved off
−2 because nothing has ever decremented it correctly.

`pq:depths` was reset to the measured `ZCARD` under the same ruling. **That reset is the only
reconciliation of these two records that has ever happened, and a person did it.**

Live afterwards:

```
$ docker exec ivgs-scheduler sh -lc 'curl -s localhost:8001/fleet'
queue_depth = {'urgent': 0, 'normal': 0, 'batch': 0}
alive_nodes = 3/3   total_vram_mb = 293661   nodes = node-02:gpu0, node-03:gpu0, node-04:gpu0

$ docker exec ivgs-redis redis-cli -n 1 --scan --pattern 'pq:*'
pq:depths                       <- the counter hash itself; correct that it remains
```

`gpu_reservations` is empty, as it was before and throughout. **P2.39 is CLOSED.**

### 3.5 ✅ P2.47 opened — and the drain found two more sites than the ruling asked for

The ruling: *"open the P2 row for the three §3.1 counter defects, all three sites named."*
**Opened as P2.47**, with those three named — and with **two more the drain exposed**, recorded
rather than left for the next package to re-find:

4. ⛔ **`get_queue_depths` clamps the defect out of sight.** `priority_queue.py:309-313`,
   `max(0, int(depths.get(...)))`. `/fleet` reported `normal: 0` while the stored counter was
   **−2**. The clamp turns an impossible value into a plausible one — the fabricated-absence
   rule inverted: **reporting a believable number about something that is broken.** This is why
   nobody has noticed in the eight days the queue has been drifting.
5. ⛔ **Project deletion never purges Redis db 1 — this is the SOURCE of the accumulation.**
   `project_deletion.py:401-410` purges five `ivgs:*` key shapes, **all in db 0**. The priority
   queue lives in **db 1** (`SCHEDULER_REDIS_URL=redis://redis:6379/1`) and is not touched.
   **Twelve of the 22 drained had no `render_jobs` row at all** — deleted projects whose queue
   entries were left behind. Reproduced by this package's own two test projects, three hours
   apart.

P2.47 also says what **not** to do: do not "fix" this by making `get_queue_depths` return the
`ZCARD`s. That makes the surface honest and leaves three write paths still corrupting a value
nobody reads — the half-fix that removes the evidence. **One record, not two**, is the answer,
and site 5 is separable and probably the most valuable single fix.

---

## §4. Task 0(b) — the three probes

### 4.1 P1.4n — `ffmpeg` through binding **and** registry: **resolves at one, named refusal at the other**

The row asks whether `ffmpeg` can ever resolve a binding. Both halves were probed:

```
# node-01, from the tree (.venv), 2026-08-28
ffmpeg          -> REFUSED  EndpointResolutionError: no endpoint mapping for engine 'ffmpeg'
motion_graphics -> REFUSED  EndpointResolutionError: engine 'motion_graphics' resolved to an
                            empty endpoint (IVGS_MOTION_GRAPHICS_URL)      [before deployment]

ffmpeg          -> CLIENT   clients.ffmpeg_client.FFmpegClient
                            family=ffmpeg_concat  produces=video/mp4
motion_graphics -> CLIENT   clients.motion_graphics_client.MotionGraphicsClient
                            family=maths_motion   produces=video/mp4
```

**The answer is: named refusal at the binding, resolves at the registry — and that is
correct, not contradictory.** `ffmpeg` is a local binary the compositor invokes; it has no
endpoint by nature, and `client_registry.py:417` says so on the row (*"Local binary, not a
served model. No weights, no endpoint"*). The refusal names the engine and the reason. Nothing
is silently defaulted. **Recorded on P1.4n; the row's "can never resolve a binding" is true and
is the intended behaviour, not a defect.**

### 4.1a ⛔ A DEFECT FOUND BY THE SAME PROBE — the registry named a module that did not exist

`resolve_client` returns `clients.motion_graphics_client.MotionGraphicsClient`. **That module
did not exist.** It has been named in `shared/providers/client_registry.py:453` since WP-68
(2026-08-26) and `import clients.motion_graphics_client` failed.

It never raised, because `client_path` is a declarative string the registry stores and never
imports — so **the Model Store's client surface has been reporting a client for `maths_motion`
that could not have been constructed.** Registering a client is a claim about what IVGS can
run.

**Fixed by making the claim true**, not by deleting it: `ivgs-workers/clients/motion_graphics_client.py`
now exists, because the renderer now does. Rowed as **RC-J2** (§8).

### 4.2 P1.5b — the BackupStale alert rule: **CLOSED on evidence**

Grepped, then checked live rather than stopping at the file:

```
ivgs-infra/configs/prometheus/alert_rules.yml:190
  - alert: BackupStale
    expr: time() - ivgs_backup_last_timestamp{backup_type!="physical_base_backup"} > 93600
    labels: {severity: critical, team: infrastructure, component: backup}

ivgs-infra/configs/prometheus/alert_rules.yml:257
  - alert: BaseBackupStale        (WP-59 Task 8 — the weekly physical base, own threshold)

ivgs-infra/configs/alertmanager/alertmanager.yml:63-68
  inhibit_rule: BackupStale suppresses BackupFailed for the same backup_type

$ curl -s :9090/api/v1/rules      # node-01, live
ivgs_critical_alerts | BackupFailed    | state=inactive | health=ok
ivgs_critical_alerts | BackupStale     | state=inactive | health=ok
ivgs_critical_alerts | BaseBackupStale | state=inactive | health=ok
```

**Loaded and evaluating, not merely present in a file.** 26 hours, not 24, so a slow daily
02:00 backup does not page. **P1.5b CLOSED.** *(A file-only grep would have closed it too, and
would have been the weaker evidence — `health=ok` is what proves Prometheus parsed it.)*

### 4.3 P2.1 — the lost "decided" text: **FOUND, in three places, agreeing with itself**

The ruling allowed `REMOVE-per-A1` if unfindable. **It is findable.** Grepping the reports and
specs for the row's `1,957` figure and its "decide before wiring" framing turned up the
decision, recorded three times:

| Source | What it says |
|---|---|
| `docs/adr/ADR-005-durable-execution-engine.md:1-6` | **Status: Accepted**, 2026-08-14, deciders Bruce Costello. The WS-T fork was taken — Temporal |
| `docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md:219-221` | `RetryEngine` (461), `DLQService` (754), `FallbackChain` (742) sit in the **Replace / Delete** column of the *binding* §8 scope boundary |
| `docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md:287` | step **8**: *"After a clean verified run, delete the Celery coordinator and the ~1,957 orphaned lines; retire ledger P0.1, P1.1–P1.2, P2.1–P2.3 together"* |

**Restored ruling: DELETE at AD-05 migration step 8, with `FallbackChain`'s L1→L4 policy
extracted first** (AD-05 §8's named special case). Two of the three modules are already gone —
WP-IVGS-08 Task 2(a) deleted `services/fallback_chain.py` under an operator ruling.
**Gate: AD-05 step 8, i.e. after M3.3-R5. No REMOVE-per-A1.**

---

## §5. Task 0(d) — the WP-IVGS-08 §9 threads

### 5.1 The two suites — both baselines recorded, and one needed the env compose supplies

| Suite | Result | Against baseline |
|---|---|---|
| `ivgs-backup-worker/tests` | **4 passed, 0 failed** (0.29 s) | ✅ matches `TEST-BASELINE_2026-08-25` §0 (**4 / 0**) |
| `tests_system` | **193 passed, 12 failed, 15 skipped, 30 errors** (4.30 s) | ✅ **exactly** the baseline (193 / 12 / 15 / 30) |

⛔ **WP-IVGS-08 §9.3(3)'s worry was right, and it costs 4 tests if the env is wrong.**
Run with only the baseline's §1 block, the backup-worker suite is **4 failed**, not 4 passed:

```
RuntimeError: IVGS_CELERY_RESULT_BACKEND is not set. The backup worker will not start
without an explicit result backend DSN: it used to fall back to a hardcoded DSN, which
could silently target the wrong database.
```

That refusal is WP-IVGS-08 Task 2(d)'s own work, doing its job — `celery_app.py:66` refuses at
import. The suite imports `tasks.backup_tasks`, which imports `celery_app`. **The fix is to
supply the env the way compose does**, from
`ivgs-infra/docker-compose.override.node01.yml:87-88`, pointed at the TEST database:

```bash
export IVGS_CELERY_BROKER_URL="redis://192.168.1.90:6379/0"
export IVGS_CELERY_RESULT_BACKEND="db+postgresql+psycopg2://<user>:<pw>@192.168.1.90:5432/ivgs_reconciliation_test"
export POSTGRES_DSN_SYNC="$BACKUP_TEST_DSN"
```

⚠ **`TEST-BASELINE_2026-08-25` §5's invocation is now incomplete** — it lists only
`BACKUP_TEST_DSN`. The three variables above belong in §1's block. **Recorded; the baseline
document is updated in the same commit.**

### 5.2 The 0043 downgrade — exercised on a SCRATCH database, production untouched

⛔ **The dump contains `DROP DATABASE IF EXISTS ivgs;`.** `scripts/backup.sh:366-368` dumps with
`--clean --create`, so the SQL carries `DROP DATABASE` / `CREATE DATABASE ivgs` / `\connect
ivgs`. **Restoring it into `ivgs-postgres` would have destroyed production**, whatever database
name the `psql` invocation named. So the scratch instance is a throwaway container, the pattern
`scripts/verify_backup.sh:255-266` already uses:

```
docker run -d --name ivgs-scratch-0043 -e POSTGRES_PASSWORD=<throwaway> \
  -p 127.0.0.1:55432:5432 -v /var/tmp/ivgs-scratch-0043:/var/lib/postgresql/data \
  --memory=1g --memory-swap=1g --shm-size=256m postgres:17-alpine
```

Loopback only, PGDATA on disk (never a tmpfs — `dev/CLAUDE.md` §7's node-01 memory trap),
memory-capped, and removed with its data directory afterwards.

**⚠ First finding: the latest dump is two migrations behind production.**

```
restored from /mnt/backup/ivgs/db/2026-08-28/ivgs_backup.sql.gz.gpg  (02:00, 185 MB of SQL)
scratch alembic_version = 0041      production alembic_version = 0043
```

0042 and 0043 were applied *after* the 02:00 backup. Not a defect — but a restore from the
latest dump does not carry the current schema, and `alembic upgrade` is a required step in any
recovery. **Worth knowing before an incident, not during one.**

**The exercise, both directions, with the observable that matters:**

| Step | `alembic_version` | `models.dynamically_loadable` column default |
|---|---|---|
| restored | `0041` | `true` |
| `alembic upgrade head` | `0043` | **`(none)`** |
| **`alembic downgrade 0042`** | **`0042`** | **`true`** — the defect deliberately restored, exactly as the migration's own comment says |
| **`alembic upgrade 0043`** | **`0043`** | **`(none)`** |

**The 0043 downgrade path works and is reversible.** Production stayed at `0043` throughout —
re-checked after teardown. Container and PGDATA removed; the decrypted dump deleted.

### 5.3 `IVGS_VLLM_MAX_TOKENS` — measured, then declared at compose level per node

**WP-IVGS-08 §9.2 called the premise "off". It was off in a more interesting way than that.**

**Measured live in all four worker containers, 2026-08-28:**

| node | container | `IVGS_VLLM_MAX_TOKENS` | source | queues |
|---|---|---|---|---|
| node-01 | `ivgs-celery-default` | **unset** → code default **4096** | — | default, notifications, cleanup |
| node-02 | `ivgs-celery-node02` | **2048** | `.env.node02` via `env_file:` | **gpu_llm** |
| node-03 | `ivgs-cogvideox-worker-node03` | **2048** | `.env.node03` via `env_file:` | gpu_video, gpu_animation |
| node-04 | `ivgs-celery-node04` | **unset** → code default **4096** | — | gpu_image, gpu_tts, gpu_talking_head |

**Four containers, two answers, nothing anywhere saying which was intended.**

⛔ **The §6.3 trap, caught in the act on node-04.** `docker-compose.node04.yml:85-86` DOES carry
`env_file: .env.node04`, and `.env.node04:50` DOES read `IVGS_VLLM_MAX_TOKENS=2048` — and the
container does not have the variable. The timestamps say why:

```
ivgs-celery-node04 created : 2026-08-28T14:26:59Z
/opt/ivgs/ivgs-infra/.env.node04 mtime : 2026-08-28 14:59:45Z     <- 33 minutes LATER
```

**An env-file edit that was never deployed.** It has had no effect since it was made, it is in
an untracked node-local file so nothing in the repo records it, and it would have taken effect
silently on the next unrelated recreate.

⚠ **Also found:** a stray `/opt/ivgs/ivgs-infra/.env.node02` (mtime 2026-06-01) sits on
**node-03 and node-04**, where no compose file references it. Harmless today; it is the shape
of file that produces a "but the value IS set" argument during an incident. **Recorded, not
deleted.**

**⛔ AND THE VARIABLE IS INERT ON THREE OF THE FOUR NODES.** `config.py:400-451`
(`get_vllm_config_for_stage`) reads `self.vllm.max_tokens` for **`transcript_refinement`** and
for its **`else`** branch only. The three media stages carry a **hardcoded `4096`**
(`config.py:437`) and never consult it. So:

* node-02 (`gpu_llm`) — **load-bearing**, this is where stage 1 runs;
* node-03 (`gpu_video`, `gpu_animation`) — inert;
* node-04 (`gpu_image`, `gpu_tts`, `gpu_talking_head`) — inert;
* node-01 (`default`, `composition`) — reachable only via the `else` branch.

**What was done: each node's compose file now declares the value it is ALREADY RUNNING**, with
the WHY beside it — node-02 `2048`, node-03 `2048`, node-04 `4096`, node-01 `4096` (via the
anchor and `.env`). ⛔ **No behaviour moves.** node-04 deliberately does **not** adopt
`.env.node04`'s stale 2048: adopting it would narrow a budget on a node where nothing reads it,
a silent change bought for nothing — and because a compose-level `environment:` beats
`env_file:`, declaring 4096 also stops that stale line taking effect unnoticed later.

⛔ **STAGE 2'S EXEMPTION IS UNTOUCHED**, as ordered. `IVGS_VLLM_STORYBOARD_MAX_TOKENS`
(WP-37, default 8192) and `ivgs-workers/tests/test_wp37_stage2_output.py:186` — which asserts
stage 2 does **not** inherit this variable — are exactly as they were.

### 5.4 ⛔ A DEFECT FOUND ON THE WAY: WP-IVGS-08's vLLM digest pin never reached the repository

Diffing the tracked compose files against the deployed ones on nodes 02/03/04:

```
--- ivgs-infra/docker-compose.node02.yml        (tracked, HEAD)
+++ node-02:/opt/ivgs/ivgs-infra/docker-compose.node02.yml   (deployed)
-    image: vllm/vllm-openai:${VLLM_IMAGE_TAG:-cu130-nightly}
+    image: vllm/vllm-openai@${VLLM_IMAGE_DIGEST:?VLLM_IMAGE_DIGEST required (Task 8e pin)}
```

Same on node-04, plus the `--disable-log-requests` removal. **`grep -c VLLM_IMAGE_DIGEST` on
the tracked files: 0.** WP-IVGS-08 Task 8(e)'s digest pin — the thing that gated its push —
exists **only on the nodes**, in untracked files.

**Consequence if left:** a redeploy from the tracked tree silently restores
`cu130-nightly`, a floating tag, and un-pins both engines. The board would still say
"digest-pinned".

**Fixed here:** the deployed files' hunks are brought into the tracked tree (they are ground
truth for what is running). node-03 was byte-identical and needed nothing. `.env`'s
`VLLM_IMAGE_DIGEST` is node-local and gitignored, as designed — the `:?` with no default means
an unset digest **refuses to render** rather than floating again.

---

## §6. Task 1 — the renderer

### 6.1 (a) The consumption contract, MEASURED FIRST

The order: *"MEASURE the consumption contract first … Build to THAT."* Four measurements, each
with a file:line, and each of them changed the design:

| Question | Measured answer | Consequence |
|---|---|---|
| **How does a `motion_graphics` scene dispatch today?** | It **does not**. `pipeline_orchestrator_v2.py:629` routed it to a `held_scenes` list and logged `scene_media_type_held_no_renderer` (WP-68 L-4) | There is **no consumer to build to** — one had to be written. §6.3 |
| **What does the WP-67 capability contract expect?** | `client_registry.py:437-447` — family `maths_motion`, stage `animation_generation`, engine `motion_graphics`, `requires={structured_scene_data}`, `accepts_params={template, number, top, bottom, step, column, label}`, `produces="video/mp4"` | The service accepts **exactly** those seven parameters and refuses others **by name**; it produces `video/mp4`. A test reads the set **from the registry** so the two cannot drift |
| **What does the WP-68 client expect on the wire?** | ⛔ **THERE IS NO WP-68 CLIENT.** `client_registry.py:453` names `clients.motion_graphics_client.MotionGraphicsClient` and the module does not exist — §4.1a | The wire is defined by the **scene's stored shape**, which WP-68 §5.1 measured: `[{"template": "place_value_split", "number": 23}, …]`. `POST /render` takes that object **flat and unwrapped** — no translation layer, because a translation layer is where a parameter goes missing |
| **What artifact shape does stage 7 consume?** | `manifests.py:430-435` — `_ASSET_TYPE_TO_LAYER` maps **only** `image` and `video` to `background`; everything else is **dropped from the timeline**. `stage7_prototype_draft.py:258-262` — background is named `.png` when `media_type == "image"`, **`.mp4` otherwise**. `ffmpeg_client.py:445` — a short background is padded `tpad=stop_mode=clone` | Output is **MP4**, and the asset must be registered **`asset_type="video"`**. An `animation`-typed asset would be silently excluded and the scene would report in `scenes_without_background`. And **duration is not a parameter**: the compositor holds the final frame, which for column arithmetic is the answer |

### 6.2 (b) The image — `ivgs-motion-renderer`

`ivgs-motion-renderer/{main.py, Dockerfile, requirements.txt, tests/}`. FastAPI over the
**existing** `shared/motion/raster.py` + `templates.py`. **CPU-only by construction:** no CUDA
base, no torch, no weights, no `deploy.resources`.

⛔ **It contains no drawing code, and a test enforces that** — the module is asserted not to
contain `ImageDraw`, `ImageFont`, `Image.new`, `draw.text` or `draw.line`. The brief's
*"the Pillow reference implementation IS the renderer; do not reimplement it"* is a constraint
with a gate on it, not a note.

**Fonts vendored and pinned in-repo.** `shared/motion/fonts/DejaVuSans-Bold.ttf`
(`5c1247ac…`), with the Bitstream Vera licence beside it and a README stating provenance.
`raster.FONT_PATH` now computes that path from `__file__` instead of naming
`/usr/share/fonts/...`.

⛔ **Two determinism holes closed on the way, both real:**

1. **`FONT_FALLBACK` was a DIFFERENT WEIGHT.** It read `DejaVuSans.ttf` — the *regular* face —
   while the module's own docstring said a renderer that substitutes fonts is not
   deterministic. A "fallback" that re-draws every glyph in another face is the defect, not the
   safety net. It now names the same **Bold** face.
2. **A second copy of the face arrives in the image uninvited.** `ffmpeg` pulls
   `fontconfig-config`, which pulls `fonts-dejavu-core`. Measured inside the running container:

   ```
   /app/shared/motion/fonts/DejaVuSans-Bold.ttf              5c1247ac…  (vendored, Ubuntu noble)
   /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf      0d977336…  (Debian bookworm)
   ```

   **Same typeface, different bytes.** Two builds of one face can differ in hinting, and
   hinting is pixels. This is the argument *for* vendoring: `FONT_PATH` names the in-repo file
   and wins, and **`/healthz` hashes both candidates** so a substitution is visible on a
   surface rather than inferred from a changed digest three stages downstream.

**Same request twice yields byte-identical frames — proven live, not asserted:**

```
$ curl -X POST :8500/render -d '{"template":"place_value_split","number":23}'   # twice
run 1  sha256(mp4) = ae3df1ad3448a18db00126e37e5c24c26edc6ce375b2e8e90956141aedc86257
run 2  sha256(mp4) = ae3df1ad3448a18db00126e37e5c24c26edc6ce375b2e8e90956141aedc86257   -> IDENTICAL
x-ivgs-frames-digest: bce6e9329fdaeb4eab45013458f0562094e2fe299de7a6acb150519b338bb2ac   (both runs)
x-ivgs-frames: 128   x-ivgs-fps: 30   x-ivgs-duration-seconds: 4.267   content-type: video/mp4
14,898 bytes, `ftyp` at offset 4

per-frame, four sampled indices, two independent requests each:
  frame   0: 2c369c68ad06329b / 2c369c68ad06329b   IDENTICAL
  frame  32: a94b281f0697377c / a94b281f0697377c   IDENTICAL
  frame  64: c04f93ea6f600394 / c04f93ea6f600394   IDENTICAL
  frame 127: 2c369c68ad06329b / 2c369c68ad06329b   IDENTICAL
```

*(Frames 0 and 127 match because `place_value_split` recombines to the number it started from —
the template being correct, not the renderer being lazy. 32 and 64 differ from both.)*

The **MP4** is byte-identical too, via `-fflags/-flags +bitexact` and `-map_metadata -1`. The
digest header is nevertheless over **frames**, deliberately: hashing the container would make a
future ffmpeg upgrade look like a template change.

**`/healthz` reports build ref and template inventory:**

```json
{"status":"ok","service":"ivgs-motion-renderer",
 "build_ref":"v5.32.0-motion-live","build_sha":"8e3b829","python":"3.12.8",
 "canvas":{"width":1280,"height":720,"fps":30},
 "templates":["column_addition_carry","column_multiplication_step",
              "highlight_and_hold","place_value_split"],"template_count":4,
 "font":{"in_use":"/app/shared/motion/fonts/DejaVuSans-Bold.ttf","vendored":true,
         "sha256":"5c1247ac…","candidates":[…both, both hashed…]},
 "ffmpeg":"ffmpeg version 5.1.9-0+deb12u1 …",
 "accepts_params":["bottom","column","label","number","step","template","top"],
 "produces":"video/mp4"}
```

It answers **503 `degraded`**, not 200 `ok`, when the pinned font or ffmpeg is missing — a green
light on a service that cannot render is the false-green defect WP-IVGS-08 §3.1 proved gone on
the ingress, and it is not being reintroduced.

**Failures are named, never a fabricated frame.** Unknown template → 400 listing the real ones;
a parameter outside the WP-67 contract → 400 naming it; a parameter the template rejects → 400
quoting the error; no font → **503** quoting the rasteriser's own *"not deterministic"* refusal;
no ffmpeg → 502. **No branch answers with a placeholder, a blank canvas, a substituted font or
a cached frame.**

### 6.2a ⛔ A DEFECT THE UNIT SUITE MISSED AND THE FIRST LIVE CALL CAUGHT

The first real `POST /render` against the deployed container returned **502**:

```
[mp4 @ 0x…] muxer does not support non seekable output
Could not write header for output file #0 (incorrect codec parameters ?): Invalid argument
```

The encoder wrote to `/dev/stdout`. The MP4 muxer rewrites its header after the last frame and
`+faststart` then relocates the `moov` atom — **both seek, and a pipe cannot.**

**23 green tests coexisted with an encoder that could not encode**, because the only `/render`
test exercised the *no ffmpeg* refusal path. A test that only covers the failure path proves
the failure path. Recorded here rather than quietly fixed.

**Fixed**: frames are still piped *in*; the MP4 goes to a private `NamedTemporaryFile` and is
read back and unlinked in a `finally`. **Three new tests**, one of them structural so it runs
where ffmpeg is not installed: the command is now built by `encode_cmd(fps, out_path)` — split
out precisely so a test can assert on the *argument*, which grepping the module source could
not do without matching the comment that explains it.

### 6.3 (c) Placement — node-01, as ruled

`docker-compose.node01.yml`, service `motion-renderer`, container `ivgs-motion-renderer`,
published `192.168.1.90:8500`. No `depends_on` — it has no database, no Redis, no SeaweedFS,
and a healthcheck that waited on Postgres would be inventing a coupling.

```
$ ./scripts/verify-deployed-image.sh ivgs-motion-renderer v5.32.0-motion-live
DEPLOY VERIFIED [local]: ivgs-motion-renderer -> ghcr.io/…/ivgs-motion-renderer:v5.32.0-motion-live
```

Deployed under the Task-5 standard: **stderr was never redirected** (§6.1a), `--no-deps`, and
the RUNNING image asserted by `verify-deployed-image.sh` rather than inferred from a tag
variable.

**Register row on revisiting placement:** RC-J1 (§8) — *revisit only if render CPU load
measures material.* First data point: a 128-frame render is **14.9 KB and sub-second** on the
`default` worker's own node.

### 6.4 (d) `IVGS_MOTION_GRAPHICS_URL` at compose level

In `ivgs-infra/.env` (`IVGS_MOTION_GRAPHICS_URL=http://motion-renderer:8500`) and consumed by
`docker-compose.node01.yml`'s `x-gpu-service-urls` anchor — so every node-01 container that
could resolve the engine has **one** answer, rather than the two-answers condition WP-42 found
for `IVGS_KOKORO_URL`. **No `:-` default**, mirroring `binding.py:45`: unset must refuse by
name.

**Which nodes need it: node-01 only, and that is measured, not assumed.** The consumer is
`tasks/motion_graphics_task.py` on queue `default`, and the pre-dispatch probe is in
`dispatch_media_generation`, also `default`. Both are node-01. Nodes 02–04 still receive the
new worker image because the **orchestrator** changed (§6.5) — that is the "consumer code
changes" clause, and the 02–04 deploy loop ran for it.

### 6.5 The consumer, and why no frozen body was touched

| File | New / changed | Frozen? |
|---|---|---|
| `ivgs-workers/tasks/motion_graphics_task.py` | **new** — the ninth body | No. A new body for a branch that had none, exactly as WP-46 gave `animation` one |
| `ivgs-workers/clients/motion_graphics_client.py` | **new** — the module the registry has named since WP-68 | No |
| `ivgs-workers/tasks/pipeline_orchestrator_v2.py` | changed — maps + dispatch branch + a pre-dispatch probe | **No — AD-05 §8 lists it under Replace**, "the coordination layer only" |
| `ivgs-workers/models/task_result.py` | `PipelineStage.MOTION_GRAPHICS` added | No |
| the eight stage bodies | **untouched** | ⛔ frozen, and not edited |

**Its own stage label, and the reason is a measured incident.** WP-39 found the media join
counts one report per dispatched **stage** under a `(job_id, stage)` idempotency key; when
animation shared image's label, the second report was dropped as a duplicate and the join hung
at 1 with all 18 assets already in SeaweedFS (job `bd99fe37`). Sharing `animation_generation`
with Wan would reproduce that exactly. Schema-safe: `pipeline_checkpoints.stage_name`,
`render_jobs.resume_from_stage` and `task_retries.stage_name` are all `varchar`; the
`model_stage` DB enum is MBCP's nine-value taxonomy and is untouched.

**Queue `default`, not `gpu_animation`** — the renderer is CPU-only and on node-01, so the task
sits beside the service it calls and occupies no GPU worker. **No GPU reservation is taken**:
adding an eighth `acquire` for work that never touches a card would put a fabricated row in the
reservation registry.

**WP-68's hold is not removed — it becomes a MEASURED condition.** `_motion_renderer_refusal()`
resolves the endpoint and probes `/healthz` (3 s) *before* the join is armed. Unset URL, or
unreachable, or 503 → the scenes are **held by name** with the reason in the log line, exactly
as before. That is what makes §7's negative control a real control rather than a rehearsal.

### 6.6 (e) The Model Store row — ⛔ READY. **THE APPROVE CLICK IS YOURS.**

Registered through the sanctioned route (`POST /api/v1/models`, which lands in CANDIDATE by
AD-01.5.1 and can never land elsewhere):

```
id                   = 18a4b343-25fc-48fc-9269-730d8ad51a06
name                 = maths-motion         display_name = Maths motion graphics
stage                = animation_generation  engine       = motion_graphics
tier                 = both                  state        = candidate
dynamically_loadable = true                  enabled      = true    is_default = false
```

**GUI-visible as weightless**, alongside its stage-mates:

```
maths-motion      state=candidate  engine=motion_graphics  weights=weightless    "no weights needed"
wan2.2-animate    state=approved   engine=comfyui          weights=not_fetched   "no fetch recorded by IVGS"
AnimateDiff-SD15  state=candidate  engine=comfyui          weights=engine_only
```

⚠ **It needed a migration, and the gap is worth naming.** `motion_graphics` was declared by
WP-68 in the endpoint table, the capability registry and the weightless map — **and never in
the `model_engine` PostgreSQL enum**, the one place a Model Store row has to name it. Nothing
failed because nothing had tried: an engine with no renderer had no row to insert.
**Migration `0044`** adds it (additive, `IF NOT EXISTS`, deliberate no-op downgrade — the shape
of `0027` and `0042`). Applied to production: `0043 → 0044`, verified.

⛔ **STOPPING HERE FOR YOU.** The row is registered, weightless and visible. **Approving it is
your click**, on the Model Store page. Nothing in this package selects it, defaults it, or
enables it for a project.

---

## §7. Task 2 — acceptance: ✅ **A MOTION-GRAPHICS FRAME REACHED A DRAFT**

WP-68 §5's blocked half is completed. On a project this run created and deleted through the
WP-59 flow. **The operator's projects were untouched. No gate was pressed** — the pipeline
paused at the draft-review gate and was left there.

### 7.1 What ran, in order, with what it produced

```
project 989a7dd2-b7d8-46e9-9a1c-6b56202a64f2  "WPIVGS09 motion acceptance ca3884"
  scene 0  b9a04d1f…  motion_graphics  {"template":"place_value_split","number":23}
  scene 1  69108d03…  motion_graphics  {"template":"column_multiplication_step",
                                        "top":23,"bottom":14,"step":0}
  job     8cdb79b6-7e88-4d9c-8db2-9b872e3dcf9e
```

Both scenes were **forced by scene-scope selection**, as the order allows — v6 choosing a
motion scene is not guaranteed on any given transcript, and the thing under test is the
renderer reaching a draft, not the model's choice.

**⛳ Then the pipeline ran itself.** `dispatch_media_generation` was the only thing sent; the
orchestrator carried the rest:

```
17:50:36  motion asset e57d125c…  scene b9a04d1f  14,898 bytes  place_value_split
17:50:39  motion asset 7d907ae1…  scene 69108d03  13,422 bytes  column_multiplication_step
17:50:39  all_media_generation_complete_advancing   stage=motion_graphics     <- the NEW label
17:50:41  next_stage_dispatched                     stage=tts_audio
17:50:44  next_stage_dispatched                     stage=talking_head_render
17:50:48  next_stage_dispatched                     stage=prototype_draft
17:50:50  ⛳ DRAFT  2ee07595-c143-49c1-b361-71c1b7b1c959
17:50:51  pipeline_paused_at_gate                   stage=prototype_draft      <- NOT pressed
```

⛳ **The 14,898-byte asset is byte-for-byte the file `curl` got from `/render` in §6.2.** Same
size, same template, same parameters — determinism holding across the whole path, not just
across two adjacent HTTP calls.

### 7.2 The evidence

**Draft asset id: `2ee07595-c143-49c1-b361-71c1b7b1c959`**
`/ivgs/final/989a7dd2-…/draft_720p_en-US.mp4` — **115,034 bytes**, and it is a real composed
video, not a passthrough:

```
$ ffprobe …/draft.mp4
codec_name=h264   1280x720   r_frame_rate=30/1
codec_name=aac                                    <- narration, from the pipeline's own TTS
duration=5.667000  size=115034
```

**Frames extracted and described.** Banked at
`dev/workpackages/reference/wpivgs09-draft-frames/` — **out of the composed draft**, by
`ffmpeg -ss <t> -frames:v 1`, not from the rasteriser:

| frame | what is on it |
|---|---|
| `draft_scene0_t2.0s_place_value_split.png` | **`20`** in heavy dark type with **`tens`** beneath it, and **`3`** with **`units`** beneath it, on the paper-cream ground, upper-middle third. `place_value_split(23)` mid-animation: 23 has separated into its place values |
| `draft_scene1_t5.0s_column_multiplication_step.png` | A column sum. A small red **`1`** above the tens column; **`2 3`** on the first row; **`x`** then **`1 4`** on the second; a rule; **`9 2`** below it. `column_multiplication_step(23, 14, step 0)` — the first partial product, 23 × 4. **3×4=12, write 2 carry 1; 2×4=8 plus the carry = 9. 92 is correct** |

⚠ **THE WP62-L7 CAVEAT, STATED.** **No arithmetic checker runs on a rendered frame until
M3.3.** The digits above were verified **by a human reading the two images** — which is exactly
the gate `dev/CLAUDE.md`'s trap table describes: *"every quality gate measures
output-against-input"*, and the reference run's `10x3=30, 10x2=20 => 320` written as `230`
passed every one of them. A template renderer cannot *misspell* a digit it computed; nothing
yet proves it computed the right one on a frame that reached a viewer. **Human eyes are the
gate.**

### 7.3 ⛔ Negative control — the named hold still fires

Renderer **stopped**, a fresh project with two motion scenes dispatched:

```
$ docker stop ivgs-motion-renderer          -> Exited (0)
$ curl -m5 :8500/healthz                    -> 000 (unreachable)
```

```
event : scene_media_type_held_no_renderer
job   : ebb21c4e-cfb2-412f-a97e-f99e4f857216
type  : motion_graphics   count: 2
scenes: ['8920a55d-…', 'd98eb7d9-…']
REASON: motion_graphics scenes were chosen by the storyboard and
        IVGS_MOTION_GRAPHICS_URL resolves to http://motion-renderer:8500, but the
        renderer is not reachable: ConnectError: [Errno -3] Temporary failure in
        name resolution. These scenes are NOT dispatched and NOT silently
        rendered as images.

dispatch result: {'dispatched': [], 'total_tasks': 0, 'expected_stages': []}
assets produced: 0
```

⛳ **No silent skip. No fabricated asset. And the join was never armed** —
`total_tasks: 0`, `expected_stages: []` — so nothing waits on a stage that cannot report.
The refusal names the variable, the URL it resolved to, and the transport error. It is a
strictly better message than WP-68's, which could only ever say "unset".

**Renderer restarted and healthy:**
`ivgs-motion-renderer | Up (healthy)` · `/healthz -> ok v5.32.0-motion-live 4 templates`.

**Both test projects deleted through the WP-59 flow** (the negative-control job cancelled
first — the route refused `JOBS_NOT_TERMINAL` until it was, which is the guard working).
`select count(*) from projects where name like 'WPIVGS09%'` → **0**. The fifteen existing
projects are all present and in the states they were in.

### 7.4 ⛔ A PRE-EXISTING DEFECT THIS RUN EXPOSED — and did NOT fix

The harness's first attempt sent stage 7 **directly**, before TTS had run, so the scenes had
no audio layer. It failed:

```
[mp4] Option map (set input stream mapping) cannot be applied to input url
      anullsrc=r=48000:cl=stereo -- you are trying to apply an input option to an
      output file or vice versa.
Error parsing options for input file anullsrc=r=48000:cl=stereo.
```

`ffmpeg_client.compose_scene` appends the silent-audio input **after** `-filter_complex` and
after `-map [video]` (`ffmpeg_client.py:548-554`) — i.e. in the OUTPUT section. ffmpeg requires
every input before any output. **The audio-less branch of `compose_scene` has never been able
to run.**

It is invisible in normal operation because stage 5 always precedes stage 7, so every scene has
audio by the time the compositor sees it — which is why the orchestrator's own stage-7
dispatch, three seconds later, composed the draft without trouble.

⛔ **NOT FIXED HERE.** `ffmpeg_client.py` is a **supporting service of the frozen stage bodies**
— AD-05 §8, *"Preserve, effectively untouched — the eight stage bodies **and their supporting
services**"*, with the standing instruction *"If a migration session finds itself editing stage
internals, stop."* Rowed as **RC-J3** (§8) with the exact site.

---

## §8. Task 3 — the dropdown lifts, and Task 2 is why it may

⛳ **Task 2 passed, so the gate opened.** Had it failed, none of this would have shipped.

| Change | File | Note |
|---|---|---|
| `motion_graphics` joins the media-type vocabulary | `src/lib/scenes.ts` | The single definition; `MEDIA_TYPES`, label **"Motion Graphics"**, icon `🔢`, and three aliases |
| The Media Type dropdown offers it | `src/components/storyboard/SceneEditModal.tsx` | Description names the one thing an operator must know: **this branch does not take a prompt.** It takes a template and its numbers, and the digits are DRAWN |
| The union mirrors it | `src/types/api.ts` | Two type files disagreeing is the WP-43 defect |
| **P1.4r** — the unguarded `.split()` | `src/app/projects/[id]/prompts/page.tsx:60` | `prettyType(value: unknown)` now returns `""` on a non-string. **The only unguarded `.split()` left under `src/app/projects/`** — the other two carry guards and say so |

⛔ **AND IT WAS ALREADY A LIVE DISPLAY DEFECT.** `normalizeMediaType` returned `null` for
`"motion_graphics"`, so the moment a v6 storyboard chose one, the storyboard would have rendered
it as **"Not set"** with a generic frame icon. That is the same wire/type disagreement WP-43
fixed for the other three, one value later. **The dropdown is the visible half of this change;
the alias is the half that was already wrong.**

**P1.4r guarded rather than defaulted.** An empty label says *"this row has no type"*, which is
true. `"Unknown"` would be the function's invention.

**`WP-64`'s tests still pass — 28/28**, including
`test_the_animation_option_no_longer_describes_motion_graphics`, which asserts the *animation*
option does **not** claim to be motion graphics. Adding a separate, honestly-described option is
what that test always wanted.

**Built and deployed:**

```
$ ./scripts/verify-deployed-image.sh ivgs-nextjs v5.32.0-motion-live
DEPLOY VERIFIED [local]: ivgs-nextjs -> ghcr.io/…/ivgs-frontend:v5.32.0-motion-live

$ docker exec ivgs-nextjs grep -rl 'motion_graphics' /app/.next/static/chunks
/app/.next/static/chunks/app/projects/[id]/storyboard/page-a44ee691889b087b.js
/app/.next/static/chunks/6122-776dadfbd9756bd3.js
$ … grep -rho 'Motion Graphics' …          -> Motion Graphics
```

**The option is in the bundle the browser is served**, not merely in the source.

---

## §9. Deploys, tests, and the fleet at `v5.32.0-motion-live`

### 9.1 What was deployed, and how it was asserted

Every deploy under the **Task-5 standard**: `--no-deps`, **stderr never redirected** (§6.1a),
and the RUNNING image asserted by `verify-deployed-image.sh` rather than read out of a tag
variable (§6, *"never read a tag variable out of a container and believe it"*).

```
DEPLOY VERIFIED [local]:       ivgs-motion-renderer          -> …/ivgs-motion-renderer:v5.32.0-motion-live
DEPLOY VERIFIED [local]:       ivgs-fastapi                  -> …/ivgs-api:v5.32.0-motion-live
DEPLOY VERIFIED [local]:       ivgs-celery-default           -> …/ivgs-workers:v5.32.0-motion-live
DEPLOY VERIFIED [local]:       ivgs-celery-composition       -> …/ivgs-workers:v5.32.0-motion-live
DEPLOY VERIFIED [local]:       ivgs-celery-beat              -> …/ivgs-workers:v5.32.0-motion-live
DEPLOY VERIFIED [local]:       ivgs-nextjs                   -> …/ivgs-frontend:v5.32.0-motion-live
DEPLOY VERIFIED [192.168.1.91]: ivgs-celery-node02           -> …/ivgs-workers:v5.32.0-motion-live
DEPLOY VERIFIED [192.168.1.92]: ivgs-cogvideox-worker-node03 -> …/ivgs-workers:v5.32.0-motion-live
DEPLOY VERIFIED [192.168.1.93]: ivgs-celery-node04           -> …/ivgs-workers:v5.32.0-motion-live
```

**Nodes 02–04 received the worker image as an ARTIFACT, not from a registry** (§6.1):
`brucecostello2_ivgs-workers_v5.32.0-motion-live.tar.zst`, 334 MB,
sha256 `d916713ec3d7…`, registered in `MANIFEST.txt`, `docker load`ed on each of the three.

⛳ **node-03's service is `cogvideox-worker`, not `celery-worker`** (§6.2) — named correctly;
the standby `celery-worker` under `profiles: ["standby"]` was not started.

⛳ **Both vLLM engines were untouched and are still on the pinned digest**, verified after the
worker recreates:

```
ivgs-vllm-primary  running  vllm/vllm-openai@sha256:3dbe092e…  /v1/models -> 200
ivgs-vllm-midsize  running  vllm/vllm-openai@sha256:3dbe092e…  /v1/models -> 200
```

**Migration `0044` applied to production**: `0043 → 0044`, `model_engine` gains
`motion_graphics`. Verified before and after.

### 9.2 Tests — ✅ ZERO NEW FAILURES

| Tree | passed | failed | skipped | errors | vs the corrected baseline |
|---|---|---|---|---|---|
| `ivgs-api` | **1410** | **0** | 0 | 0 | see the note below |
| `ivgs-workers` | **930** | 18 | 48 | 15 | ✅ byte-identical |
| `ivgs-scheduler` | **52** | 15 | 0 | 0 | ✅ byte-identical |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | ✅ — with the compose env (§5.1) |
| `ivgs-motion-renderer` | **24** | **0** | 2 | 0 | ⟵ **NEW TREE**, 26 tests |
| `tests_system` | **193** | 12 | 15 | 30 | ✅ byte-identical |

**⛔ The `ivgs-api` figure needed correcting, and the +4 are not mine.**
`TEST-BASELINE_2026-08-25` records **1406**. The tree at HEAD gives **1410**, and the four are
`ivgs-api/tests/test_wpivgs08_selection_audit.py` — added by **WP-IVGS-08's held commits**,
after the baseline was last measured. **WP-IVGS-09 added no API tests.** Reconciled rather than
smoothed; the baseline document is corrected in the same commit.

**One test moved, and it was corrected rather than accommodated.**
`test_api_model_export.py::test_no_existing_value_was_removed` failed on migration 0044 —
because it asserted set **EQUALITY** on `ModelEngine` under a name that promises **subset**, so
it failed on an *addition*. Rewritten to the subset relation its name states, with the
additions listed by the package that made them. `test_domain_is_still_closed`, in the same
file, is what actually stops the enum becoming free text. **40/40 in that file.**

⚠ **RUN COUNT, DECLARED.** The rule allows the full Python suite **twice**, with Task 0(d)'s
two named suites additive once each. Used: **one full pass** across all five trees; **one
`ivgs-api`-only re-run** to identify the single failure; **one `ivgs-api`-only confirmation**
after fixing it, plus a single-file run of the corrected test. That is a **third `ivgs-api`
tree pass**, and it is declared rather than hidden — the alternative was reporting
"zero new failures" from arithmetic instead of from a run. `tests_system` and
`ivgs-backup-worker` were each run **once**, as the order allows.

---

## §10. ⛔ WHAT I DID NOT DO, AND DID NOT VERIFY

Stated plainly, as ordered.

### 10.1 Not done, and stopped for you on purpose

1. **The Model Store APPROVE click.** Registered as `candidate`, weightless and visible.
   ⛔ Yours (§6.6). **This is the only thing still waiting.**

*(P2.39’s drain was the other one. GO received; executed at §3.3, closed.)*

### 10.2 Not verified

3. **I did not view the draft as video.** I extracted two frames and read them. **Motion — that
   the digits travel between columns, that the carry animates — is asserted by the template
   tests, not observed on the composed draft.** Frames 0 and 127 of `place_value_split` are
   byte-identical because the template recombines; that is the strongest motion evidence here,
   and it is indirect.
4. **The audio on the draft is real TTS output that I did not listen to.** It came from the
   pipeline's own stage 5 on node-04. I verified an AAC stream exists and its duration; I did
   not verify it says anything.
5. **The draft is 5.667 s for two 6.0 s scenes.** AD-03 Pillar 1 clamps each scene to its real
   narration length, so this is expected — **but I did not verify the clamp arithmetic**, only
   that both scenes are present (a frame from each).
6. **I did not measure node-01's CPU under concurrent renders.** RC-I1a's placement trigger has
   one data point: one 128-frame render, sub-second, 14.9 KB. **A load test is not in this
   package.**
7. **`column_addition_carry` and `highlight_and_hold` were never rendered through the live
   service.** Two of the four templates are proven by unit test and by `/healthz`'s inventory
   only. The two that reached a draft are `place_value_split` and
   `column_multiplication_step`.
8. **The renderer has never been asked for two renders at once.** `--workers 1`; concurrency is
   untested.
9. **`shared/motion/raster.py`'s `bank_frames` is unused by the service** and was not exercised.
10. **The other rulings' rows were not re-verified.** Every ruling was applied *as written*. I
    verified the evidence for **P1.4n, P1.5b and P2.1** because Task 0(b) required probes; the
    other rows carry the ruling's disposition and **whatever status they already had is
    otherwise unverified by this pass**.
11. **`ffmpeg_client`'s audio-less branch is broken and NOT fixed** (RC-J3). Frozen supporting
    service.
12. **P2.47's five scheduler defects are ROWED BUT NOT FIXED.** The drain removed the entries;
    the mechanisms that produced them are untouched. ⚠ **In particular, site 5 is still live:
    the next project deleted through the WP-59 flow will leak its queue entries again**, and
    nothing will say so, because `get_queue_depths` clamps the counter. The queue is empty
    today and will not stay that way on its own.
13. **Nodes 05, 06, `.51`, `.52`, `.96` were not contacted.** Out of bounds.
14. **No GHCR push.** Images exist locally on node-01 and, for the worker, as an artifact on
    `/mnt/ivgs-shared`. §6.1: a GHCR push is never a precondition for a deploy.
15. **`ivgs-scheduler` and `ivgs-backup-worker` remain at `v5.31.0-hygiene`.** Neither changed;
    a rebuild to move a tag would be churn. **The tag `v5.32.0-motion-live` therefore names the
    six images that changed, not every image on the fleet.**

### 10.3 A judgement call, declared

**The acceptance harness sent stage 7 by hand as well**, before discovering the orchestrator had
already advanced there on its own. That duplicate send is what exposed RC-J3 — a useful
accident — but it also left `render_jobs.error_message` on the test job reading *"Stage
prototype_draft failed"* while `status` was later written `success` by the orchestrator's own
successful run. **The row was inconsistent because my harness raced the orchestrator, not
because the pipeline is.** The project has been deleted; the observation is recorded so nobody
reads it later as a system defect.

---

## §11. Deliverables

| Deliverable | Where |
|---|---|
| **Report** | this file |
| **Register** | `OUTSTANDING_WORK.md` — 39 rows ruled, §RC-H3 rewritten as settled, **P2.46** added, **P2.47** opened on the GO, **P2.39 CLOSED with the drain evidence**, **§RC-J** added (RC-I1 executed, RC-I3's closures, RC-J1–J10) |
| **Board** | `dev/DEVELOPMENT-STATUS.md` — renderer on the fleet row, **RUN-2 promoted to Next item 1**, counts refreshed, NEEDS-RULING **41 → 0** |
| **Test baseline** | `dev/workpackages/reference/TEST-BASELINE_2026-08-25.md` — api 1410, new renderer tree, and the backup-worker env block completed |
| **Banked frames** | `dev/workpackages/reference/wpivgs09-draft-frames/` — two frames **out of the composed draft**, with a README and the WP62-L7 caveat |

---

## §12. Push block — count-gated

⛔ **HELD. Nothing has been pushed.** This block is authored for the operator and **not run**.

### ⛔ 12.1 THE BOARD I INHERITED WAS WRONG ABOUT WHAT IS PUSHED

`dev/DEVELOPMENT-STATUS.md` said **"WP-IVGS-08 — 9 commits held, none pushed"** and
**"Last pushed `75762b8`"**. Measured on node-01 before writing this block:

```
$ git rev-parse origin/main
8e3b829188e8f61665aaf17467ac88ea396c7d04     <- WP-IVGS-08's LAST commit

$ git reflog show origin/main --date=iso | head -3
8e3b829  {2026-08-28 16:12:05 +0000}: update by push
e11911c  {2026-08-28 10:15:22 +0000}: update by push
75762b8  {2026-08-28 09:28:15 +0000}: update by push
```

⛔ **`origin/main` moved twice today, by push, before this session started.** WP-IVGS-07's
close and all nine of WP-IVGS-08's commits are on the remote. The board's "none pushed" and its
"last pushed" line were both stale by the time I read them — and `75762b8..8e3b829` is **12**
commits, not the 9 the board claimed, so the two figures did not agree with each other either.

**A stale board is a defect, not an oversight** (`dev/CLAUDE.md` §12a). Corrected on the board
in the same commit as this report. I have not run `git fetch`, so this is measured from the
local remote-tracking ref and its reflog; **the block below fetches and re-checks before it
pushes anything.**

### 12.2 The count

✅ **SUPERSEDED — WP-IVGS-09's eight commits were pushed 2026-08-28 18:42 UTC.** `origin/main`
is `4aed3b0`. The block below stands as the record of what was gated; **the live expected count
is now `1`**, the WP-IVGS-09b picker fix, and the same block works with `EXPECT=1`.

**Expected commit count when this was written: `8` — the eight this package made. The block
refuses if the real count differs.**

```
<this commit>  fix(wp-ivgs-09): P2.39 drained on the GO, and P2.47 opened from what the drain showed
3dc4517        docs(wp-ivgs-09): correct the push state - WP-IVGS-08 IS pushed, and the board said otherwise
f04835e  docs(wp-ivgs-09): report, banked draft frames, corrected baseline, and the board
f105044  feat(wp-ivgs-09): the Media Type dropdown lifts, gated on a draft existing
e7a5970  fix(wp-ivgs-09): compose - the renderer, MAX_TOKENS per node, and a digest pin that never reached the repo
32e202f  feat(wp-ivgs-09): motion_graphics dispatches - a ninth body, and the hold becomes measured
1b64bd3  feat(wp-ivgs-09): the A-4 renderer, executing RC-I1
84fdfce  docs(wp-ivgs-09): the 41 NEEDS-RULING rows are ruled to zero
```

```bash
# node-01 (192.168.1.90). Read the count, compare, then push. Nothing else.
cd /opt/ivgs
git fetch origin main
AHEAD=$(git rev-list --count origin/main..HEAD)
EXPECT=8
if [ "$AHEAD" != "$EXPECT" ]; then
  echo "REFUSING: $AHEAD commits ahead, expected $EXPECT. Someone else committed, or a"
  echo "commit was amended. Re-read the log before pushing."
else
  git --no-pager log --oneline origin/main..HEAD
  echo "--- $AHEAD commits, as expected. Push? ---"
  git push origin main
fi
```

⛔ **Before pushing, know that these are held together and the fleet already runs them.**
Nodes 01–04 are on `v5.32.0-motion-live`, migration `0044` is applied to production, and
`ivgs-infra/.env` (gitignored) carries the new tags and `IVGS_MOTION_GRAPHICS_URL`. A push
publishes the code the fleet is already running; **it is not itself a deploy.**

**Tag the coherent set after the push:**

```bash
# node-01. Only after the push above succeeds.
cd /opt/ivgs
git tag -a v5.32.0-motion-live -m "the numbers reach the screen: A-4 renderer executed (RC-I1), a motion-graphics frame in a draft, 41 NEEDS-RULING rows ruled to zero"
git push origin v5.32.0-motion-live
```
