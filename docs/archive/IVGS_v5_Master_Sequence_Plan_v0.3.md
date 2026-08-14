# IVGS v5 — Master Sequence Plan to Production

| | |
|---|---|
| **Document** | Master Sequence Plan — the high-level path from current state to a fully deployed, production-ready system |
| **Version** | v0.3 — 2026-06-08 (M1 duration+corruption + Pillar-2 head sync closed; M4 corrected vs functional spec; WS-H / AD-04 model-certification workstream added) |
| **Authoritative as of** | `main` @ `b17397b`; workers `v5.4.23-h0` on node-01 (`celery-worker-default`/`-composition`) + node-04 (`v5.4.18-h0`). Pipeline proven **E2E Stages 1→7 with the talking-head composited into the draft**; **A/V duration + corruption (6/6) and AD-03 Pillar-2 head sync closed** (draft `f78eb063`, video==audio at 214.94s, single continuous head overlay); paused at `user_review`. **Open quality gate: the LatentSync head's lip-sync articulation is not production-viable → routed through AD-04/MBCP for a certified replacement.** |
| **Companion ledgers** | `OUTSTANDING_WORK.md` (task-level single source of truth) + `OUTSTANDING_WORK_Addendum_A` (2026-06-05). **This plan sequences workstreams and milestones; the ledger tracks individual items.** |
| **Operating principle** | *"Fix, don't park — clean as we go."* Walk the end-to-end happy path; fix bugs inline as they surface; defer nothing without recording it in the ledger. |

---

## 1. Where we are (M0 — complete)

**Pipeline.** Stages 1→7 run end-to-end for the test project: transcript refinement → storyboard → media generation (images/video/animation) → composition manifest → TTS audio → **talking-head render** → prototype draft. As of this session the talking-head (LatentSync) **renders, uploads, and composites into the 720p draft** (`num_layers: 3`, `scenes_failed: 0`), and the pipeline correctly pauses at the `user_review` gate. The 2026-06-05 image-generation regression (Addendum A / **A1**) is effectively behind us: the pipeline now produces images and advances cleanly through Stage 7.

**Fleet (AD-02 topology).** node-01 = CPU hub (Postgres / API / Redis / SeaweedFS / scheduler / orchestrator `celery-worker-default` / `celery-worker-composition` / beat). node-02 = LLM-only (Llama-3.3-70B-FP8). node-03 = video-only (CogVideoX/Wan2.1). node-04 = image + TTS + talking-head (RTX PRO 6000; ComfyUI/FLUX, Coqui, Kokoro, WhisperX, vLLM-midsize Mistral-24B, **LatentSync** built + proven). **node-05 = OFFLINE** (NVIDIA RTX 5080, 16 GB; per the functional spec §2.2: ComfyUI **SDXL/SD3.5 image fallback**, **Ollama** small-model **LLM fallback**, FFmpeg composition **overflow** + utility). **node-06 = OFFLINE** (Intel B70 Pro, 32 GB, oneAPI/IPEX — **no CUDA**; per spec: **Remotion** motion-graphics [lower-thirds, captions, animated titles, **Ken-Burns L2 fill**] and the **primary** FFmpeg compositor). Both are hardware-provisioned, not yet stood up. **Note: the spec puts the FFmpeg compositor on node-06 (primary)/node-05 (overflow) — the `celery-worker-composition` running on node-01 today is a bootstrap, not its permanent home.**

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
| **WS-F** | Composition + motion-graphics + fallback tier (06/05) | Stand up **node-06** (canonical FFmpeg compositor + Remotion captions/lower-thirds/Ken-Burns L2) and **node-05** (SDXL image + Ollama LLM fallbacks + composition overflow); migrate composition off the node-01 bootstrap. *(This is capability + resilience, not CUDA render-distribution — node-06 is Intel.)* |
| **WS-G** | Production hardening | Secrets/tokens, monitoring/alerting, DR, runbooks, load/soak testing, hygiene. |
| **WS-H** | Model evaluation & certification (AD-04) | Build the **MBCP** — benchmark, validate, and certify self-hostable models on real hardware; produce the AD-01.7 attestation. **Phase 1 settles the talking-head production model**; the full platform is AD-01's (M5) external acceptance process. |

---

## 5. Phased sequence

> Milestones define **focus**, not rigid gates. Per principle #2, debt and quality work interleave with the spine. WS-D (AD-01) and WS-E (UI) can run **in parallel** with the M3/M4 track once contracts stabilize (post-M2).

| Milestone | Goal | Exit criteria |
|-----------|------|---------------|
| **M1** | Close the happy path *at quality* | One project goes 1→8 clean; final reviewed correct (head synced + placed). |
| **M2** | Make the single-job path robust | Happy path runs with no swallowed errors / orphans; reservations succeed; state is truthful. |
| **M3** | Talking-head completeness + long videos | A 30-min video renders reliably (parallel, resumable); SadTalker fallback works. |
| **M4** | Composition + motion-graphics + fallback tier (06/05) | **M4a:** node-06 is the FFmpeg compositor; Remotion renders captions/lower-thirds + Ken-Burns (L2); composition migrated off node-01. **M4b:** node-05 SDXL image + Ollama LLM fallbacks + composition overflow online. |
| **M5** | Model management (AD-01) | Models managed per AD-01 (versioning, serving, swaps). |
| **M6** | UI functional | A non-technical user drives a project end-to-end via the UI. |
| **M7** | Production hardening | Production-readiness checklist green (security, monitoring, DR, runbooks, load test). |
| **M8** | Production launch | Final acceptance + cutover. |

### M1 — Close the happy path at quality *(immediate — this is items 1–3 + the sync catch)*
> **Update 2026-06-08.** Two AD-03 pillars are CLOSED: **(1) A/V duration + corruption** (Pillar 1, §11) — durations anchored on real audio end-to-end (`v5.4.22`); and **(2) Pillar-2 head sync** (`v5.4.23`) — the head is now composited **once** as a continuous timeline overlay (draft `f78eb063`, 214.94s, video==audio, corruption 6/6), so it tracks each scene instead of replaying the opening. The "215.5 vs 227.26" / "5/6" framing in the bullets below is superseded (real timeline **214.94s**; 215.5 was the head's own length). **Remaining mechanical M1** (model-agnostic): **Stage 8 with the head** (not yet validated) and the ~0.62s head A/V drift (frame-align). **Quality gate on M1 closure:** the LatentSync head's articulation is **not production-viable** — "final reviewed correct" now depends on a certified replacement head model via **AD-04/MBCP (WS-H)**. The composition path is model-agnostic, so the Stage-8 plumbing is validated now and the certified model drops into the same path.
- **Head placement QA — spatial *and* temporal.** Inspect stage7's overlay filter to learn the *intended* layout (PiP vs full-frame vs lower-third), then eyeball the actual draft (`8e0c8531`). Resolve the **temporal** question: the head is 215.5s but the timeline is 227.26s — confirm whether the head is sliced per-scene against each scene's audio, stretched, or left short at the tail.
- **A/V drift fix (~0.62s).** Segment rendering rounds each piece to whole frames (`ceil(slice_s × 30)`), accumulating ~0.62s of video-over-audio across 11 pieces. Fix with **frame-aligned splitting** (slice on 1/fps boundaries so pieces are whole-frame and sum exactly), or trim each rendered piece to its audio length. Regression introduced by the OAM-fix split; not present in single-render.
- **Corruption check 5/6.** Identify the failing 6th check on the draft (fails identically on head-less and head drafts, so head-independent); decide whether it gates for drafts vs finals.
- **Stage 8 final render with head.** Validate `final_render` (1080p, optionally 4k) carries the head correctly. *Do this last in M1.* **Build it to resolve the head model via the provider factory / AD-01 binding, not a hard-coded engine** (AD-04 §16) — so a newly certified production head (Wan2.2-S2V / MagiHuman / …) is a selection change, not a code change.
- **Exit:** one project completes 1→8; the final video is reviewed and confirmed correct (head synced, placed, validation passing).

### M2 — Make the single-job happy path robust
- **GPU heartbeat / reservation (`total_nodes:0`).** Nodes don't register GPU presence with the node-01 scheduler, so `acquire_gpu_reservation` soft-skips ("No alive GPU nodes" — observed every render this session). Wire heartbeat registration so reservations actually reserve. Pair with the **Blackwell GPU-exporter CrashLoop** (monitoring metric-name panic) so telemetry is trustworthy. *(This unblocks M3/M4 distributed rendering.)*
- **ORCH-5 — `projects.state` mapping.** State stays stale at `TRANSCRIPT_REFINEMENT` after a full run; the lenient `approve_storyboard` guard is empirically relied upon. Make state truthful, then tighten the guard. *(Prerequisite for an honest UI.)*
- **Addendum-A cluster:** A2 (de-band-aid vLLM model name / `IVGS_VLLM_*` vs `VLLM_*`), A4 (401 scene-asset linkage), A5 (v1→v2 orchestrator dead-code excision), A6 (non-blocking 4xx cluster incl. **checkpoint POST 405**).
- **Fleet image consistency.** node-02/03 still on older worker tags (`v5.4.0-h0`); node-01/04 on `v5.4.18-h0`. Align the fleet and adopt a consistent tag-bump discipline (the shell-shadow-`.env` trap).
- **Lower-noise items:** clock drift (node-02/03 ~20s → NTP), API healthcheck wrong-port, talking-head asset metadata loss, `_upload_asset` unused params.
- **Exit:** the happy path runs with no swallowed errors or orphan renders; reservations succeed; pipeline/project state is accurate.

### M3 — Talking-head completeness + long videos
- **Production head model (via AD-04/MBCP).** The production-tier talking-head is no longer assumed to be LatentSync — its articulation failed the viability bar — so the production head is whatever the MBCP (WS-H) certifies (Wan2.2-S2V / MagiHuman / HuMo candidates), composited via the existing model-agnostic overlay. The target is a **two-tier** render: fast LatentSync draft, certified model for production.
- **SadTalker fallback.** Build the `sadtalker:7861` engine (currently a stub) as the alignment-gated fallback when the primary head model scores below threshold. (Robustness fallback, *not* the quality answer — that comes from the MBCP-certified production model above.)
- **Segment-rendering quality:** frame-aligned splitting (from M1), pause-aligned (not even-split) seams, and tuning `MAX_SEGMENT_SECONDS` upward for fewer seams once RAM headroom is confirmed.
- **Phase 2 — parallel piece rendering.** RAM-autosensed concurrency: an engine-side dynamic semaphore sized from real-time free RAM ÷ measured per-render budget, **reserving** budget per in-flight render (LatentSync's memory spike is late). Autosense over a static cap because node-04 RAM is shared across six engines.
- **Phase 3 — per-piece Celery sub-tasks + resume.** Move pieces into `group`/`chord` sub-tasks; persist `render_segments` (table exists, 0 rows) and add the `/jobs/{id}/segments` tracking API so renders are resumable and a single task no longer spans hours.
- **Exit:** a 30-minute video renders reliably — parallel, resumable, with the fallback exercised.

### M4 — Composition + motion-graphics + fallback tier (nodes 06/05)
*Per the functional spec (§2.2, §6.3 Table 6-6, §7.1.8), 05/06 are **not** extra CUDA render nodes — node-06 is Intel (oneAPI/IPEX). They are the composition tier, the Remotion motion-graphics engine, and the image/LLM fallbacks. The old "rendering distributes across ≥4 GPU nodes" exit is dropped.*

**M4a — node-06 (composition + Remotion).** Stand up node-06 (Intel B70 Pro): make it the **primary FFmpeg compositor** and **migrate composition off the node-01 bootstrap**; bring up the **Remotion** renderer for lower-thirds, captions, animated titles, and the **L2 Ken-Burns** still-fill (per the §6.3 fallback chain); QSV encode; Intel GPU exporter. *This is a **quality** enabler for M3 (proper long-scene fill + captions), and it does **not** hard-depend on M2's CUDA heartbeat — so it can be pulled forward.*
- *Exit:* draft + final are composited on node-06; captions/lower-thirds render via Remotion; long scenes use Ken-Burns stills (L2) rather than stretched clips.

**M4b — node-05 (fallbacks + overflow).** Stand up node-05 (NVIDIA RTX 5080): ComfyUI **SDXL/SD3.5 image fallback** behind node-04 FLUX; **Ollama** small-model **LLM fallback** behind node-02 vLLM (wired through the `OllamaProvider`, folds into AD-01/M5); FFmpeg composition **overflow** (NVENC). *This is **resilience**, less urgent than M4a.*
- *Exit:* image and LLM fallbacks engage on primary-node failure; composition overflows to node-05 under load.

**Standing both up** (de-conflict identity per the node-03 clone playbook; register workers) completes the full 6-node fleet — the prerequisite for DR in M7.

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
M1 ─> M2 ─┬─> M4a (node-06: FFmpeg compositor + Remotion) ─> M3 (TH complete + long video) ─┐
          ├─> M4b (node-05: image/LLM fallback + compose overflow) ──────────────────────────┤
          ├─> M5 (AD-01 model mgmt; absorbs Ollama provider) ───────────────────────────────┼─> M7 (harden + DR) ─> M8
          └─> M6 (UI functional) ──────────────────────────────────────────────────────────┘
```

- **Hard dependencies:** M2's GPU heartbeat/scheduler gates **CUDA parallel rendering** (M3 segment parallelism) — **not** M4 (the 06/05 composition/fallback tier doesn't need it); the **full fleet** (M4a + M4b) + M5 gate DR in M7; M2's state-truthfulness (ORCH-5) gates an honest UI in M6.
- **Parallelizable once M2 lands:** M4a, M4b, M5, and M6 are largely independent of one another; M4a feeds M3's quality.
- **Sequencing rationale:** correctness (M1) before optimization; a robust single-job path (M2) before fanning out. **M4a (node-06) is pulled forward toward M3** — the spec makes Ken-Burns stills the Phase-1 primary visual and puts captions/lower-thirds in Remotion, so M3's long-video *quality* leans on node-06. M4b (fallbacks) stays later as resilience.

### Sequencing impact of the functional-spec reconciliation (2026-06-07)
The spec review (05/06 roles, Remotion compositor, §6.3 fallback chain) shifts the plan in three concrete ways — recorded here, not silently:
1. **M4 splits; node-06 pulls forward.** node-06 (canonical compositor + Remotion: captions, lower-thirds, **L2 Ken-Burns**) is a composition/quality tier, not scale-out, and is **not** gated by M2's CUDA heartbeat — so it moves up next to M3 (**M4a**). node-05 (image/LLM fallback + overflow) stays a later resilience milestone (**M4b**). The old "≥4 GPU render nodes" exit is dropped.
2. **Visual-fill strategy reorders, and part ships now.** Per Table 6-6, AI-video (L1) is **Phase-2+** and the **Ken-Burns still (L2) is the Phase-1 default primary** — so today's "generate a 6s clip and stretch it" is off-plan. Near-term: ship an **ffmpeg `zoompan` (L3) on the node-01 bootstrap** to replace the frozen-frame fill (no node-06 needed); the richer **L2 Remotion Ken-Burns lands with M4a**. This retracts AD-03's "Pillar 3 = last/cosmetic." *(Operator call: how heavily to lean on the CogVideoX clip path before Phase 2 vs. leading with stills.)*
3. **Composition migrates off node-01** (bootstrap → node-06 primary / node-05 overflow) — folded into M4a; the audio-anchored caption clock moves to Remotion there.

**Unchanged:** M1 correctness (the node-01 bootstrap delivered a clean happy path); M2 (heartbeat / ORCH-5 / fleet-consistency still next, still gates CUDA parallelism + an honest UI); M5–M8 (M5/AD-01 now explicitly absorbs the Ollama fallback provider).

### Sequencing impact of the head-model decision (2026-06-08)
The LatentSync head's articulation is not production-viable, so a certified replacement is now on M1's *quality* critical path. This adds **WS-H** (the MBCP / AD-04): its **Phase 1** — the talking-head bake-off (LatentSync vs Wan2.2-S2V vs MagiHuman) — is pulled forward to settle the production head, and the **full platform** is the external acceptance process AD-01 (M5) needs to function at all. Mechanical M1 (Stage-8 plumbing, frame-align drift) stays model-agnostic and proceeds in parallel; **Stage 8 binds its head model through the provider factory** so the certified model is a selection change, not a rebuild.

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
