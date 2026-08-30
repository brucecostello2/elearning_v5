"""Publish the two SYSTEM prompts through the same lineage as the user template.

WP-IVGS-12, on the operator's directive of 2026-08-29: *"v8 must not ship
half-versioned."*

⛳ WHAT WAS HALF-VERSIONED. `stage2_storyboard._resolve_prompts_from_api` returns
`(None, user_template)` and says why in its own docstring: a `prompts` row
carries exactly one text, so the API could only ever supply the USER half. The
SYSTEM half was a `.j2` baked into the workers image — unversioned, unrollbackable
and invisible in the run record. Migration 0047 adds the two `prompt_type`
members; this script publishes into them; and
`pipeline_orchestrator_v2._resolve_system_prompt` renders one and hands it to the
stage in `task_input.system_prompt`, which the frozen body already honours AHEAD
of its file. No frozen edit was needed for any of it.

RUN INSIDE `ivgs-fastapi`:

    sudo docker exec -i ivgs-fastapi python -m app.scripts.wpivgs12_publish_design_prompts

WHAT IT REFUSES TO DO

  * It refuses a design prompt that has lost backward design, the alignment
    triad, the rewrite-marking ruling, or the duration rule. Each is a phrase
    below and each is a defect the recovery plan measured.
  * It refuses an extraction prompt that does not branch on `source_kind`, or
    whose uploaded branch still carries the compressor. That branch IS the fix:
    "align with max_runtime_seconds" turned a four-minute script into 1:45.
  * It refuses a template that does not render — with outcomes and without,
    uploaded and generated. A template that raises at render time takes the
    stage down, and the stage is frozen.
  * It refuses if an identical version is already active, so a second run is a
    no-op rather than a version differing from its predecessor by nothing.

WHAT IT DOES NOT DO. It does not UPDATE or DELETE any earlier version. The
previous active row is preserved inactive and a rollback is one UPDATE.
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Dict, Sequence, Tuple

from jinja2 import BaseLoader, Environment
from sqlalchemy import select

from app.models.prompt import Prompt
from shared.database import async_session_factory

SEED = Path(__file__).resolve().parents[2] / "seed" / "default_prompts"

#: The design prompt's load-bearing content. Each phrase is a defect the
#: recovery plan measured, not a stylistic preference.
DESIGN_PHRASES: Tuple[str, ...] = (
    "BACKWARD DESIGN, IN THIS ORDER",
    "DETERMINE ACCEPTABLE EVIDENCE",
    "Every scene traces to an outcome, and every outcome has evidence",
    "EVERY REWRITE IS MARKED",
    "EVERY BEAT YOU DO NOT USE IS DECLARED",
    "SILENT LOSS IS THE ONE THING YOU MAY NOT DO",
    "DO NOT MERELY SHRINK THE SCRIPT TO FIT A RUNTIME",
    "A DESIGN THAT NEVER LEAVES EVENTS 1-5 IS A LECTURE, NOT A LESSON",
    "DURATION IS AN OUTPUT OF YOUR DESIGN, NEVER AN INPUT TO IT",
    # ⛔ WP-IVGS-12b REPLACES TWO PHRASES HERE, with the reason recorded rather
    # than the entries quietly deleted. v1 gated "COPY EACH ONE INTO
    # `outcomes[].text` EXACTLY AS WRITTEN" and "{{ learning_outcomes }}",
    # because the model was asked to transcribe the owner's outcomes. IT DID
    # NOT: three consecutive generations returned two of three, reworded, and
    # marked them measurable (RC-Q9). The model is not asked any more — code
    # parses `projects.learning_outcomes`, the ids close the schema's enums, and
    # the text is injected server-side. Gating a transcription instruction that
    # must no longer exist would refuse every correct v2.
    "YOU DO NOT WRITE THE OUTCOMES AND YOU CANNOT CHANGE THEM",
    "{{ o.id }} — {{ o.text }}",
    "outcome_notes",
    "proposed_refinement",
    # ⛔ WP-IVGS-12d REPLACES 12c's TWO PHRASES HERE, with the reason recorded
    # rather than the entries quietly deleted — the same discipline 12b used
    # when it dropped v1's transcription phrases.
    #
    # 12c gated "EVERY SCENE YOU NAME IS READ BACK AGAINST ITS OWN TWO
    # DECLARATIONS" and "`practice` or `assess`", because the model wrote
    # `evidence_map` and the gate refused it when the named scenes disagreed.
    # IT DISAGREED ANYWAY, on every outcome of every generation (RC-Q9c): asked
    # to assemble a list its own scenes already implied, the model assembled it
    # wrongly. **The model is not asked any more.** `evidence_map` is gone from
    # contract-4 and CODE derives it from `serves_outcomes` +
    # `instructional_event`. Gating an instruction about naming scenes in a
    # field that no longer exists would refuse every correct v4.
    #
    # What replaces it is the ORDER: the model commits to the evidence before
    # any scene exists, because `assessment_plan` is the schema's first property
    # and declaration order was measured to bind generation order.
    "DESIGN THE ASSESSMENT FIRST, THEN THE ARC THAT REALIZES IT",
    "assessment_plan",
    "evidence_kind",
    "learner_does",
    # Foundation §2's fading pattern, named as the shape practice takes. It is
    # the answer to "what does an `apply` outcome's evidence look like", and
    # without it the plan has a kind and no form.
    "THE FADING SEQUENCE",
    "a COMPLETE worked example",
    "an INDEPENDENT problem",
    # ⛔ WP-IVGS-12e. NOTHING IS REMOVED HERE — this package is additive, and
    # every 12d phrase above survives. What is added is the OPERATIONAL
    # definition of the two evidence kinds, because the measured defect was not
    # that the model refused to build an assessment: it planned one every time
    # and then wrote `assess` ZERO times in 36 scenes across three generations
    # (RC-Q9d), and twelve generations across four regimes showed the same hole.
    # A model that never emits an event it keeps promising does not know what
    # that event IS as a scene. Foundation §3 event 8 ("full second problem,
    # learner-first"), §4's modality table ("pose the problem, hold, then
    # reveal") and §2's fading sequence already define it; v5 states it where
    # the model reads.
    # ⛔ WP-IVGS-12h DROPS FOUR OF 12e's FIVE PHRASES FROM **THIS** TUPLE AND
    # THEY ARE NOT DELETED — THEY MOVED. design-contract-7 splits the design
    # across two calls, and v8 of this prompt no longer authors the independent
    # attempt: a second call against `assessment_authoring_system` does, from the
    # plan and a code-built practice summary and WITHOUT the practice wording in
    # front of it. The three-beat authoring recipe — `POSE THE PROBLEM COLD`,
    # `HOLD — a silent attempt window`, `REVEAL for self-check`, `THE ASSESS IS
    # THE WHOLE PROCEDURE, NOT A FRAGMENT` — is the instruction for writing that
    # scene, so it now lives in ASSESSMENT_PHRASES below and is gated THERE,
    # verbatim. Gating it here would refuse every correct v8.
    #
    # ⛳ AND `THE LEARNER PERFORMS IT UNAIDED` STAYS, WHICH IS THE LINE BETWEEN
    # THE TWO. It is the DEFINITION of the `assess` kind, not the recipe for the
    # scene, and call 1 still has to choose `evidence_kind` between `practice`
    # and `assess` in the plan. A model that no longer knows what `assess` MEANS
    # cannot write a plan worth answering — and the plan is the entire brief the
    # second call works from.
    #
    # `test_v8_moved_and_did_not_lose` asserts every dropped phrase is present in
    # the assessment tuple, so a "drop" that is really a deletion fails a test.
    "THE LEARNER PERFORMS IT UNAIDED",
    # ⛔ WP-IVGS-12f. NOTHING IS REMOVED HERE EITHER — every 12b/12d/12e phrase
    # above survives and a test asserts it. What is added is the sentence the
    # whole lineage turned out to be missing.
    #
    # v5 defined what an `assess` scene IS and changed nothing: 83 scenes across
    # six generations were `sourced`, 0 `designed`, 0 `assess` (RC-Q9e). 12f then
    # measured the mechanism on a second script and it was not ignorance. Given
    # a SPARSE script with no practice material in it, the same model on the same
    # stack invented five scenes and produced the first `assess` this project has
    # recorded; given a script with an explicit "now you try", it anchored to
    # that span and labelled it `practice`. Invention is not absent from the
    # model — it is out-competed by anything the script can supply.
    #
    # So the invitation is replaced by a grammar that does not ask, and this
    # prompt says the same thing in words the model reads BEFORE the schema
    # forces it: the script is source material for the teaching, and the
    # assessments are the designer's own work.
    # ⛔ WP-IVGS-12h REPLACES 12f's HEADING PIN AND MOVES ITS FRESHNESS RULE.
    # v7 headed the section *"THE SCRIPT IS SOURCE MATERIAL. THE ASSESSMENTS ARE
    # YOURS TO AUTHOR — AND SO IS THE PRACTICE."* Under contract-7 the
    # assessments are NOT this call's to author, so the heading is now *"THE
    # SCRIPT IS SOURCE MATERIAL. THE PRACTICE IS YOURS TO AUTHOR."* — 12f's claim
    # kept for the half that is still true, and gated on the new words rather
    # than on words that must no longer appear.
    #
    # `POSE THE PROBLEM COLD, IN FRESH NUMBERS THE SCRIPT NEVER WORKED` moves to
    # ASSESSMENT_PHRASES with the rest of the authoring instruction. It was never
    # about the practice: a practice posed in fresh numbers with nothing on
    # screen IS the assessment, which is the defect RC-Q9g measured.
    "THE PRACTICE IS YOURS TO AUTHOR",
    "ONE ENTRY PER OUTCOME ID",
    "AND YOU DO NOT PLACE THEM",
    # ⛔ WP-IVGS-12g REPLACES EXACTLY ONE PHRASE HERE — the only drop in the
    # package — with the reason recorded rather than the entry quietly deleted,
    # which is the discipline 12b, 12d and 12f each used in turn.
    #
    # 12f gated the literal key `"designed_assessments"`. **That key no longer
    # exists.** design-contract-6 splits it into two REQUIRED per-outcome
    # sections, `assessment_scenes` and `practice_scenes`, because contract-5
    # forced only the `assess` half and RC-Q9f measured the same defect
    # surviving whole in the unforced half: six generations of six refused
    # `PLAN_ENTRY_UNREALIZED` on the one outcome whose plan promised `practice`.
    # Gating a key that must no longer appear would refuse every correct v7.
    #
    # Everything else 12f, 12e, 12d and 12b gated is still above and still
    # required; `test_v7_removed_nothing_v6_gated` reads this tuple rather than
    # a second copy, so the two cannot drift.
    # ⛔ WP-IVGS-12h DROPS `assessment_scenes`, WHICH 12g ADDED ONE PACKAGE AGO,
    # AND IT IS THE SAME DROP FOR THE SAME REASON 12g DROPPED
    # `designed_assessments`: THE KEY IS NOT IN THIS CALL'S SCHEMA ANY MORE.
    # design-contract-7 removes it from `design_contract_schema` entirely, and
    # probe F1 measured that the model CANNOT put it back when ordered to —
    # `additionalProperties: false` at the contract's own top level. Gating a key
    # that must no longer appear would refuse every correct v8.
    "practice_scenes",
    # ⛳ The 12g reversal, pinned because it is the one thing a later package
    # would be most tempted to "tidy" back to a pin. Origin is FREE in both
    # sections: 12f's own TASK 0 measured the model finding a real "now you try"
    # span in script B1 and anchoring to it, twice, and a grammar pinning
    # `designed` would force it to invent a substitute AND to write a rationale
    # asserting the script lacked what the script contains.
    'origin: "sourced"',
    'origin: "designed"',
    # The expository/evidence split, in the words the model reads.
    "SO `scenes` IS THE EXPOSITORY ARC, AND ONLY THAT",
    "THE PRACTICE MUST NOT BE THE ASSESSMENT WEARING A LABEL",
)

#: ⛳ WP-IVGS-12h. THE CALL-2 PROMPT'S LOAD-BEARING CONTENT, AND FOUR OF THESE
#: SIX ARE THE PHRASES DESIGN_PHRASES JUST DROPPED. That is not a coincidence and
#: it is the check: a package that "moves" text has to prove the text arrived,
#: and `test_v8_moved_and_did_not_lose` reads both tuples rather than a third
#: copy of the list.
#:
#: The two that are new are the two the split itself creates. `YOU HAVE NOT BEEN
#: GIVEN THE PRACTICE WORDING` is the mechanism stated to the model — it is told
#: what it cannot see and why, so it does not fabricate a reference to it. And
#: `THE FRESH THING IS THE CASE` is 12g's own finding turned into an
#: instruction: *"where a FRESH NUMBER exists as an axis, the model
#: differentiates; where the outcome is 'explain why' or 'check your work', it
#: has no axis and writes the same sentence twice."* Two of the operator's three
#: outcomes are of that kind, so the prompt names the non-numeric case explicitly
#: instead of leaving "fresh numbers" to cover an outcome that has none.
ASSESSMENT_PHRASES: Tuple[str, ...] = (
    "THE LEARNER PERFORMS IT UNAIDED",
    "POSE THE PROBLEM COLD",
    "HOLD — a silent attempt window",
    "REVEAL for self-check",
    "THE ASSESS IS THE WHOLE PROCEDURE, NOT A\nFRAGMENT",
    "POSE THE PROBLEM COLD, IN FRESH NUMBERS THE SCRIPT NEVER WORKED",
    "YOU HAVE NOT BEEN GIVEN THE PRACTICE WORDING",
    "THE FRESH THING IS THE CASE",
    "assessment_scenes",
)

#: The extraction prompt's. The `source_kind` branch is the whole point.
EXTRACTION_PHRASES: Tuple[str, ...] = (
    '{% if source_kind == "uploaded" %}',
    "YOU ARE NOT EDITING PROSE",
    "COPIED CHARACTER FOR CHARACTER, UNCHANGED",
    "BEATS COVER THE WHOLE SCRIPT",
    "A WORKED EXAMPLE IS ONE BEAT FROM ITS FIRST SETUP LINE TO ITS ANSWER",
    "Flesch-Kincaid",          # the generated branch must still be there
    "Time Alignment",          # ... including the section this package indicts
)

TARGETS: Sequence[Tuple[str, str, Tuple[str, ...], str]] = (
    (
        "storyboard_generation_system",
        "storyboard_design_system.j2",
        DESIGN_PHRASES,
        "WP-IVGS-12h. v8 — THE CALL-1 PROMPT, and what it no longer does. "
        "design-contract-7 splits the design across two engine calls and this "
        "prompt is call 1: the plan, the SUPPORTED practice, and the expository "
        "arc. It no longer authors the independent attempt and `assessment_scenes` "
        "is no longer a key it can emit — probe F1 measured that the model cannot "
        "put it back when ordered to, because `additionalProperties: false` holds "
        "at the contract's own top level. FOUR PHRASES MOVED OUT and none was "
        "deleted: the three-beat authoring recipe (POSE COLD / HOLD / REVEAL) and "
        "'THE ASSESS IS THE WHOLE PROCEDURE, NOT A FRAGMENT' are now gated on the "
        "`assessment_authoring_system` template, verbatim, and a test reads both "
        "tuples so a move that is really a loss fails. 'THE LEARNER PERFORMS IT "
        "UNAIDED' STAYS here, because it is the definition of the kind and call 1 "
        "still chooses `evidence_kind` in the plan — and that plan is the entire "
        "brief the second call answers, which is what makes the split safe for "
        "backward design. The heading becomes 'THE SCRIPT IS SOURCE MATERIAL. THE "
        "PRACTICE IS YOURS TO AUTHOR.' WHY: RC-Q9g. Under contract-6, with the "
        "assessment written first and sitting in context while the practice was "
        "asked for, the model wrote the same scene twice — 9 of 15 outcome-pairs "
        "verbatim identical across five generations, 2 more differing by a "
        "'Let's practice' prefix, and v7 already contained the sentence "
        "forbidding it. "
        "WP-IVGS-12g. THE EVIDENCE LAYER BECOMES STRUCTURAL, COMPLETELY, "
        "closing RC-Q9f in both limbs. `scenes` is stated to be the EXPOSITORY "
        "arc and nothing else — its instructional_event enum is narrowed to "
        "SEVEN events, with `practice` and `assess` removed — and BOTH evidence "
        "kinds are authored in their own REQUIRED per-outcome sections: "
        "`assessment_scenes` (exactly one per outcome) and `practice_scenes` "
        "(one or two, because Foundation §2 fades in steps). Emission order is "
        "backward design complete: assessment_plan, then the independent "
        "attempt, then the supported attempt, then the exposition that prepares "
        "both — the model writes the END of every outcome's fading sequence "
        "while the scene list is still empty. WHY IT IS GRAMMAR AND NOT MORE "
        "PROMPT: contract-5 forced `assess` alone and RC-Q9f measured the "
        "identical defect surviving whole in the kind it left unforced — six "
        "generations of six refused PLAN_ENTRY_UNREALIZED on the one outcome "
        "whose plan promised `practice`, with the plan byte-identical every "
        "time. Four packages now measure one law: on this stack the model's "
        "plan predicts nothing and only the grammar is causal, so 12g applies "
        "it ONCE to the whole layer instead of chasing it kind by kind. It also "
        "kills RC-Q9f limb 2 — contract-5 taught the model the shape of an "
        "authored assessment and it began writing SECOND ones into `scenes` "
        "(four generations of six), which the merge then placed beside their "
        "near-identical twins; `scenes` cannot declare either evidence event "
        "any more. AND ORIGIN IS FREE IN BOTH SECTIONS, which reverses the one "
        "thing contract-5 got wrong: 12f's own second script contained an "
        "explicit unaided problem and the model found that span and used it, so "
        "pinning origin `designed` would force an invented substitute for "
        "material the script plainly has. The grammar guarantees the scene "
        "EXISTS; provenance stays honest under the same XOR every other scene "
        "uses. Placement is code's: each practice after the last present/guide "
        "serving its outcome, each assessment after that practice. "
        "WP-IVGS-12f. THE EXCERPTER IS FORCED TO DESIGN, closing the "
        "prompt half of RC-Q9e. The script is stated to be source material for "
        "present/guide/recall and NOT the source of the assessments: those are "
        "the designer's own work, one invented unaided scene per outcome, posed "
        "COLD IN FRESH NUMBERS the script never worked, then held, then "
        "revealed. This text is not what enforces it — contract-5's "
        "`designed_assessments` is a REQUIRED per-outcome object whose values "
        "are scenes the grammar pins to origin `designed`, instructional_event "
        "`assess` and serves_outcomes [that outcome], so an emission lacking one "
        "is not parseable, and code places each after the last scene serving its "
        "outcome. The prompt exists so the model knows WHY before the decoder "
        "makes it. MEASURED FIRST, on a second script, which is what changed the "
        "diagnosis: v5's operational definitions moved nothing (83 scenes, 0 "
        "designed, 0 assess), and a sparse script with no practice material in "
        "it produced five designed scenes and the first assess event on the same "
        "stack. The model was never unable to invent; it was out-competed by "
        "anything it could anchor to. "
        "WP-IVGS-12d. BACKWARD DESIGN BECOMES THE EMISSION ORDER, closing "
        "RC-Q9c. The design instruction now matches the contract it is judged "
        "against: the model writes `assessment_plan` FIRST — for each outcome, "
        "the evidence_kind (practice|assess) and one concrete sentence on what "
        "the LEARNER does to prove it — and only then designs the scene arc "
        "that realizes it. This is enforced by the decoder and not by this "
        "text: `assessment_plan` is the first property of the contract-4 "
        "schema, and schema declaration order was MEASURED to bind generation "
        "order on the pinned engine, in both directions, against a prompt "
        "explicitly ordering the model to emit `scenes` first. `properties` "
        "order controls; `required` order does not. AND THE MODEL IS NO LONGER "
        "ASKED FOR `evidence_map` AT ALL: it emitted one that contradicted its "
        "own scenes in three generations of three (RC-Q9c), so code derives it "
        "from serves_outcomes + instructional_event instead — 12b's principle, "
        "never ask the model to assemble what code can compute. Three refusals "
        "were deleted and one added: PLAN_ENTRY_UNREALIZED, which checks the "
        "finished design against the promise the model made before it had a "
        "lesson to rationalise from. Foundation §2's fading sequence (complete "
        "worked example -> faded -> independent) is named as the shape practice "
        "takes for an apply-level outcome. "
        "WP-IVGS-12 Task 3 (Phase 1, the Design Core). The stage-2 SYSTEM "
        "prompt, written FROM the Instructional Design Foundation §1-§4 and "
        "published into a lineage for the first time. Stage 2 stops being an "
        "excerpter fed by a compressor and becomes an instructional designer "
        "executing backward design: outcomes first, evidence second, scenes "
        "third; every scene traces to an outcome and every outcome has "
        "evidence; the script is raw material honoured for its substance and "
        "never sacred in its wording, with EVERY rewrite marked and EVERY "
        "unused beat declared. Duration derives from the design and the runtime "
        "figure is advisory — v7 headed the user template 'Total Runtime "
        "Target' and stage 1 was told to 'align with max_runtime_seconds', and "
        "between them a four-minute script became a 1:45 condensation with a "
        "worked example missing. AND THE LEARNING OUTCOMES ARRIVE HERE AS A "
        "FIRST-CLASS JINJA VARIABLE, closing ledger P2.66: they used to be "
        "pasted into project_description between two delimiter lines because "
        "_render_user_prompt fixes the USER template's variable list at nine "
        "names inside a body AD-05 §8 freezes. The SYSTEM slot has no such "
        "cage — task_input.system_prompt is honoured AHEAD of the .j2 file "
        "(stage2_storyboard.py:86-101) and is filled by the orchestrator, "
        "which is not frozen. No freeze exception was requested or needed.",
    ),
    (
        "assessment_authoring_system",
        "assessment_authoring_system.j2",
        ASSESSMENT_PHRASES,
        "WP-IVGS-12h. THE SECOND CALL'S SYSTEM PROMPT, v1 OF ITS OWN LINEAGE "
        "(migration 0053), closing RC-Q9g. design-contract-7 splits the design "
        "across two engine calls and this one authors every outcome's "
        "INDEPENDENT ATTEMPT — from the outcomes, from the `assessment_plan` the "
        "first call wrote before a single scene existed, and from a code-built "
        "fact sheet of what each outcome's practice covered (the numbers it "
        "used, the templates and phases it reached, how long it ran). It is NOT "
        "given the practice narrations, the expository scenes, or the source "
        "script. WHY THE CONTEXT AND NOT THE PROMPT: under contract-6 one call "
        "wrote both kinds with `assessment_scenes` declared first, declaration "
        "order binds generation order on this engine, and so the practice was "
        "asked for with the assessment already in context — and came back as a "
        "copy of it. 9 of 15 outcome-pairs verbatim identical across five "
        "generations, 2 more differing only by a 'Let's practice' prefix, every "
        "generation carrying at least one. v7 ALREADY said 'THE PRACTICE MUST "
        "NOT BE THE ASSESSMENT WEARING A LABEL', in the model's own reading "
        "order, before a single acceptance generation ran; it wrote it twice "
        "anyway. Prompt emphasis was measured not to work, and reordering would "
        "have traded backward design — 12d's measured, load-bearing property — "
        "for a duplicate that would most likely reverse direction. So the calls "
        "separate the kinds and this one cannot copy what it never sees. IT "
        "CARRIES v5's OPERATIONAL DEFINITIONS VERBATIM: 'THE LEARNER PERFORMS IT "
        "UNAIDED', the three beats POSE COLD / HOLD / REVEAL, and 'THE ASSESS IS "
        "THE WHOLE PROCEDURE, NOT A FRAGMENT' — the words moved with the job, "
        "they were not rewritten, and the publisher gates both tuples so a move "
        "that is really a deletion fails. AND IT NAMES THE NON-NUMERIC CASE, "
        "which is 12g's own finding made into an instruction: where a fresh "
        "number exists the model differentiates, and where the outcome is "
        "'explain why' or 'check your work' it has no axis and writes the same "
        "sentence twice — so the prompt tells it the fresh thing is then the "
        "CASE. There is NO file fallback for this prompt, deliberately: "
        "`design_core.assessment_call` refuses rather than reaching for a "
        "baked-in default, because the package's central claim must not be made "
        "by an unversioned string.",
    ),
    (
        "transcript_refinement_system",
        "transcript_extraction_system.j2",
        EXTRACTION_PHRASES,
        "WP-IVGS-12 Task 2. The stage-1 SYSTEM prompt, now branching on "
        "transcripts.source_kind (migration 0046). AN UPLOADED SCRIPT IS "
        "EXTRACTED, NEVER REWRITTEN: the model emits {refined_text: <the "
        "script VERBATIM>, intent: {beats with character spans and the Gagné "
        "event each naturally performs, audience, purpose, tone, constraints, "
        "ABCD-checked outcomes}}. The frozen stage body already unwraps a JSON "
        "response and takes refined_text out of it "
        "(stage1_transcript.py:359-364), discarding every sibling key — so the "
        "body receives the unchanged script and the extraction rides out to the "
        "design brief through the capture observer. A GENERATED transcript "
        "keeps the pre-existing refine-for-readability behaviour BYTE FOR BYTE, "
        "Time Alignment section included, because a generated transcript is raw "
        "material a runtime may legitimately bound and a finished script is "
        "not. MEASURED, and this is why it matters: one 3,172-byte upload sits "
        "in three of the operator's projects as 1,866 / 1,851 / 1,615 "
        "characters of refined_text — three different paraphrases, with no copy "
        "of the original anywhere, because stage 1 reads that column and writes "
        "its output back into it. Migration 0046's source_text ends that.",
    ),
)

_JINJA = Environment(loader=BaseLoader(), keep_trailing_newline=True)


def _fail(reason: str) -> None:
    print(f"REFUSED: {reason}")
    raise SystemExit(1)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _gate(prompt_type: str, text: str, phrases: Sequence[str]) -> None:
    missing = [p for p in phrases if p not in text]
    if missing:
        _fail(f"{prompt_type}: the template is missing {missing!r}")

    # It must RENDER, in every branch, or it takes a frozen stage down.
    matrix: Dict[str, Dict[str, str]] = {
        "outcomes+uploaded": {"learning_outcomes": "LO-1: do the thing",
                              "source_kind": "uploaded"},
        "outcomes+generated": {"learning_outcomes": "LO-1: do the thing",
                               "source_kind": "generated"},
        "none+uploaded": {"learning_outcomes": "", "source_kind": "uploaded"},
        "none+generated": {"learning_outcomes": "", "source_kind": "generated"},
    }
    for label, variables in matrix.items():
        try:
            rendered = _JINJA.from_string(text).render(**variables)
        except Exception as exc:                                 # noqa: BLE001
            _fail(f"{prompt_type}: does not render for {label}: {exc}")
        if not rendered.strip():
            _fail(f"{prompt_type}: renders EMPTY for {label}")

    if prompt_type == "storyboard_generation_system":
        from shared.design.outcomes import parse_outcomes

        raw = "LO-1: SENTINEL-OUTCOME-ONE.\nLO-2: SENTINEL-OUTCOME-TWO."
        parsed = parse_outcomes(raw)
        with_outcomes = _JINJA.from_string(text).render(
            learning_outcomes=raw, outcomes=parsed, source_kind="uploaded")
        without = _JINJA.from_string(text).render(
            learning_outcomes="", outcomes=[], source_kind="uploaded")
        # The outcomes must reach the model...
        for sentinel in ("SENTINEL-OUTCOME-ONE", "SENTINEL-OUTCOME-TWO"):
            if sentinel not in with_outcomes:
                _fail(
                    f"{prompt_type}: {sentinel} does not reach the rendered "
                    "prompt. It would fail silently — the model would design "
                    "without the outcome and nothing would say so."
                )
        # ...and so must the IDS, because the schema's enum is built from them
        # and a prompt that shows text without ids gives the model nothing it
        # is allowed to cite.
        for oid in ("LO-1", "LO-2"):
            if oid not in with_outcomes:
                _fail(
                    f"{prompt_type}: the outcome id {oid} does not reach the "
                    "prompt. The schema closes `serves_outcomes` to these ids; "
                    "a model that never sees them cannot cite one."
                )
        if "SENTINEL-OUTCOME" in without:
            _fail(f"{prompt_type}: renders an outcome that was not supplied")

    if prompt_type == "assessment_authoring_system":
        # ⛔ THE ONE THING THIS PROMPT MUST NEVER DO IS SHOW THE PRACTICE, so the
        # gate proves it cannot rather than trusting that it does not. The
        # template is rendered with the practice, the scenes and the script all
        # supplied as variables; if any of them reaches the output, some future
        # edit has added a `{{ }}` that undoes the whole package — silently, and
        # while every other test still passes, because the model would simply
        # start copying again and the only symptom would be a duplicate.
        leak_probe = {
            "practice_scenes": "SENTINEL-PRACTICE-NARRATION",
            "scenes": "SENTINEL-EXPOSITORY-SCENE",
            "combined_transcript": "SENTINEL-SOURCE-SCRIPT",
            "learning_outcomes": "SENTINEL-OUTCOME-TEXT",
            "source_kind": "uploaded",
        }
        rendered = _JINJA.from_string(text).render(**leak_probe)
        leaked = [k for k, v in leak_probe.items()
                  if v.startswith("SENTINEL") and v in rendered]
        if leaked:
            _fail(
                f"{prompt_type}: the template RENDERS {leaked} into the call-2 "
                "prompt. design-contract-7's entire mechanism is that the "
                "assessment author cannot see the practice, the scenes or the "
                "script — RC-Q9g is what happens when it can. The user turn is "
                "built in code by `design_core.assessment_call.build_user_message` "
                "from three arguments, and this template must stay a static role "
                "prompt."
            )
        if "{{" in text or "{%" in text.replace("{#", "").replace("#}", ""):
            # A comment block is fine; a statement or an expression is not.
            import re as _re

            body = _re.sub(r"\{#.*?#\}", "", text, flags=_re.S)
            if "{{" in body or "{%" in body:
                _fail(
                    f"{prompt_type}: the template contains Jinja statements or "
                    "expressions outside its comment header. It is a STATIC role "
                    "prompt by design — every fact call 2 receives is assembled "
                    "in code, where what it does not include is auditable."
                )

    if prompt_type == "transcript_refinement_system":
        uploaded = _JINJA.from_string(text).render(
            learning_outcomes="", source_kind="uploaded")
        generated = _JINJA.from_string(text).render(
            learning_outcomes="", source_kind="generated")
        if "Flesch-Kincaid" in uploaded:
            _fail(
                f"{prompt_type}: the UPLOADED branch still carries the "
                "refine-for-readability instructions. Extraction replaces "
                "rewriting for a finished script; that is Task 2's whole claim."
            )
        if "COPIED CHARACTER FOR CHARACTER" in generated:
            _fail(
                f"{prompt_type}: the GENERATED branch has been turned into an "
                "extractor. Task 2 keeps that path's behaviour unchanged."
            )


async def _publish() -> int:
    async with async_session_factory() as session:
        for prompt_type, filename, phrases, note in TARGETS:
            path = SEED / filename
            if not path.exists():
                _fail(f"{prompt_type}: template not found at {path}")
            text = path.read_text(encoding="utf-8")
            _gate(prompt_type, text, phrases)

            rows = (await session.execute(
                select(Prompt)
                .where(Prompt.prompt_type == prompt_type,
                       Prompt.project_id.is_(None))
                .order_by(Prompt.version.desc())
            )).scalars().all()

            active = [r for r in rows if r.is_active]
            if len(active) > 1:
                _fail(
                    f"{prompt_type}: {len(active)} active global rows. Exactly "
                    "one row may be active; refusing to add a third truth."
                )
            if active and _sha(active[0].prompt_text) == _sha(text):
                print(
                    f"  {prompt_type}: v{active[0].version} is already this "
                    "exact text — no-op, nothing published."
                )
                continue

            for row in active:
                row.is_active = False
            version = (rows[0].version + 1) if rows else 1
            session.add(Prompt(
                prompt_type=prompt_type,
                prompt_text=text,
                version=version,
                is_active=True,
                is_library_template=False,
                created_by="wp-ivgs-12-design-core",
                change_note=note,
            ))
            await session.flush()
            print(
                f"  {prompt_type}: published v{version} "
                f"({len(text)} chars, sha256 {_sha(text)[:16]}…)"
                + (f", superseding v{active[0].version}" if active else "")
            )
        await session.commit()
    return 0


if __name__ == "__main__":
    print("WP-IVGS-12 — publishing the two SYSTEM prompts into their lineage")
    sys.exit(asyncio.run(_publish()))
