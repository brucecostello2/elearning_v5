# IVGS Development Status — 2026-08-30 (WP-IVGS-12 + 12b…12h, the Design Core)

**The one-page board.** Updated as the closing act of every package
(`dev/CLAUDE.md` §12a). ⛔ **A stale board is a defect, not an oversight.**
Everything below is from measurement taken this session, not from memory.

---

## Fleet — api + workers `v5.38.3-two-call-design`, frontend `v5.37.0-design-core`

⛳ **WP-IVGS-12h IS LIVE, AND RC-Q9g IS CLOSED.** Nodes 01-04 rebuilt from
`a41d642`, banked with digest sidecars, loaded from the artifact store, deployed
under §6.1a with the compose invocation derived from container labels. **All
seven containers compared by IMAGE ID against the banked `.digest`** — api
`sha256:df91e1809c65…`, workers `sha256:7f8a76e423ed…` on all four nodes,
identical. Migration **0053** applied to production **before** the new image and
exercised 0052→0053→0052→0053 on the test database. `storyboard_generation_system`
**v8** published after the deploy, v1–v7 preserved inactive; the NEW lineage
`assessment_authoring_system` at **v1**, active. `CONTRACT_VERSION =
design-contract-7`, the two schemas, the per-call budgets (12,288 / 4,096), the
per-call timeouts (180 / 60 of a derived 240) and the belt's thresholds were all
read back out of the RUNNING containers.

⛔ **FOUR TAGS FOR TWO COMMITS, AND `v5.38.0` AND `v5.38.1` MUST NOT BE
DEPLOYED.** `v5.38.0` shipped with `IVGS_BUILD_REF` unset and reported its version
as `"unknown"`; `v5.38.1` carried the wrong ref and reported itself as `v5.38.0`.
Both are my slips, both are banked, and neither was ever a rebuilt tag — the bytes
differ, so the tags differ. `v5.38.2` is `d8da66c` correct; **the fleet is on
`v5.38.3`**, which adds the motion-catalogue fix.

⛔ **RC-Q13 IS OPEN AND IT DESCRIBES A FLEET THAT IS RUNNING.** AD-05 declares
stage 2 at soft 270 / hard 300, so the client budget is **240 s**. Measured
stage-2 wall clock across 13 generations (12g's banked logs and 12h's own):
**135–564 s. Ten exceed the client budget and eight exceed the Celery hard
limit.** No storyboard job has ever been run through the real Celery task since
contract-5, so this has never surfaced. **Raising a declared conformance number
is the operator's ruling, not an agent's.**

ⓘ **WP-IVGS-12g, superseded by the above but kept for the lineage.**

✅ **WP-IVGS-12g IS LIVE.** Nodes 01-04 rebuilt from `112831f`, banked with
digest sidecars, loaded from the artifact store, deployed under §6.1a with the
compose invocation derived from container labels (**two** `-f` files on
node-01, not the three §6 describes — the machine wins). **All seven containers
compared by IMAGE ID against the banked `.digest`** — api
`sha256:46159712 5d4a…`, workers `sha256:439d9d7cf545…` on all four nodes,
identical. **No migration: contract-6 adds no storage surface**, proved by a
database round trip, and 0052 was NOT run down on production because its down
direction drops a column that now holds rows. `storyboard_generation_system`
**v7** published after the deploy, v6 preserved inactive, exactly one active
row. `CONTRACT_VERSION = design-contract-6`, `scenes[]` narrowed to seven
events, `storyboard_max_tokens` floor **12,288** — all read back out of the
running containers.

⛔ **THE FLEET RAN `v5.37.6` FOR ~20 MINUTES AND IS NOT ON IT.** The first
acceptance run truncated a generation at the 8,192-token floor, so the floor
moved and both images were rebuilt at `v5.37.7`. `v5.37.6` exists as a git tag
and a banked artifact; **nothing should be deployed from it.**


✅ **THE 12e TAG SPLIT IS CLOSED.** 12f changed the worker-side parse, the client
seam and `celery_app`'s arming alongside the API, so **both images rebuilt** and
the fleet is back on one tag. The frontend stays at `v5.37.0` — no frontend code
changed and rebuilding only to move a tag would mint a new digest for identical
source.

✅ **WP-IVGS-12f IS LIVE.** Nodes 01-04 rebuilt from `ac77733`, banked with digest
sidecars, loaded from the artifact store, deployed under §6.1a with the compose
invocation derived from container labels. **All seven containers compared by
IMAGE ID against the banked `.digest`** — api `sha256:f0c067d792be…`, workers
`sha256:70ec2c3fefa7…` on all four nodes, identical. Migration **0052** applied
to production **before** the new image (the ORM reads the column), exercised
both directions. `storyboard_generation_system` **v6** published after the
deploy, v5 preserved inactive, exactly one active row. `CONTRACT_VERSION =
design-contract-5`, the property order `['assessment_plan',
'designed_assessments', 'scenes', …]`, the three grammar pins, the merge
placement and the gate's live verdicts were all read back out of the RUNNING
containers. ⚠ **`/api/v1/health` is on port 8001**, not 8000. Report §12f.5.

ⓘ **WP-IVGS-12d, superseded by the above but kept for the lineage.** Nodes 01-04 rebuilt, banked with digest sidecars,
loaded from the artifact store and deployed under §6.1a; **all four worker
containers on ONE image ID, `sha256:d25feffc9741…`, identical to the banked
`.digest`.** Migration **0051** applied to production ahead of the new API
(additive; **0 existing briefs**, the operator's 4 projects untouched).
`storyboard_generation_system` **v4** published after the deploy, v3 preserved
inactive. `CONTRACT_VERSION = design-contract-4`, the property order
`['assessment_plan', 'scenes', …]` and `PLAN_ENTRY_UNREALIZED` were read back
out of the RUNNING containers. Report §12d.4.

⚠ **THIS TABLE WAS STALE WHEN WP-IVGS-12h STARTED AND CONTRADICTED THE BOARD'S
OWN HEADLINE**: it read `v5.37.5-assessments-authored` on all four nodes while the
section above it said `v5.37.7`. The machine said `v5.37.7`. Corrected here, and
named rather than quietly patched — §12a says a stale board is a defect, and a
board that disagrees with itself is the shape that teaches a reader to trust
neither half.

| Node | Card / role | Key images | Health exceptions |
|---|---|---|---|
| **node-01** `.90` | CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers, monitoring. 16 GB | **api `v5.38.3-two-call-design`** + workers **`v5.38.3-two-call-design`**; frontend `v5.37.0-design-core` (unchanged tree — rebuilding it only to move a tag would mint a new digest for identical source); `ivgs-motion-renderer` `v5.34.0-v7-contract`; scheduler + backup-worker `v5.31.0-hygiene` | none |
| **node-02** `.91` | LLM (Llama-3.3-70B FP8) | worker **`v5.38.3-two-call-design`**; vLLM pinned `sha256:3dbe092e…` | ⛔ **stage 2's derived 240 s client budget is SHORTER THAN THE MEASURED WORK (280–564 s) — RC-Q13**, split 180/60 across the two calls |
| **node-03** `.92` | Video (CogVideoX, Wan) | `cogvideox-worker` **`v5.38.3-two-call-design`** | ⓘ also runs two servers no IVGS package placed — RC-I5; ⛔ **blank clip recorded as success — RC-P3** |
| **node-04** `.93` | Image + TTS + talking head. RTX PRO 6000 | worker **`v5.38.3-two-call-design`**; `ivgs-coqui` `coqui-v5.2.9-params`; vLLM pinned `sha256:3dbe092e…` | none |
| **node-05** `.94` | Qwen3.8-27B-FP8 on vLLM. No Celery worker | vLLM `sha256:3dbe092e…` | ⛔ **OUT OF BOUNDS — not contacted** |
| **node-06** `.95` | **OPERATOR-MANAGED, OUT OF BOUNDS.** Telemetry + CLIP scorer | — | not contacted |
| **.96** | **Temporal 1.29.7 host.** gRPC `:7233`, UI `:8080` | — | ⛔ node-01 root ssh **not authorized**; admin method is an operator input |

⛳ **All four worker containers compared by IMAGE ID, not by tag** —
`sha256:70ec2c3fefa7…` on nodes 01-04, matching the banked `.digest`. ⛔ **This is now the rule, not a nicety:**
RC-Q8 is closed, artifacts carry a `.digest` sidecar, and a different digest
under the same tag REFUSES — but `verify-deployed-image.sh` still compares tags,
so the cross-node ID comparison is what actually catches a stale roll-out.

⛔ **RC-I4 IS CLOSED: the cause of the coordinated reboots is a NIGHTLY OPERATOR
POWER-DOWN.** It fired again this session — nodes 02/03/04/05/06 all gone inside
a 33-second window at 05:38:58 UTC, restored ~11:20. **Any package whose
acceptance needs the GPU fleet must not assume overnight availability.**

---

## In flight

**WP-IVGS-12 + 12b…12h — Phase 1 of the recovery plan, the DESIGN CORE.**
**3 commits held, none pushed by me** — measured with
`git rev-list --count origin/main..HEAD` after a `git fetch` at close, per the §0
rule 12c added. At this session's START the same command measured **0**: the
operator had pushed all three 12g commits.

### 12h — the two-call design, and RC-Q9g CLOSED

⛳ **THE PRACTICE IS NO LONGER THE ASSESSMENT.** design-contract-6 guaranteed both
evidence kinds existed and measured the model filling both slots with the same
sentence: **11 duplicate pairs in 15** across five generations, every generation
carrying at least one. **design-contract-7 splits the design across TWO engine
calls** — call 1 writes the plan, the practice and the expository arc; call 2
authors the independent attempts from the OUTCOMES, the PLAN and a code-built
SUMMARY of what the practice covered, and **never sees the practice wording, the
scenes or the script.** The model cannot copy what it never sees.

⛳ **18 of 18 outcome-pairs DISTINCT across six generations of two runs**, against
11 of 15 duplicates under contract-6, on the same script and the same outcomes.

⛳ **AND THE "NO AXIS" CASE — THE ORDER'S STOP CONDITION — DID NOT FIRE.** 12g
measured the two non-numeric outcomes (*explain why*, *check your work*)
collapsing in 5 of 5 completed generations and reserved a per-outcome-type ruling
to the operator. Under contract-7 both invent a **CASE** every time: *"…when
multiplying 93 by 17"*, *"…of 75 by 32"*. **No escalation was needed.** B2's
non-computational LO-3, which collapsed at containment 1.000 under contract-6,
reads **0.556** and is distinct.

⛔ **AND THE BELT THE GRAMMAR CANNOT PROVIDE: `EVIDENCE_NEAR_DUPLICATE`**, a HARD
refusal, `shared.design.duplication`. The assessment scored against its own
practice AND against the lesson's worked examples — containment over stoplisted
tokens with **numerals KEPT**, plus a second limb for the no-fresh-axis case.
**Calibrated on 18 banked 12g outcome-pairs where the classes separate 0.667 |
0.900, threshold in the gap**; 12 of 12 mandated duplicates refuse and B2's
differentiated pairs pass. ⛳ **It is the first hard refusal in three packages
that measures the DESIGN rather than the grammar** — and no grammar can make it
unreachable, because two strings the same author wrote are two strings.

⛳ **AND ITS WORKED-EXAMPLE LIMB CAUGHT WHAT FIVE GENERATIONS OF HAND-COMPARISON
MISSED**: B2's LO-1 assessment under contract-6 is byte-identical to its own
`guide` scene, in a design §12g.10 called *"real scaffolding, correctly faded"*.

⚠ **RC-Q9h ROWED, NOT FIXED — the duplicate moved one layer in.** LO-1's two
practice scenes are the same sentence in 4 of 6 generations. The belt is scoped by
the order to the assessment. Same mechanism, inside one section, and the routes
are named in §12h.12.

⛔ **RC-Q13 ROWED — the declared stage-2 timeout cannot hold the measured work**,
and that is true of the fleet as it stands, not of anything 12h introduced.

### 12b — outcomes cannot be paraphrased, artifacts cannot lie

✅ **RC-Q9 CLOSED BY STRUCTURE.** The model is no longer asked to transcribe the
operator's outcomes, so it cannot paraphrase them. Code parses
`projects.learning_outcomes` (reversibility proven over an 11-case corpus),
assigns positional ids `LO-1..n`, and the API injects the operator's words
VERBATIM. **`outcomes[]` is gone from the model's schema**; it emits
`outcome_notes` keyed by the real ids, and `serves_outcomes` / `evidence_map` /
`outcome_notes` are closed by a **per-request enum measured ENFORCED** on the
pinned engine. **Three consecutive generations: all three outcomes verbatim
every time, zero invented ids, zero drift.** Compare 12a: two of three, reworded,
every time.

### 12f — the excerpter is forced to design

⛳ **THE 12e DIAGNOSIS WAS WRONG, AND THE SECOND SCRIPT IS WHY.** §12e.6 item 2
named the measurement it had not taken; 12f took it. Two mini-scripts, one
generation each, **unchanged v5/contract-4 stack**:

  * **B1**, containing an EXPLICIT unaided problem (*"Now you try. Work out 63
    minus 48. Pause here."*) → the model **found the span and anchored to it**,
    twice over two runs, and in **34 scenes invented nothing**;
  * **B2**, SPARSE — a procedure with no practice material at all → **designed
    scenes, and this project's first `assess` events**, on the stack that had
    produced 0 in 83.

⛔ **SO IT IS "WILL NOT", NOT "CANNOT".** The model designs readily when nothing
competes and never when something does. Contract-4 put sourced and designed
material in one `scenes[]` array where they contend for the same slots and
sourced won 117 times out of 117. **The fix is to remove the contest, not to
argue with the preference.**

✅ **design-contract-5.** `designed_assessments`, REQUIRED, one key per outcome,
`additionalProperties: false`, each value a FULL scene whose grammar pins
`origin: designed`, `instructional_event: assess`, `serves_outcomes: [that
outcome]`. **An output lacking an invented unaided scene per outcome is not
parseable.** Declared **SECOND** — declaration order binds generation order — so
the assessment is written while `scenes` is still empty and there is no worked
example of its own to copy numbers from. ⛳ **PLACEMENT IS CODE** (12b's
principle, third time): `shared/design/merge.py` inserts each after the LAST
scene serving its outcome and re-indexes; the model is offered no `scene_index`.
A third client seam hands the merged list to the frozen stage body, so a designed
assessment reaches `storyboard_scenes` instead of existing only in the brief.
Migration **0052** (`designed_rationale`), both directions. Prompt **v6**,
additive, **30 gated phrases, none removed**.

✅ **PROBED FIRST (RC-Q12): `const` IS implemented and enforced** on the pinned
engine — scalar and whole-array — measured under a prompt ordering each pin
broken, alongside single-value `enum`, `minItems=maxItems=1`, and the whole
contract-5 construct. **`const` is banked and NOT used**: it is a tie with the
proven construct on the scalars, and on the array RC-Q12's whitespace corridor
applies identically to both, so it buys nothing.

⛳ **THE HOLE IS CLOSED. 0 designed / 0 assess in 83 → 10 designed / 10 assess in
43** (and 12/12 in 32 on a second three-generation run). Every outcome served AND
assessed in six generations of six; `OUTCOME_UNASSESSED` did not fire once.
Assessments pose **fresh numbers** — 43×25, 43×27 against a script that works
23×14 and 32×21 — cold, with no method reminder. **The order's degeneracy STOP
condition did NOT fire.**

⛔ **ACCEPTANCE NOT MET — 1, 1, 1, and 1, 1, 1 again.** Six generations, **six
identical refusals**: `PLAN_ENTRY_UNREALIZED` on LO-2, with a byte-identical plan
every time (`{LO-1: assess, LO-2: practice, LO-3: assess}`). Contract-5 forces the
`assess` and **does not force the `practice`**, and the unforced kind is the one
the model does not follow through on. ⛳ **That is RC-Q9d verbatim, one layer
along** — four packages now show the same law: **the model's plan predicts
nothing; only the grammar is causal.** Rowed as **RC-Q9f**, ⛔ **NOT TUNED** —
loosening the check is forbidden by the 12e standing rule, adding prompt emphasis
after seeing the number is iterating against the metric, and forcing a `practice`
scene too is a contract-6 and the operator's to order.

⚠ **AND 12f's OWN ARTEFACT: the model learned to invent and overshot.** In four of
six generations it wrote an EXTRA designed `assess` into `scenes[]` itself, and
the merge places the mandated one beside its near-identical twin — **the same
assessment posed twice, back to back**. No check catches it; both scenes are
legally declared. Rowed with RC-Q9f.

⚠ **AND I DESTROYED THE FIRST RUN'S EMISSIONS** — a re-scoring script imported the
harness and its module-level write truncated eight banked files to `[]`. Harness
guarded, all four measurements re-run and re-banked (the contract-4 ones from a
git worktree at `d2fc50c`), **both sets reported**, run A's contracts declared
lost by name. §12f.11.

### 12e — the model learns what an assessment is, and it was never the problem

✅ **RULING RECORDED AS A STANDING RULE: EVIDENCE KINDS ARE NEVER COLLAPSED TO
GREEN A NUMBER.** `PLAN_ENTRY_UNREALIZED` keeps the exact kind match — `practice`
is the supported attempt, `assess` the unaided one, and a lesson stopping at the
supported attempt has not demonstrated the outcome's stated **Degree**. The
refusal to loosen it, with 12d's generation 3 one check from zero, **is the
precedent.**

**Prompt v5, additive only — 34 lines added, ZERO deleted**, five gate phrases
added and none audited out: operational definitions of both kinds, every clause
traced to Foundation §2/§3/§4 rather than to a run. ⚠ **A rebuild WAS needed and
the order's reasoning did not cover why** — the publisher reads the seed from
inside the image (measured: 10,615 bytes in the container vs 12,355 tracked), so
publishing without one would have re-published v4 and reported success. API only.

⛔ **ACCEPTANCE NOT MET — 6, 5, 6 — AND THE HOLE DID NOT MOVE: `assess` scenes
[0, 0, 0]**, identical to 12d.

> ⛔ **THE PARAGRAPH BELOW IS SUPERSEDED BY 12f AND IS KEPT SO THE CORRECTION IS
> LEGIBLE.** *"The model has never once invented a scene"* is an accurate COUNT
> and a wrong INFERENCE. See the 12f section above.

⛔ **RC-Q9e — THE ROOT CAUSE, AND IT IS NOT THE ONE 12e REPAIRED.** Generation 2's
five `practice` scenes are a fully narrated worked example — *"1 times 2 equals
2 … so our first answer is 32"* — with nothing for the learner to do, and they
are **near byte-identical to 12d's, written before these definitions existed.**
v5 changed the label's definition and not one word of the scene. The census that
should have been run five packages ago:

> **83 scenes, six generations, two prompt versions: 83 `sourced`, ZERO
> `designed`, ZERO `assess`.**

**The model has never once invented a scene.** Every scene is anchored to a span
of the uploaded script; the script's second problem is fully worked, so an
unaided attempt exists nowhere in it and there is no span to anchor one to.
⛳ **It is not failing to understand `assess` — it is not designing at all**: it
segments the script and attaches labels, which is the exact defect the Design
Core was built to remove, surviving inside the contract meant to remove it. The
prompt has invited invention since v8 (*"you invent it, mark it
`origin: designed`"*) and **that invitation has been declined 83 times out of
83.** RC-Q9c, RC-Q9d and RC-Q9e are one defect seen three times. **Rowed;
STOPPED for the architectural ruling, which is the operator's to order.**

### 12d — backward design becomes the emission order

✅ **RC-Q9c CLOSED STRUCTURALLY (12d, on the operator's ruling), AND THE CLOSURE
IS A DELETION.** ⛳ **MEASURED FIRST, and it is the fact everything rests on:
schema DECLARATION ORDER BINDS GENERATION ORDER** on the pinned engine — probed
in BOTH directions against a prompt explicitly ordering the model to emit
`scenes` first, so it is the grammar and not a model preference. **`properties`
order controls; `required` order does not**, which retroactively explains 12c's
`outcome_notes` being first in `required` and emitted last.

So contract-4 declares **`assessment_plan` FIRST** — per-outcome
`{evidence_kind, learner_does}` — and the model commits to what would PROVE each
outcome while the scene list is still empty. And **`evidence_map` is GONE from
the model's schema**: code derives it from `serves_outcomes` +
`instructional_event` in one shared function both trees import. A derived map
cannot disagree with the scenes, so **THREE REFUSALS WERE DELETED**
(`EVIDENCE_MAP_DISAGREES`, `_PHANTOM_SCENE`, `_NAMES_NOTHING` — the last was
`OUTCOME_UNASSESSED` under a second name) and **one added**:
`PLAN_ENTRY_UNREALIZED`. ⛳ **Removing three refusals and adding one is not
loosening the gate** — it removes the ones measuring the model's bookkeeping
instead of its design. Migration **0051**, both directions exercised.

⛔ **RC-Q9d — THE PLAN IS PRIOR, HONEST, STABLE, AND NON-CAUSAL.** 6, 6, 2 hard
refusals. **What worked:** the plan is emitted first in all three generations,
carries one correct entry per outcome every time, and is **byte-identical across
all three** — asked before it has a lesson, the model answers well and stably.
⛔ **Then the scenes ignore it, and one number carries it: across three
generations and 36 scenes the model wrote `assess` ZERO times**, while planning
an `assess` for LO-1 and LO-3 in every one.

  * **R3** — gens 1 and 2 contain **no application scene at all** (hook /
    present / guide / transfer). A correct assessment plan, then a lecture.
  * **R4** — gen 3 *did* build five `practice` scenes, so every outcome is
    served and assessed; its only refusals are the two outcomes that were
    promised `assess` and got `practice`. **The fading sequence stops one step
    short: supported attempt, never the unaided one.**
  * ⚠ **THE FACT THE RULING NEEDS, against my own result:** if
    `PLAN_ENTRY_UNREALIZED` matched *any* assessing event rather than the exact
    kind, **gen 3 would have scored ZERO refusals** and the run would read
    6, 6, 0. **I did not make that change** — loosening the last check between
    me and a green number is the definition of tuning to the metric. The
    operator's ruling, with the number on the record.
  * ⚠ **And an observation against my own prompt:** application-bearing
    generations went 2-of-3 under v3 to **1-of-3** under v4, which is the
    opposite of the intended direction. n=3, no control, **not iterated on.**

✅ **RC-Q9b CLOSED STRUCTURALLY, WITH THE BELT PROMOTED (12c, on the operator's
ruling).** `evidence_map` is schema-**required** per LO id and bounded **1..4**, so
"nothing assesses this outcome" is no longer an emittable sentence; and
`EVIDENCE_MAP_DISAGREES` is **promoted FLAG → HARD REFUSAL** — a scene named as
evidence for LO-x must itself declare LO-x in `serves_outcomes` AND an
`instructional_event` in {practice, assess}. **Every outcome served AND assessed
is now structurally-or-loudly true.** Empty evidence arrays went from
every-generation to **none in three**. ⛔ **No `dropped_outcomes` mechanism was
built** — dropping an outcome is an operator act at the gate.

⛔ **RC-Q9c — THE ACCEPTANCE STILL DOES NOT REACH ZERO, AND THE REASON MOVED A
THIRD TIME.** 5, 6, 5 hard refusals — `EVIDENCE_MAP_DISAGREES` ×3 every
generation plus `OUTCOME_UNASSESSED` on LO-2/LO-3. ⛳ **The count rose because the
flag became a refusal, not because anything regressed:** 12b already recorded
that flag firing "on nearly every outcome of every generation", and the
underlying `OUTCOME_UNASSESSED` count barely moved (3,2,2 → 2,3,2). **The
structure did not fix the pedagogy; it made the false claim about the pedagogy
impossible to ignore.** Two residues, RC-P14-class, **rowed with the evidence and
NOT tuned against** — the emission order was checked first (`scenes` before
`evidence_map`, so this is not the model naming scenes it has not designed):

  * **R1** — in gens 1 and 3 the designer wrote real `practice` scenes for LO-1
    and then named `present` scenes as the evidence. The right answer was in its
    own output and it pointed elsewhere.
  * **R2** — LO-2 and LO-3 are assessed by no scene in any generation; every
    practice scene serves LO-1 only.
  * ⛳ **The degeneracy the ruling asked me to watch for arrived in generation
    2:** no `practice` or `assess` scene at all, an `evidence_map` naming scenes
    anyway, and `design_notes` reading *"providing opportunities for practice and
    assessment."* Three statements by one author, two false, all three now
    refused by name.

⛔ **RC-Q12 — A LIVE HAZARD IN WHAT 12a SHIPPED.** `minItems` with no maximum
gives constrained decoding an infinite legal continuation and the model takes it
(`["LO-1","LO-3","LO-3",…]` to the token limit). The v8 contract had exactly that
on three arrays. **`maxItems` is enforced and now everywhere; `uniqueItems` is
refused HTTP 400** — ⛳ note the contrast with RC-Q1: an unimplemented GRAMMAR
key is refused loudly, an unknown BODY member is discarded silently.

⛔ **AND 12c FOUND A SECOND SHAPE `maxItems` DOES NOT CLOSE.** With
`minItems: 1, maxItems: 4` and the prompt ordering an empty array, the decoder
forbids the `]` and the model takes the only other legal continuation —
**WHITESPACE, 5,243 chars, `finish_reason=length`**. `maxItems` bounds the
elements, nothing bounds the whitespace before the first one. The bound ships
because two further probes measured the corridor unreachable under honest
pressure (told the lesson assesses nothing, the model fills the map rather than
hang), and **WP-37's `finish_reason` check raises before the parse when it is
reached.** `contains` is a third unimplemented key: **HTTP 400**, like
`uniqueItems`. **Per-request REQUIRED object keys and `additionalProperties:
false` are both ENFORCED**, measured under a prompt ordering them broken.

✅ **RC-Q8 CLOSED.** Artifact identity = name + image digest, in a **sidecar**
rather than the name — argued from every consumer, because `artifact_path_for`
resolves from a REF alone and that IS the deploy contract. Skip-if-present is
digest-conditional; a different digest under one tag **REFUSES naming both**
(proven twice live, once on my own rebuild). **Which digest won:** `e9c1001a` for
`v5.37.0-design-core` — the only build with the RC-Q7 fix, the bytes all four
nodes ran, and the bytes in the bank, **proven by a `docker load` round-trip that
restored it after a same-tag rebuild had pruned it.**

⛔ **RC-Q11 — WP-68's DEFECT, REPEATING.** Migration 0047 added two `prompt_type`
members to PostgreSQL; `prompt.py` typed its tuple by hand and did not gain them.
Rows published, then `LookupError` on the next SELECT — **which that column's own
comment has warned about since WP-64.** Fixed the way `MediaType` was: one list.
**A warning is not a mechanism.**

### Four defects 12b found in 12a's own work, all fixed

The enum never armed (the worker read a route that 401s a service token, and the
failure was silent by design); `PromptType` missing from the ORM; a merged
declaration leaving a stale `source_refs` that the XOR refused; and ⛔ **the same
XOR refusing a legal row**, because SQLAlchemy's JSONB writes a Python `None` as
JSON `null` and `IS NULL` never matches it. Migration **0050** makes the
constraint treat SQL NULL, jsonb `null` and `[]` alike, and the ORM writes SQL
NULL. ⛳ **That constraint has now been wrong in both directions and caught two
real defects — a good trade.**

---

---

## Last pushed

**`eafbf9f`** — `docs(wp-ivgs-12g): the acceptance, and RC-Q9g — the practice is the assessment`, pushed by the operator between 12g and 12h.
Measured at the start of THIS session from the remote-tracking ref after a
`git fetch`: `origin/main` and local `HEAD` were **equal**, so the held count was
**0** — the operator had pushed all three 12g commits. ⛳ **The §0 rule has now
worked four sessions running**, and each time the previous board's text would have
implied a number that was wrong.

**Held now: THREE commits — WP-IVGS-12h's two-call design (`d8da66c`, tagged
`v5.38.2-two-call-design`), the motion-catalogue fix the acceptance found
(`a41d642`, tagged `v5.38.3-two-call-design`), and this report/board commit.
The push block expects 3.**

⚠ **Three, and the middle one is not bookkeeping:** run A refused
`MOTION_WITHOUT_TEMPLATE` three times out of three because call 2 was ordered to
name a motion template and had never been shown the list. That could not have been
in the first commit — it was found by the acceptance the first commit's images
were built for — and the acceptance can only be written after both.

⚠ **I DRAFTED THIS SECTION SAYING TWO AND THEN COULD NOT MAKE IT TRUE.** The plan
was to fold the report into the fix commit. `a41d642` is tagged
`v5.38.3-two-call-design` and the RUNNING image's `IVGS_BUILD_SHA` is
`a41d642…` — amending it to keep a tidy count would leave the deployed fleet
naming a commit that does not exist, which is the exact trap this board has warned
about since 12e. **The number below is the measured one, not the planned one.**

⚠ **`ivgs-infra/.env` is dirty on ALL FOUR NODES and is not mine to commit** —
the deploy moved `IVGS_API_TAG` and `IVGS_WORKERS_TAG` to
`v5.38.3-two-call-design`. Gitignored, and §3 names it never-touch for its token.
**The rollback is `v5.37.7-evidence-structural` on all four nodes.**

⚠ **AND MIGRATION 0053 IS APPLIED TO PRODUCTION AND IS AHEAD OF `origin/main`
UNTIL THE PUSH.** Correct order — schema before code, and the code is deployed —
but a rollback of the images alone leaves an enum member the old code does not
know. It is additive and nothing reads it, so the old code is unaffected; a full
rollback runs `alembic downgrade 0052`.

⛔ **AND TWO IMAGE TAGS MUST NOT BE DEPLOYED FROM: `v5.38.0` (built with
`IVGS_BUILD_REF` unset, reported its version as `"unknown"`) and `v5.38.1`
(correct bytes, wrong ref — it reported itself as `v5.38.0`).** Both are my slips
and both are banked. Neither was a rebuilt tag: the bytes differ, so the tags
differ, which is the RC-Q8 discipline. Only `v5.38.2` and `v5.38.3` are pushed.

---

### Superseded — kept for the lineage

**`a998085`** — `docs(wp-ivgs-12d): the deploy, the acceptance, and RC-Q9d`, pushed by the operator between 12d and 12e.
Measured at the start of this package from the remote-tracking ref:
`origin/main` and local `HEAD` were **equal**, so the held count was **0**, not
the 1 the previous board claimed and not the 3 the WP-IVGS-11 report declared —
the operator pushed `70058b9`, `a6bb30c` and `af0c6a1` after that report closed.

**Held now: TWO commits — WP-IVGS-12e's prompt/gates/tests (`1f464bb`, tagged
`v5.37.4-assess-defined`) and this report/board commit. Nothing else.**
⚠ **Two, not one, and for a reason worth keeping:** the code is committed and
tagged BEFORE the images are built, so the deployed image's `IVGS_BUILD_SHA`
names a real commit that exists; the acceptance result can only be written after.
Amending a tagged commit to keep a tidy count would break that. **The push block
expects 2**, measured with `git rev-list --count`.

✅ **AND THE §0 RULE 12c ADDED WAS USED FOR THE FIRST TIME AND WORKED.** At
12d's start `git rev-list --count origin/main..HEAD` measured **0** — the
operator had pushed both 12c commits — where the previous board's text would
have implied 2. Measured, not inherited.

⚠ **AND THE LINE ABOVE THIS ONE WAS STALE WHEN 12c OPENED.** The board said
"Held now: ONE commit — `2b867b0`, WP-IVGS-12b"; `git fetch` then
`git log origin/main..HEAD` measured **0**, because the operator pushed 12b
(as `68698db`) after that board was written. **Measured from the remote-tracking
ref at close, never carried forward from the commit you made, and never trusted
from the previous board** — the same discipline this section has now had to
relearn four times, and the fourth time it was the board's own claim that was
wrong rather than a report's. ✅ **It is now a rule** — `dev/CLAUDE.md` §0
CLOSE OUT item 5: the held count is written from
`git rev-list --count origin/main..HEAD` after a `git fetch`, never carried
forward.

⚠ **AN IMAGE TAG IS NOT A GIT TAG, and this package adds a second edge to that
rule: A TAG IS NOT AN IMAGE EITHER (RC-Q8).** `v5.37.0-design-core` names the
deployed images; the git tag of the same name is created below as the coherent
set.

⛳ **12c and 12d both prove the git tag and the image tag name the same bytes
rather than assuming it:** the running API reports `IVGS_BUILD_SHA=5e179ee…`,
which is the commit `v5.37.3-plan-before-scenes` points at. **That is a check,
not a convention** — it stays true only for as long as someone measures it, and
12d nearly lost it: the first API build was stamped `PENDING-12d` because the
image was built before the commit existed. Rebuilt from the real SHA rather than
shipped with a placeholder.

---

## Reports filed this session

| report | verdict |
|---|---|
| ↳ same file, **§12h** | ⛳ **RC-Q9g CLOSED — the calls separate the kinds and the second never sees what it must not copy.** **design-contract-7** splits the design across TWO engine calls inside one stage: call 1 emits everything except `assessment_scenes` (probed: it CANNOT put the key back), call 2 authors the assessments from the outcomes, the plan and a code-built practice summary — no narrations, no scenes, no script. **18 of 18 outcome-pairs distinct over six generations**, against 11 of 15 duplicates under contract-6. ⛳ **The order's STOP condition did not fire**: both "no axis" outcomes now invent a fresh CASE, 6 of 6, and B2's collapsed LO-3 goes 1.000 → 0.556. New HARD refusal **`EVIDENCE_NEAR_DUPLICATE`**, calibrated on 18 banked pairs (classes separate 0.667 \| 0.900) and **proven RED on 12g's duplicates as part of the acceptance**; ⛳ its worked-example limb caught a defect 12g's hand-comparison missed. Prompt **v8** (four phrases MOVED, proven arrived) + NEW lineage **`assessment_authoring_system` v1**, migration **0053**; deployed to nodes 01-04 at `v5.38.3`, verified by image ID. ⛳ **ACCEPTANCE MET run B: 0 refusals 3/3**, census 127/109/18/9/12, 0 evidence events in call 1's `scenes[]` 3/3. ⛔ Run A refused 1/1/1 on `MOTION_WITHOUT_TEMPLATE` — call 2 was ordered to name a template and never shown the list; fixed with a catalogue read from the renderer's registry, and B2 then showed call 1 (told in prose) inventing a template name while call 2 (given the registry) did not. ⚠ **RC-Q9h** rowed — two identical practice scenes, 4 of 6; ⛔ **RC-Q13** rowed — the declared 240 s client budget against 280–564 s of measured work |
| `reports/WP-IVGS-12-DESIGN-CORE-report_2026-08-29.md` | the Design Core built and deployed; `guided_json` measured a silent no-op; the uploaded script found destroyed in place; **acceptance NOT met — RC-Q9** |
| ↳ same file, **§12b** | RC-Q9 closed by structure (outcomes parsed by code, per-request enum measured enforced); RC-Q8 closed by digest; **acceptance still NOT met — RC-Q9b** |
| ↳ same file, **§12g** | ⛳ **RC-Q9f CLOSED IN BOTH LIMBS by grammar** — **design-contract-6** forces BOTH evidence kinds in per-outcome sections (`assessment_scenes` exactly 1, `practice_scenes` 1..2) and narrows `scenes[]` to SEVEN events; **origin FREE in both** (12f's one reversal, on 12f's own B1 measurement); placement in Foundation §2's fading order; **no migration needed and that is a finding**; prompt v7 with one audited drop; probes measured NO HANG on either bounded shape; deployed to nodes 01-04 at `v5.37.7`, v7 published. ⛳ **0 refusals 3/3 where contract-5 refused 6/6 on a byte-identical plan**; 0 evidence events in `scenes[]` 3/3. ⛔ **acceptance STOPPED — RC-Q9g: the practice IS the assessment, written twice, 11 of 15 pairs verbatim**; the two-call escalation is the operator's. ⛔ Also: contract-6 truncated 1 generation in 3 at the 8,192 floor (raised to 12,288, measured) and **the stage-2 prompt is now 45% of node-02's serving context** |
| ↳ same file, **§12f** | ⛳ **the 12e diagnosis overturned by a second script — the model WILL NOT invent, it CANNOT be out-competed**; **design-contract-5** forces one invented unaided scene per outcome and code places it; `const` probed, enforced, deliberately unused; migration 0052; prompt v6; **both images rebuilt, deployed to nodes 01-04, v6 published**; ⛳ **0 designed/0 assess in 83 → 10 designed/10 assess in 43**; ⛔ **acceptance NOT met — 1, 1, 1 twice over, RC-Q9f**, the plan's unforced kind |
| ↳ same file, **§12e** | ruling recorded (exact kind match stands, a standing rule); prompt v5 additive with operational definitions of `practice`/`assess`; API rebuilt because the publisher reads the seed from the image; **acceptance NOT met — 6, 5, 6, `assess` still [0,0,0]** — and the census found the root cause: **0 `designed` scenes in 83 (RC-Q9e)** |
| ↳ same file, **§12d** | declaration order MEASURED to bind generation order; `assessment_plan` declared first, `evidence_map` removed and derived in code; **three refusals deleted, one added**; migration 0051; prompt v4; deployed to nodes 01-04; **acceptance still NOT met — RC-Q9d**, the plan is prior and stable but non-causal |
| ↳ same file, **§12c** | RC-Q9b closed by structure (`evidence_map` required 1..4 per id) with `EVIDENCE_MAP_DISAGREES` promoted to a hard refusal; required-keys and `additionalProperties` measured ENFORCED, `contains` HTTP 400, a new `minItems` whitespace hang found; **acceptance still NOT met — RC-Q9c**; ✅ **deployed to nodes 01-04 and prompt v3 published** (§12c.9) |

---

## Next, in order

1. ⛳ **THE OPERATOR'S BROWSER WATCH — PHASE 1'S HUMAN ACCEPTANCE. IT IS NEXT.**
   ⛳ **RC-Q9g IS CLOSED and the gate is clean: 0 hard refusals 3/3, and 18 of 18
   outcome-pairs distinct by the belt's own measure**, where contract-6 shipped a
   design in which most outcomes got the same scene twice. Every previous
   package's answer to "is it the operator's watch yet" was *"not yet, and for a
   new reason"*. **There is no such reason left.** ⚠ What the watch is FOR is
   exactly what no measurement in this lineage has touched: the rendered panel is
   still described from the payload and the component source, **never from a
   browser**, and the arc now carries a practice AND an assessment on every
   outcome plus a refusal that quotes two narrations back at the reviewer.
   **12i (audience fields) and 12j (hierarchical long-form) are queued behind it**
2. ⛔ **RC-Q13 — THE DECLARED STAGE-2 TIMEOUT CANNOT HOLD THE MEASURED WORK, AND
   THE FLEET IS RUNNING ON IT.** AD-05 declares soft 270 / hard 300, so the
   client budget is 240 s; measured wall clock across 13 generations is
   **135–564 s**, with ten over the client budget and eight over the Celery hard
   limit. Contract-6 has been deployed since yesterday in that state and nobody
   saw it because **no storyboard job has gone through the real Celery task since
   contract-5**. `celery_app.apply_declared_time_limits` makes `policies.py` the
   one definition that reaches the tasks, so the change is a one-line edit to a
   **declared conformance table** — and that is an operator ruling, not a config
   tweak. ⚠ Item 3 below is how it would be discovered rather than argued
3. ⛔ **NOT ONE GENERATION HAS GONE THROUGH THE REAL PIPELINE, AND 12h MAKES THIS
   THE LARGEST GAP BY A DISTANCE.** The second engine call, the `await`ed
   transform seam and the `DocumentTransformFatal` path have never been executed
   by Celery — only unit-tested, round-tripped through the database and read back
   out of the running containers. **RC-Q13 says the first real run would time
   out**, which is precisely why it should be the first real run
4. ⚠ **RC-Q9h — THE DUPLICATE MOVED ONE LAYER IN.** LO-1's two practice scenes are
   the same sentence in 4 of 6 generations: same mechanism, inside `practice_scenes`,
   where the first sits in context while the second is asked for. The belt is
   scoped by the order to the assessment and does not look. Three routes named at
   §12h.12; ⛔ the honest one is a third call, and that needs a view of the cost
5. ⛔ **THE STAGE-2 PROMPT IS 45% OF THE SERVING CONTEXT, AND v8 GREW IT.**
   `prompt_tokens = 14,876` against node-02's 32,768. ⛳ **The two-call split
   HELPS here and it is worth noting**: call 2 pays only ~2,300 tokens, so the
   assessments are authored at 7% of context rather than 45%. But call 1 is
   unchanged and a longer script still eats the 5,619-token headroom
6. ⛔ **THE RULING ON RC-Q9g — CLOSED BY 12h. Kept for the record.** ✅ **RC-Q9f IS CLOSED,
   both limbs**: contract-6 forces both evidence kinds and `scenes[]` can declare
   neither, and the acceptance went **6 refusals in 6 generations → 0 in 3, on a
   byte-identical plan**. ⛔ **What replaced it is that the practice and the
   assessment are the SAME SCENE, written twice** — 11 of 15 outcome-pairs
   verbatim identical, every generation affected, quoted in full at §12g.9. The
   cause is 12g's own emission order (the assessment is written first and sits in
   context while the practice is asked for). **A second call for the practice
   layer, with the assessment supplied and the instruction to fade FROM it, is
   the real answer and is the operator's to order.** ⚠ Swapping the declaration
   order would trade 12d's measured backward-design property for a duplicate that
   would probably just reverse direction; prompt emphasis is refused because
   **v7 already says it** and said it before the run
7. ⛔ **THE STAGE-2 PROMPT FIGURE, AS 12g STATED IT. Kept for the record.**
   `prompt_tokens = 14,861` against node-02's 32,768 — where the code has claimed
   *"input ~2,000"* since WP-37. Contract-6 truncated a generation at the 8,192
   output floor; the floor is now 12,288 and headroom is 5,619. **A longer script
   than the operator's 3,008-byte one eats it from the other end.** A test fails
   when it goes, which converts a production truncation into a test failure —
   it does not stop the squeeze. Cutting v7, raising `--max-model-len`, or
   accepting a script-length limit is an operator decision
8. ⛔ **12f's STATEMENT OF THE PIPELINE GAP. Superseded by item 3.** Every 12f number
   is the harness calling node-02 with the production modules. The document
   transform that carries a designed assessment into `storyboard_scenes` is
   proven by test and by reading the running containers, **never by a job.**
   This is the largest gap in the package and the cheapest thing to close
9. ⛔ **12g's "NOT YET" ON THE WATCH — SUPERSEDED BY ITEM 1.** 12g clears
   the refusals (0, 0, 0) but ships a design in which most outcomes get the same
   scene twice under two labels (RC-Q9g). ⚠ The rendered panel remains described
   from the payload and component source, **not a browser** — and the arc it now
   shows has a practice AND an assessment on every outcome, neither of which has
   ever been rendered
10. **RC-Q10** — a re-run leaves surplus scene rows and the design brief makes it
   loud. Contaminates any regenerate-on-the-same-project gate reading
11. **RC-Q3 / WP-00 #20** — a 64-character chat refusal recorded as a refined
   transcript; the "is this a transcript at all" check does not exist
12. **Recovery-plan Phase 3** (RC-C + RC-E's UX half), then Phase 4, 5, 6
13. **RUN-2 / M3.3** — unchanged, and still gated on a correct run

---

## Open operator decisions

- ⛳ **RC-Q9g — CLOSED BY WP-IVGS-12h. No ruling is needed and none was taken.**
  The order ruled the two-call escalation and it worked: **18 of 18 outcome-pairs
  distinct across six generations**, against 11 duplicates in 15. ⛳ **The
  escalation the order held in reserve — a per-outcome-type design question for
  the two "no axis" outcomes — was NOT needed**: both invent a fresh CASE in 6 of
  6 generations, and B2's collapsed LO-3 goes from containment 1.000 to 0.556.
  Quotes at §12h.10. **The remaining decisions are RC-Q13 and RC-Q9h below.**

- ⛔ **RC-Q13, NEW — THE DECLARED STAGE-2 TIMEOUT IS SHORTER THAN THE WORK, AND
  IT IS DEPLOYED.** AD-05 declares `generate_storyboard` at soft **270** / hard
  **300**; `config._storyboard_client_timeout()` derives **240 s** from it and
  12h splits that 180/60 across the two calls. **Measured wall clock, 13
  generations across 12g's banked logs and 12h's own: 135, 281, 366, 395, 427,
  457, 476, 477, 488, 491, 503, 526, 564 seconds.** Ten exceed the client budget;
  eight exceed the Celery hard limit. ⛳ **The split is NOT the cause** — call 2
  costs 36–41 s of a call 1 that already runs 280–526 s, 7–13% on a budget
  already exceeded by 100%. ⛔ **It has never surfaced because no storyboard job
  has run through the real Celery task since contract-5** (§12g.13 item 2, and
  12h's item 2). The numbers are AD-05's conformance table and
  `celery_app.apply_declared_time_limits` makes them the one definition that
  reaches the tasks, so raising them is a change to a **declared conformance
  target for the Temporal migration** — the operator's, not an agent's. §12h.6

- ⚠ **RC-Q9h, NEW — THE DUPLICATE MOVED ONE LAYER IN.** LO-1's **two practice
  scenes are the same sentence** in 4 of 6 generations: *"Now it's your turn to
  try. Multiply 34 by 21 using the standard column algorithm."*, twice. It is
  RC-Q9g's exact mechanism inside a single section — `practice_scenes` is bounded
  1..2 and both are written in one emission with the first in context while the
  second is asked for. ⛔ **The belt does not see it and that is deliberate**: the
  order scopes it to the assessment, and widening a hard refusal on my own
  judgment is not mine. ⚠ **And a second observation that may matter more**: those
  practices pose the problem COLD, which v8 tells call 1 is writing the
  assessment. The pair passes the belt because the ASSESSMENT is now genuinely
  different, not because the practice is a good faded step. Three routes at
  §12h.12; the honest one is a third call, and it needs a view of the cost given
  RC-Q13

- ⓘ **RC-Q9g AS 12g STATED IT — kept for the lineage.** Contract-6
  closed RC-Q9f in both limbs and the structural acceptance is met: **0 hard
  refusals 3/3**, both evidence kinds present per outcome, 0 evidence events
  inside the model's own `scenes[]`, every outcome served and assessed — against
  contract-5's **6 refusals in 6 generations on the identical plan**. ⛔ **And in
  11 of 15 outcome-pairs the practice narration and the assessment narration are
  the same string.** No check catches it and none can at hard-refusal strength:
  both scenes are legally declared, the kinds differ, and string similarity is a
  judgment. ⛳ **B2 isolates the cause** — where a fresh number gives the model an
  axis it differentiates properly, and even fades the scaffolding correctly
  (*"Divide 234 by 10. Use the place-value shift method."* → *"Divide 432 by
  10."*); where the outcome is *"explain why"* or *"check your work"* it has no
  axis and writes the sentence twice. The operator's script has two such outcomes
  of three. **The two-call escalation is the operator's to order.** Quotes at
  §12g.9

- ⛔ **RC-Q9f — CLOSED BY 12g. Kept for the record.** Contract-5
  forces an invented unaided `assess` per outcome and it works: **0 designed / 0
  assess in 83 → 10 designed / 10 assess in 43**, every outcome served AND
  assessed, six generations of six, fresh numbers, no degeneracy on the two tests
  the order named. ⛔ **The acceptance still fails 1, 1, 1 (twice)** on
  `PLAN_ENTRY_UNREALIZED` for the ONE outcome the model plans as `practice` — the
  kind the grammar does not force. **Forcing it too is a contract-6 and the
  operator's to order**; loosening the check is forbidden by the standing rule
  below, and adding prompt emphasis after seeing the number is tuning. ⚠ Second
  limb: in four of six generations the model ALSO writes its own copy of the
  assessment into `scenes[]`, so the lesson poses it twice, adjacent, and no
  check catches it
- ✅ **RC-Q9e CLOSED, AND ITS DIAGNOSIS CORRECTED.** *"The model has never once
  invented a scene"* was an accurate count and a wrong inference. Handed a SPARSE
  script on the **unchanged** v5/contract-4 stack the model invented immediately;
  handed a script with an explicit unaided problem it anchored to the span and
  invented nothing. **WILL NOT, not CANNOT** — it is out-competed by anything it
  can excerpt. A schema did compel it. ⛳ **The two-call split was never needed
  and stays in reserve**
- ✅ **RULING, STANDING: evidence kinds are never collapsed to green a number.**
  `PLAN_ENTRY_UNREALIZED` keeps the exact kind match; the refusal to loosen it is
  the precedent
- ⛔ **RC-Q9d — the plan is prior, honest, stable and NON-CAUSAL.** RC-Q9, Q9b
  and Q9c are all CLOSED by structure. The model plans the assessment correctly
  before any scene exists and then does not build it: **`assess` written zero
  times across three generations and 36 scenes.** Two residues (R3 no
  application at all; R4 the fading sequence stopping at `practice`). **Rowed
  with the evidence, not built** — and the exact-kind-match question is a
  yes/no in "Next, in order" #1
- ⛔ **RC-Q9c is CLOSED** — the model is no longer asked to author `evidence_map`
  at all, so R1 (naming non-assessing scenes) is unrepresentable rather than
  refused. R2 survives inside RC-Q9d
- ⛔ **RC-Q12 — the other nine per-stage LLM knobs** and every future schema: an
  unbounded array is a runaway, and `uniqueItems` is unavailable. ✅ **12f adds
  `const` to the measured set: implemented and ENFORCED**, scalar and whole-array,
  under a prompt ordering each pin broken — and **deliberately unused**, because
  it ties with single-value `enum` on scalars and the whitespace corridor applies
  identically to both on arrays. Probes banked at `wpivgs12f-evidence/`
- ⛔ **RC-Q4 — per-scene presenter selection does not exist** and Foundation §4
  assumes it. `talking_head` stays out of `media_type` (ruled); whether to BUILD
  per-scene presenter choice is open. Phase-5 candidate
- ⛔ **RC-Q8 — the artifact/tag staleness trap.** Fix the script, or add the
  cross-node image-ID comparison to §6.1a, or both
- ⛔ **RC-Q3 — the missing "is this a transcript at all" check**
- ⛔ **RC-P2 — the v8 "empty surface only" amendment.** Still not implemented
- ⛔ **RC-P14 — `text_carried_by` transportable but not reliably emitted.** Same
  family as RC-Q9, one layer down
- ⚠ **RC-P3 — a blank clip recorded as a successful render**
- ⛔ **RC-P18 / RC-Q7 — stage activities under their declared policy.** Stage 2's
  CLIENT timeout is fixed and derived; **the other nine stages still share one
  120 s knob** and none has been measured against its own policy
- ⚠ **RC-P16 — a soft-limit kill strands the job row `running`**, blocking both
  `/resume` and WP-59 deletion. Hit again this session
- ⓘ **RC-P19 — `DEPLOY VERIFIED` proves the image, not that the process stays up**
- ⛔ **P1.0a IS REVERSED (RC-L6)** — the hardcoded SadTalker fallback is alive in
  the frozen stage-6 body. An M3.3-R3 edit row
- ⛔ **node-04 headroom (RC-L7, AD-08)**
- ⛔ **.96 admin access method** — needed by M3.3-R2
- **MBCP session booking** — gates RC-G9, RC-D1/D2/D3/D9/D10

---

## Gates

Authority: **`OUTSTANDING_WORK.md`** — the P0–P3 register plus §RECONCILIATION
(`RC-*`), the **M3.3 GATE TABLE** and **§RC-Q** (this package).

| Metric | Count |
|---|---|
| Rows total (P0–P3) | **78** — unchanged. This package's findings are rowed in **§RC-Q** (RC-Q1…RC-Q10), a reconciliation section |
| **P0 open** | **0** |
| ⛔ **NEEDS-RULING** | **0** in the P0–P3 register; **§RC-Q carries 5 open operator items** (Q3, Q4, Q8, Q9, Q10) |
| ✅ **CLOSED THIS PACKAGE** | **P2.66** (the outcomes hand-off — a real end-to-end path, no frozen edit), **RC-I4** (nightly power-down) |
| **VERIFY-AT-RUN-2** | **20** — P2.12 through P2.31, contiguous |
| WP-00 swallowed-failure register | **20 instances** — #20 added this package |

---

## Tests — the corrected baseline

| Tree | passed | failed | skipped | errors | vs baseline |
|---|---|---|---|---|---|
| `ivgs-api` | **1614** | **0** | 0 | 0 | 1553 + **26** (12) + **35** (12b) |
| `ivgs-workers` | **983** | 18 | 52 | 15 | 965 + **18**; failures **identical** across 12 and 12b |
| `ivgs-scheduler` | **52** | 15 | 0 | 0 | ✅ byte-identical |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | ✅ — **only with RC-J8's three env vars** |
| `ivgs-motion-renderer` | **24** | **0** | 2 | 0 | ✅ byte-identical |
| `tests_system` | **193** | 12 | 15 | 30 | ✅ byte-identical |

✅ **ZERO NEW FAILURES**, seven times — WP-IVGS-09, 09b, 09c, 09d, WP-IVGS-10,
WP-IVGS-12 and WP-IVGS-12b. **Two full-suite runs, as the order allows, and no more.**

⚠ **THE TEST DATABASE AND PRODUCTION MUST NOW BE AT `0050`** (was 0045). 0046
adds `transcripts.source_text` + `.source_kind`; 0047 adds two `prompt_type`
members; 0048 adds seven `storyboard_scenes` columns, four CHECKs and
`storyboard_design_briefs`; 0049 widens `contract_version` to 64; 0050 makes the source-refs XOR treat SQL
NULL, jsonb `null` and `[]` alike. **All five are applied to production**, additive, and the `refined_text` content digest across
every existing transcript is **byte-identical before and after**.

⚠ **Five existing test files were RE-AIMED and none was weakened.** All five
pinned the outcomes delimiter, which P2.66 retired; each now asserts the same
risk at the new path — that the system prompt actually interpolates
`{{ learning_outcomes }}`, proved with a sentinel. ⛳ **They caught a real defect
within minutes:** editing RULE 0 swallowed an `{% endif %}`, every phrase gate
still passed, and it would have failed Stage 2 for every project at once. **A
render gate is now part of the publisher.**

⚠ **`ps aux | grep pytest` BEFORE BELIEVING A NEW FAILURE.** A stale monitor
shell from a previous session was still waiting on pytest when this one started.

---

## Temporal / M3.3

Server **1.29.7 live on 192.168.1.96**. `ivgs-workers/temporal_pipeline/` is the
WP-41 shadow, deliberately unwired. **Runway M3.3-R1…R5 unchanged.**

⛳ **M3.3 GAINS THE EASY HALF OF THIS PACKAGE.** Every wrapper here — the capture
seam, the response-format override, the instructional-header table — exists in
the shape it does *because* the eight stage bodies are frozen. When they become
activities, the Design Contract can travel through stage 2 directly, and
**RC-Q6's shortfall (a table keyed by scene number rather than one pre-selected
block) closes with one line in each of three bodies.**
