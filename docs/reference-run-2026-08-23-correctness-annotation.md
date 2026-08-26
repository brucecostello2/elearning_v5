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

The project is `c12fa967-f989-4ed4-8e20-3ea62cb92e8f`, *"double digit
multiplication"*, 18 scenes. `storyboard_scenes.scene_index` is **zero-based**,
so the sixth scene is `scene_index = 5`. Read from the live database
2026-08-26, verbatim:

> **scene_index 5:** "Multiply 10 times 3, which equals 30, and 10 times 2,
> which equals 20. Our second answer is 320, but we wrote it as 230 in the
> previous step, which is incorrect."

Two digits are transposed and the narration then argues with itself about the
transposition. It is not the only affected scene — 6, 11, 12 and 13 all carry
the same confusion forward, and 11 contains "we wrote it as 640 in the previous
step, which is incorrect" about a step that says no such thing.

The pipeline produced a 720p draft of this, on time, with every stage green.

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
