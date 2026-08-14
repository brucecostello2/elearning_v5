# IVGS v5 — Master Sequence Plan to Production

| | |
|---|---|
| **Document** | Master Sequence Plan — the high-level path from current state to a fully deployed, production-ready system |
| **Version** | **v0.4 — 2026-08-14.** Supersedes v0.3 (2026-06-08). Stage status corrected (all 8 stages execute); WS-H closed on its Phase-1 driver; **WS-T orchestration migration added and sequenced**; milestones renumbered (map in §9). |
| **Authoritative as of** | `main` @ `e613e844`; node-01 and `origin/main` in **exact sync** (0 ahead / 0 behind). Live: ivgs-api `v5.5.3-arch1`, ivgs-workers `v5.5.1-arch1`, ivgs-frontend `v5.4.2-themes`. Alembic head **0027**. **The tree at `e613e844` is byte-identical to the 2026-07-10 capture — no IVGS code has been committed since 2026-07-10.** |
| **Companion ledger** | `OUTSTANDING_WORK.md` **v4.0** (task-level SoT, rebuilt 2026-08-14). **This plan sequences workstreams and milestones; the ledger tracks individual items.** |
| **Operating principle** | *"Fix, don't park — clean as we go."* Walk the end-to-end happy path; fix bugs inline as they surface; defer nothing without recording it in the ledger. |

---

## 1. Where we are

**The pipeline executes end-to-end, all eight stages.** Transcript refinement → storyboard → media generation → composition manifest → TTS audio → talking-head render → prototype draft → **final render**. Evidence on node-01: draft `f78eb063` (214.94s, 1280×720, corruption 6/6, operator-confirmed) and final `9007b2cf` (**215.07s, 1920×1080, 30fps, h264 High, AAC 48 kHz stereo**), the latter used as evidence in the AD-04 head-model judgment.

> **Correction to v0.3.** v0.3 recorded Stage 8 as "wired but not yet validated" and the ledger showed Stage 6 as *BUILD REQUIRED*. Both are two months stale. **The remaining M1 work is validation and model-binding, not construction.**

**Model certification is delivered.** The MBCP (AD-04) was built, the talking-head bake-off was run and settled, and certified models flow MBCP → IVGS Model Store as candidates with real weight refs and checksums. Backfill complete (21 exports + 2 composition; 24 revoked correctly skipped). The Approve/Deprecate/Retire lifecycle is live and GUI-only. **WS-H's Phase-1 driver is closed.**

**But the certification chain terminates at a wall.** The live Stage-6 task (`talking_head_task.py`, the one `STAGE_TASK_MAP` dispatches) imports `LatentSyncClient` directly — the engine is **hardcoded**. The ARCH-1 provider-factory implementation lives in `stage6_talking_head.py`, the *dead duplicate* that nothing dispatches. **Certified models cannot be selected into production.** Swapping the head is a code change — precisely what AD-01 exists to prevent. This is the single item at the top of the critical path (ledger **P1.0 / ORCH-6**).

**The orchestration layer carries four correctness defects and substantial dead weight.** A code audit of `e613e844` (2026-08-14) found: a broker visibility timeout below two tasks' hard time limits (duplicate GPU execution); a media join that advances prematurely on any Redis error and is not idempotent; a checkpoint subsystem that is a silent no-op, so `resume` has nothing to resume from; and GPU reservation releases that raise `TypeError` at every call site. Separately, ~1,957 lines of retry/DLQ/fallback machinery are wired to nothing (with 14 imports against a package that does not exist), while the 1,397-line live orchestrator has **zero test coverage** and 859 lines of tests cover the dead modules. Full detail: ledger **P0.1, P1.1–P1.3, P2.1–P2.3**.

**Fleet.** node-01 = CPU hub (Postgres / API / Redis / SeaweedFS / scheduler / beat / `celery-worker-default` / `-composition`). node-02 = LLM-only. node-03 = video-only. node-04 = image + TTS + talking-head (96 GB RTX PRO 6000). **node-05 and node-06 remain OFFLINE**; node-02/03 trail on older worker tags. **node-06's card was physically swapped to an RTX 6000 96 GB**, so the AD-02 Draft-3 Intel→CUDA compose rewrite is mandatory and node-06 is redesignated as a second CUDA video node, primary compositor, and on-demand LLM failover. The `celery-worker-composition` on node-01 remains a bootstrap, not its permanent home.

---

## 2. Definition of "production ready"

A non-technical operator drives a course video from a raw transcript to a final 1080p/4K render — with a correctly placed, lip-synced talking-head presenter — **entirely through the UI**, reliably and repeatably, on the **full 6-node fleet**, with managed models, trustworthy monitoring, disaster recovery, and **no hand-edited secrets or runtime band-aids**. Concretely:

- **E2E:** Stages 1→8 produce a correct final video that passes corruption/validation gates.
- **Model agility:** a newly certified model enters production as a **GUI selection**, never a code change.
- **Scale:** 30-minute videos render reliably — parallel and **resumable from failure**.
- **Robustness:** no duplicate execution; no premature advancement; reservations actually reserve; state is truthful; failures are visible, not swallowed.
- **Breadth:** SadTalker fallback live; nodes 05/06 online; UI functional.
- **Hardening:** secrets out of git; real service tokens; trustworthy monitoring/alerting; DR in place; runbooks written; load/soak-tested.

---

## 3. Guiding principles

1. **E2E-first.** Keep one working happy path and extend it; correctness of the whole chain beats local optimization.
2. **Fix, don't park.** Bugs hit *during* any milestone are fixed inline. Anything genuinely deferred gets a ledger entry with a re-open trigger — never silent.
3. **Correctness > speed.** Verify against authoritative sources (committed code, git history, real logs); never reason forward from summaries.
4. **One image, both fixes.** When a deploy is required, fold all in-tree fixes into a single rebuilt tag.
5. **The ledger is the task SoT.** This plan is the map; `OUTSTANDING_WORK.md` is the backlog. Re-snapshot on every close.
6. **Scope discipline on replacement work.** *(New in v0.4.)* When replacing a layer, name what is replaced, what is preserved, and what is untouched — before starting. If a session finds itself editing outside the named boundary, stop: scope control has been lost.
7. **No half-migrations.** *(New in v0.4.)* A migration completes in one arc or is not started. The v1→v2 orchestrator migration has been half-done since June (ledger P2.3); that is the precedent to avoid, not repeat.

---

## 4. Workstreams

| ID | Workstream | Scope | Status |
|----|-----------|-------|--------|
| **WS-A** | E2E pipeline completeness + quality | The happy-path spine: Stages 1→8 producing a correct final; A/V sync, head placement, draft/final validation. | 🟡 near-complete — validation remains |
| **WS-B** | Talking-head subsystem | Render quality, segment correctness, SadTalker fallback, long-video scale, **model binding**. | 🟡 renders; binding blocked (ORCH-6) |
| **WS-C** | Documented-debt paydown | Ledger v4.0 P1/P2/P3 items. | 🟡 ongoing |
| **WS-D** | Model management (AD-01) | Model lifecycle, versioning, serving, selection. | 🟢 substantially built — Model Store + factory + admin GUI live; per-project selection GUI + weight-fetch remain |
| **WS-E** | UI | Project lifecycle, review gates, asset preview, approve/reject, download. | 🔴 not started |
| **WS-F** | Composition + motion-graphics + fallback tier (05/06) | node-06 primary compositor + Remotion; node-05 SDXL/Ollama fallbacks + overflow. **Note: node-06 is now CUDA, not Intel.** | 🔴 not started |
| **WS-G** | Production hardening | Secrets/tokens, monitoring/alerting, DR, runbooks, load/soak testing. | 🔴 not started |
| **WS-H** | Model evaluation & certification (AD-04 / MBCP) | Benchmark, validate, certify self-hostable models; produce the AD-01.7 attestation. | 🟢 **Phase-1 driver CLOSED** (bake-off settled, connected mode live). Platform work continues — RuntimeClass refactor Tasks B/C/D awaiting approval; CogVideoX adapter graph broken (ledger P2.8/P2.9). |
| **WS-T** | **Orchestration migration (Temporal)** *(new in v0.4)* | Replace the hand-rolled coordination layer with durable execution. Scope boundary in §6. | 🔴 not started — sequenced as M3 |

---

## 5. Milestones

> Milestones define **focus**, not rigid gates. Debt and quality work interleave with the spine per principle #2.

| Milestone | Goal | Status |
|-----------|------|--------|
| **M0** | Pipeline executes Stages 1→8 | ✅ **Complete** |
| **M1** | Close the happy path *at quality* | 🟡 In progress — ORCH-6 + Stage-8 validation |
| **M2** | Orchestration correctness defects | 🔴 Not started (~1 session) |
| **M3** | **Orchestration migration (Temporal)** | 🔴 Not started |
| **M4** | Full 6-node fleet on the new architecture | 🔴 Not started |
| **M5** | Long videos + talking-head scale | 🔴 Not started |
| **M6** | UI functional (+ AD-01 remainder) | 🔴 Not started |
| **M7** | Production hardening | 🔴 Not started |
| **M8** | Production launch | 🔴 Not started |

### M1 — Close the happy path at quality

- **ORCH-6 — make the head model selectable** *(ledger P1.0; top of the critical path)*. Promote the provider-factory binding from `stage6_talking_head.py` into the live `talking_head_task.py`, preserving the live task's proven segment/OOM strategy, AD-03 Pillar-2 overlay, and correct upload URL; then delete the duplicate. Verify against `shared/providers/factory.py` + `app/services/model_selection.py`. **This is what makes the completed bake-off consumable.**
  > *Note:* Stage 8 overlays a pre-rendered head asset by `asset_id` — it does not render the head. Addendum-B item B5 ("Stage 8 must bind via the factory") was misframed; the binding belongs at Stage 6.
- **Stage-8 formal validation** *(ledger P1.4)*. Operator visual QA of `final_1080p_9007b2cf.mp4` at full screen. **Encoder note:** measured video bitrate is 506 kb/s, but the profile constants are correct per spec (`ffmpeg_client.py:144-148` — `crf=18, vbv_maxrate="8M", vbv_bufsize="16M"`). CRF targets *quality*, not bitrate, and near-static content encodes low legitimately. **Resolve by inspection, not by the number.** Exercise the never-run **4K profile**. Add a corruption-check assertion on output quality so this is measured next time.
- **Frame-aligned segment splitting.** ~0.62s head A/V drift from `ceil(slice_s × 30)` per piece; compute boundaries in integer frames at target fps (AD-03 §4.4).
- **Capture the known-good reference output** — the verification target for M3. *(= ledger WS-T.3.)*
- **Exit:** one project completes 1→8; the final is reviewed and confirmed correct; the head model is a GUI selection; the reference output is banked.

### M2 — Orchestration correctness defects *(~1 session)*

The four defects found in the 2026-08-14 audit. These are fixed **regardless** of M3, because a working system is needed while migrating.

- **P0.1 — broker visibility timeout.** `broker_visibility_timeout = 3600` sits below `time_limit = 3900` on `talking_head_task` and `video_generation_task`. With `acks_late`, Redis redelivers while the original still runs — and `gpu_video` is consumed by node-02 **and** node-03, so the duplicate can execute **concurrently on the other node**. Raise above the longest hard limit with margin; add a config-time assert. **One config line — not a broker swap** (M3 removes the mechanism entirely).
- **P1.1 — media join.** `_decrement_media_task_count` returns `0` on Redis error and the caller reads `remaining <= 0` as "all done." Distinguish unknown from zero; add a per-`(job_id, scene_id)` SETNX idempotency guard.
- **P1.2 — checkpoints.** No `POST /jobs/{id}/checkpoints` route exists; `save_checkpoint` returns `False` and no call site checks it. Add the route (~40 lines) and assert on the return. **Highest-leverage item in this milestone** — resume-from-failure collapses the M5 iteration loop for *every* bug class, not just orchestration ones.
- **P1.3 — GPU reservations.** Fix the `release_gpu_reservation` signature at 3 sites; add `finally` releases at the other 5; decide whether reservation failure is fatal.
- **Exit:** no duplicate execution possible at current durations; the join cannot advance on incomplete media; checkpoints persist and `resume` works; reservations release cleanly.

### M3 — Orchestration migration (Temporal) *(new in v0.4)*

**Why now, and why not later.** Three limits cannot be fixed in place: Redis-as-broker has no liveness signal, only a guessed timeout; at-least-once delivery requires a hand-written idempotency guard at every fan-out, forever; and crash recovery must be designed per-stage, eight separate times. Every remaining milestone pushes on exactly these — M4 adds five nodes, M5 multiplies runtimes tenfold and adds two new fan-outs.

**The cost comparison is not "migrate vs. do nothing."** It is migrate (~8–14 sessions) vs. finish the bespoke layer (~9–13 sessions: wire P2.1's three orphaned services into eight stage tasks, build checkpoint write + resume semantics, join idempotency, orchestrator tests, plus the still-unwritten `render_segments` resume and parallel talking-head fan-out). The midpoints are close; the **risk shapes differ**. The bespoke path's uncertainty sits at the end and is unbounded discovery work; the migration's sits at the front and is bounded, estimable work.

**Before the fleet, before long videos.** Building nodes 02/03/05/06 as Celery workers means configuring them twice. Long-video testing without execution history or resume means paying a full multi-hour render per bug observation *and* per fix verification.

| Step | Item |
|---|---|
| **M3.1** | Author **AD-05 — Orchestration Migration**: workflow shape per stage, activity boundaries, the two human gates as signals, cutover + rollback, in-flight job handling. **§18 amendment — review-board approval before any code.** |
| **M3.2** | Provision a dedicated Temporal node *(operator; **not** node-01)* |
| **M3.3** | Migrate the coordinator across all 8 stages **in one arc** |
| **M3.4** | Verify against M1's reference output; Celery path stays flag-gated until verified |
| **M3.5** | Amend functional spec §2.1 / §6.2 / §6.4; retire ledger P0.1, P1.1–P1.2, P2.1–P2.3 together |

- **Exit:** the pipeline runs on durable execution; a verified reference-output diff; ~5,200 lines net deleted; the Celery coordinator removed, not coexisting.

### M4 — Full 6-node fleet on the new architecture

Each node configured **once**, on the post-migration architecture.

- **Compose deltas authored first** (AD-02 Draft 3): node-02 strip video; node-03 strip vLLM; **node-06 Intel→CUDA rewrite (mandatory — card swapped to RTX 6000 96 GB)** + `gpu_video` + composition + profile-gated stopped fp8-70B failover worker; node-05 SDXL image + Ollama LLM fallbacks + composition overflow.
- **node-06 as primary compositor + Remotion** (captions, lower-thirds, animated titles, L2 Ken-Burns fill); migrate composition off the node-01 bootstrap.
- **Trustworthy GPU telemetry** *(ledger P2.6)*: fix the Blackwell exporter CrashLoop; wire heartbeat registration so `total_nodes > 0` and reservations actually reserve. Pairs with M2's P1.3.
- **Weight-fetch live pass** *(ledger P2.10)*: IVGS **pulls** weights from MBCP via `ivgs-models/mbcp_fetch.py`. Needs the serving token + signing key handoff. *(Direction is pull, not push.)*
- **Exit:** all six nodes online and specialized; composition off node-01; telemetry trustworthy; weight-fetch exercised.

### M5 — Long videos + talking-head scale

- **30-minute videos**, parallel and **resumable** — as child workflows rather than new tables and watchdogs.
- **SadTalker fallback** built (currently a stub, alignment-gated).
- **Segment-rendering quality:** pause-aligned seams; tune `MAX_SEGMENT_SECONDS` upward once RAM headroom is confirmed.
- **Two-tier head render:** fast LatentSync draft, certified model for production (enabled by M1's ORCH-6).
- **Exit:** a 30-minute video renders reliably, resumes from mid-run failure, and the fallback is exercised.

### M6 — UI functional *(+ AD-01 remainder)*

- Operator flow end-to-end: create → live stage progress → review gates → asset/draft preview → approve/reject/regenerate → download.
- **Per-project model-selection GUI** and auto-weight-fetch-on-approve (the remaining AD-01 slivers; API exists, GUI does not).
- **Exit:** a non-technical operator drives a project transcript-to-final entirely in the UI.

### M7 — Production hardening

- **Security:** `.env.node01` gitignored *(the MBCP token has never been committed — prospective risk only)*; credential rotation; drop the `dev-service-token` default.
- **DR:** the comprehensive design (git + weights + Postgres + SeaweedFS/Redis + per-node compose/`.env`, NAS + offsite). **Prereq: full fleet (M4).**
- **Operability:** `RUNBOOK.md` *(also a prerequisite for delegating work to agents)*; image-artifact recovery convention; hygiene bundle.
- **Validation:** load/soak testing; deferred GPU-fleet acceptance bullets; test-suite coverage.
- **Exit:** production-readiness checklist green.

### M8 — Production launch

Final acceptance run, operator sign-off, cutover, go-live.

---

## 6. WS-T scope boundary *(binding)*

**Replace** — the coordination layer only: stage-transition maps, completion callbacks, join counters, the media-join watchdog, checkpointing, retry and dead-letter plumbing. ~6,283 lines, of which ~1,957 is orphaned and simply deleted.

**Preserve, effectively untouched** — the eight stage bodies (~25,000 lines): the Jinja template fixes, extensible-WAV handling, scene linkage, AD-03 duration anchoring, ffmpeg logic, the clients, `quality_validator`. Each gets a thin activity wrapper and is otherwise left alone.

**Keep entirely** — `ivgs-scheduler` (VRAM-aware bin packing across heterogeneous cards is domain logic), the API, the frontend, the DB schema, the MBCP seam, the Model Store.

**Risks to manage.** *Half-migration* — mitigated by principle #7 and the flag-gate in M3.4. *node-01 capacity* — 8 vCPU / 16 GB already runs ~13 services; a dedicated node is provisioned in M3.2. If that changes, DBOS Transact (library-only, no new server, existing Postgres) is the resource-respecting alternative. *New failure modes* — determinism constraints, replay-only bugs, and versioning discipline for in-flight workflows during deploys, which multi-hour renders and multi-day gates make constant. *Not a quality fix* — WS-T addresses none of M1; it must not displace ORCH-6 or Stage-8 validation.

---

## 7. Critical path

```
M1 (ORCH-6 + Stage-8 validation + reference output)
 └─> M2 (D1–D4 correctness)
      └─> M3 (Temporal migration, one arc, verified vs reference)
           ├─> M4 (fleet 02/03/05/06 + telemetry + weight-fetch) ─┐
           │        └─> M5 (long videos, resumable) ──────────────┤
           └─> M6 (UI + AD-01 remainder) ────────────────────────┴─> M7 (harden + DR) ─> M8
```

**Hard dependencies.** M1's reference output gates M3's verification. M3 precedes M4 so each node is configured once. M3 precedes M5 so long-video testing has execution history and resume. M4's full fleet gates DR in M7. M6 depends on M3 for truthful state (ORCH-5 becomes a workflow query).

**Parallelizable.** M6 can begin alongside M4/M5 once M3's contracts stabilize. MBCP platform work (WS-H: RuntimeClass refactor, CogVideoX adapter) runs independently throughout.

---

## 8. What changed from v0.3, and why

1. **Stage status corrected.** v0.3 showed Stage 8 unvalidated and the ledger showed Stage 6 as BUILD REQUIRED. Both stages execute; evidence is on node-01. M1 is far closer to closing than v0.3 implies.
2. **WS-H Phase-1 closed.** The bake-off is settled and MBCP serves certified models to IVGS. v0.3's M1 quality gate ("depends on a certified replacement head") is satisfied.
3. **ORCH-6 discovered and promoted to the top of the critical path.** The AD-01 provider binding landed on the dead duplicate, so certified models cannot reach production. v0.3's B5 framing (bind at Stage 8) is superseded — the binding belongs at Stage 6.
4. **WS-T added; M3 inserted.** A code audit found four correctness defects and ~1,957 orphaned lines against an untested 1,397-line orchestrator. The migration is sequenced **before** the fleet and **before** long-video testing, for the reasons in §5/M3.
5. **Old M2 split.** Its correctness half becomes M2 (~1 session); ORCH-5 state-truthfulness is absorbed by M3 (a workflow query, so it is not fixed twice); GPU telemetry moves to M4, where it actually matters.
6. **M4a/M4b merged into M4.** Both node bring-ups now happen post-migration on the new architecture. **node-06 is CUDA, not Intel** — the card was swapped to an RTX 6000 96 GB, making the AD-02 Draft-3 compose rewrite mandatory and redesignating node-06 as a second CUDA video node, primary compositor, and on-demand LLM failover.
7. **Old M5 (AD-01) retired as a milestone.** Substantially delivered; the remaining slivers fold into M6.
8. **RabbitMQ broker swap withdrawn.** Recommended earlier as a cheap fix for the visibility-timeout class — now throwaway work, since M3 removes the mechanism and M2's pre-migration testing stays short. P0.1 is closed with a config line.
9. **Principles 6 and 7 added** — scope discipline and no-half-migrations, both drawn from the P2.3 precedent.

---

## 9. Milestone renumbering map (v0.3 → v0.4)

| v0.3 | v0.4 | Note |
|---|---|---|
| M0 | M0 | Expanded — now covers Stages 1→**8** |
| M1 | M1 | Quality gate satisfied by WS-H; ORCH-6 added |
| M2 | **M2** (correctness half) + **M3** (ORCH-5 absorbed) + **M4** (telemetry) | Split |
| M3 (talking-head + long video) | **M5** | Displaced by the migration |
| M4a + M4b | **M4** | Merged; post-migration; node-06 now CUDA |
| M5 (AD-01) | — | Substantially closed; remainder → M6 |
| M6 (UI) | **M6** | + AD-01 remainder |
| M7 (hardening) | **M7** | Secret severity corrected |
| M8 (launch) | **M8** | Unchanged |
| — | **M3** | **New** — orchestration migration |

---

*End of Master Sequence Plan v0.4. Next action: M1 — ORCH-6 (promote the provider binding into the live Stage-6 task), then operator visual QA of the 1080p final. Next document: `IVGS_v5_Addendum_AD-05_Orchestration_Migration.md`.*
