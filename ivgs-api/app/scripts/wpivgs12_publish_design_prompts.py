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
