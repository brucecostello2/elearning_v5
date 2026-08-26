# WP-64-MEDIA — report

**A scene's description follows its medium, and the models stop being
blindfolded.**

Measured on node-01 (192.168.1.90) on 2026-08-26 against the running stack.
Every count in this report is the tail line of a run whose output is quoted.
Nothing here was inferred from reading code except where it says so.

---

## S0. Verdicts

| Task | Verdict |
|---|---|
| **1** — the full per-medium prompt path, measured | **DONE.** Table in S1. Three findings in the brief were confirmed, and **one was found to be wrong in a way that matters** — see S1.4. |
| **2** — storyboard v4 becomes media-aware | **DONE, COMMITTED, NOT PUBLISHED.** RULE 2 (deliberate choice) and RULE 7 (write for the medium) extend v4 in place. Checker extended. Publisher gates extended and pre-flighted read-only (S2.5). **The publish is the operator's press — D-1.** |
| **3** — "adapt description to this medium" | **DONE AND DEPLOYED.** Route live on `v5.23.0-media` (S3.6). It proposes and never writes the scene; guarded 409; audited. Its prompt row needs one operator publish. |
| **4** — the frozen runtime writer | **DONE, LEDGERED P2.65.** (a) measured end to end in the container, twice. (b) template amended to PRESERVE, and says in its own text that it cannot branch. (c) P2.65 written with file:line. **And the brief's premise about where this file lives was wrong — S4.4.** |
| **5** — acceptance on the operator's clean project | **BLOCKED ON THE OPERATOR, BY DESIGN.** Everything is deployed. Four operator blocks in S6, in order. I press nothing (WP-63 D-2 stands). |
| **6** *(addendum)* — learning outcomes | **DONE AND DEPLOYED.** Migration 0037, GUI at creation and on Overview, RULE 0 in v4, checker fixture. (c) took the **fallback branch**, stated plainly in S5.3 and ledgered **P2.66**. |

**Zero new failures.** 2242 passed against a baseline of 2133; failed / skipped
/ errors unchanged at 50 / 63 / 45. **+109 tests.** No assertion was weakened,
no skip marker added, no coverage deleted. Two existing tests moved and both
are strictly stronger — recorded in the baseline, not here, so the scoring
document carries its own history.

---

## S1. Task 1 — what text actually reaches each engine, measured

### 1.1 The table

Read on 2026-08-26 in the tree at `b55bd59`, and confirmed live inside
`ivgs-celery-default` (S4.1). "Authored by" is where the text is written;
"transformed by" is what rewrites it before the engine; "engine receives" is
the literal payload.

| | **image** | **video_clip** | **animation** |
|---|---|---|---|
| **Authored by** | Stage 2, `storyboard_generation` prompt row (v3 live) → `storyboard_scenes.visual_description` | the same, unchanged | the same, unchanged |
| **Dispatched to** | `tasks.stage3_images.generate_scene_images_task`, queue `gpu_image` | `tasks.video_generation_task.generate_video_clips`, queue `gpu_video` | `tasks.animation_generation_task.generate_scene_animations`, queue `gpu_animation` |
| | `pipeline_orchestrator_v2.py:606-617` groups scenes by `media_type`; `:655-658` is the dispatch plan | ″ | ″ |
| **Runtime writer** | `stage3_images._generate_image_prompt` (`:187`) — system = `stage3_system.j2` rendered with FOUR PROJECT VALUES (`:203-208`); user prompt hardcoded **"Generate an image prompt for this educational video scene:"** (`:210-216`) | `video_generation_task._generate_video_prompt` (`:235`) — its own inline `VIDEO_PROMPT_TEMPLATE` (`:151-161`), system role *"You are a professional cinematographer…"*, asks for *"camera movement, lighting, subject action, and atmosphere"* | **NONE.** There is no prompt writer on this path. |
| **Engine client receives** | FLUX: `positive_prompt` = the writer's first line, `negative_prompt` = its `NEGATIVE:` line or the hardcoded default (`stage3_images.py:229-241`), via `FluxGenerationParams` (`:412-416`) | CogVideoX / Wan2.1: one `prompt` string, the writer's whole output (`video_generation_task.py:333-336`, `:373`, `:381`) | Wan2.2-Animate: `WanAnimateParams.prompt` **set directly to `scene.visual_description`** (`animation_generation_task.py:387-390`), plus a reference image and a driving video |
| **Where the scene's own words end up** | inside the writer's user prompt at `stage3_images.py:213`, verbatim | inside the cinematographer prompt at `video_generation_task.py:245`, verbatim | **IS** the render prompt, verbatim |

### 1.2 The keyframe branch, which the table above does not cover

`stage3_images._process_single_scene` **also** has a `video_clip` branch
(`:372-411`): it asks CogVideoX for a KEYFRAME, falling back to FLUX. It is
reachable only if a `video_clip` scene is handed to the image task, which the
orchestrator's dispatch plan does not do. It is live code on a path the
orchestrator does not take, and it too runs `_generate_image_prompt` first.

### 1.3 What the brief said, and what is true

| Brief | Verdict |
|---|---|
| (a) `update_scene` persists a `media_type` change with no rewrite of the description | **CONFIRMED.** `app/api/v1/storyboard.py:143` → `StoryboardService.update_scene` (`storyboard_service.py:181-182`) is a `setattr` loop. |
| (b) generation runs ALL THREE media types through `_generate_image_prompt`, whose user prompt is hardcoded "Generate an image prompt…" | **HALF CONFIRMED, and the correction matters.** True for `image`, and for the `video_clip` keyframe branch of §1.2. **Not true for the two branches that actually run**: video has its own cinematographer writer (WP-46-era), and animation has NO writer at all. |
| (c) `stage3_system.j2` is rendered with project fields only; `media_type` is not passed, so it cannot branch | **CONFIRMED**, `stage3_images.py:203-208`. Measured as identity in S4.1. |
| the operator's conclusion — switching a scene dispatches the right engine into the wrong prompt | **CONFIRMED, and it is worse than (b) implies.** See §1.4. |

### 1.4 THE CORRECTION, AND WHY IT STRENGTHENS THE FINDING

The brief's diagnosis is that the wrong *writer* runs. The measurement says
something sharper: **for two of the three media the writer is fine, and there
is nothing for it to work with.**

* `video_generation_task`'s prompt asks the model for *"camera movement,
  lighting, subject action, and atmosphere"* — exactly the right question. It
  asks it **about a description authored for a still**, and a cinematographer
  handed a photograph caption invents motion or omits it.
* The animation branch has **no writer to be wrong**. Wan2.2-Animate receives
  `scene.visual_description` byte for byte. Every word of motion intent it will
  ever see is in that string.

So the repair is not "give each medium a writer" — two of three already have
the right one, or need none. **The repair is to put the medium into the
description**, which is Tasks 2 and 3, and to stop the one remaining writer
flattening it, which is Task 4. That is why this package spends its effort on
authorship rather than on the frozen writer, and it is a conclusion the
measurement produced rather than one the brief assumed.

---

## S2. Task 2 — v4 becomes media-aware before its first publish

### 2.1 Why this is an extension and not a v5

v4 is **committed and has never been published**. WP-63 D-2 held the publisher
behind an acceptance sequence that named project `14f71729`, which the operator
has since deleted. The prompts table still reads:

```
 prompt_type           | version | is_active
-----------------------+---------+-----------
 storyboard_generation |       1 | f
 storyboard_generation |       2 | f
 storyboard_generation |       3 | t
```

Three rows. There is no v4 to preserve, so v4 is extended in place. What the
operator publishes is **one version carrying WP-63 Task 9, WP-64 Task 2 and
WP-64 Task 6** — and the change note says all three.

### 2.2 (a) RULE 2 — the choice becomes a decision

The measured defect: **nine scenes, nine images** on project `14f71729`,
because nothing in v3 asked for the choice to be made. v3's RULE 2 was a
glossary of the three values; v4's is three questions asked of every scene, in
order, with the answer deciding:

1. **Is the motion inherent to the step?** — something only legible while it
   moves, so a frozen frame loses the point → `video_clip`.
2. **Is the step a transformation or build-up carried by a person in the
   frame?** → `animation`.
3. Otherwise `image`.

And, stated: *"Most scenes in most lessons are honestly images, and choosing
'image' after asking the three questions is a correct answer. Choosing it for
all of them without asking is not."*

### 2.3 THE COLLISION IN THE BRIEF'S ANIMATION CRITERION — this is D-2

The brief asks that animation be earned by *"transformation/build-up"*.
**Taken alone, that criterion produces scenes this pipeline REFUSES.**
Wan2.2-Animate is pose reenactment: it transfers a driving video's motion onto
the *subject* of the scene's still, and `animation_generation_task.py:481`
raises by name —

> `reference image contains no person to animate: … Wan2.2-Animate is pose
> reenactment: with no subject in the reference it does not decline, it
> hallucinates one.`

A "transformation/build-up" of an equation or a diagram has no person in it. So
v4 keeps the brief's criterion **and intersects it with the person condition**:
a transformation or build-up *carried by a person who is in the frame*. Motion
of equations, charts or "steps appearing on screen" stays `image` and belongs
to the composition overlay, because there is no motion-graphics pathway in this
pipeline.

If the operator wants a motion-graphics branch, that is a new engine and a new
AD-01 row, not a prompt change. **D-2 asks them to confirm or overrule.**

### 2.4 (b) RULE 7 — one decision, not two

`media_type` and `visual_description` become one decision, with the reason
stated in the prompt itself: *"the description you write here is the ONLY
motion instruction that reaches the engine."*

* `image` — one frozen instant. No camera moves, no "then", no elapsed time.
* `video_clip` — **what moves** (as a verb), **what the camera does**
  ("locked-off" is a legitimate answer, but say it), **what happens in what
  order**.
* `animation` — the build or the transform, its order, and the visible human
  whose pose drives it.

**RULE 1 is untouched and still wins**, and v4 says so where the two meet:
*"Motion, camera and time are all describable without a single digit, letter or
caption."*

### 2.5 (c) The checker, extended, and gated both ways

`test_wp63_storyboard_prompt.check_visuals` now takes each scene's own
`media_type` (absent = image, which is what the API default says and what all
nine measured scenes were).

| Fixture | Verdict |
|---|---|
| a still-authored description labelled `video_clip` | **CAUGHT** — *"names nothing that moves … the motion instruction reaching CogVideoX is this string and nothing else"* |
| the same string labelled `animation` | **CAUGHT twice** — no build, and no person |
| **the identical strings labelled `image`** | **CLEAN.** This is what makes the finding a MISMATCH rather than a quality complaint. |
| a clip that moves but never says when | **CAUGHT** — *"says neither what the camera does nor in what order"* |
| an image asked to pan | **CAUGHT** — *"only exists over a duration"* |
| `media_type: "VIDEO"` | **CAUGHT** — named, not absorbed into the image branch |
| the medium-apt storyboard (image / video_clip / animation / image) | **CLEAN, and carries no digit** |

One vocabulary entry was **dropped during authoring and the reason is written
into the source**: a first draft matched `seconds?`, which fired on *"a
**second** ruled line"* in four of the compliant fixtures — the ordinal, not the
unit. A checker that fires on the wrong word teaches authors to write around
it. Elapsed time in an image description is still caught by RULE 1's digit rule.

**34 tests, all passing** (13 before).

### 2.6 The publisher, gated and pre-flighted

`wp63_publish_storyboard_prompt.py` keeps its name — it is the same one
publish — and now refuses on three contracts instead of two. Run read-only
inside `ivgs-fastapi` on the deployed image, **writing nothing**:

```
--- storyboard_generation ---
  template      : /app/seed/default_prompts/storyboard_generation.j2
  file sha256   : 7d4f5376eb435b3509ae67e2288efefca21c9c9f954b0515bff745d326ebe3d9
  stored sha256 : c27ff0b0c8f979030fbf85d58716c726b6b5a63388dd1d48a1ab2b1b18f5ef2f
  file bytes    : 12916   stored chars: 12915
  RULE 5/6 binding      : OK  (3 phrases)
  RULE 2/7 medium       : OK  (4 phrases)
  RULE 0 outcomes       : OK  (4 phrases)
  RULE 1 no-text        : OK  (2 phrases)
```

Two digests, each named for what it covers (WP-62 Task 8(e)'s correction, which
this script inherits rather than repeats). **The live publish is S6 block 1 and
is the operator's press.**

---

## S3. Task 3 — the editor gets "adapt description for this medium"

### 3.1 What it is

`POST /api/v1/projects/{id}/scenes/{scene_id}/adapt-description`
`{"target_media_type": "image" | "video_clip" | "animation"}`

**Live on the deployed build.** From the running API's own OpenAPI:

```
ROUTE: /api/v1/projects/{project_id}/scenes/{scene_id}/adapt-description ['post']
SceneAdaptDescriptionResponse keys: ['adapted_description', 'binding',
  'current_description', 'current_media_type', 'generated_at', 'model',
  'prompt_id', 'prompt_version', 'scene_id', 'scene_index', 'scene_written',
  'target_media_type']
```

### 3.2 (a) The model does not move, and cannot

The rewrite runs on the **AD-01 binding for `storyboard_generation`**, resolved
through `shared.providers.factory.get_binding` — the same call the worker makes.
Measured live: that row is `llama-3.3-70b-storyboard`, engine `vllm`,
`default_params.engine_model = "llama-3.3-70b"`, and node-02's server answers
`/v1/models` with exactly `['llama-3.3-70b']`. The model here **cannot drift
from the model that authored the description**, because it is read from the
same row rather than named in a constant somebody has to remember to update.

The **URL** comes from the API container's own environment
(`llm_playground.resolve_engine_endpoint`), not from `binding.endpoint`, for the
reason `llm_playground` already records: `shared.providers.binding` ships
hostname defaults (`http://node-02:8000`) the API container's network cannot
resolve. Same workaround `translation_service` uses, and it is stated in the
module docstring rather than left to be discovered.

### 3.3 (b) It proposes. It never writes.

This is the property most of the module's tests are about.

* The endpoint's only durable write is the audit row.
  `test_the_scene_row_is_byte_for_byte_unchanged` drives a real adaptation and
  then re-reads the scene: description and `media_type` unchanged.
* `scene_written: false` is **in the response body**, so the contract is
  readable from the payload rather than from documentation.
* In the modal the proposal lives in local state and reaches the textarea only
  when the operator presses **"Use this text"** — at which point it is an
  ordinary unsaved edit they can still change or abandon. **Discard** throws it
  away. A test extracts the adapt handler's body and asserts
  `setVisualDescription` does not appear in it.
* The hook deliberately performs **no SWR mutation**: nothing is written, so
  there is nothing to invalidate, and wrapping it in `mutate` would refetch the
  scene list to show a change that has not happened.

### 3.4 (c) Guarded like every dispatch-capable surface

409 `PIPELINE_ALREADY_RUNNING`, through the same `active_job` definition WP-61
Task 5 and WP-62 Task 6 established — one definition of "a run is in flight"
across every surface that can spend capacity. It dispatches no stage and is
guarded anyway, for two reasons written into the code: it consumes the same LLM
a running Stage 1 or Stage 2 is using, and the scene it reads may be one that
run is about to overwrite. **The guard runs before the model call**, so a
refusal spends nothing — asserted (`test_the_refusal_spends_no_model_time`).

### 3.5 (d) Audited

One `audit_log` row per adaptation, `action_type = SCENE_DESCRIPTION_ADAPTED`,
carrying the before description, the after description, the target medium, the
prompt id and version, the model, the binding — and `scene_written: false` with
a note saying the scene row was not modified. **Recorded as a fact rather than
left to be inferred from the absence of a scene diff.**

### 3.6 Refusals, and none of them is a 500

| Condition | Answer |
|---|---|
| a run is in flight | **409** `PIPELINE_ALREADY_RUNNING`, model not called |
| `target_media_type` not one of the three | **422** from the schema, model not called |
| scene not in this project | **404** |
| scene has no description to adapt | **400**, model not called |
| no active `scene_media_adaptation` prompt | **502**, naming the publisher to run |
| the active prompt has lost the contract | **502**, model not called |
| the completion hit `max_tokens` | **502** — *"the rewrite would end mid-sentence; refusing to offer it"* (WP-58's Stage-2 lesson) |
| viewer role | **403**, model not called |

**24 tests, all passing.**

### 3.7 The prompt, and a correction the dropdown needed

`ivgs-api/seed/default_prompts/scene_media_adaptation.j2`, published through
`app/scripts/wp64_publish_adaptation_prompt.py` — the same versioning path, its
own refusals. `prompt_type.scene_media_adaptation` is migration **0038**;
`PromptType` now documents itself as *ten stage prompts and one editor prompt*.

**Also corrected, and it was load-bearing.** The Media Type dropdown described
animation as *"Motion graphics via Remotion/AnimateDiff (§7.1.8)"* — a pathway
this pipeline does not have. It is Wan2.2-Animate pose reenactment; it needs a
person in the scene's still and refuses a personless one by name. That single
line was the only thing an operator read before choosing the branch, and Task
5's acceptance gesture is exactly that choice. It now says what the branch is.

---

## S4. Task 4 — the frozen writer: measured, mitigated, ledgered

### 4.1 (a) The description IS the carrier — measured, in the container, twice

Run inside `ivgs-celery-default` against the real `_generate_image_prompt` with
the vLLM client replaced by a recorder. **Before the deploy** (`v5.22.0-validator`):

```
========================================================================
USER PROMPT AS SENT (stage3_images.py:210-216)
========================================================================
Generate an image prompt for this educational video scene:

Scene 2: Multiplying by the ones digit
Visual Description: The same desk and lamp, camera holding steady over the sheet;
the pencil begins at the ones column of the top row and traces downward, a small
carry mark forming above the tens column, then the first partial-product row fills
in beneath the ruled line, muted blue-grey illustration style
Narration Context: Now, let's start multiplying. We'll begin with the ones digit.
Multiply four times three, which equals twelve. Write down two and carry the one.
Duration: 8.0s
========================================================================
length             : 2288
contains rule 7    : False
hardcoded opener   : 'Generate an image prompt for this educational video scene:'
model / base_url   : llama-3.3-70b http://capture.invalid
```

**After the deploy** (`v5.23.0-media`), same harness: the user prompt is
identical, and `contains rule 7 : True`, `length : 3837`.

Every word of motion, camera and ordering language reaches the writer's
`user_prompt` **verbatim** at `stage3_images.py:213`. So the description is the
interim carrier of motion intent, and `test_every_word_of_it_arrives` asserts
exactly that: if it ever fails, Tasks 2 and 3 become decorative.

### 4.2 (b) The template amendment, and its honest limit

`stage3_system.j2` gains guideline 7: **PRESERVE MOTION, CAMERA AND TEMPORAL
LANGUAGE — DO NOT FLATTEN IT**, with the failure named rather than stated
abstractly (a description that begins and then continues *"must not become 'a
pencil resting on a sheet of paper'"*). WP-62 and WP-63 both learned that an
abstract rule does not hold; the concrete one is named.

**It does not pretend to branch**, and says so in its own text:

> WHY THIS RULE IS WORDED AS "PRESERVE" AND NOT "WRITE FOR THE MEDIUM": this
> template is rendered with the PROJECT's fields only and is never told which
> media type the scene is (`stage3_images.py:203-208`).

That property is asserted as **identity**, not as an absent substring: three
scenes, three different `media_type`s, one byte-identical system prompt. (A
substring check would now pass or fail on the amendment's own prose, which
mentions media types in explaining why it cannot see one.)

### 4.3 (c) Ledger P2.65 — see S9.

### 4.4 WHERE THIS FILE LIVES, AND WHY THE BRIEF'S QUESTION HAD A THIRD ANSWER

The brief asked whether `stage3_system.j2` ships in the workers or the api
image. **Workers** — but the more useful finding is the one the question
uncovered:

* it lives in `ivgs-workers/prompts/`, is baked at `/app/prompts` in
  `ivgs-workers`, and Stage 3 reads it **off disk**
  (`stage3_images._load_system_prompt`, `:177-184`);
* **it never reaches the `prompts` table at all.** The `image_generation` row in
  `prompts` (v1, active since 2026-05-23) is not what Stage 3 renders;
* and `scripts/check_seed_conformance.sh` compared **only** the api image's
  `/app/seed/default_prompts`. So this file was versioned data that **nothing
  compared to anything**. A stale baked copy would have shipped exactly as
  silently as a stale seed prompt, with one fewer place to notice — which is
  precisely the gap WP-62 Task 8(e) built that script to close.

So the script now checks both directories, both directions, resolving the
workers image by `docker inspect ivgs-celery-default` (never from a `*_TAG`
variable — dev/CLAUDE.md §6). A directory it cannot check is reported
**SKIPPED by name**, and it **refuses to print PASS when it compared nothing**.

Gated both ways, on the real script:

* **Before the rebuild** it named exactly the three files this package had
  changed — `MISSING IN IMAGE scene_media_adaptation.j2`,
  `DIVERGED storyboard_generation.j2`, `DIVERGED stage3_system.j2` — exit 1.
* **After the deploy**: `PASS: every baked template checked is byte-identical
  to the tracked one.` (full output in S8.)

The pre-existing negative test in `tests_system/test_wp62_surfaces.py` still
drives a one-byte divergence in a throwaway tree and still fails on it: the
workers pass reports SKIPPED there (that tree has no `ivgs-workers/prompts`)
and the api pass still returns 1.

---

## S5. Task 6 (addendum) — the project carries its learning outcomes

### 5.1 (a) The column

Migration **0037**: `projects.learning_outcomes`, nullable TEXT. Free text
deliberately — an outcome statement is a sentence, not an enum. **Nothing is
backfilled**; all seven live projects are NULL, and inventing outcomes for them
would put this package's guesses into a field the storyboard model then reasons
from.

Downgrade exercised on `ivgs_reconciliation_test`: `alembic downgrade 0037` →
`0036` (column gone, verified) → `upgrade head` (column back, verified). Applied
to live `ivgs`: **0036 → 0038**, `7 projects, 0 with outcomes` — no row
rewritten.

### 5.2 (b) The GUI, and the notice that is half the point

* **New Project**: a multi-line field, *"Learning outcomes — what the viewer
  should be able to do afterwards"*, optional, with a placeholder showing the
  shape and a note saying what it does — *"an outcome about following or
  performing something is one a still frame cannot serve … Left empty, the
  storyboard is planned from the transcript alone."*
* **Overview**: a panel showing it, editable in place, and — for a project with
  none — the words *"None stated. The storyboard will be planned from the
  transcript alone."* rather than an empty box that reads as a load failure.
* **The notice**, in bold, where it is edited: *"Editing this does not change
  scenes that already exist — it feeds the next storyboard generation."*
  `test_editing_them_does_not_touch_existing_scenes` asserts that property
  against a real scene row, **so the notice cannot become a lie by accident**.
* Clearing the box sends `null`, so the column is cleared rather than set to
  `""`.

### 5.3 (c) THE HAND-OFF — measured first, and the branch taken is the fallback

**The measurement.** The storyboard template's variable list is fixed inside
`stage2_storyboard._render_user_prompt` (`ivgs-workers/tasks/stage2_storyboard.py:127-137`),
which passes exactly nine names:

```
project_title, project_description, target_audience, max_duration_seconds,
total_runtime_seconds, combined_transcript, transcript_count,
target_scene_count, language_code
```

`learning_outcomes` is not among them, and that function is inside one of the
eight stage task bodies **AD-05 §8 freezes**. So the first branch — "pass it
through as its own template variable" — **is not available**, and the freeze is
not bent to make it available.

**The branch taken, and it is named as a fallback in the code itself.**
`project_description` IS one of the nine (`:130`), and
`pipeline_orchestrator_v2.py` is the orchestrator, **not** a stage body. So:

1. the API carries `learning_outcomes` to the dispatch **as its own key**
   (`project_service.trigger_pipeline`, and `regeneration.project_facts` so the
   storyboard gate's `regenerate` re-run sees what the first run saw);
2. the orchestrator folds it into `project_description` **for the
   `STORYBOARD_GENERATION` branch only**, between two explicit delimiter lines;
3. every other stage receives `project_description` exactly as the project
   wrote it — so `stage3_system.j2` does not silently gain a block of pedagogy
   it has no use for. Asserted: exactly one call site, inside the storyboard
   branch.

**The delimiter is the whole mechanism, and it is the one way this fails
silently.** The orchestrator writes the block; RULE 0 tells the model to look
for it. If the two drift, the model is handed a block it was never told to
read — no error, no log line, outcomes ignored, everything green. Tests on
**both** sides assert the two copies are byte-identical, and a third asserts the
frozen render call still passes exactly nine names.

The real fix is **ledgered P2.66**.

### 5.4 (d) RULE 0, and silent degradation

RULE 0 sits inside `{% if project_description %}`. Where outcomes are present it
conditions **RULE 2's media_type criteria** (an outcome phrased as *following*,
*performing*, *carrying out* or *watching something happen* is one a still
cannot serve; one phrased as *recognising*, *naming*, *recalling* or *comparing*
is served by a still, *"and reaching for motion there spends GPU time on
nothing"*) and **RULES 5/6/7's visual authoring**.

Where they are absent: the whole block is not rendered — **no heading, no
placeholder, nothing to reason about** — and where a description exists without
the block, the prose says *"DO NOT invent outcomes, mention their absence, or
write anything about this rule into a scene."* Both halves are asserted by
rendering the real template through Jinja.

### 5.5 (e) The checker fixture

`outcome_findings(learning_outcomes, scenes)`. It does **not** try to judge
coverage — that needs a reader. It checks the one thing decidable from the text:
an outcome naming an action the viewer must FOLLOW or PERFORM cannot be served
by a plan in which every scene is a still. That is the measured shape (nine
scenes, nine images).

| Fixture | Verdict |
|---|---|
| *"can follow the carrying step as it happens"* + an all-still plan | **CAUGHT** |
| the same outcome + the deliberate mix | clean |
| the same outcome + one `video_clip` among four | clean — one non-image scene is the bar |
| *"can name the place value … and recall the order"* + an all-still plan | **clean, deliberately.** Recognition is served by a still. |
| no outcomes at all | **clean.** Task 6(d): absence is not a defect. |

### 5.6 (f) Task 5's acceptance absorbs this — see S6.

---

## S6. Task 5 — acceptance. Four operator blocks, in order.

**I press nothing.** WP-63 D-2 stands and Task 5 restates it. Everything below
is deployed and gated; what remains is the operator's sequence. Each block is
node-labelled, self-gating, plain ASCII, and prints what it did.

### Block 1 — node-01: publish storyboard v4

```bash
# node-01 (192.168.1.90). Publishes storyboard_generation v4 (WP-63 Task 9 +
# WP-64 Tasks 2 and 6). Refuses on a template that has lost RULE 0, 1, 2, 5, 6
# or 7. Rollback is one UPDATE of is_active; nothing is deleted.
sudo docker exec -i ivgs-fastapi \
  python -m app.scripts.wp63_publish_storyboard_prompt \
  | tr -cd '\11\12\15\40-\176'
```

### Block 2 — node-01: publish the adaptation prompt

```bash
# node-01 (192.168.1.90). First version of scene_media_adaptation. Needs
# migration 0038, which is already applied (alembic current -> 0038). Without
# the prompt row the Adapt button answers 502 naming this script, which is the
# correct refusal and not a defect.
sudo docker exec -i ivgs-fastapi \
  python -m app.scripts.wp64_publish_adaptation_prompt \
  | tr -cd '\11\12\15\40-\176'
```

### Block 3 — nodes 02 / 03 / 04: the workers rebuild

**A workers rebuild IS required**: `stage3_system.j2` and
`pipeline_orchestrator_v2.py` both changed, and both ship in `ivgs-workers`.
node-01's workers are already on `v5.23.0-media`.

```bash
# node-02 (192.168.1.91) and node-04 (192.168.1.93) ONLY. Service is
# celery-worker on both. Run one node at a time.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.23.0-media.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node0X.yml \
      up -d --pull never --no-deps celery-worker
    sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep celery
  fi
)
```

```bash
# node-03 (192.168.1.92) ONLY. THE SERVICE IS cogvideox-worker, NOT
# celery-worker. node-03 also DECLARES a celery-worker under
# profiles: ["standby"] which is not running; naming it starts a second worker
# competing for the same queues and leaves the real one on the old image
# (WP-44 S6.3 recorded exactly that).
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.23.0-media.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node03.yml \
      up -d --pull never --no-deps cogvideox-worker
    sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -i worker
  fi
)
```

Replace `node0X` with the real filename on each box; derive it from the
container's own labels rather than guessing:

```bash
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
```

### Block 4 — the acceptance sequence, and its two preconditions

**PRECONDITION A — the animation gesture needs a person and a clip.** Task 5
asks the operator to switch one image scene to animation and have the asset
arrive. Two things must be true or the worker refuses **by name**, correctly:

1. the scene's own image asset must **contain a person** —
   `animation_generation_task.py:481`, checked before any GPU time;
2. the project must carry a **`reference_clip`** asset — `_resolve_inputs`
   (`:344-350`). Uploading a talking-head clip at project creation creates one;
   both existing projects that have one got it that way.

So: **choose a scene whose visual has a person in it**, and upload the
talking-head clip on the New Project form. If neither is possible for the
chosen lesson, the honest acceptance is the `video_clip` gesture instead, and
that should be recorded as the substitution rather than forced.

**PRECONDITION B — the outcomes are authored at creation** (Task 6(f)), so the
scene table is judged against them.

The sequence, one press each:

1. **Create the project.** Prompt, languages, transcripts, talking-head clip,
   **and learning outcomes** — including at least one motion-implying outcome
   if the mix is to be judged on it.
2. **Trigger.** Storyboard generates under published v4.
3. **Read the scene table BEFORE any edit** and report it verbatim —
   `scene_index`, `media_type`, `visual_description`. Read-only:
   ```bash
   sudo docker exec -i ivgs-postgres psql -U ivgs -d ivgs -x -c \
     "SELECT scene_index, media_type, visual_description
        FROM storyboard_scenes WHERE project_id = '<NEW_PROJECT_ID>'
       ORDER BY scene_index;" | tr -cd '\11\12\15\40-\176'
   ```
4. **Storyboard tab → Approve.**
5. Open one image scene whose visual has a person → set Media Type to
   **Animation** → press **Adapt description** → read it → **Use this text** →
   **Save Changes**.
6. **Regenerate** that scene. The dispatch must be `animation_generation`
   (WP-45 broker standard; WP-63 Task 7's path).
7. The chain drains to the **draft gate**. The draft decision is the
   operator's.

I will gather the evidence those presses produce, read-only, on request.

---

## S7. Decisions needed

### D-1 — the two prompt publishes are held for the operator's press

Task 2 says *"the operator block for publishing is yours to author, the
operator runs it"* and Task 5 says *"You press nothing"*. Both publishes are
therefore **authored, gated, pre-flighted read-only and not run** (S2.6). The
package's RULES separately sanction the publishes as permitted live-data
changes, so if the operator would rather I ran Blocks 1 and 2 and reported the
real output, **say so and I will**. Until then the active storyboard prompt is
still v3 and there is no `scene_media_adaptation` row — verified after the
deploy.

Nothing else in this package is waiting on that: the deploy is complete and the
Adapt button's refusal without a prompt row is a named 502, not a failure.

### D-2 — the animation criterion: "transformation/build-up" vs. the person the engine requires

**Ruling requested: confirm, or overrule.**

The addendum's Task 2(a) criterion for animation is *"transformation/build-up"*.
Implemented literally it produces scenes `animation_generation_task.py:481`
refuses by name, because Wan2.2-Animate is pose reenactment and a still with no
person in it makes the model invent a body. v4 therefore intersects the two:
**a transformation or build-up carried by a person who is in the frame**, with
motion of equations and diagrams staying `image` and belonging to the overlay.

If the operator wants motion graphics as a real branch, that is a new engine and
a new AD-01 row, not a prompt change — and it is worth saying that the frontend
dropdown has been *promising* exactly that ("Motion graphics via
Remotion/AnimateDiff") since before this package, which is now corrected.

### D-3 — Task 6(c) took the fallback branch. Confirm the carrier.

The outcomes reach Stage 2 inside `project_description`, between two delimiter
lines, because the frozen stage body fixes the template's variable list
(S5.3). That is the addendum's stated fallback and it is implemented exactly as
described — but it means **the storyboard prompt's `project_description` is no
longer only the project's description**, and any future reader of that variable
in the storyboard branch will see the block.

Two properties make it safe rather than clever, and both are asserted: the fold
happens at exactly one call site, in the storyboard branch only; and the
delimiter is identical in the writer and the reader. **If the operator would
rather wait for the real fix (P2.66, post-M3.3) and ship the column without the
hand-off, that is a two-line revert of the orchestrator change** — the schema,
the GUI and RULE 0 all stand on their own.

---

## S8. What was deployed, and what changed on the live fleet

**Deployed to node-01 only**, by the artifact path (WP-34 rule 1; GHCR is off
the deploy path):

| service | image | verified |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.23.0-media` | `docker ps` — healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.23.0-media` | healthy |
| `ivgs-celery-default` / `-composition` / `-beat` | `ivgs-workers:v5.23.0-media` | healthy |

Artifacts at `/mnt/ivgs-shared/image-artifacts/`, registered in `MANIFEST.txt`,
standard filenames from `scripts/lib/artifact_name.sh`:

```
brucecostello2_ivgs-api_v5.23.0-media.tar.zst
brucecostello2_ivgs-workers_v5.23.0-media.tar.zst
brucecostello2_ivgs-frontend_v5.23.0-media.tar.zst
```

**Nodes 02/03/04 need the workers rebuild** — S6 Block 3 — because
`stage3_system.j2` and `pipeline_orchestrator_v2.py` both ship in
`ivgs-workers`. That is an operator step; node-03's service is
`cogvideox-worker`.

`scripts/check_seed_conformance.sh` **PASSES against both deployed images** —
eleven api seed templates and seven workers stage templates, byte-identical:

```
--- api seed prompts ---     image : ivgs-api:v5.23.0-media
  ok  scene_media_adaptation.j2  3428182f4cf2235b2e37ae6b5b75c803a91dbe8b46aebedc59ff3d0fb425e086
  ok  storyboard_generation.j2   7d4f5376eb435b3509ae67e2288efefca21c9c9f954b0515bff745d326ebe3d9
  (+ 9 others, all ok)
--- workers stage prompts ---  image : ivgs-workers:v5.23.0-media
  ok  stage3_system.j2           26fce3729c5eeb9d3a0ef52fefabbe5208a8ac95cc80f5e8ed3ab30a0cc7bd25
  (+ 6 others, all ok)
PASS: every baked template checked is byte-identical to the tracked one.
```

`scripts/compliance_scanner.py`: **0 violations, 1 exemption, EXIT=0.**

**Live data changed, and nothing else:**

| change | scope |
|---|---|
| migration **0037** (one nullable TEXT column on `projects`) | schema; **no row rewritten** — 7 projects, 0 with outcomes |
| migration **0038** (one `prompt_type` enum label) | schema; 11 labels where there were 10 |
| `ivgs-infra/.env` image tags ×3 | node-01 deploy |

**No project row, scene row, asset row or prompt row was written.** Verified
after the deploy: 7 projects, 51 scenes, 73 assets, 23 render jobs,
**0** `SCENE_DESCRIPTION_ADAPTED` audit rows, storyboard prompt still **v3
active**, no `scene_media_adaptation` row. Every existing project is untouched:
`c12fa967`, `ba70a9fc`, and the five `e2e-photosynthesis-*`.

*(Recorded because the brief named it: project `52d52867` is not on this fleet.
The seven live projects are listed above and it is not among them; `14f71729`
is likewise gone, as the brief states.)*

No node other than node-01 was written to. node-05 was read once, read-only
(`GET /v1/models` → `['llama-3.3-70b']` on node-02; node-05 was not contacted at
all). node-06 was not contacted.

**One pre-existing log line, not this package's.**
`tasks.pipeline_orchestrator.process_dead_letter_queue` returns
`{'status': 'error', 'reason': 'dlq_fetch_failed'}` every 5 minutes on the
default worker. It is a periodic task in `pipeline_orchestrator.py`, which this
package did not touch (the change was to `pipeline_orchestrator_v2.py`). Noted
rather than chased.

---

## S9. Ledger

| id | entry |
|---|---|
| **P2.65** | **Per-medium prompt writers, or `media_type` passed into the Stage-3 render.** `stage3_images._generate_image_prompt` (`:187`) writes prompts for every media type it is given through one hardcoded user prompt — *"Generate an image prompt for this educational video scene:"* (`:210-216`) — and renders `stage3_system.j2` with four PROJECT values and no `media_type` (`:203-208`), so the template cannot branch and the system prompt is byte-identical for image, video_clip and animation (measured). WP-64 mitigated as far as data allows: the description now CARRIES the medium (Tasks 2, 3) and the template asks the writer to PRESERVE that language rather than flatten it (Task 4b). The real fix — either a per-medium writer or one extra render variable — requires editing a body AD-05 §8 freezes, and is post-M3.3. **Note for whoever takes it: the fix is smaller than it looks.** Two of the three branches do not need it. `video_generation_task._generate_video_prompt` (`:235`) already has a cinematographer prompt asking the right questions, and the animation branch has no writer at all — `WanAnimateParams.prompt` is `scene.visual_description` verbatim (`animation_generation_task.py:389`). Only the image writer, and the unreachable keyframe branch at `stage3_images.py:372-411`, run the wrong prompt. |
| **P2.66** | **`learning_outcomes` as its own Stage-2 template variable.** `stage2_storyboard._render_user_prompt` (`:127-137`) fixes the storyboard template's variable list at nine names inside a frozen stage body, so a tenth cannot be added pre-M3.3. WP-64 ships the outcomes inside `project_description` between `=== LEARNING OUTCOMES (authored by the course owner) ===` and `=== END LEARNING OUTCOMES ===`, composed in `pipeline_orchestrator_v2._description_with_outcomes` for the storyboard branch only. That is a carrier, not a design: it overloads a variable, and it depends on two files agreeing on a delimiter (gated by test on both sides). When the stage body opens, pass `learning_outcomes` through `_render_user_prompt` and delete the fold, the delimiter constants and RULE 0's block-detection preamble — RULE 0's *content* stays. |
| **P2.64** | *(WP-63, still open, and now larger.)* The visual-binding checker could gate a real run, and it has grown two more dimensions — the medium (Task 2c) and the outcomes (Task 6e). Stage 2's body is still frozen; the scene-create route is still the place it could go as a FLAG rather than a refusal. |

---

## S10. Push block — count-gated, for ALL held commits

**Five commits are held on `main` ahead of `origin/main`, and they are all this
package's.** WP-63's eleven have already been pushed — `origin/main` is at
`b55bd59`, WP-63's report — so the "eleven held" figure in that package's own
push block is spent. Verified before this block was written:

```
$ git log --oneline -1 origin/main
b55bd59 docs(wp-63): report - the check was measuring colour density, ...
$ git rev-list --count origin/main..HEAD
5
```

The gate counts all five and refuses on anything else.

```bash
# node-01 (192.168.1.90). Run from /opt/ivgs. Self-gating; pushes nothing
# unless the count and the two boundary commits are exactly right.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }

  AHEAD=$(git rev-list --count origin/main..HEAD)
  FIRST=$(git rev-list origin/main..HEAD | tail -1)
  HEADSHA=$(git rev-parse --short HEAD)

  echo "ahead of origin/main : $AHEAD  (expected 5)"
  echo "oldest held commit   : $(git log -1 --format=%h%x20%s "$FIRST" | tr -cd '\11\12\15\40-\176')"
  echo "newest held commit   : $(git log -1 --format=%h%x20%s HEAD | tr -cd '\11\12\15\40-\176')"
  echo
  git log --oneline origin/main..HEAD | tr -cd '\11\12\15\40-\176'
  echo

  if [ "$AHEAD" -ne 5 ]; then
    echo "REFUSED: expected 5 held commits, found $AHEAD."
    echo "Something has been added or removed since this block was written."
  elif [ "$(git rev-parse --short "$FIRST")" != "ee98547" ]; then
    echo "REFUSED: the oldest held commit is not ee98547 (storyboard v4 media)."
  elif [ "$(git rev-parse --short origin/main)" != "b55bd59" ]; then
    echo "REFUSED: origin/main has moved since this block was written."
    echo "         expected b55bd59, found $(git rev-parse --short origin/main)"
  elif [ -n "$(git status --porcelain)" ]; then
    echo "REFUSED: the working tree is not clean."
    git status --short | tr -cd '\11\12\15\40-\176'
  else
    echo "GATE PASSED. Pushing $AHEAD commits, ee98547..$HEADSHA"
    git push origin main
  fi
)
```

**The five, oldest first:**

```
ee98547  fix(wp-64): storyboard v4 chooses each scene's medium deliberately
         and writes the description for it
2f9811f  fix(wp-64): the editor can adapt a description to a medium, and it
         proposes rather than overwrites
41d56e8  fix(wp-64): the frozen prompt writer stops flattening motion, and the
         workers' templates get a conformance gate
b380273  fix(wp-64): the project carries its learning outcomes, and the
         storyboard model reads them
<this>   docs(wp-64): report + test baseline
```

The fifth carries this report and the baseline update. Its sha is deliberately
not written here - amending the commit changes it. It is printed by the
block's own `git log` line; read that rather than trusting a number written
before the amend that produced it.

---

## S11. The suite, in full

Run on node-01 with the TEST-BASELINE §1 environment block exported.

| Tree | passed | failed | skipped | errors | baseline |
|---|---|---|---|---|---|
| `ivgs-api` | **1123** | **0** | 0 | 0 | 1061 / 0 / 0 / 0 |
| `ivgs-workers` | **887** | 18 | 48 | 15 | 868 / 18 / 48 / 15 |
| `ivgs-scheduler` | **35** | 20 | 0 | 0 | 35 / 20 / 0 / 0 |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | 4 / 0 / 0 / 0 |
| `tests_system` | **193** | 12 | 15 | 30 | 165 / 12 / 15 / 30 |
| **Total** | **2242** | **50** | **63** | **45** | 2133 / 50 / 63 / 45 |

**+109 passed. Failed, skipped and errors identical in every tree.**

Frontend: `npm run test:logic` — **110 pass, 0 fail**. `npx tsc --noEmit` clean.

**One environment note, and it is an invocation difference rather than a
change.** Run WITHOUT `TEST_DATABASE_URL` exported, the `ivgs-workers` tree
reports **52** skips rather than 48: `test_wp60_orphan_guard.py` skips four
tests by name on that variable. All 52 skips in that tree are environment-gated
(Redis on port 16380, `ffmpeg`/`ffprobe`, the Temporal SDK's separate venv) and
**none is WP-64's**. Recorded in the baseline so the next package does not read
it as a regression.

The new modules:

* `ivgs-api/tests/test_wp64_adapt_description.py` (24) — the endpoint, and
  mostly what it must NOT do. The truncation and empty-completion cases drive
  the **real** `_call_model` against a stubbed transport, because a test that
  replaced that function would be asserting on its own stub.
* `ivgs-api/tests/test_wp64_learning_outcomes.py` (16) — the column, the
  dispatch, the delimiter, and RULE 0's silent degradation.
* `ivgs-workers/tests/test_wp64_media.py` (17) — the description reaching the
  writer intact, and the outcomes carrier.
* `tests_system/test_wp64_media.py` (28) — the real page sources, the real
  conformance script, the real templates.
* `ivgs-api/tests/test_wp63_storyboard_prompt.py` 13 → 34 — the checker,
  extended.
* `ivgs-workers/tests/test_wp_ivgs_0_seed_template_contract.py` 8 → 10 — the
  consumer map, plus two new tests making it stronger.
