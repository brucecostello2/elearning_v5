# WP-61-QWEN — node-05 becomes the LLM node, translation gets a contract before it gets a run

**Date:** 2026-08-26 · **Repo:** /opt/ivgs · **Baseline:** TEST-BASELINE_2026-08-25 (current revision)
**Version:** `v5.20.0-qwen` across `ivgs-api`, `ivgs-frontend`, `ivgs-workers`
**Deployed:** node-01 only, WP-34 binding rules, artifact path. **Commits are HELD, not pushed.**

---

## 0. The one page worth reading first

**Translation has never run, and that is the finding, not the preamble.**
Measured before a line was written: one `translation` prompt row created
2026-05-23 that nothing has ever rendered; 16 `language_variants` rows and all
16 `pending`; no translation task in `ivgs-workers/tasks/`; and
`LanguageService.retry_variant` saying so in its own docstring — *"a retried
variant re-renders the SOURCE narration with the target language's voice."*

So Task 3(a)'s stop condition is met: **the executing body is absent**, and no
new pipeline stage body is written pre-cutover. What is built instead is the
*consuming path* — the routing, the contract, the strip, the state transition —
which Task 3(a) puts in scope regardless. It is an API-side service, registers
no Celery task, and appears in no `STAGE_TASK_MAP`. §4.

**The contract had to come before the run, and the code refuses without it.**
Qwen appended a correction in all four languages on 2026-08-25 because the
reference project's scene 5 genuinely teaches 10×3=30, 10×2=20 ⇒ "320" written
as 230. `TranslationService` now **refuses to translate at all** under a prompt
that does not carry the fail-and-flag marker — proven live against production:

```
REFUSED, as designed:
the active translation prompt does not carry the WP-61 fail-and-flag contract:
it never mentions 'IVGS-TRANSLATION-FLAG:'. ...
variant after the refusal: ('pending', True, True)
```

The variant is untouched. Publishing the amended prompt is operator block N01-A;
the es-ES run is N01-B. **Neither has been executed** — node-05 is not yet
serving, and everything on node-05 is an operator paste block by rule.

**Three tests in this package were nearly wrong, and two of them are the most
useful things in it.** The obvious trigger-guard test passes without the guard
(§7.2). The WP-59 orphan-schedule test was passing by string accident over a
schedule that had just been turned on (§8.3). Both are recorded rather than
quietly corrected.

**Per-task verdicts:**

| Task | Verdict |
|---|---|
| 1 — provision node-05 | **AUTHORED, NOT EXECUTED.** Compose + env template + six operator blocks, committed. §2 |
| 2 — register it honestly | **DONE and deployed.** Role, services, scheduler count, playground, three stale comments. §3 |
| 3 — translation to Qwen | **HALF STOPPED AS RULED, HALF DONE.** No stage body. Contract, routing, strip, state, migration 0034, 20 tests. Acceptance is N01-A/N01-B. §4 |
| 4 — reference-run annotation | **DONE.** README beside the artefacts + `docs/`, and the Llama pin stated in both. §5 |
| 5 — trigger in-flight guard | **DONE and deployed**, with a scope finding: the six measured dispatches came through a route the ruling does not name. §7, D-1 |
| 6 — nightly tier migration LIVE | **DONE and deployed.** `dry_run=False, max_transitions=500`, and deletion made structurally impossible. §8 |
| 7 — orphan sweep scheduled | **DONE and deployed.** Weekly, quarantine-only, Type-1 excluded and ledgered. Dispatched on the deployed image. §8 |
| 8 — GPU telemetry from Prometheus | **DONE and deployed.** Live readings on the fleet card for the first time. §9 |

---

## 1. What was measured before anything was written

Every number below is from a command run on 2026-08-26 against the live system,
not from a document.

| Question | Answer | How |
|---|---|---|
| Has translation ever run? | **No.** 16 `language_variants`, all `pending` | `SELECT state, count(*) FROM language_variants GROUP BY state` |
| Is there a translation prompt? | One. `e16b6502-…`, v1, global, active, created 2026-05-23 | `SELECT … FROM prompts WHERE prompt_type='translation'` |
| Has it ever been rendered? | **No.** Its only appearance in worker code is a docstring recording it being selected *by mistake* in place of Stage 1's (IVGS-0.4) | `grep -rn 'translat' ivgs-workers/` → 5 hits, all prose |
| Is there a translation stage body? | **No.** `ivgs-workers/tasks/` has fourteen files and none is one | `ls ivgs-workers/tasks/` |
| Is translation in the Model Store? | Yes — `Llama-3.3-70B-Instruct`, stage `translation`, engine `vllm`, approved, `dynamically_loadable=true` | `SELECT … FROM models` |
| Reference project narration | scene_index **5**: *"…Our second answer is 320, but we wrote it as 230 in the previous step, which is incorrect."* | `SELECT scene_index, narration_text FROM storyboard_scenes WHERE project_id='c12fa967…'` |
| Retention policies | 3 rows, **all with NULL `archive_days` and NULL `delete_after_days`** | `SELECT * FROM retention_policies` |
| Assets | 71 rows: 70 `hot`, 1 `warm`, 0 preserved | `SELECT storage_tier, count(*) FROM assets GROUP BY 1` |
| `job_status` enum | `pending, running, success, failed` — exactly two terminal | `pg_enum` |

---

## 2. TASK 1 — node-05, authored and not executed

**Nothing in this section was run.** node-05 is reached only by operator paste
block, by rule, and this package did not read a single value off it. Every
figure the acceptance battery produces belongs in the operator's own record.

### 2.1 What was written

| File | What it is |
|---|---|
| `ivgs-infra/.env.node05.example` | The tracked statement of what `.env.node05` must contain. **`.env.node05` itself is gitignored** and is written on node-05 by block A06. |
| `ivgs-infra/docker-compose.llm.node05.yml` | One service, `vllm-qwen`, its own compose project (`name: ivgs-llm`) |
| `dev/workpackages/WP-61-operator-blocks.md` | A05…A10 on node-05, N01-A/N01-B on node-01 |

**`.gitignore` had to be corrected to let the template be tracked.**
`ivgs-infra/.env.node0*` matched `.env.node05.example` and would have silently
excluded it — so node-05 could never have pulled the file block A06's SHA gate
checks. A negation was added rather than a `git add -f`, because a force-add is
invisible to the next person.

### 2.2 The env template was written, not copied

The brief called the node-02 template known-stale and it is. Copying it would
have put four wrong facts on node-05 in the name of consistency: `CHANGE_ME`
image-tag placeholders for images this node does not run, a `POSTGRES_PASSWORD`
it has no use for (no worker, no database connection), a CogVideoX/Wan2.1 block
for engines it does not host, and no identity block at all.

The WP-38/WP-45 identity block is present and is not decoration —
`IVGS_NODE_NAME` is what config.py reads *first*, and it is what stopped the
scheduler registry filling with container hex ids (21 "nodes" on a fleet of
three GPUs, measured 2026-08-25).

`tests_system/test_wp61_node05.py::TestTheIdentityBlock` asserts all four
identity variables, and asserts the stale template's fingerprints are absent.

### 2.3 The invocation is measured, and the tests say why each flag is there

Every flag was established by a failure during the 2026-08-25 evaluation. The
tests exist because each is one careless edit away from a container that either
will not start or starts and quietly poisons Stage 2's parser:

| Flag | If it is dropped |
|---|---|
| `--max-num-seqs 128` | The engine **refuses to start**. Hybrid attention/Mamba: one Mamba cache block per decode sequence, 216 available at the 48 GB budget, default 1024. |
| `--reasoning-parser qwen3` | ~1400 tokens of chain-of-thought land in `content`, and Stage 2's JSON extractor grabs the schema echo out of the reasoning text. |
| `Qwen/Qwen3.8-27B-FP8` | The BF16 base is ~56 GB of weights against a 48 GB card. It does not fit. |
| `--trust-remote-code` | Required. |

### 2.4 `--gpu-memory-utilization` is 0.90, and 0.48 is refused by test

**0.48 was the SIMULATION cap** — a 96 GB RTX PRO 6000 held down to 0.48 to
imitate a 48 GB card. Carrying it onto the real card would have given Qwen 23 GB
of 48 and then reported the resulting KV-cache and Mamba-block figures as
REAL-48GB measurements. `TestTheSimulationCapDoesNotSurvive` fails if `0.48`
appears in either file, and fails if `VLLM_GPU_UTIL` exceeds the ruled ceiling
of 0.92.

### 2.5 Two details in the compose file that are easy to get wrong

**The healthcheck hits `/v1/models`, not `/health`.** `/health` answers 200 from
the moment the HTTP server binds, which is minutes before the weights finish
loading — it distinguishes "listening", not "serving". `/v1/models` is behind
`--api-key`, so the key is sent, using `$$VLLM_API_KEY` so expansion happens in
the container rather than being baked into the rendered compose config.
`start_period` is **900s**: the fleet default of 60s would put this container in
an unhealthy-restart loop that never completes a single weight load.

**`--env-file` is load-bearing and block A09 gates on it.** `env_file:` on a
service injects into the container; it does **not** feed `${VAR}` interpolation
in the YAML, and every vLLM flag is a `${VAR}`. Without it they collapse to
their `:-` defaults — which happen to be the right values, and that is *worse*:
an operator who edited `VLLM_GPU_UTIL` would see the edit silently ignored and
a 0.90 run reported as whatever they thought they set. Recorded in
dev/CLAUDE.md §6.3.

### 2.6 Weights provenance — the exception and the debt

A direct HuggingFace pull is authorised as the **second operator exception** to
the weights-from-MBCP doctrine. Block **A07** is its own block with a time
warning (~29 GB, 30–90 minutes, run it in `tmux`), and it sha256s every
downloaded `*.safetensors` and `*.json` into
`/mnt/ivgs-shared/qwen-weights-manifest-<date>.txt`.

**The debt, ledgered explicitly and written into the manifest header itself:**

> MBCP must **bank and certify this exact bundle** (work orders 5 and 7) before
> the Model Store lists it as anything other than an exception. Until then the
> model is **provenance-exceptional**: running, hashed, uncertified.

The manifest carries hashes only. No token, no key, no credential — asserted by
`TestOperatorBlocksAreSafeToPaste::test_no_block_contains_a_credential`.

### 2.7 The acceptance battery — authored, awaiting the operator

Block **A10** runs four measurements and the table it fills in is in the block.
The fourth is the one this package exists to produce: **the first REAL-48 GB
figures**, tabulated against the simulation. The ruling is carried in the block
in as many words:

> If Mamba blocks come back below 128, lower `VLLM_MAX_NUM_SEQS` to fit and
> record it. **Do not raise `VLLM_GPU_UTIL` past 0.92** to chase the
> simulation's numbers. The simulation is superseded by these measurements, not
> the other way round.

**These results are not in this report because the blocks have not been run.**
Reporting them would be an invention, which is the failure mode this whole
series exists to remove.

---

## 3. TASK 2 — every surface that would have lied about node-05

node-05 now has a GPU serving a model and **no Celery worker** — exactly
node-06's shape. Six surfaces were checked; four were wrong.

### 3.1 The topology row — role, services, and the reason for the count

`ivgs-api/app/api/v1/nodes.py` read `"role": "Quality services (earmarked)"` and
`OUT OF SERVICE: confirmed host memory fault`. Both halves were wrong, each in
a different way: the fault was real and is **fixed**, and the quality-services
earmark is **superseded** — the CLIP scorer runs on node-06 and node-06 is its
sole host.

Now, and verified live from the deployed API:

```
node_id                node-05
status                 online          (node-exporter-scrape)
role                   GPU LLM (Qwen3.8-27B-FP8, translation)
gpu_model              NVIDIA RTX PRO 5000 Blackwell
total_vram_mb          48935
has_gpu                True
runs_pipeline_worker   False
services               ['vllm-qwen', 'node-exporter', 'nvidia-gpu-exporter', 'node-logs']
telemetry              available=true  source=prometheus:nvidia-gpu-exporter
gpu_utilization_pct    0.0   temperature_c 37.0   power_draw_w 14.26   used_vram_mb 2.0
```

**The hardware row was NOT re-guessed.** WP-48's measurement stands; only the
role moved. A role change is not licence to re-open a number that was measured
on the box.

### 3.2 `runs_pipeline_worker` stays False, and the count stays 3

This is the field WP-57 added precisely so a surface can say what it counts.
node-05 must not enter the scheduler's fleet: **a vLLM server is not a Celery
consumer**, and AD-02's `dynamically_loadable=false` stands — the model is fixed
at container start by `--model` and cannot be swapped at runtime.

`test_wp61_surfaces.py::test_node_05_is_NOT_in_the_scheduler_fleet` fails if the
count moves off 3.

### 3.3 Three stale comments, each of which would have sent a reader wrong

**Where a surface hardcoded a role, the source was fixed, not the string.**

| Site | What it said | Why it mattered |
|---|---|---|
| `nodes.py`, node-06's comment | "node-05 has a GPU and is out of service" | The count is still 3, but for node-06's reason now, not node-05's old one. A stale *reason* in a neighbouring row is WP-60 §21.1's defect one file over. |
| `docker-compose.node01.yml:315` | "The CLIP scoring service **on node-05**" — with `${NODE_06_IP}` on the line beneath | A comment naming a different node from the code under it. Same family as §21.1. |
| `node_health.py`, `node_health_notes()["gpu"]` | "As of 2026-08-23 no node in the fleet runs a working GPU exporter (ledger P2.6a)" | **A caveat that is itself stale is worse than no caveat**: P2.6a was closed by WP-48, the module's own docstring already said so two packages earlier, and this sentence is *served to the UI* — it sends the reader after a fixed bug. |

### 3.4 The Prompt Playground listed three models node-05 has never run

`PromptPlayground.tsx` offered **Llama 3.2 8B, Phi-3 Medium and Gemma 2 9B, all
"node-05, 8 GB VRAM, Ollama"**. node-05 has never run Ollama, has never held any
of the three, and its card is a 48 GB RTX PRO 5000. Selecting one sent a
completion to `OLLAMA_URL` (node-05:11434), where nothing has ever listened.
AD-02 Draft 4 §1.2 records the same three services being asserted of this node
in the specification and says the same thing: *"None of that has ever run on
node-05."*

The three are replaced by the one real entry — and **the routing was fixed
with it**, because adding a selectable model that 404s is a new lie, not a fix.
The playground resolves the engine by model name in `models`; `qwen38-27b` is
not registered there, so it fell through to the default engine and would have
been sent to node-02. `MODEL_URL_ENV` now routes it to node-05.

**What was deliberately left alone, and is a decision, not an oversight:**
`qwen2.5-72b` on node-02+node-03 is not in the Model Store and this package did
not verify it, and the tensor-parallel pairing claimed for both node-02 entries
is a §7.1 declaration. That list should be READ from `/api/v1/models` rather
than transcribed from a spec section. Correcting only the node-05 rows is this
task's scope; rewriting the others silently would be a claim this package cannot
support. **Ledger WP61-L2.**

### 3.5 The model-residency heatmap enumerates nothing at all

Checked, as the task asked. `useMonitoring.ts:371` reads
`fleetData?.model_residency ?? data?.model_residency`, and **no route in
`ivgs-api` produces a `model_residency` key** — `grep -rn "residency"
ivgs-api/app` returns nothing. So `heatmapData` is always `[]` and the tab
renders *"No model residency data available."*

It therefore cannot lie about node-05, and **no change was made.** But it is
also not the feature it looks like: the scheduler's `/fleet` does publish
`loaded_models`, `to_node_view` already carries it, and the tab could be real.
Building it is a package of its own. **Ledger WP61-L3.**

---

## 4. TASK 3 — translation: what was stopped, and what was built

### 4.1 (a) The measurement, and the stop

`ivgs-api/app/services/translation_service.py`'s module docstring carries the
evidence rather than pointing at it. The short version is §1's table: the
schema exists, the prompt exists, and **nothing has ever executed**.

Task 3(a) rules on that case: **STOP that half.** No pipeline stage body was
written. What exists instead is:

* `TranslationService` — an API-side service, called synchronously, the same
  shape as `app/api/v1/clip.py`'s scorer proxy;
* `POST /api/v1/projects/{id}/languages/{vid}/translate`, behind
  `require_operator_or_admin` — verified registered on the deployed API;
* **no Celery task, no `STAGE_TASK_MAP` entry, no orchestrator dispatch.**

After the M3.3 cutover the Temporal activity calls
`TranslationService.translate_variant`. It does not reimplement it.

### 4.2 (b) Routing — and the constraint the whole package rests on

**Three IVGS stages run on `vllm`**: `transcript_refinement`,
`storyboard_generation` and `translation`. Pointing `IVGS_VLLM_URL` at node-05
would move all three — and then the Temporal conformance baseline would be
diffed against a different model, so the diff would answer nothing about the
orchestrator. **The model does not move under the diff.**

So the override is scoped to the (engine, stage) **pair**, following
`binding.py`'s pattern:

```python
_STAGE_ENGINE_ENDPOINTS = {
    ("vllm", "translation"): ("IVGS_VLLM_TRANSLATION_URL", "http://node-05:8000"),
}
```

`resolve_endpoint(engine, node_id=None, *, stage=None)` — a stage not in the
table resolves **exactly** as it did before the parameter existed, which is the
property `test_storyboard_and_transcript_DO_NOT_MOVE_off_llama` pins.

It is a table of names, not a computed variable name, deliberately: a derived
name means any typo in a stage string silently produces a variable nobody set,
which resolves to the unscoped default and moves the model without saying so.

Live in the deployed API container:

```
IVGS_VLLM_TRANSLATION_URL=http://192.168.1.94:8000
VLLM_TRANSLATION_URL=http://192.168.1.94:8000
VLLM_PRIMARY_URL=http://192.168.1.91:8000     <- storyboard/transcript, unmoved
```

`enable_thinking: false` is sent per request as a module constant — 53.9 s →
9.3 s measured, and translation has no use for chain-of-thought.

**One test pins that the two modules name the same variable.**
`translation_service` reads `IVGS_VLLM_TRANSLATION_URL` and `binding` resolves
the pair from the same name; if one is renamed and the other is not, the API
and a future worker binding send translation to different servers and *nothing
errors*, because both endpoints answer.

### 4.3 (c) The contract, and why the gate runs before the model call

The prompt is amended to translate faithfully, never correct, and emit at most
one `IVGS-TRANSLATION-FLAG: <reason>` line **after** the translation.
`split_flag()` removes it from the deliverable and returns the reason;
the variant goes to `flagged`, not `complete`.

**`flagged` is not `failed`.** `failed` means there is no text. `flagged` means
there is text and a human must look at it. Collapsing them either hides a real
deliverable behind an error badge or hides a real doubt behind a green one.

**The gate is `_assert_prompt_carries_contract`, and it runs before the first
write.** A prompt without the contract produces a model that corrects silently
and inline — the strip then finds nothing to strip and the run records the
corrected text as `complete`. **A guard that only runs after the damage is not a
guard.** Proven live: the refusal fires and the variant is left `pending` with
both new columns NULL (§0).

Design details worth stating:

* The marker regex is anchored to the start of a line (`^`, MULTILINE) so a
  translation that *discusses* the marker is not mangled — and a leading indent
  still counts, so a marker cannot hide behind whitespace.
* A marker with an empty reason is still a marker (`"(no reason given)"`).
  Returning `None` there would silently promote the variant to `complete`.
* Two markers are both stripped and their reasons joined. The prompt asks for
  one; a model that emits two must not thereby leave one embedded.
* Scenes are translated **one at a time**: 18 scenes would overrun a single
  4096-token completion, and a per-scene call attributes the flag to the scene
  that caused it. *"Something in this project looks wrong"* is not actionable.
* `finish_reason == "length"` is a **failure**, not a truncation. WP-58's
  Stage-2 lesson: a translation cut off mid-transcript reads fluently to the cut
  and nothing in the text says the tail is missing.
* Rendering uses `StrictUndefined`. This exact template was once rendered with
  `target_language` and `narration_text` unset — Jinja produced empty strings
  and the transcript vanished (IVGS-0.4).

### 4.4 Migration 0034

One enum label (`language_variant_state.flagged`) and two nullable JSONB columns
on `language_variants`: `translation` (the deliverable, marker already removed)
and `translation_flags` (the markers, with their scene). Two columns rather than
one blob so *"which variants did the model doubt?"* is one predicate.

**Applied to the test database and to production, and its downgrade was
exercised** — `alembic downgrade 0033` then `upgrade head` round-trips clean.
The columns drop; the enum label does not, and the docstring says why rather
than leaving it for the next reader to discover from a failed downgrade.

### 4.5 (d) Acceptance — authored, not executed, and why

Block **N01-B** runs es-ES on `c12fa967…` end to end against node-05. It has not
been run, for one reason: **node-05 is not serving yet**, because every node-05
action is an operator paste block by rule. The dependency chain is A05 → A10 →
N01-A → N01-B.

What N01-B is written to prove, and what to record:

* `state` transitions `pending → processing → flagged` (**not** `complete`,
  **not** `failed`);
* at least one flag naming **scene_index 5**;
* `marker in deliverable: False` for that scene's text;
* the `en-US` row untouched and still `pending`.

**The source narration must not be regenerated or edited.** It is the only
real-data proof the flag path works.

---

## 5. TASK 4 — the reference run's correctness annotation

Written in two places, as ruled, and **nothing in the banked run was changed**:

* `/mnt/ivgs-shared/reference-run-2026-08-23/README.md` — beside the artefacts,
  so a reader who finds the directory without finding the repo still finds the
  annotation;
* `docs/reference-run-2026-08-23-correctness-annotation.md`.

The load-bearing sentence: **"matches the reference" must never be read as
"correct".** The run is byte-comparable output from a known pipeline at a known
commit, which is exactly what a Temporal conformance diff needs, and it teaches
arithmetic wrongly.

Both documents state the consequence explicitly: **storyboard and transcript
REMAIN ON LLAMA until after M3.3**, so the next conformance diff shows
differences caused by the orchestrator rather than by the model. Both state that
regeneration happens post-M3.3 as the first production run, not before. Both
state that the source narration is not edited *because it is the live test case
the WP-61 flag path fires on*.

The affected scenes are 5, 6, 11, 12 and 13 — scene 11 contains *"we wrote it as
640 in the previous step, which is incorrect"* about a step that says no such
thing. **No pipeline stage can catch any of it**: every quality gate in IVGS
measures whether the *output* matches the *input*, and this input was rendered
faithfully.

A trap row was added to dev/CLAUDE.md so a cold-start session cannot miss it.

---

## 6. What changed in dev/CLAUDE.md, and why each line

| Change | Reason |
|---|---|
| node-05 row rewritten | It said "Earmarked for the quality-services stack". It is the Qwen LLM node, with the compose file and the `--env-file` requirement named. |
| node-06 row rewritten | It said "ONLINE, **UNPROVISIONED** … no `/opt/ivgs` and has never been provisioned". True on 2026-08-25; it is now the CLIP scorer's sole host and is operator-managed and out of bounds. |
| §6.3 added | The `--env-file` trap, stated where a cold-start reader will hit it. |
| Trap: `docker exec` heredocs | WP-60 Task 12(d) found it and it was not in the traps table. |
| Trap: the Qwen invocation is measured, not designed | So the next person does not "tidy" `--max-num-seqs`. |
| Trap: "matches the reference" is not "correct" | §5. |

---

## 7. TASK 5 — the in-flight guard, and a scope finding

### 7.1 What was built

`ProjectService.trigger_pipeline` now refuses with **409
`PIPELINE_ALREADY_RUNNING`**, naming the active run's id, type and status, while
any non-terminal `render_jobs` row exists for the project. The GUI's
`PipelineGateButton` stays **mounted and disabled** — a control that vanishes
reads as a rendering fault and invites a reload — with the reason beside it:
*"A transcript_refinement run is running (job 89383cdd…). Wait for it to finish
or cancel it."*

Three design points:

* **The guard is the first statement in the method**, before the state check,
  the transcript check, the state write and the job row. A guard after the state
  write leaves a project moved and a row inserted for a run that never happened
   — which *looks like progress* and is worse than the original defect.
* **`NOT IN (terminal)`, not `IN ('pending','running')`.** `job_status` has four
  labels and exactly two are terminal. Spelling it as the complement means a
  label added later — `cancelling`, say — is treated as in-flight until somebody
  decides otherwise, which is the safe direction for a guard.
* **One definition of "in flight."** `_active_job()` serves both the guard and
  the `active_job` field the button reads. Two copies of that predicate is how a
  button and a server come to disagree about whether a run exists; a test fails
  if a second hand-rolled version reappears.

### 7.2 The test that was written wrong first

**This is the most useful thing in Task 5 and it is kept on the record.**

The obvious test — press twice on a DRAFT project, assert one broker message —
**passes without the guard.** The first trigger moves the project
DRAFT → TRANSCRIPT_REFINEMENT and the state machine refuses the second on its
own. Verified by deleting the guard and re-running: **six of eight tests still
went green.**

A test that passes against the defect is precisely what this series of packages
exists to stop, and it nearly shipped *inside the fix for it*.

The condition that actually matters is a project in a **triggerable state that
already has a non-terminal job** — which the project's own state cannot express:
a run that failed part-way, two requests inside one another's window (the state
write and the dispatch are in the same request), or any path returning a project
to a triggerable state with work outstanding. `TestGuardBites` constructs that
directly. With the guard deleted, all four of its tests fail:

```
FAILED TestGuardBites::test_a_trigger_while_a_run_is_outstanding_publishes_NOTHING
FAILED TestGuardBites::test_the_outstanding_run_is_the_one_NAMED_in_the_refusal
FAILED TestGuardBites::test_nothing_is_written_by_the_refused_trigger
FAILED TestGuardBites::test_the_guard_lifts_when_the_run_reaches_a_terminal_status
```

The double-press tests are kept, under a class named
`TestStateMachineAlsoCoversTheSimpleCase`, so nobody later reads them as
evidence the guard works.

**Every assertion is on the broker count, not the status code** (WP-45's
standard). All six of the real presses answered 200 *and* dispatched; a 409 that
arrives after the dispatch is not a guard.

### 7.3 The scope finding — the ruling names a route the incident did not use

Read from WP-60 §13.3's `audit_log` extract: the six dispatches on project
52d52867 were `job_type` **`video_generation`** and **`animation_generation`**.
Those are not `/trigger` job types — `trigger_pipeline` produces
`transcript_refinement` or `final_render`. They came through
**`POST /projects/{id}/scenes/{sid}/regenerate`**.

The ruling says *"The trigger endpoint refuses…"*, and that is what was built.
**The route the measured incident actually used is still unguarded.** The
mechanism to close it now exists (`_active_job` is one call), but widening the
scope of a ruling on my own judgment is not this package's call. **D-1.**

---

## 8. TASKS 6 & 7 — two schedules turned on, and what stops them going further

### 8.1 The nightly tier migration is LIVE

```python
"retention-migration": {
    "task": "ivgs_workers.tasks.periodic_tasks.run_retention_migration",
    "schedule": crontab(hour=4, minute=0),
    "kwargs": {"dry_run": False, "max_transitions": 500},
    "options": {"queue": "default", "priority": 2},
},
```

Read from the **deployed** `ivgs-celery-beat`:

```
retention-migration -> ivgs_workers.tasks.periodic_tasks.run_retention_migration
   schedule: <crontab: 0 4 * * * (m/h/dM/MY/d)>
   kwargs  : {'dry_run': False, 'max_transitions': 500}
```

`max_transitions=500` is a **standing** cap, not a first-pass cap. Nobody is
watching a 04:00 job; the sane failure mode for a migration that suddenly finds
thousands eligible — a policy edit, a clock skew, a backfill — is to move 500
and set `capped=True` in a report someone reads.

The task itself **still defaults to dry run**. Live-ness lives on the entry, so
an accidental bare dispatch still reports rather than migrates.

### 8.2 archive/delete: made impossible by CODE, not by data

The brief asks for a test that "a future policy edit cannot silently enable
deletion through this path". A test alone cannot do that, so the property was
moved into the code first.

Today all three `retention_policies` rows have NULL `archive_days` and NULL
`delete_after_days`, so nothing progresses past cold. **That is true, and it is
a property of DATA**: one `UPDATE retention_policies SET delete_after_days=365`
turns the nightly job into a deleter with no code change, no review, and nothing
in any diff.

`RetentionService` gains `allow_delete: bool = False`. The `archived → deleted`
hop — the only one that destroys bytes — is refused whatever the policy says.
**The beat entry does not pass it**, and that omission is load-bearing.

Placement matters: the refusal is checked *after* eligibility and *before*
`would_move`, so the count reads *"N assets were due for deletion and were not
deleted"* rather than *"N assets are sitting in the archived tier"*, and a dry
run's `would_move` stays a truthful prediction of what a live pass moves.

**Three tests, and the second is the one that survives a future policy edit:**

1. NULL terminal days mean *do not progress*, never zero. (`mapping.get(tier, 0)`
   would have deleted the fleet on first reach — 0 satisfies
   `time_in_tier >= duration` for every asset that has ever existed.)
2. A policy with `delete_after_days=1` against a 400-day-old asset **still
   deletes nothing**, no DELETE reaches the database, and the refusal is
   *reported* in `policy_gaps` — because a refusal that is invisible reads, one
   report later, as "there was nothing to delete".
3. The negative: `allow_delete=True` **does** reach the delete path. A guard that
   refuses unconditionally is theatre and somebody will route around it.

### 8.3 The orphan sweep is ON, weekly, and cannot delete

```python
"orphan-cleanup-weekly": {
    "task": "ivgs_workers.tasks.periodic_tasks.run_orphan_cleanup",
    "schedule": crontab(day_of_week=1, hour=3, minute=30),
    "kwargs": {"dry_run": False, "quarantine_only": True,
               "exclude_scans": ["type1"]},
    "options": {"queue": "default", "priority": 2},
},
```

All three kwargs are passed **explicitly** rather than inherited: a schedule that
relies on a default is one refactor from meaning something else, and this
particular default governs whether binaries are destroyed.

* `quarantine_only=True` — the quarantine-**expiry** pass, the only path here
  that permanently destroys bytes, does not run at all. Quarantine is reversible
  for `QUARANTINE_DAYS` and every move is audited; permanent deletion is
  reversible by nothing. A schedule may do the first. A human decides the second.
  It is **not** a synonym for `dry_run`: a quarantine-only run genuinely acts.
* `exclude_scans=["type1"]` — **ledgered debt, not tidying.** Type 1 lists the
  filer namespace, which is EMPTY on this fleet; every object is a volume object
  addressed by fid and there is no supported way to enumerate the fid namespace
  (WP-60 §12.2). It returns 0 whether or not such orphans exist, which is
  indistinguishable from "there are none". A design decision about fid
  enumeration is **owed**, and until it is made **this sweep is a Type-2 and
  Type-3 backstop and must not be described as a complete one.** The service
  writes the reason into `report.coverage["type1"]` on every run.
* The `SharedObjectGuard` remains **mandatory and unparameterised** — there is no
  configuration in which this service quarantines or deletes without consulting
  it. Re-asserted by test because this package turned the schedule on.

`_report_orphan_cleanup_metrics` adds one greppable
`orphan_cleanup_weekly_result` line, the treatment WP-60 gave the tier
migration, and it is defined **above** the decorator that follows — WP-60 §21.2
records a helper inserted into exactly that gap taking the `@shared_task` and
leaving the task unregistered.

### 8.4 Dispatched against the deployed image, on real rows

Registration confirmed on the running worker (`celery -A celery_app inspect
registered`), then dispatched — **dry run, writes nothing**:

```
dry_run                          True
status                           ok
type1_seaweedfs_without_db       0
type2_db_without_seaweedfs       0
type3_zero_reference_count       0
newly_quarantined                0
permanently_deleted              0
duration_seconds                 0.198796
--- coverage ---
type1: EXCLUDED from this run. Type 1 lists the filer namespace, which is empty…
type2: 71 asset rows checked
type3: 0 zero-reference rows older than 7d considered
quarantine_expiry: NOT RUN: quarantine_only. Permanent deletion is not reachable…
```

Both exclusions carry their reason, so 0 can never be read as "nothing was due".
0.2 s, against the half-hour stall WP-60 fixed.

The tier migration, dispatched dry on the deployed image:

```
status ok   policy_source database   assets_scanned 71
would_move {'hot->warm': {'assets': 10, 'bytes': 2982283}}
transitions_performed 10   assets_deleted 0   capped False   errors []
```

**Note the fleet has shrunk since WP-60**: 161 assets scanned then, 71 now
(70 `hot`, 1 `warm`). That is WP-59's deletion service and the operator's capped
pass, not a regression in the scan — `policy_source=database` and zero errors.

### 8.5 A second, drifting beat schedule that would have undone both rulings

`periodic_tasks.get_beat_schedule()` returned a **hand-written copy** of the
schedule. Nothing called it — the real one is
`celery_app.CELERY_BEAT_SCHEDULE` — and being uncalled is the *only* reason it
never did harm. What it contained:

```
"orphan-cleanup-daily"      -> run_orphan_cleanup,      NO kwargs, DAILY 02:00
"retention-migration-daily" -> run_retention_migration, NO kwargs, hour from
                               a RETENTION_JOB_CRON env var nothing sets
```

**Both rulings live in kwargs.** An orphan entry with no kwargs is a nightly
sweep that can permanently delete and that runs the zero-coverage Type-1 scan; a
retention entry with no kwargs is an uncapped dry run. One
`app.conf.beat_schedule = get_beat_schedule()` — *which its own docstring
suggested* — would have replaced both rulings with their opposites, and every
test that reads `celery_app.py` would still have passed.

It now returns the one real schedule. The now-dead `_parse_retention_cron` helper
went with it.

### 8.6 A WP-59 test that was passing for the wrong reason

`test_the_orphan_schedule_is_off_and_not_merely_pointed_at_a_stub` asserted
`'"orphan-cleanup"' not in line`. WP-61's entry is `"orphan-cleanup-weekly"`, so
the literal with its closing quote **did not match** and the test stayed green
over a schedule that had just been turned on. It was matching a string, not
measuring a property.

Both WP-59 assertions were inverted, and the *stub* half — "'off' never means 'a
stub runs and reports ok'" — is unchanged in strength and still asserted. The
progression is in the baseline (§3) and in the test's own docstring:

| | protected | rested on |
|---|---|---|
| WP-59 | nothing unattended **runs** | a `#` |
| WP-60 | nothing unattended **moves** | a default the entry could not override |
| WP-61 | nothing unattended **destroys**, nothing moves uncapped | a refusal in the service + an explicit kwarg a reviewer can see |

---

## 9. TASK 8 — GPU temperature, utilisation and power from Prometheus

### 9.1 Why "not reported" was true and permanent

Those three fields reach the scheduler registry on a worker heartbeat, and the
heartbeat sender obtains them by shelling out to `nvidia-smi` **inside the
worker container**. The workers image has no such binary — proven 2026-08-26,
`exec: "nvidia-smi": executable file not found in $PATH`. So the sender cannot
produce a reading on any node, on any heartbeat, ever.

WP-60 made the card say "not reported" instead of "0 C", which was the correct
repair of a lie. This is the repair of the **absence behind it**: the numbers sat
one container away in Prometheus, which Node Monitor has been reading all along.

**nvidia-smi was NOT added to the worker image.** That would give the fleet two
telemetry paths that can disagree, on a system whose recurring defect is exactly
surfaces disagreeing about the same number. **One path.**

### 9.2 What was overlaid, and what deliberately was not

`GpuService._overlay_device_telemetry` fills `temperature_c`,
`gpu_utilization_pct` and `power_draw_w` from `collect_fleet_health` — the same
`node_health` module and the same Prometheus series Node Monitor uses — and sets
`telemetry_source` / `telemetry_reason` on the payload.

**`used_vram_mb` / `reserved_vram_mb` are NOT overlaid.** They are the
scheduler's reservation accounting (WP-60 Task 2b) — what it has promised
admitted jobs, which is a different fact from what the card physically holds, and
the two legitimately differ. That distinction cost WP-60 a task to establish.

Keyed on `raw_hostname`, not the display name: a node registered without
`IVGS_NODE_NAME` shows as `unnamed (61c7c02b3a…)` while its Prometheus
`instance` label is the real hostname. Matching the pretty string would silently
drop telemetry for exactly the nodes that need the most attention.

The overlay never raises; a failed probe leaves nulls and a reason, never
numbers.

### 9.3 A fifth site: `gpu_utilization_pct` was never passed at all

`_scheduler_node_response` constructed `GpuNodeResponse` with sixteen fields and
`gpu_utilization_pct` was **not one of them** — so the schema default supplied
`None` and the card said "not reported" whatever the registry held. WP-60 fixed
temperature and power on this constructor and this one was simply absent from
the list.

**No test of a default could ever have seen it**, which is why the test added
asserts on the **source** — the same reasoning WP-60 §21.1 reached one layer in.

### 9.4 Live, from the deployed API

```
node-02   temp=31.0  util=0.0  power=16.43  reserved_vram_mb=0  src=prometheus:nvidia-gpu-exporter
node-03   temp=None  util=None power=None   reserved_vram_mb=0  src=None
    reason: no GPU telemetry: Prometheus holds no nvidia-gpu-exporter series for
            this node. The node is reachable, so the exporter is not running or
            is not being scraped.
node-04   temp=34.0  util=0.0  power=20.52  reserved_vram_mb=0  src=prometheus:nvidia-gpu-exporter
```

Before this package all three read "not reported", permanently.

**node-03 is a real finding.** It is reachable and its GPU exporter is not being
scraped. Not fixed here — it is node-03, an operator paste-block node, and the
card now says which of the three possible reasons applies instead of blaming a
closed ledger entry. **WP61-L4.**

The card also prints one line naming its sources, because it carries two kinds
of number that are not interchangeable: *"Utilisation, temperature and power:
prometheus:nvidia-gpu-exporter. VRAM above is scheduler reservation, not a
device reading."* The three "not reported" tooltips — each of which told the
reader to check whether nvidia-smi succeeds on the node, a structurally
unreachable condition — now render the API's own per-node reason.

---

## 10. Deployment — node-01 only, WP-34 binding rules

`v5.20.0-qwen`, one coherent set across the three images this package touched.
GHCR is off the deploy path; artifacts under the standard name.

| Container | Image | Status |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.20.0-qwen` | healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.20.0-qwen` | healthy |
| `ivgs-celery-default` / `-composition` / `-beat` | `ivgs-workers:v5.20.0-qwen` | healthy |
| `ivgs-scheduler` | `ivgs-scheduler:v5.19.0-surfaces2` | unchanged, healthy |
| `ivgs-backup-worker` | `ivgs-backup-worker:v5.19.0-surfaces2` | unchanged, healthy |

WP-58 conformance gate: `OK: 54 artifacts conforming, 2 allowlisted`.

**`ivgs-scheduler` was deliberately NOT rebuilt.** Its image contains `shared/`,
so `binding.py` changed inside it — but the scheduler calls `resolve_endpoint`
nowhere, so the change is inert there, and WP-60 D-4 has already flagged that
this tag moved off a three-month pin. Rebuilding it to carry a no-op would move
it again for nothing.

**MIGRATION 0034 WAS APPLIED TO PRODUCTION**, before the API was recreated, and
it had to be: the ORM declares the two new columns, so a `SELECT` of
`language_variants` on a 0033 database fails with `column
language_variants.translation does not exist` — which is exactly how the test
tree failed before it was migrated. The database is at **0034**.

**A trap worth recording about the artifact path.** After adding
`wp61_publish_prompt.py` I rebuilt `ivgs-api` and re-ran
`save-image-artifact.sh`, which printed *"artifact already present, skipping
save"* — correct behaviour by its own P1.4j ruling, and it would have left the
banked artifact one build behind the tag. The stale artifact was removed and
re-saved. **Anyone rebuilding an image at a tag already banked must delete the
artifact first, or the recovery copy silently disagrees with what is running.**

**Nodes 02/03/04 need nothing.** No worker task code those nodes execute
changed: the retention and orphan repairs run on node-01's `celery-default`, and
`binding.py`'s stage parameter is inert until a translation binding is resolved.
Bringing them to the same tag is optional tidiness — and **node-03's service is
`cogvideox-worker`, not `celery-worker`.**

**node-05 was not touched by me, and nothing was read from it.** node-06 was not
touched at all.

---

## 11. Test evidence

Two full-suite passes were taken, which is the limit: one after the code was
written and one confirming pass after the baseline was updated. Everything
between was targeted. `SELECT count(*) FROM users` was 0 before both.

| Tree | Baseline (WP-60) | Now | Δ | New failures |
|---|---|---|---|---|
| `ivgs-api` | 911 / 0 / 0 / 0 | **953** / 0 / 0 / 0 | +42 | **0** |
| `ivgs-workers` | 823 / 18 / 48 / 15 | **838** / 18 / 48 / 15 | +15 | **0** |
| `ivgs-scheduler` | 35 / 20 / 0 / 0 | 35 / 20 / 0 / 0 | 0 | 0 |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | 4 / 0 / 0 / 0 | 0 | 0 |
| `tests_system` | 100 / 12 / 15 / 30 | **125** / 12 / 15 / 30 | +25 | **0** |
| **Total** | 1873 / 50 / 63 / 45 | **1955** / 50 / 63 / 45 | **+82** | **0** |

Verbatim from the confirming run:

```
ivgs-api             953 passed                                    in 271.45s
ivgs-workers         18 failed, 838 passed, 48 skipped, 15 errors  in  20.38s
ivgs-scheduler       20 failed,  35 passed                         in   1.28s
ivgs-backup-worker    4 passed                                     in   0.27s
tests_system         12 failed, 125 passed, 15 skipped, 30 errors  in   2.14s
```

**TEST-BASELINE_2026-08-25 is updated in the same commit as the tests that moved
its rows**, including the migration-0034 note and the three re-measured tree
sections.

Two tests were **inverted** (both WP-59's, both in `test_wp59_retention.py`) and
both are strictly stronger — the progression table is in §8.6 and in the
baseline. **No assertion was weakened, no skip marker added, no coverage
deleted.**

### 11.1 What each new module is actually for

* **`ivgs-api/tests/test_wp61_translation.py` (20)** — the contract. The
  assertions are about what the TEXT CONTAINS and what the STATE BECOMES, never
  about status codes, because the defect is a translation that comes back
  *improved*: nothing raises, every gate is green, and the deliverable disagrees
  with the English in a language nobody can read. The one that matters most is
  `test_the_marker_is_captured_AND_removed_from_the_deliverable` — recording the
  flag is no use if an English marker line is still in the Spanish text that
  goes to TTS.
* **`ivgs-api/tests/test_wp61_trigger_guard.py` (9)** — §7.2. Proven red by
  deleting the guard.
* **`ivgs-api/tests/test_wp61_surfaces.py` (13)** — node-05's row and the
  telemetry overlay; one asserts on the source (§9.3).
* **`ivgs-workers/tests/test_wp61_schedules.py` (15)** — both schedules and both
  structural refusals, including the negatives that keep the guards honest.
* **`tests_system/test_wp61_node05.py` (25)** — the real compose file and env
  template, plus `TestOperatorBlocksAreSafeToPaste`.

### 11.2 A gap in WP-60's own check, closed

`test_wp60_scripts.py::test_no_shipped_script_runs_a_docker_exec_heredoc_without_stdin`
globs `.sh` files. **The defect it was written for was in WP-59's operator
blocks, which are markdown** — so the test closing that hole could not see the
file the hole was in. `TestOperatorBlocksAreSafeToPaste` scans every
`WP-*-operator-blocks.md` for: a `docker exec` heredoc without `-i`, a bare
`exit` (which kills an interactive login session), a literal credential, and a
fenced block that does not declare its node in its first three lines. It runs
against WP-45's blocks as well as WP-61's.

### 11.3 An environment note

Running the workers tree **without** the `TEST_DATABASE_URL` block from
TEST-BASELINE §1 reports 52 skipped rather than 48: four
`test_wp60_orphan_guard.py` tests skip with *"TEST_DATABASE_URL is not set"*.
That is the environment, not a regression, and it briefly looked like one.

---

## 12. Ledger and register entries

**Phantom / inert-mechanism family:**

| # | Instance | Status |
|---|---|---|
| 9 | `run_orphan_cleanup` — beat dispatched a stub reporting SUCCESS nightly | **CLOSED** — the real task is on a weekly schedule, quarantine-only, and dispatched on the deployed image with its coverage reasons printed |
| 12 | **`prompts.prompt_type='translation'` — one row, created 2026-05-23, never rendered by anything.** A configured, versioned, editable prompt for a capability with no execution path. Its only appearance in worker code is a docstring recording it being selected *by mistake* | **PARTIALLY CLOSED** — it now has a consuming path, an amended contract and a route. It becomes a *pipeline* capability at the M3.3 cutover |
| 13 | **`periodic_tasks.get_beat_schedule()` — a second, drifting, uncalled beat schedule whose contents contradicted both live rulings** | **CLOSED** — returns `celery_app.CELERY_BEAT_SCHEDULE`; there is no second statement |

**New ledger entries:**

| id | Entry |
|---|---|
| **WP61-L1** | **Type-1 orphan scan has zero coverage and is excluded from the weekly sweep.** The filer namespace is empty; every object is a volume object addressed by fid and there is no supported way to enumerate the fid namespace. A design decision is owed. Until then the sweep is a Type-2/Type-3 backstop and must not be called a complete one. |
| **WP61-L2** | **`PromptPlayground`'s model list is transcribed from spec §7.1, not read from `/api/v1/models`.** The node-05 rows were corrected (they named three Ollama models this node has never run); `qwen2.5-72b` on node-02+node-03 and the tensor-parallel pairing remain unverified declarations. |
| **WP61-L3** | **The model-residency heatmap enumerates nothing.** `useMonitoring.ts` reads `model_residency`, which no API route produces. The tab has always rendered "No model residency data available". The scheduler's `/fleet` does publish `loaded_models` and `to_node_view` carries it, so it could be real. |
| **WP61-L4** | **node-03 serves no GPU telemetry.** Reachable, but Prometheus holds no `nvidia-gpu-exporter` series for it. Now visible on the GPU Fleet card with the right reason. node-03 is an operator paste-block node. |
| **WP61-L5** | **`models` row `Llama-3.3-70B-Instruct` (stage `translation`) has `dynamically_loadable = true`** and still points AD-01 binding at Llama for translation. Not edited — the Model Store is live data and outside this package's change scope. See D-3. |
| **WP61-L6** | **Qwen3.8-27B-FP8 is provenance-exceptional**: pulled directly from HuggingFace under the second operator exception, sha256-manifested, **not banked or certified by MBCP**. Work orders 5 and 7. |

---

## 13. What was NOT done, and why

* **No pipeline stage body for translation.** Task 3(a)'s stop condition was met
  and the ruling is explicit. §4.1.
* **The node-05 blocks were not executed**, and no acceptance figures are
  reported. Reporting numbers from a machine I did not touch would be the exact
  failure this series exists to remove.
* **The es-ES run (3(d)) was not executed.** It depends on node-05 serving and
  on the amended prompt being published, both of which are operator blocks. The
  contract *gate* was proven live against production instead (§0).
* **The Model Store's translation row was not edited.** It is live data.
  Changing it is D-3.
* **Storyboard and transcript were not moved off Llama.** Explicitly forbidden,
  and §5 explains what would break.
* **The scene-regenerate route was not guarded**, although it is the route the
  measured incident used. §7.3, D-1.
* **`ivgs-scheduler` was not rebuilt.** §10.
* **node-06 was not touched.** Out of bounds.
* **The model-residency heatmap was not built.** WP61-L3.

---

## 14. Decisions needed

### D-1 — the trigger guard covers `/trigger`; the incident used `/scenes/{id}/regenerate`

§7.3. The ruling names the trigger endpoint and that is guarded, tested and
deployed. But the six dispatches WP-60 measured were `video_generation` and
`animation_generation` job types, which `trigger_pipeline` does not produce —
they came through the scene-regenerate route, **which is still unguarded**.

The mechanism now exists: `ProjectService._active_job(project_id)` is one call,
and `StoryboardService.regenerate_scene` is where it would go. Whether a
regenerate should refuse while a run is in flight is a genuine product question
(regenerating one scene during an unrelated run is not obviously wrong), which
is why it is a decision and not an assumption.

### D-2 — the weekly orphan sweep's first live run is unattended

It is scheduled for **Monday 03:30 UTC**, and it acts (`dry_run=False`). Its
first real pass will be the first time this mechanism has ever quarantined
anything on this fleet. It cannot permanently delete, the shared-object guard is
mandatory and proven, and today's dry run found nothing to quarantine
(type2=0, type3=0 over 71 assets) — so the expected outcome is a no-op.

Worth knowing rather than deciding, unless you would prefer the first pass
attended: dispatching it by hand once before Monday would make it so.

### D-3 — the Model Store still routes translation to Llama

`models` holds `Llama-3.3-70B-Instruct` for stage `translation`, `approved`,
**`dynamically_loadable = true`**. Two things follow and neither was changed,
because the Model Store is live data:

1. An AD-01 binding for translation still resolves *Llama*, not Qwen. The
   execution path this package built does not use that binding — it dials the
   stage-scoped endpoint directly — so nothing is broken today, but the two will
   disagree the moment a Temporal activity uses `get_binding`.
2. `dynamically_loadable = true` contradicts the AD-02 rule this package leans
   on everywhere else. vLLM binds its model at container start; nothing on this
   fleet can load a translation model on demand.

Registering Qwen properly is blocked on WP61-L6 (MBCP must certify the bundle). The
decision is whether to correct the *flag* now and register the *model* later, or
to wait and do both at certification.

### D-4 — node-03 has no GPU telemetry

§9.4, WP61-L4. It is reachable and its exporter is not being scraped. node-03 is an
operator paste-block node, so this is a paste block, not a change. It is a
one-container fix on the same pattern nodes 02 and 04 already run.

---

## 15. Push block — COMMITTED AND HELD, NOT PUSHED

Nothing is pushed. Run the gate first; it is a gate, not a formality.

```
# RUN ON: node-01 (192.168.1.90).
# READ-ONLY GATE. It pushes nothing. It re-measures the counts this report
# claims and prints PASS or FAIL against them.
(
  set -u
  cd /opt/ivgs || { echo "ABORT"; return 0 2>/dev/null || exit 0; }
  PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
  PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
  export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
  export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
  export PGPASSWORD="$PGPW"

  N=$(psql -h 192.168.1.90 -U "$PGUSER" -d ivgs_reconciliation_test -At -c "SELECT count(*) FROM users;")
  M=$(psql -h 192.168.1.90 -U "$PGUSER" -d ivgs_reconciliation_test -At -c "SELECT version_num FROM alembic_version;")
  echo "test db: users=$N  migration=$M   (want users=0, migration=0034)"
  if [ "$N" != "0" ]; then
    echo ">>> The test database is DIRTY - residue from a killed run. The next"
    echo ">>> number will be wrong. TRUNCATE or re-run the failing module alone."
    unset PGPASSWORD; return 0 2>/dev/null || exit 0
  fi
  if [ "$M" != "0034" ]; then
    echo ">>> The test database is not at 0034. ivgs-api will fail with"
    echo ">>> 'column language_variants.translation does not exist'."
    unset PGPASSWORD; return 0 2>/dev/null || exit 0
  fi
  unset PGPASSWORD

  echo; echo "=== re-measuring. ivgs-api takes about 4.5 minutes. ==="
  A=$(.venv/bin/python -m pytest ivgs-api/tests -q 2>&1 | tail -1)
  W=$(.venv/bin/python -m pytest ivgs-workers/tests -q 2>&1 | tail -1)
  S=$(.venv/bin/python -m pytest ivgs-scheduler/tests -q 2>&1 | tail -1)
  B=$(.venv/bin/python -m pytest ivgs-backup-worker/tests -q 2>&1 | tail -1)
  T=$(.venv/bin/python -m pytest --timeout=120 tests_system -q 2>&1 | tail -1)
  printf 'api        %s\nworkers    %s\nscheduler  %s\nbackup     %s\nsystem     %s\n' \
    "$A" "$W" "$S" "$B" "$T"

  OK=1
  echo "$A" | grep -q '953 passed'                                  || { echo "FAIL api";       OK=0; }
  echo "$W" | grep -q '18 failed, 838 passed, 48 skipped'           || { echo "FAIL workers";   OK=0; }
  echo "$S" | grep -q '20 failed, 35 passed'                        || { echo "FAIL scheduler"; OK=0; }
  echo "$B" | grep -q '4 passed'                                    || { echo "FAIL backup";    OK=0; }
  echo "$T" | grep -q '12 failed, 125 passed, 15 skipped'           || { echo "FAIL system";    OK=0; }

  echo
  if [ "$OK" = "1" ]; then
    echo "GATE PASS - 1955 / 50 / 63 / 45, zero new failures against the baseline."
    echo "Commits held on main:"
    git log --oneline origin/main..HEAD
    echo
    echo "Push with:   git push origin main"
    echo
    echo "AFTER PUSHING, node-05 can be provisioned:"
    echo "  dev/workpackages/WP-61-operator-blocks.md   A05 -> A06 -> A07 -> A08 -> A09 -> A10"
    echo "  then N01-A (publish the amended prompt) and N01-B (the es-ES run)."
  else
    echo "GATE FAIL - do not push. A count moved; find out which and why first."
  fi
)
```

---

## 16. One closing observation

Three of this package's tasks were about a mechanism being turned on, and in
every one of them the interesting work was not the switch. It was establishing
what stops the switch going further than it was told to: `allow_delete`,
`quarantine_only`, the missing `nvidia-smi`, the gate that refuses a translation
under the wrong prompt.

And the sharpest thing found was not in the system at all. It was a test I wrote
for the render guard that **passed without the guard** — six of eight green with
the fix deleted. The series of packages that keeps finding surfaces which report
health they do not have produced, in the middle of a fix for one, a test that
reported a property it was not measuring. It is recorded in §7.2 and in the
module's own docstring rather than quietly corrected, because the pattern is the
point: an assertion is only worth what it fails on.
