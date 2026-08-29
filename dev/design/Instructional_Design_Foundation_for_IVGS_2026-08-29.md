# Instructional Design Foundation for IVGS

**2026-08-29 · Normative input for Phase 1 (the Design Core). The stage-1 extraction prompt, the stage-2 design prompt, and every per-scene generation prompt are written FROM this document. Drawn from canonical frameworks: backward design (Wiggins & McTighe), Bloom's taxonomy as revised (Anderson & Krathwohl), Gagné's Nine Events of Instruction, Merrill's First Principles, Mayer's multimedia principles, and cognitive load theory (Sweller). These are decades-stable, textbook-level frameworks; the operator or agent should verify any point against a current ID reference where stakes demand it.**


> ⚠ **CORRECTION NOTE — 2026-08-29, WP-IVGS-12, OPERATOR RULING. Applies to §4's
> modality table, §6's field list and §8's worked application.**
>
> **1. `talking_head` IS NOT A `media_type` ON THIS SYSTEM, and writing it as one
> does not degrade — it fails the whole storyboard.** The enum, the PostgreSQL
> type and `MEDIA_TYPE_SYNONYMS` all carry exactly `image`, `video_clip`,
> `animation`, `motion_graphics`. `_validate_storyboard_json` RAISES on anything
> else by design (`ivgs-workers/tasks/stage2_storyboard.py:304-311`), and ledger
> RC-P4 records one such scene killing an entire run the first time a storyboard
> model chose a value the enum lacked. The talking head is a pipeline STAGE that
> renders once and is composited as an overlay across the whole video.
>
> **RULED:** `talking_head` stays OUT of `media_type`; the v8 prompt refuses it
> explicitly by name; **RULE 13 routes the human/social moments of §4's table —
> welcome, objectives, encouragement, recap — to `image`**, which is the one
> place a plain still is the right answer rather than a failure of nerve; and
> **the project-level talking-head track continues to serve social presence
> globally.** §8's rows 0 and 1 read `talking_head/image` and `talking_head`;
> read both as `image`.
>
> §4's pedagogy is NOT withdrawn — social presence does serve events 1, 2, 7 and
> 9. What the system lacks is per-scene presenter SELECTION, which is a genuine
> capability gap and not a prompt defect. Registered as **RC-Q4, a Phase-5
> candidate and an operator decision**, in `OUTSTANDING_WORK.md`.
>
> **2. §6's `modality_rationale` ALREADY EXISTS AND IS CALLED `media_rationale`.**
> v7's RULE 9 asked the identical question — why THIS medium for THIS scene — and
> migration 0045 gave it that column. **RULED: one fact, one column, the existing
> name.** The Design Contract uses `media_rationale` on the wire. A second column
> would create the drift class this repository has been bitten by repeatedly (the
> WP-64 delimiter; RC-C's four sources of truth). This document stays normative on
> WHAT must be declared; it does not rename a declaration that already has a name.
>
> **3. §6's `guided_json` is superseded** — see the banner on
> `IVGS_Root_Cause_Audit_and_Recovery_Plan_2026-08-29.md`. The measured mechanism
> of record is `response_format: {"type": "json_schema", "strict": true}`.
>
> Evidence: `dev/workpackages/reports/WP-IVGS-12-DESIGN-CORE-report_2026-08-29.md`
> §3 and §5.

---

## §1 What a professional instructional designer actually does

Not: "turn this script into scenes." The professional sequence is **backward design**, three stages in strict order:

1. **Identify desired results.** Start from the learning outcomes — not the content. Interrogate them: are they measurable? What must the learner be able to *do* afterward?
2. **Determine acceptable evidence.** Before designing any instruction, decide what would *prove* each outcome was achieved — the practice items, checks, and demonstrations the learner will perform.
3. **Plan learning experiences.** Only now design the instruction — choosing, sequencing, and *rewriting* content (including a supplied script) so every minute serves stages 1–2. Source material is raw material to the designer, honored for its substance, never sacred in its wording.

**The alignment triad is the profession's core law:** every learning activity must trace to an outcome, and every outcome must have evidence. In IVGS terms: **every scene declares which outcome(s) it serves and what role it plays in proving them; any scene that serves nothing is decoration and is cut; any outcome served by nothing fails the design at the gate.**

## §2 Outcomes discipline (what stage-1 extraction must enforce)

An outcome must be **measurable**. The working format is ABCD — *Audience, Behavior, Condition, Degree*: "Given two 2-digit numbers **(C)**, the learner **(A)** will compute their product using the standard column algorithm **(B)** with correct partial products and carries **(D)**."

The **Behavior verb sets the Bloom level**, and the Bloom level dictates the kind of instruction and evidence:

| Level (revised Bloom) | Verbs (sample) | Instruction it demands | Evidence it demands |
|---|---|---|---|
| Remember | list, name, recall | tell + show, mnemonic | recall check |
| Understand | explain, compare, summarize | example + non-example, analogy | learner restates / predicts |
| **Apply** | compute, execute, use | **worked example → faded example → independent problem** | learner performs the procedure |
| Analyze | break down, attribute | guided decomposition | learner identifies parts/errors |
| Evaluate | judge, critique | criteria + contrasting cases | learner judges with reasons |
| Create | design, construct | scaffolded open task | learner produces artifact |

If an operator-supplied outcome is unmeasurable ("understand multiplication"), the designer **proposes an ABCD-refined version at the gate for approval** — it never silently substitutes, and never designs against fog.

The multiplication project's outcomes are **Apply-level**, which activates the single most robust finding in mathematics instruction: the **worked-example effect** — novices learn procedures best from complete worked examples, then *faded* examples (learner supplies missing steps), then independent problems. The uploaded script already embodies this arc (full 23×14 walkthrough → second problem 32×21); a designer *recognizes* that structure and preserves its function even while rewording.

## §3 The course arc — Gagné's Nine Events as the scene-sequence skeleton

Every effective lesson, whatever the medium, walks these events. They become the `instructional_event` enum on every scene:

| # | Event | enum value | Multiplication-script example |
|---|---|---|---|
| 1 | Gain attention | `hook` | the "seems tricky, we'll break it down" opener |
| 2 | Inform objectives | `objective` | "by the end you'll solve 23×14 yourself" |
| 3 | Stimulate recall of prior learning | `recall_prior` | ones/tens place value; single-digit facts |
| 4 | Present content | `present` | the algorithm's steps, shown |
| 5 | Provide guidance | `guide` | the four-step trick; "line up the ones digits" |
| 6 | Elicit practice | `practice` | learner attempts a step / the second problem |
| 7 | Provide feedback | `feedback` | confirm 92, correct the carry |
| 8 | Assess | `assess` | full second problem, learner-first |
| 9 | Enhance retention & transfer | `transfer` | "same trick works for any two-digit pair"; recap |

Merrill's First Principles are the cross-check on the whole design: **problem-centered** (anchor on the real task, 23×14, not abstractions), **activation** (event 3 present), **demonstration** (events 4–5), **application** (events 6–8), **integration** (event 9). A storyboard missing application is a lecture, not a lesson — the validator flags any design whose scenes never leave events 1–5.

AD-09's structural scenes map cleanly: `intro` template ≈ events 1–2 scaffold; `outro` ≈ event 9. The enum and `scene_kind` are complementary, not duplicates.

## §4 Modality selection — the decision the designer makes per scene

Chosen per *instructional moment*, governed by Mayer + cognitive load theory. Operationalized:

**The principles that bind (each is a checkable rule, not a vibe):**
- **Modality**: explain with *narration + graphics*, not on-screen text + graphics — words go to the ear while eyes parse the visual.
- **Redundancy**: do NOT put the narration's sentences on screen as text. (On-screen text is for *labels, symbols, and the worked math itself* — which narration cannot carry. **This is RULE 1's pedagogical justification**: the digits belong on screen precisely because they are the content, drawn by a renderer, never duplicated prose.)
- **Signaling**: highlight what matters as it's narrated — the carry turns red *when the voice says "carry the 1."* This is the motion-template `phase`/highlight mechanism's purpose.
- **Segmenting**: one step per scene at novice pace. (The system's scene model already does this; the designer decides the cuts by *step*, not by sentence count.)
- **Coherence**: cut decorative content that serves no outcome — the teddy bears audition against this rule.
- **Contiguity**: labels beside the thing they label; feedback beside the attempt.
- **Personalization**: conversational "we/you" narration (the script already does this; refinement must not formalize it away).

**The modality decision table (per scene = content kind × event):**

| The scene's content is… | Best modality | IVGS medium |
|---|---|---|
| Symbolic procedure (math steps, formulas, code) | narrated build-up of the symbols, signaled step-by-step | `motion_graphics` (RULE 8) |
| Static structure/context, affect, scenario framing | narrated still | `image` (no digits, no prose on surfaces) |
| Dynamic physical/spatial process | narrated motion | `video_clip` |
| Human/social: welcome, objectives, encouragement, feedback, recap | presenter on camera (social presence aids exactly these events) | `talking_head` overlay scenes — events 1, 2, 7, 9 are its natural home |
| Learner-attempt moment | prompt + pause + reveal, signaled | `motion_graphics` with `practice`-shaped template (pose the problem, hold, then reveal) |

**Cognitive-load rules the validator can enforce:** narration for a `present`/`guide` scene ≤ ~2 sentences per visual change (segmenting); no scene both introduces a new concept AND assesses it (load separation); every `practice` scene is preceded by a `present`/`guide` on the same outcome (the fading sequence); on-screen text on diffusion media = refusal (redundancy + RULE 1-EXTENDED, already built).

## §5 What this makes the prompts (the "front of the prompt" requirement)

**Stage-1 extraction prompt** opens with §1's role: *you are extracting design inputs, not editing prose* — outputs: outcome list (ABCD-validated or refinement-proposed), script beat list with source spans + the event each beat naturally performs + Bloom level touched, description-derived audience/tone/constraints.

**Stage-2 design prompt** opens with §1–§4 compressed: *you are an instructional designer executing backward design* — design the event arc for these outcomes at this audience level; place every beat; rewrite narration where the design requires (marked, original preserved); declare drops; choose modality per §4's table; emit the design contract under the schema.

**Every per-scene generation prompt (stage 3 onward) is HEADED by the scene's instructional block** — this is the "for every scene" requirement:

```
INSTRUCTIONAL CONTEXT (binding):
  serves_outcomes: [LO-1]           bloom: apply
  event: guide                       arc position: 5 of 9
  learner_state: has seen 4×3=12, carry pending
  evidence_link: prepares practice in scene 7
  modality_rationale: symbolic procedure → motion_graphics (Mayer-modality, RULE 8)
  signaling: highlight carry digit at t≈word("carry")
```
…so the image prompt writer, the motion authoring, the TTS direction, and the composition all know *what this scene is for* — a `feedback` scene's visual warmth differs from an `assess` scene's neutrality, and now the prompt says so instead of hoping.

## §6 The design contract additions (schema, Phase 1)

Per scene, added to the existing contract: `serves_outcomes[] (≥1)`, `instructional_event (enum §3)`, `bloom_level (enum §2)`, `source_refs[] | origin:"designed"`, `rewrite_of (span, when reworded)`, `modality_rationale (one line, §4 table row)`, `signal_spec (optional, §4 signaling)`. Project-level: `outcomes[] (ABCD-normalized)`, `dropped_beats[] (span + reason)`, `evidence_map (outcome → assessing scene ids)`. All under `guided_json`; the validator enforces the triad (every outcome served AND assessed; every beat used or dropped-with-reason; §4 load rules).

## §7 The gate becomes a design review

The reviewer sees, before any pixel is rendered: the outcomes (with any ABCD refinements to approve), the event arc, the outcomes × scenes matrix with the evidence column, every rewrite diffed against its source span, every drop with its reason, and the modality rationale per scene. Approving *this* is approving a course design — which is what a storyboard gate was always supposed to be.

## §8 Worked application (first beats of the multiplication project — illustrative)

| # | event | serves | medium | design note |
|---|---|---|---|---|
| 0 | hook | LO-1 | talking_head/image | girl + "tricky, we'll break it down" — coherence-checked |
| 1 | objective | LO-1 | talking_head | "you'll solve 23×14 yourself" (ABCD degree stated) |
| 2 | recall_prior | LO-1 | motion_graphics | place-value columns; 4×3 flash — recall, not new content |
| 3 | present | LO-1 | motion_graphics | setup: 23 over 14, line — signaled as narrated |
| 4 | guide | LO-1 | motion_graphics | 4×3=12, write 2 **carry 1 highlighted on the word** |
| 5 | guide | LO-1 | motion_graphics | 4×2+1=9 → 92 complete-row phase |
| … | practice→feedback→assess | LO-1 | motion practice-template + talking_head feedback | second problem 32×21 learner-first, per §2 fading |

The designer *keeps the script's arc because it's pedagogically right*, rewrites freely where narration must match the signaled visual beat-for-beat, and can now justify every scene in one line each. That justification, machine-checked, is what has been missing.
