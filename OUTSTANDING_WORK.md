# IVGS v5 — Outstanding Work (Single Source of Truth)

| | |
|---|---|
| **Document version** | v2.1 — 2026-05-30 |
| **Authoritative as of** | main @ `31f61e8` (Node Configuration delivered; P1.4 + P2.2/2.9/2.12/2.14 closed; P2.5/2.23/2.24/2.25 added) |
| **Repository / branch** | `brucecostello2/elearning_v5` on `main` |
| **Supersedes** | v1.0 (`IVGS_Outstanding_Fixes_SoT.docx`, 2026-05-26, Sessions 5–9). Items from v1.0 are reviewed below with current status. |
| **Live stack** | ivgs-api `v5.1.18-node-config`, ivgs-frontend `v5.2.16-node-config`, ivgs-workers `v5.1.4-config-2b`, ivgs-backup-worker `v5.1.0-stream-b`, ivgs-scheduler `latest` (P2.11). Alembic 0024. |
| **Purpose** | Single ledger of every known outstanding item. Each new session updates this file before close. Items have priority, source, scope, and concrete carry-forward action. |

## Operator policy on tech debt

From Phase 14 Stream B session (2026-05-29 17:54 transcript, line 1668), operator-stated:

> "our general MO should be that when there is a bug we should fix, not park for some point in the future, we need to be clean as we go."

This file exists to give effect to that policy: nothing is "deferred" without being recorded here. New deferrals require an entry. Closures require evidence (commit SHA, tag, or session transcript pointer).

## Priority definitions

- **P0 — Blocking.** System broken or unsafe; address before any other work.
- **P1 — High.** Blocks dev velocity, hides regressions, or required for next feature increment.
- **P2 — Medium.** Real defect or hygiene work; will compound if deferred.
- **P3 — Low.** Cosmetic, documentation, or strategic multi-session work.

## Snapshot

| Priority | Count | Headline items |
|---|---|---|
| P0 | 0 | — |
| P1 | 3 | Defect #4 prompt ENUM; D.11 prompt-mgmt browser smoke; Spec v1.1 §9 GPU acceptance bullets |
| P2 | 21 | monitoring `ivgs_default` external-net (P2.25); Defect #5 [object Object]; Defect #9 nodes status lie; **Defect #10 test directory scope unification**; Phase F.1–F.11 hygiene backlog; Phase E.1 infrastructure docs; **Phase E.2 RUNBOOK.md**; MP F.3/F.4 (digest pins, FlaggedAsset typing); tests/ pytest-collection SQLite blocker; forensic correction; tag taxonomy doc |
| P3 | 6 | GpuNodeStatus UPPERCASE dead code; empty seaweedfs volumes; Phase H multi-node; endpoint test coverage; rogue-branch attribution investigation; cosmetic UI polish |

---

# P1 — High Priority

## P1.1 — Defect #4: Prompt.prompt_type ENUM-as-String

| | |
|---|---|
| **Source** | v1.0 §2.3 (S7 §11.5 → S8 §6.4 → S9 → still open) |
| **Status** | OPEN. Latent because prompt library is empty. |
| **Severity** | Will 500 on first INSERT with `DatatypeMismatchError`. Architecturally identical to Defect #3 (User.role) which was fixed in v5.1.11. |
| **Blocks** | P1.2 (D.11 browser smoke) — seeding prompts against broken model would fail. |
| **Scope** | `app/models/prompt.py` lines 40–43: replace `prompt_type: Mapped[str] = mapped_column(String(32), ...)` with PG_ENUM mirroring migration 0001's 10 enum values. The `.cast(String)` workarounds in `prompt_service.py:61,77` become dead code. |
| **Carry-forward action** | (a) Read migration 0001 for canonical 10 enum values. (b) Apply PG_ENUM swap per S7 §11.5 template. (c) Build `v5.1.15`. (d) CLI-verify a prompt can be INSERTed. |
| **Effort** | 45–60 min. |

## P1.2 — Phase D.11: Prompt-management 9-step browser smoke

| | |
|---|---|
| **Source** | v1.0 §2.4 (carried from S6 → S7 §11.6 → blocked S8, S9) |
| **Status** | OPEN. Prompt-management code deployed in v5.1.8; never functionally smoke-tested end-to-end. |
| **Blocks** | Hard-blocked by P1.1 (Defect #4). |
| **Scope** | 9 steps per S7 §11.6: seed library with 10 system-tier prompts → list → filter → detail → project-tier override → effective resolution → edit → delete → fallback. |
| **Carry-forward action** | Run only after Defect #4 deploys cleanly. Halt on any 500 or console error. |
| **Effort** | 30–45 min once unblocked. |

## P1.3 — Spec v1.1 §9: GPU Fleet acceptance bullets (deferred ~18 of 24)

| | |
|---|---|
| **Source** | v1.0 §2.5 (S9 §9) |
| **Status** | PARTIAL — ~6 of 24 bullets walked via browser smoke in Session 9. Remaining ~18 are edge cases normally pytest-covered. |
| **Severity** | Edge cases unverified: range param validation, 30-day bound, MAX_HISTORY_POINTS=5000 cap with 413 response, JOIN correctness multi-node, sort stability, auth gate (403 vs 401), `power_tdp_w` correctness, chart dashed-line variant, legend stability, focus/reconnect re-fetch, 4xx-no-retry policy, empty-array vs undefined distinction. |
| **Blocks / Blocked by** | Test suite restoration (Defect #8) is now CLOSED via PR #48 (Session 12), so these are no longer hard-blocked. Test infrastructure available. |
| **Carry-forward action** | Now actionable. Write `TestGpuUtilizationHistory` class within the restored suite covering the deferred bullets. |
| **Effort** | 3–5 hours. |

## P1.4 — Push ivgs-backup-worker image to ghcr.io

| | |
|---|---|
| **Source** | Phase 14 Stream B closeout (this session) |
| **Status** | CLOSED (2026-05-29). Pushed to GHCR; node-01 override pins the registry image via `${IVGS_BACKUP_WORKER_TAG}`. See Items-closed table. |
| **Severity** | Multi-node deployment (Phase H) will fail because nodes 02–06 can't pull `:local`. |
| **Scope** | `docker tag ivgs-backup-worker:local ghcr.io/brucecostello2/ivgs-backup-worker:v5.1.0-stream-b`, push, update IVGS_BACKUP_WORKER_TAG in `.env` and `.env.node01`. |
| **Carry-forward action** | Execute next session before any multi-node work. |
| **Effort** | 5 min. |

---

# P2 — Medium Priority


## P2.1 — Defect #10: Test directory scope unification

| | |
|---|---|
| **Source** | v1.0 SoT §3.1 (Session 11 mid-execution discovery, concurred Session 10). Spec at `/mnt/user-data/outputs/Defect_10_Test_Directory_Scope_Unification.md`. |
| **Status** | OPEN — spec authored. |
| **Severity** | Medium. Defect #8 restored only `ivgs-api/tests/` (13 files). Three other test directories remain unrunnable: `tests/` (9 files; SQLite conftest can't construct PG schema), `ivgs-workers/tests/` (16 files; no conftest, no `__init__.py`), `ivgs-scheduler/tests/` (4 files; has `__init__.py` but no conftest). Plus `conftest.py` collision between `ivgs-api/tests/conftest.py` and `tests/conftest.py` blocks a unified `testpaths`. |
| **Scope** | (1) Read & catalog all 9 + 16 + 4 = 29 test files for unique coverage. (2) Resolve conftest collision via `importmode = "importlib"` (likely) vs namespace-package restructuring. (3) Decide per-directory: keep, drop, or migrate. (4) Wire up testcontainers+Alembic pattern (per Defect #8) where retained. |
| **Carry-forward action** | Per the spec — investigation phase precedes any code changes. |
| **Effort** | 4–8 hours (one session, possibly two). |

## P2.2 — Config externalization PR

| | |
|---|---|
| **Source** | Phase 14 Stream B session. Documented in `IVGS_CONFIG_EXTERNALIZATION.md` on operator's PC. |
| **Status** | CLOSED (2026-05-30). Phases 2a-2h all complete (this + prior sessions); the GPU-pipeline task-layer URL consolidation discovered during 2b is the only deferral, moved to Phase H (P3.3 H.5). Full per-increment evidence is in the Items-closed table; the detailed running log is retained below. Node-IP model: node-01 `.env` holds the full registry as literal `NODE_01_IP..NODE_06_IP` (the earlier `SUBNET_PREFIX` form was dropped per operator — admin assigns IPs at the router/machine and registers them here); `node01.yml` `x-gpu-service-urls` anchor composes the 12 GPU URLs from them. Star topology: each GPU node references only node-01 via a single `NODE_01_IP` pointer. node02-06 compose now parse (a fatal duplicate-`<<:` bug was fixed) and resolve node-01 refs to `${NODE_01_IP}`; all `.env*.template` carry the model; `deploy-node.sh` repaired. Commits `fa6f4db` (2a), `49b736d` (node-01 templates), `7c374e5` (node02-06 + parse fix), `bfcec00` (deploy-node.sh), `e0fe26f` (restore.sh, completing 2e), `68318bd` (cd-deploy.yml = 2f), `41c34bd`/`3426f0f`/`c85690b` (2g docs/SeaweedFS/stragglers). Every independent IP reference now resolves to the registry or the real `192.168.1.9x` scheme; the only `10.10.0.x` left in-tree is the 2b image code (`shared/config.py`, `ws_logs.py`, `ivgs-workers/clients/*`) plus its two coupled tests. node-01 containers healthy; node02-06 + deploy/restore scripts + CI validated by inspection only (no GPU hardware). **2b API half (this session): done + deployed.** `shared.config` trimmed of vestigial GPU/media URL fields (never read; obsolete IP defaults); `ws_logs` node map now resolves `NODE_0x_IP` from the registry env (fastapi env carries `NODE_01_IP..06`); rebuilt `ivgs-api:v5.1.15-config-2b`, recreated `--no-deps`, `/health` healthy with db/redis/seaweedfs connected, 8/8 ws_logs tests green. Commits `0c797df` (config trim), `18f17d9` (ws_logs+test), `a656514` (fastapi env). Remaining 2b: the workers bundle — re-key `WorkerConfig` URL fields to canonical unprefixed names, remove worker client `10.10.0.x` base_url defaults, fail-fast, rebuild `ivgs-workers` (watch the `/v1` suffix + per-client port drift) — plus the 2h guard. **2b workers vLLM increment (this session): done + deployed.** config.py VLLMConfig primary/secondary/midsize_base_url now `_env_required("VLLM_*_URL")` — canonical unprefixed registry names, fail-fast (no node-0X default); anchor `VLLM_*_URL` stripped of baked `/v1` (registry holds host:port; VLLMClient appends `/v1/chat/completions`, avoiding /v1/v1 on re-key); new `ivgs-workers/tests/conftest.py` seeds the vars for pytest. Commit `35954ed`; rebuilt `ivgs-workers:v5.1.2-config-2b`, recreated celery-worker-default+celery-beat `--no-deps` — both healthy, worker ready, celery ping OK, no import/EnvironmentError. Remaining 2b workers: re-key gpu_scheduler/pipeline_api URLs to `GPU_SCHEDULER_URL`/`API_BASE_URL` (keep node-01-local defaults; unify the leftover `shared/config.py` GPU_SCHEDULER_URL), strip hardcoded client base_url IP defaults + reconcile per-client ports to the anchor, seed repo-root `tests/conftest.py` + update `test_gpu_nodes.py`, second workers rebuild — then 2h guard, then close P2.2. **FINDING (NOT a 2b item — GPU pipeline / Phase H, P3.3 scope):** `tasks/stage1_transcript.py` uses a VLLMClient interface the current client lacks: `async with VLLMClient(config.vllm)` (ctor takes base_url:str not a config; no __aenter__) and `vllm_client.chat(base_url=..., system_prompt=...)` (no .chat(); client exposes generate()/stream()). Live transcript-refinement would AttributeError at construction/call; only reachable with GPU/vLLM (none on node-01), worker boots fine (breakage is in the task body). Evidence: vllm_client.py is 240L / one class; stage1 L336 + L560. **2b workers API-callback increment (this session): done + deployed.** pipeline_api re-keyed IVGS_API_BASE_URL -> canonical API_BASE_URL, default corrected node-01:8000 -> fastapi-backend:8001 (LATENT BUG: IVGS_API_BASE_URL was unset everywhere, so worker->API callbacks defaulted to an unreachable host:port); API_BASE_URL added to the node01 service-url anchor; vestigial shared/config.py GPU_SCHEDULER_URL removed (ivgs-api never read it; effective next API build). gpu_scheduler IVGS_GPU_SCHEDULER_URL deliberately LEFT as-is - cross-cluster var (node02-06 + .env env_file); renaming = disproportionate churn for cosmetic naming. Commit 1453530; ivgs-workers v5.1.3-config-2b live, worker+beat healthy, worker->API verified 200. Remaining 2b: 11-client base_url externalization (increment 3). Spec port arbitration (functional spec A.2): LATENTSYNC canonical 7860 (client default :8300 stale), REMOTION canonical 3002 (client :3100 stale); cogvideox/wan21 are node-02/03 video services needing new registry entries; flux -> COMFYUI_PRIMARY, safety_classifier -> node-04 vLLM. |
| **Severity** | Pre-commit hook currently blocks `http://10.10.0.X` strings in commits. Some env-var naming is also inconsistent. Risk of spec drift between Compose, env files, and runtime. |
| **Scope** | Externalize IP literals into env vars; standardize env-var naming convention; document acceptable patterns; update pre-commit hook scope. |
| **Carry-forward action** | DONE (2026-05-30) -- 2b and 2h are complete and deployed (see the Status row + Items-closed table for commits and image tags). The text that follows is the original plan plus residual shakeout caveats, retained as Phase-H (P3.3 H.5) pointers. Original plan: (2b) worker/API config unification — reconcile `shared/config.py` (unprefixed canonical names) vs `ivgs-workers/config.py` (IVGS_-prefixed) onto one authority, trace the still-unidentified `config` object in `localization_pipeline.py`, remove hardcoded `10.10.0.x`/hostname fallback defaults (fail-fast), rebuild `ivgs-api` + `ivgs-workers` (pin per §19.5), coordinated deploy + verify all healthy (the only phase with live-startup risk); as part of 2b re-point the two coupled tests (`tests/test_ws_node_logs.py`, `tests/smoke/test_gpu_nodes.py`) to config-sourced values, not a new hardcoded scheme. (2h) `tests/spec_compliance/test_no_hardcoded_ips.py` guard (subsumes P2.14) + widen the pre-commit hook — land alongside 2b so guard and cleaned code arrive together. OPEN CAVEATS: (i) GPU stacks (node02-06) + `deploy-node.sh` + `restore.sh` + `cd-deploy.yml` are all fixed by inspection (`bash -n` / `docker compose config` / YAML-validate) but have NEVER run end-to-end (no GPU hardware) — full shakeout when hardware lands (relates to P3.3 Phase H); (ii) `deploy-node.sh` migration step references `POSTGRES_PASSWORD` not sourced into the script shell — resolve in that shakeout; (iii) `cd-deploy.yml` deploy-node01 step depends on the self-hosted runner workspace exposing the live gitignored `ivgs-infra/.env` — verify in shakeout; (iv) SeaweedFS live volume server advertises `-ip=seaweedfs-volume` (a Docker name) — fine same-host, but cross-host GPU workers doing direct volume fetches will likely need `publicUrl=<node-01 LAN IP>`; Phase-H/shakeout item, not fixed now; (v) `ivgs-infra/docker-compose.node01.yml.backup` is a gitignored (`*.backup`) local rollback snapshot carrying the old scheme — intentionally untracked, left in place. |
| **Effort** | ~5 hours (per the doc). |

## P2.3 — Defect #5: "[object Object]" validation banner

| | |
|---|---|
| **Source** | v1.0 §3.1 (S8 §6.1) |
| **Status** | OPEN. Untouched since S8. |
| **Severity** | Medium-low. UX bug on validation errors. User sees `[object Object]` instead of real validation message. |
| **Scope** | Frontend error-handler string-coerces FastAPI structured detail envelope. Surfaces on User Management create/edit; likely also DLQ replay, Quality Review approve/reject, Storage Quota adjust. Fix: extract `detail[0].msg` (or join all messages). |
| **Carry-forward action** | Fold into next frontend session when touching a related component. |
| **Effort** | 1–2 hours. |

## P2.4 — Defect #9: /api/v1/nodes stub hardcodes status="online"

| | |
|---|---|
| **Source** | v1.0 §3.1 (S9 §4.3) |
| **Status** | OPEN. Documented; fix path scoped. |
| **Severity** | Medium for v5 alpha; high for any multi-operator scenario. `/nodes` shows '6 online' when only node-01 runs the stack. |
| **Scope** | `ivgs-api/app/api/v1/nodes.py` line 82: stub returns `status="online"` unconditionally. Phase 8 GPU scheduler will replace stub. Interim option: ping DNS/ICMP/some authoritative source (~20 lines). |
| **Carry-forward action** | Document as known limitation in v5 alpha release notes; full fix at Phase 8. Adding `test_nodes.py` should pair with Phase 8 work — testing the stub now would freeze the lie into a regression safety net. |
| **Effort** | Interim fix ~1 hour; full fix is Phase 8 (multi-day). |

## P2.5 — Stream A test bug: test_fleet_counts_nodes_in_all_states

| | |
|---|---|
| **Source** | Stream A session (2026-05-29 16:02 transcript). |
| **Status** | OPEN. Surfaced during a test rename: `online_count` vs `online_nodes` attribute mismatch on `GpuFleetSummary`. Single test failing in suite of 530. |
| **Scope** | `ivgs-api/tests/test_service_gpu.py::TestFleetUtilizationStatusBranches::test_fleet_counts_nodes_in_all_states` references `online_count`/`offline_count`/`draining_count` but the model exposes `online_nodes`/`offline_nodes`/`draining_nodes`. One commit was needed but the replace pattern matched twice — uncertainty about which to patch. |
| **Carry-forward action** | Open the test file, inspect both occurrence sites, fix correctly with full context. |
| **Effort** | 30 min. |

## P2.6 — Phase F.1: Migrate ad-hoc fetch() to centralized api-client

| | |
|---|---|
| **Source** | v1.0 §3.2 (S7 §11.8 → S8 §11.7) |
| **Status** | OPEN. 16 known sites in 7 files + GPU history call. |
| **Scope** | Migrate every `fetch()` to `src/lib/api-client.ts`. Add pre-commit hook blocking `localStorage.getItem("access_token")` without the `ivgs_` prefix. |
| **Effort** | Full session of careful work. |

## P2.7 — Phase F.2: Backend UUID path-param validation (422 not 500)

| | |
|---|---|
| **Source** | v1.0 §3.2 (S7 §11.8) |
| **Status** | OPEN. |
| **Scope** | Class-level UUID path-param validation (FastAPI dependency or custom path converter). Touches multiple endpoints. Architectural decision: which endpoints, what error envelope. |
| **Carry-forward action** | Pair with P2.2 (Defect #5) — both touch error response shape. |

## P2.8 — Phase F.3: Old GHCR image cleanup

| | |
|---|---|
| **Source** | v1.0 §3.2 (S7 §11.8) |
| **Status** | OPEN. 14+ stale tags each for ivgs-api and ivgs-frontend (more by now). |
| **Scope** | Document retention policy first (e.g., keep last N tags + every tag referenced by a session-*-close tag). Then prune. |
| **Carry-forward action** | Author retention policy → apply. |

## P2.9 — Phase F.4: Remove obsolete `version:` from docker-compose.node01.yml

| | |
|---|---|
| **Source** | v1.0 §3.2 (S7 §11.8) — smallest blast radius in F backlog |
| **Status** | CLOSED (2026-05-29). `version: "3.8"` removed; docker compose config parses clean, warning gone. See Items-closed table. |
| **Scope** | Compose produces WARN on every invocation: "the attribute version is obsolete". Delete one line; verify compose still parses. |
| **Effort** | Trivial. End-of-session warm-up/cooldown task. |

## P2.10 — Phase F.5: bcrypt/passlib version warning in fastapi logs

| | |
|---|---|
| **Source** | v1.0 §3.2 (S7 §11.8) |
| **Status** | OPEN. |
| **Scope** | Log-noisy startup warning: `(trapped) error reading bcrypt version`. Pin compatible passlib + bcrypt versions in `requirements.txt`. |
| **Carry-forward action** | Schedule alongside next backend dep update. |

## P2.11 — Phase F.6: IVGS_SCHEDULER_TAG=latest — pin or document

| | |
|---|---|
| **Source** | v1.0 §3.2 (S7 §11.8 / §14.4) — pre-existing master plan §19.5 violation |
| **Status** | OPEN. |
| **Severity** | Exact class of problem that caused the v5.1.5/v5.1.8 image-drift crisis (Session 6 Addendum A). |
| **Scope** | Either pin to a specific scheduler version (preferred) or document why this service is exempt from §19.5 no-`:latest` rule. |
| **Carry-forward action** | Operator decision pin-vs-document this session or next. **Update (this session):** while diagnosing the scheduler crash, confirmed locally that `ivgs-scheduler:v5.1.0` and `:latest` share one image ID (same 7-day-old build) — so pinning `IVGS_SCHEDULER_TAG=v5.1.0` is now a zero-behavior-change close whenever desired. |

## P2.12 — Phase F.10: Nginx hardening (resolver + variable-based proxy_pass)

| | |
|---|---|
| **Source** | v1.0 §3.2 (S5 → `IVGS_Nginx_Hardening_Backlog.docx` → S7 §11.8) |
| **Status** | CLOSED (2026-05-29). resolver + variable proxy_pass (7 sites) + proxy_connect_timeout 2s + http2 modernization; verified via forced-IP-change auto-recovery. See Items-closed table. |
| **Severity** | Operational: any fastapi-backend / nextjs-frontend / grafana recreate triggers 502 until ivgs-nginx is also restarted (nginx caches DNS at startup). |
| **Scope** | Add `resolver 127.0.0.11 valid=10s ipv6=off;` to http{}. Convert each `proxy_pass` to variable form. Apply to 3 fastapi, 2 nextjs, 2 grafana locations. Optional: remove unused upstream{} blocks. |
| **Carry-forward action** | Sequence as dedicated mini-session per the docx. |
| **Effort** | Single deploy window. |

## P2.13 — Phase F.11 / Phase G: CI scaffolding (GitHub Actions + Playwright + pytest)

| | |
|---|---|
| **Source** | v1.0 §3.2 (Master Plan Phase G → S7 §11.8) |
| **Status** | OPEN. **Now unblocked** — Defect #8 was closed via PR #48 (Session 12), so pytest path is feasible. |
| **Scope** | Three workstreams: (a) Playwright smoke automation for the 8-page browser walk + the 9-step prompt-mgmt walk; (b) GH Actions `build-images.yml` (lint, tsc --noEmit, npm run build, pytest on push; build+push to GHCR on `v5.*` tag; Playwright smoke on CI compose stack); (c) PR template with stale-base + tsc + migration-roundtrip + compose-overlay-rule checks. |
| **Carry-forward action** | Start Playwright; sequence GH Actions after. |
| **Effort** | Substantial. Multi-session. |

## P2.14 — MP F.2: Pre-commit guard for 10.10.0.x IP literals

| | |
|---|---|
| **Source** | v1.0 SoT §3.2 (Master Implementation Plan §F.2) |
| **Status** | CLOSED (2026-05-30) -- implemented as P2.2 phase 2h (commit e5816d8); see Items-closed table. |
| **Scope** | `.pre-commit-config.yaml` local hook `no-bridge-ip-literals` that rejects any commit including a `10.10.0.x` literal. Test by attempting to commit a fake .env. |
| **Carry-forward action** | Done -- delivered as P2.2 phase 2h (commit e5816d8): widened pre-commit hook + tests/spec_compliance/test_no_hardcoded_ips.py. |

## P2.15 — MP F.3: Restore @sha256: digest pins on base images

| | |
|---|---|
| **Source** | v1.0 SoT §3.2 (Master Plan §F.3, originally Addendum C deferred) |
| **Status** | OPEN. |
| **Scope** | Identify base images that lost their digest pins in commit `b933357` (FROM and `image:` directives in Dockerfiles and compose files). Restore the digest pins. |

## P2.16 — MP F.4: Properly type FlaggedAsset.metrics

| | |
|---|---|
| **Source** | v1.0 SoT §3.2 (Master Plan §F.4, originally Addendum C §4) |
| **Status** | OPEN. |
| **Scope** | Currently typed as `any` (DeepAgent TS work residue). Define a proper discriminated union (e.g., `{ kind: "scalar", value: number } \| { kind: "histogram", buckets: …}`). |

## P2.17 — Phase E.1: Update IVGS_INFRASTRUCTURE_REFERENCE.docx

| | |
|---|---|
| **Source** | v1.0 SoT §3.4 (Master Plan §E.1, originally Session 4) |
| **Status** | OPEN — doc still describes split-repo architecture. |
| **Scope** | Update to reflect single monorepo at `/opt/ivgs`, remote `brucecostello2/elearning_v5`, subdirectories `ivgs-api/`, `ivgs-frontend/`, `ivgs-infra/`, `ivgs-workers/`, `ivgs-scheduler/`. Single git history; every command from `/opt/ivgs`. |

## P2.18 — Phase E.2: Author RUNBOOK.md (canonical node-01 deployment runbook)

| | |
|---|---|
| **Source** | v1.0 SoT §3.4 (Master Plan §E.2 → S7 §11.7 → S8 §11.6 → S9) |
| **Status** | OPEN — untouched in S7–S9. **More material than ever** to capture (S7, S8 lessons 10.7–10.17, S9 lessons 5.1–5.7, Defect #8 reconciliation, Stream A/B). |
| **Scope** | Suggested structure: §1 session-start six-rep gate; §2 deploy invariants (build from monorepo root, --env-file + -f overlay rules, force-recreate-single-service, pre-recreate compose-resolution gate); §3 the v5.1.5/v5.1.8 image-drift lesson; §4 backup procedures (Stream A+B); §5 incident-response (the git clean -fd recovery procedure). |
| **Carry-forward action** | Multi-session work; high value as institutional knowledge. |

## P2.19 — Phase F (new): docker-compose.base.yml vs docker-compose.node01.yml reconciliation

| | |
|---|---|
| **Source** | v1.0 SoT §3.2 (Session 5 §3.3 → S6 §9.3) |
| **Status** | OPEN. Has twice caused seaweedfs/redis/postgres recreate accidents. |
| **Scope** | `base.yml` defines seaweedfs 3.80 with underscore-named volumes and hot/warm tiered command; `node01.yml` uses seaweedfs 3.71 with hyphen-named volumes. Mis-application causes container/volume divergence. |
| **Carry-forward action** | Reconcile or delete the base.yml. |

## P2.20 — Forensic correction: Session 5 close forensic

| | |
|---|---|
| **Source** | v1.0 SoT §3.3 (Session 6 §9.4) |
| **Status** | OPEN. |
| **Scope** | Record PR #45/#46/#47 merges (close forensic missed them — caught by Phase C.5 audit). Note the `deps.py` path typo in the Session 5 Status Report. |

## P2.21 — Tag taxonomy doc

| | |
|---|---|
| **Source** | v1.0 SoT §3.3 (Session 6 §9.4) |
| **Status** | OPEN. |
| **Scope** | Document: `v*` for releases. `archive/*` for branch preservation. `session-N-close` for bisect anchors. Never delete `archive/*` tags without explicit per-tag audit. Note: this session added `archive/master-docs-final` and `archive/sandbox-reconciliation-final`. |
| **Carry-forward action** | Brief doc, ~30 min. Could fold into RUNBOOK.md (P2.17). |

## P2.22 — Pre-commit hook: SSL keys

| | |
|---|---|
| **Source** | v1.0 SoT §3.2 (Session 6 §9.3 — defense-in-depth) |
| **Status** | OPEN. |
| **Scope** | Pre-commit hook that fails the commit if any staged path matches `*.key`, `*.crt`, `*.pem` under `configs/nginx/ssl/`. |
| **Carry-forward action** | Pair with P2.13 (MP F.2 IP-literal hook) in the same session. |

## P2.23 — ivgs-workers image bakes a broken HEALTHCHECK (`-A worker`)

| | |
|---|---|
| **Source** | This session (2026-05-29), found while diagnosing the perpetually-`unhealthy` `ivgs-celery-beat`. |
| **Status** | OPEN — latent; runtime is correct today because every consumer overrides the healthcheck in compose. |
| **Severity** | Low now, real for Phase H. The `ivgs-workers` Dockerfile `HEALTHCHECK` runs `celery -A worker inspect ping`; module `worker` does not exist (the app is `celery_app`), so the probe exits 1 forever. `celery-worker-default` and (this session) `celery-beat` both override it in compose, so it is fully shadowed now — but any future container from this image without an override (Phase H workers/beat on nodes 02-06) will be falsely `unhealthy`. `inspect ping` is also a worker RPC, wrong for beat regardless of module name. |
| **Scope** | On the next `ivgs-workers` image build: correct the module to `celery_app`, or (cleaner for a role-agnostic image used by worker/beat/scheduler) drop the baked `HEALTHCHECK` and define per-role healthchecks in compose, as worker and beat now do. |
| **Carry-forward action** | Fix on the next workers image rebuild; no rebuild solely for this (runtime already correct via overrides). |

---

## P2.24 -- `tests/` pytest collection fails on SQLite (unconditional pool args in engine factory)

| | |
|---|---|
| **Source** | Found this session (2026-05-30) while wiring the P2.2 2h guard. |
| **Status** | OPEN. Blocks running the whole `tests/` suite (including the 2h `test_no_hardcoded_ips.py` guard) under pytest in this venv / CI. App runtime unaffected (production uses Postgres). |
| **Root cause** | `shared/database.py:31` passes `pool_size=settings.DATABASE_POOL_SIZE` (plus `max_overflow`/`pool_timeout`) to the async engine factory unconditionally. When a test points `DATABASE_URL` at SQLite/aiosqlite (NullPool), SQLAlchemy raises a TypeError on those args at create_engine, failing collection for every test under `tests/` (a conftest/session fixture builds the engine at setup). |
| **Carry-forward action** | Make the engine factory dialect-aware: drop the pool args when the URL is SQLite (or whenever NullPool is selected). Pairs with P2.13 (CI scaffolding) and P2.1 (test-dir unification). Until fixed, the 2h guard is enforced by the pre-commit hook, which needs no pytest. |

---

## P2.25 -- `docker-compose.monitoring.yml` references a non-existent external network `ivgs_default`

| | |
|---|---|
| **Source** | Found this session (2026-05-30) while building the Node Configuration apply path (the host watcher's first full `docker compose up -d` failed). |
| **Status** | OPEN. Latent: a full-stack `up -d` across node01+override+monitoring fails today. Operations are unaffected because deploys use `up -d --no-deps <service>`, which never validates the monitoring network. |
| **Severity** | Medium. Blocks any full-stack `up -d`; would bite a cold start or a full monitoring recreate. |
| **Root cause** | The monitoring file declares `networks: ivgs_default: {external: true}` (no `name:`) and attaches services to it, but no docker network named `ivgs_default` exists -- the real core net is `ivgs-infra_ivgs-net` (which the same file also references correctly as external `ivgs-net`). Running monitoring containers predate the drift, so the broken ref only surfaces on a fresh `up`. |
| **Workaround in place** | `scripts/apply-node-config.sh` recreates only the IP-consuming app services with `--no-deps` using just `node01 + override` (monitoring excluded), so node-config apply never touches this. |
| **Carry-forward action** | Reconcile the monitoring network definition (attach to the real `ivgs-net`, or create/name the expected network). Pairs with P2.19. |
| **Effort** | ~1 hour (edit + a full `up -d` validation in a maintenance window). |


# P3 — Low Priority

## P3.1 — GpuNodeStatus UPPERCASE half (dead code cleanup)

| | |
|---|---|
| **Source** | v1.0 §4 (S9 §7) |
| **Status** | OPEN. |
| **Scope** | `types/api.ts` has both `"online"|"offline"|"draining"` and `"ONLINE"|"OFFLINE"|"DRAINING"`. Backend only emits lowercase. Delete UPPERCASE half; `tsc --noEmit` to verify. |
| **Effort** | Trivial. |

## P3.2 — Empty underscore-named seaweedfs volumes removal

| | |
|---|---|
| **Source** | v1.0 §4 (S5 §7) |
| **Status** | OPEN — harmless. |
| **Scope** | Four empty 4K docker volumes from S5's brief docker-compose.base.yml mis-application: `ivgs-infra_seaweedfs_{master,hot,warm,filer}_data`. |
| **Carry-forward action** | Verify no compose references them, then `docker volume rm` four volumes. |

## P3.3 — Phase H: Multi-node expansion to nodes 02–06

| | |
|---|---|
| **Source** | v1.0 §4 (Master Plan §H → S7 §11.8 F.12) |
| **Status** | OPEN — multi-session, strategic. |
| **Blocked by** | P1.4 (push ivgs-backup-worker to ghcr.io) and RUNBOOK.md. |
| **Scope** | H.1: bring up node-02 (first GPU worker). H.2: resolve stale branches `fix/vllm-client-missing-symbols`. H.3: nodes 03–06. H.4: resolve `audit/v5-spec-compliance-fixes` and `remediation/comprehensive-spec-compliance` branches. H.5: GPU-pipeline task-layer config consolidation + interface repair (detailed in the row below; surfaced during P2.2 2b). |
| **Effort** | Weeks of work. Not session-blocking for current alpha posture. |
| **H.5 -- task-layer URL consolidation + interface repair (from P2.2 2b)** | Worker CLIENT defaults are DONE (commit 5d525a7): all 11 clients in `ivgs-workers/clients/` resolve `base_url` lazily from the canonical registry env, fail-fast, zero literals; what remains is the TASK layer that calls them.<br>(A) Broken interfaces needing code repair (validate when GPU services exist): `tasks/stage1_transcript.py` does `async with VLLMClient(config.vllm)` + `vllm_client.chat(base_url=...)`, but VLLMClient takes `base_url:str` (no config, no `__aenter__`) and exposes `generate()/stream()` not `chat()` (finding 936fb47); `talking_head_task`/`video_generation_task` call `config.get_model_config(...)` which does not exist on WorkerConfig; `localization_pipeline` reads `config.LATENTSYNC_URL`/`config.WHISPERX_URL` attrs that do not exist.<br>(B) Competing URL-sourcing to consolidate onto the single canonical source the clients now use: task-level os.getenv with non-canonical names (IVGS_COMFYUI_URL / IVGS_COGVIDEOX_URL / etc.) that are set nowhere so always fall back to hardcoded values, a latentsync_config dict, inline literals (e.g. Wan21Client base_url node-02:8210), and the missing get_model_config loader.<br>(C) Port conflicts to settle against ground truth: cogvideox 8188 (legacy client) vs 8200 (task); wan21 8190 vs 8210 (latentsync already reconciled to 7860 and remotion to 3002 in the clients).<br>(D) Reserved canonical names with NO anchor entry yet (ports unknown until services run): COGVIDEOX_URL, WAN21_URL, SAFETY_CLASSIFIER_URL (safety_classifier has zero callers = dead code).<br>(E) celery_app.include currently loads only stage1_transcript / stage2_storyboard / pipeline_orchestrator; stages 3-8 + talking_head + video_generation + localization are unwired (not imported at boot), which is why workers boot healthy despite the broken task bodies.<br>DEFINITIVE COMPLETION is gated on GPU node SERVICES coming online (not merely nodes powered): that provides ground-truth ports + an end-to-end validation target, and is incremental per node (node-04 alone unblocks most media services). Steps: add the reserved registry entries with real ports; rewire every task to the single config authority (remove the IVGS_*_URL getenvs / inline literals / latentsync_config; implement-or-delete get_model_config); repair the VLLMClient / get_model_config / config.X interfaces; wire stages into celery_app.include as each is validated; smoke per node via the now registry-sourced tests/smoke/test_gpu_nodes.py. Residual shakeout caveats (i)-(v) under the P2.2 carry-forward also apply here. |

## P3.4 — Endpoint test coverage for 9 untested endpoint modules

| | |
|---|---|
| **Source** | v1.0 §4 (Defect #8 spec v1.1 §5) |
| **Status** | OPEN. Now unblocked by Defect #8 closure. |
| **Scope** | 9 endpoint modules without test files: `alerts`, `backup`, `jobs`, `languages`, `manifests`, `nodes`, `quotas`, `rollback`, `ws_logs`. Note: `backup` is now extensively exercised by Stream B tests (test_api_backup.py has 13 tests). Priority: `jobs` (High), `rollback` (High), `alerts`/`manifests`/`quotas` (Medium), `languages`/`ws_logs` (Low). `test_nodes.py` should pair with Phase 8. |
| **Carry-forward action** | Treat `test_jobs.py` and `test_rollback.py` as next-priority. |

## P3.5 — Rogue branch attribution investigation (`node01-ops <ops@ivgs>`)

| | |
|---|---|
| **Source** | v1.0 (S9 §4.4) |
| **Status** | OPEN — investigation only; branch itself force-deleted in Session 9. |
| **Scope** | 10 commits on the deleted rogue branch were authored by an unknown identity. Could be DeepAgent operating against operator's "no code changes" instruction. Diagnostic steps: (a) Check DeepAgent activity logs for 2026-05-22 to 2026-05-23. (b) Check shell history for `git config user.email ops@ivgs`. (c) Check `/var/log/auth.log` for SSH sessions during push timestamps. |
| **Carry-forward action** | Operator-driven only. Does not block any work. |

## P3.6 — Cosmetic / UI polish

| | |
|---|---|
| **Source** | Phase 14 Stream B closeout (this session) |
| **Status** | OPEN. |
| **Scope** | Banner auto-dismiss in UI; action message badge polish. |
| **Effort** | Each is ~5 min. |

---

# Operator tasks (not Claude-actionable)

| Item | Notes |
|---|---|
| GPG private key off-network backup | The signing key 4F2243FAB5A25808 should have a copy stored off the production node. Operator task; security-sensitive. |

---

# Items closed since v1.0 (2026-05-26)

| Item | Closed in | Evidence |
|---|---|---|
| Node Configuration admin GUI (commissioning tool) -- NEW feature | 2026-05-30 (this session) | Admin-only `/admin` Node Configuration page (4th card + sidebar item + `/admin/nodes`) over `GET/PUT/POST /api/v1/node-config`. Shows the applied NODE_0x_IP registry (from the API container env), stages edits, applies them. node-01 is read-only (fixed infra host; `editable=false`, never staged, enforced server-side + in the apply script). Editable nodes 02-06 are IPv4-validated with live + server advisories for off-(node-01)-subnet (the /24 derived from node-01's own IP) and duplicate IPs. Least-privilege: the API never touches `.env` or docker -- PUT writes a pending file under the existing `/ivgs` mount; `POST /apply` drops an apply-request marker; a host systemd path+service watcher (`ivgs-infra/systemd/node-config-apply.{path,service}`) runs `scripts/apply-node-config.sh`, which backs up + rewrites `.env` and recreates ONLY the IP-consuming services (`fastapi-backend ivgs-scheduler celery-worker-default celery-beat`) via `--no-deps`. UI: applied-vs-pending, restart banner, Stage/Discard/Apply-with-confirm, polls until the API returns. Verified end-to-end on node-01 (staged .96/.99 -> applied -> reverted to .95). Commits `0538ae0` + `145b366`. Live images: `ivgs-api:v5.1.18-node-config`, `ivgs-frontend:v5.2.16-node-config` (GHCR push pending). |
| Config externalization PR (P2.2) -- phases 2a-2h complete | 2026-05-29 + 2026-05-30 (this session) | All node-IP references single-sourced to the NODE_0x_IP registry in node-01 `.env`, which composes 12 GPU URLs via the `x-gpu-service-urls` anchor; the obsolete 10.10.0.x scheme is eliminated from all code/config (only this ledger history references it) and is now guarded. Prior phases 2a-2g: fa6f4db, 49b736d, 7c374e5, bfcec00, e0fe26f, 68318bd, 41c34bd, 3426f0f, c85690b. This session 2b API half: shared/config.py trimmed (0c797df), ws_logs NODE_0x_IP resolution + test (18f17d9), fastapi env (a656514) -> ivgs-api:v5.1.15-config-2b deployed, /health green, 8/8 ws_logs tests. 2b workers (4 deployed increments): vLLM URLs canonical + fail-fast, anchor /v1 stripped (35954ed); API callback re-keyed to API_BASE_URL=fastapi-backend:8001 + latent-bug fix (1453530); 11 client base_urls canonical + fail-fast, latentsync 8300->7860 and remotion 3100->3002 (5d525a7); images ivgs-workers v5.1.2/v5.1.3/v5.1.4-config-2b each rebuilt + recreated + verified (worker ready, celery ping, worker->API 200, in-container client resolution). 2h: tests/smoke/test_gpu_nodes.py re-pointed to the registry + tests/spec_compliance/test_no_hardcoded_ips.py guard + widened pre-commit hook (e5816d8). Ledger increments d6c96c0, 936fb47, 84daf9d. Deferred to Phase H (P3.3 H.5): GPU-pipeline task-layer URL consolidation + broken-interface repair (gated on GPU node services online). Live tags: ivgs-api v5.1.15-config-2b, ivgs-workers v5.1.4-config-2b. |
| Pre-commit guard for 10.10.0.x IP literals (P2.14 / MP F.2) | 2026-05-30 (this session) | Delivered as P2.2 phase 2h: the pre-commit hook now blocks both the http:// and bare forms of the obsolete 10.10.0.x scheme (with `.md` and the guard test excluded so documented history still commits), and tests/spec_compliance/test_no_hardcoded_ips.py is the CI/full-suite backstop (pattern assembled from fragments so it cannot self-match). Commit e5816d8. Running the guard via pytest is currently blocked by P2.24; the hook enforces it regardless. |
| Config externalization phase 2e remainder: `restore.sh` GPU IPs from registry | This session (2026-05-29) | Both worker stop/start SSH loops derived targets as obsolete `10.10.0.${node}`; now read `NODE_0x_IP` from node-01 `.env` (single source) with a skip+warn guard when unset. `bash -n` OK; no `10.10.0.x`. Standalone DR script, not run end-to-end (SSHes to absent GPU nodes) — same shakeout caveat. Completes phase 2e. Commit `e0fe26f`. |
| Config externalization phase 2f: `cd-deploy.yml` node IP from registry | This session (2026-05-29) | CI 'Determine node IP' step hardcoded a `node02->10.10.0.2 ...` case map; now reads `NODE_0x_IP` from node-01 `.env` via absolute path (robust to runner checkout, since `.env` is gitignored), failing the job if a key is missing. YAML validated. Untested end-to-end (full CD never run; no GPU nodes). Commit `68318bd`. |
| Config externalization phase 2g (docs): stale node IPs -> real `192.168.1.9x` | This session (2026-05-29) | README node table + SeaweedFS line, runbook VLAN prereq, PRE_DEPLOYMENT_FIXES ollama example corrected from obsolete `10.10.0.N` to the spec static VLAN assignments. GITHUB_AUDIT_REPORT row claimed Table 2-4 was `10.10.0.0/24`; the spec actually defines `192.168.1.0/24` (§2.3 + env block), so that row was stale and was corrected — no spec change needed. Commit `41c34bd`. |
| Config externalization phase 2g (SeaweedFS): obsolete `10.10.0.1` in tomls | This session (2026-05-29) | `filer.toml [postgres2] hostname` -> `postgres` (compose service DNS); `volume.toml publicUrl` -> `192.168.1.90:8080` (node-01 LAN IP, irreducible cross-node literal, env-specific); `master.toml` only `0.0.0.0` binds (unchanged); both identical trees updated. Key finding: the LIVE stack (`docker-compose.node01.yml`) mounts NONE of these tomls (CLI-flag-driven, service-name addressing, filer default metadata store) — zero live impact; only legacy `base.yml` (P2.19; seaweedfs 3.80 vs live 3.71) mounts master+filer. DB password placeholder + dup trees + version skew remain for P2.19. Commit `3426f0f`. |
| Config externalization phase 2g (stragglers): last non-runtime `10.10.0.x` | This session (2026-05-29) | `download_models.sh` OLLAMA_URL default `10.10.0.5` -> `192.168.1.94` (env override kept); `llama-3.3-70b.yaml` comment subnet -> `192.168.1.0/24`; `v4_to_v5_migration.py` usage-example hosts -> `192.168.1.90` (docstring; real host is a CLI arg). All cosmetic/example; no rebuild. After this the only in-tree `10.10.0.x` is the 2b image code (`shared/config.py`, `ws_logs.py`, `ivgs-workers/clients/*`), its two coupled tests, this ledger, and a gitignored `*.backup` snapshot. Commit `c85690b`. |
| Config externalization — phases 2c/2d: node02-06 compose + all env templates | This session (2026-05-29) | node02-06 `docker-compose` node-01 refs `10.10.0.1` -> `${NODE_01_IP}`; `.env.template`/`.env.node01.template` topology now literal `NODE_xx_IP` (dropped `SUBNET_PREFIX`); node02-06 templates drop vestigial `NODE_IP` + four hardcoded node-01 URLs (compose composes them) and carry one `NODE_01_IP` orchestrator pointer (star topology). All five validated via `docker compose config`: parse OK, node-01 refs resolve to `192.168.1.90`, zero `10.10.0.x`. Commits `49b736d`, `7c374e5`. P2.2 still open for 2b+. |
| node02-06 compose — fatal duplicate `<<:` merge keys (never parsed) | This session (2026-05-29) | Found during 2c: every GPU compose file defined the YAML merge key `<<:` twice in one mapping (common anchors + `*gpu-resources`), so `docker compose` could not parse any of them — these stacks had never been loadable. Fixed by merging anchors under one `<<:` list (node02:3, node03:3, node04:8, node05:4, node06:0). All five now parse. Commit `7c374e5`. |
| `deploy-node.sh` repaired — dirs, multi-file, --env-file, orchestrator address | This session (2026-05-29) | Script was non-functional in this layout: looked for compose/env at repo root (they live in `ivgs-infra/`), never passed `--env-file` (substitution unwired), used a single `-f` (node-01 needs node01+override+monitoring), hardcoded obsolete `10.10.0.1` for node-01 API/scheduler. All fixed; orchestrator address derived from `NODE_01_IP` in the env file. `bash -n` + path/extraction checks pass; NOT run end-to-end. Commit `bfcec00`. |
| Config externalization — phase 2a: node-01 IP single-sourcing (P2.2, still open for 2b+) | This session (2026-05-29) | `.env` gained `SUBNET_PREFIX`/`NODE_xx_IP`/`*_PORT` as the sole node-IP source; `node01.yml` `x-gpu-service-urls` anchor composes the 12 GPU URLs and merges into fastapi/scheduler/worker/beat; `.env.node01` literal URLs removed. `docker compose config` resolved every URL to a correct `.9x` IP with no placeholders; all 16 containers healthy; URLs confirmed in-container; API up. Commit `fa6f4db`. |
| `ivgs-scheduler` redis mis-wire (localhost crash) | This session (2026-05-29) | Surfaced when the phase-2a recreate restarted the scheduler fresh: it reads `SCHEDULER_REDIS_URL` (default `redis://localhost:6379/3`) but compose only set generic `REDIS_URL`, so startup crashed at `redis.ping`. Added `SCHEDULER_REDIS_URL=redis://redis:6379/1` (Redis is its only external dep). Not an image regression — `:v5.1.0` == `:latest`. Now healthy, `redis_connected`, serving `/fleet 200`. Commit `fa6f4db`. |
| `GITHUB_REPO_URL` corrected (elearning -> elearning_v5) | This session (2026-05-29) | Value pointed at a non-matching repo; the self-hosted runner registers against this URL. Fixed in `.env` and `.env.node01`. Commit `fa6f4db`. |
| celery-beat false `unhealthy` (healthcheck) | This session (2026-05-29) | Beat was functional (scheduling heartbeat / gpu-metrics / dlq tasks); `unhealthy` came from the image's broken `-A worker` probe, inherited because beat had no compose override. Added pidfile process-liveness healthcheck to `celery-beat` in node01.yml; recreated -> healthy, FailingStreak 0. Root cause logged as P2.23. Commit `13c9d90`. |
| Obsolete compose `version:` removed (P2.9) | This session (2026-05-29) | Deleted `version: "3.8"` from `ivgs-infra/docker-compose.node01.yml`; `docker compose config` parses without the obsolete-attribute warning. Commit `fbbafb5`. |
| Nginx dynamic-resolution hardening (P2.12) | This session (2026-05-29) | `configs/nginx/nginx.conf`: resolver 127.0.0.11 + variable `proxy_pass` (7 sites) + `proxy_connect_timeout 2s` + http2 modernization. Verified by forcing fastapi to 172.20.0.50, nginx untouched -> auto-recovered to 200 within TTL. Commit `7173797`. |
| ivgs-backup-worker image to GHCR (P1.4) | This session (2026-05-29) | Pushed `ghcr.io/brucecostello2/ivgs-backup-worker:v5.1.0-stream-b` (digest `sha256:18ce86f0…`); override `image:` switched from `:local` to `${IVGS_BACKUP_WORKER_TAG}`, recreated healthy. Commit `379292a`. |
| Defect #8 — Test suite restoration | Session 11/12 (PR #48 merged to main) | 512 tests passing; 28 production bugs fixed. Merge commit `a836668`. |
| Diff 1.6 — GPU Fleet integration tests | Session 11 | Subsumed under defect #8 closure — service-layer tests cover the GPU history endpoint. |
| Phase 14 backup infrastructure (Stream A) | Session 13 | NAS mount, GPG key, Prometheus pushgateway, WAL archiving, cron jobs, asset_backup.sh — all working. |
| Phase 14 API-driven backup (Stream B) | Session 14/15 (PR #49 merged) | Dedicated `ivgs-backup-worker` container, API dispatches Celery tasks, durability-first verify, frontend vocab aligned. |
| `pidbox` ValueError in ivgs-workers | Session 14 | Patched in `ivgs-workers/celery_app.py`; deployed as `ivgs-workers:v5.1.1-pidbox-fix`. |
| Origin/master and sandbox branch cleanup | This session (2026-05-29) | Branches deleted; preserved as `archive/master-docs-final` and `archive/sandbox-reconciliation-final` tags. |
| ivgs-fastapi overlay mount removal | This session | Container runs purely from baked image `v5.1.14-stream-b`; no source overlay. |
| MP F.5 — Restore wal_archive.sh | Stream A (Session 13) | `/opt/ivgs/scripts/wal_archive.sh` present and exercised; WAL archiving enabled on PostgreSQL. |

---

# Source documents

| Path | Notes |
|---|---|
| `/mnt/transcripts/*.txt` | 14 session transcripts going back to 2026-05-26. Treat as primary historical record. |
| `/mnt/transcripts/journal.txt` | One-paragraph summary per transcript. Read first to navigate. |
| `IVGS_Outstanding_Fixes_SoT.docx` (v1.0) | Prior SoT, 411 lines. Authoritative as of Session 9 close. Operator-held. |
| `IVGS_INFRASTRUCTURE_REFERENCE.docx` | Companion infra doc, 214 lines. Operator-held. |
| `IVGS_CONFIG_EXTERNALIZATION.md` | Config externalization plan from Phase 14 Stream B. Operator-held. |
| `IVGS_Session{5..9}_Close_Forensic.{docx,md}` | Per-session forensic reports. |
| `IVGS_Defect_8_Test_Suite_Restoration_v1_1.md` | Test restoration spec (closed via PR #48). |
| `IVGS_Nginx_Hardening_Backlog.docx` | Phase F.10 implementation guide. |
| `IVGS_v5___Master_Implementation_Plan.txt` | Phases 0–I with priorities. |
| `archive/master-docs-final` tag | Snapshot of pre-reconciliation docs branch. Recoverable via `git checkout`. |
| `archive/sandbox-reconciliation-final` tag | Snapshot of DeepAgent sandbox branch. Recoverable. |
| `archive/fix-migration-enum-hybrid` tag | 14 commits preserved from Session 6. P2.9 audit item references this. |
| `sandbox-phase-{0..4}-{complete,gap-closure}` tags | Defect #8 reconciliation milestones. |

---

# Update protocol

Each session that closes should, before final commit:

1. **Add** any new deferred item discovered this session (with source = session transcript path/date).
2. **Update** status of any item touched (don't delete — move closure to the "Items closed" table with evidence).
3. **Re-snapshot** the priority counts at the top.
4. **Commit** to main as `chore(docs): update OUTSTANDING_WORK.md — <session summary>`.
5. **Update** `/mnt/transcripts/journal.txt` to note the session's relationship to this file (e.g., "closed P1.4; added P2.13").

The discipline is: nothing is "deferred" without going into this file. That's the rule.

*— End of ledger —*

---

## Phase H.0 — Make Main Honest (CLOSED 2026-05-31, commit `d349c46`, branch `feat/phase-h0-make-main-honest`)

No-GPU code-surgery pass on node-01's repo: repaired the half-finished provider refactor, added the missing config method, wired all 8 stages, removed off-plan residue, reconciled node02-06 compose. Build + import + 22-task-registration gates all green; no GPU hardware exercised. Single code commit `d349c46` (16 files, +1369/-754).

**Closed by H.0:**
- **A3 / SSOT P2.27 (deploy-blocker 02-06):** node02-06 `celery -A ivgs.celery_app` -> `celery -A celery_app` (9 sites). CLOSED.
- **H.5 "doable now" interface + wiring (code/config; live validation still GPU-gated):**
  - `clients/vllm_client.py`: re-added `chat()`/`chat_json()`/`chat_completion()`, a `VLLMConfig`-accepting ctor, `__aenter__`/`__aexit__`, and `VLLMResponse`/`VLLMChoice`/`VLLMUsage`/`VLLMMessage`. Fixes the stage1 `async with VLLMClient(config.vllm)` + `.chat()` finding (was at vllm_client.py one-class/240L). RESOLVED.
  - `clients/{cogvideox,wan21,flux,coqui}_client.py`: restored deleted error/enum/params/result symbols + call-time methods; fixed result bugs (`video_bytes`->`video_data`, `audio_bytes`->`audio_data`). RESOLVED.
  - `config.py`: added `WorkerConfig.get_model_config(name)` (registry-backed, env-overridable: cogvideox_5b/wan21/latentsync/sadtalker) used by video_generation_task/talking_head_task; added `_AttrDict` so `get_vllm_config_for_stage` answers both `["model"]` and `.model`. RESOLVED.
  - `celery_app.py` + `tasks/__init__.py`: `conf.include` + `task_routes` now register all 8 stages + video/talking-head + `pipeline_orchestrator_v2`; route keys corrected to real task names. (H.5 item E — stages 3-8 unwired — RESOLVED.)
  - `tasks/localization_pipeline.py`: off-plan, non-importable residue (`ivgs_workers.*`/`provider_factory`); REMOVED (git history retains it). It was an unfinished draft of spec §17.2; a real §17.2 localization orchestration is tracked as a deferred feature (re-dispatch existing stages with a target language_code — not a standalone task).

**Advanced (partial) by H.0:**
- **A1 / SSOT P2.15:** node02-06 fabricated `@sha256` placeholder digests stripped to tag-only (matching node-01). Compose portion done; base-image re-pin (part i) unchanged.
- **SSOT P2.23:** Dockerfile baked `HEALTHCHECK` module `worker` -> `celery_app`. Done (effective next workers build).

**Decision D1 (canonical orchestrator):** `pipeline_orchestrator_v2` is canonical for pipeline dispatch (full §6.1 parallel-media + composition-manifest); v1 retained for its 6 beat/ops tasks (heartbeat/DLQ/cleanup/retention/backup/metrics) that `beat_schedule` references. Both included. Final consolidation -> H.1; runtime "which handle_stage_completion the stages call back into" -> validated at Stage 2.

**Deferred (tracked; nothing dropped):**
- Live-GPU execution of every generate*/synthesize/chat* path + primary->fallback failover (needs node services online) — Stage 2/3.
- Spec §17.2 localization orchestration (unbuilt feature).
- latentsync/sadtalker ports: H.0 defaults to the task call-site values (8300/8301), which CONFLICT with the Build Plan wire contract (7860/7861) — reconcile when node-04 is built (env-overridable, no code change). cogvideox 8200 settled; wan21 8210 per Build Plan.
- `tasks/periodic_tasks.py`: imports clean but dormant (not in conf.include/__init__; beat uses v1's copies) — likely a duplicate beat home; consolidate in H.1.
- node02/03/04 vLLM image tag `v0.6.4` is the pre-Stage-1 value (fails on Blackwell); working `cu130-nightly` lands with the node-02 DR commit / per-node at Stage 4.
- node-01 rebind (127.0.0.1 -> 192.168.1.90 for Redis/Postgres/scheduler) — the one live-infra change, prerequisite for Stage 2.

---

## Stage 0 closure — node-01 rebind + node-02 DR (2026-05-31)

- node-01 service rebind (bf78a23): postgres 5432, redis 6379, seaweedfs
  master 9333/19333 + volume 8080 + filer 8888, scheduler 8002 now published
  on ${NODE_01_IP} (was 127.0.0.1). Reachable from node-02; gates G2-G4 cleared.
- node-02 DR (663fe9e): tested CogVideoX server recipe + node-02 compose
  (cu130-nightly vLLM, cogvideox-server, thin worker) committed; .env.node02
  gitignored, .example added.
- node-02 live compose: fabricated exporter @sha256 digests stripped.

### Open pre-prod / operator items (NOT Stage-2 blockers)
- .env.node01 is tracked in git — verify, git rm --cached, rotate, consider history purge.
- Rotate Postgres/Redis shared credentials (now VLAN-reachable).
- Push feat/phase-h0-make-main-honest (4 commits) + open PR.

### Stage 0 = COMPLETE. Next: Stage 2 (first real node-01+node-02 pipeline run).

---

## Stage 2 - First Real Cross-Node Pipeline Stage (Routed Gate) (TRANSPORT GATE MET 2026-06-01; API ENTRYPOINT P1.5 CLOSED + STAGE-2B GATE CLOSED 2026-06-01 - see 'Stage 2B closure' at end)

**Mandate:** prove one real pipeline stage executes across the live 2-node cluster —
a job dispatched from node-01's worker completes using node-02's GPU services. Direct
`docker run` client checks do NOT satisfy this; only a celery-dispatched stage task,
run by a node-02 worker against node-02's vLLM, does.

**Verdict: TRANSPORT gate MET (2026-06-01 02:03); API-ENTRYPOINT gate OPEN (P1.5).** A
`refine_transcript_task` dispatched from node-01 (`celery_app.send_task(..., queue='gpu_llm')`)
was executed by node-02's `celery-worker@node02`, which called node-02's vLLM (`http://vllm:8000`,
qwen-1.5b) and returned a refined transcript; the result was written to the shared `ivgs` DB and
retrieved by the node-01 caller. Task `1c694bea`: status=success, successful_count=1, no retries,
0.24s; real refinement ("um so basically the the product is a a video thing..." -> "So basically,
the product is a video-making tool that converts text into videos automatically."), model
qwen-1.5b, finish=stop, 70+18 tok. **This proves the cross-node TRANSPORT — celery routing + vLLM +
shared result backend. It does NOT prove the product entrypoint:** the dispatch was a *manual,
direct stage-task* `send_task` (not even via the orchestrator), so the API trigger and the
orchestrator self-driving were never exercised. Per the revised paint-by-numbers + P1.5 amendment
(2026-06-01), a manual-dispatch pass does NOT close Stage 2; the real entrypoint (P1.5) is the named
next blocker, recorded below — not deferred to Stage 5.

### P1.5 — API never dispatches the orchestrator (VERIFIED 2026-06-01, branch a821b43)
Read-only greps on node-01 confirm a single root cause: the worker orchestrator is built; the API
never calls it.
- **Start trigger STUBBED:** `ivgs-api/app/services/project_service.py` `trigger_pipeline` (L221)
  validates state, advances the DB project state, logs, and returns with NO dispatch. L285 is the
  only dispatch ref, commented: `# celery_app.send_task("pipeline.execute_stage", ...)` — stale
  (that task does not exist; it passes a job id, not the job context). Fix: dispatch
  `tasks.pipeline_orchestrator_v2.dispatch_pipeline` with the job context.
- **Worker orchestrator BUILT (exonerated):** `pipeline_orchestrator_v2.py` has `dispatch_pipeline`
  (L157), `handle_stage_completion` (L236), `dispatch_media_generation` (L356),
  `build_composition_manifest` (L502), media join `_handle_media_generation_completion` (L617), and
  `STAGE_TRANSITIONS` (L57) with the deliberate post-storyboard user gate
  (`STORYBOARD_GENERATION -> None`, L62). No worker orchestration work needed.
- **E2E per-stage route ABSENT:** no `/projects/{id}/pipeline/{stage}` route (the Phase-15 suite
  POSTs to a route that isn't there). Small independent follow-on.
- **3->1 API state mapping unimplemented:** worker has its own `MEDIA_GENERATION_STAGES` grouping
  (L138, used in the fan-out join L276) but references the API's `ProjectState`/`project.state`
  nowhere; the 3 worker media stages -> 1 API `MEDIA_GENERATION` state mapping lives only in the API
  layer and is not done. Low severity.

**Worker->API callback contract also broken (NEW — runtime evidence + route greps; a Stage-2B
co-requisite the P1.5 doc under-weights).** An API-driven run that "pauses at the storyboard gate"
needs the orchestrator's status/checkpoint callbacks to land; they do not:
- `PATCH /jobs/{id}` (worker `update_job_status`) -> 405: jobs router exposes only `GET /{job_id}`
  and `POST /{job_id}/cancel`; no PATCH route. Contract mismatch.
- `POST /jobs/{id}/checkpoints` (worker `save_checkpoint`) -> 405: checkpoints live under a separate
  router/prefix (GET/POST/DELETE), not under `/jobs/{id}`; worker calls the wrong path.
- `GET /projects/{id}/prompts` (worker prompt fetch) -> 401: route exists (`project_prompt_router`,
  L449) but the worker's service token is rejected — auth gap (the stage falls back to inline
  prompts, which is why tonight's manual gate still ran).
Tolerated by a manual stage-task run, but must be reconciled (worker URLs vs API routes/auth) for
Stage-2B. So P1.5's "~a few hours" covers the start trigger only; the callback reconciliation is
separate, additional work. And the orchestrator's runtime self-drive (`dispatch_pipeline` ->
`handle_stage_completion` -> next stage) has never run (tonight bypassed it), so Stage-2B is its
first real test.

**Staging vs the revised paint-by-numbers (2026-06-01):** revised Stage 1 (node-02 pilot: vLLM chat
+ CogVideoX video via real clients) = done (tonight's groundwork); Stage 2A LLM half = done via
manual dispatch; Stage 2A video half (CogVideoX routed) = NOT done; Stage 2B (API entrypoint +
orchestrator self-drive to the gate) = OPEN = P1.5. Under the revised plan, Stage 2 is NOT complete.
P1.5 is node-01 `ivgs-api` code — independent of the node-02 clone and the v5.2.3-h0 image work.

### Groundwork (direct-client checks — necessary, NOT the gate)
These proved the H.0-restored clients in isolation over the VLAN. They were the prior
"COMPLETE" claim, corrected here: they bypass the worker->server routing the gate needs.
- VLLMClient.chat() -> HTTP 200 from node-02 qwen-1.5b ('Hello World!', finish=stop,
  23+4 tok), authenticated /v1/chat/completions over the VLAN. Both ctor forms resolve
  the api-key.
- CogVideoXClient.generate() -> 10,014-byte MP4 (magic 0000001c 66747970 isom) from
  node-02 cogvideox-server:8200, ~6s warm. POST /generate -> poll /status -> GET
  /download confirmed.
- _AttrDict dual dict+attribute access confirmed -> closes the H.0-deferred dict/attr
  question; no fix needed.

### Bug chain surfaced + fixed to reach the routed gate (committed)
1. vLLM bearer header dropped in H.0 (api_key read, never sent) -> 401. Re-added in
   _get_client. Commit 836641d, image v5.2.1-h0.
2. Worker --queues used stage/job vocabulary not canonical queue names -> GPU-routed
   tasks reached no worker. Reconciled cogvideox-worker->gpu_video, LLM->gpu_llm; wired
   IVGS_VLLM_API_KEY into node-01 anchor + node-02 worker. Commit 8eea9c0.
3. update_job_status(..., stage=...) called by 4 stage tasks but helper lacked the param
   -> TypeError. Added optional stage param into the PATCH payload. Commit e90576d,
   image v5.2.2-h0.
4. Pipeline API (fastapi-backend :8001) bound to 127.0.0.1 only, but stage tasks DO call
   it (status/checkpoints/prompts) -> must be worker-facing. Rebound to ${NODE_01_IP}:8001.
   Commit fe95a95.
5. node-02 gpu_llm worker was on the ivgs-api image with a partial vLLM env (stray /v1,
   missing secondary/midsize/api-key/API_BASE_URL). Re-pointed to ivgs-workers + full env.
   Commit 8ae4f25.
6. node-02 workers had NO explicit IVGS_CELERY_RESULT_BACKEND -> config fell through to
   the ivgs:ivgs@node-01:5432/ivgs_results dev default (wrong DB + wrong password):
   results invisible to the node-01 caller + backend auth failure. Pinned both workers
   to the ivgs DB via ${POSTGRES_PASSWORD}/${NODE_01_IP}. Commit 9514324.

Node-local pilot overrides (.env.node02, gitignored — test-model accommodations, NOT
committed; revisit for production Llama-70B):
- .env.node02 POSTGRES_PASSWORD had diverged from .env -> aligned to the correct value.
- IVGS_VLLM_PRIMARY_MODEL=qwen-1.5b — stage requests defaulted to Llama-3.3-70B which the
  test vLLM does not serve (would 404).
- IVGS_VLLM_MAX_TOKENS=2048 — the 8192 default equals the served max_model_len (8192),
  leaving zero room for the prompt -> vLLM 400 on every call.

### Deferred CODE fixes (next image, ~v5.2.3-h0 — these bite production too)
- max_tokens: lower the IVGS_VLLM_MAX_TOKENS default (config.py:90) and/or clamp against
  served max_model_len in vllm_client (Llama-70B with --max-model-len 8192 hits the same
  wall).
- vllm_client failover lets offline node-03/04 ConnectErrors overwrite last_error, so the
  surfaced "All connection attempts failed" MASKS the primary's real HTTP status -
  preserve/report the primary error.
- cogvideox-worker VLLM_PRIMARY_URL is http://${NODE_02_IP}:8000 (host LAN IP) -
  unreachable from inside the container (hairpin). Change to http://vllm:8000 (service
  name) BEFORE the Stage-3 video gate.
- Pipeline API (tolerated, not gate blockers): PATCH /jobs/{id} -> 405, POST
  /jobs/{id}/checkpoints -> 405, GET /projects/{id}/prompts -> 401 (stage falls back to
  inline prompts), transcript writeback -> 401; and gpu_reservation_skipped "'str' object
  has no attribute 'value'". Reconcile API routes/auth + the enum bug.

### Infra state (post-gate)
- 2-node celery cluster LIVE + routed: celery-worker@node02 -> [gpu_llm];
  cogvideox-worker@node02 -> [gpu_video]; default-worker@node01 -> [default,
  notifications, cleanup]. Broker redis://node-01:6379/0 cross-VLAN; result backend =
  shared ivgs DB on node-01 (both nodes).
- Fleet uniform on image v5.2.2-h0; node02 compose adds the result-backend/broker pin
  (commit 9514324, config-only, no new image).
- Image digests (SS19.5 pinning):
  v5.2.1-h0 = sha256:1fef99f174cd6e507cf927bd43135369b856bb643b0118404f4bc1284e71e6dc
  v5.2.2-h0 = sha256:046b53036f58316a0407bd13549381b5b8b0b6a09415ab5166b2f49ff71cf4fd
- Branch session commits: 836641d, 8eea9c0, e90576d, fe95a95, 8ae4f25, 9514324.

### Stage 3 milestone -- full routed VIDEO-stage completion (DEFERRED: needs offline nodes/fixtures)
1. cogvideox-worker VLLM_PRIMARY_URL hairpin fix (above) — prerequisite; its vLLM prompt
   step would fail the way Stage-1 did.
2. node-04 midsize vLLM — video_generation_task's prompt step uses VLLM_MIDSIZE_URL ->
   ${NODE_04_IP} (offline). Pilot workaround: override midsize->node-02. Real fix: node-04.
3. Pipeline fixture — a real job row + valid scenes/storyboard from upstream stages (the
   API 405/401 gaps above will surface for a non-tolerant real run).
4. Downstream per-scene path — SeaweedFS asset upload (volume publicUrl cross-host flag),
   checkpoint save, handle_stage_completion dispatch (-> default queue, node-01 consumes).
5. Unconsumed queues — gpu_image/gpu_tts/gpu_talking_head/composition have no workers
   until nodes 04/05/06 + a node-01 composition worker are online.

### Carried-forward pre-prod / operator items
- .env.node01 is git-tracked (secret leak) AND carries a stale
  IVGS_WORKERS_TAG=v5.1.1-pidbox-fix (cosmetic; running image is correct). git rm
  --cached + rotate + bump/remove the stale tag.
- Rotate Postgres/Redis shared creds (VLAN-reachable post-rebind; Redis has no auth).
- SeaweedFS volume publicUrl cross-host verification.
- Push feat/phase-h0-make-main-honest + open PR; apply SS5 SSOT amendments.
- SS19.5: pin v5.2.2-h0 digest in compose.
- Pipeline API JobUpdate schema should accept 'stage' (verify when ivgs-api in scope).


---

## Stage 2B closure - API entrypoint (P1.5) -> orchestrator -> storyboard gate (CLOSED 2026-06-01, branch feat/phase-h0-make-main-honest @ 564e343)

**Verdict: Stage 2B CLOSED.** A single real POST /api/v1/projects/{id}/trigger drives the pipeline end to end across node-01 + node-02 to the deliberate post-storyboard user gate, observably and without error. Dispatch method = API (not manual send_task). This SUPERSEDES the "API ENTRYPOINT OPEN - P1.5" verdict in the Stage 2 section above and the provisional P1.5 entry, per the Stage-2 Gate Amendment.

**Evidence (run 2026-06-01 21:33 UTC; project 90a0e5b1; job a2af8e3b):**
dispatch_pipeline -> stage1 transcript_refinement (vLLM 200, node-02) success -> self-dispatch handle_stage_completion -> next_stage=storyboard_generation -> stage2 storyboard_generation (vLLM 200) -> storyboard_validated (7 scenes) success -> self-dispatch handle_stage_completion -> STAGE_TRANSITIONS[storyboard_generation]=None -> pipeline_paused_at_gate (gate_status=storyboard_review, action=user_gate) -> render_jobs.status=success persisted, NO job_status_update_failed, no media stage dispatched. Job reached success in ~5s.

**P1.5 status:** start-dispatch CLOSED + proven. project_service.trigger_pipeline now dispatches tasks.pipeline_orchestrator_v2.dispatch_pipeline (commit 699986b; the old commented '# celery_app.send_task(pipeline.execute_stage, ...)' is no longer the path), and the API producer's broker_transport_options now match the worker fleet incl. global_keyprefix=ivgs_workers_ (commit 76d2735) so dispatched tasks reach the queues workers poll. Remaining P1.5 items (do NOT block 2B): (2) storyboard-approval -> dispatch_media_generation resume (with Stage 3); (3) ORCH-5 worker->project.state mapping (projects.state still reads TRANSCRIPT_REFINEMENT after a full run); (4) /projects/{id}/pipeline/{stage} route (or realign the Phase-15 suite).

**Bug chain fixed this session (branch feat/phase-h0-make-main-honest, pushed a821b43..564e343):**
1. 76d2735 - API producer broker_transport_options/global_keyprefix aligned (dispatched tasks stranded on un-prefixed redis keys before); + dispatch_pipeline L180 .value-on-str (current_stage is a str field) guarded.
2. 607d537 (v5.2.5-h0) - stage1_transcript/stage2_storyboard now inject their stage value and self-dispatch handle_stage_completion (v2) so the pipeline advances (they previously returned with no 'stage' key and no dispatch; stage7/8 already followed this convention).
3. 13678d0 (v5.2.6-h0) - stage2 _save_storyboard_scenes used scene.media_type.value, but StoryboardScene.media_type is a plain str -> AttributeError while persisting; use the value directly.
4. 564e343 (v5.2.7-h0) - user-gate wrote the review-gate name (storyboard_review) into render_jobs.status, but job_status is the execution enum (pending/running/success/failed) -> Postgres InvalidTextRepresentationError -> 500 -> status never persisted (job stuck running). Now persists 'success' at the gate (the stage's job succeeded; the pipeline pauses); gate_status retained in log+return; review state belongs on projects.state per spec 4.3 (ORCH-5).
(Carried in: 5847f40 service-or-user auth so the worker service token authenticates.)

**Image digests (SS19.5 pinning):**
- ivgs-workers:v5.2.7-h0 = sha256:7dba84c0f497a76a5a6a3bfd33ce387aad4a97635ebff4f4fe4c85930f0b7369
- ivgs-workers:v5.2.6-h0 = sha256:57406760728175b6c1e6dad88d2788fb2c7b82302941ea8c1bd1161e73ecace4
- ivgs-workers:v5.2.5-h0 = sha256:58bceef1247f6c4f29420433fc6e21f2d6d4a0c4e8dd1b5d02f1a404de9c272c
- ivgs-workers:v5.2.4-h0 = sha256:3530c1d7aeeb567609cf38bb20302d8f5bcca18e6aca64ac0888eaca18a63622
- ivgs-api:v5.1.20-producer-fix = sha256:85d26ae1e0c2192e9c6a1c932ae9d56ecafbec315531f8af7918faa979238ee2
- Deployed: node-01 API v5.1.20-producer-fix + celery-worker-default/celery-beat v5.2.7-h0; node-02 celery-worker@node02 v5.2.7-h0, cogvideox-worker v5.2.2-h0, cogvideox-server cogvideox-pilot-1, vllm-primary qwen-1.5b (test model).

**Honest caveat - storyboard scene persistence not yet working (scene_count=0).** The storyboard is generated + validated, but the worker POSTs scenes to /projects/{id}/scenes and the API storyboard router exposes only GET /scenes, PATCH /scenes/{sid}, POST /scenes/reorder, POST /scenes/{sid}/regenerate - NO create route - so the write hits the worker's swallowed scene_save_failed branch. The gate is proven; persisting the artifact is the first API-batch item and a Stage-3 prerequisite (media reads storyboard_scenes). The media_type column is the enum {image, video_clip, animation} (scene default image is valid).

**Next: API batch (one ivgs-api rebuild; none needs the offline nodes 03-06):**
- Add POST /projects/{id}/scenes (service-auth create) -> persist storyboard_scenes.
- SeaweedFS transcript_service .upload -> upload_to_filer (transcript upload broken; workaround = seed transcripts via SQL).
- Repoint GET /projects/{id}/prompts + PATCH /transcripts/{id} onto get_service_or_user (worker 401s; non-fatal).
- Add POST /jobs/{id}/checkpoints (worker 405s; checkpointing disabled).
- Optionally accept celery_task_id on PATCH /jobs/{id}.

**Carried follow-ons (tracked):** ORCH-5 worker->project.state mapping; P1.5 item 2 media resume (Stage 3); GPU fleet/heartbeat registry empty -> gpu_reservation_skipped (non-fatal); test-model refinement quality (qwen-1.5b returns a generic non-refinement - model/prompt, not pipeline; real model per AD-01); v1/v2 handle_stage_completion reconciliation (stage1/2 on v2, stage7/8 on v1); drift/hygiene (node-02 cogvideox-server compose cogvideox-${IVGS_WORKERS_TAG} -> pin cogvideox-pilot-1; pushgateway orphan; un-prefixed redis backlogs; bump cogvideox-worker + hairpin its vLLM URL before Stage 3); pre-prod secret rotation; SS19.5 digest pinning.

**Closure record:** /mnt/user-data/outputs/IVGS_Phase_H0_Closure_Addendum.md Part B (runtime closure, 2026-06-01).


---

### API batch outcome (2026-06-01, ivgs-api v5.1.22-scenes)

Executed the Stage-2B API batch in one ivgs-api rebuild (commits 45a4a02 -> 6832834; image ivgs-api:v5.1.22-scenes, digest sha256:e5767604260fb81030934ce6af8c5f198c6288486ebc42c2882eef9749a7bd2a). Verified by a real POST /trigger run (project 3814f845, job=success ~10s):

- DONE/PROVEN - storyboard scene persistence: added POST /projects/{id}/scenes (service-auth) -> StoryboardService.create_scene. Run persisted 6 rows into storyboard_scenes (scene_index 0-5, media_type in {image,video_clip,animation}). SceneCreate.scene_index relaxed ge=1 -> ge=0 (worker emits 0-based indices).
- DONE/PROVEN - transcript upload: transcript_service .upload(...) (nonexistent) -> upload_file(collection=hot); POST /transcripts/upload returns 201 with a real seaweedfs_fid (e.g. 2,01b0da86bc).
- DONE/PROVEN - transcript refined-text PATCH auth: update_transcript -> get_service_or_user; worker PATCH now succeeds (transcript_updated), refined text persists.
- DONE - celery_task_id accepted + written on PATCH /jobs/{id}.
- REVERTED/DEFERRED - prompts auth (GET /projects/{id}/prompts): the service-token repoint made the worker consume the unfiltered effective-prompt list (master-first; prompt_type ignored) and feed a non-storyboard prompt to qwen-1.5b -> empty storyboard (ValueError) where the bundled fallback yields scenes. Reverted list_project_prompts to get_current_user (image v5.1.21-scenes-auth superseded by v5.1.22-scenes). Custom-prompt fetch follow-on: (1) list_project_prompts must filter by prompt_type; (2) worker stage1/2 must select the matching prompt and fall back to bundled when absent/empty; (3) validate with the production model, not the 1.5B test model.
- DEFERRED - POST /jobs/{id}/checkpoints save: needs new request schema + CheckpointService method; non-fatal (worker 405; nothing reads checkpoints back yet).

Image digests (input to section 19.5 pinning): ivgs-api:v5.1.22-scenes = sha256:e5767604260fb81030934ce6af8c5f198c6288486ebc42c2882eef9749a7bd2a (DEPLOYED node-01); ivgs-api:v5.1.21-scenes-auth = sha256:007109ad3995349a4b81c6756a47d2c94246ed35ac22c1979376826ba7d7ef50 (superseded).

Net: full pipeline runs API -> orchestrator -> transcript -> storyboard (scenes persisted) -> user gate via real trigger; upload + refined-text persistence work. Genuine Stage-3 prerequisites remain: storyboard-approval -> dispatch_media_generation resume (P1.5 item 2); worker -> project.state mapping (ORCH-5); offline media nodes 03-06.

### P1.5 item 2 — storyboard-approval -> media dispatch: DELIVERED + tracked deviation (2026-06-03)

**Delivered** (commits 19bf90d api + 78c3684 workers; images ivgs-api:v5.1.24-scene-id, ivgs-workers:v5.2.8-mediafix). POST /projects/{id}/scenes/approve -> ProjectService.approve_storyboard -> dispatch_media_generation (image/animation -> gpu_image, video -> gpu_video). Proven e2e: 200 -> MEDIA_GENERATION -> 3/2/1 fan-out, accepted + scene_id-validated by the workers. Closes "Remaining P1.5 item (2)" above. (Three first-run bugs fixed in the same commits: scene_id serialization; STAGE_TASK_MAP image name +_task; WorkerConfig.redis_url.)

**TRACKED DEVIATION - intentional, kept by decision 2026-06-03 (tied to ORCH-5):** approve_storyboard's guard rejects only MEDIA_GENERATION-and-later, so it accepts earlier states incl. TRANSCRIPT_REFINEMENT and advances straight to MEDIA_GENERATION. Spec Table 4-3 (§4.3) sanctions only STORYBOARD_GENERATION -> MEDIA_GENERATION; accepting TRANSCRIPT_REFINEMENT skips STORYBOARD_GENERATION. Deliberate accommodation of ORCH-5 (projects.state stays stale at TRANSCRIPT_REFINEMENT after a run even with the storyboard persisted; the e2e relied on it). FIX-WHEN: once ORCH-5 advances state correctly, tighten the guard to require STORYBOARD_GENERATION per Table 4-3. A matching code comment marks the guard in project_service.py. (Render execution past the wiring - video_generation_task signature drift, vLLM mid-size serving, GPU heartbeat, node-02/03 DNS, checkpoint 405 - is a separate punch-list, filed later.)


---

### node-04 provisioning status + media-tier build backlog (2026-06-01)

node-04 (RTX 5000 Pro Blackwell, 48 GB; 192.168.1.93) was cloned from node-02 and DE-CONFLICTED. Identity now fully distinct from node-02 (no collision): hostname node-04; static netplan 192.168.1.93/24 (router also has a .93 DHCP reservation as backup); machine-id forced to a RANDOM value d863a3bb... (it had re-derived node-02's d0cdc853... from the cloned VM SMBIOS product_uuid -- non-blocking follow-up: regenerate the Proxmox VM SMBIOS uuid so product_uuid is unique too); fresh SSH host keys; inherited node-02 stack stopped+removed; cogvideox image (20G) + /opt/models/cogvideox-5b (21G) + old worker images pruned (node-04 does NOT run video per spec); 126 GB free; NFS /mnt/ivgs-shared (rw) + /mnt/models (ro) healthy at .93.

Authoritative stack = repo docker-compose.node04.yml: 10 services (vllm mistral-24b :8000, comfyui :8188, coqui-tts :5002, kokoro-tts :5003, whisperx :9000, latentsync :7860, sadtalker :7861, celery-worker@node04, node-exporter, nvidia-gpu-exporter).

MEDIA TIER IS NOT BUILT. node-04 cannot come up until this backlog is done. DEFERRED behind P1.5 item 2 + the node-02 resume->media smoke:
1. Build 6 media-server images from scratch -- NONE exist locally or in GHCR (confirmed via buildx imagetools across all tags); only servers/cogvideox/ exists as a template (Dockerfile CUDA 12.8/cu128 base for Blackwell sm_120 + server.py async-job contract POST /generate, GET /status/{id}, /download/{id}, /health + requirements). Build order: comfyui/FLUX first (Stage-3 primary), then coqui-tts, latentsync, whisperx; kokoro/sadtalker are fallbacks. ComfyUI/Coqui/WhisperX wrap mature upstream servers; LatentSync/SadTalker need custom wrappers. Worker contract lives in tasks/stage3_images.py + clients/flux_client.py (and stage5_voiceover/stage6_talking_head + coqui/latentsync/whisperx/kokoro/sadtalker clients).
2. Complete + reconcile model staging. ivgs-models/download_models.sh runs on node-01 (huggingface-cli -> /mnt/ivgs-shared/models; needs internet + HF token + gated-license acceptance for Llama/Mistral/FLUX-dev) and is INCOMPLETE: missing Kokoro, WhisperX large-v3, LatentSync, SadTalker, FLUX-schnell. Path drift: script stages to /mnt/ivgs-shared/models but compose mounts /data/models (HF_HOME) and a separate /mnt/models ro exists. Format drift: media_generation.yml wants flux1-{schnell,dev}-fp8.safetensors (ComfyUI single-file) but the script fetches the FLUX.1-dev diffusers repo.
3. Reconcile stale docker-compose.node04.yml: FAKE placeholder @sha256 digests on vllm + both exporters (sequential hex; will fail pull -> real digests or drop pin); celery-worker pinned to ivgs-api image + 'ivgs.celery_app' whereas the working fleet uses ivgs-workers + 'celery_app'; queue names image_generation/tts_synthesis/talking_head/caption_generation/quality_scoring vs the live gpu_* convention (must match dispatch_media_generation); vllm tag v0.6.4 vs running cu130-nightly; model id Mistral-Small-24B-Instruct vs -2501.
4. Author .env.node04 (all NODE_0X_IP, POSTGRES_PASSWORD from the node-01 secret set, IVGS_WORKERS_TAG + IVGS_API_TAG); register node-04 in the GPU heartbeat registry (currently total_nodes:0).


---

### node-02 FROZEN baseline (2026-06-02) - clone source for node-03

node-02 (RTX PRO 6000 Blackwell 96GB; 192.168.1.91) is a clean, proven, committed baseline:
- git: clean at origin HEAD f924fc2 (synced 32 commits; cogvideox-server pinned cogvideox-pilot-1; cogvideox-worker vLLM URL http://vllm:8000; node .env gitignored; .env.node02.example committed).
- .env.node02 template-aligned; qwen-1.5b test overrides kept (VLLM_GPU_UTIL=0.30, qwen, 2048 tokens).
- images: cogvideox-worker + celery-worker v5.2.7-h0; cogvideox-server cogvideox-pilot-1; vllm cu130-nightly; cogvideox-5b weights at /opt/models.
- PROVEN: vLLM drives transcript+storyboard (Stage-2B, API-triggered); CogVideoX returns a real clip via the real cogvideox_client (49f 854x480@8fps, 6.12s, ~886KB, 71.9s) -> Stage 1 + Gate-1 via-client CLOSED. Stage-2A CogVideoX-via-gpu_video-celery-task (DB scene) deferred to Stage-3 pipeline integration.
- minor: compose still has obsolete 'version:' key (cosmetic); cogvideox verified pins in /root/node02-precommit-backup not yet folded into committed servers/cogvideox/.


---

### node-03 cloned from node-02 + brought up (2026-06-02) - twin live at .92

node-03 (RTX PRO 6000 Blackwell 96GB #2, dedicated passthrough; 192.168.1.92) is live as node-02's twin:
- cloned from frozen node-02 (new MAC, DHCP .92); de-conflicted: hostname node-03, RANDOM machine-id (NOT systemd-machine-id-setup, which re-derives the cloned SMBIOS uuid), fresh SSH keys, cloud-init disabled, netplan static .92, inherited node-02-identity stack stopped/removed (images+weights kept).
- git inherited CLEAN at f924fc2 (freeze paid off - no reconciliation, unlike node-04). GOTCHA: clone branch had NO upstream tracking, so the first `git pull --ff-only` was a silent no-op (stayed f924fc2) and the stale compose got used; fixed via `git branch --set-upstream-to` + `git merge --ff-only`.
- docker-compose.node03.yml was a STALE TEMPLATE at f924fc2 (freeze only fixed node02's file; node03's was an older draft: vllm v0.6.4, cogvideox-${TAG} worker image, NO cogvideox-server, celery on ivgs-api, video_generation/llm_inference queues). Reconciled by DERIVING from the proven docker-compose.node02.yml with node-03 identity (commit 46eb806): vllm cu130-nightly, ivgs-workers:${IVGS_WORKERS_TAG} workers, cogvideox-server cogvideox-pilot-1 :8200 ADDED, gpu_video/gpu_llm queues, @node03, .env.node03, NODE_HOSTNAME node-03.
- .env.node03 from inherited .env.node02 (only NODE_HOSTNAME changed; same qwen-1.5b test rig).
- VERIFIED: vllm serves qwen-1.5b; cogvideox-server healthy; broker shows both twins (celery+cogvideox @node02 and @node03) + default-worker@node01 -> gpu_llm + gpu_video redundant across two 96GB nodes.
- node-03 minor follow-ups: exporters (nvidia_gpu_exporter:1.2.1 needs Docker Hub pull); peer-IP warnings (NODE_03/04/05_IP unset -> blank fallback URLs) benign-by-design (populate at full-fleet failover); VLLM_SECONDARY_URL=NODE_03_IP self (derivation artifact -> NODE_02_IP at failover); obsolete compose `version:` key (cosmetic, node-02/03); old worker images v5.2.0-2.6 prunable.


---

### GPU monitoring broken on Blackwell fleet (2026-06-02) - exporter panic + empty dashboards

Symptom: Node Monitor shows all nodes Online but VRAM/Util/Temp/Power read 0; GPU Fleet page shows NODES ONLINE 0/0, AVG UTIL 0%, no utilization history.
Cause #1 (exporter): committed compose pins utkuozdemir/nvidia_gpu_exporter:1.2.1, which auto-derives Prometheus metric names from nvidia-smi. Blackwell driver emits 'clocks_event_reasons_counters.sw_thermal_slowdown [us]' -> exporter builds an invalid metric name (space+brackets) -> panic -> CrashLoop. Confirmed node-03 (first to bring it up fresh). Affects all Blackwell nodes (02/03 6000, 04 5000). node-02 only looks OK because it still runs an OLDER dcgm-exporter container (committed exporter never recreated there). node-03's crashing exporter stopped (restart=no); node-exporter :9100 fine.
Cause #2 (heartbeat): GPU heartbeat registry still empty (total_nodes:0 -> gpu_reservation_skipped); nodes not registering GPU presence with node-01 scheduler, so GPU Fleet sees 0 nodes regardless of exporters.
Fix (monitoring hygiene / Stage 4.5, fleet-wide): (a) replace gpu-exporter with a Blackwell-safe option - restrict utkuozdemir --query-gpu to a safe field set (drop clocks_event_reasons_counters), bump to a newer tag that sanitizes names, or move to nvidia dcgm-exporter on a Blackwell-capable tag (fleet already used dcgm); update docker-compose.node02/03/04 + commit; (b) wire node GPU heartbeat registration so total_nodes>0. Dashboard GPU telemetry is NOT trustworthy until both land; node liveness works via a separate check.

## Stage 3 -- node-04 media tier (IN PROGRESS)

- [DONE 2026-06-02] ComfyUI/FLUX image service PROVEN end-to-end on node-04.
  Built locally: ghcr.io/brucecostello2/ivgs-workers:comfyui-v5.2.7-h0
  (ComfyUI v0.23.0, torch cu128 for Blackwell sm_120, FLUX weights MOUNTED not
  baked). The real deployed client (flux_client.generate_image,
  FluxGenerationParams) returned a valid 1024x1024 PNG in ~4s on the RTX PRO 5000.
  FLUX schnell weight SHA256
  ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72.
  NOT pushed to GHCR (see recovery decision); captured via docker save instead.
- [TODO] Reconcile docker-compose.node04.yml (stale template): real image tags,
  ivgs-workers worker image (not ivgs-api), media queues wired to
  celery-worker@node04, FLUX checkpoint mount, drop the crash-looping
  nvidia_gpu_exporter, add pull_policy: never on GPU-server services.
- [TODO] Build the rest of the node-04 media servers via the build loop
  (RECOVERY.md): Coqui-TTS, Kokoro-TTS, WhisperX, LatentSync, SadTalker,
  vLLM-midsize (Mistral-24B); plus the shared async/sync FastAPI wrapper skeleton.
- [TODO] flux_client provider-interface generate(): coerce text fields, e.g.
  negative_prompt=params.negative_prompt or "" (ImageParams default None caused a
  ComfyUI 400 via null CLIPTextEncode text). generate_image path is unaffected.

## Recovery / image-artifact strategy (DECIDED 2026-06-02)

- Large GPU images are NOT pushed to GHCR (free tier too small, storage billed).
  Recovery = Dockerfile in git + docker save artifact on owned storage +
  re-acquirable weights. Full procedure in RECOVERY.md.
- Convention: scripts/save-image-artifact.sh saves to
  /mnt/ivgs-shared/image-artifacts/ with SHA-256 + MANIFEST. Compose services use
  pull_policy: never so a node runs the locally built/loaded image.
- [TODO] Also capture existing custom GPU images this way: cogvideox-pilot-1
  (node-02 and node-03). vllm/vllm-openai:cu130-nightly is upstream/re-pullable
  (optionally save it too since its nightly tag rotates).

## DEFERRED -- comprehensive disaster recovery (after full fleet + AD-01)

- Design and implement a comprehensive DR solution using non-node location(s):
  likely BOTH a local NAS and an offsite target. Must cover ALL recoverable
  state, not just image artifacts: the git repo, /mnt/models weights, Postgres
  (ivgs DB), SeaweedFS/Redis state as appropriate, and per-node compose + .env.
  Closes the current gap where /mnt/ivgs-shared backups live on node-01's disk and
  do NOT survive a node-01 failure. Prereqs: nodes 02-06 all operational and
  AD-01 model management implemented.
## Update 2026-06-02 — node-04 media tier: shared wrapper skeleton + Kokoro DONE; NFS bulk-write wedge logged

### Done (commit `ada1896`)
- **Shared FastAPI wrapper skeleton** — `ivgs-workers/servers/common/`:
  - `base.py`: `create_app()` app factory + lifespan model load/unload + `/health` (with VRAM) + consistent JSON-500 handler + `get_model()`/`run()` helpers. Used by all five node-04 wrappers.
  - `jobs.py`: in-memory `JobStore` (TTL GC, thread-pool background runner) + `register_job_routes()` for `/status` `/download` `/metrics` (the `alignment_score` the §11.1 talking-head gate needs). Used by the async wrappers (LatentSync/SadTalker).
  - Factored from the proven `cogvideox` server; lifespan replaces deprecated `on_event`. Build context = `servers/` so wrappers `COPY common`. `cogvideox` left untouched (retrofittable later).
- **Kokoro TTS sync wrapper** — `ivgs-workers/servers/kokoro/`, port 5003:
  - `POST /tts_to_audio` → 24 kHz mono WAV; English-only fallback for Coqui (same wire contract, interchangeable client). Accepts the full Coqui payload, uses only text/language/speed.
  - cu128 Blackwell base (torch 2.12 nightly, sm_120 verified); `en_core_web_sm==3.8.0` baked so startup never pip-installs at runtime (self-contained); Kokoro-82M weights mounted via HF cache under `/data/models` (AD-01, not baked).
  - Proven end-to-end via the real `coqui_client` provider path: 212 KB / 24 kHz / 4.42 s valid WAV.
  - Recovery artifact banked: `/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_kokoro-v5.2.7-h0.tar.zst` (6.7G, zstd-verified, `sha256:e8e86256c5adca712eb7e299b2a7452e8e87077349f2a49d9163da856b7048d1`), MANIFEST updated. NOTE: this image was built via BuildKit/containerd (layers already compressed) so zstd gains little (~1.07×) vs the older classic-builder ComfyUI image (2.9×).

### OPEN ISSUE — NFS bulk-transfer wedge (intermittent; storage-layer reliability)  **[RESOLVED 2026-06-03 - root cause was the inter-switch path, NOT NIC offload; see Update 2026-06-03 at end]**
- **Symptom:** a single NFS4 TCP connection (node-04 → node-01:2049) wedged mid bulk write — node-04 Send-Q stuck (~333 KB unACKed), node-01 Recv-Q 0, while ICMP, small packets, and *new* TCP connections all worked. Surfaced on the first large `docker save | zstd` write to `/mnt/ivgs-shared`. A `readdir` (`ls`) on the mount also hung (hard mount → D-state).
- **Recovery:** self-cleared after ~15 min (kernel `tcp_retries2` gave up → hard mount reconnected → write resumed). Cost ~20 min and nearly left a truncated artifact.
- **Ruled out:** server health (node-01 fine: load 0.16, 28G RAM free, 370G disk free, nfsd 8 threads, both exports present); firewall (UFW default-deny incoming but allows `192.168.1.0/24`); MTU (1500 on both `enp6s18`, verified — the jumbo ping failed locally as expected).
- **Root cause: UNCONFIRMED.** Prime suspect = NIC offload: TSO/GSO/GRO all ON on both `enp6s18` (fits "small packets fine, bulk stalls"). BUT the earlier ComfyUI 7.4G save worked with the same settings, so offload-on is not deterministic. Other candidates: transient packet loss, host/hypervisor (VM) networking hiccup, TCP/NFS-client edge case. Intermittent — needs live capture or deliberate reproduction to confirm.
- **Impact:** can recur on any sustained large write to `/mnt/ivgs-shared` (artifact saves, pipeline stage outputs) or large reads from `/mnt/models`; hangs that mount ~15 min (or until manually reset). Any process touching it blocks.
- **Mitigations adopted:** save large artifacts local-first then copy (shrinks blast radius — the slow zstd never touches NFS); fast reset = `systemctl restart nfs-server` on node-01 (resets the connection without waiting out the timeout; does not affect Postgres/Redis/SeaweedFS).
- **Next steps when it recurs:** BEFORE resetting, capture `ss -ti` on the stuck socket + `ip -s link` (drop/error counters) + `nstat` — that's the real evidence. If offloads are implicated, disable on both nodes (`ethtool -K enp6s18 tso off gso off gro off`) and persist via netplan. A precautionary disable is available now but unconfirmed (costs some CPU), so deferred.
