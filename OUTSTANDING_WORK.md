# IVGS v5 — Outstanding Work (Single Source of Truth)

| | |
|---|---|
| **Document version** | v3.0 — 2026-06-06 (consolidated) |
| **Authoritative as of** | `feat/phase-h0-make-main-honest` @ `eaddebb` (Stages 1–5 green end-to-end; Stage 6 = build-required) |
| **Repository / branch** | `brucecostello2/elearning_v5` on `feat/phase-h0-make-main-honest` |
| **Supersedes / merges** | v2.1 (2026-05-30, `main` @ `31f61e8`, with appendix updates through 2026-06-03) **and** `OUTSTANDING_WORK_Addendum_A_2026-06-05.md` (the 06-04/05 arc). Both are folded in here; Addendum A's `A#` items are assigned final `P#` numbers (A1/A2/A4 closed by later work; A3→P1.6, A5→P2.26, A6→P2.27, A7→P3.7). |
| **Live stack (deployed)** | API **`ivgs-api:v5.2.3-h0`** (node-01); workers **`ivgs-workers:v5.4.7-h0`** (node-01 + node-04 confirmed; node-02/03 may trail at `v5.4.4-h0` — no functional impact, they run no TTS). Engines on node-04: `comfyui-v5.2.7-h0` (FLUX), vLLM `mistral-24b`, `coqui`/`kokoro`/`whisperx` `*-v5.2.7-h0`. node-02 vLLM `llama-3.3-70b` (FP8). node-03 CogVideoX (`cogvideox-pilot-1`). |
| **Purpose** | Single ledger of every known outstanding item. Each session updates this file before close. Items carry priority, source, scope, and a concrete carry-forward action. |

## Operator policy on tech debt

> "our general MO should be that when there is a bug we should fix, not park for some point in the future, we need to be clean as we go." (Phase 14 Stream B, 2026-05-29)

Nothing is "deferred" without being recorded here. New deferrals require an entry. Closures require evidence (commit SHA, image tag, or transcript pointer).

## Priority definitions

- **P0 — Blocking.** System broken or unsafe; address before any other work.
- **P1 — High.** Blocks dev velocity, hides regressions, or required for the next feature increment.
- **P2 — Medium.** Real defect or hygiene work; will compound if deferred.
- **P3 — Low.** Cosmetic, documentation, or strategic multi-session work.

## Snapshot

| Priority | Count | Headline items |
|---|---|---|
| **P0** | 0 | — (the A1 image-gen regression is **closed**; see Items-closed) |
| **P1** | 5 | Defect #4 prompt ENUM (P1.1); prompt-mgmt browser smoke (P1.2); GPU acceptance bullets (P1.3); AD-02 governance/SPOF recording (P1.6); pre-prod secret-leak + credential rotation (P1.7) |
| **P2** | ~28 | test-dir unification; `[object Object]` banner; `/nodes` status stub; CI scaffolding; RUNBOOK.md; v1→v2 orchestrator cleanup (P2.26); 4xx cluster (P2.27); ORCH-5 `projects.state` mapping (P2.28); Blackwell GPU monitoring + heartbeat (P2.29); manifest regenerate/reset (P2.30); animation asset-type (P2.31); audio duration not persisted (P2.32); non-unique audio path (P2.33); Stage-6 upload-URL pre-check (P2.34); rollback snapshot/restore unwired (P2.35); + carried hygiene |
| **P3** | ~13 | UPPERCASE dead code; empty seaweedfs volumes; **Phase H** multi-node (nodes 02/03/04 up; 05/06 + GPU-service validation remain); endpoint test coverage; manifest_version NULL; render_jobs `updated_at`; in-code Coqui default; audio-validator GUID; extensible-WAV readers; 06-04/05 hygiene (P3.7); comprehensive DR (strategic) |

## Pipeline status (2026-06-06)

| Stage | State |
|---|---|
| 1 transcript_refinement | ✅ proven (Stage 2/2B, API-triggered, cross-node) |
| 2 storyboard_generation | ✅ proven; scenes persisted; user-gate working |
| 3 media (image/video/animation) | ✅ proven e2e; scene-linked; regression closed |
| 4 composition_manifest | ✅ proven e2e; server-side build, locked manifest |
| 5 tts_audio (voiceover) | ✅ proven e2e; 6 scene-linked 48 kHz/24-bit assets |
| 6 talking_head_render | ⛔ **BUILD REQUIRED** — LatentSync/SadTalker engine images do not exist (see Stage-6 section) |
| 7 prototype_draft | ⏳ unbuilt/untested |
| 8 final_render | ⏳ unbuilt/untested |

The orchestrator auto-advances correctly and currently parks at `talking_head_render` (correct terminus — the engines aren't deployed).

---

# P0 — Blocking

*None.* (The 06-04/05 image-generation regression, formerly A1 [P0], is closed — see Items-closed.)

---

# P1 — High Priority

## P1.1 — Defect #4: `Prompt.prompt_type` ENUM-as-String
**Status:** OPEN (latent — prompt library empty). Will 500 on first INSERT with `DatatypeMismatchError`; architecturally identical to the fixed Defect #3 (`User.role`). Blocks P1.2.
**Scope/action:** `app/models/prompt.py:40–43` — swap `String(32)` for `PG_ENUM` mirroring migration 0001's 10 values; the `.cast(String)` workarounds in `prompt_service.py:61,77` become dead. Build, CLI-verify an INSERT. ~45–60 min.

## P1.2 — Phase D.11: Prompt-management 9-step browser smoke
**Status:** OPEN; code deployed in v5.1.8, never functionally smoke-tested. **Hard-blocked by P1.1.**
**Scope/action:** seed 10 system-tier prompts → list → filter → detail → project-tier override → effective resolution → edit → delete → fallback. Run only after Defect #4 deploys clean. ~30–45 min once unblocked.

## P1.3 — Spec v1.1 §9: GPU Fleet acceptance bullets (~18 of 24 deferred)
**Status:** PARTIAL — ~6/24 walked via browser smoke (Session 9); ~18 edge cases unverified (range validation, 30-day bound, MAX_HISTORY_POINTS=5000 → 413, multi-node JOIN, sort stability, auth gate 403-vs-401, `power_tdp_w`, chart/legend variants, focus re-fetch, 4xx-no-retry, empty-vs-undefined). No longer hard-blocked (test infra restored via PR #48).
**Scope/action:** write `TestGpuUtilizationHistory` covering the deferred bullets. 3–5 h.

## P1.6 — Record AD-02 node-specialization deviation; document SPOF failover; long-context decision *(was Addendum A3)*
**Status:** OPEN (governance/recording). AD-02 is **implemented + verified** (Items-closed), but the deviation and two decisions aren't captured.
**Scope/action:** (a) mark **gap N23-4 (LLM-vs-video card contention) RESOLVED** by workload separation; (b) document per-stage manual-failover for the new SPOFs (node-02 = sole LLM, node-03 = sole video engine) per AD-02.11; (c) **open decision (AD-02.12 #1):** node-02 vLLM runs `--max-model-len 32768` (below the 128 K aspiration), no explicit `--kv-cache-dtype fp8` — interim pending KV-headroom validation; record + schedule. Source: `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md`.

## P1.7 — Pre-production security: `.env.node01` secret leak + credential rotation
**Status:** OPEN — recurring across appendices; genuinely high (security).
**Scope/action:** `.env.node01` is **git-tracked** (secret leak) and carries a stale `IVGS_WORKERS_TAG` — `git rm --cached`, rotate, consider history purge. Rotate Postgres/Redis shared credentials (VLAN-reachable post-rebind; Redis has no auth). Operator-driven; security-sensitive.

---

# P2 — Medium Priority

## P2.1 — Defect #10: Test directory scope unification
**Status:** OPEN (spec authored: `Defect_10_Test_Directory_Scope_Unification.md`). Defect #8 restored only `ivgs-api/tests/`; `tests/` (9), `ivgs-workers/tests/` (16), `ivgs-scheduler/tests/` (4) remain unrunnable; `conftest.py` collision blocks a unified `testpaths`.
**Scope/action:** catalog the 29 files; resolve the collision (`importmode=importlib`); decide keep/drop/migrate per dir; wire testcontainers+Alembic. 4–8 h.

## P2.3 — Defect #5: "[object Object]" validation banner
**Status:** OPEN. Frontend error-handler doesn't string-coerce FastAPI's structured detail envelope (User Mgmt create/edit; likely DLQ replay, Quality approve/reject, Storage Quota). Extract `detail[0].msg`. 1–2 h. (Pairs with P2.7.)

## P2.4 — Defect #9: `/api/v1/nodes` stub hardcodes `status="online"`
**Status:** OPEN. `nodes.py:82` returns "online" unconditionally → "6 online" when only node-01 runs the stack. Interim ICMP/DNS ping (~1 h) or full fix at Phase 8. Don't add `test_nodes.py` until Phase 8 (would freeze the lie).

## P2.5 — Stream A test bug: `test_fleet_counts_nodes_in_all_states`
**Status:** OPEN. `test_service_gpu.py` references `online_count`/`offline_count`/`draining_count`; model exposes `*_nodes`. Inspect both occurrence sites, fix with context. 30 min.

## P2.6 — Phase F.1: Migrate ad-hoc `fetch()` to centralized api-client
**Status:** OPEN. 16 sites in 7 files + GPU-history call → `src/lib/api-client.ts`; add pre-commit hook blocking unprefixed `access_token` reads. Full session.

## P2.7 — Phase F.2: Backend UUID path-param validation (422 not 500)
**Status:** OPEN. Class-level UUID validation (dependency or path converter); architectural decision on scope + error envelope. Pair with P2.3.

## P2.8 — Phase F.3: Old GHCR image cleanup
**Status:** OPEN. 14+ stale tags each for ivgs-api/ivgs-frontend (more now). Author retention policy (keep last N + session-close-tagged) → prune.

## P2.10 — Phase F.5: bcrypt/passlib version warning
**Status:** OPEN. `(trapped) error reading bcrypt version` at fastapi startup. Pin compatible passlib+bcrypt in `requirements.txt`. Schedule with next backend dep update.

## P2.11 — Phase F.6: `IVGS_SCHEDULER_TAG=latest` — pin or document
**Status:** OPEN. §19.5 no-`:latest` violation. Confirmed `:v5.1.0` == `:latest` (same image ID), so pinning `=v5.1.0` is a **zero-behavior-change close** whenever desired.

## P2.13 — Phase F.11 / G: CI scaffolding (Actions + Playwright + pytest)
**Status:** OPEN (unblocked by PR #48). (a) Playwright smoke for the 8-page + 9-step walks; (b) `build-images.yml` (lint/tsc/build/pytest on push; build+push on `v5.*` tag; Playwright on CI compose); (c) PR template (stale-base + tsc + migration-roundtrip + overlay-rule). Multi-session.

## P2.15 — MP F.3: Restore `@sha256` digest pins on base images
**Status:** OPEN (compose half advanced — H.0 stripped fabricated GPU-node digests to tag-only). Identify base images that lost pins in `b933357` (FROM + `image:`), restore. (Also: SS19.5 — pin the live `v5.2.x/v5.4.x-h0` digests in compose.)

## P2.16 — MP F.4: Properly type `FlaggedAsset.metrics`
**Status:** OPEN. Currently `any`. Define a discriminated union (`{kind:"scalar",value} | {kind:"histogram",buckets}`).

## P2.17 — Phase E.1: Update `IVGS_INFRASTRUCTURE_REFERENCE`
**Status:** OPEN — still describes split-repo. Update to the monorepo at `/opt/ivgs` (`ivgs-api/`, `ivgs-frontend/`, `ivgs-infra/`, `ivgs-workers/`, `ivgs-scheduler/`).

## P2.18 — Phase E.2: Author RUNBOOK.md
**Status:** OPEN — more material than ever (S7–S9 lessons, Defect #8, Stream A/B, the cross-node bring-up, the consolidated-compose deploy pattern).
**Scope:** §1 session-start gate; §2 deploy invariants (build from monorepo root; `--env-file` + `-f` overlay rules; `--force-recreate --no-deps <svc>`; pre-recreate compose-resolution gate); §3 the image-drift lesson; §4 backup; §5 incident-response (`git clean -fd` recovery). High institutional value.

## P2.19 — `docker-compose.base.yml` vs `node01.yml` reconciliation
**Status:** OPEN — twice caused seaweedfs/redis/postgres recreate accidents. `base.yml` (seaweedfs 3.80, underscore volumes) vs `node01.yml` (3.71, hyphen volumes). Reconcile or delete `base.yml`.

## P2.20 — Forensic correction: Session 5 close
**Status:** OPEN. Record PR #45/#46/#47 merges; note the `deps.py` path typo.

## P2.21 — Tag taxonomy doc
**Status:** OPEN. Document `v*` (releases), `archive/*` (branch preservation — never delete without per-tag audit), `session-N-close` (bisect anchors). ~30 min; could fold into RUNBOOK.

## P2.22 — Pre-commit hook: SSL keys
**Status:** OPEN. Fail commits matching `*.key`/`*.crt`/`*.pem` under `configs/nginx/ssl/`. Pair with the IP-literal hook.

## P2.24 — `tests/` pytest collection fails on SQLite
**Status:** OPEN. `shared/database.py:31` passes `pool_size`/`max_overflow`/`pool_timeout` unconditionally; SQLite/NullPool → TypeError at `create_engine` → collection fails for all `tests/`. Make the factory dialect-aware. Pairs with P2.13/P2.1.

## P2.25 — `docker-compose.monitoring.yml` references non-existent external net `ivgs_default`
**Status:** OPEN (latent). A full-stack `up -d` across node01+override+monitoring fails; deploys use `--no-deps <svc>` so it never bites today. Real net is `ivgs-infra_ivgs-net`. Reconcile (attach to the real net or create/name it). ~1 h in a maintenance window. Pairs with P2.19.

## P2.26 — Phase-2 orchestrator cleanup (remaining half of v1→v2 = H.1) *(was Addendum A5)*
**Status:** OPEN — safe now that nothing calls v1's stage-orchestration (functional half closed in `9f692ab`).
**Scope:** (a) excise v1 `pipeline_orchestrator.py` stage-orchestration (`dispatch_pipeline`, `handle_stage_completion`, stub `STAGE_TASK_MAP`/`STAGE_TRANSITIONS`) **but keep v1's 6 periodic tasks** (heartbeat/DLQ/cleanup/retention/backup/GPU-metrics) that `beat_schedule` uses; (b) delete v2's **dead inline `build_composition_manifest`** (`pipeline_orchestrator_v2.py:~522`; the map dispatches `stage4_manifest`); (c) resolve the **dual talking-head file** (`talking_head_task.py` live; `stage6_talking_head.py` dead duplicate); (d) note the systemic `stageN_*.py` filename vs `stage(N-1)_*`/`*_task` registered-name off-by-one — `9f692ab` aligned the *map*, do **not** rename tasks; (e) also kill the dead worker-side `ManifestBuilder` (off-spec, posts to `/composition-manifests`); (f) `tasks/periodic_tasks.py` dormant duplicate — consolidate. Rebuild + verify both periodic tasks and the pipeline.

## P2.27 — Non-blocking 4xx cluster *(was Addendum A6)*
**Status:** OPEN — render proceeds through all of these; address as downstream stages need them.
**Scope:** `POST /jobs/{id}/checkpoints` → **405** (checkpointing disabled; worker calls wrong path); `POST /clip/score` → **404** (images get `quality_decision: flagged`, `clip_score: null`); `GET /assets?sha256=` → **404** (dedup absent → duplicate rows on re-fires; dedup also wouldn't backfill `scene_id`); `POST /quality-scores` → **404** (quality persistence absent). Re-enable dedup/quality when the quality/composition stages need them.

## P2.28 — ORCH-5: worker → `projects.state` mapping (+ tighten `approve_storyboard` guard)
**Status:** OPEN — confirmed reproducing. After a full run `projects.state` stays stale (e.g. `TRANSCRIPT_REFINEMENT`/`MEDIA_GENERATION`) even though the pipeline advanced; the dashboard view is misleading (render-job stage + dispatched tasks are the source of truth). The **deliberately lenient `approve_storyboard` guard** (`project_service.py`) accepts pre-`STORYBOARD_GENERATION` states and is empirically relied upon by the e2e.
**Scope/action:** update `projects.state` on each orchestrator transition (MEDIA → MANIFEST → AUDIO → TALKING_HEAD → …). **FIX-WHEN:** once state advances correctly, tighten the guard to require `STORYBOARD_GENERATION` per spec Table 4-3. *(= work-package follow-on #1.)*

## P2.29 — GPU monitoring + heartbeat registry (Blackwell)
**Status:** OPEN — two coupled gaps; dashboard GPU telemetry is **not trustworthy** (node liveness works via a separate check).
**Scope:** (a) **Exporter:** committed `utkuozdemir/nvidia_gpu_exporter:1.2.1` panics on Blackwell (`clocks_event_reasons_counters.sw_thermal_slowdown [us]` → invalid metric name) → CrashLoop on nodes 02/03/04 (node-02 only "looks OK" via an older dcgm container). Restrict `--query-gpu` to a safe field set, bump to a name-sanitizing tag, or move to dcgm on a Blackwell tag; update `node02/03/04` compose + commit. (b) **Heartbeat:** registry empty (`total_nodes:0` → `gpu_reservation_skipped`, tasks soft-continue; scheduler `:8002` → 503). Wire node GPU heartbeat registration so `total_nodes > 0`.

## P2.30 — No manifest regenerate/reset
**Status:** OPEN. `composition_manifests.job_id` is UNIQUE and there's no reset endpoint; once a manifest exists, re-running Stage 4 for that job can't regenerate (the driver reuses the existing `draft`/`locked`). Add a reset/regenerate path for re-runs after asset changes. *(= work-package follow-on #4.)*

## P2.31 — Animation stored as `asset_type="image"`
**Status:** OPEN. Interim relabel; the manifest groups animation as image. Give animation a distinct type for correct layer semantics. *(= follow-on #5.)*

## P2.32 — `assets.duration_seconds` not persisted on upload *(Stage-5 → 6/7)*
**Status:** OPEN. The voiceover task computes real per-scene durations (8.6 s … 57.7 s) and the column exists, but `POST …/assets/upload` accepts only `file/asset_type/scene_id/language_code` — so all audio rows are `duration_seconds = NULL`. Stage-6 lip-sync + Stage-7/8 timing want the **actual synthesized** duration.
**Scope/action:** add a `duration` form field (and optionally `sample_rate`/`bit_depth`) to `upload_asset` and send it, or probe the file server-side — else downstream must `ffprobe`. *(= follow-on #10.)*

## P2.33 — `seaweedfs_path` not unique per scene *(Stage-5; latent path-read trap)*
**Status:** OPEN. The server derives the audio path from project + language only (`/ivgs/audio/{project_id}/{lang}.wav`), so all same-language audio assets **share one path string** with distinct FIDs. (a) the worker's result reports a *different* path (`…/{scene_id}/{lang}.wav`) that doesn't match the DB; (b) anything fetching by **reconstructing the path** instead of `seaweedfs_fid`/`asset_id` would collide. Always retrieve by FID or by `scene_id` query.
**Scope/action:** include `scene_id` in the server path for uniqueness + debuggability; align the worker's reported path. *(= follow-on #11.)*

## P2.34 — Stage-6 `talking_head_task.py` upload-URL pre-check
**Status:** OPEN — pre-check before wiring Stage 6. The dead `stage6_talking_head.py:234` has the same wrong `/assets/upload` URL that bit Stage 5; confirm the **live** `talking_head_task.py` posts to `…/projects/{id}/assets/upload`. *(= follow-on #12; relates to P2.26(c).)*

## P2.35 — Rollback feature snapshot/restore unwired
**Status:** OPEN. The storage-path crash was fixed (`c3e8a1a`, repointed to `/mnt/ivgs-shared/rollback_points`), but `rollback_service.py` (~164/241/244) still references `/ivgs/ivgs-api/config` and `/ivgs/.env`, and `rollback_to` restarts containers — full §14.3 rollback needs host-level `deploy-node.sh` integration (the service runs in-container without host access). Decide: wire to the real layout, or remove. *(= follow-on #7.)*

---

# P3 — Low Priority

## P3.1 — `GpuNodeStatus` UPPERCASE half (dead code)
**Status:** OPEN. `types/api.ts` has both case variants; backend emits lowercase only. Delete UPPERCASE; `tsc --noEmit`.

## P3.2 — Empty underscore-named seaweedfs volumes
**Status:** OPEN (harmless). Four empty 4K volumes from an S5 mis-application. Verify no compose refs, then `docker volume rm`.

## P3.3 — Phase H: Multi-node expansion
**Status:** OPEN — substantially **advanced**: node-02 (LLM), node-03 (video), node-04 (image+TTS) are up and AD-02-specialized; cross-node pipeline proven (Stages 1–5). **Remaining:** nodes 05/06; full GPU-services validation per node; **H.5 task-layer remainder** (client base_urls done in `5d525a7`; H.0 repaired the broken task interfaces — `VLLMClient.chat`, `get_model_config`, stage wiring); definitive completion is per-node as services come online. Strategic, multi-session. (The v1→v2 cleanup half is now P2.26.)

## P3.4 — Endpoint test coverage (9 modules)
**Status:** OPEN (unblocked). No test files for `alerts`, `backup`(now covered by Stream B), `jobs`, `languages`, `manifests`, `nodes`, `quotas`, `rollback`, `ws_logs`. Priority: `jobs`/`rollback` (High), `alerts`/`manifests`/`quotas` (Med). `test_nodes.py` pairs with Phase 8.

## P3.5 — Rogue-branch attribution investigation
**Status:** OPEN (investigation only; branch force-deleted Session 9). 10 commits by `node01-ops <ops@ivgs>`. Check agent logs 2026-05-22/23, shell history for `git config user.email`, `/var/log/auth.log`. Operator-driven; blocks nothing.

## P3.6 — Cosmetic / UI polish
**Status:** OPEN. Banner auto-dismiss; action-message badge polish. ~5 min each.

## P3.7 — 06-04/05 session hygiene bundle *(was Addendum A7; (a) already closed)*
**Status:** OPEN — small, low-risk. (b) stale unused `.env.node01 IVGS_WORKERS_TAG` — remove (node-01 deploys read `.env`); (c) `.bak` cruft in `ivgs-workers/` (e.g. `celery_app.py.bak-…`) — delete; (d) GPU-node source-tree drift — keep `/opt/ivgs` trees in sync or document that source on GPU nodes is non-authoritative. *(A7(a) dirty `checksums.sha256` closed via `7569ed5`.)*

## P3.8 — `composition_manifests.manifest_version` left NULL
**Status:** OPEN. The API `generate` doesn't populate it — cosmetic, but should be set. *(= follow-on #2.)*

## P3.9 — `render_jobs` has no `updated_at` column
**Status:** OPEN. Minor schema inconsistency (hit when clearing a stale `failed` status). Add for audit parity if desired. *(= follow-on #6.)*

## P3.10 — In-code Coqui default still wrong *(guarded)*
**Status:** OPEN. `stage5_voiceover.py:~516` hardcodes `http://node-04:5002` as the Coqui fallback; harmless now that the env URLs override it (Stage-5 fix #5), but correct on the next workers build so it isn't a latent trap. *(= follow-on #13.)*

## P3.11 — Audio validator doesn't parse the `WAVE_FORMAT_EXTENSIBLE` SubFormat GUID
**Status:** OPEN. `audio_validator.py::_parse_wav_header` reads only the first 16 `fmt ` bytes, so for `wFormatTag=0xFFFE` (65534) it trusts the container without confirming the embedded SubFormat. Fine for current XTTS output (proven PCM, decoded + scored). A rigorous validator reads the GUID. Context: `39ee28d` added 65534 to the accepted set `(1,3,65534)`. *(= follow-on #8.)*

## P3.12 — Downstream audio readers must tolerate extensible WAV *(Stage-5 → 6/7)*
**Status:** OPEN. XTTS emits `WAVE_FORMAT_EXTENSIBLE` (0xFFFE), now accepted as valid Stage-5 output. Any later stage opening it with Python stdlib `wave` (raises on 0xFFFE) rather than ffmpeg/soundfile/librosa will fail. Verify the talking-head/compositor readers use a tolerant decoder, or transcode to `fmt=1` at the Stage-5 upload boundary. *(= follow-on #9.)*

## P3.13 — Clients swallow real exceptions to `""`
**Status:** OPEN (observability). `flux_client`/cogvideox/coqui clients catch errors and return `""`, masking root causes (the Stage-5 10 s Coqui timeout was hidden this way). Surface the real error.

## P3.14 — Comprehensive disaster recovery *(strategic, deferred)*
**Status:** DEFERRED (after full fleet + AD-01). Design DR using non-node location(s) — local NAS + offsite — covering ALL recoverable state (git repo, `/mnt/models` weights, Postgres, SeaweedFS/Redis as appropriate, per-node compose + `.env`). Closes the gap where `/mnt/ivgs-shared` backups live on node-01's disk and don't survive a node-01 failure. **Recovery/image-artifact policy (DECIDED 2026-06-02):** large GPU images are **not** pushed to GHCR (free-tier limits); recovery = Dockerfile-in-git + `docker save` artifact on owned storage (`scripts/save-image-artifact.sh` → `/mnt/ivgs-shared/image-artifacts/` with SHA-256 + MANIFEST) + re-acquirable weights; compose uses `pull_policy: never`. Full procedure in `RECOVERY.md`.

---

# Stage 6 — Talking Head (LatentSync + SadTalker): BUILD REQUIRED

**This is the next major build, not a deploy.** The compose declares both engine services (`docker-compose.node04.yml`: `latentsync` :7860, `sadtalker` :7861) but they are **parked placeholders** (`profiles: ["pending"]`, `pull_policy: never`) and the images **do not exist** in ghcr (`docker manifest inspect …:latentsync-v5.2.7-h0` / `…:sadtalker-v5.2.7-h0` → `manifest unknown`, confirmed 2026-06-06). The pipeline auto-advances and parks cleanly at `talking_head_render` (correct).

**Placement decision (2026-06-06): node-03.** node-04 has only ~8 GB free (RTX PRO 5000 48 GB; FLUX ~16.8 + Mistral-24B vLLM ~16.1 + TTS ~7.5), too tight for LatentSync (~12 GB). **node-03** (RTX PRO 6000, 97.9 GB, ~70 GB free with CogVideoX resident ~26 GB) has ample room. Tradeoff: concentrates a second stage on the sole video node (SPOF) — acceptable for bring-up; node-05/06 remain an isolation option later.

**Work breakdown:**
1. **Build two GPU engine images** (the bulk): `ghcr.io/brucecostello2/ivgs-workers:{latentsync,sadtalker}-v5.2.7-h0`. Per engine: upstream model code + checkpoints (weights live in the mounted `/data/models`, not baked) + a server wrapper exposing `/health` + an inference endpoint matching the IVGS client contract + a Dockerfile on a Blackwell-capable CUDA base; build/push from node-01. Template: the existing engine builds (ComfyUI/Coqui/Kokoro/WhisperX `*-v5.2.7-h0`) and the `servers/common/` skeleton + `servers/cogvideox/` (async-job contract `POST /generate`, `GET /status/{id}`, `/download/{id}`, `/health`).
2. **Wiring** (smaller): move the two service defs `node04.yml` → `node03.yml`; add engine URLs to node-03's worker env via the consolidated-compose pattern; shift the `gpu_talking_head` queue onto node-03's worker (engines + worker co-located for intra-node DNS); implement the live `talking_head_task.py` client logic — LatentSync-primary **>0.85 alignment gate**, SadTalker fallback, DLQ, **600 s** timeout, output path, manifest binding (the `metrics`/`alignment_score` route from `servers/common/jobs.py` feeds the gate). Confirm the upload URL (P2.34).
3. **Inputs:** presenter-clip upload (`POST /projects/{id}/upload-talking-head` → `asset_id`) + retrieve the Stage-5 audio; **skip Stage 6 cleanly** when no clip is uploaded. (The test project has no presenter clip — first run can exercise the skip path, or upload a test clip.)
4. **Output:** spec path `/ivgs/talking-heads/{project_id}/{language_code}.mp4` — confirm the live mount (`/mnt/ivgs-shared`, per the rollback `/ivgs` lesson) before relying on it.

**Risk — Blackwell (sm_120) compatibility.** LatentSync/SadTalker are 2023–2025 codebases likely pinning PyTorch/CUDA predating Blackwell → may need dependency bumps that cascade. Mitigant: FLUX/vLLM/TTS already run on this fleet (cu128/cu130 Blackwell base proven), so there's a working base image to copy. This is the main schedule unknown.

**Also build the missing `GET /projects/{id}/manifests` endpoint** (Stage 7/8's `_fetch_latest_manifest` GETs it; only `/jobs/{job_id}/manifest` exists) and the asset-endpoint auth sweep (`get_asset`/`download_asset` if a stage needs them) when wiring downstream stages.

---

# Operator tasks (not Claude-actionable)

| Item | Notes |
|---|---|
| GPG private key off-network backup | Signing key `4F2243FAB5A25808` should have an off-node copy. Security-sensitive. |
| `.env.node01` secret leak + credential rotation | See P1.7. Operator-driven. |
| Push `feat/phase-h0-make-main-honest` + open/track PR | Branch carries all current work through `eaddebb`. |

---

# Items closed (evidence)

### Closed this arc (regression + Stages 3/4/5, 2026-06-05 → 06)

| Item | Closed in | Evidence |
|---|---|---|
| **A1 — image-generation regression** | 2026-06-05 (`d3d1fb4`, config-only) | NOT a code regression (overturns the Forensic Report): `config.py`/clients byte-identical across images; cause was a latent `IVGS_*`-prefixed-vs-deployment env-name mismatch sprung by `--force-recreate`. Cure = move canonical `IVGS_*` names into the **tracked** `docker-compose.node0X.yml` `environment:` blocks. Image 3 + 1 animation via FLUX (0 failed) + video 2 via CogVideoX proven post-fix. |
| **A2 — de-band-aid node-04 vLLM model name** | 2026-06-05 (`d3d1fb4`) | `IVGS_VLLM_MIDSIZE_MODEL=mistral-24b` (+ `IVGS_COMFYUI_URL=http://comfyui:8188`) now set in tracked compose; no longer a hand-edited gitignored `.env.node04`. |
| **A4 — 401 scene-asset linkage (image/animation `scene_id` NULL)** | 2026-06-05 (`a914352`, workers `v5.4.3-h0`) | Root cause **worker-side** (not API-side as A4 hypothesized): `stage3_images.py::_upload_to_seaweedfs` omitted `scene_id`; added it + deleted the dead operator-only 401 scene-PATCH. Animation rides the same task. e2e: all assets scene-linked, no `__global__` orphans. |
| **Stage 4 — composition manifest (e2e PASS)** | 2026-06-05 (`a91cdce`; workers `v5.4.4-h0`, API `v5.2.1-h0`) | Manifest built **server-side** by `POST /api/v1/jobs/{id}/manifest/generate` (groups assets by `scene_id`, NULL→`__global__`); worker `build_composition_manifest` is a thin idempotent driver (GET→404→generate→validate→lock→`handle_stage_completion`). Manifests router remounted `/manifests`→`/jobs` (also fixes the in-repo frontend timeline editor); all 4 endpoints → `get_service_or_user`. (The worker-side `ManifestBuilder` is now dead — excise via P2.26.) Run: manifest `b636fe87` locked, `total_duration_ms 115000`, scene_count 6. |
| Stage-4 media-join failure decrement (soft-continue) | 2026-06-05 (`35d9226`, workers `v5.4.1-h0`) | Failure path now decrements + advances with a `failed_count` (was: only decremented on success → a failed media stage hung the join forever). |
| Stage-4 media-join crash watchdog | 2026-06-05 (`0bde15e`, workers `v5.4.2-h0`) | Celery-beat `media_join_watchdog` (5 min) drains joins stranded by a hard worker crash. |
| Infra hygiene (closes A7(a)) | 2026-06-05 (`7569ed5`) | Dropped obsolete compose `version:`; committed `ivgs-models/checksums.sha256` (was dirty per A7(a)); gitignored smoke-test compose. |
| API `/ivgs` crash (rollback storage) | 2026-06-05 (`c3e8a1a`, API `v5.2.2-h0`) | `rollback_service.py` ran `mkdir` on hardcoded `/ivgs` at import (unmounted; API runs non-root) → crash-looped the API. Repointed `ROLLBACK_STORAGE_DIR` → `/mnt/ivgs-shared/rollback_points`. (Full rollback wiring remains — P2.35.) |
| **Stage 5 — TTS/voiceover (e2e PASS)** | 2026-06-06 (5 commits; API `v5.2.3-h0`, workers `v5.4.7-h0`) | Final run `3cb8c4d6` (42.6 s): 6/6 scenes → Coqui XTTS v2 `200` → validated → uploaded `201`; **48 kHz/24-bit, approved, SNR 60 dB**, six distinct `seaweedfs_fid`, all scene-linked. Seven fixes: **auth** (`92616f7`, API `v5.2.3-h0`) `list_scenes`+`list_assets` → `get_service_or_user`; **`CoquiClient` ctor + retry raise-None** (`82d9490`, workers `v5.4.5-h0`); **TTS engine URLs in worker env** (`db264c5`, compose); **validator accepts `WAVE_FORMAT_EXTENSIBLE`** (`39ee28d`, workers `v5.4.6-h0`); **upload URL + `scene_id`/`language_code`** (`eaddebb`, workers `v5.4.7-h0`). Auto-advances to `talking_head_render`. |
| Voiceover auto-advance — confirmed present | 2026-06-06 | The Stage-5 task calls `handle_stage_completion` on success (dispatched `talking_head_render` unprompted) — no gap at the TTS→talking-head boundary. |

### Closed in the 06-04/05 arc (Addendum A §B)

| Item | Closed in | Evidence |
|---|---|---|
| Storyboard prompt-truncation (empty/off-topic output) | 2026-06-04 (`a9b2e47`); baked + verified 2026-06-05 | Root cause = truncated Jinja templates committed at v5.0.0; reconstructed `stage1_user/system.j2`, `stage2_system.j2`; baked into `v5.4.0-h0`, NFS override dropped. On-topic in two fresh e2e runs. |
| AD-02 node specialization — implemented | 2026-06-04 (`AD-02`); verified at Stage 3 | node-02 LLM-only (Llama-3.3-70B-FP8), node-03 video-only, node-04 image+TTS; Stage-3 topology conformance PASS. (Governance recording remains — P1.6.) |
| `MEDIA_GENERATION` park — root-caused + unparked (functional half of v1→v2) | 2026-06-05 (`9f692ab`, `v5.4.0-h0`) | Partial v1→v2 migration: 6 call-site repoints v1→v2 + 3 added v2 advances + 4 `STAGE_TASK_MAP` name fixes. Proven e2e (no `next_stage_task_not_registered`). Phase-2 cleanup remains — P2.26. |
| node-04 vLLM-midsize (Mistral-24B w4a16) live | 2026-06-05 | `mistral-24b` at `vllm:8000`, HTTP 200 for image-prompt generation. |
| Profile-gating of AD-02 standby services | 2026-06-05 (`68ac33b`) | `profiles: ["standby"]` on node-02 cogvideox + node-03 vllm/worker so a plain `up` can't resurrect disabled services. |
| Signature-drift + DNS concerns — non-reproducing | Stage-3 report §3.3 | `acquire_gpu_reservation(vram_mb=)`/`save_checkpoint(stage=)` TypeError + name-resolution worries do not reproduce on the deployed image. |

### Closed earlier (v2.1 era + appended milestones)

| Item | Closed in | Evidence |
|---|---|---|
| P1.4 — push ivgs-backup-worker to GHCR | 2026-05-29 (`379292a`) | `:v5.1.0-stream-b` pushed; override pins via `${IVGS_BACKUP_WORKER_TAG}`. |
| **P1.5 — API never dispatches the orchestrator** | 2026-06-01 (Stage 2B, `699986b`+`76d2735`, branch `…@564e343`) | `trigger_pipeline` now dispatches `dispatch_pipeline`; producer `broker_transport_options`/`global_keyprefix` aligned. Real `POST /trigger` drove transcript→storyboard→user-gate e2e. (Remaining sub-items folded into P2.28/P3.3.) |
| P1.5 item 2 — approval → media dispatch | 2026-06-03 (`19bf90d`+`78c3684`) | `POST /scenes/approve` → `dispatch_media_generation`; proven 3/2/1 fan-out, scene_id-validated. (Lenient guard = tracked deviation → P2.28.) |
| Stage 2B API batch (scenes/transcript persistence) | 2026-06-01 (`ivgs-api:v5.1.22-scenes`) | `POST /projects/{id}/scenes` (service-auth) persists 6 rows; transcript upload + refined-text PATCH work. |
| P2.2 — config externalization (phases 2a–2h) | 2026-05-29/30 | All node-IP refs single-sourced to the `NODE_0x_IP` registry; obsolete `10.10.0.x` eliminated + guarded. Live-startup risk half deployed + verified. (Task-layer remainder → P3.3 H.5.) |
| P2.9 — obsolete compose `version:` | 2026-05-29 (`fbbafb5`) | Removed; parses clean. |
| P2.12 — Nginx dynamic-resolution hardening | 2026-05-29 (`7173797`) | resolver + variable `proxy_pass` (7 sites) + http2; verified via forced-IP auto-recovery. |
| P2.14 — pre-commit guard for `10.10.0.x` | 2026-05-30 (`e5816d8`) | Hook + `test_no_hardcoded_ips.py` backstop. |
| **P2.23 — workers image baked broken HEALTHCHECK** | H.0 (`d349c46`); effective in deployed `v5.2.4-h0`+ | Dockerfile `HEALTHCHECK` module `worker` → `celery_app`. Deployed image is `v5.4.7-h0`, so effective fleet-wide. |
| Phase H.0 — Make Main Honest | 2026-05-31 (`d349c46`) | No-GPU code-surgery: repaired provider refactor, added `get_model_config`, wired all 8 stages, removed off-plan residue, reconciled node02-06 compose. Build + 22-task-registration green. |
| Stage 0 — node-01 rebind + node-02 DR | 2026-05-31 (`bf78a23`,`663fe9e`) | node-01 services rebound to `${NODE_01_IP}`; node-02 CogVideoX recipe + compose committed. |
| Stage 2 — cross-node transport | 2026-06-01 | `refine_transcript_task` dispatched node-01 → executed node-02 vLLM → result via shared DB. |
| node-02/03/04 bring-up + de-conflict | 2026-06-02/01 | node-02 frozen baseline; node-03 twin live (`46eb806`); node-04 provisioned (image+TTS, video pruned). |
| Node Configuration admin GUI | 2026-05-30 (`0538ae0`+`145b366`) | `/admin` node-IP registry editor; host watcher applies via `--no-deps`. |
| Defect #8 — test suite restoration | Session 11/12 (PR #48, `a836668`) | 512 tests passing; 28 bugs fixed. |
| Phase 14 backup (Stream A + B) | Session 13/14/15 (PR #49) | NAS/GPG/pushgateway/WAL/cron + `ivgs-backup-worker`. |
| ComfyUI/Coqui/Kokoro/WhisperX engine images | 2026-06-02+ | Built for Blackwell (cu128, sm_120), weights mounted; deployed + healthy on node-04 (`*-v5.2.7-h0`). Recovery artifacts banked. |
| NFS bulk-transfer wedge | RESOLVED 2026-06-03 | Root cause = the inter-switch path (NOT NIC offload); mitigations: save local-first then copy; `systemctl restart nfs-server` fast-reset. |

*(Older v1.0/Session-5–9 closures and the full per-increment config-externalization log live in v2.1 history and the transcripts.)*

---

# Source documents

| Path | Notes |
|---|---|
| `/mnt/transcripts/*.txt` + `journal.txt` | Primary historical record; journal first to navigate. |
| `IVGS_Stage4_Closure_and_Stage5-6_Work_Package_2026-06-05.md` | This arc's working doc (regression close, Stage 4/5 closures, the 13 follow-ons, Stage-6 plan). |
| `IVGS_v5_Forensic_Report_ImageGen_Regression_2026-06-05.md` | A1/A2 detail — §6.2/§9.C **overturned** by the config root cause. |
| `IVGS_Stage3_E2E_Test_Report_2026-06-05.md` | Known-good baseline; the proven re-fire recipe. |
| `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md` | Authoritative topology; AD-02 deviation (P1.6). |
| `IVGS_v5_Addendum_AD-01_Model_Management.md` | Model management (gated; do-not-build). |
| `ivgs_v5_functional_spec.md` | §5.2.5 manifest API, §6.1 stages, Stage-5 TTS spec, Stage-6 LatentSync/SadTalker spec, §14.3 rollback. |
| `IVGS_Phase_H0_Closure_Addendum.md` | H.0 + Stage-2B runtime closure. |
| `RECOVERY.md` | Image-artifact recovery procedure (P3.14). |
| `OUTSTANDING_WORK_Addendum_A_2026-06-05.md` | Now merged here (A1/A2/A4 closed; A3/A5/A6/A7 → P1.6/P2.26/P2.27/P3.7). |

---

# Update protocol

Each session that closes should, before final commit:

1. **Add** any new deferred item discovered this session (source = transcript path/date).
2. **Update** the status of any item touched — move closures to the *Items-closed* table with evidence; don't delete.
3. **Re-snapshot** the priority counts.
4. **Commit** as `chore(docs): update OUTSTANDING_WORK.md — <session summary>` and push.
5. **Update** `/mnt/transcripts/journal.txt` to note the session's relationship to this file.

The discipline: nothing is "deferred" without going into this file.

*— End of ledger (v3.0, consolidated 2026-06-06) —*
