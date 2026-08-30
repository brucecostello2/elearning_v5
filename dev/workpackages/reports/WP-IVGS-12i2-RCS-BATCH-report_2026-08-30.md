# WP-IVGS-12i2 — the RC-S batch: a ghost assessment, a loophole, and the first check that asks whether the content is TRUE

**Session:** 2026-08-30 (second watch). **Order:** DEFECT ORDER — RC-S batch.
**Ledger:** `OUTSTANDING_WORK.md` §12i-watch2.
**Evidence:** `dev/workpackages/reference/wpivgs12i2-evidence/`.
**Live project READ, never written by hand:** `680d9e4c-608b-488a-9270-9b4317a7f693`.
**Everything written happened on:** `43c59a2a-917a-4df0-9368-ce5752f1651d`.
⛔ **It is still alive and must be deleted through the WP-59 flow.**

---

## STATE AT SESSION END

**Done.** All four ordered rows. RC-S1 measured to its cause and fixed there,
with the acceptance proven by two real pipeline runs. RC-S2(a) closed and
calibrated against both live designs. RC-S2(b) measured and rowed, not tuned.
RC-S4 built for the decidable half and rowed loudly for the half that is not.
RC-S3 widened. One defect of my own found on the acceptance run and fixed.

**Mid-way through: nothing.**

**How the order is now stale.**

1. RC-S1 offered four candidate mechanisms. **It is the third — stale rows —
   and the first (call 2 emitting two) is disproved, not merely unchosen:** the
   active contract emits exactly one assessment per outcome.
2. RC-S4 asks for a lint "over every scene narration + every authored template's
   declared numbers". **The narration limb is the whole of the hard check.** The
   template limb is already discharged by `motion_authoring.producible_numbers`
   (WP-IVGS-10), which decides what a spec can legitimately draw phase by phase;
   re-deriving it here would be a second implementation of one rule. The
   template's operands are read and **quoted in the refusal as evidence**.

**Learned and not written down anywhere else.** The equation lint's calibration
is a finding in its own right: **the uploaded script carries 17 complete
arithmetic claims and all 17 are true; both live designs carry ZERO.** The lint
has nothing to bite on precisely because the designs abandoned the script's
teaching. That is the strongest single argument for RC-S2(a) in this report and
I did not expect to find it.

---

## 1. RC-S1 — the second assessment was a ghost

### The measurement, before any code was written

`rcs1-stale-rows-mechanism.txt`, read-only:

```
brief 2fb0b951 active=False 14:12:04  designs=19  assess-by-LO {LO-2:[3],  LO-1:[14], LO-3:[18]}
brief b436d74d active=True  15:42:37  designs=17  assess-by-LO {LO-1:[9],  LO-2:[12], LO-3:[15]}

scene ROWS in the database: 19        indices 0..18
indices in the ACTIVE contract:       0..16
ROWS WITH NO ENTRY IN THE ACTIVE CONTRACT: [17, 18]
  orphan 17  updated_at 14:12:05  event=practice  serves=['LO-3']
  orphan 18  updated_at 14:12:05  event=assess    serves=['LO-3']
every regenerated row: updated_at 15:42:37
```

**The active contract emits exactly one assessment per outcome.** Call 2 was
innocent, the merge was innocent, and the repair pass was innocent. Row 18 is an
`assess` serving LO-3 left behind by the previous generation, so the gate saw
LO-3 assessed by scene 15 and scene 18 and fired `OUTCOME_ASSESSED_TWICE`.

⛳ **The validator's own sentence — *"this firing means the structural guarantee
has stopped holding"* — was true about the database and false about the
contract.** That is why it read as a contract-7 regression and is not one.

### The cause, self-documented for two packages

`ivgs-api/app/services/storyboard_service.py:92-98`:

> a re-run that produces FEWER scenes than the project already has leaves the
> surplus rows behind. This method sees one scene at a time and cannot know the
> new total ... Trimming needs the whole-storyboard write that Stage 2 does not
> make; ledgered for the Temporal cutover.

That is RC-Q10, known and unfixed. The gate got louder around it (the design
brief made the surplus visible) but nothing ever removed it.

### The fix

`storyboard_repair.prune_scenes_not_in_design` reconciles the rows against
`scene_designs` on the **active brief** — the design of record by RC-Q18's
ruling — and runs **before** the repair pass, at the pre-gate seam WP-IVGS-12i
already established. It is the whole-storyboard write, made where it can be made
without touching a frozen body.

- **Index-set membership, not `index >= count`.** A contract with a gap in its
  indices is trimmed correctly by the first and wrongly by the second.
- ⛔ **It refuses to guess.** No active brief, or a brief with no
  `scene_designs`, prunes **nothing** and records *which* silence it is, so a
  pre-v8 storyboard is untouched and a reviewer can tell "there was no surplus"
  from "I could not tell whether there was one".
- Every removed row is declared in full — index, event, outcomes, media type,
  narration, `updated_at` — on the brief and at the gate.
- ⚠ **What deletion takes with it, stated rather than discovered later:**
  `assets.scene_id` is `ON DELETE SET NULL` so generated media survives and is
  merely unlinked; `prompts.scene_id` and `project_model_selections.scene_id`
  are `ON DELETE CASCADE` and go.

### The acceptance — two real pipeline runs

| | scenes designed | rows after | pruned | per-LO assess |
|---|---|---|---|---|
| generation 1 | 37 | 37 | **0** | 1 / 1 / 1 |
| regeneration | **16** | **16** | **21** | **LO-1=1, LO-2=1, LO-3=1** |

Among the 21 pruned rows was **scene 36, an `assess` serving LO-1** — the live
defect, reproduced on a fresh project and removed. The repair pass reported
`scenes: 16`, not 37: the prune ran first, as designed.

---

## 2. RC-S2(a) — the loophole, and why the fix needed no new bookkeeping

12b's rule was `gap >= HARD_GAP_CHARS and not dropped_beats`. **The second clause
is GLOBAL where the first is PER-SPAN**, so one throwaway declared drop anywhere
made every hole in the script soft.

⛳ **The fix is to delete the global clause, and that IS the operator's rule
rather than an approximation of it** — because a declared drop's span is already
merged into the coverage computation. A stretch that survives as a gap is, by
construction, one that **no drop declared**. Nothing needed to be matched up;
the matching was already happening.

### Calibration against both live designs — both refuse, and both correctly

| design | covered | gap | drops | old rule | new rule |
|---|---|---|---|---|---|
| WATCH-1 (19 scenes) | 1,622 / 3,138 (**51.7%**) | 1,473 | 2 | 0 refusals | **1 refusal** |
| WATCH-2 regen (17 scenes) | 110 / 3,138 (**3.5%**) | 2,968 | 1 | 0 refusals | **1 refusal** |

WATCH-1's 1,473-character hole is the script's whole *"Step 4: Add the Two
Answers"* section — a real teaching beat, unused and undeclared. **A
1,473-character hole is not span-offset arithmetic**, which is the doubt that
keeps gap *attribution* soft and which does not reach a threshold this size. So
refusing it is correct, and refusing a design that used 3.5% of its script is
not a close call.

⚠ The two 12b tests that pinned the loophole are **superseded in place** with the
change of sense written into the class docstring, not deleted. One of them now
asserts the inverse of what it asserted, and says so.

---

## 3. RC-S2(b) — the input was full; this is variance

**Call 1 received the whole script.** `refined_text` is byte-identical to
`source_text` at 3,138 characters (stage 1 did not paraphrase this run), and the
reconstructed call-1 user prompt carries all 3,150 characters of the combined
transcript **including the "Step 4" section the design left uncovered**.

| | storyboard `total_input_tokens` | output | scenes | sourced / designed | coverage |
|---|---|---|---|---|---|
| WATCH-1 | **15,547** | 3,796 | 19 | 13 / 6 | 51.7% |
| WATCH-2 regen | **13,993** | 3,185 | 17 | **6 / 11** | **3.5%** |

Both are full-scale; the difference is a smaller design and a shorter call-2
user message, not a truncated input. Same script, same prompts, same model, same
day, and coverage moved from 51.7% to 3.5% while invention moved from 6 scenes to
11.

**Full input + script-free output = RC-P15-class variance.** The order's ruling
applies: **rowed with both censuses, not tuned.** ⛳ And RC-S2(a) is the answer to
it — the fidelity rule does not make the model faithful, it makes an unfaithful
design *refuse*, which is the only lever available that is not prompt-tuning
against a sample of two.

---

## 4. RC-S4 — the first check that asks whether the content is TRUE

Scene 4 of the regenerated design:

> "To multiply two double-digit numbers, we need to multiply the tens and the
> units separately."

The classic misconception, taught as method. A learner following it computes
23 × 14 as 20 × 10 + 3 × 4 = 212. Every check this pipeline has asks whether a
scene is **declared**, **depictable**, or **consistent with its template**. Not
one asks whether it is **right**.

### The deterministic half, built

`shared/design/equations.py` parses **complete** arithmetic claims — both
operands, the operation and the result, in prose or symbols — and
`design_review` hard-refuses any false one as `NARRATION_ARITHMETIC_FALSE`,
naming the scene and quoting the claim with what it actually computes to.

⛔ **An incomplete statement is never a claim.** *"Now multiply 4 times 3"*,
*"write the 2 underneath and carry the 1"*, *"our first answer is 92"* and
*"Our problem is 23 times 14"* all parse to nothing. The cost is false
negatives, which are the right failures for a check that hard-refuses.

### Calibration, which turned out to be a finding

| | complete claims | false |
|---|---|---|
| the operator's uploaded script (3,138 chars) | **17** | **0** |
| WATCH-1 design | **0** | 0 |
| WATCH-2 regen | **0** | 0 |

**The script is full of checkable arithmetic and both designs contain none of
it.** The lint passes a correct script cleanly — the half of the calibration
that matters most for a hard refusal — and has nothing to bite on in either
design because both abandoned the script's teaching.

Proven live on the test project: `"4 times 3 equals 13"` seeded into scene 0
refuses with `computed: 12, stated: 13`; the same sentence made true returns
zero arithmetic refusals.

### ⛔ The method-prose half, rowed loudly

*"Multiply the tens and the units separately"* contains no numerals and states
no equation. Deciding it is wrong requires knowing what the method computes —
a semantic judgement about generated prose. **It stays at the human gate until
the L7 checker (M3.3)**, with scene 4 as the driving evidence, and
`test_the_method_prose_half_is_NOT_caught_and_that_is_declared` pins the
limitation so that no future reader takes the presence of an arithmetic check
for a guarantee that the maths was checked.

⛳ **And the primary guard for an uploaded script is not this lint. It is
RC-S2(a).** A design anchored to a correct script cannot state a wrong method;
scene 4 exists because the regeneration used 110 characters of 3,138 and
invented the rest.

---

## 5. RC-S3 — the belt widened, and a defect of my own

12h's belt is assessment-anchored and its own docstring names the residue:
*"The practice is NOT compared against the worked examples here."* So the live
regen's LO-2 `guide` scene 10 and `practice` scene 11 — **byte-identical**
narration — were invisible to it, as were LO-1's 6/7/8 and LO-3's 13/14.

`SAME_OUTCOME_NEAR_DUPLICATE` compares **any** two scenes serving one outcome,
using `duplication_verdict` and the same calibrated thresholds so a retune moves
both limbs together. **Hard only where 12h's ruling made it hard**: any pair
containing an `assess` is left entirely to the hard limb, so no flag ever
appears beside a refusal about the same two scenes. Elsewhere it flags — two
`guide` scenes restating one question are usually a defect and sometimes
deliberate repetition for an anxious nine-year-old, and that is the reviewer's
call. **9 flags on the acceptance regen**, over exactly the guide/practice shape.

⚠ **A defect of mine, caught on the acceptance run and fixed.** The limb first
shipped reusing `duplication.explain`, whose sentences are written for the
assessment-anchored limb and begin *"the assessment"*. The live gate then
reported *"the assessment restates that scene"* about a `guide`/`practice` pair
in which neither scene is an assessment. A shared helper whose wording fits only
one caller is worse than two sentences. Fixed, redeployed as `v5.40.1`, and
pinned by `test_the_flag_does_not_call_either_scene_the_assessment`.

---

## 6. ⛔ What this deploy CHANGES on the operator's live gate

Stated plainly because it is a change the operator did not make and will see:

- **The live storyboard gate now shows 1 hard design refusal** —
  `UNDECLARED_SPAN_OVER_THRESHOLD`, 2,968 of 3,138 characters used by no scene
  and declared in no drop. It showed none before. **The design did not change;
  the rule did**, and the design has been that unfaithful since 15:42.
- **Several `SAME_OUTCOME_NEAR_DUPLICATE` flags** appear over the guide/practice
  pairs. Flags block nothing.
- `OUTCOME_ASSESSED_TWICE` **will clear on the next regeneration**, when the
  prune removes rows 17 and 18. ⛔ **It is still showing now**, because nothing
  in this package touches a project outside a generation and I did not run one
  on the operator's project.
- No arithmetic refusal: the live design states no complete claims.

---

## 7. Tests

| suite | result |
|---|---|
| `test_wpivgs12i2_rcs_batch.py` (new, 20 tests) | **20 passed** |
| `ivgs-api/tests` full, after every change in this package | **1831 passed, 0 failed** (`api-tests-1831-passed.txt`) |
| `ivgs-frontend` `tsc --noEmit` | clean, exit 0 |

The suite pins the mechanism *before* the fix (`OUTCOME_ASSESSED_TWICE` fires on
the live shape), the fix, the refusal to guess, and the declaration — plus the
span rule calibrated on both live designs, the lint's true/false/incomplete
classes, and both duplication limbs.

⚠ **A harness characteristic worth recording:** when a DB-backed test in this
suite fails, session teardown blocks on the `TRUNCATE` and the run hangs rather
than reporting. Recovering needs
`pg_terminate_backend` over `ivgs_reconciliation_test` plus a manual truncate.
Not caused by this package; it cost real time and is not written down anywhere.

---

## 8. Deploy — node-01 only, §6.1a

⛳ **Node-01 only, and the order's condition is the reason: nothing moved in
`ivgs-workers`.** `git status` over that tree is empty. The validator
(`design_review`) and the merge-reconciliation (`storyboard_repair`) are both
API-side, and `shared/design/equations.py` is imported by the API alone.

| container | image | verified |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.40.1-rcs-batch` | `sha256:ab1913df7648…` **by image ID** |
| `ivgs-nextjs` | `ivgs-frontend:v5.40.0-rcs-batch` | `sha256:7d41bae3786f…` **by image ID** |

stderr never redirected; `verify-deployed-image.sh` green; running `.Image`
compared against each banked artifact digest (RC-Q8); `docker ps` healthy
(RC-P19). `v5.40.0` of the API was live for ~20 minutes and is superseded by
`v5.40.1`; both are banked with digests. **No migration** — this package adds no
column.

---

## 9. The tree

**Committed and HELD — one commit** (`6bdf6f0`). Nothing pushed.

⚠ **The count is ONE, not two: WP-IVGS-12i's commit `ed72440` is already on
`origin/main`** — the operator pushed it between the two watches. The push
block below is therefore count-gated at 1.

⛔ **`ivgs-infra/.env` is DIRTY and is NOT mine to stage** — `IVGS_API_TAG` and
`IVGS_FRONTEND_TAG` moved with the deploy. Untracked and gitignored (§3).

⛔ **THE ACCEPTANCE PROJECT IS ALIVE AND IS THE OPERATOR'S TO DELETE.**
`43c59a2a-917a-4df0-9368-ce5752f1651d` — "WP-IVGS-12i2 RC-S acceptance (CLAUDE
TEST - delete via WP-59)". 16 scenes, two design briefs (one superseded), one
recorded `regenerate` gate decision. Scene 0's narration was edited twice to
prove the equation lint and **restored to its original text**.

**Nothing was written to the operator's live project by hand.** Its scene rows
were last written at 15:42:37 by the operator's own regeneration.

---

## 10. Push block — the operator's

```bash
# node-01
cd /opt/ivgs
test "$(git rev-list --count origin/main..HEAD)" = "1" || { echo "REFUSED: expected 1 held commit, found $(git rev-list --count origin/main..HEAD)"; exit 1; }
git log --oneline origin/main..HEAD
git push origin main
```
