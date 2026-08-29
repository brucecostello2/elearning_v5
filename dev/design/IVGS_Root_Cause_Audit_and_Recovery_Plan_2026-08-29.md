# IVGS — Root-Cause Audit and Recovery Plan

> ⛔ **SUPERSEDED IN ONE PARTICULAR — BANNERED BY WP-IVGS-12, 2026-08-29, NOT SILENTLY REINTERPRETED**
> (`dev/CLAUDE.md` §0 rule 5 step 3: a superseded instruction gets implemented as written.)
>
> **§1 RC-A step 4 and §4 Phase 1 both prescribe vLLM `guided_json`. On the pinned engine that is
> a silent no-op.** Measured 2026-08-29 against `vllm/vllm-openai@sha256:3dbe092e…` on node-02
> (vLLM `0.19.2rc1.dev134+gfe9c3d6c5`): `guided_json` returns **HTTP 200 and is discarded** —
> output byte-identical to an unconstrained call, and it still returns 200 when handed
> `{"type":"not_a_json_type"}` or the bare integer `12345`. So does `guided_choice`, and so does a
> field name invented for the test. **The engine drops unknown top-level body members without
> comment**, so building on `guided_json` would have shipped a permanent no-op that reports success.
>
> ✅ **The replacement, measured ENFORCING on a realistic nested contract (closed enums, a `oneOf`,
> `minItems`, `additionalProperties:false`): `response_format: {"type": "json_schema", "strict":
> true}`.** `structured_outputs: {"json": …}` measured equivalent and is held in reserve.
> **No digest change — the WP-62 pin stands.** Read every "guided_json" below as that mechanism.
>
> Evidence: `dev/workpackages/reports/WP-IVGS-12-DESIGN-CORE-report_2026-08-29.md` §1.3; probes and
> raw output banked at `dev/workpackages/reference/wpivgs12-prompt-stack/`.
>
> **Also closed by that report: §RC-I4's unexplained coordinated reboots** — the cause is a nightly
> operator power-down, supplied by the operator 2026-08-29.


**2026-08-29 · Audited from the operator-supplied codebase zip (539 Python files) plus 48 hours of live measurements. Every claim below carries file:line from the zip or a measured incident from this session.**

---

## §0 Executive verdict

The system is not riddled with sixty independent bugs. It is **~90% sound plumbing wrapped around six root causes**, and every incident of the last 48 hours maps onto one of them. The reason it feels non-convergent is that the work-package process — my process — fixed the *incident* each time and left the *cause* standing, so the same cause produced a fresh incident within hours wearing a different face.

The single most important sentence in this audit: **the pipeline was designed to transform raw transcripts into videos, and you are feeding it finished scripts.** Stage 1's system prompt orders the model to *"transform,"* *"reduce complexity,"* *"eliminate redundancy,"* and *"align with max_runtime_seconds"* (`ivgs-workers/prompts/stage1_system.j2`; `stage1_transcript.py:750-761`). Your multiplication script — two worked examples, the four-step trick, ~4 minutes read aloud — went in, and a paraphrased 8-scene / ~1:45 condensation came out, *by design*. Everything downstream then faithfully rendered the wrong lesson. No downstream fix can recover fidelity that stage 1 discarded.

Recovery is six phases, each one order, each with a mechanical exit test, ending in **THE TEST**: this exact script produces a watched video in which every scene's visual depicts its narration and the mathematics is correct end to end. That is the only definition of "operational" this plan accepts.

---

## §1 The six root causes

### RC-A — There is no design function *(the content killer — REWRITTEN per operator correction 2026-08-29)*

**The operator's formulation, adopted as the diagnosis:** the system must extract INTENT from the script, INTENT from the description, and INTENT from the learning outcomes, and **design** a storyboard whose scenes serve the integrated intent — rewriting the script where intent requires it, never merely shrinking it to fit and never merely preserving it. Instead the three inputs are wired as separate strings and one of them gets *sequenced*. The original audit's "script-canonical mode" repeated the same category error in reverse (verbatim sequencing) and is **withdrawn**.

This is not a new requirement — it is AD-07's own ratified thesis with its consequence drawn: *"the storyboard is the canonical, machine-executable production contract; downstream workers execute it without reinterpreting the course."* If downstream may never reinterpret, **all design authority lives at stage 2**. Stage 2 currently has none.

**Evidence the inputs are separate today:** `learning_outcomes` travels as a delimited text block *inside* `project_description` (P2.66 — the hand-off literally parked); the scene contract is five fields with no outcome refs, no source refs, no design rationale (code-verified 2026-08-22 assessment §5; its G4 named the missing scene→source linkage six days ago); stage 2's prompt demands narration "Verbatim… (from refined transcript)" (`prompts/stage2_system.j2:10`) — an excerpter fed by a compressor:

| Evidence | Where |
|---|---|
| System prompt: "transform raw transcripts… refined, audience-appropriate narrations… reduce complexity… eliminate redundancy… align with max_runtime_seconds" | `prompts/stage1_system.j2`; `stage1_transcript.py:750-761` |
| Stage 2 then *excerpts the refined text*, not your script: "narration_text … (from refined transcript)", "excerpt from the transcript" | `stage2_storyboard.py:909-912`; `prompts/stage2_system.j2:10` |
| Duration pressure compounds it: `max_duration_seconds = context max_runtime_seconds` feeds both prompts | `stage2_storyboard.py:132,897` |
| No mode anywhere says "this is a finished script — segment it, do not rewrite it." No check anywhere compares output narration to input script. | absence, verified by grep |

**Incidents it explains:** the 8-scene storyboard from a 20+-beat script; the "generic" narrations; the second example (32×21) and four-step trick at risk of vanishing; the whole "content not related to the uploaded script" complaint. Also the *original* 14-scene project's oddities — every run so far has rendered a paraphrase.

**Fix principle — the DESIGN CORE (replaces both the built behavior and the withdrawn script-canonical mode):**
1. **Intent extraction** (repurposed stage 1): from the *script* → an ordered beat list (concept / worked-example / step / check / recap) with source spans; from the *description* → audience, purpose, tone, constraints; from the *learning outcomes* → the assessment spine (promoted to a first-class input, closing P2.66's parked hand-off). Extraction, not rewriting.
2. **Design** (stage 2): scenes are *designed against the integrated intent*. Every scene declares `serves_outcomes[]`, and either `source_refs[]` (script spans it uses — verbatim or **rewritten in service of intent, marked as rewritten with the original alongside**) or `origin: designed` with a one-line rationale (material the intent required that the script lacked). Duration *derives from* the design; it never drives it. Beats consciously dropped are declared in `dropped_beats[]` with reasons — dropping is a design decision, not silent loss.
3. **Intent-coverage validation at the gate** (deterministic, on the declared structure): every learning outcome served by ≥1 scene; every script beat either sourced or consciously dropped; digit-bearing content still forced to motion/carried per RULE 1-EXTENDED. The gate reviews **the design brief** — outcomes × scenes × sources, rewrites diffed — not just thumbnails.
4. **Schema-constrained decoding** (absorbs old RC-B): the design contract is emitted under vLLM `guided_json` — `serves_outcomes` required, `source_refs` ⊕ `origin:designed` enforced, `media_type` enum, motion ⇒ `template`+`params` required. Compliance becomes structural, not behavioural: RC-P15's 5/0/4 erraticism (three identical runs, three different medium choices) cannot survive a schema that refuses the escape hatches.

### RC-B — *(merged into RC-A step 4)* A free-running LLM sat at the correctness core; the design contract + constrained decoding is its cure. Retained as a label only so the incident map below still reads.

### RC-C — Four sources of truth about one pipeline *(the confusion engine)*

`projects.state`, the checkpoint ledger, `render_jobs.job_type` (frozen at creation), and the frontend's own computation all describe the same run and routinely disagree. The UI *admits it in a banner*: "the stepper is computed from checkpoints… the stored state column says DRAFT, which is behind the work recorded." Measured this session: `INVALID_STATE_TRANSITION: DRAFT → TALKING_HEAD_RENDER` warnings mid-healthy-run (`project_service.py:308`); Jobs tab showing "transcript refinement / under 1s" for a 90-second run that died at stage 7; P1.4q's failed-callback resetting live projects to DRAFT (`project_service.py:573`, `project_progress.py:24` — c12fa967 is its named victim); Resume dispatching stage 7 with zero scenes (`jobs.py:200-245`, RC-N7).

**Fix principle:** the checkpoint ledger is *already* authoritative (the error messages say so; the stepper says so). Make it official: job label = latest checkpoint stage; duration = ledger span; Resume derives its stage from the ledger; `projects.state` becomes a derived cache with the transition-refusal downgraded to a log line. One truth, three mirrors.

### RC-D — Partial-advance is the wrong policy under a human review gate *(the misleading failures)*

A failed media stage *continues* — dispatches talking-head, audio, composition — then fails terminally with the *last* stage's name on it (`pipeline_orchestrator_v2.py:425-428, 1007-1059`; the checkpoint ledger even carries an apology explaining which stage "really" failed). This burned GPU on doomed runs three times yesterday and mislabeled every one of them.

**Fix principle:** under the current design (a human reviews the draft anyway), a failed media sub-stage should **hold at a reviewable state** — like a gate, named, resumable per-scene — not advance. Partial-advance made sense for unattended batch; you don't run unattended batch.

### RC-E — Declared-but-dead error paths *(the silent lies)*

The house pattern, still alive in the error layer: a DLQ read-and-replay surface over a table **nothing has ever written** (routing now 405s honestly — RC-N10/M7); `error_classifier` tagging everything `classified_default_transient` including hard config errors; `_save_storyboard_scenes` swallowing non-2xx (frozen body); and the gate's **Regenerate button sitting beside Approve with no confirmation and no "this discards your six edits" warning** (`GateReviewPanel.tsx:39-44` — three decisions, no destructive-action guard), which is exactly how tonight's storyboard was wiped. Plus stale UI text still citing closed RC-P1.

**Fix principle:** one batch: build the small DLQ write side (failures are frequent; the read surface already exists), give the classifier real classes for the ten errors actually seen this week, and make Regenerate a typed-confirm that *shows what it will discard*. The swallow waits for RC-F.

### RC-F — The freeze inversion *(the velocity killer and bug-shaper)*

Eight stage bodies are frozen to protect a Temporal conformance bank **that still does not exist**, while the shadow implementation it protects has been complete for weeks (4,384 lines, semantics proven). Meanwhile every real fix contorts around the freeze — wrappers, two-site exceptions, an unfixable swallow, a fallback that woke from the dead (`falling_back_to_sadtalker`, fired live 20:03 against a ruling) — and each contortion is itself a new bug surface. **The freeze now generates more risk than it retires.** Its runway is short and fully specified (M3.3-R1…R5 in the register).

**Fix principle:** don't lift the freeze — **finish it**. The moment Phases 1–2 produce one correct video, bank it as the golden run and execute M3.3 within days: `temporalio` in, worker service up, stubs realized (the gate-table edits execute here), conformance replay against the bank, cutover. Everything frozen-gated then closes in one sweep instead of dribbling exceptions.

### RC-G — Capacity stacking on node-04 *(the OOM class)*

`vllm-midsize` holds 92.5 GB resident on the same card as every image/TTS/talking-head engine; LatentSync OOM'd at **4.31 MiB free** *while holding a reservation* — reservations account, they don't evict (AD-08's known gap, now with live evidence). Every talking-head render is currently a coin-flip against whatever else is resident.

**Fix principle:** an operator ruling with three options, measured before choosing: (a) cap `vllm-midsize`'s `gpu-memory-utilization` to leave a measured headroom envelope; (b) relocate midsize (node-02 alongside primary won't fit — 88 GB resident; node-05 has ~6 GB free — won't fit; so (b) really means "retire midsize until AD-08"); (c) gate talking-head dispatch on *measured* free VRAM, refusing loudly. My recommendation: **(a) now, (c) as the permanent guard.**

### RC-H — The inputs model fights the operator *(the SQL-flip class)*

The creation form makes a reference clip **mandatory** while the pipeline treats it as optional (a clean skip exists: `talking_head_task.py:436-444`); no GUI lists or unassigns reference clips (P2.18's real residue), so removing a presenter takes SQL; assets carry model provenance as an unconstrained **name string** (205 audio assets, D-4's rename hazard); and the gallery now says "newest asset is document" because of our own flip. Small stuff, but it's why operating the system requires me.

**Fix principle:** presenter optional at creation; a reference-clip section under Media Assets (list/assign/unassign); gallery picks newest *renderable* asset. D-4 rename ruling: **move the orphan** (`Kokoro`, 1 approval row) not the rendering row (524 unprotected history references) — per the seam measurement.

---

## §2 Incident → cause map (last 48 h)

| Incident | Cause |
|---|---|
| 8 scenes / 1:45 from a 4-minute script; "generic" narration; second example endangered | **RC-A** |
| Wrong math vs voice (first draft); identical params across five scenes; 5/0/4 motion-scene erraticism; six gate refusals | **RC-B** (RC-A upstream) |
| Jobs tab wrong type/duration; "transcript refinement FAILED" for a stage-7 death; DRAFT resets; INVALID_STATE warnings; vacuous Resume "success" | **RC-C** |
| Talking-head/composition running after media failed; terminal error naming the wrong stage; wasted GPU | **RC-D** |
| DLQ 405 on every failure; everything "transient"; storyboard wiped by adjacent Regenerate; stale RC-P1 gate text | **RC-E** |
| Stage-2 params stripped (needed exception #2); SadTalker fallback firing against a ruling; swallow unfixable; 120s limit undetectable by its own test | **RC-F** |
| LatentSync OOM at 4 MiB free under a held reservation | **RC-G** |
| Presenter removal via SQL; mandatory-clip form; "newest asset is document" card | **RC-H** |
| *(Fixed for good this session, cause closed: picker medium map, scene-scoped dedup, mpeg4 encode, 120s→300s policy application, engine env over-share, silent-no-op deploys, board truth protocol)* | — |

---

## §3 Why the process didn't converge — accountability

1. **Orders were scoped to incidents, not causes** (mine). Each fix was real; the cause re-presented within hours.
2. **Acceptance was "it renders," not "it teaches"** (mine). A draft existing said nothing about the lesson being right.
3. **The freeze forced every fix into contortions** (mine to enforce; right instinct, wrong duration). Wrappers and exceptions are bug-shaped.
4. **A rewriting stage 1 sat undiagnosed** because nobody compared output narration to input script — including me, while reviewing storyboards scene by scene.
5. What *did* work — and stays: measure-first orders, refuse-by-name over silent defaults, count-gated pushes, the close-out protocol, agents correcting their own findings.

**Process change, effective now:** recovery runs as **six phase-orders**, one at a time, each with a mechanical exit test the operator performs; no micro-orders against content; micro-orders remain only for genuine plumbing breaks. Every phase ends with `CLOSE OUT`.

---

## §4 The recovery plan

> Each phase = one order to one fresh agent session, full suite discipline, commit-and-hold, exit test performed by the operator before the next phase starts. Golden project `4ca0d5c5` stays untouched throughout; it becomes the Phase-6 vehicle's predecessor, not its subject.

**Phase 0 — the ruling sitting (operator, ~10 minutes, this message).** Five rulings, listed in §5 with recommendations. Everything below encodes them.

**Phase 1 — THE DESIGN CORE (RC-A, all four steps), built on the Instructional Design Foundation. Size L — the centerpiece.**
**Normative input: `Instructional_Design_Foundation_for_IVGS_2026-08-29.md`** (operator-directed; backward design, Bloom/ABCD outcome discipline, Gagné event arc as the `instructional_event` enum, Merrill cross-checks, Mayer/CLT modality decision table). The stage-1 and stage-2 prompts are written FROM that document, and **every per-scene generation prompt is headed by the scene's instructional block** (§5 of the foundation). Intent extraction from all three inputs (learning outcomes promoted to first-class, ABCD-validated-or-refined-at-gate, closing P2.66's park); stage 2 redesigned as instructional designer emitting the design contract (§6 of the foundation: `serves_outcomes`, `instructional_event`, `bloom_level`, `source_refs`/`origin:designed` with rewrite-marking, `modality_rationale`, `dropped_beats`, `evidence_map`) under `guided_json`; the storyboard gate renders the **design brief as a design review** (§7). *Exit test: this script + description + explicit learning outcomes → a gate showing every outcome served AND assessed, the Gagné arc complete through application, both worked examples present (used or consciously redesigned with stated reasons), zero silent drops — and three consecutive generations produce structurally valid contracts with zero refusals.*

**Phase 2 — *(absorbed into Phase 1; number retained so later phases keep their names in prior discussion)*.**

**Phase 3 — One truth (RC-C + RC-E's UX half). Size M.**
Ledger-authoritative read model: job label/duration from checkpoints; Resume derives from ledger; state column demoted to cache; Regenerate gets typed-confirm + discard preview; stale texts purged. *Exit test: on a fresh run, Jobs tab matches the ledger at every stage; Regenerate demands confirmation naming what dies.*

**Phase 4 — Failure semantics (RC-D + RC-E's DLQ/classifier half). Size S-M.**
Media-stage failure ⇒ named reviewable hold, per-scene resumable; DLQ write side built; classifier gains the ten real classes from this week's log corpus. *Exit test: kill one scene's render mid-run; pipeline holds at the media gate naming that scene; DLQ shows the row; nothing downstream ran.*

**Phase 5 — Capacity + inputs (RC-G + RC-H). Size S.**
Midsize capped per ruling; talking-head dispatch gated on measured free VRAM (refuse loudly); presenter optional at creation; reference-clip management UI; gallery fix; D-4 orphan rename per ruling. *Exit test: talking-head renders on the golden vehicle with the clip present, no OOM, no SQL anywhere.*

**Phase 6 — THE TEST.**
Fresh project: this exact script + a real description + explicit learning outcomes, presenter clip attached, defaults, zero SQL, zero agent involvement in the run. Operator reviews the **design brief at the gate** (outcomes served, sources honored, rewrites justified, drops conscious), then watches the full video. **Pass = the video demonstrably teaches the stated learning outcomes; the script's substance is present or consciously redesigned with visible reasons; every scene's visual depicts its narration; 23×14=322 and 32×21=672 correct on screen; audio matches; talking-head present.** On pass: bank everything as the **golden run** — the Temporal conformance target.

**Phase 7 — Finish the freeze (RC-F).**
M3.3-R1…R5 against the bank; cutover; the frozen-gated register rows (fail-open flip, video `get_binding`, the swallow, the fallback removal, O-3…) close in one sweep. The system exits recovery *and* exits its migration in the same act.

Estimated wall time at this week's demonstrated pace: **Phases 1-5 ≈ 2-3 working days of agent time; Phase 6 an evening; Phase 7 its own short window.**

---

## §5 Phase 0 — the five rulings (recommendations attached)

1. **The Design Core** (RC-A as rewritten — intent extraction from all three inputs; stage 2 as designer; design contract with outcome/source/rewrite declarations; intent-coverage gate): adopt as Phase 1? — *Recommend YES.*
   1a. **Rewrite policy**: the designer MAY rewrite script narration in service of intent, provided every rewrite is marked, the original is shown beside it at the gate, and drops are declared with reasons? — *RULED YES (operator, 2026-08-29).*
   1b. ~~Learning outcomes become a first-class input~~ — **CORRECTED BY OPERATOR (screenshot evidence): the form field already exists** (WP-64: "Learning outcomes — what the viewer should be able to do afterwards", read by the storyboard model). What remains parked is the *hand-off* (P2.66: delivered as a delimited block inside `project_description`) and the *discipline* (no ABCD validation, no per-scene `serves_outcomes` linkage, no evidence map). Phase 1 fixes the hand-off and adds the discipline; no new form field is built.
2. **Partial-advance** (RC-D): media failure holds-for-review instead of advancing? — *Recommend YES.*
3. **DLQ**: build the write side (vs delete the surface)? — *Recommend BUILD.*
4. **node-04** (RC-G): cap `vllm-midsize` headroom now + measured-VRAM dispatch guard permanent? — *Recommend YES (option a+c).*
5. **Freeze path** (RC-F): commit to executing M3.3 immediately after Phase 6's bank (no new freeze exceptions before then except via the tested two-site pattern)? — *Recommend YES.*

One word per line answers Phase 0. Phase 1's order is then generated against the answers.
