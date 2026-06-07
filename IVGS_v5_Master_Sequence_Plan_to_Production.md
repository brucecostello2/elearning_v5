# IVGS v5 — Master Sequence Plan to Production

| | |
|---|---|
| **Document** | Master Sequence Plan — the high-level path from current state to a fully deployed, production-ready system |
| **Version** | v0.1 — 2026-06-07 (initial draft) |
| **Authoritative as of** | `main` @ `8b07c88`; workers `v5.4.18-h0` on node-01 (`celery-worker-default`/`-composition`) and node-04; pipeline proven **E2E Stages 1→7 with the talking-head composited into the draft**, paused at `user_review`. |
| **Companion ledgers** | `OUTSTANDING_WORK.md` (task-level single source of truth) + `OUTSTANDING_WORK_Addendum_A` (2026-06-05). **This plan sequences workstreams and milestones; the ledger tracks individual items.** |
| **Operating principle** | *"Fix, don't park — clean as we go."* Walk the end-to-end happy path; fix bugs inline as they surface; defer nothing without recording it in the ledger. |

---

## 1. Where we are (M0 — complete)

**Pipeline.** Stages 1→7 run end-to-end for the test project: transcript refinement → storyboard → media generation (images/video/animation) → composition manifest → TTS audio → **talking-head render** → prototype draft. As of this session the talking-head (LatentSync) **renders, uploads, and composites into the 720p draft** (`num_layers: 3`, `scenes_failed: 0`), and the pipeline correctly pauses at the `user_review` gate. The 2026-06-05 image-generation regression (Addendum A / **A1**) is effectively behind us: the pipeline now produces images and advances cleanly through Stage 7.

**Fleet (AD-02 topology).** node-01 = CPU hub (Postgres / API / Redis / SeaweedFS / scheduler / orchestrator `celery-worker-default` / `celery-worker-composition` / beat). node-02 = LLM-only (Llama-3.3-70B-FP8). node-03 = video-only (CogVideoX/Wan2.1). node-04 = image + TTS + talking-head (RTX PRO 6000; ComfyUI/FLUX, Coqui, Kokoro, WhisperX, vLLM-midsize Mistral-24B, **LatentSync** built + proven). **nodes 05/06 = OFFLINE** (hardware provisioned, prerequisites installed, not yet stood up).

**Stage 8 (final render)** is wired for the head (orchestrator dispatch now passes `talking_head_asset_id` + `enable_talking_head`) but **not yet validated**.

This session's six fixes that closed the Stage-6B loop are listed in §7.

---

## 2. Definition of "production ready"

A non-technical operator can drive a course video from a raw transcript to a final 1080p/4k render — with a correctly placed, lip-synced talking-head presenter — **entirely through the UI**, reliably and repeatably, on the **full 6-node fleet**, with managed models, trustworthy monitoring, disaster recovery, and **no hand-edited secrets or runtime band-aids**. Concretely:

- **E2E:** Stages 1→8 produce a correct final video (head synced and placed right; passes corruption/validation gates).
- **Scale:** 30-minute videos render reliably (parallel, resumable); rendering distributes across the GPU fleet.
- **Robustness:** GPU reservations actually reserve; no swallowed errors; pipeline/project state is truthful.
- **Breadth:** SadTalker fallback live; AD-01 model management implemented; UI functional; nodes 05/06 online.
- **Hardening:** secrets out of git; real service tokens; monitoring/alerting trustworthy; DR in place; runbooks written; load/soak-tested.

---

## 3. Guiding principles

1. **E2E-first.** Keep one working happy path and extend it; correctness of the whole chain beats local optimization.
2. **Fix, don't park.** Bugs hit *during* any milestone are fixed inline. Anything genuinely deferred gets a ledger entry — never silent.
3. **Correctness > speed.** Verify against authoritative sources (committed code, git history, real logs); don't reason forward from summaries.
4. **One image, both fixes.** When a deploy is required, fold all in-tree fixes into a single rebuilt tag (avoid the A1-style "the build swept in other work" trap).
5. **The ledger is the task SoT.** This plan is the map; `OUTSTANDING_WORK.md` is the backlog. Re-snapshot it on every close.

---

## 4. Workstreams (parallel concerns)

| ID | Workstream | Scope |
|----|-----------|-------|
| **WS-A** | E2E pipeline completeness + quality | The happy-path spine: Stages 1→8 producing a correct final; A/V sync, head placement, draft/final validation. |
| **WS-B** | Talking-head subsystem | LatentSync render quality, segment-rendering correctness, SadTalker fallback, long-video scale. |
| **WS-C** | Documented-debt paydown | `OUTSTANDING_WORK` P1/P2 items + Addendum A (A2/A4/A5/A6/A7) + this session's new items. |
| **WS-D** | Model management (AD-01) | Implement the AD-01 model lifecycle/versioning/serving design. |
| **WS-E** | UI | Make the user-facing flow functional: project lifecycle, review gates, asset preview, approve/reject, download. |
| **WS-F** | Fleet scale-out | Stand up nodes 05/06; GPU heartbeat/scheduler; distributed + parallel rendering. |
| **WS-G** | Production hardening | Secrets/tokens, monitoring/alerting, DR, runbooks, load/soak testing, hygiene. |

---

## 5. Phased sequence

> Milestones define **focus**, not rigid gates. Per principle #2, debt and quality work interleave with the spine. WS-D (AD-01) and WS-E (UI) can run **in parallel** with the M3/M4 track once contracts stabilize (post-M2).

| Milestone | Goal | Exit criteria |
|-----------|------|---------------|
| **M1** | Close the happy path *at quality* | One project goes 1→8 clean; final reviewed correct (head synced + placed). |
| **M2** | Make the single-job path robust | Happy path runs with no swallowed errors / orphans; reservations succeed; state is truthful. |
| **M3** | Talking-head completeness + long videos | A 30-min video renders reliably (parallel, resumable); SadTalker fallback works. |
| **M4** | Fleet scale-out (nodes 05/06) | Rendering distributes across ≥4 GPU nodes. |
| **M5** | Model management (AD-01) | Models managed per AD-01 (versioning, serving, swaps). |
| **M6** | UI functional | A non-technical user drives a project end-to-end via the UI. |
| **M7** | Production hardening | Production-readiness checklist green (security, monitoring, DR, runbooks, load test). |
| **M8** | Production launch | Final acceptance + cutover. |

### M1 — Close the happy path at quality *(immediate — this is items 1–3 + the sync catch)*
- **Head placement QA — spatial *and* temporal.** Inspect stage7's overlay filter to learn the *intended* layout (PiP vs full-frame vs lower-third), then eyeball the actual draft (`8e0c8531`). Resolve the **temporal** question: the head is 215.5s but the timeline is 227.26s — confirm whether the head is sliced per-scene against each scene's audio, stretched, or left short at the tail.
- **A/V drift fix (~0.62s).** Segment rendering rounds each piece to whole frames (`ceil(slice_s × 30)`), accumulating ~0.62s of video-over-audio across 11 pieces. Fix with **frame-aligned splitting** (slice on 1/fps boundaries so pieces are whole-frame and sum exactly), or trim each rendered piece to its audio length. Regression introduced by the OAM-fix split; not present in single-render.
- **Corruption check 5/6.** Identify the failing 6th check on the draft (fails identically on head-less and head drafts, so head-independent); decide whether it gates for drafts vs finals.
- **Stage 8 final render with head.** Validate `final_render` (1080p, optionally 4k) carries the head correctly. *Do this last in M1* — no point spending a 4k render before the head is synced and placed.
- **Exit:** one project completes 1→8; the final video is reviewed and confirmed correct (head synced, placed, validation passing).

### M2 — Make the single-job happy path robust
- **GPU heartbeat / reservation (`total_nodes:0`).** Nodes don't register GPU presence with the node-01 scheduler, so `acquire_gpu_reservation` soft-skips ("No alive GPU nodes" — observed every render this session). Wire heartbeat registration so reservations actually reserve. Pair with the **Blackwell GPU-exporter CrashLoop** (monitoring metric-name panic) so telemetry is trustworthy. *(This unblocks M3/M4 distributed rendering.)*
- **ORCH-5 — `projects.state` mapping.** State stays stale at `TRANSCRIPT_REFINEMENT` after a full run; the lenient `approve_storyboard` guard is empirically relied upon. Make state truthful, then tighten the guard. *(Prerequisite for an honest UI.)*
- **Addendum-A cluster:** A2 (de-band-aid vLLM model name / `IVGS_VLLM_*` vs `VLLM_*`), A4 (401 scene-asset linkage), A5 (v1→v2 orchestrator dead-code excision), A6 (non-blocking 4xx cluster incl. **checkpoint POST 405**).
- **Fleet image consistency.** node-02/03 still on older worker tags (`v5.4.0-h0`); node-01/04 on `v5.4.18-h0`. Align the fleet and adopt a consistent tag-bump discipline (the shell-shadow-`.env` trap).
- **Lower-noise items:** clock drift (node-02/03 ~20s → NTP), API healthcheck wrong-port, talking-head asset metadata loss, `_upload_asset` unused params.
- **Exit:** the happy path runs with no swallowed errors or orphan renders; reservations succeed; pipeline/project state is accurate.

### M3 — Talking-head completeness + long videos
- **SadTalker fallback.** Build the `sadtalker:7861` engine (currently a stub) as the alignment-gated fallback when LatentSync scores below threshold. Closes the last node-04 media-tier TODO.
- **Segment-rendering quality:** frame-aligned splitting (from M1), pause-aligned (not even-split) seams, and tuning `MAX_SEGMENT_SECONDS` upward for fewer seams once RAM headroom is confirmed.
- **Phase 2 — parallel piece rendering.** RAM-autosensed concurrency: an engine-side dynamic semaphore sized from real-time free RAM ÷ measured per-render budget, **reserving** budget per in-flight render (LatentSync's memory spike is late). Autosense over a static cap because node-04 RAM is shared across six engines.
- **Phase 3 — per-piece Celery sub-tasks + resume.** Move pieces into `group`/`chord` sub-tasks; persist `render_segments` (table exists, 0 rows) and add the `/jobs/{id}/segments` tracking API so renders are resumable and a single task no longer spans hours.
- **Exit:** a 30-minute video renders reliably — parallel, resumable, with the fallback exercised.

### M4 — Fleet scale-out (nodes 05/06)
- Stand up nodes 05/06 per AD-02 (deploy worker + engine images, register with the scheduler, de-conflict identity per the node-03 clone playbook), and validate **distributed** rendering across the GPU fleet.
- **Depends on M2** (heartbeat/scheduler) and leverages **M3** (parallel pieces) for the real speedup on 30-min videos.
- **Exit:** rendering parallelizes across ≥4 GPU nodes.

### M5 — Model management (AD-01)
- Implement the AD-01 model-management design (lifecycle, versioning, mounted-weights convention, served-alias resolution, controlled swaps). Folds in the A2 config-naming source-of-truth cleanup.
- **Exit:** models are managed per AD-01; no per-node hand-edited model names.

### M6 — UI functional *(can begin in parallel after M2 stabilizes contracts)*
- Repair the user-facing flow end-to-end: project create → live stage progress → the review gates (`storyboard_review`, `user_review`) → asset/draft preview → approve/reject/regenerate → final download.
- **Depends on M2** for truthful state (ORCH-5) and stable API contracts.
- **Exit:** a non-technical operator drives a project from transcript to final entirely in the UI.

### M7 — Production hardening
- **Security:** secrets out of git (`.env.node0x` tracked — P1.7), real `IVGS_SERVICE_TOKEN` (drop the `dev-service-token` default), permission/role review.
- **Disaster recovery:** the comprehensive DR design (git + `/mnt/models` weights + Postgres + SeaweedFS/Redis + per-node compose/.env to NAS + offsite). **Prereq per the ledger: full fleet (M4) + AD-01 (M5).**
- **Observability:** trustworthy GPU telemetry (depends on the M2 exporter fix), alerting, dashboards.
- **Operability:** `RUNBOOK.md`, the image-artifact recovery convention, hygiene bundle (A7: `.bak` cruft, stale `.env.node01`, dirty `checksums.sha256`, GPU source-tree drift).
- **Validation:** load/soak testing; the deferred GPU-fleet acceptance bullets (P1.3); test-suite coverage.
- **Exit:** production-readiness checklist green.

### M8 — Production launch
- Final acceptance run, operator sign-off, cutover, go-live.

---

## 6. Critical path & parallelism

```
M1 (quality happy path)
   └─> M2 (robust single-job) ──┬─> M3 (TH complete + long video) ─> M4 (fleet scale-out) ─┐
                                │                                                          ├─> M7 (hardening + DR) ─> M8 (launch)
                                ├─> M5 (AD-01 model mgmt) ─────────────────────────────────┤
                                └─> M6 (UI functional) ────────────────────────────────────┘
```

- **Hard dependencies:** M2's GPU heartbeat/scheduler gates M3/M4 distributed rendering; M4 + M5 gate DR in M7; M2's state-truthfulness (ORCH-5) gates an honest UI in M6.
- **Parallelizable once M2 lands:** M5 (AD-01) and M6 (UI) run alongside the M3→M4 rendering track.
- **Sequencing rationale:** correctness (M1) before optimization (M3); a working single-job path (M2) before scaling it across the fleet (M4); breadth features (M5/M6) after the contracts they depend on are honest (M2).

---

## 7. This session's items to fold into `OUTSTANDING_WORK.md`

**Closed this session (Stage-6B talking-head — evidence: commits/tags below):**
1. Segment-based talking-head render, one segment per scene — fixes full-narration OOM. *(`29f854a` / v5.4.15)*
2. Over-length scenes split into ≤30s sub-renders — fixes single-scene OOM; proven bounded (~15 GB peak/piece). *(`6a1324a` / v5.4.16)*
3. Talking-head upload to the real endpoint `POST /projects/{id}/assets/upload`; read `seaweedfs_path`. *(`54d3281` / v5.4.17)*
4. `save_checkpoint` call corrected to `stage_name`/`stage_index`/`status`. *(`0ca2e78`)*
5. Orchestrator wiring: `prototype_draft` + `final_render` dispatch now resolve `talking_head_asset_id` via `_fetch_talking_head_asset` (was hardcoded `None`); `enable_talking_head` added to final_render. *(`8b07c88` / v5.4.18)*
6. LatentSync engine built + proven on node-04. *(`latentsync-v5.2.7-h0`)*

**New items to ADD (proposed priorities):**
- **[P2 / quality]** Talking-head A/V drift ~0.62s — frame-aligned segment splitting *(M1)*.
- **[P2 / quality]** Head temporal alignment vs timeline (215.5s head vs 227.26s timeline) — verify/fix *(M1)*.
- **[P3 / quality]** Draft corruption check 5/6 — identify the failing check; decide gating *(M1)*.
- **[P3]** Talking-head asset upload drops metadata (route has no metadata field) — add a field or accept the loss (model/alignment/dims still in logs + Stage6Output).
- **[P3 / hygiene]** `_upload_asset` unused params (`sha256_hash`, `metadata`) — trim signature + call site.
- **[P3 / hygiene]** 38 GB cgroup mem-cap on `ivgs-latentsync` → convert to a persistent `node04.yml` `mem_limit`.
- **[P2 / consistency]** Fleet worker-tag drift: node-02/03 on `v5.4.0-h0`, node-01/04 on `v5.4.18-h0` — align.
- **[P3 / hygiene]** Duplicate draft assets from re-fires (`0a83f6f2` superseded by `8e0c8531`); single talking-head (`b45b19ce`) — dedup/cleanup policy.
- **[P2 / scaling]** Phase 2 (RAM-autosensed parallel pieces) + Phase 3 (per-piece sub-tasks + `render_segments` resume + `/jobs/{id}/segments` API) — for 30-min videos *(M3)*.
- **[P3 / latent]** `acquire_gpu_reservation` extra-kwarg debt across other tasks — audit (the same class as the `save_checkpoint` bug just fixed).

**Confirmed still open (observed this session):** GPU heartbeat registry empty / `total_nodes:0` → reservations skipped *(M2)*; checkpoint `POST 405` (A6) — now a non-fatal warning in talking-head too *(M2)*; ORCH-5 `projects.state` stale *(M2)*.

---

*End of Master Sequence Plan v0.1. Next action: execute M1 (head-placement QA → A/V sync fix → corruption triage → Stage 8 final render with head).*
