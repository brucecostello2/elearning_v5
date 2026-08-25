# IVGS v5 — Functional Specification Addendum AD-02, **Draft 4 (proposed)**

## node-05 redesignation: from image/LLM fallback to the **quality-services** node

**Addendum to:** IVGS v5.0 Functional Specification (18 May 2026)
**Amends:** AD-02 Draft 3 (2026-07-07) — §AD-02.2 node-05 bullet, and Appendix AD-B row `node-05`
**Version:** Draft 4, proposed 2026-08-26 by WP-44-QUALITY
**Classification:** Internal Working Document
**Change-control status:** **DRAFT FOR REVIEW — NOT ADOPTED.** Prepared under the
§18 change-control process. **No specification text has been edited.** AD-02
Draft 3 and `docs/ivgs_v5_functional_spec.md` are untouched by WP-44; this file
is the proposal that must be reviewed before either changes.
**Closes:** ledger **P2.43** (node-05's hardware corrected in the operational docs
but not in the specs), by supplying the amendment P2.43 asks for.
**Depends on:** AD-02 Draft 3; §11.1 quality gates (Table 11-1); AD-04 Seam
direction (dev/CLAUDE.md §11.1)

---

## 1. Why an amendment is needed

Three separate statements about node-05 in the specification set are wrong. Two
were wrong about the hardware and one is now wrong about the role.

### 1.1 The hardware was wrong, and has been corrected only operationally

Measured on the box 2026-08-25 (WP-48-TELEMETRY):

```
NVIDIA RTX PRO 5000 Blackwell, 48935 MiB, driver 580.173.02, node ONLINE
```

Every specification document says **"RTX 5080, 16 GB"**, and the ledger records
node-05 as **OFFLINE**. All three claims are wrong. WP-48 corrected the
*operational* surfaces where the wrong number was load-bearing (`dev/CLAUDE.md`,
`README.md`, `ivgs-api/app/api/v1/nodes.py`, both `prometheus.yml` copies, the
WP-24 honesty test). It deliberately did **not** touch the specifications,
because those go through change control. That is what this draft is for.

A fallback sized against 16 GB on a 48 GB card is the node-04 error WP-24
corrected, inverted: it under-commits real capacity instead of over-committing
imaginary capacity.

### 1.2 The role is wrong in a different way

AD-02 Draft 3, §AD-02.2:

> **node-05.** NVIDIA RTX 5080, 16 GB — ComfyUI SDXL/SD3.5 **image fallback**
> (behind node-04 FLUX), **Ollama** small-model **LLM fallback** (behind node-02
> vLLM, via `OllamaProvider`), and FFmpeg composition **overflow**. Unchanged.

None of that has ever run on node-05. Measured 2026-08-25: the node had **no
`/opt/ivgs` checkout at all** until WP-48 created one, and ran **no containers**.
As of WP-44 it runs the telemetry pair and one quality service. There is no
ComfyUI on it, no Ollama on it, and no compositor on it.

So the amendment is not "node-05 changes job". It is "node-05 is given the job
it is actually doing, in place of a job it has never done".

---

## 2. Proposed replacement text

### 2.1 §AD-02.2, the node-05 bullet — REPLACE

> - **node-05.** NVIDIA **RTX PRO 5000 Blackwell, 48 GB** (measured 48935 MiB,
>   driver 580.173.02) — the **quality-services** node. It hosts the model-backed
>   checks that the §11.1 quality gates depend on and that no other node has room
>   for: **CLIP image/text scoring** (`ivgs-clip-scorer`, port 8300) today, and
>   the safety-classifier and any future scoring services as they land. It runs
>   **no pipeline stage** and consumes **no Celery queue**: it is called
>   synchronously by node-01's API, never by a worker, and it holds no
>   pipeline state.
>
>   *Supersedes the Draft-3 "SDXL image fallback / Ollama LLM fallback / FFmpeg
>   composition overflow" role, none of which was ever deployed on this node.*

### 2.2 Appendix AD-B, the `node-05` row — REPLACE

| Node | Queues | Resulting workload |
|---|---|---|
| node-05 | **none** (not a Celery consumer) | **Quality services**: CLIP scorer on :8300, called by node-01's API. RTX PRO 5000 Blackwell 48 GB. |

### 2.3 Appendix AD-A — ADD a row

| Configuration | LLM weights | LLM KV | Video set | Compositor | Quality | Per-card | Fits 48 GB? |
|---|---|---|---|---|---|---|---|
| **node-05: quality services** | — | — | — | — | ≈ 1.0 | ≈ 1.0 | **Yes** (47.9 GB headroom) |

---

## 3. The measured basis for the numbers above

Measured on node-05 on 2026-08-26, with `ivgs-clip-scorer:v5.10.0-quality`
resident and serving:

| | |
|---|---|
| Card | NVIDIA RTX PRO 5000 Blackwell, 48935 MiB |
| Model | `openai/clip-vit-base-patch32`, weights baked into the image |
| **VRAM, process** | **1040 MiB** (`nvidia-smi --query-compute-apps`) |
| VRAM, torch allocator | 577.1 MiB allocated / 630.0 MiB reserved |
| VRAM, whole card | 1050 MiB of 48935 (**2.1%**) |
| Idle power | 59.04 W |
| **Latency, compute** | **21 ms** median for a 1920×1080 PNG (10 samples: 21.3 / 21.7 / 21.9 min/med/max) |
| Latency, direct round trip | 60 ms median |
| Latency, via node-01's proxy | 130 ms median (116 / 129.6 / 133.8) |

**The headroom argument.** One scoring service occupies 2.1% of this card. The
role change is not a capacity claim — it is a statement that this node's job is
to hold *many small model-backed checks*, of which CLIP is the first. The safety
classifier (§11.1's `safety_score`, still unimplemented fleet-wide) is the
obvious second.

---

## 4. What this amendment does NOT propose

* **It does not make node-05 a Celery consumer.** Deliberate. A quality check
  that runs inside the pipeline's own worker fleet competes with the pipeline
  for the resource it is meant to be auditing. Scoring is a synchronous call
  from the API, and node-05 holds no queue subscription. This is the one place
  where "capability is the queue subscription" (AD-02, Appendix AD-B footnote)
  does not apply.
* **It does not restore the SDXL/Ollama fallbacks anywhere else.** Whether IVGS
  still wants an image fallback and an LLM fallback at all is a separate
  question, and answering it by leaving stale text in a spec is not answering it.
  Flagged in §6 below.
* **It does not touch node-06.** Draft 3's node-06 designation stands unchanged.
* **It does not change any threshold in Table 11-1.**

---

## 5. Consequential edits required if this draft is adopted

Adopting Draft 4 requires the following, all currently carrying the wrong text
(inventory measured 2026-08-25, ledger P2.43):

| File | Sites | Current text |
|---|---|---|
| `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md` | §AD-02.2 bullet; Appendix AD-B row | "RTX 5080, 16 GB — ComfyUI SDXL/SD3.5 image fallback … Ollama … Unchanged." |
| `docs/ivgs_v5_functional_spec.md` | `:855`, `:951`, `:1431` | same |
| `ivgs-infra/docker-compose.node05.yml` | `:7` header comment | same |
| `tests_system/smoke/test_gpu_nodes.py` | node-05 block | "node-05 GPU smoke tests — RTX 5080 16 GB", plus a ComfyUI/Ollama service map for services the node does not run |

Note the last one: a *test* asserts the wrong hardware and the wrong service
map. It passes because it never reaches the node.

---

## 6. Open questions for the reviewer

1. **Do the SDXL image fallback and the Ollama LLM fallback survive at all?**
   Draft 3 assigned both to node-05 and neither was ever built. If they are still
   wanted, they need a node with room and an owner; if they are not, they should
   be struck from the spec rather than relocated. **WP-44 takes no position.**
2. **Does node-05 keep FFmpeg composition overflow?** Same question, same answer.
   Note node-06's Draft-3 designation already makes it the primary compositor.
3. **Where does the §11.1 safety classifier go?** Table 11-1 requires a
   `safety_score` for every asset type and nothing implements one anywhere on the
   fleet. node-05 has 47.9 GB free and is now the quality node; this is the
   natural home, but it is a scoping decision, not a WP-44 one.
4. **Should the CLIP scorer model be registered in MBCP?** Raised as a decision
   by WP-44 (report S3.5), not blocked on. It bears on whether node-05's
   services are provenance-tracked assets or infrastructure.

---

*Prepared as an additive deviation under §18 change control. This document
proposes; it does not amend. AD-02 Draft 3 remains the authoritative text until
this draft is reviewed and adopted.*
