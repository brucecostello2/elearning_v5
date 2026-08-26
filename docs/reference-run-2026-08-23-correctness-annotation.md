# The reference run is a CONFORMANCE baseline, not a CORRECTNESS one

**Subject:** `reference-run-2026-08-23` (`/mnt/ivgs-shared/reference-run-2026-08-23/`)
**Written:** 2026-08-26 by WP-61-QWEN, Task 4
**Status of the run:** UNCHANGED. Nothing in it was regenerated, edited or
re-scored. **RULED: annotate, do not regenerate.**

---

## 1. The one sentence

**"Matches the reference" must never be read as "correct".** The reference run
is byte-comparable output from a known pipeline at a known commit, and that is
exactly what a Temporal conformance diff needs. It also *teaches arithmetic
wrongly*, and no stage of the pipeline that produced it can tell.

## 2. What the run is for, and why it must not move

`reference-run-2026-08-23` is the baseline the AD-05 orchestration migration is
diffed against: same pipeline, same stages, same models, byte-comparable
output. Its entire value is that it is FIXED. A conformance diff answers one
question — *did moving the orchestrator from Celery to Temporal change the
output?* — and it can only answer it if the output it compares against has not
changed for any other reason.

Regenerating it to fix the content would destroy that. The first production run
under Temporal, after M3.3, is where a corrected version belongs.

**Consequence, and it is deliberate: storyboard generation and transcript
refinement STAY ON LLAMA until after M3.3.** WP-61 routes *translation* to Qwen
on node-05 and moves nothing else. If Stage 1 or Stage 2 moved to a different
model, the next conformance diff would show differences caused by the model
rather than by the orchestrator, and the diff would answer nothing. **The model
does not move under the diff.**

## 3. What is wrong with the content

**EXTENDED 2026-08-26 by WP-62 Task 9(a). The corruption is wider than scene 5,
and wider than this document previously said.** The paragraph below is
unchanged; what follows it is the second worked example, quoted in full,
because "6, 11, 12 and 13 all carry the same confusion forward" understated it.
The entire second worked example is self-arguing narration, and the scene that
starts it is *correct* — which matters, because a false flag was raised against
that scene and the flag contract has been narrowed as a result (§3.3).

The project is `c12fa967-f989-4ed4-8e20-3ea62cb92e8f`, *"double digit
multiplication"*, 18 scenes. `storyboard_scenes.scene_index` is **zero-based**,
so the sixth scene is `scene_index = 5`. Read from the live database
2026-08-26, verbatim:

> **scene_index 5:** "Multiply 10 times 3, which equals 30, and 10 times 2,
> which equals 20. Our second answer is 320, but we wrote it as 230 in the
> previous step, which is incorrect."

Two digits are transposed and the narration then argues with itself about the
transposition.

The pipeline produced a 720p draft of this, on time, with every stage green.

### 3.1 The first worked example, 23 x 14 — scenes 5, 6, 7

Scenes 0-4 set the problem up correctly. Then, verbatim from
`storyboard_scenes` on 2026-08-26:

> **5:** "Multiply 10 times 3, which equals 30, and 10 times 2, which equals
> 20. Our second answer is 320, but we wrote it as 230 in the previous step,
> which is incorrect."
>
> **6:** "Now, let's add the two answers together. We have 92 and 320, but
> since we are adding the results of multiplying 23 by 4 and 23 by 10, we
> should add 92 and 230, which was the result of multiplying 23 by 10, but that
> was also incorrect."
>
> **7:** "The correct step is to multiply 23 by 10, which equals 230, and then
> multiply 23 by 4, which equals 92. Now, let's add them: 92 + 230 equals 322."

Scene 7 lands on the right answer (23 x 14 = 322). Scenes 5 and 6 are the
lesson correcting a mistake it made two sentences earlier, out loud, to a
learner who has no idea which number to write down.

### 3.2 The second worked example, 32 x 21 — scenes 8 to 14, quoted in full

This is the extension. **Six consecutive narrations, verbatim**, scenes 9 to
14, following the setup at scene 8 ("Let's try another example: 32 times 21.
Write 32 on top and 21 underneath."):

> **9:** "Start with the ones digit, which is 1. Multiply 1 times 2, which
> equals 2, and 1 times 3, which equals 3. Our first answer is 32."
>
> **10:** "Now, move to the tens digit, which is 20. Multiply 20 times 2, which
> equals 40, and 20 times 3, which equals 60."
>
> **11:** "This gives us 200 + 60, which equals 260, but we wrote it as 640 in
> the previous step, which is incorrect."
>
> **12:** "The correct calculation is 20 times 2 equals 40 and 20 times 3
> equals 60, so our second answer is indeed 260, but since we are multiplying
> 21, which is 20 + 1, we need to consider the correct placement of the
> numbers."
>
> **13:** "Now, let's add 32 and 260, but since we are adding the results of
> multiplying 32 by 1 and 32 by 20, we should add 32 and 640, but that was
> incorrect."
>
> **14:** "The correct step is to multiply 32 by 1, which equals 32, and then
> multiply 32 by 20, which equals 640. Now, let's add them: 32 + 640 equals
> 672."

Read as a sequence, the second example has the same disease as the first and a
worse case of it. Scene 9 is CORRECT — 32 x 1 worked digit by digit gives 2 and
3, and 32 is the right first partial product. Scene 10 is correct. Scene 11
then invents a step: it says "we wrote it as 640 in the previous step", and no
previous step says 640; and it asserts 200 + 60 = 260 out of operands (40 and
60) that produce neither. Scene 12 restates the wrong partial product as "indeed
260" and then hedges. Scene 13 says to add 32 and 260, then says to add 32 and
640, then says that was incorrect. Scene 14 arrives at 672, which is right.

**Four of the six are defective, two are correct, and the lesson never says
which of the numbers it produced is the one to use.** 32 x 20 = 640, not 260;
the narration contains both, asserts each in turn, and calls each of them
incorrect at a different moment.

### 3.3 What this changes about the baseline

Nothing about its status: `reference-run-2026-08-23` remains the technical
conformance standard for the AD-05 migration and must not be regenerated before
M3.3 (§2, §5).

What it changes is how far "matches the reference" is from "correct".
This document previously named one bad scene and four that carried it forward.
The measured position is that **both worked examples in an 18-scene lesson on
double-digit multiplication are corrupted by self-arguing narration** — scenes
5, 6 and 7 in the first, and 11, 12, 13 with 14 tidying up in the second. Nine
scenes of eighteen. A run that reproduces this byte for byte has proved the
orchestrator changed nothing, and has proved nothing whatever about the
lesson.

**"Matches the reference" is even less "correct" than this document previously
recorded.**

## 4. How it was found: by a translator, not by a checker

Nothing in IVGS validates the arithmetic in a narration. There is no stage that
could: Stage 1 refines a transcript, Stage 2 storyboards it, Stages 3–8 render
it. **Every quality gate in the system measures whether the output matches the
input** — CLIP similarity between an image and its prompt, caption timing,
duration, resolution — and this input was faithfully rendered.

It was caught on 2026-08-25, incidentally, during a standalone Qwen evaluation
that translated this narration into Spanish, French, German and Arabic. **The
model appended a correction in all four**, unprompted. From the banked output
(`/mnt/ivgs-shared/qwen-translation-output-20260825.txt`):

> **es-ES:** "Nuestra segunda respuesta es 320, pero en el paso anterior la
> escribimos como 230, lo cual es incorrecto."
>
> **de-DE:** "Unsere zweite Zwischensumme ist 320. Im vorherigen Schritt haben
> wir jedoch 230 geschrieben, was falsch ist."

That is a real finding and it is also, as a translator behaviour, a defect —
which is why WP-61 Task 3(c) rules the translation contract to
**fail-and-flag**: translate faithfully, never correct, emit
`IVGS-TRANSLATION-FLAG:` instead. A translator that silently improves the
source produces a deliverable that disagrees with the English in languages
nobody on the team can read.

## 5. What this annotation therefore obliges

| | |
|---|---|
| **Comparing against this run** | Legitimate, and the point of it. A byte-identical result means the orchestrator changed nothing. |
| **Citing it as an example of correct output** | NOT legitimate. It is an example of *conformant* output. |
| **Regenerating it before M3.3** | Forbidden. It is the baseline the migration is measured against. |
| **Regenerating it after M3.3** | Expected — as the first production run under Temporal, not as a repair job. |
| **Editing the source narration** | Not done, deliberately. The erroneous narration is the live test case the WP-61 translation flag path fires on (Task 3(d)); editing it would remove the only real-data proof that the flag works. |

## 6. Where else this is recorded

* `/mnt/ivgs-shared/reference-run-2026-08-23/README.md` — beside the artefacts
  themselves, so a reader who finds the directory without finding this document
  still finds the annotation.
* WP-61-QWEN report, Task 4.
* WP-41-TEMPORAL-PREP and WP-42-VOICE reports reference this run; neither is
  edited, because neither was wrong about what it said.

---

## 7. The flags this source actually produced, and the two that were wrong

**Added 2026-08-26 by WP-62 Task 9. Operator-verified against the source.**

The es-ES variant `3fccf815-f639-43c1-8a90-631336dc2d13` was translated on
2026-08-26 under prompt v2 (`18c8919d`) and came back `flagged` with **seven**
flags. Verified against the narrations quoted in §3:

| Scene | Flag's stated reason (abridged) | Verdict |
|---|---|---|
| 5 | "Arithmetic inconsistency: 10*3 + 10*2 = 50, not 320 or 230." | **GENUINE** — the scene is erroneous. |
| 6 | "23*10 is 230, not 320; 92+230 is 322, not 320" | **GENUINE** |
| 9 | "1 * 32 is 32, but the described steps 1*2=2 and 1*3=3 imply a different number ... pedagogically confusing/incorrect" | **FALSE POSITIVE** — 32 x 1 worked digit by digit gives exactly 2 and 3, and 32 is the correct partial product. Correct standard algorithm, flagged on pedagogy. |
| 11 | "Source contains a factual arithmetic error (200 + 60 = 260, not 640)" | **GENUINE SCENE, MISREAD REASON** — see below. |
| 12 | "Arithmetic inconsistency: 20*2 + 20*3 equals 100, not 260." | **GENUINE** |
| 13 | "32 * 20 is 640, not 260 ... and logical inconsistency" | **GENUINE** |
| 15 | "'start the next line with a zero' is a non-standard or potentially incorrect pedagogical description" | **FALSE POSITIVE** — a pedagogy opinion about a correct convention. |

**Scene 11 is worth stating precisely, because the flag and the scene are both
defective and not in the same way.** The flag says "200 + 60 = 260, not 640",
which misreads its own arithmetic — 200 + 60 IS 260, and the flag's complaint
should be that neither figure follows from the operands the previous scene
supplied (40 and 60), and that 32 x 20 is 640. **The scene is defective
regardless**: it is self-referential ("we wrote it as 640 in the previous step"
about a step that says no such thing) and it asserts a partial product that is
wrong. A misread reason on a genuinely broken scene is still a flag that should
have fired.

### 7.1 The ruling, and what changed because of it

**RULED: the flag contract covers FACTUAL AND ARITHMETIC ERRORS ONLY.
Pedagogical style is out of scope and must not flag.**

Scenes 9 and 15 are the argument. Both are correct arithmetic; both were
flagged for how the lesson teaches. Long multiplication, division and fractions
are taught differently in different countries and all of those methods are
correct, so a translator's opinion about method is not a finding — and a false
flag on a correct lesson trains the reviewer to ignore the flags, which costs
more than the flag saves.

Prompt **v3** (`ivgs-api/seed/default_prompts/translation.j2`) states the scope
both ways: what to flag, what never to flag, and the test to apply — *could a
competent teacher who uses a different method disagree with you? Then it is
style.* It names scene 9's exact shape ("1 times 2 is 2, and 1 times 3 is 3, so
the answer is 32 ... it is the STANDARD ALGORITHM ... do not flag it") because
a rule stated abstractly did not stop this one. v2 is preserved inactive
through the prompts table's own versioning; the fail-and-flag MECHANISM v2
introduced is unchanged and correct.

### 7.2 The variant stays flagged

**RULED.** Under v3 the two false positives are expected to go and the five
genuine flags to remain, so `3fccf815` stays `state = flagged` either way. The
source is genuinely wrong and regeneration is post-M3.3 by the ruling in §2 and
§5. A flagged deliverable that a human must look at is the correct end state
for a faithful translation of a defective source — which is the whole point of
the fail-and-flag contract.


---

## 8. The quality record was validator-distorted until 2026-08-26

**Added 2026-08-26 by WP-63-VALIDATOR, Task 2.** Nothing in the run moved. No
asset was regenerated, no narration edited, no variant touched. What changed is
what the QUALITY RECORD beside the run is worth.

### 8.1 What was wrong

`ImageValidator`'s blank/solid-colour check computed *distinct colours divided
by total pixels* and demanded more than 0.05. That is a measure of colour
density, not of blankness, and its denominator is the pixel count. Stage 3 fits
every non-16:9 frame inside 1920x1080 and pads it with black before validating,
which adds 907,200 identical pixels — **43.75% of the frame** — to that
denominator.

So the pipeline's own letterboxing pushed real frames under the floor. Measured
on three frames the operator recovered from ComfyUI and verified by eye
(people at whiteboards, a hand with a pencil over paper):

| | as generated, 1024x1024 | after Stage 3's resize | old verdict |
|---|---|---|---|
| `ivgs_flux_00087_` | 0.0876 | 0.0485 | REJECT |
| `ivgs_flux_00089_` | 0.0766 | 0.0427 | REJECT |
| `ivgs_flux_00094_` | 0.0809 | 0.0447 | REJECT |

### 8.2 What it did to this run's record

The 2026-08-26 08:10 rescore of this project's banked assets returned
**11 approved / 1 flagged / 8 rejected** over 20 assets. **Six of the eight
rejections were "Image appears blank or solid color".**

Re-scored on 2026-08-26 under the corrected validator, append-only, tagged
`WP-63-VALIDATOR` (`asset_quality_scores`; the old rows are untouched and still
say what they said):

| | 2026-08-26 08:10 | 2026-08-26, corrected | moved |
|---|---|---|---|
| approved | 11 | **17** | +6 |
| flagged | 1 | 1 | — |
| rejected | 8 | **2** | −6 |

The six that moved are exactly the six that carried the blank/solid message.
The two remaining rejections are `Unsupported video codec: mpeg4` and the one
flag is a video resolution/duration deviation — unchanged, which is the control:
nothing moved that the fix did not touch.

**So: for three months this run's technical quality record understated it by
six assets, for a reason that had nothing to do with the assets.**

### 8.3 And they are still not good frames — for the reason §3 is about

This matters, and it is the same lesson as the rest of this document. The six
are **not blank**. Two of them, read by eye:

* `3d89b0ef…` is a wall-mounted screen carrying five rows of garbled
  arithmetic — `- 45 - 15+4+ - 15+2`, `- 25 - 15+ = - 15`. Rich, structured,
  and wrong.
* `ef51a8c8…` is a near-white sheet with a faint `x 6/4 =` floating in the
  middle of it.

Both are **text-in-the-visual failures**: the image model was asked for numbers
and produced text-shaped marks, which is precisely what RULE 1 of the storyboard
prompt exists to prevent and what §3 of this document is about at the narration
level.

The corrected blank check gives the right answer to its own question — these
frames are not blank. **Whether they are USABLE is a different question, and no
scorer in this pipeline answers it**, for the same reason §4 gives: every gate
here measures output against input, and these were faithfully rendered from
what they were asked for.

### 8.4 What this does not change

Nothing about the run's status. `reference-run-2026-08-23` remains the technical
conformance standard for the AD-05 migration, must not be regenerated before
M3.3, and its narration is still the live test case the WP-61 translation flag
fires on. The es-ES variant was not read and stays `flagged`.

**"Matches the reference" is still not "correct". What §8 adds is that "the
reference scored badly" was not correct either.**
