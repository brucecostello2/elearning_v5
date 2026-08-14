# Step 10 — MBCP Reconciliation and Cross-System Seam Register

| | |
|---|---|
| **Prepared** | 2026-08-14 |
| **Supersedes** | Documentation Status Register step 10 ("MBCP SSOT v3.4 + doc sweep") — **that scoping was wrong; see §1** |
| **Verified against** | `MBCP-main` @ 2026-08-05 (repo HEAD `c9c5878`, migration head `0057`); `dev/CLAUDE.md` and `dev/workorders/WORK_PACKAGES.md` @ 2026-08-05; IVGS `e613e844` |
| **Purpose** | Correct the IVGS deliverables where MBCP's live state contradicts them, and record the items that sit **between** the two systems — which neither register currently owns |

---

## 1. Step 10 was mis-scoped

The register assumed MBCP needed the same treatment IVGS just received. It doesn't. MBCP has **already been re-baselined**, and to a higher standard:

- `dev/CLAUDE.md` — a cold-start brief with fleet table, gate battery, deployment rules, storage facts, eleven known traps, and an explicit authority statement.
- `dev/workorders/WORK_PACKAGES.md` — twelve work packages ordered **by risk, not by numbering**, each ending in *"a live proof on real hardware, not a passing unit test."*
- Both live **inside the repo**, so they are committed and pushed rather than sitting untracked on one host.

Two things IVGS should adopt from this, and one caution:

| Adopt | Why |
|---|---|
| **Exit gates phrased as live proofs** | IVGS's ledger says what is broken; MBCP's register says what must be *demonstrated* to close it. Stronger. |
| **`dev/CLAUDE.md` as a committed cold-start brief** | Runbook 2.0 §8 covers agent constraints, but a single always-loaded brief is better. Recommend `dev/CLAUDE.md` in `elearning_v5`, pointing at the ledger, plan, and runbook. |

> **Caution.** `dev/CLAUDE.md` §3 says *"Do not trust summaries, handoff documents, or recollection — including this file."* That instruction is well-placed and this session proved why: three of my own ledger items were stale within two weeks.

**SSOT v3.5 is WP-K and depends on every package above it.** Writing it now would produce exactly the aspirational document the exercise exists to eliminate. It is correctly sequenced where it is; I should not pre-empt it.

---

## 2. Corrections to the IVGS deliverables

Three ledger items are wrong. Apply before committing v4.0.

### 2.1 P2.8 — RuntimeClass refactor: **CLOSE**

I recorded Tasks B/C/D as "awaiting approval," and you chose Option B (split PRs) on that basis. **The work was already merged as PR #48** — a single PR, not a split.

Verified in the snapshot: `mbcp_adapters/runtimes/comfyui.py` plus nine graphs in `mbcp_adapters/comfyui_graphs/`.

**The Option B decision is moot.** Recorded so the trail is clear rather than silently dropped.

### 2.2 P2.9 — CogVideoX adapter: **CLOSE as a code defect; RE-OPEN as WP-A**

I recorded the graph as broken. **It has been rebuilt.** Verified node types in `cogvideox-5b.json`:

```
CLIPLoader · CogVideoTextEncode · CogVideoSampler · CogVideoDecode
DownloadAndLoadCogVideoModel · EmptyLatentImage · VHS_VideoCombine
```

Exactly the correct names the Task A audit derived — no X-suffixed phantoms remain.

**But it has never touched a GPU.** WP-A is the highest-priority MBCP package and blocks WP-B. My earlier caution stands and is now MBCP's own: *treat the first GPU smoke as a gate, not a formality.*

### 2.3 P1.5 — `.env.node01` secret hygiene: **RAISE SEVERITY**

I recorded this as "prospective risk — the token has never been committed." That remains true on the IVGS side.

**It is no longer the whole picture.** WP-E records that `MBCP_AD01_TOKEN` was **exposed during the 2026-08-04 session**, alongside DB passwords, `REDIS_PASSWORD`, `JWT_SECRET`, `ARTIFACT_SIGNING_KEY`, `WEIGHT_SIGNING_KEY`, `WEIGHT_SERVICE_TOKEN` and the Grafana admin credential.

`MBCP_AD01_TOKEN` **is** `IVGS_MBCP_INGEST_TOKEN`. The same secret, on both sides of the seam.

**This makes rotation a coordinated two-system change, not MBCP hygiene.** Rotating it on `.51` without the matching change on node-01 breaks the AD-01 seam — certification exports begin failing with 401 and park in the drain queue. See §3.1.

**Revised P1.5 text:**

> **P1.5 — `.env.node01` secret hygiene + coordinated token rotation.** *(P1, was "prospective risk only")*
> The IVGS-side token has never been committed (verified `e613e844`). **However, the shared `MBCP_AD01_TOKEN` / `IVGS_MBCP_INGEST_TOKEN` was exposed on the MBCP side on 2026-08-04** and is scheduled for rotation under MBCP WP-E. Rotation must be coordinated across both hosts in one window (§3.1). Additionally: gitignore the tracked file; scan its history; rotate Postgres/Redis credentials; drop the `dev-service-token` default.

---

## 3. Cross-system seam register

**These items belong to neither register and are therefore at risk of being dropped by both.** That gap is the reason this document exists.

### S-1 — Coordinated ingest-token rotation ⚠️ **highest cross-system risk**

| | |
|---|---|
| **Systems** | MBCP `.51` (`/root/mbcp-local.env`) **and** IVGS node-01 (`/opt/ivgs/ivgs-infra/.env.node01`) |
| **Trap** | Rotating one side alone breaks the seam. Failures are **not loud** — exports park in `drain-pending-exports` and retry every 5 minutes, so the symptom is silent staleness, not an alarm. |
| **Sequence** | Generate the new token → update **both** files → recreate MBCP management/backup/ingest workers → recreate IVGS API → verify with `docker exec <c> env` on both sides (runbook §3.4) → force one export and confirm a 201 receipt → confirm the drain queue is empty |
| **Owner** | MBCP WP-E, but **must not be executed as an MBCP-only task** |

### S-2 — Stage taxonomy divergence ⚠️ **active ambiguity**

The two systems both say "stage" and mean different things.

**IVGS: eight pipeline stages.** transcript → storyboard → media → manifest → TTS → talking head → draft → final.

**MBCP: nine AD-01 model-capability stages** (`mbcp_core/enums.py:161`, migration `0019_stage_taxonomy`): `transcript_refinement, storyboard, translation, image_generation, video_generation, animation_generation, tts, talking_head, composition`.

They are **not the same list and not meant to be**:

| MBCP stage | IVGS pipeline stage |
|---|---|
| `image_generation` / `video_generation` / `animation_generation` | all three → Stage 3 |
| `composition` | Stages 4, 7 and 8 collapsed |
| `translation` | §17 localisation — **not an IVGS pipeline stage at all** (ledger DEF.2) |

**Consequence:** "Stage 6" is unambiguous only within IVGS. The AD-01 selection key `(stage, tier)` uses **MBCP's** taxonomy. A reader — or an agent — moving between the two documents will get this wrong.

MBCP already documents the reconciliation in `enums.py:168` (*"AD-04-v3 used 8 stages; AD-01's 9 are canonical"*). **IVGS does not.** Add to AD-01 Draft 2 §AD-01.16 and to the glossary: **"pipeline stage" (IVGS, 8) and "capability stage" (AD-01/MBCP, 9) are distinct taxonomies; the mapping is above.**

### S-3 — Addendum number collision: **two different AD-05s** ⚠️

MBCP already has **AD-05 (adapter authoring)** — complete — and **AD-06 (text/audio output safety)** — WP-I, in flight.

I issued **IVGS AD-05 (Orchestration Migration)** yesterday. That collides.

The AD-NN space was never namespaced: AD-01/02/03 are IVGS-internal, **AD-04 is IVGS's addendum describing MBCP**, and MBCP then continued the sequence with its own AD-05/AD-06. Reasonable at each step; ambiguous in aggregate.

| Option | Assessment |
|---|---|
| **A. Namespace explicitly** — `IVGS-AD-05`, `MBCP-AD-05` | **Recommended.** Both keep their numbers, no renaming, no stale references. Filenames already carry `IVGS_v5_Addendum_`; make it explicit in the headers and in prose. |
| **B. Renumber IVGS AD-05 → AD-07** | Avoids collision but AD-05 is one day old and already referenced from the ledger, the plan, the spec amendment, ADR-005, and the runbook. Churn for no gain. |
| **C. Leave it** | Guarantees a future misfiled reference. |

**Recommend A.** Cheap, and the ambiguity is real today, not hypothetical.

### S-4 — Weight-fetch seam: **unblocked earlier than the IVGS ledger assumes**

IVGS ledger P2.10 says the pull path needs the M4 fleet rollout. **MBCP WP-J records that the IVGS repo is now cloned at `/root/IVGS` on `.51`**, so `mbcp_fetch.py` can be developed and proven against the live serving endpoint **without waiting for M4**.

**Revise P2.10:** development and proof are available now; only the *production* pass across GPU nodes is gated on M4. Worth pulling forward — it de-risks M4 and needs only the serving-token/signing-key handoff. *(Note: `WEIGHT_SIGNING_KEY` and `WEIGHT_SERVICE_TOKEN` are both in S-1's rotation set — sequence the handoff after rotation, not before, or it happens twice.)*

### S-5 — Schema coupling is already live

IVGS commit `e613e84` added `ffmpeg` to `ModelEngine` **specifically to unblock MBCP composition exports**; MBCP added `ExportBundle.engine` in the same window. The enums are coupled across two repositories with **no test on either side** that would catch a divergence.

**Recommend** a seam contract test — MBCP asserting that every engine value it can export is accepted by the IVGS receiver. Neither register currently holds this. New ledger item.

### S-6 — Certification honesty: 8 of 18 certificates rest on audited overrides

`dev/CLAUDE.md` §11: nine stages hold draft + production certificates — **10 at the full gate, 8 via audited override**, pending AD-06.

This matters to IVGS because AD-01 treats a certification as evidence for approval. **Eight of those certificates are not full-gate evidence**, and IVGS has no visibility into which.

**Two actions.** (a) AD-04 v3.1 §3.19 must record this — I wrote "Phase 3 complete," which is true of the machinery but overstates the ledger. (b) The AD-01 attestation should carry the gate status, so an IVGS approver can see whether a certificate is full-gate or override-based. Currently it cannot.

MBCP WP-I closes this by moving all 18 to full-gate and re-exporting. Until then, IVGS approvals are working from partially unqualified evidence.

### S-7 — VRAM figures are placeholders

Every VRAM value in `mbcp_adapters/comfyui.py` is marked `PROVISIONAL` (15 occurrences), as are the TTS figures in `tts_server.py`. WP-A states it plainly: **"the certification record currently rests on guesses."**

IVGS's `ivgs-scheduler` performs VRAM-aware bin packing. If it ever consumes MBCP's declared figures, it is packing against guesses. Verify whether the scheduler reads declared VRAM from the Model Store or measures locally — **and if the former, do not roll M4 before WP-A closes.**

### S-8 — R-8: CogVideoX resolution overclaim

`mbcp_adapters/comfyui.py:169-170` declares `cogvideox-5b` at `max_width: 1920, max_height: 1080`. The engine is really 720×480. Verified present in the snapshot; MBCP WP-B owns it.

**Cross-system relevance:** if IVGS ever reads these specs to size a render request, it will request a resolution the engine cannot produce. Same class as S-7 — declared capability diverging from real capability, on a seam.

### S-9 — Fleet documentation is incomplete on the IVGS side

`dev/CLAUDE.md` documents `.53` (authoring LLM host, Qwen2.5-Coder-32B on vLLM:8010, firewall permits **only `.51`**) and `.7` (TrueNAS, backup/DR target, 24 TB free). `.60` is **retired** as of 2026-08-04.

No IVGS document mentions `.53` or `.7`. **`.7` is directly relevant to IVGS's DEF.1** — comprehensive DR is deferred partly because IVGS backups live on node-01's own disk, and a verified, restore-tested 24 TB NAS now exists on the same VLAN.

**Recommend** revisiting DEF.1's deferral. The blocker was partly "no off-node target." There is one now, and MBCP has already run a byte-for-byte restore drill against it.

### S-10 — `.51` is a Proxmox clone with a parked production twin

`dev/CLAUDE.md` §2: the original production VM is powered off and parked; the clone holds the same IP, disks and data. WP-E notes both share `machine-id` and SSH host keys.

**IVGS exposure:** node-01 holds an SSH known-hosts entry and a service token pointing at `192.168.1.51`. When the production VM is rejoined, the host key will not match. Regenerate `machine-id` and host keys **before** both run, and expect to clear node-01's known-hosts entry.

---

## 4. Revised step 10

| Step | Item | Owner | Status |
|---|---|---|---|
| 10.1 | Apply §2 corrections to ledger v4.0 and AD-04 v3.1 | IVGS | **Do before committing** |
| 10.2 | Add the S-1…S-10 seam items to ledger v4.0 as a new **§S — Cross-System** section | IVGS | Do before committing |
| 10.3 | Resolve S-3 (addendum namespacing) | Both | Decision needed |
| 10.4 | Adopt `dev/CLAUDE.md` for IVGS | IVGS | Recommended |
| 10.5 | Revisit DEF.1 given `.7` (S-9) | IVGS | Recommended |
| ~~10.6~~ | ~~MBCP SSOT v3.4~~ | MBCP | **Withdrawn — it is WP-K, correctly gated on WP-A…WP-J** |
| ~~10.7~~ | ~~MBCP doc sweep~~ | MBCP | **Withdrawn — `dev/` structure already supersedes it** |

## 5. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| **D-7** | S-3 addendum namespacing | **Option A** — explicit `IVGS-AD-NN` / `MBCP-AD-NN` prefixes. No renumbering. |
| **D-8** | Does `ivgs-scheduler` consume MBCP's declared VRAM figures? (S-7) | Verify before M4. If yes, WP-A becomes an M4 prerequisite. |
| **D-9** | Pull S-4 weight-fetch development forward, off the M4 critical path? | **Yes** — it can be proven now on `.51`, and it de-risks M4. Sequence after S-1's rotation. |
| **D-10** | Reopen DEF.1 now that `.7` exists with a proven restore drill? (S-9) | Worth a decision. The original deferral reason has weakened materially. |

---

*Step 10 prepared 2026-08-14. Completes the documentation re-baseline. Three IVGS ledger corrections and ten cross-system items to fold in before committing.*
