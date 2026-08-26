# WP-68-MOTION — teaching animations: numbers that move, carries that travel

Read `WP-65-68-RUN-ORDER.md` first. It governs this package. **Do not start
until WP-67's report is written and its commits are held.**

This is the only one of the four packages that adds **new capability** rather
than closing a gap in something already half-built. Scope it honestly: a partial
WP-68 with a working core and a clear ledger is the expected good outcome.

## CONTEXT

Repo `/opt/ivgs`. Read `dev/CLAUDE.md`, the current TEST-BASELINE, your WP-65/66/67
reports, `docs/IVGS_v5_Addendum_AD-01*` (engine rows), `docs/IVGS_v5_Addendum_AD-02*`
(node specialization), and AD-05 §8 (frozen stage bodies).

Tag: **`v5.27.0-motion`**. Migrations continue from wherever WP-67 left them.

## THE FINDING THIS PACKAGE ADDRESSES (measured 2026-08-26)

The operator's project asked, in its own description, for "fun animations", and
one of its stated learning outcomes is *"understand the difference between 10's
and unit numbers"* — a concept that is **inherently animated**: digits moving
between columns, a carry travelling, a number splitting into tens and units.

The system produced **zero animations across thirteen scenes**, and could not
have produced any:

- `animation_generation` is bound to Wan2.2-Animate, which is **pose
  reenactment** — it needs a person in the still and a reference clip
  (`animation_generation_task.py:481`, `:344-350`). WP-64's D-2 ruling therefore
  tied the animation criterion to "a transformation carried by a person in the
  frame", which is correct for the engine and **structurally excludes the
  mathematics**.
- `ivgs-workers/services/motion_graphics.py` exists but is a **Ken Burns / zoom-
  pan effect service** — `apply_ken_burns` (`:160`), `apply_zoom_pan` (`:303`) —
  and **nothing calls it**: zero hits across `ivgs-workers/tasks/`.
- `ivgs-workers/clients/remotion_client.py` exists. **No Remotion container runs
  on node-02, node-03 or node-04** (checked 2026-08-26).
- The frontend Media Type dropdown was advertising "Motion graphics via
  Remotion/AnimateDiff" — a pathway that does not exist. WP-64 corrected the
  copy.

So the capability the lesson wants has: an unused effects service, an unused
client, no host, no engine row, no templates, and no stage integration.

## TASK 1 — measure what already exists before building anything

Report, with file:line:

- **`remotion_client.py`**: what it can do, what it expects to talk to, whether
  it was ever complete, what its inputs and outputs are, and whether any test
  covers it;
- **`motion_graphics.py`**: the full surface, and the git history of when it was
  last called and by what — the Ken Burns work may be reusable even though the
  service is not what the name suggests;
- **`composition`** stage: how the overlay is rendered today. The storyboard
  prompt's RULE 1 keeps digits *out* of generated images and reserves "the upper
  right third of the sheet kept clear for the overlay", which means **the
  compositor is already the thing that draws numbers**. Establish what it can
  do: does it draw static text over video, and could it animate that text?
- whether an `animation` media type can route anywhere other than
  `animation_generation_task` today, and what the pipeline would do with a scene
  bound to an engine that has no host.

**This measurement may change the shape of the whole package.** If the
compositor can already animate overlays, the cheapest real teaching animation is
an *animated overlay over a still or slow video*, needing no new engine at all —
and that would be a far better first delivery than standing up Remotion. Report
the finding and take the cheaper path if it is genuinely available; say so
explicitly rather than building the expensive thing because this brief named it.

## TASK 2 — the engine, declared honestly (AD-01 row)

Whatever Task 1 concludes, motion graphics needs to be a **first-class engine**
in the Model Store rather than a special case:

- add the engine to `shared/providers/binding.py`'s endpoint map with its env
  var and no misleading default (an engine with no host must not silently
  resolve to node-04's ComfyUI, which is what `animatediff` does today);
- add the AD-01 engine row and whatever registry entry a motion-graphics
  "model" needs — note that a template-driven renderer has no weights, so
  **WP-65's availability model must be able to express "this engine needs no
  weights"** rather than reporting it as permanently unfetched. If it cannot,
  extend it here, or STOP and report the gap;
- WP-67's client registry gains the motion-graphics family and its capability
  contract: inputs are *structured scene data*, not a still.

## TASK 3 — the templates, which are the actual product

A motion-graphics engine is worthless without a small, correct library of
maths-teaching animations. Build them as **parameterised templates**, not
one-offs:

- **column-multiplication step**: a partial product being written digit by
  digit, with the carry travelling to the next column;
- **place-value split**: a two-digit number separating into tens and units and
  recombining — the exact concept the operator's second learning outcome names;
- **column-addition with carry**: two rows summing, the carry appearing above
  the next column;
- **highlight-and-hold**: an existing frame with one region emphasised as the
  narration refers to it.

Each takes parameters (the numbers, the step index, the timing) and renders
deterministically — the same inputs give the same frames, which matters for the
conformance baseline and for Temporal's determinism requirement later. Digits
here are **drawn by the renderer, not generated by an image model**: this is the
path that makes RULE 1 unnecessary rather than merely enforced.

Choose the rendering technology on Task 1's evidence. If the compositor route is
available, these are compositor templates. If Remotion is genuinely the answer,
they are Remotion compositions — and the container stand-up is an **operator
block, authored and held**, never run by you.

## TASK 4 — the storyboard learns to ask for them (prompt work)

With a real motion-graphics capability, the storyboard prompt's media criteria
change substantially. Publish the next storyboard version (v6, or whatever
number follows WP-65 Task 6's publish; previous version preserved inactive):

- a **fourth media type** — or an animation subtype, whichever the schema
  supports without a migration that outruns this package — for motion graphics,
  with criteria naming exactly what earns it: *a numeric or structural
  transformation that the viewer must see happen*;
- the WP-64 D-2 person-in-frame criterion **stays** for `animation_generation`,
  because Wan is still Wan. The two are different capabilities and the prompt
  must choose between them deliberately, not blur them;
- for a motion-graphics scene, the prompt emits the **template name and its
  parameters** as structured data, not prose — the renderer needs `{template:
  "place_value_split", number: 23}`, not "a number splitting into tens and
  units". Establish where that structure can live on `storyboard_scenes` without
  a schema fight; if it needs a column, take the next migration number;
- the deterministic checker gains assertions for the new type.

**Run the publish yourself** (WP-64 D-1 precedent). Do not regenerate any
existing project's storyboard.

## TASK 5 — end-to-end proof, as far as the fleet allows

On a test project you create and may delete:

- a storyboard generated under the new prompt that **chooses at least one
  motion-graphics scene** for a place-value or carry step, with template and
  parameters emitted as structured data;
- that scene rendering through the new path to a real asset, **if** Task 1's
  route needs no new container. If it needs Remotion and Remotion has no host,
  render the template through a local fixture harness instead, bank the output
  frames as evidence, and stage the live pass as an operator block;
- the asset flowing into composition and appearing in the draft — or, where the
  live path is blocked, the precise point at which it stops, named.

**You press no gates.** If reaching the draft needs a gate press, stage it.

## WHAT SUCCESS LOOKS LIKE HERE

This package is allowed to end with the engine declared, the templates built and
unit-proven, the prompt publishing them, and the live render staged behind an
operator block. That is a complete WP-68. What it must **not** end with is a
surface claiming motion graphics work when no frame has ever been rendered —
that is the exact defect the dropdown was committing before WP-64 corrected it,
and it is the one outcome that would make this package worse than not doing it.

## RULES

Commit and HOLD — never push. Deploy `v5.27.0-motion` to **node-01 only**, via
the artifact path with the standard filename. Nodes 02/03/04 are operator paste
blocks; node-03's service is `cogvideox-worker`. NODE-05 and NODE-06 out of
bounds. **Stand up no containers** — every engine deployment is an operator
block, authored and held. Live data limited to: the storyboard prompt publish,
and your own test projects, deletable via the WP-59 flow. **The operator's
project `another new multiplication test run` is untouchable**, as is every
other existing project. Frozen stage bodies untouched — STOP-and-ledger instead.
Full Python suite at most twice. ZERO NEW FAILURES against the baseline, updated
in the same commit as any fix that moves a row. No secrets in the report or
chat. Report to `dev/workpackages/reports/WP-68-MOTION-report_<date>.md` with a
count-gated push block for this package's commits — **and then write
`dev/workpackages/reports/WP-65-68-RUN-SUMMARY.md`** per the run-order file.
