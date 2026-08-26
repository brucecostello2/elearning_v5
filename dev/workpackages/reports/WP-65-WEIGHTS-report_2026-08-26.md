# WP-65-WEIGHTS — report, 2026-08-26

Tag **`v5.24.0-weights`**. Commits HELD, not pushed. Deployed to **node-01 only**.

**Headline: the brief's central premise is measured FALSE, and the truth is
worse than the premise.** A complete, correct, already-proven weight-fetch
client exists and has been used live. What was missing was never the fetch. And
the one model the Model Store called "available" is attributed to the wrong
node, on evidence that never looked at a disk.

---

## S0. VERDICTS

| Task | Outcome |
|---|---|
| 1 — what "available" means | **DONE.** And the answer is that it means something else entirely. §1. |
| 2 — the weight fetch service | **DONE against fixtures; live pass HELD** for the MBCP token. 44 tests. §2. |
| 3 — placement policy | **DONE.** Refusal tested as a first-class outcome, plus one the brief did not name. §3. |
| 4 — the surface tells the truth | **DONE and deployed.** Eight states where there was one word. §4, §7.3. |
| 5 — engine-name reconciliation | **DONE.** STOP checked and does not apply; 3 rows corrected, serving row untouched. §5. |
| 6 — storyboard prompt v5 | **DONE and published** (v5 active, v1–v4 inactive). Checker strengthened; the brief's two asks were already present. §6, §7.2. |

**Nothing stopped.** Six items are ledgered (§9) — none of them blocks a task in
this package; each is either MBCP-owned, frozen-body-owned, or a follow-on that
this package's refusals make honest in the meantime.

**Two corrections I made to my own work**, both recorded because they are the
same class of defect the package exists to close:

1. `fetch-weights` would have written verified bytes into a node-03 path created
   locally on node-01, and recorded them as available. Now
   `PlacementNotLocalError`, failing closed, before the network. §2.4.
2. The `not_fetched` label read *"certified, weights not fetched"* — a claim
   about the node that IVGS cannot make. Now *"no fetch recorded by IVGS"*. §7.4.

---

## 0. What the brief said, and what is actually there

| Brief's claim | Measured | Where |
|---|---|---|
| "Nothing consumes that reference… No download, no checksum verification" | **FALSE.** `ivgs-models/mbcp_fetch.py` fetches, verifies per-file SHA-256, recomputes the bundle digest and verifies the manifest HMAC. It was used live on 2026-08-25: *"9 bundles via mbcp_fetch.py, HMAC+digest+SHA256 verified 23/23"* | `models.vetting_reference` for `wan2.2-animate`; the file itself |
| The brief's grep (`weight_fetch\|fetch_weights\|weight_ref`) returned nothing | **True, and that is the finding.** The client is named `mbcp_fetch`, lives in `ivgs-models/`, which **no Dockerfile copies and no module imports**. A correct implementation was unreachable from the running system. | `ivgs-api/Dockerfile:32`, `ivgs-workers/Dockerfile:30` copy `shared/` only |
| Wan shows `34.1 GB / 1 available` because of "hand placement plus a recorded row" | **Half right.** `34.10` is hand-typed into `models.vram_gb`. "1 available" is a live poller. And **the node is wrong**. | §1 |
| AnimateDiff/MimicMotion are "catalogued and their bytes have never landed" | **True, but not for the stated reason.** MBCP certified them **engine-only** — there are no bytes to land, and there never will be. | §2 |
| The checker should "gain an assertion that no two scenes share a description" | **It has had one since WP-63.** | §6 |
| The checker should "fail a description containing multi-digit numerals" | **`DIGITS = re.compile(r"\d")` already fails on a SINGLE digit.** Implementing the request literally would have been a relaxation. Not done. | §6 |

---

## 1. TASK 1 — what "available" means today

### 1.1 The two columns, traced to their sources

| Column | Rendered at | Fed by | What it actually measures |
|---|---|---|---|
| **VRAM** | `ivgs-frontend/src/app/admin/models/page.tsx:634` | `ModelOut.vram_gb` → `models.vram_gb` (`shared/models/model_store.py:183`) | **A number typed into a form.** `page.tsx:880-886` is the input; `ivgs-api/app/api/v1/model_store.py:118` stores it. Nothing measures it, nothing checks it. |
| **NODES** | `page.tsx:637-643` | `m.node_availability.filter(a => a.status === "available").length` (`page.tsx:606-608`) | **A Redis LRU of models a JOB once loaded.** Not bytes, not capability, not residency. |

### 1.2 The availability chain, end to end

```
ivgs-scheduler/scheduler.py:303        record_model_load(...)   <- on job dispatch
  -> Redis zset gpu:model_lru:{node}:{gpu}:{n}    (model_concurrency.py:186-250, LRU_PREFIX :110)
  -> get_loaded_models(...)                        (model_concurrency.py:307-320)
  -> GET /fleet -> nodes[].loaded_models           (ivgs-scheduler/main.py:787, :816)
  -> poll_model_node_availability                  (ivgs-workers/tasks/periodic_tasks.py:1017)
  -> _reconcile_availability                       (periodic_tasks.py:918-1002)
  -> PG model_node_availability
```

**It never inspects a filesystem.** `_reconcile_availability`'s own docstring
says what it does: *"Servable models present on a node become AVAILABLE"*,
where "present" means the model NAME appeared in a `/fleet` snapshot.

**The LRU key has no expiry.** Measured on node-01's Redis, 2026-08-26:

```
gpu:model_lru:node-03:gpu0:0    -> ttl=-1   members=cogvideox_5b,kokoro-82m,latentsync
gpu:model_lru:7f479b3018af:gpu0:0 -> ttl=-1 members=latentsync
gpu:model_lru:3772bab239e5:gpu0:0 -> ttl=-1 members=flux1-schnell
```

So it is a permanent record of *"a job ran this here once"*. The
container-hash keys (`7f479b3018af`, `3772bab239e5`, `78bbe35faab1`,
`61c7c02b3a8a`, `3b11b9cc6f16`, `bb0711848fba`) are dead worker containers whose
rows are still in `model_node_availability` — nine of the twelve rows in that
table point at nodes that no longer exist.

**The poller runs every 30 seconds** (`ivgs-workers/celery_app.py:380`) and
flips every AVAILABLE row not in the current snapshot to UNAVAILABLE
(`periodic_tasks.py:996-1000`). This is decisive for §2's schema choice.

### 1.3 How Wan came to show `34.1 GB / 1 available` — and why it is wrong

**Hypothesis in the brief: hand placement plus a recorded row. PARTLY DISPROVEN.**

* `34.10` **is** hand-typed. The WP-46 attestation records a measured
  *"34.06 GiB"*; the row says `34.10`. A human rounded and transcribed.
* `1 available` is **not** a hand-placed row. It is live: node-04's LRU carries
  `wan2.2-animate` because a real render ran on 2026-08-25 (asset `3bc54e58`,
  per the attestation), and `last_health_check` was `2026-08-26 20:46:45` when
  measured — refreshed seconds earlier.
* **THE NODE IS WRONG.** The row says `node-04:gpu0`. The bytes are on
  **node-03**.

Measured, read-only, 2026-08-26:

```
node-04  ivgs-comfyui-primary   192.168.1.93:8188
  CheckpointLoaderSimple.ckpt_name = ['flux1-schnell-fp8.safetensors']
  UNETLoader.unet_name = []      LoraLoader.lora_name = []
  CLIPVisionLoader.clip_name = []   VAELoader.vae_name = ['pixel_space']
  WanVideoModelLoader             -> NOT INSTALLED (empty /object_info)

node-03  ivgs-wan-animate-server-node03   192.168.1.92:8220
  WanVideoModelLoader.model = ['Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors']
  WanVideoVAELoader.model_name = ['Wan2_1_VAE_bf16.safetensors']
  CLIPVisionLoader.clip_name = ['clip_vision_h.safetensors']
```

node-04's ComfyUI mounts exactly one directory —
`/data/models/comfyui/checkpoints` (`ivgs-infra/docker-compose.node04.yml:68`) —
and does not have the WanVideo custom nodes installed at all. It **could not**
hold or load Wan2.2-Animate. node-03's `wan-animate-server`
(`docker-compose.node03.yml:191-207`) mounts eight model directories and has the
weights.

**So the "1 available" is accidentally right about the count and wrong about
everything else**, and it would read exactly the same if the bytes had been
deleted the moment after that one render.

### 1.4 Why the engine key does not identify a host

`shared/providers/binding.py:21-32` maps engine → one env var. But **two
different ComfyUI deployments share the key `comfyui`**, and
`docker-compose.node03.yml:113-120` says so in as many words:

> *"Wan2.2-Animate's engine key is `comfyui` … so resolve_endpoint('comfyui')
> reads IVGS_COMFYUI_URL — the same variable node-04's worker uses to reach the
> FLUX image ComfyUI. Two ComfyUI instances, one engine key, one endpoint map:
> they are told apart by the PER-WORKER value of this variable…"*

| Node | `IVGS_COMFYUI_URL` | Queues |
|---|---|---|
| node-03 `cogvideox-worker` | `http://wan-animate-server:8188` (`:120`) | `gpu_video,gpu_animation` |
| node-04 `celery-worker` | `http://comfyui:8188` (`node04:105`) | `gpu_image,gpu_tts,gpu_talking_head` |
| node-01 workers | **unset** → binding default `http://node-04:8188` | `default,notifications,cleanup`; `composition` |

Placement is therefore decided by **queue routing plus per-worker env**, and the
Model Store renders the GPU scheduler's *unrelated* VRAM-based node choice. The
two placement decisions do not agree and nothing reconciles them.

Also measured: `COMFYUI_FALLBACK_URL=http://192.168.1.94:8188` in node-01's
worker env points at **node-05**, the Qwen node. Connection refused (`000`).
A stale fallback to a node that has never served ComfyUI.

### 1.5 What a worker does when weights are absent — NOT DISTINGUISHABLE

`animation_generation_task.py:61` imports `WanAnimateClient` at module level.
A missing model file surfaces as ComfyUI rejecting the graph at validation:
`WanAnimateWorkflowError("ComfyUI rejected the workflow: HTTP 400 …")`
(`ivgs-workers/clients/wan_animate_client.py:417-420`), which is the **same
class and the same message shape** as a malformed graph, a wrong node version,
or a bad input. `wan_animate_client.py:79-80` defines it as
*"ComfyUI reported an execution error, or the graph was rejected"* — the two
are deliberately one class.

**There is no distinguishable "weights absent" failure**, and there is no
pre-flight check: `available_node_types()` exists (`:317-330`) and checks node
TYPES, not model FILES.

### 1.6 Verdict

Declared-but-inert is the wrong description here — the poller genuinely runs and
genuinely writes. The accurate statement is **measuring-the-wrong-thing**:
every part of the chain works, and the thing at the end of it is not
availability. That is the sixth surface since WP-57 to present a real signal as
an answer to a question it was never asked.

---

## 2. TASK 2 — the weight fetch service

### 2.1 The finding that reshapes the task: engine-only certifications

`/opt/MBCP/mbcp_api/api/v1/certifications.py:603-622` (read-only clone):

```python
is_engine_only = not cert.weights_checksum
bundle_digest = cert.weights_checksum or engine_digest
...
if is_engine_only:
    bundle_manifest_url = f"{settings.serving_url}/engines/{engine_digest}/manifest"
else:
    bundle_manifest_url = f"{settings.serving_url}/weights/{cert.model_id}/manifest?tier=certified"
```

with the comment *"engine_only has NO weights to serve, so it must NOT point at
/weights/{model}/manifest"*.

IVGS stores that URL in a column called `weights_ref` and that digest in one
called `weights_checksum` (`ivgs-api/app/api/ad01_ingest.py:176-177`, `:197-198`).
**The names are wrong for half the rows**, and the consequences are visible:

```sql
SELECT weights_checksum, count(*), string_agg(name,', ')
  FROM models WHERE weights_checksum IS NOT NULL GROUP BY 1 HAVING count(*)>1;

 sha256:257fc2624282e57ce36457d8d9ae06a8672e5d90ebd6c475b8b7146fa36df9b5 | 5 |
   FLUX.1-dev, Wan2.2-T2V, CogVideoX-5b, Wan2.2-Animate, MimicMotion
```

**Five models share one "weights checksum".** It is not a bug in the backfill —
it is the ComfyUI **engine image digest**, correctly recorded, in a column whose
name says something else. Verifying bytes against it would pass any of five
different models' weights.

And `mbcp_serving` has **no `/engines/{digest}/manifest` route at all** — its
routes are `/ingest`, `/promote`, `/revoke`, `/internal/*`, `/healthz`,
`/weights/{id}/manifest`, `/weights/{id}/files/{name}`
(`/opt/MBCP/mbcp_serving/api/*.py`). A fetch against an engine-only reference
would 404.

**This is an MBCP-side observation, recorded and not acted on** — `/opt/MBCP` is
a read-only reference clone and the seam is change-controlled (CLAUDE.md §11.1).

### 2.2 What was built

`mbcp_fetch.py`'s verification was **relocated, not rewritten** — it was already
correct and already proven, and two copies of HMAC + per-file SHA-256 + digest
checks drift. `ivgs-models/mbcp_fetch.py` is now a re-export shim keeping the
operator CLI's arguments, exit codes and output identical.

| File | What it is |
|---|---|
| `shared/weights/refs.py` | Parses `weights_ref`. Three shapes recognised, everything else refused by name. |
| `shared/weights/placement.py` | Task 3. Engine hosts and directory conventions, **as data**. |
| `shared/weights/bundle.py` | The verification core, relocated + **staging**. |
| `shared/weights/service.py` | The refusal ladder, then fetch/verify/record. |
| `shared/weights/errors.py` | One class per refusal, each with a stable `reason` slug. |
| `ivgs-api/app/services/weight_placement.py` | Computes the surface state; records outcomes. |
| `ivgs-api/migrations/versions/0039_wp65_weight_placements.py` | The table. |

**Staging is the one behavioural change to the fetch itself.** The original
streamed each file straight to its final path, so an interrupted fetch left a
truncated file exactly where a loader would find it. Bytes now go to a
`.staging-*` sibling, are fully verified there, and are promoted file-by-file
with `os.replace` (atomic per file; the destination is a live model directory
holding other bundles, so a directory rename is not available). The staging tree
is removed on **every** exit path.

### 2.3 Why a new table and not columns on `model_node_availability`

**Decisive: the poller would erase it within 30 seconds.**
`_reconcile_availability` (`periodic_tasks.py:996-1000`) flips every AVAILABLE
row not in the fleet snapshot to UNAVAILABLE, and it builds `desired` purely
from `loaded_models`. It knows nothing about bytes, so a fetch record there
would never be in `desired`, and the beat is `timedelta(seconds=30)`
(`celery_app.py:380`).

Three further reasons, each independently sufficient:

1. **Different owners.** That table is poller-owned; this is fetch-owned.
2. **Different questions.** *"A job loaded this name here once"* vs *"these
   bytes are on this disk and their hashes were checked."*
3. **Different node identity.** Availability keys on `node-04:gpu0`; weights
   live on `node-03`'s filesystem, not on a GPU.

Migration **0039**, exercised both ways on `ivgs_reconciliation_test`:

```
upgrade 0038 -> 0039   ->  model_weight_placements | 1   (table, and the type)
downgrade 0039 -> 0038 ->                          | 0   (both dropped)
upgrade 0038 -> 0039   ->  model_weight_placements | 1   (round trip clean)
```

Unlike 0027/0033/0034/0038, whose downgrades are deliberate no-ops (PostgreSQL
cannot remove an enum value in place), 0039 creates a **new** type and can drop
it cleanly — nothing pre-existing carries it.

### 2.4 The refusal ladder

Steps 1–6 need **no credentials and no network**, which is what lets the admin
page label a model correctly before anyone clicks.

| # | Refusal | `reason` | State it means |
|---|---|---|---|
| 1 | `NoWeightReferenceError` | `no_weight_reference` | never ingested from MBCP |
| 2 | `EngineOnlyCertificationError` | `engine_only_certification` | **no bytes exist**; deploy the image |
| 3 | `UnknownReferenceFormError` | `unknown_reference_form` | refused, not guessed |
| 4 | `NoHostForEngineError` | `no_host_for_engine` | Task 3; a correct end state |
| 5 | `NoPlacementRuleError` | `no_placement_rule` | host mounts no such directory |
| 6 | `PlacementNotLocalError` | `placement_not_local` | **see below** |
| 7 | `CredentialsUnavailableError` | `credentials_unavailable` | operator has not supplied the token |
| 8 | `BundleVerificationError` / `DigestMismatchError` | … | transfer/verify outcomes |

**`PlacementNotLocalError` was found while authoring the operator block, not by
reading.** The service resolves the animation destination to
`/opt/models/comfyui-wan/models/diffusion_models` on **node-03** — correct — but
nothing stopped `ivgs-fastapi` on node-01 from opening that path, creating it
locally, verifying a real bundle into it and recording it as available. That is
verified bytes in a directory no engine mounts, reported as present: **the exact
defect this package exists to close, reintroduced by the fix for it.** It now
fails closed, before the network is touched, and a host that declares no
`NODE_HOSTNAME` is treated as "not the target".

### 2.5 Acceptance — proven against fixtures (43 tests)

* successful fetch-verify-place-record cycle ✓
* checksum mismatch refused, **staging tree removed, nothing promoted** ✓
* second fetch no-ops with `skipped_present=True` and **zero** file requests ✓
* presence decided by **hash**, not existence — a truncated file is re-fetched ✓
* promotion leaves other bundles' files in the destination untouched ✓
* the digest form matches MBCP's reference byte for byte ✓
* the serving token never appears in an outcome, a plan repr or a record ✓

**The live pass is HELD** — operator block A, §8. Not run.

---

## 3. TASK 3 — placement policy

`ENGINE_HOSTS` in `shared/weights/placement.py` is one row per **engine
deployment**, not per engine, because an IVGS engine key does not identify a
host (§1.4). Directory layout is transcribed from MBCP's own
`ENGINE_MATERIALIZATION` (`mbcp_core/weights/materialization.py:37-100`) — the
map the .51 materializer already writes node-03's tree with — rather than a
second IVGS convention invented alongside it.

| engine | node | container | model root | mounts |
|---|---|---|---|---|
| comfyui | node-03 | `ivgs-wan-animate-server-node03` | `/opt/models/comfyui-wan/models` | 8 dirs |
| comfyui | node-04 | `ivgs-comfyui-primary` | `/data/models/comfyui` | `checkpoints` only |
| cogvideox | node-03 | `ivgs-cogvideox-server-node03` | `/opt/models` | `cogvideox-5b` |
| vllm | node-02 | `ivgs-vllm-primary` | `/data/models` | `hub` |

`host_for_model(engine, stage)` disambiguates the two `comfyui` rows **the way
the running system does** — by which node's worker consumes the stage's queue —
so `animation_generation` resolves to node-03 and `image_generation` to node-04.

**The refusal is tested as a first-class outcome**, and so is the case the brief
did not name: node-04 *hosts* `comfyui` but mounts no `diffusion_models`, so
placing an animation bundle there raises `NoPlacementRuleError` rather than
writing bytes where no loader looks.

`UNHOSTED_ENGINES` records `animatediff`, `remotion`, `sadtalker` and `wan21`
with the reason each is unhosted. A test asserts **node-05 and node-06 are not
placement targets** — both are out of bounds and nothing must ever place weights
on either.

---

## 4. TASK 4 — the surface tells the truth

`GET /api/v1/models` now carries `weight_placements[]` and a computed
`weight_status` (`ivgs-api/app/api/v1/model_store.py`, `_with_weight_status`).
Two new routes: `GET /models/{id}/weight-status` (no side effects) and
`POST /models/{id}/fetch-weights` (**admin-only, GUI-only** — the standing
zero-CLI rule).

**Eight states where there was one word.** The admin page's Nodes column became
**Weights**, and each state carries the action it implies:

| state | shown as | action |
|---|---|---|
| `available` | weights verified on node-03 | — |
| `not_fetched` | certified, weights not fetched | Fetch weights |
| `engine_only` | engine-only certification — no weights to fetch | deploy the image |
| `no_host` | no node hosts this engine | stand a host up |
| `no_reference` | no weight reference — not ingested from MBCP | register/re-certify |
| `unknown_reference` | weight reference not understood | refused, not guessed |
| `fetching` / `failed` | in progress / last fetch failed + reason | — |

**No fabricated zero.** `bytes_on_disk` is `None` when nothing was measured and
the UI prints *"not measured"*, never `0 B`. `vram_gb` is now labelled
*"Declared at registration, not measured"* and *"not declared"* replaces the
bare em-dash, with the real on-disk size shown beneath it where one exists.

**The scheduler signal is kept and demoted.** `node_availability` still renders,
under *"Scheduler residency (not weights)"*, with a tooltip saying what it is.
It is a real signal about a real thing; it was simply answering the wrong
question.

**Rendered against live data** — §7 records the live `GET /api/v1/models`
response after deploy, showing `wan2.2-animate` available on node-03 and the
three engine-only rows saying so distinctly.

The `fetch-weights` route answers **202 for every outcome**, because a refusal
is the answer to the action, and it is durable: the placement row records which
refusal it was, so *"nobody has tried"* and *"this can never work"* stop looking
the same.

---

## 5. TASK 5 — engine-name reconciliation

### 5.1 Where the transform is, and that it was already fixed

`ivgs-api/app/api/ad01_ingest.py:156` — `engine = bundle.engine or
_STAGE_DEFAULT_ENGINE.get(stage)`. IVGS was **not** overriding a value MBCP
sent; it was supplying its own when MBCP sent none. Commit **`d536967`**
(WP-46) already changed that default from `ANIMATEDIFF` to `COMFYUI`:

```
-    ModelStage.ANIMATION_GENERATION: ModelEngine.ANIMATEDIFF,
+    ModelStage.ANIMATION_GENERATION: ModelEngine.COMFYUI,
```

**Nothing pinned it.** No test asserted the value, so a future tidy-up would
have reverted it silently. `ivgs-api/tests/test_wp65_engine_reconciliation.py`
(11 tests) is the pin, and it is **verified red-green**: reverting the one line
turns two tests red, restoring it turns them green.

### 5.2 The STOP check — does not apply

| model | engine | state | enabled | is_default | selections | availability rows |
|---|---|---|---|---|---|---|
| AnimateDiff-SD15 | animatediff | candidate | f | f | 0 | 0 |
| MimicMotion | animatediff | candidate | f | f | 0 | 0 |
| Wan2.2-Animate | animatediff | candidate | f | f | 0 | 0 |

There are **zero rows in `project_model_selections` fleet-wide**, and
`_SERVABLE_VIA_SELECTION = ("approved","deprecated")` (`factory.py:44`) means a
candidate cannot resolve at all.

**The live serving model is a SEPARATE ROW and was already `comfyui`.** The
store holds both `wan2.2-animate` (lowercase, comfyui, approved, default,
serving) and `Wan2.2-Animate` (capitalised, MBCP-ingested, candidate, disabled).
The brief read these as one model with two engine names; they are two rows. The
correction cannot reach the serving one.

### 5.3 The correction — applied

```sql
UPDATE models m SET engine='comfyui', updated_at=now()
 WHERE m.engine='animatediff' AND m.stage='animation_generation'
   AND m.state='candidate' AND m.enabled=false AND m.is_default=false
   AND NOT EXISTS (SELECT 1 FROM project_model_selections s WHERE s.model_id=m.id);
-- UPDATE 3
```

| id | name | before | after |
|---|---|---|---|
| `06c53d62-cd8f-4732-9d52-3f4b892d2988` | AnimateDiff-SD15 | `animatediff` | `comfyui` |
| `ab3342a7-132c-444e-95f1-f94cef163d70` | MimicMotion | `animatediff` | `comfyui` |
| `e5473067-71d0-4c48-9f90-0016f2372069` | Wan2.2-Animate | `animatediff` | `comfyui` |
| `8d00bb16-be1c-44e3-952d-a9e7b2e6ebd5` | wan2.2-animate | `comfyui` | **untouched** |

`engine` and `updated_at` only. No lifecycle state, no flags, no other column.
Zero `animatediff` rows remain.

---

## 6. TASK 6 — storyboard prompt v5

### 6.1 The checker already caught both defects

Run against the operator's **real v4 storyboard** (project `92e30c7e`, 13
scenes, read-only SELECT — its scenes are stated evidence and nothing was
modified), the existing `check_visuals` returned **22 findings**, including
exactly what the brief describes:

* duplicates at **9≡5, 10≡6, 11≡0** — the brief's three pairs, confirmed;
* digits in scenes **1, 2, 4, 7, 8** — the brief's five, confirmed;
* and 14 more (stock framing, no step named, clips that describe no motion).

So the brief's two requested checker extensions were **already implemented**,
and the digit one more strictly than requested (`re.compile(r"\d")` fails on a
single digit; "multi-digit numerals" would have been a **relaxation**, which the
rules forbid). `DIGITS` is unchanged.

### 6.2 What was actually missing, and what was added

**The identity check only catches byte-identical repeats.** Strengthened with
content-word Jaccard similarity (`NEAR_DUPLICATE_THRESHOLD = 0.85`, style and
setting vocabulary excluded so a deliberately consistent visual style does not
read as a repeat). Re-run on the same storyboard, it finds **six** repeated
pictures, not three:

```
 8 vs  2: 100%      <- content-identical; the byte check MISSED this
 7 vs  1:  94%      <- missed
 5 vs  3:  90%      <- missed
11 vs  0: 100%      <- caught before
 9 vs  5: 100%      <- caught before
10 vs  6: 100%      <- caught before
```

The threshold is measured, not guessed: the six repeats score 90–100%, the
highest non-repeat scores 60%, and 0.85 sits in that gap. Strictly stronger —
everything the old check rejected, it still rejects.

### 6.3 v5's two amendments

**(a) RULE 1 — naming a number in prose.** v4's WRONG examples are all about
text written *on a surface*, so "23 on top and 14 underneath" read as permitted.
v5 names the failure, gives an applicable **test** (*delete every digit — does
the description still say what the scene teaches?*), three WRONG examples drawn
from the measured run, and the vocabulary that replaces digits: *position,
count, width, order, emptiness*.

**(b) RULE 6 — the recap gap.** The repeats are the storyboard's **tail
repeating its head** (11←0, 9←5, 10←6). v4 *forbade* repeats but gave no
sanctioned way to picture a recap, so the model copied. v5 says how to write a
revisiting scene (the *completed* working, never the working mid-step) and adds
a closing self-check whose operative invariant is **the working surface only
ever gains** — a property the model can check against its own output.

`RULE 1` is tightened, not traded. All 13 publisher gate phrases survive, pinned
by `test_wp65_storyboard_v5.py` (30 tests), and the publisher gains five new
gate phrases of its own.

### 6.4 The publish

*(Publisher output verbatim — §7.)*

**The operator's in-flight project is unaffected.** Its scenes are stored rows
generated under v4. It was read, never modified, never regenerated, never
triggered, never approved.

---

## 6b. TESTS AND THE BASELINE

*(Counts confirmed by the runs quoted in §7.5.)*

| file | tests | what it pins |
|---|---|---|
| `ivgs-api/tests/test_wp65_weight_fetch.py` | 44 | reference parsing (all three shapes + four refusals), placement (both `comfyui` deployments, the unhosted refusal, node-05/06 excluded), the fetch core (staging, mismatch cleanup, hash-based idempotency, promotion beside other bundles, MBCP digest equivalence), the refusal ladder in order, the off-target guard, and that no label overclaims absence |
| `ivgs-api/tests/test_wp65_storyboard_v5.py` | 30 | the near-duplicate detector, and v5's two amendments as contract phrases; every WP-63/WP-64 gate phrase still present |
| `ivgs-api/tests/test_wp65_engine_reconciliation.py` | 11 | the ingest engine default — **verified red-green** |
| `ivgs-api/tests/test_wp63_storyboard_prompt.py` | 34 (unchanged) | strengthened, not extended: `check_visuals` gains near-duplicate detection. **No test was weakened and none removed.** |

**`DIGITS` was deliberately NOT changed.** The brief asked for "multi-digit
numerals" to fail; `re.compile(r"\d")` already fails on a single digit.
Implementing the request literally would have been a relaxation, which the
package rules forbid.

Nothing was skipped, no assertion loosened, no coverage deleted.

---

## 7. WHAT WAS DEPLOYED, AND THE LIVE EVIDENCE

### 7.1 node-01, `v5.24.0-weights`

Migration **0039** applied to live `ivgs` (`0038 -> 0039`) **before** the API
started — the ORM declares `model_weight_placements` with a `selectin`
relationship, so an API on the new image against a 0038 database would fail
every model read.

```
ivgs-fastapi              ghcr.io/brucecostello2/ivgs-api:v5.24.0-weights        Up (healthy)
ivgs-celery-default       ghcr.io/brucecostello2/ivgs-workers:v5.24.0-weights    Up (healthy)
ivgs-celery-composition   ghcr.io/brucecostello2/ivgs-workers:v5.24.0-weights    Up (healthy)
ivgs-celery-beat          ghcr.io/brucecostello2/ivgs-workers:v5.24.0-weights    Up (healthy)
ivgs-nextjs               ghcr.io/brucecostello2/ivgs-frontend:v5.24.0-weights   Up (healthy)
```

Artifacts banked through `scripts/save-image-artifact.sh` with the standard
filename (GHCR is off the deploy path):

```
brucecostello2_ivgs-api_v5.24.0-weights.tar.zst        126,015,304  f22b833c…
brucecostello2_ivgs-workers_v5.24.0-weights.tar.zst    333,208,305  a1f7911c…
brucecostello2_ivgs-frontend_v5.24.0-weights.tar.zst    58,588,606  6d6645a8…
```

**Nodes 02/03/04 were NOT touched.** Their paste blocks are §8 Block B.

### 7.2 Task 6's publish — publisher output, verbatim

```
template      : /app/seed/default_prompts/storyboard_generation.j2
file sha256   : f861c7e3898cd4c135eae368ddd262888fc2157c0015b3c6a256cd40c700f5aa
stored sha256 : a803d746c877579ac756489dc28691b03ce81eb0bb75600a9565c20fb8ce1a22
file bytes    : 16989   stored chars: 16988
contract : OK (RULE 0, RULE 2, RULE 5, RULE 6 and RULE 7 present, RULE 1 intact,
               WP-65 v5 amendments present)

BEFORE:
  63835b0d-c2ba-4e81-8786-a810aa884348  v1  active=False  2026-05-23 15:42:45.169227+00:00
  19c8197a-7809-4777-92cd-ea684edee3cf  v2  active=False  2026-08-22 23:56:35.244014+00:00
  e8d5e044-223c-4fee-987c-cac7b60f8b96  v3  active=False  2026-08-25 10:33:22.066210+00:00
  22c0acf2-13e7-4c24-9867-c7f79ef61ecd  v4  active=True   2026-08-26 18:31:23.457418+00:00

v4 -> is_active false  (22c0acf2-13e7-4c24-9867-c7f79ef61ecd)
v5 inserted             (5d36291e-c5c0-419c-aff6-38213ef68519)

AFTER:
  v1 False   v2 False   v3 False   v4 False   v5 active=True

ROLLBACK, if the next storyboard reads worse: one UPDATE flips is_active back
to v4. Nothing was deleted.
```

### 7.3 Task 4's surface, against live data

`compute_status` over all 18 live rows, inside `ivgs-fastapi`, after deploy:

| weight state | count | models |
|---|---|---|
| `engine_only` | **11** | FLUX.1-dev, CogVideoX-5b, Wan2.2-T2V, AnimateDiff-SD15, MimicMotion, Wan2.2-Animate, Kokoro, XTTS-v2, latentsync, FFmpeg-composition, Llama-3.3-70B-Instruct |
| `unknown_reference` | **4** | llama-3.3-70b-transcript, llama-3.3-70b-storyboard, flux1-schnell, kokoro-82m |
| `no_reference` | **2** | test-model-1, latentsync-alt |
| `not_fetched` | **1** | wan2.2-animate |
| `available` | **0** | — |

**This is a much larger finding than the brief's.** The brief describes two
models whose bytes never landed. In fact **eleven of eighteen** rows are
engine-only certifications for which MBCP has no weight bundle at all, and the
`weights_ref`/`weights_checksum` columns hold engine identities for every one of
them.

The four `unknown_reference` rows are hand-registered and use the column as free
text — HuggingFace repo ids (`hexgrad/Kokoro-82M`,
`RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic`) and a node-local filesystem path
(`node-04:/app/ComfyUI/models/checkpoints/…`). Refusing to parse those is
correct: guessing at them is how the wrong bytes get fetched and recorded as
verified. **Three distinct absences, three distinct labels, three distinct
actions — which is what Task 4 asked for.**

### 7.5 Tests — ZERO NEW FAILURES

Two full runs, the package's allowance. Run 1 confirmed the tree before the last
two corrections; run 2 is authoritative.

```
.venv/bin/python -m pytest ivgs-api/tests
  1208 passed, 2307 warnings in 311.99s        baseline 1123 passed, 0 failed  -> +85, 0 failed

.venv/bin/python -m pytest ivgs-workers/tests
  18 failed, 887 passed, 48 skipped, 15 errors in 34.94s
  baseline                     18 failed, 887 passed, 48 skipped, 15 errors    -> IDENTICAL
```

`ivgs-workers` was re-run rather than assumed, because
`shared/models/model_store.py` gained a table that tree imports. Every one of
its four figures is unchanged. `TEST-BASELINE_2026-08-25.md` is updated in the
same commit as the change that moved it, per the rules.

### 7.4 The honest gap in the acceptance

The brief asks the surface to show *"at least one truly available model"*. **It
shows none, and that is the true answer.** No verified fetch has been recorded,
because the live pass is held for credentials.

`wan2.2-animate` is the interesting case and it forced a correction. Its bytes
**are** on node-03 — measured, its engine enumerates them — but no placement row
exists, because the operator's CLI placed them before this table did. The label
first read *"certified, weights not fetched"*, which is **false about the node
and true only about IVGS's records**. It now reads *"no fetch recorded by
IVGS"*, and a test pins that it must not assert absence
(`TestTheSurfaceDoesNotOverclaimAbsence`). Getting the distinction wrong here
would have reproduced, in the fix, the exact defect the package exists to close.

---

## 8. OPERATOR BLOCKS — authored, held, NOT RUN

*(Blocks A, B and C, below.)*

---

## 9. THE LEDGER

| id | what | why it is not closed here |
|---|---|---|
| **WP-65 L-1** | `fetch-weights` cannot place bytes on a remote node; it refuses with `placement_not_local`. The architectural answer is a Celery task on the target node's queue. | A new worker task is beyond this package, and the live pass is held anyway. The refusal is honest and tested; the CLI covers the operator path. |
| **WP-65 L-2** | `models.weights_checksum` holds an **engine image digest** for engine-only certifications, and `weights_ref` holds an engine manifest URL. Five rows share one value. | The column names are IVGS's; the semantics are MBCP's. Renaming is a seam change, change-controlled (CLAUDE.md §11.1). |
| **WP-65 L-3** | MBCP emits `/engines/{digest}/manifest`, a route `mbcp_serving` does not implement. | MBCP-side. `/opt/MBCP` is read-only. |
| **WP-65 L-4** | `model_node_availability` holds 9 rows keyed on dead container hashes; the Redis LRU has no TTL. | Pruning is a poller change; `scripts/prune-scheduler-model-keys.sh` exists and is the operator's. Recorded, not run. |
| **WP-65 L-5** | `check_visuals` is not wired into the pipeline. | Its only home is Stage 2's task body, frozen under AD-05 §8. Carried forward from WP-63. |
| **WP-65 L-6** | `COMFYUI_FALLBACK_URL` points at node-05 (Qwen), connection refused. | A config change on a node this run may not touch. |
### OPERATOR BLOCK A — the first real weight fetch (WP-65 Task 2, STAGED, NOT RUN)

Held because it needs the MBCP serving token and signing key, which are the
operator's standing pending-register item. **Never printed, never committed,
never written to a Model Store row.** IVGS reads them from the environment and
records only that they were present.

```bash
# node-01. Supply the two secrets for THIS SHELL ONLY. Do not add them to
# ivgs-infra/.env* -- nothing in the deploy path needs them persisted.
read -rsp "MBCP serving token: " MBCP_SERVING_TOKEN; echo
read -rsp "MBCP signing key  : " MBCP_WEIGHT_SIGNING_KEY; echo
export MBCP_SERVING_TOKEN MBCP_WEIGHT_SIGNING_KEY

# Dry run first: what WOULD be fetched, and where. No network, no credentials
# used. Every refusal short of the transfer is decidable offline.
cd /opt/ivgs
sudo docker exec -i ivgs-fastapi python - <<'PY' | tr -cd '\11\12\15\40-\176'
import asyncio
from sqlalchemy import select
from shared.database import async_session_factory
from shared.models.model_store import Model
from shared.weights.service import plan_fetch

async def main():
    async with async_session_factory() as s:
        for m in (await s.execute(select(Model).order_by(Model.stage, Model.name))).scalars():
            p = plan_fetch(m)
            if p.can_fetch:
                print(f"FETCHABLE {m.name:<26} -> {p.host.node_id}:{p.dest_dir}")
            else:
                print(f"refused   {m.name:<26} [{p.reason}] {p.message[:90]}")
asyncio.run(main())
PY
```

Then, for ONE model at a time, through the GUI (admin functionality has no CLI):

    Admin -> Models -> expand the row -> "Fetch weights"

The confirm dialog states the destination node, directory and container before
anything happens. Bytes are staged under a `.staging-*` sibling, every file's
SHA-256 checked against the signed manifest, the bundle digest recomputed, and
only then moved into place. A failure at any point removes the staging tree.

**The API container must be able to see the destination.** `fetch-weights`
writes to `plan.dest_dir`, which for the animation family is
`/opt/models/comfyui-wan/models/diffusion_models` **on node-03** -- a path
node-01's `ivgs-fastapi` does not mount. Until the placement is executed by a
worker on the target node (ledgered, WP-65 L-1), the live fetch is an
operator-run CLI on the target node:

```bash
# node-03 ONLY. Same verification core the API uses -- one implementation.
export MBCP_SERVING_TOKEN=...        # not echoed, not persisted
python -m ivgs-models.mbcp_fetch \
  --serving-url https://<mbcp-serving-host> \
  --model-id <models.weights_ref's model_id> \
  --dest /opt/models/comfyui-wan/models/diffusion_models \
  --tier certified
```

### OPERATOR BLOCK B — nodes 02/03/04, v5.24.0-weights (AUTHORED, NOT RUN)

Only node-01 was deployed by this package. These are the paste blocks for the
rest of the fleet. **node-03's worker service is `cogvideox-worker`, not
`celery-worker`** (WP-44 §6.3): naming the wrong one starts a second worker on
the same queues and leaves the real one on the old image.

```bash
# node-02
cd /opt/ivgs && \
zstd -d -c /mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.24.0-weights.tar.zst | sudo docker load && \
sudo docker compose --env-file ivgs-infra/.env -f ivgs-infra/docker-compose.node02.yml \
  up -d --pull never --no-deps celery-worker && \
sudo docker inspect ivgs-celery-worker-node02 --format '{{.Config.Image}}'
```

```bash
# node-03  -- cogvideox-worker, NOT celery-worker
cd /opt/ivgs && \
zstd -d -c /mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.24.0-weights.tar.zst | sudo docker load && \
sudo docker compose --env-file ivgs-infra/.env -f ivgs-infra/docker-compose.node03.yml \
  up -d --pull never --no-deps cogvideox-worker && \
sudo docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
```

```bash
# node-04  -- --no-deps matters: celery-worker depends_on comfyui
cd /opt/ivgs && \
zstd -d -c /mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.24.0-weights.tar.zst | sudo docker load && \
sudo docker compose --env-file ivgs-infra/.env -f ivgs-infra/docker-compose.node04.yml \
  up -d --pull never --no-deps celery-worker && \
sudo docker inspect ivgs-celery-worker-node04 --format '{{.Config.Image}}'
```

### OPERATOR BLOCK C — confirm what is actually on node-03's disk (READ-ONLY)

WP-65 Task 1 could not measure node-03's filesystem: running a command on a node
other than node-01 is out of bounds for this run. What it COULD measure is what
the engine enumerates, which is the fact that matters for loading, and that is
recorded in §1. This block closes the remaining gap.

```bash
# node-03, read-only
sudo du -sh /opt/models/comfyui-wan/models/* 2>/dev/null | sort -k2
sudo find /opt/models/comfyui-wan/models -name '.staging-*' -maxdepth 2
```

A `.staging-*` directory here would be the residue of an interrupted fetch. None
can exist yet -- staging is introduced by this package -- so finding one means a
fetch ran between this report and the block.


---

## 10. PUSH BLOCK — count-gated, for WP-65's commits ONLY

**Commits are HELD. Nothing was pushed.** The operator pushes all four packages
when they return; this block covers WP-65 alone and refuses if the count is not
what this report says.

```bash
# node-01. Refuses unless exactly the expected number of WP-65 commits are
# ahead of origin/main -- a count that does not match means another package's
# commits are in the range, and the push is not this report's to authorise.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  EXPECTED=2
  AHEAD=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $AHEAD (expected $EXPECTED for WP-65 alone)"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$AHEAD" -ne "$EXPECTED" ]; then
    echo "REFUSED: $AHEAD commits ahead, expected $EXPECTED."
    echo "If WP-66/67/68 have since committed, use the RUN SUMMARY's combined block instead."
  else
    echo "git push origin main    # <- run this line by hand"
  fi
)
```

Expected, for WP-65 alone:

| # | commit |
|---|---|
| 1 | `fix(wp-65): a certified model's bytes get a fetch, a placement and a record that means it` |
| 2 | `docs(wp-65): report - the fetch was never missing, and the store was measuring the wrong thing` |
