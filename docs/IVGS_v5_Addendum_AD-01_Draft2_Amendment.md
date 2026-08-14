# IVGS v5 — Addendum AD-01, Draft 2 (Amendment)

## Model Management Subsystem & Content-Aware Model Selection

| | |
|---|---|
| **Amends** | AD-01, Draft 1 (`docs/IVGS_v5_Addendum_AD-01_Model_Management.md`) |
| **Version** | **AD-01, Draft 2 — 2026-08-14** |
| **Change-control status** | Draft for review (per §18) |
| **Reason for amendment** | Draft 1 was written as a design ahead of implementation. Substantial parts have since shipped — Phase A complete, Phase B largely complete, MBCP live as the external acceptance process — while **one binding is on the wrong file**, which leaves AD-01's central guarantee unmet at the stage that matters most. |
| **Verified against** | `elearning_v5` @ `e613e844`; `SESSION_HANDOFF_2026-07-09.md`; MBCP @ 2026-08-05 |
| **Application** | Sections AD-01.1 → AD-01.11 and Appendices AD-A/AD-B are **unchanged** and remain authoritative. This amendment replaces AD-01.12–AD-01.14 and adds AD-01.15. |

---

## AD-01.12 Rollout plan — **status as at 2026-08-14** *(replaces Draft 1 §AD-01.12)*

**Prerequisites — both closed.**

- **ARCH-1 — provider abstraction as a selection-aware factory.** ✅ **Delivered.** `shared/providers/factory.py`, `shared/providers/binding.py`, `ivgs-api/app/services/model_selection.py`. Built as a selection-aware factory as Draft 1 required, not as static per-engine config — the "fix once, the right way" item was honoured.
- **ORCH-1 / ORCH-2 — runnable pipeline.** ✅ **Delivered.** All eight stages execute end-to-end.

**Delivery phases.**

| Phase | Scope | Status |
|---|---|---|
| **A — Registry** | Schema, registry service, availability poller, admin CRUD | ✅ **Complete.** Migrations 0026 (AD-01 tables) + 0027 (`ffmpeg` engine enum). Node self-registration and a 30-second availability poller are live. |
| **B — Binding** | Provider factory reads selections; per-(stage, tier) defaults; scheduler carries model identity | 🟡 **Largely complete — one gap.** Stages 1, 2, 3 and 5 resolve through the factory. **Stage 6 does not.** See AD-01.15. |
| **C — Intelligence & UX** | Per-scene capability inference, scene-level overrides, full admin UI, test action | 🟡 **Partial.** The `/admin/models` lifecycle GUI is live and GUI-only. The **per-project selection GUI does not exist** (the API does). `MODEL_PLANNING` as a distinct pipeline stage is **not implemented**; selection resolves per job at execution time instead. |

**What shipped beyond Draft 1's plan.**

- **`/admin/models` lifecycle GUI**, state-machine-gated: candidate → approve (attestation required) → set-default (transactional per-(stage, tier) swap; only APPROVED models eligible) → deprecate (auto-clears default) → retire (only from deprecated). **GUI-only, no CLI path** — the hard requirement is met.
- **Selection resolution per job:** project override → (stage, tier) default → error. Implemented as designed.
- **MBCP integration in connected mode** — AD-01.7's external acceptance process is now a real system, not a checklist. See AD-01.15.

**Backward-compatibility guarantee — upheld.** With no `project_model_selections` row for a (stage, tier), the factory uses the `is_default` model. No existing project was broken.

## AD-01.13 Acceptance criteria — **verification status** *(replaces Draft 1 §AD-01.13)*

| # | Criterion | Status |
|---|---|---|
| 1 | Admin registers a `CANDIDATE`; not selectable until approved | ✅ Verified |
| 2 | No `APPROVED` transition without a complete attestation record | ✅ Verified |
| 3 | Model Management page shows models by stage with live per-node availability badges | 🟡 Page live; badges read `nodes:0` until the GPU fleet rolls (M4) |
| 4 | `MODEL_PLANNING` produces a persisted per-stage selection with rationale | ❌ **Not implemented** — no `MODEL_PLANNING` stage; selection resolves at execution |
| 5 | Prototype-tier and production-tier models applied to draft and final respectively | ❌ **Blocked by AD-01.15** |
| 6 | Two contrasting production profiles resolve to different models | ❌ Not demonstrated |
| 7 | Operator overrides at project and scene level, honoured and recorded | 🟡 API exists; **no GUI** |
| 8 | An unserved vLLM model is never selected | 🟡 Constraint implemented; not exercised across the fleet |
| 9 | With no selection present, execution falls back to the default | ✅ Verified |
| 10 | All store mutations and approvals appear in `audit_log` | ✅ Verified |

**Four of ten fully verified.** Criteria 4–6 depend on work not yet done; 3 and 8 depend on the fleet (M4); 7 needs the per-project GUI (M6).

## AD-01.14 Open design decisions *(replaces Draft 1 §AD-01.14)*

| # | Decision | Status |
|---|---|---|
| 1 | Capability inference cost — per-scene LLM classification vs project-level only | **Open**, and now cheaper to defer: `MODEL_PLANNING` was not built, so nothing depends on it |
| 2 | vLLM served-set management — store *drives* or *reflects* the served set | **Resolved: reflects.** The availability poller reports what is served; the store does not command ops |
| 3 | Default taxonomy ratification before Phase A schema freeze | **Superseded.** Phase A shipped; the taxonomy is whatever migration 0026 froze. Re-ratify only if inference (decision 1) is built |
| 4 | Persist the planner's score breakdown, not just the rationale string | **Moot** while `MODEL_PLANNING` is unbuilt |

**New decision.** *(D-5)* Should approving a model **auto-trigger a weight fetch** from MBCP, or remain a separate operator action? Currently separate and untested (ledger P2.10). Recommend keeping it explicit until the pull path has been exercised once against the live serving endpoint.

## AD-01.15 — **ORCH-6: the binding gap at Stage 6** *(new)*

> **This is AD-01's most significant open defect.** It is recorded here because it defeats the addendum's central promise at the one stage where model choice matters most.

**The finding.** `STAGE_TASK_MAP` dispatches `tasks.talking_head_task.render_talking_head`. That live file imports `LatentSyncClient` directly (`talking_head_task.py:42-47`) — **the engine is hardcoded**. The ARCH-1 provider-factory implementation ("render via the AD-01-selected provider (ARCH-1: no engine here)") lives in `stage6_talking_head.py:43-48, 297, 338` — **a dead duplicate that nothing dispatches**.

The AD-01 binding work was done, correctly, on the wrong file.

**Why it matters.** MBCP was built specifically to settle the talking-head model question. That bake-off is complete and certified models flow MBCP → Model Store → approved. They then stop: nothing in the live path can select one. Swapping the production head is a **code change** — precisely the condition AD-01.1 exists to eliminate.

Every downstream commitment inherits this: the two-tier draft/production head render (AD-01.13 #5), Addendum-B item B5, and Master Plan M5's certified-model rollout.

**Resolution.** **Promote**, do not merely delete. Port the provider binding from `stage6_talking_head.py` into the live `talking_head_task.py`, preserving the live task's proven segment/OOM strategy, AD-03 Pillar-2 continuous overlay, and correct upload URL (`talking_head_task.py:155` — the dead file at `:241` carries the wrong URL that previously broke Stage 5). Then delete the duplicate.

Tracked as `OUTSTANDING_WORK.md` v4.0 **P1.0**; sequenced as Master Plan **M1**, ahead of the AD-05 migration so the fix is not carried forward into the new architecture.

**Note on B5.** Addendum B recorded this as "Stage 8 must bind the head model via the provider factory." That framing was wrong: Stage 8 overlays a **pre-rendered** head asset by `asset_id` and does not render the head. The binding belongs at Stage 6. B5 is superseded by this section.

## AD-01.16 — Relationship to MBCP (AD-04) *(new)*

AD-01.7 required an external acceptance process performed outside IVGS and recorded as an in-system attestation. That process is now **MBCP** (AD-04-v3), operating in connected mode.

- **Seam:** AD-01 receiver at `/ad01/v1`, authenticated by `X-Service-Token`. Certification export dedups by `certification_id`, so re-export is safe.
- **Direction:** **IVGS pulls weights from MBCP** (`ivgs-models/mbcp_fetch.py` against `{serving_url}/weights/{model}/manifest`). MBCP does not push. *This distinction must not be inverted in any document or implementation.*
- **Backfill complete:** 21 exports plus 2 composition transmitted; all non-revoked certifications landed as CANDIDATEs; 24 revoked correctly skipped.
- **Certify ≠ export.** Certification happens in MBCP; export is a distinct admin action. The per-certification "Export to IVGS" button was delivered 2026-07-12.
- **Not yet exercised:** the weight-fetch pull path itself (ledger P2.10), pending the fleet (M4) and the serving-token / signing-key handoff.

**Boundary.** MBCP certifies; AD-01 governs lifecycle and selection. A certification is evidence, not an approval — approval remains a deliberate in-IVGS act with attestation. **AD-01 must never auto-approve on certification receipt.**

---

*AD-01 Draft 2 amendment prepared 2026-08-14 against `e613e844`. Apply over Draft 1; sections AD-01.1–AD-01.11 and Appendices AD-A/AD-B unchanged.*
