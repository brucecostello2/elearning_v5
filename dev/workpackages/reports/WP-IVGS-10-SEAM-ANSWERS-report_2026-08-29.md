# WP-IVGS-10 — seam answers appendix, 2026-08-29

**Scope:** ANSWERS ONLY. No code was written, no rename performed, nothing built.
Filed under `dev/CLAUDE.md` §12 because chat is not storage — these three answers
were produced in a session whose priority work was the stage-2 time-limit fix and
the operator-run resume, and they would otherwise have been lost with it.

**Companion report:** `WP-IVGS-10-V7-CONTRACT-report_2026-08-29.md` (the package body).
This file is its appendix, not a separate package.

---

## STATE AT SESSION END — this appendix

| | |
|---|---|
| **Done** | Both ratified amendments read in full; Q3, Q4 and D-4 answered from measurement |
| **Mid-way through** | Nothing. All three answers are complete |
| **Blocked on** | D-4's ruling (operator). No rename until it lands — explicitly instructed |
| **Stale because of this report** | `OUTSTANDING_WORK.md` **RC-D10** ("⚠ SCHEDULED, not closed") and **§RC-E** — both are answered by §B below. Rows not edited: they are the register's, and the ruling round is the operator's |

**Verified live vs inferred (`dev/CLAUDE.md` §12):**

- **Live, against the running system:** every D-4 row count (`ivgs-postgres`, database `ivgs`);
  the registry resolution of both Kokoro rows (executed through `resolve_client`); the
  `talking_head` family list and the endpoint-map gaps (executed).
- **Live, against the tree:** every file:line and every literal count.
- **Read, not executed:** all MBCP-side facts in §B. Read from `/opt/MBCP`'s fetched
  `origin/main` refs. No checkout, `.51` not touched (§11).

---

## §0 The two ratified amendments, and what they change here

Read in full before writing any of the below: `IVGS_MBCP_Amendment_AD-07_v1_3_2026-08-27.md`
and `IVGS_MBCP_Amendment_AD-10_v1_1_2026-08-27.md`, both ratified by the operator 2026-08-28.

**AD-07 v1.3 §4.7.3 falsifies the premise this session was briefed on.** v1.2 §6.3 held that
*"a model that produces both tracks will always sync perfectly with itself"* and that gating
joint mode on `lse_c` would be *"a rubber stamp — a metric that cannot fail."* Measured:
accepted render `09308b25` carries **16.97 s of video against 20.44 s of audio**, self-sync
**0.0466 — the worst of the seven artifacts tested.** The `lse_c` prohibition survives, on the
corrected reason: `lse_c` is structurally inapplicable to joint mode (§4.7.3's two hard rules),
not incapable of failing. ⛔ **Any future joint gate must carry the drift check v1.2 omitted** —
`av_drift_seconds` per §4.7.3a, frame-relative, and only after the one-sided-`max` fail-open and
`output_fps` coverage are fixed, in that order.

**AD-10 v1.1 §3.1a is the value-domain rule §7.2 was waiting on. §7.2 is closed.** `engine`
names the runtime; the domain is jointly owned with MBCP's adapter runtimes as the authoritative
source; ⛔ no MBCP adapter ships until its engine value exists on the IVGS side first; neither
side may map around a mismatch. Migration `0042` already satisfies rule 3 for all three engines
in §A.

---

## §A — Q3: clients for `magihuman`, `humo`, `wan22_s2v`

**Derived from the WP-67 registry's actual requirements, not estimated.**

### A.1 What the registry requires of a new client — six sites, measured

| # | site | file:line |
|---|---|---|
| 1 | `ClientContract` — family, display_name, stage, engine, `requires` / `optional` / `accepts_params` / `produces` | `shared/providers/contracts.py:69-100` |
| 2 | `ClientSpec` + `register_client(..., name_patterns=)` in `register_builtin_clients` | `shared/providers/client_registry.py:78-91`, `:113-119`, `:264` |
| 3 | `_ENGINE_ENDPOINTS` entry | `shared/providers/binding.py:22` |
| 4 | provider class + `register_engine_builder` — **NOT frozen** (WP-67 §1.2) | `ivgs-workers/providers/talking_head.py:182-184` |
| 5 | `_ENGINE_DEFAULT_VRAM_MB` entry | `ivgs-workers/providers/talking_head.py:35` |
| 6 | the client class itself | `ivgs-workers/clients/` |

### A.2 The gap today, measured by execution

All three engine values exist in the `model_engine` enum (migration
`0042_wp_ivgs_03_mbcp_runtime_engines.py:46`; `shared/models/model_store.py:123-127`) **and
nowhere else in the system.**

```
registered talking_head families : ('latentsync', 'sadtalker')
  ('talking_head','latentsync','latentsync') -> LatentSyncClient  requires: audio_track, reference_clip
  ('talking_head','sadtalker','sadtalker')   -> SadTalkerClient   requires: audio_track, reference_image

magihuman   in _ENGINE_ENDPOINTS: False   in _REGISTRY (any stage): False
humo        in _ENGINE_ENDPOINTS: False   in _REGISTRY (any stage): False
wan22_s2v   in _ENGINE_ENDPOINTS: False   in _REGISTRY (any stage): False
```

Zero client code exists for any of the three. Every occurrence in the tree is the enum, a
migration comment, or a test asserting the enum accepts the value.

### A.3 The answers

| model | new build or reuse | size | basis |
|---|---|---|---|
| **magihuman** | ⛔ **NEW BUILD — and it forces a REGISTRY CHANGE, which is the real deliverable** | client **~450-550 lines** + demux + **~40 lines of registry change** + ~30 across sites 2-5 + 16-34 tests | `latentsync_client.py` = **503 lines** (409 code) — the only other byte-returning talking-head HTTP client. WP-67's own new-family test counts: 16 worker + 34 api |
| **humo** | **NEW BUILD, small — the contract is a copy of SadTalker's** | client **~300-370 lines** + ~25 across sites 2-5. **No registry change** | `sadtalker_client.py` = **368 lines** (288 code); its contract `{REFERENCE_IMAGE, AUDIO_TRACK} -> video/mp4` is HuMo's contract exactly |
| **wan22_s2v** | ⛔ **BUILD NOTHING** | **0 lines** | AD-07 §5.4 standing prohibition: *"`wan22-s2v-14B` is not to be certified. Its `license` column stays NULL."* |

**Not a ComfyUI-graph family, any of them.** Migration `0042`'s header records that
`magihuman` / `humo` follow MBCP's measured `engine == adapter_key` convention for `engine_only`
**remote** engines. So the analogue is `latentsync` / `sadtalker` (HTTP clients), not
`animatediff` (264-line client + 126-line graph JSON). No graph file is needed for any of the three.

### A.4 ⛔ Why magihuman is not merely a bigger client

It is the only one of the three that is not "inputs → one video".

1. **Two artifacts, two certificates.** AD-07 §4.7.0a splits a joint render at the adapter: the
   audio half is graded at `tts`, the video half at `talking_head`. `ClientContract.produces` is
   a single `str` (`contracts.py:95`), and the registry key is `(stage, engine, family)`
   (`client_registry.py:96`), so joint MagiHuman needs **two registrations over one client**.
2. ⛔ **And the two AD-07 contracts collide on one key.** MagiHuman serves **both**: Contract A
   (`a2v` / `ti2v_a2v`, `requires` includes `AUDIO_TRACK`) and Contract B (`t2v` / `ti2v`, which
   does not). Both resolve to `(talking_head, magihuman, magihuman)`. **One key cannot hold two
   different `requires` sets.** §4.7.0 prohibition 3 forbids inferring the mode, so `driving_mode`
   must be a declared fourth key dimension or a variant contract. **That is the change worth
   making, and neither of the other two models needs it.**
3. ⛔ **The wiring that makes it useful is FROZEN.** AD-09.6.2's *"joint mode skips Stage 5 and
   demuxes the output into an audio asset and a talking-head asset"* is a stage-body edit →
   **M3.3**. WP-67 §1.2 measured `providers/talking_head.py` unfrozen but the fallback at
   `talking_head_task.py:354-382` frozen.

### A.5 humo's problem is evidence, not code

Its contract is SadTalker-shaped, so sites 1-5 are a copy. But AD-07 §4.7.0 records that **every
Contract A candidate evaluated has been rejected**, and §4.7.4's correction of record puts the
~53.1 GiB OOM on **HuMo, not MagiHuman**. Building it now builds for a model that has already
failed on this fleet.

### A.6 No seam blocker on any of the three

AD-10 §3.1a rule 3 requires the engine value to exist on the IVGS side **before** the MBCP
adapter ships. `0042` did that on 2026-08-27. The blockers are therefore **certification**
(magihuman, §5.4 preconditions 0-5), **evidence** (humo), and **licence** (wan22_s2v) — not the
value domain.

### A.7 Recommendation

**Build one — magihuman — and not before §5.4's preconditions land.** The registry change it
forces is the deliverable; the other two do not need it, and one of them may not be built at all.

---

## §B — Q4: the "Export to IVGS" button (RC-D10 / §RC-E)

**SETTLED. Not superseded by the drain.**

Method: `/opt/MBCP`'s fetched `origin/main` refs only — no checkout, `.51` not touched, per
`dev/CLAUDE.md` §11. The same method §RC-E used, carried further.

| link in the chain | evidence |
|---|---|
| **The button exists** | `ivgs-bench-frontend/src/app/bench/certifications/page.tsx:587-588,756` — *"Export to IVGS (AD-01 seam) — per-card action. POST /api/v1/exports {certification_id}; admin-gated server-side."* Test: `ivgs-bench-frontend/__tests__/exports/ExportToIVGS.test.tsx` |
| **It writes the drain's queue** | `mbcp_api/api/v1/certifications.py:708-709` `create_export`. Module docstring: in `local` mode this *"writes a `pending_exports` row and returns a receipt with `transmitted=false`"* |
| **The drain transmits that queue** | `mbcp_worker/export_drain.py` — *"re-send `pending_exports` once AD-01 connectivity is available… when the deployment flips to `connected`, this drain re-sends the un-transmitted rows via `AD01Export`"* |

> **They are the two halves of ONE outbox, not two competing paths. Button = enqueue. Drain =
> transmit.**

**RC-D10 answers NO and can close as *not a duplicate*** rather than remaining ⚠ SCHEDULED.
§RC-E's open point — *"whether the per-certificate button still exists as a separate path, and
whether it writes to the same queue, was not established"* — is now established on both limbs.

⚠ **One consequence worth carrying rather than dropping: a successful button press is not a
delivery.** A certificate can be clicked, receipted, and never delivered if the deployment mode
never flips to `connected`. The receipt says `transmitted=false` honestly (INV-9), but the label
"Export to IVGS" reads as delivery — which is exactly the ambiguity `OUTSTANDING_WORK.md:479`
already records as *"failed or was parked by `drain-pending-exports` or simply never clicked."*

---

## §C — D-4: what references `kokoro-82m` by name

⛔ **MEASUREMENT ONLY. No rename attempted, none performed, none recommended here.** The ruling
is the operator's and is coming separately.

D-4, as opened by WP-IVGS-04 §10: *"MBCP's name `Kokoro` and IVGS's rendering row `kokoro-82m`
are different rows; the orphan is what gets certified."*

### C.1 The two rows, live in database `ivgs`

| id | name | display_name | stage | engine | state | enabled | is_default | created |
|---|---|---|---|---|---|---|---|---|
| `2b2a0be5` | `Kokoro` | Kokoro | voiceover_tts | **`coqui`** | candidate | **f** | f | 2026-07-10, bruce |
| `a1ac974d` | `kokoro-82m` | Kokoro-82M | voiceover_tts | **`kokoro`** | approved | t | **t** | 2026-08-24, admin |

`models_name_key` is a UNIQUE constraint on `name`.

### C.2 Database references — by foreign key

| table | `kokoro-82m` | `Kokoro` |
|---|---|---|
| `model_node_availability` | **3** | 0 |
| `model_approvals` | **1** | **1** |
| `project_model_selections` | 0 | 0 |
| `model_weight_placements` | 0 | 0 |
| `model_capability_tags` | 0 | 0 |
| `actors.certified_model_id` | 0 | 0 |

### C.3 Database references — by NAME STRING. This is the load-bearing measurement

| location | rows carrying the literal `kokoro-82m` |
|---|---|
| **`assets.generation_metadata` → key `model`** | **205** — every one `asset_type = audio` |
| `audit_log.after_payload` | **317** |
| `audit_log.before_payload` | **2** |
| `model_approvals.checklist` | 1 |
| `models.default_params` | 0 |

⛔ **`assets` HAS NO MODEL FOREIGN KEY.** Its only FKs are `project_id`, `scene_id`,
`generation_prompt_id`, `library_asset_id` and `superseded_by`. **The name string in
`generation_metadata` is the sole link from a rendered audio asset to the model that produced
it.** Nothing constrains it, nothing cascades, and a rename breaks it silently.

### C.4 Code references — ZERO in production

52 literal occurrences in the tree (all spellings: `kokoro-82m`, `kokoro_82m`, `kokoro82m`):

| kind | count | where |
|---|---|---|
| **tests** | **16** | `ivgs-api/tests/test_wp67_clients.py` 5, `ivgs-api/tests/test_api_model_export.py` 5, `ivgs-workers/tests/test_wpivgs04_tts_runtime_builder.py` 5, `ivgs-scheduler/tests/test_load_balancer.py` 1 |
| **comments only** | **3** | `ivgs-workers/servers/kokoro/Dockerfile` 2, `migrations/versions/0042_…py` 1 |
| **reports / docs** | **33** | 8 files under `dev/workpackages/` |

**Nothing resolves a model by that literal at runtime.** The only name lookups in the system are
`ivgs-api/app/api/ad01_ingest.py:156` (`Model.name == bundle.model_name`) and
`ivgs-api/app/api/v1/model_store.py:132` (`Model.name == body.name`) — both against wire input,
neither against a hardcoded string.

### C.5 Registry resolution — executed, both rows

Both rows derive family `kokoro` from the pattern `r"kokoro"` (`client_registry.py:592`):

```
'Kokoro'      family=kokoro -> REFUSED  NoClientForFamilyError:
              "model 'Kokoro' is selected for stage 'voiceover_tts' on engine 'coqui',
               but IVGS has no client for family 'kokoro'."
'kokoro-82m'  family=kokoro -> clients.kokoro_client.KokoroClient
```

**The orphan is unrunnable today, and harmlessly so:** `enabled=false`, `state=candidate`, zero
selections. The refusal is the WP-67 honest refusal working as designed.

### C.6 Four constraints any rename ruling has to survive

1. ⛔ **`models_name_key` is UNIQUE.** Renaming `kokoro-82m` → `Kokoro` **collides with the live
   orphan.** It cannot be done at all without first removing or renaming `2b2a0be5`.
2. ⛔ **205 audio assets lose their only provenance link, silently.** No FK, no cascade, nothing
   raises. The breakage is undetectable by any existing check.
3. **319 `audit_log` payloads stop matching by name.**
4. **Four test files pin the literal and fail loudly.** That is the cheap half, and the only half
   any current test would catch.

**Reading, offered as input and not as a ruling:** the expensive half is **524 name-keyed history
rows that no constraint protects**. The cheaper end to move is the **orphan** (`Kokoro`: 1
approval row, 0 assets, 0 audit payloads, 0 selections, disabled) rather than the rendering row.
But which row moves is D-4's ruling, not this report's.

---

## §D — What this appendix did NOT do

- ⛔ No rename, no migration, no data write of any kind.
- ⛔ No client built for any of the three engines.
- ⛔ `OUTSTANDING_WORK.md` rows **RC-D10** and **§RC-E** were **not edited** — §B answers them,
  the operator rules them.
- No MBCP working tree checked out; `.51` not contacted.
