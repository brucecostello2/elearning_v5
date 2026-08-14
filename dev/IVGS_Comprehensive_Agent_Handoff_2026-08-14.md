# IVGS — Comprehensive Agent Handoff

**Date:** 2026-08-14 (late evening) · **Author:** outgoing orchestrator (Claude, claude.ai) · **Operator / sole merge authority:** Bruce Costello
**Repo:** `brucecostello2/elearning_v5` at `/opt/ivgs` on node-01 · **HEAD:** `b09b70f`+, pushed, `origin/main` in sync
**Companion repo:** `brucecostello2/MBCP`, read-only clone at `/opt/MBCP`

Read this first, then §1's documents in order. Everything here was true when written. **Bruce's pasted terminal output and screenshots are evidence that outrank this document.**

---

## 0 — THE THREE LAWS (read before anything else)

### Law 1 — Every command is labelled with its node

**EVERY bash block you give Bruce MUST state which machine it runs on. NO EXCEPTIONS.** This is the most-repeated correction in this project's history.

| Node | IP | Role |
|---|---|---|
| **node-01** | 192.168.1.90 | This machine. CPU hub: Postgres 17, Redis, SeaweedFS (master/volume/filer), Nginx, FastAPI, Next.js, Prometheus, Grafana, Alertmanager, scheduler, beat, workers. **16 GB.** All git commits happen here. |
| **node-02** | 192.168.1.91 | LLM only (vLLM). Trails on older worker tags. |
| **node-03** | 192.168.1.92 | Video only (CogVideoX). Trails on older worker tags. |
| **node-04** | 192.168.1.93 | Image + TTS + talking head. RTX PRO 6000 Blackwell 96 GB. |
| **node-05** | 192.168.1.94 | **OFFLINE** |
| **node-06** | 192.168.1.95 | **OFFLINE.** Card swapped to RTX 6000 Blackwell 96 GB — **now CUDA, not Intel.** Redesignated: primary compositor + Remotion + second video node + profile-gated LLM failover. |
| **`.7`** | 192.168.1.7 | TrueNAS. Backup target: `/mnt/store/ivgs` and `/mnt/store/ivgs-archive`. 22 TB free. |
| **`.9`** | 192.168.1.9 | **RETIRED** CIFS NAS. Was 100% full. Do not write to it. |
| **`.51`** | 192.168.1.51 | MBCP management plane. MBCP commits happen there, never on node-01. |
| **`.53`** | 192.168.1.53 | MBCP authoring LLM (Qwen2.5-Coder-32B, vLLM :8010). Firewall admits only `.51`. |
| **Proxmox host** | `n5Pro` | 61 GB. **OOM-killed node-01 twice on 2026-08-14.** 32 GB swap since added. |

There is no `.61`. A full sweep on 2026-08-14 found zero references anywhere — repo, env files, fstab, mounts, systemd, hosts, cron, container environments.

### Law 2 — You deliver bash, not instructions

**Bruce runs everything. You give him complete, paste-ready blocks.** He is sharp and catches real bugs, but he is not a developer by trade and he does not want prose describing what to do. Prose describing a command is a failed delivery.

Every block must be:

- **Node-labelled** — first line, always: `# RUN ON: IVGS node-01 (192.168.1.90)`
- **Single and self-gating** — one paste, no mid-block decisions, no "if you see X then run Y"
- **Wrapped in `( ... )`** — an `exit` in an interactive shell **kills his login session**. This happened twice on 2026-08-14 and both times was misread as a crash. Same for `set -e` and `set -u`.
- **Plain ASCII** — no smart quotes, no em-dashes, no Unicode. Several scripts emit non-ASCII; pipe their output through `tr -cd '\11\12\15\40-\176'`.
- **Complete** — no placeholders except genuinely unavoidable ones (a fresh digest, a job id)
- **Safe to abort** — a half-executed block leaves a recoverable state

**Never paste code containing angle brackets through PuTTY.** TSX, heredocs, generics — all mangled. Ship code files via WinSCP with a SHA gate.

**Never leave him to diagnose.** Give the next concrete step. If a block's output could go two ways, give both follow-ups or gate inside the block.

**ALL-CAPS from Bruce is a sharp correction.** Stop, acknowledge, change course. Do not defend.

### Law 3 — Zero technical debt. Quality and robustness beat development speed. Always.

**This is the operator's most-repeated instruction and it is not a preference — it is the standard the work is judged against.** "Fastest to develop" has been explicitly rejected, repeatedly, in favour of the right fix.

What it means in practice:

- **Fix at root, never band-aid.** If a temporary measure is genuinely unavoidable, it goes in the ledger in the same session with a removal trigger. An undocumented workaround is a defect you have chosen to hide.
- **No parked bugs.** Nothing is "noted for later." If it surfaced, it goes in `OUTSTANDING_WORK.md` or a work-package report before the session ends. "I'll add it to the backlog" is a failure mode unless you name the entry.
- **Architectural completeness beats a working demo.** A partial implementation that passes a test but leaves the design incomplete is worse than not starting, because it looks finished.
- **Do not widen scope to seem thorough, and do not narrow it to seem fast.** If a fix needs six call sites changed, change six. If five of them are out of bounds, say so and stop — do not do four and call it done.
- **Leave the code cleaner than you found it**, within the stated scope boundary.
- **A fix is not done until you have observed it working.** Exit code 0 is not proof. Check the artifact. See §3.

**Why this is stated as a law rather than a preference.** This system accumulated a 75-day silent backup failure, ~1,957 lines of orphaned machinery wired to nothing, a test suite covering dead code while the live orchestrator has zero coverage, four accepted-but-contradicted documents, and five instances of a swallow-failure pattern — every one of which was an individually defensible shortcut at the time. The debt did not announce itself. It presented as a working system with green dashboards.

If you find yourself reasoning "this is good enough for now," you are the mechanism by which that recurs.

---

## 1 — MUST-READ documents, in order

### 1a. In the repo, committed — read these first

| # | Path | Why |
|---|---|---|
| 1 | `/opt/ivgs/dev/CLAUDE.md` | Cold-start brief. Fleet, never-touch list, traps, deploy rules, report protocol. Claude Code auto-loads it if started from `/opt/ivgs/dev`. **Verify it is committed** — it was created untracked. |
| 2 | `/opt/ivgs/docs/ivgs_v5_functional_spec.md` | 8,189 lines. §1.4 declares it the SSOT. **Note §6.1's header says "Seven-Stage" and is wrong** — there are eight; ADR-003 filed the correction and it was never applied. |
| 3 | `/opt/ivgs/docs/deployment/runbook.md` | Operations. §5 rewritten 2026-08-14 for the `.7` migration and the two-scheduler asymmetry. |
| 4 | `/opt/ivgs/docs/IVGS_v5_Addendum_AD-02_Node_Specialization_Draft3.md` | Authoritative fleet topology. Current. |
| 5 | `/opt/ivgs/docs/stage-numbering-map.md` | **Read before touching any stage task.** Filenames are not task identities. |
| 6 | `/opt/ivgs/configs/systemd/README.md` | Host config outside Docker that a node-01 rebuild would silently lose. |

### 1b. Applied 2026-08-14 — now in the repo

The documentation re-baseline landed at `b09b70f`. All of these are committed and readable:

| Document | Path |
|---|---|
| `OUTSTANDING_WORK.md` **v4.1** | repo root — v3.1 preserved as `OUTSTANDING_WORK_archive_v3.1.md` |
| Master Sequence Plan **v0.4** | repo root — inserts the Temporal migration as M3 |
| **AD-05 Orchestration Migration** | `docs/` — §18 amendment, **approved**. §8's scope boundary is binding |
| **ADR-005** engine decision, **ADR-006** superseding ADR-004 | `docs/adr/` |
| **ERRATA — node-01 capacity** | `docs/` — corrects a wrong premise carried by AD-05 and ADR-005 |
| **Agent Development Plan v1.0** | `dev/` — 21 packages tiered by verifiability |
| AD-01 Draft 2, AD-03 v0.4, AD-04 v3.1 amendments | `docs/` |
| Functional Spec Amendment v5.1 | `docs/` |
| AD-04-v3.0 (the current MBCP design) | `docs/` — v0.1 deleted |

**⚠ Four of these are amendment INSTRUCTIONS, not replacement files.** They sit in `docs/` describing edits that have not been made:

- **Functional Spec v5.1** — ten amendments, none applied. `grep -c "Seven-Stage" docs/ivgs_v5_functional_spec.md` still returns 2, so §6.1's header is wrong and **ADR-003 remains open**. `intel b70` / `oneapi` still appear in the spec, AD-01, AD-02 and `README.md` despite node-06 being CUDA since July.
- **AD-01 Draft 2, AD-03 v0.4, AD-04 v3.1** — amendments over their existing addenda, not yet merged into them.

Applying these is a work package. Until it is done, the base documents and their amendments disagree, and **the base document is the one a reader will find first.**

### 1c. Work package reports — in the repo, committed

`/opt/ivgs/dev/workpackages/reports/` — committed at `ad44bf4`. `/home/dev/workpackages` is a symlink to it, so the old path still works.

```
WP-BACKUP-REPORTING_2026-08-14.md      WP-BACKUP-SCHEDULE_2026-08-14.md
WP-ALERTING_2026-08-14.md              WP-00-SWALLOWED-FAILURES_2026-08-14.md
WP-BACKUP-VERIFY_2026-08-14.md         WP-WAL-ARCHIVE_2026-08-14.md
```

**`WP-00-SWALLOWED-FAILURES` is a standing REGISTER, not a closed report.** Add instances as found; do not close one without observed evidence that the failure now surfaces.

Read all six before proposing backup or alerting work — they contain corrections to earlier briefs that this document does not repeat.

### 1d. MBCP, for seam work only

`/opt/MBCP/dev/CLAUDE.md` and `/opt/MBCP/dev/workorders/WORK_PACKAGES.md`. Read before touching anything seam-related. MBCP's register is the model for how IVGS's should look — twelve packages ordered **by risk, not numbering**, each ending in *"a live proof on real hardware, not a passing unit test."*

---

## 2 — Exact current status

**Pipeline:** all eight stages execute end-to-end. Evidence on node-01: draft `f78eb063` (214.94s, 720p, corruption 6/6) and final `9007b2cf` (215.07s, 1920×1080, 30fps, AAC 48k). The final was good enough to serve as evidence in the AD-04 head-model decision.

**The critical blocker — ORCH-6.** `STAGE_TASK_MAP` dispatches `tasks.talking_head_task.render_talking_head`, and that live file imports `LatentSyncClient` directly. The AD-01 provider-factory binding sits in `stage6_talking_head.py` — **the dead duplicate nothing dispatches**. So MBCP's certified models flow to the Model Store, get approved, and stop. **MBCP's entire output is unconsumable by the stage it was built to serve.** Fix is to *promote* the binding into the live file, not delete the duplicate. Ledger P1.0, Master Plan M1.

**Backups — fixed and deployed 2026-08-14.** Was a 75-day database backup gap. Six root causes, all closed. Now: beat 02:00 database (in-container), cron 03:00 assets + 04:00 config + 05:00 verify (host), WAL archiving live via Postgres `archive_command`. Alertmanager deployed. **Nothing has yet fired unattended — the mechanism is proven, the clock is not. Check `backup_records` after 06:00.**

**Fleet:** node-01 and node-04 live. node-02/03 provisioned, trailing tags. node-05/06 offline.

**Orchestration:** Celery + Redis. Migration to Temporal approved (AD-05), scheduled M3 — **after** M1 closes and before the fleet rollout, so each node is configured once.

**Recent commits:**

```
b09b70f docs: apply the 2026-08-14 documentation re-baseline
ad44bf4 docs(dev): move work package reports into the repo
9dc90aa feat(alerting): deploy Alertmanager, add BackupStale, let BackupFailed clear
55ea53e fix(backup-verify): portable checksum, NAS-side compare, no 2 GB tmpfs
55ead2a fix(backup): raise on failure; scripts own backup_records; exact row counts
e1f4c58 chore(infra): untrack .env.node01; record host config in repo
1f0fd31 fix(backup): survive rsync exit 23/24 on NFS target
e613e84 fix(model-store): add ffmpeg to model_engine enum (migration 0027)
```

Note the five-week gap before `1f0fd31` — `e613e84` was 2026-07-10 and nothing landed until 2026-08-14.

---

## 3 — Working method (non-negotiable)

**Authority.** Bruce is sole merge authority. Agents author and propose. **Agents do not commit, push, merge, or deploy** unless he explicitly releases it — and on 2026-08-14 he did release commits for the backup work, so read the current instruction, not this default.

**Two-pass gate on every work package.** Findings and proposed fix *before* writing code — stop and show Bruce. Then what changed and how it was verified. This gate has already paid for itself: pass-1 analysis recommended running asset backups from the worker container, and pass-2 found the worker lacks all four required mounts. A single-pass agent would have shipped a job failing nightly.

**Evidence discipline.** Separate what was **verified live** from what was **inferred from reading code**. Cite `file:line`. **An exit code of 0 is not proof — check the artifact.** The current agent does this well; hold the standard.

**Reports.** `/home/dev/workpackages/reports/WP-<NAME>_<YYYY-MM-DD>.md`. See §1c — they should move into the repo.

**Ground truth.** Verify against committed code and running containers. Not against summaries, not against memory, **not against this document.** In one 2026-08 sweep, four documents were found asserting facts production contradicted: ADR-004 (TimescaleDB vs `postgres:17.2`), `stage-numbering-map.md` (files that don't exist), MBCP's `CUSTOM_NODES.txt` (nodes that don't exist), and every document stating node-01 had 16 GB when it had 31.

**Deploy.** Derive the compose invocation from container labels, never guess:

```
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
```

node-01 uses three `-f` files (`node01` + `override.node01` + `monitoring`) with `--env-file ivgs-infra/.env`. **Always `--no-deps`** on a single-service recreate or Postgres restarts too. After any recreate verify with `docker exec <c> env`, not by reading `.env` — compose only passes variables the YAML references.

**Working principles, restated often by Bruce and meant:** correctness over speed · fix, don't band-aid · no parked bugs · architectural completeness over speed · zero technical debt. "Fastest to develop" has been explicitly rejected.

---

## 4 — Hard lessons (each cost real time; ★ = 2026-08-14)

1. ★ **A green surface over a dead mechanism is this system's signature failure.** Five instances in one day: Celery logging "succeeded" for failed backups; a populated `wal/` directory while archiving had been dead for hours; `BackupFailed` firing into Prometheus with no Alertmanager to deliver it; a beat job returning `{"status":"ok"}` having done nothing; `verify_backup.sh` never pushing success so one failure pinned the alert forever. **Verify against `pg_stat_archiver`, `celery_taskmeta`, and the artifact — never against appearances.**
2. ★ **`exit` in a paste block kills Bruce's login session.** Looks exactly like a crash. Wrap in `( ... )`.
3. ★ **`set -euo pipefail` + `trap EXIT` makes every `if [ $? -ne 0 ]` dead code.** The shell exits before the check runs; the trap logs a generic failure. Capture with `|| rc=$?`.
4. ★ **A bind mount does not follow a remount of its source.** The `.9`→`.7` cutover orphaned `ivgs-postgres`'s WAL archive mount; archiving died silently for 4.5 hours. **Any remount needs a recreate sweep of every container mounting that path.** Both binds still use `rprivate`, so it can recur.
5. ★ **rsync to NFS returns 23 even on success** — `--archive` implies `-p -o -g` and the server owns those. Treat 23/24 as non-fatal.
6. ★ **The Proxmox host can kill node-01 with the guest logs completely clean.** No panic, no trace, no OOM in the guest — the kill came from outside. Diagnose host-side; `journalctl -k -b -1` in the guest shows nothing.
7. ★ **A fact repeated across six documents is duplicated, not corroborated.** node-01's memory. Measure hardware claims on the box, in the same session the argument is made.
8. **Filenames are not task identities.** Four stage files register Celery names that don't match their filenames. The orchestrator dispatches by registered name. Consult `stage-numbering-map.md`.
9. **The dead talking-head file is the better implementation.** `stage6_talking_head.py` is never dispatched but holds the AD-01 binding. Promote, don't delete. It also carries a wrong upload URL that previously broke Stage 5.
10. **Config causes outrank code causes here.** The 2026-06-05 image-generation "regression" got a forensic report written on the wrong premise; it was an environment-name mismatch. The 75-day backup gap was one word — `POSTGRES_HOST=localhost` against a Postgres publishing only on `192.168.1.90:5432`.
11. **Don't guess the compose `-f` set.** `base.yml` and `node01.yml` disagree on SeaweedFS version and volume naming; the wrong set has twice recreated infrastructure containers against wrong definitions.
12. **`git clean -fd` destroys untracked work.** node-01 has held untracked specification documents and render artifacts with no other copy.

---

## 5 — Open work

Full detail in `OUTSTANDING_WORK.md` **v4.1** (operator-held) and the development plan. Headlines:

| Priority | Item | Reference |
|---|---|---|
| **Critical path** | **ORCH-6** — promote the AD-01 binding into the live Stage-6 task | P1.0 · WP-02 |
| **P0** | `broker_visibility_timeout` 3600 < `time_limit` 3900 → duplicate GPU execution across node-02/03 | P0.1 · WP-05 |
| **P1** | Media join returns `0` on Redis error → advances on incomplete footage | P1.1 · WP-06 |
| **P1** | Checkpoint resume does not exist — no `POST /jobs/{id}/checkpoints` route was ever built | P1.2 · WP-07 |
| **P1** | GPU reservations swallowed at 6 call sites; registry empty (`total_nodes:0`) | P1.3 · WP-08 |
| **P1** | Stage-8 formal validation; 4K profile never exercised | P1.4 · WP-03 |
| **P2** | 15 of 16 Prometheus scrape targets down — monitoring is largely blind | new |
| **P2** | No out-of-hours alert channel; no SMTP; Grafana contact points unenumerated | WP-ALERTING |
| **P2** | ~1,957 lines orphaned (`RetryEngine`/`DLQService`/`FallbackChain`), 14 imports against a package that doesn't exist | P2.1 |
| **P2** | Zero test coverage on the live 1,397-line orchestrator; 859 lines of tests on the dead modules | P2.2 |
| **Open register** | Four swallowed-failure instances remain; detector proposed | WP-00 |
| **Cross-system** | S-1 token rotation (both hosts, one window) through S-10 | ledger §S |

**Unverified and contradictory — do not act on either side:** `CLAUDE.md` §7 says `release_gpu_reservation` raises `TypeError` at all three call sites; the ledger says the same signature drift does not reproduce on the deployed image. Neither has been tested. Bruce to resolve.

---

## 6 — First actions for the incoming agent

1. **Run the session-start gate** (runbook §1). Confirm `git rev-list --left-right --count HEAD...origin/main` reads `0 0` and running images match `ivgs-infra/.env`.
2. **Check last night's scheduled runs.** This is the outstanding proof from 2026-08-14:
   ```
   # RUN ON: IVGS node-01 (192.168.1.90)
   ( docker exec ivgs-postgres psql -U ivgs -d ivgs -c "select backup_type,status,started_at,completed_at,verified_at from backup_records order by started_at desc limit 8;"
     docker exec ivgs-postgres psql -U ivgs -d ivgs -tAc "select archived_count,failed_count,last_archived_time from pg_stat_archiver;"
     ls -la /mnt/backup/ivgs/db/ /mnt/backup/ivgs/assets/ | tail -20 )
   ```
3. **Apply the four outstanding amendment documents** (§1b). Ten spec edits, plus AD-01/AD-03/AD-04. Closes ADR-003 and removes the last `intel b70` / `oneapi` references. Mechanical, self-verifying, and it stops the base documents contradicting their own amendments.
4. **Then WP-02 (ORCH-6)** — top of the programme. Everything MBCP delivered is blocked behind it.

---

## 7 — What is deployed but unproven

Recorded so absence is not mistaken for pass:

- **No backup has fired unattended.** Beat and cron are configured and the mechanism is proven by manual dispatch; the clock has not run.
- **No IVGS restore drill against `.7`.** MBCP has run one, byte-for-byte. IVGS has not.
- **Checkpoint resume** — never worked, no route exists.
- **Five GPU nodes responding to the scheduler** — registry empty, nodes 05/06 offline.
- **DLQ routing** — `DLQService` is wired to nothing.
- **Localization** — never exercised end to end.
- **The 4K render profile** — never run.
- **`BackupStale` firing-state notification** — the resolved payload was captured, the firing one only for `BackupFailed`.

---

*Handoff 2026-08-14. Verified against `b09b70f`.*

**The three sentences that matter most, in order:**
1. **Law 3** — zero technical debt; quality and robustness beat development speed, always. Everything else in this document exists because that rule was relaxed somewhere.
2. **Law 2** — give Bruce bash, not prose.
3. **§4.1** — a green surface is not evidence.
