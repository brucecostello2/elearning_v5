# WP-IVGS-12i — the auto-repair pass, and the button that crashed

**Session:** 2026-08-30. **Order:** WATCH FINDINGS ORDER — RC-R batch, Phase-1 watch.
**Ledger:** `OUTSTANDING_WORK.md` §12i-watch. **Evidence:** `dev/workpackages/reference/wpivgs12i-evidence/`.
**Live project READ, never written:** `680d9e4c-608b-488a-9270-9b4317a7f693` ("sunday's test").
**Everything written happened on:** `0840e6c2-ab35-4206-bced-2eac9bde6dd5`, a throwaway for this
watch. ⛔ **It is still alive and must be deleted through the WP-59 flow — see "The tree" below.**

---

## STATE AT SESSION END

**Done.** RC-R4 built, deployed and proven end-to-end through the real pipeline. RC-R1 measured,
found worse than reported, fixed and proven at both zero and nonzero. RC-R2 built, including the
one-click the order believed already existed and which never did. RC-R3(a) and (b) measured and
rowed, nothing built. RC-R5 opened.

**Mid-way through: nothing.** No half-finished edit is held.

**How the order is now stale.**

1. ⛔ **"the modal's one-click 'Author as motion graphics' remains"** — it never existed. What
   existed was WP-64's "Adapt description", which proposes prose and authors no template. Built in
   this package; the order's word *remains* should read *is added*.
2. ⛔ **"Acceptance: … a brief whose mechanical refusals are ZERO"** — not reached, and the reason
   is the ruling working. **8 mechanical refusals in, 3 repaired, 5 refused BY THE AUTHORING GUARD,
   5 out.** The order's acceptance assumes the authoring call succeeds; on the operator's own script
   it succeeds five times in eight. See §3.
3. ⚠ **"RC-R1 — measure whether POST approve refuses server-side"** — it does, and has since
   WP-IVGS-10. The defect was one step earlier and worse: **HTTP 500**. See §4.

**Learned and not written down anywhere else.** The pass's product is not a clean gate. It is a
**triaged** one: eight identical-looking `DELEGATES-TO-WRONG-MEDIUM` rows became three silent fixes
and five refusals a human genuinely must decide, each carrying the sentence that says why. That is
a better outcome than zero refusals would have been, and it is not what the acceptance asked for.

---

## 1. What the watch opened on, measured before a line was written

`census_r.py` against the operator's live project, read-only:

```
19 scenes, 14 refuse, 1 flag        (identical on the read path and the enforcement path)
  13 × VISUAL_DEMANDS_ON_SCREEN_TEXT   the description names "23 x 14" / "multiplication problem"
   1 × NARRATION_TEXT_UNDECLARED       scene 0, no text_carried_by
```

The operator's **14 hard refusals** reproduce exactly, and **all fourteen are the same verdict**,
`DELEGATES-TO-WRONG-MEDIUM`. The design layer is clean: `GET /design-review` returns **0 refusals,
10 flags** (`SEGMENTING` ×7, `PRACTICE_NOT_PREPARED` ×2, `UNDECLARED_SCRIPT_GAP` ×1) — RC-Q18 held.

⛳ **So the whole of the operator's gate blockage is one limb, and that limb is the one with a
deterministic exit.** That is why RC-R4 is the centerpiece and why it was worth building.

---

## 2. RC-R4 — the pass

### 2.1 Where it runs, and why there is only one candidate seam

`pipeline_orchestrator_v2.handle_stage_completion`, in the `next_stage is None` branch, immediately
before `pipeline_paused_at_gate`. Stage 2 validates and writes its scenes; the next thing that
happens is that a human starts judging them. There is no other seam between the two — and the stage
body is frozen (§3), so the repair could not live there even if it belonged there, which it does
not: **the pass reads the SAVED rows, which is the storyboard the reviewer will actually approve.**

The orchestrator does no work. It POSTs `/projects/{id}/scenes/auto-repair` and logs. The authoring
primitive, the scene rows and the design brief all live in the API, and a second implementation in
the worker would be WP-IVGS-09f's "two builders for one payload".

⛔ **The call never blocks the gate.** A repair pass that fails, times out or answers non-2xx leaves
the gate opening exactly as before, with its refusals intact and honest. What must never be
swallowed is a repair that FAILED, and it is not — see §2.3.

### 2.2 The classification, as data

`MECHANICAL_CODES` is the only thing that decides. It holds all four hard refusals
`storyboard_completeness` can emit, because all four are `DELEGATES-TO-WRONG-MEDIUM` and all four
are answered by the one exit the validator's own message names:

> "author the scene as motion_graphics with a template + parameters (RULE 8)"

That exit is judgment-free: the medium becomes a constant, and the template and its numbers are read
out of the scene's own narration by the primitive WP-IVGS-09f proved. **The other exit the same
message offers is not**: *"set `text_carried_by='narration'` and describe the non-text situation"*
requires rewriting prose, which is authorship, which a model asked to do would make a prompt loop.

**Not one of `design_review`'s sixteen hard codes is mechanical**, argued individually in the module
docstring in three families — the fix is a scene that does not exist; a declaration is missing and
there is no default for "which of Gagné's nine events is this"; or the finding IS the belt proving a
regression shipped, and repairing it would erase the evidence.

`test_every_hard_refusal_the_classifier_emits_is_classified` fails the day a fifth refusal kind is
added without arguing it into one column or the other.

### 2.3 What it writes, including the failures

Migration 0054 adds `storyboard_design_briefs.system_corrections`, **nullable with no server
default**, because NULL ("the pass never ran") and `repaired: 0` ("it ran and found nothing") are
different facts and a default would have collapsed them on every historical brief.

Each correction records: scene, refusal code and the validator's words, `was → is`, the template and
its parameters, **the original `visual_description` — preserved, never rewritten, and recorded so
the reviewer can see that it was** — and, when authoring refused, the authoring error beside the
original refusal. **Both errors, per the ruling.** The gate renders it as a **System corrections**
section, failures first.

---

## 3. The acceptance run — and the number that is not zero

A real end-to-end generation on the throwaway project, from the operator's own uploaded script
(3,138 bytes, byte-identical to the live project's `transcripts.source_text`), same three learning
outcomes, same 300 s budget. `auto_repair_pass_complete`, 15:04:42Z:

```
scenes 15 | refusals_before 8 | mechanical 8 | judgment 0
          | repaired 3 | repair_refused 5 | refusals_after 5
```

**The three that took:**

| scene | code | was → is | template |
|---|---|---|---|
| 1 | `MOTION_CONTRADICTS_NARRATION` | motion_graphics → motion_graphics | `highlight_and_hold{top:23, bottom:14, column:0}` |
| 2 | `MOTION_CONTRADICTS_NARRATION` | motion_graphics → motion_graphics | `column_multiplication_step{top:23, bottom:14, step:0, phase:full}` |
| 6 | `MOTION_CONTRADICTS_NARRATION` | motion_graphics → motion_graphics | `column_multiplication_step{top:23, bottom:14, step:1, phase:complete}` |

**The five that did not, with the guard's own words:**

| scene | code | why the repair was refused |
|---|---|---|
| 0 | `NARRATION_TEXT_UNDECLARED` | *"template 'place_value_split' needs narration about place value/tens place/ones place, and this scene's words contain none of them: 'Hi! Today, we're going to learn how to multiply two-digit numbers…'"* |
| 4 | `VISUAL_DEMANDS_ON_SCREEN_TEXT` | same, over *"Can you identify the unit numbers and 10's in the problem 23 x 14?"* |
| 5 | `VISUAL_DEMANDS_ON_SCREEN_TEXT` | same, over *"Explain why 56 is different from 60 in terms of units and tens"* |
| 7 | `MOTION_CONTRADICTS_NARRATION` | *"the narration announces 4 — '## Step 4: Add the Two Answers' — but `column_addition_carry{top:230, bottom:92}` never produces 4; it draws [3, 9, 12, 92, 230, 322]"* |
| 10 | `NARRATION_TEXT_UNDECLARED` | *"the narration says 322, which `highlight_and_hold{top:23, bottom:14}` can never draw — the largest number it produces is 23"* |

**Every one of the five was put back** — `media_type` reverted, `generation_params` untouched — and
its original refusal stands. Verified in the database and in the gate payload.

### ⛔ The acceptance target was not met, and the honest reading of that

Scene 0 is an introduction. Scene 5 asks the learner to *explain*. Neither is a motion graphic, and
**the guard refusing to draw one is the correct answer, not a failure of the guard.** What the
measurement shows is that the validator's "default exit" is the right exit for most of this class
and the wrong exit for some of it, and that the authoring guard is what tells the two apart —
**failing safe, downstream of the repair, exactly where a wrong default should be caught.**

Whether "mechanical, tried, and refused by the guard" should be **reclassified as judgment** is an
operator ruling and is deliberately not taken here. The counters report `mechanical_before` and the
residue separately, so either ruling applies to the same numbers without re-running anything.

---

## 4. RC-R1 — the button did not lie. It crashed.

The order asks whether `POST approve` refuses server-side. **It does, and has since WP-IVGS-10
Task 3**: `STORYBOARD_INCOMPLETE`, 409, every failing scene named. That limb is proven working and
now also carries a `refusals` integer beside the code, so no surface has to parse an English
sentence for N.

⛔ **The defect is one step earlier and it is worse.** Pressing Approve on the acceptance project
with five refusals outstanding returned:

```
HTTP 500
{"error":{"code":"INTERNAL_ERROR","message":"An unexpected error occurred",
          "request_id":"d3ed86f6-3a61-4483-aff2-18752dda717c"}}
```

`approve_storyboard` runs `_author_missing_motion_specs` **before** the completeness check, and that
helper raises `RegenerationError` for a motion scene whose template cannot be authored — by design,
WP-IVGS-09f: *"one scene that cannot be drawn is a reason not to start."* `_gate_decision` caught
`PipelineAlreadyRunningError`, `StoryboardIncomplete` and `ValueError`, and not that.

⛔ **And the gate decision row was already written** — `gate_decision … decision=approved`, 15:05:39Z
— one second before the traceback. So an approval stood on record, with a 500 on screen, and nothing
dispatched.

⛔ **A 500 says the system BROKE. A refusal says the system REFUSED.** They are opposite instructions
about what to do next, and the operator got the wrong one on a storyboard that was behaving exactly
as designed. The log held the entire answer — *"the narration announces 4 … but
`column_addition_carry` never produces 4"* — and the surface discarded it.

**Fixed**: `MOTION_AUTHORING_REFUSED`, 409, carrying the guard's sentence and stating that the
approval was recorded and only the dispatch refused. Proven live after redeploy.

### The button itself

`GateReviewPanel` now disables **Approve** while any refusal stands, computing the count from
`state.completeness` — the same array the banner counts, not a second fetch and not the error body,
because two numbers derived two ways will disagree. The reason renders as a sentence under the
buttons as well as a tooltip. **Reject and Regenerate stay enabled**: they are how a reviewer ACTS on
a refusal, and disabling them would trap the gate closed.

**Proven at both states.** Nonzero: 5 refusals → 409 by name. Zero: after a reviewer resolved the
five residual scenes by hand (declaring the carrier on two, applying RULE 1's deletion test to two,
and judging scene 7's section heading not to be a drawn step), the gate reads **0 refusals, 4 flags
intact**, and `zerocheck.py` confirms the pre-gate authoring would touch **nothing** and
`refuse_if_incomplete` passes over all 15 scenes — **without dispatching, so no GPU was spent to
prove it.**

### ⛔ The other banner, rowed not built

`DesignBriefPanel` said *"N design refusals — approving will be refused by name."* **False.**
`design_review`'s sixteen hard codes are enforced nowhere on the approve path. Measured 0 today on
both projects, so nobody has been misled yet, but it is the same class of lie RC-R1 exists to
remove. **The wording is corrected to what is true**; whether design refusals should BLOCK approval
is a change to what the gate IS, and it is the operator's ruling.

---

## 5. RC-R2 — findings at the work surface

A badge on the card (red carrying the refusal code, amber for a flag, **nothing when clean** — a
badge that is always there stops being read) and the findings in full, in the server's own words,
inside the Edit modal above the actions. One array, indexed once on the page, shared by the panel,
the cards and the modal, so no two surfaces can disagree about the same scene. `SceneAssessment`
gained a stable `code` for this and for the repair pass.

⛔ **The one-click did not exist.** The order says it *remains*; it never did. WP-64's "Adapt
description" proposes prose for the medium already selected and authors no template — so flipping
the dropdown to Motion Graphics and pressing Save has always produced a motion scene with no
template, which is `MOTION_WITHOUT_TEMPLATE` and the `Needs template` badge WP-IVGS-09c added to
explain it. Now built as `POST /scenes/{sid}/author-motion` with an emerald button beside Adapt:
**the same primitive `storyboard_repair` calls**, refusing by name and leaving the scene untouched
when the guard refuses.

---

## 6. RC-R3 — two rows, nothing built

**(a) The Jobs tab names the first stage and the ledger records two.** Live `680d9e4c`: one
`render_jobs` row, `job_type = transcript_refinement`, against `pipeline_checkpoints` holding
`transcript_refinement` (14:06:52Z) **and** `storyboard_generation` (14:08:09Z). The tab renders
`job.job_type` verbatim (`jobs/page.tsx:203`) and that column is frozen at creation, so storyboard
generation — the stage that produced the artefact under review — has no row at all. Reproduced on
the acceptance project. Registered on recovery plan §4 **Phase 3, "Ledger-authoritative read
model"**, whose exit test is *"on a fresh run, Jobs tab matches the ledger at every stage."* It does
not. Same family as RC-L8's TYPE column.

**(b) No design-duration advisory exists, and the live project is 17:00 against a declared 5:00.**
`max_runtime_seconds = 300`; nineteen scenes sum to **1,020 s**. Nothing compares them —
`design_review` has no duration finding, `gate_service` computes none, and `max_runtime_seconds`
reaches only the job context and the stage-1 prompt. ⛳ **And it must never be a refusal**: duration
derives from the design by ruling, and a gate refusing seventeen minutes would enforce a number the
operator typed before they knew what the lesson was. The row is an **advisory in the brief**. Note
the direction of the historical error: WP-63 records stage 1 being told to *"align with
max_runtime_seconds"* and turning a four-minute script into 1:45 — the budget has already once been
allowed to eat the content.

---

## 7. RC-R5, new — the authoring model picks a template the guard forbids

Three of five repair refusals are one shape: the model answered `place_value_split` for narration
containing no place-value words. **Not introduced here — measured here for the first time**, because
nothing before this package ever called `author_params_for_scene` on a scene that was not already
`motion_graphics`. It may be a prompt defect (the authoring prompt never tells the model it may
answer "none of these fit"), or it may be RC-R4's open classification question. **Rowed, not fixed:
three instances is a measurement rather than one, and the ruling is the operator's.**

---

## 8. Tests

| suite | result |
|---|---|
| `ivgs-api/tests/test_wpivgs12i_auto_repair.py` (new, 14 tests) | **14 passed** |
| `ivgs-api/tests` full, after every change in this package | **1811 passed, 0 failed** (`api-tests-1811-passed.txt`) |
| `ivgs-frontend` `tsc --noEmit` | **clean, exit 0** (`frontend-tsc-clean.txt`, empty by design) |

⛳ **The authoring call is stubbed in every unit test and that is not a shortcut.**
`author_params_for_scene` reaches a live model; WP-IVGS-09f already proves what it produces and the
guard already proves what it refuses. What is new is the pass AROUND it — which refusals it selects,
what it writes, what it puts back, what it declares — and all of that is decidable with a stub. The
real-engine proof is §3, run through the actual pipeline.

`test_one_authoring_call_per_refused_scene_and_not_one_more` is the **no-prompt-loops rule made
mechanical**: it asserts one call per mechanically-refused scene per pass, in index order, and that
the clean scene was never sent to a model at all. A future "just retry once" fails it.

---

## 9. Deploy — node-01 only, §6.1a

| container | image | verified |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.39.1-approve-refusal-named` | `sha256:acb97af1e1bd…` **by image ID** |
| `ivgs-nextjs` | `ivgs-frontend:v5.39.0-auto-repair` | `sha256:26ac97a1b147…` |
| `ivgs-celery-default` | `ivgs-workers:v5.39.0-auto-repair` | `sha256:0f2edb534f5b…` |
| `ivgs-celery-composition` | `ivgs-workers:v5.39.0-auto-repair` | `sha256:0f2edb534f5b…` |
| `ivgs-celery-beat` | `ivgs-workers:v5.39.0-auto-repair` | `sha256:0f2edb534f5b…` |

stderr never redirected; `verify-deployed-image.sh` green on all five; **and the running `.Image` ID
compared against the banked artifact digest for each**, per RC-Q8 — all five match. `docker ps`
shows all five healthy, per RC-P19: a verified image is not a running process.

⚠ **`v5.39.0-auto-repair` of the API is superseded by `v5.39.1`** and was live for four minutes. Both
are banked with digests. The frontend and workers did not change between the two.

**Migration 0054 applied to the live database** (`alembic_version` 0053 → 0054) and to
`ivgs_reconciliation_test`. Additive, nullable, no backfill, no data touched.

---

## 10. The tree

**Committed and HELD — one commit.** `git push` is the operator's; nothing was pushed.

⛔ **`ivgs-infra/.env` is DIRTY and is NOT mine to stage.** `IVGS_API_TAG`, `IVGS_FRONTEND_TAG` and
`IVGS_WORKERS_TAG` were moved to the new tags as part of the deploy. That file is untracked and
gitignored (§3, "never touch") and it is left exactly as the deploy left it.

⛔ **THE ACCEPTANCE PROJECT IS STILL ALIVE AND IS THE OPERATOR'S TO DELETE.**
`0840e6c2-ab35-4206-bced-2eac9bde6dd5` — "WP-IVGS-12i acceptance (CLAUDE TEST - delete via WP-59)".
It holds 15 scenes, one design brief with a `system_corrections` record, one transcript and one
uploaded asset. It carries **one recorded gate decision** (approved, refused at dispatch, nothing
rendered). Deleting it through the WP-59 flow also exercises P2.47 site 5, which is a small bonus
and not a reason to delay.

**Nothing was written to the operator's live project.** The only statements this package makes about
`680d9e4c` come from `SELECT`s and from `census_r.py`, which computes and returns and writes nothing.

---

## 11. Push block — the operator's

```bash
# node-01
cd /opt/ivgs
test "$(git rev-list --count origin/main..HEAD)" = "1" || { echo "REFUSED: expected 1 held commit, found $(git rev-list --count origin/main..HEAD)"; exit 1; }
git log --oneline origin/main..HEAD
git push origin main
```
