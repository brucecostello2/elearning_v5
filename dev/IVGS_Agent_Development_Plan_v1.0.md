# IVGS — Agent Development Plan v1.0

| | |
|---|---|
| **Prepared** | 2026-08-14 |
| **Purpose** | Sequence the backlog into work packages an agent can deliver with minimum supervision, by classifying each package on whether the agent can **prove** it finished. |
| **Basis** | `OUTSTANDING_WORK.md` v4.1; Master Plan v0.4; AD-05; Step 10 cross-system register; live findings 2026-08-14 |
| **Companion** | `/opt/ivgs/dev/CLAUDE.md` (cold-start brief) · reports to `/home/dev/workpackages/reports/` |

---

## 1. The organising principle

**Supervision cost is set by verifiability, not by task size.**

Every defect found on 2026-08-14 shared one property: it *looked* successful. Celery logged "Task succeeded" for a failed backup. `save_checkpoint` returned `False` and no call site checked. `acquire_gpu_reservation` logged a warning and continued for months. `_decrement_media_task_count` returned `0` on error, which the caller read as "all scenes complete."

None was caught by monitoring. All were found by reading code.

The consequence for agent work is direct: **an agent that reports "exit code 0" has told you nothing.** Parallelism multiplies unverified output rather than reducing review load. So each package is classified by what the agent can demonstrate, and that classification sets its supervision level.

| Tier | Definition | Agent autonomy | Your involvement |
|---|---|---|---|
| **A — Self-proving** | Ends in a machine-checkable artifact: a passing test that fails without the fix, a checksum match, a diff against a reference output, a static check | Runs to completion, produces report | Review the report and the proof; commit |
| **B — Observable** | Ends in a state checkable in one command or one screen | Investigates and proposes; you run the verification | Verify, then commit |
| **C — Judgement** | Quality, architecture, scope boundaries, anything touching the migration or a stage body | Proposes only | Full review at each step |

Borrowed from MBCP's register, which already phrases exit gates as *"a live proof on real hardware, not a passing unit test."* That standard is the right one and IVGS should adopt it.

## 2. Agent topology

**Two agents, one per system.** node-01 for IVGS, `.51` for MBCP. `.51` already holds both repos; node-01 now holds `/opt/MBCP` read-only. Commits happen on the owning host only.

**Subagents enabled on both.** Investigation fans out; only the parent writes. This suits the audit-shaped packages — "find every instance of pattern X across both repos" — with no merge risk.

**Git worktrees for Tier A parallel work only.** `git worktree add` gives a second agent its own directory and branch off the same repo. Restricted to packages with disjoint file sets — WP-09 through WP-14 below. Everything touching `pipeline_orchestrator_v2.py`, the stage tasks, or `celery_app.py` runs sequentially, because those are where scope violations do damage.

**Cross-system items have a named owner.** S-1 through S-10 belong to neither register and will be dropped by both unless assigned. They are listed in §6 with an owner column.

### Guardrail note

`dev` is in the `docker` group and runs with `--dangerously-skip-permissions`. The Docker socket is a root-escalation path, so the agent effectively has root on node-01. `dev/CLAUDE.md`'s must-not list is advisory, not enforced. This is an accepted risk on a dev box, recorded so it is a decision rather than an oversight.

---

## 3. WP-00 — Make the failure class detectable *(do this first)*

**Tier A · IVGS · no dependencies · highest leverage in the plan**

Four independent instances of *swallow the failure, return a value nobody checks*:

| Location | Behaviour |
|---|---|
| `ivgs-backup-worker/tasks/backup_tasks.py` | Returns `{'status':'failed'}`; Celery records success |
| `pipeline_orchestrator_v2.py:869-880` | Returns `0` on Redis error; caller reads it as "all scenes done" |
| `utils/error_handler.py:435-441` | Returns `False`; unchecked at every call site |
| `utils/gpu_utils.py` + 8 call sites | `except Exception: log.warning`, continue |

**Scope.** A static check that fails CI when a function's error path returns a sentinel that any call site ignores. Start narrow — the four known shapes — rather than attempting general dataflow analysis.

**Exit gate (the proof).** The check fails on all four known instances at `e613e844`, passes after each is fixed, and runs in CI. Demonstrate by reverting one fix and showing the check catches it.

**Why first.** It converts a whole category of work from Tier C to Tier A. Without it, every "is it actually fixed?" question comes back to you personally.

---

## 4. Work package catalogue

### Track 1 — M1 critical path *(sequential, IVGS agent)*

| WP | Item | Ledger | Tier | Exit gate |
|---|---|---|---|---|
| **WP-01** | Backup reporting: tasks must raise; record coverage; `verified_at` not `completed_at`; real row counts | F1–F9 | **B** | Trigger a backup from the GUI; record shows `completed`; deliberately break it and confirm Celery marks the task **failed** |
| **WP-02** | **ORCH-6** — promote the provider binding from `stage6_talking_head.py` into live `talking_head_task.py`; delete the duplicate | P1.0 | **C** | A head model swap performed **entirely in the GUI** changes which engine Stage 6 invokes, evidenced in worker logs. Segment/OOM strategy, Pillar-2 overlay and upload URL unchanged |
| **WP-03** | Stage-8 formal validation; exercise the 4K profile; add a bitrate/quality assertion to corruption checks | P1.4 | **B** | 4K render completes and passes corruption checks; assertion fires on a deliberately degraded input. *Visual QA is operator-only* |
| **WP-04** | Frame-aligned segment splitting — integer frames at target fps | AD-03 §4.4 | **A** | Measured head A/V drift **< 1 frame** on a short job, down from ~0.62s |

**WP-02 is the top of the programme.** Until it lands, MBCP's entire certified-model output is unconsumable by the stage it was built to serve.

**Note on WP-04:** AD-03 §7 Q5 (authoritative target fps per profile) must be settled first — it is a single value and it blocks the arithmetic.

### Track 2 — M2 orchestration correctness *(sequential, IVGS agent)*

| WP | Item | Ledger | Tier | Exit gate |
|---|---|---|---|---|
| **WP-05** | Raise `broker_visibility_timeout` above the longest hard `time_limit`; assert at config load | P0.1 | **A** | Config-time assert fails when the invariant is violated; passes at the corrected value |
| **WP-06** | Media join: distinguish unknown from zero; per-`(job_id, scene_id)` SETNX idempotency | P1.1 | **A** | Test: simulated Redis error does **not** advance the pipeline; duplicate completion callback decrements once |
| **WP-07** | Build `POST /jobs/{id}/checkpoints`; assert on the return value at every call site | P1.2 | **A** | Kill a worker mid-stage; the job resumes without re-running completed stages |
| **WP-08** | Fix `release_gpu_reservation` signature at 3 sites; `finally` releases at the other 5 | P1.3 | **A** | Reservation count returns to baseline after a completed and after a failed job |

WP-07's exit gate is the one that matters most for M5 — resume-from-failure collapses the long-video iteration loop for *every* bug class, not just orchestration.

### Track 3 — Parallel-safe hygiene *(git worktrees, disjoint file sets)*

| WP | Item | Ledger | Tier | Exit gate |
|---|---|---|---|---|
| **WP-09** | Pin `IVGS_SCHEDULER_TAG`; restore `@sha256` base-image digests | P2.11, P2.30(c) | **A** | `enforce_sha_tags.sh` passes; no `:latest` in compose |
| **WP-10** | Reconcile or delete `docker-compose.base.yml`; fix the monitoring network reference | P2.29 | **B** | Deriving the invocation from labels matches the tracked files; stack recreates without touching Postgres |
| **WP-11** | Test-directory unification; dialect-aware engine factory | P2.26, P2.27 | **A** | A single `pytest` invocation collects all three suites and passes |
| **WP-12** | Migrate 16 ad-hoc `fetch()` sites to the api-client; pre-commit hook blocking raw `access_token` reads | P2.24 | **A** | Hook rejects a deliberate violation; `tsc --noEmit` clean |
| **WP-13** | Hygiene batch: `.bak` cruft, `.env.bak.*`, `/root` tarballs, dead `get_beat_schedule()` | P3.6, P3.15 | **A** | Named files absent; repo clean; nothing else changed |
| **WP-14** | GHCR image retention policy; bcrypt/passlib pin | P2.30(a,b) | **B** | Startup warning gone; retention policy documented and applied |

These six touch disjoint files and can run concurrently on worktrees. **Nothing in Tracks 1 or 2 may run in parallel** — they all touch the orchestrator or a stage task.

### Track 4 — Documentation application *(single pass, IVGS agent)*

| WP | Item | Tier | Exit gate |
|---|---|---|---|
| **WP-15** | Apply the twelve rebuilt documents per Step 9's ordered procedure | **B** | `grep -ril "intel b70\|oneapi"` returns nothing; no secrets staged; ADR set complete; `git status` clean |

**Ordering is load-bearing** — Step 9 Part E step 1 (`git rm --cached .env.node01`) is already done as of `e1f4c58`, so start at step 2.

### Track 5 — Cross-system *(named owner required)*

| WP | Item | Owner | Tier | Exit gate |
|---|---|---|---|---|
| **WP-16** | S-1 coordinated ingest-token rotation | **Operator** | **C** | Both hosts updated in one window; forced export returns 201; drain queue empty |
| **WP-17** | S-5 seam contract test — every engine value MBCP can export is accepted by the IVGS receiver | MBCP agent | **A** | Test fails when a value is added on one side only |
| **WP-18** | S-2 stage-taxonomy note in AD-01 §AD-01.16 and the glossary | IVGS agent | **B** | Both taxonomies documented with the mapping table |
| **WP-19** | S-7/D-8 — determine whether `ivgs-scheduler` consumes MBCP's declared VRAM figures | IVGS agent | **B** | Answered with `file:line`. If yes, WP-A becomes an M4 prerequisite |

**WP-16 must not be executed as an MBCP-only task.** Rotating one side alone breaks the seam silently — exports park in the drain queue and retry every 5 minutes, so the symptom is staleness, not an alarm.

### Track 6 — Storage completion *(IVGS agent)*

| WP | Item | Tier | Exit gate |
|---|---|---|---|
| **WP-20** | Fix `verify_backup.sh`: read the NAS directory, not staging; use real row counts | **A** | Verification passes against a known-good backup and fails against a corrupted copy |
| **WP-21** | Backup staleness alert on the age of the newest `full_database` record | **A** | Alert fires when the newest record exceeds 26 hours |

WP-21 is what would have caught the 75-day gap. Failure alerts don't fire for a job that stops running.

---

## 5. Sequencing

```
WP-00 (detectability)
  └─> WP-01 (backup reporting)  ──┐
  └─> WP-05..WP-08 (M2)         ──┤
                                   ├─> WP-02 (ORCH-6) ─> WP-03, WP-04 ─> M1 CLOSED
  WP-09..WP-14 (parallel, worktrees, any time)
  WP-15 (docs) ─ any time, before agents lean on AD-05
  WP-20, WP-21 (storage) ─ any time
  WP-16..WP-19 (cross-system) ─ WP-16 needs an operator window
```

**M1 closes when WP-02, WP-03 and WP-04 are done** and a short job runs end to end at acceptable quality with the head model selectable from the GUI. That run is captured as the **reference output** and becomes AD-05's verification target.

Only then does the M3 migration begin — and every migration package is Tier C, because the scope boundary in AD-05 §8 is the thing most likely to be violated and least likely to be caught by a test.

---

## 6. Report protocol

Every package writes to `/home/dev/workpackages/reports/WP-<NAME>_<YYYY-MM-DD>.md`, in two passes:

1. **Before code** — findings with `file:line` evidence, and the proposed fix. Stop and show the operator.
2. **After code** — what changed, diff summary, how each change was verified, what remains open.

**Mandatory in every report:** what was verified **live** versus what was inferred from reading code. An exit code of 0 is not proof — check the artifact.

The agent does not commit, push, merge, or deploy. The operator holds sole merge authority.

---

## 7. What this plan does not attempt

**Anything in AD-05's migration.** Tier C throughout, gated on M1 and M2, and requiring review-board approval that has been given but whose scope boundary needs enforcing by a human at each step.

**Quality judgements.** Visual acceptance of renders, model selection, architectural trade-offs. An agent can measure drift in frames; it cannot tell you whether the presenter looks right.

**MBCP's own backlog.** `WORK_PACKAGES.md` owns that, ordered by risk, and it is better structured than anything I would replace it with. WP-A (GPU smoke of the nine consolidated graphs) is its highest-priority item and blocks WP-B.

---

*Plan v1.0 — 2026-08-14. Start at WP-00. It is the package that makes the rest cheaper to supervise.*
