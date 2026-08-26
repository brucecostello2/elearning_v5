# WP-67-CLIENTS — a selected model reaches the code that knows how to run it

Read `WP-65-68-RUN-ORDER.md` first. It governs this package. **Do not start
until WP-66's report is written and its commits are held.**

## CONTEXT

Repo `/opt/ivgs`. Read `dev/CLAUDE.md`, the current TEST-BASELINE, your WP-65
and WP-66 reports, `docs/IVGS_v5_Addendum_AD-01*`, and **AD-05 §8 — the frozen
stage bodies.** That freeze is the central constraint of this package and the
most likely reason a task here stops.

Tag: **`v5.26.0-clients`**. Migrations continue from wherever WP-66 left them.

## THE FINDING THIS PACKAGE CLOSES (measured 2026-08-26 in the tree)

WP-65 gets the bytes onto a node. WP-66 lets a user select the model. Neither
changes **which code talks to it**:

- `ivgs-workers/tasks/animation_generation_task.py:61` imports
  `WanAnimateClient` **directly, at module level**. Not selected from the
  binding — imported.
- The binding resolves *which model row and which endpoint*
  (`shared/providers/binding.py`, `factory.py`), and then the task calls Wan's
  client, Wan's ComfyUI graph, Wan's preprocessors, Wan's inputs.
- `animation_generation_task.py:481` refuses a scene whose still contains no
  person — correct for Wan2.2-Animate, which is pose reenactment, and **wrong as
  a property of the stage**. MimicMotion, AnimateDiff and SVD have different
  input contracts entirely.
- `ivgs-workers/clients/` holds: `cogvideox`, `coqui`, `ffmpeg`, `flux`,
  `kokoro`, `latentsync`, `ollama`, `remotion`, `sadtalker`, `vllm`, `wan21`,
  `wan_animate`, `whisperx` — and a **`graphs/`** subdirectory. There is no
  AnimateDiff client and no MimicMotion client.

So selecting AnimateDiff-SD15 today would fetch its weights (WP-65), record the
selection (WP-66), resolve its endpoint — and then run `WanAnimateClient`
against it. The model would be blindfolded in a new way.

**The `graphs/` subdirectory is the promising lead.** All six MBCP animation
candidates and all twelve supporting components carry engine `comfyui`. If
per-model behaviour is already expressed as a ComfyUI graph plus parameters,
then a new family may need a **graph and a small adapter**, not a whole client —
and that work may sit outside the frozen bodies. Task 1 settles it.

## TASK 1 — the client selection point, measured before anything is built

Establish and report with file:line:

- what `ivgs-workers/clients/graphs/` contains, how a graph is chosen today, and
  whether graph choice is already parameterised by model;
- for each stage that has more than one plausible model family
  (`animation_generation`, `video_generation`, `image_generation`,
  `talking_head`, `tts_audio`), **where the client is chosen** — module-level
  import, factory call, or conditional — with the line;
- for each of those points, **whether the file is a frozen stage body under
  AD-05 §8**. This determines what this package can do and must be stated
  explicitly per stage;
- what the binding already carries that a selector could use: does
  `ModelBinding` expose family, engine, model id, and any per-model parameters?
  If a family field exists but nothing reads it, that is the fourth
  declared-but-unused mechanism this month and it goes in the report as such.

**If every client selection point is inside a frozen body**, this package
delivers Task 2's registry, Task 3's adapters, and their tests — proven in
isolation — and ledgers the wiring for M3.3 with the file:line facts. That is a
complete and successful outcome. Say so plainly rather than reaching into a
frozen file.

## TASK 2 — a client registry keyed on model family

Build, in unfrozen territory (`ivgs-workers/clients/` and `shared/providers/`):

- a **registry** mapping `(stage, engine, family) -> client factory`, populated
  by declaration rather than by a chain of `if` statements;
- a **capability contract** each client declares: what inputs it requires (a
  still? a person in the still? a reference clip? a text prompt only?), what
  parameters it accepts, what it produces. `animation_generation_task.py:481`'s
  person requirement becomes **Wan's declared input requirement**, not the
  stage's law;
- a **resolution function** that takes a resolved `ModelBinding` and returns the
  right client, with a named, actionable failure when no client is registered
  for that family ("model X is selected but IVGS has no client for family Y" —
  the honest refusal, which is what AnimateDiff would hit today);
- **pre-flight validation**: given a scene and a client's declared contract,
  answer *can this client run this scene?* before dispatch, so an unsatisfiable
  binding is refused at the point a human can act on it rather than deep in a
  worker. This is the mechanism that would have caught "animation scene with no
  person" as a selection-time refusal instead of a stage-time one.

Register the existing clients into it — `wan_animate` at minimum, plus every
client whose selection point Task 1 found to be unfrozen — without changing
their behaviour. A registry that produces exactly today's routing for today's
models is the correct first state, and its tests prove that equivalence.

## TASK 3 — one new family, end to end, as the proof

Pick **one** additional animation family and implement it against the registry.
Choose on evidence, not preference:

- **MimicMotion** and **AnimateDiff-SD15** are both `comfyui` in MBCP, both
  currently `candidate` with no weights;
- prefer whichever has the simpler ComfyUI graph and the input contract closest
  to what an educational still can satisfy — a family needing only a still and a
  prompt is worth more here than one needing a driving video;
- state the choice and the reasoning in the report.

Deliver: the graph (or graph parameterisation), the client implementing the
capability contract, its registration, and tests that run it against a fixture
without requiring the real weights. **A live run is not required and probably
not possible** — the weights are unfetched (WP-65's live pass is held) and the
engine may have no host (WP-67 does not stand up containers). Author the
operator block that would exercise it live once weights and host exist; report
it as staged.

If the chosen family turns out to need an engine that has no host on the fleet,
that is Task 1's "no node hosts engine X" refusal from WP-65 Task 3, and it is
the correct end state — record it and do not stand anything up.

## TASK 4 — the stage's refusals become the client's

Wherever Task 1 found an input requirement hardcoded as a stage property —
`animation_generation_task.py:481` being the known one — the requirement moves
into the owning client's declared contract, **if and only if** the moving can be
done outside a frozen body.

- If the stage body must change to consult the contract: **STOP, ledger, and
  report** with the exact edit that M3.3 will make.
- If the stage already calls out to something unfrozen that can consult the
  contract: make it consult the contract, and prove Wan's behaviour is
  unchanged — same refusal, same message, now sourced from the contract instead
  of the constant.

Either way, the report carries a table: requirement, where it lives today, where
it belongs, whether this package could move it.

## TASK 5 — the Model Store learns which families IVGS can actually run

WP-65 made "has weights on a node" visible. This package adds the second half of
the truth:

- a model whose family has **no registered client** shows that state distinctly
  — certified, fetchable, and unrunnable by this system today;
- the admin Models page and WP-66's selection pickers both honour it: such a
  model is visible, disabled, and labelled with the reason;
- the label distinguishes the three states cleanly — *no client*, *no host for
  the engine*, *not fetched* — because they need three different actions and
  conflating them is how an operator ends up selecting something that cannot
  run.

## ACCEPTANCE

- Task 1's table, complete, with the frozen/unfrozen verdict per stage.
- The registry resolving today's models to today's clients, proven equivalent to
  current behaviour by test.
- The new family's client passing its fixture tests and refusing correctly when
  its declared inputs are unsatisfiable.
- The "no client registered" refusal proven as a named, actionable outcome.
- Task 5's three states visible and distinct on the admin surface.
- Every STOP recorded with file:line and the ruling it needs.

## RULES

Commit and HOLD — never push. Deploy `v5.26.0-clients` to **node-01 only**, via
the artifact path with the standard filename. Nodes 02/03/04 are operator paste
blocks; node-03's service is `cogvideox-worker`. NODE-05 and NODE-06 out of
bounds. **Stand up no containers and no engines** — that is WP-68's question and
an operator action either way. Live data limited to your own test projects,
deletable via the WP-59 flow; the operator's project `another new multiplication
test run` and every other existing project are untouchable. You press no gates.
**Frozen stage bodies untouched — this package is the worked example of that
constraint, and stopping is the expected outcome for any task that meets it.**
Full Python suite at most twice. ZERO NEW FAILURES against the baseline, updated
in the same commit as any fix that moves a row. No secrets in the report or
chat. Report to `dev/workpackages/reports/WP-67-CLIENTS-report_<date>.md` with a
count-gated push block for this package's commits.
