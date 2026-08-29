# WP-IVGS-10 — the visual description must depict the narration

**Report · started 2026-08-28, completed 2026-08-29 · written as the work proceeded.**

**Operator ruling implemented:** *"the storyboard's visual layer is authored as aesthetic
staging, not content. A scene's `visual_description` routinely omits what its narration
actually says."* The earlier math-planner proposal is WITHDRAWN as over-fit; this package
implements the general rule.

---

## §0 ⛔ CONFLICTS — FLAGGED, NOT CHOSEN

Two, and neither is resolved by this package.

**(1) `dev/CLAUDE.md` §3 freezes the eight stage task bodies; the fix this package's Task 1
found lives inside one of them.** `stage2_storyboard._save_storyboard_scenes:437-443` POSTs
five keys and silently drops `generation_params` — so **RULE 8 has never worked at birth**
(§3). The permanent fix is five lines inside a frozen body. This package **wraps rather than
edits**, per §3's own *"Wrapping is allowed; editing is not"*, by reading the fields out of
the checkpoint the stage already writes. **The edit itself is an M3.3-R3 row and is filed as
RC-P1.** A characterisation test fails the day somebody does make that edit, so the wrapper
is retired rather than left running forever.

**(2) RC-J10 is unchanged and unamended.** `dev/CLAUDE.md` §1 says *"Claude does NOT commit,
push, merge, or deploy."* This order says **"Commit and HOLD"** and Task 5 requires a full
pipeline run, which requires a deploy. I followed the order — commits held, **nothing
pushed** — and the contradiction stays on the board for the operator to settle. It is not
amended on a package's own initiative.

---

## §1 Headline

| Task | Result |
|---|---|
| 1 — measure the incompleteness | ✅ §2 — **reference run 16/18 delegate, 9c29b1d1 8/14**, and every visual the storyboard model itself wrote is a delegation or generic |
| 2 — v7 storyboard contract | ✅ §4 — RULE 1-EXTENDED, RULE 5 amended, RULE 9 added, RULE 8 gains `phase`; every WP-63/64/65/68 gate phrase survives |
| 3 — completeness validator at the gate | ✅ §5 — hard refusal on the objective case only, soft flags in the gate UI, no prompt loops |
| 4 — RC-O10, the template distinguishes its phases | ✅ §6 — `full` **byte-identical**, `start`/`complete` distinct and continuous |
| 5 — prove end to end, then hand the watch over | see §8 |
| Zero new failures | see §7 |

---

## §2 TASK 1 — the incompleteness, measured

**Read-only, from the live database on 2026-08-28.** Classified by
`ivgs-api/app/services/storyboard_completeness.py` — **the same module the gate now runs**, so
this table and the validator cannot drift apart.

### The verdicts, defined

| verdict | test | what the gate does |
|---|---|---|
| **DEPICTS** | a diffusion scene naming part of the working surface, or a motion scene whose template passes the WP-IVGS-09f narration guard | nothing |
| **GENERIC** | the narration bears content and the description names *no* part of the working surface — no row, column, ruled line, answer row, placeholder or carry — or it is another scene's description word for word | **soft flag** |
| **DELEGATES-TO-WRONG-MEDIUM** | the narration's content is written or numeric and the scene is a diffusion medium declaring nothing about where that content lives; or the description itself asks for digits or writing; or a motion scene has no template | **hard refusal, by name** |

#### c12fa967 — `reference-run-2026-08-23`, 18 scenes

| # | medium | narration's content-critical referents | what the visual actually depicts | verdict |
|---|---|---|---|---|
| 0 | `image` | num 23,14; change: multiply, times | **nothing of the working surface** | ⛔ DELEGATES |
| 1 | `motion_graphics` | num 23,14; written: write, draw a line | template `highlight_and_hold` {"top": 23, "label": 0, "bottom": 14, "column": 0} | ✅ DEPICTS |
| 2 | `video_clip` | num 4,3,12,2,1; written: write; change: multiplying, multiply, times | **nothing of the working surface** | ⛔ DELEGATES |
| 3 | `animation` | num 4,2,8,1,9,92; change: multiply, times, equals | **nothing of the working surface** | ⛔ DELEGATES |
| 4 | `animation` | num 10; written: put a; change: multiply, multiplying | **nothing of the working surface** | ⛔ DELEGATES |
| 5 | `animation` | num 10,3,30,2,20,320; written: wrote; change: multiply, times, equals | **nothing of the working surface** | ⛔ DELEGATES |
| 6 | `animation` | num 92,320,23,4,10,230; change: add, adding, multiplying | **nothing of the working surface** | ⛔ DELEGATES |
| 7 | `animation` | num 23,10,230,4,92,322; change: multiply, equals, add | **nothing of the working surface** | ⛔ DELEGATES |
| 8 | `video_clip` | num 32,21; written: write; change: times | **nothing of the working surface** | ⛔ DELEGATES |
| 9 | `animation` | num 1,2,3,32; change: multiply, times, equals | **nothing of the working surface** | ⛔ DELEGATES |
| 10 | `animation` | num 20,2,40,3,60; change: move, multiply, times | **nothing of the working surface** | ⛔ DELEGATES |
| 11 | `animation` | num 200,60,260,640; written: wrote; change: equals | **nothing of the working surface** | ⛔ DELEGATES |
| 12 | `animation` | num 20,2,40,3,60,260; change: times, equals, multiplying | **nothing of the working surface** | ⛔ DELEGATES |
| 13 | `animation` | num 32,260,1,20,640; change: add, adding, multiplying | **nothing of the working surface** | ⛔ DELEGATES |
| 14 | `animation` | num 32,1,20,640,672; change: multiply, equals, add | **nothing of the working surface** | ⛔ DELEGATES |
| 15 | `image` | change: multiply, add | **nothing of the working surface** | ⛔ DELEGATES |
| 16 | `image` | change: line up, multiplying, becomes | **nothing of the working surface** | ⛔ DELEGATES |
| 17 | `image` | change: multiply | **nothing of the working surface** | ⚠ GENERIC |

**1 DEPICTS · 1 GENERIC · 16 DELEGATES-TO-WRONG-MEDIUM**

#### 9c29b1d1 — *two by two multiplication*, 14 scenes

| # | medium | narration's content-critical referents | what the visual actually depicts | verdict |
|---|---|---|---|---|
| 0 | `video_clip` | num 23,14; change: multiply, times | **nothing of the working surface** | ⛔ DELEGATES |
| 1 | `image` | written: write, draw a line; change: line up | **nothing of the working surface** | ⛔ DELEGATES |
| 2 | `motion_graphics` | num 4,14,3,12,2,1; written: write; change: multiplying, multiply, times | template `column_multiplication_step` {"top": 23, "step": 0, "bottom": 14} | ⛔ DELEGATES |
| 3 | `motion_graphics` | num 4,2,8,1,9,92; change: multiply, times, equals | template `column_multiplication_step` {"top": 23, "step": 0, "bottom": 14} | ✅ DEPICTS |
| 4 | `motion_graphics` | num 1,14,10; written: put a; change: multiply | template `column_multiplication_step` {"top": 23, "step": 1, "bottom": 14} | ✅ DEPICTS |
| 5 | `motion_graphics` | num 1,3,2,230; change: multiply, times, equals | template `column_multiplication_step` {"top": 23, "step": 1, "bottom": 14} | ✅ DEPICTS |
| 6 | `image` | num 92,230,2,0,9,3; written: write; change: add, equals, carry | row, column, partial-product, rows, already written | ⛔ DELEGATES |
| 7 | `motion_graphics` | num 1,2,3,322,23,14; change: equals, times | template `column_addition_carry` {"top": 230, "bottom": 92} | ✅ DEPICTS |
| 8 | `image` | num 32,21,1; written: write; change: times | **nothing of the working surface** | ⛔ DELEGATES |
| 9 | `image` | num 1,2,3,32; change: multiply, times, equals | row, column, multiplication sign, ruled horizontal, answer row | ⛔ DELEGATES |
| 10 | `motion_graphics` | num 2,4,3,6,640; change: move, multiply, times | template `column_multiplication_step` {"top": 32, "step": 1, "bottom": 21} | ✅ DEPICTS |
| 11 | `video_clip` | num 32,640,672,21; change: add, equals, times | row, column, partial-product, rows, already written | ⛔ DELEGATES |
| 12 | `image` | change: multiply, add, multiplying | **nothing of the working surface** | ⛔ DELEGATES |
| 13 | `image` | change: multiply | **nothing of the working surface** | ⛔ DELEGATES |

**5 DEPICTS · 0 GENERIC · 9 DELEGATES-TO-WRONG-MEDIUM**

### What the table says

⛔ **Every visual the storyboard model itself authored is a delegation or a generic.** In
`9c29b1d1` the six DEPICTS are *all six motion scenes*, and every one of their templates was
authored by WP-IVGS-09c/09f's release path from the narration — **not by the storyboard
model**. Strip those out and the model's own score on that project is **0 of 8**.

⚠ **The reference run's one DEPICTS is not from the run.** Scene 1's row was flipped to
`motion_graphics` at **2026-08-28 22:56:59Z**, an hour before this package started. As the run
produced it, scene 1 was `motion_graphics`-less prose — *"A close-up of a hand writing the
multiplication problem 23 x 14 on a piece of paper … with a focus on the handwriting and the
numbers"* — which is a DELEGATES. **The run as banked is 17 of 18.** Nothing in that project
was touched by this package; the observation is recorded because the table would otherwise
overstate the baseline by one.

⛔ **The operator's quoted case reproduces exactly.** `9c29b1d1` scene 1:

| | |
|---|---|
| narration | *"First, we set up the problem. **Write the numbers** on top and underneath, making sure the ones digits **line up** and the tens digits line up. **Draw a line** underneath."* |
| visual | *"A hand holding a pencil, poised over a blank sheet of lined paper with a ruler and a soft pink pencil case nearby, warm and gentle lighting"* |
| depicted | **nothing of the working surface** |

### Three defects the measurement exposed that no package had recorded

**(a) ⛔ RULE 8 has never worked at birth — `generation_params` is dropped in transit.**
`stage2_storyboard._save_storyboard_scenes` builds a five-key payload. `SceneCreate` has
accepted `generation_params` since migration 0028 and v6 has asked for it since 2026-08-26;
the worker never sends it. Every motion spec that has ever reached a renderer on this fleet
was authored *later*, from the narration alone. §3 is the wrapper; §0 is the conflict.

**(b) ⛔ The output contract contradicted RULE 2.** v6's field list read *`"media_type": One
of "image", "video_clip", or "animation"`* — three rules above RULE 2 and RULE 8, which offer
`motion_graphics`. The model reads its own output contract first. Corrected in v7 and gated.

**(c) ⚠ RULE 1 has only ever been checked for digits.** Three measured descriptions demand
legible writing while containing no numeral: *"a few key steps **written** in the margins"*
(9c29b1d1 s12), *"her paper with a few **calculations** on it"* (s13), and an infographic
*"with a focus on the steps and the **calculations**"* (reference run s15). v7's classifier
checks both halves.

**(d) ⚠ And a fourth, small and live.** The reference run's scene 1 carries
`{"template": "highlight_and_hold", …, "label": 0}` — a caption written as the **integer
zero**, because `motion_authoring.build_prompt` rendered *every* parameter to the model as
`"<name>": <int>`, `label` included. Fixed in §6 by deriving each parameter's shape from the
template's own signature.

---

## §3 The transit loss, and the wrapper that does not touch a frozen body

`ivgs-workers/models/task_result.py:307` declares the worker's `StoryboardScene` with
`model_config = ConfigDict(extra="allow", …)`. **So the data is not lost.** Every key the
model emits survives on the pydantic object, into `StoryboardGenerationOutput.scenes`, through
`to_checkpoint_data()` and into `pipeline_checkpoints.checkpoint_data` — written on the line
after the scenes are saved. It is missing only from the *table*.

`app/services/storyboard_reconcile.py` recovers it, and the constraints are the interesting
part:

| property | why |
|---|---|
| **matched on verbatim narration, never on index** | a re-run producing a different scene count makes every index mean something else; matching on it would attach one scene's template to another scene's words |
| **never overwrites a non-empty field** | the checkpoint holds what the model *first* said — older and less checked than a spec WP-IVGS-09f's guard verified or an operator edited |
| **`{}` counts as empty** | the GUI flip leaves an object that exists and says nothing; WP-IVGS-09c had to write `has_motion_spec` for exactly this |
| **never touches `updated_at`** | that column is the storyboard fingerprint's input, so a write here would invalidate the approval it runs underneath — RC-O12 in miniature, and WP-IVGS-09f measured it happening for real |
| **reads on GET, writes only on POST** | `overlay_authored_fields` returns a copied view so the gate's status can show the storyboard as authored without leaving a dirty ORM object for the next `commit()` to flush |

---

## §4 TASK 2 — the v7 contract

Published through the WP-63 lineage mechanism: `app/scripts/wp63_publish_storyboard_prompt.py`,
same script, same one-publish shape, current version preserved inactive.

### (a) The description must depict the narration's referents — RULE 5 amended

**STAGING MAY REMAIN. CONTENT IS MANDATORY.** The desk, the lamp, the palette and the framing
all stay; a description made *only* of them has described the room. Every description now
answers, in order and with the first three non-optional:

1. **WHAT IS SHOWN** — the referents the narration names
2. **IN WHAT STATE** — how much is already on the page
3. **CHANGING HOW** — what is different at the end of the scene from the beginning
4. and then the staging

and carries **the deletion test in its second form**: RULE 1 asks you to delete every digit
and check the description survives; v7 asks you to delete every piece of *staging* and check
the same. The operator's own measured example is quoted in the template as the WRONG answer,
verbatim — every rule in this template that has actually held carries the output that broke it.

### (b) RULE 1 EXTENDED UPSTREAM — the general rule

RULE 1 has governed the **description** since v3 and has never governed the **media-type
choice**. That gap is the whole defect: a scene whose content *is* written or numeric could
still be handed to diffusion, and RULE 1 then forbade its description from naming the very
thing the scene teaches. The scene was left with nothing to depict, and *"a hand, a pencil,
warm lighting"* is what nothing-to-depict looks like.

v7 classifies the content **first** and derives the medium from it. A content-bearing scene
has exactly two sanctioned answers, and **there is no third**:

- **`motion_graphics` with `generation_params`** — the RULE 8 path, a renderer drawing the
  digits in a real font; or
- **a diffusion medium with `text_carried_by: "narration"`** — an explicit declaration that
  the words carry the text while the picture carries the situation.

**The declaration is a COLUMN, not a phrase in the prose** (migration 0045). Every previous
attempt to state something about a visual inside the visual's own text has had to be recovered
by a regular expression afterwards, and those are the checks this repository has repeatedly
measured being satisfied by accident. A declaration a machine must infer is not a declaration.

⛔ **And declaring never licenses a digit.** RULE 1 is checked *before* the declaration, so a
declared scene whose description names a numeral or asks for "the calculations" is refused
exactly as an undeclared one is. Pinned by
`test_the_declaration_never_licenses_a_digit`; if that ordering is ever reversed,
`text_carried_by` becomes a way to ask an image model for digits with the gate's blessing.

**The 09f narration guard is kept exactly as is.** Assertions 1–4 are unchanged byte for byte;
it is the arithmetic-domain instance of this rule and it stays. §6 adds a *fifth* assertion,
for the new parameter only, and says why.

### (c) Media type is DERIVED, and the reason is recorded — RULE 9

One line per scene naming the classification that decided the medium, into
`storyboard_scenes.media_rationale`. WP-64 made the choice deliberate and WP-68 gave it a
fourth option; neither asked why, so a wrong choice and a right one have looked identical on
the row ever since and the reviewer has had nothing to read.

### Every gate the publisher enforces, dry-run against v7 before any database write

| group | package | phrases | result |
|---|---|---|---|
| BINDING | WP-63 | 3 | ✅ |
| MEDIUM | WP-64 | 4 | ✅ |
| OUTCOMES | WP-64 | 4 | ✅ |
| NO_TEXT (RULE 1) | v3, tightened five times | 2 | ✅ |
| V5 | WP-65 | 5 | ✅ |
| V6 | WP-68 | 4 | ✅ |
| **V7** | **WP-IVGS-10** | **10** | ✅ |
| **FIELD LIST** | **WP-IVGS-10** | **3** | ✅ |
| templates offered vs served | — | 4 / 4 | ✅ none unknown |
| **template parameters named in the prompt** | **new gate** | 7 | ✅ none unnamed |

**`RULE 1 IS TIGHTENED, NOT TRADED`** — the assertion that matters most in the suite is
`test_every_earlier_gate_phrase_survives_v7`, parameterised over all six earlier groups.

⛳ **One new publisher gate is worth naming.** It checks that every parameter the templates
module *declares* is named somewhere in the prompt. Without it, adding `phase` in Task 4 would
have produced specs missing it, refused by `parse_and_validate` one stage late, with a message
about a missing parameter rather than about a prompt that never asked for one.

---

## §5 TASK 3 — the completeness validator at the gate

**One assessment, two consumers, no second opinion.**

| | where | severity | effect |
|---|---|---|---|
| soft | `GateService.status()` → `GET /projects/{id}/gates` → `GateReviewPanel` | `flag` | shown to the reviewer, **blocks nothing** |
| hard | `ProjectService.approve_storyboard`, after `_author_missing_motion_specs` | `refuse` | `409 STORYBOARD_INCOMPLETE`, every failing scene named in one message |

**Why the hard check runs AFTER the authoring.** A motion scene arrives with no template far
more often than not — that is §3's transit loss — so a completeness check placed before the
authoring would refuse every motion scene in every storyboard for a field the very next line
fills in. It runs on the rows as they will actually be dispatched.

**Its own error code, not `INVALID_STATE_TRANSITION`.** A reviewer told "invalid state
transition" goes to look at the project's state, and the project's state is fine: what is
wrong is named scenes on their screen. The 409 carries the full per-scene list so the surface
shows the same evidence the refusal was computed from.

**The approval stands; only the dispatch is refused** — the same rule every other release
refusal at this gate already follows.

**No prompt loops.** A refusal is a stop and the fix is the reviewer's: rewrite the
description, flip the medium, or declare the carrier. Nothing re-asks a model.

**Every scene appears in the gate payload, not only the failing ones.** A list that shows only
problems cannot be told from a list that was never computed.

⛔ **And the panel must never render the soft flags as a verdict.** There is no
count-of-problems badge on the Approve button, no disabled state driven by flags, and no
wording implying the storyboard is bad. The human gate stays the judge of everything
subjective; the panel is the evidence, laid out so it can be judged.

---

## §6 TASK 4 — RC-O10: the template distinguishes its phases

RC-O10, in its own words: *"Scenes 2 and 3 render the identical animation; so do 4 and 5. One
multiplier digit of one sum, and the template takes only `(top, bottom, step)` — it cannot
separate 'write the 2, carry the 1' from '…so our first answer is 92'."*

`step` says **which multiplier digit**. It has never said **how far through that digit's row**,
and those are two different questions. Both column templates now take a `phase`:

| phase | what it draws | the narration that chooses it |
|---|---|---|
| `full` | the whole row, beginning to end. **THE DEFAULT** | one sentence walks the whole row |
| `start` | the first column only — written, carried, row left **incomplete** | writes a digit and carries, announces no result |
| `complete` | opens with that first column **already drawn**, finishes the row | continues a begun row and announces its result |

### Measured, on the four scenes that opened RC-O10

| scene | narration (verbatim, abridged) | spec | last frame |
|---|---|---|---|
| 2 | *"…ones digit, which is 4 in 14. Multiply 4 times 3 … **carry the 1**"* | `23×14 step 0 phase start` | `2` + carry `1` — **no 9** |
| 3 | *"…4 times 2 … our **first answer is 92**"* | `23×14 step 0 phase complete` | `92` + carry |
| 4 | *"…tens digit, which is 1 in 14 … **zero in the ones place**"* | `23×14 step 1 phase start` | `0`, `3` |
| 5 | *"…1 times 3 … 1 times 2 … **second answer is 230**"* | `23×14 step 1 phase complete` | `230` |

**`start`'s last frame and `complete`'s first frame carry the same marks**, for both steps —
the second scene opens on exactly the page the first closed on. That continuity is the
property a lesson needs and the one the single-picture version could not have. Pinned by
`test_start_hands_the_page_to_complete_unchanged`.

### ⛔ `full` is byte-identical, and the frame count does not prove it

| template | params | frames | ops digest before | after |
|---|---|---|---|---|
| `column_multiplication_step` | 23×14 step 0 | 89 | `f614cd2acc14b8c2` | **same** |
| `column_multiplication_step` | 23×14 step 1 | 83 | `71bc3b21f2b88f50` | **same** |
| `column_multiplication_step` | 32×21 step 1 | 83 | `55e9a84cdfbf1464` | **same** |
| `column_addition_carry` | 230+92 | 135 | `9e5df190d8b2ba7a` | **same** |
| `column_addition_carry` | 27+15 | 115 | `e0d67515954c23a7` | **same** |

⚠ **An intermediate cut of this change moved two of those digests while keeping the frame
count identical.** Seeding the partial-product list with the placeholder zeros before the
opening hold put the zero on screen from frame 0 instead of after eighteen frames: 83 frames
at step 1 exactly as before, different pixels. **Only an op-level comparison caught it**, which
is why the digests are banked in the test file rather than the counts. Every banked frame in
`dev/workpackages/reference/` and every rendered asset on the fleet was produced by the
pre-phase code.

### The guard learns the parameter — and assertions 1–4 are untouched

`producible_numbers` is now phase-aware: `(23,14,step 0)` reaches **92** at `full` and stops at
**{1,2,3,4,12,14,23}** at `start`, because the row is deliberately left half-written. **Absent
or `"full"` reproduces the pre-phase set exactly**, pinned by
`test_producibility_narrows_with_the_phase_and_is_unchanged_without_it`.

A **fifth assertion** refuses both wrong ways round: a scene announcing a result under `start`
(the learner hears a number the picture cannot contain), and a scene that only carries under
`full` (the answer appears before the words reach it — RC-O10 seen from the other side).

⚠ **This is an addition to the 09f guard, and the order said to keep that guard exactly as is.**
Nothing was removed or weakened; assertions 1–4 are byte-identical. The fifth exists because a
guard that cannot see a parameter cannot refuse a spec that gets it wrong, and adding `phase`
without it would move the defect from *"the template cannot tell these apart"* to *"the
template can, and nothing checks whether it did"*. **Flagged rather than assumed.**

### The parameter reaches every layer that has to agree about it

| layer | change |
|---|---|
| `shared/motion/templates.py` | `phase` on both column templates; `PHASES`; `_phase()` refuses an unknown value by name rather than defaulting |
| `shared/providers/client_registry.py` | `maths_motion.accepts_params` += `phase` |
| `ivgs-motion-renderer/main.py` | `_ACCEPTED_PARAMS` += `phase` — the renderer refuses by name against the WP-67 contract, so a parameter in one and not the other is a 400 on a spec the templates would have drawn |
| `motion_authoring.build_prompt` | the catalogue is rendered from the module, so `phase` appeared automatically — **with the wrong shape**, see §2(d) |
| `storyboard_generation.j2` RULE 8 | the phase, and how to read it from the narration |

---

## §7 Tests — zero new failures, and one figure that reconciles

**Two full-suite passes, as the order allows.** The second is the one below.

| Tree | with the change | baseline (board) | delta |
|---|---|---|---|
| `ivgs-api` | **1545 P / 0 F** | 1451 P / 0 F | **+94, zero failures** |
| `ivgs-workers` | 939 P / 18 F / 48 S / 15 E | 939 / 18 / 48 / 15 | ✅ **byte-identical** |
| `ivgs-scheduler` | 52 P / 15 F | 52 / 15 | ✅ byte-identical |
| `ivgs-backup-worker` | **4 P / 0 F** | 4 P | ✅ — see the note below |
| `ivgs-motion-renderer` | 24 P / 2 S | 24 / 2 | ✅ byte-identical |
| `tests_system` | 193 P / 12 F / 15 S / 30 E | 193 / 12 / 15 / 30 | ✅ byte-identical |

**The `ivgs-api` +94 reconciles exactly**: 71 new tests in this package's four
files, plus **23** from WP-IVGS-09f, which the board's baseline table predates
(it was last updated by 09d). 1451 + 23 + 71 = **1545**.

⚠ **Two measurement artefacts of my own invocation, recorded because both looked
like regressions.**

1. **Seven failures that were two pytest processes sharing one database.** A
   tool timeout left an orphaned run alive; a second run against
   `ivgs_reconciliation_test` — which `TRUNCATE`s every table after every test —
   produced failures in `test_bug_004`, `test_bug_009` and `test_checkpoint_api`
   that had passed minutes earlier and passed again once the orphan was killed.
   `ps aux | grep pytest` showed both. **Not a regression; my measurement.**
2. **`ivgs-backup-worker` read 4 FAILED** until it was re-run with the three
   extra environment variables RC-J8 requires. Re-run correctly: **4 passed.**
   That is a single-tree re-measure, not a third full-suite pass, and the same
   applies to `ivgs-workers`, whose ten new tests arrived after the second pass.

⚠ **Two existing test files were EDITED, and neither was weakened.**

* **`test_wpivgs09c_motion_authoring.py`** — `CORRECT` now carries a phase per
  scene. The change is RC-O10 itself: the shipped specs for scenes 4 and 5 were
  `(23, 14, step 1)` for BOTH, so `AS_SHIPPED[4] == CORRECT[4]` cannot hold any
  more. `test_scenes_4_and_5_were_ALREADY_right_and_stay_accepted` now asserts
  both halves separately — the guard still does not REFUSE them (no false
  positive was introduced), AND the two now render different pictures.
* **Three gate fixtures** (`test_wp62_gates`, `test_wp38_storyboard_state`,
  `test_wp63_regeneration`) became v7-valid storyboards. Their narrations read
  `f"Scene {i}"`, which states a numeral, so RULE 1-EXTENDED refused them —
  correctly. The assertions are untouched; the scenes now carry the declaration
  a real scene like that would.

⛳ **And the fixtures caught a real defect in my own classifier.** My first
rewrite described *"a partial-product row already **written** above a ruled
line"* — which is v5's RULE 1 gold-standard answer — and the text-demand check
refused it on the bare word "written". Three existing tests failed and were
right to. The check now triggers on the TEXT OBJECT (calculations, the numbers,
a caption, a message on screen), never on the verb alone, and both directions
are pinned.

---

## §8 TASK 5 — the acceptance run, and exactly what it proves

Fresh project `5d58f2f5-88b9-439e-aea5-beaede42b694` through the normal flow:
create → upload the operator's own 3,172-byte source script (`sha256 3ea4eb8a…`)
→ trigger. Same brief, same outcomes, same 300 s as `9c29b1d1`.

### ⛔ The first run FAILED, and it found a defect nothing else could have

    Scene 3: media_type 'motion_graphics' is not in the pipeline taxonomy.
    Known values: ['animated','animation','image','still','video','video_clip'].
    Stage 3 dispatches on this field and has no branch for it.

**Stage 2 has never been able to receive a `motion_graphics` scene.** WP-68 added
the value on 2026-08-26 to the PostgreSQL enum, the capability registry, the
selection panel and the prompt — and not to `MediaType` in
`ivgs-workers/models/task_result.py`. Nothing met the gap because nothing had
tried: every motion scene on this fleet since then arrived by a GUI flip or by
Regen, both of which write through the API, past that enum entirely. **This run
was the first time a storyboard model ever chose the value**, and it met the gap
immediately. WP-53's check RAISES rather than skipping the scene — deliberately,
and correctly — so **one scene failed the entire storyboard** and the stage
retried to exhaustion. Fixed here (the enum and the synonym table are not a
frozen stage body), pinned by ten tests including the invariant that would have
caught it on the day: every enum member must be reachable from the synonym
table.

### The second run

**12 scenes.** ⛳ **Five chose `motion_graphics`** — a media type the previous
prompt could ask for and the pipeline could not accept.

⛔ **And none of v7's three new fields arrived.** `generation_params`,
`media_rationale` and `text_carried_by` were all NULL on all twelve rows, and
the stage-2 checkpoint holds only eight keys per scene. **That corrected §3's
premise**: the loss is not the POST, it is `_validate_storyboard_json:315-324`,
an explicit eight-keyword constructor that drops every extra key *before* the
checkpoint is written. `extra="allow"` keeps keys that are SUPPLIED, and none
are. Both losses are inside the frozen body — **RC-P1**.

### The gate, and the reviewer's answers

| stage | refusals | soft flags | ok |
|---|---|---|---|
| as authored | **4** | 8 | 0 |
| after the reviewer's answers | **0** | 6 | 6 |
| after approval authored the templates | **0** | **0** | **12** |

⚠ **The four declarations and six descriptions were written BY ME, standing in
for the reviewer, and that is the honest limit of this run.** They could not
come from the model, because RC-P1 blocks their transport. What the machine did
unaided: chose the media types, wrote descriptions markedly more content-bearing
than any previous version's, and — at approval — authored six templates from the
narrations, **including the phases**, through WP-IVGS-09f's guard.

⛳ **The authoring picked the phases correctly and unaided:**

| scene | narration | authored spec |
|---|---|---|
| 2 | *"We start with the ones digit… Multiply 23 by 4."* | `col_mult 23×14 step 0` **`start`** |
| 3 | *"4 times 3 is 12, write 2 and carry the 1… first answer is 92."* | `col_mult 23×14 step 0` **`complete`** |
| 5 | *"we multiply 23 by 10, which equals 230."* | `col_mult 23×14 step 1` **`complete`** |
| 6 | *"92 plus 230 equals 322."* | `col_add 92 + 230` `full` |
| 8 | *"32 by 1 to get 32. Then 32 by 20 to get 640."* | `col_mult 32×21 step 1` `full` |
| 9 | *"32 plus 640 equals 672."* | `col_add 32 + 640` `full` |

**Task 1's table, re-run on the new storyboard: 12 DEPICTS, 0 GENERIC, 0
DELEGATES-TO-WRONG-MEDIUM.** Draft asset
`0b64b812-2c35-4455-99f6-b0984db8077b`, 2,627,405 bytes, 12/12 scenes composed.

### One frame per motion scene, read by eye against its narration

All six correct, and **scenes 2 and 3 close RC-O10 visibly**: scene 2 ends with
the carry and the `2` alone, scene 3 opens on that exact page and ends at `92`.
Banked at `dev/workpackages/reference/wpivgs10-v7-fixture/`.

⚠ **Scene 8 is a residual.** Its narration works BOTH partial products in one
breath; `column_multiplication_step` draws one row, so the picture shows 640 and
not the 32 before it. The spec is consistent with the words and the guard
accepted it. The defect is upstream: v7 says *"give each step its OWN scene"*
and this storyboard did not.

---

## §9 ⛔ THE FINDING THAT GOVERNS THE OPERATOR'S ACCEPTANCE WATCH

**Task 5 asked for the image scenes to be checked for attempted digit-drawing.
Four of five attempted it.**

| scene | its description named | the image contains |
|---|---|---|
| 0 | a surface *"entirely empty, no ruled line and no rows written yet"* | ✅ **nothing written. Clean.** |
| 1 | *"two rows… right edges flush… a freshly ruled horizontal line… answer row still empty"* | ⛔ **`23 = 14`** and **`-- = 14`** |
| 7 | *"the completed working… every row filled beneath its ruled line"* | ⛔ two sheets of invented arithmetic |
| 10 | *"both partial-product rows written above the ruled line… answer row completely filled"* | ⛔ a page of invented arithmetic |
| 11 | *"the working visible across it: two partial-product rows above the ruled line"* | ⛔ **the description's own vocabulary printed as headings** — *"Partial product rows"*, *"Full Answer row:"* — over nine rows of garbage |

**Not one of those five descriptions contains a numeral.** They pass RULE 1's
deletion test, they pass the gate, and the model drew digits anyway — because a
*column-arithmetic layout* means digits, and describing the layout is enough to
summon them.

⛔ **So RULE 1's founding premise does not hold.** "Describe the structure and
let the overlay supply the digits" assumes a diffusion model will leave the
structure empty. It will not. RULE 1 can stop you ASKING for digits; it cannot
stop the model DRAWING them.

**The correlation across the five images is clean and it points at the fix:**
the only image with no writing is the only one whose surface was described as
EMPTY. Proposed v8 amendment, for the operator's ruling rather than this
package's initiative:

> A diffusion scene may depict a working surface only in its **EMPTY** state.
> Any surface with writing already on it is `motion_graphics`, without
> exception. "Already written", "filled", "the completed working" and
> "partial-product row" are forbidden in a diffusion description — they are
> instructions to draw text, in the same way naming a numeral is.

That is objective and gate-checkable with the machinery this package already
ships. **It is not implemented here**: one run is not a false-positive rate, and
fitting a new hard rule to a single storyboard is the over-fitting the operator
withdrew the math-planner proposal for. Filed as **RC-P2**.

⛔ **And a second, unrelated defect the frames exposed: scene 4's `video_clip` is
BLANK.** 720×480, 48 frames, 889,012 bytes, recorded `success`, composed into
the draft — and flat. Greyscale stddev **0.45–0.53** at five sample points
against **95.8** for a real image. That is a fabricated absence of exactly the
class WP-57/60 legislated against: an asset that is not the requested render,
which the pipeline cannot tell from one that is. **RC-P3.**

---

## §10 What was deployed, and what was written to production data

**Fleet coherent at `v5.34.0-v7-contract`** (api at `v5.34.1`, one patch ahead for §5's
read-path correction). All six containers `DEPLOY VERIFIED` against the running image, never
against a tag variable (`dev/CLAUDE.md` §6).

| node | service | image |
|---|---|---|
| node-01 | `fastapi-backend` | `ivgs-api:v5.34.1-v7-contract` |
| node-01 | `motion-renderer`, `nextjs-frontend`, 3 × celery | `v5.34.0-v7-contract` |
| node-02 | `celery-worker` | `v5.34.0-v7-contract` |
| node-03 | `cogvideox-worker` *(not `celery-worker` — §6.2)* | `v5.34.0-v7-contract` |
| node-04 | `celery-worker` | `v5.34.0-v7-contract` |

Workers travelled as an artifact (`docker save | sudo sh -c "zstd -o …"`, 319 MB), never GHCR
— §6.1. **node-05, node-06 and `.96` were not contacted.**

⚠ **node-02's first deploy printed `couldn't find env file: /root/ivgs-infra/.env`** — the
missing-`cd` trap §6.1a names, visible only because stderr was not redirected. It is the
fourth time this repository has recorded that exact line.

ⓘ **`scripts/verify-deployed-image.sh` gave three false `DEPLOY FAILED`s** before I read it:
it prepends `root@` itself, so `root@192.168.1.91` became `root@root@…` and an unreachable
host reports as *"container is not running at all"* — indistinguishable from a genuinely
absent container. Ground truth came from `docker ps` on each node. **Not fixed here; RC-P11.**

### Production data writes, stated plainly

1. **Migration 0045** — two nullable columns and a CHECK on `storyboard_scenes`. **Additive;
   zero existing rows altered**, verified: 0 of 38 carry either value.
2. **Prompt v7 inserted, v6 deactivated.** v1–v6 all still readable; rollback is one UPDATE.
3. **Project `5d58f2f5` created and then deleted** through the WP-59 flow — 60 rows, 27 files,
   `audit_id a1d23697`. Nothing else touched: `9c29b1d1` still has 14 scenes / 200 assets and
   `c12fa967` 18 / 102, both exactly as found.
4. **Nothing was written to `9c29b1d1` or `c12fa967`.** The Task-1 measurement is read-only.

⚠ **An observation about `c12fa967`, recorded because it changes what the baseline means.**
Its scene 1 was flipped to `motion_graphics` at **2026-08-28 22:56:59Z** and it produced fresh
audio assets at **23:03** — i.e. it is being run, an hour before this package started. It is
the AD-05 conformance baseline that `dev/CLAUDE.md` says must not move before M3.3. **Not
this package's doing and not this package's call**; flagged.

---

## §11 ⛔ PUSH — count-gated

**Nothing was pushed. One commit is held.**

⚠ **The board's "Held now: WP-IVGS-09b's single commit" was stale by four packages.** Measured
at the close of this package from the remote-tracking ref and its reflog — the discipline that
row itself demands: `origin/main` and local `HEAD` were **both `ab5d874`**, so 09b, 09c, 09d,
09e and 09f are **all already on the remote** and the held count before this commit was **0**.
The operator also pushed two AD-07/AD-10 amendment commits *during* this session, which moved
`HEAD` under the working tree; they touch two new files and do not overlap this package.

```bash
# node-01. Refuses unless EXACTLY ONE commit is held.
cd /opt/ivgs
git fetch origin
HELD=$(git rev-list --count origin/main..HEAD)
if [ "$HELD" -ne 1 ]; then
  echo "REFUSED: expected 1 held commit, found $HELD. Do not push."
else
  git log --oneline origin/main..HEAD
  echo "--- 1 commit as expected; pushing"
  git push origin main
fi
```

---

## §12 ⛔ WHAT IS NOT DONE, AND WHAT THE OPERATOR MUST RULE BEFORE THE WATCH

| id | state |
|---|---|
| **RC-P1** | ⛔ **OPEN, and it gates this package's acceptance.** v7's `text_carried_by` and `media_rationale` cannot reach the database — two losses inside a frozen stage body. **Sanction the two-line edit, or accept hand-answering at the gate.** The wrapper is written, tested and inert until then |
| **RC-P2** | ⛔ **OPEN.** RULE 1's premise does not hold: four of five image scenes drew digits from digit-free descriptions. A v8 amendment is proposed and deliberately unimplemented |
| **RC-P3** | ⛔ **OPEN.** A blank clip recorded as a successful render |
| **RC-P11** | ⓘ `verify-deployed-image.sh` reports an unreachable host as a missing container |
| **RC-P12** | ⚠ Scene 8 crowded two partial products into one scene; the template draws one row. Upstream of the renderer |
| **RC-O10** | ✅ **CLOSED** |
| **RC-P4** | ✅ **CLOSED** — Stage 2 can now receive `motion_graphics` |

### The acceptance is the operator's, and I have stopped

Task 5 says the package's acceptance is the operator watching a correct lesson, and that gate
is theirs. My test project is deleted, the fixture is banked, and I have not run a second one.

⛔ **But they should not start the watch blind.** On a fresh v7 project today they will meet,
in this order: a storyboard whose media choices and descriptions are markedly better than any
previous version's; a gate that refuses every content-bearing diffusion scene because RC-P1
blocks the declarations; and, once past it, image scenes that attempt digits because of RC-P2.
The motion scenes will be right.

**Frozen stage bodies were not touched. Nodes 05, 06 and `.96` were not contacted. No secrets
appear in this report or in any commit.**
