# AD-07 v1.3 — The Brief and the Scene Contract
## Joint Functional Specification Amendment: IVGS v5 + MBCP
### Ratified v1.0 2026-08-21 · v1.1 2026-08-27 00:22 · v1.2 2026-08-27 · **Revised v1.3 2026-08-27**

> **NARROW DIFF, by the convention v1.2 set for itself.** This revision replaces **§4.7 in full**,
> adds **§4.7.6**, and amends **§5.4** and **§6.4**. **Everything else — §§1, 2, 2.1a, 3, 4.1–4.6a,
> 4.8, 4.9, 5.1–5.3, 6.1–6.5 — carries from v1.2 unchanged and is not restated here.** Read this
> alongside v1.2, not instead of it.

---

## §0.0 What changed in v1.3, and why

v1.2 was written before the joint-mode metrics were built and run, and before the IVGS codebase was
reviewed against it. **Four of its claims are falsified by measurement and one requirement is
absent.** All of it lands on §4.7.

| # | v1.2 said | v1.3 says | Evidence |
|---|---|---|---|
| **17** | *"A model that produces both tracks **will always sync perfectly with itself**. Gating joint mode on `lse_c` would be a rubber stamp — a metric that cannot fail"* (§4.7.3) | ⛔ **FALSE, and the risk is the opposite.** A joint model can and did fail to sync with itself | Accepted render `09308b25` carries **16.97 s of video against 20.44 s of audio**. Its self-sync measured **0.0466 — the worst of all seven artifacts tested** |
| **18** | `articulation_range` is a gate metric *"directly targeting the LatentSync defect"* | ⛔ **Does not discriminate. Demoted to investigation** | LatentSync `09211e37` — the artifact rejected *for articulation* — scored the **highest** of all seven (10.889). Controls prove the instrument works: **motion magnitude is not what bad articulation means** |
| **19** | `av_sync_self` heads the required metric list | ⛔ **Failed the acceptance test. Demoted** | Fully overlapping, and still fails with the defective render excluded — the clean accepted value 0.4091 sits inside the rejected range 0.1869–0.4175 |
| **20** | `identity_stability` is a gate metric | **Retained, marked unbandable on current evidence** | The three LatentSync artifacts score *highest* (0.862–0.868) — real footage with a resynthesised mouth. A metric guarding a failure the rejected samples do not exhibit cannot separate them |
| **21** | Contract B: *"reference image + script → video **with audio**"* — one output | ⭐ **Contract B produces TWO artifacts and TWO certificates** (§4.7.0a) | Operator ruling 2026-08-27. Answers **AD-09.14 Q2**, which has blocked AD-09.6 since 2026-08-24 |
| **22** | *"`driving_mode` **is** a first-class recorded attribute of every talking-head run and of every certificate"* | **Restated as a REQUIREMENT, not a description** (§4.7.1) | It is recorded **nowhere certifiable** — only in `sandbox_runs.telemetry.extra`. **AD-10 §3.1 rejects an envelope without it** |
| **23** | *(silent on the actor)* | ⭐ **NEW §4.7.6 — presenter identity, deferring to IVGS AD-09.4.3** | IVGS already has an `actors` table with an `engine_bindings` column, deliberately empty. AD-07 must reference it, not invent a rival |
| **24** | *(silent)* | ⭐ **§4.7.3a — MBCP adopts IVGS's `av_drift_seconds`** | IVGS gates at `approve_threshold: 0.0334`. **The render MBCP accepted would fail it by a factor of 104.** A live contract violation, not a metric proposal |
| **25** | *"This work is WO-MBCP-02 Phase 5"* | **Repointed to WO-MBCP-03** | Phase 5 delivered its ruling and acceptance test; the build remainder moved |

**Not changed, deliberately:** §4.7.0's two-contract topology and its four prohibitions — **the
measurements strengthen it.** Contract A's rejections are now backed by per-artifact numbers.
Driven-mode `lse_c` behaviour, the six-check gate, the export factory, and `wan22-s2v-14B`'s
standing prohibition all stand.

---

## §4.7 Talking head — **REPLACES §4.7 OF v1.2 IN FULL**

**I:** unchanged flow. Everything below is MBCP-side unless marked.

### §4.7.0 Two contracts, and the declaration that selects between them

*Carried from v1.2 unchanged in substance. Restated because §4.7.0a extends it.*

Talking head is **not one stage with one contract.** It is two contracts, both first-class, both
permanently supported:

| | **Contract A — audio-supplied** | **Contract B — joint** |
|---|---|---|
| Inputs | reference image + **supplied audio** → video | reference image + **script** → audio **and** video |
| Adapter modes | MagiHuman `a2v` / `ti2v_a2v`; LatentSync; Wan2.2-S2V; HuMo | MagiHuman `t2v` / `ti2v` |
| Gating metric | `lse_c` — **unchanged, correct as built** | **not `lse_c`** — see §4.7.3 |
| Status today | **Every candidate evaluated has been rejected** | MagiHuman accepted (§4.7.1) |
| Separate TTS step | **Required** | **Skipped by IVGS** — the model produces the audio (§4.7.0a) |

**Contract A is retained, and retaining it is the point.** A rejection is a result, not a reason to
delete the contract. It is the baseline the next audio-supplied candidate is measured against.

**The declaration is the mechanism.** An adapter **declares which mode it serves**, exactly as it
declares `engine_only`. The orchestrator **branches on the declaration** — never inferring mode from
the presence of an audio input, never from the model's identity.

> **Which mode runs is DATA, NOT STRUCTURE.** Adopting a future audio-supplied model must be a
> selection change, not a rebuild.

**Prohibitions — each a defect, not a trade-off:**

1. **No code may assume a single mode.**
2. **Contract A may not be deleted, disabled or narrowed** because nothing currently passes it.
3. **Mode may not be inferred.** An undeclared adapter is an error, not a default.
4. **Certificates carry the mode.** A certificate that does not say which contract it was earned
   under is ambiguous evidence.

### §4.7.0a ⭐ NEW — Contract B produces TWO artifacts and TWO certificates

**Operator ruling, 2026-08-27. This answers AD-09.14 Q2 and unblocks AD-09.6's contract dependency.**

A joint render is **not one artifact with an awkward contract problem.** It is **two artifacts from a
model that performs two stages.** MBCP splits at the adapter and records what happened:

| Half | Stage | Graded by |
|---|---|---|
| **audio** | existing **`tts`** | `snr_db` and `clipping_pct` work today. ⛔ **`wer` DOES NOT** — see the correction below |
| **video** | existing **`talking_head`** | the talking-head standard, against the split-out audio |

**One `models` row. `supported_stages = [tts, talking_head]`. One certification per stage** — the
pattern already ruled for Llama-3.3-70B.

⚠ **CORRECTED 2026-08-27: "already working" overstated it.** Llama-3.3-70B's **six** multi-stage
certificates **have never been through the AD-01 outbox.** The multi-stage *export* is a prediction
from the bundle schema, not a production fact. The pattern is proven for **certification**; it is
**unproven for delivery**, and the 422 finding shows this seam is barely exercised.

⛔ **AND A SECOND CORRECTION — the audio half does NOT have a working gate on day one.**
An earlier draft said `wer` against the `Dialogue:` text *is* script fidelity and that no second
metric was needed. **Both halves of that are false, measured:**

- **`mbcp_core/quality/scorers/audio/_asr_backend.py` does not exist.** `wer.py` imports it lazily
  and raises `ScorerUnavailable` on any host without it — which is every host.
- **Nothing in the scoring path parses a `Dialogue:` block.** The only occurrences are a docstring
  in `shared/clients/magihuman_client.py` and a build-time presence check in
  `engines/magihuman/verify_build.py`. **There is no reference text to score against.**

**So the audio half ships with `snr_db` and `clipping_pct` — is it speech-shaped, is it clean — and
with NO measure of whether the model said what the script said.** For instructional video that is
the metric that matters most. **`script_fidelity` is real work: an ASR backend AND a
`Dialogue:`-block parser. It is not a rename of `wer`.**

**⛔ NOT a tenth `ivgs_stage`.** The nine AD-01 stages are canonical (`mbcp_core/enums.py:172-182`).
A tenth would propagate through the export and tell a consumer a pipeline stage exists that does not.

**⛔ NOT a declared variant of `talking_head`.** The model genuinely performs the TTS stage. Recording
that as a qualifier on a different stage is a less true record.

**Why this fits IVGS exactly.** AD-09.6.2 specifies that joint mode skips Stage 5 and demuxes the
output into an audio asset and a talking-head asset, with the invariant that *"by the time Stage 7
runs, the database state is identical in both modes."* Joint mode skips the TTS **engine**; it does
not skip the TTS **artifact** — Stage 7 still needs audio with a real duration for AD-03 Pillar-1.

> **A `tts` certificate on a joint model is precisely the statement: *this model produces what the
> TTS stage would have produced.*** There was previously no way to say it.

**Binding consequence, normative:** a model may be selected for `voice_video_coupling: joint` **only
if it holds both a `tts` certificate and a `talking_head` certificate.** One without the other is
not a joint-capable model, and the binding must refuse it **at planning time with a sentence**,
never discover it at render time.

### §4.7.1 The operator ruling — a contract term

> **The only acceptable talking-head output today is `davinci-magihuman` generating its own audio
> and video from one prompt (joint mode: `t2v` / `ti2v`).** MagiHuman driven by a separately-supplied
> voice track was **evaluated and rejected**. So was Wan, and every other model tested to date.
> *Operator ruling, 2026-08-27. It states what passes today; it does not state what the platform may
> measure.*

**And the counterweight, of equal force:**

> A future model with separable audio and video may be better, and the platform must be able to
> **demonstrate** that without a rebuild. Any change that makes joint mode the only *representable*
> mode — as opposed to the only currently *accepted* one — is a defect against §4.7.0.

**⛔ CORRECTED IN v1.3.** v1.2 stated as fact: *"`driving_mode` is a first-class recorded attribute
of every talking-head run and of every certificate."* **It is not.** Measured 2026-08-27: no
`driving_mode` column exists on `run_results`, on `quality_metrics`, or anywhere in the certifiable
path. It exists only in `sandbox_runs.telemetry.extra` — the bench lane, which
`mbcp_api/api/v1/sandbox.py:553` states is *"a look, not evidence."*

**Restated as a requirement with an owner:** `driving_mode` **MUST BECOME** a recorded attribute of
every talking-head run and every certificate. **AD-10 §3.1 already rejects an envelope without it**,
so until this lands, no joint certificate can lawfully be exported. Owner: WO-MBCP-03.

### §4.7.2 MagiHuman takes a script — as a format, not a field

*Carried from v1.2 unchanged. Settled by evidence; recorded so it is never re-litigated.*

- The script rides **inside the prompt text**, in the Dialogue format of
  `prompts/enhanced_prompt_design.md` (deployed sha256 `ba5b7866…`, commit `209209b7`). There is no
  script parameter. **A search of the API surface for a script *field* cannot find a *format*** —
  one was conducted and wrongly concluded it could not be done.
- **Structure:** main body (**150–200 words**) → `Dialogue:` → `Background Sound:` (mandatory; the
  fixed string `<No prominent background sound>` when silent). The dialogue text appears **twice**.
- **Syntax:** `<character (5-word description), language>: "Dialogue content"`. CJK requires single
  spaces between characters.
- **Proof:** `telemetry.extra.prompt` on **both** accepted renders contains a full `Dialogue:` block
  with real spoken English.
- **The format tolerates deviation.** The accepted fixture's character description far exceeds five
  words and worked. Treat the 5-word rule as guidance, not a validator.

**Do not commission further work to prove this. It is proven.**

### §4.7.3 The joint-mode measurement gate — **REWRITTEN**

**⛔ v1.2's central argument is false and must not be carried forward.** It read: *"A model that
produces both tracks will always sync perfectly with itself. Gating joint mode on `lse_c` would be a
rubber stamp — a metric that cannot fail."*

**Measured, 2026-08-27:** accepted render `09308b25` carries **16.97 s of video against 20.44 s of
audio**, and its self-sync scored **0.0466 — the worst of all seven artifacts tested.** A joint model
**can** produce a face and a voice that do not line up, and one did, on a render the operator
accepted. **The risk is the opposite of the one v1.2 named: not a metric that cannot fail, but a
defect nothing was looking for.**

**The structural obstacles remain true and are unchanged:**

- `quality_thresholds` is keyed `(ivgs_stage, metric, tier)` — driving mode is none of the three
  (`quality_threshold.py:38-42`).
- `SyncNetLSEScorer.applies_to` is hard-gated to `IvgsStage.talking_head`
  (`syncnet_lse.py:47-48`) — a scorer naming a stage no result carries **silently never fires**.

**§4.7.0a dissolves both** for the joint case: after the split, the audio is graded at `tts` and the
video at `talking_head`, each by machinery that already exists.

**The metric position, measured against the operator's own labelled verdicts:**

| Metric | Verdict | Standing in v1.3 |
|---|---|---|
| `voiced_ratio` | Separates (gap 0.0598) | **Move to `tts`.** Its confound — comparing model audio against *fixture* audio — dissolves at that stage, where the comparison is against Kokoro and XTTS-v2 output. **Verify; do not assume** |
| `syllabic_ratio` | Separates (gap 0.0153, thin) | Same |
| `face_centre_jitter` | Separates (gap 0.0150) | **The only robust visual separator found.** ⚠ May be measuring *locked-off generated presenter vs driven footage of a moving person*. **Legitimate for a to-camera presenter, but must be DECLARED as a framing standard in the threshold's rationale — not passed off as general quality** |
| `mouth_motion_mean` | Separates (gap 0.0026) | **Unproven.** A raw pixel magnitude across sources from 640×1088 to 1920×1080 |
| `av_sync_self` | ⛔ **Fails** | Demoted. Overlapping, and still fails with the defective render excluded |
| `articulation_range` | ⛔ **Fails** | **Demoted to investigation.** The artifact rejected *for articulation* scores highest. **"No metric found" is a permitted outcome** |
| `identity_stability` | ⛔ Cannot band on this set | Retained, **unbandable on current evidence** |
| `speech_likeness` (composite) | ⛔ Fails | **Do not ship the product; ship the component.** `active_ratio` is noise and destroys the separation its siblings carry |
| `prompt_adherence` | — | ⚖ **advisory only** |

**⚠ The bands are advisory and must say so.** n = 2 accepted, one model, one fixture, one variant.
**Bands are set from measurements, never invented and never loosened to admit a model.**

**Two hard rules, both carried from v1.2 unchanged:**

1. **`lse_c` must report "not applicable" for joint mode — never "missing."** Structurally
   inapplicable and failed-to-run must not produce identical evidence.
2. **Driven-mode `lse_c` behaviour is not to be touched.** ⚠ v1.3 notes without changing it: on the
   only labelled evidence that exists, `lse_c` **passed 8 of 8 operator-rejected results**, scoring
   8.0452 on the clip rejected for articulation. **The metric is not wrong — it measures sync
   timing, and LatentSync's timing is good while its mouth shapes are bad. It is blind, not
   broken.** No metric for that blindness has been found. That is an open problem, separate from
   joint mode, and it must not be conflated with it.

**The acceptance test stands and was run:** score every already-judged artifact; a metric that cannot
separate accepted from rejected is not measuring what matters. **The operator's verdicts are ground
truth; the scorers are validated against them, not the other way round.**

**This work is `WO-MBCP-03`.** Until it lands, `talking_head` certification is blocked (§5.4).

### §4.7.3a ⭐ NEW — MBCP adopts IVGS's `av_drift_seconds`

IVGS already measures video-minus-audio duration drift as **`av_drift_seconds`**
(`ivgs-workers/tasks/talking_head_task.py:163`) and **already gates it** —
`ivgs-api/config/quality_thresholds.yaml:134`, `approve_threshold: 0.0334`, one frame at 30 fps,
with the note *"WP-04 closes it. Do not relax these to make it pass."*

**MBCP adopts that NAME and those SEMANTICS. It does NOT adopt the number.** A second name for one
measurement is precisely the drift §6.3 exists to prevent — but a threshold is a measurement, and
this one does not survive contact with the fleet.

⛔ **CORRECTED 2026-08-27 by measurement (WO-MBCP-03 Phase 1).** An earlier draft of this section
said the threshold must not be relaxed. That was wrong, and the reason is instructive:

> **`0.0334` is one frame at 30 fps. Five of the seven judged artifacts are 25 fps, where one frame
> is `0.0400`.** Every non-zero drift on this fleet except the outlier is an **exact multiple of one
> video frame** — quantisation to frame boundaries, not a defect. **The threshold encodes a frame
> rate this fleet does not use.**

**The band must therefore be frame-relative, not absolute**, and two things block setting one:

1. ⛔ **A one-sided `max` band fails OPEN on negative values.** `metric_passed` compares the raw
   signed value, so `max=0.0334` **passes** `−0.0800`. A band set today would silently pass the exact
   rows it targets. **`sync_offset_ms` has the same hole and is already in `ABS_METRICS`.** Fix the
   absolute-value handling first or the gate is decorative.
2. **`output_fps` is recorded on 6 of 212 `run_results` rows**, and on neither row the two live
   `talking_head` certificates cite. A frame-relative band cannot be computed for a row whose frame
   rate is unknown.

**Sequence: fix the absolute-value handling → record `output_fps` → then band, frame-relatively.**
Shipping non-gating in the meantime is correct, not a deferral.

⚠ **The 3.48 s outlier stands undiminished.** Accepted render `09308b25` carries 16.967 s of video
against 20.440 s of audio — roughly **104 frames**, not one. It is the one artifact in the set whose
drift is not frame quantisation, and it is a real defect on a render the operator accepted.

⛔ **A correction of record:** an earlier draft of §4.7.4 transposed the two accepted renders' frame
rates. Measured: **`44ad87bd` is 25 fps; `09308b25` is the only 30 fps file in the set.**

### §4.7.4 The measured envelope — and what is still unmeasured

*Carried from v1.2, with one addition.*

| | Measured |
|---|---|
| Node of both accepted renders | **`.52`** — four independent witnesses, incl. a GPU baseline fingerprint of 5,051 MiB |
| Variant / mode / duration | `sr_540p` · `t2v` · 17 s · `audio_source = model_generated` |
| **VRAM peak** | **84,104 / 84,122 MiB of 97,887** |
| Wall clock | 1,265 s and 1,385 s |
| **Host-RAM peak** | ⛔ **NEVER MEASURED** — no host-RAM field exists in sandbox telemetry at all |
| **Output geometry** | ⛔ **NOT RECORDED** — and ⭐ **v1.3 makes this a requirement** |

⭐ **NEW: output geometry is a certification attribute, not a composition detail.** `artifacts`
records no width or height; the accepted renders' params carried only `seconds`/`seed`/`output_fps`.
**IVGS's AD-09.14 Q5 asks MBCP which certified engines render portrait natively at usable
resolution, and MBCP cannot answer it.** AD-09.9 rules orientation *"belongs in the Stage-6
generation request and in the actor's engine binding."* Geometry recording lands in WO-MBCP-03
Phase 1; **Q5 stays open until models have been benchmarked with it in place.**

**Two corrections of record:** the ~53.1 GiB OOM was **HuMo, not MagiHuman**; and `.53` — the only
node ever to complete a **1080p** MagiHuman render — is **powered off**. The runbook's 72.38 GiB
figure describes 1080p/17 s and does not describe this workload.

### §4.7.5 The long-form suite — deferred, not cancelled

*Carried from v1.2 unchanged.* Sequenced after the §4.7.3 gate and the §4.7.4 host-RAM
instrumentation. Building it first would produce numbers nobody can interpret.

### §4.7.6 ⭐ NEW — Presenter identity: AD-07 defers to IVGS AD-09.4.3

**The requirement.** Each MagiHuman invocation creates a new actor. Scene to scene that is
unacceptable. Testing indicates the same initial setup reproduces the same actor, so IVGS lets users
save actors to a reusable library.

**⛔ AD-07 does not define an actor model. IVGS already has one and AD-07 defers to it.**
`actors` (migration `0031_wp56_actors`, **AD-09.4.3**) carries `reference_clip_id`,
`reference_image_id`, `voice_profile`, **`engine_bindings`** (JSONB keyed by engine —
`{"latentsync": {...}, "magihuman": {...}}`), `default_orientation` and `certified_model_id`.
**Defining a rival here would be the second-truth defect this amendment exists to prevent.**

**What MBCP owes that model:**

1. **The identity parameter set**, in the shape `engine_bindings` expects. Its own code records that
   this *"is operator knowledge recorded **nowhere** in this repository"* and that WP-56
   **deliberately did not invent its contents**. This is **AD-09.14 Q1**, open, addressed to the
   operator. MBCP measures it in WO-MBCP-03 Phase G.
2. ⛔ **These parameters do NOT travel in `request_constraints`.** That seam carries per-model
   operating limits. Identity is per-actor, keyed by engine. **They are different things and must
   not be conflated.**
3. **A reproducibility measurement**, answering **AD-09.14 Q3** — *"is there a scorer for 'same voice
   across runs', or is this human-eval only?"* WO-MBCP-03 Phase G.2 measures **face-embedding AND
   speaker-embedding distance across two renders of an identical setup.**
   ⚠ **Scope limit, normative:** AD-09.15's acceptance criterion is *"across two separately created
   **projects**."* The MBCP test is two renders in one window — **the necessary condition, not the
   sufficient one. A pass does not close Q3. A failure settles it negatively and the library must
   not be built.**

**Re-certification is an identity event.** AD-09.4.3 rules that *"an actor's identity is only
reproducible on the engine it was established against; changing the bound engine is an identity
change, and the UI must say so."* AD-09.8 adds that *"changing the actor requires re-running Stages
5/6 onward."*

> ⛔ **Therefore: re-certifying a joint model on a new engine digest invalidates every actor bound to
> it and forces Stage 5/6 re-runs on every course using them.** Neither AD-07 v1.2 nor AD-10 said
> this. **AD-10 §5 must carry it**, and a re-certification that changes the engine digest must be
> announced to IVGS as an identity event, not a routine version bump.

**Reproducibility policy (AD-09.14 Q4) is the operator's, and is NOT to be answered yet.** AD-09.8
already warns *"do not promise reproducibility the pipeline cannot deliver."* **Phase G.2 is the
evidence for whether the promise is keepable. Answer Q4 after it reports, not before.**

---

## §5.4 Talking-head certification preconditions — **AMENDED**

*v1.2's four preconditions stand. v1.3 adds a fifth and reorders, because the order is not optional.*

⛔ **Precondition 0, which outranks all of v1.2's four: there is no scorable benchmark result, and
there cannot be one until the `.52` worker is deployed.** Both accepted renders are on the **bench**
lane, and `quality_metrics.run_result_id` is a foreign key to `run_results` — **the bench lane cannot
carry a quality metric at all, by schema.** `davinci-magihuman` has exactly one benchmark result and
it **errored on a fixture defect** since fixed by `c3a093f`, never re-run. **However good the metrics
become, there is nothing for them to act on.** And the `.52` worker still runs pre-`weight_fetch_error`
code, so a re-run today inherits a defect WO-MBCP-01 already closed.

Then, in order: **(1)** the §4.7.3 gate exists and passes its own acceptance test · **(2)** the
adapter declares its contract and `driving_mode` is recorded on the run and carried onto the
certificate · **(3)** host-RAM sampling exists in the lane the renders run in · **(4)**
`davinci-magihuman` is bound to `ivgs_stage` with a tier and a **benchmark** run produces the
evidence · **(5)** ⭐ **under §4.7.0a, both `tts` and `talking_head` certificates exist** — one
without the other is not a joint-capable model.

**Standing prohibition, unchanged:** `wan22-s2v-14B` is **not to be certified.** Its `license` column
stays NULL.

**The option that remains open, and is the operator's alone:** certify MagiHuman under an audited
`allow_incomplete` override, accepting that joint-mode metrics are absent and recorded as absent, to
unblock IVGS. A legitimate choice with a visible cost. **Not the default; no agent may take it.**

---

## §6.4 Sequencing — **AMENDED**

Two pointers change; the phase structure does not.

- *"Runs alongside Phase 0: **WO-MBCP-02 Phase 5**"* → **`WO-MBCP-03`.** Phase 5 delivered its §5.1
  ruling and its acceptance test; the build remainder moved.
- **Phase 3's talking-head long-form suite** is gated behind §4.7.3, §4.7.4 **and now §5.4
  precondition 0** — the worker deployment, which is an operator action and gates everything after it.

⭐ **New cross-repo note.** **IVGS AD-09.13 item 6 (voice/video coupling) is gated on this
amendment's §4.7.0a and on MagiHuman certification.** §4.7.0a is now delivered. Certification is the
remaining gate. **IVGS items 1–5 are unaffected and correctly proceeding** — verified against the
tree: `actors`, `library_assets` and presets are built, and `voice_video_coupling` appears nowhere.
**The delay is MBCP-side, and IVGS's sequencing was right.**

---

*v1.3 supersedes v1.2 **for §4.7, §5.4 and §6.4 only**. All other sections carry from v1.2 unchanged.
Ratification of v1.3 adds, as operator decisions requiring their own Appendix-G rows: the **two-stage
joint contract** (§4.7.0a), the **`driving_mode` recording requirement** (§4.7.1), the **adoption of
IVGS's `av_drift_seconds`** (§4.7.3a), the **output-geometry recording requirement** (§4.7.4), and
the **deferral of presenter identity to AD-09.4.3** (§4.7.6).*

***v1.3 awaits ratification.***
