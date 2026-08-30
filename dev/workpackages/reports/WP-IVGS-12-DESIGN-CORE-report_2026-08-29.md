# WP-IVGS-12 — Phase 1: THE DESIGN CORE

**Report, 2026-08-29 · node-01 · commit and HOLD · report written as the work proceeds**

Charter: `dev/design/IVGS_Root_Cause_Audit_and_Recovery_Plan_2026-08-29.md` §1 RC-A (as
rewritten) and §4 Phase 1. Normative source: `dev/design/Instructional_Design_Foundation_for_IVGS_2026-08-29.md`.
Operator rulings R1, R1a, R1b, R2, R5 of 2026-08-29 are binding on this package.

---

## STATE AT SESSION END

| | |
|---|---|
| **Done** | Task 0 (a)-(d) measured; Tasks 1-6 built and deployed; Task 7 run to the gate three times and the test project deleted. Migrations **0046-0049** on production and on the test DB. **v8** plus **two SYSTEM prompts** published through the WP-63 lineage. Eight containers on `v5.37.0-design-core` across nodes 01-04, images compared by ID. **ZERO NEW FAILURES**, two full-suite runs |
| **Mid-way through** | Nothing. The package is at its Task-7 stop point |
| ⛔ **ACCEPTANCE: NOT MET, and deliberately not chased** | Structural validity ✅ three times; the Gagné arc reaches application ✅ three times; **zero hard refusals ✗ — one per generation, the same one.** Cause is **RC-Q9**: the designer paraphrases the operator's outcomes and drops one, all three times, and nothing can currently catch it. Rowed, not built. I did not iterate the prompt against three runs of one script |
| **Package now stale because of this report** | **Task 4's "guided_json"** — the mechanism is `response_format: json_schema` (§1.3); the audit and the Foundation are bannered. **Task 6's "per-scene header"** — ships as a table keyed by scene number, because no seam carries scene identity (RC-Q6). **Task 3's `talking_head`** — Foundation §4/§8 conflict with the code and were ruled (RC-Q4) |
| **Not yet written down anywhere else** | **RC-Q8** — `save-image-artifact.sh` ships stale bytes when a tag is rebuilt and `DEPLOY VERIFIED` cannot see it; comparing `.Image` IDs across nodes is the only check that catches it. **The two-doors import defect recurred**, and a module-level `sys.path` anchor did NOT suffice where the in-handler `__file__` anchor did — cause not established, diagnostic now permanent |
| **Held** | **1 commit.** Nothing pushed |

**Verified live vs inferred (`dev/CLAUDE.md` §12):**

- **Executed and observed:** every vLLM probe (against the pinned digest, asserted
  from `.Config.Image` before probing); the migration chain up, **down and up
  again** with rows present; all six CHECK-constraint cases; the full acceptance
  run end to end; the WP-59 deletion; every deploy, with image IDs compared
  across nodes; both full test suites.
- **Read, not executed:** nothing load-bearing. ⛔ **NOT VERIFIED, and named:**
  the *rendered* gate panel — the design brief is described in §9.3 from the live
  `GET /design-review` payload and from the component source, **not from a
  browser screenshot**; no headless browser was driven. The payload is banked so
  the description is checkable, but **whether the panel LOOKS right on screen is
  unverified and is part of the operator's watch.**
- **NOT verified:** that any of this improves a rendered video. The package stops
  at the storyboard gate by instruction; no media stage ran.

---

## §0 Premises of the package, checked before acting

`dev/CLAUDE.md` §0 rule 5 closing clause — verify the package's own factual premises first.

| Premise (from the order or the board) | Checked | Verdict |
|---|---|---|
| Held commits = 1 (`70058b9`), per the WP-IVGS-10 board row | `git log --oneline origin/main..HEAD` → **empty**; `origin/main` = local `HEAD` = `af0c6a1` | ⚠ **STALE. Held count is 0**, not 1 and not the 3 the WP-IVGS-11 report declared. The operator pushed `70058b9`, `a6bb30c` and `af0c6a1` after that report closed |
| Alembic head is 0045 | `alembic_version` in `ivgs` = **0045**; tree's highest is `0045_wp_ivgs_10_scene_content_contract.py`, `down_revision="0044"`, chain 0039→0045 contiguous | ✅ **TRUE.** Next free number is **0046** |
| The learning-outcomes form field exists (R1b) | `migrations/versions/0037_wp64_learning_outcomes.py:49`; `models/project.py:70`; `LearningOutcomesPanel.tsx:54`; `projects/new/page.tsx:239` | ✅ **TRUE.** No new field is needed, exactly as R1b says |
| v7 is the active storyboard prompt | `prompts` row `6907e7b1-fccd-4b66-92e3-154f90a30430`, `is_active = t` | ✅ **TRUE** (detail in §1.2) |
| The scene contract post-RC-P1 carries 11 keys | measured on live checkpoints (§1.4) | ✅ **TRUE** |
| Nodes 01–04 are deployable under §6.1a | **nodes 02, 03, 04 are OFFLINE** (§1.3) | ⛔ **FALSE AS OF 05:39 UTC TODAY.** See §1.3 — this is the package's first stop point |
| `dev/design/` is tracked | `git status --porcelain` → `?? dev/design/` | ⚠ **UNTRACKED.** The two documents this package is built FROM are not in git. Flagged in §Y — a report citing an uncommitted file is uncheckable |

---

## §1 TASK 0 — the ground, measured

### 1.1 (a) The learning-outcomes hand-off, end to end, today

**The path, with file:line at every hop.**

| # | Hop | Where | What travels |
|---|---|---|---|
| 1 | Operator types the outcomes | `ivgs-frontend/src/app/projects/new/page.tsx:239` (create) and `ivgs-frontend/src/components/project/LearningOutcomesPanel.tsx:54` (edit, PATCH) | free text, or `null` when blank |
| 2 | API schema | `ivgs-api/app/schemas/project.py:40` (create), `:70` (update), `:112` (read) | `Optional[str]` |
| 3 | Column | `ivgs-api/app/models/project.py:70`; migration `0037_wp64_learning_outcomes.py:49` | `projects.learning_outcomes`, nullable `TEXT` |
| 4 | Dispatch (normal run) | `ivgs-api/app/services/project_service.py:487-489` | `job_context["learning_outcomes"]`, **omitted entirely when empty** |
| 4b | Dispatch (gate regenerate) | `ivgs-api/app/services/regeneration.py:128-130` | same key, same omit-when-empty rule |
| 5 | ⛔ **The fold** | `ivgs-workers/tasks/pipeline_orchestrator_v2.py:1186-1194` calling `_description_with_outcomes` at `:1256-1288` | outcomes are **concatenated into `project_description`** between the delimiters `OUTCOMES_OPEN` / `OUTCOMES_CLOSE` (`:1252-1253`) |
| 6 | Stage 2 receives | `StoryboardGenerationInput.job_context.project_description` (`models/task_result.py:363-370`) | one string: description `\n\n` delimiter-block |
| 7 | Into the prompt | `ivgs-workers/tasks/stage2_storyboard.py:130` — `project_description=context.get("project_description", "")` | the model sees the block only if v7's RULE 0 spots the delimiter |

**The fold is scoped to the storyboard branch only** (`pipeline_orchestrator_v2.py:1186`), so stage 3's
FLUX prompt writer does not receive it. That was deliberate and is correct.

⛔ **Why it is parked (P2.66), measured rather than quoted.** The user template is rendered by
`_render_user_prompt` (`stage2_storyboard.py:114-145`), whose `template.render(...)` call at
`:128-137` passes **exactly nine names**:

    project_title, project_description, target_audience, max_duration_seconds,
    total_runtime_seconds, combined_transcript, transcript_count,
    target_scene_count, language_code

`learning_outcomes` is not among them, and `jinja_env` is built with the default undefined, so a
`{{ learning_outcomes }}` in the published template renders as the empty string rather than
raising. `stage2_storyboard.py` is one of the eight stage bodies `dev/CLAUDE.md` §3 freezes, so a
tenth name cannot be added by editing. **The orchestrator's own docstring states this
correctly** (`pipeline_orchestrator_v2.py:1261-1268`) and it is accurate to the line.

### 1.2 (b) The prompt stack in force

**Storyboard — the ACTIVE row is v7 and nothing later exists.**

| field | value |
|---|---|
| id | `6907e7b1-fccd-4b66-92e3-154f90a30430` |
| prompt_type | `storyboard_generation` |
| version | **7** |
| is_active | **true** (v1–v6 all false) |
| project_id | `NULL` — global, not project-scoped |
| length | **31,848 characters** |
| created_at | 2026-08-29 00:46:11 UTC |
| created_by | `wp-63-validator+wp-64-media` |

Full text banked at `dev/workpackages/reference/wpivgs12-prompt-stack/v7_storyboard_user.txt`
(541 lines) so that v8 can be diffed against it by anyone reading this report.

⚠ **Only the USER template comes from the database.** `_resolve_prompts_from_api`
(`stage2_storyboard.py:146-181`) returns `(None, user_template)` and says why in its own
docstring at `:151-153`: *"a PromptType row carries exactly one text, so the API can only supply
the user template."* The SYSTEM prompt is always the file `ivgs-workers/prompts/stage2_system.j2`
baked into the workers image (`stage2_storyboard.py:95-101`). **Two publishing surfaces, one
lineage** — the WP-63 versioning discipline governs only half of the stage-2 prompt.

**Stage 1 in force.**

| slot | source | value |
|---|---|---|
| system | file `ivgs-workers/prompts/stage1_system.j2` | 58 lines. Orders the model to *"transform raw transcripts into refined, audience-appropriate narrations"*, *"Remove extraneous information"*, *"Structure refined content to fit within the allocated video duration"*, *"If the refined content significantly exceeds the time budget, prioritize core concepts and note omissions"* |
| user | DB row `8ef57fec-41b0-4bde-be73-138b8118cfb8`, `transcript_refinement` **v2**, active, 751 chars, `WP-IVGS-0 F6`, 2026-08-22 | (the file fallback is `prompts/stage1_user.j2`) |

⛳ **The audit's §1 RC-A opening sentence is confirmed to the line.** The stage-1 system prompt
is a compressor by explicit instruction, and it is the same instruction whether the transcript
was generated by the system or uploaded finished by the operator — `transcripts` has **no column
recording which** (`\d transcripts`: `id, project_id, sequence_order, original_asset_id,
refined_text, language_code, created_at, updated_at`). `original_asset_id` is the only signal,
and it is nullable with no constraint tying it to an upload.

### 1.3 (c) vLLM structured output — MEASURED, and the audit's prescription is a NO-OP

⚠ **This section was written twice.** The first pass could not probe: nodes .91–.95 were all
off the network between **05:38:58** and the operator's restore at ~11:20 UTC. That outage is
now explained and closed — see §1.3.3. The measurement below was taken **after** the restore,
against the engine the pin names.

**Provenance of the probe target, asserted before probing** (`dev/CLAUDE.md` §6 — never believe
a tag):

    node-02  docker inspect ivgs-vllm-primary --format '{{.Config.Image}}|{{.Image}}'
      vllm/vllm-openai@sha256:3dbe092ec5b2cef63b6104d33fa75d6ce53a7870962529ada69f78bbbc38e776
      sha256:3dbe092ec5b2cef63b6104d33fa75d6ce53a7870962529ada69f78bbbc38e776

**Config.Image and the resolved Image are the same digest, and it is the pinned one.** Serving
`RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic` as `llama-3.3-70b`, `--max-model-len 32768`.
Engine version read from inside the container:

    docker exec ivgs-vllm-primary python3 -c "import vllm; print(vllm.__version__)"
      0.19.2rc1.dev134+gfe9c3d6c5

⚠ **`python` is not on PATH in that image; `python3` is.** Noted because the obvious command
fails with `executable file not found` and reads like a broken container.

#### 1.3.1 The result

Probe banked at `reference/wpivgs12-prompt-stack/vllm_structured_output_probe.py`, output at
`vllm-probe-2026-08-29.txt`. Every case uses one trivial schema that is **hostile on purpose** —
a closed enum `["alpha","beta"]`, a required integer, `additionalProperties: false` — against a
prompt that begs the model to answer `GAMMA`, add an extra key, and write a preamble.
**ACCEPTED and ENFORCED are measured separately**, because a server that ignores an unknown
field returns 200 and unconstrained text.

| mechanism | HTTP | accepted | enforced | evidence |
|---|---|---|---|---|
| *(none — baseline)* | 200 | — | ⛔ no | prose preamble, not JSON |
| `response_format: {"type":"json_object"}` **← what ships today** | 200 | yes | ⛔ **NO** | JSON, but `verdict: "GAMMA"` — enum violated |
| ⛔ **`guided_json`** | 200 | yes | ⛔ **NO** | **byte-identical to the unconstrained baseline** |
| ⛔ **`guided_json` + `guided_decoding_backend: xgrammar`** | 200 | yes | ⛔ **NO** | byte-identical to baseline |
| ✅ **`response_format: {"type":"json_schema", strict:true}`** | 200 | yes | ✅ **YES** | `{"verdict": "alpha", "count": 1}` |
| ✅ **`structured_outputs: {"json": …}`** | 200 | yes | ✅ **YES** | `{"verdict": "alpha", "count": 1}` |

⛔ **`guided_json` IS ACCEPTED WITH HTTP 200 AND SILENTLY IGNORED.** This is the single most
important measurement in Task 0. The audit's RC-A step 4 says in as many words that *"the design
contract is emitted under vLLM `guided_json`"*. **On the pinned engine that would have shipped a
permanent no-op that returns 200 forever** — the exact failure class RC-E is named after, and
one no test asserting "the call succeeded" could ever catch.

#### 1.3.2 The confirmation — two questions the first probe left open

Banked at `vllm_probe_confirm.py` / `vllm-probe-confirm-2026-08-29.txt`.

**A. Is `guided_json` ignored, or just losing a fight with a stubborn model?** Decisive test: give
the field something that is not a schema. A server that READS it must reject.

| sent | result |
|---|---|
| `guided_json: {"type": "not_a_json_type"}` | **HTTP 200**, `'GAMMA.'` |
| `guided_json: 12345` *(not even a dict)* | **HTTP 200**, `'GAMMA.'` |
| `guided_choice: ["alpha","beta"]` | **HTTP 200**, `'GAMMA.'` |
| `ivgs_field_that_cannot_exist: {...}` *(control)* | **HTTP 200**, `'GAMMA.'` |

⛳ **The legacy field is indistinguishable from a field that does not exist.** This engine
discards unknown top-level body members without comment. `guided_json` and `guided_choice` are
dead on `sha256:3dbe092e…`, and they die quietly.

**B. Does `json_schema` still enforce on a REALISTIC contract shape?** A trivial schema proves
nothing about the one this package needs. Probed with a nested Design-Contract skeleton —
`outcomes[]` with `minItems:1`, `scenes[]` with `minItems:2`, two closed enums (five media types,
nine Gagné events), `serves_outcomes` as a required array with `minItems:1`, and provenance as a
**`oneOf`** of `{source_refs[]}` versus `{origin:"designed", rationale}` — against a prompt
demanding `media_type: "hologram"`, `instructional_event: "warmup"`, an extra `notes` key and a
preamble:

    http=200  finish_reason=stop  scenes=2  outcomes=1
      media_type       -> ['image', 'image']          (asked for 'hologram')
      instructional_ev -> ['present', 'practice']     (asked for 'warmup')
      provenance keys  -> [['source_refs'], ['source_refs']]
      extra scene keys -> []                          (asked for 'notes')
      serves_outcomes  -> [['add-2-digit-numbers'], ['add-2-digit-numbers']]

✅ **Closed enums held against an adversarial prompt, `oneOf` resolved to a legal branch,
`additionalProperties:false` dropped the requested key, `minItems` satisfied, no preamble,
`finish_reason=stop`.** The mechanism the Design Contract needs works on the pinned engine at
the shape the Design Contract actually has.

#### 1.3.3 Verdict — no operator ruling is required here

**The order's stop point does not trigger.** It asks the operator to choose between a digest
upgrade and schema-by-validation *if the pinned engine cannot constrain*. **It can.** What it
cannot do is constrain via the field the audit named. So:

- **Task 4's mechanism is `response_format: {"type":"json_schema", "strict": true}`.**
  `structured_outputs` measured equivalent and is held in reserve; `guided_json` is **forbidden
  in this codebase** and gets an explicit refusal rather than a silent 200 (§5.4).
- **No digest change. The WP-62 pin discipline is untouched** — `sha256:3dbe092e…` stands.
- ⚠ **The audit is superseded on this point.** `IVGS_Root_Cause_Audit_and_Recovery_Plan_2026-08-29.md`
  §1 RC-A step 4 and §4 Phase 1 both name `guided_json`. **Bannered in that file** rather than
  silently reinterpreted (`dev/CLAUDE.md` §0 rule 5 step 3).

#### 1.3.4 The outage, and RC-I4

⛳ **Cause supplied by the operator and recorded: a nightly operator power-down.** That closes
**RC-I4**, which had recorded the 2026-08-28 coordinated boot of nodes 02–05 (.94 02:31:48,
.91 02:32:41, .93 02:34:31, .92 03:16:11) with the cause explicitly *not established*. This
session produced a **second** coordinated event of the same shape — node-02 05:38:58.901881Z,
node-04 ~05:39:15, node-03 ~05:39:31, all inside 33 seconds, with .94 and .95 alongside — and
one cause now explains both. `OUTSTANDING_WORK.md` RC-I4 updated; no unattended-upgrades theory
survives.

### 1.4 (d) The scene contract as deployed

**`storyboard_scenes`, 16 columns, live:**

    id, project_id, scene_index, narration_text, visual_description, media_type,
    duration_seconds, created_at, updated_at, camera_angle, transition_type,
    effects (jsonb), timing_offset_ms, generation_params (jsonb),
    media_rationale (text), text_carried_by (varchar 16)

with `ck_storyboard_scenes_text_carried_by CHECK (text_carried_by IS NULL OR
text_carried_by = 'narration')` and `ix_storyboard_scenes_project_index (project_id, scene_index)`.

**The checkpoint payload post-RC-P1 — measured, not quoted.** Distinct keys across every scene
in every `storyboard_generation` checkpoint written in the last two days:

    duration_seconds, generation_params, media_rationale, media_type,
    narration_text, notes, scene_index, scene_title, text_carried_by,
    transition, visual_description

**Eleven keys**, confirming the board's "8 keys to 11". The envelope around them is
`StoryboardGenerationOutput.to_checkpoint_data()` (`models/task_result.py:403-406`) — a plain
`model_dump` plus `stage`, so the checkpoint's top level is
`job_id, project_id, status, scenes, total_scenes, total_duration_seconds,
total_input_tokens, total_output_tokens, processing_time_seconds, model_used,
idempotency_hash, scene_ids, errors, completed_at, stage`.

⛔ **AND HERE IS THE FINDING THAT SHAPES TASKS 1 AND 3.** The eleven keys are not a passthrough.
They are **two hard-coded name lists inside the frozen body**, and every one of the Design
Contract's new scene fields dies at both of them unless something is done:

| # | Site | What it is |
|---|---|---|
| 1 | `stage2_storyboard.py:314-357` | an explicit **eleven-keyword** `StoryboardScene(...)` constructor. `extra="allow"` on the model is irrelevant: extras are kept only when SUPPLIED, and the raw scene dict is never splatted |
| 2 | `stage2_storyboard.py:467-492` | the POST payload — five keys, then a **fixed three-name tuple** `("generation_params", "media_rationale", "text_carried_by")` |

Freeze exception #2's own comment at site 1 predicted this in as many words:
*"the cost is stated rather than hidden: a v8 field needs this line again."*

⚠ **`_validate_storyboard_json` is handed the WHOLE parsed object**, not just the scenes array
(`stage2_storyboard.py:736-739` passes `parsed_json`; the function unwraps `scenes` /
`storyboard` at `:210-213`). So project-level contract members — `outcomes[]`,
`dropped_beats[]`, `evidence_map` — are visible at that boundary and are discarded there
unread. That is the seam Task 1 has to use.


---

## §2 ⛔ THE FINDING THAT IS BIGGER THAN THE AUDIT SAYS

The recovery plan's §0 says stage 1 paraphrases a finished script. **It also
destroys it**, and that second half is why nobody ever caught the first.

**One creation path writes a `transcripts` row** —
`TranscriptService.upload_transcripts` (`transcript_service.py:157`) — and it
puts the text extracted from the uploaded file into **`refined_text`**. Stage 1
then READS that column (`stage1_transcript.py:208`) and PATCHes its own output
back into it (`:241`). There is no `original_text` column; the worker's
`TranscriptRecord.original_text` is populated *from* `refined_text` and is
therefore not the original at all. The orchestrator's own docstring calls the
column *"dual-purpose: raw until the refinement stage overwrites it"*
(`pipeline_orchestrator_v2.py:1858`) — the defect was written down as a design.

**Measured 2026-08-29 on the operator's own projects. One 3,172-byte upload:**

| project | `refined_text` now | fraction of the upload |
|---|---|---|
| `4ca0d5c5` (live, at the storyboard gate) | **1,866 chars** | 59% |
| `9c29b1d1` (archived) | **1,851 chars** | 58% |
| `c12fa967` | **1,615 chars** | 51% |

Same source file — the asset row is 3,172 bytes on all three — **three different
paraphrases, and not one byte of the script survives in the database.**

⛳ **THIS IS WHY RECOVERY-PLAN §3 ITEM 4 HAPPENED.** *"A rewriting stage 1 sat
undiagnosed because nobody compared output narration to input script — including
me."* **The comparison was not possible.** The input was gone by the time anyone
looked, and it is gone on a re-run twice over: stage 1 refines its own previous
output, so a resumed project is a paraphrase of a paraphrase.

⚠ **AND A FOURTH ROW SHOWS THE SAME COLUMN HOLDING SOMETHING THAT WAS NEVER A
TRANSCRIPT.** Project `0361c667`: `refined_text` is
*"Sure! Please provide the raw transcript you'd like me to refine."* — **64
characters where a 540-byte upload used to be.** The model's chat pleasantry was
written over the operator's file and recorded as success. **This is a new
instance of the WP-00 swallowed-failure class and it is rowed there.**

**The fix, and it is why migration 0046 does more than the directive asked.**
`transcripts.source_text` is the extraction as uploaded, written once by the
upload path and by nothing else. Every `source_refs` character span in the
Design Contract indexes into **that** column — an offset against a string that
is rewritten between the write and the read means nothing — and it is what the
gate shows beside a rewrite under ruling R1a. ⛔ **It is deliberately NOT
backfilled**: copying today's `refined_text` into it would enshrine the
paraphrase AS the original and destroy the only evidence that the two differ.
Recovery from the SeaweedFS asset is an opt-in script, not a migration.

---

## §3 ⚠ TWO CONFLICTS WITH THE NORMATIVE SOURCE, FLAGGED NOT SILENTLY CHOSEN

The order requires that where the Foundation conflicts with code reality I
flag rather than choose. Two do.

### 3.1 ⛔ `talking_head` IS NOT A MEDIA TYPE, AND WRITING IT WOULD KILL THE RUN

Foundation §4's modality table has a row *"`talking_head` overlay scenes —
events 1, 2, 7, 9 are its natural home"*, and §8's worked application assigns it
to scenes 0 and 1. **The system has no such media type.**

    MediaType / MEDIA_TYPES  : image, video_clip, animation, motion_graphics
    PostgreSQL enum media_type: image, video_clip, animation, motion_graphics
    MEDIA_TYPE_SYNONYMS      : eight spellings, none of them talking_head

The talking head is a **pipeline STAGE** (stage 6) that renders once and is
composited as an overlay across the whole video (`enable_talking_head: True` on
the manifest), not a per-scene choice. And a scene claiming an unknown media
type does not degrade: `_validate_storyboard_json` **raises**, by design
(`stage2_storyboard.py:304-311`), and **one such scene fails the entire
storyboard** — which is exactly what ledger **RC-P4** records happening the
first time a storyboard model ever chose a value the enum lacked.

**Taken here:** v8 does NOT offer `talking_head`. It carries an explicit
refusal instead, naming RC-P4, and RULE 13 routes human/social moments to
`image` — the one place a plain still is the right answer rather than a failure
of nerve. **The Design Contract schema was already correct**, because it closes
its media enum from `MEDIA_TYPES` rather than from the Foundation's prose.

⛔ **OPERATOR DECISION, NOT TAKEN HERE:** whether per-scene presenter selection
should EXIST. Foundation §4 is pedagogically right that social presence serves
events 1/2/7/9, and the system cannot express it. That is a real capability gap
and it is a Phase-5 or AD-08-shaped question, not a Phase-1 prompt edit.

### 3.2 `modality_rationale` ALREADY EXISTS AND IS CALLED `media_rationale`

Foundation §6 lists `modality_rationale (one line, §4 table row)` as a new
per-scene field. v7's RULE 9 asked for exactly that question — why THIS medium
for THIS scene — and migration 0045 gave it the column `media_rationale`.

**Taken here: one fact, one column, the existing name.** Adding a second column
would create the drift class this repository has been bitten by repeatedly (the
WP-64 delimiter; RC-C's four sources of truth). The Foundation is normative on
WHAT must be declared, not on what a declaration is called when it already has a
name. Recorded in migration 0048's docstring as well as here.

---

## §4 TASK 1 — the Design Contract (schema + storage)

**Three migrations, each single-purpose, each with a REAL downgrade.** Head was
`0045` in the tree and `0045` in the database, both verified by me before
numbering: next free was 0046.

| # | what | downgrade |
|---|---|---|
| **0046** | `transcripts.source_text`, `.source_kind` + CHECK; `source_kind` backfilled from asset provenance | drops both columns and the CHECK — **and it is genuinely lossy**, which the docstring says rather than pretends otherwise |
| **0047** | two `prompt_type` members: `transcript_refinement_system`, `storyboard_generation_system` | **rebuilds the enum** without them, deleting the rows that use them first and loudly. Unlike 0041's documented no-op |
| **0048** | seven design columns on `storyboard_scenes` + four CHECKs + the `storyboard_design_briefs` table | drops all of it; the five original scene columns are untouched throughout |

**Verified on a scratch database, both directions, with rows present:**

    upgrade   0001 -> 0048  clean, 48 migrations
    (insert rows on both new prompt_types, a brief, a transcript with source_text)
    downgrade 0048 -> 0045  prompt_type members 13 -> 11, prompts rows 2 -> 0,
                            brief table gone, 7 scene columns gone, 2 transcript
                            columns gone, FIVE ORIGINAL SCENE COLUMNS INTACT
    upgrade   0045 -> 0048  clean, 3 migrations re-applied, head 0048

### 4.1 ⛔ A DEFECT I SHIPPED INTO MY OWN CHECK, AND THE MEASUREMENT THAT CAUGHT IT

The `source_refs XOR origin:designed` rule is a CHECK constraint. My first
draft read:

    scene_origin IS NULL
    OR (scene_origin = 'designed' AND source_refs IS NULL)
    OR (scene_origin = 'sourced' AND jsonb_typeof(source_refs) = 'array'
        AND jsonb_array_length(source_refs) > 0)

**It ACCEPTED the row it exists to refuse.** A scene with `scene_origin =
'sourced'` and `source_refs` NULL evaluates the third branch to NULL
(`jsonb_typeof(NULL)` is NULL), the disjunction becomes `FALSE OR FALSE OR
NULL` = **NULL**, and **a CHECK constraint PASSES on NULL**. Three-valued logic
turned the strictest branch into the weakest one.

Caught by testing all six cases rather than the happy one. `source_refs IS NOT
NULL` added, re-measured from a fresh database:

| case | want | got |
|---|---|---|
| `sourced` + NULL refs | REFUSED | ✅ REFUSED |
| `sourced` + empty array | REFUSED | ✅ REFUSED |
| `designed` + refs present | REFUSED | ✅ REFUSED |
| `designed` alone | ACCEPTED | ✅ ACCEPTED |
| `sourced` + one real ref | ACCEPTED | ✅ ACCEPTED |
| declares nothing (every pre-Design-Core row) | ACCEPTED | ✅ ACCEPTED |

plus `instructional_event='warmup'` REFUSED, `bloom_level='synthesise'`
REFUSED, and the partial unique index refusing a second ACTIVE brief per
project while accepting a superseded one.

### 4.2 The storage shape, argued from how the gate reads it

Per-scene facts (event, bloom, serves, provenance, signalling) go on
`storyboard_scenes`, because the gate already SELECTs those rows and renders a
panel per scene — `media_rationale`/`text_carried_by` set that precedent, and a
join to fetch an event name would buy nothing.

Whole-design facts (outcomes, dropped beats, evidence map) go in **one row of a
new table**, because they are a document: they have no scene to hang on, they
are what the reviewer approves, and **a regeneration must not silently
overwrite the design the reviewer is reading.** That is not hypothetical —
RC-E records the Regenerate button discarding a storyboard with no confirmation
and no record. One row per design, `is_active` marking the current one under a
partial unique index, is the `prompts` lineage shape and it is chosen for the
same reason.

---

## §5 TASK 4 — constrained decoding, and the seam that carries the result

### 5.1 The mechanism

`response_format: {"type": "json_schema", "strict": true}`, per §1.3.
`guided_json` is **refused by name** in `design_core/contract.py` with the
measurement in the message, because the recovery plan's text will outlive this
session and the refusal has to live where its reader reaches.

**The real 7.9 kB contract schema was probed against the pinned engine, not
assumed from the toy one.** Nested `oneOf` provenance, five closed enums,
`minItems`, `additionalProperties:false` throughout, against a prompt demanding
`media_type: "hologram"`, `instructional_event: "warmup"`, an extra key and a
preamble:

    HTTP 200 in 72.8s   finish_reason=stop   completion_tokens=1533
    enum violations: 0    scenes with no serves_outcomes: 0    extra keys: 0

⛳ **AND THE PROBE EARNED A SCHEMA CHANGE.** With `measurable` and
`proposed_refinement` as independent members, the model returned
`measurable: true` **and** a non-null refinement for both outcomes — the gate
would have shown the operator a refinement to approve for an outcome that needed
none. The outcome schema is now a two-branch `oneOf`, which makes the
contradiction **ungrammatical** rather than merely discouraged, using the
construct §1.3.2 measured working.

⚠ **The probe also shows what a schema CANNOT do**, and it is the whole
argument for Task 3: with a thin prompt the emission was 4 scenes, all four
`origin: "designed"` (the script unused), no event outside `present`/`guide`,
and not one `motion_graphics` for pure symbolic mathematics. **Structure is
enforceable; quality is prompt-work.** Banked at
`reference/wpivgs12-prompt-stack/design-contract-probe-emission.json`.

### 5.2 The seam — approved by the operator, and NO exception #3

The contract cannot survive a trip through `stage2_storyboard.py`: an
eleven-keyword constructor at `:314-357` and a fixed three-name tuple at
`:467-492`, both frozen, and freeze exception #2's own comment predicts it
(*"a v8 field needs this line again"*). Ruling R5 says prefer a wrapper. The
route the operator approved uses **three owned modules and no runtime patching**:

1. `celery_app.on_task_prerun` arms `design_core.capture` from the task's own
   payload, and — for stage 2 only — arms the response-format schema, because
   the frozen body passes none and cannot be made to.
2. `VLLMClient` gains `RESPONSE_OBSERVERS` (a list and a loop on the success
   path) and an override for `chat_json`'s hard-coded `{"type":"json_object"}`.
   Both default to the previous behaviour exactly.
3. The observer POSTs the emission to `POST /projects/{id}/design-brief`.

⛳ **IT FLUSHES EAGERLY, NOT AT `task_postrun`, AND THAT IS A CORRECTNESS
POINT.** `_save_storyboard_scenes` swallows a non-2xx (RC-E, open, frozen), so
scene rows can fail to appear while the task reports success. A brief written
*before* that point survives it, and the gate can then say "the design exists
and the scenes did not" instead of showing nothing.

⛳ **AND STAGE 1 RIDES THE SAME SEAM FOR FREE.** The frozen stage-1 body already
parses a JSON response and takes `refined_text` out of it, discarding every
sibling key (`stage1_transcript.py:359-364`). So the extraction prompt emits
`{"refined_text": "<the script VERBATIM>", "intent": {...}}` — the frozen body
receives the unchanged script, **so nothing is rewritten and nothing is lost**,
and the extraction rides out through the observer.

---

## §6 TASKS 2 & 3 — the prompts

### 6.1 Directive (1): the dual publishing surface, argued from code

The operator directed: bring the SYSTEM prompt under the WP-63 lineage, or
fingerprint the `.j2`. **The code says do the first, and no frozen edit is
needed.** `_resolve_prompts` (`stage2_storyboard.py:86-111`) reads
`task_input.system_prompt` FIRST and falls back to the file; `api_sys` is always
`None` so the API branch never fires; and `StoryboardGenerationInput.system_prompt`
is filled by `_build_stage_input`, **which is not frozen and set neither prompt
field.** The mirror-image trick does not work on the user half — the API fetch
overwrites `user_prompt_template` unconditionally — which is precisely why the
SYSTEM slot is the one to use.

**Both were done, because the second is what makes the first auditable.** When
no row is published the stage still loads its `.j2`, and that path is now
recorded rather than invisible: `_resolve_system_prompt` fingerprints whichever
prompt actually won (`<type>:db:sha256=…` or `<type>:file:sha256=…`) and it
travels in the job context onto the brief. ⚠ `pipeline_checkpoints.version_fingerprint`
has existed since migration **0002** and **nothing has ever written to it** —
grep over `ivgs-workers` returns no hits.

### 6.2 R1b / P2.66 — CLOSED, and the same seam closes it

⛳ **The system slot is also where the learning outcomes belong.** They are the
design's governing constraint, so `{{ learning_outcomes }}` is a first-class
Jinja variable in the stage-2 system prompt, rendered by the orchestrator.
`_description_with_outcomes` is **retired** — kept as a documented artefact, not
deleted, because the WP-64 test that pins its delimiters was right for as long as
the block was the carrier and deleting it would delete the record of why P2.66
sat open for three packages. The storyboard branch now hands
`project_description` over **exactly as the project wrote it**.

### 6.3 Task 2 — the mode switch

`transcript_refinement_system` branches on `transcripts.source_kind`
(migration 0046) and on nothing else — not on a heuristic and not on the
presence of an asset id, which `ON DELETE SET NULL` can clear:

- **uploaded** → extraction. *"YOU ARE NOT EDITING PROSE."* Beats with character
  spans and quotes, the Gagné event each beat NATURALLY performs, Bloom touched,
  audience/purpose/tone/constraints, ABCD-checked outcomes with refinements
  **proposed, never applied**. `refined_text` is the script, copied.
- **generated** → the pre-existing refine-for-readability prompt, **byte for
  byte, Time Alignment section included.** ⚠ That section is the one the
  recovery plan indicts, and it is kept: it is RIGHT for a generated transcript,
  which is raw material a runtime may bound, and WRONG for a finished script.
  It now lives behind the branch instead of applying to everything. **Deleting
  it would have been an undeclared change to the path Task 2 says keeps its
  behaviour** — I removed it in the first draft and put it back.

### 6.4 Task 3 — v8, and every gate phrase audited

v8 is built from the published v7 (verified byte-identical to the tracked
template before editing) and grows RULES 10-13. **All 30 pre-existing gate
phrases were audited against the new text:**

| group | survives | note |
|---|---|---|
| BINDING (WP-63) | 3/3 | |
| MEDIUM (WP-64) | 4/4 | |
| V5 (WP-65) | 5/5 | |
| V6 (WP-68) | 4/4 | |
| V7 (WP-IVGS-10) | **10/10** | RULE 1-EXTENDED and RULE 8 survive intact, on the Mayer-redundancy justification the order names |
| FIELD_LIST | 3/3 | |
| OUTCOMES (WP-64) | **2/4** | ⚠ **two DROPPED, deliberately** |

⛔ **The two dropped phrases are the delimiter lines**
`=== LEARNING OUTCOMES (authored by the course owner) ===` and
`=== END LEARNING OUTCOMES ===`. **Reason: nothing writes them any more.** They
were gated because a drift between the orchestrator's copy and the prompt's
meant the model was handed a block it was never told to look for while
everything ran green. With the outcomes on a real variable there is no block,
and gating a delimiter nothing writes would refuse every correct v8. Two v8
phrases replace them in the publisher, and the two OUTCOMES phrases that are
still TRUE — `RULE 0 —` and `DO NOT invent outcomes` — are kept.

**Nine new V8 gate phrases**, with RULE 12 named as the load-bearing one: v7
headed the prompt *"Total Runtime Target"* and stage 1 was told to *"align with
max_runtime_seconds"*, and between them a four-minute script became 1:45 with a
worked example missing. **Duration is an output of a design.**

---

## §7 TASK 5 — the validator, and TASK 6 — the headers

### 7.1 The design review

`app/services/design_review.py`, keeping WP-IVGS-10's two-limb discipline
exactly: hard-refuse only what is objectively checkable, soft-flag every
judgment, one assessment feeding both surfaces, no prompt loops, every refusal
naming its scene or outcome.

**Refusals** (objective): a scene serving no outcome; a scene citing an outcome
the brief does not declare; a scene with no or an invalid event; **provenance
undeclared**; `sourced` with no span; `motion_graphics` without a template or
without params (RULE 8, unchanged); an outcome served by nothing; **an outcome
served but never assessed**; an evidence_map naming a scene that does not exist.

**Flags** (judgment): Merrill — the design never leaves events 1-5; a
practice/assess scene with no earlier present/guide on the same outcome (the
fading sequence); segmenting — a present/guide scene over ~2 sentences; a
rewrite carrying no original; an unmeasurable outcome with a proposal awaiting
approval; an evidence_map that disagrees with the scenes' own declarations; and
**undeclared script gaps**.

⚠ **Beat coverage is a FLAG though the arithmetic is objective.** Every
character of the uploaded script should sit inside some `source_refs` span or
inside a declared `dropped_beats` span — but a beat BOUNDARY is a judgment and
the offsets are counted by the model, so an off-by-twenty would hard-refuse a
sound design. The uncovered stretch is shown, **quoted**, so the reviewer sees in
one glance whether a worked example just went missing. ⛳ **This is the check
recovery-plan §3 item 4 says nobody ever performed** — *"no check anywhere
compares output narration to input script"* — performed at the strength the
evidence supports.

Exercised against a deliberately broken design: **5 refusals and 5 flags, every
planted defect caught and nothing else.**

### 7.2 Task 6 — measured first, and the shortfall is stated

Four per-scene prompts are compiled downstream. **The scene's identity exists
only inside an f-string built in frozen code** (`stage3_images.py:210-216`), so
no seam carries it into any of these templates without either a frozen edit or
overloading `scene_title` — which would put pedagogy into the storyboard UI and
the composition manifest.

⛳ **So the block is delivered as a TABLE keyed by the scene number the user
prompt already names.** The user prompt says `Scene 4:`; the system prompt
carries block 4 among the others and names the key. That is not a regular
expression and not inference — it is handing the model the table.

**Mechanism: two documented Jinja APIs, no monkey-patching.**

| path | template | seam |
|---|---|---|
| stage 3 image prompt writer | `stage3_system.j2` (a FILE) | `Environment.globals` — the file calls `{{ instructional_blocks() }}` |
| stage 5 TTS direction | `stage4_system.j2` (a FILE) | same |
| video cinematographer | `VIDEO_PROMPT_TEMPLATE`, **a constant inside a frozen body** | a `jinja2.ext.Extension` with a `preprocess` hook, added with `add_extension` — Jinja's own supported way to modify template SOURCE, and the only way to reach a frozen constant |
| motion authoring | — | **no LLM prompt exists**; it acts on a template name and params |

Each block carries Foundation §5's fields: `serves_outcomes`, `bloom`, `event`,
arc position, `learner_state` (**derived from the arc, not asked of the model,
so it cannot disagree with it**), `evidence_link`, `modality_rationale`, and the
signalling line when `text_carried_by` is set.

⚠ **THE SHORTFALL, STATED:** Foundation §5 shows ONE pre-selected block at the
head of ONE scene's prompt. What ships is the whole table plus a lookup
instruction. Closing that gap needs one line inside three frozen bodies; R5 says
prefer the wrapper, so it is **ledgered for the M3.3 window**, where those bodies
become activities and the edit is free.

✅ **Verified:** the header reaches all three paths including the frozen
constant, and **a project with no design brief produces the prompt it always
did, byte for byte** — no placeholder, nothing for the model to reason about.

---

## §8 THE OPERATOR'S RULINGS OF 2026-08-29, EXECUTED

| ruling | executed as |
|---|---|
| **(1)** `json_schema`-strict is the mechanism of record; `guided_json`'s silent no-op gets its own register row | **RC-Q1**, written as a trap for *every* future structured-output call, not only this one — the engine drops **any** unknown top-level body member without comment. The audit banner stands as placed |
| **(2a)** originals for pre-0046 projects are UNRECOVERABLE from the database — stated plainly | **RC-Q2**, ending *"Do not look for a database column; there is none and there never was"*, with the note that the bytes may still exist in SeaweedFS behind `original_asset_id` and that recovery from there is a script, not a migration |
| **(2b)** `0361c667`'s refusal-recorded-as-success joins the WP-00 register with file:line | **WP-00 instance 20** and **RC-Q3**. The validator gap is named — the only check on stage 1's output is `if not refined_text` (`stage1_transcript.py:368`), so a non-empty string of any content passes — and it is **rowed, not built** |
| **(3)** `talking_head` stays OUT of `media_type`; v8 refuses it explicitly; RULE 13 routes human/social to `image`; per-scene presenter selection is a register row and a Phase-5 candidate; `media_rationale` keeps its name | **RC-Q4**, plus a dated **CORRECTION NOTE** on the Foundation covering §4, §6 and §8, applied by the same assert-guarded `sudo tee` used for the audit banner — **ownership verified `root:root 644` before and after** |
| **(4)** `dev/design/` joins the repo | `chown dev:ivgsdev`, both documents git-tracked **with** their banner and annotation |

---

## §9 TASK 7 — THE ACCEPTANCE RUN

**Method.** A test project through the normal flow: the operator's own uploaded
script (the 3,172-byte multiplication lesson, fetched read-only from the asset
behind project `4ca0d5c5`'s transcript), a real description, and **three genuine
ABCD outcomes typed into the WP-64 form field**. No SQL. Authentication by a
short-lived token minted from the app's own security module for an existing
admin — **no new user row, no password handled**.

### 9.1 What the run proved

✅ **`source_text` and `source_kind` are written at upload.** The API response
carried `"source_kind": "uploaded"` and a `source_text` byte-identical to
`refined_text` before any stage touched it. Migration 0046 works end to end.

✅ **The Design Contract is emitted and enforced, on the pinned engine, on the
operator's real material.** 11,577 prompt tokens in, 4,335 completion tokens
out, `finish_reason=stop`, zero enum violations across every generation.

✅ **The seam carries it.** `design_contract_captured` fires, the brief is
stored, and `create_scene` applies the per-scene declarations from it.

✅ **The gate renders the design review** — outcomes × scenes × evidence, the
event arc, the modality rationale per scene, the drops and the rewrites.
Described in §9.3.

✅ **WP-59 deletion accounts for the new table.** The preview lists
**Design briefs** as its own category, and the delete removed **31 rows and 1
file** — `storyboard_scenes 13, storyboard_design_briefs 3, transcripts 1,
render_jobs 4, pipeline_checkpoints 5, project_gate_decisions 3, assets 1,
projects 1`. **The operator's four projects were untouched throughout** and are
all still present.

### 9.2 ⛔ THE ACCEPTANCE CRITERION IS NOT MET, AND THIS IS WHY

Three consecutive generations, each scored on **its own emitted contract**
(see §9.4 for why not on the scene rows):

| gen | scenes | outcomes | sourced | dropped_beats | rewrites marked | **hard refusals** | flags |
|---|---|---|---|---|---|---|---|
| 1 | 7 | **2** | 4 | **0** | **0** | **1** | 2 |
| 2 | 8 | **2** | 4 | **0** | **0** | **1** | 3 |
| 3 | 11 | **2** | 7 | **0** | **0** | **1** | 4 |

✅ **Structurally valid: all three.** Every scene declared `serves_outcomes`,
an event, a Bloom level and a provenance; every enum closed; every
`motion_graphics` scene carried a complete template spec. **The schema held.**

✅ **The arc reaches application on all three** — generation 1
`hook → present → guide ×3 → practice → transfer`, generation 2 adds `assess`
and `feedback`, generation 3 runs eleven scenes through
`… → assess → practice → guide → feedback`. **The Merrill check passes; no
generation is a lecture.** That is the thing v7 could not do at all.

⛔ **Zero hard refusals: NOT met. One refusal per generation, the same one every
time — `OUTCOME_UNASSESSED` on the second outcome.**

⛔ **AND THE REASON IS WORSE THAN THE REFUSAL. THE DESIGNER PARAPHRASED THE
OPERATOR'S OUTCOMES AND DROPPED ONE — ALL THREE TIMES.** Three ABCD outcomes
went in; **two came out of every generation**, reworded:

    supplied: "Given two 2-digit numbers written in column form, the learner
               will compute their product using the standard column algorithm,
               producing both partial products with correct carries and a
               correct final sum."
    emitted : "The learner can multiply two double-digit numbers."
              measurable: true    proposed_refinement: null

**LO-3 vanished entirely and was not declared in `dropped_beats` either.** The
v8 system prompt says *"COPY EACH ONE INTO `outcomes[].text` EXACTLY AS
WRITTEN"* and *"You never edit the owner's words"*. **The schema cannot enforce
it, because a paraphrase is a valid string**, and the gate shows nothing wrong:
the matrix is drawn against the paraphrase, and every outcome the CONTRACT
declares is served.

⛳ **This is RC-P14's shape at the outcome layer, and it is worse, because the
outcomes are the spine everything downstream aligns to.** The check that would
catch it is cheap and objectively decidable and **does not exist**: compare the
contract's `outcomes[]` against `projects.learning_outcomes`, count first and
text second, and hard-refuse a missing or reworded operator outcome.
`design_review.review()` cannot do it today because **it is never given what the
operator actually wrote.**

⛔ **ROWED AS RC-Q9, NOT BUILT.** The package is at its Task-7 stop point; three
runs is a measurement rather than a hunch; and whether the answer is a validator
check, a prompt change or both is the operator's ruling. ⚠ **I did not iterate
the prompt to chase a green number** — the standing restraint from RC-P2 and
RC-P14 applies, and a prompt tuned against three runs of one script would be
fitted to this script.

⚠ **Also reproducible and unfixed:** `dropped_beats` was **empty on all three**
while the coverage check flagged **2,658 characters of the uploaded script used
by no scene and declared in no drop**, and **no rewrite was ever marked** though
every narration is visibly reworded. The declaration machinery works; the model
does not use it. Same class, same restraint.

### 9.3 The design brief, as the gate renders it

Described from the live `GET /design-review` payload, banked at
`reference/wpivgs12-acceptance/design-review-as-the-gate-rendered-it.json`.

At the top of the amber gate panel, above the existing depicts-narration panel,
sits **"Design brief — you are approving a course design"**, with the contract
version, the model and the prompt fingerprint in small monospace on the right.

- **The event arc** as nine chips in Gagné order. Events the design performs are
  green; events it does not are struck through and grey. On generation 3:
  `hook present guide practice feedback assess` lit, `objective recall_prior
  transfer` struck.
- **The outcomes × scenes × evidence matrix**, one row per outcome: the id, the
  outcome's own words, its Bloom level, the scenes that SERVE it, and — in a
  separate column — the scenes that ASSESS it. `NOTHING` renders in bold red.
  On every generation the second outcome's assessed column read **NOTHING**.
- **Refusals** in a red block *above the decision buttons*, each naming its scene
  or outcome and its code, so nobody presses Approve to find out; **flags** in an
  amber block below, labelled *"information, not a verdict. These block
  nothing."*
- **An `UNDECLARED_SCRIPT_GAP` flag quotes the uncovered script text inline**, in
  monospace, so a reviewer sees in one glance whether a worked example just went
  missing.
- **Rewrites** would render side by side — *"The script said"* against *"The
  design says"* — but none was marked, so the section is absent. **That absence
  is itself the finding.**
- **Modality, scene by scene**: `07 transfer / motion_graphics → [LO-1, LO-2] —
  symbolic procedure, the renderer draws the digits`, and *"no rationale
  recorded"* in italics where one is missing.

### 9.4 ⚠ Why the generations are scored on the contract and not on the gate

Generation 1 produced 13 scenes; generation 2 produced 8. **The gate then showed
13 rows — five of them from a design that no longer existed**, carrying no
declarations, and the review drew **24 hard refusals where the generation's own
contract drew 1.**

That is `StoryboardService.create_scene`'s pre-existing, self-documented
limitation: it upserts by `scene_index` and *"a re-run that produces FEWER
scenes than the project already has leaves the surplus rows behind."* ⛳ **Before
this package the surplus was invisible** — one more thumbnail among thumbnails.
The design brief makes it loud, which reads as a regression and is an
improvement. **Rowed as RC-Q10.**

### 9.5 Three defects the run found, all mine, all fixed

| # | what | how it was found |
|---|---|---|
| **a** | **`design_core` was invisible to the worker.** `docker exec … python3 -c "import design_core"` printed `ok` while the running worker logged `No module named 'design_core'` — **the WP-IVGS-10 addendum's two-doors defect, repeating**. A console-script entry point puts `/usr/local/bin` on `sys.path`, not the cwd | the observer's own registration-failure log, which is loud and non-fatal by design. ⚠ **A module-level anchor did NOT suffice; the `__file__` anchor INSIDE the handler did, and I cannot explain why** — the diagnostic (sys.path + traceback in the error line) is now permanent so the next occurrence answers itself |
| **b** | **`contract_version VARCHAR(16)` against the 17-character value `design-contract-1`.** Every ingest returned HTTP 500 | the capture **raised instead of swallowing** — `design_contract_capture_failed` carried the status and the body. Fixed by migration **0049** (widened to 64, with a real downgrade that nulls what it cannot represent) |
| **c** | **The design review assumed `generation_params` nested a `params` key.** The real shape is FLAT — `{"top": 23, "bottom": 14, "phase": "start", "template": "…"}` — so it refused **seven sound motion scenes** | the acceptance run's own refusal list. Now checked against **the renderer's own `template_spec`**, so a template that gains a parameter (as two did when WP-IVGS-10 added `phase`) cannot leave the check quietly passing |

⛳ **(b) is the argument for the eager flush, made by accident.** The brief failed
to store and **thirteen scenes still landed and the run still reached the gate**,
because the observer is non-fatal by construction. A capture problem degraded the
review; it did not cost a render.

### 9.6 A defect the run found that is NOT mine

⛔ **`scripts/save-image-artifact.sh` silently shipped stale bytes.** It skips the
save when an artifact of that name exists (P1.4j, to keep MANIFEST.txt clean) —
**and the name is derived from the TAG.** A tag rebuilt mid-session re-saves
nothing, `docker load` restores the OLD image under the same tag on every remote
node, and **`verify-deployed-image.sh` reports DEPLOY VERIFIED** because it
compares the tag. Measured: node-01 on `e9c1001a` while nodes 02/03/04 ran
`aa89c778` under the identical tag, with the timeout fix absent on all three.
⚠ **The script printed `artifact already present, skipping save` and I tailed
past it.** Rowed as **RC-Q8**; the check that catches it is comparing
`docker inspect --format '{{.Image}}'` ACROSS nodes.

---

## §10 DEPLOY, and the tests

**Deployed under §6.1a** — stderr never redirected, which immediately earned its
keep by refusing `celery-default` (the container is `ivgs-celery-default`; the
SERVICE is `celery-worker-default`) instead of exiting 0 on a silent no-op.

**Eight containers on `v5.37.0-design-core`, all VERIFIED, all processes up**
(RC-P19: the image is not the process):

    node-01  ivgs-fastapi · ivgs-nextjs · ivgs-celery-default
             ivgs-celery-composition · ivgs-celery-beat
    node-02  ivgs-celery-node02          node-03  ivgs-cogvideox-worker-node03
    node-04  ivgs-celery-node04

and, after RC-Q8, the **image IDs were compared across nodes**: all four on
`sha256:e9c1001a…` for the workers.

**Migrations applied to production**, additive and verified non-destructive:
the `refined_text` content digest across all four existing transcripts is
**byte-identical before and after** (`eb44de25c4e19787906f1a1e29585a1c`), all 4
rows backfilled `source_kind='uploaded'` from asset provenance, **0 backfilled
`source_text`** exactly as ruled, and **0 of 47 existing scenes** gained a
declaration.

**Prompts published through the WP-63 lineage:** `storyboard_generation` **v8**
(38,549 chars, superseding v7 which stays readable and inactive — rollback is
one UPDATE), `storyboard_generation_system` **v1**, `transcript_refinement_system`
**v1**. The seed-conformance gate passes against the deployed image.

### 10.1 Tests — ZERO NEW FAILURES

| tree | baseline | now | verdict |
|---|---|---|---|
| `ivgs-api` | 1553 passed, **0** failed | **1579 passed, 0 failed** | ✅ **+26**, still zero |
| `ivgs-workers` | 965 passed, **18** failed, 48 skipped, 15 errors | **983 passed, 18 failed**, 52 skipped, 15 errors | ✅ **+18**, failures identical |
| `ivgs-scheduler` | 52 passed, 15 failed | 52 passed, 15 failed | ✅ identical |
| `ivgs-backup-worker` | 4 passed, 0 failed | 4 passed, 0 failed | ✅ identical — **only with RC-J8's three env vars**, which my first harness omitted |
| `ivgs-motion-renderer` | 24 passed, 2 skipped | 24 passed, 2 skipped | ✅ identical |
| `tests_system` | 193 passed, 12 failed, 15 skipped, 30 errors | 193 passed, 12 failed, 15 skipped, 30 errors | ✅ identical |

**Two full-suite runs, as the order allows, and no more.**

⚠ **Three worker-tree failures diagnosed as PRE-EXISTING, not inherited
silently:** `test_stage1/test_stage2::test_full_task_execution` fail at
`stage2_storyboard.py:621` — `UUID(project_id)` on a non-UUID fixture, inside a
frozen body this package did not touch.

### 10.2 Five existing test files were re-aimed, and none was weakened

`test_wp64_learning_outcomes.py`, `test_wp63_storyboard_prompt.py`,
`test_wp65_storyboard_v5.py`, `test_wp64_media.py`,
`test_wp_ivgs_0_seed_template_contract.py`.

**All five pinned the delimiter carrier, and the carrier is gone (P2.66 closed).**
Each now asserts the SAME risk at the new path — that the system prompt actually
interpolates `{{ learning_outcomes }}`, proved by rendering it with a sentinel
and without — plus that no delimited block survives in the template, that the
constants remain byte-identical in the orchestrator, and that **nothing calls
the retired fold**. ⛳ **The strongest assertion of the five is untouched and is
now worth more:** `test_the_frozen_render_call_is_untouched` still counts nine
names in `_render_user_prompt`, and it is the proof this package took the
wrapper rather than the edit.

⛳ **AND THE RE-AIMED TESTS CAUGHT A REAL DEFECT WITHIN MINUTES.** Editing RULE 0
swallowed the `{% endif %}` closing `{% if project_description %}`. **Every
phrase gate still passed** — a substring check cannot see an unbalanced block —
and it would have published cleanly and raised `TemplateSyntaxError` inside a
frozen stage body at run time, failing Stage 2 for every project at once. **A
render gate is now part of the publisher**, in both branches, with a length
floor.

---

## §11 THE TREE, AND THE OPERATOR'S PUSH BLOCK

**Held: 1 commit. Nothing pushed. Working tree clean.**

    c3812b1  feat(wp-ivgs-12): the Design Core — a storyboard becomes an
             instructional design

**Tagged `v5.37.0-design-core`** — a real git tag this time, on `c3812b1`,
covering the coherent set. ⚠ The images of the same name were deployed before
the tag existed; **a tag is not an image and an image is not a git tag**, and
RC-Q8 adds the third edge of that rule.

**Files that appeared and are not mine: none.** `dev/design/`'s two documents
were the operator's, root-owned and untracked; ruling (4) brought them into the
repo, `chown dev:ivgsdev`, **with** the audit banner and the Foundation
correction note.

⚠ **`ivgs-infra/.env` was edited and is NOT committed** — it is gitignored and
carries deploy configuration. Its three tag variables now read
`v5.37.0-design-core`; the same edit was made on nodes 02, 03 and 04. A backup
of the pre-edit file is in this session's scratch and **is not preserved** —
declared here rather than implied.

### The push block — count-gated, the operator's to run

```
# node-01, as the operator
cd /opt/ivgs
EXPECTED=1
ACTUAL=$(git log --oneline origin/main..HEAD | wc -l)
if [ "$ACTUAL" -ne "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git push origin main && git push origin v5.37.0-design-core
fi
```

⛔ **Read §9.2 before pushing.** The code is deployed and the prompts are
published, so the behaviour described there is already live on the fleet
whether or not this commit is pushed. **The acceptance criterion is not met**,
and RC-Q9 is the reason.

---

## §Z WHAT I DID NOT VERIFY

Stated plainly, per `dev/CLAUDE.md` §12.

1. ⛔ **The rendered gate panel.** §9.3 describes the design brief from the live
   `GET /design-review` payload and from `DesignBriefPanel.tsx`. **No browser was
   driven and no screenshot was taken.** The frontend typechecks (`tsc --noEmit`,
   clean) and the payload is banked, so the description is checkable — but
   **whether it LOOKS right is unverified** and is part of the operator's watch.
2. ⛔ **That any of this improves a rendered video.** The package stops at the
   storyboard gate by instruction. No media stage ran.
3. ⛔ **Why the module-level `sys.path` anchor did not suffice** where the
   in-handler `__file__` anchor did. Both are in place, the symptom is gone, and
   the diagnostic (sys.path + traceback) is permanent — but **the cause is not
   established** and I will not claim it is.
4. **The three failures I attribute to pre-existing causes** — `test_stage1` and
   `test_stage2`'s `test_full_task_execution` — were diagnosed by reading the
   traceback to `stage2_storyboard.py:621` inside a body this package did not
   touch. I did not run them against a pre-change checkout.
5. **The other nine stages' client timeouts.** RC-Q7 fixes stage 2 and measures
   it. The rest still share one 120 s knob and **none was measured** against its
   own declared policy.
6. **`structured_outputs` as a live fallback.** Measured ENFORCING on the trivial
   schema in probe 0(c); **never exercised on the real contract** and never run
   through the pipeline.
7. **The 0046 `source_text` recovery from SeaweedFS.** Named as the only route
   for pre-0046 originals; **no such script was written or run.**

---
---

# §12b — WP-IVGS-12b: outcomes cannot be paraphrased, artifacts cannot lie

**2026-08-29 · same package lineage, appended here because the RC-Q rows it
closes are above. Commit and HOLD.**

## 12b.0 STATE AT SESSION END

| | |
|---|---|
| **Done** | RC-Q9 cured STRUCTURALLY; RC-Q8 closed with a digest rule; migrations 0050; v9 + system prompt v2 published; images rebuilt, re-banked and the fleet reconciled BY DIGEST; register and board updated |
| ⛔ **ACCEPTANCE: PARTLY MET** | ✅ all three outcomes verbatim, every generation. ✅ **zero invented ids**, every generation. ✅ drops now declared. ⛔ **zero hard refusals STILL NOT MET — 3, 2, 2** — but for a *different* reason: **RC-Q9b**, the designer serves an outcome and never assesses it |
| **Held** | **1 commit** — `2b867b0`, this one. ⚠ I first wrote "2": WP-IVGS-12's `cead433` was held when 12b began and the operator pushed it mid-session (`git reflog show origin/main`: `cead433 update by push`). Measured from the remote-tracking ref at close |

**Verified live:** every probe; the migration; the digest refusal, twice; three
generations end to end; the fleet compared by image ID. ⛔ **Still NOT verified:**
the rendered gate panel in a browser (unchanged from §Z), and that any of this
improves a video.

## 12b.1 Task 1 — RC-Q9 cured by removing the question

**The model is no longer asked to transcribe what the database holds.**

- `shared/design/outcomes.py` parses `projects.learning_outcomes` into stable
  positional ids `LO-1..n`. **Reversibility is the contract** —
  `reconstruct(parse(x)) == x.strip()` over an 11-case corpus (LO-prefixed,
  numbered, bulleted, unmarked, wrapped, blank-separated, empty). Without it the
  byte-compare belt would compare against a normalisation.
  ⛳ One corpus case changed the design: three UNMARKED lines collapsed into one
  outcome under the continuation rule — the same silent-loss shape. If nothing
  in the text carries a marker, every non-empty line is its own outcome.
- **`outcomes[]` is gone from the model's schema.** It emits `outcome_notes`, an
  OBJECT keyed by the real ids — `required` forces one entry per outcome and
  `additionalProperties:false` forbids an invented one. An array would have let
  it emit two for LO-1 and none for LO-3: the same failure in a new hat.
- **Foundation §2 survives (ruling 1c):** `proposed_refinement` is proposed
  *against an id*, beside text the model never touched.
- `DesignBriefService._outcomes_from_the_project` injects the operator's words
  with `authored_by: "operator"` and merges the notes by id.

### 12b.1.1 The measurement Task 1(b) was gated on

Per-request enums differ on every call and cannot ride a cached grammar, so
strict-mode on a fixed schema does not imply them. Probed first:

| construct | verdict |
|---|---|
| per-request `enum` | ✅ **ENFORCED** — given ids `["LO-1"]` and *ordered in the prompt* to serve LO-1, LO-2 and LO-3, the model emitted **LO-1 only** |
| `maxItems` | ✅ **ENFORCED**, string-enum and object arrays alike |
| `minItems` with no max | ⛔ **RUNAWAY** — `["LO-1","LO-3","LO-3",…]` to the token limit, `finish_reason=length` |
| `uniqueItems` | ⛔ **HTTP 400** `Grammar error: Unimplemented keys: ["uniqueItems"]` |

⛔ **THE RUNAWAY IS A LIVE HAZARD IN THE v8 CONTRACT WP-IVGS-12 SHIPPED** —
`serves_outcomes`, `source_refs` and `scenes` all had `minItems` and no maximum.
It happened to terminate. **Every array now carries a `maxItems`** (RC-Q12).

⛳ **And note the contrast with RC-Q1:** an unimplemented GRAMMAR key is refused
**loudly**; an unknown BODY member is discarded **silently**. Two failure modes,
one engine, and only one of them tells you.

### 12b.1.2 Task 1(d) — the belt, and the emptiness refusal

`OUTCOMES_COUNT_DRIFTED` / `OUTCOMES_TEXT_DRIFTED` **cannot fire** with the
structural fix in place. They exist so that if anyone routes outcome text back
through a model — a v10 prompt, a refactor — **RC-Q9 returns LOUD instead of
silently redrawing the matrix against a paraphrase.**

`UNDECLARED_GAP_WITH_NO_DROPS` is a **hard refusal** at ≥400 uncovered
characters with `dropped_beats == []`. ⛳ **The span-arithmetic doubt that keeps
attribution soft does not touch it:** the empty array is the model's own CLAIM
that it used everything, the hole is measured **by code**, and both cannot be
true. With drops declared, a residual gap stays a flag.

## 12b.2 Task 2 — RC-Q8, and why the digest is a sidecar

**Argued from every consumer**, because the WP-58 one-definition rule is the
point: `artifact_path_for`/`artifact_require` resolve from an image REF and
nothing else — that IS the deploy contract, since a remote node has the tag,
lacks the image, and the artifact exists to carry the image it lacks.
Digest-in-name would force every deploy caller to know the digest before it
could find the file; `check-image-artifacts.sh` pins the name shape and would go
red for every artifact ever banked; `tests_system/test_wp58_retention.py`
asserts that exact output and is doing its job.

**So the name is unchanged and the fix is in the SKIP LOGIC, which is where the
defect was.** New `image_local_digest` / `artifact_digest_path_for` /
`artifact_banked_digest`; a `.digest` sidecar per save; `image:<digest>` in
MANIFEST rows; **a different digest under the same tag REFUSES, naming both** —
proven twice live, once on my own rebuild. A present artifact with **no**
recorded digest is **re-saved, not adopted**: stamping a digest onto unverified
bytes would make a lie checkable, which is worse than the bug. The checker
reports artifacts without a digest (93 of 95) and **does not fail** — a
permanently-red gate is the mistake its own header records WP-56 closing.

**Which digest won, and why.** For `v5.37.0-design-core`: **`sha256:e9c1001a…`**
— the only build carrying the RC-Q7 timeout fix, the bytes all four nodes ran,
and the bytes in the bank. ⛳ **Proven by round-trip:** `docker load` of the
banked artifact restored `e9c1001a` under that tag after a same-tag rebuild had
pruned it locally. `aa89c778` predates the fix and is retired. The fleet then
moved to **`v5.37.1-outcomes-by-code` / `sha256:6f5bcf93…` on all four nodes,
verified by IMAGE ID**.

## 12b.3 The acceptance — three consecutive generations

Same script, same three ABCD outcomes, same flow.

| | gen 1 | gen 2 | gen 3 |
|---|---|---|---|
| outcomes present, **verbatim** | ✅ 3/3 | ✅ 3/3 | ✅ 3/3 |
| **invented ids** | **NONE** | **NONE** | **NONE** |
| `outcome_notes` entries | 3 | 3 | 3 |
| scenes | 12 | 7 | 7 |
| sourced scenes | 12 | 4 | 4 |
| `dropped_beats` | 0 | 1 | 1 |
| arc reaches application | ✅ | ✅ | ✅ |
| **hard refusals** | **3** | **2** | **2** |

✅ **RC-Q9 IS CURED AND THE PROOF IS THE ABSENCE OF DRIFT.** Three generations,
zero paraphrases, zero dropped outcomes, zero invented ids. The belt never fired
because it cannot. Compare 12a: **2 of 3 outcomes, reworded, every time.**

⛔ **THE CRITERION IS STILL NOT MET, AND THE REASON MOVED — RC-Q9b.** The
dominant refusal is now **`OUTCOME_UNASSESSED`**: the designer serves an outcome
and never has a scene assess it. Generation 3 also left **LO-3 unserved
entirely**. `EVIDENCE_MAP_DISAGREES` flagged on nearly every outcome of every
generation — the model fills `evidence_map` with a claim its own scene events do
not support.

⛳ **This is a better failure than RC-Q9 was.** The gate now refuses for a real
pedagogical reason, measured against the operator's own words, instead of
drawing a matrix over a paraphrase. But it is a failure, and I did not iterate
the prompt against it — RC-P2/RC-P14's restraint, and structural options exist
(derive `evidence_map` from the scenes, losing the cross-check; or close it so
an outcome with no assessing scene is ungrammatical). **Rowed as RC-Q9b; the
ruling is the operator's.**

## 12b.4 Four defects found on the way, all mine, all fixed

| # | what | how it surfaced |
|---|---|---|
| **a** | **The enum never armed.** The worker read `GET /projects/{id}`, which takes `get_current_user` and answers a service token **401**; `outcome_ids_for_current_project` returns `[]` on any error *by design*, so the schema degraded to an open string and every scene cited an invented `outcome_1`. New `GET /projects/{id}/design-outcomes` under `get_service_or_user`, returning the PARSE so worker and API share one function | the stored brief cited `outcome_1/2/3` while `outcomes[]` was already correct |
| **b** | **`PromptType` in the database and not in the ORM.** 0047 added two members; `prompt.py` typed its tuple by hand. Rows published, then `LookupError` on the next SELECT — **WP-68's defect, and that column's own comment had warned of it since WP-64.** Fixed the way `MediaType` was: `PROMPT_TYPES`, one list. **A warning is not a mechanism** (RC-Q11) | 12b's publisher looking for a version to supersede |
| **c** | **A merged declaration left a stale `source_refs`.** Gen 1 left scene 6 `sourced` with refs; gen 2 called it `designed`; the update set the origin and left the refs → CHECK violation → the whole brief lost. `_clean` now writes the declaration **whole**, which also clears leftovers of a design that no longer exists | the XOR constraint, doing its job |
| **d** | ⛔ **The same constraint, the opposite error: it REFUSED a legal row.** SQLAlchemy's JSONB defaults to `none_as_null=False`, so an explicit Python `None` is written as JSON `null`; `source_refs IS NULL` is FALSE for that, so `designed` could never match — and the DETAIL line printed `null`, reading as perfectly legal. **Both halves fixed:** `none_as_null=True` on the four design columns, and migration **0050** so the CHECK treats SQL NULL, jsonb `null` and `[]` alike | reproduced directly: SQL NULL accepted, `'null'::jsonb` refused, same row otherwise |

⛳ **(c) and (d) are the same constraint failing in opposite directions, and both
were caught by it rather than by a reviewer.** 0048's first draft accepted the
row it exists to refuse (`FALSE OR FALSE OR NULL` is NULL); 0050 stops it
refusing one it should accept. The constraint has now been wrong twice and
caught two real defects — a good trade.

## 12b.5 Six existing tests re-aimed, none weakened

`test_wp63_storyboard_prompt`, `test_wp64_learning_outcomes`, `test_wp64_media`,
and three of my own from 12a. All asserted the 12a architecture: the sentinel
`{{ learning_outcomes }}`, the `measurable`/`refinement` `oneOf`, and `_clean`
omitting absent keys. Each now asserts the **same risk at the new shape** — that
the text **and the ids** reach the rendered prompt (a model that cannot see an
id cannot cite one, and the grammar admits nothing else); that the schema
carries no outcome text at all; that a dropped field is `None` rather than
absent, which is what CLEARS a stale declaration.

## 12b.6 The tree, and the operator's push block

**Held: 1 commit. Nothing pushed by me. Working tree clean.**

    2b867b0  fix(wp-ivgs-12b): outcomes cannot be paraphrased, artifacts
             cannot lie

**Tagged `v5.37.1-outcomes-by-code`**, verified on HEAD. ⚠ `v5.37.0-design-core`
is on `cead433`, which the operator pushed during this session.

**No frozen stage body was touched** — asserted file by file across all nine, and
a test still pins `FREEZE EXCEPTION #2` at exactly two occurrences. **No files
appeared that are not mine.** `ivgs-infra/.env` was edited (three tag variables)
and is gitignored; the same edit was made on nodes 02, 03 and 04.

```
# node-01, as the operator
cd /opt/ivgs
EXPECTED=1
ACTUAL=$(git log --oneline origin/main..HEAD | wc -l)
if [ "$ACTUAL" -ne "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git push origin main && git push origin v5.37.1-outcomes-by-code
fi
```

⛔ **Read §12b.3 before pushing.** The code is deployed and v9 is published, so
the behaviour described there is live on the fleet whether or not this commit is
pushed. **The acceptance still does not reach zero hard refusals**, and RC-Q9b is
the reason.

## 12b.7 What I did not verify — 12b's additions to §Z

1. ⛔ **The rendered gate panel, still.** Unchanged from §Z: no browser was
   driven. The design brief now shows the operator's own outcome text verbatim,
   which is the thing most worth looking at, and **it has been verified only in
   the payload.**
2. ⛔ **`structured_outputs` as a fallback for the per-request enum.** The enum
   was measured under `response_format: json_schema` only.
3. ⛔ **The other 93 artifacts.** Their digests are unrecorded and their
   provenance unprovable; the checker reports them and nothing re-banks them
   until someone calls `save-image-artifact.sh` for that reference.
4. ⛔ **That RC-Q9b is only a prompt problem.** I did not test whether closing
   `evidence_map` structurally would fix it — that is the ruling I am stopping
   for, and guessing at its outcome here would pre-empt it.
5. **The 0050 downgrade path was not exercised** against a database containing
   jsonb-`null` rows. The docstring states the normalising UPDATE it needs; I
   ran the upgrade on production and the test database, not the downgrade.

---
---

# §12c — WP-IVGS-12c: RC-Q9b closed structurally, with the belt promoted

**2026-08-29 · same package lineage, appended here because the RC-Q rows it
closes are above. Commit and HOLD.**

## 12c.0 STATE AT SESSION END

| | |
|---|---|
| **Done** | `evidence_map` is schema-required per LO id and bounded **1..4** — "nothing assesses this" is no longer an emittable sentence; `EVIDENCE_MAP_DISAGREES` **promoted FLAG → HARD REFUSAL** with the two halves reported separately; the prompt states the rule the gate enforces; 18 new tests, one re-aimed |
| ⛔ **ACCEPTANCE: NOT MET, AND THE REASON MOVED AGAIN** | ✅ zero invented ids, ✅ all three outcomes verbatim, ✅ `outcome_notes` 3/3, ✅ **zero empty evidence arrays** (12b had them every generation), ✅ drops declared. ⛔ **hard refusals 5, 6, 5.** The residue is `EVIDENCE_MAP_DISAGREES` ×3 every generation and `OUTCOME_UNASSESSED` on LO-2/LO-3 — **rowed as RC-Q9c, not tuned** |
| ✅ **DEPLOYED AND PUBLISHED** | On the operator's grant of 2026-08-29, after the rest of this section was written. **Nodes 01-04 on `v5.37.2-evidence-by-structure`, all four worker containers on ONE image ID matching the bank**; `storyboard_generation_system` **v3** published, v2 preserved inactive. Every verification line in §12c.9 |
| **Held** | **2 commits** — 12c's code, and the deploy/close-out commit. `git rev-list --count origin/main..HEAD` at close |

**Verified live:** every probe against the pinned engine; three end-to-end
generations on node-02; both full suites baselined by stash-and-rerun; the
deploy, by image ID on four nodes and by reading `CONTRACT_VERSION` and the
promoted refusal out of the RUNNING containers.
⛔ **Still NOT verified:** the rendered gate panel in a browser (unchanged from
§Z and §12b.7), and that any of this improves a video.

## 12c.1 Task (1) — MEASURE FIRST, and the table

12b proved a per-request `enum` and `maxItems` on ARRAY ITEMS. Required keys on
an OBJECT are a different construct and were not thereby proven. Probed before
anything was built — and in every case **the prompt was ordered to violate the
constraint**, because a schema the model had no wish to break proves nothing.
The control is the temptation.

| construct | verdict |
|---|---|
| per-request **REQUIRED property keys** | ✅ **ENFORCED.** Ordered to emit `LO-1` only and to omit `LO-2`/`LO-3` "entirely — they are wrong and must not appear", it emitted **all three** |
| **`additionalProperties: false`** per-request | ✅ **ENFORCED.** Ordered to add `"LO-9": [0]` — "that id is the correct one" — it did not appear |
| **`minItems` + `maxItems` together** | ⚠ **ENFORCED, AND IT CAN HANG.** See below |
| **`contains`** | ⛔ **HTTP 400** `Grammar error: Unimplemented keys: ["contains"]` — exactly like `uniqueItems`, and the only construct that could have expressed "some scene in this list assesses" without leaving the schema |
| `maxItems` (re-confirmed) | ✅ ENFORCED — no array exceeded its bound in any probe |

### 12c.1.1 ⛔ THE HANG, WHICH IS RC-Q12'S RUNAWAY IN A SHAPE `maxItems` DOES NOT CLOSE

Ordered to emit `[]` into an array declared `minItems: 1, maxItems: 4`, the
decoder forbade the `]` and the model took the only other legal continuation:
**whitespace — 5,243 characters of it, `finish_reason=length`, nothing
parseable.** `maxItems` bounds the ELEMENTS. Nothing bounds the whitespace
between `[` and the first one.

⛳ **This nearly killed the structure the ruling asked for**, so it was measured
rather than reasoned about, twice more:

| probe | result |
|---|---|
| same schema, **neutral** prompt | ✅ 200 in 4s — `{"LO-1":[0,2],"LO-2":[1],"LO-3":[3,4]}` |
| same schema, a lesson told plainly it is **demonstration-only and assesses nothing** | ✅ 200 in 5s — it **filled the map anyway**: `{"LO-1":[0,1,2,3],"LO-2":[2],"LO-3":[4]}` |

So the corridor is only reachable when the model's next token would be `]`, and
under honest pressure it does not go there — it names a scene instead. **The
bound ships**, and when the corridor IS reached, WP-37's `finish_reason` check
raises `VLLMTruncatedResponseError` *before* the parse, naming the token limit.
A loud failure, not a silent one. Recorded in `contract.py` beside the constant.

⛳ **AND THAT SECOND PROBE PRE-ANSWERED TASK (4) BEFORE THE STRUCTURE WAS
WRITTEN.** In the demonstration-only run the model's own `design_notes` said the
lesson "does not include any practice or assessment items" **while its
`evidence_map` named scenes**. Structure can force the claim to exist. It cannot
make the claim true.

## 12c.2 Task (2) — the structure

`design-contract-3`. `evidence_map` carries one **required** key per outcome id,
`additionalProperties: false`, each holding **1..4** scene indices. The LOWER
bound is the load-bearing one: RC-Q9b's dominant shape was an outcome assessed
by nothing, and `[]` was the legal way to write it.

**Required-keys measured IMPLEMENTED, so the schema carries this and the
validator is the belt, not the load.** On the one path the schema cannot reach —
a project whose operator stated no outcomes, where the enum degrades to an open
object — `design_review` carries the whole weight, and it says so by name
(`EVIDENCE_MAP_NAMES_NOTHING`) rather than passing quietly.

⛔ **No `dropped_outcomes` mechanism was built, and none exists.** Dropping an
outcome is an operator act at the gate. An outcome the operator typed is served
and assessed, or the design is refused; the designer has no third answer. A test
pins the absence in both the schema and the validator, so a later package cannot
add one by drift.

## 12c.3 Task (3) — the belt promoted

`EVIDENCE_MAP_DISAGREES` is a **hard refusal**. A scene named as evidence for
LO-x must itself declare **both**: LO-x in its `serves_outcomes`, **and** an
`instructional_event` in `{practice, assess}` (`ASSESSING_EVENTS` — one
definition, not a second copy in the gate).

⛳ **WHY IT QUALIFIES UNDER WP-IVGS-10'S LINE.** Both halves are closed enums the
designer wrote itself. Nothing is judged; two declarations by one author are
compared. That is "scene 7 declares no outcome", not "scene 7 feels thin".

**The two halves are reported separately** — `not_serving` and `not_assessing` —
because they have different fixes: one scene is pointed at the wrong outcome, the
other is labelled the wrong event. The measured run shows why that mattered:
`not_serving` fired twice and `not_assessing` eleven times, and a single
"disagrees" would have left the reviewer to bisect it.

**The seam is closed, and a test pins it:** the map must name a scene (schema),
and every named scene must serve AND assess (belt) — so a design passing both
has, for every outcome, a scene that serves and assesses it, which is exactly
what `OUTCOME_UNASSESSED` asks. **Every outcome served and assessed is now
structurally-or-loudly true.**

## 12c.4 Task (5) — the acceptance, third attempt

Same script (the operator's 3,172-byte multiplication lesson), same three ABCD
outcomes, production parameters (`temperature 0.3`, `top_p 0.9`,
`max_tokens 8192`), three consecutive generations on the pinned engine.

⚠ **Run on a harness, not through the fleet, and this is why:** the acceptance
ran BEFORE the deploy grant arrived (§12c.9); the fleet then received exactly
the code the harness had exercised. The harness renders the user template from the seed —
**verified byte-identical to the active DB row `storyboard_generation` v9** — and
the system template from the seed, which is byte-for-byte what the publisher
would publish as v3; it builds the schema from `design_core.contract` and scores
with `app.services.design_review`, the same modules the worker and the API
import. What it does not exercise is the capture observer and the storage
round-trip, **neither of which 12c touched.**

| | gen 1 | gen 2 | gen 3 |
|---|---|---|---|
| scenes | 15 | 10 | 17 |
| outcomes verbatim | ✅ 3/3 | ✅ 3/3 | ✅ 3/3 |
| **invented ids** | **NONE** | **NONE** | **NONE** |
| `outcome_notes` entries | 3 | 3 | 3 |
| **empty evidence arrays** | **NONE** | **NONE** | **NONE** |
| `dropped_beats` | 1 | 1 | 1 |
| **hard refusals** | **5** | **6** | **5** |
| ↳ `EVIDENCE_MAP_DISAGREES` | 3 | 3 | 3 |
| ↳ `OUTCOME_UNASSESSED` | 2 | 3 | 2 |
| flags | 8 | 8 | 7 |

**The deltas against 12b (3, 2, 2):** RC-Q9's cure held under regression —
outcomes verbatim and zero invented ids in all six generations across both
sessions. `dropped_beats` went from 0,1,1 to **1,1,1** and no gap refusal fired.
**Empty evidence arrays went from present-in-every-generation to none** — that
is task (2) working, and it is the one number that moved the way it was meant to.

⛔ **AND THE COUNT WENT UP, WHICH IS THE PROMOTION AND NOT A REGRESSION.** 12b
recorded `EVIDENCE_MAP_DISAGREES` "flagged on nearly every outcome of every
generation". Those same claims are now refusals. The underlying
`OUTCOME_UNASSESSED` count barely moved (3,2,2 → 2,3,2): **the structure did not
fix the pedagogy, it made the false claim about the pedagogy impossible to
ignore.** That is what was ordered, and it is not the acceptance criterion.

## 12c.5 Task (4) — ⛔ THE HONEST LIMIT, MEASURED, AND ROWED AS RC-Q9c

Before rowing it I ruled out the defect that would have been mine. **The
emission order is `scenes` first, `evidence_map` third** — confirmed on all
three raw contracts — so the model wrote every map with its own scene list
already in context. It is not being asked to name scenes it has not designed.

Two residues, and they are different:

**R1 — the map points away from the model's own assessing scenes.** In
generations 1 and 3 the designer wrote five and five `practice` scenes serving
LO-1 (indices 11-15, and 11-13/15-16) — a genuinely assessed outcome — and then
named `[2,3,4,6]` and `[3,4,7,9]` as the evidence, every one of them `present`.
`not_assessing` on eleven scene-references across the three runs. **The correct
answer existed in its own output and it named something else.**

**R2 — LO-2 and LO-3 are never assessed by any scene, in any generation.** Every
practice scene the designer wrote serves LO-1 only. This is the RC-Q9b
pedagogical failure itself, undiminished.

⛳ **AND THE DEGENERATE CASE THE RULING ASKED ME TO WATCH FOR ARRIVED IN
GENERATION 2.** It contains **no `practice` and no `assess` scene at all**
(`MERRILL_NO_APPLICATION` fired), its `evidence_map` names scenes 2-6 and 10
anyway, and its `design_notes` reads *"providing opportunities for practice and
assessment."* Three statements by one author in one document, two of them false,
and the gate now refuses all three by name. **This is the assess-labelling
degeneracy, and it is rowed with the evidence rather than tuned against.**

⛔ **WHAT (2)+(3) CANNOT FORCE, stated plainly.** Neither the schema nor the gate
can make a named scene GENUINELY assess. A designer that labels a recap `assess`
and points the map at it passes both checks — there is a test that asserts
exactly that and tells the next reader not to "fix" it. What changed is the SHAPE
of the failure the reviewer meets: RC-Q9b arrived as a missing map, which reads
as a machine fault; it now arrives as a brief whose evidence claim contradicts
its own scene labels, which reads as what it is — **a wrong-looking brief, in
front of the reviewer, at the gate, by design.**

⛔ **I DID NOT ITERATE THE PROMPT AGAINST THESE THREE RUNS.** One prompt section
was added — *"EVERY SCENE YOU NAME IS READ BACK AGAINST ITS OWN TWO
DECLARATIONS"* — and it was written **before** the acceptance ran, because the
contract changed and a model judged on a rule nobody told it is being tested on
a secret. It is gated by the publisher like every other load-bearing phrase. It
has **not** been touched since the results came in, and it must not be.

## 12c.6 Tests — zero new failures, one re-aimed

| tree | baseline (stashed) | with 12c | verdict |
|---|---|---|---|
| `ivgs-api` | — | **1632 passed, 0 failed** | ✅ green |
| `ivgs-workers` | 18 failed, 987 passed, 48 skipped, 15 errors | **18 failed, 987 passed, 48 skipped, 15 errors** | ✅ **identical** |

**Baselined by `git stash -u` and re-run, not by memory.** The 18 worker failures
are the pre-existing set §10.1 diagnosed.

`test_wpivgs12c_evidence.py` — **18 new tests**: the schema's bounds and the
no-ids degradation; RC-Q12's unbounded-array guard re-run over the changed shape;
both halves of the promoted belt and their separate reporting; `practice`
counting as well as `assess`; a phantom scene not being double-reported as a
disagreement; a JSONB `["0", null, "x"]` not 500-ing the gate; the seam between
(2) and (3); the absence of `dropped_outcomes`; and **the honest limit, pinned**.

⛳ **ONE EXISTING TEST WAS RE-AIMED, AND ITS FAILURE WAS THE POINT.**
`test_a_clean_design_produces_no_refusals` passed with **no `evidence_map` at
all** — the gate calling a design clean while nothing had decided what would
prove the outcome, which is RC-Q9b in a unit test. It now carries the map a clean
design has to carry, naming the `assess` scene that agrees with it. **Same risk,
new shape. Not weakened.**

## 12c.7 The tree and the push block

**Held: 2 commits. Nothing pushed by me. Working tree clean. No frozen stage body
was touched.**

    dd27799  fix(wp-ivgs-12c): an outcome's evidence cannot be empty, and
             cannot lie about the scenes
    <2nd>    chore(wp-ivgs-12c): deploy v5.37.2, publish prompt v3, and the
             held-count becomes a rule

**Tagged `v5.37.2-evidence-by-structure`** on `dd27799` — the commit the deployed
images actually carry, read back as `IVGS_BUILD_SHA=dd277998…` from inside the
running container rather than inferred.

⚠ **TWO COMMITS, NOT ONE, AND THE COUNT SAYS SO.** §1 asks for one commit per
package unless the order says otherwise. The deploy order arrived after the first
commit was made and tagged, and its work — the deploy record and the new §0 rule
— is a different concern from the contract change. **Amending a tagged commit to
preserve a tidy count would have been the worse answer**, and hiding the second
commit is precisely what the count-gated block exists to catch.

```
# node-01, as the operator
cd /opt/ivgs
EXPECTED=2
ACTUAL=$(git rev-list --count origin/main..HEAD)
if [ "$ACTUAL" -ne "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git push origin main && git push origin v5.37.2-evidence-by-structure
fi
```

⛔ **Read §12c.4 before pushing.** The code is deployed and v3 is published, so
the behaviour it describes is live on the fleet whether or not these commits are
pushed. **The acceptance still does not reach zero hard refusals**, and RC-Q9c is
the reason.

## 12c.8 What I did not verify — 12c's additions to §Z

1. ⛔ **The rendered gate panel, still.** No browser was driven. The panel renders
   findings generically by `severity` (`DesignBriefPanel.tsx:124`), so the
   promotion needs no frontend change — **read from the component source, not
   from a screen.**
2. ⛔ **The acceptance through the real pipeline.** It ran on a harness, before
   the deploy grant arrived, and it was NOT re-run through the fleet afterwards —
   re-running it would have been three more generations of the same script, which
   is the evidence base the ruling told me not to build on. The capture observer
   and the storage round-trip were not re-exercised; 12c did not change them, and
   that is an argument, not a measurement. **The operator's watch is what closes
   this**, and the fleet is now carrying the code it will watch.
3. ⛔ **The whitespace hang under production conditions.** It was produced only
   by a prompt explicitly ordering `[]`. Three real generations did not reach it.
   **That is three runs, not a proof**, and WP-37's check is the net under it.
4. ⛔ **Whether R1 and R2 have the same cause.** The map pointing away from real
   practice scenes (R1) and LO-2/LO-3 never being assessed (R2) may be one defect
   or two. Distinguishing them means changing something and re-running, which is
   the tuning the ruling forbids against this evidence.
5. **`structured_outputs` as a fallback for required-keys.** Measured under
   `response_format: json_schema` only — the same gap 12b left for the enum.

## 12c.9 THE DEPLOY, EXECUTED — every verification line

Granted by the operator 2026-08-29, after §12c.1–12c.8 were written. Ordered
rebuild → deploy → verify by image ID → publish, and run in that order.

**BUILT** on node-01 from `dd27799`, both images carrying their own identity:

    ivgs-api      sha256:2785faf86ac9f41347bceed8685cc149b0d981636c19bd2652424e7ca329620e
    ivgs-workers  sha256:f08df6a8e843bd25dbe37c49eabdbe33843420d377585d466ce92c52a068dc3c

**BANKED** with the RC-Q8 digest sidecar, both `registered in MANIFEST.txt`:

    brucecostello2_ivgs-api_v5.37.2-evidence-by-structure.tar.zst      + .digest
    brucecostello2_ivgs-workers_v5.37.2-evidence-by-structure.tar.zst  + .digest

**LOADED** on nodes 02/03/04 from the shared artifact store — `Loaded image:`
three times. GHCR was not on the path (§6.1).

**DEPLOYED** under §6.1a, stderr never redirected, and ⛳ **it earned its keep
twice inside ten minutes:**

  * `no such service: api` — node-01's service is `fastapi-backend`. A silent
    no-op exiting 0 is exactly what §6.1a exists to prevent, and it did.
  * `grep: ivgs-infra/.env: No such file or directory`, three times — an `ssh`
    block with no `cd`, the second shape §6.1a records. ⚠ **And I re-sent the
    same broken command twice before fixing it**, which is worth recording: the
    guard caught the defect every time and the operator's time was still spent
    on it. Fixed with ABSOLUTE PATHS rather than a `cd` a later edit can drop.

**VERIFIED, seven containers, every line from `verify-deployed-image.sh`:**

    DEPLOY VERIFIED [local]        ivgs-fastapi                 -> ivgs-api:v5.37.2-evidence-by-structure
    DEPLOY VERIFIED [local]        ivgs-celery-default          -> ivgs-workers:v5.37.2-evidence-by-structure
    DEPLOY VERIFIED [local]        ivgs-celery-composition      -> ivgs-workers:v5.37.2-evidence-by-structure
    DEPLOY VERIFIED [local]        ivgs-celery-beat             -> ivgs-workers:v5.37.2-evidence-by-structure
    DEPLOY VERIFIED [192.168.1.91] ivgs-celery-node02           -> ivgs-workers:v5.37.2-evidence-by-structure
    DEPLOY VERIFIED [192.168.1.92] ivgs-cogvideox-worker-node03 -> ivgs-workers:v5.37.2-evidence-by-structure
    DEPLOY VERIFIED [192.168.1.93] ivgs-celery-node04           -> ivgs-workers:v5.37.2-evidence-by-structure

⛳ **AND BY IMAGE ID, WHICH IS THE CHECK THAT ACTUALLY CATCHES A STALE ROLL-OUT**
(RC-Q8 — `verify-deployed-image.sh` compares TAGS). All four worker containers:

    node-01 · node-02 · node-03 · node-04   sha256:f08df6a8e843…
    banked .digest                          sha256:f08df6a8e843…   ✅ identical

**RC-P19 — the image is not the process.** All seven `(healthy)` once the
healthchecks settled; `/api/v1/health` returns 200 with
`"version":"v5.37.2-evidence-by-structure"`, database, redis and seaweedfs all
connected. ⚠ The health path is `/api/v1/health`; plain `/health` answers 404,
which reads like a dead API and is not one.

**PUBLISHED, after the deploy and not before** — publishing v3 against contract-2
workers would have told the model the schema forbids what it still permitted:

    storyboard_generation_system: published v3 (9217 chars, sha256 1bac03c3c9761abf…), superseding v2
    transcript_refinement_system: v1 is already this exact text — no-op, nothing published.

Lineage checked in the database: **v3 active, v2 and v1 inactive, exactly ONE
active row**, and the new rule present in the published text. Rollback is one
UPDATE.

**AND THE LIVE CODE WAS READ BACK OUT OF THE RUNNING CONTAINERS**, because a
verified tag proves which bytes are there and not what they do:

    ivgs-celery-default   CONTRACT_VERSION = design-contract-3
                          evidence_map required = ['LO-1','LO-2','LO-3']
                          LO-2 bound = {"type":"array","minItems":1,"maxItems":4,…}
    ivgs-fastapi          a map naming a `present` scene -> ('refuse', 'EVIDENCE_MAP_DISAGREES')

⚠ **WHAT THE DEPLOY DOES NOT CHANGE: the acceptance verdict.** §12c.4 stands —
5, 6, 5 hard refusals, RC-Q9c rowed and not tuned. **The fleet now refuses those
designs where it used to flag them**, which is the promotion reaching production,
not the criterion being met.

---
---

# §12d — WP-IVGS-12d: backward design becomes the emission order

**2026-08-29 · same package lineage, appended here because the RC-Q rows it
closes are above. Commit and HOLD.**

## 12d.0 STATE AT SESSION END

| | |
|---|---|
| **Done** | Declaration order MEASURED to bind generation order; `assessment_plan` declared FIRST (contract-4); `evidence_map` REMOVED from the model's schema and derived in code; **three refusals deleted, one added**; migration 0051 both directions; prompt v4 published; nodes 01-04 on `v5.37.3-plan-before-scenes` verified by image ID |
| ⛔ **ACCEPTANCE: NOT MET — 6, 6, 2** | ✅ ids verbatim 3/3, zero invented, drops honest 1/1/1, **plan carries one correct entry per outcome in all three**. ⛔ **The plan is prior, honest, stable — and NON-CAUSAL.** Rowed as **RC-Q9d**, prompt NOT iterated |
| **Held** | **2 commits** — the code, and this report/board commit. `git rev-list --count origin/main..HEAD` at close |

**Verified live:** the order probe; three generations on node-02; both suites
baselined; the deploy by image ID on four nodes; migration 0051 up AND down;
`CONTRACT_VERSION`, the property order and `PLAN_ENTRY_UNREALIZED` read out of
the RUNNING containers. ⛔ **Still NOT verified:** the rendered gate panel in a
browser, and that any of this improves a video.

## 12d.1 TASK 1 — the measurement everything rests on

`assessment_plan` is only Foundation §1's sequence if the model must write it
**before** it has scenes. If the decoder lets the model choose, the plan is a
rationalisation of a lesson already designed and the package is theatre. So this
was measured before anything was built, and it was the declared stop-condition.

12c had *observed* the emission order matching the `properties` dict on three
contracts — but that observation has two candidate causes (the grammar, or the
model simply preferring to write scenes first) and could not separate them.
**The probe separates them by disagreeing with the prompt in both directions.**

| probe | schema | prompt demands | emitted | verdict |
|---|---|---|---|---|
| **A** | `properties [plan, scenes]` | **scenes first** | `[assessment_plan, scenes]` | ✅ schema wins |
| **B** | `properties [scenes, plan]` | **plan first** | `[scenes, assessment_plan]` | ✅ schema wins |
| **C** | `properties [scenes, plan]`, `required [plan, scenes]` | plan first | `[scenes, assessment_plan]` | **`properties` rules** |

✅ **DECLARATION ORDER BINDS, IN BOTH DIRECTIONS, AGAINST AN EXPLICIT PROMPT
INSTRUCTION.** A and B fail in opposite directions, so this is the grammar and
not a model preference wearing the grammar's coat.

⛳ **And C settles which list controls: `properties`, not `required`.** That
retroactively explains 12c, where `outcome_notes` was FIRST in `required` and
emitted LAST — a detail that looked like noise and was the rule.

⚠ **So the order of the `properties` dict is now load-bearing code.** Moving
`assessment_plan` down the file would silently convert a commitment into a
rationalisation, and no membership check would notice. A test asserts its
POSITION.

## 12d.2 TASK 2 — design-contract-4

**(a) `assessment_plan`, required, declared first.** Per-outcome required keys
with `additionalProperties: false` — 12c's measured-enforced construct, reused
rather than re-invented — each entry `{evidence_kind: practice|assess,
learner_does: <300 chars}`. `learner_does` is bounded because RC-Q12 applies to
strings as much as arrays.

**(b) `evidence_map` REMOVED from the model's schema.** 12b's principle one layer
up: *never ask the model to assemble what code can compute.* The map is derived
from `serves_outcomes` + `instructional_event` by `shared.design.evidence`, one
function imported by both the worker's parse and the gate so they cannot drift.

⛳ **A DERIVED MAP CANNOT DISAGREE WITH THE SCENES — the failure is
unrepresentable, not merely detected — SO THREE REFUSALS WERE DELETED:**

| deleted | why it is now meaningless |
|---|---|
| `EVIDENCE_MAP_DISAGREES` | nothing left to disagree; the map **is** the scenes |
| `EVIDENCE_MAP_PHANTOM_SCENE` | a derived index came from a scene by construction |
| `EVIDENCE_MAP_NAMES_NOTHING` | it was `OUTCOME_UNASSESSED` under a second name |

`OUTCOME_UNASSESSED` is the one true check, computed from the derived map. ⛳ **A
package that removes three refusals and adds one is not loosening the gate** — it
is removing the ones that measured the model's bookkeeping instead of its design.
The `review()` signature no longer accepts an `evidence_map` at all, so the gate
recomputes from the live scene rows a reviewer is editing rather than from a
value derived at capture.

**(c) `PLAN_ENTRY_UNREALIZED`, the one refusal added.** Every plan entry must be
realized by ≥1 scene serving that outcome and declaring that **exact**
`evidence_kind`, and the refusal names the outcome, the kind and the promise.

⚠ **EXACT, NOT "ANY ASSESSING EVENT", AND THIS IS A CHOICE WITH A COST — SEE
§12d.5.** A `practice` scene does not keep an `assess` promise. Both are in
`ASSESSING_EVENTS`, so `OUTCOME_UNASSESSED` is silent on that case: this refusal
is the only thing that notices a design quietly downgrading what it promised the
learner would do unaided.

**Migration 0051** adds `assessment_plan`, additive, `'{}'::jsonb` default, **both
directions exercised** on the test database — and it deliberately does **not**
rewrite existing briefs: a contract-3 brief's model-authored map is the evidence
that RC-Q9c happened, and normalising it away would destroy the record. A test
asserts the migration contains no `UPDATE`.

## 12d.3 TASK 3 — prompt v4, and the two phrases dropped

The instruction now matches the contract: write the assessment first, then the
arc that realizes it; each entry is a `evidence_kind` and one concrete sentence
on what the LEARNER does. Foundation §2's fading pattern is named as the shape
practice takes for an `apply` outcome — **complete worked example → faded →
independent** — with step 3 identified as what an `assess` entry means.

⚠ **TWO 12c GATE PHRASES WERE DROPPED, AUDITED IN THE PUBLISHER RATHER THAN
QUIETLY DELETED** (12b's discipline): `"EVERY SCENE YOU NAME IS READ BACK AGAINST
ITS OWN TWO DECLARATIONS"` and ``"`practice` or `assess`"``. Both instructed the
model about naming scenes inside `evidence_map`, **a field that no longer
exists**; gating them would refuse every correct v4. Six phrases replace them.
Every other v8/v3 phrase survives and is still gated — audited one by one.

## 12d.4 TASK 4 — the deploy, and the acceptance

**DEPLOYED** `v5.37.3-plan-before-scenes`, ordered build → bank → load →
migrate → deploy → verify → publish.

    ivgs-api      sha256:ba4160c62b91…      ivgs-workers  sha256:d25feffc9741…

Seven containers `DEPLOY VERIFIED`; **all four worker containers on
`sha256:d25feffc9741…`, identical to the banked `.digest`**; all seven healthy;
`/api/v1/health` reports `v5.37.3-plan-before-scenes`. Migration 0051 applied to
production ahead of the new API — additive, so safe under the old code — with
**0 existing briefs** and the operator's **4 projects untouched**.
`storyboard_generation_system` **v4** published AFTER the deploy, v3 preserved
inactive, exactly one active row. Read back out of the running containers:
`design-contract-4`, property order `['assessment_plan', 'scenes', …]`,
`evidence_map` absent, and the API answering `PLAN_ENTRY_UNREALIZED`.

⚠ **§6.1a earned its keep again** — `couldn't find env file: /root/.env` on
node-02, an ssh block with no `cd`. **And again I re-sent the identical command
twice before fixing it**, exactly as in 12c; the guard caught it every time and
the repetition was still mine. Fixed with `--project-directory` and absolute
paths, which removes the dependency on cwd rather than restoring it.

### The three generations

| | gen 1 | gen 2 | gen 3 |
|---|---|---|---|
| scenes | 10 | 9 | 17 |
| outcomes verbatim | ✅ 3/3 | ✅ 3/3 | ✅ 3/3 |
| **invented ids** | **NONE** | **NONE** | **NONE** |
| **plan entries** | **3/3** | **3/3** | **3/3** |
| plan emitted FIRST | ✅ | ✅ | ✅ |
| `dropped_beats` | 1 | 1 | 1 |
| **derived evidence** | **all empty** | **all empty** | LO-1 `[11,12,14,15]`, LO-2 `[11,13]`, LO-3 `[11]` |
| `practice` / `assess` scenes | **0 / 0** | **0 / 0** | **5 / 0** |
| **hard refusals** | **6** | **6** | **2** |
| ↳ `OUTCOME_UNASSESSED` | 3 | 3 | 0 |
| ↳ `PLAN_ENTRY_UNREALIZED` | 3 | 3 | 2 |

## 12d.5 ⛔ RC-Q9d — THE PLAN IS PRIOR, HONEST, STABLE, AND NON-CAUSAL

**What the mechanism achieved, and it is not nothing.** The plan is emitted
first in all three generations, confirming Task 1 at production scale. It carries
one entry per outcome, every time. The `learner_does` sentences are concrete and
correct — *"Multiplies two 2-digit numbers using the standard column algorithm,
producing both partial products with correct carries"* — and the plan is **byte
identical across all three generations**. Asked before it has a lesson, the model
answers well and answers stably.

⛔ **AND THEN THE SCENES DO NOT FOLLOW IT.** One number carries the finding:

> **Across three generations and 36 scenes, the model wrote `assess` ZERO
> times** — while planning an `assess` for LO-1 and LO-3 in every single one.

Two residues:

**R3 — the plan does not cause the arc.** Generations 1 and 2 contain **no
application scene at all**: hook, present, guide, transfer, and nothing else.
`MERRILL_NO_APPLICATION` fired on both. The model wrote a correct assessment plan
and then designed a lecture, in full view of its own plan.

**R4 — the fading sequence stops one step short.** Generation 3 *did* build the
application arc — five `practice` scenes — so every outcome is served and
assessed and `OUTCOME_UNASSESSED` is silent. Its only refusals are the two
outcomes whose plan promised `assess` and received `practice`. **The design gets
the learner to a supported attempt and never to the unaided one.** That is
exactly the third step of the pattern v4 names, and it is a real pedagogical gap,
not a bookkeeping one.

⚠ **THE FACT THE RULING NEEDS, STATED AGAINST MY OWN RESULT.** If
`PLAN_ENTRY_UNREALIZED` matched *any* assessing event instead of the exact kind,
**generation 3 would have scored ZERO hard refusals** and the acceptance would
read 6, 6, 0. I am not making that change. The strictness was specified, it is
what makes the promise mean anything, and loosening a check because it is the
last thing between me and a green number is the definition of tuning to the
metric. **It is the operator's ruling, and the number it would produce is on the
record so the ruling can be made with it.**

⚠ **AND ONE OBSERVATION AGAINST MY OWN PROMPT.** Application-bearing generations
went from 2-of-3 under v3 to **1-of-3** under v4. The v4 system prompt is 1,309
characters longer. That may be noise at n=3 and I will not claim otherwise — but
it is the opposite of the intended direction and it is recorded rather than
omitted. **I did not iterate the prompt against it**, per the standing rule and
the order's explicit instruction to stop here.

⛔ **ROWED AS RC-Q9d. STOPPING FOR THE RULING**, as Task 4 directs.

## 12d.6 Tests — zero new failures, four files re-aimed

| tree | baseline | with 12d | verdict |
|---|---|---|---|
| `ivgs-api` | 1632 passed, 0 failed | **1650 passed, 0 failed** | ✅ green |
| `ivgs-workers` | 18 failed, 987 passed, 48 skipped, 15 errors | **identical** | ✅ zero new |

`test_wpivgs12d_assessment_plan.py` — **23 new tests**: the plan's POSITION (not
its membership); required-keys, closed `evidence_kind`, bounded `learner_does`;
no plan when there are no ids, so no unsatisfiable grammar; RC-Q12's array guard
re-run; the worker parse **ignoring a model-emitted `evidence_map` while keeping
it visible in `raw_contract`**; `review()` having no such parameter; both halves
of the realization check; the exact-kind case that `OUTCOME_UNASSESSED` cannot
see; migration 0051 containing no `UPDATE`; the prompt/publisher agreeing; and
**two round-trip tests that store a contract-4 emission in the database and read
it back through the gate** (see §12d.8 item 2).

**Four existing files re-aimed, none weakened.** `test_wpivgs12c_evidence.py` was
largely rewritten — its subject was a model-authored map — and **the risk behind
each deleted assertion is re-asserted at the new shape**, with a test that walks
the derived map back to the scenes it came from, and one asserting the three
deleted codes no longer construct a `Finding` (a deletion nobody can see is a
deletion that comes back). Two more asserted `evidence_map` in the schema and now
assert the same closure on `assessment_plan`.

## 12d.7 The tree and the push block

**Held: 2 commits. Nothing pushed by me. Working tree clean. No frozen stage body
was touched.**

    5e179ee  feat(wp-ivgs-12d): backward design becomes the emission order
    <2nd>    docs(wp-ivgs-12d): the acceptance, RC-Q9d, and the board

**Tagged `v5.37.3-plan-before-scenes`** on `5e179ee` — the commit the deployed
images carry, read back as `IVGS_BUILD_SHA` from the running container.

⚠ Two commits again, and for the same honest reason as 12c: the code was
committed and tagged before the images were built, so the deployed image names a
real commit; the acceptance result could only be written after. **The block
expects 2, measured with `git rev-list --count`** — §0's new rule, used here for
the first time.

```
# node-01, as the operator
cd /opt/ivgs
EXPECTED=2
ACTUAL=$(git rev-list --count origin/main..HEAD)
if [ "$ACTUAL" -ne "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git push origin main && git push origin v5.37.3-plan-before-scenes
fi
```

⛔ **Read §12d.5 before pushing.** The code is deployed and v4 is published, so
this behaviour is live whether or not these commits are pushed.

## 12d.8 What I did not verify — 12d's additions to §Z

1. ⛔ **The rendered gate panel, still.** No browser was driven. The panel renders
   findings generically by `severity`, so the deleted and added codes need no
   frontend change — **read from the component source, not from a screen.**
2. ⚠ **The acceptance through the real pipeline** — harness again, for the reason
   §12c.8 gives: re-running it through the fleet would be three more generations
   of the same script. ✅ **But the storage half of this caveat is now CLOSED
   rather than flagged.** 12d changed `parse_contract` and the ingest, which
   made "the round-trip was not re-exercised" too weak to leave standing, so a
   real contract-4 emission is now driven through the worker's parse, the API's
   service and the gate **against the database**: the plan persists, the stored
   `evidence_map` is `{"LO-1": [2], "LO-2": [3]}` — derived and keyed by the
   operator's ids — the outcome text survives verbatim, and a broken promise
   still comes back as `PLAN_ENTRY_UNREALIZED` from a STORED brief rather than
   only from a hand-built dict. ⛳ **Writing it caught my own wrong assumption
   about the data** — I asserted `outcomes[].text` still carried the `"LO-1: "`
   marker; it does not, the marker is carried separately so the parse stays
   reversible. **What remains unexercised is the HTTP ingest route and the
   capture observer**, neither of which 12d changed.
3. ⛔ **Whether R3 and R4 are one defect or two.** Distinguishing them means
   changing something and re-running — the tuning the ruling forbids.
4. ⛔ **Whether the longer v4 prompt caused the arc regression.** n=3, no control.
5. **The `minItems` whitespace corridor** is unchanged and unexercised; contract-4
   has no `minItems` array left in `assessment_plan`, but `scenes` and
   `source_refs` still carry one.

---
---

# §12e — WP-IVGS-12e: the model learns what an assessment is, and it was never the problem

> ⛔ **SUPERSEDED IN PART BY §12f, 2026-08-30 — READ THIS BEFORE ACTING ON §12e.4.**
> RC-Q9e below concludes *"THE MODEL HAS NEVER ONCE INVENTED A SCENE"* and infers
> from it that the model **is not designing at all** and that *"no schema can"*
> compel a scene with no source span. **The count is right and the inference is
> wrong.** §12f took the second-script measurement §12e.6 item 2 said was needed:
> handed a SPARSE script with no practice material in it, the same model on the
> **same v5/contract-4 stack** invented scenes and emitted this project's first
> `assess` events. The model will not invent when it has something to excerpt; it
> invents readily when it does not. **A schema did compel it** — contract-5, §12f.3.
> Everything else in §12e stands, including the standing rule in §12e.1.

**2026-08-29 · same package lineage. Commit and HOLD.**

## 12e.0 STATE AT SESSION END

| | |
|---|---|
| **Ruling recorded** | ✅ `PLAN_ENTRY_UNREALIZED` **keeps the exact kind match**. Evidence kinds are semantic and **are never collapsed to green a number** — now a standing rule on the row, and the precedent |
| **Done** | Prompt **v5**, purely additive (34 lines, **zero deletions**), operational definitions of `practice` and `assess` traced clause by clause to the Foundation; five new gate phrases, **none audited out**; API rebuilt to `v5.37.4-assess-defined` and redeployed |
| ⛔ **ACCEPTANCE: NOT MET — 6, 5, 6** | ⛔ **The hole survived operational definitions: `assess` scenes [0, 0, 0]**, unchanged from 12d |
| ⛔ **ROOT CAUSE FOUND, AND IT IS NOT WHAT THIS PACKAGE REPAIRED** | **83 scenes across six generations: 83 `sourced`, ZERO `designed`, ZERO `assess`.** Rowed as **RC-Q9e**. **STOPPING for the architectural ruling**, as ordered |
| **Held** | **2 commits** — `git rev-list --count origin/main..HEAD` at close |

## 12e.1 The ruling, recorded

⛔ **EVIDENCE KINDS ARE NEVER COLLAPSED TO GREEN A NUMBER.** `practice` is the
supported attempt; `assess` is the unaided one; a lesson stopping at the
supported attempt has not demonstrated the outcome's stated **Degree** (Foundation
§2's ABCD). The exact-kind match in `PLAN_ENTRY_UNREALIZED` stands, and the
refusal to loosen it — with generation 3 of 12d one check away from zero — is the
precedent for the next package that finds itself in that position.

## 12e.2 TASK 1 — prompt v5, additive only

**The diff is 34 added lines and zero deleted ones**, banked at
`reference/wpivgs12e-evidence/prompt-v4-to-v5.diff`. One new section,
`## WHAT \`practice\` AND \`assess\` ACTUALLY ARE, AS SCENES`:

- **`practice`** — the learner attempts it **with support visible**: a guided
  step, a prompt-then-confirm, a faded worked example with the working still on
  screen. The middle of the fading sequence.
- **`assess`** — the learner performs it **unaided**, in three beats and no
  fourth: **POSE** the problem cold (no method reminder, no first step, no column
  pre-filled) → **HOLD**, a silent attempt window with nothing narrated and
  nothing highlighted → **REVEAL** for self-check.
- *"If your scene narrates the method while the learner is supposed to be
  attempting, you have written a `guide` and labelled it `assess`."*
- For an `apply` outcome the assess is **the whole procedure, not a fragment**;
  and an `assess` comes **after** that outcome's `practice`.

⛳ **EVERY CLAUSE TRACES TO THE NORMATIVE SOURCE, NOT TO A RUN** — which is what
separates this from tuning: Foundation §3's event-8 row (*"full second problem,
learner-first"*), §4's modality table (*"prompt + pause + reveal … pose the
problem, hold, then reveal"*), §4's load rules (the fading sequence), and §2's
worked-example effect with its **Degree** column.

**Five gate phrases added, none removed.** A test asserts that every phrase v4
gated is still present — this package had to earn its keep by adding, not by
trading one instruction away for another.

### ⚠ A REBUILD WAS NEEDED, AND THE ORDER'S REASONING DID NOT COVER WHY

The order said no rebuild was needed because contract-4 and the validator are
untouched — **and that reasoning is correct about ORDERING**: 12c's
publish-after-deploy rule exists to stop a prompt promising what the deployed
contract does not enforce, and there is no contract change here.

⛔ **But the publisher reads the seed from INSIDE the image.** Measured before
publishing: the running container's
`/app/seed/default_prompts/storyboard_design_system.j2` was **10,615 bytes** (v4)
against the tracked file's **12,355**. Publishing without a rebuild would have
re-published **v4's text** and reported success — the RC-E failure class again.

So the API image alone was rebuilt to **`v5.37.4-assess-defined`** and
redeployed. ⛳ **The workers were NOT rebuilt and their tag is deliberately left
at `v5.37.3-plan-before-scenes`**: no worker code changed, they do not carry the
seed, and rebuilding to move a tag would mint a new digest for identical source —
the board's own stated reason for leaving the frontend at `v5.37.0`. **A split
tag across the fleet is the honest state and the board says so.**

Reusing the 12d tag was never an option: different bytes under one tag is exactly
RC-Q8, and `save-image-artifact.sh` would have refused it.

**Published:** `storyboard_generation_system` **v5** (12,250 chars, sha256
`635347538553b7da…`), superseding v4; **v4 preserved inactive, exactly one active
row**, rollback one UPDATE. Verified in the database that v5 carries the
definitions, and read back from the running containers that **contract-4 and the
exact-kind refusal are unchanged**.

## 12e.3 TASK 2 — the acceptance, and it did not move

| | 12d gen 1-3 (v4) | 12e gen 1 | 12e gen 2 | 12e gen 3 |
|---|---|---|---|---|
| scenes | 10 / 9 / 17 | 18 | 19 | 10 |
| **`assess` scenes** | **0 / 0 / 0** | **0** | **0** | **0** |
| `practice` scenes | 0 / 0 / 5 | 0 | 5 | 0 |
| application-bearing | 1 of 3 | ✗ | ✓ | ✗ |
| plan entries | 3/3 every time | 3/3 | 3/3 | 3/3 |
| ids verbatim / invented | ✅ / NONE | ✅ / NONE | ✅ / NONE | ✅ / NONE |
| `dropped_beats` | 1 / 1 / 1 | 2 | 1 | 1 |
| **hard refusals** | **6, 6, 2** | **6** | **5** | **6** |

**The regressions held** — outcomes verbatim, zero invented ids, drops declared,
the plan still correct and stable in all three. **Nothing else moved**, and the
refusal count is marginally worse.

**The assess scenes' shape, which the order asked for: there were none to
describe.** Zero across three generations and 47 scenes.

## 12e.4 ⛔ RC-Q9e — THE ROOT CAUSE, AND IT IS NOT THE ONE I WAS REPAIRING

Generation 2 produced five `practice` scenes. Their narration:

> *"Start with the ones digit, which is 1. 1 times 2 equals 2. 1 times 3 equals
> 3. So our first answer is 32."* … *"2 times 2 equals 4. 2 times 3 equals 6.
> That gives us 640."* … *"Now add: 32 plus 640 equals 672."*

⛔ **THAT IS NOT A PRACTICE SCENE. IT IS A FULLY NARRATED WORKED EXAMPLE.** The
narration performs every step **for** the learner; there is no pose, no hold, no
reveal, and nothing for the learner to do. And it is **near byte-identical to
12d generation 3's**, written under v4, before any of these definitions existed.
**v5 changed the label's definition and did not change one word of the scene.**

That prompted the census that should have been run five packages ago:

| | scenes | `sourced` | **`designed`** | **`assess`** |
|---|---|---|---|---|
| 12d gens 1-3 (v4) | 36 | 36 | **0** | **0** |
| 12e gens 1-3 (v5) | 47 | 47 | **0** | **0** |
| **six generations** | **83** | **83** | **0** | **0** |

> ⛔ **SUPERSEDED BY §12f.2:** *has never* is accurate for this script and *cannot*
> is not. See the banner at the head of §12e.

⛔ **THE MODEL HAS NEVER ONCE INVENTED A SCENE.** Every scene of every generation
is `origin: "sourced"`, anchored to a span of the uploaded script. The script's
second problem (32×21) is **fully worked with every step narrated**, so an
unaided attempt exists nowhere in it — and the model has no span to anchor one
to.

⛳ **SO THE DIAGNOSIS THIS PACKAGE ACTED ON WAS WRONG, AND I SHOULD SAY SO
PLAINLY.** The model does not fail to understand what an `assess` scene is. It
is **not designing at all**: it segments the uploaded script and attaches labels.
Telling a segmenter what an assessment looks like cannot produce one, because the
missing step is not knowledge — it is **invention**, and the prompt has invited it
since v8 (*"Material the outcomes require that the script lacks is legitimate:
you invent it, mark the scene `origin: designed`"*). **That invitation has been
declined 83 times out of 83.**

⛳ **AND IT EXPLAINS THE WHOLE LINE OF PACKAGES AT ONCE.** RC-Q9c (evidence
pointing at `present` scenes), RC-Q9d (a plan promising `assess` and never
building one), RC-Q9e (definitions changing nothing) are one defect seen three
times: **the excerpter the Design Core was built to remove is still there,
wearing the contract's labels.** Every structural fix has correctly forced the
model to *declare* better; none has made it *design*, and no schema can, because
the contract cannot compel a scene that has no source span.

⛔ **ROWED AS RC-Q9e. STOPPING FOR THE ARCHITECTURAL RULING**, exactly as Task 2
directs. The next move is the operator's to order and not mine to attempt — and
⚠ **the census above should inform it**: whatever shape it takes, the thing to
fix is that stage 2 will not write a scene the script does not contain, and
"`designed` scenes: 0 of 83" is the number to measure it against.

## 12e.5 Tests, and the tree

| tree | baseline | with 12e | verdict |
|---|---|---|---|
| `ivgs-api` | 1650 passed, 0 failed | **1652 passed, 0 failed** | ✅ green |
| `ivgs-workers` | 18 failed, 987 passed, 48 skipped, 15 errors | **identical** | ✅ zero new |

Two tests added: one pinning all four beats of the `assess` definition, one
asserting **v5 removed nothing v4 gated**.

**Held: 2 commits. Nothing pushed by me. Working tree clean. No frozen stage body
was touched. No contract, validator or worker code changed.**

    1f464bb  feat(wp-ivgs-12e): the model learns what an assessment IS
    <2nd>    docs(wp-ivgs-12e): the acceptance, and RC-Q9e — 0 designed scenes in 83

```
# node-01, as the operator
cd /opt/ivgs
EXPECTED=2
ACTUAL=$(git rev-list --count origin/main..HEAD)
if [ "$ACTUAL" -ne "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git push origin main && git push origin v5.37.4-assess-defined
fi
```

⛔ **THE BROWSER WATCH DOES NOT FOLLOW THIS ONE.** The hand-off the order
anticipated was conditional on a pass, and this is not a pass: v5 is live and a
real project through the gate will be **refused**, for the reasons in §12e.4.
**The next step is the RC-Q9e ruling, not the watch.**

## 12e.6 What I did not verify — 12e's additions to §Z

1. ⛔ **The rendered gate panel, still.** No browser was driven, and this package
   gives no occasion to: the gate refuses.
2. ⛔ **Whether the model would invent a scene if the script contained no worked
   example at all.** The census shows 0 `designed` scenes against *this* script;
   it does not establish that the model *cannot* invent, only that it never has
   here. **One script, six generations** — that is the limit of the claim, and
   distinguishing "will not" from "cannot" needs a second script, which is a
   measurement the ruling may want and which I did not take.
3. ⛔ **Whether prompt length is now hurting.** The system prompt has grown
   7,788 → 12,250 chars across v1-v5 and the arc has not improved. Untested.
4. **The API/worker tag split** (`v5.37.4` / `v5.37.3`) is correct and
   deliberate, but `verify-deployed-image.sh` compares tags per container and
   nothing checks that the SPLIT is intentional. A future reader sees two tags.

---
---

# §12f — WP-IVGS-12f: the excerpter is forced to design

**2026-08-29/30 · same package lineage. Commit and HOLD.**

## 12f.0 STATE AT SESSION END

| | |
|---|---|
| ⛳ **THE 12e DIAGNOSIS IS WRONG AND §12e IS SUPERSEDED ON THIS POINT** | RC-Q9e concluded *"the model has never once invented a scene"* and inferred it **is not designing at all**. TASK 0 measured the second script §12e.6 item 2 said was needed, and the answer is **WILL NOT, not CANNOT**: a SPARSE script produced designed scenes and the project's first `assess` events under the **unchanged** v5/contract-4 stack. The model is not incapable of invention — it is **out-competed** by anything it can excerpt |
| **Done** | **design-contract-5**: `designed_assessments`, REQUIRED, one key per outcome, each value a full scene the grammar pins to `origin: designed` / `instructional_event: assess` / `serves_outcomes: [that outcome]`. **Placement by code** (`shared/design/merge.py`). Migration **0052**, both directions. **Prompt v6**, additive, 30 gated phrases, **none removed**. Built, deployed to nodes 01-04, published, read back from the running containers |
| ⛳ **THE HOLE IS CLOSED** | **0 designed / 0 assess in 83 → 10 designed / 10 assess in 43**, three generations, plus a second three-generation run that replicates it |
| ⛔ **ACCEPTANCE: NOT MET — 1, 1, 1 (and 1, 1, 1 again)** | **Six generations, six identical refusals**: `PLAN_ENTRY_UNREALIZED` on LO-2. The plan promises `practice`; the grammar forces only `assess`; no practice scene is built. **RC-Q9d's non-causal plan, surviving in the one kind the grammar does not force.** Rowed as **RC-Q9f**. ⛔ **NOT TUNED — see 12f.7** |
| ⛳ **The degeneracy check the order named did NOT fire** | The designed assessments pose **fresh numbers** (43×25, 43×27) against a script that works 23×14 and 32×21, cold, with no method reminder. Quoted verbatim in **12f.8** |
| ⛔ **I DESTROYED THE FIRST RUN'S EVIDENCE** | A re-scoring script imported the harness and its module-level write truncated **eight banked emission files to `[]`**. All four measurements were **re-run and re-banked**; both sets are reported. **12f.11** |
| **Held** | **2 commits** — `git rev-list --count origin/main..HEAD` at close |

## 12f.1 Premises of the order, checked before acting

| Premise | Checked | Verdict |
|---|---|---|
| Held commits, from d2fc50c | `git fetch` then `git rev-list --count origin/main..HEAD` → **0** | ⚠ **The operator pushed both 12e commits.** Measured at the ref, per the §0 rule 12c added |
| Alembic head is 0051 | `alembic_version` = **0051**; tree's highest `0051_wp_ivgs_12d_assessment_plan.py` | ✅ **TRUE.** Next free number is **0052** |
| Nodes 01-04 deployable under §6.1a | ssh reachable on `.91`, `.92`, `.93`; all four ran `v5.37.3`/`v5.37.4` | ✅ **TRUE** — unlike 12's opening, where three nodes were offline |
| Fleet is split `v5.37.4` API / `v5.37.3` workers | `docker ps` on all four | ✅ **TRUE**, exactly as §12e recorded |
| Prompt v5 active, contract-4 live | `prompts` row v5 `is_active = t`; `CONTRACT_VERSION` in the running worker | ✅ **TRUE** |
| The operator's script is the 3,172-byte multiplication lesson | Asset `62cd2663`, fid `7,0237c99b8fb7`, **3,172 bytes, md5 `f65f340c…`** — fetched read-only from SeaweedFS | ✅ **TRUE**, and it is the file every generation below used |
| The banked copy is that script | `dev/workpackages/reference/wpivgs12-acceptance/uploaded-script.txt` is **3,008 bytes**, 164 lines, **every line differing** | ⚠ **LINE-ENDING NORMALISED.** Same 164 lines, CRLF→LF, so 164 bytes lighter. The BANKED copy is not byte-identical to what the pipeline receives, and a span offset computed against one does not hold against the other. Flagged, not fixed — the bank is 12's and rewriting it would destroy the record of what 12 actually scored |

## 12f.2 TASK 0 — the second-script measurement, and it overturned the diagnosis

Two mini-scripts, a different arithmetic topic from the operator's, one generation
each under the **unchanged** v5/contract-4 stack. Banked at
`dev/workpackages/reference/wpivgs12f-evidence/`.

  * **B1** — subtraction with regrouping, 366 words, containing an **EXPLICIT
    unaided-problem span**: *"Now you try. … Work out 63 minus 48. Pause here. Do
    not read on yet. … The answer is 15."*
  * **B2** — dividing by 10 and by 100, 411 words, **SPARSE**: a procedure and
    the reason it works, **no practice material of any kind**, not one worked
    number.

| | scenes | `sourced` | **`designed`** | **`assess`** | `practice` |
|---|---|---|---|---|---|
| **baseline** — operator's script, 6 gens, v4+v5 | 83 | 83 | **0** | **0** | 5 |
| **B1** run A (explicit unaided span) | 21 | 21 | **0** | **0** | 3 |
| **B1** run B (re-banked) | 13 | 13 | **0** | **1** | 2 |
| **B2** run A (sparse) | 15 | 10 | **5** | **1** | 2 |
| **B2** run B (re-banked) | 13 | 10 | **3** | **3** | 0 |

### ⛳ THE VERDICT, AND IT IS NOT THE ONE RC-Q9e WROTE

⛔ **B2 INVENTED, UNDER THE STACK THAT HAD INVENTED NOTHING IN 83 SCENES.** Same
prompt v5, same contract-4, same engine, same day. Its designed scenes pose
numbers that appear nowhere in the script — *"Now it's your turn to try. Divide
456 by 10."* — because the script contains no numbers at all to lift.

⛔ **B1 DID NOT INVENT, AND IT IS THE SHARPER RESULT.** The script hands the model
an unaided problem in plain words and tells the learner to pause. The model
**found the span and anchored to it, both runs** — run A across three `practice`
scenes, run B as a single `assess` — and in **34 scenes across the two runs it
invented nothing at all.**

So the two questions the order separated come apart cleanly:

  * **Label-understanding is partial and unstable.** Handed a literal unaided
    problem, the model called it `practice` once and `assess` once. It has some
    grip on the distinction and no reliability.
  * **Invention-refusal is total, and conditional on supply.** 0 `designed` in
    every generation of every script that contained *anything* excerptable — 117
    scenes now — and immediate invention on the one script that contained
    nothing.

⛳ **THAT IS WHY THE FIX IS GRAMMAR AND NOT PROMPTING, AND IT IS A DIFFERENT
ARGUMENT FROM THE ONE RC-Q9e MADE.** 12e concluded the model cannot design and
that no schema can compel a scene with no source span. B2 shows it designs
readily when nothing competes. The defect is **competition inside one
`scenes[]` array**, where sourced material always wins. Contract-5 does not
argue with that preference — it removes the contest.

⚠ **NO FIX CAME FROM THIS TABLE, as ordered.** It sharpened the row and it cost
two generations, then two more to re-bank.

## 12f.3 TASK 1 — the probe first, then contract-5

### The RC-Q12 probe, run before a line of the contract was written

Every probe **orders the model to break the construct**, which is 12c's
discipline: a schema the model had no wish to violate proves nothing. Each is
checked for all three outcomes this engine has shown — ENFORCED, HTTP 400
(`uniqueItems`, `contains`), and the dangerous one, **200 with the constraint
silently doing nothing** (`guided_json`).

| probe | ordered to emit | emitted | verdict |
|---|---|---|---|
| **A** single-value `enum`, scalar | `"sourced"` | `"designed"` | ✅ **ENFORCED** (the proven construct, re-measured) |
| **B** `const`, scalar string | `"sourced"` | `"designed"` | ✅ **ENFORCED — `const` IS implemented**, not 400, not a no-op |
| **C** `const`, whole array | `["LO-1","LO-3","LO-9"]` | `["LO-2"]` | ✅ **ENFORCED** |
| **D** array `minItems=maxItems=1` + enum | `["LO-1","LO-3","LO-9"]` | `["LO-2"]` | ✅ **ENFORCED** |
| **E** the contract-5 construct, whole | omit `LO-1`, add `LO-7`, event `present`, serves `["LO-4","LO-5"]`, origin `sourced` | every pin held | ✅ **ENFORCED in every part** |

⛳ **THE RULING, AND IT IS THE ORDER'S TIE-BREAK APPLIED HONESTLY.** `const` works.
It is **not used.** For the scalars it is a plain tie with `enum`, so the proven
construct wins. For the array it looks stronger and **is not**: RC-Q12's hang is
the decoder forbidding `]` while whitespace stays legal, and that corridor is
identical under `const ["LO-2"]` and under `minItems=maxItems=1`. `const` buys
nothing the measured-since-12c construct does not already give, and taking an
unproven key into the load-bearing contract to buy nothing is how a package
acquires a second unmeasured variable. **Measured, banked at
`wpivgs12f-evidence/const-probe.json`, and deliberately unused.**

### design-contract-5

⛔ **`designed_assessments`, REQUIRED, one key per outcome,
`additionalProperties: false`.** Each value is a full scene object. Three fields
are not decisions the model makes:

    provenance.origin      enum ["designed"]   it cannot cite a span
    instructional_event    enum ["assess"]     it cannot downgrade to `practice`
    serves_outcomes        [enum [that id]]    it cannot re-aim at another outcome

**An output lacking an invented unaided scene per outcome is not parseable.** The
excerpter cannot decline, because there is nothing to decline.

⛳ **DECLARED SECOND, AND THE POSITION IS THE ARGUMENT.** Declaration order binds
generation order (12d, measured in both directions), so `designed_assessments`
sits between `assessment_plan` and `scenes` and the model writes the unaided
attempt **while the scene list is still empty** — with no worked example of its
own to lift numbers out of. Foundation §1 in full for the first time: outcomes,
then the evidence, then the assessment that IS the evidence, then the arc.
Property order in the deployed worker:

    ['assessment_plan', 'designed_assessments', 'scenes', 'dropped_beats',
     'design_notes', 'outcome_notes']

⛔ **AND THERE IS NO `scene_index`.** Placement is the third application of 12b's
principle — never ask the model for what code can compute. `shared/design/merge.py`
inserts each designed assessment **after the LAST scene serving its outcome**, the
end of that outcome's fading sequence, and re-indexes the merged design 0..n-1.
The model's own `scenes` array is never edited; the merged sequence is what stage
3+ and the derived `evidence_map` consume, and `raw_contract` keeps the emission
verbatim as the evidence limb.

⚠ **RE-INDEXING IS NOT COSMETIC AND IT CORRECTED A LATENT DEFECT.** The frozen
stage body has always re-indexed its rows sequentially after validation, while
`parse_contract` preserved the model's own numbering — so a brief's
`evidence_map` could name a row that was somewhere else. Two 12d tests pinned the
old numbering and were **re-aimed with the reason recorded** (12f.10).

⛔ **AND THE MERGED LIST HAS TO REACH THE FROZEN BODY, OR THE ASSESSMENT IS NEVER
RENDERED.** `stage2_storyboard` builds its `StoryboardScene` rows from `scenes`
and POSTs them. Without a seam, every designed assessment would exist in the
brief, be reviewed at the gate, and appear in **no scene row** — designed,
stored, approved and invisible. So `clients/vllm_client` grows a **third seam of
the same shape as the two 12a added**: `set_document_transform`, applied to
`chat_json`'s parsed document, armed by `celery_app`'s prerun for the storyboard
task only, cleared at postrun, never raising, and **identity when nothing is
registered**. It calls the same `merged_scene_sequence` the parse calls, so the
brief's `scene_designs` and the `storyboard_scenes` rows are one list computed
once — 12d's lesson about `derive_evidence_map`, applied before it could be
learned twice. No frozen body was edited and no exception #3 was requested.

**Every array in the new object carries a `maxItems`** (RC-Q12 (d)); the only one
is `serves_outcomes`, bounded 1..1. The `minItems` corridor is honoured on 12c's
argument: it is reachable only when the model's next token would be `]`, and a
schema pinning the array to one known id under a prompt naming that outcome does
not go there.

### Migration 0052, and the validator

**`storyboard_scenes.designed_rationale`**, nullable, additive, **exercised both
directions on the live database** (0051→0052→0051→0052, column present/absent/
present, `alembic_version` following). `scene_origin` has accepted `'designed'`
since 0048 and **not one row ever carried it**; contract-5 makes designed scenes
mandatory, so an invented scene now reaches the table — and `scene_origin =
'designed'` with no account of itself is the silent-invention defect one layer
down. The gate renders it beside the origin.

⛳ **A GENERAL INVARIANT TEST CAUGHT A REAL DEFECT IN THIS, WITHIN THE HOUR.**
`test_the_design_fields_are_editable_at_the_gate` iterates `SCENE_DESIGN_FIELDS`
and asserts each is in `StoryboardService.OPTIONAL_SCENE_FIELDS` — it noticed the
new field was **storable and not correctable at the gate**, which is precisely
the "shown a problem and denied the fix" shape it was written for. Fixed in the
code; the test was not touched.

⛔ **`PLAN_ENTRY_UNREALIZED(assess)` AND `OUTCOME_UNASSESSED` ARE NOW
STRUCTURALLY UNREACHABLE, AND NEITHER IS DELETED.** Asserted directly — including
against the hostile case, a pure lecture in `scenes[]`, which under contract-4
was three refusals every time. Both checks stay as the loud regression belt: a
structural guarantee is a claim about a schema, a merge and a decoder, all three
editable by someone who does not know why they are shaped this way, and this
lineage is a record of guarantees narrower than believed. **The `practice` branch
is untouched and still fires** — and 12f.7 is where it fires.

⚠ **AND ONE REFUSAL GOT WEAKER, WHICH IS 12f's OWN COST AND IS NOT HIDDEN.**
`OUTCOME_UNSERVED` asks whether ANY scene declares the outcome, and a designed
assessment declares it — so an outcome the lesson never **teaches** is no longer
unserved. `PRACTICE_NOT_PREPARED` names exactly that shape and remains a FLAG.
Promoting it is an operator ruling and this package did not take it; 12c's
promotion of `EVIDENCE_MAP_DISAGREES` was **ordered**, and that precedent is the
point. A test pins the behaviour so it is discovered by reading, not by accident.

## 12f.4 TASK 2 — prompt v6

**+3,691 characters, 12,250 → 15,941, and ZERO deletions.** One new section,
`## ⛔ THE SCRIPT IS SOURCE MATERIAL. THE ASSESSMENTS ARE YOURS TO AUTHOR.`, plus
one additive line inside backward-design stage 2 and one bullet under the
raw-material rules.

  * *"The script is source material for `present`, `guide` and `recall` — the
    teaching. **It is not the source of your assessments.** No script contains
    the learner's own unaided attempt, because that attempt has not happened yet:
    it is the thing the whole lesson exists to produce."*
  * ⛔ **POSE THE PROBLEM COLD, IN FRESH NUMBERS THE SCRIPT NEVER WORKED** — *"If
    the script teaches 23 × 14 and then works 32 × 21, your assessment uses
    NEITHER of them."*
  * **ONE ENTRY PER OUTCOME ID**, and the three pinned fields named so the model
    knows why before the decoder makes it.
  * ⛳ **AND YOU DO NOT PLACE THEM** — *"design each one as an ENDING."*
  * ⚠ A modality line earned by B2, whose designed assess was refused
    `MOTION_WITHOUT_PARAMS`: a computational attempt is `motion_graphics` **with**
    a template; an explain-or-check attempt is `image` or `talking_head`, because
    the renderer has no template for it.

**Five gate phrases added, none removed.** `test_v6_removed_nothing_v5_gated`
reads the publisher's own tuple rather than a second copy, so the two cannot
drift: **30 phrases, 0 missing.**

## 12f.5 TASK 3 — build, deploy, publish

**BOTH images rebuilt — no tag split this time**, because the worker-side parse,
the client seam and `celery_app`'s arming all changed alongside the API. Built on
node-01 from `ac77733`, which is why the code is committed **before** the images
exist: `IVGS_BUILD_SHA` must name a commit that does.

    ivgs-api      sha256:f0c067d792be90c0804136f70149f68c9cc443a8b79f500a5e5871ea917771cf
    ivgs-workers  sha256:70ec2c3fefa7d11b932a0b1aa1bb2f88193f88e3d6501e14790753fa7a83fe48

**BANKED** with RC-Q8 digest sidecars, both `registered in MANIFEST.txt`.
**LOADED** on nodes 02/03/04 from the shared store — `Loaded image:` three times.

⛔ **SCHEMA BEFORE CODE.** 0052 was applied to the live database **first**: the new
ORM column would break a SELECT if the column were missing, so the image that
reads it is deployed after. Compose invocations were **derived from container
labels**, never guessed — and the labels say **two** `-f` files on node-01, not
the three `dev/CLAUDE.md` §6 describes. The machine wins.

**VERIFIED, seven containers, every line from `verify-deployed-image.sh`:**

    DEPLOY VERIFIED [local]        ivgs-fastapi                 -> ivgs-api:v5.37.5-assessments-authored
    DEPLOY VERIFIED [local]        ivgs-celery-default          -> ivgs-workers:v5.37.5-assessments-authored
    DEPLOY VERIFIED [local]        ivgs-celery-composition      -> ivgs-workers:v5.37.5-assessments-authored
    DEPLOY VERIFIED [local]        ivgs-celery-beat             -> ivgs-workers:v5.37.5-assessments-authored
    DEPLOY VERIFIED [192.168.1.91] ivgs-celery-node02           -> ivgs-workers:v5.37.5-assessments-authored
    DEPLOY VERIFIED [192.168.1.92] ivgs-cogvideox-worker-node03 -> ivgs-workers:v5.37.5-assessments-authored
    DEPLOY VERIFIED [192.168.1.93] ivgs-celery-node04           -> ivgs-workers:v5.37.5-assessments-authored

⛳ **AND BY IMAGE ID, WHICH IS THE CHECK THAT CATCHES A STALE ROLL-OUT** —
`verify-deployed-image.sh` compares TAGS (RC-Q8). All seven **running** containers'
`.Image`, against the banked `.digest`: `f0c067d7…` for the API, `70ec2c3f…` for
all six worker containers on all four nodes. **Identical.**

**RC-P19 — the image is not the process.** Four node-01 containers `(healthy)`;
`/api/v1/health` returns `{"status":"healthy","version":"v5.37.5-assessments-authored",…}`
with database, redis and seaweedfs connected. ⚠ **On port 8001, not 8000** — the
12c report says `/api/v1/health` without the port and 8000 refuses the
connection, which reads like a dead API and is not.

**PUBLISHED AFTER THE DEPLOY, per 12c's rule** — and the 12e lesson was checked
rather than assumed: the seed **inside the running image** was compared to the
tracked file before publishing, `16,080` bytes and sha `62560091…` on both.

    storyboard_generation_system: published v6 (15941 chars, sha256 62560091f531c6d3…), superseding v5
    transcript_refinement_system: v1 is already this exact text — no-op, nothing published.

Lineage in the database: **v6 active, v1–v5 inactive, exactly ONE active row**;
the new phrases present and v5's `THE LEARNER PERFORMS IT UNAIDED` still there.
Rollback is one UPDATE.

**AND THE LIVE BEHAVIOUR WAS READ BACK OUT OF THE RUNNING CONTAINERS**, because a
verified tag proves which bytes are there and not what they do:

    ivgs-celery-default  CONTRACT_VERSION = design-contract-5
                         property order   = [assessment_plan, designed_assessments, scenes, …]
                         designed required = ['LO-1','LO-2','LO-3'], additionalProperties = False
                         pins LO-2        = event ['assess'] | origin ['designed'] | serves ['LO-2']
                         scene_index offered = False
                         merge placement  = [(0,LO-1), (1,LO-1 assess), (2,LO-2), (3,LO-2 assess), (4,LO-3 assess)]
                         prerun arms transform: True   postrun clears it: True
    ivgs-fastapi         lecture WITHOUT the designed assess -> OUTCOME_UNASSESSED, PLAN_ENTRY_UNREALIZED
                         lecture WITH it (contract-5 shape)  -> NO REFUSALS
                         designed_rationale storable: True   editable at the gate: True

## 12f.6 TASK 4 — the acceptance, sixth attempt, census-scored

Three consecutive generations, the operator's script (md5 `f65f340c…`), the same
three ABCD outcomes, the same production parameters — **and then three more**,
because I destroyed the first run's emissions (12f.11). Both sets are reported;
neither is preferred.

| | run A g1 | g2 | g3 | run B g1 | g2 | g3 |
|---|---|---|---|---|---|---|
| scenes (merged) | 12 | 8 | 12 | 17 | 13 | 13 |
| `sourced` | 8 | 4 | 8 | 14 | 10 | 9 |
| ⛳ **`designed`** | **4** | **4** | **4** | **3** | **3** | **4** |
| ⛳ **`assess`** | **4** | **4** | **4** | **3** | **3** | **4** |
| `practice` | 0 | 0 | 0 | 1 | 0 | 1 |
| every LO served **and** assessed | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| outcome text verbatim | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| invented ids | NONE | NONE | NONE | NONE | NONE | NONE |
| `dropped_beats` | 1 | 1 | 1 | 1 | 1 | 1 |
| ⛔ **hard refusals** | **1** | **1** | **1** | **1** | **1** | **1** |

**The census against the baseline the order named:**

| | scenes | `sourced` | **`designed`** | **`assess`** |
|---|---|---|---|---|
| RC-Q9e baseline, 6 gens, v4+v5 | 83 | 83 | **0** | **0** |
| **12f run A**, 3 gens, v6/contract-5 | 32 | 20 | **12** | **12** |
| **12f run B**, 3 gens, v6/contract-5 | 43 | 33 | **10** | **10** |

⛳ **THE HOLE THIS PACKAGE LINEAGE HAS BEEN CHASING SINCE 12c IS CLOSED.** Every
outcome is served and assessed by the derived map **over the merged sequence**,
in six generations of six. `OUTCOME_UNASSESSED` did not fire once. Every
regression held: outcomes verbatim, zero invented ids, one honest drop per
generation.

⛔ **AND THE ACCEPTANCE IS STILL NOT MET, ON ONE CHECK, SIX TIMES OUT OF SIX.**

## 12f.7 ⛔ RC-Q9f — THE PLAN'S UNFORCED KIND, AND I DID NOT TUNE IT

**Every one of the six refusals is the same one:** `PLAN_ENTRY_UNREALIZED` on
**LO-2**. And the assessment plan is **identical in all six generations**:

    {"LO-1": "assess", "LO-2": "practice", "LO-3": "assess"}

LO-2 is *"explain why a placeholder zero is written"*. The model plans a
**supported** attempt for it — which is a defensible reading of an
understand-level outcome — and then never builds one. Contract-5 forces an
`assess` scene for every outcome. **It does not force a `practice` scene**, so
the one kind the grammar leaves to the model's own follow-through is the one kind
the model does not follow through on.

⛳ **THAT IS RC-Q9d, VERBATIM, ONE LAYER ALONG.** 12d measured the plan to be
*prior, honest, stable and NON-CAUSAL*: the model commits well and the scenes
ignore the commitment. 12f forced the `assess` half and the same non-causality
reappeared **in the unforced half, unchanged and just as stable**. Four packages
now show one law: **on this stack the model's plan predicts nothing; only the
grammar is causal.**

⛔ **AND I DID NOT CLOSE IT, DELIBERATELY.** Three routes were available and each
is refused for a reason:

  * **Loosen `PLAN_ENTRY_UNREALIZED` to match any assessing event.** ⛔ Refused
    outright. That is exactly the change 12d declined with the number on the
    record and 12e made a **standing rule**: *evidence kinds are never collapsed
    to green a number*. LO-2's learner would still never get a supported attempt.
  * **Add a sentence to the prompt telling the model that planning `practice`
    commits it to building one.** ⚠ Refused as tuning. The instruction is
    **already there and already correct** — v4 added *"a plan entry no scene
    realizes is refused, by outcome and by kind"* and v6 keeps it. Adding
    emphasis after seeing the number is iterating against the metric, and this
    lineage has a precedent for not doing that.
  * **Force a `practice` scene too, the way `assess` is now forced.** ⛔ **This is
    the real answer and it is not mine to take.** It is a second required
    per-outcome object, a contract-6, and a structural escalation of exactly the
    kind the order reserved to the operator.

⛔ **ROWED AS RC-Q9f. The escalation is the operator's to order.**

### ⚠ AND A SECOND FINDING, WHICH IS 12f's OWN ARTEFACT

⛳ **THE MODEL LEARNED TO INVENT FROM THE GRAMMAR, AND OVERSHOT.** In **all three**
run-A generations and **one** run-B generation it wrote an **extra `designed`
`assess` scene into `scenes[]` itself** — the first `designed` scenes ever
emitted into that array on the operator's script. The merge then places the
mandated one immediately after its near-identical twin:

    run A gen 1, scenes 10 and 11, adjacent:
      "Now it’s your turn. Multiply 43 by 27 using the standard column algorithm."
      "Now it's your turn. Multiply 43 by 27 using the standard column algorithm."

    run A gen 2, scenes 6 and 7, adjacent:
      "Now it's your turn to try. Multiply 43 by 27 using the standard column algorithm."
      "Now it's your turn to try. Multiply 43 by 27 using the standard column algorithm."

    run B gen 3, scenes 11 and 12, adjacent:
      "Check your work."
      "Check your work by verifying the column alignment, each partial product, and the placeholder zero."

**The lesson poses the same assessment twice, back to back.** No check catches it:
both scenes are legally declared and both genuinely assess. It is a quality
defect a reviewer would cut in one click, and it is **caused by this package** —
contract-5 taught the model the shape and did not tell it the shape is already
provided. **Rowed with RC-Q9f**, with the same refusal to fix it by prompt
emphasis after the fact.

⚠ **Not every adjacency is a duplicate.** Run B gen 1 pairs a `practice` sourced
from the script's own second problem (*"Let's try another one. Multiply 32 by
21."*) with the designed assess on fresh numbers — **that is the fading sequence
working exactly as Foundation §2 describes it**, and the merge put the
independent attempt at the end of it. The placement rule is doing its job.

## 12f.8 The check the grammar cannot make — every designed assessment, verbatim

The order's two degeneracy tests are **the script's worked answer restated as an
"unaided" attempt**, and **the same numbers posed**. The script teaches **23 × 14**
and works **32 × 21**. Every designed assessment across both runs:

**Run A**

> **LO-1** *"Now it's your turn. Multiply 43 by 27 using the standard column algorithm."*
> **LO-1** *"Now it's your turn to try. Multiply 43 by 27 using the standard column algorithm."*
> **LO-1** *"Now it's your turn to try. Multiply 43 by 25 using the standard column algorithm."*
> **LO-2** *"Why do we write a placeholder zero in the ones column when multiplying by the tens digit?"* (×2)
> **LO-2** *"Explain why a placeholder zero is written in the ones column before multiplying by the tens digit."*
> **LO-3** *"Check your work by verifying the column alignment, each partial product, and the placeholder zero."* (×3)

**Run B**

> **LO-1** *"Now it's your turn to try. Multiply 43 by 25 using the standard column algorithm."* (×3)
> **LO-2** *"Explain why a placeholder zero is written in the ones column before multiplying by the tens digit."* (×2)
> **LO-2** *"Why do we write a placeholder zero in the ones column when multiplying by the tens digit?"*
> **LO-3** *"Check your work by verifying the column alignment, each partial product, and the placeholder zero."* (×2)
> **LO-3** *"Check your work."*

And the rationale attached to each, which is the evidence limb for an invented
scene: *"The script does not contain an unaided attempt at a two-digit
multiplication problem."*

⛳ **NEITHER DEGENERACY TEST FIRES.** **43 × 27** and **43 × 25** appear nowhere in
the script; the problem is posed cold, with no method reminder and no first step;
no worked answer is restated. **So the order's STOP condition is NOT triggered**
and the two-call escalation is not called for on those grounds.

⚠ **AND THE HONEST LIMITS OF THAT, STATED RATHER THAN GLOSSED.** Three of these
are thin as scenes. *"Check your work."* is four words and cannot pose anything.
The LO-3 assessments restate the outcome's own wording back at the learner
instead of giving them a specific worked attempt to check — a real weakness, and
one the schema cannot see, because a string that reads like an instruction is a
valid string. **Genuineness past this point is the operator's gate judgment, per
the 12c ruling**, and this is the material for it.

## 12f.9 The generalization check — B2 under contract-5, reported not scored

| | scenes | `sourced` | `designed` | `assess` | plan | plan realized | refusals |
|---|---|---|---|---|---|---|---|
| B2 run A | 19 | 16 | **3** | **3** | all `assess` | ✅ | 11 × `MOTION_UNKNOWN_TEMPLATE` |
| B2 run B | 14 | 11 | **3** | **3** | all `assess` | ✅ | 6 × `MOTION_UNKNOWN_TEMPLATE` |

⛳ **THE MECHANISM GENERALIZES.** A different topic, a different script, exactly
one designed assessment per outcome, every outcome assessed, fresh numbers
(*"Divide 432 by 10. Show your work."*, *"Divide 9432 by 100."*) against a script
that contains **no numbers at all**, **no duplicate**, and **zero
`PLAN_ENTRY_UNREALIZED`** — because on this script the model planned `assess` for
all three outcomes, which is precisely the difference from the operator's script
and confirms 12f.7's diagnosis by contrast.

⚠ **The refusals are a RENDERER gap, not a design one, and they have nothing to
do with 12f.** The model chose `motion_graphics` for division and
`shared.motion.templates` serves four templates, all column-arithmetic:
`place_value_split`, `column_addition_carry`, `column_multiplication_step`,
`highlight_and_hold`. **There is no division template**, so every motion scene in
a division lesson is refused `MOTION_UNKNOWN_TEMPLATE`. That is a real coverage
limit worth knowing before anyone points this pipeline at a second topic, and it
is not a defect this package introduced or should fix.

## 12f.10 Tests — zero new failures, both baselines re-measured in this environment

⚠ **THE PUBLISHED BASELINES WERE NOT REPRODUCIBLE HERE, so I measured them by
stash-and-rerun rather than inheriting them** — the §0 rule about measuring the
ref, applied to test counts.

| tree | baseline (stashed, same environment) | with 12f | verdict |
|---|---|---|---|
| `ivgs-api` | **1652 passed, 0 failed** | **1682 passed, 0 failed** | ✅ **+30**, still zero |
| `ivgs-workers` | **18 failed, 983 passed, 52 skipped, 15 errors** | **identical** | ✅ **zero new** |

⚠ The worker tree reported `987 passed, 48 skipped` on one run out of four and
`983/52` on the other three, baseline and 12f alike. **Failures (18) and errors
(15) were identical in every run.** Four tests flip between passed and skipped on
something environmental; I did not chase it and it is not 12f's.

⚠ Running these at all needed **both** `DATABASE_URL` and `TEST_DATABASE_URL`
pointed at `ivgs_reconciliation_test`, and that database **migrated to 0052** —
`conftest` reads one variable and the app's own startup reads the other, so
setting only the documented one produces 1,562 errors that look like a broken
package and are a broken harness.

⚠ **TWO OF THE THIRTY TESTS ARE IN THE SECOND COMMIT, NOT THE TAGGED ONE.** The
database round-trip pair was written after the images were built, so the image
tagged `v5.37.5-assessments-authored` carries 28 of them. Tests do not ship
behaviour and nothing deployed differs, but the tagged commit and the tree are
not identical on this file and saying so is cheaper than a reader discovering it.

**Thirty tests added** in `test_wpivgs12f_designed_assessments.py`, including a
**contract-5 round trip through the database** (parse → service → scene rows →
gate, asserting the merged indices `apply_scene_design` matches rows on, the
rationale landing on designed rows and NULL on sourced ones) and a regenerate
test proving a stale rationale is cleared — the RC-Q10 shape, for the field 12f
adds.

**Three existing tests re-aimed, none weakened:**

  * `test_the_contract_version_records_the_shape_change` pinned `-4`. Re-aimed to
    assert the current version **and that it is past -3**, so a shape change with
    no bump still fails loudly without every package editing the same line.
  * Two 12d tests asserted the model's own `scene_index` survived the parse. **The
    claim under test is unchanged** — the evidence map is derived and the model's
    own is ignored — and the index is now the merged position, which 12f.3
    explains is the more correct of the two.
  * ⛳ **One test was NOT re-aimed and the code was fixed instead**, which is the
    right way round: see 12f.3 on `OPTIONAL_SCENE_FIELDS`.

## 12f.11 ⛔ EVIDENCE I DESTROYED, AND WHAT I DID ABOUT IT

I wrote a script to replay the banked emissions into a transcript. It **imported**
the census harness, whose module-level code runs the generate-and-write loop —
with `N = 0`, so `json.dump([], …)` **truncated all eight banked emission files to
`[]`**. Four measurements' raw contracts were gone in one command.

**What was lost:** the emissions behind run A of the acceptance, and behind run A
of both TASK 0 scripts. Their **numbers survive in this report** and in the
console output they were read from, but ⛔ **a reader cannot check them against
the bytes**, which §0 rule 5.1 says is not sufficient.

**What I did:**

  1. **Fixed the harness so it cannot recur** — everything below an
     `if __name__ == "__main__"` guard, and the tree under measurement made an
     env var. Proved with a sentinel file that importing it now writes nothing.
  2. **Re-ran all four measurements and banked them.** The contract-4 runs were
     reproduced from a **git worktree at `d2fc50c`**, so B1 and B2 were measured
     against the real contract-4 schema and not a reconstruction. The worktree is
     removed; `git worktree list` shows only `/opt/ivgs`.
  3. **Reported both sets.** Run B replicates run A on every load-bearing finding
     — 0 designed on B1, designed scenes on B2, and **1, 1, 1 refusals with the
     identical plan and the identical cause** — so the conclusions rest on n=6 for
     the acceptance and n=2 for each TASK 0 script, not on the lost run.

⚠ **Run A's contracts are declared LOST BY NAME** and are not in the bank. Run B's
are, in full.

## 12f.12 The tree, and the operator's push block

**Held: 2 commits. Nothing pushed by me. Working tree clean. No frozen stage body
was touched. No freeze exception was requested.**

⚠ **Two, not one, and for 12e's reason:** the code is committed and tagged BEFORE
the images are built, so `IVGS_BUILD_SHA` names a commit that exists; the
acceptance can only be written afterwards.

    ac77733  feat(wp-ivgs-12f): the excerpter is forced to design   [tag v5.37.5-assessments-authored]
    <2nd>    docs(wp-ivgs-12f): the acceptance, and RC-Q9f — the plan's unforced kind

⚠ **`ivgs-infra/.env` is MODIFIED AND IS NOT MINE TO COMMIT** on node-01, and the
same file is modified on nodes 02, 03 and 04: the deploy moved `IVGS_API_TAG` and
`IVGS_WORKERS_TAG` to `v5.37.5-assessments-authored`. It is gitignored and
`dev/CLAUDE.md` §3 names it never-touch for its token; the tag lines are what a
deploy changes and they are left as deployed. A copy of node-01's pre-deploy file
is in the session scratchpad and **does not survive the session** — the rollback
is the two tag values above, written out here because that is the only place they
will keep.

```
# node-01, as the operator
cd /opt/ivgs
EXPECTED=2
ACTUAL=$(git rev-list --count origin/main..HEAD)
if [ "$ACTUAL" -ne "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git push origin main && git push origin v5.37.5-assessments-authored
fi
```

## 12f.13 What I did not verify — 12f's additions to §Z

1. ⛔ **The rendered gate panel, still, and now it matters more than before.**
   No browser was driven. The gate has gained a field this package added
   (`designed_rationale` in `_arc_row`) and a scene kind that has never appeared
   in it, and **nothing has confirmed the frontend renders either** — the
   frontend is still `v5.37.0-design-core` and was not rebuilt, correctly, since
   no frontend code changed. What a reviewer actually sees is unmeasured.
2. ⛔ **NOT ONE GENERATION WENT THROUGH THE REAL PIPELINE.** Every number above
   comes from the harness calling node-02 directly with the seed-rendered prompts
   and the contract schema — the same modules production imports, but **not the
   Celery task, not `task_prerun`, not the document transform, not the capture
   observer, and not the scene rows.** The transform and the merge are tested and
   were read back out of the running containers; they have **never run inside a
   real stage-2 job.** ⚠ This is the largest gap in the package: the seam that
   carries designed assessments into `storyboard_scenes` is proven by test and by
   inspection, and not by a job.
3. ⛔ **Whether a designed assessment RENDERS.** Stage 3+ has never been handed
   one. The motion assessments carry `highlight_and_hold`-shaped intent but the
   renderer has not drawn one, and B2 showed the template set does not cover
   division at all.
4. ⚠ **n is small and the script is one script.** Six generations on the
   operator's script and two each on B1/B2. The `assess`-vs-`practice` label
   flipped between B1's two runs, which is a direct measure of how unstable a
   single generation is.
5. ⚠ **Prompt length, still untested and now worse.** 7,788 → 15,941 characters
   across v1–v6. The arc improved this time, so the question is live rather than
   answered: nothing measures what the length costs.
6. ⚠ **`ivgs-scheduler`, `ivgs-backup-worker`, `ivgs-motion-renderer` and
   `tests_system` were not run.** 12f touches none of them, and I did not
   re-measure their baselines to prove it.
7. ⚠ **The `rationale` on the `scenes` oneOf's `designed` branch is still
   unbounded**, where the new one has a `maxLength`. Named as a residue in
   `contract.py` rather than widened into this package's blast radius.
