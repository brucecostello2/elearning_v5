# IVGS v5 — Addendum AD-04, v3.1 (Amendment)

## Model Benchmarking & Certification Platform (MBCP)

| | |
|---|---|
| **Amends** | AD-04-v3.0 (2026-06-08) |
| **Version** | **v3.1 — 2026-08-14** |
| **Change-control status** | Draft for review (per §18) |
| **Reason for amendment** | v3.0 was written as a forward design with a Phase-0 review gate ahead of any build. MBCP has since been **built and is in production use**: Phases 0–4 are delivered, the talking-head bake-off is settled, and connected mode is live. This amendment records delivered state, closes the open decisions that implementation settled, and adds the operational defects found since. |
| **Verified against** | `MBCP-main` @ 2026-08-05; `elearning_v5` @ `e613e844`; `SESSION_HANDOFF_2026-07-09.md`; `MBCP_RuntimeClass_Refactor_TaskA_Audit.md` |
| **Application** | §3.1–§3.18 and Appendix AD-04-v3-A are **unchanged** and remain authoritative. This amendment replaces §3.19–§3.21 and adds §3.22–§3.24. |

---

## ⚠ Repository action required

`docs/IVGS_v5_Addendum_AD-04_Model_Benchmarking_Certification_Platform.md` in `elearning_v5` is **v0.1 (2026-06-07)** — two revisions stale and superseded in architecture (single control plane rather than three planes; scheduler reused rather than removed).

**Meanwhile v3.0 exists only as an untracked file on node-01.** The current authoritative design has no version control.

1. Commit v3.0 as `docs/IVGS_v5_Addendum_AD-04-v3_Model_Benchmarking_Certification_Platform.md` — scan for tokens and IP literals first.
2. Apply this amendment.
3. **Delete** the v0.1 file.
4. Commit `AD-04-v3_Analysis_Phase_0_Focus.md` (1,655 lines) to `docs/archive/` — a completed-gate artefact, retained for provenance, not maintained.

## §3.19 Phased build — **delivered status** *(replaces v3.0 §3.19)*

| Phase | Scope | Status |
|---|---|---|
| **0** | Code-level implementation plan + review gate | ✅ **Complete.** Gate served its purpose and is closed; the Phase-0 framing throughout v3.0 is now historical |
| **1** | Spike + MVP / talking-head bake-off | ✅ **Complete.** Adapter contract proven; HF-free weight serving working; synchronized N-up comparison player delivered |
| **2** | Automated quality metrics | ✅ **Substantially complete.** Scoring, aggregates and scorecards live |
| **3** | Human evaluation + certification | ✅ **Complete.** Human-eval queue, aggregates, certification records, revocation with reason, lifecycle |
| **4** | AD-01 integration + ops | ✅ **Complete on the MBCP side** — connected mode live. 🟡 **The IVGS-side weight-fetch pull has never been exercised** (ledger P2.10) |
| **5** | Generalise to all model classes and all 8 stages | 🟡 **Partial.** Adapters exist across stages; **the CogVideoX adapter is broken** (§3.23) |

**The headline outcome is achieved.** The talking-head production model decision — the reason MBCP was built and the M1 quality blocker — is settled on data.

## §3.20 Relationship to the Master Sequence Plan *(replaces v3.0 §3.20)*

Against **Master Plan v0.4**:

- **WS-H's Phase-1 driver is CLOSED.** v0.3's M1 quality gate ("depends on a certified replacement head model") is satisfied.
- **WS-H continues as platform work** — the RuntimeClass refactor and the CogVideoX adapter rebuild (§3.23), running independently of the IVGS milestone track.
- **AD-01's approval path is now functional.** v3.0 correctly stated AD-01 is non-operable without an external acceptance process; that process exists and is connected.

**One carried allowance requires correction.** v3.0 §3.20 states *"Stage-8 final rendering must resolve its talking-head model through the provider factory / AD-01 binding."* **That placement is wrong.** Stage 8 overlays a **pre-rendered** head asset by `asset_id`; it does not render the head. The binding belongs at **Stage 6**.

More seriously, the binding **is not present in the live Stage-6 task**: `talking_head_task.py` imports `LatentSyncClient` directly, while the provider-factory implementation sits in the dead duplicate `stage6_talking_head.py`.

**Consequence for MBCP: the certification chain terminates at a wall.** Certified models flow MBCP → Model Store → approved → and cannot be selected. **MBCP's entire output is currently unconsumable by the pipeline stage it was built to serve.** Tracked as ledger **P1.0 / ORCH-6**; AD-01 Draft 2 §AD-01.15; Master Plan **M1**.

*This does not diminish MBCP's delivery — the platform works and the decision is made. It is one wiring defect on the IVGS side, and it is the highest-priority item in the programme.*

## §3.21 Open design decisions — **status** *(replaces v3.0 §3.21)*

**Closed by implementation:**

| # | Decision | Resolution |
|---|---|---|
| 5 | ARCH-1 sequencing — MBCP delivers `get_provider()`, or IVGS does | **IVGS delivered it.** `shared/providers/factory.py` + `binding.py`; the MBCP adapter shape stayed compatible as the leaning anticipated |
| 2 | Weight-serving transport | **HTTP** — `ivgs-models/mbcp_fetch.py` against `{serving_url}/weights/{model}/manifest`, with checksum verification. **Direction is pull: IVGS pulls, MBCP does not push.** Not yet exercised end-to-end (ledger P2.10) |

**Still open:**

| # | Decision | Note |
|---|---|---|
| 1 | Decisive vs advisory metrics; production talking-head thresholds | Still open, but **less urgent** — the bake-off was settled with human evaluation in the loop. Needed before certification is delegated or automated |
| 3 | Fixture curation and sandbox→fixture promotion policy | Open |
| 4 | Certification expiry policy — what forces re-certification | Open, and **increasingly load-bearing**: the M4 fleet rollout changes driver/CUDA/hardware context across five nodes. Settle before M4, or every existing certification silently becomes of uncertain validity |

**New decision.** *(D-6)* Should MBCP certification records carry the **IVGS Model Store model ID** after a successful export, giving a bidirectional link? Currently the receiver dedups by `certification_id` but MBCP holds no reference back. Would make "which certification is running in production?" answerable from either side.

## §3.22 — Delivered integration state *(new)*

**Connected mode, live since 2026-07-09.**

- **Seam:** IVGS receiver `/ad01/v1`, `X-Service-Token` authenticated. `MBCP_AD01_MODE=connected`.
- **Certify ≠ export.** Export is a distinct admin action, `POST /api/v1/exports {certification_id}`. The receiver dedups by `certification_id`, so re-export is safe.
- **Drain:** `drain-pending-exports` every 5 minutes retries parked rows.
- **Backfill complete:** 21 exports plus 2 composition transmitted; all non-revoked certifications landed in IVGS as CANDIDATEs (including FFmpeg-composition, engine `ffmpeg`); 24 revoked correctly skipped.
- **Schema changes both sides:** IVGS migration 0027 added `ffmpeg` to `ModelEngine`; MBCP added `ExportBundle.engine`. AD-01 rejections surface as `502 AD01_REJECTED` rather than a raw 500.
- **Export-to-IVGS GUI button** delivered 2026-07-12 (`docs/MBCP_Delivery_20260712_ExportButton_WSTEST.md`), closing v3.0's "no GUI button" gap.

**Boundary, restated.** MBCP certifies; AD-01 governs lifecycle and selection. A certification is **evidence, not an approval** — approval remains a deliberate in-IVGS act with attestation. **AD-01 must never auto-approve on certification receipt.**

## §3.23 — Adapter framework defects *(new)*

The RuntimeClass audit (Task A, complete, no code changed) found:

**Fragmentation is narrower than assumed.** vLLM is already a single runtime class; TTS is a single adapter. **Only ComfyUI is fragmented** — three per-model adapters each embedding a full workflow graph.

**The CogVideoX adapter is broken.** Its embedded graph references **four node types that do not exist** in the installed `CogVideoXWrapper`:

| Embedded | Reality |
|---|---|
| `CogVideoXTextEncoderLoader` | Does not exist — T5 loads via core `CLIPLoader` with `type="sd3"` |
| `CogVideoXTextEncode` | Real node is `CogVideoTextEncode` (no "X") |
| `CogVideoXSampler` | Real node is `CogVideoSampler`; adapter also wrongly injects width/height |
| `CogVideoXDecode` | Real node is `CogVideoDecode` |

Plus wrong parameter keys on two loaders that do exist. The correct graph shape has been derived from the wrapper's source and the pinned example workflow; the adapter must be **rebuilt, not extracted**.

**Consequence:** the video stage has **no working benchmark path**. CogVideoX is IVGS's video engine on nodes 02/03 (and node-06 after the AD-02 Draft-3 redesignation), so no video model can be certified before those nodes roll at M4.

`engines/comfyui/CUSTOM_NODES.txt` compounds this — it lists the same non-existent X-prefixed names.

**Approved resolution (2026-08-14): split into two PRs.**

1. **PR 1** — extract FLUX and AnimateDiff graphs to JSON. Both validated as matching installed nodes; low risk; mergeable without GPU access.
2. **PR 2** — rebuild the CogVideoX graph against installed nodes; correct `CUSTOM_NODES.txt`. **Validatable only at a real GPU smoke test — treat that smoke as a gate, not a formality**, since the rebuild is derived from source reading rather than from a working render.

Rationale for splitting: the two pieces carry different risk profiles and should not share a fate. Tracked as ledger **P2.8** and **P2.9**.

## §3.24 — Open operational items *(new)*

| Item | Status |
|---|---|
| `serving-authoring-loop-1` **unhealthy** on `.51` | Pre-existing; undiagnosed (ledger P2.7) |
| Weight-fetch pull path | Never exercised. Needs the fleet (M4) plus `MBCP_SERVING_TOKEN` and `MBCP_WEIGHT_SIGNING_KEY` handoff (ledger P2.10) |
| `docs/MBCP_Dev_VM_Setup_verified.md` | 214 lines, verified 2026-06-08, **untracked on node-01** — commit it |
| MBCP SSOT v3.3 | Requires reconciliation to v3.4 against 2026-08-05 state |
| MBCP `docs/` set (~20 files) | Per-slice requirements and run reports; most should move to `docs/archive/` |

**Note on MBCP's own orchestration.** MBCP shares IVGS's hand-rolled pattern — Postgres status-column ledgers, monolithic Celery tasks with guarded transitions, a `sweep_stuck_runs` zombie reaper, a bespoke `export_drain` retry queue with poison-row parking, and a custom DB-polling Beat subclass. AD-05 addresses **IVGS only**.

MBCP is a materially better candidate for a later migration than IVGS was — it has no in-flight state to preserve at cutover — but **it is explicitly out of scope for now**. Recorded here so the question is deferred deliberately rather than forgotten. Re-open after IVGS's M3 completes and the migration's real cost is known rather than estimated.

---

*AD-04 v3.1 amendment prepared 2026-08-14. Apply over v3.0; §3.1–§3.18 and Appendix AD-04-v3-A unchanged. Commit v3.0 to version control first — the current authoritative design exists only as an untracked file on a single host.*
