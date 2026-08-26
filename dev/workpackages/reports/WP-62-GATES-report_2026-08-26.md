# WP-62-GATES — the gates the spec always had, one progress display, and the fleet page that finally shows the fleet

**Date:** 2026-08-26 · **Node:** node-01 (192.168.1.90) · **Branch:** `main`
**Commits:** 9, **COMMITTED AND HELD. Nothing pushed.**
**Deployed to node-01:** `ivgs-api:v5.21.0-gates`, `ivgs-frontend:v5.21.0-gates`
**Migration:** 0035, applied to `ivgs` and to `ivgs_reconciliation_test`

---

## 0. The one page worth reading first

Four of this package's nine tasks turned out to be about something other than
what they looked like. That is the useful part of the report.

| Task | What it looked like | What it measured to be |
|---|---|---|
| 3 | "nothing advances `projects.state`" | The writer exists and works. **A stale job's failure callback was walking projects back to DRAFT mid-run**, and every stage hop after that was refused as an illegal transition out of DRAFT. Three 409s in the log, 90 seconds apart. |
| 5 | "`PROJECT_DELETE_COMPLETED` must update the originating row" | **It already does, on all fourteen recorded deletions.** What was missing is any way to READ that: the obvious field says "pending" forever. |
| 8(e) | "the baked seed template differs from the tree" | **It does not.** `205ddaba` and `67be5991` are the same bytes with and without a trailing newline, printed under the same label five lines apart. |
| 9(b) | "expect the two false positives gone and the genuine five remaining" | The two ruled false positives ARE gone and all five genuine flags remain — **and two NEW false positives appeared.** Seven flags before, seven after. |

And one that was exactly what it looked like, for the third time:

| 1 | The GPU Fleet page drew the scheduler's registry and called it the fleet. Two previous packages relabelled the tile. The page now draws all five GPUs. |

**Live data changed: exactly two things.** Prompt v3 was published (v2 preserved
inactive) and variant `3fccf815` was re-translated. Every project's `state` and
`updated_at` is byte-for-byte as found, `en-US` is still `pending`, and no
stored project state was hand-edited anywhere.

**Zero new test failures.** 1955 → 2053 passed; failed, skipped and errors
unchanged in all five trees. Eighteen existing tests updated, none weakened —
the per-test accounting is in §11 and in the baseline itself.

**Two decisions needed** (§14): the full engine digest, and whether to iterate
the translation prompt to v4.

---

## 1. What was measured before anything was written

Every figure below is from the running system on 2026-08-26, not from reading.

| Question | Answer, measured |
|---|---|
| Does the "Approve storyboard" button exist? | Yes. `storyboard/page.tsx:431` → `POST /projects/{id}/scenes/approve?tier=` → `ProjectService.approve_storyboard` (`project_service.py:522`). |
| What does it write? | `projects.state = 'MEDIA_GENERATION'`. Nothing else. Zero rows anywhere. |
| Who reads that decision? | **Nobody.** No table, no column, no query. |
| Did media generation run unapproved? | Project 64207933, `09:07:47.255Z`: *"Storyboard approved … scenes=9 prev_state=STORYBOARD_GENERATION celery_task=36498351"*. Nine scenes to GPU work; the only trace is that log line and a state column overwritten 0.4 s later. |
| Does anything advance `projects.state`? | Yes. `{"new_state": "STORYBOARD_GENERATION", "event": "project_state_advanced"}`, 09:00:36, HTTP 200. |
| Then why is the stepper frozen? | Three 409s: `MANIFEST_GENERATION` 09:07:49, `AUDIO_GENERATION` 09:07:53, `TALKING_HEAD_RENDER` 09:08:24 — all *"Invalid state transition: DRAFT → …"*. |
| How many deletion audit rows are unclosed? | Zero. 14 of 14 are `PROJECT_DELETE_COMPLETED` with `after_payload.purge_state = 'complete'`. |
| Does the image's `translation.j2` differ from the tree? | No. Both `67be5991ad4819…`. |
| Which vLLM models claim runtime loading? | `test-model-1` and `Llama-3.3-70B-Instruct`. The other two were already `false`. |
| Does node-05 report telemetry? | Yes: 42694 MiB used, 37 °C, 14.07 W. It always did; the GPU page just never asked. |

---

## 2. TASK 1 — every GPU, and why relabelling was never going to be the answer

### 2.1 The defect, stated precisely

`GET /gpu/nodes` reads through to the scheduler's registry (WP-45 Task 4(b)).
A node enters that registry by running a **Celery worker** that calls
`POST /register`. node-05 runs vLLM; node-06 runs the CLIP scorer. Neither runs
a Celery worker, deliberately, and neither ever will under AD-02.

So the one source the page read **could not contain them by construction.**
WP-57 Task 4 and WP-60 Task 2 each made a tile say which of three defensible
numbers it was — 6 machines, 5 GPUs, 3 scheduler workers. Both were correct.
Neither put a missing GPU on the page.

### 2.2 What was built

`GpuService._fleet_views` unions the scheduler's fleet with every
`total_vram_mb > 0` row in the fleet topology. Four fields carry the
distinction so no surface has to infer it: `in_scheduler`, `role`,
`supports_drain`, `device_used_vram_mb` / `device_total_vram_mb`.

Live from the deployed API:

```
node-02  sched=True   dev_vram=88494/97887  resv=0  temp=31.0  GPU LLM (fp8 Llama-3.3-70B)
node-03  sched=True   dev_vram=None/97887   resv=0  temp=None  GPU Video (CogVideoX/Wan2.1)
node-04  sched=True   dev_vram=49108/97887  resv=0  temp=87.0  GPU Image + TTS + Talking Head
node-05  sched=False  dev_vram=42694/48935  resv=0  temp=37.0  GPU LLM (Qwen3.8-27B-FP8, translation)
node-06  sched=False  dev_vram=964/16303    resv=0  temp=35.0  GPU Video + Compositor + LLM failover
```

Header: **"5 GPUs — 3 scheduler workers"**, both counts off ONE payload, so they
cannot drift the way two tiles reading two endpoints did.

### 2.3 Physical VRAM is on the card now, and it is a different number

The only VRAM figure on this page was the scheduler's **reservation**. That is
why it showed node-02 at 0.0 GB while Node Monitor — same Prometheus, same
instant — showed 86.4 GB. WP-60 correctly relabelled it; the number still was
not a device reading, because the source could not produce one.

`nvidia_smi_memory_used_bytes` was already being collected by
`collect_fleet_health`; nothing surfaced it here. Both figures are now on the
payload, each labelled, and the card prints one provenance line.

**node-05's near-full card renders neutral and captioned as a resident model.**
It idles at 42.7 of 47.8 GB because vLLM pre-allocates its KV cache at
`--gpu-memory-utilization 0.90`. Painting that red would train the operator to
ignore the colour.

### 2.4 Two deliberate non-changes

`/gpu/utilization` **stays the scheduler subset.** It is reservation accounting
and admission control reasons about it; node-05's 48 GB is not capacity it may
spend, and adding it would inflate that denominator.

Drain on a non-scheduler node is **409 `DRAIN_NOT_APPLICABLE`, not 404** — the
node exists and the page draws it — and the card does not render the button.
Silently succeeding would be worse: the operator would believe they had stopped
work reaching a node that never received any.

### 2.5 Two hardcoded lists deleted

`NODE_TOPOLOGY` moved to `app/core/node_topology.py` (re-exported from
`api/v1/nodes.py`; four test modules import it from there). The frontend's
`GPU_LABELS` and `NODE_IDS` are **gone** — a hand-maintained sixth statement of
the fleet's hardware that was wrong twice: WP-53 found all five rows naming
cards not in this fleet under a comment citing "§3.2", and the corrected list
then still carried node-04 at 96 GB against the API's 48 GB (WP-53 D-2).

---

## 3. TASK 2 — the gates: what the button did, and what refuses now

### 3.1 (a) What it did, reported before the fix

| | |
|---|---|
| surface | `ivgs-frontend/src/app/projects/[id]/storyboard/page.tsx:431` |
| endpoint | `POST /api/v1/projects/{id}/scenes/approve?tier=` (`storyboard.py:232`) |
| body | `ProjectService.approve_storyboard` (`project_service.py:522`) |
| writes | `projects.state = 'MEDIA_GENERATION'` |
| dispatch | `tasks.pipeline_orchestrator_v2.dispatch_media_generation` |
| **readers of the decision** | **none — the decision was never recorded** |

The button was a **dispatcher, not a gate.** It had no memory, so it had no
authority: nothing downstream could ask whether an approval existed, so nothing
refused. The draft gate had no surface at all — `POST /trigger` from
`USER_REVIEW` **was** the approval, so approving a draft and spending the
full-resolution GPU time were one irreversible press with nothing recorded.

### 3.2 (b) The contract, and the artifact version

```
POST /api/v1/projects/{id}/gates/storyboard  {decision, note?}
POST /api/v1/projects/{id}/gates/draft       {decision, note?}
GET  /api/v1/projects/{id}/gates
```

All three §6.4 decisions are accepted. **Reject and Regenerate did not exist
anywhere in the application before this package** — the only thing a reviewer
could do was approve, or do nothing and leave no trace of having looked.

**M3.3 compatibility is not deferred.** The response and the audit row both
carry the Temporal signal body (`gate_storyboard` / `gate_draft`), so a
Celery-era decision and a cutover-era one are the same object. Nothing here
dispatches on behalf of a workflow; a row is written and the caller decides.

**The artifact version is the mechanism, not a field.** A decision names the
exact artifact it was taken against — a sha256 over the ordered
`(scene_id, scene_index, updated_at)` rows for the storyboard, over the newest
`prototype_draft` checkpoint for the draft — and currency is **recomputed on
read**. Three consequences, all wanted:

* *"upstream re-run invalidates downstream approvals"* needs **no invalidation
  write.** Re-running Stage 2 moves `updated_at`, the fingerprint moves, both
  approvals go stale in the same instant.
* There is no window in which a crashed invalidator leaves a stale approval
  standing, because nothing was ever asked to invalidate anything.
* A draft approval also records the storyboard version it was taken under, so
  re-running the storyboard invalidates the DRAFT approval immediately —
  before any new draft exists to change the draft's own fingerprint.

The draft gate is anchored to the **checkpoint**, deliberately not to
`projects.state`. That column is a position rather than a thing to review, and
Task 3 is the demonstration that it has been wrong.

### 3.3 (c) Enforcement, at the trigger layer

| Path | Refuses without |
|---|---|
| `POST /scenes/approve` → release | a current storyboard approval |
| `POST /scenes/{sid}/regenerate` | a current storyboard approval |
| `POST /assets/{id}/regenerate` | a current storyboard approval |
| `POST /quality-scores/{id}/reject?regenerate=true` | a current storyboard approval |
| `POST /trigger` from `USER_REVIEW` | a current **draft** approval |

**"Trigger pipeline" cannot bypass.** From `USER_REVIEW` that button IS the
final render, and the gate runs after the in-flight guard and before the state
write — so a refused trigger leaves the project exactly as it found it. Asserted:
no state change, no job row.

`POST /scenes/approve` keeps working and now runs through the same service. The
enforcement was built **behind** the existing surface rather than beside it: a
second Approve button would have left this one as a working bypass of the gate
it was supposed to be.

### 3.4 (d) The GUI

The open gate is the **primary action** — a full-width amber panel above
everything else on Overview, on the Storyboard tab and on the Draft tab, with
the artefact under review beside the decision, all three decisions offered, and
a note field that lands in `audit_log`. An operator must never have to navigate
away to see what they are approving and navigate back to approve it.

The old control was a green button between a read-only badge and the
Grid/Timeline toggle: a blocking review gate at the visual weight of a view
toggle. It is gone from that row — leaving it would be the same-screen
duplication Task 4 removes on Overview.

**Stepper stage 9 "Review" is the draft gate's home**, pinned by test.

Also removed from that page: a hand-maintained list of eight `ProjectState`
values deciding *when* to show the approve button. It was a second copy of the
gate's rule, in a browser, over a column this fleet has been wrong about. What
is left there is RBAC, which genuinely is a client-side concern.

### 3.5 (e) and (f)

Every decision writes `audit_log` — **not every approval.** An unrecorded
rejection is exactly as bad as an unrecorded approval when somebody later asks
why a project sat for three days.

**No frozen stage body was touched.** AD-05 §8 holds; the enforcement is at the
trigger layer and needed no hook inside a stage, so the "STOP that half and
report" branch was not taken. `TestFrozenStageBodiesAreUntouched` fails by name
if any `stage*.py`, `video_generation_task.py` or `talking_head_task.py` ever
imports the gate service.

### 3.6 Acceptance, WP-45 standard

Every refusal is asserted **on the broker**, not on a status code — a 409 that
arrives after the dispatch is not a gate, and all six of WP-60's real presses
answered 200 *while dispatching*.

| Criterion | Test | Result |
|---|---|---|
| refusal observed at the broker | `test_media_generation_never_reaches_the_broker_without_an_approval` | `broker.sent == []` |
| | `test_the_render_trigger_never_reaches_the_broker_unapproved` | `broker.sent == []`, 409 `GATE_NOT_APPROVED` |
| approve releases | `test_approving_then_releasing_does_dispatch` | one `dispatch_media_generation` |
| reject re-opens | `test_a_rejection_dispatches_nothing_and_re_opens_the_gate` | nothing dispatched, gate open |
| upstream re-run invalidates | `test_an_upstream_rerun_invalidates_the_approval` | `approved: false`, reason names both versions |
| …and stops the dispatch | `test_a_stale_approval_does_not_release_the_broker` | `broker.sent == []` |

All on new test projects; every existing project untouched.

---

## 4. TASK 3 — the stepper, and the thing that was actually freezing it

### 4.1 The measurement, in order

```
09:00:11  trigger_pipeline            -> state TRANSCRIPT_REFINEMENT
09:00:36  advance STORYBOARD_GENERATION -> 200   <- the writer works
09:07:47.255  "Storyboard approved ... scenes=9" -> state MEDIA_GENERATION
09:07:47.645  projects.updated_at moves; state is DRAFT   <- P1.4q reset
09:07:49  advance MANIFEST_GENERATION  -> 409 "DRAFT -> MANIFEST_GENERATION"
09:07:53  advance AUDIO_GENERATION     -> 409
09:08:24  advance TALKING_HEAD_RENDER  -> 409
```

Four hundred milliseconds after a human released the storyboard, a **stale**
job's failure callback returned the project to DRAFT. The run carried on —
stages 4, 5 and 6 all executed and all reported — and every report was refused,
because the project was now three hops behind the pipeline running inside it.
The stepper sat at step 1 while the render completed.

c12fa967 is the same story with older timestamps: reset to DRAFT at 15:31:10 on
2026-08-25 by a failed `image_generation`, then a `final_render` that
**succeeded** at 15:39:57 whose `COMPLETE` hop had nowhere legal to go.

So: a writer existed (WP-45 built it, it works), it stopped working the moment
`reset_after_terminal_failure` was introduced for any project whose run had a
partial failure, and the choke point is `app/api/v1/jobs.py`.

### 4.2 The fix at the choke point

The reset now requires the failing job to have been the **last live work** on
the project — `active_job`, the same question WP-61's guard asks.

**P1.4q is not removed and not weakened.** It exists because a project stuck in
an in-progress state answers 409 forever and the operator's documented recourse
was an `UPDATE` statement. It just stops abandoning live runs.

**The test was verified red.** With `still_running = await active_job(...)`
replaced by `still_running = None`,
`test_a_stale_job_failing_mid_run_does_not_reset_the_project` fails and its
sibling (`test_the_last_job_failing_still_resets_it`) passes. That is the WP-61
discipline applied: a test that passes against the defect is worth nothing.

### 4.3 ONE computation, recomputed on read

`GET /projects/{id}/progress` derives the 11-step stepper from three facts, in
this order of authority:

1. `pipeline_checkpoints` — what actually **executed**. The only record that
   cannot be wrong about whether a stage happened.
2. the gate decisions — whether a human is being waited on.
3. `projects.state` — used for the live step and for terminal states, **never**
   to decide whether an earlier stage completed.

The same payload feeds the top stepper, the per-tab indicators and the Overview
panel, so the three cannot disagree. Colours as ruled: complete green, active
blue, failed red, gated amber, pending grey. **Amber had nowhere to appear
before this package** — the gates had no record, so a blocked pipeline simply
looked stopped.

Checkpoints are read **across every job**, taking the LATEST outcome per stage.
That is a deliberate departure from `lib/pipeline-run.ts`, which picks one job
and explains why: the run panel answers *"how did THIS run go"*, where a
cross-job merge would paint a stage red that a later run completed. The stepper
answers *"how far has this PROJECT got"*, where the last word on a stage is the
true one. Both surfaces keep their own question; the run panel and its WP-60
provenance labels are untouched.

### 4.4 Acceptance — c12fa967, live, no manual edit

```
stored: DRAFT | derived: USER_REVIEW | matches: False
1:DRAFT=complete  2:TRANSCRIPT=complete  3:STORYBOARD=gated  4:MEDIA=complete
5:MANIFEST=pending 6:AUDIO=pending  7:TALKING=complete  8:PROTOTYPE=complete
9:REVIEW=gated  10:FINAL=pending  11:COMPLETE=pending
gates: storyboard(open) draft(open)
```

**Steps 5 and 6 grey is the truth, not a gap.** That project has **no**
`composition_manifest` checkpoint at all, and its newest `tts_audio` checkpoint
is genuinely `pending` (2026-08-25 15:20:38, after an earlier `complete` one).
The recomputation is honest rather than optimistic, which is the property that
makes it worth trusting.

`projects.state` is **still DRAFT** and `updated_at` is still
`2026-08-25 15:31:10.545641+00` — verified after the read. No stored state was
hand-edited, and no operator block was needed, because recompute-on-read was the
better half of the ruled choice: no write, correct for a project whose column is
stale for a reason nobody has diagnosed, and nothing to drift.

**The gap is shown, not hidden.** The strip prints, in words, that the column
says DRAFT while the checkpoints say USER_REVIEW, and why. Every project that
ran before this package has that gap; an operator reading "DRAFT" over a green
Final Render needs to be told which is which.

A fresh test project advancing live in colour, amber at an open gate, is covered
by `test_wp62_progress.py` and by the Task 2 acceptance on new projects.

---

## 5. TASK 4 — the Overview page stops duplicating itself

**Quick Access removed entirely.** It rendered a card per tab —
Transcripts, Storyboard, Media Assets, Audio, Talking Head, Draft Preview, Final
Renders, Prompts, Jobs, Languages — a grid of links to the same ten destinations
the tab bar lists an inch above it. Ten affordances, **zero added information**:
no counts, no status, no "3 scenes need review". The cards were larger, so on a
short viewport they were the *more* prominent of the two navigations.

WP-43 Task 1 is why it survived. Before that package the tab bar lived inside
this page, so Quick Access was a second navigation on the one page that had a
first; WP-43 moved the tab bar into the shell and onto all eleven tabs, and the
duplicate below it was left behind.

### The sweep

| Affordance | Verdict | Reason |
|---|---|---|
| Quick Access grid (10 links) | **REMOVED** | Duplicates the tab bar with no added information. |
| "Approve storyboard" corner button (Storyboard tab) | **REMOVED** | The gate panel above the same page now carries it, with the consequence stated and all three decisions offered. Two approve controls on one screen. |
| Top stepper | **KEPT** | Status. Says where the WORK is. |
| Tab bar | **KEPT** | Navigation. Says where YOU are. They look similar and are not. |
| "Trigger pipeline" / "Start final render" | **KEPT, one control** | Its label and confirm text change with state; there is never a second. |
| "▶ Watch" (COMPLETE only) | **KEPT** | Reaches the player, which no tab does. |
| Delete (admin only) | **KEPT**, pushed right | WP-59 placed it deliberately away from the action an operator came to press. |
| Preset panel | **KEPT** | An action, not a link. |
| Per-tab status dots | **ADDED** | Information the tab bar did not carry, from the same computation as the stepper — so a dot cannot disagree with a step. |

Tabs that are not a pipeline stage (Overview, Prompts, Jobs, Languages) get **no
dot** rather than a grey one: a grey dot on Jobs would read as "no jobs".

Pinned by `TestOverviewDoesNotDuplicateItself`, including a sweep that fails if
**any** project page maps `PROJECT_TABS` itself.

---

## 6. TASK 5 — purge_state: the closure existed, the read path did not

Read from the live `audit_log`, all fourteen rows:

```
action_type              count  before.purge_state  after.purge_state
PROJECT_DELETE_COMPLETED    14  pending             complete
```

`_record_completion` **UPDATEs the originating row by its own id** and flips
`action_type`. The ledger item's requirement was already met before this package
started, and saying so is more useful than building a second mechanism beside
it.

**What was genuinely missing:** `before_payload->>'purge_state'` says `"pending"`
forever on a finished deletion — one column away from an `after_payload` saying
`"complete"` — so an operator querying the obvious field gets the wrong answer
on every historical row.

The `before_payload` is **not** rewritten on completion. It is a record of the
moment before destruction, and editing it would destroy the evidence that the
row was written before the rows were, which is the entire reason the ordering
is what it is. It is **labelled** instead (`purge_state_note`,
`purge_started_at`, both new rows onward), and there is now one read path:

`GET /api/v1/projects/deletions/audit` (admin) classifies every row:

| class | means | resumable |
|---|---|---|
| `completed` | COMPLETED, `purge_state = 'complete'` | no |
| `completed_partial` | COMPLETED, files and/or Redis did not finish | no |
| `died_mid_purge` | still STARTED, older than five minutes | **yes**, from the manifest |
| `in_flight` | still STARTED, written in the last five minutes | yes |

`in_flight` is its own class deliberately: a running purge writes nothing until
it finishes, so it is indistinguishable from a dead one **by the record alone**.
Reporting it as `died_mid_purge` would raise a false alarm on every live
deletion.

### How an operator audits the ten 2026-08-26 deletions

They are historical test data and **nothing in this package modifies them.**

```
GET /api/v1/projects/deletions/audit    (admin token)
```

All fourteen read `completed`, which is what they are. Their
`before_payload.purge_state` still says `"pending"` and always will; rows written
from this package onward carry `purge_state_note` explaining that in place,
which is exactly why the ten needed a read path rather than a data fix.

The equivalent by hand, for the record:

```sql
SELECT id, before_payload->>'project_name'   AS project,
       action_type,
       after_payload->>'purge_state'          AS outcome,
       after_payload->>'completed_at'         AS completed
FROM audit_log
WHERE resource_type = 'project'
  AND action_type IN ('PROJECT_DELETE_STARTED','PROJECT_DELETE_COMPLETED')
ORDER BY timestamp DESC;
```

`action_type` is the field that says whether the purge finished; a row still at
`PROJECT_DELETE_STARTED` died mid-purge and is resumable.

**`project_gate_decisions` was added to the deletion category map.** It was
found by `test_every_project_fk_table_is_in_the_map` failing by name, exactly as
designed — the second table that test has caught.

---

## 7. TASK 6 — the guard reaches the route the incident used

WP-60's six dispatches on project 52d52867 were `job_type` `video_generation`
and `animation_generation`. `trigger_pipeline` produces neither. They came
through `POST /projects/{id}/scenes/{sid}/regenerate`, which WP-61's guard did
not reach — recorded there as D-1.

### The five dispatch-capable endpoints, enumerated

| # | Endpoint | Before | Now |
|---|---|---|---|
| 1 | `POST /projects/{id}/trigger` | guarded (WP-61) | unchanged |
| 2 | `POST /projects/{id}/scenes/{sid}/regenerate` | **unguarded** | guarded |
| 3 | `POST /assets/{id}/regenerate` | **unguarded** | guarded |
| 4 | `POST /quality-scores/{id}/reject?regenerate=true` | **unguarded** | guarded |
| 5 | `POST /jobs/{id}/resume` | **unguarded** | guarded |
| 6 | `POST /projects/{id}/languages/{vid}/retry` | **unguarded** | guarded |

2, 3 and 4 converge on `dispatch_scene_media_regeneration` and are guarded
**there**, so a fourth caller added later inherits the guard instead of
reintroducing the hole.

`POST /jobs/{id}/resume` was a real hole rather than a completeness exercise: it
checked *this job's* status and said nothing about the **project**, and a
project with one failed job and one running job is precisely the shape a
partially-failed run leaves behind — which is why WP-61 rejected `projects.state`
as a guard in the first place.

**Deliberately not guarded, argued rather than overlooked:** DLQ replay
(`POST /dlq/{id}/replay`). Admin-only, re-enqueues one named dead message rather
than starting a run, and refusing it while a run is in flight would block the
operator's only tool for draining a queue that a run is stuck behind. Backup
dispatches are not project pipeline work at all.

### Two details that would otherwise bite

Both refusals run **before the job row is inserted.** WP-45's finding was that a
caller must never be told "queued" by something that queued nothing; the mirror
is that a refused request must not leave a `pending` row behind to be counted,
retried or resumed. Asserted.

**Catch order is load-bearing.** `PipelineAlreadyRunningError` subclasses
`ValueError` (WP-61 made it one so existing callers kept behaving), so a route
whose `except ValueError` came first would answer `INVALID_STATE_TRANSITION` —
the wrong code, and one an operator would try to fix by changing the project's
state. Pinned by test in both routes that have the ordering.

The quality-reject path catches all three refusals **locally**: its WP-45
contract is that the reviewer's rejection stands whether or not the fleet can act
on it, and a 409 propagating from there would roll a recorded verdict back
because a run was in flight.

**Acceptance, WP-45 standard:** `test_the_second_dispatch_never_reaches_the_broker`
presses regenerate twice; `len(broker.sent) == 1` after the second, the 409
names the active run, and the job-row count is unchanged.

---

## 8. TASK 7 — one flag that was a lie on a live surface

Measured 2026-08-26:

```
llama-3.3-70b-transcript  vllm  approved   dynamically_loadable = false
llama-3.3-70b-storyboard  vllm  approved   dynamically_loadable = false
test-model-1              vllm  retired    dynamically_loadable = TRUE
Llama-3.3-70B-Instruct    vllm  approved   dynamically_loadable = TRUE
```

Two of four already correct is what makes the other two a **drift**, not a
convention. `model_selection.py:69` reads this flag, so a true value on a live
approved row means a selection path could decide to "load" a model onto an
engine that binds its model at container start by `--model`.

Migration 0035 scopes the UPDATE `WHERE engine = 'vllm'`, because the property
belongs to the **engine** — a by-name list goes stale the first time a vLLM row
is added. `downgrade()` restores the two measured rows **by name**, because
setting every vLLM row true would "restore" a value two of them never held.

Verified live after the migration: all four `false`.

**Translation routing is NOT moved.** The entry stays on its certified Llama
record until MBCP certifies the Qwen bundle (work orders 5 and 7), annotated on
the record itself with the provenance-exception status and the manifest path
(`/mnt/ivgs-shared/qwen-weights-manifest-2026-08-26.txt`, 74 hashes, 66 shards).
Registering an uncertified bundle as approved would be a worse lie than the flag
this corrected. Storyboard and transcript stay on Llama until after M3.3
regardless, so the AD-05 conformance diff is not moved by a model change.

---

## 9. TASK 8 — five field defects, and which touched runtime config

| | Correction | File-only or runtime? |
|---|---|---|
| (a) | `--entrypoint hf`; `--local-dir-use-symlinks` dropped | **File only.** The block is the artefact; nothing else carried the invocation. Two stale "huggingface-cli resumes" instructions fixed with it. |
| (b) | `find -L`, both places | **File only.** |
| (c) | ufw insert-not-append, with a BEFORE posture check and an AFTER gate on rule numbers | **File only** — but it describes a runtime state the operator has already corrected by hand on node-05. |
| (d) | engine pinned by digest | **RUNTIME CONFIG.** `docker-compose.llm.node05.yml` and `.env.node05.example` both changed; A06's SHA gate was updated to the new files; new block A06B fills the digest into `.env.node05` on the node. |
| (e) | two named digests in the publisher; `scripts/check_seed_conformance.sh` added | **Neither, and both.** No config changed; a new gate ships and the publisher's output changed. |

### (a) and (b), in one sentence each

`huggingface-cli` is **removed** from the current nightly and its shim exits 1,
so A07 aborted at `RC != 0`. `--local-dir-use-symlinks` is rejected by the newer
hub and was pointless anyway: there is no `--local-dir`, so it was controlling
the layout of a directory the command was not writing to.

`find … -type f` hashed **nothing**. The hub cache stores blobs under `blobs/`
and exposes them under `snapshots/` as **symlinks**; `-type f` tests the link,
not its target. A 29 GB cache produced a manifest whose own total line read
`# safetensors files: 0`, the block exited 0, and the provenance debt this
exception was authorised against was recorded against nothing. Both `find`s
needed `-L`, because fixing one gives a manifest whose body and total disagree.

### (c) the ufw posture

node-05 carries `Anywhere ALLOW 192.168.1.0/24`. ufw is first-match, so the
**appended** deny sat below it and was inert — the rule set *looked* like
"fleet only" and every host on the LAN still reached :8000.

The block now measures the posture first, deletes any earlier attempt
(idempotent), **inserts** the four allows at 1–4 and the deny at 5, and then
gates on the rule **numbers**, naming the subnet rule by position if it still
sits above the deny. An echo telling a human to check an ordering is not a
control.

### (d) the tag moved mid-package

`cu130-nightly` was pulled twice and produced two different images **reporting
the same vLLM version string** `v0.19.2rc1.dev134`. The one field a reader would
have checked did not move.

The compose now references `vllm/vllm-openai@${VLLM_IMAGE_DIGEST}` with **no
`:-` default**. Every other `${VAR}` in that file has one, so a missing env file
fails loudly on the model name — but the image is the opposite case: a fallback
to a floating tag fails **silently**, because the container starts and serves.

`.env.node05.example` carries the **recorded prefix only** and is deliberately
not a valid digest. A tracked file shipping a plausible but wrong 64-character
string is how a fleet gets pinned to an image nobody ran. **D-1.**

### (e) the "divergence" that was not one

WP-62 was told the baked seed differed from the tree — container `205ddaba`
against tracked `67be5991` — and asked to find the build-context /
`.dockerignore` / stale-layer cause.

**There is no divergence.** Measured on the running stack:

```
$ docker exec ivgs-fastapi sha256sum /app/seed/default_prompts/translation.j2
67be5991ad481914214ad3dd6a3341862513c52f223668817a4cd0d897ef0f33
$ sha256sum ivgs-api/seed/default_prompts/translation.j2
67be5991ad481914214ad3dd6a3341862513c52f223668817a4cd0d897ef0f33
```

`205ddaba` is the sha of **the same bytes with the trailing newline stripped**:

```
$ printf '%s' "$(cat ivgs-api/seed/default_prompts/translation.j2)" | sha256sum
205ddabad3673a5939316e622ee23a79a7b1aaa272f803d6b1ed09ccc6747a1f
```

That is exactly what `wp61_publish_prompt.py:70` computes — `.read_text().strip()`
— and what line 73 printed under the label `sha256`, five lines below an operator
block printing `sha256sum` on the file. **Two digests, two byte strings, one
label, one package.**

A **measurement** defect, not a build defect, and both halves are closed:

1. The publisher prints both, each named for what it covers (`file sha256`,
   `stored sha256`). Live output at publish time is in §10.2.
2. `scripts/check_seed_conformance.sh` gates baked-equals-tracked **in both
   directions**, because nothing anywhere compared them: a genuinely divergent
   seed **would** have shipped silently, and the only reason it had not is that
   nobody had changed a template since the last build. A template that reaches
   the `prompts` table is a contract — `TranslationService` REFUSES to run under
   one without the marker — so a stale one is not cosmetic drift.

**It caught a real divergence during this package**, between the tree carrying
prompt v3 and an image still carrying v2, and it is tested both ways: the
negative case adds one byte to a copy in `tmp_path` and asserts exit 1 naming the
file.

---

## 10. TASK 9 — the annotation, prompt v3, and the run that did not go as ruled

### 10.1 (a) The corruption is wider than one scene

`docs/reference-run-2026-08-23-correctness-annotation.md` §3 is extended with
both worked examples quoted verbatim from `storyboard_scenes` — the six
narrations of the second example (scenes 9–14) plus the first example's three
(5–7). The two that make the case:

> **11:** "This gives us 200 + 60, which equals 260, but we wrote it as 640 in
> the previous step, which is incorrect."
>
> **13:** "Now, let's add 32 and 260, but since we are adding the results of
> multiplying 32 by 1 and 32 by 20, we should add 32 and 640, but that was
> incorrect."

No previous step says 640; neither figure follows from the operands the previous
scene supplied (40 and 60); and scene 13 asserts both numbers in one sentence
and calls one of them incorrect. **Nine scenes of eighteen** are affected.
Scenes 9 and 14 are correct.

The run is UNCHANGED and remains the technical conformance standard.
**"Matches the reference" is even less "correct" than previously recorded.**

### 10.2 (b) Prompt v3, published through the versioning path

```
template      : /app/seed/default_prompts/translation.j2
file sha256   : fb9ce1cd75a98e2065a1bf7fe0a90ee18700b46112ea28cdf80e9c9a34847a10
stored sha256 : e30d4694cc892da02e045a2d8047dcf2ab2a89acef2f6c7de9fc0abc475e206c
contract : OK (IVGS-TRANSLATION-FLAG: present, correction forbidden, scope stated)

v2 -> is_active false  (18c8919d-b3c0-404e-9909-1eca90d7910b)
v3 inserted            (688e0227-4f1b-46e2-932c-f944ff6b3577)
```

v1 (`e16b6502`) and v2 (`18c8919d`) both remain, inactive and readable. The
publisher now **refuses** a template that carries the marker but not the scope:
such a prompt would publish cleanly, run cleanly and reproduce the false
positives — a green path over an unstated rule.

### 10.3 The re-run — measured, and not the ruled expectation

Variant `3fccf815` only, the same single-variant path as N01-B. 18 scenes,
2026-08-26 11:15:18 → 11:16:55 UTC, **97 seconds**, `qwen38-27b` on node-05,
prompt version 3, marker absent from every delivered scene, state `flagged`.

| Scene | v2 | v3 | Verdict |
|---|---|---|---|
| 3 | — | **flagged** | **NEW FALSE POSITIVE.** "4 times 2 plus the carried 1 equals 9, not 92" — it misreads a correct two-digit partial product. |
| 5 | flagged | flagged | genuine |
| 6 | flagged | flagged | genuine scene; **reason was ~200 words of the model's own deliberation** ending "No factual or arithmetic error found." |
| 9 | flagged | **gone** | ✅ the ruled false positive, removed |
| 11 | flagged | flagged | genuine scene; reason still misreads its own arithmetic (200 + 60 *is* 260) — **accepted as-worded**, the scene is defective regardless |
| 12 | flagged | flagged | genuine |
| 13 | flagged | flagged | genuine |
| 14 | — | **flagged** | **NEW FALSE POSITIVE.** "32 + 640 equals 672, but the correct sum is 672" — it flags a scene by agreeing with it. |
| 15 | flagged | **gone** | ✅ the ruled false positive, removed |

**Seven flags before, seven after. Two removed as ruled, all five genuine ones
retained, two new ones introduced.** Reported as measured. Whether to iterate to
v4 is a ruling and not mine to make — *"keep tuning until the flag set is
right"* is how a prompt gets fitted to one document. **D-2.**

### 10.4 What the acceptance run found, and what was fixed because of it

Scene 6's reason was a reasoning dump on a line the prompt has always specified
as `<short reason, in English>`. Nothing enforced it.

A reason is now **capped at 300 characters for display, kept in full as
`reason_full`, and marked `reason_suspect`.** The flag is **not dropped** —
dropping one because its own text says "no error" is a heuristic that would
eventually drop a real one; the marking is so a reviewer reads it rather than
trusting the summary.

**The stored row is not re-run under the cap.** It is the v3 acceptance
evidence, and re-rolling the model would destroy it. The cap is verified by test
against the exact text the model produced.

### 10.5 (c) The variant stays flagged

As ruled. The source is genuinely wrong, regeneration is post-M3.3, and a
flagged deliverable a human must look at is the correct end state for a faithful
translation of a defective source.

---

## 11. Test evidence

**Two full-suite passes were taken, which is the limit.** One after the code was
written (18 failures, all in existing tests, all one behaviour change) and one
confirming pass after they were fixed.

| Tree | passed | failed | skipped | errors | Was |
|---|---|---|---|---|---|
| `ivgs-api` | **1026** | **0** | 0 | 0 | 953 |
| `ivgs-workers` | 838 | 18 | 48 | 15 | **identical** |
| `ivgs-scheduler` | 35 | 20 | 0 | 0 | **identical** |
| `ivgs-backup-worker` | 4 | 0 | 0 | 0 | **identical** |
| `tests_system` | **150** | 12 | 15 | 30 | 125 |
| **Total** | **2053** | **50** | **63** | **45** | 1955 / 50 |

**Zero new failures.** 98 tests added (73 api, 25 system).

### 11.1 Eighteen existing tests updated, none weakened

One behaviour change caused all of them: both review gates now BLOCK. The
accounting is in the baseline §2 so it can be checked rather than taken on
trust. The three worth naming here:

* **`test_wp45_dedup_and_gate.py::test_triggering_from_user_review_produces_a_broker_message`** —
  its fixture described the project as *"a draft the operator has approved"* and
  recorded no approval, because there was nowhere to record one. **The fixture
  became honest about a claim in its own docstring.**
* **`test_wp61_trigger_guard.py::test_non_terminal_is_the_complement_of_terminal`** —
  the query moved to a module-level `active_job`; the test follows it **and
  gains** an assertion that the method is a delegation rather than a second
  copy. Strictly stronger: one definition, now protected across five callers.
* **`test_wp59_deletion.py::TestCategoryMap::test_every_project_fk_table_is_in_the_map`** —
  **not edited at all.** It failed by name on `project_gate_decisions`, exactly
  as designed, and the fix was to add the category. Second table it has caught.

No assertion was weakened, no skip marker added, no coverage deleted.

### 11.2 Two tests that were checked for passing against the defect

`test_a_stale_job_failing_mid_run_does_not_reset_the_project` was verified red
by replacing the guard with `still_running = None`: it fails, its sibling
passes. That is WP-61's lesson applied — the obvious test there passed without
the guard, and six of eight went green when the guard was deleted.

`TestSeedConformanceGate` is gated both ways for the same reason. A conformance
check that could never fail would be trivially "safe" and would gate nothing.

### 11.3 A note on `tests_system/test_wp62_surfaces.py`'s block scans

They read the **fenced code with comment lines removed**, not the whole
markdown. The corrections are recorded twice on purpose — once in the header
table, once beside the line they fixed — and both quote the defective command
verbatim. A whole-document scan would fail on its own changelog and, worse,
would pass if somebody moved a defective command into a comment. What these
tests measure is what would RUN if the block were pasted.

---

## 12. Deployment — node-01 only, WP-34 binding rules

`v5.21.0-gates`, one coherent set across the two images this package touched.
GHCR is off the deploy path; artifacts under the standard name.

| Container | Image | Status |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.21.0-gates` | healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.21.0-gates` | healthy |
| `ivgs-celery-*` | `ivgs-workers:v5.20.0-qwen` | unchanged, healthy |
| `ivgs-scheduler` | `ivgs-scheduler:v5.19.0-surfaces2` | unchanged |
| `ivgs-backup-worker` | `ivgs-backup-worker:v5.19.0-surfaces2` | unchanged |

**`ivgs-workers` was deliberately NOT rebuilt.** No worker code changed: the
gate enforcement is entirely at the trigger layer and AD-05 §8 freezes the stage
bodies. Rebuilding it to carry a no-op would move a tag for nothing.

Artifacts banked:

```
brucecostello2_ivgs-api_v5.21.0-gates.tar.zst       8a6f1e16239e1bf5…
brucecostello2_ivgs-frontend_v5.21.0-gates.tar.zst  91676ee7e1e7a9df…
```

**Migration 0035 was applied to production before the API was recreated**, and
it had to be: the ORM declares `project_gate_decisions`, so a gate read on an
0034 database fails. The database is at **0035**, and the downgrade path was
exercised on the test database — `alembic downgrade 0034` then `upgrade head`
round-trips clean.

`ivgs-api` was built twice at the same tag (the second carrying §10.4's cap).
Per WP-61's recorded trap, the stale artifact would otherwise have been kept by
`save-image-artifact.sh`'s "already present, skipping" rule — the artifacts above
were saved after the final build.

**Nodes 02/03/04 need nothing.** No worker task code changed. **node-05 and
node-06 were not touched**: the only contact with node-05 was Task 9(b)'s
translation calls to its existing `/v1/chat/completions`, and reading its
Prometheus telemetry.

### 12.1 Live data changed — the complete list

| Change | Sanctioned by |
|---|---|
| `prompts`: v3 inserted (`688e0227`), v2 set inactive | Task 9(b), "publish v3 through the same versioning path" |
| `language_variants` `3fccf815`: `translation`, `translation_flags`, state stays `flagged` | Task 9(b), the ruled re-run |
| `models`: 2 rows `dynamically_loadable` → false, translation row annotated | Task 7, "correct the flag NOW" |
| `alembic_version` 0034 → 0035, `project_gate_decisions` created (empty) | the deploy |

**Nothing else.** Verified after the fact: every project's `state` and
`updated_at` is as found, including c12fa967 at DRAFT / `15:31:10.545641+00` and
64207933 at DRAFT / `09:07:47.645098+00`; `en-US` is still `pending`; no stored
project state was hand-edited. The orphan and tier-migration schedules are
exactly as WP-61 left them — no schedule file was touched.

---

## 13. Ledger and register entries

| Id | Entry |
|---|---|
| **WP62-L1** | `reset_after_terminal_failure` fired on any job of a project, stranding live runs. **CLOSED** — guarded on `active_job`, test verified red. |
| **WP62-L2** | Both human review gates were unenforced surfaces. **CLOSED** — recorded, blocking, tested on the broker. |
| **WP62-L3** | The GPU Fleet page could not show node-05/06. **CLOSED** — third report, and the last. |
| **WP62-L4** | The in-flight guard did not reach four dispatch-capable endpoints. **CLOSED** — WP-61 D-1 extended, DLQ replay excluded with reasons. |
| **WP62-L5** | Nothing compared a baked seed template with the tracked one. **CLOSED** — `scripts/check_seed_conformance.sh`, gated both ways. |
| **WP62-L6** | A flag reason was unbounded and accepted a reasoning dump. **CLOSED** — capped, kept in full, marked. |
| **WP62-L7** | Prompt v3 removed two false positives and introduced two others. **OPEN — D-2.** |
| **WP62-L8** | `.env.node05.example` carries an 8-character digest prefix. **OPEN — D-1.** |
| **WP61-L6** | MBCP must certify the Qwen bundle. Unchanged; the Model Store entry is now annotated with the exception rather than silent about it. |
| **WP61-L4** | node-03 has no GPU telemetry. Unchanged, and now visible on the GPU Fleet page as well as Node Monitor. |

Swallow register: no new instances found; none closed.

---

## 14. Decisions needed

### D-1 — the full engine digest for node-05

§9(d). `cu130-nightly` moved mid-package and the compose now pins by digest with
no fallback, which is right. This package was given **eight hex characters**
(`sha256:3dbe092e…`). `.env.node05.example` records exactly that and is
deliberately not a valid digest, because a tracked file shipping a plausible but
wrong 64-character string is how a fleet gets pinned to an image nobody ran.

Two ways to close it, either is fine:

1. **Run A06B on node-05.** It reads the digest off the running container,
   refuses unless it starts `sha256:3dbe092e`, and writes it into
   `.env.node05`. Nothing else is needed.
2. Paste the full digest and it goes into `.env.node05.example` in a one-line
   commit.

Until then, `docker compose … config` on node-05 **refuses to render**, which is
the intended failure and not a regression.

### D-2 — prompt v4, or stop here?

§10.3. v3 did what it was ruled to do — scenes 9 and 15 are gone and all five
genuine flags remain — and it introduced two new false positives (scenes 3 and
14) that v2 did not produce. Net flag count unchanged at seven.

The two new ones have a shape a prompt can name, the same technique that removed
9 and 15. But that is the third iteration of a prompt against **one document**,
and each round fits it more closely to this project's narration. The question is
whether to:

| | Implication |
|---|---|
| **(a) Publish v4 naming the two new shapes** | Likely removes them. Fourth version fitted to one 18-scene lesson; the next unseen document is untested either way. |
| **(b) Stop at v3 and accept a ~2-in-18 false-positive rate** | The contract is stated correctly; the model is imperfect at applying it. Reviewers see 7 flags of which 5 are real, and `reason_suspect` marks the worst offender. |
| **(c) Move the scope test out of the prompt** | An arithmetic checker over narration would catch scenes 5/6/11/12/13 deterministically and flag nothing on 3/9/14/15. Real work, not this package, and it is the only option that stops being a prompt-tuning loop. |

My recommendation is **(b) now, (c) as a ledger item after M3.3** — but the
package ruled the scope, so the iteration decision is the operator's.

### D-3 — node-04 was at 87 °C during this package

§2.2. Incidental, observed while verifying the fleet page, and worth knowing
rather than deciding: node-04 read 87 °C and 49 GB of device VRAM in use while
node-01 was building images. Nothing in this package touches node-04. It is
above the amber threshold the card draws (85 °C) and below nothing that stops
work.

---

## 15. What was NOT done, and why

* **No worker code changed.** The gate enforcement is at the trigger layer;
  AD-05 §8's frozen stage bodies were not touched, and the "STOP that half and
  report" branch was not taken because no hook inside one was needed.
* **No operator block was written for Task 3.** Recompute-on-read was the better
  half of the ruled choice and needs no write, so no project state was edited
  and no dry run was required.
* **The ten 2026-08-26 deletion rows were not modified.** They are historical
  test data; §6 is how an operator audits them.
* **Translation routing was not moved to Qwen** in the Model Store. Blocked on
  MBCP certification (WP61-L6); the entry is annotated instead.
* **The es-ES variant was not regenerated**, and neither was the reference run.
  Both are post-M3.3 by ruling.
* **`ivgs-workers`, `ivgs-scheduler` and `ivgs-backup-worker` were not
  rebuilt.** Nothing in them changed.
* **The reference project's source narration was not edited.** It is the live
  test case the flag path fires on.

---

## 16. Push block — COMMITTED AND HELD, NOT PUSHED

Nine commits, this report included. Run the gate first; it is a gate, not a
formality. It re-measures
what this report claims and prints PASS or FAIL against it. **It pushes
nothing.**

```
# RUN ON: node-01 (192.168.1.90).
# READ-ONLY GATE. It writes nothing, pushes nothing and starts nothing.
(
  set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; return 0 2>/dev/null || exit 0; }
  RC=0

  echo "=============== 1. the nine held commits ==============="
  N=$(git log --oneline 6a3b074..HEAD | wc -l)
  git log --oneline 6a3b074..HEAD
  echo "held commits: $N (expect 9)"
  [ "$N" = "9" ] || { echo ">>> FAIL: commit count"; RC=1; }
  git status --porcelain | head
  [ -z "$(git status --porcelain)" ] || { echo ">>> FAIL: working tree dirty"; RC=1; }

  echo
  echo "=============== 2. nothing is pushed yet ==============="
  git status -sb | head -1
  git rev-list --count origin/main..HEAD | xargs printf 'ahead of origin/main by: %s\n'

  echo
  echo "=============== 3. the deployed images ==============="
  for C in ivgs-fastapi ivgs-nextjs; do
    printf '%-16s %s  %s\n' "$C" \
      "$(docker inspect $C --format '{{.Config.Image}}')" \
      "$(docker inspect $C --format '{{.State.Health.Status}}')"
  done

  echo
  echo "=============== 4. the seed conformance gate ==============="
  bash scripts/check_seed_conformance.sh >/tmp/seed.$$ 2>&1
  tail -1 /tmp/seed.$$
  grep -q '^PASS:' /tmp/seed.$$ || { echo ">>> FAIL: seed conformance"; RC=1; }
  rm -f /tmp/seed.$$

  echo
  echo "=============== 5. the fleet page shows five GPUs ==============="
  docker exec ivgs-fastapi python -c "
import asyncio
from app.services.gpu_service import GpuService
async def m():
    nodes, total = await GpuService(None).list_nodes()
    print('GPU nodes:', total, '(expect 5)')
    print('scheduler workers:', sum(1 for n in nodes if n.in_scheduler), '(expect 3)')
    for n in nodes:
        print(' ', n.node_hostname, 'sched=' + str(n.in_scheduler),
              'dev_vram=' + str(n.device_used_vram_mb))
asyncio.run(m())" 2>&1 | grep -v '^{' 

  echo
  echo "=============== 6. the database is at 0035 ==============="
  PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
  PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
  export PGPASSWORD="$PGPW"
  V=$(psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -At -c \
        "SELECT version_num FROM alembic_version;")
  echo "alembic_version: $V (expect 0035)"
  [ "$V" = "0035" ] || { echo ">>> FAIL: migration"; RC=1; }

  echo
  echo "=============== 7. Task 7 landed, and nothing else in models ======"
  psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -c \
    "SELECT name, dynamically_loadable FROM models WHERE engine='vllm' ORDER BY name;"
  L=$(psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -At -c \
        "SELECT count(*) FROM models WHERE engine='vllm' AND dynamically_loadable;")
  echo "vllm rows still claiming runtime loading: $L (expect 0)"
  [ "$L" = "0" ] || { echo ">>> FAIL: Task 7"; RC=1; }

  echo
  echo "=============== 8. the live data this package changed ==============="
  psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -c \
    "SELECT version, is_active, created_at FROM prompts
      WHERE prompt_type='translation' ORDER BY version;"
  psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -c \
    "SELECT language_code, state,
            translation->>'prompt_version' AS prompt_v,
            jsonb_array_length(coalesce(translation_flags,'[]'::jsonb)) AS flags
       FROM language_variants
      WHERE project_id='c12fa967-f989-4ed4-8e20-3ea62cb92e8f'
      ORDER BY language_code;"
  echo ">>> EXPECT: v1/v2 inactive, v3 active; es-ES flagged under v3 with 7"
  echo ">>> flags; en-US still pending and untranslated."

  echo
  echo "=============== 9. no project state was hand-edited ==============="
  psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -c \
    "SELECT name, state, updated_at FROM projects ORDER BY created_at;"
  echo ">>> EXPECT: c12fa967 DRAFT / 2026-08-25 15:31:10.545641+00 and"
  echo ">>> 64207933 DRAFT / 2026-08-26 09:07:47.645098+00, both UNCHANGED."
  unset PGPASSWORD

  echo
  echo "=============== 10. c12fa967's stepper, recomputed ==============="
  docker exec ivgs-fastapi python -c "
import asyncio
from uuid import UUID
from sqlalchemy import select
from shared.database import async_session_factory
from app.models.project import Project
from app.services.project_progress import ProjectProgressService
async def m():
    async with async_session_factory() as db:
        p = await db.scalar(select(Project).where(
            Project.id==UUID('c12fa967-f989-4ed4-8e20-3ea62cb92e8f')))
        r = await ProjectProgressService(db).compute(p)
        print('stored:', r['stored_state'], '| derived:', r['derived_state'])
        print(' '.join(str(s['index'])+':'+s['status'] for s in r['steps']))
asyncio.run(m())" 2>&1 | grep -v '^{'
  echo ">>> EXPECT: stored DRAFT, derived USER_REVIEW, and the stepper green"
  echo ">>> through step 4 with 3 and 9 amber. Steps 5 and 6 grey is TRUE:"
  echo ">>> that project has no composition_manifest checkpoint and its"
  echo ">>> newest tts_audio checkpoint is genuinely 'pending'."

  echo
  echo "=============== 11. the test counts this report claims ==============="
  PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
  PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
  export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
  export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
  unset PGPW PGUSER
  echo "--- ivgs-api: expect 1026 passed, 0 failed ---"
  .venv/bin/python -m pytest ivgs-api/tests -q 2>&1 | tail -1
  echo "--- tests_system: expect 150 passed, 12 failed ---"
  .venv/bin/python -m pytest --timeout=180 tests_system -q 2>&1 | tail -1
  echo "--- ivgs-workers: expect 838 passed, 18 failed (BASELINE, unchanged) ---"
  .venv/bin/python -m pytest ivgs-workers/tests -q 2>&1 | tail -1
  echo "--- ivgs-scheduler: expect 35 passed, 20 failed (BASELINE) ---"
  .venv/bin/python -m pytest ivgs-scheduler/tests -q 2>&1 | tail -1
  echo "--- ivgs-backup-worker: expect 4 passed, 0 failed ---"
  .venv/bin/python -m pytest ivgs-backup-worker/tests -q 2>&1 | tail -1

  echo
  echo "=================================================================="
  if [ $RC -eq 0 ]; then
    echo "GATE: PASS on every check it can make on its own."
    echo "Read sections 8, 9, 10 and 11 above before pushing - they need eyes,"
    echo "not an exit code."
    echo
    echo "Then, and only then:   git push origin main"
  else
    echo "GATE: FAIL. Do not push. The failing check is named above."
  fi
)
```

---

## 17. One closing observation

Three of the four surprises in §0 have the same shape. A mechanism existed and
worked — the state writer, the deletion closure, the seed in the image — and
what was broken was the thing that *reported* on it: a reset that fired too
widely, a field that said "pending" forever, a label over two different
digests. In each case the obvious reading of the symptom pointed at building the
mechanism again.

The fourth is the inverse and is the one to watch. Task 1's symptom was reported
three times and was exactly what it looked like every time; twice it was closed
by making the report of it more precise. A more accurate label on an incomplete
page is a better lie, not a smaller one.
