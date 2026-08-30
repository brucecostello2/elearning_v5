# WP-IVGS-12i3 — stage-complete means approvable: three exits, one invariant, and what the invariant found

**Session:** 2026-08-30 (third watch). **Order:** RULING + ORDER — RC-T, with the
binding amendment of the same day.
**Ledger:** `OUTSTANDING_WORK.md` §12i-watch3.
**Evidence:** `dev/workpackages/reference/wpivgs12i3-evidence/`.
**Live project READ, never written by hand:** `680d9e4c-608b-488a-9270-9b4317a7f693`.
**Acceptance fixture:** `43c59a2a-917a-4df0-9368-ce5752f1651d`, deleted via WP-59
at the end of this session.

---

## STATE AT SESSION END

**Done.** RC-T1 (all three exits), RC-T2 (the invariant, including the coverage
non-regression check), RC-T3 (the lexicon, measured and cited). Two new rows
opened by the acceptance itself: RC-T4 and RC-T5.

**Mid-way through: nothing.**

**How the order is now stale.**

1. The order presents the exits as an ordered set of attempts. ⛔ **They are
   CONDITIONS, and reading them as attempts produces the exact defect the
   amendment forbids** — see §1.1. The implementation was corrected mid-session.
2. **The acceptance's "the gate must show mechanical refusals ZERO" was met on
   one generation of four**, and the other three failed the stage for three
   different legitimate reasons. That is the invariant working, not failing, but
   it is not the unqualified pass the order anticipated. See §5.

**Learned and not written down anywhere else.** The residue after three exits is
dominated by a single shape: **the authoring model picks a template whose
trigger vocabulary its own narration does not use.** RC-T3 fixed one instance of
it from the Foundation's own words. RC-T4 is the next instance, measured and
deliberately NOT patched, because patching a lexicon because one generation
tripped on it is the tuning the order forbids.

---

## 1. RC-T1 — the three exits

### 1.1 ⛔ The ruled order is a set of GUARDS, and my first cut read it as a sequence

I implemented (a)-then-(c)-on-failure. On the operator's own opener —

> "Hi! Today, we're going to learn how to multiply two-digit numbers. That might
> sound tricky, but don't worry. By the end, you'll be able to solve a problem
> like 23 times 14 all by yourself."

— **exit (a) SUCCEEDS.** The words carry "multiply", 23 and 14, so a
`column_multiplication_step` is authored and WP-IVGS-09f's guard passes it. The
result is a warm welcome to an anxious nine-year-old rendered as an animated
column sum, produced by a repair pass reporting success.

The ruling says (a) applies *"where the template fits the whole narration"*. A
narration mixing a welcome with an operand does not meet that. **A mixed
narration now goes straight to (c)**, and the test that pins it uses an
authoring stub that deliberately succeeds — so a future refactor making (c) a
fallback again fails it.

### 1.2 Exit (b), narrowed to incidental demands

One bounded call: `response_format` + `json_schema` + `strict: true`, one key
out. ⛳ RC-Q1 is why: on this fleet `guided_json` is accepted with HTTP 200 and
silently ignored, along with every unknown body member. `_call_model` gained an
opt-in `response_format` passthrough, omitted by default so every existing
caller's body is byte-for-byte unchanged.

⛔ **The post-check is what makes one call safe.** The result goes back through
*the very extractor that produced the refusal* — `names_a_numeral` and
`demands_on_screen_text` — and one surviving demand discards it. The model is
never trusted to have complied; compliance is measured. **No retry.**

⛳ **And legality is decided from the contract before any model is called.**
`instructional_event ∈ {present, guide, practice, assess}` over narration
stating written or numeric content ⇒ forbidden, citing Foundation §4: on-screen
text is *"for labels, symbols, and the worked math itself — which narration
cannot carry"*. A `media_rationale` saying the learner must SEE it forbids it
too: if the designer wrote it down, it is not incidental.

Proven live: *"A teacher beside a whiteboard showing the multiplication problem
23 x 14."* → *"A teacher beside a whiteboard with a two-row layout, the top row
having two placeholders and the bottom row having one placeholder, all still
empty."* The narration is untouched; the learner still hears 23 × 14.

### 1.3 Exit (c), the split

Sentences cut at boundaries by code, sorted by the same `referents` extractor the
refusal used; the digit half authored by exit (a)'s primitive; the context half
keeps the parent's medium. **No new judgment, no new model call beyond the one
authoring ask.**

- **Spans reunite by construction** — both children carry the parent's
  `source_refs` — which is *why* a split cannot lower coverage. RC-T2 verifies it
  rather than trusting it.
- **Durations split by narration length** and sum to the parent's.
- ⛔ **`assess` lands on ONE child only**; the context half becomes `guide`
  (Foundation §3 event 5). RC-S1's per-outcome invariant survives a split rather
  than being re-broken from inside the repair.

**Two interactions that would have undone the split silently, both closed:**

1. ⛔ **RC-S1's own prune would have eaten the child.** `prune_scenes_not_in_design`
   deletes every row the active contract does not contain. The split therefore
   writes the child into `scene_designs` and shifts every later index — a repair
   that worked once and then quietly reverted would have been the worst possible
   outcome. Pinned by a test that runs the prune immediately after a split.
2. ⛔ **Migration 0048's provenance XOR refused my first cut**, which marked every
   child `designed` while copying the parent's spans. **The constraint was right
   and the code was wrong**: a split MOVES sentences, it does not write them, so
   calling the child `designed` would claim this pass invented words it only
   relocated — and would drop the spans, which is the fidelity loss RC-T2
   exists to forbid. The child now inherits the parent's provenance exactly.

### 1.4 ⛔ And the split does not finish by itself — found by the acceptance

A split moves the digits out of the NARRATION and leaves the DESCRIPTION as it
was. Scene 6 narrated *"Do not worry, this is easier than it looks. Now multiply
4 times 3…"* under *"A worksheet showing the multiplication problem and the
calculations."* After a perfectly good split the parent went on refusing and
**the stage failed over a scene the pass had just repaired.**

The context parent is now re-examined **once**. That is not a loop: its narration
changed, and the legality test now reads a context-only narration — exactly the
case where a leftover text demand is incidental. One further exit-(b) call at
most, never the same call twice.

---

## 2. RC-T2 — the invariant

After the pass, mechanical refusals must be ZERO. A scene surviving all three
exits **fails the stage**: `update_job_status(job_id, "failed", …)` with every
surviving scene named and every exit's own refusal sentence quoted, including
why exit (b) was forbidden.

⛳ **The rows are left where they are, deliberately.** The operator's remedy is
to regenerate OR to edit, and deleting the storyboard would remove the second.
What changes is the JOB — so the Jobs tab and the gate agree, instead of a green
job sitting beside a gate full of red.

⛳ **Fidelity is part of the same invariant.** Coverage is measured before and
after, over the same script and the same merge the gate uses
(`design_review.covered_character_count`, shared so the two cannot disagree), and
**a drop is itself a stage failure**. Measured across the acceptance runs:
**40→40, 120→120, 170→170 — never lowered.**

⚠ **A defect of my own, caught by the acceptance and fixed.** The failure message
first derived survivors from "corrections that did not apply", so a scene that
still refused but was never a correction's subject was **counted and not named**:
the live message read *"1 scene(s) survived"* above an empty list. A message that
states a count it cannot name is worse than no message. Survivors now come from
the re-validation, so the count and the names are one fact.

---

## 3. RC-T3 — the lexicon, measured against the Foundation

Scenes 9/10: *"Can you identify the unit numbers and 10's in the number 45?"* —
a place-value question in the operator's own words, refused because the guard
wanted the token "place" beside the place's name.

**The Foundation names them itself**, §3, the Gagné event-3 row:

> | 3 | Stimulate recall of prior learning | `recall_prior` | ones/tens place value; single-digit facts |

So `ones`, `tens` and `unit` are added, and a test reads the Foundation file to
check the citation still says it.

⛔ **Refused, with reasons:** `digit`/`digits` and `number`/`numbers` (a necessary
condition everything satisfies is not a check); any script literal
(script-specific by definition); `hundreds`/`thousands` (defensible but
unmeasured — widen when a run produces one).

⚠ **The honest cost.** This is a NECESSARY condition, so widening weakens it:
*"now multiply by the tens digit"* now also satisfies `place_value_split`. That
is a real loss, accepted because the alternative is refusing a scene for using
the Foundation's own words. The producibility limb is untouched.

### The three residue scenes, re-run

| scene | before | after |
|---|---|---|
| 1 (`objective`, *"Today we will learn how to multiply two double-digit numbers"*) | (a) refused: `place_value_split` needs place-value words | **still refused by (a) — correctly, it has no place-value content — and takes exit (b)** |
| 9 (`present`) | (a) refused, same reason | **authors under (a); came back `motion_graphics` on the next generation** |
| 10 (`practice`) | (a) refused, same reason | **authors under (a); came back `motion_graphics`** |

That split — two rescued, one correctly still refused — is what "widen where
Foundation-general, refuse where script-specific" looks like when it is right.

---

## 4. RC-T4, new — the same gap in the multiplication lexicon, NOT tuned

Acceptance run C failed on scene 4: *"For example, 3 x 4 means 3 groups of 4."*
`_MULT_WORDS` is `(multiply, multiplying, times, digit, placeholder, zero)`; the
narration says **"x"** and **"groups of"** — the multiplication symbol and the
standard primary-school phrase, both Foundation-general. Exit (b) was correctly
forbidden (a `present` scene over digit narration); exit (c) did not apply (no
context sentence); the scene survived and the stage failed.

⛔ **Not widened here, on purpose.** `"groups of"` would be a safe substring, but
adding vocabulary *because one generation tripped on it* is exactly the tuning
RC-T3 forbids. And `x`/`×` cannot be added at all under the current
**plain-substring matcher** — `w in words` would fire on "example", "next",
"six" — so carrying the symbol requires making the matcher word-bounded, which
changes every template's behaviour and deserves its own measurement.

**Rowed with the measurement, for an operator ruling.**

---

## 5. The acceptance, stated as it happened

Four generations through the full pipeline with the three exits deployed:

| run | scenes | refusals | mechanical after | coverage | outcome |
|---|---|---|---|---|---|
| A (18:02) | 13 | 4 → 0 | **0** | 40 → 40 | ✅ **approvable — gate opened normally** |
| B (18:16) | 14 | 3 → 1 | 1 | 170 → 170 | ⛔ stage failed: `MOTION_CONTRADICTS_NARRATION`, re-authoring invented `bottom=42` for a spec that had invented `bottom=280` |
| C | 17 | 4 → 1 | 1 | 80 → 80 | ⛔ stage failed: RC-T4's multiplication lexicon; exit (b) correctly forbidden |
| D | 12 | 3 → 2 | 2 | 120 → 120 | ⛔ stage failed, two survivors |

Plus, on run A's storyboard, the two exits the order asked to see exercised
directly through `POST /scenes/auto-repair`:

- **Exit (c) twice** — the intro-with-digits shape (context: *"Hi!"*, *"Today, we
  are going to learn…"*, *"That might sound tricky…"*; digits: *"By the end,
  you'll be able to solve a problem like 23 times 14 all by yourself."*) and a
  mixed `guide` scene (context: *"Do not worry, this is easier than it looks."*;
  digits: *"Now multiply 4 times 3."*, *"4 times 3 equals 12, so write the 2
  underneath and carry the 1."*). Scene count 13 → 15; **coverage 40 → 40**.
- **Exit (b) once**, on the intro's description.
- Then, with the parent-repair fix deployed, the same storyboard reached
  **refusals 1 → 0, `mechanical_after` 0, `stage_failure` NONE.**

### The gate payload, described

`GET /design-review` on the final storyboard returns: **1 design refusal**
(`UNDECLARED_SPAN_OVER_THRESHOLD` — RC-S2's fidelity rule, 120 of 3,138
characters used) and **3 judgment flags** (`SAME_OUTCOME_NEAR_DUPLICATE` ×1,
`PRACTICE_NOT_PREPARED` ×2), with the **System corrections** block carrying
`repaired: 1`, `pruned: 5` (RC-S1 still reconciling), `coverage 120 → 120`,
`mechanical_after: 2` and the **stage-failure text rendered in full at the top of
the panel in red**. Equation lint: no false claims — this design, like both live
ones, states no complete arithmetic claim at all.

⛔ **So the order's "mechanical refusals ZERO" was met on one run of four**, and
I am stating that rather than rounding it up. §12i-watch3 RC-T5 rows why: the
residue is dominated by the authoring model choosing a template whose trigger
vocabulary its own narration does not use, and nothing about that got worse
today — before this package those same storyboards reached the gate as **green
jobs carrying red refusals.** The stage now says so.

---

## 6. Tests

| suite | result |
|---|---|
| `test_wpivgs12i3_rct_exits.py` (new, 24 tests) | **24 passed** |
| `ivgs-api/tests` full, after every change in this package | **1855 passed, 0 failed** (`api-tests-final.txt`) |
| `ivgs-frontend` `tsc --noEmit` | clean, exit 0 |

---

## 7. Deploy — node-01, §6.1a

| container | image |
|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.41.3-rct-parent-repair` (`sha256:6ccd327cfcd2…`) |
| `ivgs-nextjs` | `ivgs-frontend:v5.41.0-rct-exits` (`sha256:346dfebc5746…`) |
| `ivgs-celery-default` / `-composition` / `-beat` | `ivgs-workers:v5.41.0-rct-exits` (`sha256:430450667cf2…`) |

⛔ **THE DEPLOYED API IMAGE PREDATES THIS SESSION'S LAST THREE EDITS, AND THEY
ARE DOCSTRINGS ONLY — MEASURED, NOT ASSERTED.** The close-out banners
(`storyboard_service.py`, `design_review.py`, `storyboard_completeness.py`) were
written after `v5.41.3` was built. I did not rebuild for comment-only text, and
I did not want that to rest on my word: each file was parsed out of the running
container and out of the tree, docstrings stripped, and the ASTs compared —
**identical in all three.** The fleet is running the tree's code. The next deploy
picks up the prose.

⛳ **The workers moved this time and the reason is RC-T2**: `handle_stage_completion`
now fails the job on a non-approvable stage. stderr never redirected;
`verify-deployed-image.sh` green on all five; running `.Image` compared against
each banked artifact digest (RC-Q8); `docker ps` healthy (RC-P19). Intermediate
API tags `v5.41.0`/`.1`/`.2` are each banked with digests and superseded within
the session. **No migration.**

---

## 8. The tree

**Two commits for this package; ONE is held.**

| commit | state |
|---|---|
| `9ec1bb2` `feat(wp-ivgs-12i3)` — the three exits and the invariant | ✅ **already on `origin/main`** — the operator pushed it while this close-out was being written |
| `d22d0e3` `docs(wp-ivgs-12i3)` — this close-out | ⛔ **HELD.** Nothing pushed by me |

WP-IVGS-12i's `ed72440` and 12i2's `e40f4dc` were pushed by the operator between
watches. **The count-gate below is therefore 1**, and it is the close-out commit.
⚠ Re-check it before running the block: the operator has pushed mid-session
twice today, and a gate written against a moving `origin/main` is exactly the
kind of stale instruction §0 rule 5.3 exists to stop.

⛔ **`ivgs-infra/.env` is DIRTY and is NOT mine to stage** — the three tag lines
moved with the deploy. Untracked and gitignored (§3).

✅ **The acceptance fixture `43c59a2a` was DELETED through the WP-59 flow**, as
ordered, after its evidence was banked.

**Nothing was written to the operator's live project by hand.** Its rows were
last written at 15:42:37 by the operator's own regeneration.

⛔ **A FILE APPEARED THAT IS NOT MINE, AND IT IS LEFT UNTRACKED AND UNSTAGED**
(§0 rule 5.5, "never stage another agent's files"). It was swept in by a
directory-wide `git add` during the close-out and removed again with
`git restore --staged`:

    dev/workpackages/Design_Note_WP-IVGS-12j_Interview_and_Vocabulary_2026-08-30.md
    root:root, 8,425 bytes, written 19:32 — mid-session, by the operator

⛳ **It is worth reading before the next package starts, because it already
consumes this session's output.** It states the law twelve packages have proved
— *"what the grammar or code demands, the model delivers every time; what the
prompt merely requests, it eventually declines"* — and cites **RC-T5's number,
"one approvable generation in four"**, as the residue that motivates contract-8:
the free-text fields become selections from closed vocabularies, the parameters
the model invents become user inputs, and the judgment calls discovered at the
gate become questions asked before design. It says the validator suite is not
discarded but **demotes to regression belts** — which is the right reading of
everything in §12i-watch, §12i-watch2 and §12i-watch3.

⚠ **It is the operator's file and this package neither edits it nor acts on
it.** RC-T4 (the multiplication lexicon, rowed unpatched) is squarely inside its
scope, and a closed vocabulary would remove the whole class rather than widen a
trigger list a third time.

---

## 9. Session close-out (dev/CLAUDE.md §0 rule 5)

**Closing act for all three packages of this session — 12i, 12i2 and 12i3.**

**1. Evidence out of scratch.** Three albums committed:
`wpivgs12i-evidence/` (14 files), `wpivgs12i2-evidence/` (15),
`wpivgs12i3-evidence/` (13). Every number in all three reports traces to one of
them.

⚠ **Declared lost by name**, and none of it load-bearing: `t3.txt` (a pytest
transcript, superseded by the banked suite results), `proj2.json`,
`testpid.txt`/`testpid2.txt`, `orig_narration.txt` (session bookkeeping),
`vtest.py` (a throwaway probe used once to find the motion guard's parameter
shape, its answer quoted in the 12i report), `rct-stage-failed-real-run.json` (a
mis-named duplicate of a banked file), and `operator_script.md`/`.txt` (the
operator's upload, already banked at
`wpivgs12h-evidence/operator-script-f65f340c.txt` and still in the live
database). ⛔ **`token.txt` and `mint.py` are deliberately NOT banked**: one is a
live JWT and the other mints them from the users table. Neither belongs in git.

**2. Indexed** in `dev/DEVELOPMENT-STATUS.md` under `## Reports filed this
session`, all three reports with one-line verdicts, and the session narrative
above the table corrected — it described only the four earlier packages and
would have read as the whole session.

**3. Superseded text bannered, not edited around.** Three statements this
session made false:

| file | what it said | why it is now wrong |
|---|---|---|
| `storyboard_service.py` `create_scene` | *"Trimming needs the whole-storyboard write that Stage 2 does not make; ledgered for the Temporal cutover"* | RC-S1 built it. It did not need Temporal; it needed the design of record, which arrived with the Design Core. A reader would have concluded the surplus is unhandled until M3.3 |
| `design_review._evidence_is_distinct` | *"The practice is NOT compared against the worked examples here … a named residue in the report rather than a check smuggled in under this one"* | Still exactly true of that function, and RC-S3 closed the residue ELSEWHERE at flag level. Without the banner a reader concludes nothing compares them anywhere |
| `storyboard_completeness` module header | *"There is no prompt loop here and no re-authoring … Nothing in between"* | Still true of that module and no longer the whole story: a separate pass now repairs its refusals before the gate, and a surviving refusal fails the stage |

⛳ Also superseded, in the previous package and recorded there: the two
`test_wpivgs12b_outcomes.py` tests that pinned the fidelity loophole — one now
asserts the inverse of what it asserted, with the change of sense written into
the class docstring.

**4. `STATE AT SESSION END`** is at the top of each of the three reports.

**5. The tree** is declared in §8 above and in the closing message.

---

## 10. Push block — the operator's

```bash
# node-01
cd /opt/ivgs
test "$(git rev-list --count origin/main..HEAD)" = "1" || { echo "REFUSED: expected 1 held commit, found $(git rev-list --count origin/main..HEAD)"; exit 1; }
git log --oneline origin/main..HEAD
git push origin main
```
