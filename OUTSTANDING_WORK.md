# IVGS v5 — Outstanding Work (Single Source of Truth)

| | |
|---|---|
| **Document version** | v2.0 — 2026-05-29 |
| **Authoritative as of** | Phase 14 Stream B closeout, main @ `1cb2c58` |
| **Repository / branch** | `brucecostello2/elearning_v5` on `main` |
| **Supersedes** | v1.0 (`IVGS_Outstanding_Fixes_SoT.docx`, 2026-05-26, Sessions 5–9). Items from v1.0 are reviewed below with current status. |
| **Live stack** | ivgs-api `v5.1.14-stream-b`, ivgs-frontend `v5.2.12-backup-vocab-alignment`, ivgs-workers `v5.1.1-pidbox-fix`, ivgs-backup-worker `local`. Alembic 0024. |
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
| P2 | 21 | Defect #5 [object Object]; Defect #9 nodes status lie; **Defect #10 test directory scope unification**; config externalization; Phase F.1–F.11 hygiene backlog; Phase E.1 infrastructure docs; **Phase E.2 RUNBOOK.md**; MP F.2/F.3/F.4 (pre-commit IP guard, digest pins, FlaggedAsset typing); forensic correction; tag taxonomy doc |
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
| **Status** | IN PROGRESS. Phase 2a done (this session, 2026-05-29): node-01 live stack single-sourced — `.env` now holds `SUBNET_PREFIX`/`NODE_xx_IP`/`*_PORT` as the sole node-IP source; `node01.yml` `x-gpu-service-urls` anchor composes the 12 GPU URLs and merges into fastapi/scheduler/worker/beat; `.env.node01` literal URLs removed (env_file cannot interpolate). All 16 containers healthy. Commit `fa6f4db`. |
| **Severity** | Pre-commit hook currently blocks `http://10.10.0.X` strings in commits. Some env-var naming is also inconsistent. Risk of spec drift between Compose, env files, and runtime. |
| **Scope** | Externalize IP literals into env vars; standardize env-var naming convention; document acceptable patterns; update pre-commit hook scope. |
| **Carry-forward action** | Remaining phases, each behind a verify gate: (2b) Python fail-fast — remove the hardcoded `10.10.0.x` fallback defaults in `shared/config.py` + `ivgs-workers/config.py` (the one phase with live-startup risk); (2c) node02-06 compose `${VAR}` conversion + obsolete `version:` removal; (2d) `.env*.template` topology propagation; (2e) `scripts/deploy-node.sh` + `restore.sh`; (2f) `.github/workflows/cd-deploy.yml`; (2g) docs; (2h) add `tests/spec_compliance/test_no_hardcoded_ips.py` guard (subsumes P2.14) + update pre-commit hook scope. |
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
| **Status** | OPEN — fully scoped in master plan. **Partially overlaps P2.1 (config externalization).** |
| **Scope** | `.pre-commit-config.yaml` local hook `no-bridge-ip-literals` that rejects any commit including a `10.10.0.x` literal. Test by attempting to commit a fake .env. |
| **Carry-forward action** | Implement as part of, or alongside, P2.1 (config externalization). |

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
| **Scope** | H.1: bring up node-02 (first GPU worker). H.2: resolve stale branches `fix/vllm-client-missing-symbols`. H.3: nodes 03–06. H.4: resolve `audit/v5-spec-compliance-fixes` and `remediation/comprehensive-spec-compliance` branches. |
| **Effort** | Weeks of work. Not session-blocking for current alpha posture. |

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
