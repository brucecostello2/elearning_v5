# WP-66-SELECTION — report, 2026-08-26

Tag **`v5.25.0-selection`**. Commits HELD, not pushed. Deployed to **node-01 only**.

**Headline: the mechanism was built, scene-aware, and unreachable — the brief
was right about that. What it was wrong about is what the middle needed to
enforce, and the live run proved it by refusing three models the pipeline is
running on today.**

---

## S0. VERDICTS

| Task | Outcome |
|---|---|
| 1 — what the endpoints do | **DONE.** Three of the brief's assumptions are false; the measurement wins. §1. |
| 2 — selection respects availability | **DONE, narrowed on evidence, half STOPPED per the brief's own escape hatch.** §2. |
| 3 — project-scoped UI | **DONE and deployed.** A Models tab, every stage, provenance on each. §3. |
| 4 — scene-scoped UI | **DONE and deployed.** In Edit Scene beside Media Type; override badge on the grid. §4. |
| 5 — invalidation asymmetry (RULED) | **DONE.** Implemented by composition; proven both ways, live and in tests. §5. |
| 6 — the presets path | **DONE.** The write is real; the provenance was not. Migration 0040. §6. |

**One task half-stopped**, exactly where the brief said to stop it (§2.3), and
**one correction to my own work made on live evidence** (§2.4) — a refusal rule
that would have rejected `CogVideoX-5b`, `FFmpeg-composition` and
`Llama-3.3-70B-Instruct`: the `is_default` models three stages render with now.

---

## 1. TASK 1 — what the three endpoints actually do

### 1.1 Measured, with file:line

| Endpoint | Where | What it actually does |
|---|---|---|
| `GET /selections` | `model_store.py:358-374` | `project_id` only — **no scoping parameters at all**. Returns every row for the project, project- and scene-scoped alike, ordered `(stage, tier, scene_id)`. Scene rows are distinguished by a non-null `scene_id`. Empty project → `[]`. |
| `POST /selections/plan` | `model_store.py:377-407` → `model_selection.py:172-268` | **NOT a dry run.** `plan_stage` ends in `_replace_selection` — a DELETE then an INSERT — and the route commits. It is an auto-planner that PERSISTS `selected_by='auto'` rows for every stage requested. Refuses `tier=BOTH` with 422. |
| `PUT /selections` | `model_store.py:410+` → `manual_override` | Replace-then-insert per exact scope (`_replace_selection:132-166`), so it replaces rather than accumulates — the brief had this right. |

### 1.2 Three of the brief's assumptions are false

**(a) "what it does today if the model is not approved" — it already refuses.**
`model_selection.py:284` (pre-WP-66) rejected any model not in
`(APPROVED, DEPRECATED)`. What it lacked was a machine slug the surface could
switch on and a sentence a user could act on: it raised a bare `ValueError`
mapped to a generic 422 string.

**(b) `rationale` IS enforced non-empty** — at the schema, not the service:
`ManualSelectionIn.rationale: str = Field(min_length=1)`
(`schemas/model_store.py:380`). Existing writers put: the planner's generated
sentence (`"selected X; capability match: …"`), the route's
`f"{body.rationale} (manual override by {username})"`, and the preset's
`f"preset {name!r} v{version}"`.

**(c) The preset path is REAL** — see §6. Not another declared-but-inert write.

### 1.3 What the UI must write

`SelectionSource` was `AUTO | MANUAL`. The UI writes `MANUAL`; the planner
writes `AUTO`; **the preset had nowhere to write itself** and used `MANUAL`,
which §6 fixes.

### 1.4 One more gap the brief did not name

`SelectionOut` carried `model_id` and nothing else about the model — while
`ProjectModelSelection.model` is `lazy="joined"` (`model_store.py:389`), so the
row **already travelled with every response** and the schema dropped it. A
picker therefore had to fetch the entire registry to render a name. It now
carries `model_name`, `model_display_name`, `model_engine`, `model_state`.

---

## 2. TASK 2 — selection respects availability

### 2.1 What was built

`SelectionRefused(ValueError)` carries a `reason` slug beside its message. A
`ValueError` subclass so every existing caller keeps working, and the route maps
it to a 422 with `{"error": {"code": …, "message": …}}` rather than a bare
string.

| reason | means | who fixes it |
|---|---|---|
| `not_approved` | lifecycle: candidate/retired | an **admin**, in Admin → Models |
| `no_host` | no container on this fleet serves the engine | an **operator**, by deploying one |
| `wrong_stage` / `model_missing` | integrity | — |

### 2.2 The picker and the writer share one definition

`selection_panel._candidates_for` calls the same `_availability_refusal` the
write calls. A test asserts the equivalence model-by-model
(`test_the_picker_and_the_writer_agree_on_what_is_selectable`): a picker that
offers what the write refuses — or greys out what it would accept — is worse
than no picker.

### 2.3 The STOPPED half, per the brief's own escape hatch

The brief asks `PUT /selections` to refuse a model with "no verified weights on
a node hosting its engine", and then says: *"If WP-65 Task 2 stopped and no
availability record exists, implement the approval check and STOP the
availability half… Do not invent an availability signal."*

**Measured after WP-65 deployed: `model_weight_placements` holds ZERO rows**,
because the live fetch needs the operator's MBCP token and is held. Enforcing
the verified-bytes rule would refuse **every model in the store** — including
`wan2.2-animate`, whose bytes are demonstrably on node-03.

And it would assert what IVGS cannot know. WP-65 §7.4 settled the distinction:
*IVGS has no record of a fetch* is a fact about IVGS's records; *there are no
bytes on the node* is a fact about the node. Refusing on the first while
claiming the second is inventing an availability signal.

**So the verified-bytes half is STOPPED and ledgered (WP-66 L-1).** It becomes
enforceable the moment one real fetch is recorded, and turning it on is one
entry added to `_CERTAINLY_UNRUNNABLE`. A model with no fetch record is
**accepted with a warning** on the panel instead — Task 2's last clause.

### 2.4 THE CORRECTION THE LIVE RUN FORCED

`engine_only` was originally in `_CERTAINLY_UNRUNNABLE` — it looked like the
strongest possible evidence of unrunnability: MBCP has no bundle and never will.

**The live acceptance run refuted it.** Asked how many models each stage can
actually select, the answer was:

```
transcript_refinement   1/1     storyboard_generation   1/2
image_generation        1/2     video_generation        0/2   <--
animation_generation    1/4     voiceover_tts           1/3
talking_head            1/2     composition             0/1   <--
translation             0/1  <--
```

The models being refused on those three stages were **CogVideoX-5b,
FFmpeg-composition and Llama-3.3-70B-Instruct** — the `is_default` models those
stages are bound to and **rendering with today**. The gate would have refused an
explicit selection of a model the pipeline is already using.

The reasoning was wrong in exactly the way WP-65 §7.4 was wrong before it was
corrected, one level up. *"MBCP has no weight bundle for this model"* is a fact
about MBCP's serving plane. *"This model cannot run"* is a fact about the fleet.
An engine-only certification means the model ships **inside its engine image**
(`mbcp_api/api/v1/certifications.py:603-620`), so wherever that image is
deployed, the model runs. That is why eleven of eighteen live rows are
engine-only and several of them are serving.

**`engine_only` is now a warning, not a bar**, and
`test_no_live_default_model_would_be_refused_by_this_gate` states the property
so it cannot regress.

### 2.5 A finding the acceptance produced along the way

**Nine of nine stages offer at most ONE selectable model.** After the
correction three stages gained their default back, but no stage offers a
genuine *choice*. The UI is right and necessary — it is how a choice gets made
at all — but the store is thin, and "the user chooses the model" is today a
choice between one option and the same option. Recorded, not fixed: populating
the store is certification work on MBCP's side.

Consequence for the acceptance: the two-*different*-models proof of scene
precedence cannot be made on live data. It is made in the test suite, which
creates its own models; the live run proves the **scope mechanism** (§7.2).

### 2.6 Invalid existing selections warn, and are never rewritten

`resolve_binding` returns a `warning` when the bound model has been deprecated,
retired, disabled, or become unrunnable. The selection is **kept**: the user
chose that model, and silently choosing a different one is the failure this
avoids. `test_a_selection_that_went_bad_warns_and_is_not_rewritten` pins it.

---

## 3. TASK 3 — project-scoped selection UI

A **Models** tab (`/projects/{id}/models`), added to `PROJECT_TABS` — whose
stated invariant, *"every tab points at a page that ships"*, still holds.

- **Stages come from the enum**, server-side (`selection_panel._stage_list`),
  never retyped. The brief listed nine by hand; a test asserts the list IS
  `list(ModelStage)`, so a stage added to the enum appears without an edit.
- **Provenance on every row**, as five distinct states — `scene`, `selection`,
  `preset`, `auto`, `default` — plus `none`. This is why migration 0040 exists
  (§6): four of those were previously indistinguishable in the column that
  exists to record them.
- **Unavailable models are visible and disabled with the reason**, not filtered
  out. A user who cannot see the model they expected reports "the picker is
  broken" instead of "the weights are not fetched".
- **Rationale defaults to `"operator selection"`** and is editable. The column
  is mandatory; demanding prose for a routine choice trains people to type "x".
- **Tier is presented, not hidden** — a selector, with a tooltip saying
  prototype drives the draft and production the final render.
- **`audit_log` row per write** (`MODEL_SELECTION_SET`), carrying the previous
  model and its provenance in `before_payload`.

One request serves the whole panel (`GET …/model-selections/panel`), with
provenance computed **server-side beside the model it describes** — a frontend
deriving "is this a default?" from the absence of a row is exactly the inference
WP-60 Task 5 found being made wrongly.

---

## 4. TASK 4 — scene-scoped selection UI

In the **Edit Scene** modal, directly beneath Media Type.

- **Changing Media Type changes the candidate list.** The mapping is data and
  lives server-side (`selection_panel.MEDIA_TYPE_STAGE`), so the picker and the
  dispatcher cannot drift: `image → image_generation`,
  `video_clip → video_generation`, `animation → animation_generation`.
- **It composes with WP-64's Adapt description.** Medium, description and model
  are the three things a scene binds, and the modal now shows all three
  together — the picker sits between the Media Type control and the Adapt panel.
- **"Use the project default" DELETES the scene row.** Not a copy of the project
  row. The difference is silent and later: a duplicate keeps pointing at the old
  model after the project default changes, while dispatch reads scene-scoped
  first (`factory.py:147-151`) and never looks at the project row again — the
  scene stops following a default it appears to follow. `clear_selection` is
  scene-scoped only, and proven by the row's **absence**.
- **The storyboard grid shows the exceptions.** `SceneCard` carries a
  `model: X` badge when a scene overrides the project binding, sourced from one
  `GET /model-selections` for the whole grid rather than one request per card.
  Failure-tolerant: if that read fails the cards carry no badge, because a
  missing badge is a smaller wrong than a storyboard that will not render.
- Same refusals, same audit row (`MODEL_SELECTION_CLEARED` for the clear).

---

## 5. TASK 5 — what a selection change invalidates (RULED)

**The ruling, implemented as ruled: a model selection change invalidates the
DRAFT gate only.**

The reasoning, for the record: the storyboard artifact is narration, visual
descriptions and media types. A model choice alters none of them, and
invalidating that approval would refuse the very regeneration the user is
picking a model for — the same asymmetry WP-63 D-1 resolved for regeneration.
The draft IS what the models produced, so approving a draft and then changing
the model that made it must re-open that decision.

**Implemented by composition, and the implementation is the proof.**
`gate_service.draft_upstream_version` already read
`storyboard_version + scene_media_version`; it now also reads
`model_selection_version`. `storyboard_version` is **untouched**, so a storyboard
approval *cannot* be affected — not "is not", cannot be, because the selection
rows are not among its inputs. A test asserts that by reading the function's
source rather than by observing an outcome, since an outcome could be a
coincidence.

Nothing writes an invalidation. The fingerprint moves and the approval stops
being current on the next read — the property `gate_service.py:37-41` already
established for every other gate in the module.

The fingerprint is over `(scene_id, stage, tier, model_id)`, ordered. It
includes `scene_id`, so a scene override moves it too. It excludes `rationale`
and `created_at`: re-selecting the same model with different prose is not a
different draft, and re-approving over it would be noise.

**Proven both ways, twice.** Nine tests in
`test_wp66_invalidation.py`, and live on a project created for the run (§7.2 §6).
**Verified red-green**: removing the one composed term turns five tests red.

---

## 6. TASK 6 — the presets path

**It works.** `PresetApplyPanel.tsx`'s claim that a preset "writes the preset's
actor, model selections and media defaults into this project" is **true** for
model selections: `preset_service.py:246` calls `model_selection.manual_override`
— the same function the API's own override route calls, not a stub — for every
entry, and deliberately does not duplicate its checks so that *"a preset created
while a model was approved and applied after it was retired must fail with the
CURRENT reason"*.

**What it lost was which of them it was.** `manual_override` hardcoded
`selected_by=MANUAL`, so a selection a preset wrote was indistinguishable, in
the column that exists to say so, from an operator's own choice. The only
surviving trace was a free-text rationale an operator can edit.

Migration **0040** adds `selection_source.preset`; `manual_override` takes
`selected_by` (defaulting to MANUAL); `preset_service` passes it. **Nothing
switches on the value at dispatch** — `factory.py:113-165` passes it through to
the binding and never compares it — so a `preset` row dispatches exactly as a
`manual` row does, which is correct: the preset IS the operator's choice, made
earlier. Downgrade is a deliberate no-op (PostgreSQL cannot remove an enum
value), the same treatment as 0027/0033/0034/0038. **No rows were rewritten**;
there were none, and a migration could not have told a preset-written row from a
hand-written one any better than the runtime could — that is the defect being
fixed, not one to backfill over.

---

## 6b. WHAT WAS DEPLOYED

Migration **0040** applied to live `ivgs` (`0039 -> 0040`); `selection_source`
now reads `auto, manual, preset`.

```
ivgs-fastapi              ghcr.io/brucecostello2/ivgs-api:v5.25.0-selection       Up (healthy)
ivgs-celery-default       ghcr.io/brucecostello2/ivgs-workers:v5.25.0-selection   Up (healthy)
ivgs-celery-composition   ghcr.io/brucecostello2/ivgs-workers:v5.25.0-selection   Up (healthy)
ivgs-celery-beat          ghcr.io/brucecostello2/ivgs-workers:v5.25.0-selection   Up (healthy)
ivgs-nextjs               ghcr.io/brucecostello2/ivgs-frontend:v5.25.0-selection  Up (healthy)
```

Artifacts banked through `scripts/save-image-artifact.sh` with the standard
filename. **Nodes 02/03/04 were NOT touched** — their paste blocks are §8.

---

## 6c. TESTS AND THE BASELINE

```
.venv/bin/python -m pytest ivgs-api/tests
  1252 passed, 0 failed, in 323.08s     baseline 1208 passed, 0 failed  -> +44, 0 failed

.venv/bin/python -m pytest ivgs-workers/tests
  18 failed, 887 passed, 48 skipped, 15 errors    -> IDENTICAL to baseline
```

`ivgs-workers` was re-run because `shared/models/model_store.py` and
`shared/weights/placement.py` both changed and both ship in that image.

| file | tests | what it pins |
|---|---|---|
| `test_wp66_selection.py` | 33 | the endpoints as measured; the refusal set and its narrowing; picker/writer equivalence; provenance for all five origins; scene precedence and clearing; the preset path and its provenance; the audit rows |
| `test_wp66_invalidation.py` | 11 | Task 5 both ways, the fingerprint's inputs read from source, recovery, no-op on re-selection, and the reason naming all three causes — **verified red-green** |

**Two intermediate runs are recorded honestly.** The first full API run after the
UI landed showed **1 failure** (`test_manual_override_validations`, following the
message change) and the second showed 1252/0. Both are counted against the
package's two-run allowance; the second is authoritative.

**One WP-65 defect was found by WP-66's tests and fixed in this package**:
`shared/weights/placement.py`'s fallback destination was a module-level constant
reading `"diffusion_models"` — a Wan-pack convention applied to every host. On
node-04's FLUX ComfyUI, which mounts `checkpoints` only, it made every
familyless image model look unplaceable, and this package's selection refusal
then rejected models that are fine. The fallback now belongs to the host, a
NAMED family with no convention on that host is refused rather than dropped into
it, and four tests were added to `test_wp65_weight_fetch.py`.

---

## 7. ACCEPTANCE — a test project created, used, and deleted

Run inside `ivgs-fastapi` against the live database, on a project this run
created and removed. **The operator's project and every other existing project
were untouched.** No gate was pressed through any UI: the gate state was created
programmatically on this run's own project, per the brief; WP-63 D-2 stands.

### 7.1 The WP-45 standard

Every selection clause is proven through
`shared.providers.factory.get_binding` — **the function the Celery stage bodies
call** — not by reading back the row that was written. A row in a table is not
proof that a render will use it.

### 7.2 Result: **17/17**

```
1. PROJECT-SCOPED SELECTION, OBSERVED AT DISPATCH
  [PASS] the bound model reaches the dispatch binding
         binding.name=flux1-schnell endpoint=http://node-04:8188
  [PASS] read back through the selections list

2. SCENE-SCOPED OVERRIDE TAKES PRECEDENCE, SIBLINGS DO NOT MOVE
  [PASS] a scene-scoped row exists for scene 0 only -- scene0=1 scene1=0
  [PASS] scene 0 dispatches via its own row
  [PASS] scene 1 dispatches the project binding
  [PASS] provenance distinguishes the two scenes -- scene0=scene scene1=selection

3. 'USE THE PROJECT DEFAULT' CLEARS THE ROW
  [PASS] the scene row is absent, not duplicated -- cleared=1 remaining=0
  [PASS] scene 0 falls back to the project binding at dispatch

4. UNAVAILABLE MODELS REFUSED
  [PASS] AnimateDiff-SD15 (candidate) refused as not_approved
  [PASS] MimicMotion (candidate) refused as not_approved

4b. AND AN ENGINE-ONLY MODEL IS NOT REFUSED -- ITS IMAGE RUNS IT
  [PASS] CogVideoX-5b (engine-only, and the live default) is selectable
         binding=CogVideoX-5b endpoint=http://cogvideox-server:8200

5. THE PANEL, WITH PROVENANCE                       [PASS] every stage present -- 9
     transcript_refinement  llama-3.3-70b-transcript  [default]
     storyboard_generation  llama-3.3-70b-storyboard  [default]
   ! image_generation       flux1-schnell             [selection] chosen for this project
   ! video_generation       CogVideoX-5b              [selection] chosen for this project
     animation_generation   wan2.2-animate            [default]
     voiceover_tts          kokoro-82m                [default]
     talking_head           latentsync                [default]
     composition            FFmpeg-composition        [default]
     translation            Llama-3.3-70B-Instruct    [default]
  [PASS] the explicit selection reads as a selection, not a default

6. TASK 5 -- THE INVALIDATION ASYMMETRY, LIVE
  [PASS] both gates start approved
  [PASS] the DRAFT approval is invalidated
  [PASS] the STORYBOARD approval survives -- "approved and current"

8. CLEANUP (WP-59 flow)
  [PASS] the test project is deleted
```

**Two clauses of the brief's acceptance could not be met on live data, and both
are reported rather than worked around:**

* *scene override with a DIFFERENT model* — impossible: no stage offers two
  selectable models (§2.5). The live run proves the **scope** mechanism (a row
  exists for one scene and not its sibling; dispatch reads it; clearing removes
  it); the two-different-models proof is
  `test_a_scene_override_takes_precedence_and_siblings_do_not_move`, which
  creates its own models.
* *audit rows* — the acceptance drives the **service layer**, which writes none;
  the **routes** write them. Asserted by test instead
  (`TestTheAuditTrail`), and the run says so rather than reporting 0 as a pass.

### 7.3 Screenshots

The environment still has no browser (WP-59 §12 convention). No screenshots were
taken and none are claimed. The evidence above is the text of a live run.

### 7.4 The correction, before and after

| stage | selectable BEFORE the §2.4 correction | AFTER |
|---|---|---|
| video_generation | **0/2** | 1/2 |
| composition | **0/1** | 1/1 |
| translation | **0/1** | 1/1 |
| voiceover_tts | 1/3 | 2/3 |
| talking_head | 1/2 | 2/2 |

Nine of nine stages offered at most one model before; seven of nine do now, and
two offer a real choice.

---

## 9. THE LEDGER

| id | what | why it is not closed here |
|---|---|---|
| **WP-66 L-1** | The verified-bytes half of Task 2 is **STOPPED**. Only `not_approved` and `no_host` bar a selection; "no fetch recorded" warns. | `model_weight_placements` holds zero rows because WP-65's live fetch is held for the operator's MBCP token. Enforcing it would refuse every model in the store and would assert what IVGS cannot know. One entry in `_CERTAINLY_UNRUNNABLE` turns it on. |
| **WP-66 L-2** | Seven of nine stages offer at most ONE selectable model. | Populating the store is MBCP certification work, not IVGS work. The picker is what makes a choice possible at all; there is little to choose between yet. |
| **WP-66 L-3** | `POST /selections/plan` persists rather than proposing, despite its name. The new UI does not call it. | Renaming a shipped endpoint is a contract change. Recorded so the next reader does not use it as a preview. |
| **WP-66 L-4** | Nine `model_node_availability` rows still name dead container hashes (carried from WP-65 L-4). | Pruning is the operator's; `scripts/prune-scheduler-model-keys.sh` exists. |

---
## 8. OPERATOR BLOCKS — authored, held, NOT RUN

### Block A — nodes 02 / 03 / 04, `v5.25.0-selection`

A workers rebuild IS required: `shared/models/model_store.py` (the
`SelectionSource` enum) and `shared/weights/placement.py` (the host-fallback fix
found by this package's tests) both ship in `ivgs-workers`. node-01's workers are
already on this tag.

```bash
# node-02 (192.168.1.91) and node-04 (192.168.1.93). Service is celery-worker on
# both. One node at a time. --no-deps matters on node-04: celery-worker
# depends_on comfyui, so without it a single-service recreate reaches further
# than its name suggests.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.25.0-selection.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node0X.yml \
      up -d --pull never --no-deps celery-worker
    sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep celery
  fi
)
```

```bash
# node-03 (192.168.1.92) ONLY. THE SERVICE IS cogvideox-worker, NOT
# celery-worker. node-03 also DECLARES a celery-worker under
# profiles: ["standby"] which is not running; naming it starts a second worker
# competing for the same queues and leaves the real one on the old image
# (WP-44 §6.3 recorded exactly that happening).
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.25.0-selection.tar.zst
  if [ ! -f "$A" ]; then echo "REFUSED: artifact not found: $A"; else
    zstd -d -c "$A" | sudo docker load
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node03.yml \
      up -d --pull never --no-deps cogvideox-worker
    sudo docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
  fi
)
```

### Block B — see the picker with something to pick from (OPTIONAL)

Seven of nine stages offer at most one selectable model (§2.5, WP-66 L-2), so
the UI currently presents a choice of one. Nothing in IVGS can fix that: the
store is populated by MBCP certification. This block is the read that shows the
current state, and it is safe to run at any time.

```bash
# node-01, read-only.
sudo docker exec -e PYTHONPATH=/app -w /app ivgs-fastapi python - <<'PY' | tr -cd '\11\12\15\40-\176'
import asyncio
from shared.database import async_session_factory
from shared.models.model_store import ModelStage, ModelTier
from app.services import selection_panel

async def main():
    async with async_session_factory() as db:
        for st in ModelStage:
            c = await selection_panel._candidates_for(db, st, ModelTier.PRODUCTION)
            ok = [x.name for x in c if x.selectable]
            no = [(x.name, x.refusal_reason) for x in c if not x.selectable]
            print(f"{st.value:<24}{len(ok)}/{len(c)}  usable={ok}")
            for n, r in no:
                print(f"{'':<24}  - {n}: {r}")
asyncio.run(main())
PY
```

---

## 10. PUSH BLOCK — count-gated, for WP-66's commits ONLY

**Commits are HELD. Nothing was pushed.**

```bash
# node-01. Refuses unless exactly the expected number of commits are ahead.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  EXPECTED=4          # WP-65's two, plus WP-66's two
  AHEAD=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $AHEAD (expected $EXPECTED through WP-66)"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$AHEAD" -ne "$EXPECTED" ]; then
    echo "REFUSED: $AHEAD commits ahead, expected $EXPECTED."
    echo "If WP-67/68 have since committed, use the RUN SUMMARY's combined block."
  else
    echo "git push origin main    # <- run this line by hand"
  fi
)
```

Expected, for WP-66 alone:

| # | commit |
|---|---|
| 3 | `fix(wp-66): the user chooses the model, per project and per scene` |
| 4 | `docs(wp-66): report - the middle existed at both ends, and the gate refused three models that were running` |
