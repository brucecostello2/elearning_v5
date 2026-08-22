# WP-IVGS-0 — Five defect fixes that gate everything else

**Report date:** 2026-08-22 · **Node:** node-01 (192.168.1.90) · **Branch:** `main`
**Start HEAD:** `4c21460` (clean tree, `HEAD == origin/main`) · **End HEAD:** `9262944`
**Status:** all five defects fixed, five commits, **HELD — nothing pushed, nothing deployed, no running service touched.**

Path and naming per CLAUDE.md §12 (`dev/workpackages/reports/`, amended 2026-08-22). No `dev/workorders/` directory was created.

---

## Contents

1. [STEP 0 — ground truth and baseline](#step-0)
2. [Two conflicts resolved before any code was written](#conflicts)
3. [Per-defect verdicts](#verdicts)
4. [What was NOT verified](#not-verified)
5. [Found along the way — reported, not fixed](#found)
6. [Decisions needed from the operator](#decisions)
7. [Commits](#commits)

---

<a name="step-0"></a>
## 1. STEP 0 — ground truth and baseline

### 1.1 Repo state

```
$ git status --porcelain      # (no output — clean)
$ git rev-parse HEAD          4c214604affc7ce81619743834200f60f7dbd54c
$ git fetch origin && git rev-parse origin/main
                              4c214604affc7ce81619743834200f60f7dbd54c
```

Repo root `/opt/ivgs`. Working rules read from `dev/CLAUDE.md` (there is no root `CLAUDE.md`).

### 1.2 How the tests were run

The API suite refuses to run against a non-test database (`ivgs-api/tests/conftest.py:95`, a TRUNCATE guard). The disposable database `ivgs_reconciliation_test` already existed on `ivgs-postgres`. Postgres is published on `192.168.1.90:5432`, **not** `127.0.0.1`, and Redis on `192.168.1.90:6379`; credentials were sourced from `ivgs-infra/.env` into environment variables without being printed. `ivgs-infra/.env.node01` was never read (CLAUDE.md §3).

```
TEST_DATABASE_URL=postgresql+asyncpg://<user>:<pw>@192.168.1.90:5432/ivgs_reconciliation_test
REDIS_URL=redis://192.168.1.90:6379/15
```

SeaweedFS is stubbed by an autouse fixture (`ivgs-api/tests/conftest.py:344`), so **no file was written to the running SeaweedFS.** All database writes went to `ivgs_reconciliation_test` and are truncated after every test. The live `ivgs` database was never touched.

### 1.3 BASELINE — before any change

| Gate | Command | Baseline result |
|---|---|---|
| Whole suite, repo config | `pytest` | **EXIT 4 — cannot run.** `ImportPathMismatchError: ('tests.conftest', '/opt/ivgs/ivgs-api/tests/conftest.py', '/opt/ivgs/tests/conftest.py')` |
| API | `pytest ivgs-api/tests` | **1 failed, 578 passed** (171s) |
| Workers, repo config | `pytest ivgs-workers/tests` | **0 collected, 15 collection errors** — `ModuleNotFoundError: No module named 'models'` |
| Workers, `PYTHONPATH=ivgs-workers` | as above | **14 failed, 91 passed, 22 errors, 7 collection errors** |
| Root `tests/` | `pytest tests` | **EXIT 4 — cannot run.** `ModuleNotFoundError: No module named 'aiosqlite'` at conftest import |
| Frontend types | `npx tsc --noEmit` | **exit 0, clean** |
| Frontend lint | `npx next lint` | **no baseline** — ESLint is unconfigured; the command drops into an interactive setup prompt |
| Compliance | `python scripts/compliance_scanner.py .` | **PASSED** — 1173 files, 0 violations |

The single baseline API failure is `ivgs-api/tests/test_health.py::test_health_check_no_auth_required`. It fails identically before and after every commit in this package.

### 1.4 AFTER — end of the package

| Gate | After | Delta |
|---|---|---|
| API | **1 failed, 620 passed** | +42 passed, **same single failure** |
| Workers (repo config, no PYTHONPATH needed) | **14 failed, 120 passed, 22 errors, 7 collection errors** | +29 passed, **failure and error sets byte-identical to baseline** |
| Root `tests/` | unchanged — still uncollectable | not in scope |
| Frontend `tsc --noEmit` | **exit 0** | unchanged |
| Compliance | **PASSED, 0 violations** | unchanged |

The failure set was diffed after every commit against the previous commit's; `diff` reported IDENTICAL each time. The one exception is documented under IVGS-0.2 below (one pre-existing test needed a new argument; it is called out rather than hidden).

Worker collection now works under the repo's own pytest invocation. `ivgs-workers/tests/conftest.py` puts `ivgs-workers` on `sys.path` — scoped to that directory, so the API run is unaffected. This was necessary for any acceptance test in this package to run at all, and is the only test-infrastructure change made.

---

<a name="conflicts"></a>
## 2. Two conflicts resolved before any code was written

The order says: *"If this order conflicts with what you find in the tree, STOP on that item and report the conflict — do not improvise."* Two arose. Neither blocks the work; both are recorded here rather than improvised past silently.

**(a) CLAUDE.md §3 forbids editing the eight stage task bodies.** The prohibition is scoped: "*during the orchestration migration* — the scope boundary in AD-05 §8 is binding," and AD-05 §8 itself is written for a migration session ("If a migration session finds itself editing stage internals, stop"). WP-IVGS-0 is a defect-fix package, not the migration, and it names `stage1_transcript.py`, `stage2_storyboard.py`, `stage3_images.py` and `stage5_voiceover.py` explicitly under operator approval (AD-07 §5.1). **Proceeded.** Every stage edit in this package is confined to the vLLM call site and the prompt resolver; no domain logic — no Jinja templates, no `WAVE_FORMAT_EXTENSIBLE` handling, no duration anchoring, no ffmpeg logic — was touched.

**(b) CLAUDE.md §12 requires two passes.** "Findings and proposed fix BEFORE writing code (stop and show the operator), then what changed and how it was verified after." The session instruction was to execute the package in full and commit. **Proceeded as instructed**; both passes are in this one document — §3 records findings and evidence before each fix, and the verification after it. The operator reviews before anything is pushed, which preserves the gate the two-pass rule exists to provide.

---

<a name="verdicts"></a>
## 3. Per-defect verdicts

### IVGS-0.1 — The user's runtime and description never reach the pipeline · **FIXED** · `c5e8f96`

**Re-verified evidence.** Partly drifted, and the drift is reported rather than glossed:

- `project_service.py:290-299` — the pipeline-start payload **does** now carry `project_name` and `project_description`. The order says it omits `description`; that is no longer true at this site. What it genuinely omitted was **`max_runtime_seconds`**.
- `project_service.py:394-401` (`approve_storyboard`) — omitted `project_description`, `max_runtime_seconds` **and** `priority`. The order's claim holds here in full.
- `models/task_result.py:97` — `max_runtime_seconds: int = 600`. With no key sent, every job got 600.
- `pipeline_orchestrator_v2.py:322-324` — `handle_stage_completion` calls `_build_stage_input(next_stage, None, ...)`, i.e. **always** `job_context=None`, so `_extract_context()` ran for every stage after the first. That function returns four keys (`job_id`, `project_id`, `project_name`, `language_code`). `project_description`, `max_runtime_seconds` and `tier` were lost from Stage 2 onward. The same `job_context=None` call appears at `:684` (media join) and `:1061` (watchdog).
- Confirmed the values are genuinely consumed: `stage1_transcript.py` `_render_user_prompt` binds `max_duration_seconds` and `project_description`; `prompts/stage1_user.j2` prints both. So the defect reached the model's prompt text.

**Fix.**
- API: pipeline start sends `max_runtime_seconds` **only when the project has one**, so the 600s default lives in exactly one place (`PipelineJobContext`) rather than being re-baked at the dispatch site. `approve_storyboard` now carries description, priority and runtime alongside name and audience.
- Workers: the job context is written to Redis at both dispatch entry points and read back by `_build_stage_input` for every later stage. The store **raises** on write failure rather than degrading quietly — `config.redis_url` *is* the Celery broker (`config.py:293-295`), so a Redis that cannot take this write cannot take the dispatch either. `_extract_context()` is now the last resort only and a store miss logs `job_context_store_miss` at **error** level naming exactly what is lost.
- `base_input` carries `project_description`, `target_audience` and `max_runtime_seconds` at the top level, which is where the flat-input stages (3, 5, video) actually read them; the per-scene media task inputs carry the same.

**Acceptance — met.**
- `ivgs-api/tests/test_wp_ivgs_0_dispatch_context.py` — asserts on the payload handed to `send_task` at both dispatch sites with `max_runtime_seconds=1800` and a description.
- **Negative control:** a project with no runtime sends **no key at all**, so 600 can only come from the model default. Asserted.
- `ivgs-workers/tests/test_wp_ivgs_0_job_context.py` — renders the **real** `stage1_user.j2` and `stage2_user.j2` and asserts `1800` and the description appear in the rendered text, and that `600` does not. A second negative control renders the same template from a default context and asserts `600` appears and `1800` does not.
- Also asserts the stored context beats the four-key stage output across a stage boundary, and that a store miss is loud.

**Pre-fix proof.** With `project_service.py` reverted: 2 of 3 API tests FAIL. With `pipeline_orchestrator_v2.py` reverted: 3 of 6 worker tests FAIL. The three prompt-rendering tests pass either way by design — the templates were always correct; the defect was upstream of them, and saying otherwise would overclaim.

---

### IVGS-0.2 — Three stages run a different model than they report · **FIXED** · `cc00209`

**Re-verified evidence.** Confirmed at all three sites, with one material correction to the order's framing.

- Stage 1 (`stage1_transcript.py:498-503`) resolves the AD-01 binding, then calls with `model=vllm_config["model"], base_url=vllm_config["base_url"]` (`:339-347`) and reports `model_used=binding.name` (`:658`). **Exactly as stated.**
- Stage 3 prompt writer (`stage3_images.py:193-194`) and Stage 5 text optimiser (`stage5_voiceover.py:159`) do the same. Stage 5 additionally requests `get_vllm_config_for_stage("image_generation")` for a text job. **Confirmed.**
- Stage 2 (`stage2_storyboard.py:598-599`) uses `model=engine_model_id(binding), base_url=binding.endpoint`. **Confirmed as the correct pattern.**

**Correction to the order.** The order says all three "resolve the AD-01 binding but call with env config", implying the fix is to use the binding already in hand. That is true for Stage 1 only. Stages 3 and 5 have **no chat-LLM binding to use**: Stage 3's is ComfyUI (`img_binding`/`vid_binding`), Stage 5's is Coqui/Kokoro (`tts_binding`). Neither can serve a `/v1/chat/completions` call. `ModelStage` (AD-01.5.2) has nine members and none of them is an auxiliary text-generation stage.

**Fix.**
- Stage 1: `_refine_single_transcript` takes the binding and calls through it. `output.model_used` is now the model the **engine says it served**, seeded with the binding's engine-native handle — never `binding.name` alone, which is a Model Store label, not evidence of what ran.
- Stages 3 and 5: each auxiliary call **borrows** the chat-LLM stage whose work it most resembles, and says so at the call site. Stage 3's prompt writer borrows `storyboard_generation` (scene description → creative visual text); Stage 5's optimiser borrows `transcript_refinement` (text rewriting). Both borrowed bindings are guaranteed to exist by the time the borrowing stage runs — Stage 3 always follows Stage 2, Stage 5 always follows Stage 1.
- New `ivgs-workers/utils/llm_binding.py` resolves the borrowed binding and **refuses** one whose engine cannot serve a chat call (`TextLLMBindingError`), instead of silently falling back to the env profile — which is what the old code did.
- Stage 5 also stops requesting the `image_generation` sampling profile; it now reads `transcript_refinement`, the text stage it borrows.

**Acceptance — met.** `ivgs-workers/tests/test_wp_ivgs_0_binding_honesty.py`, one test per fixed site. Each stubs a binding whose endpoint (`http://192.168.1.99:9999`) and engine model (`bound-model-engine-handle`) differ from anything the env config can produce — the test asserts that difference first, so it cannot pass by coincidence — then asserts the call went to the binding. Plus the `model_used` assertion and both sides of the non-chat-engine guard.

**Pre-fix proof.** With the three stage files reverted: **5 of 7 FAIL.**

**One pre-existing test was edited, deliberately.** `_refine_single_transcript` gained a required `binding` argument, so `test_stage1.py`'s three call sites needed it. Of those three, one (`test_refine_handles_timeout`) was passing at baseline and passes now; the other two were **already failing** at baseline for an unrelated reason (they import `VLLMResponse` from `models.task_result`, the pydantic model, which has no `.content` property, instead of `clients.vllm_client`). That defect was **not** fixed — the two tests still fail, exactly as they did before. Reported in §5.

---

### IVGS-0.3 — Production tier is unreachable · **FIXED** · `07bcd96`

**Re-verified evidence.** Confirmed exactly as stated. Neither dispatch payload set `tier`; `PipelineJobContext.tier` defaults `"prototype"` (`task_result.py:100-102`); every `get_binding(..., tier=...)` therefore resolved prototype. Corroborated in-repo at `talking_head_task.py:106-111`, whose own comment records the same gap. Additionally found: `_build_stage_input`'s `base_input` did not carry `tier` either, so even a correctly dispatched tier would have been dropped before reaching Stages 3, 5 and 6, which read `task_input.tier`.

**Where the value should come from (the one sentence the order asked for).** Tier belongs to the **run**, not the project — a project is drafted many times before it is rendered for real — so the smallest honest version is a dispatch parameter defaulting to prototype, exposed as an optional query parameter on both entry points, leaving the plumbing complete for whatever per-run UI the product later chooses without a schema change.

**Fix.** `trigger_pipeline` and `approve_storyboard` take `tier` (default `"prototype"`) and put it in the payload; an unknown tier **raises** rather than being silently coerced back to prototype. `POST /projects/{id}/trigger` and `POST /projects/{id}/storyboard/approve` accept `?tier=`, and an unknown value is a **400**, not a 409 — it is a bad request, not a state conflict. `base_input` and the per-scene media inputs carry `tier`.

**Acceptance — met.** The order asks for "a test dispatching with `tier="production"` and asserting `get_binding` receives it". Both halves are covered, plus the span between them:
- `ivgs-api/tests/test_wp_ivgs_0_tier_dispatch.py` — production reaches the payload; prototype is the default; an unknown tier is refused with **nothing dispatched**; storyboard approval carries it too.
- `ivgs-workers/tests/test_wp_ivgs_0_tier.py` — the tier survives job context → stage input for both values, survives a stage boundary where `handle_stage_completion` passes `job_context=None`, and `get_binding` is asserted to actually receive `tier="production"` at the end of the chain.

---

### IVGS-0.4 — Prompt resolution can replace Stage 1's prompt with the translation template · **FIXED** · `8092cd8`

**Re-verified evidence.** Confirmed in every particular.

- `stage1_transcript.py:273-276` sends `params={"prompt_type": "transcript_refinement"}`.
- `prompts.py:452-459` — `list_project_prompts` took **no such parameter**; `prompt_service.py:96-109` `resolve_effective_prompts` loops `for pt in PromptType` and returns all ten.
- `stage1_transcript.py:282-291` classified on `"system" in p.get("prompt_type","").lower()`. `PromptType` (`shared/models/enums.py:111-122`) has ten members and **none contains the substring "system"**, so every prompt fell through to the `user_prompt` branch and the last one assigned won. The last enum member is `TRANSLATION`.
- `seed_prompts.py` seeds all ten active from `ivgs-api/seed/default_prompts/`, so the defect bites whenever the DB prompts are seeded. Without seeding, the `.j2` fallback is correct — as the order says.
- Stage 2 (`stage2_storyboard.py:552-556`) is the same pattern, copied.

**Fix.** The endpoint honours `prompt_type`; an unknown type is a **400**, not an empty list a caller could misread as "not configured"; unfiltered behaviour is unchanged. New `ivgs-workers/utils/prompt_selection.py` selects by **exact declared type** and raises `PromptTypeMismatchError` when the response carries prompts and none is the requested one — the endpoint ignoring the filter is precisely the failure being fixed, so it must be loud. Both stage resolvers now do that selection **outside** their `try/except`, so the refusal is not swallowed by the broad transport handler; a genuinely dead API still falls back to the `.j2` templates quietly, which is correct.

**Corrected while here.** Both resolvers now return `None` for the system slot and say why. A `PromptType` row carries exactly **one** text, so the API can never supply a system prompt — the old `"system"`-substring branch was pretending to read a distinction the schema does not have. The system prompt comes from `stage1_system.j2` / `stage2_system.j2`, as it always did in practice.

**Acceptance — met.**
- `ivgs-api/tests/test_wp_ivgs_0_prompt_filter.py` — **all ten prompts seeded**; filtered request returns exactly one; each of the ten is individually addressable (parametrised over all ten); the specific regression that `translation` is not what Stage 1 receives; unknown type is a 400.
- `ivgs-workers/tests/test_wp_ivgs_0_prompt_type.py` — Stage 1 receives `transcript_refinement` **and only that** from a ten-type response; the filter is actually sent; **negative control:** a mismatched type raises rather than substituting; substring matches no longer count (`transcript_refinement_v2` does not satisfy `transcript_refinement`); an empty response is not an error; a transport failure still falls back quietly. Same for Stage 2.

**Pre-fix proof.** API endpoint reverted: **13 of 14 FAIL.** Stage files reverted: **4 of 12 FAIL** (the 8 that still pass exercise the new pure selection helper, which is new code).

> **This fix alone does not make seeded DB prompts work.** See finding F6 in §5 — a serious follow-on that the order did not anticipate.

---

### IVGS-0.5 — The New Project form cannot succeed as built · **FIXED** · `9262944`

**Re-verified evidence.** Confirmed, and **worse than stated**.

- `useProjects.ts:74-82` posts `multipart/form-data` to `projects.py:67-80`, a JSON Pydantic route taking `data: ProjectCreate`. **Confirmed.** Additionally: it goes through `apiClient.post`, which does `JSON.stringify(body)` (`api-client.ts:257-262`) — so the body arrived as the literal string `"{}"` regardless of what the user typed. The request could not have succeeded even against a form-accepting endpoint.
- Language codes `en`/`es`/… (`new/page.tsx:27-38`) against the allow-list `en-US`/`es-ES`/… (`schemas/project.py:38-45`). **Confirmed** — and only 8 of the form's 10 languages exist server-side at all (`pt`, `ko`, `hi` have no BCP-47 counterpart in the allow-list).
- `talking_head_clip` has no handler on the create route; the pipeline reads a `reference_clip` asset (`pipeline_orchestrator_v2:1323-1343` queries `asset_type=reference_clip`). **Confirmed.**
- `existing_storyboard` has zero server-side consumers. **Confirmed.**

**Fix — smallest honest version, no new backend capability.**
- `createProject` sends **JSON** for the four fields the endpoint takes.
- The clip is uploaded afterwards through the **existing** assets route as `reference_clip`.
- **Transcripts are uploaded too**, through the existing transcripts route. The order's four fields do not include them, but without at least one transcript `trigger_pipeline` refuses to start ("Cannot trigger pipeline: no transcripts uploaded") — a form that creates an unrunnable project has not succeeded in any useful sense.
- The language list is now **exactly** the server's allow-list.
- **The storyboard is stored**, as a project `document` asset, and the field says plainly: *"Saved with the project — not yet used. Nothing in the pipeline reads this file today; it is kept so you do not have to upload it again when support arrives."* The order allowed removal or storage-with-a-plain-label. Storage was chosen because it needs no new backend capability (the assets route already accepts `document`) and silently discarding a file the user deliberately attached is the worse of the two.

**Acceptance — met, with a stated substitution.** The order allows "a frontend test **or** documented manual walk with screenshots". There is **no frontend test framework in this repo** (no jest, no vitest in `ivgs-frontend/package.json`), and adding one is beyond this package. **No browser was driven and there are no screenshots.** In their place, `ivgs-api/tests/test_wp_ivgs_0_new_project_form.py` (21 tests) does the documented walk mechanically:

- **The full walk** replays the exact request sequence the fixed form issues — create → clip → transcripts → storyboard — in order, then **verifies the created rows by reading them back through the API**: project name, description, `max_runtime_seconds=1800`, state `DRAFT`; the assets list showing the clip under `reference_clip` with the id the upload returned, plus the `document`; both transcripts listed.
- **The project can then actually be triggered**, and the dispatch carries `1800` and `tier=prototype` — proving the form's output feeds the pipeline fixed in IVGS-0.1 and 0.3.
- Every language the form offers is accepted (parametrised over all 8); every code from the **old** list is still rejected with 422 (parametrised) — proof the old list could never have worked.
- The old multipart payload shape, verbatim, is a 422.
- **Four cross-checks read `ivgs-frontend` source** and hold the client to the server's contract: offered languages ⊆ allow-list; `createProject` builds no `FormData`; the clip goes up as `reference_clip` and `talking_head_clip` is gone; the storyboard field says "not yet used" and `existing_storyboard` is gone.

**Pre-fix proof.** With both frontend files reverted, **all four cross-checks FAIL**. `npx tsc --noEmit` exits 0 after the change.

---

<a name="not-verified"></a>
## 4. What was NOT verified

Stated plainly, because a claim without evidence is a defect in the report.

1. **Nothing was run against a live pipeline.** No Celery task was dispatched to a real worker, no vLLM endpoint was called, no image or audio was generated. Every worker-side claim rests on unit and integration tests with the HTTP client, the binding resolver, or Celery's `send_task` stubbed. **Observed working means observed in tests, not observed in production.**
2. **No browser was driven and no screenshots exist for IVGS-0.5.** The frontend change is verified by `tsc --noEmit`, by source-level cross-checks, and by an API-level replay of the request sequence — not by a human clicking the form. Whether the page *renders and behaves* correctly is unverified.
3. **The Redis job-context store (IVGS-0.1) was never exercised against a real Redis.** `_store_job_context` / `_get_job_context` are patched in the tests. The claim that a Redis write failure fails the dispatch loudly rests on reading `config.py:293-295` (redis_url is the broker), not on an observed outage.
4. **The borrowed bindings (IVGS-0.2) were never resolved against the real Model Store.** `get_binding` is stubbed throughout. Whether a `storyboard_generation` or `transcript_refinement` binding actually resolves on this fleet today is unverified — the Model Store's seeded state was not inspected. If either is absent, Stage 3's prompt writer and Stage 5's optimiser will now raise where they previously fell back to the env profile. **This is a deliberate behaviour change and the operator should be aware of it before deploy.**
5. **IVGS-0.3's tier was never carried through a real `get_binding` to a real production-tier model.** The test asserts `get_binding` receives `tier="production"`; whether a production-tier model exists for any stage in the Model Store was not checked.
6. **The `?tier=` query parameters were not exercised over HTTP.** They were verified at the service layer; the route wiring is verified only by `tsc`-equivalent reasoning and the API test suite passing unchanged.
7. **Root `tests/` (e2e, integration, smoke, providers, spec_compliance) never ran** — the directory is uncollectable at baseline (`aiosqlite` missing) and remains so. Nothing in this package changed that, and nothing in this package is covered by it.
8. **7 worker test files remain uncollectable** and 22 worker tests remain in error, all pre-existing. Those code paths were not exercised.
9. **No deploy, no container rebuild, no image tag change.** The running containers are on the pre-change images. Nothing in this report describes deployed behaviour.

---

<a name="found"></a>
## 5. Found along the way — reported, not fixed

**F1 — The repo's own pytest gate cannot run.** `pytest` with the configured `testpaths` dies at collection: `ImportPathMismatchError: ('tests.conftest', '/opt/ivgs/ivgs-api/tests/conftest.py', '/opt/ivgs/tests/conftest.py')`. Both `ivgs-api/tests` and `tests/` carry `__init__.py` and resolve to the package name `tests`. **There is no single command that runs this project's tests.** Each path must be invoked separately. Not fixed — the fix is to rename one package or drop an `__init__.py`, which touches every import in that tree.

**F2 — Root `tests/` is entirely uncollectable.** `tests/conftest.py:34` imports `shared.database`, which builds an engine from `DATABASE_URL` — set at the top of the same file to `sqlite+aiosqlite:///./test.db`. `aiosqlite` is not installed in `.venv`. Every test under `tests/e2e`, `tests/integration`, `tests/smoke`, `tests/providers` and `tests/spec_compliance` has therefore been dead. Not fixed — installing a dependency changes the environment.

**F3 — 7 worker test files cannot be collected**, from three missing modules: `ivgs_workers`, `tasks.prototype_draft_task`, `tasks.stage4_voiceover`. The latter two are the filename-vs-registered-name trap in CLAUDE.md §7 leaking into the tests: `STAGE_TASK_MAP` registers `tasks.stage4_voiceover.generate_voiceover_task` and `tasks.prototype_draft_task.assemble_prototype_draft`, but the files are `stage5_voiceover.py` and `stage7_prototype_draft.py`. Affected: `test_composition.py`, `test_dlq_service.py`, `test_fallback_chain.py`, `test_orphan_cleanup.py`, `test_retention.py`, `test_retry_engine.py`, `test_stage4.py`.

**F4 — `test_health.py::test_health_check_no_auth_required` fails at baseline** and still fails. Unrelated to this package; not investigated.

**F5 — `test_stage1.py` imports the wrong `VLLMResponse`.** It imports from `models.task_result` (the pydantic model, which has **no** `.content` or `.finish_reason` property) rather than `clients.vllm_client` (the dataclass, which has both). Two tests have therefore been failing on `AttributeError: 'VLLMResponse' object has no attribute 'content'` — not on anything about Stage 1. Left failing so the baseline comparison stays honest. One-line fix when someone wants it.

> **F6 — SERIOUS: IVGS-0.4's fix alone does not make seeded DB prompts work.**
> The seeded templates and the workers disagree on variable names. `ivgs-api/seed/default_prompts/transcript_refinement.j2` uses `{{ project_title }}`, `{{ max_duration_seconds }}` and **`{{ narration_text }}`**. `stage1_transcript._render_user_prompt` binds `project_title` ✓, `max_duration_seconds` ✓ — and **`transcript_text`**, not `narration_text`. `storyboard_generation.j2` has the identical mismatch against `stage2_storyboard._render_user_prompt`, which binds `combined_transcript`.
>
> So with prompts seeded, Stage 1 now correctly receives the `transcript_refinement` template — and Jinja still renders `{{ narration_text }}` as empty, so **the transcript still vanishes**. The order attributed the empty render to the translation template's variables; the same defect exists in the *correct* template. IVGS-0.4 fixes which prompt is selected, which was genuinely broken and is genuinely fixed. It does not fix what that prompt renders to.
>
> Not fixed: it needs an operator decision on whether the templates are renamed to the workers' variables or the workers bind the templates' names, and it touches the seed data that may already be in the live database.

**F7 — `POST /projects/{id}/upload-talking-head` feeds nothing.** It stores `asset_type="talking_head"` (`projects.py:216-224`) and sets `project.talking_head_asset_id`. The orchestrator's `_fetch_reference_clip_id` queries `asset_type="reference_clip"`. A clip uploaded through the dedicated route will never be found as the Stage 6 reference clip. The fixed form deliberately uses the generic assets route with `reference_clip` instead. The dedicated route was left alone.

**F8 — `shared/models/enums.py:AssetType` is missing `reference_clip`.** The database enum has it (migration `0025_add_reference_clip_asset_type`), `asset_service.ASSET_TYPE_PATHS` and `MAX_FILE_SIZES` have it, `app/models/asset.py:42` has it. Only the shared enum does not. Anything validating against `AssetType` will reject a legitimate asset type.

**F9 — `projectFetcher` in `useProjects.ts:45` unwraps a wrapper that is not there.** It returns `response.data.data` for `GET /api/v1/projects/{id}`, but that route has `response_model=ProjectResponse` and returns the object **unwrapped** (`ivgs-api/tests/test_projects.py:114,120` reads `response.json()["id"]` directly). The project **detail** page therefore receives `undefined`. `projectsFetcher` at `:39` is correct, because the *list* route genuinely returns `PaginatedResponse`. This is on the page the fixed New Project form navigates to after a successful create. **Not fixed** — it is a different route from the one this order names, and the order says report, don't fix. It is a one-line change and I recommend it be scheduled next.

**F10 — CI's Python jobs are switched off.** `.github/workflows/ci.yml`: `lint-python` and `test-python` both carry `if: false`. `docker-build` declares `needs: [test-python, ...]`, so it depends on a job that never runs. No Python test or lint gate runs in CI; local node-01 runs are the only signal, which matches the comment in the file.

**F11 — the frontend has no lint gate and no test framework.** `npx next lint` drops into an interactive ESLint setup prompt (no config present), so it cannot run unattended; CI wraps it in `|| true` anyway. `package.json` has no jest/vitest.

**F12 — files not mine appeared in the working tree mid-session.** `dev/workpackages/WP-31-TEMPORAL-GROUNDWORK.md` (owned by `root`, timestamped 21:42) and `configs/temporal/` were created by something outside this session while it was running. One was swept into the IVGS-0.1 commit by a `git add -A` and was **removed from that commit by amend** before anything else happened; every later commit used explicit paths. Both remain **untracked and untouched** — nothing was deleted (CLAUDE.md §3 / the order's no-deletion rule).

---

<a name="decisions"></a>
## 6. Decisions needed from the operator

1. **F6 — the seeded prompt templates.** Rename the template variables to the workers' names (`transcript_text`, `combined_transcript`), or change the workers to bind the templates' names (`narration_text`)? Until one happens, a seeded `transcript_refinement` prompt renders with an empty transcript. This touches seed data that may already be live.
2. **IVGS-0.2 borrowed bindings.** Stage 3's prompt writer borrows `storyboard_generation` and Stage 5's optimiser borrows `transcript_refinement`. Both are my judgement calls, recorded at the call site. If AD-01 should instead grow a ModelStage for auxiliary text generation, these are the two call sites to repoint.
3. **IVGS-0.2 behaviour change on deploy.** Stages 3 and 5 now **raise** if their borrowed binding resolves to a non-chat engine, where they previously fell back to the env profile. Confirm the Model Store has servable `storyboard_generation` and `transcript_refinement` bindings on this fleet before deploying, or Stage 3 and Stage 5 will fail where they used to (wrongly) proceed.
4. **IVGS-0.3 tier surface.** `?tier=` is on both routes but nothing in the UI sets it. Is a per-run tier selector wanted on the frontend, and where?
5. **F9 — the project detail fetcher.** Shall I fix the one-line `response.data.data` bug next? It is on the page the New Project form navigates to.
6. **F1/F2/F3 — the test gates.** Three of the four Python test paths cannot run under the repo's own configuration. Do you want a follow-up package to make `pytest` work as a single command?
7. **F12 — the foreign files.** `dev/workpackages/WP-31-TEMPORAL-GROUNDWORK.md` and `configs/temporal/` are untracked in the tree and are not mine. Leave, commit, or remove — your call; I have not touched them.

---

<a name="commits"></a>
## 7. Commits — HELD, not pushed

| # | Hash | Defect | Subject |
|---|---|---|---|
| 1 | `c5e8f96` | IVGS-0.1 | carry the user's runtime and description end to end |
| 2 | `cc00209` | IVGS-0.2 | three stages ran a different model than they reported |
| 3 | `07bcd96` | IVGS-0.3 | make the production tier reachable |
| 4 | `8092cd8` | IVGS-0.4 | stop the translation template replacing Stage 1's |
| 5 | `9262944` | IVGS-0.5 | the New Project form could not succeed as built |

Base `4c21460`. Each commit is one defect, gated on the compliance scanner (PASSED, 0 violations, at every step) and on the API and worker suites with the failure set diffed against the previous commit.

Files changed across the package:

```
 ivgs-api/app/api/v1/projects.py                          +15  -2
 ivgs-api/app/api/v1/prompts.py                           +37  -2
 ivgs-api/app/api/v1/storyboard.py                        +11  -2
 ivgs-api/app/services/project_service.py                 +47  -3
 ivgs-frontend/src/app/projects/new/page.tsx              +59 -33
 ivgs-frontend/src/hooks/useProjects.ts                   +68  -7
 ivgs-workers/tasks/pipeline_orchestrator_v2.py          +120 -15
 ivgs-workers/tasks/stage1_transcript.py                  +34 -22
 ivgs-workers/tasks/stage2_storyboard.py                  +16 -16
 ivgs-workers/tasks/stage3_images.py                      +22  -2
 ivgs-workers/tasks/stage5_voiceover.py                   +28  -6
 ivgs-workers/utils/llm_binding.py                        +71  -0   (new)
 ivgs-workers/utils/prompt_selection.py                   +88  -0   (new)
 ivgs-workers/tests/conftest.py                           +17  -1
 ivgs-workers/tests/test_stage1.py                        +22  -0
 ivgs-api/tests/test_wp_ivgs_0_dispatch_context.py       +170  -0   (new)
 ivgs-api/tests/test_wp_ivgs_0_tier_dispatch.py          +107  -0   (new)
 ivgs-api/tests/test_wp_ivgs_0_prompt_filter.py          +105  -0   (new)
 ivgs-api/tests/test_wp_ivgs_0_new_project_form.py       +270  -0   (new)
 ivgs-workers/tests/test_wp_ivgs_0_job_context.py        +204  -0   (new)
 ivgs-workers/tests/test_wp_ivgs_0_binding_honesty.py    +246  -0   (new)
 ivgs-workers/tests/test_wp_ivgs_0_tier.py               +102  -0   (new)
 ivgs-workers/tests/test_wp_ivgs_0_prompt_type.py        +151  -0   (new)
```

**Nothing has been pushed. Nothing has been deployed. No running service was modified.** The operator reviews this report before anything leaves node-01.
