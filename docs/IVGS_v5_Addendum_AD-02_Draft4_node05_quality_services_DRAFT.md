# IVGS v5 — Functional Specification Addendum AD-02, **Draft 4 (proposed)**

> ## ⚠ SUPERSEDED, 2026-08-26, BY OPERATOR RULING. See §7.
>
> **Draft 4 proposed node-05 as the quality-services node. It was never
> adopted, and the operator has since ruled node-05 to be the Qwen LLM node.**
> The CLIP scorer moved to node-06 and node-06 is now its sole host. Read §7
> before acting on anything in §§1–6.
>
> **§§1–6 are LEFT EXACTLY AS WRITTEN and are not to be edited.** They are the
> record of what was proposed on 2026-08-26 and why, and §1's measurements —
> the card, the VRAM, the latency — are still the measurements. Rewriting a
> proposal to look like it always said the thing that was later decided is how
> a specification set stops being evidence of anything. History is appended to
> here, not amended.


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

---

## 7. SUPERSEDED — node-05 is the Qwen LLM node (operator ruling, 2026-08-26)

**Recorded by WP-61-QWEN, Task 1. This section supersedes §2 of this document.
It does not edit it.**

### 7.1 The ruling

> node-05's role is the Qwen LLM node, per the 2026-08-25 evaluation. The AD-02
> quality-services role assignment is superseded.
> — operator, 2026-08-26

### 7.2 What changed underneath the proposal

Draft 4 was written on 2026-08-26 against a node-05 that was **out of service
with a confirmed host memory fault** and that had, before the fault, been given
the CLIP scorer. Two things then happened on the same day:

1. **node-05 came back.** Its Proxmox host passed multiple full memtest cycles
   clean after the RAM replacement. The VM now has **78 GB RAM** and the
   **RTX PRO 5000 Blackwell, 48935 MiB measured**. §1.1's hardware correction
   stands unchanged and is still the measurement of record.
2. **The CLIP scorer moved to node-06, and stayed.** node-06 is now its sole
   host — verified `served_by: node-06`. node-05's scorer is stopped and
   removed, and node-05 was left running only telemetry
   (`gpu-exporter`, `node-logs`) with a real `/opt/ivgs` checkout at `3904eec`
   and **no `.env.node05` and no worker**.

So §2's premise — "node-05 is given the job it is actually doing" — no longer
holds, through no fault of its reasoning. The job it is actually doing changed.

### 7.3 The replacement role

> - **node-05.** NVIDIA **RTX PRO 5000 Blackwell, 48 GB** (measured 48935 MiB,
>   driver 580.173.02), 78 GB host RAM — the **LLM node for translation**. It
>   serves **Qwen/Qwen3.8-27B-FP8** on vLLM (`--served-model-name qwen38-27b`),
>   OpenAI-compatible, port **8000**, reachable only from 192.168.1.90–93.
>   It runs **no pipeline stage** and consumes **no Celery queue**: it is called
>   synchronously, never by a worker's queue subscription, and it holds no
>   pipeline state.
>
>   *Supersedes Draft 4 §2.1 (quality services) and, through it, the Draft-3
>   "SDXL image fallback / Ollama LLM fallback / FFmpeg composition overflow"
>   role. None of the Draft-3 services was ever deployed on this node.*

**`dynamically_loadable = false` for this capability, and it is not a
formality.** vLLM binds its model at container start from `--model`. There is
no runtime path that swaps Qwen for anything else, so a scheduler that treated
this node as able to load a model on demand would be reasoning about a
capability that does not exist. AD-02's existing rule stands and is why node-05
must NOT be added to the GPU scheduler's fleet: a vLLM server is not a Celery
consumer.

### 7.4 The measured basis (real 48 GB, superseding a simulation)

Every Qwen figure that existed before this package was taken on a **96 GB
RTX PRO 6000 capped to `--gpu-memory-utilization 0.48` to SIMULATE a 48 GB
card** (`/mnt/ivgs-shared/qwen-invocation.txt`). node-05 gives the first
measurements on a real 48 GB card. The WP-61 report tabulates them against the
simulation; the load-bearing constraints, all discovered by failure, are:

| | |
|---|---|
| Model | `Qwen/Qwen3.8-27B-FP8` **only** — the BF16 base is ~56 GB of weights and does not fit |
| Engine | `vllm/vllm-openai:cu130-nightly`, vLLM v0.19.2rc1.dev134+ (earlier builds may not resolve the `qwen3_5` architecture) |
| `--max-num-seqs 128` | **MANDATORY.** Hybrid attention/Mamba: each decode sequence consumes one Mamba cache block, 216 were available at the 48 GB budget, and the default of 1024 makes the engine **refuse to start** |
| `--reasoning-parser qwen3` | **MANDATORY.** Without it ~1400 tokens of chain-of-thought land in `content`, and Stage 2's JSON extractor grabs the schema echo out of the reasoning text |
| `chat_template_kwargs {"enable_thinking": false}` | Per request. 53.9 s → 9.3 s on the storyboard-shaped prompt; JSON still parses |
| Context | 131072 configured, **proven at a 60,069-token prompt** |
| `--trust-remote-code` | Required |

### 7.5 Weights provenance — a SECOND ruled exception, and a ledgered debt

A direct HuggingFace pull is authorised as a **second operator exception** to
the weights-from-MBCP doctrine. (The first was the 2026-08-25 evaluation; that
clone and its cache were destroyed.)

The exception carries an obligation, stated here so it is not lost:

* every downloaded `*.safetensors` and `config.json` is sha256'd at the moment
  of download, and the manifest is written to
  `/mnt/ivgs-shared/qwen-weights-manifest-<date>.txt`;
* **MBCP must bank and certify this exact bundle** (work orders 5 and 7) before
  the Model Store may list it as anything other than an exception.

Until that happens, `Qwen3.8-27B-FP8` on node-05 is **provenance-exceptional**:
it is running, it is hashed, and it is not certified. It must not be described
as a Model-Store-managed model.

### 7.6 What §§5 and 6 of this draft now mean

* **§5 (consequential edits).** Still owed, and the target text is now §7.3
  rather than §2.1. `ivgs-infra/docker-compose.node05.yml`'s header and
  `tests_system/smoke/test_gpu_nodes.py` still assert an RTX 5080 16 GB with a
  ComfyUI/Ollama service map for services this node has never run — a *test*
  asserting the wrong hardware, which passes only because it never reaches the
  node.
* **§6 question 3 (where does the safety classifier go?)** is REOPENED by this
  ruling. Draft 4 answered "node-05, it has 47.9 GB free". It does not any
  more: Qwen at `--gpu-memory-utilization 0.90` is the tenant of that card.
  node-06 hosts the CLIP scorer and is the natural home for its successor.
* **§6 questions 1, 2 and 4** are unaffected.

### 7.7 What this section does NOT do

It does not adopt anything. AD-02 Draft 3 remains the authoritative
specification text; Draft 4 remains unadopted and is now also superseded. This
section records a ruling so that the next reader of this file is not led by an
unmarked proposal into provisioning the wrong service on the wrong node.
