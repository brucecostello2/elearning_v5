# WP-IVGS-03 — `ModelEngine` cannot express four of MBCP's eight runtimes

## For the IVGS agent · 2026-08-27 · Operator-approved · **rev 2 — three corrections from IVGS-side review, all accepted**

**Four live MBCP certificates cannot be delivered to IVGS. Three more models, currently being
onboarded, will fail identically the moment they are certified.** The cause is a value-domain
mismatch in one enum, and the fix has a precedent in this repository.

---

## §1 What was measured

MBCP's export drain ran against `POST /ad01/v1/certified-models` and got, verbatim:

```
STATUS 422
{"detail":[{"type":"enum","loc":["body","engine"],
  "msg":"Input should be 'vllm','ollama','comfyui','coqui','kokoro','cogvideox',
         'wan21','animatediff','latentsync','sadtalker','remotion' or 'ffmpeg'",
  "input":"tts"}]}
```

**The refused field is `engine`. The refused value is `tts`.**

Two things follow, and both matter:

- **Pydantic reports every validation failure in one response.** `detail` has exactly **one** entry,
  so every other field in that payload — including `bundle_link_basis`, `bundle_version` and
  `request_constraints` — **was accepted**. An earlier hypothesis blamed those three. It was wrong
  and is recorded here so it is not revived.
- **AnimateDiff-SD15 was accepted in the same drain run** only because its `engine` is `comfyui`,
  which is in the enum. It has a `bundle_manifest_url` pointing at a route that does not exist, and
  IVGS accepted it anyway. **The correlation with the manifest URL was real; the causation was not.**

---

## §2 The scope — larger than one row

| Blocked now | Blocked on arrival |
|---|---|
| **Kokoro** (`engine=tts`) | **`magihuman`** — the talking-head model WO-MBCP-03 exists to certify |
| **XTTS-v2** × 3 certificates (`engine=tts`) | **`humo`** |
| | **`wan22_s2v`** |

**Four of MBCP's eight engine values cannot be expressed at this seam.**

⛔ **The consequence for the programme:** MagiHuman is the model the entire talking-head workstream
is built around. It can be benchmarked, gated and certified — and the certificate **still cannot
reach IVGS**. Nobody had counted this step.

---

## §3 Why IVGS is wrong here — on IVGS's own stated reasoning

This is not a matter of taste. **`ad01_ingest.py:52-62` (WP-46) already ruled it**, and the ruling
is correct:

> `animatediff` *"is the name of ONE MBCP model family, not of an engine… so the engine is `comfyui`
> for all three."*

**`engine` means the runtime.** Applying that rule to the current enum:

- `coqui` and `kokoro` are **model families**, not runtimes — the exact category WP-46 rejected.
- On MBCP, **both TTS models are served by one adapter**, `mbcp_adapters.tts_server:TtsServerAdapter`
  — structurally identical to how `comfyui` serves many model families.
- The runtime's name is `tts`. **IVGS offers no value that names it.**

> **MBCP cannot send a correct value even in principle.** That is the definition of a contract
> defect on the receiving side, not a sender bug.

---

## §4 The precedent

**`e613e84` — `fix(model-store): add ffmpeg to model_engine enum`, migration `0027`.** Same shape,
same reason, already merged: MBCP had a runtime IVGS could not name, and the enum was extended to
name it. That commit unblocked MBCP's composition exports.

**Follow that pattern.**

---

## §5 The work

### 5.1 — Derive the authoritative list. Do not take mine.

Establish MBCP's real set of engine values from MBCP's own source — `adapter_key` on each class in
`mbcp_adapters/`. **The list below is what the investigation found; treat it as a starting point to
verify, not a specification:**

`tts` · `magihuman` · `humo` · `wan22_s2v`

**State the full set you found and which are already expressible.** If it differs from the four
above, **your measurement wins** — say so and proceed with yours.

### 5.2 — Extend `ModelEngine` and migrate

- Add every missing value to `ModelEngine`.
- Write the migration, following `0027`'s **shape** — but **not its number.**
  ⚠ **The current head is `0041` (WP-68's enum label). The next free number is `0042`.**
  Verify that yourself before writing; if the head has moved, **your measurement wins.**
- **Precedent for the downgrade:** the last two enum-label migrations shipped with a
  **deliberate no-op downgrade**. Follow that, and say in the migration why.
- ⛔ **Add nothing else. Remove nothing.** In particular **do not remove `coqui`, `kokoro`,
  `animatediff`, `latentsync` or `sadtalker`** in this package, even though §3's reasoning says
  several are model families rather than runtimes. **They are in use.** Removing them is a separate
  ruling with its own blast radius — see §7.

### 5.3 — Prove what you can, and be explicit about what you cannot

⛔ **THE FULL PROOF CANNOT BE RUN IN THIS PACKAGE, AND THE REPORT MUST SAY SO.** The enum change
lands in the API image, so **nothing takes effect until node-01 is deployed and the migration runs**
— and this order forbids deploying. A report claiming a live proof here would be asserting a
mechanism that is not yet running, which is the exact defect class this project keeps catching.

**Split it:**

| Provable by you, now | Deferred, operator-side, after deploy |
|---|---|
| An `engine=tts` payload validates against the updated schema — via a **test client**, in your test suite | The live endpoint accepts it |
| The migration applies and rolls back cleanly | MBCP re-sends `pending_exports` row `b4e8c2e6-40cd-44b7-925d-b9277d4c1818` (`transmitted=false`, `attempts=5`) and it lands |

**State both halves plainly in your report, and label the second as NOT YET PROVEN.** The re-send is
a two-sided operator action: that row lives on MBCP, not here.

### 5.4 — Make the version readable

⛔ **`.90` reports no version.** `/health`, `/version` and `/openapi.json` all return 404 **through
the ingress**, so it is impossible to tell which build is deployed. The investigation could not
determine whether the running `ExportBundleIn` uses `extra="ignore"` or the newer `extra="allow"`
(WP-53), and had to record that as undetermined.

⚠ **DIAGNOSE BEFORE YOU BUILD. The 404 is probably nginx, not the API.** MBCP found the same shape
on its own side — an nginx running a stock default that did not proxy the service behind it. **If
the routes already exist on the container and nginx simply does not route them, adding an endpoint
fixes nothing.**

1. **Measure first:** hit those paths **directly against the `ivgs-fastapi` container** (it publishes
   on `192.168.1.90:8001`), bypassing nginx. Report which of the three exist there.
2. **If they exist and the gap is ingress** — that is an **nginx configuration change on node-01,
   an operator action, not a code change.** Report exactly what routing rule is needed and **stop.**
3. **Only if the routes genuinely do not exist** should you add one. Say which case you found.

---

## §6 What you must NOT do

- ⛔ **Do not ask MBCP to work around this.** A name-based `tts → kokoro`/`coqui` map would make
  MBCP assert a **model family in a runtime field** — recreating from the sending side the exact
  defect WP-46 fixed on the receiving side — and would unblock one model while leaving three
  blocked. **This has been ruled. Do not reopen it.**
- ⛔ Do not remove or rename any existing enum value.
- ⛔ Do not change `ExportBundleIn`'s `extra` policy.
- ⛔ Do not modify any `pending_exports` row — those are MBCP's.
- Do not change anything on `.51` or `.52`.

---

## §7 Reported, not for action — two things for the operator

**7.1 — The enum contains model families. RULED 2026-08-27: ledger it, do not clean it up.**
By §3's own reasoning, `coqui`, `kokoro`, `animatediff`, `latentsync` and `sadtalker` name model
families rather than runtimes. WP-46 established the principle; the existing values were never
reconciled to it.

⛔ **Do not remove them.** The blast radius touches live rows — **including the Kokoro-82M row that
is rendering today.** Record the inconsistency in the ledger and let it resolve when AD-10's
value-domain reconciliation lands, which is when both sides' domains get compared anyway. **Adding
a cleanup migration to this package would break production to satisfy a naming principle.**

**7.2 — AD-10 does not govern this field.** The transport amendment's §3.1 envelope table lists
eleven fields and **`engine` is not among them**, though it is mandatory on the wire. More
generally, **no field in AD-10 has a specified value domain, and nothing keeps the two sides'
enumerations in step.** AD-10 carries a *zero-reader prohibition* — no field added without a named
consumer. It needs the mirror: **no field with an enumerated domain without a mechanism to keep both
sides' domains in step, and no MBCP adapter added without its engine value landing here first.**
**The orchestrator is amending AD-10 accordingly — this is in flight, not deferred.** Without it,
this exact failure recurs with every new adapter MBCP adds.

---

## §8 Exit

A report under this repository's reports directory stating: the authoritative engine list and how
you derived it, the values added, the migration id, the proof that an `engine=tts` payload is
accepted, the version endpoint, and **what you did NOT verify**.

**Commit and hold. The operator pushes.**
