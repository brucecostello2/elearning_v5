# WP-67-CLIENTS — report, 2026-08-26

Tag **`v5.26.0-clients`**. Commits HELD, not pushed. Deployed to **node-01 only**.

**Headline: the registry the brief asked for already existed, keyed on the wrong
thing — and one media stage never consults a binding at all, so WP-66's whole
capability is inert for it. Task 4 stops at a frozen body, as the brief
predicted, and the exact edit M3.3 will make is written out.**

---

## S0. VERDICTS

| Task | Outcome |
|---|---|
| 1 — the client selection point | **DONE.** A registry exists; it is keyed on engine alone. And `video_generation` ignores the binding entirely. §1. |
| 2 — a registry keyed on family | **DONE.** `(stage, engine, family)`, capability contracts, pre-flight, and equivalence to today's routing proven by test. §2. |
| 3 — one new family end to end | **DONE.** AnimateDiff-SD15, chosen on measured evidence over MimicMotion. Fixture-proven; live run staged. §3. |
| 4 — the stage's refusals become the client's | **STOPPED at the frozen body**, with the exact edit written. §4. |
| 5 — the store learns which families run | **DONE and deployed.** Three states, three different people, three different actions. §5. |

**This is the outcome the brief called complete and successful**: *"If every
client selection point is inside a frozen body, this package delivers Task 2's
registry, Task 3's adapters, and their tests — proven in isolation — and ledgers
the wiring for M3.3."* Every point but one is inside a frozen body. The one that
is not is worse than frozen: it does not read the binding at all.

---

## 1. TASK 1 — the client selection point, measured

### 1.1 `clients/graphs/` — one file, and choice is not parameterised

`ivgs-workers/clients/graphs/` contained exactly **one** file,
`wan_animate.json`. The graph is chosen by a **module-level constant** —
`wan_animate_client.py:50`, `GRAPH_PATH = Path(__file__).../graphs/wan_animate.json`
— loaded once and cached (`:286-289`), deep-copied and slot-injected per render
(`:379`).

So the brief's lead is half-true: per-model behaviour **is** expressed as a
ComfyUI graph plus parameters, which is why a new family needs a graph and a
small adapter rather than a whole engine. But graph choice is **not**
parameterised by model — it is welded to its client by a constant.

### 1.2 Where the client is chosen, per stage, with the frozen verdict

| stage | where the client is chosen | frozen? |
|---|---|---|
| `animation_generation` | **module-level import**, `animation_generation_task.py:61`, plus the typed parameter at `:438`. The binding supplies the endpoint and model id only. | **FROZEN** — stage body |
| `video_generation` | `_select_model(scene)` at `:224-232`, then a two-branch `if` at `:372-386` with a swap-the-other-one fallback at `:392-411`. **See §1.3.** | **FROZEN** — stage body |
| `image_generation` | `providers/image.py:31-51` — `build_comfyui` branches on `binding.stage` | **NOT frozen** — provider layer |
| `talking_head` | `providers/talking_head.py:183-184` registers two engines; the SadTalker fallback is inline at `talking_head_task.py:354-382` | **provider layer NOT frozen; the fallback IS** |
| `tts_audio` | `providers/tts.py:43-44` — two engines, two builders | **NOT frozen** |

`ivgs-workers/providers/` is not a stage body and is not in AD-05 §8's preserve
list; the brief rules it unfrozen in as many words ("`ivgs-workers/clients/` and
`shared/providers/`"). The stage task bodies are frozen by CLAUDE.md §3 and
AD-05 §8's stop-rule: *"If a migration session finds itself editing stage
internals, stop."*

### 1.3 THE FINDING THE BRIEF DID NOT ANTICIPATE

**`video_generation_task.py` is the only media stage that never calls
`get_binding`.** Measured across `ivgs-workers/tasks/`:

```
animation_generation_task  get_binding x4      stage3_images        x6
stage1_transcript          x2                  stage5_voiceover     x2
stage2_storyboard          x2                  talking_head_task    x2
video_generation_task      ---  NONE  ---
```

It picks its client from a heuristic on the scene instead:

```python
# video_generation_task.py:224-232
def _select_model(scene) -> str:
    if scene.preferred_model != "auto":
        return scene.preferred_model
    if scene.duration_seconds <= 5.0 and scene.scene_type in ("broll", "transition"):
        return "wan21"
    return "cogvideox"
```

**So WP-66's entire capability is inert for video.** A user who selects
CogVideoX-5b or Wan2.2-T2V on the Models tab changes a row that
`video_generation_task` never reads; the client is chosen by clip length. The
selection is recorded, audited, invalidates the draft gate — and does not reach
the render.

This is a frozen body, so it is **ledgered (WP-67 L-1)**, not fixed. It is the
single highest-value item in that ledger: WP-66's video-stage picker is honest
about everything except that nothing downstream consults it.

### 1.4 What the binding carries — and what it does not

`ModelBinding` (`shared/providers/binding.py:105-121`) exposes `model_id`,
`name`, `display_name`, `stage`, `engine`, `tier`, `endpoint`, `node_id`,
`vram_requirement_mb`, `dynamically_loadable`, `default_params`, `selection_id`,
`selected_by`, `rationale`.

**There is no `family` field.** So this is *not* the fourth declared-but-unused
mechanism the brief expected to find — the mechanism does not exist at all, and
family has to be derived (§2.2). A cleaner answer than the brief predicted, and
a smaller change: nothing has to be un-lied about.

### 1.5 The registry that already existed

`register_engine_builder(engine, builder)` (`factory.py:47`), populated at
import by `ivgs-workers/providers/{llm,image,video,tts,talking_head}.py`. Seven
engines registered.

**Keyed on ENGINE ALONE — and that is the gap.** Where one engine serves two
families the builder branches:

```python
# ivgs-workers/providers/image.py:31-51
def build_comfyui(binding, **kwargs):
    if binding.stage == "animation_generation":
        return WanAnimateClient(...)
    return FluxClient(...)
```

That is the "chain of ifs" Task 2 exists to replace, already two branches deep
on one engine — and it branches on **stage**, which cannot tell two *animation*
families apart at all. A third ComfyUI family is a third branch and a fourth is
a fourth.

---

## 2. TASK 2 — the registry, keyed on family

### 2.1 What was built

| file | what |
|---|---|
| `shared/providers/contracts.py` | `SceneInput`, `ClientContract`, `SceneCapabilities`, `preflight` |
| `shared/providers/client_registry.py` | `(stage, engine, family) -> ClientSpec`, family derivation, `resolve_client`, `can_client_run` |

Registration is **by declaration**, one `register_client(...)` call per family,
and the built-ins are declared in one function that reads as a table.

**It does not import a client.** `ClientSpec.client_path` is a dotted string, on
purpose: `shared/` is imported by `ivgs-api` too, and the API has no business
loading a ComfyUI client to answer *"can this model run this scene?"*.

### 2.2 Family derivation, and why it needs no migration

Every live Model row carries no family. Resolution order:

1. `default_params["family"]` — what MBCP would send if it sent one.
2. `default_params["weight_family"]` — the materialization-map spelling.
3. A **name pattern registered beside the client that claims it**.
4. The model name, lowercased — so a refusal names something a human
   recognises rather than "unknown".

Backfilling a family by migration would be guessing at rows nobody has
re-certified. A pattern declared next to its client is auditable in one place
and disappears the moment MBCP starts sending the field.

### 2.3 Equivalence to today's routing — proven, not assumed

Eleven live models, each asserted to resolve to the client it uses today
(`test_every_live_model_resolves_to_the_client_it_uses_today`). Nothing about
any client's behaviour changed. And the thing the engine-keyed registry could
not do:

```
wan2.2-animate    -> wan_animate  -> WanAnimateClient   requires: prompt, reference_image,
                                                                  person_in_reference, reference_clip
AnimateDiff-SD15  -> animatediff  -> AnimateDiffClient  requires: prompt
```

Same engine, same stage, different clients, different contracts.

### 2.4 The capability contract, and the refusal that matters

`animation_generation_task.py:481` refuses a personless reference **as a
property of the stage**. Correct for Wan2.2-Animate — pose reenactment does not
decline a personless still, it hallucinates a subject — and wrong for the stage.

The requirement is now `wan_animate`'s, declared. The consequence, in one test:

```
scene = SceneCapabilities.of(PROMPT)          # a maths scene: words, no person
wan.ok        is False   "...it needs person_in_reference (a person visible in the
                          reference still. This model is pose reenactment: with no
                          subject in the reference it does not decline, it
                          hallucinates one...)"
animatediff.ok is True
```

That is the mechanism that would have caught "animation scene with no person" at
**selection** time. Pre-flight is pure, so a selection screen can call it as
cheaply as a dispatcher.

### 2.5 The honest refusal

`NoClientForFamilyError` — the state AnimateDiff would have hit today:

> model 'MimicMotion' is selected for stage 'animation_generation' on engine
> 'comfyui', but IVGS has no client for family 'mimicmotion'. Clients exist for:
> animatediff, wan_animate. **A model can be certified, fetched and selected and
> still have nothing in IVGS that knows how to call it; that is this state.**

Kept distinct from "this client cannot run this scene" (`can_client_run` raises
the first and returns the second), because one needs a developer and the other
needs a different scene or a different model.

---

## 3. TASK 3 — AnimateDiff-SD15, chosen on evidence

Measured against MBCP's own certified graphs, not preferred:

| | nodes | inputs |
|---|---:|---|
| `animatediff-sd15.json` | **8** | `CLIPTextEncode` + `ADE_EmptyLatentImageLarge` — the latent starts **empty**. **A prompt and nothing else.** |
| `mimicmotion.json` | **16** | adds `LoadImage`, `VHS_LoadVideo`, `MimicMotionGetPoses`, `InspyrenetRembg`, masks, compositing |

**MimicMotion is pose transfer: it needs a still AND a driving video** — the
same contract that makes Wan2.2-Animate unusable for a mathematics lesson, and
the reason WP-64 D-2 had to tie the animation criterion to a person in the
frame. AnimateDiff needs a prompt. For a repo whose measured problem is
*"thirteen scenes about column multiplication and no animation was possible"*,
the family that needs no person and no driving video is worth strictly more.

Delivered: the certified graph copied verbatim
(`clients/graphs/animatediff_sd15.json`), `AnimateDiffClient`, its registration,
and 16 fixture tests.

**One thing this client does that no existing one does**: it checks
`/object_info` for its required node types **before** rendering and raises
`AnimateDiffCapabilityError`. WP-65 Task 1 measured that a missing model file
and a missing custom node both surface as `"ComfyUI rejected the workflow: HTTP
400"` and are indistinguishable from a malformed graph. This one says *"the
ComfyUI at X does not have ADE_AnimateDiffLoaderGen1 … this is not a weights
problem and fetching weights will not fix it."*

**No live run is claimed.** Its weights are unfetched — WP-65 measured that its
certification is engine-only, so there is nothing to fetch — and no ComfyUI on
this fleet has the `ADE_*` nodes (probed 2026-08-26: node-04 answers `{}`). The
operator block is §8, staged.

---

## 4. TASK 4 — STOPPED at the frozen body

| requirement | where it lives today | where it belongs | could this package move it? |
|---|---|---|---|
| person in the reference still | `animation_generation_task.py:470-491` | `wan_animate`'s `ClientContract.requires` | **NO — frozen stage body.** The contract now declares it (§2.4); the stage still enforces its own copy. |
| a driving clip | `animation_generation_task.py:344-350` | same | **NO — same body** |
| video model chosen by clip length | `video_generation_task.py:224-232` | the binding, via the registry | **NO — frozen, and it reads no binding at all (§1.3)** |
| SadTalker fallback | `talking_head_task.py:354-382` | a registered client + a selection | **NO — frozen body** |
| ComfyUI client chosen by `if binding.stage ==` | `providers/image.py:31-51` | the registry | **YES, and it is not moved.** See below. |

**The one movable point was deliberately left alone.** `providers/image.py` is
unfrozen and the registry could replace its `if` today — but the callers of
`build_provider` are all inside frozen bodies, so rewiring it would change what
those bodies get back while they are frozen. The registry is proven equivalent
to it instead (§2.3), which is the state that makes the M3.3 swap a deletion
rather than a rewrite.

### 4.1 THE EXACT EDIT M3.3 WILL MAKE — `animation_generation_task.py`

Replace lines 470-491 with a contract consultation. The person check itself does
not move: `utils/person_detector.py` is unfrozen and stays exactly as it is.
What moves is **who decides that ABSENT is fatal**.

```python
# animation_generation_task.py, replacing :470-491
from shared.providers.client_registry import resolve_client
from shared.providers.contracts import SceneInput, SceneCapabilities, preflight

spec = resolve_client(binding)

if SceneInput.PERSON_IN_REFERENCE in spec.contract.requires:
    detection = PersonDetector().detect(reference_image)
    result.reference_person_check = detection.presence.value
    log.info("animation_reference_person_check", ...)      # unchanged
    if detection.presence is PersonPresence.ABSENT:
        caps = SceneCapabilities.of(
            SceneInput.PROMPT, SceneInput.REFERENCE_IMAGE, SceneInput.REFERENCE_CLIP,
            best_confidence=detection.best_confidence, model=detection.model,
        )
        raise WanAnimateInputError(preflight(spec.contract, caps).message)
    if detection.presence is PersonPresence.UNAVAILABLE:
        log.warning("animation_reference_person_check_unavailable", ...)  # unchanged
```

Two properties this preserves and one it gains:

* **Wan's behaviour is unchanged** — same detector, same threshold, same
  UNAVAILABLE handling, and the message still names the hallucination failure
  because the contract's help text carries that sentence verbatim.
* **The ~1.3 s detection still runs before the GPU reservation**, which is the
  whole reason it sits where it does (`:466-469`).
* **AnimateDiff stops paying for a check it does not need.** Today every
  animation scene runs person detection; with the contract consulted, a family
  that does not require a person skips it.

Ledgered as **WP-67 L-2**.

---

## 5. TASK 5 — the store learns which families IVGS can run

`GET /api/v1/models` now carries `client_status` beside WP-65's
`weight_status`, **kept separate on purpose**. Three states, three different
people:

| state | shown as | who fixes it |
|---|---|---|
| `no_client` | *no client — IVGS cannot run this model* | a **developer** |
| `no_host` (weight_status) | *no node hosts this engine* | an **operator** |
| `not_fetched` (weight_status) | *no fetch recorded by IVGS* | an **admin** |

The admin Models page gains a **Client** column and a Client block in the
expanded row showing the family, what the client needs from a scene, and the
action. WP-66's selection pickers honour it: a model with no client is visible,
disabled, and labelled, and `PUT /selections` refuses it with `reason="no_client"`.

**Merging `client_status` into `weight_status` was considered and rejected.** It
would put an operator back where WP-65 found them: one word standing for several
different jobs. Fetching weights cannot fix "no client", and writing code cannot
fix "no host".

### 5.1 What the live store says

Computed over all 18 live rows:

```
15 client_available     3 no_client
```

and all three are correct: `MimicMotion` (the family deliberately not
implemented), `test-model-1` (a retired test row), and `Kokoro` — a row whose
`engine` is `coqui` while its name says Kokoro, so `(voiceover_tts, coqui,
kokoro)` is genuinely unregistered. That last one is an engine/model mismatch in
the store, on a candidate/disabled row, and the refusal is honest about it.

**Two families were registered mid-package on live evidence.** `vllm_chat` and
`ffmpeg_concat` were initially absent, which made the surface say *"no client —
IVGS cannot run this model"* about the three Llama rows and about
`FFmpeg-composition` — the compositor that assembles every render. Saying that
about something demonstrably running is the same defect WP-66 §2.4 corrected,
and it was caught the same way: by asking the live store rather than the tests.

---
### 5.2 The two dimensions, live, after deploy

Computed inside `ivgs-fastapi` on `v5.26.0-clients`, over all 18 rows:

```
MODEL                     WEIGHTS             CLIENT            NEEDS FROM A SCENE
llama-3.3-70b-transcript  unknown_reference   client_available  prompt
llama-3.3-70b-storyboard  unknown_reference   client_available  prompt
test-model-1              no_reference        no_client         -
FLUX.1-dev                engine_only         client_available  prompt
flux1-schnell             unknown_reference   client_available  prompt
CogVideoX-5b              engine_only         client_available  prompt
Wan2.2-T2V                engine_only         client_available  prompt
AnimateDiff-SD15          engine_only         client_available  prompt
MimicMotion               engine_only         no_client         -
wan2.2-animate            not_fetched         client_available  person_in_reference,prompt,
                                                                reference_clip,reference_image
Wan2.2-Animate            engine_only         client_available  person_in_reference,prompt,
                                                                reference_clip,reference_image
Kokoro                    engine_only         no_client         -
kokoro-82m                unknown_reference   client_available  prompt
XTTS-v2                   engine_only         client_available  prompt
latentsync                engine_only         client_available  audio_track,reference_clip
latentsync-alt            no_reference        client_available  audio_track,reference_clip
FFmpeg-composition        engine_only         client_available  structured_scene_data
Llama-3.3-70B-Instruct    engine_only         client_available  prompt
```

**The two columns move independently, which is the whole argument for keeping
them apart.** `MimicMotion` and `AnimateDiff-SD15` have identical weight state
and opposite client state. `wan2.2-animate` and `Wan2.2-Animate` have identical
client state and different weight state. Neither column can be derived from the
other, and no single word could carry both.

And the rightmost column is the thing that did not exist before this package:
the two animation families are on the same engine, at the same stage, with
`prompt` against
`person_in_reference, prompt, reference_clip, reference_image`. A user can now
see, before selecting either, why they are not interchangeable.

---

## 6. WHAT THIS PACKAGE FOUND IN ITS PREDECESSORS

Two WP-65 defects, both surfaced by giving models a real family for the first
time, both fixed here rather than ledgered:

**(a) A host with no family map refused every named family.** `dest_for` refuses
a NAMED family a host has no convention for — correct, and the reason it exists
is that writing a 14B Wan bundle into node-04's `checkpoints` would put bytes
where a checkpoint loader will try to read them. But only node-03's Wan pack had
a map, so `flux` on node-04 was refused with *"declares no family conventions at
all"*: correct given the rule, and wrong about the fleet. Each host now declares
its own map, in one table (`_FAMILY_DESTS_BY_HOST`) rather than a conditional.

**(b) The registry answered "no client" for every ORM row.** A `ModelBinding`
carries plain strings; a `Model` row carries `ModelStage`/`ModelEngine` enum
members, and `str(ModelStage.IMAGE_GENERATION)` is `'ModelStage.IMAGE_GENERATION'`
— which nothing is registered under. Silent: every row would have reported "IVGS
cannot run this model", including the ones running. Normalised in `_key`, with a
test that asks the registry an ORM row directly.

Both were caught by tests failing, not by reading. Neither would have been
visible from WP-65's own suite, because WP-65 had no reason to ask a Model row
for a client.

---

## 7. TESTS

| file | tests | what it pins |
|---|---|---|
| `ivgs-api/tests/test_wp67_clients.py` | 34 | the registry's equivalence to today's routing (11 live models, parametrized); family derivation and its four fallbacks; the two resolution refusals; the capability contracts; pre-flight both ways on the same scene |
| `ivgs-workers/tests/test_wp67_animatediff.py` | 16 | the graph filled and every slot resolved; an unfillable slot refused; the motion module not parameterised; the contract enforced before a request; a ComfyUI without `ADE_*` refused with its own error |

**One assertion in my own new tests was wrong and is recorded**: a first draft
checked `"{" not in json.dumps(graph)` to prove no slot was left unfilled. A
JSON document is full of braces, so that assertion could never pass and
therefore never meant anything. It now asks `_unresolved_slots`, the walker the
Wan client already uses.

---

## 7b. THE NUMBERS, AND THE DEPLOY

```
.venv/bin/python -m pytest ivgs-api/tests
  1286 passed, 0 failed in 332.36s      baseline 1252 passed, 0 failed  -> +34, 0 failed

.venv/bin/python -m pytest ivgs-workers/tests
  18 failed, 903 passed, 48 skipped, 15 errors   baseline 887 passed, 18/48/15 -> +16, rows identical
```

The first package in this run to add a worker-tree test — because it added a
client, and clients live there.

**No migration.** The registry is code, and family is derived from
`default_params` plus name patterns precisely so that no data migration is
needed. Nothing in the database changed.

```
ivgs-fastapi              ghcr.io/brucecostello2/ivgs-api:v5.26.0-clients        Up (healthy)
ivgs-celery-default       ghcr.io/brucecostello2/ivgs-workers:v5.26.0-clients    Up (healthy)
ivgs-celery-composition   ghcr.io/brucecostello2/ivgs-workers:v5.26.0-clients    Up (healthy)
ivgs-celery-beat          ghcr.io/brucecostello2/ivgs-workers:v5.26.0-clients    Up (healthy)
ivgs-nextjs               ghcr.io/brucecostello2/ivgs-frontend:v5.26.0-clients   Up (healthy)
```

Artifacts banked with the standard filename. **Nodes 02/03/04 not touched**;
**no container or engine was stood up**, per this package's rules.

---

## 9. THE LEDGER

| id | what | why it is not closed here |
|---|---|---|
| **WP-67 L-1** | **`video_generation_task` never calls `get_binding`.** It picks its client from clip length (`:224-232`). WP-66's video-stage selection is therefore recorded, audited, and inert. | Frozen stage body. The edit is small — resolve the binding, `resolve_client(binding)`, drop `_select_model` — but it is stage internals. **Highest-value item in this ledger.** |
| **WP-67 L-2** | The person requirement is enforced by the stage, not by the contract that now declares it. | Frozen stage body. The exact edit is written out in §4.1. |
| **WP-67 L-3** | `providers/image.py`'s `if binding.stage ==` still routes ComfyUI, with the registry proven equivalent beside it. | Deliberate. Rewiring it changes what frozen bodies get back while they are frozen; the equivalence test makes the M3.3 swap a deletion. |
| **WP-67 L-4** | `talking_head`'s SadTalker fallback is inline at `:354-382` rather than a registered client and a selection. | Frozen stage body. |
| **WP-67 L-5** | `Kokoro` (candidate, disabled) carries `engine=coqui` while being a Kokoro model, so it resolves to no client. | A Model Store row correction, and WP-67's rules sanction no Model Store writes. WP-65's engine-name precedent covers the shape of the fix. |
| **WP-67 L-6** | AnimateDiff-SD15 cannot run anywhere on this fleet: no ComfyUI carries the `ADE_*` custom nodes. | Standing up an engine is an operator action, and this package's rules forbid standing up containers. Block A in §8. |

---

## 8. OPERATOR BLOCKS — authored, held, NOT RUN

### Block A — what AnimateDiff-SD15 would need to run live

**Not run, and not runnable by this package**: WP-67's rules say stand up no
containers and no engines. This records what the live pass needs, so it can be
decided rather than rediscovered.

Three things, in order, and the first is the one that surprises:

1. **An engine image with AnimateDiff-Evolved.** Probed 2026-08-26: node-04's
   ComfyUI answers `{}` for `/object_info/ADE_AnimateDiffLoaderGen1`, and
   node-03's Wan pack is a different image. This is **not** a weights problem
   and fetching weights will not fix it — the client says exactly that, by name.
2. **An SD-1.5 checkpoint on that host**, under `checkpoints`. WP-65's placement
   map now routes `animatediff -> checkpoints` on node-04.
3. **The model row corrected to a servable state.** It is `candidate` and
   disabled; WP-66 refuses a candidate at selection, correctly.

```bash
# ANY node, read-only. Does an engine here carry the AnimateDiff nodes?
for HOST in 192.168.1.93:8188 192.168.1.92:8220; do
  printf '%s -> ' "$HOST"
  curl -s --max-time 8 "http://$HOST/object_info/ADE_AnimateDiffLoaderGen1" \
    | head -c 40
  echo
done
```

Empty `{}` means the nodes are absent. Both answered `{}` on 2026-08-26.

### Block B — nodes 02 / 03 / 04, `v5.26.0-clients`

A workers rebuild IS required: `shared/providers/client_registry.py`,
`shared/providers/contracts.py`, `shared/weights/placement.py` and the new
`clients/animatediff_client.py` all ship in `ivgs-workers`.

```bash
# node-02 (192.168.1.91) and node-04 (192.168.1.93). celery-worker on both.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.26.0-clients.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node0X.yml \
      up -d --pull never --no-deps celery-worker
    sudo docker ps --format '{{.Names}} {{.Image}}' | grep celery
  fi
)
```

```bash
# node-03 (192.168.1.92) ONLY. THE SERVICE IS cogvideox-worker.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.26.0-clients.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node03.yml \
      up -d --pull never --no-deps cogvideox-worker
    sudo docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
  fi
)
```

---

## 10. PUSH BLOCK — count-gated, for WP-67's commits ONLY

```bash
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  EXPECTED=6          # WP-65's two, WP-66's two, WP-67's two
  AHEAD=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $AHEAD (expected $EXPECTED through WP-67)"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$AHEAD" -ne "$EXPECTED" ]; then
    echo "REFUSED: $AHEAD commits ahead, expected $EXPECTED."
    echo "If WP-68 has since committed, use the RUN SUMMARY's combined block."
  else
    echo "git push origin main    # <- run this line by hand"
  fi
)
```

| # | commit |
|---|---|
| 5 | `fix(wp-67): a selected model reaches the code that knows how to run it` |
| 6 | `docs(wp-67): report - the registry existed keyed on the wrong thing, and one stage never reads a binding` |
