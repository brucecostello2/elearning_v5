# WP-65 to WP-68 — RUN SUMMARY

**Unattended run, 2026-08-26. Four packages, in the order the run-order file
set. All four completed. Nothing pushed. No gate pressed. The operator's project
`another new multiplication test run` was read as evidence and never modified.**

---

## THE ONE-PARAGRAPH VERSION

All four packages found their brief's central premise to be partly false, and in
every case the truth was more useful than the premise. The weight fetch was
never missing — it existed, worked, and lived where nothing could import it,
while the Model Store's availability column measured a Redis LRU of jobs and
named the wrong node. The selection mechanism was complete at both ends and had
no middle, and the gate I built for it briefly refused three models the pipeline
renders with today. The client registry already existed, keyed on engine alone,
and one media stage never reads a binding at all. And motion graphics turned out
to rest on a promise this repository has been making since v3 and has never been
able to keep: **nothing in it can draw a number.**

---

## PER PACKAGE

| | WP-65 WEIGHTS | WP-66 SELECTION | WP-67 CLIENTS | WP-68 MOTION |
|---|---|---|---|---|
| **Tag deployed (node-01 only)** | `v5.24.0-weights` | `v5.25.0-selection` | `v5.26.0-clients` | `v5.27.0-motion` |
| **Commits held** | 2 | 2 | 2 | 2 |
| **Migration** | 0039 (new table) | 0040 (enum label) | none | 0041 (enum label) |
| **Tasks completed** | 6 of 6 | 6 of 6 | 4 of 5 | 4 of 5 |
| **Tasks stopped** | 0 | ½ (Task 2's availability half) | 1 (Task 4, frozen body) | ½ (Task 5, no renderer) |
| **Ledger entries** | 6 | 4 | 6 | 6 |
| **Live data touched** | v5 publish; 3 engine-name rows | own test project | none | v6 publish; own test project |

**Combined: 8 commits held. `git rev-list --count origin/main..HEAD` = 8.**

### WP-65 — WEIGHTS
The brief said nothing consumes the weight reference. **A complete, correct,
already-proven fetch client existed** — `ivgs-models/mbcp_fetch.py`, used live
for 23/23 verified files — in a directory no Dockerfile copies. Relocated to
`shared/weights/`, given staging, placement policy, idempotency and a record.

**The Model Store's "1 available" named the wrong node.** Availability is a
projection of the GPU scheduler's Redis LRU of models a *job* once loaded (no
TTL; nine of twelve rows point at dead container hashes). The bytes are on
node-03; the store said node-04, whose ComfyUI mounts only `checkpoints`.

**Eleven of eighteen models are engine-only certifications** — MBCP has no
bundle for them, and IVGS stores the *engine image digest* in a column called
`weights_checksum`, which is why five rows share one value.

### WP-66 — SELECTION
Built the missing middle: a Models tab, a per-scene picker in Edit Scene, an
override badge on the storyboard grid, provenance on every binding, and Task 5's
ruled invalidation asymmetry implemented **by composition** so a storyboard
approval *cannot* be affected rather than merely happening not to be.

**The live acceptance refuted my own refusal rule.** `engine_only` briefly
barred selection, and three stages showed zero selectable models — refusing
`CogVideoX-5b`, `FFmpeg-composition` and `Llama-3.3-70B-Instruct`, the defaults
those stages render with today. Corrected to a warning.

### WP-67 — CLIENTS
A registry existed, keyed on engine alone; `providers/image.py` was already a
two-branch `if` on `stage`, which cannot separate two *animation* families.
Rebuilt on `(stage, engine, family)` with capability contracts, so Wan's
person-in-the-still requirement stops being a property of the stage.

**`video_generation_task` never calls `get_binding`** — it picks its client from
clip length. WP-66's video-stage selection is recorded, audited, and inert.
Frozen body; ledgered as the highest-value item there.

AnimateDiff-SD15 chosen over MimicMotion on measured evidence: 8 nodes from an
empty latent versus 16 needing a still *and* a driving video.

### WP-68 — MOTION
**`drawtext` appears nowhere in this repository.** The compositor overlays
pre-rendered layers and burns bottom-aligned captions; it cannot place a digit.
So the cheap path the brief hoped for does not exist — and RULE 1's standing
promise, that "the composition overlay renders the numbers in a real font", has
had one half missing since v3.

Four maths templates built as deterministic, renderer-agnostic drawing
timelines, arithmetic-checked across parameters, with 20 real frames banked.
Prompt v6 asks for them as structured data in `generation_params` — a JSONB
column that already existed. The engine is declared with **no** misleading
default, and WP-65's availability model gained a *weightless* state.

---

## WHAT NEEDS A RULING, AND WHAT NEEDS AN ACTION

### Rulings needed — 3

| | question | why it needs you |
|---|---|---|
| **R-1** | **`models.weights_ref` and `weights_checksum` hold engine identities for eleven of eighteen rows.** Rename, add columns, or leave and document? | The column names are IVGS's; the semantics are MBCP's. Changing either is a change-controlled seam amendment (CLAUDE.md §11.1). |
| **R-2** | **MBCP emits `/engines/{digest}/manifest`, a route `mbcp_serving` does not implement.** | MBCP-side. `/opt/MBCP` is a read-only clone and this run did not touch it. |
| **R-3** | **`Kokoro` carries `engine=coqui` while being a Kokoro model**, so it resolves to no client. | A Model Store row correction, and only WP-65 sanctioned Model Store writes. WP-65 §5 is the precedent for the shape. |

### Operator actions awaiting you — 5

| | action | where |
|---|---|---|
| **A-1** | **Push all 8 commits.** Count-gated block below. | this file |
| **A-2** | **Deploy `v5.27.0-motion` to nodes 02/03/04.** Artifacts are banked. node-03's service is `cogvideox-worker`. | WP-68 report §8 Block C |
| **A-3** | **The first real weight fetch** — needs the MBCP serving token and signing key, your standing pending-register item. | WP-65 report §8 Block A |
| **A-4** | **Decide whether to deploy a motion-graphics renderer.** Everything else is built and proven. | WP-68 report §8 Block A |
| **A-5** | **AnimateDiff-SD15 needs an engine image with the `ADE_*` nodes** — not a weights problem, and fetching weights will not fix it. | WP-67 report §8 Block A |

### Things that are now HELD rather than silent

Three states that used to pass quietly and now say what they are. This is most
of what the run bought:

* a model with **no client** — certified, fetchable, and unrunnable by this
  system (WP-67);
* an engine with **no host** — resolves to nothing by name instead of to
  node-04's FLUX ComfyUI (WP-65, WP-68);
* a **`motion_graphics` scene** — held by the orchestrator instead of becoming
  a still with nothing saying so (WP-68).

---

## CORRECTIONS I MADE TO MY OWN WORK

Recorded because each is the same class of defect the run existed to close, and
because three of them were caught by looking at live output rather than by a
test.

1. **WP-65** — `fetch-weights` would have written verified bytes into a node-03
   path created locally on node-01 and recorded them as available. Now
   `PlacementNotLocalError`, failing closed, before the network.
2. **WP-65** — the `not_fetched` label read *"certified, weights not fetched"*,
   a claim about the node that IVGS cannot make. Now *"no fetch recorded by
   IVGS"*.
3. **WP-66** — `engine_only` as a selection bar refused three models that are
   rendering today. Caught by the live acceptance run.
4. **WP-67** — the placement fallback was a Wan-pack constant applied to every
   host, and the registry answered "no client" for every ORM row because enum
   members do not stringify to their values. Both found by tests failing.
5. **WP-68** — three template defects found by **opening the banked PNGs**: a
   carry that vanished after travelling, a leading zero (`27 + 15 = "042"`), and
   a tens digit that changed shape mid-animation. Every one passed all the
   assertions I had written.
6. **WP-68** — migration 0041 added the fourth media type to PostgreSQL and to
   two validators, and **missed the ORM column's own list**, so a row could be
   written and not read back. Found by the acceptance run; there is now one
   list.

---

## TESTS

| tree | start | WP-65 | WP-66 | WP-67 | WP-68 | failures |
|---|---|---|---|---|---|---|
| `ivgs-api` | 1123 | 1208 | 1252 | 1286 | **1359** | **0, every run** |
| `ivgs-workers` | 887 | 887 | 887 | 903 | **903** | 18 / 48 skipped / 15 errors — **identical, every run** |

**+252 tests. Zero new failures at the end of every package.**

Three intermediate runs showed a failure and each is recorded in its package
report rather than quietly re-run:

* **WP-66** — `test_manual_override_validations`, following a refusal message
  that gained a machine slug. Strengthened to assert the wording AND the slug.
* **WP-68** — `test_diagram_motion_maps_to_image`, which required the storyboard
  prompt to say *"there is no motion-graphics pathway in this pipeline"*. WP-68
  built the pathway. Renamed and strengthened.
* **WP-68 again** — my first replacement for that test was itself wrong: it
  demanded a negation (*"is not 'animation'"*) that `stage2_user.j2` has never
  used, since that template states the rule by inclusion. Two worker templates
  went red and the assertion was corrected, not the templates.

**Zero new failures in every package.** `TEST-BASELINE_2026-08-25.md` was updated
in the same commit as each change that moved a row, and every intermediate run
that showed a failure is recorded in the package report rather than quietly
re-run.

Two things were deliberately **not** done, and both are recorded:

* WP-65 declined to implement the brief's request to fail on "multi-digit
  numerals" — `DIGITS` already fails on a single digit, so writing it would have
  been a **relaxation**.
* WP-68 kept `adaptation_service.MEDIA_TYPES` at three values while the API
  accepts four, because *Adapt description* rewrites prose and a motion graphic
  does not take prose. A test asserts the shorter list so a future tidy-up does
  not "fix" it.

---

## PUSH BLOCK — count-gated, all four packages

```bash
# node-01. Refuses unless exactly the 8 commits this run held are ahead.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }
  EXPECTED=8
  AHEAD=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $AHEAD (expected $EXPECTED)"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$AHEAD" -ne "$EXPECTED" ]; then
    echo "REFUSED: $AHEAD commits ahead, expected $EXPECTED. Something else has"
    echo "committed since this run finished; read the log above before pushing."
  else
    echo
    echo "git push origin main    # <- run this line by hand"
  fi
)
```

| # | commit |
|---|---|
| 1 | `fix(wp-65): a certified model's bytes get a fetch, a placement and a record that means it` |
| 2 | `docs(wp-65): report - the fetch was never missing, and the store was measuring the wrong thing` |
| 3 | `fix(wp-66): the user chooses the model, per project and per scene` |
| 4 | `docs(wp-66): report - the middle existed at both ends, and the gate refused three models that were running` |
| 5 | `fix(wp-67): a selected model reaches the code that knows how to run it` |
| 6 | `docs(wp-67): report - the registry existed keyed on the wrong thing, and one stage never reads a binding` |
| 7 | `fix(wp-68): numbers that move, drawn rather than generated` |
| 8 | `docs(wp-68): report - nothing in this repository could draw a number, and the run summary` |

---

## FLEET STATE AT HANDBACK

* node-01 api/frontend/workers **`v5.27.0-motion`**, all five services healthy.
* nodes 02/03/04 workers still **`v5.23.0-media`** — paste blocks held (A-2).
* DB at migration **0041**. 0039 adds a table (downgrade exercised both ways);
  0040 and 0041 add one enum label each (downgrades are deliberate no-ops).
* Storyboard prompt **v6 active** (`726af31f-80f1-4224-83cd-b133a62406f7`),
  v1–v5 preserved inactive. Rollback is one `UPDATE` of `is_active`.
* `scene_media_adaptation` v1 unchanged.
* Model Store: three animation rows corrected `animatediff` → `comfyui`; zero
  `animatediff` rows remain. The live serving row `wan2.2-animate` was not
  touched.
* Every test project this run created was deleted through the WP-59 flow.
* node-05 and node-06 were not touched. No container was stood up anywhere.

**The operator's project, verified rather than asserted.** Its 13 scenes were
created and last updated at **18:59:51+00**; this run's first write of any kind
was the v5 prompt publish at **21:18:38+00**, two hours and nineteen minutes
later. `state=STORYBOARD_GENERATION`, 13 scenes, unapproved — exactly as it was
handed over. It was read twice as evidence (once to run the deterministic
checker over its visuals, once to count its repeated descriptions) and never
written to, regenerated, triggered, approved or deleted.

---

## IF YOU READ ONLY ONE MORE THING

**WP-68 ledger L-2.** RULE 1 has instructed the storyboard model since v3 that
the composition overlay renders every number in a real font, and has had every
scene reserve the upper-right third of the sheet for it. Nothing draws them.
That is why the operator's thirteen scenes contain no numbers anywhere — not in
the images, which RULE 1 correctly forbids, and not in the overlay, which does
not exist. The templates this run built are the first thing in the repository
that could keep that promise, and they are one deployed renderer away from
doing it.
