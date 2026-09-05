> ⚠ **STALE PREMISES — banner added 2026-09-05 by the WP-69 executor under `dev/CLAUDE.md` §0 rule 5.3, at operator instruction.**
> 1. §2 D1 says *"alembic head (0054)"*. The tree's migration chain head is **0055** (`0055_wp_ivgs_12j_interview_and_vocabulary.py`, held, undeployed); **production is at 0054**. The index replays to 0055 and labels 0055-only columns per table.
> 2. §3 step 1 says *"use `ts-morph` if present"*. It is **absent** from the frontend toolchain; the TypeScript pass is the regex fallback.
> 3. §4 *"only files … under `dev/audit/` and the report"* conflicted with `dev/CLAUDE.md` §0 rules 5.2/5.3; **operator ruling 2026-09-05: the CLAUDE.md rules stand** — the board row and this banner were added in a follow-up commit.
> Report: `dev/workpackages/reports/WP-69-CONSUMER-AUDIT-report_2026-09-05.md`.

# WP-69 — CONSUMER AUDIT: every shared definition in the codebase, checked against every place that uses it

**Order date:** 2026-09-05 · **Owner:** operator · **Executor:** coding agent on node-01, one fresh session (a second session is permitted only via the HANDOFF rule below) · **Tier:** B (observable) — the deliverable is a generated index plus a defect list with file:line evidence the operator can open · **Repo:** `/opt/ivgs` (IVGS only; MBCP is read-only context and is out of scope) · **GPU nodes:** not required; do not start them.

## 1. Why this order exists

Two external reviews in a row found the same defect class in the specification: a definition was changed in one place while the places that use it kept the old rule. The 14 August and 29 August audits found the same class in the code — a save that returned `False` and no caller checked; a decrement that returned `0` on error and was read as "all done"; a preset that writes an actor's clip as `talking_head` while Stage 6 looks for `reference_clip`. Each was found by a person reading code. None was found by a test.

This order makes that reading systematic and complete for the code as it stands today. It does not pick a start date: there is no verified-good baseline to measure from. It lists every shared definition in the system and checks every consumer of each one.

**This is a read-only audit.** You change no source file. You fix nothing, however obvious. Every finding goes in the report; the operator decides what becomes a work package.

## 2. Scope — the seven definition families

Enumerate every definition in each family, then every consumer of each definition, then check agreement. "Agreement" means: same name, same type, same optionality, same enumeration members, same argument count and order, same key spelling — whatever the family's notion of a contract is.

| # | Family | Definition sites | Consumer sites | What "disagree" means |
|---|---|---|---|---|
| D1 | **Database schema** | alembic head (0054): every table, column, type, nullability, FK, enum | SQLAlchemy models (`ivgs-api/app/models/`), raw SQL anywhere (`text(`, f-strings with SQL, `psql` in scripts), API schemas that mirror rows, frontend types that mirror rows | a model column the migration lacks or vice versa; a nullable mismatch; a Python enum whose members differ from the DB enum; raw SQL naming a column that does not exist |
| D2 | **API contracts** | every Pydantic request/response model in `ivgs-api/app/schemas/` and inline route models | routes, services, `ivgs-frontend/src/types/*.ts` and every `fetch`/client call, `ivgs-workers` HTTP clients that call the API, `ivgs-scheduler` callers | a TS field the Pydantic model does not emit; a required field the client omits; an enum value one side has and the other lacks; a route path or method a client calls that no route serves |
| D3 | **Task and activity signatures** | every Celery task (`@celery_app.task` / `@shared_task`: name, args, kwargs), every `temporal_pipeline` activity and its payload dataclass | every `send_task(`, `apply_async(`, `.delay(`, `STAGE_TASK_MAP`, `signature(`; the workflow's activity calls | a producer passing arguments the task does not accept, or omitting ones it requires; a task name string that matches no registered task; a payload dataclass that disagrees with the Pydantic model it mirrors |
| D4 | **Enumerations and name vocabularies** | project/job states, stage names and `stage_index` values, checkpoint stage names, `asset_type` values, error-classifier classes, GPU queue names, capability and style names, model-registry keys, gate names, notification kinds — wherever each is *defined* (Python `Enum`, a constants module, a DB enum, a TS union) | every string literal or member reference of that vocabulary anywhere in Python, TS, SQL, YAML, compose files, scripts | a literal not in the definition; a definition member no consumer uses; two definitions of the same vocabulary that differ (the stage-index map is a known case — cite `docs/stage-numbering-map.md`) |
| D5 | **Configuration keys** | every `os.environ`/`settings.` read, every `Field(env=…)`; every key declared in `configs/`, `ivgs-infra/*.yml`, `.env.example`, node `.env` files you can read | the reverse: every declared key vs every read | a key read but never declared anywhere (silent default); a key declared but never read (dead config); the same key with different defaults in two places |
| D6 | **Cross-service protocols** | the scheduler's HTTP API (`ivgs-scheduler/main.py` routes: register, heartbeat, reserve, release, extend, fleet, nodes); engine server request/response shapes (`ivgs-workers/servers/*`); Redis key schemas (media-join counters, priority queues, GPU registry, node liveness); SeaweedFS path/key conventions; the API's node/model endpoints the frontend polls | the worker-side clients (`utils/gpu_utils.py`, `clients/*`), the API's scheduler client, the frontend's monitoring pages, `periodic_tasks.py` | a client sending a field the server ignores or lacking one it requires; a Redis key written under one pattern and read under another; a server response field no client reads and a client field no server sends |
| D7 | **Frontend ↔ API types** | `ivgs-frontend/src/types/*.ts` | every component and hook that reads a field of those types; the Pydantic models of D2 | a field the UI renders that the API never sends (renders blank forever); a field the API sends that no type declares; optionality mismatch (UI assumes present, API may omit) |

Out of scope: MBCP; the retired design-path prompts (they are being replaced); anything under `dev/spikes/`; code style.

## 3. Method — build the index first, then check

**Step 1 — Inventory (script-built, committed).** Write `dev/audit/build_consumer_index.py` that produces `dev/audit/consumer_index.json` and a readable `dev/audit/consumer_index.md`. For Python use `ast` (class/enum/table definitions, decorators, call sites, string literals); for TypeScript use `ts-morph` if present in the frontend toolchain, otherwise a disciplined regex pass over `types/` and `src/`; for SQL/YAML/compose use direct parsing. One row per definition: family, name, definition file:line, and the list of consumer file:line entries. The script must be re-runnable and deterministic (sorted output). Commit the script and both outputs.

**Step 2 — Check.** For every row, compare each consumer to the definition under the family's "disagree" rule. Do this by script where the check is mechanical (name/type/enum membership/arg count) and by reading where it is not (semantic mismatch — a field with the right name used for the wrong thing, as in the `talking_head` / `reference_clip` case). Record every disagreement in the report with: family, definition, consumer file:line, what disagrees, and a **failure scenario** — the concrete input or state under which the disagreement produces wrong behaviour. A disagreement with no describable failure scenario is *suspect*, not *definite*.

**Step 3 — Classify.** Three lists, most severe first:
- **Definite defects** — a disagreement with a failure scenario.
- **Suspect** — a disagreement you could not turn into a scenario, or a semantic mismatch you are not certain of.
- **Orphans** — definitions with no consumer (dead) and consumers with no definition (undeclared).

For each definite defect, also say which of the two futures it lives in: **replaced** (the design path or a stage body — being rebuilt under AD-11/AD-12) or **surviving** (API, DB, scheduler, frontend, worker plumbing). The surviving list is the one that becomes work packages.

**Step 4 — Calibration (mandatory).** The method is only trustworthy if it finds what is already known. Your definite or orphan lists **must** contain each of the following, found by the method rather than by looking them up; if any is absent, the index is incomplete — say so and fix the script before reporting:
1. `preset_service.apply_to_project` writes the actor clip with `asset_type="talking_head"`; the orchestrator's Stage-6 lookup reads `asset_type=reference_clip` (D4, definite).
2. `gpu_registry.add_node_job` has no caller (D6/D3, orphan).
3. `scheduler.extend_reservation` is called only from tests (D6, orphan in production paths).
4. The frontend never sends `library_kind` although `POST /projects/{id}/assets/upload` accepts it (D2/D7, orphan).
5. `project_gate.signal_payload()` emits `gate_storyboard` / `gate_draft` while `temporal_pipeline` declares `storyboard_approved` / `draft_approved` (D3/D4, definite).
6. `composition_manifest` writes no checkpoint row while every other stage does; `tts_audio` uses `stage_index=4` colliding with the stage-numbering map (D4, definite).

Report the calibration result explicitly: six of six found, or which were missed and why.

## 4. Constraints

- **No source edits.** The only files you create or change are under `dev/audit/` and the report. If you notice a one-line fix, write it in the report as a recommendation with the diff you would apply; do not apply it.
- **No pipeline runs, no deploys, no GPU.** Static analysis and reading only. Running the existing test suite is permitted at most **twice** and only if the index script needs a fixture it provides; a timeout-killed run is an environment note, not a retry trigger.
- **No deletions** of any file. No `git rm`. Orphans are reported, never removed.
- **Commit and HOLD.** Commit `dev/audit/*` and the report on a branch `wp-69-consumer-audit`; do not push. The operator pushes count-gated.
- **Weights:** irrelevant to this order; do not fetch anything from HuggingFace or elsewhere.
- **Time-box:** if the index script is not producing complete D1–D4 output by the midpoint of your context, stop extending it and report what it covers; a partial index honestly labelled beats a complete one you cannot finish.

## 5. Deliverables

1. `dev/audit/build_consumer_index.py` — re-runnable, deterministic.
2. `dev/audit/consumer_index.json` and `dev/audit/consumer_index.md` — the index, with a header stating the commit hash it was built from and per-family counts (definitions, consumers).
3. `dev/workpackages/reports/WP-69-CONSUMER-AUDIT-report_2026-09-05.md` with sections in this order: **Calibration result** · **Definite defects — surviving code** · **Definite defects — replaced code** · **Suspect** · **Orphans** · **Per-family coverage and known gaps of the method** (what the script cannot see: dynamic attribute access, `getattr` strings, f-string SQL you could not parse, TS you could only regex) · **Recommended one-line fixes (not applied)** · **HANDOFF** (only if a second session is needed: exact state, what remains, how to resume).

Every defect row: `family | definition (file:line) | consumer (file:line) | disagreement | failure scenario | future (replaced/surviving)`.

## 6. Exit test (performed by the operator before the next order)

1. `python dev/audit/build_consumer_index.py` runs from a clean checkout of the branch and reproduces `consumer_index.json` byte-identically.
2. The operator picks three definitions at random from the index and greps the codebase for them; every consumer the grep finds is in the index row (a missing consumer fails the test).
3. The calibration section reports six of six found by the method.
4. Every definite defect's `file:line` opens to code that shows the disagreement described.
5. `git status` on the branch shows changes only under `dev/audit/` and `dev/workpackages/reports/`.

## 7. Chat reply on completion

Report path, the per-family counts, the calibration result, the number of definite defects in surviving code, and any decision you need from the operator. Nothing else — the report is the deliverable.
