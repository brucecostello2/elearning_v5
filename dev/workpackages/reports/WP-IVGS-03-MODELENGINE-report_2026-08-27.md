# WP-IVGS-03 — `ModelEngine` value domain

**Report · 2026-08-27 · written as the work proceeded (pass 1 = findings, pass 2 = what changed)**
Work package: `dev/workpackages/WP-IVGS-03_ModelEngine_Value_Domain.md` — **rev 2** (header verified before starting).

---

## §0 Conventions and conflicts declared up front

`dev/CLAUDE.md` exists and was read in full before starting. Two clauses conflict with the
operator's session order. Both were reported to the operator rather than resolved silently, and
the operator's explicit instruction was followed in each case:

| `dev/CLAUDE.md` | Session order | Followed |
|---|---|---|
| §1 Authority — *"Claude does NOT commit, push, merge, or deploy."* | *"Commit and HOLD."* (also WP §8: *"Commit and hold. The operator pushes."*) | **Commit only.** No push, no deploy, no service restart. |
| §12 Reports — *"Two passes: findings and proposed fix BEFORE writing code (stop and show the operator)"* | *"Read it in full and execute it"* + *"Write your report AS YOU GO"* | **Findings pass written to this file before any code change** (this §0–§2), then executed in the same session rather than stopping. |

Everything else in `dev/CLAUDE.md` was complied with: node-labelled commands, ground-truth
verification over documentation, `file:line` citations, and explicit separation of what was
observed live from what was inferred from reading code.

---

## §1 The authoritative engine list, and how it was derived

### 1.1 The WP's prescribed derivation is wrong. Its answer is right.

§5.1 instructs: *"Establish MBCP's real set of engine values from MBCP's own source — `adapter_key`
on each class in `mbcp_adapters/`."*

**`adapter_key` is not the engine value.** Measured on MBCP `origin/main`, the ten registered
adapter keys are (`mbcp_core/adapters/registry_map.py:36-58`, `ADAPTER_IMPL_BY_KEY`):

```
latentsync  wan22_s2v  magihuman  humo  vllm_refiner  vllm_translator
vllm_storyboard  comfyui  tts_coqui  ffmpeg_composition
```

The TTS adapter's key is **`tts_coqui`**, not `tts` (`mbcp_adapters/tts_server.py:59`). The
composition adapter's key is **`ffmpeg_composition`**, not `ffmpeg`
(`mbcp_adapters/ffmpeg_composition.py:83`). Three separate vLLM text adapters carry three distinct
keys, and IVGS expresses all three as one engine, `vllm`.

Had the prescribed method been followed literally, it would have produced a **different and wrong**
list — proposing `tts_coqui`, `ffmpeg_composition`, `vllm_refiner`, `vllm_translator` and
`vllm_storyboard` as enum values, three of which duplicate `vllm` and one of which duplicates the
already-present `ffmpeg`. **Per §5.1 (*"your measurement wins"*), the derivation below was used
instead.**

### 1.2 The correct derivation: where MBCP actually writes `models.engine`

`engine` is a plain column, **`String(64)`, `nullable=False`, with no enum and no CHECK constraint**
(`mbcp_core/models/model.py:33`). It is set as free text by the caller at seed/onboarding time
(`mbcp_api/api/v1/onboarding.py:336` — `engine=body.engine`; `mbcp_api/api/v1/models.py:607`) and
travels to the wire unchanged as `AD01Export`'s `engine` field
(`mbcp_core/schemas/export.py:90` — `engine: str | None = None`).

So the authoritative set is **every literal MBCP writes into that column in non-test source**,
cross-checked against the adapter registry and the committed engine recipe directories.

**The full set — eight values:**

| # | `engine` value | Producer (MBCP `origin/main`) | Models | In IVGS `ModelEngine`? |
|---|---|---|---|---|
| 1 | `vllm` | `scripts/seed_stage.py:172` | Llama-3.3-70B-Instruct | ✅ yes |
| 2 | `comfyui` | `scripts/seed_stage.py:183,239,272,303,336,380` | FLUX.1-dev, FLUX.1-schnell, SDXL-base-1.0, SD3.5-medium, CogVideoX-5b, AnimateDiff-SD15 | ✅ yes |
| 3 | `ffmpeg` | `scripts/seed_stage.py:419` | FFmpeg-composition | ✅ yes (added by `e613e84`/`0027`) |
| 4 | `latentsync` | `scripts/ops/seed_latentsync_cell.py:59` | LatentSync | ✅ yes |
| 5 | **`tts`** | `scripts/seed_stage.py:543` and `:576` | **XTTS-v2, Kokoro** | ❌ **MISSING** |
| 6 | **`wan22_s2v`** | `scripts/ops/seed_wan22_cell.py:39` | Wan2.2-S2V-14B | ❌ **MISSING** |
| 7 | **`magihuman`** | inferred — see 1.3 | davinci-magihuman | ❌ **MISSING** |
| 8 | **`humo`** | inferred — see 1.3 | humo-17B | ❌ **MISSING** |

**Four of eight are expressible; four are not.** This independently confirms WP §2's headline
count and §5.1's four-value list — reached by a different route, which is the stronger result.

### 1.3 What is measured and what is inferred

- Values 1–6 are **measured**: each is a string literal in committed MBCP source, cited above.
- Values 7–8 (`magihuman`, `humo`) are **inferred, not measured.** Their `models` rows predate the
  current source (`scripts/seed_magihuman_adapter.py:4`, `scripts/seed_humo_adapter.py:4` both state
  the row already existed), and their `engine` column lives in MBCP's live database on `.51`, which
  this package does not touch and cannot read. The inference rests on MBCP's own convention for
  `engine_only` remote-engine adapters, which is **`engine == adapter_key`** and holds for both
  measurable cases: `latentsync` → `engine="latentsync"`, `wan22_s2v` → `engine="wan22_s2v"`. Both
  are `engine_only = True` (`mbcp_adapters/latentsync.py:47`, `wan22_s2v.py:54`), exactly as
  `magihuman` (`magihuman.py:152`) and `humo` (`humo.py:112`) are. WP §2 asserts the same two values
  from MBCP's side independently. **Two sources agree; neither is a direct read of the row.**

### 1.4 MBCP's clone was stale — how stale, and what was done

`/opt/MBCP` is the read-only reference clone (`dev/CLAUDE.md` §11). Its checkout was at
`ea7f91e` (2026-08-05) and **348 commits behind `origin/main`**. A `git fetch origin` advanced the
remote ref to `211afbf`, at which point the working tree measured **378 commits behind**.

⛔ **The clone's working tree was deliberately NOT checked out or otherwise modified** — §11 makes it
read-only. Every MBCP fact in this report was read from `origin/main` via `git show origin/main:<path>`
and `git grep origin/main`, never from the stale working tree. **Reading the working tree would have
produced the wrong answer:** it predates `magihuman.py`, `humo.py`, `wan22_s2v.py` and the whole
`mbcp_adapters/runtimes/` substrate.

---

## §2 §5.4 — the version diagnosis, done BEFORE building anything

**Result: none of the three cases §5.4 anticipated. The routes exist, at a different prefix, and
two of the three already work through the ingress today. Nothing was built.**

### 2.1 Direct against the container, bypassing nginx — node-01, `192.168.1.90:8001`

```
/health          404
/version         404
/openapi.json    404
```

**All three 404 on the container too.** The 404 is therefore **not** nginx, contrary to §5.4's
stated expectation. Mapping the actual surface:

```
/                      200      {"name":"IVGS v5 API","version":"5.0.0","status":"operational","docs":"/api/v1/docs"}
/api/v1/health         200      exists  (ivgs-api/app/api/v1/health.py:40)
/api/v1/openapi.json   200      exists
/api/v1/docs           200      exists
/api/v1/version        404      does not exist
```

`grep -rn 'get("/version"' --include=*.py ivgs-api/ shared/` returns **nothing**. There is no
`/version` route at any prefix.

### 2.2 Through the ingress — node-01, `https://192.168.1.90`

```
/health                  200     <-- nginx's OWN stub: body is {"status":"ok"}
/version                 404
/openapi.json            404
/api/v1/health           200     <-- the real API, reachable through the ingress TODAY
/api/v1/openapi.json     200     <-- likewise
```

### 2.3 Which case this is

| §5.4's case | Found? |
|---|---|
| 1 — routes exist on the container, gap is ingress → operator nginx change | **Partly.** `/health` and `/openapi.json` exist, but at `/api/v1/…`, and **already reach through the ingress unchanged. No nginx change is needed for them.** The investigation's premise — that all three 404 through the ingress — is true only of the bare root paths it probed. |
| 2 — routes genuinely do not exist → add one | **True of `/version` only.** |
| 3 — *(the actual situation)* | **Neither. The build identity is unreadable for a different reason entirely — see 2.4.**

### 2.4 ⛔ The real defect: every version this API reports is a hardcoded literal

The running image is **`ghcr.io/brucecostello2/ivgs-api:v5.27.0-motion`** (`docker inspect
ivgs-fastapi --format '{{.Config.Image}}'`, node-01). What the API says about itself:

| Source | Reports | Truth |
|---|---|---|
| `/api/v1/health` | `"version":"5.0.0"` | hardcoded at `ivgs-api/app/api/v1/health.py:68` |
| `/` | `"version":"5.0.0"` | hardcoded |
| `/api/v1/openapi.json` `info.version` | `"5.1.0"` | hardcoded, and disagrees with the other two |
| `docker exec ivgs-fastapi env` | `IVGS_API_TAG=v5.1.14-stream-b` | **stale by 26 minor versions** |

**Adding a `/version` endpoint would not have fixed this and could not have been done honestly.**
Nothing inside the image carries its own build identity: the Dockerfile (`ivgs-api/Dockerfile`)
declares **no `ARG`, no `ENV` and no `LABEL`**, and the one variable that looks like a version is the
stale service-level `env_file` injection that `dev/CLAUDE.md` §6 documents as a known liar —
measured again here, still lying, exactly as §6 says.

An endpoint reading that variable would have shipped a confident falsehood. **So none was added**,
and by §5.3's own discipline — do not ship a mechanism you cannot prove — that is the correct stop.

### 2.5 What the operator needs to do — reported, not built

1. **No nginx change is needed to read health or the schema.** Use `/api/v1/health` and
   `/api/v1/openapi.json`; both return 200 through the ingress right now. If the bare paths are
   wanted as conveniences, the rule is an nginx alias on node-01 —
   `location = /health { proxy_pass http://fastapi-backend:8001/api/v1/health; }` and the same for
   `/openapi.json` — an **operator action, not a code change.**
2. ⚠ **`GET /health` through the ingress is a false green.** It returns `200 {"status":"ok"}` from
   nginx itself and never reaches the API. It would report `ok` with the API stopped. Anything
   monitoring that path is monitoring nginx. This belongs in the swallowed-failures register.
3. **Making the build readable is a build-path change, and it is the only thing that fixes 2.4:**
   add `ARG IVGS_BUILD_REF` / `ENV IVGS_BUILD_REF` to `ivgs-api/Dockerfile`, pass the real tag at
   `docker build`, and have a `/api/v1/version` route report it alongside the git SHA. Deliberately
   **not** done here: it cannot be proven without a build and deploy, both forbidden by this order.

---

## §3 What changed

Three files. **Nothing was removed, nothing renamed, no `extra` policy touched, no
`pending_exports` row touched, nothing on `.51` or `.52` touched.**

| File | Change |
|---|---|
| `shared/models/model_store.py:104-127` | Four values appended to `ModelEngine`: `TTS = "tts"`, `MAGIHUMAN = "magihuman"`, `HUMO = "humo"`, `WAN22_S2V = "wan22_s2v"`. The twelve existing values are untouched and in their original order. |
| `ivgs-api/migrations/versions/0042_wp_ivgs_03_mbcp_runtime_engines.py` | **New. Migration `0042`, `down_revision = "0041"`.** Four `ALTER TYPE model_engine ADD VALUE IF NOT EXISTS`, following `0027`'s shape. |
| `ivgs-api/tests/test_api_model_export.py` | New `TestMbcpRuntimeEngines` — 7 tests (4 parametrised + 3). |

### 3.1 The migration number was verified, not taken from the WP

WP §5.2 states the head is `0041` and the next free number is `0042`, and instructs verification.
**Verified two independent ways, both agreeing:**

- The chain: `0041_wp68_motion_graphics_media_type.py` has `revision = "0041"`, `down_revision = "0040"`; no file declares `down_revision = "0041"`. `0041` is the head.
- The live test database reports `select version_num from alembic_version` → `0041`.

`0042` was free. The WP was right.

### 3.2 The no-op downgrade, and why

WP §5.2 states *"the last two enum-label migrations shipped with a deliberate no-op downgrade"*.
**Verified:** `0040_wp66_selection_source_preset.py` and `0041_wp68_motion_graphics_media_type.py`
both have `def downgrade(): pass`, as does the `0027` precedent. `0042` follows, and the migration
says why in its own body: **PostgreSQL cannot remove a value from an enum type.** Dropping one would
require proving no row references it, which a downgrade cannot do safely against live data.

⚠ **The honest consequence, stated because "rolls back cleanly" could otherwise be read as "reverts":**
`alembic downgrade 0041` runs cleanly and moves the revision pointer back, but **the four enum
values remain in the type.** That is by design and matches every enum migration in this repository.
It is a clean rollback, not a reversal.

---

## §4 §7.1 — the inconsistency, ledgered and NOT cleaned up

As ruled. `coqui`, `kokoro`, `animatediff`, `latentsync` and `sadtalker` remain in `ModelEngine`
untouched. Recorded here for AD-10's value-domain reconciliation, with the evidence:

**Eight of IVGS's twelve pre-existing engine values have no producer anywhere in MBCP.** Searching
MBCP `origin/main` non-test source for each as an `engine` literal returns **zero hits** for:

```
ollama   coqui   kokoro   cogvideox   wan21   animatediff   sadtalker   remotion
```

The two most pointed cases, because MBCP serves those exact models under a different value:

- **CogVideoX-5b** is certified by MBCP with `engine="comfyui"` (`scripts/seed_stage.py:336`), not `cogvideox`.
- **AnimateDiff-SD15** is certified with `engine="comfyui"` (`scripts/seed_stage.py:380`), not `animatediff` — which is precisely the case WP-46 already ruled on.
- `ollama` is *structurally* unreachable: `registry_map.py:62-67` records that Ollama is **intentionally absent** from `RUNTIME_KIND_ADAPTER_KEY` because no concrete Ollama adapter is registered, *"so it can never be onboarded."*

**Not acted on.** The blast radius is live rows, including the Kokoro-82M row rendering today.
`TestMbcpRuntimeEngines::test_no_existing_value_was_removed` pins the full 16-value set so a later
package cannot remove one by accident — only deliberately, with the separate ruling that requires.

---

## §5 Proof — split as §5.3 demands

### 5.1 ✅ PROVEN HERE, against a test client

Run on node-01 against `ivgs_reconciliation_test` (the guarded disposable DB;
`ivgs-api/tests/conftest.py:93-102` refuses any database not named for testing).

**a) The enum change alone is NOT sufficient — measured, not assumed.** Running the new tests with
`shared/models/model_store.py` updated but `0042` **not yet applied** gave **5 failures**, and the
failure had moved from Pydantic to PostgreSQL:

```
sqlalchemy.exc.DBAPIError: asyncpg.exceptions.InvalidTextRepresentationError:
invalid input value for enum model_engine: "tts"
```

**This is the proof that the migration is load-bearing.** Validation passed; the write failed. A
package that shipped the enum without the migration would have turned a clean 422 into a 500.

**b) With `0042` applied — 26/26 pass in that file, 123/123 across every test file that touches
`ModelEngine`:**

```
alembic upgrade head        0041 -> 0042
pytest ivgs-api/tests/test_api_model_export.py           26 passed
pytest <6 ModelEngine-touching files>                   123 passed
```

Files exercised: `test_api_model_export.py`, `test_wp62_ledger.py`, `test_wp66_selection.py`,
`test_wp67_clients.py`, `test_wp66_invalidation.py`, `test_wp65_engine_reconciliation.py`.

**c) The verbatim refused payload now validates AND reaches the row.**
`test_the_exact_refused_payload_shape_validates` posts `ivgs_stage="tts"`, `engine="tts"` and asserts
**not just a 201** but that `models.engine == ModelEngine.TTS` on the stored row. `engine` is
supplied-wins (`ad01_ingest.py:195`), and a value that validated but was silently overwritten by the
stage default (`coqui`, `ad01_ingest.py:69`) would still be a defect. It is not overwritten.

**d) The enum is still closed.** `test_domain_is_still_closed` posts `engine="tts_coqui"` —
MBCP's *adapter_key*, deliberately chosen — and asserts a 422 on `["body","engine"]`.

**e) The migration applies and rolls back cleanly, both directions, twice:**

```
alembic upgrade head      0041 -> 0042     alembic_version = 0042
alembic downgrade 0041    0042 -> 0041     alembic_version = 0041
alembic upgrade head      0041 -> 0042     alembic_version = 0042
select count(*) from pg_enum where enumtypid='model_engine'::regtype  ->  16
```

Enum content after: `vllm ollama comfyui coqui kokoro cogvideox wan21 animatediff latentsync
sadtalker remotion ffmpeg tts magihuman humo wan22_s2v` — **twelve preserved in order, four appended.**

### 5.2 ⛔ NOT YET PROVEN — deferred, operator-side, after deploy

**Nothing in this package is running anywhere.** The enum lands in the API image; it takes effect
only when node-01 is rebuilt, deployed and `0042` runs against the production database. **This order
forbids deploying, and no deploy, push or service restart was performed.**

| Deferred claim | Status |
|---|---|
| The live `POST /ad01/v1/certified-models` on `.90` accepts `engine=tts` | **NOT YET PROVEN.** The deployed image is `v5.27.0-motion`, which predates this commit. |
| Production `model_engine` contains the four values | **NOT YET PROVEN.** `0042` has run against the *test* database only. |
| MBCP re-sends `pending_exports` row `b4e8c2e6-40cd-44b7-925d-b9277d4c1818` (`transmitted=false`, `attempts=5`) and it lands | **NOT YET PROVEN, and not IVGS's to perform.** That row lives on MBCP `.51`. Untouched, as ordered. A two-sided operator action after deploy. |
| The other three blocked certificates (XTTS-v2 × 3) land | **NOT YET PROVEN.** Same gate. |

---

## §6 ⚠ D-1 — THE NEXT BLOCKER, FOUND AND MEASURED. Not fixed; needs an operator ruling.

**This package unblocks INGESTION. It does not make any of the four models RUNNABLE, and the
reason is §7.1's inconsistency biting one link downstream.**

IVGS's client registry is keyed on `(stage, engine, family)` (`shared/providers/client_registry.py:106`).
Its two TTS clients are registered under **`engine="coqui"`** (`:492`) and **`engine="kokoro"`**
(`:506`) — the model-family values §7.1 identifies as wrong-shaped. **The moment MBCP sends the
correct runtime name, the registry misses.** Measured live, not inferred:

```
engine='kokoro'  -> RESOLVES to clients.kokoro_client.KokoroClient
engine='tts'     -> NoClientForFamilyError: model 'Kokoro-82M' is selected for stage
                    'voiceover_tts' on engine 'tts', but IVGS has no client for family
                    'kokoro'. Clients exist for: kokoro, xtts.
```

Two things follow:

1. ✅ **The failure is loud and named, not silent.** WP-67 built `resolve_client` to refuse by name,
   and its message already says the exact thing: *"A model can be certified, fetched and selected
   and still have nothing in IVGS that knows how to call it; that is this state."* Nothing here
   fails quietly, and no exhaustive `ModelEngine` dispatch table exists that four new values could
   silently break — checked across `shared/`, `ivgs-api/` and `ivgs-workers/`.
2. ⛔ **§7.1's "defer the cleanup" ruling has a cost the WP did not anticipate.** The registry keys
   on the wrong-shaped values, so deferring reconciliation to AD-10 means a Kokoro certificate can
   be accepted, stored and selected — and still not render. `magihuman`, `humo` and `wan22_s2v` have
   no registered client at all, so they are in the same state for a different reason.

**Deliberately NOT fixed here.** §5.2 says *"Add nothing else"*, and the `coqui`/`kokoro`
registrations are live and serve the Kokoro-82M row rendering today. **This is for the operator:**
either register the `tts` engine key alongside the existing two, or bring the §7.1 reconciliation
forward. It should not wait for AD-10 silently.

---

## §7 What I did NOT verify

Stated plainly, in the order they matter.

1. **Nothing was proven live.** No deploy, no push, no restart. Everything in §5.1 is a test-client
   and test-database result. The live seam is exactly as it was before this commit.
2. **`magihuman` and `humo` engine values are INFERRED, not measured** (§1.3). Their `models` rows
   live in MBCP's database on `.51`, which this package does not touch and cannot read. The
   inference rests on MBCP's `engine == adapter_key` convention, measured for `latentsync` and
   `wan22_s2v`; WP §2 asserts the same values independently. **If either row actually carries a
   different string, that value is still blocked and needs a `0043`.** ⚠ A one-line query on `.51` —
   `select name, engine from models where name in ('davinci-magihuman','humo-17B')` — would settle
   it, and is worth running before the operator considers this closed.
3. **The set of eight is the set MBCP writes TODAY.** MBCP's `models.engine` is unconstrained free
   text (`String(64)`, no CHECK), so a ninth value can be introduced on `.51` at any time with no
   signal to IVGS. **That is §7.2's point, and this package does not fix it** — it fixes the four
   values that exist, not the mechanism that lets a fifth appear unannounced.
4. **The onboarding API path was read, not exercised.** `mbcp_api/api/v1/onboarding.py:336` passes
   `engine=body.engine` straight through; I did not run it.
5. **`ExportBundleIn`'s `extra` policy was neither changed nor determined.** WP §5.4 wanted the
   deployed setting identified; §2.4 explains why that remains impossible — the running build cannot
   be identified from outside, and the hardcoded `5.0.0` / `5.1.0` / stale `IVGS_API_TAG` all
   disagree with the actual `v5.27.0-motion`. **This remains undetermined, for the same reason as
   before, and no code change here would have settled it.**
6. **The full `ivgs-api/tests/` suite was not run to completion** — it exceeded the command timeout.
   The six files that reference `ModelEngine` were run in full (123 passed); files that do not
   reference it were not re-run.
7. **MBCP's live database was not read** for anything, and `/opt/MBCP`'s working tree was not
   checked out or modified — only `origin/main` refs were read, via `git show` / `git grep`.

---

## §8 Exit checklist against WP §8

| Required | Where |
|---|---|
| The authoritative engine list and how it was derived | §1 — eight values, with the WP's own derivation method corrected in §1.1 |
| The values added | §3 — `tts`, `magihuman`, `humo`, `wan22_s2v` |
| The migration id | **`0042`**, verified against the chain and the live `alembic_version` (§3.1) |
| Proof that an `engine=tts` payload is accepted | §5.1(a)–(d), with the live half labelled NOT YET PROVEN in §5.2 |
| The version endpoint | §2 — diagnosed, **none added**, with the reason and the operator actions in §2.5 |
| What I did NOT verify | §7 |

**Committed and held. Not pushed. Not deployed. No service restarted. The operator holds sole
merge authority.**
