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
