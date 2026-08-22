# WP-26-MODEL-STORE - report

| | |
|---|---|
| **Package** | WP-26-MODEL-STORE (Track S, **Tier C - judgement**) |
| **Brief** | `workpackages/WP-26-MODEL-STORE.md` |
| **Ledger** | AD-01.12 Phase B/C; P1.4d; blocks M4 and M5 |
| **HEAD** | `134c34f` + the operator's 31-file push |
| **Date** | 2026-08-15 |
| **Agent** | Claude. node-01 plus SSH to node-02/03/04. |

> # STATUS: PASS 1 - STOPPED BEFORE ANY GUI ACTION
> No model was registered, approved or set default. No SQL touched `models`. Per the
> brief's hard stop, the agent proposes and verifies; the operator clicks.

---

# PASS 1 - FINDINGS

## 1.1 The brief's task order is wrong, and must be re-sequenced

The brief puts engine verification (task 1) before the node-02/03 upgrade (task 4).
**Half of task 1 cannot be done in that order.** Verified:

```
node-02  ivgs-celery-node02          ModuleNotFoundError: No module named 'shared.providers.binding'
node-03  ivgs-cogvideox-worker-node03 ModuleNotFoundError: No module named 'shared.providers.binding'
```

Both run `v5.4.7-h0`, which predates ARCH-1. `resolve_endpoint` does not exist there,
so **the endpoint a binding would resolve to on those nodes cannot be measured until
they are upgraded.** That covers `transcript_refinement`, `storyboard_generation` and
`video_generation` - three of the five stage keys.

**Proposed order:** verify what is verifiable now (node-04 stages) -> upgrade node-02/03
-> verify the remaining three -> then GUI approvals stage by stage, each followed by its
smoke. Approving a model whose endpoint has never been measured is the failure mode this
package exists to prevent.

## 1.2 Endpoint resolution measured - the trap is real and it has already bitten

`binding.py:21-52` resolves per-engine from `IVGS_<ENGINE>_URL`, falling back to a
shipped default. Measured **inside the node-04 worker**, which is the node that runs
Stages 3-image, 5 and 6:

| Engine | `IVGS_<ENGINE>_URL` | Binding resolves to | Reachable |
|---|---|---|---|
| `comfyui` | `http://comfyui:8188` | `http://comfyui:8188` | **200** |
| `coqui` | `http://ivgs-coqui:5002` | `http://ivgs-coqui:5002` | **200** |
| `kokoro` | **(unset)** | **`http://node-05:8021`** | **TIMEOUT** |

**Kokoro is unusable as a binding target, on two independent counts:**

1. The shipped default points at **node-05**, which is offline and does not run Kokoro.
2. Kokoro actually runs on **node-04** as `ivgs-kokoro`, listening on **5003** - not
   8021. So even correcting the host would leave the port wrong.

This is exactly the class of defect that made the Stage-6 endpoint work in WP-02 only
because `IVGS_LATENTSYNC_URL` happened to be set. Where the override is missing, the
shipped default is wrong.

## 1.3 What the engines actually serve

**vLLM on node-02** - queried with the worker's own credentials:

```
{"id":"llama-3.3-70b", "root":"RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic",
 "max_model_len":32768, "owned_by":"vllm"}
```

Worker env: `VLLM_SERVED_NAME=llama-3.3-70b`,
`VLLM_MODEL_NAME=RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic`,
`VLLM_PRIMARY_URL=http://vllm:8000`.

**Note `VLLM_PRIMARY_URL` is `http://vllm:8000`, while `binding.py`'s shipped default
for the `vllm` engine is `http://node-02:8000`.** Whether `IVGS_VLLM_URL` is set on
node-02 could not be read through the binding (no ARCH-1), so **whether the binding
would reach vLLM at all on that node is currently unknown**. It must be measured after
the upgrade, before Stage 1 or 2 is approved.

**ComfyUI on node-04** - `http://comfyui:8188/system_stats` returns 200.
**Coqui on node-04** - `http://ivgs-coqui:5002/health` returns 200.
**CogVideoX on node-03** - container `ivgs-cogvideox-server-node03` healthy
(`cogvideox-pilot-1`); endpoint resolution not measurable yet.

## 1.4 Store state, measured 2026-08-15

| Stage key | Rows | Approved+enabled | Default | Candidate names |
|---|---|---|---|---|
| `transcript_refinement` | **0** | 0 | 0 | - |
| `storyboard_generation` | 1 | 0 | 0 | `test-model-1` (**retired**) |
| `image_generation` | 1 | 0 | 0 | `FLUX.1-dev` (candidate) |
| `video_generation` | 2 | 0 | 0 | `CogVideoX-5b`, `Wan2.2-T2V` (candidates) |
| `voiceover_tts` | 2 | 0 | 0 | `Kokoro`, `XTTS-v2` (candidates) |
| `talking_head` | 2 | 2 | 1 | `latentsync`, `latentsync-alt` |

## 1.5 Recommended defaults, with the evidence for each

**Nothing below is approved. These are proposals for the operator.**

| Stage key | Recommend | Engine | Endpoint (measured) | Evidence / caveat |
|---|---|---|---|---|
| `voiceover_tts` | **`XTTS-v2`** | `coqui` | `http://ivgs-coqui:5002` **200** | **Not Kokoro** - its binding endpoint times out (S1.2). This is the one recommendation I can make on hard evidence today |
| `image_generation` | `FLUX.1-dev` | `comfyui` | `http://comfyui:8188` **200** | Endpoint verified. **Not verified: that ComfyUI has the FLUX weights loaded.** Confirm before approving |
| `video_generation` | `CogVideoX-5b` | `cogvideox` | **unmeasured** | Server healthy on node-03, but AD-04 S3.23 records the CogVideoX **adapter is broken** (four non-existent node types). Establish whether that affects the IVGS provider or only MBCP's before approving |
| `transcript_refinement` | new row, `llama-3.3-70b` | `vllm` | **unmeasured** | Serves correctly; endpoint unknown until upgrade. **No row exists - must be created** |
| `storyboard_generation` | new row, `llama-3.3-70b` | `vllm` | **unmeasured** | Only row is `retired`; AD-01.5.1 allows no transition out of retired |
| `talking_head` | **hold** | - | `http://latentsync:7860` | Both rows are the same engine, so no swap can improve lip-sync. **Do not approve on quality grounds until P1.4d's investigation completes** |

## 1.6 P1.4d - the certified winner: not yet investigated

Deliberately not started this pass. It requires reading MBCP on `.51`, which is outside
node-01/02/03/04 and outside my SSH grant. `/opt/MBCP` is a read-only reference clone
and may not reflect `.51`'s live state.

The one thing established here: the winner is **absent** from `talking_head`, and both
present rows share the `latentsync` engine. Also carried forward - `model_approvals`
holds 26 rows across **13 distinct `model_id`s** against **12** rows in `models`, so at
least one attestation references a model that no longer exists.

## 1.7 Evidence basis

**Verified live:** vLLM `/v1/models` on node-02 with worker credentials; `resolve_endpoint`
per engine inside the node-04 worker; HTTP reachability of comfyui, coqui, kokoro and
node-05 from node-04; Kokoro's published port; ARCH-1 absence on node-02/03; the store
table; container inventory on all four nodes.

**Not verified:** any endpoint on node-02/03 (no ARCH-1); whether ComfyUI has FLUX
loaded; whether CogVideoX's broken adapter affects the IVGS provider; anything about
MBCP's certification records; whether `IVGS_VLLM_URL` is set on node-02.

## 1.8 Decisions requested

| # | Decision | Recommendation |
|---|---|---|
| **D-1** | Re-sequence: verify node-04 stages -> upgrade node-02/03 -> verify the rest -> approve stage by stage | **Accept.** Approving an unmeasured endpoint is the failure this package prevents |
| **D-2** | Kokoro's endpoint is broken (offline host, wrong port). Fix `IVGS_KOKORO_URL` in node-04's compose, or approve XTTS-v2 and leave Kokoro unapproved? | **Approve XTTS-v2; leave Kokoro unapproved.** Fixing its endpoint is a compose change belonging with WP-29's errata, not a prerequisite here. But record it - an unapproved model with a broken endpoint is a trap for whoever approves it later |
| **D-3** | Approve `image_generation` before confirming ComfyUI has FLUX weights? | **No.** Confirm first - it is one query |
| **D-4** | `video_generation` given AD-04 S3.23's broken CogVideoX adapter | Establish blast radius before approving. May need to defer this stage |
| **D-5** | P1.4d needs MBCP access on `.51`, outside my grant | Operator to run the MBCP queries, or extend the grant |

---

# PASS 2

*Not started. Awaiting operator review - Tier C hard stop.*
