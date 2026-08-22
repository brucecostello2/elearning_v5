# WP-IVGS-0 — Five defect fixes that gate everything else
## Work order for the IVGS agent · Operator-approved under AD-07 §5.1, 2026-08-21 · Complete and standalone

You are a fresh session in the IVGS v5 repository (`elearning_v5-main`). Everything you need is in this document. Every claim below was verified against this codebase on 2026-08-21 with file:line evidence — re-verify each before fixing (line numbers may have drifted; the defects will not have).

## The rules of this project (identical to the companion MBCP project's, now in force here)

- One package = one commit series · **commit and HOLD — the operator pushes.** Never push, never deploy, never touch a running service.
- Delete nothing without operator sign-off to a named list.
- Every report states what was verified, HOW it was verified (command + output), and what was NOT verified. A claim without evidence is a defect in the report.
- Plain English in anything a user sees.
- If this order conflicts with what you find in the tree, STOP on that item and report the conflict — do not improvise.

## STEP 0 — Establish the ground truth of this repo (report it before fixing anything)

1. Confirm repo root, current HEAD, clean tree.
2. Find and run the existing test gates (Python: pytest config at repo root or per service; frontend: `ivgs-frontend` package.json scripts; CI: `.github/workflows/`). Record the BASELINE result of each — what passes and what fails BEFORE you change anything, so your changes are never blamed for pre-existing failures (or credited with pre-existing passes).
3. Your report lives in `dev/workpackages/reports/`. **Amended 2026-08-22 by operator ruling, FINAL:** this order originally said `dev/workorders/reports/` "mirroring the MBCP convention". That directory does not exist in this repo, and CLAUDE.md §12 governs — `dev/workpackages/reports/` is the committed convention for all reports, where twelve already live. **`workorders/` is not adopted and must not be created**; one created on 2026-08-22 was removed the same day. MBCP's layout does not govern here. Ledger **P1.4i**, CLAUDE.md §12.

## THE FIVE DEFECTS — fix in this order; one commit each

### IVGS-0.1 — The user's runtime and description never reach the pipeline
**Evidence:** `ivgs-api/app/services/project_service.py:290-299` — the dispatch payload omits `max_runtime_seconds` and `description`; `PipelineJobContext.max_runtime_seconds` then defaults to 600 (`ivgs-workers/models/task_result.py:97`), so Stage 1/2 prompts say "600 seconds" for every project. `ivgs-workers/tasks/pipeline_orchestrator_v2.py:805-814` `_extract_context()` rebuilds context from the previous stage's 4-key output, so `project_description` is `""` from Stage 2 onward.
**Fix:** include the project's real `max_runtime_seconds`, `description`, `name` in every dispatch payload (both dispatch sites — project start AND `approve_storyboard`'s `dispatch_media_generation`, `project_service.py:394-401`); make `PipelineJobContext` carry them end to end; `_extract_context()` must never be the source of project facts — the job context is.
**Accept:** a unit/integration test creating a project with `max_runtime_seconds=1800` and a description, asserting the rendered Stage-1 AND Stage-2 user prompts contain `1800` and the description. Negative control: the 600 default appears ONLY when the project genuinely has no value.

### IVGS-0.2 — Three stages run a different model than they report
**Evidence:** Stage 1 resolves the AD-01 binding (`stage1_transcript.py:498-503`) but calls with `model=vllm_config["model"], base_url=vllm_config["base_url"]` from env config (`:339-347`), then reports `output.model_used = binding.name` (`:658`). Same pattern: Stage 3 prompt-writer (`stage3_images.py:193-194`), Stage 5 text-optimiser (`stage5_voiceover.py:159` — which also requests the `image_generation` vLLM profile for a TTS task). Stage 2 is the CORRECT pattern: `model=engine_model_id(binding), base_url=binding.endpoint` (`stage2_storyboard.py:598-599`).
**Fix:** all three call sites use the binding, exactly as Stage 2 does. `model_used` must be the model that ran — never the one that was merely selected.
**Accept:** tests stubbing a binding whose endpoint/model differ from env config, asserting the HTTP call goes to the binding's endpoint with the binding's model, and `model_used` equals it. One test per fixed site.

### IVGS-0.3 — Production tier is unreachable
**Evidence:** neither dispatch payload sets `tier`; `PipelineJobContext.tier` defaults `"prototype"` (`task_result.py:100-102`), so every `get_binding(..., tier=...)` resolves prototype. Corroborated in-repo at `talking_head_task.py:106-111`.
**Fix:** thread `tier` through dispatch. Where the value should come from (project field, per-run choice) — propose in one sentence and implement the smallest honest version (a dispatch parameter defaulting to prototype), so the plumbing exists when the product decides.
**Accept:** a test dispatching with `tier="production"` and asserting `get_binding` receives it.

### IVGS-0.4 — Prompt resolution can replace Stage 1's prompt with the translation template
**Evidence:** the worker requests `?prompt_type=...` (`stage1_transcript.py:273-276`) but the endpoint takes no such parameter and returns ALL ten types (`ivgs-api/app/api/v1/prompts.py:452-459`, `prompt_service.py:96-109`); the worker's classifier keys on the substring `"system"` (`stage1_transcript.py:282-291`), which no type contains, so the LAST enum member — TRANSLATION — wins as the user prompt; its variables (`target_language`, `narration_text`) are never passed and Jinja renders them empty, so the transcript vanishes. Applies when DB prompts are seeded (`seed_prompts.py` seeds all ten active); otherwise the `.j2` fallback is correct.
**Fix:** the endpoint honours a `prompt_type` filter; the worker matches by exact type, never substring; a returned prompt whose declared type differs from the requested one is refused loudly. Same fix wherever the pattern is copied (Stage 2: `stage2_storyboard.py:552-556`).
**Accept:** a test with all ten prompts seeded asserting Stage 1 receives `transcript_refinement` and only that; a negative control asserting a mismatched type raises rather than silently substitutes.

### IVGS-0.5 — The New Project form cannot succeed as built
**Evidence:** the form posts `multipart/form-data` (`ivgs-frontend/src/hooks/useProjects.ts:74-82`) to a JSON Pydantic endpoint (`ivgs-api/app/api/v1/projects.py:67-80` with `data: ProjectCreate`); its language codes (`en`, `es`… — `new/page.tsx:27-38`) fail the validator's allow-list (`en-US`, `es-ES`… — `schemas/project.py:38-45`); `talking_head_clip` has no handler on the create route (the pipeline reads a `reference_clip` asset uploaded via `assets.py:78-99`); `existing_storyboard` has zero server-side consumers.
**Fix, smallest honest version:** the form submits JSON for the four real fields; on success it uploads the talking-head clip through the existing assets route as `reference_clip`; language options use the codes the validator accepts; the storyboard upload is either removed or stored as an asset with the UI saying plainly "saved — not yet used" (state which you did and why). Do NOT build new backend capability here — that is Phase 1 of AD-07.
**Accept:** a frontend test (or documented manual walk with screenshots) proving a project can actually be created from the form with a clip and languages, and the created rows verified via the API.

## Exit gate

Baseline test results vs after (both recorded); one commit per defect, HELD; a report at `dev/workpackages/reports/WP-IVGS-0-report_<YYYY-MM-DD>.md` (path and naming per CLAUDE.md §12; amended 2026-08-22) with: per-defect verdict + evidence, what was NOT verified, anything found along the way (report, don't fix), commit hashes. The operator reviews the report before anything is pushed.
