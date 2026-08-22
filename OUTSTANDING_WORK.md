# IVGS v5 — Outstanding Work (Single Source of Truth)

| | |
|---|---|
| **Version** | **v4.1 — 2026-08-14 (evening).** Updates v4.0 with the storage migration, the backup remediation, and the Step-10 cross-system register. v4.0 superseded v3.1 + Addenda A/B, all folded in. |
| **Repo state** | `brucecostello2/elearning_v5` @ `main` = **`e1f4c58`**. node-01 and `origin/main` in exact sync. `.env.node01` now untracked and gitignored (P1.5 CLOSED). |
| **Live stack** | ivgs-api `v5.5.3-arch1`, ivgs-workers `v5.5.1-arch1`, ivgs-frontend `v5.4.2-themes`, ivgs-scheduler `latest` (unpinned — P2.11), ivgs-backup-worker `v5.1.0-stream-b`. Alembic head **0027**. |
| **Code currency** | The tree at `e613e844` was byte-identical to the 2026-07-10 capture — no code had been committed for five weeks. Two commits landed 2026-08-14: `1f0fd31` (backup rsync/NFS) and `e1f4c58` (untrack `.env.node01`, record host config). |
| **Infrastructure** | node-01 memory is **31 GB reduced to 16 GB** — every prior document said 16 GB and was wrong; the VM was over-provisioned. Proxmox host `n5Pro` was **OOM-killing VMs**; 32 GB swap added. Backup NAS migrated `.9` CIFS (100% full) → **`.7` NFS4.2** (22 TB). |
| **Sources merged** | v3.1 ledger; Addendum A; Addendum B; `SESSION_HANDOFF_2026-07-09.md` register; `AD-04-v3` + its Phase-0 analysis; Master Plan v0.3; AD-01/02/03; direct code audit of `e613e844` (2026-08-14). |
| **Operating principle** | *"Fix, don't park — clean as we go."* Nothing is deferred without an entry. Closures require evidence (commit SHA, image tag, file:line, or transcript pointer). |
| **Companion docs** | `OUTSTANDING_WORK_archive_v3.1.md` (full historical closure detail — nothing lost); `IVGS_v5_Master_Sequence_Plan_to_Production.md` (milestone map); `IVGS_v5_Addendum_AD-05_Orchestration_Migration.md` (to be authored — WS-T). |

---

## Priority definitions

- **P0 — Blocking.** System broken or unsafe; address before any other work.
- **P1 — High.** Blocks the critical path, hides regressions, or required for the next increment.
- **P2 — Medium.** Real defect or hygiene work; will compound if deferred.
- **P3 — Low.** Cosmetic, documentation, or strategic multi-session work.
- **DEFERRED.** Consciously not-now, with a stated reason and a re-open trigger.

## Snapshot

| Priority | Count | Headline |
|---|---|---|
| **P0** | 1 | D1 broker visibility timeout → duplicate GPU execution *(P0.2 backup gap CLOSED 2026-08-14)* |
| **P1** | 9 | ORCH-6 head-model binding on the dead file; D2 join; D3 checkpoints; D4 GPU reservations; backup reporting; prompt ENUM; smoke; GPU acceptance; AD-02 governance |
| **P2** | 31 | orphaned operational layer (F1); zero orchestrator tests (F2); orchestrator cleanup (F3); 4xx cluster; ORCH-5 state; GPU telemetry; + carried hygiene |
| **P3** | 17 | dead code; test coverage; UI polish; schema parity; observability |
| **DEFERRED** | 2 | comprehensive DR; localisation |
| **WS-T** | 7 | Temporal orchestration migration (new workstream) |
| **§S** | 10 | Cross-system seam items (new — belong to neither register) |

## Pipeline status (2026-08-14)

| Stage | State |
|---|---|
| 1 transcript_refinement | ✅ proven e2e |
| 2 storyboard_generation | ✅ proven e2e; user gate working |
| 3 media (image/video/animation) | ✅ proven e2e; scene-linked |
| 4 composition_manifest | ✅ proven e2e; server-side build, locked manifest |
| 5 tts_audio | ✅ proven e2e; 48 kHz/24-bit, scene-linked |
| 6 talking_head_render | ✅ **runs** (LatentSync, node-04) — ⚠️ engine **hardcoded**, not AD-01-selectable (ORCH-6) |
| 7 prototype_draft | ✅ proven — draft `f78eb063`, 214.94s, 1280×720, corruption 6/6 |
| 8 final_render | ✅ **runs** — final `9007b2cf`, **215.07s, 1920×1080, 30fps, AAC 48k stereo**; used as evidence in the AD-04 head-model judgment. ⚠️ never formally validated; visual QA outstanding (M1-QA) |

> **Correction to all prior documents.** v3.1 and Addendum B show Stage 6 as *BUILD REQUIRED* and Stages 7/8 as *unbuilt/untested*. That is two months stale. **All eight stages execute end-to-end.** The remaining M1 work is validation and model-binding, not construction.

## Critical path (in order)

1. **ORCH-6** — make the head model selectable, else the entire MBCP certification chain is unconsumable.
2. **M1-QA** — visual acceptance of `final_1080p_9007b2cf.mp4`; formal Stage-8 validation.
3. **D1–D4** — the four orchestration correctness defects.
4. **WS-T** — orchestration migration, before fleet rollout and before long-video testing.

---

# P0 — Blocking

## P0.1 — `broker_visibility_timeout` below two tasks' hard time limits → duplicate execution *(new, code audit 2026-08-14; was "D1")*
**Status:** OPEN — live latent defect, verified at `e613e844`.
`config.py:214-215` sets `broker_visibility_timeout = 3600`. `talking_head_task.py:284` and `video_generation_task.py:445` both declare `time_limit=3900`. With the Redis broker and `task_acks_late = True` (`celery_app.py:293`), a message unacked past the visibility timeout is **redelivered while the original still runs**.
- `gpu_video` is consumed by node-02 **and** node-03 → the duplicate can execute **concurrently on the other node**, two CogVideoX jobs on the same scene contending for VRAM.
- `gpu_talking_head` is node-04 only → duplicate runs sequentially, wasting a full render.
- Either way the duplicate reaches the task tail and fires `handle_stage_completion` again → **double join decrement** (P1.2).

Latent today only because renders are short; near-certain at the M3 30-minute target.
**Scope/action:** raise `IVGS_BROKER_VISIBILITY_TIMEOUT` above the longest hard `time_limit` with margin (7200); add a config-time assert that `visibility_timeout > max(task time_limit)`. One config line + one guard. **Do not** swap the broker for this — WS-T removes the mechanism entirely.

---

# P1 — High Priority

## P1.0 — ORCH-6: live Stage-6 task hardcodes LatentSync; ARCH-1 provider binding is on the *dead* duplicate *(new, code audit 2026-08-14)*
**Status:** **CLOSED 2026-08-15** by WP-02-ORCH6 — code complete and unit-verified on
node-01; **the on-hardware GUI-swap gate is outstanding and is operator-run** (node-04).
Report: `dev/workpackages/reports/WP-02-ORCH6-report_2026-08-15.md`.

**What was wrong.** `STAGE_TASK_MAP` dispatches `tasks.talking_head_task.render_talking_head`.
That live file imported `LatentSyncClient` directly — the engine was hardcoded. The
AD-01/ARCH-1 provider-factory implementation lived in `stage6_talking_head.py`, the dead
duplicate nothing dispatched. Certified MBCP models could not be selected.

**What changed.** The binding was promoted into the live task: `ensure_registered()` +
`get_binding("talking_head", project_id=..., tier=...)` + `build_provider(...)` resolved
once per job, the GPU reservation now asks for `binding.name` /
`provider.vram_requirement_mb()`, each segment renders through `provider.render(...)`, and
`model_used` is stamped from `binding.name`. The duplicate and its test are deleted; all
map, route, `imports` and `__all__` references are cleaned. The registered task name,
segment/OOM strategy, AD-03 Pillar-2 behaviour and the correct
`/projects/{id}/assets/upload` URL are unchanged.

**Three things this did NOT close — carried forward.**

1. **The SadTalker fallback is still engine-direct.** `SadTalkerProvider` requires a
   per-scene still image that this whole-project stage does not have, so a
   `sadtalker`-engine selection raises `ValueError` at render time. A true cross-engine
   GUI swap needs that provider fixed. *(New item — see P1.0a.)*
2. **AD-01.13 criterion 5 remains open.** Stage 6 renders once and both Stage 7 and
   Stage 8 consume the single asset, so prototype- and production-tier models cannot be
   applied to draft and final respectively without a pipeline change. `tier` is a
   constant (`"prototype"`) on `Stage6Input`.
3. **Stage 6 now fails loudly** with `SelectionError` when no approved, enabled, default
   `talking_head` model exists. Deliberate: a silent fallback to a hardcoded engine would
   make a GUI swap appear to work when it had not.

*(Note: Stage 8 consumes a pre-rendered head asset by `asset_id` and overlays it — it does
not render the head. B5's "Stage 8 must bind via the factory" was misframed; the binding
belongs at Stage 6. Recorded here so B5 is not lost.)*

## P1.0a — Stage-6 SadTalker fallback is not selection-driven *(new, WP-02-ORCH6 finding F2, 2026-08-15)*
**Status:** OPEN — blocks a true cross-engine GUI swap at Stage 6.
`ivgs-workers/providers/talking_head.py` `SadTalkerProvider.render` raises
`ValueError("sadtalker provider requires scene image and voiceover audio")` unless a
per-scene still is supplied. Stage 6 renders the presenter from the reference clip against
narration audio and has no scene image, so the provider cannot serve this stage. The live
task therefore keeps its own engine-direct `_render_with_sadtalker` fallback.

Second, independent defect in the same provider: `_spill` writes bytes to a **worker-local**
`tempfile.TemporaryDirectory()`, and `SadTalkerClient._submit_job` posts those paths as JSON
to the remote SadTalker service, which cannot open them unless it shares the worker's
`/tmp`. **Unverified against a running SadTalker service** — node-04 was out of scope.

Three mutually incompatible SadTalker contracts now exist: the live task's
`POST {base}/generate` multipart (the only one exercised), `SadTalkerClient`'s
`POST /api/render` JSON-of-paths, and `SadTalkerProvider`'s worker-local paths handed to the
second. **Which one node-04 actually implements is unknown and should be established first.**

## P1.0b — Every GPU node except node-01 names a database driver that is not installed; this blocks the entire AD-01 binding on the fleet *(new, WP-02 check-6b deployment, 2026-08-15)*
**Status:** OPEN — **node-04 fixed; nodes 02, 03, 05, 06 still broken.** Severity proposed P1; operator to confirm.

**The defect.** `DATABASE_URL` in the per-node compose files:

```
docker-compose.node01.yml   postgresql+asyncpg     <- correct
docker-compose.node02.yml   postgresql+psycopg     <- broken
docker-compose.node03.yml   postgresql+psycopg     <- broken
docker-compose.node04.yml   postgresql+asyncpg     <- FIXED 2026-08-15 (was +psycopg)
docker-compose.node05.yml   postgresql+psycopg     <- broken
docker-compose.node06.yml   postgresql+psycopg     <- broken
```

The workers image ships **`psycopg2` and `asyncpg`, not `psycopg` (v3)** — verified by
import inside `ghcr.io/brucecostello2/ivgs-workers:v5.5.2-orch6` on both nodes. So
SQLAlchemy's `postgresql+psycopg` dialect raises at engine creation:

```
ModuleNotFoundError: No module named 'psycopg'
  sqlalchemy/dialects/postgresql/psycopg.py -> import psycopg
```

`DATABASE_URL` is consumed **only** by `create_async_engine` (`shared/database.py:38`,
`ivgs-workers/tasks/periodic_tasks.py:656`), so it must name an **async** driver
regardless — `psycopg2` would not work either. `asyncpg` is the only installed async
driver, and node-01 has used it successfully throughout.

**Why it was invisible until now.** Pre-ARCH-1 worker images never opened a database
session from a worker, so the wrong driver cost nothing. ARCH-1 changed that:
`get_binding` opens a short-lived session (`factory.py:218-221`). **Any GPU node
running an ARCH-1 image cannot resolve a model binding** — which fails Stages 1, 2, 3
and 5 (already factory-bound per AD-01.12) as well as Stage 6 (WP-02).

**Observed.** On node-04 with `v5.5.2-orch6` and the original `+psycopg`, the first
`get_binding` call raised `ModuleNotFoundError`. After changing the line to `+asyncpg`
and recreating, the same call returned
`latentsync-alt [latentsync] tier=prototype via=default endpoint=http://latentsync:7860`
and `LatentSyncProvider` built with `engine_health: True`.

**This is a hard blocker for M4 (fleet rollout).** Standing up nodes 02/03/05/06 on any
ARCH-1 image without this fix will fail every model-bound stage on those nodes, and the
failure surfaces as a Python import error deep in SQLAlchemy rather than as anything
that names the real cause.

**Scope/action:** change `postgresql+psycopg` to `postgresql+asyncpg` in
`docker-compose.node02.yml`, `node03`, `node05`, `node06` (one line each; node-04 is
done). Leave `db+postgresql+psycopg2` result-backend URLs alone — psycopg2 **is**
installed and that path is sync. Consider a start-up assertion in the worker that
resolves the configured driver and fails loudly at boot rather than at first query.

*(node-04's on-disk checkout was edited directly to unblock verification and now differs
from the repo until synced; a backup `docker-compose.node04.yml.bak.pre-asyncpg` sits
beside it.)*

## P1.1 — Media join advances prematurely on Redis error; not idempotent *(new, code audit; was "D2")*
**Status:** OPEN — correctness defect.
`pipeline_orchestrator_v2.py:869-880` — `_decrement_media_task_count` returns **`0`** on any exception. The caller at `:672` treats `remaining <= 0` as *"all media reported, dispatch Stage 4."* A single transient Redis error during any one scene's callback **advances the pipeline with incomplete footage**. Same class: `_store_media_task_count` (`:856-866`) swallows its failure — if the counter was never written, `decr` on a missing key returns `-1`, `max(0,-1) == 0`, and the join collapses on the *first* scene to report.
No idempotency: every media task fires the callback at the end of its body then returns (`stage3_images.py:736-741`, `video_generation_task.py:574-580`); with `acks_late` + `task_reject_on_worker_lost`, a worker death in that window requeues and re-decrements.
**Scope/action:** distinguish "unknown" from "zero" (return `None` / raise and let the task retry); per-`(job_id, scene_id)` SETNX guard on the decrement.

## P1.2 — Checkpoint subsystem is a silent no-op; `resume` has nothing to resume from *(new, code audit; was "D3"; supersedes the P2.27 405 line item)*
**Status:** OPEN — **upgraded from P2.** Prior framing ("non-blocking 405 noise") understated it.
`utils/error_handler.py:409` POSTs to `/jobs/{job_id}/checkpoints`. `ivgs-api/app/api/v1/checkpoints.py` declares only `GET /checkpoints` (`:79`), `GET /checkpoints/{stage}` (`:106`), `POST /resume` (`:137`), `DELETE /checkpoints` (`:175`). **There is no `POST /jobs/{id}/checkpoints`** — hence the 405. `save_checkpoint` logs a warning and returns `False` (`:435-441`); **no call site checks the return value**. Every stage calls it; nothing is ever written. `POST /jobs/{id}/resume` therefore resumes from an empty table.
The §6.2 checkpoint/resume guarantee is **fictional**. This is the only stated mechanism for not re-running a 30-minute render after a transient failure — i.e. the single biggest lever on long-video test-cycle cost.
**Scope/action:** add the POST route (~40 lines) + assert on the return value at call sites. Worth doing now regardless of WS-T, because it collapses the M3 iteration loop for *every* bug class, not just orchestration ones.

## P1.3 — GPU reservations: 8 acquires, 3 releases, and those 3 raise `TypeError` *(new, code audit; was "D4"; absorbs old P3 "extra-kwarg debt")*
**Status:** OPEN.
`utils/gpu_utils.py:211` — `def release_gpu_reservation(reservation_id: str) -> bool:` takes **one** parameter. All three call sites pass two: `talking_head_task.py:543,699`, `video_generation_task.py:540` — `release_gpu_reservation(reservation, config)`. Every one raises `TypeError`. There are **8** `acquire_gpu_reservation(` call sites against 3 release attempts; stages 1/2/3/5/6 never release, relying on the 5-minute TTL. Every acquire is wrapped in `except Exception: log.warning("gpu_reservation_skipped")` (e.g. `stage1_transcript.py:526-530`) — the subsystem fails open and silently, which is why `total_nodes:0` (P2.29) has been invisible.
**Scope/action:** fix the signature at 3 sites; add `finally`-block releases at the other 5; decide explicitly whether reservation failure should be fatal. Pairs with P2.29.

## P1.4 — M1-QA: formal Stage-8 validation + visual acceptance *(new)*
**Status:** **(a), (b), (c) all DONE 2026-08-15 by WP-03-STAGE8-VALIDATION.** Report:
`dev/workpackages/reports/WP-03-STAGE8-VALIDATION-report_2026-08-15.md`.

- **(a) Operator visual QA — DONE. Both the 1080p and the 4K finals PASS on picture
  quality at full screen.** The encoder question is **CLOSED as not-a-defect**: the
  measured 506 kb/s (1080p) and 939 kb/s (4K) against 8/20 Mbps VBV ceilings are CRF
  behaving correctly on near-static content, exactly as AD-03 §14 predicted. `-crf`
  demonstrably reaches the executed command — the output carries `libx265` /
  `yuv420p10le` at 3840×2160. AD-03 §14 annotated closed.
- **(b) 4K profile — DONE, exercised for the first time ever.** hevc, 3840×2160,
  yuv420p10le, 30 fps, 215.067 s, 31,149,351 bytes, corruption checks passed.
- **(c) Bitrate assertion — DONE.** `video_bitrate_floor` in
  `validators/corruption_detector.py`: a 20 kb/s *collapse* floor at WARNING severity,
  set far below every known-good measurement so it cannot fail a reference. Passes the
  reference at 939,325 bps; fires on black at 10,501 bps. **Not yet in a deployed
  image** — ships on the next rebuild.

Reference banked at `dev/workpackages/reference/REFERENCE-OUTPUT_2026-08-15.md`
(narrow — see P1.0b/WP-26; Stages 1–5 were not run).

**Remaining under P1.4: nothing.** The lip-sync finding from the same QA session is a
separate item — see **P1.4d**.

## P1.4e — Neither system has ever measured lip-sync articulation: three unfailable metrics *(new, 2026-08-15, IVGS+MBCP joint investigation)*
**Status:** OPEN. Investigation complete; no code proposed yet.

**Three metrics, none of which can detect the defect that matters.**

| # | Metric | Where | Why it cannot fail |
|---|---|---|---|
| 1 | `alignment_score = 0.90` | `servers/latentsync/server.py:39,120` — `DEFAULT_ALIGNMENT`, env-overridable, emitted with `"scored": False` | A constant. Gated at 0.85 by the segment check in `talking_head_task.py` |
| 2 | `lip_sync_score = 0.9971` | `validators/lipsync_validator.py` | Computed, but measures **A/V duration agreement only**: `1 - (mismatch / audio_duration)`. `base_score` saturates at 1.0 via `min(1.0, (frame+energy)/2 + 0.2)`. Gated at 0.85 by `quality_thresholds.yaml` |
| 3 | `lse_c 6.58 / 6.68` | MBCP, on `.52` | **TH1**: the benchmark fixture's `audio_matched.wav` IS `presenter_face.mp4`'s own soundtrack. RMS difference -135.4 dB, 102 dB below baseline; durations differ by 104 microseconds |

**Metric 2 in detail.** `talking_head_task.py` calls `lipsync_validator.validate()`
**without** `latentsync_score`, so the engine's 0.90 is discarded and the module falls
to its ffprobe heuristic. Verified arithmetic against tonight's log:
`0.618667 / 214.881333 = 0.00287911` (logged exactly) and
`1.0 - 0.00287911 = 0.9971`. `base_score` was exactly 1.0, so `correlation` was
saturated. The module docstring advertises "Audio-visual correlation analysis" and
"Phoneme-to-viseme timing verification"; **neither is implemented.**

**Why 0.9971 was identical on 2026-06-08 and 2026-08-15:** it tracks duration, and the
duration mismatch (0.6187 s, the WP-04 frame-align defect) and audio length have not
changed. It would be unmoved by any articulation change.

**Consequence.** The only real measurement of articulation that has ever been taken is
the human verdict of 2026-06-08 (`docs/archive/OUTSTANDING_WORK_Addendum_B_2026-06-08.md:32`,
"a deal-breaker"). Both automated systems have reported approval ever since. Certificates
`9e0fc3cd` and `7b26811f` are unsupported (operator, MBCP side).

**Scope/action:** IVGS-2 addresses the two IVGS-side gates — **DONE 2026-08-15**
(both marked non-functional; `av_drift_seconds` added as the first working check).
Metric 3 is MBCP's. Metric 1 needs `server.py` and is deferred with IVGS-3/4
(digest/provenance coupling).

**Follow-up tied to IVGS-3/4 — typed face-detection error.** IVGS-5 detects
face-detection failure by matching the exception *message*, because the engine raises a
bare `RuntimeError("Face not detected")` and a typed exception would require `server.py`.
That file's image digest is pinned by MBCP certificate provenance, so it cannot be
rebuilt unilaterally. **When `server.py` is eventually rebuilt under IVGS-3/4, replace
the message predicate `_is_face_detection_failure` in `talking_head_task.py` with a
typed error.** Recorded so the compromise is not forgotten once the constraint lifts.

## P1.4f — Model Store hygiene items *(new, 2026-08-15; record only, do not act)*
**Status:** OPEN, recorded at operator instruction.

1. **`latentsync-alt` must never become a production default.** A deliberate test model
   created to debug the WP-02 check-6b GUI swap — not an error. **Once WP-02 is closed,
   retire it or move it out of `approved`** so it cannot be selected. Currently
   `state=approved`.
2. **Can IVGS distinguish attested-by-certificate from attested-by-free-text?**
   `model_approvals.vetting_reference` is free text. 22 of 26 rows hold certificate
   UUIDs; 4 hold prose (`"a test model"`, `"MBCP bake-off 2026-07"`, `"anything text"`).
   **Nothing in the schema or the enumeration path distinguishes them**, so an
   approved-models listing cannot tell a certified model from a hand-attested one.
   Gap worth knowing independently of `latentsync-alt`.
3. **20 of 26 attestations belong to models still in `candidate`.** Attestation exists,
   approval never happened. **Flag whether that is intended** — if attestation is meant
   to imply approval-readiness, 20 models are sitting one click away with nobody having
   decided.
4. **A MagiHuman or HuMo win needs an IVGS provider builder that does not exist.**
   `registered_engines()` on 2026-08-15: `cogvideox, comfyui, coqui, kokoro, latentsync,
   sadtalker, vllm`. Neither engine is present, and `build_provider` raises
   `EngineNotRegisteredError` for an unregistered engine. **Scope this now** so it is not
   discovered after MBCP R-11 delivers adapters.

## P1.4d — Lip-sync quality is poor. Diagnostic only: NO model swap is scoped *(new, operator visual QA 2026-08-15; scope clarified by operator 2026-08-15)*

> **SCOPE CLARIFICATION, operator, 2026-08-15.** The talking-head model is **NOT being
> swapped out.** Substantial IVGS development continues on the current model. Everything
> recorded under P1.4d/e/f is **diagnostic and metric-honesty work, which stands
> regardless of which model runs.** If LatentSync later proves unsuitable that is a
> separate decision at a later date. **Do not scope, plan or prepare a model swap.**
> The earlier framing of this item ("remediation is to consume the certified winner")
> is superseded by this paragraph.

> **SUPERSEDED IN PART — operator ruling, 2026-08-22.** The
> `IVGS_Directive_Consume_MBCP_Envelope_2026-08-19.md` directive **supersedes this
> item's hold** to the following extent, and no further:
>
> - **Proceeds now:** the operating-envelope / `EngineDeploymentSpec` ingest, the
>   placement check at engine bring-up, and digest-pinned launch. **This is generic
>   infrastructure** — it is about whether a machine can run a model at all, and it is
>   correct regardless of which model IVGS runs. Tracked as **P1.4g**.
> - **Still held:** the model swap itself. It waits for a certified MagiHuman bundle
>   carrying a *measured* envelope. **P1.4f.4 remains in force — record only, do not
>   act** on a provider builder for MagiHuman or HuMo.
> - Unchanged: the 2026-08-15 clarification above still governs everything in
>   P1.4d/e/f. Building the machinery is not scoping a swap; do not read it as one.

**Status:** OPEN. **Not** an encoder or composition defect — does not reopen P1.4 or
AD-03 §14.

Operator visual QA on 2026-08-15 records lip-sync quality as poor on both finals. That
is the **known LatentSync limitation** the MBCP bake-off was built and run to settle
(AD-04 §3.19: "the talking-head production model decision — the reason MBCP was built
and the M1 quality blocker — is settled on data").

**The problem: the winner is not in the Model Store.** `stage='talking_head'` holds
exactly two rows, measured 2026-08-15:

```
latentsync      engine=latentsync  approved  is_default=t
latentsync-alt  engine=latentsync  approved  is_default=f
```

Both are the **same engine**, so the GUI swap proved in WP-02 check 6b changes the
binding but **cannot improve lip-sync**. The certified winner was never landed.

**Scope/action:** folded into **WP-26-MODEL-STORE task 5** — establish which model MBCP
certified, whether an export was ever attempted (AD-04 §3.22: certification and export
are distinct admin actions, so certifying alone would not have landed it), whether it
failed or was parked by `drain-pending-exports` or simply never clicked, and what it
takes to land it including whether its engine has a registered provider builder.

*Data-integrity note — RETRACTED 2026-08-15.* An earlier note here claimed an orphaned
attestation (13 distinct `model_id`s vs 12 `models` rows). That was a **snapshot
artefact**: `models` was counted at 12 before `latentsync-alt` was created and approvals
at 13 after. Re-measured: 13 models, 13 distinct approval `model_id`s, **0 orphans**.
No integrity problem exists.
Evidence on node-01: `final_1080p_9007b2cf.mp4` — 215.07s, 1920×1080, 30fps, h264 High, AAC 48 kHz stereo; 0.13s from the draft's 214.94s. Segment planning, parallel render, concat, A/V alignment and head carry-through all work.
**Open question — encoder:** measured video bitrate is 506 kb/s (draft 153 kb/s at 720p). The profile constants are **correct** per spec (`ffmpeg_client.py:144-148`: `crf=18, vbv_maxrate="8M", vbv_bufsize="16M"`, applied at `:560-567` and `:834-842`). CRF targets *quality*, not bitrate, and near-static content (stills + slow Ken Burns + 0.25-scale PiP head) legitimately encodes low. **This is not yet a defect — resolve by visual inspection, not by the number.** If full-screen playback is clean, close it; if soft, investigate whether `-crf` reaches the executed command.
**Scope/action:** (a) operator visual QA at full screen; (b) 4K profile never exercised — run it; (c) add a corruption-check assertion on output bitrate/quality so this is measured, not eyeballed, next time; (d) record the run as the **known-good reference output** for WS-T verification.

## P1.4g — Consume MBCP's operating envelope and deployment spec *(new; operator directive 2026-08-19, ruled in force 2026-08-22)*
**Status:** OPEN, **in scope and proceeding.** Brief:
`dev/workpackages/IVGS_Directive_Consume_MBCP_Envelope_2026-08-19.md`.

**Why.** MBCP proved daVinci-MagiHuman renders 1080p talking heads, but only on a host
with 82 GB RAM and a 128 GB swapfile, in an environment that **permits paging**. Every
earlier attempt "proved" the model needed more memory than existed, because container
limits silently forbade swap — a memory-swap cap equal to the memory cap forbids paging
and the failure then blames the model. That cost three weeks on the MBCP side. If IVGS
stands a model up from the weight bundle alone it will faithfully reproduce the failure
and misdiagnose it the same way.

**The rule:** a certified model arrives with its machine requirements, and IVGS refuses
to schedule it onto a machine that cannot meet them — **loudly, before any GPU time,
naming the node, the requirement and the shortfall.** Never a mid-render death.

**Scope/action:** (1) ingest and store `operating_envelope` and `deployment`
(`EngineDeploymentSpec`) with the AD-01 candidate record — they are part of the model's
identity, not documentation; (2) placement check at engine bring-up covering host RAM,
swap **and whether the execution environment actually permits paging**, scratch disk and
GPU VRAM; (3) launch from the digest-pinned deployment spec, never a hand-written service
definition — the digest carries the patches; (4) honour request-side constraints already
travelling with the adapter (MagiHuman: dimensions divisible by 32, so 1080p renders at
1920×1088 and is trimmed on delivery; frame rate fixed by engine config); (5) surface
envelope satisfaction wherever IVGS shows which model serves a stage.

**Absent is a fact, not a default.** A bundle may carry neither block; historical
certificates say "not recorded". Treat a missing envelope as *"requirements unknown —
operator decision to schedule"*, never as *"no requirements"*.

**Acceptance:** IVGS takes a bundle for a model it has never seen, answers "which of my
nodes can run this?" without consulting any MBCP document or person, places it correctly,
and refuses incorrect placement in a sentence a human can act on.

**Boundary:** this is the machinery only. Landing MagiHuman as a production head remains
held under P1.4d and P1.4f.4. The figures in the directive are provisional pending MBCP's
30-second measurement round — **build against the contract shape, not those numbers.**

## P1.4h — IVGS-0.6: animation scenes render a still image *(new, operator ruling 2026-08-22)*
**Status:** OPEN, **numbered but not yet in any work order.**

AD-07 §4.6 records that IVGS animation scenes render a still image rather than motion,
and calls it "defect IVGS-0.5". **That number is already taken** — IVGS-0.5 in both
WP-IVGS-0 and AD-07 §5.1 item 5 is the New Project form. Operator ruling 2026-08-22:
**do not renumber the existing defects.** The animation-stills defect takes the next free
number, **IVGS-0.6**.

**Two consequences, both recorded rather than acted on:**
1. **AD-07 §4.6 carries a mis-citation** — "defect IVGS-0.5" should read "defect
   IVGS-0.6". AD-07 is an unratified draft and is committed as record unedited;
   **correct this at ratification**, not before.
2. **IVGS-0.6 is not in WP-IVGS-0's scope.** That order is operator-approved and
   standalone at five defects; a sixth is not added to it here. IVGS-0.6 needs its own
   order, and AD-07 §4.6 already describes the intended shape — split the capability into
   a deterministic `motion_graphic` renderer (adopting the orphaned
   `services/motion_graphics.py`) and the existing pose-guided `animation_generation`,
   and stop presenting one as the other.

## P1.4i — Report/work-order path convention: FINAL *(operator ruling 2026-08-22)*
**Status:** CLOSED by ruling. Recorded so it cannot be re-litigated.

`dev/workpackages/` and `dev/workpackages/reports/` are **the** convention for work
packages, work orders and reports. **`dev/workorders/` is not adopted and must not be
created.**

It has now been proposed twice: by `WP-IVGS-0_Defect_Fixes.md`'s own STEP 0.3 ("mirroring
the MBCP convention") and again as a session instruction on 2026-08-22, under which a
`dev/workorders/reports/` directory **was** created and one report written into it. Both
were reversed the same day: the directory removed, the report moved to
`dev/workpackages/reports/WP-DEPLOY-INCIDENT_2026-08-22.md`, and WP-IVGS-0's two path
references amended.

**Why it kept flipping:** MBCP genuinely uses `workorders/`, and this repo's agents read
MBCP documents. MBCP's layout does not govern here. Recorded in CLAUDE.md §12 as well, so
a cold-start session sees it without reading the ledger. If an incoming order names
`dev/workorders/`, **amend the order** — do not create the directory.

## P1.4j — v5.5.4-metrics deployed to node-01 AND node-04; five doc defects closed *(2026-08-22)*
**Status:** DEPLOY **CLOSED**. Five findings **CLOSED by edit**. One item OPEN (rotation, folded into S-1).

**What shipped.** `ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics`, built from `874a0c8`,
digest `sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9` — identical
across node-01's store, node-04's store and GHCR. Carries **P1.4e / IVGS-5** (alignment gate
marked non-functional, `av_drift_seconds`, face-detection abort) and **P1.4(c)/WP-03** (the
`video_bitrate_floor` assertion). Both verified present *inside the running containers* on
both nodes (`1` / `2` / `0`). Report:
`dev/workpackages/reports/WP-DEPLOY-R2-R5-NODE04_2026-08-22.md`.

**Node-04 address contradiction — RESOLVED.** CLAUDE.md §2 was right: node-04 is
**`192.168.1.93`**. `.93` answers ping and tcp/22, is in `known_hosts`, and returns
`hostname: node-04`; `.52` is DOWN and absent from `known_hosts`. The incident report §8.4
held that the node-04 block could not be labelled honestly until this was settled — it is now.
Dated erratum added to `HANDOFF_metric-honesty_2026-08-15.md` §6.

**LatentSync is no longer a single copy.** `latentsync-v5.2.7-h0` (23.3GB, irreplaceable —
absent from ghcr.io) is banked at
`/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_latentsync-v5.2.7-h0.tar.zst`,
7.7G, sha256 `2da83e5a2bb60f4f…`. Verified **restorable**, not merely present: checksum,
`zstd -t`, `tar -t`, and `manifest.json` `RepoTags`.

**Five documentation/tooling defects, all closed by edit in this package:**

| # | Defect | Fix |
|---|---|---|
| 1 | CLAUDE.md §6 said to verify a recreate with `docker exec <c> env` — **misleading for tag variables**. `env_file: .env.node0X` injects stale `IVGS_*_TAG` independent of the `--env-file .env` that selects the image. Both nodes reported wrong tags while running the right image | §6 rewritten: `docker ps` / `.Config.Image` for the image, `env` for config only. `depends_on` note added |
| 2 | `save-image-artifact.sh` needs root (store is `root:root 0755`); it failed at the redirect *after* `docker save` began, reading as a save failure | Usage says `sudo`; an explicit writability precheck now fails fast with a clear message |
| 3 | The R4 block printed two secrets | Narrowed to `^IVGS_[A-Z]*_TAG=` in the R4 block **and** runbook §3.4, which carried the same live grep |
| 4 | Handoff §6 gave node-04's address as `.52` | Dated erratum |
| 5 | R5 coupled push-and-bank, so a transient push failure suppressed the durable artifact save | Runbook **§3.5a**: bank first, separate steps, verify from the registry/filesystem never an exit code, never rebuild to work around a push failure |

**`.7` backup coverage of the artifact store — CONFIRMED, with one gap.** `asset_backup.sh:71`
takes `/mnt/ivgs-shared` wholesale as `SRC_SHARED_VOLUME`, rsynced to `shared-volume/` with
**no `--exclude` anywhere in the script**; daily 03:00 host cron; 14-day retention;
hard-linked across generations. Verified on `.7`:
`/mnt/backup/ivgs/assets/2026-08-22/shared-volume/image-artifacts/` holds the artifacts, with
daily directories 08-15 → 08-22. **This corrects the residual-risk note in
`WP-DEPLOY-R2-R5-NODE04` §10, which said coverage was unconfirmed — it is confirmed, and
DEF.1 already recorded it.**

**The gap that IS real:** the 03:00 cron means a freshly banked artifact spends up to ~24 h on
node-01's disk alone. Today's run was 03:00; the two new artifacts were banked at 19:26 and
19:32, so they reach `.7` at 03:00 on 2026-08-23. **One-line fix — run the asset backup by
hand immediately after banking anything irreplaceable:**

    (set -a; . /etc/ivgs/cron-backup-env; set +a; sudo /opt/ivgs/scripts/asset_backup.sh)

Not run in this package: it is a multi-GB rsync on a 16 GB node with a documented OOM history
(CLAUDE.md §7), and no ruling covered it. **Operator decision.**

**Also observed, not acted on.** node-04's `ivgs-infra/.env` carries `IVGS_API_TAG=v5.1.18-node-config`
and `IVGS_FRONTEND_TAG=v5.2.16-node-config`. node-04 runs neither service, so these are
probably vestigial — but that is inference, not measurement.

## P1.4k — The CI gate has been blind for 87 days; runner revival DEFERRED *(2026-08-22)*
**Status:** Gate **RESTORED** by moving off self-hosted. CD workflow **DISABLED**. Runner
revival **DEFERRED** with binding conditions. Blindness window **recorded, not remediable** —
see below.

### What was wrong
`.github/workflows/compliance-check.yml` and all three `cd-deploy.yml` jobs specify
`runs-on: [self-hosted, linux, x64, ivgs-infra]`. **No such runner has existed since
2026-05-26T22:41:36Z** — `ivgs-github-runner` started and exited 0.145 s later, exit 0, zero
log output, no restarts, no systemd unit, though still declared at
`docker-compose.node01.yml:557`.

**The failure mode is silence, not red.** A job with no matching runner does not fail; it
**queues indefinitely**. GitHub shows "queued", never a failure, and nothing raises an alarm.
Spec §F.2 describes this workflow as "fail build on any violation". **It has gated nothing for
87 days**, including all five commits of 2026-08-22. Every green CI signal in that period came
from `ci.yml`, which is entirely `ubuntu-latest` — and whose two Python jobs are `if: false`.
Recorded as WP-00 instance **16**.

Discovered only because run **#341** was noticed sitting queued against `a918fb9`. Nothing in
the tooling would have reported it.

### What was done
| Action | Detail |
|---|---|
| Compliance Audit restored | `runs-on: ubuntu-latest`. It needs nothing from node-01 — checkout, setup-python, four greps, `scripts/compliance_scanner.py .`, all against the checked-out repo. No docker, ssh, host path or network. Runs on the next push, with no runner and no host exposure |
| CD Deploy disabled | `push:` trigger removed (`workflow_dispatch` only) **and** `if: false` on all three jobs, matching `ci.yml`'s existing convention. Original trigger preserved verbatim in the header comment so re-enabling is exact |

**Correction to an earlier assumption.** CD Deploy did **not** queue a phantom run on every
push to main — its `push:` trigger carries a `paths:` filter (`docker-compose.*.yml`,
`.env.*.template`, `scripts/deploy-node.sh`, `configs/**`). Checked against all nine commits
of 2026-08-22: **none matched**, so it fired on none of them. It was disabled on the other
two grounds, not on trigger frequency.

**Why CD Deploy stays off regardless of the runner.** It runs `scripts/deploy-node.sh`, which
does `docker compose down` on the **whole stack** and pulls from GHCR — precisely what the
runbook's `--no-deps` rule and the `--pull never` correction exist to prevent
(`WP-DEPLOY-INCIDENT` §4). It would restart Postgres to deploy a worker. It carries
`environment: production` with real secrets and auto-triggers on a path match. Manual
deployment as practised on 2026-08-22 is gated, verified and reversible; this is not.

### Runner revival — DEFERRED
**Re-open trigger:** a decision that CD should be automated at all, or another workflow that
genuinely needs node-01. Not needed for the compliance gate, which now runs GitHub-hosted.

Four requirements, all necessary — the service as written cannot work even if started:
1. **A fresh registration token.** `GITHUB_RUNNER_TOKEN` in `.env` is non-empty but ~3 months
   stale; registration tokens expire in about an hour.
   `gh api -X POST /repos/{owner}/{repo}/actions/runners/registration-token`
2. **A `command:`/entrypoint.** The compose block has neither. The official
   `ghcr.io/actions/actions-runner` image does not self-register — it ships `config.sh` and
   `run.sh` and must be told to run them. This is why it exits in 0.145 s.
3. **A named volume** for runner config and `_work`. Only `/var/run/docker.sock` is mounted
   today, so registration would live in the container layer and vanish on any recreate.
4. **A decision on the Docker socket** — see condition A.

**TWO BINDING CONDITIONS, operator ruling 2026-08-22. Neither is advisory.**

> **A. No Docker socket mounted unless a specific job demonstrably needs it.** The service
> currently mounts `/var/run/docker.sock`. A self-hosted runner holding the host Docker
> socket while executing workflow-authored code is root on node-01 for whoever authored that
> code. If some job genuinely needs it, that job gets it — not the runner as a standing grant.
>
> **B. `pull_request` never targets self-hosted.** `compliance-check.yml:17` triggers on
> `pull_request`; combined with A, that was root on node-01 for whoever opened a PR.
> GitHub's fork-approval default is a policy setting, not a guarantee, and is the wrong
> thing to rely on. Now moot for the compliance audit — it is GitHub-hosted — and it must
> stay moot.

### Not verified
No GitHub-side state was inspected: there is no `gh` credential on node-01 (`gh auth status`:
not logged in). Whether other runners are registered, how many runs sit queued behind #341,
and whether repo settings permit fork workflows are all unknown from this box. **Run #341 and
any siblings will stay queued until cancelled in the UI** — the fix stops new ones, it does
not drain the existing queue.

## P1.4l — Compliance Rules 1 and 3 fixed; gate green — **RESOLVED** *(2026-08-22)*
**Status:** **RESOLVED.** Rule 1 **FIXED**. Rule 3 **FIXED** by operator ruling 2026-08-22.
All five rules verified passing against a simulated CI checkout. Node-20 deprecation **P3, noted**.

### Rule 1 — fixed
The rule was a bare substring match, so it fired on the prohibition comments that *document*
the policy — `# OPENAI_API_KEY — NEVER` in `.env.template` and all six
`.env.node0X.template` files — and on the scanner's own test fixtures in
`tests/test_compliance_scanner.py`. **Operator ruling: fix the rule, not the sources** —
those comments are the policy's documentation and must not have to hide from its enforcement.

Now anchored: `^[[:space:]]*(VAR1|...)[[:space:]]*[=:]` — start of line, optional whitespace,
name, optional whitespace, `=` or `:`. Gated both ways: **zero** hits across a simulated CI
checkout (651 tracked files), and it still catches a synthetic real assignment at column 0,
an indented one, and the YAML `KEY: value` form. The `[=:]` alternation closes a real gap —
this rule scans `*.yml`/`*.yaml`, where a leak reads `OPENAI_API_KEY: sk-...` with a colon,
which an `=`-only anchor would miss entirely.

### Rule 3 — the same defect, newly found, NOT fixed
**Each rule `exit 1`s on its first hit, so the job stopped at Rule 1 and Rules 2-5 never
ran.** Fixing Rule 1 does not produce a green run; it reveals Rule 3, which fails on:

| File | Lines | What it actually is |
|---|---|---|
| `ivgs-infra/scripts/v4_to_v5_migration.py:52-56` | 3 | `CLOUD_ASSET_PATTERNS` — the list of cloud URLs the migration script **searches for and removes**. Detection code, not usage |
| `tests/test_compliance_scanner.py` | 4 | The scanner's own test fixtures |

Identical class to Rule 1: **the enforcement's own references to the thing it forbids trip
the enforcement.** But the fix is a genuine judgement call rather than a mechanical one, so it
is recorded here rather than applied. A comment is distinguishable from an assignment by
regex; a URL in a *pattern list* is not distinguishable from a URL being *called*.

**RESOLVED — operator ruling 2026-08-22: APPROVED.** File-level exclusions applied to Rule 3,
mirroring the existing `--exclude="compliance_scanner.py"`:
`--exclude="test_compliance_scanner.py"` and `--exclude="v4_to_v5_migration.py"`, with an
inline comment in the workflow stating that both hold detection patterns and fixtures rather
than live calls, and that Rule 5 still covers them.

**The accepted trade, stated plainly so it is not rediscovered as a surprise:** a genuine
prohibited call added to either file would not be caught by *this rule*. Accepted because a
URL in a pattern list is not distinguishable by regex from a URL being called, and because
**Rule 5 — `scripts/compliance_scanner.py`, the scanner §F.2 actually names — still scans both
files** and reports 0 violations across all 651 tracked files.

**Verified after the change**, against a simulated CI checkout built from tracked files only:

| Rule | Result |
|---|---|
| 1 prohibited env vars | PASS |
| 2 prohibited pip packages | PASS |
| 3 prohibited API endpoints | **PASS** |
| 4 prohibited imports | PASS |
| 5 `compliance_scanner.py` | PASS — 0 violations, 651 files, exit 0 |

**Negative control:** a synthetic `httpx.post("https://api.openai.com/...")` dropped into a
non-excluded file is still **caught** by Rule 3. The exclusions narrow the rule to two named
files; they do not disable it.

**Reassurance on the substance:** `scripts/compliance_scanner.py`, the actual §F.2 scanner and
the more capable tool, was run over the same simulated checkout and reports **0 violations
across 651 files, exit 0**. Rules 2 and 4 also pass. The repository is compliant; only two of
the five grep rules mis-classify their own enforcement code.

### P3 — actions run on deprecated Node 20
`actions/checkout@v4` and `actions/setup-python@v5` execute on the Node 20 runtime, which
GitHub has scheduled for deprecation; runs emit a warning. Cosmetic today, breaking whenever
GitHub retires the runtime. **Fix when convenient:** bump to whatever major currently ships a
Node 24 runtime. Not urgent, not touched here — it is a warning, not a failure, and bumping
action majors unreviewed is how unrelated breakage arrives.

## P1.4m — The Model Store cannot bind eight of nine stages; Stage 1 dies before it starts *(new, WP-IVGS-0 pre-deploy gate, operator ruling 2026-08-22)*
**Status:** OPEN — **blocks the whole pipeline.** Read-only measurement of the live `ivgs`
database, 2026-08-22. Not caused by WP-IVGS-0; found by its pre-deploy gate.

`get_binding` (AD-01.9, `shared/providers/factory.py:171-190`) falls back to the
`(stage, tier)` default only for a model that is `is_default` **and** `state=approved`
**and** `enabled`. Measured against every (stage, tier) pair:

| Stage | prototype | production |
|---|---|---|
| `talking_head` | RESOLVES | RESOLVES |
| **all eight others** | **SelectionError** | **SelectionError** |

`project_model_selections` holds **0 rows**, so nothing reaches the selection branch either;
`model_node_availability` holds **0 rows**, so any binding that did resolve would carry
`node_id=None`. Of 13 models, only the two `talking_head` rows are `approved`; the rest are
`candidate` (11) or `retired` (1), and **no `transcript_refinement` model exists at all**.

**Consequence:** `stage1_transcript.py:498` resolves its binding before any prompt or vLLM
work, so **Stage 1 raises `SelectionError` on every run today** and nothing downstream is
reachable. This is independent of, and prior to, every defect WP-IVGS-0 fixed — those fixes
are correct and tested, and none of them can be observed end to end until this is resolved.

**Interaction with WP-IVGS-0.2** (recorded so it is not rediscovered): Stage 3's prompt
writer now resolves a `storyboard_generation` binding at `stage3_images.py:649` and raises if
it cannot, where it previously fell through to the env profile. With the store in this state
that turns Stage 3 from "every scene reports failed" into "the task raises". Moot while
Stage 1 cannot run, and the loud failure is the intended behaviour, but it is a real change.

**Action:** approve and enable a default model per stage, or create selection rows. Needs an
operator decision on which models are certified enough to mark `approved`; P1.4f already
records Model Store hygiene items. **Do not deploy WP-IVGS-0 expecting a working pipeline
until this is closed** — the package fixes real defects but this gate sits in front of them.

## P1.5 — Backup subsystem failure reporting *(new 2026-08-14; replaces the closed secret-hygiene item)*
**Status:** OPEN — the reason a 75-day backup gap went undetected.
Backup tasks return `{'status':'failed', 'returncode':N}` instead of raising, so Celery logs `Task ... succeeded` for a failed backup and every dashboard shows green. Related: direct script runs create no `backup_records` row (the GUI showed 13 records for 75 days of daily attempts, and could not see the only good backup); verification stamps `completed_at` on historical rows, producing 110,502-minute durations; `scripts/backup.sh:374` reads `n_live_tup`, a statistic that resets on restart, which `verify_backup.sh` then compares with a 1% tolerance.
**Scope/action:** raise on non-zero return; `_update_record_failed` sets `completed_at` + `error_message` before raising; record coverage for all invocation paths; write `verified_at` not `completed_at`; frontend duration sanity clamp; real row counts or drop the check. Also investigate why the worker path takes 64 s for work the CLI does in under 1 s. **Agent plan WP-01.**

## P1.5a — `verify_backup.sh` has never been able to pass *(new 2026-08-14)*
**Status:** OPEN.
It reads the **staging** directory (`/tmp/ivgs-backup/<date>`), not the NAS. Compounding this, `backup.sh` writes the checksum file with the staging path embedded, so `sha256sum -c` can never succeed from the NAS. It also spawns a sibling Postgres container with a 2 GB tmpfs via the mounted Docker socket — affordable on 31 GB, and it was never affordable when the box was thought to be 16 GB.
**Scope/action:** point at the NAS directory; write checksums with bare filenames; use real row counts. **Do not run it until fixed.** Agent plan **WP-20**.

## P1.5b — No alert on backup staleness *(new 2026-08-14)*
**Status:** OPEN. `BackupFailed` fires on failure. Nothing fires when a backup simply does not happen — which is the actual failure mode, and was invisible for 75 days because of P1.5.
**Scope/action:** alert on the age of the newest `full_database` record, beyond ~26 hours. Agent plan **WP-21**.

## P1.6 — Defect #4: `Prompt.prompt_type` ENUM-as-String *(carried, v3.1 P1.1)*
**Status:** OPEN (latent — prompt library empty). Will 500 on first INSERT with `DatatypeMismatchError`; architecturally identical to the fixed Defect #3 (`User.role`). **Blocks P1.7.**
**Scope/action:** `app/models/prompt.py:40-43` — swap `String(32)` for `PG_ENUM` mirroring migration 0001's 10 values; the `.cast(String)` workarounds in `prompt_service.py:61,77` become dead. Build, CLI-verify an INSERT. ~45–60 min.

## P1.7 — Prompt-management 9-step browser smoke *(carried, v3.1 P1.2)*
**Status:** OPEN; code deployed in v5.1.8, never functionally smoke-tested. **Hard-blocked by P1.6.**
**Scope/action:** seed 10 system-tier prompts → list → filter → detail → project-tier override → effective resolution → edit → delete → fallback. ~30–45 min once unblocked.

## P1.8 — GPU Fleet acceptance bullets (~18 of 24 deferred) *(carried, v3.1 P1.3)*
**Status:** PARTIAL — ~6/24 walked via browser smoke (Session 9); ~18 edge cases unverified (range validation, 30-day bound, `MAX_HISTORY_POINTS=5000` → 413, multi-node JOIN, sort stability, auth gate 403-vs-401, `power_tdp_w`, chart/legend variants, focus re-fetch, 4xx-no-retry, empty-vs-undefined). Unblocked (test infra restored via PR #48).
**Scope/action:** write `TestGpuUtilizationHistory` covering the deferred bullets. 3–5 h.

## P1.9 — AD-02 governance: record deviation, SPOF failover, long-context decision *(carried, v3.1 P1.6)*
**Status:** OPEN (governance/recording). AD-02 is implemented + verified; the deviation and two decisions are not captured.
**Scope/action:** (a) mark **gap N23-4** (LLM-vs-video card contention) RESOLVED by workload separation; (b) document per-stage manual failover for the new SPOFs (node-02 = sole LLM, node-03 = sole video engine) per AD-02.11; (c) **open decision (AD-02.12 #1):** node-02 vLLM runs `--max-model-len 32768` (below the 128 K aspiration), no explicit `--kv-cache-dtype fp8` — interim pending KV-headroom validation; record + schedule. **Update to AD-02 Draft 3** (node-06 Intel→CUDA, card swapped to RTX 6000 96GB).

---

# WS-T — Orchestration Migration (Temporal) *(new workstream)*

**Rationale.** The orchestration layer is ~6,283 lines, of which ~1,957 is orphaned (P2.1) and the live 1,397-line orchestrator has zero test coverage (P2.2). Four correctness defects (P0.1, P1.1–P1.3) are instances of three structural limits that cannot be fixed in place: (a) Redis-as-broker has no liveness signal, only a guessed timeout; (b) at-least-once delivery requires a hand-written idempotency guard at every fan-out, forever; (c) crash recovery must be designed per-stage, eight times.

**Decision context.** The alternative is not "do nothing" — it is finishing the bespoke layer: wiring P2.1's three services into eight stage tasks, building the checkpoint write path, join idempotency, orchestrator tests, plus the still-unwritten `render_segments` resume and parallel talking-head fan-out. That is ~9–13 sessions for a structurally weaker result maintained by one operator. Temporal is ~8–14 sessions, deletes ~5,200 lines net, and turns the last two items into child workflows.

**Agreed sequence** (supersedes any earlier ordering):

| ID | Item | Status |
|---|---|---|
| **WS-T.1** | Fix P0.1 + P1.1–P1.3 (config + point fixes; **not** a broker swap) | OPEN |
| **WS-T.2** | Close M1: ORCH-6 (P1.0) + Stage-8 validation (P1.4) → verified end-to-end at short duration on node-01 + node-04 | OPEN |
| **WS-T.3** | Capture the known-good short-job reference output (the migration's verification target) | OPEN |
| **WS-T.4** | Author **AD-05 — Orchestration Migration** (§18 amendment artifact): workflow shape per stage, activity boundaries, the two human gates as signals, cutover + rollback, in-flight job handling. Review-board approval before code. | OPEN |
| **WS-T.5** | Stand up the Temporal node (dedicated host — **not** node-01; see risk note) + migrate the coordinator across all 8 stages **in one arc** | OPEN |
| **WS-T.6** | Verify against WS-T.3's reference output; keep the Celery path behind a flag until verified | OPEN |
| **WS-T.7** | Roll out nodes 02/03/05/06 on the new architecture — each node configured **once** (absorbs P3.3 / handoff register #4) | OPEN |

**Then:** long-video testing (M3) with resume-from-failure.

**Scope discipline (hard).** Replace the coordination layer only — stage transitions, completion callbacks, join counters, watchdog, checkpointing, retry/DLQ plumbing. **Preserve** the eight stage bodies (~25,000 lines of June's hard-won domain knowledge: Jinja fixes, extensible-WAV handling, scene linkage, AD-03 duration anchoring, ffmpeg logic) as activities with thin wrappers. **Keep** `ivgs-scheduler`, the API, frontend, DB schema, MBCP seam, Model Store. *If a migration session finds itself editing stage internals, stop — scope control has been lost.*

**Risks to manage.**
- **Half-migration.** P2.3 is a v1→v2 orchestrator migration half-done since June. Mitigation: all 8 stages in one arc; no long-term coexistence; Celery path flag-gated until WS-T.6 passes.
- **node-01 capacity.** 8 vCPU / 16 GB already runs ~13 services and is the P1.9 SPOF. Operator has confirmed additional compute is available — **provision a dedicated Temporal node.** If that changes, DBOS Transact (library-only, no new server, uses existing Postgres) is the resource-respecting alternative.
- **New failure modes.** Determinism constraints; replay-only bugs; versioning discipline for in-flight workflows during deploys (multi-hour renders + multi-day gates make this constant, not occasional).
- **Not a quality fix.** WS-T addresses none of M1. Do not let it displace P1.0/P1.4.

---

# P2 — Medium Priority

## P2.0a — Establish which API endpoint node-04 workers actually call, and why its traffic does not appear in `ivgs-fastapi`'s access log *(new, WP-02 check-5 verification, 2026-08-15)*
**Status:** OPEN — unresolved observability gap. Not a known-broken path: the calls **succeed**.

**What was observed.** During the WP-02 check-5 Stage-6 render on node-04
(2026-08-15 01:54–02:24), the worker demonstrably made successful Pipeline-API
calls against **this** database:

- It downloaded 13 assets (1 reference clip + 12 scene audio) via
  `GET /assets/{id}/download` — the render could not have produced output otherwise.
- Its upload was content-hash deduplicated against asset
  `b45b19ce-c12a-459f-bdf0-1dcae7625a4e`, whose `reference_count` went 1 → 2 and
  whose `last_accessed_at` was stamped `2026-08-15 02:24:01.236` — 33 ms before the
  task's own `stage6_talking_head_complete` at `02:24:01.269`.
- Its checkpoint POST returned **405**, which matches `ivgs-fastapi`'s actual route
  table exactly (GET-only on `/jobs/{id}/checkpoints`, ledger P1.2) — so whatever
  answered behaves like this API.

**What contradicts it.**

- `docker logs ivgs-fastapi` contains **zero** `/assets` or `/jobs` requests across
  **74,969 lines**, spanning container start (2026-08-14 16:48) through the render.
- The access log **does** capture that route family — a control probe from node-01
  appears as `192.168.1.90 … "GET /api/v1/projects/{uuid}/assets" 403 Forbidden`.
- `pg_stat_activity` showed **no** client connection from `192.168.1.93`; only the
  node-01 docker-bridge clients `172.20.0.6` and `172.20.0.12`.

**Candidate explanations — none asserted, all untested:**

1. A second API instance somewhere (on node-04, or elsewhere) sharing this Postgres.
2. A different ingress path (nginx, another published port, or a proxy) whose
   requests are attributed differently.
3. Access-log level or filtering that suppresses these specific routes under some
   condition not reproduced by the control probe.
4. Worker environment on node-04 pointing `API_BASE_URL` at an unexpected URL.

**Why it matters.** Until this is settled, `ivgs-fastapi`'s access log cannot be
used as evidence of what the fleet did or did not call — which is precisely the
kind of blind spot the WP-00 register exists to eliminate. It also means any
audit, rate-limit, or incident timeline built on that log is incomplete for
worker traffic.

**Scope/action:** on node-04, read the worker's effective `API_BASE_URL` and
`full_base_url`, `curl` the resolved host, and trace where the request terminates
(`ss`, `iptables -t nat -L`, container inspect). Then reconcile against
`ivgs-fastapi`'s logging configuration. Cross-node work — operator-run.
*(Deliberately not investigated at discovery time; recorded to avoid an unbounded
detour mid-verification.)*

## P2.1 — 1,957 lines of orphaned operational machinery *(new, code audit; **decide before wiring**)*
**Status:** OPEN — **this is the WS-T fork in the road.**
`RetryEngine` (461), `DLQService` (754), `FallbackChain` (742) are **imported by no stage task**. They reference each other only in docstrings describing an integration that was never built (`dlq_service.py:18`, `fallback_chain.py:23`). Their internal lazy imports use a package that does not exist anywhere in the repo — there is no `ivgs_workers/` directory and nothing in `pyproject.toml` creates the alias — e.g. `fallback_chain.py:459`, `periodic_tasks.py:166`. **14 such imports.** Being inside function bodies they don't break registration; they would `ModuleNotFoundError` on first execution. This is why `periodic_tasks.py` is dormant: it cannot run.
Meanwhile actual retry behaviour is ad-hoc `self.retry()` with hand-rolled `retry_config` lookups (`stage1_transcript.py:678-694`, `stage2_storyboard.py:702-718`), and Table 6-4's backoff sequences are re-encoded as decorator constants across eight files.
**Scope/action:** **Do not wire these in pending the WS-T decision** — 2–4 sessions of work a durable engine makes redundant. **Do** extract `FallbackChain`'s L1→L4 *policy* (needed either way; it is domain logic). Under WS-T these 1,957 lines are deleted outright.

## P2.2 — Test coverage is inverted *(new, code audit)*
**Status:** OPEN — most significant supportability finding.
Zero tests reference `pipeline_orchestrator*`, `handle_stage_completion`, or the media join. Meanwhile `test_retry_engine.py` (236), `test_dlq_service.py` (379), `test_fallback_chain.py` (244) — **859 lines** — cover the P2.1 modules that never execute. The 1,397-line live orchestrator, source of most ledger incidents, is untested.
**Scope/action:** if WS-T proceeds, write tests against the new workflow definitions rather than the doomed orchestrator. If it does not, orchestrator tests become P1.

## P2.3 — Orchestrator cleanup (v1→v2 remaining half) *(carried, v3.1 P2.26; **partially reframed by P1.0**)*
**Status:** OPEN. Safe — nothing calls v1's stage orchestration (functional half closed in `9f692ab`).
**Scope:** (a) excise v1 `pipeline_orchestrator.py` stage-orchestration (`dispatch_pipeline`, `handle_stage_completion`, stub maps) **but keep v1's 6 periodic tasks** that `beat_schedule` actually uses; (b) delete v2's dead inline `build_composition_manifest` (`pipeline_orchestrator_v2.py:~522`; the map dispatches `stage4_manifest`); (c) **dual talking-head file — see P1.0: promote the provider-factory version, don't simply delete it**; (d) the systemic filename-vs-registered-name off-by-one (below) — `9f692ab` aligned the *map*; do **not** rename tasks; (e) kill the dead worker-side `ManifestBuilder`; (f) consolidate `tasks/periodic_tasks.py` (dormant per P2.1); (g) the dead `stage6_talking_head.py:241` carries the wrong `/assets/upload` URL — dies with the file.

**Registered-name mismatch table (verified `e613e844`):**

| File | Registered name |
|---|---|
| `stage5_voiceover.py` | `tasks.stage4_voiceover.generate_voiceover_task` |
| `stage6_talking_head.py` | `tasks.stage5_talking_head.generate_talking_head_task` *(in no map)* |
| `stage7_prototype_draft.py` | `tasks.prototype_draft_task.assemble_prototype_draft` |
| `stage8_final_render.py` | `tasks.final_render_task.render_final` |

Each is a runtime-only `next_stage_task_not_registered` waiting to happen; none is caught by any static check. *(Independently corroborated by AD-04-v3 §8, which flags the Stage-6 map entry.)* WS-T removes this class entirely (typed calls, import-time failure).

## P2.4 — Residual 4xx cluster *(carried, v3.1 P2.27; checkpoint line item promoted to P1.2)*
**Status:** OPEN — render proceeds through all of these.
`POST /clip/score` → **404** (images get `quality_decision: flagged`, `clip_score: null`); `GET /assets?sha256=` → **404** (dedup absent → duplicate rows on re-fires; dedup also wouldn't backfill `scene_id`); `POST /quality-scores` → **404** (quality persistence absent). Re-enable dedup/quality when the quality/composition stages need them.

## P2.5 — ORCH-5: worker → `projects.state` mapping (+ tighten `approve_storyboard` guard) *(carried, v3.1 P2.28)*
**Status:** OPEN — confirmed reproducing. After a full run `projects.state` stays stale even though the pipeline advanced; the dashboard view is misleading (render-job stage + dispatched tasks are the de facto truth). The deliberately lenient `approve_storyboard` guard (`project_service.py`) accepts pre-`STORYBOARD_GENERATION` states and is empirically relied upon by the e2e.
**Scope/action:** update `projects.state` on each transition. **FIX-WHEN:** once state advances correctly, tighten the guard per spec Table 4-3. *(Under WS-T this becomes a workflow query — truthful by construction. Consider deferring the full fix into WS-T rather than fixing twice.)*

## P2.6 — GPU monitoring + heartbeat registry (Blackwell) *(carried, v3.1 P2.29)*
**Status:** OPEN — two coupled gaps; dashboard GPU telemetry is **not trustworthy**.
(a) **Exporter:** `utkuozdemir/nvidia_gpu_exporter:1.2.1` panics on Blackwell (`clocks_event_reasons_counters.sw_thermal_slowdown [us]` → invalid metric name) → CrashLoop on nodes 02/03/04. Restrict `--query-gpu`, bump to a name-sanitizing tag, or move to dcgm on a Blackwell tag. (b) **Heartbeat:** registry empty (`total_nodes:0` → `gpu_reservation_skipped`; scheduler `:8002` → 503). Wire node GPU heartbeat registration. **Pairs with P1.3** — the reservation subsystem fails open, which is why this stayed invisible. *Not addressed by WS-T.*

## P2.7 — MBCP: `serving-authoring-loop-1` unhealthy *(new, handoff register #2)*
**Status:** OPEN — pre-existing on `.51`. Diagnose.

## P2.8 — MBCP RuntimeClass refactor — **CLOSED** *(corrected 2026-08-14)*
**Status:** CLOSED. The consolidation was **already merged as PR #48** — `mbcp_adapters/runtimes/comfyui.py` plus nine JSON graphs. The "awaiting approval on Tasks B/C/D" framing in v4.0 was stale, and the Option-B split decision taken on that basis is moot. Recorded so the trail is visible rather than silently dropped.

## P2.9 — MBCP: CogVideoX adapter — **rebuilt, never GPU-tested** *(corrected 2026-08-14)*
**Status:** Code defect CLOSED; re-opened as MBCP **WP-A**. Verified in `cogvideox-5b.json`: `CLIPLoader`, `CogVideoTextEncode`, `CogVideoSampler`, `CogVideoDecode`, `DownloadAndLoadCogVideoModel` — the correct names, no X-suffixed phantoms. **But it has never touched a GPU.** MBCP WP-A is that smoke test and blocks WP-B. Every VRAM figure in `comfyui.py` remains `PROVISIONAL` (see S-7). Treat the first GPU smoke as a gate, not a formality.

## P2.10 — Weight-fetch live pass *(carried, handoff register #5)*
**Status:** OPEN — never exercised. IVGS **pulls** weights via `ivgs-models/mbcp_fetch.py` against `{serving_url}/weights/{model}/manifest`. Needs the fleet up (WS-T.7) plus `MBCP_SERVING_TOKEN` + `MBCP_WEIGHT_SIGNING_KEY` handoff. *(Direction is pull, not push — do not invert in docs or code.)*

## P2.11 — `IVGS_SCHEDULER_TAG=latest` — pin *(carried, v3.1 P2.11)*
**Status:** OPEN. §19.5 no-`:latest` violation; the only unpinned tag in `.env`. Confirmed `:v5.1.0` == `:latest` (same image ID) → pinning is a zero-behaviour-change close.

## P2.12 — No manifest regenerate/reset *(carried, v3.1 P2.30)*
`composition_manifests.job_id` is UNIQUE with no reset endpoint; re-running Stage 4 can't regenerate. Add a reset/regenerate path.

## P2.13 — Animation stored as `asset_type="image"` *(carried, v3.1 P2.31)*
Interim relabel; the manifest groups animation as image. Give animation a distinct type for correct layer semantics.

## P2.14 — `assets.duration_seconds` not persisted on upload *(carried, v3.1 P2.32 + Addendum B1 — merged)*
The voiceover task computes real per-scene durations and the column exists, but `POST …/assets/upload` accepts only `file/asset_type/scene_id/language_code` → all audio rows `NULL`. Stage 7 works around it by re-deriving the timeline via `ffprobe`. **Root of the "duration disease"** — Stage-4 storyboard estimates (115s) were never reconciled against real narration (~214.94s). **Fix:** add a `duration` form field (plus `sample_rate`/`bit_depth`) or probe server-side.

## P2.15 — `seaweedfs_path` not unique per scene *(carried, v3.1 P2.33)*
Server derives the audio path from project + language only, so all same-language audio share one path string with distinct FIDs; the worker reports a *different* path. Latent trap for anything reconstructing paths instead of using `seaweedfs_fid`/`asset_id`. Include `scene_id` in the server path; align the worker's reported path.

## P2.16 — Rollback snapshot/restore unwired *(carried, v3.1 P2.35)*
Storage-path crash fixed (`c3e8a1a`), but `rollback_service.py` (~164/241/244) still references `/ivgs/ivgs-api/config` and `/ivgs/.env`, and `rollback_to` restarts containers — full §14.3 rollback needs host-level `deploy-node.sh` integration. Decide: wire to the real layout, or remove.

## P2.17 — Voiceover dead scene→audio back-link PATCH (401) *(carried, v3.1 P2.36)*
Fires 6×/run. Audio is already scene-linked via the upload form's `scene_id` (`eaddebb`), so the back-link adds nothing and is swallowed as a warning. Confirm nothing reads `scene.audio_asset_id`, then delete the call + helper. Bundle with P2.3.

## P2.18 — `GET /assets?asset_type=reference_clip` returns 500 *(carried, v3.1 P2.37)*
Orchestrator's presenter-clip lookup 500s; the orchestrator soft-continues so it doesn't block. A 5xx server bug — likely an enum/query mishandle in `list_assets`. Return empty list / clean 404 so Stage 6 can take the no-clip skip path.

## P2.19 — stage7 caption clock not audio-anchored *(carried, Addendum B2)*
Latent until captions are enabled (Remotion on node-06, WS-T.7). Anchor the caption clock on real audio length, same principle as the Pillar-1 fix.

## P2.20 — Duplicate/accumulated assets; no supersede-or-prune *(carried, Addendum B3)*
Re-fires accumulated multiple draft assets (`0a83f6f2`, `8e0c8531`, `4a9ce479`, `061f64eb`, `f78eb063`) plus duplicate per-scene audio. Add an asset supersede/cleanup policy. Inflates SeaweedFS and muddies "current best".

## P2.21 — Defect #5: "[object Object]" validation banner *(carried, v3.1 P2.3)*
Frontend error-handler doesn't string-coerce FastAPI's structured detail envelope. Extract `detail[0].msg`. Pairs with P2.23.

## P2.22 — Defect #9: `/api/v1/nodes` stub hardcodes `status="online"` *(carried, v3.1 P2.4)*
`nodes.py:82` returns "online" unconditionally → "6 online" when only node-01 runs. Interim ICMP/DNS ping, or full fix at fleet rollout. Don't add `test_nodes.py` until then (would freeze the lie).

## P2.23 — Backend UUID path-param validation (422 not 500) *(carried, v3.1 P2.7)*
Class-level UUID validation; architectural decision on scope + error envelope. Pair with P2.21.

## P2.24 — Migrate ad-hoc `fetch()` to centralized api-client *(carried, v3.1 P2.6)*
16 sites in 7 files + GPU-history call → `src/lib/api-client.ts`; add a pre-commit hook blocking unprefixed `access_token` reads.

## P2.25 — CI scaffolding (Actions + Playwright + pytest) *(carried, v3.1 P2.13)*
(a) Playwright smoke for the 8-page + 9-step walks; (b) `build-images.yml`; (c) PR template (stale-base + tsc + migration-roundtrip + overlay-rule). Multi-session.

## P2.26 — Test directory scope unification *(carried, v3.1 P2.1)*
`tests/` (9), `ivgs-workers/tests/` (16), `ivgs-scheduler/tests/` (4) unrunnable; `conftest.py` collision blocks a unified `testpaths`. Resolve via `importmode=importlib`; wire testcontainers + Alembic. Pairs with P2.27, P2.2.

## P2.27 — `tests/` pytest collection fails on SQLite *(carried, v3.1 P2.24)*
`shared/database.py:31` passes `pool_size`/`max_overflow`/`pool_timeout` unconditionally; SQLite/NullPool → TypeError at `create_engine`. Make the factory dialect-aware.

## P2.28 — Author RUNBOOK.md *(carried, v3.1 P2.18)*
High institutional value; more material than ever. §1 session-start gate; §2 deploy invariants (build from monorepo root; `--env-file` + `-f` overlay rules; `--force-recreate --no-deps <svc>`; derive compose invocation from container labels); §3 image-drift lesson; §4 backup; §5 incident response. **Absorbs P2.21-tag-taxonomy from v3.1.** Prerequisite for delegating work to agents.

## P2.29 — Compose reconciliation: `base.yml` vs `node01.yml`; monitoring net *(merges v3.1 P2.19 + P2.25)*
`base.yml` (seaweedfs 3.80, underscore volumes) vs `node01.yml` (3.71, hyphen volumes) — twice caused recreate accidents; reconcile or delete `base.yml`. `docker-compose.monitoring.yml` references non-existent external net `ivgs_default` (real net: `ivgs-infra_ivgs-net`) — latent because deploys use `--no-deps`.

## P2.30 — Image/dependency hygiene *(merges v3.1 P2.8, P2.10, P2.15, P2.22)*
(a) Old GHCR image cleanup — 14+ stale tags each for api/frontend; author a retention policy. (b) bcrypt/passlib version warning at startup — pin compatible versions. (c) Restore `@sha256` digest pins on base images lost in `b933357`; pin live `v5.5.x` digests in compose. (d) Pre-commit hook failing `*.key`/`*.crt`/`*.pem` under `configs/nginx/ssl/`.

## P2.31 — Update `IVGS_INFRASTRUCTURE_REFERENCE` *(carried, v3.1 P2.17)*
Still describes a split repo. Update to the monorepo at `/opt/ivgs`.

---


## P2.32 — AD-07 v2.x contract extension: style bible, continuity IDs, source refs *(new 2026-08-22)*
**Status:** OPEN — **recording only, nothing implemented.**
**Origin:** operator-commissioned external design review, 2026-08-22. Working note on node-01
at `docs/Assessment_External_Orchestrator_Prompt_vs_IVGS_2026-08-22.md` — **currently
untracked**; commit it if this entry is to have a durable citation.

Extend the AD-07 Scene Contract (§2.2) with three additions:

1. **`style_bible`** — a per-project block, authored once and carried whole, describing the
   visual language every generated asset must obey.
2. **Persistent continuity IDs** — stable identifiers for characters, environments and
   reusable assets, so the same person or place is recognisably the same across scenes and
   across regenerations.
3. **`source_refs` per scene** — optional, pointing at the material a scene was derived from.

**Gate — this is the point of the entry.** This extension MUST be drafted **and ratified**
before implementation of **WS-H (certified head model)** begins. Generated-visual continuity
depends on it: standing up a certified head without a continuity contract produces a model
that is certified against a looser private contract than the one the pipeline needs, which is
exactly the drift AD-07 §6.3 exists to prevent.

**Relationship to AD-07 as ratified.** This is a v2.x *extension*, not an amendment to what is
already ratified — the Brief and Scene Contract v2 stand unchanged. It needs its own draft and
its own ratification.

## P2.33 — Stage-2 computes a duration total and never checks it *(new 2026-08-22)*
**Status:** OPEN — **recording only.** Cheap; **Track P candidate.**

`stage2_storyboard.py` computes `total_duration` but never compares it against
`max_runtime_seconds`. The runtime target reaches the model as a **prompt suggestion only**,
so a storyboard may plan well past the user's stated budget and nothing says so at plan time.
The first hint arrives after audio and render time have already been spent.

**Scope/action:** add an **advisory** check — warn or flag when the planned total falls outside
`runtime_tolerance_pct` of `runtime_target_seconds`.

**Binding constraint on the fix.** It must **never override the AD-03 measured-audio anchor.**
Measured audio is ground truth for duration; this check is a plan-time smell test, not an
authority. A gate that trims scenes to hit a planned number, in preference to what the audio
actually measures, would be a regression dressed as a feature.

**Relationship to AD-07.** AD-07 §2.2 specifies a real duration validator with a body. This
entry is the cheap advisory version available **now**, on the current contract, and is not a
substitute for that validator.

## P2.34 — `visual_style` is a dead knob *(new 2026-08-22)*
**Status:** OPEN — **recording only.**

`stage3_images.py` reads `visual_style` from `project_context`, but **nothing in `ivgs-api`
ever populates it**. Every project therefore generates with the hardcoded default, and the
knob appears to exist while doing nothing.

**Same defect family as WP-IVGS-0 defect 0.1** — a user-facing field that never reaches the
stage that would consume it, the read side built and the write side absent. See
`dev/workpackages/WP-IVGS-0_Defect_Fixes.md`.

**Scope/action:** fix alongside **P2.32** (where `style_bible` supersedes a bare
`visual_style` and the field needs designing rather than merely wiring), or as part of the
WP-IVGS-0 follow-up if that lands first. **Do not wire it in isolation** without deciding
which of the two owns the field, or the same conflict is rebuilt one layer up.

# P3 — Low Priority

| ID | Item | Note |
|---|---|---|
| P3.1 | `GpuNodeStatus` UPPERCASE half (dead code) | `types/api.ts`; backend emits lowercase only. Delete + `tsc --noEmit`. |
| P3.2 | Empty underscore-named seaweedfs volumes | Four empty 4K volumes from an S5 mis-application. Verify no compose refs, then remove. |
| P3.3 | Endpoint test coverage (9 modules) | No tests for `alerts`, `jobs`, `languages`, `manifests`, `nodes`, `quotas`, `rollback`, `ws_logs`. Priority `jobs`/`rollback`. |
| P3.4 | Rogue-branch attribution investigation | 10 commits by `node01-ops <ops@ivgs>`; branch force-deleted Session 9. Operator-driven; blocks nothing. |
| P3.5 | Cosmetic / UI polish | Banner auto-dismiss; action-message badge polish. |
| P3.6 | Session hygiene bundle | `.bak` cruft in `ivgs-workers/`; GPU-node source-tree drift; ~30 `.env.bak.*` in `ivgs-infra`; `/root` tarball + stage cleanup on both hosts. *(Absorbs v3.1 P3.7 + handoff register #3.)* |
| P3.7 | `composition_manifests.manifest_version` left NULL | API `generate` doesn't populate it. |
| P3.8 | `render_jobs` has no `updated_at` column | Minor schema inconsistency; add for audit parity. |
| P3.9 | In-code Coqui default still wrong (guarded) | `stage5_voiceover.py:~516` hardcodes `http://node-04:5002`; env URLs override. Correct on next build. |
| P3.10 | Audio validator doesn't parse `WAVE_FORMAT_EXTENSIBLE` SubFormat GUID | `_parse_wav_header` reads only the first 16 `fmt ` bytes. Fine for current XTTS output. |
| P3.11 | Downstream audio readers must tolerate extensible WAV | Any stage using stdlib `wave` (raises on `0xFFFE`) will fail. Verify tolerant decoders or transcode at the Stage-5 boundary. |
| P3.12 | Clients swallow real exceptions to `""` | `flux_client`/cogvideox/coqui mask root causes (the Stage-5 10s Coqui timeout hid this way). Surface real errors. |
| P3.13 | Properly type `FlaggedAsset.metrics` | Currently `any`; define a discriminated union. |
| P3.14 | Forensic correction: Session 5 close | Record PR #45/#46/#47 merges; note the `deps.py` path typo. |
| P3.15 | Dead `get_beat_schedule()` in `periodic_tasks.py` | *(handoff register #3)* Dies with P2.3(f). |
| P3.16 | Backup-worker hardcoded DSN fallback | *(handoff register #3)* |
| P3.17 | Per-project model-selection GUI + auto-weight-fetch-on-approve; light-mode contrast sweep; authenticated `/nodes` topology check | *(handoff register #6 — optional/future)* |

---

# S — Cross-System (IVGS ↔ MBCP)

**These belong to neither register and will be dropped by both unless owned.** Source: Step 10 reconciliation, 2026-08-14.

| ID | Item | Owner | Note |
|---|---|---|---|
| **S-1** | Coordinated ingest-token rotation **+ Postgres password** | **Operator** | `MBCP_AD01_TOKEN` == `IVGS_MBCP_INGEST_TOKEN`. Exposed on the MBCP side 2026-08-04. Rotating one side alone breaks the seam **silently** — exports park in `drain-pending-exports` and retry every 5 min. Both hosts in one window. **WIDENED 2026-08-22 (WP-DEPLOY-R2-R5-NODE04 §4.1):** the incident report's R4 verification block ran `docker exec … env \| grep IVGS_`, printing **`IVGS_MBCP_INGEST_TOKEN`** — the one variable CLAUDE.md §3 forbids printing — **and the Postgres password**, carried in clear text inside `IVGS_CELERY_RESULT_BACKEND`. Both reached a terminal and an agent transcript. **The Postgres password is now in this rotation set**; it was not before. Blast radius is wider than the token's: `DATABASE_URL`, `IVGS_CELERY_RESULT_BACKEND`, `ivgs-infra/.env`, `.env.node0*` on every node, `/etc/ivgs/cron-backup-env`, and the backup scripts. The offending grep has been narrowed in all four places it appeared (R4 block, runbook §3.4, CLAUDE.md §6, and this package's own report). |
| **S-2** | Stage taxonomy divergence | IVGS agent | IVGS has 8 **pipeline** stages; MBCP has 9 **capability** stages (`mbcp_core/enums.py`). MBCP's image/video/animation → IVGS Stage 3; `composition` collapses 4/7/8; `translation` is not an IVGS stage. AD-01's `(stage,tier)` key uses MBCP's taxonomy. Document in AD-01 §AD-01.16 + glossary. |
| **S-3** | Addendum number collision | Operator | Two different AD-05s (IVGS orchestration, MBCP adapter authoring) and MBCP also has AD-06. **Decision D-7: namespace as `IVGS-AD-NN` / `MBCP-AD-NN`.** No renumbering. |
| **S-4** | Weight-fetch unblocked earlier than assumed | IVGS agent | IVGS is cloned at `/root/IVGS` on `.51`, so `mbcp_fetch.py` can be proven now. Only the production pass needs M4. Sequence **after** S-1, since `WEIGHT_SIGNING_KEY` and `WEIGHT_SERVICE_TOKEN` are in that rotation set. |
| **S-5** | Schema coupling with no test | MBCP agent | `e613e84` added `ffmpeg` to `ModelEngine` to unblock MBCP composition exports; MBCP added `ExportBundle.engine`. Coupled across two repos, **no test either side**. Agent plan **WP-17**. |
| **S-6** | 8 of 18 certifications rest on audited overrides | MBCP (WP-I) | AD-01 treats certification as evidence for approval. IVGS cannot see which certificates are full-gate. Attestation should carry gate status. |
| **S-7** | VRAM figures are `PROVISIONAL` | IVGS agent | 15 placeholders in MBCP's `comfyui.py`. **D-8: does `ivgs-scheduler` consume declared VRAM, or measure locally?** If declared, MBCP WP-A becomes an M4 prerequisite. Agent plan **WP-19**. |
| **S-8** | CogVideoX resolution overclaim | MBCP (WP-B) | Declared 1920×1080; engine is 720×480. If IVGS ever sizes a request from these specs it will ask for the impossible. |
| **S-9** | `.7` and `.53` absent from IVGS docs | IVGS agent | **Partially closed 2026-08-14** — `.7` is now IVGS's backup target and appears in `dev/CLAUDE.md` and `configs/systemd/README.md`. `.53` (authoring LLM, firewall permits only `.51`) still undocumented on the IVGS side. |
| **S-10** | `.51` is a Proxmox clone with a parked twin | Operator | Shares `machine-id` and SSH host keys with the parked production VM. node-01 holds a known-hosts entry for `.51`. Regenerate before both run; expect to clear node-01's entry. |

## P2.35 — Proposed AD-01 amendment: an auxiliary text-generation ModelStage *(new, WP-IVGS-0.2, operator ruling 2026-08-22)*
`ModelStage` has nine members and none covers an auxiliary chat-LLM call, so Stage 3's image-prompt writer borrows `storyboard_generation` and Stage 5's narration optimiser borrows `transcript_refinement` (`utils/llm_binding.py`; bindings KEPT as implemented by ruling) — propose a dedicated stage at the next AD-01 amendment and repoint those two call sites.

## P2.36 — Per-run tier selector in the UI — DEFERRED to M6 *(new, WP-IVGS-0.3, operator ruling 2026-08-22)*
`?tier=` is plumbed end to end on `POST /projects/{id}/trigger` and `POST /projects/{id}/storyboard/approve` and defaults to prototype, but nothing in the frontend sets it; surface a per-run choice at M6.

# DEFERRED (conscious, with re-open trigger)

## DEF.1 — Comprehensive disaster recovery *(carried, v3.1 P3.14 — **premise materially changed 2026-08-14**)*
**Deferred until:** full fleet up + AD-01 complete. **Re-examine now:** the storage leg is done. Backups run to `.7` NFS (22 TB, hard mount) and 38 GB of image artifacts have an off-node copy with six verified checksums. v4.0's statement that backups lived on node-01's disk was wrong — they were on `.9` CIFS, now retired. What genuinely still needs the full fleet is per-node compose/`.env` capture and the fleet-wide restore procedure. **A restore drill against `.7` has not yet been run for IVGS** (MBCP has run one). Design DR using non-node location(s) — local NAS + offsite — covering git repo, `/mnt/models` weights, Postgres, SeaweedFS/Redis, per-node compose + `.env`. Closes the gap where `/mnt/ivgs-shared` backups live on node-01's disk and don't survive a node-01 failure.
**Decided 2026-06-02 (recovery/image-artifact policy):** large GPU images are **not** pushed to GHCR (free-tier limits); recovery = Dockerfile-in-git + `docker save` artifact on owned storage (`scripts/save-image-artifact.sh` → `/mnt/ivgs-shared/image-artifacts/` with SHA-256 + MANIFEST) + re-acquirable weights; compose uses `pull_policy: never`. Procedure in `RECOVERY.md`.

## DEF.2 — Localisation pipeline (§17)
**Deferred until:** M8 / post-launch. `language_variants` table and state exist; no variant has been exercised end-to-end. Re-open when a second language is actually required.

## DEF.3 — PowerPoint ingestion *(new 2026-08-22 — backlog, no milestone)*
**Deferred until:** PPT input becomes a **real requirement**. **Re-open trigger:** a stated
need to ingest customer decks — not an assumption that it would be nice. Nothing is scheduled
and nothing should be built speculatively.

**Shape, recorded so the idea is not re-derived from scratch.** Ingestion is **per-slide
triage**, not bulk conversion. Each slide is classified into one of six dispositions:

| Disposition | Meaning |
|---|---|
| `REUSE` | take the slide essentially as-is |
| `RESTYLE` | keep content, regenerate to the project's visual language |
| `REBUILD` | keep intent, author the visual afresh |
| `EXTRACT` | harvest specific content (a figure, a table) and discard the rest |
| `REFERENCE_ONLY` | informs the script; never appears on screen |
| `OMIT` | drop entirely |

**Speaker notes are a separate source** from slide content, with their own path into the
pipeline — they are usually the narration intent, while the slide is usually the visual, and
collapsing the two loses exactly the distinction that makes a deck worth ingesting.

**Requires its own addendum.** This touches the Brief, the Scene Contract and the asset model
at once; it is not a work package against the current contract. **Origin:**
operator-commissioned external design review, 2026-08-22.

---

# Operator tasks (not Claude-actionable)

| Item | Notes |
|---|---|
| GPG private key off-network backup | Signing key `4F2243FAB5A25808` needs an off-node copy. Security-sensitive. |
| `.env.node01` gitignore + credential rotation | See P1.5. Operator-driven. |
| Visual QA of `final_1080p_9007b2cf.mp4` | See P1.4(a). Only the operator can judge acceptance. |
| MBCP serving token + weight-signing key handoff | Gates P2.10. |
| Provision the Temporal node | Gates WS-T.5. |
| Commit the two untracked docs | `docs/IVGS_v5_Addendum_AD-04-v3_…md` (451 lines) and `docs/MBCP_Dev_VM_Setup_verified.md` (214) exist only on node-01 — SSOT material with no version control. Scan for tokens/IP literals first. |

---

# Items closed (compressed evidence)

*Full narrative detail preserved in `OUTSTANDING_WORK_archive_v3.1.md`.*

### Closed since v3.1 (2026-06-08 → 2026-08-14)

| Item | Closed | Evidence |
|---|---|---|
| **B4 — LatentSync not production-viable → certified replacement** | 2026-07/08 | MBCP built and operating; bake-off complete; certified models serving to IVGS. *(Consumption blocked by P1.0 — the decision is closed, the plumbing is not.)* |
| **Stage 6 — talking head: BUILD REQUIRED** | 2026-06-07 | LatentSync engine built + proven on node-04 (`latentsync-v5.2.7-h0`); head renders, uploads, composites. |
| **Stage 7 — prototype draft** | 2026-06-07/08 | Draft `f78eb063`, 214.94s, 1280×720, corruption 6/6, operator-confirmed. |
| **Stage 8 — final render executes** | 2026-06-08 | `final_1080p_9007b2cf.mp4`, 215.07s, 1920×1080/30fps, AAC 48k stereo; used as evidence in the AD-04 head judgment. *(Formal validation → P1.4.)* |
| **AD-03 Pillar 1 — A/V duration + corruption** | 2026-06-08 (`v5.4.22-h0`, `4c38240`+`10b2290`) | Scene durations anchored on real audio; draft `061f64eb` 214.97s, video==audio (3.7 ms), corruption 6/6. |
| **AD-03 Pillar 2 — head per-scene desync** | 2026-06-08 (`v5.4.23-h0`, `f0b1f9a`) | Head composited once as a continuous timeline overlay; `num_layers` 3→2; draft `f78eb063` ≈5 ms A/V. |
| **ARCH-1 — Model Store + selection-aware provider factory** | 2026-07-09 | `shared/providers/{factory,binding}.py`, `app/services/model_selection.py`; stages 1/2/3/5 bound. *(Stage 6 → P1.0.)* |
| **AD-01 admin GUI — model lifecycle** | 2026-07-09 | `/admin/models`: candidate → approve (attestation) → set-default (transactional per-(stage,tier)) → deprecate (auto-clears default) → retire. GUI-only. |
| **MBCP ↔ IVGS connected mode** | 2026-07-09 | AD-01 seam receiver `/ad01/v1` + `X-Service-Token`; node self-registration + 30s availability poller; migration 0027 (`ffmpeg` enum) + `ExportBundle.engine`. |
| **MBCP certification backfill** | 2026-07-09 | 21 exports + 2 composition transmitted; all non-revoked certs landed as CANDIDATEs; 24 revoked correctly skipped. |
| **MBCP "Export to IVGS" button** | 2026-07-12 | `docs/MBCP_Delivery_20260712_ExportButton_WSTEST.md`. *(Handoff register #1.)* |
| **P1.5 (old) — `.env.node01` secret hygiene** | 2026-08-14 (`e1f4c58`) | `git rm --cached` + gitignored. Token verified never committed (single added line, no removal; last commit to the file `fa6f4db`, May). File remains on disk. |
| **P0.2 — 75-day database backup gap** | 2026-08-14 | Six root causes: host cron used `POSTGRES_HOST=localhost` against a containerised Postgres (exit 4 daily); `/var/run/ivgs` root-owned so the container path failed on the lock file; `set -euo pipefail` aborted before the rsync check; checksum files recorded the staging path; `.9` was 100% full; Proxmox was OOM-killing the VM. Backup verified: `a4cee889…`, decrypts to 38 `CREATE TABLE`, 12,673 rows. |
| **Storage migration `.9` → `.7`** | 2026-08-14 | 100 GB copied and verified by dry-run rsync; fstab updated to NFS4.2 `hard`; all four backup types (db/assets/config/wal) writing to `.7`. Asset backup 47.7 GB — first since 20 July. `.9` retired, retained as fallback. |
| **Image artifacts off node-01** | 2026-08-14 | 38 GB to `/mnt/store/ivgs-archive`, six checksums verified against the copies. First off-node copy; these are the only reliable recovery route for the Blackwell engine images. |
| **Proxmox host OOM-killing VMs** | 2026-08-14 | Host `n5Pro`, 61 GB, swap fully consumed; killed VM 102 twice during NFS transfers. node-01 reduced 31 GB → 16 GB; 32 GB swap file added. Guest logs were clean because the kills came from outside. |
| **`.61` reference sweep** | 2026-08-14 | Zero references in repo, env files, fstab, mounts, systemd, hosts, cron or container environments. The `.61` NAS does not exist; the retired share was `//192.168.1.9/elearning` over CIFS. |
| **P2.34 — Stage-6 upload-URL pre-check** | verified 2026-08-14 | `talking_head_task.py:155` posts to the correct `…/projects/{id}/assets/upload`. *(The wrong URL survives only in the dead duplicate → P2.3.)* |
| Light/dark theming; login crash fixes; JWT username claim; celery-beat pidfile; AD-02 Draft-3 topology in `nodes.py`; Tier-0 harness; backup-test closeout | 2026-07-09 | Per `SESSION_HANDOFF_2026-07-09.md` §1. |

### Closed in v3.1 and earlier (one line each)

| Item | Closed | Evidence |
|---|---|---|
| A1 — image-generation regression | 2026-06-05 (`d3d1fb4`) | Not a code regression; latent `IVGS_*` env-name mismatch sprung by `--force-recreate`. Cure = canonical names in tracked compose. |
| A2 — node-04 vLLM model name de-band-aided | 2026-06-05 (`d3d1fb4`) | `IVGS_VLLM_MIDSIZE_MODEL=mistral-24b` in tracked compose. |
| A4 — scene-asset linkage (`scene_id` NULL) | 2026-06-05 (`a914352`) | Worker-side root cause; `_upload_to_seaweedfs` omitted `scene_id`. |
| Stage 3 — media generation e2e | 2026-06-05/06 | FLUX 4/4 images+animation; CogVideoX 2/2 videos, ~26 GB peak on the 48 GB card. |
| Stage 4 — composition manifest e2e | 2026-06-05 (`a91cdce`) | Server-side build; manifest `b636fe87` locked, scene_count 6. |
| Stage 4 — media-join failure decrement | 2026-06-05 (`35d9226`) | Failure path decrements + advances with `failed_count`. *(Superseded by P1.1.)* |
| Stage 4 — media-join crash watchdog | 2026-06-05 (`0bde15e`) | Beat `media_join_watchdog` (5 min). *(Compensating code — deleted under WS-T.)* |
| Stage 5 — TTS/voiceover e2e | 2026-06-06 (7 fixes) | Run `3cb8c4d6`: 6/6 scenes, 48 kHz/24-bit, SNR 60 dB, all scene-linked. |
| Storyboard prompt truncation | 2026-06-04 (`a9b2e47`) | Truncated Jinja templates at v5.0.0; reconstructed + baked. |
| AD-02 node specialization implemented | 2026-06-04 | node-02 LLM-only, node-03 video-only, node-04 image+TTS; Stage-3 conformance PASS. *(Governance → P1.9.)* |
| `MEDIA_GENERATION` park (functional half of v1→v2) | 2026-06-05 (`9f692ab`) | 6 call-site repoints + 3 advances + 4 map fixes. *(Cleanup half → P2.3.)* |
| node-03↔04 GPU swap + Stages 1–5 re-validation | 2026-06-06 | node-04 = 96 GB RTX PRO 6000; node-03 = 48 GB RTX PRO 5000. |
| Make Main Honest — merged to `main` | 2026-06-06 (`5657f95`) | 70 commits `--ff-only`; tag `stages-1-5-green-2026-06-06`. |
| API `/ivgs` crash (rollback storage) | 2026-06-05 (`c3e8a1a`) | Repointed to `/mnt/ivgs-shared/rollback_points`. *(Full wiring → P2.16.)* |
| Profile-gating of AD-02 standby services | 2026-06-05 (`68ac33b`) | `profiles: ["standby"]` prevents accidental resurrection. |
| P1.5 — API never dispatches the orchestrator | 2026-06-01 | `trigger_pipeline` → `dispatch_pipeline`; broker options aligned. |
| P2.2 — config externalization (2a–2h) | 2026-05-29/30 | Node IPs single-sourced; `10.10.0.x` eliminated + guarded. |
| P2.12 — Nginx dynamic-resolution hardening | 2026-05-29 (`7173797`) | resolver + variable `proxy_pass` (7 sites) + http2. |
| P2.14 — pre-commit guard for `10.10.0.x` | 2026-05-30 (`e5816d8`) | Hook + `test_no_hardcoded_ips.py`. |
| P2.23 — workers image broken HEALTHCHECK | H.0 (`d349c46`) | Module `worker` → `celery_app`. |
| Phase H.0 — Make Main Honest (code surgery) | 2026-05-31 (`d349c46`) | Provider refactor repaired; all 8 stages wired; 22-task registration green. |
| Defect #8 — test suite restoration | PR #48 (`a836668`) | 512 tests passing; 28 bugs fixed. |
| Phase 14 backup (Stream A + B) | PR #49 | NAS/GPG/pushgateway/WAL/cron + `ivgs-backup-worker`. |
| Engine images (ComfyUI/Coqui/Kokoro/WhisperX) | 2026-06-02+ | Blackwell cu128/sm_120; deployed + healthy on node-04. |
| NFS bulk-transfer wedge | 2026-06-03 | Root cause = inter-switch path, not NIC offload. |
| Node Configuration admin GUI; P1.4 backup-worker GHCR push; P2.9 compose `version:`; Stage-0/2 bring-up; node-02/03/04 de-conflict | May–June | See archive. |

---

# Renumbering map (v3.1 → v4.0)

*Nothing was dropped. Every v3.1 / Addendum ID resolves here.*

| Old | New | Old | New |
|---|---|---|---|
| P1.1 | P1.6 | P2.27 | P2.4 *(405 → P1.2)* |
| P1.2 | P1.7 | P2.28 | P2.5 |
| P1.3 | P1.8 | P2.29 | P2.6 |
| P1.6 | P1.9 | P2.30 | P2.12 |
| P1.7 | P1.5 *(severity revised)* | P2.31 | P2.13 |
| P2.1 | P2.26 | P2.32 + B1 | P2.14 *(merged)* |
| P2.3 | P2.21 | P2.33 | P2.15 |
| P2.4 | P2.22 | P2.34 | **CLOSED** |
| P2.5 | **CLOSED** *(fixed in PR #48 sweep)* | P2.35 | P2.16 |
| P2.6 | P2.24 | P2.36 | P2.17 |
| P2.7 | P2.23 | P2.37 | P2.18 |
| P2.8, P2.10, P2.15, P2.22 | P2.30 *(merged)* | P3.1–P3.2 | P3.1–P3.2 |
| P2.11 | P2.11 | P3.3 | **WS-T.7** |
| P2.13 | P2.25 | P3.4 | P3.3 |
| P2.17 | P2.31 | P3.5 | P3.4 |
| P2.18 + P2.21 | P2.28 *(merged)* | P3.6 | P3.5 |
| P2.19 + P2.25 | P2.29 *(merged)* | P3.7 | P3.6 |
| P2.20 | P3.14 | P3.8–P3.13 | P3.7–P3.12 |
| P2.24 | P2.27 | P3.14 | **DEF.1** |
| P2.26 | P2.3 | B2 | P2.19 |
| Stage-6 BUILD REQUIRED | **CLOSED** | B3 | P2.20 |
| B4 | **CLOSED** | B5 | **P1.0** *(reframed)* |
| Handoff #1 | **CLOSED** | Handoff #2 | P2.7 |
| Handoff #3 | P1.5, P3.6, P3.15, P3.16 | Handoff #4 | **WS-T.7** |
| Handoff #5 | P2.10 | Handoff #6 | P3.17 |

---

# Source documents

| Path | Notes |
|---|---|
| `OUTSTANDING_WORK_archive_v3.1.md` | Full closure narrative preserved from v3.1 + Addenda A/B. |
| `SESSION_HANDOFF_2026-07-09.md` | Live-state snapshot; register folded in above. |
| `IVGS_v5_Master_Sequence_Plan_to_Production.md` | Milestone map — **needs v0.4 to absorb WS-T + the corrected stage status.** |
| `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` | Model lifecycle; the consumer of certifications. |
| `docs/IVGS_v5_Addendum_AD-02_Node_Specialization_Draft3.md` | Authoritative topology; node-06 Intel→CUDA. |
| `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` | Pillars 1–3; frame-aligned splitting. |
| `docs/IVGS_v5_Addendum_AD-04-v3_…md` | MBCP design spec — **untracked on node-01; commit it.** |
| `ivgs_v5_functional_spec.md` | §1.4 SSOT — **§2.1/§6.2/§6.4 need amendment under WS-T.4.** |
| `MBCP_RuntimeClass_Refactor_TaskA_Audit.md` | MBCP adapter audit; drives P2.8/P2.9. |
| `/mnt/transcripts/*.txt` + `journal.txt` | Primary historical record. |

---

# Update protocol

1. Every closure records evidence: commit SHA, image tag, `file:line`, or transcript pointer.
2. New deferrals require a `DEF.n` entry with a stated re-open trigger. Nothing is parked silently.
3. Re-snapshot the counts table at every session close.
4. **Verify against committed code, not summaries** — this document is a map, the repo is the territory.
5. When WS-T lands, retire P2.1/P2.2/P2.3 and the P0.1/P1.1–P1.2 entries together, in one arc, with the reference-output diff as evidence.

*Rebuilt 2026-08-14 against `e613e844` (node-01 == origin/main). Next: Master Plan v0.4, then AD-05.*
