# WP-65-WEIGHTS — a certified model's bytes reach a node, and the store stops guessing about it

Read `WP-65-68-RUN-ORDER.md` first. It governs this package.

## CONTEXT

Repo `/opt/ivgs`. Read `dev/CLAUDE.md`, then
`dev/workpackages/reference/TEST-BASELINE_*` at its current revision — authority
for every count; update any row your fixes move in the same commit as the fix.
Read `docs/IVGS_v5_Addendum_AD-01*` (the Model Store addendum) and the WP-53
report (the AD-01 ingest work).

Tag: **`v5.24.0-weights`**. Migrations continue from 0038.

## THE FINDING THIS PACKAGE CLOSES (measured 2026-08-26 in the tree)

MBCP certifies a model and exports it to IVGS. IVGS **records** it and never
**fetches** it:

- `ivgs-api/app/api/ad01_ingest.py:75-80` — `POST /ad01/v1/certified-models`
  ingests the bundle as a CANDIDATE with an attestation, storing a weight
  reference and checksum. Idempotent, replay-safe, working.
- **Nothing consumes that reference.** `grep -rn "weight_fetch\|fetch_weights\|
  weight_ref"` across `ivgs-api/`, `ivgs-workers/` and `shared/` returns
  **nothing** outside the ingest schema itself. No download, no checksum
  verification, no placement, no availability record.
- The consequence is visible in the operator's own Model Store: for
  `animation_generation`, AnimateDiff-SD15 and MimicMotion show **NODES: none,
  VRAM: —, state candidate**, while Wan2.2-Animate 14B — placed by hand months
  ago — shows **34.1 GB, 1 available, approved, default**. The store is telling
  the truth: those models are catalogued and their bytes have never landed.

A second, smaller finding sits beside it: **the same model carries two different
engine names in the two systems.** MBCP lists AnimateDiff-SD15 with engine
`comfyui` (all six animation candidates and all twelve supporting components are
`comfyui` in MBCP). The IVGS Model Store shows it as `animatediff`. Engine name
drives endpoint resolution — `shared/providers/binding.py:21` maps
`comfyui -> IVGS_COMFYUI_URL` and `animatediff -> IVGS_ANIMATEDIFF_URL`, both
defaulting to `http://node-04:8188` today, so the disagreement is currently
harmless and will not stay harmless the moment those endpoints differ.

## TASK 1 — what "available" means today, measured before anything is built

The Model Store's NODES and VRAM columns are the surface this package must make
true. Establish, with file:line evidence:

- what computes `nodes_available` and the VRAM figure on the model-store read
  path (API service, and what the frontend renders);
- whether it reflects **bytes present on a node**, a **static registry row**, or
  a **capability declaration** — and whether anything verifies it;
- how Wan2.2-Animate 14B came to show `34.1 GB / 1 available` when no fetch code
  exists (hand placement plus a recorded row is the hypothesis — prove or
  disprove it);
- what a worker actually does at dispatch when a bound model's weights are
  **absent** from the node it lands on: the failure's shape, where it surfaces,
  and whether it is distinguishable from any other engine error.

This is §1 of your report and the baseline for Task 4's acceptance. If any of
these turn out to be declared-but-inert — the pattern found in every package
since WP-57 — say so plainly; that is a finding, not a blocker.

## TASK 2 — the weight fetch service

Build the missing link: given a Model Store row carrying a weight reference and
checksum, fetch the bytes to a target node's model directory, verify, and record
availability.

- **Fetch** from the MBCP weight endpoint named in the ingest bundle. Resumable
  where the transport allows; a partial file is never left where a loader could
  find it (fetch to a temp name, verify, then move into place — the WP-63
  supersede discipline applied to bytes).
- **Verify** the checksum recorded at ingest, always, before the move. A
  checksum mismatch is a hard failure with a named error, never a warning.
  Record the verification result.
- **Place** by engine convention: establish where each engine expects its models
  (`comfyui` under its models dir by type — checkpoints, loras, vae, and so on;
  vLLM under its HF cache) and honor it. Placement rules are data, not
  hardcoded paths scattered through the fetch code.
- **Record** availability so Task 1's surface becomes true: which model, which
  node, bytes on disk, checksum verified, fetched when, by whom. New table or
  new columns — argue the choice in the report; migration with an exercised
  downgrade.
- **Idempotent**: a second fetch of a model already present and verified is a
  no-op that says so, not a re-download.

**The live pass is HELD.** A real fetch needs the MBCP serving token and signing
key, which the operator has not handed over (their standing pending-register
item). Build against fixtures and a local fake endpoint, test thoroughly, and
author the operator block that performs the first real fetch — including how the
credentials are supplied (an env var on node-01, never printed, never committed).
Report the block as staged, not run.

## TASK 3 — placement policy: which node gets which model

A fetch needs a destination, and the fleet is specialized (AD-02):

- node-02, node-03, node-04 are the GPU workers (node-03's worker service is
  `cogvideox-worker`);
- node-05 serves Qwen and is out of bounds;
- node-06 is the sole CLIP scorer and is out of bounds.

Establish from AD-02 and the live compose files which node hosts which engine,
and make placement follow it rather than guessing. A model whose engine has no
host on the fleet **cannot be fetched** — the attempt refuses with a named
reason ("no node hosts engine X"), which is exactly the state AnimateDiff and
MimicMotion are in until WP-67 and WP-68 change it. That refusal is a correct
outcome and must be tested as one.

## TASK 4 — the Model Store surface tells the truth about availability

With Task 2's record existing, make the NODES and VRAM columns mean it:

- a model with verified bytes on a node shows that node and the real on-disk
  size;
- a model with no bytes anywhere shows the absence **in words** — the WP-57/60
  rule applies here as everywhere: no fabricated zero, no implied capability;
- a model whose engine has no host says that, distinctly from "certified but not
  fetched" — they are different states and an admin needs to tell them apart;
- the admin page gains a **Fetch weights** action per model (GUI-only, admin
  auth, no CLI), which dispatches Task 2's service and reports progress and
  outcome honestly, including the refusal cases above.

Zero CLI for admin functionality stands (the standing IVGS rule). If the fetch
is long-running, the action reports queued/running/failed states truthfully
rather than blocking the page.

## TASK 5 — engine-name reconciliation (sanctioned live-data change)

MBCP says `comfyui`; the IVGS store says `animatediff` for the same model.

- Establish which side is authoritative. The ingest bundle carries MBCP's value,
  so the likely answer is that IVGS is transforming or overriding it somewhere —
  find that code path and report file:line.
- Fix the mapping so an ingested model's engine in IVGS is the engine MBCP
  certified it against, and add a test pinning it.
- **Correct the existing rows** for the affected models (this is the one Model
  Store write this package sanctions). Record the before/after per row in the
  report. Do not touch lifecycle state, flags, or any other column.
- If reconciliation would change which endpoint a currently-working model
  resolves to, **STOP** and report instead — Wan2.2-Animate 14B is live and
  serving, and this package does not risk it for a naming tidy-up.

## TASK 6 — storyboard prompt v5: the two defects the v4 run exposed

The operator's first v4 storyboard (13 scenes, 2026-08-26) was a clear
improvement — descriptions now depict the actual step, and three scenes were
deliberately chosen as `video_clip`. Two defects showed:

- **Duplicate descriptions.** Scenes 0/11, 5/9 and 6/10 carry byte-identical
  `visual_description` text. A viewer sees the same frame three times, and
  content-hash dedup will collapse them into shared bytes, so the repetition is
  invisible in the asset count. v5 must require each scene's visual to be
  distinguishable from every other scene's in the same storyboard — and the
  deterministic checker gains an assertion that no two scenes share a
  description.
- **RULE 1 applied inconsistently.** Scenes 3, 5 and 9 describe structure only
  ("the first partial-product row already written above a ruled horizontal
  line") — correct. Scenes 1, 2, 4, 7 and 8 name digits ("23 on top and 14
  underneath"), which asks the image model to render numerals — the failure mode
  this repo has now measured three times, including in WP-63's own rescore.
  Tighten v5 so structure-not-symbols is unambiguous, and extend the checker to
  fail a description containing multi-digit numerals.

Publish v5 through the prompts-table path (v4 preserved inactive) — **you run the
publish**, per the WP-64 D-1 precedent. Report the publisher output verbatim.

**The operator's in-flight project is unaffected**: its scenes were generated
under v4 and are stored rows; publishing v5 changes only what the *next*
storyboard run produces. Do not regenerate it, do not touch it.

## ACCEPTANCE

- Task 1's measurement table, complete, with file:line.
- Task 2's service proven against fixtures: a successful fetch-verify-place-
  record cycle; a checksum mismatch refused with the temp file cleaned up; a
  second fetch that no-ops; the operator block for the live pass authored and
  staged.
- Task 3's refusal ("no node hosts engine X") tested as a first-class outcome.
- Task 4's surface rendered against live data, showing at least one truly
  available model and one honestly-absent one.
- Task 5's rows corrected with a before/after table, or the STOP recorded.
- Task 6's v5 published, checker extended, both new assertions red-green.

## RULES

Commit and HOLD — never push. Deploy `v5.24.0-weights` to **node-01 only**, via
the artifact path with the standard filename. Nodes 02/03/04 are operator paste
blocks; node-03's service is `cogvideox-worker`. NODE-05 and NODE-06 out of
bounds. Live data limited to: the v5 prompt publish, the Task 5 engine-name row
corrections, and test projects you create and may delete via the WP-59 flow.
**The operator's project `another new multiplication test run` is untouchable.**
You press no gates. Frozen stage bodies untouched — STOP-and-ledger instead.
Full Python suite at most twice. ZERO NEW FAILURES against the baseline, updated
in the same commit as any fix that moves a row. No secrets in the report or chat
— the MBCP credentials appear as a named env var, never a value. Report to
`dev/workpackages/reports/WP-65-WEIGHTS-report_<date>.md` with a count-gated push
block for this package's commits.
