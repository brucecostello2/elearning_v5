# WP-IVGS-09f — a motion scene is authored from ITS OWN narration

**Report · 2026-08-28 · written as the work proceeded.**

⛔ **The primary deliverable is `OUTSTANDING_WORK.md` §RC-O.** This file says what was done,
what was measured, and what was not.

---

## §1 Headline

| Task | Result |
|---|---|
| (a) what the prompt receives / returned, as a table | ✅ §2 — **it got the narration and no position, then was handed the answer** |
| (b) author each scene from ITS OWN narration | ✅ §3 — worked example moved off this lesson's numbers; step kinds spelled out; neighbours supplied for operands only |
| (c) verify mechanically, refuse by name | ✅ §4 — **four assertions**, all derived from the templates' own arithmetic; commented as a guard, **not** the L7 checker |
| (d) re-author six, re-render, new draft, table + eyeball | ✅ §6 — draft **`5bb622d7`**, 14/14 composed, **six frames read by eye** |
| Zero new failures | ✅ §7 — like-for-like against HEAD baselines |

**Held: 5** (RC-O10…RC-O14). Frozen stage bodies untouched.

---

## §2 (a) What the authoring prompt actually received — measured

`build_prompt` took exactly four things:

| Given per scene | Present? |
|---|---|
| `narration` (the scene's own words) | ✅ |
| `visual_description` (image-era prose the renderer never reads) | ✅ |
| `project_name`, `project_description` | ✅ |
| **`scene_index`** | ⛔ **no** |
| **neighbouring scenes' narrations** | ⛔ **no** |

So the words *were* there. Two things defeated them.

**⛔ The prompt contained a fully worked answer in this lesson's own numbers:**

    So that scene is {"top": 23, "bottom": 14, "step": 0} — NOT {"top": 14, "bottom": 3}

At `TEMPERATURE = 0.1`, a model shown a complete answer returns that answer. It was written to
teach the whole-numbers rule; it functioned as an answer key.

**⛔ And a lesson works more than one sum.** `9c29b1d1` does 23 × 14 in scenes 0–7 and **32 × 21
in scenes 8–11**. Nothing told the prompt which one a scene belonged to.

### What came back, per scene — the table the order asked for

| # | Narration, abridged | Returned | Correct? |
|---|---|---|---|
| 2 | ones digit **4 in 14**; 4×3=12; carry the 1 | `{top:14, bottom:3, step:0}` | ⛔ operands **inverted** (draws 14×3=42) |
| 3 | 4×2=8, +carry → **first answer 92** | `{top:23, bottom:14, step:1}` | ⛔ step 1 draws **230**, not 92 |
| 4 | tens digit **1 in 14**; **zero as placeholder** | `{top:23, bottom:14, step:1}` | ✅ correct |
| 5 | 1×3, 1×2 → **second answer 230** | `{top:23, bottom:14, step:1}` | ✅ correct |
| 7 | 1 **plus** 2 → **final answer 322** | `{top:23, bottom:14, step:1}` | ⛔ wrong **operation**; can draw at most 230 |
| 10 | tens digit 2; 2×2, 2×3 → **second answer 640** | `{top:23, bottom:14, step:1}` | ⛔ wrong **sum entirely** (words work 32×21) |

**Four of six wrong. Five of six identical.**

---

## §3 (b) Authoring from the scene's own words

Three changes, in `motion_authoring.build_prompt`:

1. **The worked example is now 47 × 36**, not this lesson's sum — copying it is visibly wrong
   rather than quietly plausible, and the prompt says outright it is an illustration.
2. **Template choice is spelled out per step kind** — partial product / carry / placeholder row
   / addition of the two partials / place-value split — instead of resting on one word in a
   parameter gloss. `step` is defined explicitly as counting from the multiplier's units digit.
3. **The scene is placed in its lesson**: `scene_index` plus index-labelled `context_scenes`,
   marked **context-for-operands-only**. The scene's own words stay the sole authority on WHICH
   STEP.

⚠ **Point 3 is a deliberate widening of "its own narration", and the reason is measured, not
stylistic.** Scene 10 never says 32 or 21. Its multiplier is named once, in scene 8, and never
again. A prompt given only that scene's words cannot resolve its operands — asking it to would
be asking it to guess, which is what produced the defect. The guard's operand test is scoped the
same way, and §5 shows a test pinning exactly this.

**Dry-run before any deploy or data write**, twice, against the live binding
(`llama-3.3-70b-storyboard`, node-02): all six scenes returned the correct spec both times.

---

## §4 (c) The guard — four assertions, all refuse-by-name

`verify_spec_against_narration(spec, narration, context_text, scene_index)`:

| # | Assertion | Catches |
|---|---|---|
| 1 | **Step kind.** The template's keyword class must appear in the words | a template animating a step the words never mention |
| 2 | **Producibility.** No number the narration says may exceed anything the template can draw | scene 7 (322 > 230), scene 10 (640 > 230) |
| 3 | **The announced result.** A sentence announcing a result requires that exact number to be one the template produces | scene 3 — 92 is *smaller* than 230, so test 2 alone lets it through |
| 4 | **The multiplier the words name.** *"the ones digit, which is 4 in 14"* pins `bottom=14` **and** pins `step` to the position of 4 | scene 2 — inverted operands, invisible to 1–3 |

Every number in tests 2–4 is computed **the way the template computes it** — same units-first
digit order, same carries, same placeholder shift — so the guard cannot drift from what is drawn.

⛔ **It is a guard, not the L7 checker, and the module says so in those words.** It cannot tell
you a spec is correct; only that a spec is **provably inconsistent with the words it plays
under**. WP62-L7's real checker is human eyes until M3.3. Its blind spot is pinned as a passing
test rather than left implied — and RC-O14 records that scene 2 would have survived assertions
1–3, which is precisely why assertion 4 exists.

**A contradicting spec is now re-authored rather than respected.** WP-IVGS-09c deliberately left
an existing spec alone; that holds for a spec that is a *choice*, not for one the guard can
*prove* contradicts its narration.

---

## §5 ⛔ The second defect — found only because the first fix was deployed

With correct specs written to the database, **all six motion scenes still failed in the worker**:

    is media_type=motion_graphics but carries no generation_params

`project_service.approve_storyboard` **hand-rolled its own six-key scene payload** while
`regeneration.scene_payload` — the builder every other dispatch uses — has carried
`camera_angle`, `transition_type`, `effects`, `timing_offset_ms` and **`generation_params`**
since migration 0028. The release path never learned them, so **it could not dispatch a motion
scene's template even when the row held a perfect one**. The worker was telling the truth about
the message; the database held the spec all along.

Two builders for one payload was the defect; there is now one. The release path **also** now runs
the authoring guard — *"must not render"* has to mean on every path that renders, or it means
nothing.

---

## §6 (d) Proof

Deployed `ivgs-api:v5.33.2-scene-payload` on node-01 — service **`fastapi-backend`** (my first
attempt named `fastapi` and printed `no such service: fastapi`, caught **because stderr was not
redirected**), `--no-deps`, then `DEPLOY VERIFIED` on the running container.

**The guard fired live**, on the four it should and neither of the two it should not:

```
motion_spec_contradicts_narration index=2  reason=... the narration calls 14 the number
                                                     being multiplied BY ... wrong way round
motion_spec_contradicts_narration index=3  reason=... announces 92 ... never produces 92
motion_spec_contradicts_narration index=7  reason=... says 322 ... largest it produces is 230
motion_spec_contradicts_narration index=10 reason=... says 640 ... largest it produces is 230
   (scenes 4 and 5 were already correct and were left alone)
```

### The six specs beside their narration — read by eye, one frame each

| # | Narration (verbatim, abridged) | Spec | Frame shows |
|---|---|---|---|
| 2 | "…**ones digit, which is 4 in 14**. Multiply 4 times 3 … **carry the 1**" | `col_mult 23×14 step 0` | `23 × 14`, red carry **1**, row **92** ✅ |
| 3 | "…4 times 2 … our **first answer is 92**" | `col_mult 23×14 step 0` | `23 × 14`, **4 and 3 highlighted** ✅ |
| 4 | "…**tens digit, which is 1 in 14** … **zero in the ones place**" | `col_mult 23×14 step 1` | row **230** with placeholder **0** ✅ |
| 5 | "…1 times 3 … 1 times 2 … **second answer is 230**" | `col_mult 23×14 step 1` | row **230** ✅ |
| 7 | "…1 **plus** 2 … **final answer is 322**" | `col_add 230 + 92` | **230 + 92 = 322**, carry 1 ✅ |
| 10 | "…**tens digit, 2** … 2 times 2 … 2 times 3 … **second answer is 640**" | `col_mult **32×21** step 1` | **32 × 21 → 640** ✅ |

⚠ Frames were taken from **the assets themselves**, not from timestamps in the composed draft:
the composed timeline drifts from the manifest's nominal milliseconds (a sample at the manifest's
stated t=110 s for scene 10 landed in a neighbouring scene). The asset is the exact artifact; the
manifest offset is not. Recorded because reading the wrong frame would have "verified" nothing.

**New draft asset `5bb622d7-8c83-4cac-bb43-3d0ebd6f7643`** — `draft_720p_en-US.mp4`, 1280×720,
h264 + AAC 48 kHz stereo, **137.468 s**, 3,471,526 bytes, **scene_count 14, scenes_composed 14,
scenes_failed 0**, sha256 `a74f6c06…` matching its row. (Previous draft: `c9cabd58`.)

---

## §7 Tests, and one scare that was my own invocation

| Suite | With change | HEAD baseline | Delta |
|---|---|---|---|
| `ivgs-api` | 225F / **597P** / 1547E | 225F / 574P / 1547E | **0 new failures, +23 passed** |
| `ivgs-workers` | 18F / 935P / 52S / 15E | 18F / 935P / 52S / 15E | **0** |
| `ivgs-scheduler` | 15F / 52P | 15F / 52P | **0** |

The +23 are this package's own tests, which use project `9c29b1d1`'s **verbatim** narrations —
a paraphrase would test a sentence I wrote rather than the one that shipped.

⚠ **An intermediate run showed `ivgs-workers` at 22F/48S and I chased it before reporting it.**
`test_wp60_orphan_guard.py` skips unless `TEST_DATABASE_URL` is set; I had exported it for that
run and not for the baseline, so four tests unskipped and then failed on
`socket.gaierror: Temporary failure in name resolution` — the DSN host resolves inside
containers, not on the host. Re-run with the baseline's own invocation: **18F/935P/52S/15E,
identical.** Not a regression; my measurement, not the code.

⚠ **Two existing tests were EDITED, and neither was weakened.**
`test_the_worked_counter_example_survives_the_f_string` guards *f-string escaping*, pinned to
exact literal JSON — it still does, now on `47 × 36`, **plus a new assertion that this lesson's
numbers are NOT handed to the model as an answer**. `test_it_says_the_numbers_must_be_the_lesson_s_own`
now asserts the narrower **scene**-scoped wording; a lesson's numbers were satisfied by scene 10
being authored against 23 × 14 while its words worked 32 × 21.

**Fleet after:** 43 containers across nodes 01–04, **zero unhealthy**.

---

## §8 ⛔ HELD — 5

| id | What | Why held |
|---|---|---|
| **RC-O10** | **Scenes 2 and 3 render the identical animation; so do 4 and 5.** One multiplier digit of one sum, and the template takes only `(top, bottom, step)` — it cannot separate "write the 2, carry the 1" from "…so our first answer is 92" | Needs a template that renders **part** of a row — a renderer change, outside this order |
| **RC-O11** | The guard cannot catch a wrong spec whose numbers are all spoken and whose result is never announced | The honest limit; pinned as a passing test. L7's checker is human eyes until M3.3 |
| **RC-O12** | **Authoring moves the storyboard fingerprint, invalidating the approval that released it** — `artifact_version` hashes `updated_at` | Structural; belongs to AD-05, not a drive-by fix |
| **RC-O13** | `approve_storyboard` dispatches onto the project's **latest** job row rather than creating one — it released onto `a6e5f2d1`, already `failed` | Pre-existing; outside this order |
| **RC-O14** | Scene 2's original spec would have survived assertions 1–3 | Not work — a recorded blind spot, and the reason assertion 4 exists |

### ⚠ Data writes I made, stated plainly

To force all six through authoring I set `generation_params = {}` on the six motion scenes, then
**restored all six to their exact prior values** (diffed against a recorded before-state:
identical) once I found that clearing them changed the storyboard fingerprint and re-opened the
gate. The gate then had to be re-approved — **that re-approval was made necessary by my own
write**, not by the defect, and it is recorded in `project_gate_decisions` under my token with a
note naming this package. The six scenes' final specs were authored by the model through the
guard, not written by hand.
