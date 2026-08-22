# IVGS v5 — Status & Progress Summary

| | |
|---|---|
| **Document** | Status & progress summary for the IVGS training-video generation system, with the path to complete implementation |
| **Prepared** | 2026-08-14 (late evening). **Supersedes the 2026-07-30 edition**, which was built on the 2026-07-09 handoff and Master Plan v0.3 — see §7 for what it got wrong. |
| **Authoritative sources** | `IVGS_Comprehensive_Agent_Handoff_2026-08-14.md` · `OUTSTANDING_WORK.md` v4.1 (task-level SoT) · Master Sequence Plan v0.4 · AD-05 (approved) · ERRATA node-01 capacity · runbook 2.1 · Agent Development Plan v1.0 |
| **Repo state (as at preparation, 2026-08-14)** | `brucecostello2/elearning_v5` @ `b09b70f`, node-01 == `origin/main`. Live: ivgs-api `v5.5.3-arch1`, ivgs-workers `v5.5.1-arch1`, ivgs-frontend `v5.4.2-themes`, ivgs-backup-worker `v5.1.0-stream-b`. Alembic head 0027. MBCP (.51) connected mode LIVE. |
| **AS-AT NOTE — committed 2026-08-22, unrevised** | This document was written 2026-08-14, amended 2026-08-15 with the bake-off erratum, and committed on **2026-08-22 without revision**. **Read every figure below as at 2026-08-14 unless dated otherwise.** State at commit: HEAD `3e2744b`, node-01 == `origin/main` (`0  0`), live ivgs-workers **`v5.5.2-orch6`** (not `v5.5.1-arch1`). That running image is one commit behind HEAD and does not contain the WP-03 bitrate assertion committed at `3e2744b`. Source: `dev/workpackages/reports/WP-TREE-TRIAGE-report_2026-08-22.md`. |
| **Ground rule** | Verify on-box before assuming. A green surface is not evidence — five instances of a swallowed-failure pattern were found in one day. A fact repeated across documents is duplicated, not corroborated. |

---

## 1. Executive summary

**The pipeline executes end-to-end, all eight stages.** Evidence on node-01: draft `f78eb063` (214.94s, 720p, corruption 6/6, operator-confirmed) and final `9007b2cf` (215.07s, 1920×1080, 30fps, h264 High, AAC 48 kHz stereo). The remaining M1 work is validation and model-binding, not construction.

**MBCP is delivered. The bake-off is NOT settled — see the erratum below.**

> **ERRATUM 2026-08-15 — the bake-off has NOT been run.** This section states or
> implies that the talking-head comparison is complete and settled. **The platform is
> complete; the comparison is not.** Evidence:
>
> - MBCP's weight store holds three talking-head models — davinci-magihuman (171 GB),
>   humo-17B (130 GB) and latentsync (4 GB) — but **all four talking-head certificates
>   are LatentSync**, because MagiHuman and HuMo have **no adapters** (MBCP work
>   package **R-11**, still open). A model without an adapter cannot be benchmarked,
>   so it cannot be certified or exported.
> - LatentSync therefore "won" a field of one — and it is the model already judged
>   non-viable for articulation on 2026-06-08
>   (`docs/archive/OUTSTANDING_WORK_Addendum_B_2026-06-08.md:32`, "a deal-breaker").
> - The two LatentSync certificates IVGS holds (`9e0fc3cd`, `7b26811f`) are
>   **unsupported**: MBCP's lip-sync gate was scored against a fixture whose
>   `audio_matched.wav` is the presenter clip's own soundtrack (RMS difference
>   -135.4 dB, 102 dB below baseline). It could not fail.
> - No IVGS or MBCP metric measures lip-sync **articulation** — the defect that
>   matters. Ledger **P1.4e**.
>
> **The blocker is MBCP R-11**: adapters for MagiHuman and HuMo. Until those exist
> there is no comparison, no winner, and nothing for IVGS to consume. A win by either
> would additionally need an IVGS provider builder that does not exist
> (`registered_engines()` lists only cogvideox, comfyui, coqui, kokoro, latentsync,
> sadtalker, vllm).
>
> Amended, not rewritten: "bake-off complete" was a genuine belief on the information
> then available, and the record of that belief is part of the evidence. Ledger P1.4d.


**Original text:** MBCP is delivered and the bake-off is settled. Certified models flow MBCP → IVGS Model Store as candidates; backfill complete (21 exports + 2 composition; 24 revoked correctly skipped); the Approve/Deprecate/Retire lifecycle is live and GUI-only. WS-H's Phase-1 driver is CLOSED.

**But the certification chain terminates at a wall — ORCH-6 (P1.0), top of the critical path.** The live Stage-6 task (`talking_head_task.py`) imports `LatentSyncClient` directly; the AD-01 provider-factory binding sits in `stage6_talking_head.py`, the dead duplicate nothing dispatches. Certified models cannot be selected into production. Fix: **promote** the binding into the live file (preserving its segment/OOM strategy, Pillar-2 overlay and correct upload URL), then delete the duplicate.

**The 75-day backup gap was found and closed 2026-08-14.** Six root causes fixed; storage migrated `.9` CIFS (100% full, retired) → `.7` TrueNAS NFS4.2 (22 TB, hard mount); WAL archiving live; Alertmanager deployed; 38 GB of image artefacts now have a first off-node copy with verified checksums. **The mechanism is proven; the clock is not** — no backup has yet fired unattended. Check `backup_records` after 06:00.

**The orchestration layer carries four correctness defects** (P0.1 duplicate GPU execution, P1.1 premature media join, P1.2 fictional checkpoints, P1.3 fail-open GPU reservations) plus ~1,957 orphaned lines and inverted test coverage. The migration to **Temporal** is approved (AD-05) and sequenced as **M3** — after M1/M2 close, before fleet rollout, so each node is configured once. The errata matters: the binding constraint is **host** memory on `n5Pro` (which OOM-killed node-01 twice on 2026-08-14), so provisioning the Temporal node is a hardware/reallocation decision to settle before M3.2, with DBOS Transact as the live fallback.

**Documentation re-baseline is committed (`b09b70f`) but four amendment documents are instructions not yet applied** — Spec v5.1 (ten edits, incl. the "Seven-Stage" header errata / ADR-003), AD-01 Draft 2, AD-03 v0.4, AD-04 v3.1. Until applied, the base documents contradict their own amendments.

---

## 2. What is done

**Pipeline (Stages 1→8).** All eight stages end-to-end: transcript refinement → storyboard (gate) → media generation → composition manifest → TTS → talking-head render → prototype draft (gate) → final render. AD-03 Pillars 1 & 2 closed with evidence (durations anchored on real audio; head composited once as a continuous timeline overlay).

**Model management (AD-01/ARCH-1).** Model Store + selection-aware provider factory + admin GUI lifecycle live; stages 1/2/3/5 bound (Stage 6 → ORCH-6).

**MBCP ↔ IVGS.** Connected mode live since 2026-07-09; certify ≠ export; receiver dedups by `certification_id`; Export-to-IVGS GUI button delivered 2026-07-12. RuntimeClass consolidation merged (PR #48). CogVideoX adapter rebuilt with correct node names — **never GPU-tested** (MBCP WP-A is the gate).

**Backups (2026-08-14).** Beat 02:00 db (in-container) · cron 03:00 assets + 04:00 config + 05:00 verify (host) · WAL archiving via `archive_command` · `verify_backup.sh` fixed and gated both ways (passes known-good, fails corrupted) · Alertmanager deployed with `BackupFailed` + `BackupStale`. Backup tasks now raise `BackupTaskError` instead of returning failure dicts Celery logged as success.

**Fleet.** node-01 (CPU hub, now genuinely 16 GB) and node-04 (RTX PRO 6000 96 GB — image/TTS/head) live. node-02 (LLM) / node-03 (video) provisioned, trailing tags. node-05/06 OFFLINE; **node-06's card swapped to RTX 6000 Blackwell 96 GB — CUDA, not Intel** — redesignated primary compositor + Remotion + second video node + gated LLM failover.

---

## 3. Milestone status (Master Plan v0.4)

| Milestone | Goal | Status |
|---|---|---|
| **M0** | Pipeline executes Stages 1→**8** | ✅ Complete |
| **M1** | Close the happy path at quality | 🟡 In progress — **ORCH-6**, Stage-8 formal validation + 4K, frame-aligned splitting, bank reference output |
| **M2** | Orchestration correctness defects (P0.1, P1.1–P1.3) | 🔴 Not started (~1 session) |
| **M3** | **Orchestration migration (Temporal)** — new in v0.4 | 🔴 Not started; AD-05 approved; node-07 decision pending |
| **M4** | Full 6-node fleet on the new architecture (M4a/M4b merged) | 🔴 Not started |
| **M5** | Long videos + talking-head scale (30-min, resumable, SadTalker) | 🔴 Not started |
| **M6** | UI functional (+ AD-01 remainder) | 🔴 Not started |
| **M7** | Production hardening (S-1 rotation, DR + restore drill, monitoring, load/soak) | 🔴 Not started |
| **M8** | Production launch | 🔴 Not started |

Critical path: M1 → M2 → M3 → (M4 → M5, M6 in parallel) → M7 → M8. M1's reference output gates M3's verification; M3 precedes M4 so each node is configured once, and precedes M5 so long-video testing has execution history and resume.

---

## 4. Remaining steps, in dependency order

1. **Prove the unattended backup run** — `backup_records` after 06:00, `pg_stat_archiver`, files on `.7` (handoff §6.2 paste block).
2. **Apply the four amendment documents** (WP-15) — mechanical, self-verifying; closes ADR-003; removes the last `intel b70`/`oneapi` references.
3. **WP-02 / ORCH-6** — promote the provider binding into `talking_head_task.py`. Tier C, two-pass gate. Exit proof: a head-model swap performed entirely in the GUI changes the engine, evidenced in worker logs.
4. **Close M1** — Stage-8 formal validation incl. first 4K run + bitrate/quality assertion (WP-03); frame-aligned segment splitting to <1 frame drift (WP-04; settle AD-03 Q5 authoritative fps first); capture the known-good reference output.
5. **M2** (WP-05…08) — raise visibility timeout + config assert; media-join unknown-vs-zero + SETNX idempotency; build `POST /jobs/{id}/checkpoints` + assert returns; fix reservation releases + `finally` blocks.
6. **M3 Temporal migration** — one arc, all 8 stages, flag-gated until verified against the reference output; scope boundary AD-05 §8 is binding (stage bodies untouched).
7. **M4 fleet** — compose deltas first (node-06 Intel→CUDA rewrite mandatory); Blackwell telemetry fix (P2.6); weight-fetch live pass (P2.10, after S-1).
8. **M5 → M8** — long videos, UI, hardening (DR drill vs `.7`, monitoring repair — 15/16 scrape targets down), launch.

**Also first, per the Agent Development Plan:** WP-00, the swallowed-failure detector — converts a whole defect class from judgement-review to machine-checkable. Four instances remain open in the WP-00 register.

**Operator-only:** visual QA of `final_1080p_9007b2cf.mp4` · node-07/host-capacity decision (before M3.2) · S-1 coordinated token rotation (both hosts, one window — rotating one side breaks the seam silently) · commit the two untracked docs on node-01 (AD-04-v3, MBCP VM setup) · GPG key `4F2243FAB5A25808` off-network copy.

---

## 5. Deployed but unproven (absence is not pass)

- No backup has fired unattended (mechanism proven by manual dispatch only)
- No IVGS restore drill against `.7` (MBCP has run one, byte-for-byte)
- 4K render profile never exercised
- Checkpoint resume never worked (route did not exist; fixed under M2/WP-07)
- Five GPU nodes responding to scheduler — registry empty (`total_nodes:0`), nodes 05/06 offline
- DLQ routing and localisation never exercised
- `BackupStale` firing-state payload uncaptured

---

## 6. Key risks & watch-items

- **Host capacity (`n5Pro`, 61 GB).** OOM-killed node-01 twice on 2026-08-14 with clean guest logs; 32 GB swap added. Any hardware/capacity figure used in an argument must be measured on the box the same session. node-07 provisioning is not free capacity waiting to be assigned.
- **Green surface over dead mechanism** — this system's signature failure (five instances in one day). Verify against `pg_stat_archiver`, `celery_taskmeta`, and the artifact, never against appearances.
- **Monitoring largely blind** — 15/16 Prometheus scrape targets down; no out-of-hours alert channel; Blackwell exporter crashloops.
- **Unresolved contradiction** — `release_gpu_reservation` `TypeError` claim (dev CLAUDE.md) vs no-repro (ledger). Neither tested. Do not act on either side; operator to resolve.
- **Half-migration precedent** — v1→v2 orchestrator half-done since June (P2.3). M3 runs in one arc or not at all.
- **S-1** — `IVGS_MBCP_INGEST_TOKEN` == `MBCP_AD01_TOKEN`, exposed MBCP-side 2026-08-04; coordinated rotation pending.

---

## 7. Corrections to the 2026-07-30 edition

The 07-30 summary (and its milestone tracker) carried claims the 08-14 re-baseline overturned:

| 07-30 said | Corrected |
|---|---|
| Pipeline runs 1→7; Stage 8 remains | All **eight** stages execute; Stages 6–8 had been running since 2026-06-08 |
| Head-model bake-off still to run; certified model is the M1 gate | Bake-off complete and settled; the gate is **ORCH-6** — certified models exist but cannot be selected |
| Stage 8 must bind the head via the provider factory (B5) | Misframed — Stage 8 overlays a pre-rendered head by `asset_id`; the binding belongs at **Stage 6** |
| Milestones per Plan v0.3 (M2 robustness, M3 TH/long-video, M4a/M4b, M5 AD-01) | Renumbered in v0.4; **M3 = Temporal migration**; AD-01 retired as a milestone |
| `.env.node01` is git-tracked; secret-leak risk | Closed at `e1f4c58` — untracked/gitignored; token never committed; **S-1 rotation** is what remains |
| No orchestration-defect or backup-gap awareness | 08-14 audit found P0.1/P1.1–P1.3 + 1,957 orphaned lines; 75-day backup gap found and closed |
| node-01 = 16 GB (memory-constrained) | Was 31 GB, over-provisioned; now deliberately 16 GB; the real constraint is the Proxmox host |

---

*Prepared 2026-08-14 against `b09b70f`. Update this file as milestones close; `OUTSTANDING_WORK.md` v4.1 remains the task-level SoT. Companion artefact: `ivgs_milestone_tracker_2.html` (same snapshot).*
