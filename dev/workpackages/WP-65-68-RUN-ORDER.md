# WP-65 to WP-68 — RUN ORDER (unattended)

You are working four packages back to back with **no operator present**. Read
this file first, in full, then work the four briefs in the order below. They sit
beside this file in `dev/workpackages/`.

1. `WP-65-WEIGHTS-brief.md`
2. `WP-66-SELECTION-brief.md`
3. `WP-67-CLIENTS-brief.md`
4. `WP-68-MOTION-brief.md`

The order is **binding**. WP-66 consumes what WP-65 establishes; WP-67 and WP-68
consume both. Do not reorder, do not interleave, do not start a package before
the previous one's report is written and its commits are held.

---

## THE ONE RULE THAT GOVERNS UNATTENDED WORK

**Every decision that is not already ruled in a brief is a STOP-and-report, never
a guess.** The operator is not available to rule mid-flight. A task that cannot
proceed on the facts as measured stops, records what it measured with file:line
evidence, states what ruling it needs, and the package moves to its next task.
An unruled guess that reaches live data is the one outcome worse than an
unfinished package.

This is the same discipline WP-56 Task 3, WP-61 Task 3(a) and WP-64 Task 4 used.
It has been right every time. Use it freely — a package that stops three tasks
and reports honestly is a **success**, not a failure.

## WHAT STOPS A TASK vs WHAT STOPS THE WHOLE RUN

**Stop the task, record it, continue the package:**
- a brief's premise is measured false (this has happened in every package this
  month — expect it)
- the work requires a ruling the briefs do not contain
- the work requires credentials, a container, or a node action you do not have
- the work requires editing a frozen stage body (AD-05 §8)

**Stop the whole run, write what you have, and go no further:**
- a node-01 deploy fails and cannot be rolled back to the previous tag
- the test baseline goes backwards (any new failure you cannot fix)
- a migration cannot be downgraded cleanly
- the live database is in a state you did not intend
- you find yourself about to write to a project row that is not sanctioned below

## LIVE DATA — the complete allowed list

Nothing else. If a task seems to need more, that task stops.

- **Prompt publishes** named in a brief (WP-65 Task 6). You run these; the WP-64
  D-1 precedent settled that publishes are versioned, reversible data and are
  the agent's to run when the RULES sanction them.
- **Test projects you create yourself**, which you may delete through the WP-59
  flow when done.
- **Model Store rows** as WP-65 Task 5 specifies (engine-name reconciliation),
  and only those rows.

**PROJECT `another new multiplication test run` IS UNTOUCHABLE.** It is the
operator's live test project, storyboard generated under v4 and **not yet
approved**. Do not read-modify it, do not trigger it, do not approve it, do not
delete it. Its scenes are evidence.

Every other existing project is untouchable: `c12fa967` (reference baseline),
`52d52867`, the five `e2e-photosynthesis-*`, `another multiplication pass e2e`.

**YOU PRESS NO GATES.** WP-63 D-2 stands permanently: the human half of a review
gate is the operator's. If a package's acceptance needs a gate press, the
acceptance is staged as an operator block and reported as staged, not run.

## DEPLOY AND PUSH

- **Commit and HOLD. Never push.** Each package's report ends with a count-gated
  push block covering that package's commits. The operator pushes all four when
  they return. Do not push between packages.
- **Deploy to node-01 ONLY**, via the artifact path with the standard filename
  (`scripts/save-image-artifact.sh`, `brucecostello2_<image>_<tag>.tar.zst`).
  GHCR is off the deploy path.
- **Nodes 02/03/04 get OPERATOR PASTE BLOCKS ONLY** — author them, never run
  them. node-03's worker service is `cogvideox-worker`, NOT `celery-worker`
  (WP-44 §6.3). node-01 runs a worker too, so node-01 deployment is sufficient
  to test worker-side changes.
- **NODE-05 and NODE-06 are out of bounds** except reading telemetry and calling
  their existing endpoints (node-05 serves Qwen; node-06 is the sole CLIP
  scorer).

## VERSION TAGS AND MIGRATIONS

One coherent version per package across the images it touches:

| Package | Tag |
|---|---|
| WP-65 | `v5.24.0-weights` |
| WP-66 | `v5.25.0-selection` |
| WP-67 | `v5.26.0-clients` |
| WP-68 | `v5.27.0-motion` |

Migrations continue from **0038** (the last applied). Take the next free number
in sequence as you need one; **do not reserve numbers you do not use**, and do
not leave a gap. Exercise every downgrade before committing it.

## TESTS AND THE BASELINE

- The baseline is `dev/workpackages/reference/TEST-BASELINE_*` at its current
  revision. It is the authority for every count.
- Full Python suite **at most twice per package**. A timeout-killed run is an
  environment note, not a retry trigger.
- **ZERO NEW FAILURES**, per package, updated in the same commit as any fix that
  moves a row.
- Do not weaken an assertion, add a skip marker, or delete coverage to improve a
  count. Better discrimination, never looser gates.

## REPORTS

One per package, at `dev/workpackages/reports/WP-6N-<NAME>-report_<date>.md`,
each carrying: what was measured (with file:line), what was built, what stopped
and why, the acceptance evidence, the ledger additions, and a count-gated push
block for that package's commits.

**When all four are done**, write one additional file:
`dev/workpackages/reports/WP-65-68-RUN-SUMMARY.md` — a single page the operator
reads first, listing per package: tag deployed, commits held, tasks completed,
tasks stopped with the ruling each needs, operator blocks awaiting them, and the
combined push count.

## FLEET STATE AT HANDOVER (verified 2026-08-26)

- node-01 api/frontend/workers **v5.23.0-media**; nodes 02/03/04 workers
  **v5.23.0-media**. DB at migration **0038**.
- Repo pushed through **3686609** (WP-64). Working tree clean.
- Storyboard prompt **v4 active** = `22c0acf2-13e7-4c24-9867-c7f79ef61ecd`
  (v1–v3 preserved inactive). `scene_media_adaptation` **v1 active** =
  `fc97de3f-7dc3-42a0-a410-a0d5593b97d1`.
- node-05 serves Qwen, digest-pinned `sha256:3dbe092e…`. node-06 sole CLIP
  scorer. node-04's GPU capped at 450 W, boot-persistent.
- `IVGS_SERVICE_TOKEN` is rotated and live fleet-wide. **Never print it.**
- `docker exec` heredocs **REQUIRE `-i`** or they execute empty and exit 0.

## BUDGET AND PACE

Work steadily; correctness over completion. If you reach a point where finishing
a package well would require rushing another, **stop and report** — an
unfinished WP-68 with an honest ledger is worth more than four hurried packages.
The operator would rather read "Task 4 stopped: needs a ruling on X, here is
what I measured" than discover a guess in production.
