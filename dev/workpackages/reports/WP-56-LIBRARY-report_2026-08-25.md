# WP-56-LIBRARY — the asset library, actors, presenter columns, logo, and presets

**Date:** 2026-08-25 · **Node:** node-01 (192.168.1.90) · **Version set:** `v5.15.0-library`
**Scope:** AD-09 sequencing items 2, 3 and 4 — a deliberate partial pull-forward
ahead of the Temporal cutover.

---

## 0. Headline

| Task | Outcome |
|---|---|
| **0** — CI glob fix (P2.49) | **DONE.** `fnmatchcase`. All 19 compliance tests pass; blast radius re-measured at zero. |
| **1** — DLQ replay (P2.60) | **DONE and PROVEN LIVE.** Three ORM models moved to `shared/models/`. `process_dlq` dispatched into the live queue and **completed**: `SUCCESS`, 0.148 s. |
| **2** — `library_assets` + actors (AD-09.4) | **DONE.** Migrations 0030/0031, models, service, 8 routes, GUI, 25 tests. |
| **3** — presenter columns + logo layer (AD-09.9/.10) | **STOPPED, with evidence.** AD-09's premise is wrong at three of four links, and closing it requires editing a frozen stage body. See §4 — this is the finding the package asked for. |
| **4** — presets (AD-09.5) | **DONE.** Migration 0032, versioned model, service, 5 routes, GUI, apply-to-project. |
| **5** — GUI, no CLI | **DONE.** `/library` with three tabs, a project-side preset apply panel and a library picker. Frontend moved v5.11.0-apibatch → v5.15.0-library. |
| **6** — 54.3% job failure rate | **DONE, read-only.** 19 failures, **six** root causes. §6. **Not one is a live pipeline defect.** No row changed. |

**Test position: zero new failures, two rows improved.**

| Tree | Before | After |
|---|---|---|
| `ivgs-api` | 850 / 0 / 0 / 0 | **875 / 0 / 0 / 0** |
| `ivgs-workers` | 766 / 18 / 48 / 15 | 766 / 18 / 48 / 15 (unchanged) |
| `ivgs-scheduler` | 22 / 21 / 0 / 0 | 22 / 21 / 0 / 0 (unchanged) |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | 4 / 0 / 0 / 0 (unchanged) |
| `tests_system` | 35 / 16 / 15 / 30 | **39 / 12 / 15 / 30** |

`TEST-BASELINE_2026-08-25.md` is updated in the same commit as the fixes that
moved those rows.

---

## 1. Scope ruling — the premise, checked

The package states: *"Items 2-4 are additive schema, API and frontend. No
pre-cutover code path reads the new tables… If you find that premise is wrong —
that any item here touches the storyboard→manifest spine — STOP and report it."*

**The premise holds for items 2 and 4, and it is FALSE for item 3.** The split
is clean and it is not a judgement call:

* **Items 2 and 4 create new tables.** `library_assets`, `actors`, `presets`.
  Verified after building: `grep -rn "library_asset\|actors\|presets"
  ivgs-workers/` returns nothing. No worker imports them, and the ORM classes
  are deliberately in `ivgs-api/app/models/` rather than `shared/models/` — the
  package the worker image actually ships — so a future import is a visible
  choice rather than an accident.
* **Item 3 is not additive at all.** It requires behaviour changes in
  `services/manifest_builder.py`, `tasks/pipeline_orchestrator_v2.py` and
  `tasks/stage7_prototype_draft.py`. The last of those is one of the eight stage
  task bodies that CLAUDE.md §3 and AD-05 §8 freeze: *"Wrapping is allowed;
  editing is not."*

Item 3 therefore **stopped**. Items 0, 1, 2, 4, 5 and 6 were completed in full.
§4 is the evidence.

One column crosses the line and is called out rather than buried:
`assets.library_asset_id` is on an EXISTING table, so the worker's `Asset` model
carries it. No worker code reads it. It is inert data, and it forces a deploy
ordering constraint recorded at `shared/models/asset.py` — **migration 0030 must
be applied before a worker image carrying that class starts**, or `select(Asset)`
raises `UndefinedColumn`. That ordering was followed here.

---

## 2. Task 0 — the CI glob (P2.49, CLOSED)

`scripts/compliance_scanner.py:105`'s `match_glob` handled only `*`-PREFIXED
globs and exact filenames. Every glob with an **infix** `*` fell through to the
`filename == pattern` branch and matched nothing.

`PIP_FILE_GLOBS`' `"requirements*.txt"` was the only such glob in the file.
That is why Appendix F.2 **Rule 2 alone** was unenforced while the other three
categories worked: their globs are all `*`-prefixed.

Replaced with `fnmatch.fnmatchcase` — **case-sensitive deliberately**.
`fnmatch.fnmatch` normalises case against the host platform, which would make
the gate answer differently on a Linux runner and a macOS checkout. A compliance
gate that disagrees with itself per platform is worse than one that is wrong the
same way everywhere. The old `*.env*`-matches-`.env` special case is not
reproduced because `fnmatchcase(".env", "*.env*")` is already true.

**Blast radius re-measured after the fix, not assumed:**

```
$ python3 scripts/compliance_scanner.py /opt/ivgs
Files scanned: 1455   Violations found: 0   ✓ Compliance check PASSED   rc=0
```

WP-55's measurement holds. All 19 cases in `test_compliance_scanner.py` pass;
`tests_system` moves 35 → 39 passed, 16 → 12 failed.

---

## 3. Task 1 — DLQ replay (P2.60, DLQ leg CLOSED, proven live)

### 3.1 What was wrong

Four deferred imports named `ivgs_api.app.models` — a package that resolves in
**no** image. The worker image ships `shared/` and `ivgs-workers/`
(`ivgs-workers/Dockerfile:30-31`) and does not ship `ivgs-api/`. Every one of
those imports raised `ModuleNotFoundError` the moment it was reached, and
`process_dlq` reached `_dlq_table()` and died there.

### 3.2 The repair, as ruled

Moved, with `git mv` so history follows:

| Class | From | To |
|---|---|---|
| `Asset` | `ivgs-api/app/models/asset.py` | `shared/models/asset.py` |
| `DeadLetterMessage` | `ivgs-api/app/models/dead_letter_queue.py` | `shared/models/dead_letter_queue.py` |
| `TaskRetry` | `ivgs-api/app/models/task_retry.py` | `shared/models/task_retry.py` |

The move was cheap because all three already declared against
`shared.database.Base` and none uses `relationship()` — only string-named
`ForeignKey`s. `app/models/*.py` are now **re-export shims**, so Alembic
autogenerate, `Base.metadata.create_all()` and all 20-odd existing
`from app.models.asset import Asset` sites are unchanged. Verified as one class,
not two:

```
app.models.Asset is shared.models.Asset  ->  True
tables registered on Base.metadata: 33
```

Re-declaring in the shim would raise `InvalidRequestError: Table is already
defined`; a comment in each shim says so.

**HTTP was explicitly not chosen**, per the ruling: the DLQ is the mechanism you
reach for when things are already failing, and a network hop inside a recovery
path is a new way for the recovery itself to fail.

### 3.3 The fifth site is deliberately still broken

`fallback_chain.py:274` imports `FallbackPolicyModel`, which **exists nowhere in
this repository**. WP-55 ruled it (P2.66): leave it broken, because repairing
the import would create the appearance of a database-backed fallback policy
system with no table, no writer and no caller behind it. That ruling was
honoured; the site is untouched.

### 3.4 The acceptance — a completed live dispatch, not a status code

```
node-01 $ docker exec ivgs-celery-default python -c "...send_task('...process_dlq', queue='default')"
DISPATCHED 4d95505f-d79b-40bf-917b-4125c63e3a11

state  = SUCCESS
result = {'auto_replayed': 0, 'flagged_stale': 0, 'total_pending': 0}
```

Worker log, `ivgs-workers:v5.15.0-library`:

```
Task ...process_dlq[4d95505f...] received
{"event": "dlq_processing_started", ...}
{"service": "dlq_service", "total_pending": 0, "event": "dlq_periodic_processing_complete", ...}
Task ...process_dlq[4d95505f...] succeeded in 0.1487672099901829s
```

`total_pending: 0` because `dead_letter_messages` is genuinely empty (measured).
The number is honest, and the proof is not the number — it is that the task
**reached the table, queried it, and returned**, where every previous run raised
`ModuleNotFoundError` before touching the database. Confirmed inside the
deployed container:

```
node-01 $ docker exec ivgs-celery-default python -c "from services.dlq_service import DLQService; print(DLQService._dlq_table())"
IN-CONTAINER _dlq_table() OK -> dead_letter_messages 14 columns
```

---

## 4. Task 3 — STOPPED. The AD-09.9 premise is wrong at three of four links

The package required this claim to be verified before building: *"the consuming
code in `manifest_builder` ALREADY EXISTS, only the columns are missing."*

**It does not exist as an end-to-end path.** Traced link by link against the
tree at `f2f7644`:

| # | Link | AD-09.9 assumes | Measured |
|---|---|---|---|
| 1 | `services/manifest_builder.py:167-172` | reads `talking_head_position` / `talking_head_scale` from scene data | **TRUE.** The code is there. But its input is `_fetch_project_scenes` → `GET /projects/{id}/scenes` → `SceneResponse`, which has no such fields, so it always takes the defaults. |
| 2 | manifest → Stage 7 | the positioned PiP layer reaches the compositor | **FALSE.** `pipeline_orchestrator_v2.py:1889 _build_manifest_scenes` rebuilds Stage-7 scene dicts from the locked manifest and reads **only `background` layers** (`:1932`). The `talking_head` layer manifest_builder writes is **discarded**. The emitted dict (`:1959-1966`) has no presenter key at all. |
| 3 | `stage7_prototype_draft.py:271-287` | maps five positions onto `PiPPosition` | **DEAD CODE.** The branch is guarded by `if talking_head_path and ...`, and its only caller passes `talking_head_path=None` (`:431`, comment: *"AD-03 Pillar 2: head overlaid once at the timeline level"*). It is never entered. |
| 4 | the actual overlay | — | `ffmpeg_client.py:700 compose_timeline(...)` composites the head **ONCE over the whole assembled timeline** (`:757-766`), with `talking_head_position` / `talking_head_scale` **defaulted** — Stage 7 (`:514`) passes neither. |

### 4.1 Why this is architectural, not a missing wire

Link 4 is **AD-03 Pillar 2** and it is deliberate: the head is rendered from the
full concatenated audio and overlaid at 0:00 so each scene's mouth lands on its
own audio. **Per-scene presenter control is not a flag on that design — it
contradicts it.** Honouring `presenter_enabled = false` for scene 3 of 7 means
cutting a single continuous overlay into per-scene segments, which changes
Pillar-2 behaviour for every project, not just ones using the new column.

AD-09 Draft 1 did not notice this. Its §AD-09.9 was written against links 1 and
3 — both of which contain real, readable code — without following either to a
caller.

### 4.2 Why it stopped rather than shipped

Closing it requires edits to **`tasks/stage7_prototype_draft.py`**, one of the
eight stage task bodies. CLAUDE.md §3: *"Wrapping is allowed; editing is not."*
AD-05 §8: *"If a migration session finds itself editing stage internals, stop.
Scope control has been lost."* It also requires editing `_build_manifest_scenes`
inside `pipeline_orchestrator_v2.py`, which AD-05 §8 lists in the **replace**
column — the coordination layer the Temporal cutover swaps out, and precisely
the diff the 2026-08-25 staging ruling protected.

### 4.3 What was NOT shipped, and why the absence is the honest choice

The columns and a GUI toggle were **not** landed. Adding
`storyboard_scenes.presenter_enabled` plus a switch in `SceneEditModal` would
have produced a control the operator can set, that saves, that reads back — and
that changes nothing in the rendered video. That is a green surface over an
empty action: the exact family AD-09.3 names as a blocking precondition and
lists eight existing instances of. This package declined to add a ninth.

Presets **can** record a logo and a logo policy, because the operator needs
somewhere to put those decisions now. Every such field is labelled *"Recorded,
not rendered"* in the GUI, and `POST /projects/{id}/apply-preset` returns them
under `recorded_not_applied`, never under `applied`.

### 4.4 Font provisioning — what the code requires (AD-09.14 Q6, out of scope)

Recorded so the operator can provision node-06 without re-deriving it:

* Fonts live in the library as `kind = "font"` (migration 0030); upload works today.
* Nothing reads them. There is no font resolution path in `manifest_builder`,
  `stage7_prototype_draft` or `ffmpeg_client`.
* The consumer, when built, is **Remotion** — lower-thirds and title cards are
  rendered by `remotion` (`manifest_builder.py:178-184`, `render_params.composition
  = "LowerThird"`), which resolves font families through the browser/Node runtime
  in the compositor container. A font must be installed **inside that container's
  font path**, not merely present on the node's filesystem.
* AD-09.10's recommendation stands and is unimplemented: **a render-time
  assertion**. Without one, a missing face falls back silently — the failure mode
  the addendum itself calls out.

---

## 5. Tasks 2, 4 and 5 — what was built

### 5.1 Migrations — sequenced, three of them, and round-tripped

AD-09.12 asks for a sequenced set rather than one unreviewable revision.

| Rev | Contents |
|---|---|
| **0030** | `library_asset_kind` + `library_owner_scope` ENUMs, `library_assets`, three indexes, `assets.library_asset_id` FK |
| **0031** | `presenter_orientation` ENUM, `actors`, two indexes |
| **0032** | `presets` (unique `(name, version)`, one active per name), `projects.preset_id` + `preset_version` |

Exercised both directions on `ivgs_reconciliation_test`: `upgrade head` →
`downgrade 0029` → `upgrade head`, clean. ORM/schema parity checked by
reflection rather than by reading: `library_assets` 16/16, `actors` 14/14,
`presets` 10/10, `assets` 21/21, `projects` 13/13, no drift either way.

Applied to the live `ivgs` database. Existing rows untouched and counted before
and after: 17 projects, 155 assets, `alembic_version` = `0032`.

*(`alembic check` is not usable in this repo and that is pre-existing: `env.py`
imports only `shared.database`, never `app.models`, so autogenerate reports
every API table as "removed". Not introduced here; noted so the next package
does not chase it.)*

### 5.2 The three design points AD-09 is emphatic about, and how each is enforced

**A new table, not `project_id NULL`** (AD-09.4.1). Re-checked against the live
schema rather than taken on the addendum's word: `assets.project_id` is `NOT
NULL … ON DELETE CASCADE`. Relaxing it would put library assets in a cascade
path — deleting the first project that used a shared logo would take the logo —
and inside `storage_quotas`' per-project accounting. Both are silent wrong
answers, not errors. Migration 0030's docstring records this so it is not
"simplified" back later.

**Reference, don't copy** (AD-09.4.2). `LibraryService.reference_into_project`
creates an `assets` row pointing at the **same** SeaweedFS object. The test that
guards it asserts on the act, not the status code: same `seaweedfs_fid`, same
`content_hash`, and **no additional upload call**. It also sets
`preserve_flag=True` so `RetentionService` cannot tier a referenced asset out
from under the projects pointing at it, and is idempotent — the GUI's "use this"
button is exactly the control that gets double-clicked.

**Upload-on-use, opt-in** (AD-09.4.2). `POST /projects/{id}/assets/upload` takes
an optional `library_kind`. **It must stay opt-in and there is a test that fails
if it does not**: every media task in the fleet uploads through that method, and
defaulting it on would pour generated frames, per-scene audio and talking-head
renders into a library that AD-09.14 Q7 (retention and quota) does not yet
govern.

### 5.3 `actors.engine_bindings` — AWAITING THE OPERATOR

AD-09.14 open question 1 is unanswered and **WP-56 did not invent an answer.**
The MagiHuman parameter set for (a) working generation and (b) actor/voice
consistency is operator knowledge recorded nowhere in this repository.

The column is JSONB, keyed by engine, **unvalidated on both sides**, and read by
nothing. A validator written against a guess would reject the operator's real
values on the day they are finally recorded — and a plausible guess written into
a schema is indistinguishable from a recorded fact six months later, which is
the failure the CLAUDE.md §2 fleet table has been corrected for twice. A test
pins the non-validation (`test_engine_bindings_are_stored_verbatim_and_unvalidated`),
and the GUI field carries an amber "Awaiting the operator" note.

`certified_model_id` is the AD-09.4.3 constraint made expressible: an actor is
only reproducible on the engine it was established against, so changing it is an
identity change, not a setting.

### 5.4 Presets — versioned, never mutated

Identity is `(name, version)`, not `id`. There is **no PATCH route and there will
not be one**: `POST /presets/by-name/{name}/revise` inserts version *n+1* and
deactivates the previous one. An in-place edit would silently rewrite the
provenance of every project already created from it. A partial unique index
enforces exactly one active version per name, so "the current version of
Corporate 2026" is a defined phrase rather than a convention.

`projects.preset_version` duplicates a column reachable through `preset_id`,
which would normally be a defect. The FK is `ON DELETE SET NULL`, and when that
fires this column is the only surviving record that the project came from
version 3 of something. Provenance a delete can erase is not provenance.

**Applying is itemised.** `PresetApplyResult` returns `applied` and
`recorded_not_applied` as two lists. Against the current schema, three of
AD-09.15 criterion 1's four categories are genuinely written:

* model selections → `project_model_selections` via
  `model_selection.manual_override`, which the pipeline reads and which
  re-validates the model at apply time (a preset created while a model was
  approved and applied after it was retired fails with the *current* reason);
* actor → the reference clip is referenced into the project and bound as
  `projects.talking_head_asset_id`, which Stage 6 reads;
* media defaults / runtime / audience → project columns.

Branding is the fourth and lands in `recorded_not_applied`, for the reason in
§4.3. `test_apply_preset_reports_branding_as_recorded_not_applied` fails if that
ever changes silently.

### 5.5 Preset drift — NOT DECIDED (AD-09.14 Q8)

Unruled, and this package did not rule it. **No `preset_drift` column was
added.** Adding one now would pick "surface it" by default and leave a column
nothing computes. It is one additive migration whenever the operator rules.
Recorded in §9 as D-2.

### 5.6 GUI — AD-09.15 criterion 7, no CLI step

| Surface | Operations |
|---|---|
| `/library` → **Assets** | browse, filter by kind, upload (with scope), replace/supersede, promote to global (admin) |
| `/library` → **Actors** | create with reference media, voice profile, engine bindings, orientation; retire; show retired |
| `/library` → **Presets** | create, revise into a new version, inspect full version history |
| `/projects/{id}` | **Apply a Preset** panel, showing both result lists |
| `/projects/{id}/assets` | **Use from the library** picker, driven by the server's own kind→asset_type map |
| Header nav | **Library** entry, viewer-visible; every write operator/admin-gated in the UI *and* server-side |

There is deliberately no seeding script and no management command. A route only
a script calls becomes one within a week.

### 5.7 The WP-40/43 lesson — and a fourteenth instance found and closed

The rule was applied both ways.

**Forward:** `src/types/library.ts` declares a field only where the API
demonstrably populates it, verified against live responses. Absent on purpose,
so reaching for one is a compile error: `preset_drift`, the presenter scene
fields, `logo_enabled`, intro/outro templates, courses.

**Backward — a real phantom found while doing it.** `src/lib/api-client.ts:42`
and `src/types/api.ts:640` **both** declared

```ts
export interface PaginatedResponse<T> { items: T[]; …; total_pages: number }
```

and this API has never sent `items` or `total_pages` from any route. It sends
`{data, total, page, per_page, pages, has_more}` — which `src/lib/unwrap.ts` has
documented correctly since WP-35. The two disagreed and **the wrong one had the
more inviting name.** Nothing read it yet, so nothing was visibly broken; the
first component to trust it would have rendered an empty list for a populated
response. The trap fired immediately — the first `useLibrary` hook written
against it failed to compile.

Both declarations now carry the true shape, confirmed against a live response
from the deployed API:

```
$ curl -H "Authorization: Bearer …" http://192.168.1.90:8001/api/v1/library/assets
{"data":[],"total":0,"page":1,"per_page":50,"pages":0,"has_more":false}
```

`.items` is now a compile error, which is the point. `tsc --noEmit` and
`next build` both clean.

---

## 6. Task 6 — the 54.3% job failure rate, investigated (READ-ONLY)

**No row was modified.** Every figure below is from `SELECT` against the live
`ivgs` database.

19 of 35 `render_jobs` have `status='failed'` (7 success, 7 running, 2 pending).
`failure_category` is NULL on all 19, which is itself a finding — the column
exists and nothing populates it, so the classification the DLQ and retry
machinery key on has never been written for a render job.

### 6.1 Six root causes

| # | Count | Root cause | Is it a live defect? |
|---|---:|---|---|
| 1 | **9** | **Phantom rows from the never-dispatching regenerate endpoint.** `error_message` says so verbatim: *"Cancelled by WP-45 sweep: this row was created by the pre-WP-45 scene-regenerate endpoint, which inserted a job and dispatched no Celery task."* All nine have `celery_task_id IS NULL` and no checkpoints. **These are not failed renders. They are rows that were never renders.** | No — AD-09.3 stub family, `storyboard_service.py:174`. |
| 2 | **3** | **Stage 2 storyboard generation.** The one with evidence (`e408515a`, 2026-08-23) has a `failed` checkpoint reading `JSON parse failed: vLLM response is not valid JSON: Unterminated string starting at: line 86 column 27 (char 8186)`. An **output-token truncation**, not a parse bug — the model was cut off mid-string at ~8 KB. The two June instances (`8caf292e`, `64124c00`) carry only `"Stage storyboard_generation failed"` and predate checkpoint writing, so their cause is **unproven**; the shape matches. | **Possibly — the only candidate.** See §6.2. |
| 3 | **2** | **Worker crash stranding the media-generation join**, both 2026-06-05: *"media-generation join stranded (worker crash); no dispatch context available to advance."* This is the Redis-join fragility AD-05 §5.2 replaces with Temporal fan-out. | Known, architecturally addressed by the cutover. |
| 4 | **2** | **Defects fixed in later builds, and the rows say so.** `90891425`: *"Stage3Input validation — dispatch_pipeline had no media branch; fixed in this build."* `b3df6eb6`: *"tts_audio checkpoint write returned 429 (pipeline rate-limited itself; fixed in v5.11.0-apibatch)."* | No — both closed. |
| 5 | **2** | **Synthetic/test rows.** `768c4b59` has `error_message IS NULL` and its only checkpoints are `wp36-probe` and `wp36_post_deploy_verification` — a WP-36 deploy probe. `7980c0b9` (2026-08-15) is a bare *"Stage prototype_draft failed"* with no checkpoint. | No. |
| 6 | **1** | **Animation generation, instant failure.** `e038ea52`, node-03: `{"failed_count": 1, "successful_count": 0, "binding_source": "explicit-override", "total_generation_time": 0.23}`. 0.23 s is a **binding/dispatch-time refusal**, not a generation attempt. A sibling job (`5eb2bda1`) completed `animation_generation` two hours earlier on the same day. | Unresolved, single instance. |

### 6.2 What the 54.3% actually is

**Nine of nineteen — 47% of all failures — are rows that never dispatched
anything.** Add causes 4 and 5 and **13 of 19 are not live defects at all**:
seven phantoms-and-probes, two already-fixed builds, plus two worker crashes on
a join the cutover replaces.

The residue that could still bite a RUN-2 is small and specific:

* **Stage 2 vLLM output truncation (up to 3 jobs).** The one measured instance
  died at 8186 characters mid-string. Before RUN-2, check `max_tokens` on the
  storyboard call against the length of a full storyboard for the target runtime.
  This is the single highest-value pre-RUN-2 check.
* **One animation binding refusal**, one instance, node-03.

**RUN-2 should not be attempted until the Stage-2 token budget is checked** —
which was the package's own instruction and is now supported by the measurement
rather than by caution.

### 6.3 The alert stays as it is

Correct not to fire on history: 13 of these 19 are not the event the alert is
for. Unchanged, as ruled.

### 6.4 Two by-products, recorded not fixed

* `render_jobs.failure_category` is NULL on all 19 failures. Nothing writes it.
* `task_retries` is **empty** (`SELECT count(*)` = 0) across all 35 jobs,
  including the ones that failed with retries configured. Consistent with
  P2.60 — `retry_engine.py`'s recording path imported `ivgs_api.app.models` and
  raised before writing. **That import is repaired in this package**, so the
  table should begin filling from `v5.15.0-library` onward. First confirmation
  opportunity is RUN-2; it is not claimed as verified here.

---

## 7. Deployment — node-01 only, via the artifact path

Compose invocation derived from container labels, not guessed:
`docker-compose.node01.yml` + `docker-compose.override.node01.yml` +
`docker-compose.monitoring.yml`, `--env-file ivgs-infra/.env`, `--no-deps`.

**Order mattered and was followed:** migrations `0030→0032` applied to live
`ivgs` **first**, then the images — see §1 on `UndefinedColumn`.

Verified by `docker ps`, never by reading a tag out of a container (CLAUDE.md §6):

| Container | Image | Status |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.15.0-library` | healthy |
| `ivgs-celery-default` | `ivgs-workers:v5.15.0-library` | healthy |
| `ivgs-celery-composition` | `ivgs-workers:v5.15.0-library` | healthy |
| `ivgs-celery-beat` | `ivgs-workers:v5.15.0-library` | healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.15.0-library` | healthy |

The frontend has moved **v5.11.0-apibatch → v5.15.0-library**, closing the
three-version gap.

Live checks after deploy:

```
GET /api/v1/library/assets  (no token)  -> 403      # HTTPBearer, as everywhere
GET /api/v1/library/assets  (admin)     -> {"data":[],"total":0,...}
GET /api/v1/actors          (admin)     -> {"data":[],"total":0,...}
GET /api/v1/presets         (admin)     -> {"data":[],"total":0,...}
GET /library (frontend, direct :3001)   -> 200, chunk app/library/page present
GET /library (via nginx)                -> 200
```

**No live write was performed against the new tables.** They are empty in
production and the library has no delete route by design (AD-09.4.2 — never
hard-deleted while referenced), so seeding a demo row would have left debris the
operator cannot remove. The write paths are covered by 25 tests against a real
PostgreSQL; the live checks prove deployment, auth and DB reach.

### 7.1 Operator paste blocks — nodes 02, 03, 04

Worker rebuild is an OPERATOR job. Artifact is staged and checksummed:

```
/mnt/ivgs-shared/image-artifacts/ivgs-workers-v5.15.0-library.tar.zst   313M
sha256 a004ca6f56adc2b3a72ca36e375f1106973a3b661be88fde403c7406c2e8e581
```

**Note on necessity:** these nodes do not process the DLQ (`default` queue is
node-01), but `motion_graphics.py` (`Asset`) and `retry_engine.py` (`TaskRetry`)
run on GPU nodes and carry two of the four repaired imports. Cause 6.4's second
by-product — the empty `task_retries` table — will only start filling once these
nodes are on this image.

**node-02** (192.168.1.91):

```bash
cd /mnt/ivgs-shared/image-artifacts && sha256sum -c ivgs-workers-v5.15.0-library.tar.zst.sha256 && \
sudo sh -c "zstd -d -c ivgs-workers-v5.15.0-library.tar.zst | docker load" && \
cd /opt/ivgs/ivgs-infra && sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.15.0-library/' .env && \
sudo docker compose -f docker-compose.node02.yml --env-file .env up -d --pull never --no-deps celery-worker && \
docker inspect ivgs-celery-worker-node02 --format '{{.Config.Image}}'
```

**node-03** (192.168.1.92) — **the service is `cogvideox-worker`, NOT
`celery-worker`.** node-03 also declares a `celery-worker` under
`profiles: ["standby"]` which is not running; naming it starts a second worker
competing for the same queues and leaves the real one stale (WP-44 §6.3,
CLAUDE.md §6.2):

```bash
cd /mnt/ivgs-shared/image-artifacts && sha256sum -c ivgs-workers-v5.15.0-library.tar.zst.sha256 && \
sudo sh -c "zstd -d -c ivgs-workers-v5.15.0-library.tar.zst | docker load" && \
cd /opt/ivgs/ivgs-infra && sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.15.0-library/' .env && \
sudo docker compose -f docker-compose.node03.yml --env-file .env up -d --pull never --no-deps cogvideox-worker && \
docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
```

**node-04** (192.168.1.93) — `celery-worker` here `depends_on: comfyui`, so
`--no-deps` is load-bearing (CLAUDE.md §6):

```bash
cd /mnt/ivgs-shared/image-artifacts && sha256sum -c ivgs-workers-v5.15.0-library.tar.zst.sha256 && \
sudo sh -c "zstd -d -c ivgs-workers-v5.15.0-library.tar.zst | docker load" && \
cd /opt/ivgs/ivgs-infra && sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.15.0-library/' .env && \
sudo docker compose -f docker-compose.node04.yml --env-file .env up -d --pull never --no-deps celery-worker && \
docker inspect ivgs-celery-worker-node04 --format '{{.Config.Image}}'
```

Nodes 05 and 06 were not touched: **node-05 is out of service** (confirmed
hardware memory fault) and **node-06 is operator-managed**.

---

## 8. Test evidence

```
ivgs-api          875 passed                              in 266.51s   (was 850/0)
ivgs-workers      766 passed, 18 failed, 48 skipped, 15 errors  in 20.23s   (unchanged)
ivgs-scheduler     22 passed, 21 failed                   in  1.30s   (unchanged)
ivgs-backup-worker  4 passed                              in  0.31s   (unchanged)
tests_system       39 passed, 12 failed, 15 skipped, 30 errors  in  1.63s   (was 35/16)
```

Zero new failures. No assertion weakened, no skip marker added, no coverage
deleted. The 25 new API tests are additions, not relaxations.

**One environment note, per the package's own rule.** The first `ivgs-api` run
was killed by a 2-minute harness timeout mid-test. The `db_session` teardown
TRUNCATE never ran, so `operator_token_user` survived and errored the *next*
run's first test with `UniqueViolationError: users_username_key` — 874 passed,
1 error. Not a retry trigger and not a regression: the module passes alone, and
a clean re-run after verifying `SELECT count(*) FROM users` = 0 gave 875/0/0/0.
The mechanism is now recorded in the baseline §2 so the next package recognises
it in one step instead of debugging it.

---

## 9. Decisions needed

**D-1 — Task 3 (presenter columns + logo layer): how to proceed.** §4 is the
evidence. Per-scene presenter control cannot be delivered without editing
`stage7_prototype_draft.py` (a frozen stage body) and changing AD-03 Pillar-2
overlay semantics from one continuous overlay to per-scene segments.

| Option | Implication |
|---|---|
| **Hold until M3.3** *(recommended)* | Item 3 joins item 5 behind the cutover. Stage 7 becomes an activity; the overlay change lands once, in the new architecture, against a clean baseline. Cost: per-scene presenter control stays unavailable. |
| Amend AD-05 §8 to permit this one stage-body edit | Delivers AD-09.15 criterion 4 now. Cost: contaminates the cutover baseline diff on Stage 7 — the exact thing the 2026-08-25 staging ruling deferred item 5 to avoid — and reopens a scope boundary CLAUDE.md calls binding. |
| Ship columns + GUI now, render later | **Not recommended, and not done.** A presenter toggle that saves and reads back but changes no output is a ninth instance of the AD-09.3 stub family. |

**D-2 — Preset drift (AD-09.14 Q8), UNRULED and untouched.** Surface divergence
between a project and its preset, or ignore it? WP-56 did not decide. Nothing
was built either way; whichever is ruled, it is one additive migration plus a
comparison over the preset payload. The decision point is real now that presets
exist and are being applied.

**D-3 — `actors.engine_bindings` is empty and waiting on you (AD-09.14 Q1).**
The MagiHuman parameter set for working generation and for actor/voice
consistency is recorded nowhere in this repository. Until it is, an actor stores
identity intent but cannot reproduce identity. The column, the API and the GUI
field are ready to receive it verbatim.

**D-4 — Stage-2 vLLM output truncation, before RUN-2.** §6.2. One measured
instance died at 8186 characters mid-JSON-string; two more June failures match
the shape without evidence. Check `max_tokens` on the storyboard call against a
full storyboard for the target runtime before RUN-2 is attempted.

**D-5 — `render_jobs.failure_category` is never written.** NULL on all 19
failures. The column exists, the ENUM exists, and the classification the DLQ and
retry machinery key on has never been recorded for a render job. Out of scope
here; worth a ledger entry.

---

## 10. Push block — COMMITTED AND HELD, NOT PUSHED

Nothing has been pushed. Held commits:

| # | Commit | Subject |
|---|---|---|
| 1 | `c5d0fe0` | `fix(wp-56): compliance scanner glob, and DLQ models move to shared/` |
| 2 | `4754339` | `feat(wp-56): library_assets, actors and presets — AD-09.4/.5` |
| 3 | *(this commit)* | `docs(wp-56): report, and the 2026-08-25 baseline moved to 875/39` — a commit cannot carry its own SHA; `git log --oneline -3` shows it |

**Count gate — run this before pushing. It must print `GATE PASS`:**

```bash
cd /opt/ivgs
PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
unset PGPW PGUSER

API=$(.venv/bin/python -m pytest ivgs-api/tests -q 2>&1 | tail -1)
WRK=$(.venv/bin/python -m pytest ivgs-workers/tests -q 2>&1 | tail -1)
SCH=$(.venv/bin/python -m pytest ivgs-scheduler/tests -q 2>&1 | tail -1)
BUP=$(.venv/bin/python -m pytest ivgs-backup-worker/tests -q 2>&1 | tail -1)
SYS=$(.venv/bin/python -m pytest --timeout=120 tests_system -q 2>&1 | tail -1)

printf 'api : %s\nwrk : %s\nsch : %s\nbup : %s\nsys : %s\n' "$API" "$WRK" "$SCH" "$BUP" "$SYS"

ok=1
echo "$API" | grep -q '875 passed'                                        || ok=0
echo "$WRK" | grep -q '18 failed, 766 passed, 48 skipped'                 || ok=0
echo "$SCH" | grep -q '21 failed, 22 passed'                              || ok=0
echo "$BUP" | grep -q '4 passed'                                          || ok=0
echo "$SYS" | grep -q '12 failed, 39 passed, 15 skipped'                  || ok=0
python3 scripts/compliance_scanner.py /opt/ivgs >/dev/null 2>&1           || ok=0
if [ "$ok" -eq 1 ]; then echo "GATE PASS"; else echo "GATE FAIL - DO NOT PUSH"; fi
```

If it fails on `api`, check `SELECT count(*) FROM users` in
`ivgs_reconciliation_test` first — a timeout-killed run leaves that table dirty
and the next run errors on its first test (§8).

**Push, only after `GATE PASS` and only on the operator's word:**

```bash
git log --oneline -3 && git push origin main
```
