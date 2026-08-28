# WP-IVGS-04 — the runtime name resolves to a client, and the seam is proven

**Report · 2026-08-28 · written as the work proceeded.**
Closes WP-IVGS-03 **D-1**. Opens **D-2** and **D-3**, both measured, neither fixed.

---

## §0 Conventions, and the conflicts declared rather than resolved silently

`dev/CLAUDE.md` was read in full first. Two clauses conflict with the session order;
both were put to the operator and the operator's answer followed.

| `dev/CLAUDE.md` | Session order | Followed |
|---|---|---|
| §1 — *"Claude does NOT commit, push, merge, or deploy."* | *"Commit and HOLD"* + *"Deploy to node-01 ONLY"* | **Committed, not pushed. Deployed node-01 only.** No other node touched. |
| §12 — *"findings and proposed fix BEFORE writing code (stop and show the operator)"* | Execute | **Stopped and asked** — twice, on D-2's scope and on 4(c). Both answered before any code was written. |

**Two operator rulings were taken mid-package and are recorded because they bound the work:**

1. **D-2 scope — *"Task 1 verbatim; D-2 reported only."*** `binding.py` and
   `ivgs-workers/providers/tts.py` were therefore **not touched**, though §6 shows they are
   what stands between this package and a pipeline-level render.
2. **Task 4(c) — *"Author a node-04 paste block that completes 4(c)."*** Authored at §8.4.
   ⚠ It is **staged, not runnable as it stands**: it depends on D-2 being lifted, which this
   package was told not to do. That is stated inside the block itself, not only here.
3. **Task 2 — *"Also measure the XTTS-v2 blast radius in depth."*** §5.3.

---

## §1 Headline

| Task | Result |
|---|---|
| 1 — two registry entries | **Done**, red-green. `(voiceover_tts, tts, kokoro)` and `(voiceover_tts, tts, xtts)`. Nothing removed. |
| 2 — what ingest does to the live row | **UPDATE, not INSERT** (`ad01_ingest.py:149-152`, `:190-196`) — **but it updates the ORPHAN, not the row rendering today.** The order's premise did not survive measurement. §5. |
| 3 — which images ship the change | **api + workers**, not four. Both at `v5.28.0-engine-domain`, deployed node-01. Production alembic **0041 → 0042**. §7. |
| 4a — INGEST | Operator's, two-sided. IVGS-side check block authored, §8.3. **Not run.** |
| 4b — RESOLVE | **PROVEN** in the deployed image against the live registry. §6.1. |
| 4c — RENDER | **Real audio produced from an `engine='tts'` binding, both families** (§6.2). The **pipeline-level** render is **BLOCKED by D-2** and is the node-04 block at §8.4. |

**Zero new test failures.** `ivgs-api` **1377 passed / 0 failed**; `ivgs-workers`
**903 passed / 18 failed / 48 skipped / 15 errors** — identical to
`TEST-BASELINE_2026-08-25.md`. One full-suite run used of the two allowed.

---

## §2 Task 1 — the two entries, and why the three-tuple was the right key

`shared/providers/client_registry.py`. Verified against the source before writing, as §5.2 of
the order required — and the order's stated values were **correct**:

- stage is `voiceover_tts` (`client_registry.py:491,505`; `model_store.py:86`)
- families are `xtts` (registered under engine `coqui`, `:502`) and `kokoro` (engine `kokoro`, `:516`)

```
BEFORE                                   AFTER
(voiceover_tts, coqui,  xtts)   ->Coqui  (voiceover_tts, coqui,  xtts)   -> CoquiClient   [untouched]
(voiceover_tts, kokoro, kokoro) ->Kokoro (voiceover_tts, kokoro, kokoro) -> KokoroClient  [untouched]
                                         (voiceover_tts, tts,    kokoro) -> KokoroClient  [NEW]
                                         (voiceover_tts, tts,    xtts)   -> CoquiClient   [NEW]
```

**The ruling is vindicated by measurement.** MBCP certifies **both** TTS models with
`engine="tts"` — XTTS-v2 at `scripts/seed_stage.py:543` and Kokoro at `:576`, read off
`origin/main`, two config rows on ONE `tts_coqui` adapter. An `engine -> client` alias maps a
runtime to a single client; it would have picked one model and been silently wrong for the
other. §6.2 demonstrates the difference with real audio from two different servers.

**Two implementation choices worth naming:**

- **The contract is derived, not retyped.** `replace(spec.contract, engine="tts")` reads the
  entry already registered, so "what Kokoro requires" cannot fork into two drifting copies as
  the runtime key ages. A test pins that the two keys agree on `requires`/`produces`/`family`.
- **`name_patterns` are deliberately not re-declared.** They are family-keyed and
  engine-independent; passing them again would only duplicate entries in `_NAME_PATTERNS`.
  Measured after: **15 patterns, one `kokoro` and one `xtts`** — unchanged.

### 2.1 Red-green, as ordered

RED, before the entries existed — **4 failed, 4 passed**:

```
test_engine_tts_resolves_to_kokoro_for_the_kokoro_family   FAILED
test_engine_tts_resolves_to_xtts_for_the_xtts_family       FAILED
test_one_engine_two_families_two_different_clients         FAILED
test_the_contract_is_the_same_object_shape_on_both_keys    FAILED

NoClientForFamilyError: model 'kokoro-82m' is selected for stage 'voiceover_tts'
on engine 'tts', but IVGS has no client for family 'kokoro'.
```

The **4 that passed are the guards** — the two existing registrations, the named refusal, and
the two-families invariant. They are green before *and* after, which is what makes them
evidence that nothing was removed rather than decoration.

GREEN: **42 passed** in `test_wp67_clients.py` (34 pre-existing + 8 new).

---

## §3 ⚠ D-2 — the runtime name misses TWO MORE engine-keyed lookups. NOT FIXED.

**This is the successor to WP-IVGS-03's D-1, and it is the reason Task 4(c) could not be
completed at the pipeline level.** Reported to the operator before any code was written; the
ruling was *"Task 1 verbatim; D-2 reported only."*

`engine='tts'` is consulted in **three** places, not one:

| # | Mechanism | Key | `tts` |
|---|---|---|---|
| 1 | `client_registry._REGISTRY` (`client_registry.py:106`) | `(stage, engine, family)` | ✅ **fixed by Task 1** |
| 2 | `binding._ENGINE_ENDPOINTS` (`binding.py:22-46`) | **engine alone** | ⛔ `EndpointResolutionError` |
| 3 | `factory._BUILDERS` (`factory.py:44`) | **engine alone** | ⛔ `EngineNotRegisteredError` |

Measured **inside the deployed `v5.28.0-engine-domain` worker**, not inferred:

```
resolve_endpoint('kokoro') -> http://node-05:8021
resolve_endpoint('coqui')  -> http://node-05:8020
resolve_endpoint('tts')    -> RAISES EndpointResolutionError: no endpoint mapping for engine 'tts'
registered engine builders: ('cogvideox','comfyui','coqui','kokoro','latentsync','sadtalker','vllm')
```

**Stage 5 never calls `resolve_client` at all.** `stage5_voiceover.py:618` calls `get_binding`
— which hits #2 inside `_binding_from_model` (`factory.py:97`) — then `build_provider` at
`:647`, which hits #3. So a pipeline render through an `engine='tts'` row dies at #2 **before
the registry this package fixed is ever consulted.**

⚠ **The failure is loud and named in both cases**, so nothing here fails silently. But
**Task 1 alone does not make an `engine='tts'` model renderable through the pipeline**, and
saying otherwise would be false. ⛔ **No configuration can work around #2**: `resolve_endpoint`
consults `_ENGINE_ENDPOINTS` **before** any environment variable, so setting `IVGS_TTS_URL`
would not help — the map lookup returns `None` and raises first (`binding.py:97-99`).

**The fix, when it is ruled on, is not two lines.** `_BUILDERS` is keyed on engine ALONE, so a
single `tts` builder cannot distinguish Kokoro from XTTS — it needs exactly the family branch
`client_registry` was built to replace. That is a design decision, which is why it was not
taken unilaterally.

### 3.1 A finding raised and then WITHDRAWN, recorded rather than quietly dropped

I initially flagged that node-01's workers resolve `kokoro` to `http://node-05:8021`, which is
dead (`IVGS_KOKORO_URL` is set only in `docker-compose.node04.yml:113`, never on node-01).
**That is not a defect.** Stage 5 is routed to `gpu_tts` (`pipeline_orchestrator_v2.py:137`),
consumed only by `image-worker@node04`, where the variable *is* set. The value is correct by
placement and node-01 never uses it. Withdrawn.

Likewise `shared/weights/placement.py` treats `coqui`, `kokoro` and `tts` **identically** —
all three raise `NoHostForEngineError` (measured). That is not a delta introduced here, so it
is not counted as a finding.

---

## §4 ⚠ D-3 — the engine value is a SILENT branch in the stage body. NOT FIXED.

**The sharpest finding in this package, and the only one that fails quietly.**

`ivgs-workers/tasks/stage5_voiceover.py:364`:

```python
if tts_binding.engine == "coqui":
    synthesis_params = CoquiSynthesisParams(
        text=..., language=..., speaker_wav=task_input.speaker_wav_data,   # <- inline BYTES
        speaker_wav_path=..., temperature=task_input.tts_temperature, speed=...)
    _synth = await tts_provider.synthesize(synthesis_params)
else:
    _synth = await tts_provider.synthesize(narration_text, coqui_lang,
        TTSParams(speaker_wav=task_input.speaker_wav_path, speed=...))
```

When XTTS-v2's engine flips `coqui -> tts` (§5.3 — it will, by name match), this branch falls
to the **else**. `CoquiClient.synthesize` is **dual-dispatch** (`coqui_client.py:237-258`), so
**it does not raise.** It rebuilds a `CoquiSynthesisParams` from the narrow ABC parameters:

| Passed on `engine='coqui'` | Passed on `engine='tts'` |
|---|---|
| `speaker_wav` = inline reference-voice **bytes** (`:368`) | ⛔ **dropped** |
| `temperature` = `task_input.tts_temperature` | ⛔ **dropped** — falls to the dataclass default `0.75` (`coqui_client.py:94`) |
| `speaker_wav_path`, `speed` | carried |

**Result: a valid WAV, in the wrong voice, at a different sampling temperature, with no
exception and no warning.** Voice cloning silently disabled by a change to a metadata string.
That is the exact "right engine, wrong weights, plausible output" shape AD-01 selection exists
to prevent, and it belongs in `WP-00-SWALLOWED-FAILURES`.

**Not fixed here** — `stage5_voiceover.py` is a stage body, and `dev/CLAUDE.md` §3 makes the
eight stage task bodies off limits during the orchestration migration ("wrapping is allowed;
editing is not"). This needs an operator ruling, not an edit.

---

## §5 Task 2 — what ingest actually does. **The order's premise does not survive measurement.**

### 5.1 The determination: it UPDATES — `ad01_ingest.py:149-152` and `:190-196`

```python
149  existing = (await db.execute(select(Model).where(Model.name == bundle.model_name))
150                 ).scalar_one_or_none()
152  created = existing is None
...
190  else:
191      model = existing
195      if bundle.engine is not None:
196          model.engine = bundle.engine          # supplied-wins
```

The match is **exact string equality on `Model.name`**, which carries a UNIQUE constraint
(`models_name_key`, measured). There is no engine in the predicate, and no INSERT branch is
reachable when a name matches.

### 5.2 ⛔ But it does NOT reach the row that is rendering. The names differ.

Measured on the **production** database, node-01:

| id | name | engine | state | enabled | is_default | created |
|---|---|---|---|---|---|---|
| `a1ac974d` | **`kokoro-82m`** | `kokoro` | approved | **t** | **t** | 2026-08-24 |
| `2b2a0be5` | **`Kokoro`** | `coqui` | candidate | f | f | 2026-07-10 |
| `0d466bca` | `XTTS-v2` | `coqui` | approved | **t** | f | 2026-07-10 |

**MBCP's certificate carries `model_name="Kokoro"`** — `mbcp_api/api/v1/certifications.py:829`
(`model_name=model.name`) sourcing `scripts/seed_stage.py:576`, both on `origin/main`.

`"Kokoro" != "kokoro-82m"`. So the certificate lands on the **orphan** row `2b2a0be5`, the one
WP-IVGS-03 §7.1 already found. What actually happens:

- `Kokoro` (orphan): engine **`coqui` -> `tts`**, weights ref/digest refreshed, a fresh
  attestation appended. **Stays `candidate`, stays `enabled=false`** — the update branch
  touches neither, so it remains unselectable.
- `kokoro-82m` (rendering, default, enabled): ⛔ **never touched. Its engine does not change.**

**So the order's first branch — *"the live rendering row's engine changes under it, and Task 1's
registration is the only thing that keeps audio working"* — is FALSE.** Audio is not at risk
from ingest at all. The registration in Task 1 is still correct and still needed, but for the
row MBCP is actually certifying, not for the one producing audio today.

**And the second branch is only half true.** No *new* duplicate is created — the duplicate the
order anticipated **already exists**, created 2026-07-10, and this re-send updates it rather
than adding a third. ⛔ **Not deduplicated.** AD-10 §5.2, as instructed.

Both `Kokoro` and `XTTS-v2` already carry MBCP provenance in `default_params` (`provenance_id`,
`engine_image_digest`) — they were ingested through this same receiver in July, landing on
`coqui` because those older bundles omitted `engine` and hit the stage default
(`ad01_ingest.py:70`). `kokoro-82m` carries only `{"engine_model": "kokoro"}`: hand-seeded,
never certified. **That is the root of the split.**

### 5.3 Blast radius of the XTTS-v2 flip — measured in depth, as ruled

`XTTS-v2` is MBCP's model name **and** the IVGS row name, so its certificate **does** match and
its engine **will** flip `coqui -> tts` on an **approved, enabled** row.

| Selection path | State | Effect of the flip |
|---|---|---|
| `project_model_selections` for `voiceover_tts` | **0 rows** (3 total, all `image_generation`) | none — nothing selects it |
| `is_default` fallback (`factory.py:180-190`) | `is_default = false` | none — `kokoro-82m` holds the default |
| `presets` | **table empty** | none |
| `actors.certified_model_id` | **table empty** | none |
| `fallback_policies` | 4 rows, scene-type strategies (`ai_video`/`zoom_pan`…), **no model refs** | none |
| `model_capability_tags` | **0 rows** for the stage | none |
| `model_weight_placements` | **0 rows** for the stage | none |
| `model_node_availability` | 3 rows, all `unavailable` | none — `_pick_node` already returns `None` |

**Conclusion: XTTS-v2 is currently unreachable by every selection path, so the flip changes
nothing today.** ⚠ **But it arms two live traps for whoever next selects it** — the moment an
operator sets `is_default` or writes a selection row, **D-2** refuses the render outright and
**D-3** silently drops voice cloning. Both are latent, and neither is visible from the store.

### 5.4 Proven, not merely read — 3 tests, all passing

`ivgs-api/tests/test_api_model_export.py::TestWpIvgs04WhatTheReSentTtsCertificateDoesToTheStore`

- matching name -> **one row, updated in place**, `created=False`, same `ad01_id`, engine now `TTS`
- different name -> **INSERT**, `created=True`, and the pre-existing row's engine **verified unchanged**
- `XTTS-v2` -> engine flips to `TTS` while `state=APPROVED` and `enabled=True` are **kept**

⛔ **No production row was read-modified. Every one of these ran against
`ivgs_reconciliation_test`.** The live table is byte-identical before and after this package
(§7.4).

---

## §6 Tasks 4(b) and 4(c) — the proof, in the deployed image

### 6.1 (b) RESOLVE — against the live registry, not a test double ✅

`docker exec ivgs-fastapi` / `ivgs-celery-default`, image `v5.28.0-engine-domain`, module
resolved to `/app/shared/providers/client_registry.py`:

```
('voiceover_tts', 'coqui',  'xtts')   -> clients.coqui_client.CoquiClient
('voiceover_tts', 'kokoro', 'kokoro') -> clients.kokoro_client.KokoroClient
('voiceover_tts', 'tts',    'kokoro') -> clients.kokoro_client.KokoroClient
('voiceover_tts', 'tts',    'xtts')   -> clients.coqui_client.CoquiClient

kokoro-82m  engine=tts     family=kokoro  -> clients.kokoro_client.KokoroClient
XTTS-v2     engine=tts     family=xtts    -> clients.coqui_client.CoquiClient
kokoro-82m  engine=kokoro  family=kokoro  -> clients.kokoro_client.KokoroClient   [unchanged]
XTTS-v2     engine=coqui   family=xtts    -> clients.coqui_client.CoquiClient     [unchanged]

Bark-small  engine=tts  -> NoClientForFamilyError: ... no client for family 'bark-small'.
```

The deployed API also now advertises the value domain — read from the live
`/api/v1/openapi.json`, **no row written**:

```
ModelEngine: ['vllm','ollama','comfyui','coqui','kokoro','cogvideox','wan21','animatediff',
              'latentsync','sadtalker','remotion','ffmpeg','tts','magihuman','humo','wan22_s2v']
```

That closes WP-IVGS-03 §5.2's first deferred claim.

### 6.2 (c) RENDER — real audio from an `engine='tts'` binding, both families ✅

Run inside `ivgs-celery-default` (`v5.28.0-engine-domain`) against the **live** MBCP TTS
servers on node-04. The client was **not named by me** — it is whatever
`resolve_client` returned, imported from `spec.client_path`:

```
binding: name=kokoro-82m stage=voiceover_tts engine=tts  endpoint=http://192.168.1.93:5003
  registry resolved -> clients.kokoro_client.KokoroClient
  audio bytes       -> 235244
  RIFF/WAVE         -> channels=1 rate=24000 frames=117600 dur=4.90s

binding: name=XTTS-v2 stage=voiceover_tts engine=tts     endpoint=http://192.168.1.93:5002
  SAME stage, SAME engine=tts, family=xtts -> clients.coqui_client.CoquiClient
  audio bytes -> 182348 | channels=1 rate=24000 dur=3.80s
```

**Two families, one runtime engine name, two different clients, two different servers, real
audio from each.** This is the property an `engine -> client` alias could not have expressed,
demonstrated rather than argued.

### 6.3 ⛔ What 4(c) does NOT prove, stated plainly

1. **The endpoint was supplied by hand.** `resolve_endpoint('tts')` raises (**D-2**), so the
   binding could not source its own endpoint. **A pipeline render through an `engine='tts'`
   row still fails**, and this proof does not claim otherwise.
2. **`build_provider` was bypassed.** The client was constructed from `spec.client_path`
   because `_BUILDERS` has no `tts` key (**D-2 #3**).
3. **Stage 5 was not executed.** No Celery task ran, no job, no checkpoint. The proof covers
   *runtime name -> registry -> correct client -> real audio*; it does not cover the stage body,
   which is where **D-3** lives.
4. **No test project was created.** The order permitted one via the WP-59 flow. It would not
   have moved the blocked claim — D-2 blocks the pipeline path with or without a project — and
   creating a `models` row carrying `engine='tts'` in production is a live-data change beyond
   this package's authority. **Deliberately not done.**
5. **Not run on node-04.** node-04 still runs `v5.27.0-motion`, whose `ModelEngine` has no
   `TTS` member; a `models` row on `engine='tts'` would fail there at ORM load. §8.4.

---

## §7 Task 3 — images, versioning, deploy

### 7.1 Which images ship the change — the answer is api + workers, and it was measured

`COPY shared/` appears in **four** Dockerfiles, not two: `ivgs-api:32`, `ivgs-workers:30`,
`ivgs-scheduler:30`, `ivgs-backup-worker:70`. So the order's "api, workers, or both" is a
narrower menu than the tree offers. What the **running** images actually contain:

| Image | `model_store.py` (the enum) | `client_registry.py` | Imports either? |
|---|---|---|---|
| `ivgs-api` | ✅ | ✅ | **yes** — `ad01_ingest`, `selection_panel` |
| `ivgs-workers` | ✅ | ✅ | **yes** — `get_binding`, `build_provider`, `resolve_client` |
| `ivgs-scheduler` | ✅ (unused) | ❌ absent | **no** — zero imports |
| `ivgs-backup-worker` | ✅ (unused) | ❌ absent | **no** — zero imports |

The two absences are not a Dockerfile exclusion: both run `v5.19.0-surfaces2`, built before
WP-67 created `client_registry.py`. They are already versioned apart from api/workers in
`ivgs-infra/.env`, and they import neither module (`grep`: zero hits in either tree).

**Ruling applied: the coherent set is api + workers.** `ivgs-frontend` is a Node image with no
`COPY shared/` and stays at `v5.27.0-motion`; scheduler and backup-worker stay at
`v5.19.0-surfaces2`. Rebuilding them would drag unrelated drift for no functional gain.

### 7.2 Build, verified by content and not by exit code

```
ghcr.io/brucecostello2/ivgs-api:v5.28.0-engine-domain
ghcr.io/brucecostello2/ivgs-workers:v5.28.0-engine-domain
```

Both builds were fully cached (2.4s / 1.5s), so **the images were opened and checked** rather
than trusted — `dev/CLAUDE.md` §12, *"an exit code of 0 is not proof"*:

```
grep -c MBCP_TTS_RUNTIME_ENGINE /app/shared/providers/client_registry.py  -> 2   (both images)
grep -n 'TTS = ' /app/shared/models/model_store.py                        -> 120:    TTS = "tts"
```

Banked via `scripts/save-image-artifact.sh` (§6.1 artifact path, standard filename):

```
/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-api_v5.28.0-engine-domain.tar.zst      126358324 B
  f10a8126b4fdf8e3cb4da50e5d3a130af78718b1e9b1d6d05fb2cf2e7cb25900
/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.28.0-engine-domain.tar.zst  333367370 B
  0a9cef86c57276320f926359e3a5897c5849eacfdb60d401bbd972e739848e89
```

Both registered in `MANIFEST.txt`. No GHCR push — §6.1: never a precondition.

### 7.3 Migration 0042 against PRODUCTION — before and after, as ordered

```
BEFORE   alembic_version = 0041      pg_enum(model_engine) = 12 labels
         (a models + alembic_version dump was taken to the scratchpad first)

INFO  [alembic.runtime.migration] Running upgrade 0041 -> 0042,
      0042  add MBCP's four unnamed runtimes to the model_engine enum.

AFTER    alembic_version = 0042      pg_enum(model_engine) = 16 labels
  vllm ollama comfyui coqui kokoro cogvideox wan21 animatediff latentsync
  sadtalker remotion ffmpeg  tts magihuman humo wan22_s2v
```

**Twelve preserved in their original order, four appended.** Run from the new API image against
`postgres:5432/ivgs` on `ivgs-infra_ivgs-net`.

### 7.4 node-01 deploy, and what it did not disturb

Compose invocation **derived from container labels**, never guessed (§6):
`docker-compose.node01.yml` + `docker-compose.override.node01.yml` +
`docker-compose.monitoring.yml`, `--env-file ivgs-infra/.env`, project `ivgs-infra`,
**`--no-deps`**, `--pull never`.

```
ivgs-fastapi              ghcr.io/brucecostello2/ivgs-api:v5.28.0-engine-domain      Up (healthy)
ivgs-celery-default       ghcr.io/brucecostello2/ivgs-workers:v5.28.0-engine-domain  Up (healthy)
ivgs-celery-composition   ghcr.io/brucecostello2/ivgs-workers:v5.28.0-engine-domain  Up (healthy)
ivgs-celery-beat          ghcr.io/brucecostello2/ivgs-workers:v5.28.0-engine-domain  Up (healthy)
ivgs-postgres             postgres:17.2                                             Up 47 hours (healthy)
```

Postgres's 47-hour uptime is the evidence `--no-deps` held. `GET /api/v1/health -> 200`;
`celery inspect ping -> 4 nodes online`. `.env` backed up to the scratchpad before the tag bump.

**The `voiceover_tts` rows are byte-identical before and after the whole package** — re-read
after the deploy:

```
XTTS-v2    | coqui  | approved  | t | f
Kokoro     | coqui  | candidate | f | f
kokoro-82m | kokoro | approved  | t | t
```

### 7.5 A fleet correction worth recording

An early sweep in this session found nodes 02/03/04/05 unreachable on both ICMP and TCP, and I
reported a real render impossible. **That was a transient window, and it was wrong.** Re-measured:

| Node | ICMP | Celery | TTS |
|---|---|---|---|
| node-02 `.91` | UP | `celery-worker@node02` (`gpu_llm`) | — |
| node-03 `.92` | **DOWN** | absent | — |
| node-04 `.93` | UP | `image-worker@node04` (`gpu_image, gpu_tts, gpu_talking_head`) | `:5002` and `:5003` both **200**, routes `['/health','/tts_to_audio']` |
| node-05 `.94` | UP | none by design | — |

**node-03 is down** and its `cogvideox-worker` is not on the bus. Its block at §8.2 is authored
anyway and will simply not apply until it returns.

---

## §8 OPERATOR BLOCKS — authored, NOT run

⛔ **None of the blocks in this section were executed.** All are node-labelled, single,
self-gating, plain ASCII, no `exit` in an interactive shell, output ASCII-filtered (§5).

### 8.1 node-02 — worker image

```bash
# ===== NODE-02  192.168.1.91  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.28.0-engine-domain.tar.zst
  if [ ! -s "$A" ]; then echo "MISSING ARTIFACT: $A"; else
    ( cd "$(dirname $A)" && sha256sum -c "$(basename $A).sha256" ) &&
    zstd -d -c "$A" | sudo docker load &&
    sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.28.0-engine-domain/' ivgs-infra/.env &&
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node02.yml up -d --pull never --no-deps celery-worker &&
    sleep 8 &&
    sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -i celery
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

### 8.2 node-03 — worker image. **The service is `cogvideox-worker`.**

⚠ node-03 declares a `celery-worker` under `profiles: ["standby"]`
(`docker-compose.node03.yml:225-228`) which is **not running**. Naming it would start a second
worker competing for the same queues and leave the real one on the old image — `dev/CLAUDE.md`
§6.2, and WP-44 S6.3 recorded exactly that happening.

⚠ node-03 was **DOWN** when this was written (§7.5).

```bash
# ===== NODE-03  192.168.1.92  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.28.0-engine-domain.tar.zst
  if [ ! -s "$A" ]; then echo "MISSING ARTIFACT: $A"; else
    ( cd "$(dirname $A)" && sha256sum -c "$(basename $A).sha256" ) &&
    zstd -d -c "$A" | sudo docker load &&
    sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.28.0-engine-domain/' ivgs-infra/.env &&
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node03.yml up -d --pull never --no-deps cogvideox-worker &&
    sleep 8 &&
    sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -i cogvideox-worker
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

### 8.3 (4a) INGEST — what to check on the IVGS side after MBCP re-sends

⛔ **The re-send itself is yours and happens on `.51`.** This package did not touch `.51`,
`.52`, or any `pending_exports` row. Run this on node-01 **after** MBCP reports 2xx for
`b4e8c2e6-40cd-44b7-925d-b9277d4c1818`.

⚠ **Read §5.2 before interpreting the result.** The certificate carries `model_name="Kokoro"`,
so it lands on the **orphan** row. If `kokoro-82m` has changed, something other than this
certificate changed it.

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  docker exec ivgs-postgres psql -U ivgs -d ivgs -P pager=off -c \
   "select name, engine, state, enabled, is_default, weights_checksum, updated_at
      from models where stage='voiceover_tts' order by created_at;"
  echo '--- attestations, newest first (a re-send appends one) ---'
  docker exec ivgs-postgres psql -U ivgs -d ivgs -P pager=off -c \
   "select m.name, a.vetting_reference, a.attested_by, a.created_at
      from model_approvals a join models m on m.id=a.model_id
     where m.stage='voiceover_tts' order by a.created_at desc limit 6;"
  echo '--- artifact fields on the row the certificate targets ---'
  docker exec ivgs-postgres psql -U ivgs -d ivgs -P pager=off -c \
   "select name, weights_ref, weights_checksum, vram_gb, license,
           default_params->'_unknown_export_fields' as unknown_fields
      from models where name='Kokoro';"
  echo '--- the rendering row MUST be unchanged: engine kokoro, approved, default ---'
  docker exec ivgs-postgres psql -U ivgs -d ivgs -P pager=off -tAc \
   "select case when engine='kokoro' and is_default and enabled
                then 'OK  kokoro-82m untouched'
                else 'CHANGED -- investigate, this certificate should not reach it' end
      from models where name='kokoro-82m';"
  echo '--- unknown-field warnings (seam drift; MBCP now sends bundle_version + bundle_link_basis) ---'
  docker logs --since 30m ivgs-fastapi 2>&1 | grep -c ad01_export_unknown_fields
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

ⓘ Expect `ad01_export_unknown_fields` to be non-zero: MBCP's `ExportBundle` now carries
`bundle_version` and `bundle_link_basis` (`mbcp_core/schemas/export.py`, `origin/main`) and
`ExportBundleIn` has neither. They are recorded, not dropped (WP-53) — but the seam has drifted
again and that is worth a look.

### 8.4 (4c) node-04 — deploy, then the pipeline-level render

⛔ **STAGED, NOT RUNNABLE AS IT STANDS.** Part 2 **will fail** at
`EndpointResolutionError: no endpoint mapping for engine 'tts'` until **D-2 (§3)** is lifted,
which this package was instructed not to do. Part 1 is runnable now and is worth doing on its
own — it brings node-04 onto the same image as node-01.

⚠ node-04's `celery-worker` has `depends_on: [comfyui]` (`docker-compose.node04.yml:83`), so
**`--no-deps` is not optional** — without it the recreate restarts ComfyUI too.

```bash
# ===== NODE-04  192.168.1.93  =====  PART 1 of 2 - deploy (runnable now)
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.28.0-engine-domain.tar.zst
  if [ ! -s "$A" ]; then echo "MISSING ARTIFACT: $A"; else
    ( cd "$(dirname $A)" && sha256sum -c "$(basename $A).sha256" ) &&
    zstd -d -c "$A" | sudo docker load &&
    sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.28.0-engine-domain/' ivgs-infra/.env &&
    sudo docker compose --env-file ivgs-infra/.env \
      -f ivgs-infra/docker-compose.node04.yml up -d --pull never --no-deps celery-worker &&
    sleep 8 &&
    sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -E 'celery-node04|comfyui' &&
    echo '--- the enum must now name tts, or the row cannot even load ---' &&
    sudo docker exec ivgs-celery-node04 python -c \
      "from shared.models.model_store import ModelEngine; print('TTS' in ModelEngine.__members__)"
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

```bash
# ===== NODE-04  192.168.1.93  =====  PART 2 of 2 - the render seam
# EXPECTED TO FAIL AT STEP 2 UNTIL D-2 IS LIFTED. Run it anyway: the refusal is
# the measurement, and it names the exact missing map entry.
( set -u
  sudo docker exec ivgs-celery-node04 python -c "
import uuid
from shared.providers.binding import ModelBinding, resolve_endpoint
from shared.providers.client_registry import resolve_client, family_of
from shared.providers.factory import build_provider, registered_engines
from providers import ensure_registered
ensure_registered()

b = ModelBinding(model_id=uuid.uuid4(), name='Kokoro', display_name='Kokoro',
                 stage='voiceover_tts', engine='tts', tier='production',
                 endpoint='http://ivgs-kokoro:5003')

print('1. registry  ->', resolve_client(b).client_path, '(family', family_of(b) + ')')

try:
    print('2. endpoint  ->', resolve_endpoint('tts', stage='voiceover_tts'))
except Exception as e:
    print('2. endpoint  -> D-2 STILL OPEN:', type(e).__name__ + ':', e)

try:
    print('3. provider  ->', type(build_provider(b)).__name__)
except Exception as e:
    print('3. provider  -> D-2 STILL OPEN:', type(e).__name__ + ':', e)
    print('   registered engines:', registered_engines())
"
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

ⓘ **Steps 2 and 3 are precisely what D-2 costs.** Step 1 already passes — that is this
package's contribution, and §6.2 shows it produces real audio once an endpoint is supplied.

---

## §9 What I did NOT verify — plainly, in the order it matters

1. ⛔ **No pipeline-level render through an `engine='tts'` row.** Blocked by **D-2**, twice
   over (endpoint, then builder), and additionally by node-04 running `v5.27.0-motion`. §6.3
   lists every step the §6.2 proof does **not** cover. The audio is real; the *stage* was not run.
2. ⛔ **4(a) not performed and not observed.** MBCP's re-send of
   `b4e8c2e6-40cd-44b7-925d-b9277d4c1818` is a two-sided operator action on `.51`. **No
   `pending_exports` row was read or modified; `.51` and `.52` were not touched.** Everything in
   §5 about what the certificate *will* do is derived from committed code plus tests against the
   test database — **not from an observed live ingest.**
3. ⛔ **Nodes 02, 03 and 04 were not deployed.** Blocks authored (§8), none run. node-04
   therefore still cannot load a `models` row carrying `engine='tts'`.
4. ⚠ **D-3 (§4) is reasoned from code, not executed.** The dual-dispatch at
   `coqui_client.py:243` and the dropped `speaker_wav`/`temperature` were read, and the
   parameter sets compared field by field. **I did not run a render with an inline
   `speaker_wav_data` to watch the voice change.** The mechanism is certain; the audible
   consequence is inferred.
5. ⚠ **No test project was created and none deleted.** §6.3(4) explains why. The WP-59 delete
   flow was located (`ivgs-api/app/api/v1/projects.py:266`, admin + `confirm_name`) but **not
   exercised**.
6. **`magihuman` / `humo` remain inferred, not measured** — WP-IVGS-03 §7.2 carries this, and
   nothing here changed it. MBCP's live database on `.51` was not read for anything.
7. **`/opt/MBCP`'s working tree was not checked out or modified.** Every MBCP fact is from
   `git show origin/main:<path>` / `git grep origin/main`. The clone remains ~378 commits behind
   on disk, as WP-IVGS-03 found it.
8. **`tests_system`, `ivgs-scheduler` and `ivgs-backup-worker` suites were not re-run.** The
   change is in `shared/providers/`, which neither the scheduler nor the backup worker imports
   (§7.1); `tests_system` was not touched. Their baseline rows are carried forward unverified.
9. ⚠ **A fleet claim I made earlier in this session was wrong and is corrected in §7.5**, not
   quietly dropped: I reported every GPU node unreachable and a real render impossible. That was
   a transient outage window. The nodes came back and the render was performed.

---

## §10 Ledger — what this package opens

| id | What | Where | Status |
|---|---|---|---|
| **D-1** | Runtime engine name has no client | `client_registry.py` | ✅ **CLOSED** by this package |
| **D-2** | `tts` misses `_ENGINE_ENDPOINTS` and `_BUILDERS`, both keyed on engine alone | `binding.py:22-46`, `factory.py:44` | ⛔ **OPEN** — operator ruled "report only". Needs a design decision, not two lines (§3) |
| **D-3** | `engine == "coqui"` is a silent branch; the flip drops `speaker_wav` + `temperature` with no error | `stage5_voiceover.py:364` | ⛔ **OPEN** — frozen stage body (§4). Belongs in `WP-00-SWALLOWED-FAILURES` |
| **D-4** | MBCP's name `Kokoro` and IVGS's rendering row `kokoro-82m` are different rows; the orphan is what gets certified | store + `ad01_ingest.py:150` | ⛔ **OPEN** — AD-10 §5.2, not deduplicated as instructed (§5.2) |
| **D-5** | Seam drift: MBCP now sends `bundle_version`, `bundle_link_basis`; `ExportBundleIn` has neither | `mbcp_core/schemas/export.py` vs `schemas/model_store.py:79-96` | ⚠ **NOTED** — recorded not dropped (WP-53's `extra="allow"`), but the contract moved again |

---

## §11 Push block — count-gated

⛔ **NOT PUSHED. `dev/CLAUDE.md` §1: the operator holds sole merge authority.** One commit,
plus this report.

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  N=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $N"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$N" -eq 2 ]; then
    git push origin main && echo "PUSHED"
  else
    echo "REFUSING: expected exactly 2 (the fix + this report), found $N."
    echo "Inspect the list above before pushing anything."
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

| Commit | |
|---|---|
| `0c49444` | `fix(wp-ivgs-04): the runtime name MBCP sends now resolves, per family` |
| *(pending)* | `docs(wp-ivgs-04): report` |

**Committed and held. Not pushed. node-01 deployed; nodes 02/03/04 authored only. No live row
changed. No gate pressed. `.51`, `.52`, NODE-05 and NODE-06 untouched.**

---
---

# ADDENDUM — D-2 and D-3 closed, and the pipeline render proven

**2026-08-28, second session. Two operator rulings, both recorded at §A0.**
Supersedes §3, §4 and §6.3 above; §10's ledger is restated at §A8.

## §A0 The two rulings, and the conditions attached

**1. D-2 — fix it.** Reversing the earlier *"report only"*.

**2. D-3 — the stage-body freeze lifted, NARROWLY.** Operator's reasoning, recorded as a ruling:
*"D-2's fix converts a hard failure into a silent one, and shipping that to the fleet is worse
than shipping nothing. That justifies the exception."* Conditions: the edit is confined to the
branch condition; no refactor, no cleanup while the file is open; show the diff; **stop and ask
rather than widening if the correct fix needs more than that branch.**

⚠ **It needed two lines, not one, and that was flagged before the edit rather than absorbed.**
The condition cannot reach `family_of` without an import. Nothing else in the file is touched:

```diff
+from shared.providers.client_registry import family_of
...
-        if tts_binding.engine == "coqui":
+        if family_of(tts_binding) == "xtts":
```

`1 file changed, 2 insertions(+), 1 deletion(-)` — the whole diff.

**3. node-01-only confinement lifted** for nodes 02/03/04 (*"that was for unattended running; I am
here"*). NODE-05 and NODE-06 remain out of bounds and were not touched.

---

## §A1 ⛔ CORRECTION — §4's account of D-3 was overstated

**§4 above says the narrow branch silently disables voice cloning and yields "a valid WAV in the
wrong voice". That is wrong, and it was wrong when written.** Measured on the wire:

```
rich branch   -> {'speaker_wav': '/ref/actor.wav', 'temperature': 0.31, 'top_k': 50, ...}
narrow branch -> {'speaker_wav': '/ref/actor.wav', 'temperature': 0.75, 'top_k': 50, ...}
DELTA on the wire: {'temperature': (0.31, 0.75)}
```

`coqui_client.py:204` sends **`params.speaker_wav_path or ""`**. That path is set on BOTH
branches — the rich one from `task_input.speaker_wav_path`, the narrow one from
`TTSParams.speaker_wav`, which stage 5 populates from the *same* field. **The reference voice
survives the narrow branch. The only on-wire loss was `temperature`.**

What misled me: `CoquiSynthesisParams.speaker_wav` (inline `bytes`) has no equivalent on
`TTSParams`, so a field-name comparison shows a loss. But that field **is never transmitted by
any branch** — see D-6 below. The earlier reading confused "dropped between the two params
objects" with "dropped from the request".

⚠ **And the real-world impact of the surviving delta is currently ZERO** — see §A5. The fix is
still correct, and I would still make it; but it corrected an honesty defect in the code, not an
active production fault. Claiming otherwise would be the thing this report exists to avoid.

---

## §A2 D-2 — what was built

### A2.1 Endpoints: an ALIAS, not a second table of URLs

`shared/providers/binding.py`. `_ENGINE_ENDPOINTS` is keyed on the engine alone, and `tts` serves
two families on two different servers, so there is **no single right answer** to
`resolve_endpoint("tts")`.

Copying the two URLs into a `(engine, family)` table would have answered it and created the
defect this module already guards against: **two definitions of where Kokoro serves**, free to
drift, with node-04's `IVGS_KOKORO_URL` updating only one. So the runtime name resolves
**through** the entry that already exists:

```python
_RUNTIME_FAMILY_ALIASES: dict[tuple[str, str], str] = {
    ("tts", "kokoro"): "kokoro",
    ("tts", "xtts"):   "coqui",
}
```

**The property this buys, asserted by test rather than assumed:**
`resolve_endpoint("tts", family="kokoro") == resolve_endpoint("kokoro")`, always.

⛔ **A runtime name with no family REFUSES BY NAME.** It must never pick one — that would send
Kokoro's text to XTTS's server and return plausible audio in the wrong voice.

### A2.2 Providers: the builder asks the registry

`ivgs-workers/providers/tts.py`. `_BUILDERS` is also engine-keyed, so one `tts` builder serves
both families — **by asking `resolve_client`**, not by branching on name or stage.
`providers/image.py:31-51` is the chain-of-ifs pattern being avoided. It **reuses**
`build_coqui`/`build_kokoro`, so there is no second construction path and Coqui keeps its ARCH-1
`fallback_url=None` (pinned by test).

### A2.3 `factory.py` passes the family

`_binding_from_model` now derives the family with the same `family_of` the registry uses, so the
endpoint and the client can never disagree about which family a row is.

---

## §A3 Deploy — the whole fleet, and what it did NOT disturb

`v5.28.1-engine-domain`, api + workers, built and **verified by opening the images** (both builds
were cached, so an exit code proved nothing):

```
grep -c _RUNTIME_FAMILY_ALIASES /app/shared/providers/binding.py   -> 4   (api and workers)
grep -n 'family_of(tts_binding)' /app/tasks/stage5_voiceover.py    -> 365: if family_of(tts_binding) == "xtts":
grep -c 'register_engine_builder("tts"' /app/providers/tts.py      -> 1
```

Banked as artifacts with checksums, then loaded on each node from the shared store — no GHCR.

| Node | Service | Result |
|---|---|---|
| node-01 | fastapi-backend + 3 workers | `v5.28.1`, healthy. Postgres **Up 2 days** — `--no-deps` held |
| node-02 | `celery-worker` | `ivgs-celery-node02` on `v5.28.1` |
| node-03 | **`cogvideox-worker`** | `ivgs-cogvideox-worker-node03` `v5.27.0-motion` -> `v5.28.1`. ⚠ Only it moved; the `profiles: ["standby"]` `celery-worker` was **not** started (CLAUDE.md §6.2) |
| node-04 | `celery-worker` | `ivgs-celery-node04` on `v5.28.1`. ⚠ ComfyUI, kokoro and coqui all still **"Up About an hour"** — `--no-deps` held against `depends_on: [comfyui]` |

**D-2 verified on node-04 against its REAL configuration**, which is the point of the alias
design — zero config change was needed:

```
tts/kokoro  -> http://ivgs-kokoro:5003
tts/xtts    -> http://ivgs-coqui:5002
engines: ('cogvideox','comfyui','coqui','kokoro','latentsync','sadtalker','tts','vllm')
```

---

## §A4 The pipeline render — a real Stage 5 task, on node-04, through `engine='tts'`

Fixtures, all disposable and all since deleted: one project, **two new `models` rows carrying
`engine='tts'`**, one project-scoped selection, one storyboard scene, one render job. **No
existing row was modified at any point.**

⚠ **The first attempt failed, and that is recorded rather than smoothed over.** It failed at the
asset-upload FK (`scene_id ... is not present in storyboard_scenes`) and then the checkpoint
404 — both my incomplete fixture, neither the change. It is worth reading because it shows the
seam already worked: `model_bound -> wpivgs04-xtts-testrow`, `synthesizing_voiceover` ->
1.0 s -> `normalizing_audio` -> `validating_audio`, and 941,766 bytes reached SeaweedFS.

ⓘ I also hit the `docker exec` heredoc trap on the way — a fixture INSERT reported success and
inserted nothing, because `-i` was missing. `dev/CLAUDE.md` §7 documents exactly this; the
project's own notes caught it.

**The clean run:**

```json
"model_used": "wpivgs04-xtts-testrow",     "status": "success",
"asset_id": "9b22d22a-a2db-4b1e-a947-1c65d61446c1",
"file_size_bytes": 868038,  "duration_seconds": 6.027,
"sample_rate": 48000,  "bit_depth": 24,
"quality_score": 1.0,  "quality_decision": "approved",  "snr_db": 101.34,
"successful_count": 1, "failed_count": 0
```

A real Celery task, routed to `gpu_tts`, executed by `image-worker@node04`, resolving a model row
whose engine is `tts`, producing validated 48 kHz/24-bit audio persisted to SeaweedFS.

ⓘ The GPU reservation failed open as designed (`gpu_reservation_unavailable ... fail_open=True`),
on a **pre-existing** scheduler fault: `unsupported operand type(s) for /: 'NoneType' and 'float'`
— HTTP 500 from `:8002/schedule`, unrelated to this package but worth a look.

---

## §A5 Acceptance — the voice verified, the temperature NOT

The operator's condition: *"verify the voice, not the bytes ... if you cannot verify voice
identity by any means available on this fleet, say so plainly and report the render as
UNVERIFIED rather than claiming it."*

### A5.1 ✅ Do the parameters reach the client? — PROVEN

The **real** `_process_single_voiceover` on node-04, with a recording provider (the branch is
real; only the transport is not):

| row | engine | branch | temperature handed to client |
|---|---|---|---|
| `wpivgs04-xtts-testrow` | **tts** | **RICH** | **0.31** |
| `XTTS-v2` | coqui | RICH | 0.31 — identical |
| `kokoro-82m` | tts | NARROW | n/a — **the control**, unchanged either way |

### A5.2 ✅ Is it the same voice? — PROVEN, against a real reference clip

Long-term average spectrum cosine similarity, renders made through the deployed client on
node-04, reference `/mnt/ivgs-shared/wp42-voice-ab/kokoro_short_scene17_en-US.wav`:

| comparison | similarity |
|---|---|
| cloned `engine='tts'` vs cloned `engine='coqui'` | **0.98488** |
| cloned `engine='tts'` vs the DEFAULT speaker | 0.73508 |
| cloned `engine='coqui'` vs the DEFAULT speaker | 0.71832 |

**This discriminates.** The reference clip demonstrably moves the voice (0.72–0.74 away from the
built-in speaker), and the two engine values land on **each other** at 0.985 — with byte-identical
output lengths (258,124 both). The engine value does not change the voice.

### A5.3 ⛔ Does `temperature` change the audio? — **UNVERIFIED, because it CANNOT**

Reported as the operator required rather than claimed. The behavioural test **failed to
discriminate**:

```
intra-pair LTAS similarity @ temp=0.05 : 0.92024
intra-pair LTAS similarity @ temp=0.99 : 0.95473
-> low-temp renders are NOT more self-consistent
```

**The reason is not measurement weakness. The server discards the parameter.** `ivgs-coqui`'s
`/app/server.py`:

```python
kwargs = {"text": req.text, "language": _lang(req.language), "speed": req.speed}
...
tts.tts_to_file(file_path=out_path, **kwargs)
```

`TTSRequest` declares `temperature`, `length_penalty`, `repetition_penalty`, `top_k` and `top_p`
— and **none of them is passed to the model.** The server's own comment says they are *"accepted
(XTTS defaults match these)"*.

⛔ **So D-3's live impact today is ZERO**, and §4's severity was overstated twice over. The fix
remains right — the code now says what it does, and the defect would bite the moment the server
honours the parameter — but **no audible defect was fixed, and none is claimed.**

---

## §A6 Tests and baseline

| Tree | Result | Baseline | Delta |
|---|---|---|---|
| `ivgs-api` | **1395 passed, 0 failed** | 1359 / 0 | +36 tests, **0 failures** |
| `ivgs-workers` | **916 passed**, 18 failed, 48 skipped, 15 errors | 903 / 18 / 48 / 15 | +13 tests, **failure counts identical** |

**ZERO NEW FAILURES.** Two full-suite runs used, the limit.

New: 18 endpoint tests (every pre-existing engine pinned to resolve *exactly* as before), 13
builder + D-3 tests. ⚠ **One of my own new tests asserted something false and was corrected**:
it claimed `TTSParams` cannot carry `speaker_wav`. It can — as a `str` path, where the rich
object has `bytes`. The corrected test pins the *type* difference, which is the actual trap and
is what a name-only comparison misses. That correction is what exposed §A1.

---

## §A7 Teardown — nothing of mine remains

```
projects=0   test_models=0   orphan_assets=0    seaweedfs delete -> 200
```

The three live `voiceover_tts` rows are **byte-identical to their state before this package
began**, re-read after teardown:

```
XTTS-v2    | coqui  | approved  | t | f
Kokoro     | coqui  | candidate | f | f
kokoro-82m | kokoro | approved  | t | t
```

**15 projects remain** — the operator's and every other existing project untouched.

---

## §A7a ⛔ OPERATOR RULING ON THE FREEZE EXCEPTION — recorded 2026-08-28

**A frozen stage body was opened for a defect that measured cosmetic.**

The exception at §A0 was granted on my premise that D-2's fix would convert a hard failure into
a silent wrong-voice one. **That premise was wrong.** `speaker_wav_path` was sent by both
branches (§A1), and `temperature` cannot have an audible effect because `ivgs-coqui`'s server
declares it and passes it to nothing (§A5.3). The two-line edit stands and the code is now
honest, but the justification for opening the file did not survive measurement.

⚠ **The rule this leaves behind, in the operator's words: next time that argument is made, we
need to know it was CHECKED TO THE WIRE, not reasoned from code.** A severity claim that opens a
frozen file must be measured at the boundary it claims to cross, before the exception is
requested — not after the edit has shipped. **This is not a precedent.**

## §A7b Design note worth reusing — the alias that needed no configuration

Resolving `tts` **through the entry that already defines where each family serves**, rather than
into a second URL table, required **zero configuration change on node-04**: its existing
`IVGS_KOKORO_URL` and `IVGS_COQUI_URL` drove the new runtime name unchanged.

`IVGS_TTS_URL` had been assumed inevitable — by me in §3, which states flatly that no
environment variable could work around D-2. That was true of the *shape* the fix was assumed to
take and false of the fix that was built. **The reason it was avoidable: one definition cannot
drift from itself.** A second table would have answered the question and introduced a second
place for Kokoro's address to live.

## §A8 Ledger, restated

| id | What | Status |
|---|---|---|
| **D-1** | Runtime engine name has no client | ✅ CLOSED (Task 1) |
| **D-2** | `tts` misses `_ENGINE_ENDPOINTS` and `_BUILDERS` | ✅ **CLOSED** — alias + registry-delegating builder, proven on node-04 |
| **D-3** | Branch keyed on the engine string | ✅ **CLOSED** — two lines, under the operator's narrow exception. ⚠ Severity was overstated; live impact is zero (§A5.3) |
| **D-4** | `Kokoro` vs `kokoro-82m` are different rows | ⛔ OPEN — AD-10 §5.2 |
| **D-5** | Seam drift: `bundle_version`, `bundle_link_basis` unmodelled | ⚠ NOTED |
| **D-6** | `CoquiSynthesisParams.speaker_wav` (inline bytes) is **never transmitted** — `coqui_client.py:204` sends only the path. An operator supplying inline speaker audio with no path gets the default voice, silently, on every branch | ⛔ **NEW, OPEN** — pre-existing, not introduced here |
| **D-7** | `ivgs-coqui` accepts five XTTS sampling parameters and passes none to the model (`server.py`). The client sends them; the server drops them | ⛔ **NEW, OPEN** — engine-side |
| **D-8** | GPU scheduler 500: `unsupported operand type(s) for /: 'NoneType' and 'float'` on `POST :8002/schedule`; every TTS render fails open unreserved | ⛔ **NEW, OPEN** — pre-existing |

---

## §A9 ⚠ The gating condition for MBCP's re-send

**With D-2 and D-3 closed, XTTS-v2's row can flip to `engine='tts'` and still render correctly** —
that was the last barrier. As the operator required, **confirm the whole chain is green BEFORE
the re-send is scheduled, not after.** Run §8.3's block plus this, on node-01:

```bash
# ===== NODE-01  192.168.1.90  =====  green-light check, run BEFORE scheduling the re-send
( set -u
  echo "--- 1. every node on the new image ---"
  docker exec ivgs-celery-default celery -A celery_app inspect ping --timeout 10 2>&1 | grep -cE '^->'
  echo "--- 2. the enum names tts in production ---"
  docker exec ivgs-postgres psql -U ivgs -d ivgs -tAc \
    "select count(*) from pg_enum where enumtypid='model_engine'::regtype and enumlabel='tts';"
  echo "--- 3. resolve + build, on the node that runs TTS ---"
  ssh root@192.168.1.93 "docker exec ivgs-celery-node04 python -c \"
from shared.providers.binding import resolve_endpoint
from shared.providers.client_registry import resolve_client
from shared.providers.factory import build_provider
from shared.providers.binding import ModelBinding
from providers import ensure_registered; ensure_registered()
import uuid
for n,f in (('XTTS-v2','xtts'),('kokoro-82m','kokoro')):
    b=ModelBinding(model_id=uuid.uuid4(),name=n,display_name=n,stage='voiceover_tts',
                   engine='tts',tier='production',endpoint=resolve_endpoint('tts',family=f))
    print(' ', n, '->', resolve_client(b).client_path, '@', b.endpoint,
          '->', type(build_provider(b)).__name__)
\""
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

Expect `5`, `1`, and both rows resolving to their own client and endpoint. ⛔ **If any line
differs, do not schedule the re-send.**

---

## §A10 What I did NOT verify — addendum

1. ⛔ **`temperature` has no demonstrable effect on the audio, and cannot** (§A5.3). Reported
   UNVERIFIED, as instructed. What IS proven is that it reaches the client.
2. ⛔ **Voice cloning was verified with a SHARED-PATH reference clip.** `ivgs-coqui` resolves
   `speaker_wav` as a path **on the server** and falls back to the built-in speaker if it is not
   readable there. `/mnt/ivgs-shared` is mounted in that container, so a shared path works — **a
   node-01-local path would silently fall back.** I did not test that failure mode.
3. ⛔ **4(a) still not performed.** No `pending_exports` row touched; `.51`/`.52` untouched. The
   §A9 block is the pre-flight, not the ingest.
4. ⚠ **The render used my own test rows, not `XTTS-v2` or `kokoro-82m`.** Their live engine values
   were never changed. The rows were name-matched to the same families, so they exercise the same
   registry and endpoint entries — but they are not the production rows.
5. **`tests_system`, `ivgs-scheduler`, `ivgs-backup-worker` suites not re-run** (unchanged trees).
6. **Kokoro through the full pipeline was not run** — only through the recorder and the direct
   client. It is the control for D-3, not the subject.
7. **D-6, D-7 and D-8 are reported, not fixed**, and none is in this package's scope.

---

## §A11 Push block — count-gated, superseding §11

⛔ **NOT PUSHED.**

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  N=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $N"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$N" -eq 4 ]; then
    git push origin main && echo "PUSHED"
  else
    echo "REFUSING: expected exactly 4, found $N. Inspect the list above."
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

| Commit | |
|---|---|
| `0c49444` | `fix(wp-ivgs-04): the runtime name MBCP sends now resolves, per family` |
| `2cf50c9` | `docs(wp-ivgs-04): report — the premise that did not survive measurement` |
| `e343692` | `fix(wp-ivgs-04): D-2 and D-3 — endpoint, provider, and the right call shape` |
| *(pending)* | `docs(wp-ivgs-04): addendum — the render proven, and two corrections` |

**Fleet on `v5.28.1-engine-domain` (nodes 01–04). Production at alembic 0042. No live row
changed. No gate pressed. NODE-05, NODE-06, `.51` and `.52` untouched. Committed and held.**
