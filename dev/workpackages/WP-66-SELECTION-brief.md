# WP-66-SELECTION — the user chooses the model, per project and per scene

Read `WP-65-68-RUN-ORDER.md` first. It governs this package. **Do not start
until WP-65's report is written and its commits are held.**

## CONTEXT

Repo `/opt/ivgs`. Read `dev/CLAUDE.md`, then the current TEST-BASELINE —
authority for every count. Read `docs/IVGS_v5_Addendum_AD-01*` §5.2 (the
selection model), your own WP-65 report (availability is its output and this
package's input), and the WP-62 gate work.

Tag: **`v5.25.0-selection`**. Migrations continue from wherever WP-65 left them.

## THE FINDING THIS PACKAGE CLOSES (measured 2026-08-26 in the tree)

The selection mechanism is **built, scene-aware, and unreachable**:

- `shared/models/model_store.py:350` — `ProjectModelSelection` carries
  `project_id`, a **nullable `scene_id`** (`:365-369`), `stage`, `tier`,
  `model_id`, `selected_by`, and a mandatory `rationale`. Per-scene binding was
  designed in from the start.
- `shared/providers/factory.py:118-148` — dispatch **reads it correctly**:
  scene-scoped selection first, project-scoped as fallback, most recent wins.
- `ivgs-api/app/api/v1/model_store.py:269, :287, :321` — `GET /selections`,
  `POST /selections/plan`, `PUT /selections` all exist.
- **The frontend never calls any of them.** `grep -rn "selections"` across
  `ivgs-frontend/src` returns only unrelated hits (a preset type, a storyboard
  "clear all selections" handler). There is no model picker at any scope.

So the operator's stated capability — *models certified in MBCP, made available
by the IVGS admin, then selected by the user scene by scene* — is complete at
both ends and has no middle. This package fits the middle.

## TASK 1 — what the three endpoints actually do, measured

Before building any UI, establish and report with file:line:

- `GET /selections` — its scoping parameters, what it returns for a project with
  no selections, whether it exposes scene-scoped rows distinctly;
- `POST /selections/plan` — what "plan" means here. Read it carefully: it may be
  an auto-planner that picks models for every stage, which would change how the
  UI should present defaults. Report its actual behaviour, not its name;
- `PUT /selections` — its upsert semantics (`model_selection.py:142-155` deletes
  the scope then inserts, so it replaces rather than accumulates), its auth, its
  validation, and **what it does today if the model is not approved, or has no
  weights on any node**;
- whether `rationale` is enforced non-empty, and what the existing writers put
  there;
- what `selected_by` values exist (`SelectionSource`) and which the UI should
  write.

If any endpoint's behaviour differs from what this brief assumes, **the brief is
wrong and the measurement wins** — report it and build against what is there.

## TASK 2 — selection must respect availability (WP-65's output)

A selection whose bytes are not on a capable node is a runtime failure waiting
for a run. Close it at selection time:

- `PUT /selections` refuses a model that is **not approved** (lifecycle state),
  or has **no verified weights on a node hosting its engine**, with a named
  reason distinguishing the two cases — the same distinction WP-65 Task 4 made
  visible in the store.
- The refusal is a 4xx with a message a user can act on ("this model is
  certified but its weights have not been fetched — an admin can fetch them from
  Admin → Models"), not a generic validation error.
- If WP-65 Task 2 stopped and no availability record exists, **implement the
  approval check and STOP the availability half**, reporting the dependency.
  Do not invent an availability signal.
- Existing selections that later become invalid (model deprecated, weights
  removed) surface as a warning where the selection is displayed; they are not
  silently rewritten.

## TASK 3 — project-scoped selection UI

On the project page, a **Models** panel or tab:

- lists every stage the project will run (`transcript_refinement`,
  `storyboard_generation`, `translation`, `image_generation`,
  `video_generation`, `animation_generation`, `tts_audio`, `talking_head`,
  `composition` — take the real list from `ModelStage`, do not retype this one);
- for each stage, shows the currently bound model and **where the binding came
  from** — an explicit project selection, a preset, or the system default. The
  provenance label is not decoration: WP-60 Task 5 established that a surface
  presenting mixed provenance as one fact is the recurring defect in this
  codebase;
- offers the choice from models that are **approved and available** for that
  stage, with unavailable ones visible but disabled and labelled with why;
- captures a **rationale** (the column is mandatory) — default it to something
  honest like "operator selection" rather than forcing prose, but let the user
  write one;
- writes through `PUT /selections` with the right `selected_by`, and writes an
  `audit_log` row (a model change alters what the pipeline will produce).

Tier: selections are keyed by `(stage, tier)`. Establish what tiers exist
(`ModelTier` — prototype/final or similar) and present the tier explicitly
rather than hiding it; a user choosing a final-tier model should know that is
what they chose.

## TASK 4 — scene-scoped selection UI

This is the capability the operator asked for by name. The schema already
supports it; dispatch already honours it.

- In the **Edit Scene** modal, beside Media Type, a model picker for **that
  scene's** media type, showing the project-scoped binding as the inherited
  default and letting the user override it for this scene alone.
- Changing Media Type changes the candidate list (an animation scene offers
  animation models). This composes with WP-64's **Adapt description** action —
  medium, description and model are the three things a scene binds, and the
  modal should make that legible.
- An explicit **"use the project default"** choice that *clears* the scene-scoped
  row rather than writing a duplicate of the project one — the difference
  matters when the project default later changes.
- The storyboard grid shows, per card, when a scene overrides the project
  default, so an operator can see the exceptions without opening every card.
- Same availability refusal as Task 2, same audit row.

## TASK 5 — what a selection change invalidates (RULED)

**Ruling, so you do not have to ask:** a model selection change **invalidates
the draft gate only.** It does not invalidate the storyboard approval.

The reasoning, for the report: the storyboard artifact is narration, visual
descriptions and media types — a model choice does not alter it, and
invalidating it would refuse the very regeneration the user is selecting a model
for (the same asymmetry WP-63 D-1 resolved for regeneration). The draft, by
contrast, is the thing the models produced, so approving a draft and then
changing the model that made it must re-open that decision.

Implement it that way, test both halves (storyboard approval survives; a held
draft approval is invalidated with the reason recorded), and state the ruling
and its reasoning in the report.

## TASK 6 — the presets path stays consistent

`PresetApplyPanel.tsx` already claims a preset "writes the preset's actor, model
selections and media defaults into this project". Establish whether preset model
selections actually reach `project_model_selections` today, or whether that
copy is another declared-but-inert path. If it works, make the new UI show
preset-provenance correctly (Task 3's provenance label). If it does not, **fix
it or STOP and report** — do not leave a surface claiming a write that does not
happen.

## ACCEPTANCE

Build a test project of your own for this (create it, use it, delete it via the
WP-59 flow):

- project-scoped selection set through the UI, read back through `GET
  /selections`, and **observed at dispatch** — the WP-45 standard: the bound
  model reaching the engine call, not merely a row in a table;
- scene-scoped override set on one scene, proven to take precedence for that
  scene and to leave its siblings on the project default;
- "use the project default" clearing the scene row, proven by the row's absence;
- an unavailable model refused at selection with the correct reason, both cases;
- Task 5's invalidation asymmetry proven both ways;
- audit rows present for every selection write.

Screenshots per the WP-59 §12 convention if the environment still lacks a
browser — text renderings from captured payloads, stated plainly as such.

## RULES

Commit and HOLD — never push. Deploy `v5.25.0-selection` to **node-01 only**,
via the artifact path with the standard filename. Nodes 02/03/04 are operator
paste blocks; node-03's service is `cogvideox-worker`. NODE-05 and NODE-06 out
of bounds. Live data limited to your own test project and its rows. **The
operator's project `another new multiplication test run` is untouchable**, as is
every other existing project. You press no gates — Task 5's draft-invalidation
test uses a gate state you create programmatically on your own test project, or
it stops. Frozen stage bodies untouched. Full Python suite at most twice. ZERO
NEW FAILURES against the baseline, updated in the same commit as any fix that
moves a row. No secrets in the report or chat. Report to
`dev/workpackages/reports/WP-66-SELECTION-report_<date>.md` with a count-gated
push block for this package's commits.
