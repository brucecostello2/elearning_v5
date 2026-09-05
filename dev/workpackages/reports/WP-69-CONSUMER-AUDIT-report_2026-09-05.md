# WP-69 — CONSUMER AUDIT report

**Date:** 2026-09-05 · **Branch:** `wp-69-consumer-audit` (commit and HOLD; not pushed) · **Executor:** coding agent, node-01, one session · **Tier:** B (observable) · **Read-only audit:** no source file changed, nothing fixed, nothing deleted, no pipeline run, no GPU node touched, no test suite run (the index script needed no fixture).

## STATE AT SESSION END

**Done.** The index script, both index outputs and this report exist and are committed on the branch. All seven families (D1–D7) are indexed; D1–D4 were complete before any checking started (order §4 time-box met). Output is deterministic: two consecutive runs produced byte-identical `consumer_index.json` and `consumer_index.md` (sha256 prefixes `dfc9ed188e88d187f` / `8a604758c6b6760f6`).

**Mid-way through:** nothing.

**Ways the work package is now stale (premises checked against the machine, §0 rule 5):**
1. Order §2 D1 says *"alembic head (0054)"*. The tree's migration chain head is **0055** (`0055_wp_ivgs_12j_interview_and_vocabulary.py`, held with WP-IVGS-12j, undeployed). Production is at 0054 (board, 2026-08-30). The index replays the chain to **0055** as "head" and records, per table, which columns exist only after 0054 (`cols_only_after_0054` in the D1 rows) and, per enum, whether it exists at 0054. Nothing in the definite lists depends on a 0055-only column.
2. Order §3 step 1 says *"use `ts-morph` if present in the frontend toolchain"*. It is not (`package.json` has no `ts-morph`; `node_modules` has 352 entries, none is it). The TypeScript pass is a disciplined regex pass, as the order's fallback allows; its blind spots are listed under D7 gaps.
3. Order §4 *"The only files you create or change are under `dev/audit/` and the report"* conflicts with `dev/CLAUDE.md` §0 rule 5.2 (index the report on the board `dev/DEVELOPMENT-STATUS.md`) and rule 5.3 (banner the superseded premise in the order file). I followed the **order** (more specific, later, operator-written) and did **not** edit the board or the order file. Both are flagged here for the operator; see "Decisions needed".
4. Calibration item 2 says `gpu_registry.add_node_job` *"has no caller"*. Measured: it has **one test caller** (`ivgs-scheduler/tests/test_scheduler.py:293`) and zero production callers. Same class as item 3, not "no caller anywhere".

**Learned, not yet written anywhere else:** the system python on node-01 has neither SQLAlchemy nor Pydantic installed; the index is stdlib-only (`ast`, `re`, `yaml`) and therefore runs from a clean checkout without the images.

**Tree at close (§0 rule 5.5):**
- Committed on `wp-69-consumer-audit`: `dev/audit/build_consumer_index.py`, `dev/audit/consumer_index.json`, `dev/audit/consumer_index.md`, this report. One commit.
- **Held:** `git rev-list --count origin/main..HEAD` after `git fetch` = **10** (9 held WP-IVGS-12j commits that were already on `main` unpushed, plus this package's 1). The count-gated push block below states 10.
- Dirty and **not mine**: `dev/workpackages/WP-69-CONSUMER-AUDIT_order_2026-09-05.md` is untracked (the operator's order file). Not staged.
- Evidence in scratch: only the intermediate review dumps used to write this report; everything they contain is derivable by re-running the script. Declared lost by name: `scratchpad/review.txt`, `scratchpad/run1.json`, `scratchpad/run1.md` (the second-run comparison copies). Nothing else.

---

## 1. Calibration result — 6 of 6 found by the method

| # | Known defect (order §3 step 4) | Found by | Where in the index |
|---|---|---|---|
| 1 | preset writes actor clip `asset_type="talking_head"`, Stage-6 lookup reads `reference_clip` | D4 slot scan: the `asset_type` row lists, per member, every writer and reader with its slot mode. Reading that row: `talking_head` is written by `preset_service.py:219` (`write:asset_type`, in `apply_to_project`) and `reference_clip` is read by `pipeline_orchestrator_v2.py:2567` (`read:asset_type`, `params={"asset_type": "reference_clip"}` in `_fetch_reference_clip_id`). The pairing is the "by reading" step of §3 step 2; the row is the method's product. | `rows.D4` → `vocab:asset_type` |
| 2 | `gpu_registry.add_node_job` has no caller | D6 def/call analysis (every def in scheduler/utils/clients/services counted against every Name/Attribute reference in the repo) | `findings.D6` orphan: `GpuRegistry.add_node_job (ivgs-scheduler/gpu_registry.py:617)` — 1 test reference, 0 production |
| 3 | `scheduler.extend_reservation` called only from tests | same | `findings.D6` orphan: `GpuScheduler.extend_reservation (ivgs-scheduler/scheduler.py:501)` — 2 test references, 0 production |
| 4 | frontend never sends `library_kind` to `POST /projects/{id}/assets/upload` | D2 route↔client match: route `Form(...)` params vs every FormData `.append` in the matched frontend call sites | `findings.D2` orphan: `Form('library_kind')` never appended (also `library_name`, `scene_id`, `language_code`, `content_hash`, `generation_params_hash`, `metadata`) |
| 5 | `project_gate.signal_payload()` emits `gate_storyboard`/`gate_draft`; workflow declares `storyboard_approved`/`draft_approved` | D3 signal check: definition = `@workflow.signal(name=…)` constants resolved; consumers = every literal or f-string in a `signal`-named dict/kwarg slot; f-string patterns compared as regex | `findings.D3` definite: `projects.py:961` and `gate_service.py:607` build `gate_{}` (`{"signal": {"name": f"gate_{gate}", …}}`); no declared signal matches; plus 4 orphans: none of the four declared signals has a production emitter |
| 6a | `composition_manifest` writes no checkpoint row | D4 stage-body helper coverage matrix (helpers called from most of the 9 stage files per `docs/stage-numbering-map.md`) | `findings.D4`: `save_checkpoint()` called from 8 of 9 stage task files, absent from `stage4_manifest.py` (so are `update_job_status()`, `get_logger()`, `bind()`, `model_dump()`) |
| 6b | `tts_audio` uses `stage_index=4` colliding with the map | D4 numeric slot: every `stage_index=<int>` literal paired with its file's spec stage from `docs/stage-numbering-map.md` | `findings.D4` definite: `stage5_voiceover.py:694` and `:743` write `stage_index=4`; map says stage 5 |

**Honesty note on how they were found.** Items 4, 5, 6a and 6b surfaced on the first complete run without any tuning aimed at them. Items 1, 2/3 needed the extractor generalised after the first run *missed* them, exactly as the order anticipates ("if any is absent, fix the script"): the D4 read-mode heuristic did not treat `params={...}` dicts or `_list_*/_fetch_*` keyword arguments as reads (item 1's reader was classified as a writer), and D6's def/call analysis did not exist yet (items 2/3). While generalising, I looked at the shapes of three consumer sites to know what the extractor had to parse (`_fetch_reference_clip_id`, `signal_payload`, the `save_checkpoint` calls) — the shapes, not the answers; the findings above are produced by the committed script from those general rules, and the rules also produced everything else in this report.

---

## 2. Definite defects — surviving code (API, DB, scheduler, frontend, worker plumbing, scripts)

Every row: `family | definition (file:line) | consumer (file:line) | disagreement | failure scenario | future`. All `file:line` were opened and checked.

| # | family | definition | consumer | disagreement | failure scenario | future |
|---|---|---|---|---|---|---|
| S1 | D1 | `assets` table, `ivgs-api/migrations/versions/0001_initial_core.py:157` (head columns: `seaweedfs_path`, `generation_metadata`, no `status`, no `storage_path`, no `metadata`); DB enum `asset_type` (`0001_initial_core.py:38`) has no `animation` | `ivgs-workers/services/motion_graphics.py:598` (`INSERT INTO assets (… storage_path, file_size_bytes, metadata, status, …)`); `motion_graphics.py:267` and `:417` set `asset_type="animation"` | raw SQL names three columns the table does not have, and writes an enum value the DB enum lacks | Every motion-graphics asset registration raises `UndefinedColumn` (and, were the columns present, `invalid input value for enum asset_type: "animation"`). No motion-graphics asset row is ever persisted; the stage completes against an empty asset set. This is the identical class WP-60 Task 10 fixed in `orphan_cleanup.py` (its docstring at `:705`). | surviving (worker service; its only caller is the motion-graphics stage body) |
| S2 | D1 | `users` (`0001_initial_core.py:114`, columns `username`, `password_hash`, `role`, `is_active`, `last_login_at`, `created_at`, no `email`, no `updated_at`); `audit_log` (`0001_initial_core.py:380`, columns `action_type`, `resource_type`, `resource_id`, `after_payload`, `timestamp`) | `scripts/create_admin.py:54` (`WHERE email = %s`), `:62` (`INSERT INTO users (id, email, …, updated_at)`), `:71` (`INSERT INTO audit_log (id, user_id, action, entity_type, entity_id, after_state, client_ip, created_at)`) | script names columns that do not exist (7 of them across two tables) | `python scripts/create_admin.py` fails on its first statement with `UndefinedColumn: column "email" does not exist`. No admin can be bootstrapped by this script; it has been dead since 0001. | surviving (scripts) |
| S3 | D1 | `prompts` (`0001_initial_core.py:264`, columns `prompt_text`, `prompt_type`, `is_library_template`, … no `name`, `template`, `is_global`, `updated_at`); `fallback_policies` (`0014_fallback_policies.py:20`, columns `level_1_strategy`…`level_4_strategy`, no `l1_provider`, no `description`) | `scripts/seed_data.py:203` (`WHERE prompt_type = %s AND is_global = TRUE`), `:209` (INSERT prompts with `name, template, is_global, updated_at`), `:257` (INSERT fallback_policies with `l1_provider…l4_provider, description`) | script names 9 columns that do not exist | `python scripts/seed_data.py` aborts at the first prompt SELECT. The seed data the runbook may rely on cannot be loaded by this script. | surviving (scripts) |
| S4 | D2 | ivgs-api route table (`ivgs-api/app/api/v1/retention.py` serves `/retention/policies`, `/retention/policies/{id}`, `/retention/report` only) | `ivgs-frontend/src/app/admin/retention/page.tsx:117` — `api.post("/api/v1/retention/run")` | client calls a path no route serves | Admin → Retention → "Run cleanup" always returns 404; the success toast never shows; no cleanup is ever triggered from the UI. | surviving (frontend/API) |
| S5 | D2 | `WEBSOCKET /api/v1/ws/jobs/{job_id}/status` (`ivgs-api/app/api/v1/ws_logs.py:95`) | `ivgs-frontend/src/app/monitoring/pipeline/page.tsx:156` — `useWebSocket(`/api/v1/jobs/${selectedJobId}/status`)`; `useWebSocket.ts:130` concatenates the path verbatim onto `ws://host` | path differs by the `/ws` segment | The monitoring pipeline page's live-update socket never connects (HTTP 404 on upgrade); `connectionState` stays disconnected and the page shows only SWR polling data. Unverified: whether a reverse proxy outside the repo rewrites the path (no nginx/ingress config in the tree). | surviving (frontend) |
| S6 | D2 | `GET /api/v1/projects/{project_id}/assets` (`ivgs-api/app/api/v1/assets.py:51`) is the only method on that path; uploads are `POST …/assets/upload` (`assets.py:88`) | `ivgs-frontend/src/hooks/useAssets.ts:50` — `apiClient.post(`/api/v1/projects/${projectId}/assets`, formData)`; called from `app/projects/[id]/assets/page.tsx:119` | client POSTs to a GET-only path | Manual asset upload from the project Assets page always fails (405 Method Not Allowed); the page's upload handler never succeeds. | surviving (frontend) |
| S7 | D2 | `POST /api/v1/projects/{project_id}/transcripts/reorder` (`ivgs-api/app/api/v1/transcripts.py:153`, body `TranscriptReorderRequest`) | `ivgs-frontend/src/hooks/useTranscripts.ts:63` — `apiClient.put(…/transcripts/reorder, { order })` | method PUT vs route POST | Calling `reorderTranscripts` returns 405. **Latent today:** `reorderTranscripts` is exported by the hook but no component calls it (D7 orphan). | surviving (frontend) |
| S8 | D2 | `POST /api/v1/jobs/{job_id}/resume` (`ivgs-api/app/api/v1/checkpoints.py:224`) | `ivgs-frontend/src/hooks/useJobs.ts:67` — `apiClient.post(`/api/v1/projects/${projectId}/jobs/${jobId}/resume`)` | client path nests under `/projects/{id}`; route does not | Calling `resumeJob` returns 404. **Latent today:** `resumeJob` is exported but never called from any component (D7 orphan). | surviving (frontend) |
| S9 | D3 | Temporal workflow signals `storyboard_approved`, `storyboard_rejected`, `draft_approved`, `cancel_job` (`ivgs-workers/temporal_pipeline/workflow.py:181,186,197,201`) | `ivgs-api/app/api/v1/projects.py:961` and `ivgs-api/app/services/gate_service.py:607` — `{"signal": {"name": f"gate_{gate}", "payload": row.signal_payload()}}` | emitter builds `gate_storyboard` / `gate_draft`; workflow has no handler of either name; none of the four declared names has any production emitter | At M3.3 cutover the gate decision is delivered under a name the workflow does not handle; `workflow.wait_condition` never returns and the job hangs at the gate forever. Today the same object rides a Celery dispatch, so the defect is latent until Temporal cutover — but the shape was "defined now so it does not move later" (`project_gate.py:121`), and it already disagrees. | surviving (API + temporal plumbing) |
| S10 | D4 | vocabulary `asset_type` (DB enum `0001_initial_core.py:38`; ORM `shared/models/asset.py:59`) | writer `ivgs-api/app/services/preset_service.py:219` (`asset_type="talking_head"` for the actor clip, in `apply_to_project`); reader `ivgs-workers/tasks/pipeline_orchestrator_v2.py:2567` (`params={"asset_type": "reference_clip", "limit": 1}` in `_fetch_reference_clip_id`, feeding `reference_clip_asset_id` at `:1506`) | the same object is written under one member and looked up under another | Applying a preset with an actor clip never produces a `reference_clip` row; Stage 6 receives `reference_clip_asset_id=None` and logs `stage6_skipped_no_reference_clip` (`talking_head_task.py:437`). Talking-head is silently skipped for every preset-driven project. | surviving (API service + orchestrator plumbing) |
| S11 | D7 | `DLQMessageResponse` (`ivgs-api/app/schemas/dlq.py`) emits `failure_category`, `exception_message`, `retry_count_exhausted` | TS `DLQMessage` (`ivgs-frontend/src/types/monitoring.ts:157`) declares `category`, `error_message`, `retry_count`, `entered_dlq_at`; rendered at `components/monitoring/DLQTable.tsx:162,204,208,214` | four UI fields the API never sends | The DLQ table renders an empty category badge and an empty error message for every row, forever; the expand-to-see-error affordance shows nothing. | surviving (frontend) |
| S12 | D7 | `UserResponse` (`ivgs-api/app/schemas/user.py`) emits `last_login_at` | TS `User.last_login` (`types/monitoring.ts:16`), rendered `app/admin/users/page.tsx:565-566` | field name differs | Admin → Users shows every user as never logged in. | surviving (frontend) |
| S13 | D7 | `SceneResponse` (`ivgs-api/app/schemas/storyboard.py`) — 23 fields, no `status`, no `error_message`, no `generation_prompt_id`; route `GET /projects/{id}/scenes` returns `List[SceneResponse]` | TS `Scene` (`types/storyboard.ts:104`) declares all three as required; `app/projects/[id]/storyboard/page.tsx:209,255` filters and counts by `s.status`; `app/projects/[id]/page.tsx:112` filters `s.status === "gated"` | UI reads a field the API never sends | The storyboard status filter matches zero scenes for every status, the per-status counters always read 0, and the project page's gated-scene list is always empty. | surviving (frontend) |

**Count: 13 definite defects in surviving code** (S7 and S8 are latent: the broken helpers have no caller).

## 3. Definite defects — replaced code (stage bodies / design path, being rebuilt under AD-11/AD-12)

| # | family | definition | consumer | disagreement | failure scenario | future |
|---|---|---|---|---|---|---|
| R1 | D4 | `docs/stage-numbering-map.md:14` — `stage5_voiceover.py` is spec stage 5, `talking_head_task.py` 6, `stage7_prototype_draft.py` 7, `stage8_final_render.py` 8; stage 4 is the composition manifest | `stage5_voiceover.py:694,743` write `stage_index=4`; `talking_head_task.py:959` writes 5; `stage7_prototype_draft.py:464,578` write 6; `stage8_final_render.py:706` writes 7 | every stage from voiceover onward writes the index of the stage before it; index 4 is written under two identities and index 3 under four | Checkpoint rows for `tts_audio` carry the composition manifest's index; anything ordering or resuming by `stage_index` (the checkpoint API's resume path, `CheckpointService`'s stage order — already an open register entry) resolves to the wrong stage. | replaced (stage bodies) |
| R2 | D4 | the nine stage task files per `docs/stage-numbering-map.md`; `save_checkpoint()` (`ivgs-workers/utils/error_handler.py`) | `stage4_manifest.py` — the only stage file that never calls `save_checkpoint()` (also never `update_job_status()`) | one stage in nine writes no checkpoint | Resume-from-checkpoint has a hole at `composition_manifest`: no row is ever written for it, so a job that fails after the manifest resumes from the media stage and re-runs it. | replaced (stage body) |
| R3 | D2 | `SceneUpdate` (`ivgs-api/app/schemas/storyboard.py:250`) — no `audio_asset_id`; `storyboard_scenes` has no such column | `ivgs-workers/tasks/stage5_voiceover.py:277` — `client.patch(…/scenes/{scene_id}, json={"audio_asset_id": asset_id})` | worker sends a key the request model lacks | Pydantic drops the key silently and returns 200; the "update scene record with generated audio asset_id" step (`:270` docstring) has never persisted anything. Nothing downstream can find a scene's audio by the scene row. | replaced (stage body; API side surviving but only if the field is wanted) |

---

## 4. Suspect (disagreement without a firm failure scenario, or semantic mismatch not certain)

Mechanical suspect counts per family are in the index header (D1 59, D2 31, D3 34, D4 212, D5 14, D6 24, D7 4). The ones worth a human's minute, verified by reading:

| family | definition | consumer | disagreement | why suspect, not definite |
|---|---|---|---|---|
| D1 | DB enum `asset_type` (7 members) | `shared/models/enums.py:186` `AssetType` lacks `reference_clip`; `ivgs-frontend/src/types/api.ts:36` `AssetType` lacks `document`, `final_render`, `reference_clip`; `ivgs-api/app/services/asset_service.py:26,42` `ASSET_TYPE_PATHS`/`MAX_FILE_SIZES` lack `reference_clip` | four definitions of one vocabulary, none complete | The ORM column lists members explicitly (`asset.py:59`) so writes succeed; the Python enum simply cannot name `reference_clip` and the TS union cannot type it. The `asset_service` dicts keyed by type have no `reference_clip` entry — an upload of that type takes whatever the `.get()` default is. Needs a reader to say whether that path is reachable. |
| D1 | DB enum `backup_type` has `physical_base_backup` (added by migration) | `ivgs-api/app/models/backup_record.py:32` PG_ENUM member list lacks it; TS `BackupType` (`types/monitoring.ts:404`) lacks it | model/type enum lists stale | SQLAlchemy's PG ENUM does not validate strings on bind by default, so the write goes through; the UI will not type the value. |
| D1 | `job_status` DB enum (`pending/running/success/failed`) | `shared/models/enums.py:231` and TS `JobStatus` (`types/api.ts:34`) carry both cases (`pending`… and `PENDING`, `IN_PROGRESS`, `QUEUED`…); worker/server `JobStatus` enums (`servers/common/jobs.py:33`, `servers/cogvideox/server.py:53`) are a different vocabulary with the same name | one name, at least three vocabularies | The TS union having both cases is a symptom of the API and workers disagreeing about case; which side the UI compares against per page is not mechanically resolvable. |
| D1 | `storage_tier` DB enum (`hot/warm/cold/archived/deleted`) | TS `StorageTier` in `types/api.ts:53` is `hot/warm/cold/archive` | `archive` vs `archived` | the retention admin page writes `archived` (`retention/page.tsx:54`) so the live path is right; the `api.ts` union is dead-wrong but nothing verified renders from it. |
| D1 | nullable: `projects.created_by` nullable in migration | `ivgs-api/app/models/project.py:53` declares `nullable=False` (also `asset_quality_scores.job_id`, `prompt_tags.created_at`, `gpu_nodes.registered_at`, `gpu_reservations.reserved_at`) | model stricter than DB | harmless until a row with NULL exists; then the ORM returns `None` into a `Mapped[uuid]` and typing lies. |
| D1 | `from_attributes` response models with fields the ORM lacks: `GpuNodeResponse` (13 fields), `ProjectResponse` (6), `LanguageVariantResponse` (4), `ModelOut` (2) | e.g. `ivgs-api/app/schemas/project.py:183-201` | field not on the ORM class | all have defaults, so `model_validate(orm_row)` silently emits the default; whether the services fill them by hand before validating was not traced. |
| D2 | `GET /api/v1/projects` (`projects.py:119`) declares no `expand` query param | `ivgs-frontend/src/hooks/usePipeline.ts:60` sends `?expand=…` | ignored query param | the hook's intent is unknowable statically; the API ignores it. |
| D6 | `POST /generate` on the CogVideoX engine server, `GenerateRequest.prompt` required (`ivgs-workers/servers/cogvideox/server.py:42`) | `ivgs-workers/tasks/talking_head_task.py:367` posts to `…/generate` without `prompt` | route-tail match | probably a **matcher collision**: several engine servers expose `/generate`, and the talking-head client targets LatentSync/SadTalker, not CogVideoX. Listed so the operator sees the class; not counted. |
| D6 | scheduler `FleetResponse` (`alive_nodes`, `available_vram_mb`, `draining_nodes`, …) | `ivgs-workers/utils/gpu_utils.py:85`, `periodic_tasks.py:995`, `pipeline_orchestrator.py:529,714` read `node_id`, `is_alive`, `is_draining`, `loaded_models`, `online_nodes`, `status`, `gpu_index` after `GET /fleet` | keys not top-level in the response model | the keys are plausibly inside the `nodes[]` element model; the reader-key scan cannot tell nesting apart. |
| D5 | `SCHEDULER_REDIS_URL` | `ivgs-scheduler/main.py:110` default `redis://localhost:6379/3`; `shared/config.py:29` default `…/1` and its comment says "same default the scheduler itself ships" | code defaults differ; the comment is wrong | compose sets the key explicitly on node-01 (`docker-compose.node01.yml:332,411,490,577`, all db 1), so the divergence only bites a bare-metal run. |
| D5 | `IVGS_GPU_SCHEDULER_URL` | API default `''` (`scheduler_fleet.py:74`), workers default `http://node-01:8001`, node-02/03 compose set `:8002` | three defaults, two ports | compose declares it everywhere it matters; suspect because the port disagreement (8001 vs 8002) between node-01's compose and the other nodes' compose was not resolved by reading. |
| D5 | `ivgs-api/config/retry_policies.yaml:15-33` `on_exhaustion: fallback_then_dlq`, `fallback_chain_then_dlq`, `kokoro_fallback_then_dlq`, `sadtalker_fallback_then_dlq` | `ExhaustionAction` enum (`ivgs-workers/services/retry_engine.py:58`) defines `dlq`, `fallback_and_dlq`, `kokoro_fallback_and_dlq`, `sadtalker_fallback_and_dlq` | YAML values are not enum members | the only reader of that YAML (`shared/config_loader.py:51`) returns `max_retries` only; nothing reads `on_exhaustion` from YAML, so this is dead config that *looks* authoritative. Orphan-class. |
| D4 | Celery queues declared by `Queue(...)` in `ivgs-workers/celery_app.py` | compose `--queues=` lists name `cleanup`, `notifications` (`docker-compose.node01.yml:514`), `ffmpeg`, `utility`, `image_generation_fallback`, `llm_inference_fallback` (`node05.yml:130,163`), `composition_overflow`, `ffmpeg_overflow`, `final_composition`, `overflow`, `remotion` (`node06.yml:102,134`) | workers listen on queues nothing routes to | harmless (idle consumers) unless something is *expected* to arrive there; node-05/06 files are operator-managed. |
| D4 | `pipeline_stage`/`project_state` group: `pipeline_orchestrator_v2.py:1491-1524` reads `stage` ∈ {`composition_manifest`, `tts_audio`, `talking_head_render`, `prototype_draft`, `final_render`} | no production site writes those literals into a `stage` slot | readers without writers | the value likely arrives as `PipelineStage.X.value` through a variable the slot scan cannot follow; a reader should confirm the labels agree with `PipelineStage` (`ivgs-workers/models/task_result.py:32`), which the definitions-disagree check says they do. |
| D3 | `TranscriptRecord` dataclass (`temporal_pipeline/payloads.py:110`) vs `TranscriptResponse` (`schemas/transcript.py:13`) | dataclass has `original_text`; pydantic has `source_text`, `source_kind`, `original_asset_id`, … | payload/API twin drift | temporal pipeline is conformance-only until M3.3. |

## 5. Orphans

Full lists are in `consumer_index.json` → `findings.<family>` with `class == "orphan"` (D1 2, D2 160, D3 4, D4 168, D5 192, D6 104, D7 116). The ones with a claim on a work package:

- **D6 scheduler/registry methods with zero production callers** (definitions dead or test-only): `GpuRegistry.add_node_job` (**calibration 2**), `GpuRegistry.remove_node`, `GpuRegistry.undrain_node`, `GpuScheduler.extend_reservation` (**calibration 3**), `GpuScheduler.get_active_reservations`, `GpuScheduler.get_job_reservation`, `AdmissionController.get_job_state`/`update_job_state`, `CircuitBreaker.record_error`/`record_success`/`reset`/`get_all_states`, `LoadBalancer.select_weighted_random`/`get_node_weight_history`, `ModelConcurrencyManager.get_concurrent_count`/`get_model_fleet_distribution`, `PriorityQueueManager.get_queued_jobs`/`get_total_depth`/`remove_job`, all eight `SchedulerMetrics.increment_*/set_*` setters (the metrics they feed are never updated), `RedisClient.get_json`/`set_json` (`shared/redis_client.py`), `check_gpu_available` (`ivgs-workers/utils/gpu_utils.py:65`).
- **D6 Redis key patterns read but never written, or written but never read** (production code only): read-only `gpu:node:{}` (`admission_control.py:439`), `gpu:nodes:all` (`:542`), `sched:node_reservations:{}` (`gpu_registry.py:280`), `sched:reservation:{}` and `sched:reservations:index` (`project_deletion.py:543,553` — the deletion service checks a registry under keys the scheduler never writes under that pattern; **worth a look next to WP-59's deletion guarantee**), `job:{}:status` (`ws_logs.py:116`); write-only `ivgs:alerts` (`alerts.py:36`), `ivgs:media_tasks:{}` (`pipeline_orchestrator_v2.py:1977`).
- **D2 routes no frontend calls** — 107 of the API's routes (82 have a python client; 25 have none at all), and 48 Pydantic models with no route and no production reference. Listed in the index; not itemised here.
- **D2 upload form fields never sent by the frontend**: `library_kind` (**calibration 4**), `library_name`, `scene_id`, `language_code`, `content_hash`, `generation_params_hash`, `metadata` on `POST /projects/{id}/assets/upload`.
- **D3**: none of the four Temporal signals has a production emitter (see S9); every registered Celery task has at least one production producer.
- **D4 vocabulary members with no production consumer** — 168, mostly enum members defined for completeness (`ProjectState.DELETING` is written directly by the deletion service and is correctly absent from the transition table; the D4 orphan for it is expected).
- **D5 keys read with a silent default and declared in no tracked file** — 192 (most of `ivgs-workers/config.py`'s `IVGS_*` tunables, `JWT_ALGORITHM`, `IVGS_SERVICE_TOKEN`, `IVGS_MBCP_INGEST_TOKEN`, all `IVGS_*_TAG` image tags on node-04). **Caveat:** the gitignored node `.env` files were deliberately not read (§3 forbids printing `.env.node01`), so "declared nowhere" means "declared in no tracked file"; the operator can confirm against the real env files. Keys declared but never read: 0 flagged beyond compose-only interpolations.
- **D7 TS fields never read by any component** — 116 (dead type fields or fields read only via spread); plus the two exported-but-uncalled hook helpers `reorderTranscripts` and `resumeJob` (S7, S8).

---

## 6. Per-family coverage and known gaps of the method

Header of the index (built from commit `a7f238cb8d50853d2028ed8546a17e2b92b75865`, the last commit that touched the audited source; `source_tree_dirty: false`):

| Family | Definitions | Consumers | definite | suspect | orphan |
|---|---|---|---|---|---|
| D1 Database schema | 70 | 331 | 21 | 59 | 2 |
| D2 API contracts | 425 | 2205 | 33 | 31 | 160 |
| D3 Task and activity signatures | 99 | 506 | 2 | 34 | 4 |
| D4 Enumerations and name vocabularies | 119 | 6385 | 6 | 212 | 168 |
| D5 Configuration keys | 450 | 1475 | 0 | 14 | 192 |
| D6 Cross-service protocols | 128 | 233 | 1 | 24 | 104 |
| D7 Frontend ↔ API types | 109 | 797 | 8 | 4 | 116 |

The mechanical "definite" counts above are the script's; the human-classified lists in §2/§3 are smaller because (a) D1's 21 collapse to S1–S3 (one script statement = several column rows), (b) D2's 33 include 29 `client omits required` hits that are all in **tests** posting deliberately incomplete bodies (kept in the index, not defects), (c) D6's 1 is the matcher collision noted in §4.

**What the script cannot see (per family):**

- **D1.** Raw SQL column extraction handles INSERT column lists, UPDATE SET lists and single-table WHERE/SELECT lists; JOIN queries are indexed as table consumers but their columns are not checked. f-string SQL shows interpolations as `{}` and those names are unchecked. SQLAlchemy Core `select(Model.col)` is an ORM consumer (python catches attribute errors), not a raw-SQL consumer. Enums whose migration builds the member list from a variable are resolved for module-level lists/dicts/`", ".join(...)` patterns only (`model_engine`'s migration was not resolvable; its membership checks were skipped and it is so labelled in `gaps.D1`).
- **D2.** Frontend HTTP method is inferred from `apiClient|api|client.<verb>` on the same or previous three lines; URLs built in helpers are attributed to the literal's line with method assumed GET (each such row says so). Request-body key checks run only for inline object literals; bodies built in variables are unchecked. `response_model` expressions are matched by token, not evaluated.
- **D3.** Producers with dynamic task names (variables, `STAGE_TASK_MAP[...]`, f-strings) are listed as suspect, not arity-checked; `.delay(*args, **kw)` forwarding is marked `**`. Default task names are derived as `<module>.<func>` relative to the package root — every registered task in this tree names itself explicitly, so this fallback was not exercised.
- **D4.** Slot binding is by name: a literal is membership-checked only when it sits in a keyword argument, dict key, comparison, `in`, `match` or assignment whose name is a slot owned by a vocabulary (DB column names typed by the enum; pydantic/dataclass/TS fields typed with the enum; snake_case of the enum class). Positional literals are indexed as consumers but not checked. Generic slot names (`name`, `type`, `status`, `id`, `model`, `role`, …) are excluded from ownership to keep noise down, so vocabularies whose only slot is generic get no undeclared-literal check. Values reaching a slot through a variable, `getattr`, or an f-string are invisible. TypeScript is regex per line: multi-line object literals and template-built values are missed; type-guard helpers are invisible.
- **D5.** Node `.env` files were not read (see §5). Worker config helpers are matched by name (`_env`, `_get_env`, `_env_int`, …). BaseSettings fields are read as upper-cased field names; a pydantic `env_prefix` is not applied.
- **D6.** Def/call orphan analysis counts any Name/Attribute reference by bare name, so a method sharing its name with a common attribute (`get`, `run`, `close`) is never reported — the orphan list is an under-count. Engine-server clients are matched by URL tail only where the tail is a literal, and identical tails on different servers collide (see the `GenerateRequest` suspect). SeaweedFS path conventions are **not indexed**: no single definition site anchors them.
- **D7.** `ts-morph` is not in the toolchain; interfaces are parsed by regex (generics, mapped types, intersections approximated). Field-usage counts are bare-name matches across `src/`, so common field names are never reported dead. TS↔Pydantic links exist where the frontend call's generic type and the route's `response_model` both name an indexed type; the rest are name-based and marked `name match only` in the finding note.

**Exit-test notes for the operator (order §6).** (1) Reproduction: `python3 dev/audit/build_consumer_index.py` from a clean checkout of the branch; the stamp is the last commit touching the audited source dirs, so the audit commit does not change the bytes. Two consecutive runs here were byte-identical. (2) Grep test: rows list every consumer the extractors found; a grep will also find prose mentions in comments and docstrings, which the index deliberately excludes (docstrings are skipped in D1; comment lines in D2/D4 TS scanning). (5) `git status` on the branch shows only `dev/audit/` and the report changed; the untracked order file is the operator's.

---

## 7. Recommended one-line fixes (NOT applied)

Diffs I would apply, for the operator to turn into packages. Nothing below was written to the tree.

```diff
# S4 — ivgs-frontend/src/app/admin/retention/page.tsx:117  (no /retention/run route exists; the
#      nearest server-side trigger is the Celery beat task; a route must be added or the button removed)
-      await api.post("/api/v1/retention/run");
+      await api.post("/api/v1/retention/run"); // NO ROUTE — needs a package: add POST /retention/run or drop the button

# S5 — ivgs-frontend/src/app/monitoring/pipeline/page.tsx:156
-    selectedJobId ? `/api/v1/jobs/${selectedJobId}/status` : null
+    selectedJobId ? `/api/v1/ws/jobs/${selectedJobId}/status` : null

# S6 — ivgs-frontend/src/hooks/useAssets.ts:50
-      `/api/v1/projects/${projectId}/assets`,
+      `/api/v1/projects/${projectId}/assets/upload`,

# S7 — ivgs-frontend/src/hooks/useTranscripts.ts:62
-    await apiClient.put(
+    await apiClient.post(

# S8 — ivgs-frontend/src/hooks/useJobs.ts:67
-      `/api/v1/projects/${projectId}/jobs/${jobId}/resume`
+      `/api/v1/jobs/${jobId}/resume`

# S9 — ivgs-api/app/services/gate_service.py:607 and ivgs-api/app/api/v1/projects.py:961
#      (decision-dependent: the workflow declares <gate>_approved / storyboard_rejected; the emitter
#       must map decision -> declared name rather than build gate_<gate>)
-                        "name": f"gate_{gate}",
+                        "name": f"{gate}_{'approved' if row.decision == 'approve' else 'rejected'}",  # verify decision vocabulary first

# S10 — ivgs-api/app/services/preset_service.py:219  (or change the reader; the DB enum has both members)
-            asset_type="talking_head",
+            asset_type="reference_clip",

# S12 — ivgs-frontend/src/types/monitoring.ts:16 (User)
-  last_login: string | null;
+  last_login_at: string | null;   # and app/admin/users/page.tsx:565-566

# S11 — ivgs-frontend/src/types/monitoring.ts:157 (DLQMessage): rename category->failure_category,
#       error_message->exception_message, retry_count->retry_count_exhausted; drop entered_dlq_at;
#       then DLQTable.tsx:162,204,208,214.  Multi-line; not a one-liner.

# S1 — ivgs-workers/services/motion_graphics.py:598 (three column renames + the enum value; not a one-liner):
#       storage_path->seaweedfs_path, metadata->generation_metadata, drop status, and asset_type 'animation'
#       must become a DB-enum member ('video' today, or ALTER TYPE asset_type ADD VALUE 'animation').

# S2/S3 — scripts/create_admin.py and scripts/seed_data.py: rewrite against the 0001 column names
#       (users.username, audit_log.action_type/resource_type/resource_id/after_payload/timestamp;
#        prompts.prompt_text/prompt_type; fallback_policies.level_N_strategy). Not one-liners.

# R1 — ivgs-workers/tasks/stage5_voiceover.py:694,743   stage_index=4 -> 5 ; talking_head_task.py:959 5 -> 6 ;
#       stage7_prototype_draft.py:464,578 6 -> 7 ; stage8_final_render.py:706 7 -> 8   (frozen bodies: §3 — wrapper, not edit)
```

---

## Decisions needed from the operator

1. **Board and order-file edits.** Order §4 forbids touching anything outside `dev/audit/` and the report; `dev/CLAUDE.md` §0 rules 5.2/5.3 require a board row and a banner on the stale premise ("alembic head (0054)"). I followed the order. Say whether the board row should be added in a follow-up commit.
2. **Which surviving defects become packages.** My ordering by blast radius: S10 (talking-head silently skipped for presets), S1 (motion-graphics assets never persisted), S13/S11/S12 (three monitoring/storyboard pages rendering blanks), S5/S6/S4 (three UI actions that always fail), S9 (M3.3 blocker, latent), S2/S3 (scripts), S7/S8 (latent, unused helpers).
3. **`sched:reservation:{}` / `sched:reservations:index` read by the deletion service under a pattern the scheduler never writes** (D6 orphan) — worth a look before the next deletion-guarantee claim.

## Push block (operator runs; Claude never pushes)

```bash
# node-01 only
( cd /opt/ivgs && git fetch origin && n=$(git rev-list --count origin/main..wp-69-consumer-audit) && if [ "$n" -eq 10 ]; then git push origin wp-69-consumer-audit; else echo "held count is $n, expected 10 - refusing"; fi )
```
