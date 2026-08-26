# WP-68-MOTION — report, 2026-08-26

Tag **`v5.27.0-motion`**. Commits HELD, not pushed. Deployed to **node-01 only**.

**Headline: the cheap path the brief hoped for does not exist, and finding that
out uncovered something larger — RULE 1's standing promise has had one half
missing since v3. Nothing in this repository can draw a number.**

---

## S0. VERDICTS

| Task | Outcome |
|---|---|
| 1 — measure what exists | **DONE, and it changed the shape of the package.** §1. |
| 2 — the engine, declared honestly | **DONE.** No misleading default; WP-65's availability model extended with a *weightless* state. §2. |
| 3 — the templates | **DONE.** Four templates, deterministic, arithmetic-checked, frames banked. §3. |
| 4 — the storyboard learns to ask | **DONE and published** — v6 active, v1–v5 inactive. §4. |
| 5 — end-to-end proof | **PARTIAL, and named.** The renderer has no host; the exact stopping point is §5. |

**What this package does NOT claim.** No motion-graphics frame has reached a
draft, no renderer is deployed, and the Media Type dropdown deliberately does
not offer the new value. The brief's one prohibition — *"it must not end with a
surface claiming motion graphics work when no frame has ever been rendered"* —
is honoured by making every surface say what is actually true.

---

## 1. TASK 1 — what already exists, and why it reshaped this package

### 1.1 The cheap path was looked for and is not there

The brief said: *"If the compositor can already animate overlays, the cheapest
real teaching animation is an animated overlay over a still — and that would be
a far better first delivery than standing up Remotion. Report the finding and
take the cheaper path if it is genuinely available."*

**It is not available.** `drawtext` appears **nowhere** in this repository. The
compositor can do exactly two things with pixels it did not receive:

| capability | where | limit |
|---|---|---|
| overlay a PRE-RENDERED layer | `ffmpeg_client.py:480-517`, `:659-675` | fixed `x:y`, whole images only |
| burn SRT captions | `ffmpeg_client.py:524-531` | bottom-aligned (`Alignment=2, MarginV=40`), narration only |

It cannot place a digit at a position, and it certainly cannot move one between
columns. So the compositor route is closed, and this is recorded as a measured
finding rather than a preference.

### 1.2 `motion_graphics.py` — a Ken Burns service, and its caller is never built

618 lines. `apply_ken_burns` (`:160`) and `apply_zoom_pan` (`:303`), both
`zoompan` filtergraphs — camera moves over a still, not drawn content. The
brief said *"nothing calls it: zero hits across `ivgs-workers/tasks/`"*, which is
true; the precise statement is that its **only** callers are
`fallback_chain.py:667` and `:722`, and **`FallbackChain` is never constructed
outside tests**. Git history shows it last reached from `tasks/` in the Phase 1
and Phase 3 sprints.

Reusable for a slow push-in over a rendered frame. Not a way to draw numbers.

### 1.3 `remotion_client.py` — wired, and swallowing

540 lines, eight declared compositions (`LowerThird`, `TitleCard`,
`DataVisualization`, `KenBurns`, `AnimatedTitle`, `KeyTermOverlay`,
`ProgressBar`, `SceneTransition`), a health check, `list_compositions`, and a
batch path.

**It IS called** — `stage7_prototype_draft.py:219` and
`stage8_final_render.py:412` — which corrects the brief's implication that it is
orphaned. But only for **lower thirds**, gated on `enable_lower_thirds`, and:

```python
# stage7_prototype_draft.py:230-236
except Exception as e:
    logger.warning("lower_third_render_failed", scene_id=..., error=str(e))
    return None
```

**Every failure is swallowed.** With no Remotion container the render fails, the
warning is logged, `None` is returned, and the draft composes without the layer.
Nothing surfaces. Added to the standing register as **WP-00-SWALLOWED-FAILURES**
instance (§6).

**No test covers this client at all.**

### 1.4 THE FINDING THAT MATTERS MOST — RULE 1's promise has no keeper

The storyboard prompt has told the model since v3:

> *"Every equation, number, label and caption is rendered by the COMPOSITION
> OVERLAY in a later stage, with a real font. Describe only the imagery that
> sits beneath the overlay, and leave clear space where the overlay will go."*

and RULE 5 reserves *"the upper right third of the sheet kept clear for the
overlay"*.

**No stage draws those numbers.** The only text that reaches a rendered frame is
the narration, as bottom-aligned burned-in captions. The upper-right third is
kept clear for an overlay that is never composited.

RULE 1 is still *right* — an image model asked for "23 x 14" produced
"2? x 23.14", measured twice — but the bargain it offers has only ever had one
side. **These templates are the first thing in this repository that could keep
it**, and that is a larger justification for the package than the brief claimed.

### 1.5 Where an `animation` media type can route — one place, and unknowns are absorbed

`pipeline_orchestrator_v2.py:606-621` groups scenes into three lists and
dispatches them to three stages (`:653-655`). `animation` reaches
`animation_generation_task` on `gpu_animation` and nowhere else. **Anything
unrecognised falls into the image branch silently** — no log, no record.

So a fourth media type would have become a still with nothing saying so. §4.3
is what was done about that.

---

## 2. TASK 2 — the engine, declared honestly

### 2.1 An endpoint entry with NO default, deliberately

`shared/providers/binding.py` gains `motion_graphics ->
("IVGS_MOTION_GRAPHICS_URL", "")`. Every other row carries a default, and for a
hosted engine that is right. For an unhosted one it is actively harmful:

```
motion_graphics -> REFUSED: engine 'motion_graphics' resolved to an empty
                            endpoint (IVGS_MOTION_GRAPHICS_URL)
animatediff     -> http://node-04:8188      <- the misleading default, for contrast
```

`animatediff` silently resolves to node-04's **FLUX** ComfyUI, which cannot run
it and answers HTTP 400 — a failure WP-65 Task 1 measured as indistinguishable
from a malformed graph. An empty default raises `EndpointResolutionError` by
name instead.

### 2.2 WP-65's availability model gains a *weightless* state

The brief: *"a template-driven renderer has no weights, so WP-65's availability
model must be able to express 'this engine needs no weights' rather than
reporting it as permanently unfetched. If it cannot, extend it here."*

**It could not, and it now can.** WP-65 had two answers for a model with no
bytes — `not_fetched` and `engine_only` — and both imply bytes are a thing that
could exist. `WEIGHTLESS_ENGINES` names the two engines for which they never
will:

```
FFmpeg-composition    weightless    no weights needed
                      ffmpeg is a local binary invoked by the compositor…
maths-motion          weightless    no weights needed
                      a motion graphic is rendered from a template and its
                      parameters; there are no weights and there is nothing to fetch
```

Checked **first** in `compute_status`, because every other branch would give
such a model a wrong state. This is the fabricated-absence rule (WP-57/60)
applied one level along: reporting "not fetched" about something that was never
going to be present is an absence invented.

### 2.3 WP-67's registry gains the family and its contract

`maths_motion`, on stage `animation_generation`, engine `motion_graphics`,
**requiring `structured_scene_data`** — not a still, not a person, not a prompt.
That is the whole difference between it and the stage's other two families, and
WP-67's surface now shows all three side by side.

Registered under `animation_generation` rather than a new stage: the
orchestrator routes media types to three stages and a fourth would need a queue,
a worker and a task. The **family** is what separates it inside the stage it has.

---

## 3. TASK 3 — the templates, which are the actual product

### 3.1 Why they are a SPEC and not a renderer

Task 1 closed the compositor route, and Remotion has no host. Writing a React
project no test in this repo can execute would be the defect the brief forbids.
So a template is a **deterministic timeline of drawing operations**:

    parameters -> TemplateRender -> Frame[] -> DrawOp[]

renderer-agnostic (the same spec drives Remotion, an ffmpeg filtergraph, or the
local rasteriser), deterministic (same inputs, same bytes — asserted by hashing
two independent renders), provable without an engine, and honest.

### 3.2 The four

| template | parameters | what it shows |
|---|---|---|
| `place_value_split` | `number` | a two-digit number separates into tens and units and recombines — **the operator's second stated learning outcome, by name** |
| `column_addition_carry` | `top`, `bottom` | two rows sum; the carry appears above the next column **and travels there** |
| `column_multiplication_step` | `top`, `bottom`, `step` | ONE partial product, digit by digit, with its carry; `step` 1 writes its placeholder zero first |
| `highlight_and_hold` | `top`, `bottom`, `column`, `label` | the working with one column emphasised as the narration refers to it |

### 3.3 The arithmetic is checked — the one thing no gate here can catch

CLAUDE.md's trap table records it: the reference run's scene-5 narration teaches
`10x3=30, 10x2=20 => "320"` written as 230, and **no pipeline stage could catch
it, because every quality gate measures output-against-input**. A template
renders the arithmetic itself, so it can be checked once, for all parameters:

```
 27 + 15  = 42     23 + 14  = 37     5 + 5 = 10    99 + 1 = 100    12 + 34 = 46
 23 x 4 (step 0) = 92      23 x 1 (step 1) = 230      47 x 6 = 282
 47 x 2 (step 1) = 940     9 x 9 = 81
```

### 3.4 THREE DEFECTS FOUND BY LOOKING AT THE FRAMES

All three passed every assertion I had written and were caught by opening the
banked PNGs. Recorded because the lesson is the point: a digest over frames
proves reproducibility, not correctness.

**(a) The carry vanished after it travelled.** `column_addition_carry_0057.png`
showed the tens column highlighted with **no carry above it** — the 1 was drawn
only during its travel frames. A child adding that column is meant to *see* it
sitting there; an animation that removes it teaches the wrong thing more
convincingly than a still would. The carry now persists above the column it
landed on.

**(b) A leading zero.** The loop runs one column past the operands so a final
carry has somewhere to go; with no final carry that column's digit is 0, and
27 + 15 rendered as **"042"**.

**(c) The tens digit changed shape mid-animation.** `place_value_split`
travelled the *digit* "2" and then held the *value* "20". The concept being
taught is that the 2 in the tens column **means** 20; showing "2" while saying
so undermines it. It now travels "20" throughout — only `23`, `20` and `3` ever
appear.

### 3.5 Banked evidence

Twenty PNG frames at `dev/workpackages/reference/wp68-frames/`, five per
template, rendered by `shared/motion/raster.py` with a **pinned** font — a
renderer whose output depends on which fonts are installed is not deterministic,
so it refuses rather than substituting, and a test proves the refusal.

`column_addition_carry_0057.png` shows 27 + 15 with the units column done, the
carried **1** in red above the tens column, and the tens column highlighted.
`column_addition_carry_0114.png` shows the answer 42. `place_value_split_0064.png`
shows **20 tens / 3 units**.

---

## 4. TASK 4 — the storyboard learns to ask

### 4.1 A fourth media type, and why not a subtype

`motion_graphics`, migration **0041** (one enum label, no column). A subtype
would have put two incompatible input contracts behind one value the
orchestrator routes by, and WP-67's contracts state the difference exactly:

```
animation (wan_animate)  requires prompt, reference_image,
                                  person_in_reference, reference_clip
motion_graphics          requires structured_scene_data — no image, no person
```

**WP-64's D-2 person criterion STAYS for `animation`**, because Wan is still
Wan. v6 says in as many words that the two are not interchangeable: a person
demonstrating earns `animation`, numbers changing earn `motion_graphics`, and a
scene with no person can never be the former *however much it moves*.

### 4.2 RULE 8 — structured data, not prose

The structure lives in **`storyboard_scenes.generation_params`**, a JSONB column
that has existed since the table was created. The brief asked where it could go
"without a schema fight"; it already had somewhere.

RULE 8 names all four templates with their exact parameter names, and **scopes
RULE 1 rather than contradicting it**: the parameters *are* digits, and they are
**drawn, not generated** — the path that makes RULE 1 unnecessary rather than
merely enforced. The scene's `visual_description` is still written, still short
and still digit-free, because it is a caption and a record, not an instruction.

It also removes v4's now-false sentence *"There is no motion-graphics pathway in
this pipeline yet"*, which a test pins as gone.

### 4.3 What the orchestrator does with it — HOLDS IT BY NAME

`pipeline_orchestrator_v2.py` recognises `motion_graphics` and **does not
dispatch it**, logging `scene_media_type_held_no_renderer` with the scene ids
and the reason. The alternative was the existing silent `else`, which would have
made it an image with nothing saying so.

The same edit gives the `else` branch a warning of its own
(`scene_media_type_unrecognised_defaulted_to_image`), so the next unknown value
is not silent either.

### 4.4 The dropdown does NOT offer it

WP-64 removed a Media Type option advertising "Motion graphics via
Remotion/AnimateDiff" — a pathway that did not exist. Adding one back before a
renderer is deployed would be the same defect, so the prompt may choose the
value and the editor may not. `adaptation_service.MEDIA_TYPES` also stays at
three: *Adapt description* rewrites prose for a medium, and a motion graphic
does not take prose.

---
## 5. TASK 5 — end to end, and the exact point at which it stops

On a project this run created and deleted. The operator's project was untouched.
**No gate was pressed.**

### 5.1 Result: 9/9

```
1. THE NEW MEDIA TYPE PERSISTS, WITH ITS STRUCTURED PARAMS
  [PASS] motion_graphics scenes stored -- 2 of 4
  [PASS] generation_params round-trips as real JSON
         [{"template": "place_value_split", "number": 23},
          {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 0}]

3. THE TEMPLATES RENDER THESE SCENES' ACTUAL PARAMETERS
  [PASS] place_value_split           produces 128 frames (4.3s) from {'number': 23}
  [PASS] column_multiplication_step  produces  89 frames (3.0s) from
                                     {'top': 23, 'bottom': 14, 'step': 0}
  [PASS] the rasteriser REFUSES in-container without its pinned font

4. WHERE IT STOPS, EXACTLY
  [PASS] the motion_graphics engine resolves to NO endpoint, by design
         "engine 'motion_graphics' resolved to an empty endpoint (IVGS_MOTION_GRAPHICS_URL)"
  [PASS] a client IS registered for the family
         "Maths motion graphics needs ['structured_scene_data']"

5. CLEANUP (WP-59 flow)                       [PASS] the test project is deleted
```

Two halves ran on node-01 rather than inside the image, and the reason is
recorded rather than glossed:

* **The checker** imports `pytest`, which is not in the production image and
  should not be. Run against the **exact live payload** (printed by the
  in-container run so the two are demonstrably the same input): **2 findings,
  0 about motion**. Both are RULE 5 findings on visual descriptions I wrote by
  hand for this fixture, not WP-68 defects.
* **The rasteriser** refused in-container because its pinned font is not
  installed there — **which is the determinism guarantee working**, not a
  failure. It is a fixture harness, not the production renderer, and the
  production image has no business rendering. On node-01 both scenes rasterise:
  128 frames / 358 colours and 89 frames / 288 colours.

### 5.2 The stopping point, named

The templates render, the family has a registered client, the prompt asks for
it, and the scene stores its parameters. **What is missing is a deployed
renderer for the `motion_graphics` engine.** So the orchestrator holds those
scenes by name rather than dispatching them or silently turning them into
images, and `IVGS_MOTION_GRAPHICS_URL` resolves to nothing by design.

Standing a renderer up is an operator action, and this package's rules forbid
it. **WP-68 ledger L-1**, with the block at §8.

---

## 6. A SWALLOWED FAILURE, FOR THE STANDING REGISTER

Per CLAUDE.md §12, `WP-00-SWALLOWED-FAILURES` is a standing register and
instances are added as they are found.

**Instance: Remotion lower-third renders fail silently.**
`stage7_prototype_draft.py:230-236` and the same shape at
`stage8_final_render.py`: `except Exception` -> `logger.warning` -> `return
None`. With no Remotion container the render fails, `None` is returned, and the
draft composes without the layer. The job succeeds. Nothing surfaces to the
operator, and no test covers this client at all.

Not fixed here: the swallow is inside a frozen stage body (AD-05 §8), and both
call sites are in `stage7`/`stage8`. Recorded with its file:line so the register
carries it.

---

## 7. TESTS, AND THE ONE FAILURE THIS PACKAGE INTRODUCED

```
.venv/bin/python -m pytest ivgs-api/tests
  1359 passed, 0 failed in 319.61s     baseline 1286 passed, 0 failed  -> +73, 0 failed

.venv/bin/python -m pytest ivgs-workers/tests
  first run:  19 failed, 902 passed, 48 skipped, 15 errors   <- ONE NEW FAILURE
  after fix:  18 failed, 903 passed, 48 skipped, 15 errors   <- baseline, exactly
```

**The new failure is recorded rather than quietly re-run.**
`test_wp44_storyboard_prompt_rules.py::…::test_diagram_motion_maps_to_image`
asserted that the storyboard template contains the phrase *"motion-graphics"* —
a phrase that was only ever present inside v4's sentence **"There is no
motion-graphics pathway in this pipeline yet."** WP-68 built the pathway, so v6
says `motion_graphics` and routes those scenes to it, and the old assertion
would have required the prompt to describe a capability the system now has as
one it does not.

Renamed to `test_diagram_motion_does_not_map_to_animation` and **strengthened**:
it accepts any of the three spellings and still requires a destination to be
named, which may now be `image` OR `motion_graphics`. The rule it guards — that
non-person motion is never `animation` — is untouched.

**My first replacement for it was itself wrong**, and that is recorded too. It
demanded the phrase *"is not 'animation'"*, which `stage2_user.j2` has never
contained: that template states the same rule by **inclusion** rather than by
negation. Requiring the negation would have been imposing a wording the template
never had — a different thing from following a change. Two worker templates went
red and the assertion was corrected, not the templates.

### 7.1 Two worker templates corrected on a point of fact

`prompts/stage2_system.j2` and `prompts/stage2_user.j2` both said *"there is no
motion-graphics pathway in this pipeline"*, which this package made false; and
`stage2_user.j2` added that such motion *"belongs to the composition overlay on
top of a still"*, which §1.1 measured as impossible. Both now say a pathway
exists, that no renderer is deployed for it, and that these scenes therefore
stay `"image"` for now. **The routing they teach is unchanged** — only the
factual claim about why.

### 7.2 The test files

| file | tests | what it pins |
|---|---|---|
| `test_wp68_motion.py` | 50 | the four templates exist and declare their parameters; determinism over PIXELS; the pinned font refusing rather than substituting; **the arithmetic**, across parameters, for addition and every multiplication step; the carry travelling AND persisting; digits drawn as exact text; the rasteriser producing a non-blank picture whose frames differ |
| `test_wp68_prompt_v6.py` | 23 | v6's criterion and RULE 8; all four templates named and **no template named that does not exist**; RULE 1 scoped rather than contradicted; the checker's six motion findings red-green; and that the fourth media value exists in the ORM, the schema, the Python enum and the checker — the four places migration 0041 had to reach |

---

## 9. THE LEDGER

| id | what | why it is not closed here |
|---|---|---|
| **WP-68 L-1** | No renderer is deployed for the `motion_graphics` engine, so no motion-graphics frame has reached a draft. | Standing up a container is an operator action and this package's rules forbid it. The templates, the engine row, the client contract, the prompt and the checker are all in place and proven; the block is §8. |
| **WP-68 L-2** | RULE 1 has promised since v3 that "the composition overlay renders the numbers in a real font", and **nothing draws them**. The only text on a rendered frame is bottom-aligned narration captions. | Closing it means a renderer (L-1). The templates are the first thing in the repo that could keep the promise. **The largest finding in this package.** |
| **WP-68 L-3** | Remotion lower-third failures are swallowed at `stage7_prototype_draft.py:230-236`. | Frozen stage body. Added to the standing swallow register (§6). |
| **WP-68 L-4** | `motion_graphics` scenes are HELD, not dispatched. A project containing one gets a storyboard it cannot fully render. | Deliberate, and better than the alternative: the previous `else` branch absorbed unknown media types into the image branch silently. Holding says the true thing. |
| **WP-68 L-5** | `services/motion_graphics.py` (618 lines) remains reachable only from `FallbackChain`, which is never constructed. Its Ken Burns work is reusable for a slow push-in over a rendered frame. | Wiring `FallbackChain` is AD-05's own listed work ("its L1-L4 strategy selection is domain logic and must be extracted and wired in regardless of engine choice"). |
| **WP-68 L-6** | The Media Type dropdown does not offer `motion_graphics`, so only the storyboard model can choose it. | Deliberate until a renderer exists — WP-64 removed a dropdown option advertising a pathway that did not exist, and adding one back early would be the same defect. |

---

## 7b. WHAT WAS DEPLOYED

Migration **0041** applied to live `ivgs` (`0040 -> 0041`); `media_type` now
reads `image, video_clip, animation, motion_graphics`.

```
ivgs-fastapi              ghcr.io/brucecostello2/ivgs-api:v5.27.0-motion        Up (healthy)
ivgs-celery-default       ghcr.io/brucecostello2/ivgs-workers:v5.27.0-motion    Up (healthy)
ivgs-celery-composition   ghcr.io/brucecostello2/ivgs-workers:v5.27.0-motion    Up (healthy)
ivgs-celery-beat          ghcr.io/brucecostello2/ivgs-workers:v5.27.0-motion    Up (healthy)
ivgs-nextjs               ghcr.io/brucecostello2/ivgs-frontend:v5.27.0-motion   Up (healthy)
```

### The publish — v6 active, and the idempotency guard proved

```
contract : OK (RULE 0, RULE 2, RULE 5, RULE 6, RULE 7 and RULE 8 present,
               RULE 1 intact, WP-65 v5 and WP-68 v6 amendments present,
               4 motion templates all served)

  v1 False   v2 False   v3 False   v4 False   v5 False   v6 active=True
  726af31f-80f1-4224-83cd-b133a62406f7   20616 chars
```

A second invocation refused, which is worth recording as evidence rather than
noise: *"The active prompt is ALREADY this exact text. Nothing to do; a second
run must not create a version that differs by nothing."*

**Nodes 02/03/04 not touched. No container was stood up.**

---

## 8. OPERATOR BLOCKS — authored, held, NOT RUN

### Block A — what a motion-graphics renderer needs

**Not run. This package's rules say stand up no containers.** Three decisions,
in order:

1. **Choose the renderer.** The templates are renderer-agnostic by design —
   `TemplateRender` is a list of `DrawOp`s, and `shared/motion/raster.py` is the
   reference implementation of what those ops mean. Remotion is the candidate
   that already has a client and two call sites; an ffmpeg filtergraph or a
   headless Pillow service would also satisfy the spec.
2. **Set `IVGS_MOTION_GRAPHICS_URL`** on the node that hosts it. Until then the
   engine resolves to nothing, by design, and says so by name.
3. **Register a Model Store row** for the family so it can be selected —
   `engine=motion_graphics`, and WP-68 makes the store report it as
   *weightless* rather than permanently unfetched.

```bash
# node-01, read-only. What the fleet says about motion graphics today.
sudo docker exec -e PYTHONPATH=/app -w /app ivgs-fastapi python - <<'PY' | tr -cd '\11\12\15\40-\176'
from shared.providers.binding import resolve_endpoint
from shared.providers.errors import EndpointResolutionError
from shared.providers.client_registry import resolve_client
from shared.weights.placement import WEIGHTLESS_ENGINES, UNHOSTED_ENGINES

try:
    print("endpoint:", resolve_endpoint("motion_graphics"))
except EndpointResolutionError as e:
    print("endpoint: REFUSED --", e)
print("weightless:", WEIGHTLESS_ENGINES.get("motion_graphics"))
print("unhosted  :", UNHOSTED_ENGINES.get("motion_graphics"))
PY
```

### Block B — see the templates, without deploying anything

The banked frames are committed at
`dev/workpackages/reference/wp68-frames/` (20 PNGs). To render more, or other
numbers, on node-01:

```bash
.venv/bin/python - <<'PY'
import sys; sys.path[:0]=['.']
from shared.motion.templates import render, template_names
from shared.motion.raster import bank_frames
print("templates:", template_names())
r = render("column_addition_carry", top=48, bottom=37)      # any numbers
print(bank_frames(r, "/tmp/wp68-preview"))
PY
```

### Block C — nodes 02 / 03 / 04, `v5.27.0-motion`

A workers rebuild IS required: `shared/motion/`, `shared/providers/binding.py`,
`shared/weights/placement.py`, `shared/models/enums.py` and
`tasks/pipeline_orchestrator_v2.py` all ship in `ivgs-workers`.

```bash
# node-02 (192.168.1.91) and node-04 (192.168.1.93). celery-worker on both.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.27.0-motion.tar.zst
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
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.27.0-motion.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node03.yml \
      up -d --pull never --no-deps cogvideox-worker
    sudo docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
  fi
)
```

**Migration 0041 must be applied before these workers start**, because
`shared/models/enums.py` declares the fourth label and a worker reading a scene
row would otherwise raise `LookupError`. It is already applied on node-01's
database, which is the only one.
